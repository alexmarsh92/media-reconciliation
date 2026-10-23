"""Fixed composite eval for autoresearch (hard DEV split only).

Prints ONE number: harmonic mean of match_recall, error_recall, flag_precision on the
HARD DEV split (generate/dev_hard.py, seeds 424201-424205). Different seed space AND
generator logic from the held-out adversarial set (data/adversarial, seed 909091),
which this module never touches.
"""
from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

from ..generate.dev_hard import DEV_SEEDS, generate
from ..pipeline import run
from . import score


def composite(match_recall: float, error_recall: float, flag_precision: float) -> float:
    vals = [max(match_recall, 1e-9), max(error_recall, 1e-9), max(flag_precision, 1e-9)]
    return 3.0 / sum(1.0 / v for v in vals)


def run_dev(seeds=DEV_SEEDS, noise: float | None = None) -> dict:
    """noise is accepted for backward compatibility and ignored (difficulty is baked into dev_hard)."""
    per = []
    with tempfile.TemporaryDirectory() as tmp:
        for s in seeds:
            d = Path(tmp) / f"dev{s}"
            gold = generate(d, seed=s)
            per.append(score(gold, run(d, d / "out")))
    avg = lambda k: sum(m[k] for m in per) / len(per)
    mr, er, fp = avg("match_recall"), avg("error_recall"), avg("error_precision")
    return {"composite": composite(mr, er, fp), "match_recall": mr, "error_recall": er,
            "flag_precision": fp, "match_precision": avg("match_precision"),
            "extraction_field_accuracy": avg("extraction_field_accuracy"),
            "seeds": list(seeds), "split": "dev_hard"}


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Print composite metric on the hard DEV split")
    p.add_argument("--seeds", default=",".join(map(str, DEV_SEEDS)))
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    res = run_dev(seeds=tuple(int(s) for s in a.seeds.split(",")))
    print(json.dumps(res) if a.json else f"{res['composite']:.6f}")


if __name__ == "__main__":
    main()


def run_validation(seeds=None) -> dict:
    """VALIDATION gate split (generate/validation.py). Non-regression gate only."""
    from ..generate.validation import VAL_SEEDS
    from ..generate.validation import generate as vgen
    seeds = seeds or VAL_SEEDS
    per = []
    with tempfile.TemporaryDirectory() as tmp:
        for s in seeds:
            d = Path(tmp) / f"val{s}"
            gold = vgen(d, seed=s)
            per.append(score(gold, run(d, d / "out")))
    avg = lambda k: sum(m[k] for m in per) / len(per)
    mr, er, fp = avg("match_recall"), avg("error_recall"), avg("error_precision")
    return {"composite": composite(mr, er, fp), "match_recall": mr, "error_recall": er,
            "flag_precision": fp, "seeds": list(seeds), "split": "validation"}
