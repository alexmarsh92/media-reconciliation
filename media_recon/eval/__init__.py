"""Evaluation against planted gold: extraction, matching, error detection, time saved."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from ..generate.synth import generate
from ..pipeline import run
from ..schema import FIELDS

# Time-saved assumptions (minutes). Conservative, stated in README.
MANUAL_MIN_PER_RECORD = 2.0       # find + key one line from an IO/invoice/report into a sheet
MANUAL_MIN_PER_IO_MATCH = 3.0     # tie one IO line to its invoice + delivery lines
MANUAL_MIN_PER_EXCEPTION = 15.0   # investigate + document one exception
TOOL_MIN_PER_IO_REVIEW = 0.5      # skim the tool's match + citation per IO line
TOOL_MIN_PER_EXCEPTION = 7.0      # exceptions arrive pre-sourced with citations
MONTHLY_IO_LINES = 400            # assumed mid-size agency monthly volume


def _eq(a, b) -> bool:
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return abs(a - b) <= 0.01
    return (a or None) == (b or None)


def score(gold: dict, result: dict) -> dict:
    g_recs = {r["record_id"]: r for r in gold["records"]}
    hits = total = 0
    for r in result["records"]:
        gr, d = g_recs.get(r.record_id), r.to_dict()
        for f in FIELDS[r.source]:
            total += 1
            hits += bool(gr) and _eq(d[f], gr[f])
    total += sum(len(FIELDS[r["source"]]) for rid, r in g_recs.items()
                 if rid not in {x.record_id for x in result["records"]})  # missed records count as wrong

    gm = {k: v for k, v in gold["matches"].items() if v}
    pm = result["matched"]
    tp = sum(pm.get(k) == v for k, v in gm.items())

    g_err = {(e["type"], e["key"]) for e in gold["errors"]}
    p_err = {(e.type, e.key) for e in result["exceptions"]}
    by_type = {}
    for t in sorted({t for t, _ in g_err}):
        g = {x for x in g_err if x[0] == t}
        by_type[t] = f"{len(g & p_err)}/{len(g)}"
    return {"extraction_field_accuracy": hits / total if total else 0,
            "match_precision": tp / len(pm) if pm else 0, "match_recall": tp / len(gm) if gm else 0,
            "error_recall": len(g_err & p_err) / len(g_err), "error_precision": len(g_err & p_err) / len(p_err) if p_err else 0,
            "error_recall_by_type": by_type, "n_records": len(g_recs), "n_planted_errors": len(g_err)}


def time_saved(n_io: int, n_records: int, n_exc: int, runtime_s: float) -> dict:
    manual = n_records * MANUAL_MIN_PER_RECORD + n_io * MANUAL_MIN_PER_IO_MATCH + n_exc * MANUAL_MIN_PER_EXCEPTION
    tool = runtime_s / 60 + n_io * TOOL_MIN_PER_IO_REVIEW + n_exc * TOOL_MIN_PER_EXCEPTION
    scale = MONTHLY_IO_LINES / n_io
    return {"manual_hours": manual / 60, "tool_hours": tool / 60, "pct_saved": 1 - tool / manual,
            "monthly_hours_saved_at_400_lines": (manual - tool) * scale / 60}


def evaluate(seeds=(1, 2, 3, 4, 5), noise: float = 0.0) -> dict:
    per_seed = []
    with tempfile.TemporaryDirectory() as tmp:
        for seed in seeds:
            data = Path(tmp) / f"s{seed}"
            gold = generate(data, seed=seed, noise=noise)
            t0 = time.perf_counter()
            res = run(data, data / "out")
            rt = time.perf_counter() - t0
            m = score(gold, res)
            n_io = sum(r.source == "io" for r in res["records"])
            m["time"] = time_saved(n_io, len(res["records"]), len(res["exceptions"]), rt)
            m["runtime_s"] = rt
            per_seed.append(m)
    keys = ["extraction_field_accuracy", "match_precision", "match_recall", "error_recall", "error_precision"]
    agg = {k: sum(m[k] for m in per_seed) / len(per_seed) for k in keys}
    by_type = {}
    for m in per_seed:
        for t, v in m["error_recall_by_type"].items():
            a, b = map(int, v.split("/"))
            x = by_type.setdefault(t, [0, 0]); x[0] += a; x[1] += b
    agg["error_recall_by_type"] = {t: f"{a}/{b}" for t, (a, b) in by_type.items()}
    agg["time"] = {k: sum(m["time"][k] for m in per_seed) / len(per_seed) for k in per_seed[0]["time"]}
    agg["avg_runtime_s"] = sum(m["runtime_s"] for m in per_seed) / len(per_seed)
    agg["seeds"], agg["noise"] = list(seeds), noise
    agg["records_per_seed"] = per_seed[0]["n_records"]
    agg["planted_errors_total"] = sum(m["n_planted_errors"] for m in per_seed)
    return agg


def format_report(r: dict) -> str:
    t = r["time"]
    lines = [f"Seeds {r['seeds']}  noise={r['noise']}  ({r['records_per_seed']} records/seed, "
             f"{r['planted_errors_total']} planted errors total)",
             f"Extraction field accuracy : {r['extraction_field_accuracy']:.1%}",
             f"Match precision / recall  : {r['match_precision']:.1%} / {r['match_recall']:.1%}",
             f"Error-detection recall    : {r['error_recall']:.1%}  (precision {r['error_precision']:.1%})",
             "  by type: " + ", ".join(f"{k} {v}" for k, v in r["error_recall_by_type"].items()),
             f"Pipeline runtime          : {r['avg_runtime_s']:.2f}s per batch",
             f"Time per batch            : manual {t['manual_hours']:.1f}h vs tool {t['tool_hours']:.1f}h "
             f"({t['pct_saved']:.0%} saved)",
             f"At 400 IO lines/month     : ~{t['monthly_hours_saved_at_400_lines']:.0f} hours saved/month"]
    return "\n".join(lines)


def main_json(r: dict) -> str:
    return json.dumps(r, indent=1, default=str)
