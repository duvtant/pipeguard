"""Data loader facts and feature rules: no lookahead, no cross-unit leakage, incremental == full, NaNs."""
import numpy as np
import pandas as pd

from core.features import build_features, feature_names, latest_features
from core.sensors import SENSORS
from ml.data_io import load_test, load_test_rul, load_train


def test_loader_facts():
    tr, te, rul = load_train(), load_test(), load_test_rul()
    assert tr["unit"].nunique() == 100 and len(tr) == 20631
    life = tr.groupby("unit")["cycle"].max()
    assert (life.min(), life.median(), life.max()) == (128, 199, 362)
    assert te["unit"].nunique() == 100 and len(te) == 13096
    assert len(rul) == 100
    assert tr.columns.str.startswith("Unnamed").sum() == 0 and not tr[SENSORS].isna().any().any()
    assert (tr["rul_capped"] <= 125).all() and (tr.groupby("unit")["rul_true"].min() == 0).all()


def _two_units(train_df):
    return train_df[train_df["unit"].isin([1, 2])].reset_index(drop=True)


def test_no_lookahead(train_df):
    df = _two_units(train_df)
    base = build_features(df, unit_col="unit")
    t = 50  # change every reading of unit 1 after cycle 50
    mod = df.copy()
    future = (mod["unit"] == 1) & (mod["cycle"] > t)
    mod.loc[future, SENSORS] = mod.loc[future, SENSORS] * 3 + 100
    got = build_features(mod, unit_col="unit")
    past = ((df["unit"] == 1) & (df["cycle"] <= t)).to_numpy()
    pd.testing.assert_frame_equal(base[past], got[past])


def test_no_cross_unit_leakage(train_df):
    df = _two_units(train_df)
    both = build_features(df, unit_col="unit")
    alone = build_features(df[df["unit"] == 2], unit_col="unit")
    np.testing.assert_array_equal(both[df["unit"].to_numpy() == 2][feature_names()].to_numpy(),
                                  alone[feature_names()].to_numpy())


def test_incremental_equals_full_history(train_df):
    """The live path (newest row only) is bitwise identical to the training path, NaNs included."""
    df = train_df[train_df["unit"].isin([3, 7, 11])].reset_index(drop=True).copy()
    rng = np.random.default_rng(0)
    vals = df[SENSORS].to_numpy()
    vals[rng.random(vals.shape) < 0.08] = np.nan
    vals[(df["unit"] == 7).to_numpy() & (df["cycle"] > 40).to_numpy(), 2] = np.nan  # a dead sensor
    df[SENSORS] = vals
    full = build_features(df, unit_col="unit")
    for t in (1, 2, 3, 9, 10, 21, 60, 120):
        hist, cyc, rows = [], [], []
        for u in (3, 7, 11):
            m = ((df["unit"] == u) & (df["cycle"] <= t)).to_numpy()
            hist.append(df.loc[m, SENSORS].to_numpy())
            cyc.append(t)
            rows.append(np.flatnonzero(m)[-1])
        live = latest_features(hist, cyc)
        np.testing.assert_array_equal(live, full.loc[rows, feature_names()].to_numpy())


def test_nan_handling(train_df):
    df = train_df[train_df["unit"] == 1].reset_index(drop=True).copy()
    df.loc[10:40, "s3"] = np.nan               # 31 missing readings: windows go fully NaN
    f = build_features(df, unit_col="unit")
    assert np.isnan(f.loc[35, "s3_m20"]) and np.isnan(f.loc[35, "s3_sl10"])
    assert np.isfinite(f.loc[35, "s3_ewm10"])  # EWM keeps its memory
    assert np.isfinite(f.loc[35, "s4_m20"])     # other sensors unaffected
    assert np.isfinite(f.loc[43, "s3_m5"]) and np.isnan(f.loc[42, "s3_sl10"])  # slope needs 3 valid points
    assert np.isfinite(f.loc[43, "s3_sl10"])
    assert f.loc[0, "history_len"] == 1 and f["history_len"].iloc[-1] == len(df)
    assert np.isnan(f.loc[0, "s3_sl10"]) and f.loc[0, "s3_m20"] == df.loc[0, "s3"]
