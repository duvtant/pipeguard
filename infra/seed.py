"""Seeds the demo company: stations, units, roster, planted faults, backfilled history.

Safe to rerun: wipes every table and reloads from scenario.json, so it doubles as the demo reset.
Same scenario + same ADMIN_TOKEN = same rows (phone-page slugs included), so rehearsals match the pitch.
Run from the repo root:  python infra/seed.py
"""
import hashlib
import hmac
import json
import sys
from pathlib import Path

import pandas as pd
import psycopg
from psycopg import sql
from sqlmodel import SQLModel

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # lets "core" import when this runs as a script

from core import models  # noqa: E402,F401  registers every table on SQLModel.metadata
from core.config import get_settings  # noqa: E402
from core.db import init_db, psycopg_dsn  # noqa: E402
from core.models import SENSOR_COLUMNS  # noqa: E402

# id, code, name, lat, lon. Same order as the contract's STATION_ORDER.
STATIONS = [
    (1, "EDS", "Edson", 53.58, -116.43),
    (2, "HIN", "Hinton", 53.40, -117.58),
    (3, "WHT", "Whitecourt", 54.14, -115.68),
    (4, "GPR", "Grande Prairie", 55.17, -118.80),
    (5, "DRH", "Drumheller", 51.46, -112.71),
]
STATION_ID = {code: sid for sid, code, *_ in STATIONS}

# id, name, station code, shift, language, is_backup. Fictional. Matches the mock API roster.
ROSTER = [
    (1, "Sam Whitford", "EDS", "day", "en", False), (2, "Priya Nair", "EDS", "night", "en", True),
    (3, "Marc Tremblay", "EDS", "day", "fr", False), (4, "Jordan Cardinal", "HIN", "day", "en", False),
    (5, "Aisha Bello", "HIN", "night", "en", True), (6, "Luc Gagnon", "WHT", "day", "fr", False),
    (7, "Dana Kowalski", "WHT", "night", "en", True), (8, "Chris Lavoie", "GPR", "day", "en", False),
    (9, "Mei Lin Zhao", "GPR", "night", "en", True), (10, "Tom Redcrow", "GPR", "day", "en", False),
    (11, "Elena Petrova", "DRH", "day", "en", False), (12, "Omar Haddad", "DRH", "night", "en", True),
]

FAULT_TYPES = {"dead", "stuck", "spike", "out_of_range"}
DEFAULT_THRESHOLD = 0.5  # until ml/tune runs and writes its own value (POST /api/admin/tune)
DEFAULT_HORIZON_DAYS = 14

# NASA C-MAPSS file layout: no header, 26 whitespace-separated columns.
RAW_COLUMNS = ["unit", "cycle", "setting1", "setting2", "setting3", *[f"s{i}" for i in range(1, 22)]]


def field_slug(tech_id: int, key: str) -> str:
    # Unguessable but stable: HMAC of the technician id. A reset keeps every phone link working.
    digest = hmac.new(key.encode(), f"field-{tech_id}".encode(), hashlib.sha256).hexdigest()
    return f"t-{digest[:10]}"


def load_scenario(path: Path) -> dict:
    if not path.exists():
        raise SystemExit(f"scenario file not found: {path} (set SCENARIO_PATH)")
    scenario = json.loads(path.read_text(encoding="utf-8"))
    ids = [u["unit_id"] for u in scenario["units"]]
    if len(ids) != len(set(ids)):
        raise SystemExit("scenario has duplicate unit ids")
    return scenario


def load_nasa() -> dict[int, pd.DataFrame]:
    path = ROOT / "ml" / "data" / "train_FD001.txt"
    if not path.exists():
        raise SystemExit(f"NASA data not found: {path}")
    df = pd.read_csv(path, sep=r"\s+", header=None, names=RAW_COLUMNS)
    # One frame per engine, in cycle order.
    return {int(e): g.sort_values("cycle") for e, g in df.groupby("unit")}


