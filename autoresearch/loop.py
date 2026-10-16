#!/usr/bin/env python3
"""Karpathy-style overnight autoresearch over media_recon/tunables.json.

Selection signal: DEV composite only.
Held-out adversarial: checkpoints only (never to pick winners).
Live monitor: live_best.json + live_updates.log on each new best.
"""
from __future__ import annotations

import copy
import json
import os
import random
import signal
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from media_recon.tunables import load as load_tunables, save as save_tunables  # noqa: E402
from media_recon.eval.composite import run_dev, run_validation as _run_val_split  # noqa: E402
from media_recon.eval.adversarial_eval import evaluate_adversarial as _eval_diag  # noqa: E402
from media_recon.eval.sealed_eval import evaluate_sealed  # noqa: E402

# Restart #4 (jump plan) objective redesign:
#   SELECT  = mean(DEV composite, VALIDATION composite)  -> keeps can't overfit one generator
#   GATE    = old adversarial set (data/adversarial), demoted to a diagnostic: must not drop
#   CHECK   = SEALED held-out v2 (data/sealed_holdout) scored at checkpoints only, never selects
_run_dev_only = run_dev


def run_dev(seeds=None, noise=None) -> dict:  # selection signal (name kept for minimal diff)
    d, v = _run_dev_only(seeds=seeds), _run_val_split()
    out = {k: (d[k] + v[k]) / 2 for k in ("composite", "match_recall", "error_recall", "flag_precision")}
    out.update(dev_composite=d["composite"], val_composite=v["composite"], split="dev+val")
    return out


def run_validation() -> dict:  # non-regression gate: diagnostic adversarial set
    m = _eval_diag()
    return {"composite": m["composite"], "match_recall": m["match_recall"],
            "error_recall": m["error_recall"], "flag_precision": m["error_precision"], "split": "diag_adversarial"}


def evaluate_adversarial() -> dict:  # checkpoint: sealed held-out v2
    m = evaluate_sealed()
    m["error_precision"] = m["flag_precision"]
    return m

AR = ROOT / "autoresearch"
RESULTS = AR / "results.tsv"
LOG = AR / "run.log"
LIVE_BEST = AR / "live_best.json"
LIVE_UPDATES = AR / "live_updates.log"
ALERT_OVERFIT = AR / "ALERT_OVERFIT"
ALERT_STALL = AR / "ALERT_STALL"
MORNING = AR / "MORNING.md"
PID_FILE = AR / "PID"
BEST_TUNABLES = AR / "best_tunables.json"
BASELINE_TUNABLES = AR / "baseline_tunables.json"

# Overnight window: default 8 hours from start (override with AUTORESEARCH_HOURS)
HOURS = float(os.environ.get("AUTORESEARCH_HOURS", "8"))
CHECKPOINT_EVERY_KEPT = int(os.environ.get("AUTORESEARCH_CKPT_KEPT", "3"))
CHECKPOINT_EVERY_EXP = int(os.environ.get("AUTORESEARCH_CKPT_EXP", "15"))
STALL_MINUTES = float(os.environ.get("AUTORESEARCH_STALL_MIN", "45"))
from media_recon.generate.dev_hard import DEV_SEEDS  # noqa: E402  hard DEV split
DEV_NOISE = None  # unused; difficulty baked into dev_hard

# Over-specificity guards (restart #3, after exp-47 overfit):
# - at most MAX_VENDOR_ALIAS_ADDS vendor-specific alias entries may be added beyond the baseline table
# - single-string changes (alias +/-) must clear a larger DEV gain to be kept
# - vendor-alias proposals are sampled far less often than generic abbreviation expansions
MAX_VENDOR_ALIAS_ADDS = int(os.environ.get("AUTORESEARCH_MAX_ALIAS_ADDS", "0"))  # resolver replaces per-vendor aliases
SPECIFIC_MIN_GAIN = float(os.environ.get("AUTORESEARCH_SPECIFIC_MIN_GAIN", "0.005"))
VAL_TOL = float(os.environ.get("AUTORESEARCH_VAL_TOL", "1e-9"))  # validation must not drop
BASE_ALIAS_KEYS: set[str] = set()
VAL_STATE: dict = {}

