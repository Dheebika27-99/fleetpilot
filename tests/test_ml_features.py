"""
Unit tests for the feature + label logic, on a tiny hand-made dataset.
They don't need the real Scania download, so they can run anywhere (e.g. in CI).
"""

import pandas as pd

from ml.features import (add_change_features, encode_specs, label_train_readouts,
                         sample_snapshots)


def tiny_readouts():
    # two trucks; sensor "171_0" is a counter that only goes up
    return pd.DataFrame({
        "vehicle_id": [1, 1, 1, 2, 2],
        "time_step":  [10, 20, 60, 5, 15],
        "171_0":      [100.0, 150.0, 400.0, 10.0, 30.0],
    })


def test_change_features_are_differences_per_truck():
    df = add_change_features(tiny_readouts())
    assert pd.isna(df.loc[0, "171_0__delta"])          # first readout: nothing to compare
    assert df.loc[1, "171_0__delta"] == 50.0           # 150 - 100
    assert df.loc[2, "171_0__delta"] == 250.0          # 400 - 150
    assert pd.isna(df.loc[3, "171_0__delta"])          # new truck starts fresh
    assert df.loc[2, "time_step__delta"] == 40         # 60 - 20


def test_labels_only_near_a_real_repair():
    # truck 1 repaired at step 60; truck 2 never repaired (study ended at 15)
    tte = pd.DataFrame({"vehicle_id": [1, 2],
                        "length_of_study_time_step": [60, 15],
                        "in_study_repair": [1, 0]})
    labelled = label_train_readouts(tiny_readouts(), tte, horizon=48)
    by_step = dict(zip(zip(labelled.vehicle_id, labelled.time_step), labelled.label))
    assert by_step[(1, 10)] == 0      # 50 steps before repair -> outside 48-step window
    assert by_step[(1, 20)] == 1      # 40 steps before repair -> inside window
    assert by_step[(1, 60)] == 1      # at the repair
    assert by_step[(2, 15)] == 0      # never repaired -> never positive


def test_snapshots_keep_every_truck_and_failure_rows():
    tte = pd.DataFrame({"vehicle_id": [1, 2],
                        "length_of_study_time_step": [60, 15],
                        "in_study_repair": [1, 0]})
    labelled = label_train_readouts(tiny_readouts(), tte, horizon=48)
    snaps = sample_snapshots(labelled, per_vehicle=1)
    assert set(snaps.vehicle_id) == {1, 2}
    assert snaps["label"].sum() >= 1                    # positives are always kept


def test_specs_are_encoded_as_numbers():
    specs = pd.DataFrame({"vehicle_id": [1], **{f"Spec_{i}": [f"Cat{i}"] for i in range(8)}})
    out = encode_specs(specs)
    assert out.loc[0, "Spec_3"] == 3