def reseed() -> dict:
    cfg = get_settings()
    scenario = load_scenario(Path(cfg.scenario_path))
    nasa = load_nasa()
    key = cfg.admin_token or "dev-only-slug-key"  # empty in dev, set in .env on the server
    init_db()  # creates any missing tables first

    # --- build everything in memory first, so a bad scenario fails before we touch the database ---
    unit_rows, reading_rows = [], []
    for u in scenario["units"]:
        uid, eng, offset = u["unit_id"], int(u["source_engine"]), int(u["start_offset"])
        code = uid.split("-")[0]
        if code not in STATION_ID or eng not in nasa:
            raise SystemExit(f"{uid}: unknown station code or NASA engine {eng}")
        last_cycle = int(nasa[eng]["cycle"].max())
        if not 1 <= offset < last_cycle:
            raise SystemExit(f"{uid}: start_offset {offset} must be in 1..{last_cycle - 1}")

        # cycle at sim_day d is d - life_start_day + 1, so sim_day 0 lands on cycle `offset`.
        life_start = 1 - offset
        unit_rows.append((uid, STATION_ID[code], eng, offset, life_start, "healthy", 0, 0, 0))

        # Backfill every cycle BEFORE the start point at negative sim_days (Olise's live == cross-fitted
        # test needs the full history). The simulator writes sim_day 0 onward on its ticks.
        hist = nasa[eng][nasa[eng]["cycle"] < offset]
        for cycle, *vals in hist[["cycle", *SENSOR_COLUMNS]].itertuples(index=False, name=None):
            reading_rows.append((uid, int(cycle) - offset, *[None if pd.isna(v) else float(v) for v in vals]))

    known = {r[0] for r in unit_rows}
    fault_rows = []
    for f in scenario.get("planted_faults", []):  # optional section in scenario.json
        if f["unit_id"] not in known or f["sensor"] not in SENSOR_COLUMNS or f["type"] not in FAULT_TYPES:
            raise SystemExit(f"bad planted fault: {f}")
        fault_rows.append((f["unit_id"], f["sensor"], f["type"], int(f["start_day"]), f.get("end_day"), "planted"))

    tech_rows = [(tid, name, STATION_ID[code], shift, lang, field_slug(tid, key), backup)
                 for tid, name, code, shift, lang, backup in ROSTER]

    with psycopg.connect(psycopg_dsn()) as conn:
        # 1) Pause and bump the epoch in its own commit, so a running simulator/engine drops in-flight work.
        conn.execute("UPDATE sim_state SET status = 'paused', epoch = epoch + 1 WHERE id = 1")
        conn.commit()

        # 2) Wipe and reload in ONE transaction: nobody ever reads a half-seeded database.
        row = conn.execute("SELECT epoch FROM sim_state WHERE id = 1").fetchone()
        epoch = row[0] if row else 0
        tables = [t.name for t in SQLModel.metadata.sorted_tables]  # every table, no hardcoded list
        # RESTART IDENTITY so ids start from 1 again and two seeds produce identical tables.
        conn.execute(sql.SQL("TRUNCATE TABLE {} RESTART IDENTITY CASCADE").format(
            sql.SQL(", ").join(sql.Identifier(t) for t in tables)))

        with conn.cursor() as cur:
            cur.executemany("INSERT INTO stations (id, code, name, lat, lon) VALUES (%s, %s, %s, %s, %s)", STATIONS)
            cur.executemany(
                "INSERT INTO units (id, station_id, source_engine, start_offset, life_start_day, status,"
                " serviced_count, above_count, below_count) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", unit_rows)
            cur.executemany(
                "INSERT INTO technicians (id, name, station_id, shift, language, field_page_id, is_backup)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s)", tech_rows)
            cur.execute(
                "INSERT INTO sim_state (id, sim_day, status, speed_seconds_per_day, scenario_id, epoch)"
                " VALUES (1, 0, 'paused', %s, %s, %s)",
                (float(scenario.get("speed_seconds_per_day", 1.0)), scenario["scenario_id"], epoch))
            cur.execute("INSERT INTO engine_params (id, threshold, horizon_days) VALUES (1, %s, %s)",
                        (DEFAULT_THRESHOLD, DEFAULT_HORIZON_DAYS))
            if fault_rows:
                cur.executemany(
                    "INSERT INTO faults (unit_id, sensor, type, start_day, end_day, source)"
                    " VALUES (%s, %s, %s, %s, %s, %s)", fault_rows)

            # Explicit ids above don't advance the sequences, so set them or the next insert collides.
            for table in ("stations", "technicians"):
                cur.execute(f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), (SELECT MAX(id) FROM {table}))")

            # COPY is far faster than row-by-row inserts for the backfilled history.
            cols = ["unit_id", "sim_day", *SENSOR_COLUMNS]
            with cur.copy(f"COPY readings ({', '.join(cols)}) FROM STDIN") as copy:
                for r in reading_rows:
                    copy.write_row(r)
        conn.commit()

        # Tell a running simulator to reload (nobody listening is fine).
        conn.execute("SELECT pg_notify('clock_cmd', 'reset')")
        conn.commit()

    return {"epoch": epoch, "stations": len(STATIONS), "units": len(unit_rows), "technicians": len(tech_rows),
            "readings": len(reading_rows), "planted_faults": len(fault_rows),
            "slugs": {name: slug for _, name, _, _, _, slug, _ in tech_rows}}


if __name__ == "__main__":
    out = reseed()
    slugs = out.pop("slugs")
    print("seeded:", out)
    print("phone pages (do not commit or post these):")
    for name, slug in slugs.items():
        print(f"  {name:18} /field/{slug}")