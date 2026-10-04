"""PostgreSQL implementation of engine.store.Store (techstack section 10 schema).

Owner: Olise (interim). Ebube's core/db.py helpers were not available when this was written, so the SQL
lives here, in one file. Table and column names follow techstack section 10. Optional columns that the
contract needs but section 10 does not list (predictions.data_source / top_sensors / sensor_issue /
display_status, events.title / detail / severity) are written only if the table has them; otherwise
title/detail/severity go into events.payload. Swap the internals for core/db.py helpers when they land.

The plan write runs under pg_advisory_xact_lock(PLAN_LOCK_KEY): the API must take the SAME lock around
"read state, build plan, write plan" after a voice constraint.
"""
from __future__ import annotations

import contextlib
import json
import os
import select
from typing import Callable

import pandas as pd
import psycopg
from psycopg.rows import dict_row

from core.contracts import STATIONS, Capacity, Constraint, EventDraft, PlanItem, PlanResult, QualityFlag, VerdictRecord, station_of
from core.sensors import SENSORS
from engine.pipeline import UnitInfo
from engine.store import PredictionRow, SimState

PLAN_LOCK_KEY = 4_242_001   # shared with the API (re-plan after a voice constraint)


def _dsn(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://")


class PgStore:
    def __init__(self, database_url: str):
        self.dsn = _dsn(database_url)
        self.conn = psycopg.connect(self.dsn, autocommit=True, row_factory=dict_row)
        self._cols: dict[str, set[str]] = {}

    def cols(self, table: str) -> set[str]:
        if table not in self._cols:
            rows = self.conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,)).fetchall()
            self._cols[table] = {r["column_name"] for r in rows}
        return self._cols[table]

    # ---- reads -------------------------------------------------------------------------------
    def get_sim_state(self) -> SimState:
        r = self.conn.execute("SELECT sim_day, epoch, status FROM sim_state WHERE id = 1").fetchone()
        return SimState(sim_day=int(r["sim_day"]), epoch=int(r["epoch"] or 0), status=r["status"])

    def get_engine_params(self) -> tuple[float, int]:
        r = self.conn.execute("SELECT threshold, horizon_days FROM engine_params WHERE id = 1").fetchone()
        if not r:
            return 0.5, int(os.environ.get("HORIZON_DAYS", 14))
        return float(r["threshold"]), int(r["horizon_days"])

    def get_capacity(self) -> Capacity:
        return Capacity(crews_per_station=int(os.environ.get("CREWS_PER_STATION", 2)))

    def get_units(self) -> list[UnitInfo]:
        rows = self.conn.execute("SELECT id, source_engine, life_start_day, status FROM units ORDER BY id").fetchall()
        return [UnitInfo(unit_id=r["id"], station_code=station_of(r["id"]), source_engine=int(r["source_engine"]),
                         life_start_day=int(r["life_start_day"]), failed=(r["status"] == "failed")) for r in rows]

    def get_readings(self, after_day: int, upto_day: int) -> pd.DataFrame:
        cols = ", ".join(SENSORS)
        rows = self.conn.execute(
            f"SELECT unit_id, sim_day, {cols} FROM readings WHERE sim_day > %s AND sim_day <= %s ORDER BY unit_id, sim_day",
            (after_day, upto_day)).fetchall()
        df = pd.DataFrame(rows, columns=["unit_id", "sim_day", *SENSORS])
        df[SENSORS] = df[SENSORS].astype(float)
        return df

    def get_prediction_history(self, unit_id: str, from_day: int, before_day: int) -> list[PredictionRow]:
        rows = self.conn.execute(
            "SELECT unit_id, sim_day, rul_low, rul_likely, rul_high, p_fail_h, confidence, status, reason, model_version "
            "FROM predictions WHERE unit_id = %s AND sim_day >= %s AND sim_day < %s ORDER BY sim_day",
            (unit_id, from_day, before_day)).fetchall()
        return [PredictionRow(**r) for r in rows]

    def get_constraints(self, today: int) -> list[Constraint]:
        rows = self.conn.execute("SELECT unit_id, earliest_day, technician_id, note FROM constraints WHERE earliest_day >= %s",
                                 (today,)).fetchall()
        return [Constraint(unit_id=r["unit_id"], earliest_day=int(r["earliest_day"]), technician_id=r["technician_id"],
                           note=r["note"] or "") for r in rows]

    def get_verdicts(self) -> list[VerdictRecord]:
        rows = self.conn.execute("SELECT id, unit_id, technician_id, verdict, sim_day FROM feedback ORDER BY id").fetchall()
        return [VerdictRecord(**r) for r in rows]

    # ---- writes ------------------------------------------------------------------------------
    def upsert_predictions(self, rows: list[PredictionRow]) -> None:
        if not rows:
            return
        base = ["unit_id", "sim_day", "rul_low", "rul_likely", "rul_high", "p_fail_h", "confidence", "status", "reason", "model_version"]
        extra = [c for c in ("data_source", "top_sensors", "sensor_issue", "display_status") if c in self.cols("predictions")]
        cols = base + extra
        upd = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols[2:])
        sql = (f"INSERT INTO predictions ({', '.join(cols)}) VALUES ({', '.join(['%s'] * len(cols))}) "
               f"ON CONFLICT (unit_id, sim_day) DO UPDATE SET {upd}")
        data = []
        for r in rows:
            d = r.__dict__.copy()
            if "top_sensors" in extra:
                d["top_sensors"] = json.dumps(r.top_sensors)
            data.append(tuple(d[c] for c in cols))
        with self.conn.cursor() as cur:
            cur.executemany(sql, data)

    def upsert_quality_flags(self, flags: list[QualityFlag]) -> tuple[list[QualityFlag], list[QualityFlag]]:
        """One row per episode keyed (unit_id, sensor, flag_type, sim_day). Returns (created, newly resolved)."""
        new, resolved = [], []
        with self.conn.transaction():
            for f in flags:
                r = self.conn.execute("SELECT id, resolved_day FROM quality_flags WHERE unit_id=%s AND sensor=%s AND flag_type=%s AND sim_day=%s",
                                      (f.unit_id, f.sensor, f.flag_type, f.sim_day)).fetchone()
                if r is None:
                    self.conn.execute("INSERT INTO quality_flags (unit_id, sim_day, sensor, flag_type, resolved_day) VALUES (%s,%s,%s,%s,%s)",
                                      (f.unit_id, f.sim_day, f.sensor, f.flag_type, f.resolved_day))
                    new.append(f)
                    if f.resolved_day is not None:
                        resolved.append(f)
                elif r["resolved_day"] != f.resolved_day:
                    self.conn.execute("UPDATE quality_flags SET resolved_day=%s WHERE id=%s", (f.resolved_day, r["id"]))
                    if r["resolved_day"] is None and f.resolved_day is not None:
                        resolved.append(f)
        return new, resolved

    def _technicians(self) -> dict[str, list[int]]:
        """station code -> technician ids (primary before backup). stations.id may be the code or a number."""
        order = "t.is_backup, t.id" if "is_backup" in self.cols("technicians") else "t.id"
        rows = self.conn.execute(
            f"SELECT t.id, t.station_id, s.name FROM technicians t LEFT JOIN stations s ON s.id = t.station_id ORDER BY {order}"
        ).fetchall()
        by_name = {name: code for code, name in STATIONS.items()}
        out: dict[str, list[int]] = {}
        for r in rows:
            code = str(r["station_id"]) if str(r["station_id"]) in STATIONS else by_name.get(r["name"] or "", "")
            out.setdefault(code, []).append(int(r["id"]))
        return out

    def replan(self, build: Callable[[list[PlanItem]], PlanResult], sim_day: int) -> PlanResult:
        with self.conn.transaction():
            self.conn.execute("SELECT pg_advisory_xact_lock(%s)", (PLAN_LOCK_KEY,))
            rows = self.conn.execute(
                "SELECT unit_id, planned_day, expected_saving, reason, state FROM plan_items "
                "WHERE state IN ('planned', 'needs_manager_decision') AND planned_day >= %s", (sim_day,)).fetchall()
            previous = [PlanItem(unit_id=r["unit_id"], station_code=station_of(r["unit_id"]), planned_day=int(r["planned_day"]),
                                 crew=0, expected_saving=float(r["expected_saving"] or 0), reason=r["reason"] or "",
                                 state=r["state"]) for r in rows]
            result = build(previous)
            if not result.changed and len(previous) == len(result.items):
                return result
            techs = self._technicians()
            self.conn.execute("DELETE FROM plan_items WHERE state IN ('planned', 'needs_manager_decision') AND planned_day >= %s", (sim_day,))
            for it in result.items:
                pool = techs.get(it.station_code) or []
                tech = pool[it.crew] if it.crew < len(pool) else None
                self.conn.execute(
                    "INSERT INTO plan_items (unit_id, planned_day, technician_id, expected_saving, reason, state) VALUES (%s,%s,%s,%s,%s,%s)",
                    (it.unit_id, it.planned_day, tech, it.expected_saving, it.reason, it.state))
        return result

    def write_events(self, events: list[EventDraft]) -> list[int]:
        cols = self.cols("events")
        ids = []
        with self.conn.transaction():
            for e in events:
                payload = dict(e.payload)
                fields = {"sim_day": e.sim_day, "type": e.type, "unit_id": e.unit_id}
                for k in ("title", "detail", "severity"):
                    if k in cols:
                        fields[k] = getattr(e, k)
                    else:
                        payload[k] = getattr(e, k)
                fields["payload"] = json.dumps(payload)
                names = ", ".join(fields)
                r = self.conn.execute(f"INSERT INTO events ({names}) VALUES ({', '.join(['%s'] * len(fields))}) RETURNING id",
                                      tuple(fields.values())).fetchone()
                ids.append(int(r["id"]))
            for i in ids:
                self.conn.execute("SELECT pg_notify('ui_event', %s)", (str(i),))
        return ids

    def after_tick(self, sim_day: int) -> None:
        """Alert policy hook. Ebube's core/alerts.py owns call decisions; call it if it exposes on_engine_tick."""
        try:
            from core import alerts
        except Exception:  # noqa: BLE001
            return
        hook = getattr(alerts, "on_engine_tick", None)
        if callable(hook):
            hook(sim_day)

    # ---- LISTEN ------------------------------------------------------------------------------
    @contextlib.contextmanager
    def listener(self, channel: str):
        """Dedicated autocommit connection. Yields wait(timeout) which returns after a notify or the timeout."""
        conn = psycopg.connect(self.dsn, autocommit=True)
        try:
            conn.execute(f"LISTEN {channel}")

            def wait(timeout: float = 1.0) -> bool:
                got = False
                if select.select([conn.fileno()], [], [], timeout)[0]:
                    for _ in conn.notifies(timeout=0, stop_after=1000):
                        got = True
                return got
            yield wait
        finally:
            conn.close()
