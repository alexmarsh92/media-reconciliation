"""Live tunables for matching and exception thresholds.

Autoresearch mutates tunables.json only. Defaults live here so the package works
without that file. Never load held-out adversarial into selection logic.
"""
from __future__ import annotations

import json
from pathlib import Path

_DEFAULTS = {
    # grouped matching (one-to-many, many-to-one, cross-period allocation)
    "enable_grouped": True,
    "group_min_score_factor": 0.85,   # extra lines join a group at >= min_score * factor
    "group_date_window_days": 45,     # extra lines must overlap/within this many days of the flight
    "merge_split": True,              # split "A & B" invoice lines into parts and cover both IOs
    "merge_part_min_score": 0.35,
    "alloc_rel_tol": 0.02,            # aggregate tolerance for grouped invoice vs earned
    "alloc_abs_tol": 1.0,             # $ slack for rounding across split/monthly lines
    "date_tol_days": 0,
    "fee_lines_as_exceptions": False, # non-media fee lines (ad serving, tech, production) are not IO lines

    # vendor entity resolution + optimal assignment (jump plan)
    "vendor_resolve": True,
    "vendor_affinity_min": 0.5,
    "vendor_vote_margin": 0.1,
    "optimal_assign": True,
    "optimal_max_regret": 0.15,

    "min_score": 0.45,
    "w_name": 0.70,
    "w_campaign": 0.15,
    "w_date": 0.15,
    "underdelivery_pct": 0.90,
    "overbill_tol": 0.02,
    "rate_tol": 0.005,
    "soft_vendor": True,
    "vendor_jaccard_min": 0.55,
    "expand": {
        "mob": "mobile",
        "dt": "desktop",
        "prosp": "prospecting",
        "rtg": "retargeting",
        "vid": "video",
        "disp": "display",
        "prem": "premium",
        "srch": "search",
        "fb": "meta",
        "ig": "instagram",
        "yt": "youtube",
        "tt": "tiktok",
        "ctv": "ctv",
        "olv": "online",
        "impr": "impressions",
        "clk": "clicks",
    },
    "vendor_aliases": {
        "meta": "meta platforms",
        "facebook": "meta platforms",
        "facebook ads": "meta platforms",
        "meta platforms inc": "meta platforms",
        "meta platforms, inc.": "meta platforms",
        "fb ads": "meta platforms",
        "google": "google ads",
        "google ads llc": "google ads",
        "adwords": "google ads",
        "ttd": "the trade desk",
        "thetradedesk": "the trade desk",
        "trade desk": "the trade desk",
        "amazon ads": "amazon advertising",
        "amazon dsp": "amazon advertising",
        "ams": "amazon advertising",
        "hulu": "hulu ad manager",
        "disney hulu": "hulu ad manager",
        "spotify": "spotify advertising",
        "spotify ads": "spotify advertising",
    },
    "extra_date_formats": [
        "%Y/%m/%d",
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y.%m.%d",
        "%m-%d-%Y",
        "%b %d %Y",
        "%d %b %Y",
    ],
}


def _path() -> Path:
    return Path(__file__).with_name("tunables.json")


def load() -> dict:
    p = _path()
    data = dict(_DEFAULTS)
    if p.exists():
        raw = json.loads(p.read_text())
        data.update(raw)
        # nested merges for dict tunables
        for key in ("expand", "vendor_aliases"):
            if key in raw and isinstance(raw[key], dict):
                merged = dict(_DEFAULTS[key])
                merged.update(raw[key])
                data[key] = merged
        if "extra_date_formats" in raw:
            # union preserving order
            seen, formats = set(), []
            for f in list(_DEFAULTS["extra_date_formats"]) + list(raw["extra_date_formats"]):
                if f not in seen:
                    formats.append(f)
                    seen.add(f)
            data["extra_date_formats"] = formats
    return data


def save(data: dict) -> None:
    _path().write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def reset_to_defaults() -> dict:
    save(dict(_DEFAULTS))
    return load()
