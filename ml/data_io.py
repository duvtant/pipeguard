"""Loading NASA C-MAPSS FD001 (Saxena et al., 2008). Copied from the hackathon repo into ml/data/.

Owner: Olise.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from core.sensors import RAW_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "ml" / "data"
ARTIFACTS = ROOT / "ml" / "artifacts"
RUL_CAP = 125


def _read(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path, sep=r"\s+", header=None)
    # The NASA files end each line with spaces; drop any stray all-NaN trailing columns.
    df = df.dropna(axis=1, how="all")
    if df.shape[1] != len(RAW_COLUMNS):
        raise ValueError(f"{path.name}: expected {len(RAW_COLUMNS)} columns, got {df.shape[1]}")
    df.columns = RAW_COLUMNS
    df["unit"] = df["unit"].astype(int)
    df["cycle"] = df["cycle"].astype(int)
    return df.sort_values(["unit", "cycle"]).reset_index(drop=True)


def load_train(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    """Training engines with `max_cycle`, `rul_true` and `rul_capped` (min(RUL, 125))."""
    df = _read(data_dir / "train_FD001.txt")
    df["max_cycle"] = df.groupby("unit")["cycle"].transform("max")
    df["rul_true"] = df["max_cycle"] - df["cycle"]
    df["rul_capped"] = np.minimum(df["rul_true"], RUL_CAP)
    return df


def load_test(data_dir: Path = DATA_DIR) -> pd.DataFrame:
    return _read(data_dir / "test_FD001.txt")


def load_test_rul(data_dir: Path = DATA_DIR) -> np.ndarray:
    """True RUL at the last row of each test engine, in engine order 1..100."""
    return pd.read_csv(data_dir / "RUL_FD001.txt", sep=r"\s+", header=None).dropna(axis=1, how="all")[0].to_numpy()
