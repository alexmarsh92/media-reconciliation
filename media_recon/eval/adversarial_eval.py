"""Score the held-out adversarial set. Checkpoint use ONLY — never for selection."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..pipeline import run
from . import score
from .composite import composite


def evaluate_adversarial(data: Path | None = None) -> dict:
    root = Path(__file__).resolve().parents[2]
    data = data or (root / "data" / "adversarial")
    gold = json.loads((data / "gold.json").read_text())
    assert gold.get("held_out") and gold.get("do_not_use_for_selection")
    out = data / "out"
    res = run(data, out)
    m = score(gold, res)
    m["composite"] = composite(m["match_recall"], m["error_recall"], m["error_precision"])
    m["held_out"] = True
    return m


def main(argv=None) -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/adversarial")
    p.add_argument("--json", action="store_true")
    a = p.parse_args(argv)
    m = evaluate_adversarial(Path(a.data))
    if a.json:
        print(json.dumps({k: v for k, v in m.items() if k != "error_recall_by_type"}, indent=1))
        print("by_type:", m.get("error_recall_by_type"))
    else:
        print(f"heldout_composite={m['composite']:.6f}")
        print(f"match_recall={m['match_recall']:.3f} error_recall={m['error_recall']:.3f} "
              f"flag_precision={m['error_precision']:.3f}")


if __name__ == "__main__":
    main()
