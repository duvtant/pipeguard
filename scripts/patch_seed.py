"""Edit infra/seed.py: seed engine_params from the tuned values in ml/artifacts/metadata.json (threshold 0.3,
horizon 21 instead of the 0.5 / 14 placeholders) and add the column defaults the engine's inserts rely on.
Safe to run twice. Run from the repo root:  python scripts/patch_seed.py
"""
from pathlib import Path

path = Path("infra/seed.py")
src = path.read_text(encoding="utf-8")
done = []

if "def tuned_defaults" not in src:
    anchor = "def field_slug("
    use = "(DEFAULT_THRESHOLD, DEFAULT_HORIZON_DAYS))"
    if src.count(anchor) != 1 or src.count(use) != 1:
        raise SystemExit("could not find the engine_params insert or field_slug in infra/seed.py: edit by hand")
    helper = '''def tuned_defaults() -> tuple[float, int]:
    """(threshold, horizon_days) from ml/artifacts/metadata.json 'tuned', else the placeholders above."""
    try:
        tuned = json.loads((ROOT / "ml" / "artifacts" / "metadata.json").read_text(encoding="utf-8"))["tuned"]
        return float(tuned["threshold"]), int(tuned["horizon_days"])
    except (OSError, ValueError, KeyError, TypeError):
        return DEFAULT_THRESHOLD, DEFAULT_HORIZON_DAYS


'''
    src = src.replace(anchor, helper + anchor).replace(use, "tuned_defaults())")
    done.append("tuned engine_params")

if "ensure_columns" not in src:
    imp, call = "from core.db import init_db, psycopg_dsn  # noqa: E402\n", "    init_db()  # creates any missing tables first\n"
    if src.count(imp) != 1 or src.count(call) != 1:
        raise SystemExit("could not find the init_db lines in infra/seed.py: edit by hand")
    src = src.replace(imp, imp + "from core.migrate import ensure_columns  # noqa: E402\n")
    src = src.replace(call, call + "    ensure_columns()  # defaults the engine's raw inserts rely on, also on older databases\n")
    done.append("ensure_columns")

if done:
    path.write_text(src, encoding="utf-8")
    print("patched infra/seed.py:", ", ".join(done))
else:
    print("infra/seed.py already has everything, nothing to do")
