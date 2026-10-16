"""CLI: media-recon generate | run | eval"""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="media-recon", description="AI media reconciliation (synthetic demo)")
    sub = p.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="create synthetic IOs, invoice PDFs, delivery reports + gold.json")
    g.add_argument("--out", default="data/synthetic")
    g.add_argument("--seed", type=int, default=7)
    g.add_argument("--noise", type=float, default=0.0, help="0-1: typos/dropped words in names")
    r = sub.add_parser("run", help="extract, match, flag exceptions, write outputs")
    r.add_argument("--data", default="data/synthetic")
    r.add_argument("--out", default="data/output")
    r.add_argument("--llm", action="store_true", help="use LLM plugin for invoices if MEDIA_RECON_LLM_URL is set")
    e = sub.add_parser("eval", help="score against planted gold over several seeds")
    e.add_argument("--seeds", default="1,2,3,4,5")
    e.add_argument("--noise", type=float, default=0.0)
    e.add_argument("--json", action="store_true")
    adv = sub.add_parser("eval-adversarial", help="score held-out adversarial set (checkpoint only)")
    adv.add_argument("--data", default="data/adversarial")
    adv.add_argument("--json", action="store_true")
    comp = sub.add_parser("eval-composite", help="print one composite metric on messy DEV split")
    comp.add_argument("--seeds", default="1,2,3")
    comp.add_argument("--noise", type=float, default=0.6)
    comp.add_argument("--json", action="store_true")
    gena = sub.add_parser("generate-adversarial", help="build held-out adversarial data/")
    gena.add_argument("--out", default="data/adversarial")
    gena.add_argument("--seed", type=int, default=909091)
    a = p.parse_args(argv)

    if a.cmd == "generate":
        from .generate.synth import generate
        gold = generate(Path(a.out), seed=a.seed, noise=a.noise)
        print(f"Wrote {len(gold['records'])} records, {len(gold['errors'])} planted errors to {a.out}")
    elif a.cmd == "run":
        from .pipeline import run
        res = run(Path(a.data), Path(a.out), use_llm=a.llm)
        print(json.dumps(res["summary"], indent=1))
        print(f"Outputs: {a.out}/exceptions.csv, exceptions.xlsx, accruals.csv, summary.html")
    elif a.cmd == "eval":
        from .eval import evaluate, format_report, main_json
        res = evaluate(tuple(int(s) for s in a.seeds.split(",")), a.noise)
        print(main_json(res) if a.json else format_report(res))
    elif a.cmd == "eval-adversarial":
        from .eval.adversarial_eval import evaluate_adversarial
        m = evaluate_adversarial(Path(a.data))
        if a.json:
            print(json.dumps({k: v for k, v in m.items() if k != "error_recall_by_type"}, indent=1))
        else:
            print(f"heldout_composite={m['composite']:.6f}")
            print(f"match_P/R={m['match_precision']:.3f}/{m['match_recall']:.3f} "
                  f"error_R={m['error_recall']:.3f} flag_P={m['error_precision']:.3f}")
    elif a.cmd == "eval-composite":
        from .eval.composite import main as comp_main
        comp_main(["--seeds", a.seeds, "--noise", str(a.noise)] + (["--json"] if a.json else []))
    elif a.cmd == "generate-adversarial":
        from .generate.adversarial import generate as gen_adv
        gold = gen_adv(Path(a.out), seed=a.seed)
        print(f"Adversarial: {len(gold['records'])} records, {len(gold['errors'])} gold errors -> {a.out}")
    else:
        raise SystemExit(f"unknown cmd {a.cmd}")


if __name__ == "__main__":
    main()
