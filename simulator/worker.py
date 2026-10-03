"""Historian simulator. Owner: Ebube. Spec: docs/techstack.md section 8.

Plays the customer's data historian: owns the simulated clock and writes one reading per unit
per simulated day into `readings`, then NOTIFYs the engine.

Clock protocol (the API implements the other half):
  - play / pause / speed: the API updates sim_state.status / speed_seconds_per_day. We poll every 250 ms.
  - advance N days (tests, fast-forward): NOTIFY clock_cmd 'advance:N'. Works while paused.
  - reset: seed.py bumps sim_state.epoch and reloads. We see the epoch change and start over.
  - part_replaced: the API sets units.life_start_day to sim_day + 1, so cycle 1 is written on the next tick.

sim_state.sim_day is the newest day that HAS readings. On startup and after every reset we write the
current day first, so the engine has data before the first tick.
"""
import os
import queue
import threading
import time
from pathlib import Path

import pandas as pd
import psycopg
from psycopg.types.json import Jsonb

from core.db import RECONNECTED, listen, psycopg_dsn
from core.models import SENSOR_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
NASA_PATH = Path(os.getenv("NASA_TRAIN_PATH", ROOT / "ml" / "data" / "train_FD001.txt"))
RAW_COLUMNS = ["unit", "cycle", "setting1", "setting2", "setting3", *[f"s{i}" for i in range(1, 22)]]
SENSOR_IDX = {s: i for i, s in enumerate(SENSOR_COLUMNS)}

POLL_SECONDS = 0.25   # how often we re-read sim_state
SPIKE_STDS = 10       # spike and out-of-range faults are this many training stds
MAX_ADVANCE = 1000    # cap on one 'advance:N' command

# One reading row. ON CONFLICT makes a replayed tick (restart, duplicate notify) a no-op.
INSERT_READING = (
    "INSERT INTO readings (unit_id, sim_day, " + ", ".join(SENSOR_COLUMNS) + ") VALUES (%s, %s"
    + ", %s" * len(SENSOR_COLUMNS) + ") ON CONFLICT (unit_id, sim_day) DO NOTHING"
)


def load_nasa():
    """Per-engine sensor arrays (row i = cycle i+1) plus per-sensor training std and max."""
    if not NASA_PATH.exists():
        raise SystemExit(f"NASA data not found: {NASA_PATH}")
    df = pd.read_csv(NASA_PATH, sep=r"\s+", header=None, names=RAW_COLUMNS)
    cols = list(SENSOR_COLUMNS)
    engines = {int(e): g.sort_values("cycle")[cols].to_numpy(dtype=float) for e, g in df.groupby("unit")}
    return engines, df[cols].std().to_numpy(dtype=float), df[cols].max().to_numpy(dtype=float)


def apply_fault(values, sensor, ftype, start, day, life_start, arr, std, mx):
    """Corrupt one sensor of today's reading in place. History already written is never touched."""
    i = SENSOR_IDX.get(sensor)
    if i is None:
        return
    if ftype == "dead":
        values[i] = None
    elif ftype == "stuck":
        # Repeat the last good value from before the fault started (the cycle of day start-1).
        c0 = min(max(start - life_start, 1), len(arr))
        values[i] = float(arr[c0 - 1, i])
    elif ftype == "spike":
        if day == start and values[i] is not None:  # one reading only
            values[i] += SPIKE_STDS * std[i]
    elif ftype == "out_of_range":
        values[i] = float(mx[i] + SPIKE_STDS * std[i])  # physically impossible, above anything in training


