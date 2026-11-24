"""
Turn the raw Scania files into a model-ready table (features + label).

Raw files (per split: train / validation / test):
  *_operational_readouts.csv  one row per (vehicle_id, time_step): ~105 anonymised sensor
                              counters and histogram bins. Values ACCUMULATE over time.
  *_specifications.csv        one row per vehicle: Spec_0..Spec_7 (categories like "Cat3")
  train_tte.csv               one row per train vehicle: length_of_study_time_step,
                              in_study_repair (1 = Component X was repaired at the end)
  validation_labels.csv       one row per validation vehicle: class_label 0-4 for its LAST
                              readout (0 = failure more than 48 steps away, 1-4 = closer)

What we build for each chosen readout ("snapshot"):
  - the sensor values at that moment            (how much the truck has been used)
  - the change since the previous readout       (how fast it is being used right now)
  - the truck's specifications                  (what kind of truck it is)
  - time_step                                   (how far into its life the truck is)
  - label: 1 if Component X fails within HORIZON steps, else 0
"""

import numpy as np
import pandas as pd

from ml.config import HORIZON, RANDOM_SEED, SNAPSHOTS_PER_VEHICLE, SCANIA_DIR

ID_COLS = ["vehicle_id", "time_step"]
SPEC_COLS = [f"Spec_{i}" for i in range(8)]


# --------------------------------------------------------------------------- loading
def load_readouts(split, data_dir=SCANIA_DIR):
    """Read one split's readouts. float32 halves the memory (the train file is ~1 GB)."""
    path = data_dir / f"{split}_operational_readouts.csv"
    header = pd.read_csv(path, nrows=0).columns
    dtypes = {c: "float32" for c in header if c not in ID_COLS}
    df = pd.read_csv(path, dtype=dtypes)
    return df.sort_values(ID_COLS).reset_index(drop=True)


def load_specs(split, data_dir=SCANIA_DIR):
    return pd.read_csv(data_dir / f"{split}_specifications.csv")


def load_tte(data_dir=SCANIA_DIR):
    return pd.read_csv(data_dir / "train_tte.csv")


def load_labels(split, data_dir=SCANIA_DIR):
    return pd.read_csv(data_dir / f"{split}_labels.csv")


# --------------------------------------------------------------------------- features
def sensor_columns(readouts):
    return [c for c in readouts.columns if c not in ID_COLS]


def add_change_features(readouts):
    """
    Counters only go up, so the CHANGE since the previous readout says how hard the
    truck is working right now. First readout of each truck -> change = NaN (unknown).
    """
    cols = sensor_columns(readouts)
    diffs = readouts.groupby("vehicle_id")[cols].diff()
    diffs.columns = [f"{c}__delta" for c in cols]
    steps = readouts.groupby("vehicle_id")["time_step"].diff().rename("time_step__delta")
    return pd.concat([readouts, diffs, steps], axis=1)


def encode_specs(specs):
    """'Cat12' -> 12. The model treats these columns as categories, not numbers."""
    out = specs.copy()
    for c in SPEC_COLS:
        out[c] = out[c].astype(str).str.replace("Cat", "", regex=False).astype("int16")
    return out


def feature_columns(table):
    return [c for c in table.columns if c not in ("vehicle_id", "label")]


# --------------------------------------------------------------------------- labels
def label_train_readouts(readouts, tte, horizon=HORIZON):
    """
    For every train readout: how many steps until the end of that truck's study?
    If the truck WAS repaired at the end and the repair is <= horizon steps away -> label 1.
    Trucks never repaired in the study are 0 everywhere (no failure observed).
    """
    df = readouts.merge(tte, on="vehicle_id", how="inner")
    steps_left = df["length_of_study_time_step"] - df["time_step"]
    label = ((df["in_study_repair"] == 1) & (steps_left <= horizon)).astype("int8").rename("label")
    # concat (instead of df["label"] = ...) keeps the wide table in one memory block = faster
    return pd.concat([df.drop(columns=["length_of_study_time_step", "in_study_repair"]), label], axis=1)


def sample_snapshots(df, per_vehicle=SNAPSHOTS_PER_VEHICLE, seed=RANDOM_SEED):
    """
    Pick a few random readouts per truck (not only the last one), and always keep some
    readouts close to a failure, which are rare and the most important to learn from.
    Trick: give every row a random number, sort by it, and take the first N per truck.
    """
    rng = np.random.default_rng(seed)
    shuffled = df.assign(_random=rng.random(len(df))).sort_values(["vehicle_id", "_random"])
    random_pick = shuffled.groupby("vehicle_id").head(per_vehicle)
    near_failure = shuffled[shuffled["label"] == 1].groupby("vehicle_id").head(per_vehicle)
    both = pd.concat([random_pick, near_failure]).drop_duplicates(subset=ID_COLS)
    return both.drop(columns="_random").sort_values(ID_COLS)


# --------------------------------------------------------------------------- tables
def build_train_table(data_dir=SCANIA_DIR):
    readouts = add_change_features(load_readouts("train", data_dir))
    labelled = label_train_readouts(readouts, load_tte(data_dir))
    snapshots = sample_snapshots(labelled)
    table = snapshots.merge(encode_specs(load_specs("train", data_dir)), on="vehicle_id", how="left")
    return table.reset_index(drop=True)


def build_last_readout_table(split, data_dir=SCANIA_DIR, with_labels=True):
    """Validation / test: one row per truck, its LAST readout (what we'd score today)."""
    readouts = add_change_features(load_readouts(split, data_dir))
    last = readouts.groupby("vehicle_id").tail(1)
    table = last.merge(encode_specs(load_specs(split, data_dir)), on="vehicle_id", how="left")
    if with_labels:
        labels = load_labels(split, data_dir)
        # class 0 = failure more than 48 steps away; classes 1-4 = within 48 -> positive
        labels["label"] = (labels["class_label"] > 0).astype("int8")
        table = table.merge(labels[["vehicle_id", "label"]], on="vehicle_id", how="inner")
    return table.reset_index(drop=True)
