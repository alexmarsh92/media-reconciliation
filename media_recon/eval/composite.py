"""Fixed composite eval for autoresearch (DEV split only).

Prints ONE number: harmonic mean of match_recall, error_recall, flag_precision
on the messy (noise=0.6) synthetic tier. Never touches held-out adversarial.
"""
from __future__ import annotations

import argparse
import json
import sys

from . import evaluate


def composite(match_recall: float, error_recall: float, flag_precision: float) -> float:
    vals = [max(match_recall, 1e-9), max(error_recall, 1e-9), max(flag_precision, 1e-9)]
    return 3.0 / sum(1.0 / v for v in vals)


def run_dev(seeds=(1, 2, 3), noise: float = 0.6) -> dict:
    r = evaluate(seeds=seeds, noise=noise)
    c = composite(r["match_recall"], r["error_recall"], r["error_precision"])
    return {
        "composite": c,
        "match_recall": r["match_recall"],
        "error_recall": r["error_recall"],
        "flag_precision": r["error_precision"],
        "match_precision": r["match_precision"],
        "seeds": list(seeds),
        "noise": noise,
    }


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description="Print composite metric on messy DEV split")
    p.add_argument("--seeds", default="1,2,3")
    p.add_argument("--noise", type=float, default=0.6)
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    seeds = tuple(int(s) for s in a.seeds.split(","))
    res = run_dev(seeds=seeds, noise=a.noise)
    if a.json:
        print(json.dumps(res))
    else:
        # ONE number for the autoresearch loop
        print(f"{res['composite']:.6f}")


if __name__ == "__main__":
    main()
