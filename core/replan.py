"""Rebuild the weekly plan after something changed outside the engine tick (a voice constraint).

This calls Olise's PgStore.replan, the SAME code the engine runs every tick: same plan-wide advisory lock,
same feedback urgency, same history handling. One implementation means the engine and a voice call can
never disagree and flip the plan back and forth.

It commits the caller's session first (the engine's store reads through its own connection and must see
the new constraint) and then runs on that connection.
"""
from __future__ import annotations

import os

from sqlmodel import Session

from core import app_settings
from core.config import get_settings

settings = get_settings()


def warm_up() -> None:
    """Import the engine modules (about 1.2 s, ~200 MB) at API start so the first voice call is fast."""
    from engine import pg_store, pipeline, worker
    return pg_store, pipeline, worker


def replan(s: Session, reason: str | None = None, emit: bool = True, source: str | None = None):
    """Returns Olise's PlanResult. Writes plan_items and, if the plan changed, one plan_changed event."""
    from core.contracts import PlanParams
    from core.feedback import urgency_multipliers
    from core.scheduler import build_plan, plan_units_from_rows
    from engine.pg_store import PgStore
    from engine.pipeline import plan_event
    from engine.worker import day_namer

    s.commit()
    st = PgStore(settings.database_url)
    try:
        sim_day = st.get_sim_state().sim_day
        _, horizon = st.get_engine_params()
        rows = [dict(r) for r in st.conn.execute(
            "SELECT DISTINCT ON (unit_id) unit_id, p_fail_h, status, rul_low FROM predictions "
            "WHERE sim_day <= %s ORDER BY unit_id, sim_day DESC", (sim_day,)).fetchall()]
        failed = {u.unit_id for u in st.get_units() if u.failed}
        units = plan_units_from_rows(rows, failed, urgency_multipliers(st.get_verdicts(), sim_day))
        app = app_settings.read_conn(st.conn)  # NOT the caller's session: it was committed above and may sit inside a transaction block
        params = PlanParams(cost_breakdown=app["cost_breakdown"], cost_service=app["cost_service"])
        result = st.replan(lambda previous: build_plan(units, st.get_capacity(), st.get_constraints(sim_day),
                                                        params, sim_day, previous, horizon_days=horizon), sim_day)
        if emit and result.changed:
            path = settings.scenario_path if os.path.exists(settings.scenario_path) else None
            ev = plan_event(result.changes, sim_day, day_namer(path))
            if ev:
                if reason:
                    ev = ev.model_copy(update={"detail": ev.detail.rstrip(".") + f" ({reason})."})
                if source:  # source=voice marks the moves a manager still has to approve
                    ev = ev.model_copy(update={"payload": {**ev.payload, "source": source}})
                st.write_events([ev])
        return result
    finally:
        st.conn.close()
