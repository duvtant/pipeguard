"""API router: test mode, sensor faults you can toggle in front of a judge (techstack 11.2).

The simulator applies open faults to the readings; Olise's engine notices the bad sensor and writes the
sensor_issue event. This router only records the fault, so it never writes a second event.
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api.deps import require_admin
from core import reads
from core.db import session_scope
from core.sensors import SENSORS

router = APIRouter(prefix="/api/testmode", tags=["testmode"], dependencies=[Depends(require_admin)])
FAULT_TYPES = ("dead", "stuck", "spike", "out_of_range")
_COLS = "id, unit_id, sensor, type, start_day, end_day, source"


class FaultBody(BaseModel):
    unit_id: str
    sensor: str
    type: str


@router.get("/faults")
def list_faults():
    with session_scope() as s:
        return [dict(r) for r in s.execute(text(f"SELECT {_COLS} FROM faults WHERE end_day IS NULL ORDER BY id")).mappings()]


@router.post("/faults")
def add_fault(body: FaultBody):
    if body.sensor not in SENSORS or body.type not in FAULT_TYPES:
        raise HTTPException(422, "unknown sensor or fault type")
    with session_scope() as s:
        unit = s.execute(text("SELECT status FROM units WHERE id = :u"), {"u": body.unit_id}).first()
        if unit is None:
            raise HTTPException(422, "unknown unit")
        if unit[0] == "failed":
            return {"ok": True, "ignored": "unit already failed"}  # a failed unit has no readings to break
        s.execute(text("SELECT pg_advisory_xact_lock(hashtext(:k))"), {"k": f"fault:{body.unit_id}:{body.sensor}"})
        open_one = s.execute(text(f"SELECT {_COLS} FROM faults WHERE unit_id = :u AND sensor = :s AND end_day IS NULL"),
                             {"u": body.unit_id, "s": body.sensor}).mappings().first()
        if open_one:
            return dict(open_one)  # a second click leaves one open fault
        day = reads.sim_state(s)["sim_day"]
        return dict(s.execute(text(
            f"INSERT INTO faults (unit_id, sensor, type, start_day, source) VALUES (:u, :s, :t, :d, 'toggle') "
            f"RETURNING {_COLS}"), {"u": body.unit_id, "s": body.sensor, "t": body.type, "d": day}).mappings().one())


@router.delete("/faults/{fault_id}")
def end_fault(fault_id: int):
    with session_scope() as s:
        day = reads.sim_state(s)["sim_day"]
        s.execute(text("UPDATE faults SET end_day = :d WHERE id = :i AND end_day IS NULL"), {"d": day, "i": fault_id})
        row = s.execute(text(f"SELECT {_COLS} FROM faults WHERE id = :i"), {"i": fault_id}).mappings().first()
    if row is None:
        raise HTTPException(404, "unknown fault")
    return dict(row)  # ending an already ended fault is fine
