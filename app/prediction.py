"""
Failure-risk predictions from the MLflow "champion" model.

The model is loaded ONCE (first request) and kept in memory, like a chef who reads the
recipe once and then cooks many bowls. If no model has been trained yet, the endpoints
answer 503 with a clear message instead of crashing.
"""

from functools import lru_cache

import mlflow
import mlflow.sklearn
import pandas as pd
from fastapi import APIRouter, HTTPException
from mlflow.tracking import MlflowClient
from pydantic import BaseModel

from ml.config import CHAMPION_ALIAS, MLFLOW_TRACKING_URI, MODEL_NAME, PROCESSED_DIR

router = APIRouter(prefix="/scania", tags=["predictive maintenance"])


class FailureRisk(BaseModel):
    vehicle_id: int
    failure_probability: float
    at_risk: bool                 # probability >= the threshold chosen on validation data
    model_name: str
    model_version: str


@lru_cache(maxsize=1)
def load_champion():
    """Load the champion model, its threshold, and the scored trucks' features."""
    mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
    client = MlflowClient()
    version = client.get_model_version_by_alias(MODEL_NAME, CHAMPION_ALIAS)
    model = mlflow.sklearn.load_model(f"models:/{MODEL_NAME}@{CHAMPION_ALIAS}")
    threshold = float(client.get_run(version.run_id).data.params["threshold"])
    features = pd.read_parquet(PROCESSED_DIR / "test_features.parquet").set_index("vehicle_id")
    return model, threshold, str(version.version), features


def get_champion():
    try:
        return load_champion()
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="No trained model available yet. Run: python -m ml.train",
        )


@router.get("/vehicles")
def list_scored_vehicles(limit: int = 20):
    """IDs of trucks we can score (the Scania test trucks)."""
    _, _, _, features = get_champion()
    return {"vehicle_ids": features.index[:limit].tolist(), "total": len(features)}


@router.get("/vehicles/{vehicle_id}/failure-risk", response_model=FailureRisk)
def failure_risk(vehicle_id: int):
    """Probability that Component X fails within the next 48 time steps."""
    model, threshold, version, features = get_champion()
    if vehicle_id not in features.index:
        raise HTTPException(status_code=404, detail=f"Truck {vehicle_id} not found")
    row = features.loc[[vehicle_id]]
    proba = float(model.predict_proba(row)[:, 1][0])
    return FailureRisk(
        vehicle_id=vehicle_id,
        failure_probability=round(proba, 4),
        at_risk=proba >= threshold,
        model_name=MODEL_NAME,
        model_version=version,
    )
