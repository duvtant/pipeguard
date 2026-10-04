"""Rerun the whole ML pipeline in one command: train -> evaluate -> tune -> scenario (+ fallback).

Owner: Olise.  Run:  python -m ml.run_all [--version v1]
"""
from __future__ import annotations

import argparse
import sys

from ml import baseline, evaluate, make_scenario, train, tune


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", default="v1")
    args = ap.parse_args()
    sys.argv = [sys.argv[0]]          # the steps below parse their own (default) arguments
    baseline.main()
    train.train(version=args.version)
    evaluate.main()
    tune.main()
    make_scenario.main()


if __name__ == "__main__":
    main()
