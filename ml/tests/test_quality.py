"""Quality checks: zero flags on clean engines, every fault type caught, masks, episodes, day-0 faults.

Thresholds come from core.quality.fit_thresholds on the training data (the same call train.py makes),
so these tests do not need the trained artifacts.
"""
import numpy as np
import pytest

from core.quality import CLEAR_AFTER, check_quality_arrays, fit_thresholds
from core.sensors import SENSORS


@pytest.fixture(scope="module")
def qcfg(train_df):
    return {"quality": fit_thresholds(train_df, SENSORS, unit_col="unit")}


def _unit(train_df, engine):
    g = train_df[train_df["unit"] == engine]
    return g[SENSORS].to_numpy(dtype=float), np.arange(len(g))


def _run(qcfg, h, uid="EDS-01"):
    return check_quality_arrays([h], [np.arange(len(h))], [uid], qcfg)


def test_zero_flags_on_all_clean_training_engines(train_df, qcfg):
    hs, ds, ids = [], [], []
    for e in range(1, 101):
        h, d = _unit(train_df, e)
        hs.append(h), ds.append(d), ids.append(f"E{e}")
    res = check_quality_arrays(hs, ds, ids, qcfg)
    assert res.flags == []
    for h, m in zip(hs, res.masked):
        np.testing.assert_array_equal(h, m)


def test_s17_low_resolution_repeats_are_not_stuck(qcfg):
    assert qcfg["quality"]["s17"]["max_natural_run"] >= 8          # integer-valued sensor repeats a lot
    assert qcfg["quality"]["s17"]["stuck_n"] > qcfg["quality"]["s17"]["max_natural_run"]


@pytest.mark.parametrize("engine,sensor", [(5, "s4"), (17, "s11"), (42, "s7"), (88, "s17"), (63, "s21")])
def test_each_fault_type_is_detected(train_df, qcfg, engine, sensor):
    h0, _ = _unit(train_df, engine)
    j = SENSORS.index(sensor)
    q = qcfg["quality"][sensor]
    start = 60

    dead = h0.copy(); dead[start:, j] = np.nan
    r = _run(qcfg, dead)
    f = [x for x in r.flags if x.flag_type == "sensor_offline"]
    assert len(f) == 1 and f[0].sim_day == start and f[0].resolved_day is None   # one episode, stays open
    assert sensor in r.masked_latest["EDS-01"] and r.flagged_latest["EDS-01"] == [sensor]

    stuck = h0.copy(); stuck[start:, j] = h0[start - 1, j]
    r = _run(qcfg, stuck)
    f = [x for x in r.flags if x.flag_type == "sensor_stuck"]
    assert len(f) == 1 and f[0].sim_day - start <= q["stuck_n"]
    detect = f[0].sim_day
    assert np.isnan(r.masked[0][detect:, j]).all()                 # masked from detection on
    assert not np.isnan(r.masked[0][:detect, j]).any()

    # A jump inside the physical range is a spike ...
    spike = h0.copy(); spike[start, j] = h0[start - 1, j] + 1.2 * q["spike_abs"] * (1 if h0[start - 1, j] < q["mean"] else -1)
    r = _run(qcfg, spike)
    f = [x for x in r.flags if x.flag_type == "sensor_spike"]
    assert len(f) == 1 and f[0].sim_day == start
    masked = np.isnan(r.masked[0][:, j])
    assert masked.sum() == 1 and masked[start]                      # only that reading
    assert f[0].resolved_day == start + CLEAR_AFTER                  # clears after 5 clean readings
    # ... and the simulator's 10 x std jump is caught too (as a spike, or out of range when it leaves the range).
    big = h0.copy(); big[start, j] += 10 * q["std"]
    r = _run(qcfg, big)
    assert [(x.flag_type in ("sensor_spike", "sensor_out_of_range"), x.sim_day) for x in r.flags] == [(True, start)]
    assert np.isnan(r.masked[0][:, j]).sum() == 1

    oor = h0.copy(); oor[start:start + 3, j] = q["hi"] + 5 * q["std"]
    r = _run(qcfg, oor)
    f = [x for x in r.flags if x.flag_type == "sensor_out_of_range"]
    assert len(f) == 1 and f[0].sim_day == start and f[0].resolved_day == start + 2 + CLEAR_AFTER
    assert np.isnan(r.masked[0][start:start + 3, j]).all()


def test_fault_from_day_zero(train_df, qcfg):
    h0, _ = _unit(train_df, 9)
    h = h0.copy(); h[:, 0] = np.nan; h[0:2, 1] = 1e6
    r = _run(qcfg, h)
    types = {(f.sensor, f.flag_type, f.sim_day) for f in r.flags}
    assert ("s2", "sensor_offline", 0) in types and ("s3", "sensor_out_of_range", 0) in types


def test_flag_episodes_resolve_and_reopen(train_df, qcfg):
    h0, _ = _unit(train_df, 12)
    h = h0.copy(); j = SENSORS.index("s9")
    h[30:33, j] = np.nan          # outage 1
    h[50:52, j] = np.nan          # outage 2, after it had cleared
    r = _run(qcfg, h)
    eps = [(f.sim_day, f.resolved_day) for f in r.flags if f.flag_type == "sensor_offline"]
    assert eps == [(30, 32 + CLEAR_AFTER), (50, 51 + CLEAR_AFTER)]
    h2 = h0.copy(); h2[30, j] = np.nan; h2[33, j] = np.nan   # second blank within the clean window: same episode
    r2 = _run(qcfg, h2)
    assert [(f.sim_day, f.resolved_day) for f in r2.flags] == [(30, 33 + CLEAR_AFTER)]


def test_recomputation_is_stable_day_to_day(train_df, qcfg):
    """Re-running on a longer history never changes an earlier episode's start (idempotent upserts)."""
    h0, _ = _unit(train_df, 20)
    h = h0.copy(); h[40:, 3] = np.nan
    starts = {tuple((f.sensor, f.flag_type, f.sim_day) for f in _run(qcfg, h[:t]).flags) for t in range(45, 80)}
    assert starts == {(("s7", "sensor_offline", 40),)}