# Candidate tables are derived from the DEV vocabulary + generic industry abbreviations ONLY.
# Held-out (data/adversarial) vendor names/abbreviations were deliberately removed to avoid leakage.
EXPAND_CANDIDATES = {
    "mob": "mobile", "dt": "desktop", "prsp": "prospecting", "prosp": "prospecting",
    "rtg": "retargeting", "vid": "video", "awr": "awareness", "conv": "conversion",
    "cnsd": "consideration", "spons": "sponsored", "gen": "generic", "hp": "homepage",
    "ntwk": "network", "ntv": "native", "cat": "catalog", "shop": "shopping",
    "tko": "takeover", "coll": "collection", "comm": "commercials", "disp": "display",
    "prem": "premium", "srch": "search", "aud": "audience", "ctv": "ctv", "olv": "online",
}
VENDOR_CANDIDATES = {
    "tiktok": "tiktok for business", "tiktok ads": "tiktok for business", "tik tok": "tiktok for business",
    "bytedance ads": "tiktok for business", "bytedance": "tiktok for business",
    "snapchat": "snap", "snap ads": "snap", "snap inc.": "snap",
    "pinterest inc": "pinterest", "pinterest ads": "pinterest", "pintrest": "pinterest",
    "linkedin": "linkedin marketing solutions", "linkedin ads": "linkedin marketing solutions",
    "li marketing": "linkedin marketing solutions",
    "reddit inc": "reddit", "reddit": "reddit",
    "bing ads": "microsoft", "bing": "microsoft", "microsoft ads": "microsoft", "msft advertising": "microsoft",
    "msft": "microsoft",
    "yahoo": "yahoo dsp", "yahoo advertising": "yahoo dsp", "verizon media dsp": "yahoo dsp",
    "verizon media": "yahoo dsp",
    "roku": "roku", "roku ads": "roku", "the roku channel": "roku",
}


def log(msg: str) -> None:
    line = f"{datetime.now(timezone.utc).isoformat()} {msg}"
    print(line, flush=True)
    with LOG.open("a") as f:
        f.write(line + "\n")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_stall(reason: str) -> None:
    ALERT_STALL.write_text(f"{now_iso()}\n{reason}\n")
    log(f"ALERT_STALL: {reason}")


def write_overfit(details: dict) -> None:
    ALERT_OVERFIT.write_text(json.dumps(details, indent=2) + "\n")
    log(f"ALERT_OVERFIT: {details}")


def record_live_best(best_seq: int, exp_id: int, change: str, dev_old: float, dev_new: float,
                     heldout: float | None) -> None:
    payload = {
        "best_seq": best_seq,
        "commit": f"exp-{exp_id}",
        "experiment_id": exp_id,
        "plain_words_change": change,
        "dev_old": round(dev_old, 6),
        "dev_new": round(dev_new, 6),
        "heldout_score": None if heldout is None else round(heldout, 6),
        "timestamp": now_iso(),
    }
    LIVE_BEST.write_text(json.dumps(payload, indent=2) + "\n")
    with LIVE_UPDATES.open("a") as f:
        f.write(json.dumps(payload) + "\n")
    log(f"NEW_BEST seq={best_seq} exp={exp_id} {dev_old:.4f}->{dev_new:.4f} :: {change}")


