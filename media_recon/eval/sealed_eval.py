"""Score the SEALED held-out v2 (data/sealed_holdout). Checkpoint/merge-gate use ONLY."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from ..pipeline import run
from . import score
from .composite import composite

ROOT = Path(__file__).resolve().parents[2] / "data" / "sealed_holdout"


def tree_hash(root: Path = ROOT) -> str:
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file() and "out" not in p.relative_to(root).parts and p.name != "SHA256":
            h.update(str(p.relative_to(root)).encode()); h.update(p.read_bytes())
    return h.hexdigest()


def evaluate_sealed(root: Path = ROOT) -> dict:
    exp = (root / "SHA256").read_text().split()[0]
    assert tree_hash(root) == exp, "sealed held-out files changed"
    per = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        gold = json.loads((d / "gold.json").read_text())
        assert gold.get("do_not_use_for_selection")
        per.append(score(gold, run(d, d / "out")))
    avg = lambda k: sum(m[k] for m in per) / len(per)
    mr, er, fp = avg("match_recall"), avg("error_recall"), avg("error_precision")
    return {"composite": composite(mr, er, fp), "match_recall": mr, "error_recall": er,
            "flag_precision": fp, "sha256": exp, "split": "sealed_holdout_v2"}


def main(argv=None) -> None:
    argparse.ArgumentParser().parse_args(argv)
    print(json.dumps(evaluate_sealed()))


if __name__ == "__main__":
    main()
