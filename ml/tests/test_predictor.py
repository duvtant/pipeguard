"""Predictor: live replay equals the cross-fitted predictions; ordering; masking; folds; fallback; dead sensors."""
import json

import numpy as np
import pandas as pd
import pytest

from core.contracts import unit_id_for_engine
from core.features import feature_names
from core.predict import N_FOLDS, Predictor
from core.sensors import SENSORS
from engine.pipeline import FleetPipeline, UnitInfo
from ml.data_io import ARTIFACTS
from ml.train import make_folds


def test_folds_grouped_by_engine(oof):
    fmap = json.loads((ARTIFACTS / "unit_fold_map.json").read_text())
    assert len(fmap) == 100
    sizes = pd.Series(fmap).value_counts()
    assert sorted(sizes.tolist()) == [20] * N_FOLDS
    per_engine = oof.groupby("source_engine")["fold"].nunique()
    assert (per_engine == 1).all()                              # no engine in two folds
    assert {int(k): v for k, v in fmap.items()} == make_folds(np.arange(1, 101))
    assert (oof.groupby("source_engine")["fold"].first().to_dict() == {int(k): v for k, v in fmap.items()})


def test_live_replay_matches_oof(predictor, oof, train_df):
    """Open question 9: backfill + day-by-day live path == oof_predictions.parquet on clean data."""
    for engine, offset in ((1, 50), (37, 5), (81, 120)):
        g = train_df[train_df["unit"] == engine]
        vals = g[SENSORS].to_numpy(dtype=float)
        uid = unit_id_for_engine(engine)
        info = UnitInfo(unit_id=uid, station_code=uid[:3], source_engine=engine, life_start_day=1 - offset)
        pipe = FleetPipeline(predictor)
        pipe.add_readings(uid, info.life_start_day, np.arange(1 - offset, 1), vals[:offset])
        got = []
        for d in range(0, len(vals) - offset + 1):
            if d > 0:
                pipe.add_readings(uid, info.life_start_day, [d], vals[offset + d - 1][None, :])
            r = pipe.process_day(d, [info], 0.5, 14, with_explain=False).units[0]
            got.append((r.cycle, r.prediction.rul_low, r.prediction.rul_likely, r.prediction.rul_high))
        got = pd.DataFrame(got, columns=["cycle", "rul_low", "rul_likely", "rul_high"]).set_index("cycle")
        exp = oof[oof["source_engine"] == engine].set_index("cycle").loc[got.index, ["rul_low", "rul_likely", "rul_high"]]
        np.testing.assert_allclose(got.to_numpy(), exp.to_numpy(), rtol=0, atol=1e-9)


def _feature_frame(train_df, engine, upto):
    from core.features import build_features
    g = train_df[train_df["unit"] == engine].iloc[:upto].copy()
    f = build_features(g, unit_col="unit").tail(1).copy()
    f.insert(0, "unit_id", unit_id_for_engine(engine))
    f["source_engine"] = engine
    f["sim_day"] = 0
    return f


def test_quantiles_ordered_and_masking(predictor, train_df):
    f = _feature_frame(train_df, 10, 150)
    clean = predictor.predict(f)[0]
    assert clean.rul_low <= clean.rul_likely <= clean.rul_high and clean.confidence == "normal"
    masked = predictor.predict(f, {f["unit_id"].iloc[0]: ["s4"]})[0]
    assert masked.confidence == "low" and masked.rul_likely == pytest.approx(clean.rul_likely)
    assert masked.rul_high - masked.rul_likely == pytest.approx(1.2 * (clean.rul_high - clean.rul_likely))
    exp_low = max(0.0, clean.rul_likely - 1.2 * (clean.rul_likely - clean.rul_low))
    assert masked.rul_low == pytest.approx(exp_low)
    young = predictor.predict(_feature_frame(train_df, 10, 12))[0]
    assert young.confidence == "low"                             # history_len < 20


def test_routes_to_the_fold_that_never_saw_the_engine(predictor, oof):
    for e in (3, 50, 99):
        assert predictor.fold_for(e) == int(oof.loc[oof["source_engine"] == e, "fold"].iloc[0])


def test_fallback_switch_for_one_bad_unit(predictor, train_df, oof):
    f = pd.concat([_feature_frame(train_df, 10, 150), _feature_frame(train_df, 11, 100)], ignore_index=True)
    f.loc[1, "source_engine"] = 999                               # unknown engine -> its model lookup fails
    out = predictor.predict(f)
    assert out[0].data_source == "live" and out[1].data_source == "fallback" and out[1].confidence == "low"
    assert len(out) == 2                                           # the fleet keeps going


def test_fallback_table_exists_and_covers_scenario():
    fb = pd.read_parquet(ARTIFACTS / "fallback" / "fallback_predictions.parquet")
    scen = json.loads((ARTIFACTS.parents[1] / "infra" / "scenario.json").read_text())
    assert set(fb["unit_id"]) == {u["unit_id"] for u in scen["units"]}
    assert (fb.groupby("unit_id")["sim_day"].min() == 0).all()
    assert (fb["rul_low"] <= fb["rul_likely"]).all() and (fb["rul_likely"] <= fb["rul_high"]).all()


def test_dead_sensor_bounded_drop(cfg):
    """Each single sensor dead from day 0 and from mid-life: no crash, bounded accuracy drop (test set)."""
    meta = json.loads((ARTIFACTS / "metadata.json").read_text())
    if "dead_sensor" not in meta:
        pytest.skip("run python -m ml.evaluate first")
    for row in meta["dead_sensor"]:
        for k in ("mae_dead_from_day0", "mae_dead_from_midlife"):
            assert np.isfinite(row[k]) and row[k] <= row["clean_mae"] * 1.6, row