def mutate(cfg: dict, rng: random.Random) -> tuple[dict, str]:
    c = copy.deepcopy(cfg)
    kind = rng.choice([
        "min_score", "weights", "under", "overbill", "rate", "soft_vendor",
        "expand_add", "expand_add", "expand_drop", "vendor_add", "vendor_drop", "multi",
        "grouped", "grouped", "alloc",
    ])
    parts = []
    def jitter(key, lo, hi, scale=0.05):
        old = float(c[key])
        new = min(hi, max(lo, old + rng.uniform(-scale, scale) * (hi - lo)))
        # occasional jump
        if rng.random() < 0.15:
            new = rng.uniform(lo, hi)
        c[key] = round(new, 4)
        parts.append(f"{key} {old:.4f}->{c[key]:.4f}")

    if kind == "min_score" or kind == "multi":
        jitter("min_score", 0.25, 0.70, 0.15)
    if kind == "weights" or kind == "multi":
        for k, lo, hi in (("w_name", 0.4, 0.9), ("w_campaign", 0.05, 0.35), ("w_date", 0.05, 0.35)):
            if rng.random() < 0.7 or kind == "weights":
                jitter(k, lo, hi, 0.2)
    if kind == "under" or (kind == "multi" and rng.random() < 0.5):
        jitter("underdelivery_pct", 0.80, 0.97, 0.2)
    if kind == "overbill" or (kind == "multi" and rng.random() < 0.5):
        jitter("overbill_tol", 0.005, 0.08, 0.25)
    if kind == "rate" or (kind == "multi" and rng.random() < 0.5):
        jitter("rate_tol", 0.001, 0.05, 0.25)
    if kind == "soft_vendor" or (kind == "multi" and rng.random() < 0.4):
        if rng.random() < 0.3:
            c["soft_vendor"] = not bool(c.get("soft_vendor", True))
            parts.append(f"soft_vendor->{c['soft_vendor']}")
        jitter("vendor_jaccard_min", 0.30, 0.85, 0.2)
    # grouped-matching knobs (structural baseline in match/ + exceptions/; loop tunes, never edits code)
    if kind == "grouped" or (kind == "multi" and rng.random() < 0.4):
        jitter("group_min_score_factor", 0.5, 1.0, 0.2)
        if rng.random() < 0.5:
            jitter("group_date_window_days", 0, 90, 0.2)
            c["group_date_window_days"] = int(round(c["group_date_window_days"]))
        if rng.random() < 0.5:
            jitter("merge_part_min_score", 0.15, 0.7, 0.2)
        if rng.random() < 0.1:
            c["merge_split"] = not bool(c.get("merge_split", True))
            parts.append(f"merge_split->{c['merge_split']}")
    if kind == "alloc" or (kind == "multi" and rng.random() < 0.4):
        jitter("alloc_rel_tol", 0.0, 0.08, 0.25)
        if rng.random() < 0.5:
            jitter("alloc_abs_tol", 0.0, 25.0, 0.2)
        if rng.random() < 0.3:
            jitter("date_tol_days", 0, 10, 0.3)
            c["date_tol_days"] = int(round(c["date_tol_days"]))
    if kind in ("expand_add", "multi") and rng.random() < 0.8:
        k, v = rng.choice(list(EXPAND_CANDIDATES.items()))
        c.setdefault("expand", {})[k] = v
        parts.append(f"expand+{k}={v}")
    if kind == "expand_drop" and c.get("expand"):
        k = rng.choice(list(c["expand"].keys()))
        if k not in ("mob", "dt", "prosp", "rtg"):  # keep core
            c["expand"].pop(k, None)
            parts.append(f"expand-{k}")
    added = set(c.get("vendor_aliases", {})) - BASE_ALIAS_KEYS
    vendor_ok = len(added) < MAX_VENDOR_ALIAS_ADDS
    if kind in ("vendor_add", "multi") and vendor_ok and rng.random() < (0.8 if kind == "vendor_add" else 0.15):
        k, v = rng.choice(list(VENDOR_CANDIDATES.items()))
        c.setdefault("vendor_aliases", {})[k] = v
        parts.append(f"alias+{k}")
    if kind in ("vendor_add", "multi") and rng.random() < 0.6:  # resolver knobs (structural, general)
        jitter("vendor_affinity_min", 0.3, 0.9, 0.2)
        if rng.random() < 0.5:
            jitter("vendor_vote_margin", 0.0, 0.4, 0.2)
        if rng.random() < 0.1:
            c["optimal_assign"] = not bool(c.get("optimal_assign", True))
            parts.append(f"optimal_assign->{c['optimal_assign']}")
    if kind == "vendor_drop" and c.get("vendor_aliases") and rng.random() < 0.5:
        k = rng.choice(list(c["vendor_aliases"].keys()))
        c["vendor_aliases"].pop(k, None)
        parts.append(f"alias-{k}")
    if not parts:
        jitter("min_score", 0.25, 0.70, 0.1)
    return c, "; ".join(parts)


