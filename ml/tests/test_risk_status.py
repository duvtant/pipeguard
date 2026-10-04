"""p_fail edge cases and the status state machine (confirmation, hysteresis, unreliable readings)."""
import numpy as np

from core.contracts import StatusState
from core.risk import CLEAR_READINGS, CONFIRM_READINGS, classify, classify_series, p_fail


def test_p_fail_anchor_points():
    assert abs(p_fail(10, 20, 40, 10) - 0.1) < 1e-9
    assert abs(p_fail(10, 20, 40, 20) - 0.5) < 1e-9
    assert abs(p_fail(10, 20, 40, 40) - 0.9) < 1e-9


def test_p_fail_monotone_in_horizon():
    h = np.arange(0, 200)
    p = p_fail(30, 50, 90, h)
    assert np.all(np.diff(p) >= 0) and p[0] == 0.0 and p[-1] == 1.0


def test_p_fail_falls_as_range_shifts_later():
    shifts = np.arange(0, 100)
    p = p_fail(10 + shifts, 30 + shifts, 60 + shifts, 14)
    assert np.all(np.diff(p) <= 0)


def test_p_fail_degenerate_and_edges():
    assert p_fail(20, 20, 20, 14) == 0.0 and p_fail(20, 20, 20, 25) == 1.0
    assert np.isfinite(p_fail(20, 20, 20, 20))
    assert p_fail(0, 0, 5, 0) == 1.0 and p_fail(-3, -1, 2, 14) == 1.0      # rul_likely <= 0
    assert 0.1 <= p_fail(0, 200, 10_000, 14) < 0.15                         # very wide range: finite, near q10
    assert 0.0 <= p_fail(1, 2, 3, 0) <= 1.0                                 # horizon 0
    assert p_fail(30, 20, 10, 14) == p_fail(10, 20, 30, 14)                 # crossed input is tolerated


def test_confirmation_needs_three_readings():
    st = StatusState()
    for i in range(CONFIRM_READINGS - 1):
        st = classify(0.7, 0.5, st)
        assert st.status == "watch"
    st = classify(0.7, 0.5, st)
    assert st.status == "at_risk"


def test_hysteresis_and_unreliable_readings():
    st = StatusState()
    for _ in range(3):
        st = classify(0.7, 0.5, st)
    assert st.status == "at_risk"
    st = classify(0.47, 0.5, st)               # below threshold but within hysteresis band: stays red
    assert st.status == "at_risk" and st.below_count == 0
    for _ in range(CLEAR_READINGS - 1):
        st = classify(0.3, 0.5, st)
        assert st.status == "at_risk"
    st = classify(0.3, 0.5, st, reliable=False)  # masked reading does not clear
    assert st.status == "at_risk"
    st = classify(0.3, 0.5, st)
    assert st.status == "watch"


def test_unreliable_readings_do_not_confirm():
    st = StatusState()
    for _ in range(10):
        st = classify(0.9, 0.5, st, reliable=False)
    assert st.status == "watch"
    st = classify(0.9, 0.5, st)
    st = classify(0.9, 0.5, st, reliable=False)   # breaks the streak
    st = classify(0.9, 0.5, st)
    st = classify(0.9, 0.5, st)
    assert st.status == "watch"
    st = classify(0.9, 0.5, st)
    assert st.status == "at_risk"


def test_healthy_watch_boundary_and_reset():
    assert classify(0.05, 0.5).status == "healthy"
    assert classify(0.10, 0.5).status == "watch"
    assert StatusState().status == "healthy"  # a unit whose life restarts begins healthy with no history


def test_classify_series_matches_scalar():
    rng = np.random.default_rng(1)
    p = np.clip(np.cumsum(rng.normal(0.01, 0.08, 120)), 0, 1)
    rel = rng.random(120) > 0.1
    series = classify_series(p, 0.5, rel)[0]
    st = StatusState()
    for t in range(120):
        st = classify(p[t], 0.5, st, bool(rel[t]))
        assert ("healthy", "watch", "at_risk")[series[t]] == st.status