def add_event(cur, day, typ, unit_id, title, detail, severity, payload=None):
    cur.execute(
        "INSERT INTO events (sim_day, type, unit_id, title, detail, severity, payload)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (day, typ, unit_id, title, detail, severity, Jsonb(payload or {})))
    # pg_notify inside the transaction is delivered on commit, so listeners never see a missing row.
    cur.execute("SELECT pg_notify('ui_event', %s)", (str(cur.fetchone()[0]),))


def produce(conn, data, epoch, step, force):
    """Write one day of readings in ONE transaction. Returns (day, readings, failures) or None.

    step=1 advances the clock, step=0 rewrites the current day (startup).
    None means the epoch changed (reset) or the clock was paused since our last poll.
    """
    engines, std, mx = data
    with conn.cursor() as cur:
        # Row lock: a reset (seed.py) waits for this tick to finish, and a stale epoch writes nothing.
        cur.execute(
            "UPDATE sim_state SET sim_day = sim_day + %s WHERE id = 1 AND epoch = %s"
            " AND (status = 'running' OR %s) RETURNING sim_day", (step, epoch, force))
        row = cur.fetchone()
        if row is None:
            conn.rollback()
            return None
        day = row[0]

        # Read units and faults fresh every tick: toggles and part_replaced take effect immediately.
        cur.execute("SELECT id, source_engine, life_start_day, status FROM units ORDER BY id")
        units = cur.fetchall()
        # Active on `day`. Inclusive end_day, so nothing already written changes.
        cur.execute("SELECT unit_id, sensor, type, start_day FROM faults"
                    " WHERE start_day <= %s AND (end_day IS NULL OR end_day >= %s)", (day, day))
        faults: dict = {}
        for uid, sensor, ftype, start in cur.fetchall():
            faults.setdefault(uid, {}).setdefault(sensor, (ftype, start))  # first fault per sensor wins

        rows, newly_failed, alive = [], [], 0
        for uid, eng, life_start, status in units:
            if status == "failed":
                continue  # failed units stop reporting, faults on them are ignored
            arr = engines[eng]
            cycle = day - life_start + 1
            if cycle > len(arr):
                newly_failed.append(uid)  # past the engine's last row: it failed in service
                continue
            alive += 1
            if cycle < 1:
                continue  # replaced unit: its new life starts on a later day
            values = arr[cycle - 1].tolist()
            for sensor, (ftype, start) in faults.get(uid, {}).items():
                apply_fault(values, sensor, ftype, start, day, life_start, arr, std, mx)
            rows.append((uid, day, *values))

        if rows:
            cur.executemany(INSERT_READING, rows)

        for uid in newly_failed:
            # Conditional update: a restart can never write the failure event twice.
            cur.execute("UPDATE units SET status = 'failed' WHERE id = %s AND status <> 'failed' RETURNING id", (uid,))
            if cur.fetchone():
                add_event(cur, day, "failure", uid, "Unit failed", f"{uid} failed in service.", "critical")

        if newly_failed and alive == 0:
            # Last unit just failed: pause. The contract has no generic info event type, so status_change.
            cur.execute("UPDATE sim_state SET status = 'paused' WHERE id = 1")
            add_event(cur, day, "status_change", None, "Scenario finished",
                      "Every unit has failed. The replay is paused.", "info")

    conn.commit()
    # Notify AFTER the commit, with the ID only: the engine reads rows from the table.
    conn.execute("SELECT pg_notify('new_day', %s)", (str(day),))
    conn.commit()
    return day, len(rows), len(newly_failed)


def poll(conn):
    """(status, speed, epoch) from sim_state, or None while the database has not been seeded yet."""
    try:
        row = conn.execute("SELECT status, speed_seconds_per_day, epoch FROM sim_state WHERE id = 1").fetchone()
    except psycopg.errors.UndefinedTable:
        row = None
    conn.commit()  # end the read transaction, never sit idle inside one
    return row


def command_listener(q):
    # Own thread: listen() blocks, and the main loop has to keep time.
    for channel, payload in listen(["clock_cmd"]):
        q.put("poll" if channel == RECONNECTED else payload)  # after a reconnect, re-read the state


def run(data, q):
    with psycopg.connect(psycopg_dsn()) as conn:
        epoch, need_init, running, speed = None, True, False, 1.0
        pending, next_poll, next_tick, waiting = 0, 0.0, 0.0, False
        print("simulator: connected", flush=True)
        while True:
            now = time.monotonic()

            while True:  # drain commands
                try:
                    cmd = q.get_nowait()
                except queue.Empty:
                    break
                if cmd.startswith("advance:"):
                    try:
                        pending = min(pending + int(cmd.split(":", 1)[1]), MAX_ADVANCE)
                    except ValueError:
                        print(f"simulator: bad command {cmd!r}", flush=True)
                else:
                    next_poll = 0.0  # play, pause, reset...: re-read sim_state right away

            if now >= next_poll:
                row = poll(conn)
                if row is None:  # not seeded yet: wait instead of crash-looping
                    if not waiting:
                        print("simulator: waiting for the seed (python infra/seed.py)", flush=True)
                        waiting = True
                    time.sleep(2)
                    next_poll = 0.0
                    continue
                waiting = False
                status, speed, ep = row
                if ep != epoch:  # first poll, or a reset happened: drop everything and start over
                    print(f"simulator: loaded epoch {ep}", flush=True)
                    epoch, need_init, pending = ep, True, 0
                now_running = status == "running"
                if now_running and not running:
                    next_tick = now  # play pressed: first tick right away
                running = now_running
                next_poll = now + POLL_SECONDS

            if need_init:  # make sure the current day has readings before anything else
                if produce(conn, data, epoch, step=0, force=True) is None:
                    next_poll = 0.0
                    continue
                need_init = False

            if pending > 0:  # advance: as fast as possible, ignores pacing and pause
                if produce(conn, data, epoch, step=1, force=True) is None:
                    pending, next_poll = 0, 0.0
                else:
                    pending -= 1
                continue

            if running and now >= next_tick:
                out = produce(conn, data, epoch, step=1, force=False)
                if out is None:  # paused or reset since the last poll
                    next_poll = 0.0
                else:
                    day, n_rows, n_failed = out
                    if day % 10 == 0 or n_failed:
                        print(f"simulator: day {day}: {n_rows} readings, {n_failed} failed", flush=True)
                    interval = max(speed, 0.0)
                    next_tick += interval  # schedule against a target time, so work time never drifts the pace
                    if next_tick < now - interval:
                        next_tick = now  # fell behind: skip ahead, no burst catch-up
                if speed <= 0:
                    continue  # speed 0 = as fast as possible

            time.sleep(0.02)


def main():
    data = load_nasa()
    print(f"simulator: loaded {len(data[0])} NASA engines", flush=True)
    q: queue.Queue = queue.Queue()
    threading.Thread(target=command_listener, args=(q,), daemon=True).start()
    while True:
        try:
            run(data, q)
        except (psycopg.OperationalError, OSError) as exc:
            print(f"simulator: database connection lost ({exc}), retrying in 3s", flush=True)
            time.sleep(3)


if __name__ == "__main__":
    main()