def append_result(row: dict) -> None:
    with RESULTS.open("a") as f:
        f.write("\t".join([
            str(row["exp_id"]), row["timestamp"], str(int(row["kept"])),
            f"{row['dev_composite']:.6f}", f"{row['match_recall']:.6f}",
            f"{row['error_recall']:.6f}", f"{row['flag_precision']:.6f}",
            row["change"].replace("\t", " "),
            "" if row["heldout_composite"] is None else f"{row['heldout_composite']:.6f}",
            "" if row.get("val_composite") is None else f"{row['val_composite']:.6f}",
        ]) + "\n")


def refresh_morning(baseline: dict, best: dict, best_change: str, heldout_hist: list,
                    kept_changes: list[str], overfit_notes: list[str]) -> None:
    def row(d):
        return (f"| {d.get('label','')} | {d['composite']:.4f} | {d['match_recall']:.3f} | "
                f"{d['error_recall']:.3f} | {d['flag_precision']:.3f} |")
    lines = [
        "# Morning summary (auto-refreshed)",
        "",
        f"_Updated: {now_iso()}_",
        "",
        "## Baseline vs best (DEV)",
        "| | composite | match_recall | error_recall | flag_precision |",
        "|---|---|---|---|---|",
        row({**baseline, "label": "Baseline"}),
        row({**best, "label": "Best"}),
        "",
        f"Best change path (latest keep): `{best_change}`",
        "",
        "## Latest held-out adversarial checkpoint",
        "| checkpoint_exp | composite | match_recall | error_recall | flag_precision |",
        "|---|---|---|---|---|",
    ]
    if heldout_hist:
        h = heldout_hist[-1]
        lines.append(f"| {h['exp_id']} | {h['composite']:.4f} | {h['match_recall']:.3f} | "
                     f"{h['error_recall']:.3f} | {h['flag_precision']:.3f} |")
    else:
        lines.append("| — | — | — | — | — |")
    lines += ["", "## Validation gate (keep only if DEV improves AND validation does not drop)",
              f"Baseline validation: {VAL_STATE.get('baseline', float('nan')):.4f} | "
              f"current best validation: {VAL_STATE.get('best', float('nan')):.4f} | "
              f"gate rejections: {VAL_STATE.get('rejected', 0)}"]
    lines += ["", "## Top changes kept"]
    if kept_changes:
        for i, ch in enumerate(kept_changes[-15:], 1):
            lines.append(f"{i}. {ch}")
    else:
        lines.append("_None yet._")
    lines += ["", "## Overfitting check"]
    if overfit_notes:
        lines.extend(f"- {n}" for n in overfit_notes)
    elif len(heldout_hist) >= 2:
        a, b = heldout_hist[-2], heldout_hist[-1]
        lines.append(
            f"Last two held-out composites: {a['composite']:.4f} → {b['composite']:.4f} "
            f"(DEV best {best['composite']:.4f})."
        )
        if best["composite"] > baseline["composite"] and b["composite"] < a["composite"]:
            lines.append("**Warning:** DEV improved vs baseline while held-out dropped at last checkpoint.")
        else:
            lines.append("No clear overfitting signal at last checkpoint.")
    else:
        lines.append("_Need at least two held-out checkpoints._")
    lines += [
        "",
        "## How to read this",
        "- DEV is the selection signal (hard DEV split: generate/dev_hard.py, seeds 424201-424205).",
        "- Held-out adversarial is scored at checkpoints only and must not guide keeps.",
        "- If DEV rises while held-out falls → see `ALERT_OVERFIT`.",
        "",
    ]
    MORNING.write_text("\n".join(lines))


