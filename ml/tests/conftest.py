"""Shared fixtures. Tests that need trained artifacts are skipped until `python -m ml.train` has run."""
from __future__ import annotations

import json

import pandas as pd
import pytest

from ml.data_io import ARTIFACTS, load_train


def _have_artifacts() -> bool:
    return (ARTIFACTS / "feature_config.json").exists() and (ARTIFACTS / "oof_predictions.parquet").exists()


needs_artifacts = pytest.mark.skipif(not _have_artifacts(), reason="run python -m ml.train first")


@pytest.fixture(scope="session")
def train_df() -> pd.DataFrame:
    return load_train()


@pytest.fixture(scope="session")
def cfg() -> dict:
    if not _have_artifacts():
        pytest.skip("run python -m ml.train first")
    return json.loads((ARTIFACTS / "feature_config.json").read_text())


@pytest.fixture(scope="session")
def oof() -> pd.DataFrame:
    if not _have_artifacts():
        pytest.skip("run python -m ml.train first")
    return pd.read_parquet(ARTIFACTS / "oof_predictions.parquet")


@pytest.fixture(scope="session")
def predictor():
    if not _have_artifacts():
        pytest.skip("run python -m ml.train first")
    from core.predict import Predictor
    return Predictor(ARTIFACTS)
