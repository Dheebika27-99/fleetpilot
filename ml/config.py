"""Settings for the Scania predictive-maintenance model."""

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCANIA_DIR = ROOT / "data" / "scania"           # unzip the Scania download here
PROCESSED_DIR = SCANIA_DIR / "processed"         # features we build are saved here

# MLflow keeps experiment runs + the model registry in a local SQLite file.
MLFLOW_TRACKING_URI = f"sqlite:///{ROOT / 'mlflow.db'}"
EXPERIMENT_NAME = "scania-component-x"
MODEL_NAME = "scania-failure-risk"
CHAMPION_ALIAS = "champion"                     # the version the API serves

# Prediction target: "will Component X fail within the next HORIZON time steps?"
# 48 = the widest warning window used in the Scania labels (classes 1-4 = within 48).
HORIZON = 48

# For training we take a few random moments ("snapshots") from each truck's history,
# so the model learns from early, middle and late readouts, like real life.
SNAPSHOTS_PER_VEHICLE = 5
RANDOM_SEED = 42