def main() -> None:
    AR.mkdir(exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    end_ts = time.time() + HOURS * 3600
    end_iso = datetime.fromtimestamp(end_ts, timezone.utc).isoformat()
    log(f"START pid={os.getpid()} hours={HOURS} end≈{end_iso}")

    stopping = {"flag": False}

    def _stop(signum, frame):
        stopping["flag"] = True
        log(f"signal {signum} — will stop after current experiment")

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)

    baseline_cfg = load_tunables()
    BASELINE_TUNABLES.write_text(json.dumps(baseline_cfg, indent=2) + "\n")
    try:
        baseline = run_dev(seeds=DEV_SEEDS, noise=DEV_NOISE)
    except Exception as e:
        write_stall(f"baseline eval failed: {e}\n{traceback.format_exc()}")
        raise
    log(f"BASELINE composite={baseline['composite']:.6f} "
        f"MR={baseline['match_recall']:.3f} ER={baseline['error_recall']:.3f} "
        f"FP={baseline['flag_precision']:.3f}")

    BASE_ALIAS_KEYS.update(baseline_cfg.get("vendor_aliases", {}).keys())
    val_best = run_validation()
    VAL_STATE.update(baseline=val_best["composite"], best=val_best["composite"], rejected=0)
    log(f"BASELINE validation={val_best['composite']:.6f} MR={val_best['match_recall']:.3f} "
        f"ER={val_best['error_recall']:.3f} FP={val_best['flag_precision']:.3f}")
    try:
        h0 = evaluate_adversarial()
        log(f"BASELINE heldout_checkpoint={h0['composite']:.6f}")
    except Exception as e:
        h0 = None
        log(f"baseline checkpoint error: {e}")

    best = dict(baseline)
    best_cfg = copy.deepcopy(baseline_cfg)
    BEST_TUNABLES.write_text(json.dumps(best_cfg, indent=2) + "\n")
    best_change = "(baseline)"
    best_seq = 0
    record_live_best(0, 0, "baseline", baseline["composite"], baseline["composite"], None)

    kept_changes: list[str] = []
    heldout_hist: list[dict] = []
    overfit_notes: list[str] = []
    last_heldout_score: float | None = None if h0 is None else h0["composite"]
    kept_since_ckpt = 0
    exp_id = 0
    last_progress = time.time()
    rng = random.Random(20261016)

    refresh_morning(baseline, best, best_change, heldout_hist, kept_changes, overfit_notes)

    try:
        while time.time() < end_ts and not stopping["flag"]:
            exp_id += 1
            # stall detection between experiments
            if time.time() - last_progress > STALL_MINUTES * 60:
                write_stall(f"No completed experiment for {STALL_MINUTES} minutes "
                            f"(last_progress={datetime.fromtimestamp(last_progress, timezone.utc).isoformat()})")

            proposal, change = mutate(best_cfg, rng)
            save_tunables(proposal)
            try:
                dev = run_dev(seeds=DEV_SEEDS, noise=DEV_NOISE)
            except Exception as e:
                log(f"exp {exp_id} EVAL ERROR: {e}")
                save_tunables(best_cfg)
                write_stall(f"eval error at exp {exp_id}: {e}\n{traceback.format_exc()}")
                append_result({
                    "exp_id": exp_id, "timestamp": now_iso(), "kept": False,
                    "dev_composite": 0.0, "match_recall": 0.0, "error_recall": 0.0,
                    "flag_precision": 0.0, "change": f"ERROR {change}", "heldout_composite": None,
                })
                last_progress = time.time()
                continue

            specific = ("alias" in change) and not any(t in change for t in ("min_score", "w_", "tol", "expand"))
            need = SPECIFIC_MIN_GAIN if specific else 1e-9
            dev_up = dev["composite"] > best["composite"] + need
            val = None
            improved = False
            if dev_up:
                val = run_validation()
                improved = val["composite"] >= val_best["composite"] - VAL_TOL
                if not improved:
                    VAL_STATE["rejected"] = VAL_STATE.get("rejected", 0) + 1
                    log(f"exp {exp_id} REJECTED by validation gate: DEV {best['composite']:.4f}->"
                        f"{dev['composite']:.4f} but VAL {val_best['composite']:.4f}->{val['composite']:.4f} :: {change}")
                    change = f"[VAL-GATE {val['composite']:.4f}<{val_best['composite']:.4f}] " + change
            heldout_val = None
            do_ckpt = False
            if improved:
                do_ckpt = (kept_since_ckpt + 1) >= CHECKPOINT_EVERY_KEPT
            if exp_id % CHECKPOINT_EVERY_EXP == 0:
                do_ckpt = True

            if do_ckpt:
                try:
                    h = evaluate_adversarial()
                    heldout_val = h["composite"]
                    entry = {
                        "exp_id": exp_id,
                        "composite": h["composite"],
                        "match_recall": h["match_recall"],
                        "error_recall": h["error_recall"],
                        "flag_precision": h["error_precision"],
                    }
                    heldout_hist.append(entry)
                    if last_heldout_score is not None and improved and heldout_val < last_heldout_score - 1e-6:
                        note = (f"exp {exp_id}: DEV {best['composite']:.4f}->{dev['composite']:.4f} "
                                f"but held-out {last_heldout_score:.4f}->{heldout_val:.4f}")
                        overfit_notes.append(note)
                        write_overfit({
                            "exp_id": exp_id, "change": change,
                            "dev_old": best["composite"], "dev_new": dev["composite"],
                            "heldout_old": last_heldout_score, "heldout_new": heldout_val,
                            "timestamp": now_iso(),
                        })
                    last_heldout_score = heldout_val
                    log(f"CHECKPOINT exp={exp_id} heldout={heldout_val:.6f}")
                except Exception as e:
                    log(f"checkpoint error: {e}")
                    write_stall(f"held-out checkpoint failed exp {exp_id}: {e}\n{traceback.format_exc()}")

            if improved:
                old = best["composite"]
                best = dict(dev)
                val_best = val
                VAL_STATE["best"] = val["composite"]
                best_cfg = copy.deepcopy(proposal)
                BEST_TUNABLES.write_text(json.dumps(best_cfg, indent=2) + "\n")
                best_change = change
                best_seq += 1
                kept_since_ckpt = 0 if do_ckpt else kept_since_ckpt + 1
                kept_changes.append(f"exp {exp_id}: {change} (dev {old:.4f}->{dev['composite']:.4f})")
                record_live_best(best_seq, exp_id, change, old, dev["composite"], heldout_val)
            else:
                save_tunables(best_cfg)  # revert
                kept_since_ckpt = kept_since_ckpt  # unchanged

            append_result({
                "exp_id": exp_id, "timestamp": now_iso(), "kept": improved,
                "dev_composite": dev["composite"], "match_recall": dev["match_recall"],
                "error_recall": dev["error_recall"], "flag_precision": dev["flag_precision"],
                "change": change, "heldout_composite": heldout_val,
                "val_composite": None if val is None else val["composite"],
            })
            last_progress = time.time()
            if exp_id % 5 == 0 or improved:
                refresh_morning(baseline, best, best_change, heldout_hist, kept_changes, overfit_notes)
                log(f"exp {exp_id} kept={improved} dev={dev['composite']:.6f} best={best['composite']:.6f} :: {change}")

        # final
        save_tunables(best_cfg)
        refresh_morning(baseline, best, best_change, heldout_hist, kept_changes, overfit_notes)
        log(f"DONE experiments={exp_id} best={best['composite']:.6f} baseline={baseline['composite']:.6f}")
    except Exception as e:
        write_stall(f"loop crash: {e}\n{traceback.format_exc()}")
        save_tunables(best_cfg)
        raise


if __name__ == "__main__":
    main()
