"""Starter-style linear model. Must reproduce MAE 27.5 and 12 of 25 caught.

Owner: Olise. Spec: Olise guide section 4 step 1.

The baseline is the hackathon's Case 4 starter (`ml/legacy/agent_starter.py`, copied verbatim from
github.com/nagusubra/industry-hackathon-lab): a straight line on s4, s7, s11, s12, s15, fitted to the
UNCAPPED training RUL, scored on the last row of each test engine.

"Caught" definition (reused unchanged from the starter, never tuned to flatter a model):
  failing engine = true RUL at the last test row < 30 cycles   (25 of the 100 test engines)
  caught         = failing engine whose predicted RUL is < 30 cycles (the starter's inspect cut-off)

Run:  python -m ml.baseline
"""
from __future__ import annotations

import json

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

from core.sensors import SENSORS
from ml.data_io import RUL_CAP, load_test, load_test_rul, load_train

STARTER_FEATURES = ["s4", "s7", "s11", "s12", "s15"]
CUTOFF = 30


def nasa_score(pred, true) -> float:
    d = np.asarray(pred, dtype=float) - np.asarray(true, dtype=float)
    return float(np.sum(np.where(d < 0, np.exp(-d / 13.0) - 1, np.exp(d / 10.0) - 1)))


def caught(pred: np.ndarray, true: np.ndarray, cutoff: int = CUTOFF) -> dict[str, int]:
    failing = true < cutoff
    flag = pred < cutoff
    return {"failing": int(failing.sum()), "caught": int((flag & failing).sum()),
            "missed": int((failing & ~flag).sum()), "extra": int((flag & ~failing).sum())}


def score(pred: np.ndarray, true_raw: np.ndarray) -> dict:
    capped = np.minimum(true_raw, RUL_CAP)
    return {
        "mae_raw": float(np.mean(np.abs(pred - true_raw))),           # the starter's number (27.5)
        "rmse": float(np.sqrt(np.mean((pred - capped) ** 2))),        # standard: against capped true RUL
        "mae": float(np.mean(np.abs(pred - capped))),
        "nasa_score": nasa_score(pred, capped),
        **caught(pred, true_raw),
    }


def last_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df.loc[df.groupby("unit")["cycle"].idxmax()].sort_values("unit")


def linear_baseline() -> dict:
    tr, te, y = load_train(), load_test(), load_test_rul()
    model = LinearRegression().fit(tr[STARTER_FEATURES], tr["rul_true"])
    pred = model.predict(last_rows(te)[STARTER_FEATURES])
    return {"model": "linear, starter features, uncapped target", **score(pred, y)}


def quick_untuned_model() -> dict:
    """Reconstruction of the 'quick untuned model' (14.8 / 18 of 25). The original script is not in the
    repo; this is the closest simple configuration: LightGBM defaults, 14 kept sensors (raw, last row) plus
    cycle, target capped at 125. See ml/README.md for the gap."""
    tr, te, y = load_train(), load_test(), load_test_rul()
    feats = SENSORS + ["cycle"]
    model = lgb.LGBMRegressor(random_state=42, verbose=-1, deterministic=True, force_row_wise=True, n_jobs=4)
    model.fit(tr[feats], tr["rul_capped"])
    pred = model.predict(last_rows(te)[feats])
    return {"model": "LightGBM defaults, 14 sensors + cycle, capped 125", **score(pred, y)}


def main() -> None:
    base = linear_baseline()
    quick = quick_untuned_model()
    print(json.dumps({"linear_baseline": base, "quick_untuned": quick}, indent=1))
    assert round(base["mae_raw"], 1) == 27.5, base
    assert base["caught"] == 12 and base["failing"] == 25, base
    print(f"\nBaseline reproduced: MAE {base['mae_raw']:.1f} cycles, caught {base['caught']} of {base['failing']}.")


if __name__ == "__main__":
    main()
