"""
Train the Scania failure-risk model, track it in MLflow, and promote it if it's better.

Steps:
  1. build features + labels           (ml/features.py)
  2. baseline: always predict the average failure rate (the score to beat)
  3. train a gradient-boosted tree model (scikit-learn HistGradientBoosting,
     same family as LightGBM / XGBoost, no extra system libraries needed)
  4. evaluate on the VALIDATION trucks (never seen in training)
  5. log params, metrics and the model to MLflow; register a new model version
  6. promotion gate: the new version becomes "champion" only if its validation
     PR-AUC beats the current champion's
  7. final report on the TEST trucks + save test features for the API

Run:  python -m ml.train
See:  mlflow ui --backend-store-uri sqlite:///mlflow.db   -> http://localhost:5000
"""

import json

import mlflow
import mlflow.sklearn
import numpy as np
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient
from sklearn.dummy import DummyClassifier
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score

from ml.config import (CHAMPION_ALIAS, EXPERIMENT_NAME, HORIZON, MLFLOW_TRACKING_URI, MODEL_NAME,
                       PROCESSED_DIR, RANDOM_SEED, SNAPSHOTS_PER_VEHICLE)
from ml.features import SPEC_COLS, build_last_readout_table, build_train_table, feature_columns

PARAMS = {
    "learning_rate": 0.05,
    "max_iter": 400,
    "max_leaf_nodes": 31,
    "min_samples_leaf": 50,
    "l2_regularization": 1.0,
    "early_stopping": True,          # stops adding trees when an inner validation set stops improving
    "random_state": RANDOM_SEED,
}


def evaluate(y_true, proba, threshold=0.5):
    """
    ROC-AUC: can the model rank failing trucks above healthy ones? (0.5 = random)
    PR-AUC : same idea but focused on the rare failing trucks. Better for imbalanced data.
    precision / recall at a threshold: of the trucks we flag, how many really fail? /
                                       of the trucks that fail, how many did we flag?
    """
    pred = (proba >= threshold).astype(int)
    return {
        "roc_auc": float(roc_auc_score(y_true, proba)),
        "pr_auc": float(average_precision_score(y_true, proba)),
        "precision": float(precision_score(y_true, pred, zero_division=0)),
        "recall": float(recall_score(y_true, pred, zero_division=0)),
        "positive_rate": float(np.mean(y_true)),
    }


def best_threshold(y_true, proba):
    """Pick the threshold with the best F1 on validation (balance of precision and recall)."""
    best_t, best_f1 = 0.5, -1.0
    for t in np.linspace(0.05, 0.95, 91):
        pred = proba >= t
        tp = np.sum(pred & (y_true == 1))
        p = tp / max(pred.sum(), 1)
        r = tp / max((y_true == 1).sum(), 1)
        f1 = 0 if p + r == 0 else 2 * p * r / (p + r)
        if f1 > best_f1:
            best_t, best_f1 = round(float(t), 2), float(f1)
    return best_t


def current_champion_pr_auc(client):
    try:
        version = client.get_model_version_by_alias(MODEL_NAME, CHAMPION_ALIAS)
    except Exception:
        return None                      # no champion yet
    return client.get_run(version.run_id).data.metrics.get("val_pr_auc")


def main():
    print("1. Building features (this reads ~1.5 GB, give it a minute)...")
    train = build_train_table()
    val = build_last_readout_table("validation")
    test = build_last_readout_table("test")
    features = feature_columns(train)
    print(f"   train snapshots: {len(train):,} rows, {len(features)} features, "
          f"{train['label'].mean():.1%} positive")
    print(f"   validation trucks: {len(val):,} ({val['label'].mean():.1%} fail within {HORIZON} steps)")
    print(f"   test trucks:       {len(test):,}")

    X_train, y_train = train[features], train["label"].to_numpy()
    X_val, y_val = val[features], val["label"].to_numpy()
    X_test, y_test = test[features], test["label"].to_numpy()

    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    mlflow.set_experiment(EXPERIMENT_NAME)
    client = MlflowClient()

    # ---- 2. baseline (the score any real model must beat)
    with mlflow.start_run(run_name="baseline-prior"):
        dummy = DummyClassifier(strategy="prior").fit(X_train, y_train)
        base = evaluate(y_val, dummy.predict_proba(X_val)[:, 1])
        mlflow.log_metrics({f"val_{k}": v for k, v in base.items()})
    print(f"2. Baseline       val PR-AUC={base['pr_auc']:.3f}  ROC-AUC={base['roc_auc']:.3f}")

    # ---- 3-5. real model
    with mlflow.start_run(run_name="hist-gradient-boosting") as run:
        model = HistGradientBoostingClassifier(
            categorical_features=[features.index(c) for c in SPEC_COLS if c in features],
            class_weight="balanced",      # failures are rare: give them more weight
            **PARAMS,
        )
        model.fit(X_train, y_train)

        val_proba = model.predict_proba(X_val)[:, 1]
        threshold = best_threshold(y_val, val_proba)
        val_metrics = evaluate(y_val, val_proba, threshold)
        test_metrics = evaluate(y_test, model.predict_proba(X_test)[:, 1], threshold)

        mlflow.log_params({**PARAMS, "horizon_steps": HORIZON,
                           "snapshots_per_vehicle": SNAPSHOTS_PER_VEHICLE,
                           "n_features": len(features), "n_train_rows": len(train),
                           "threshold": threshold})
        mlflow.log_metrics({f"val_{k}": v for k, v in val_metrics.items()})
        mlflow.log_metrics({f"test_{k}": v for k, v in test_metrics.items()})
        mlflow.sklearn.log_model(
            model,
            artifact_path="model",
            # we trained this model ourselves, so the classic pickle format is safe here
            serialization_format=mlflow.sklearn.SERIALIZATION_FORMAT_CLOUDPICKLE,
            signature=infer_signature(X_val.head(100), val_proba[:100]),
            registered_model_name=MODEL_NAME,
        )
        new_version = client.search_model_versions(f"run_id='{run.info.run_id}'")[0].version

    print(f"3. Model          val PR-AUC={val_metrics['pr_auc']:.3f}  ROC-AUC={val_metrics['roc_auc']:.3f}  "
          f"precision={val_metrics['precision']:.2f} recall={val_metrics['recall']:.2f} @ {threshold:.2f}")
    print(f"   Test (final)   PR-AUC={test_metrics['pr_auc']:.3f}  ROC-AUC={test_metrics['roc_auc']:.3f}")

    # ---- 6. promotion gate
    old = current_champion_pr_auc(client)
    if old is None or val_metrics["pr_auc"] > old:
        client.set_registered_model_alias(MODEL_NAME, CHAMPION_ALIAS, new_version)
        print(f"4. Version {new_version} promoted to '{CHAMPION_ALIAS}' "
              f"(val PR-AUC {val_metrics['pr_auc']:.3f} vs previous {old if old is None else round(old, 3)})")
    else:
        print(f"4. Version {new_version} NOT promoted: val PR-AUC {val_metrics['pr_auc']:.3f} "
              f"<= champion {old:.3f}")

    # ---- 7. save what the API needs: test-truck features + the decision threshold
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    test[["vehicle_id"] + features].to_parquet(PROCESSED_DIR / "test_features.parquet", index=False)
    report = {"model_version": new_version, "threshold": threshold, "baseline_val": base,
              "val": val_metrics, "test": test_metrics}
    (PROCESSED_DIR / "last_training_report.json").write_text(json.dumps(report, indent=2))
    print("5. Saved test features + report to data/scania/processed/")


if __name__ == "__main__":
    main()
