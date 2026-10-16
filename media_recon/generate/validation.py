"""VALIDATION split (gate only) — separate seed space AND vocabulary/knobs from BOTH
hard DEV (generate/dev_hard.py, seeds 4242xx) and the final held-out set
(data/adversarial, seed 909091).

Reuses the dev_hard file-writing machinery but swaps in:
- a vendor universe disjoint from DEV and held-out (no shared vendor aliases, so
  vendor-specific alias tweaks learned on DEV cannot help here; only general logic can),
- different placement vocabulary, abbreviation table, OCR confusion map, date styles,
- different error mix / decoy / merge / cross-period probabilities,
- seeds in the 7713xx range.

Used by autoresearch as a NON-REGRESSION gate: a change is kept only if DEV improves
AND validation does not drop. Never used to propose changes.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from pathlib import Path

from . import dev_hard

VAL_SEEDS = (771301, 771302, 771303, 771304)

VENDORS = [
    ("Taboola", ["Taboola Inc", "Taboola Ltd.", "Tabola"], "CPC",
     ["Native Feed Recommendation", "Homepage Widget Desktop", "Video Native Mobile"]),
    ("Outbrain", ["Outbrain Inc", "Outbrian", "OB Amplify"], "CPC",
     ["Amplify Feed Prospecting", "Smartfeed Mobile Native", "Clip Video Outstream"]),
    ("Criteo", ["Criteo SA", "Criteo S.A.", "Criteo Retail Media"], "CPM",
     ["Dynamic Retargeting Display", "Retail Media Sponsored Products", "Commerce Video Prospecting"]),
    ("Nextdoor Ads", ["Nextdoor", "Next Door", "Nextdoor Inc"], "CPM",
     ["Neighborhood Feed Sponsored", "Local Deals Takeover", "Sidebar Display Desktop"]),
    ("Quora Ads", ["Quora", "Quora Inc"], "CPC",
     ["Question Targeting Text", "Image Ads Consideration", "Lead Gen Form Ads"]),
    ("X Ads", ["Twitter Ads", "X Corp", "Twitter"], "CPM",
     ["Promoted Post Awareness", "Amplify Pre-Roll Video", "Trend Takeover Homepage"]),
    ("SiriusXM Media", ["Pandora", "SiriusXM", "Sirius XM Media"], "CPM",
     ["Audio Streaming Prime Time", "Podcast Midroll Network", "Display Companion Mobile"]),
    ("Samsung Ads", ["Samsung", "Samsung Electronics Ads", "Samsung TV Plus"], "CPM",
     ["CTV Home Screen First Look", "Universal Guide Video 15s", "Mobile Display Prospecting"]),
]
CAMPAIGNS = ["Back To School 2026", "Black Friday Countdown", "Regional Expansion", "Evergreen Brand"]
ABBR = {
    "Recommendation": "Rec", "Desktop": "DSK", "Mobile": "Mbl", "Prospecting": "Prspct",
    "Retargeting": "ReTgt", "Display": "Dspl", "Sponsored": "Spnsd", "Video": "Vdo",
    "Homepage": "HmPg", "Network": "Netwk", "Consideration": "Consid", "Awareness": "Awrns",
    "Products": "Prods", "Native": "Ntv", "Takeover": "TO", "Streaming": "Strm",
}
OCR = str.maketrans({"e": "c", "a": "o", "r": "n", "t": "f", "E": "F", "D": "O", "m": "rn"})
DATE_STYLES = ["%Y.%m.%d", "%d-%m-%Y", "%b %d %Y", "%m/%d/%Y", "%Y-%m-%d"]
INV_DATE_STYLES = ["%d %b %Y", "%Y.%m.%d", "%m/%d/%Y"]
P_ERR = {
    "overbilling": 0.07, "underdelivery": 0.10, "rate_mismatch": 0.08, "missing_invoice": 0.05,
    "currency_mismatch": 0.06, "date_mismatch": 0.05, "partial_makegood": 0.07,
}
KNOBS = dict(CROSS_P=0.14, SPLIT_P=0.07, FEE_P=0.15, MERGE_P=0.25, ABBR_P=0.45,
             INV_CANON_W=8, INV_TYPO_P=0.08)

_LOCK = threading.Lock()


@contextmanager
def _swapped():
    names = dict(VENDORS=VENDORS, CAMPAIGNS=CAMPAIGNS, ABBR=ABBR, OCR=OCR, DATE_STYLES=DATE_STYLES,
                 INV_DATE_STYLES=INV_DATE_STYLES, P_ERR=P_ERR, **KNOBS)
    with _LOCK:
        saved = {k: getattr(dev_hard, k) for k in names}
        try:
            for k, v in names.items():
                setattr(dev_hard, k, v)
            yield
        finally:
            for k, v in saved.items():
                setattr(dev_hard, k, v)


def generate(out: Path, seed: int = VAL_SEEDS[0]) -> dict:
    with _swapped():
        gold = dev_hard.generate(out, seed=seed)
    if isinstance(gold, dict):
        gold["split"] = "validation"
    return gold
