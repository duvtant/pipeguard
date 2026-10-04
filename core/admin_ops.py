"""Operations that change the whole demo state. Used by the clock endpoint now, admin endpoints next."""
import importlib.util
from pathlib import Path

SEED_PATH = Path(__file__).resolve().parents[1] / "infra" / "seed.py"


def reset_demo() -> dict:
    """Re-run infra/seed.py's reseed(): pause, bump the epoch, wipe and reload. Takes a few seconds.

    Returns counts only. The seed also knows each technician's phone link; those never leave this function.
    Raises RuntimeError with a readable message if the seed cannot run (missing data file, bad scenario).
    """
    if not SEED_PATH.exists():
        raise RuntimeError(f"seed script not found at {SEED_PATH}")
    spec = importlib.util.spec_from_file_location("pipeguard_seed", SEED_PATH)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
        out = mod.reseed()
    except SystemExit as exc:  # the seed signals bad input with SystemExit("message")
        raise RuntimeError(str(exc)) from None
    out.pop("slugs", None)
    return out
