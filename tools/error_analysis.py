"""Error analysis: categorize match misses, missed errors and false flags on a split."""
from __future__ import annotations
import json, sys, tempfile
from collections import Counter
from pathlib import Path
from media_recon.pipeline import run
from media_recon.eval import score
from media_recon.eval.composite import composite
from media_recon.match import norm_vendor, vendors_compatible, score as mscore, is_fee, is_makegood, _clean

def analyze(data: Path, gold: dict):
    res = run(data, data / "out")
    recs = {r.record_id: r for r in res["records"]}
    gm = {k: v for k, v in gold["matches"].items() if v}
    pm = res["matched"]
    cats = Counter(); detail = []
    for rid, iid in gm.items():
        if pm.get(rid) == iid: continue
        r, io = recs.get(rid), recs.get(iid)
        if r is None or io is None: c = "extraction_missing_record"
        elif not vendors_compatible(r.vendor, io.vendor): c = "vendor_name_variant"
        elif is_fee(r) or is_makegood(r): c = "misfiltered_fee_or_makegood"
        elif rid in pm: c = "wrong_io_near_duplicate" if norm_vendor(recs[pm[rid]].vendor)==norm_vendor(io.vendor) else "wrong_io_cross_vendor"
        elif " & " in (r.placement or "") or " + " in (r.placement or ""): c = "allocation_merge_split"
        elif r.start and io.start and (r.start < io.start or r.end > io.end): c = "date_period_partial"
        else:
            s = mscore(_clean(r), io)
            c = "placement_abbrev_ocr_low_score" if s < 0.45 else "assignment_conflict_one_to_many"
        cats[("match", c)] += 1; detail.append(("match", c, rid, r and r.vendor, r and r.placement, io and io.vendor, io and io.placement))
    g_err = {(e["type"], e["key"]) for e in gold["errors"]}
    p_err = {(e.type, e.key) for e in res["exceptions"]}
    for t, k in g_err - p_err:
        upstream = any(gm.get(x) == k and pm.get(x) != k for x in gm)
        cats[("missed_error", f"{t}{' (match miss upstream)' if upstream else ''}")] += 1
    for t, k in p_err - g_err:
        cause = "from_unmatched" if t.startswith("unmatched") else "rule_threshold"
        if t.startswith("unmatched") and k in recs and gold["matches"].get(k):
            cause = "consequence_of_match_miss"
        cats[("false_flag", f"{t} [{cause}]")] += 1
    m = score(gold, res)
    return cats, detail, m, gm, pm, g_err, p_err

def lift(m, n_gm, n_ge, n_pe, kind, n):
    mr, er, fp = m["match_recall"], m["error_recall"], m["error_precision"]
    base = composite(mr, er, fp)
    tp_e = er * n_ge
    if kind == "match": mr = min(1, mr + n / n_gm)
    elif kind == "missed_error": tp = tp_e + n; er = tp / n_ge; fp = tp / (n_pe + n)
    else: fp = tp_e / max(n_pe - n, 1)
    return composite(mr, er, fp) - base

def splits(which):
    if which == "validation":
        from media_recon.generate.validation import VAL_SEEDS, generate
        for s in VAL_SEEDS:
            d = Path(tempfile.mkdtemp()) / f"v{s}"; yield d, generate(d, seed=s)
    elif which == "adversarial":
        d = Path("data/adversarial"); yield d, json.loads((d / "gold.json").read_text())

if __name__ == "__main__":
    for which in sys.argv[1:]:
        tot = Counter(); ms = []; info = []
        for d, g in splits(which):
            cats, det, m, gm, pm, ge, pe = analyze(d, g); tot += cats; ms.append((m, len(gm), len(ge), len(pe))); info += det
        k = len(ms)
        avg = {x: sum(m[0][x] for m in ms) / k for x in ("match_recall", "error_recall", "error_precision")}
        ngm, nge, npe = (sum(m[i] for m in ms) / k for i in (1, 2, 3))
        print(f"## {which}: composite {composite(*avg.values()):.4f} mr {avg['match_recall']:.3f} er {avg['error_recall']:.3f} fp {avg['error_precision']:.3f}  (per-seed avg: gold matches {ngm:.0f}, gold errors {nge:.0f}, flags {npe:.0f})")
        print("| kind | category | count | est. lift if fixed |\n|---|---|---:|---:|")
        for (kind, c), n in tot.most_common():
            print(f"| {kind} | {c} | {n} | {lift(avg, ngm, nge, npe, kind, n / k):+.3f} |")
        for x in info[:60]: print("   ", x, file=sys.stderr)
