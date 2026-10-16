"""SEALED held-out split (v2). Built 2026-10-16 after the old held-out (data/adversarial) was
opened for error analysis and demoted to a diagnostic set.

NEVER read by autoresearch/loop.py, tuning, or error analysis. Scored only at checkpoints via
`python -m media_recon.eval.sealed_eval` against the frozen files in data/sealed_holdout/
(hash recorded in data/sealed_holdout/SHA256).

Author style differs from DEV, validation and the old held-out: a disjoint vendor universe built
around the observed failure modes (rebrands with no shared characters, legal-suffix noise, typos),
canonical vendor names almost never used on invoices, heavier abbreviation/OCR, more merges,
splits and cross-period billing, plus novel stresses (dotted/slashed abbreviations, all-caps
author style, a different OCR confusion map and error mix).
"""
from __future__ import annotations

from pathlib import Path

from . import validation as _v

SEALED_SEEDS = (555011, 555012, 555013)

VENDORS = [
    ("Pandora Media", ["SiriusXM Audio", "Pandora Inc.", "Pandroa"], "CPM",
     ["Audio Everywhere Drive Time", "Video Plus Rewarded", "Podcast Host Read Network"]),
    ("Vevo Ads", ["Vevo LLC", "VEVO Music Video", "Veov"], "CPM",
     ["Music Video Preroll 15s", "CTV Channel Sponsorship", "Homepage Masthead Desktop"]),
    ("Waze Ads", ["Google Waze", "Waze Local", "Wazee Ads"], "CPM",
     ["Pin Promoted Local", "Takeover Zero Speed", "Search Arrow Mobile"]),
    ("Twitch Advertising", ["Amazon Twitch", "Twitch Interactive Inc", "Twich"], "CPM",
     ["Stream Display Premium", "Preroll Video Gaming", "Homepage Carousel Takeover"]),
    ("Meta Audience Network", ["Facebook AN", "FAN", "Meta Platforms Ireland Ltd"], "CPM",
     ["Rewarded Video Mobile", "Native Banner Prospecting", "Interstitial Retargeting"]),
    ("Viant DSP", ["Adelphic", "Viant Technology LLC", "Vaint"], "CPM",
     ["Household CTV Prospecting", "Linear Addressable Video", "DOOH Billboard Network"]),
    ("Kargo", ["Kargo Global Inc", "Kargo Mobile", "Krago"], "CPM",
     ["Breakout Display Mobile", "Venti Video Outstream", "Social Canvas Retargeting"]),
    ("StackAdapt", ["Stack Adapt Inc", "StackAdapt Programmatic", "Stackadpt"], "CPC",
     ["Native Contextual Prospecting", "Display Retargeting Desktop", "Audio Streaming Awareness"]),
]
CAMPAIGNS = ["Holiday Sprint 2026", "Brand Lift Q4", "Store Openings West", "Clearance Push"]
ABBR = {"Prospecting": "Prsp.", "Retargeting": "R/T", "Video": "VID.", "Mobile": "MBL", "Desktop": "D/T",
        "Display": "DISP.", "Network": "NTWK", "Takeover": "T/O", "Homepage": "H/P", "Premium": "PREM",
        "Awareness": "AWRNS", "Streaming": "STRM", "Contextual": "CTXL", "Sponsorship": "SPONS",
        "Household": "HH", "Interstitial": "INTSTL", "Rewarded": "RWD", "Outstream": "O/S"}
OCR = str.maketrans({"a": "@", "o": "0", "s": "5", "u": "v", "h": "b", "I": "l", "C": "G"})
DATE_STYLES = ["%d.%m.%Y", "%Y-%m-%d", "%B %d %Y", "%m/%d/%Y"]
INV_DATE_STYLES = ["%B %d %Y", "%d %b %Y", "%Y-%m-%d"]
P_ERR = {"overbilling": 0.08, "underdelivery": 0.08, "rate_mismatch": 0.07, "missing_invoice": 0.06,
         "currency_mismatch": 0.05, "date_mismatch": 0.07, "partial_makegood": 0.06}
KNOBS = dict(CROSS_P=0.3, SPLIT_P=0.12, FEE_P=0.25, MERGE_P=0.4, ABBR_P=0.55, INV_CANON_W=1, INV_TYPO_P=0.15)


def generate(out: Path, seed: int = SEALED_SEEDS[0]) -> dict:
    saved = {k: getattr(_v, k) for k in ("VENDORS", "CAMPAIGNS", "ABBR", "OCR", "DATE_STYLES",
                                          "INV_DATE_STYLES", "P_ERR", "KNOBS")}
    try:
        _v.VENDORS, _v.CAMPAIGNS, _v.ABBR, _v.OCR = VENDORS, CAMPAIGNS, ABBR, OCR
        _v.DATE_STYLES, _v.INV_DATE_STYLES, _v.P_ERR, _v.KNOBS = DATE_STYLES, INV_DATE_STYLES, P_ERR, KNOBS
        gold = _v.generate(out, seed=seed)
    finally:
        for k, v in saved.items():
            setattr(_v, k, v)
    gold.update(split="sealed_holdout_v2", held_out=True, do_not_use_for_selection=True)
    import json
    (out / "gold.json").write_text(json.dumps(gold, indent=1, default=str))
    return gold
