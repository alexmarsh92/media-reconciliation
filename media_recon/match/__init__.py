"""Match invoice and delivery lines to IO lines (one-to-one, greedy by score)."""
from __future__ import annotations

import re

from ..schema import LineItem, Match

EXPAND = {"mob": "mobile", "dt": "desktop", "prosp": "prospecting", "rtg": "retargeting",
          "vid": "video", "disp": "display", "prem": "premium", "srch": "search"}
MAKEGOOD = re.compile(r"(^|[\s_\-])(mg|makegood|make good|bonus|adu)($|[\s_\-])", re.I)
MIN_SCORE = 0.45


def tokens(s: str) -> set[str]:
    return {EXPAND.get(t, t) for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def name_sim(rec: LineItem, io: LineItem) -> float:
    r = tokens(rec.placement) - tokens(rec.campaign)   # delivery names are prefixed with the campaign
    return jaccard(r or tokens(rec.placement), tokens(io.placement))


def date_overlap(a: LineItem, b: LineItem) -> float:
    if not (a.start and a.end and b.start and b.end):
        return 0.5
    inter = (min(a.end, b.end) - max(a.start, b.start)).days + 1
    span = (max(a.end, b.end) - min(a.start, b.start)).days + 1
    return max(inter, 0) / span


def score(rec: LineItem, io: LineItem) -> float:
    if rec.vendor.lower() != io.vendor.lower():
        return 0.0
    if rec.io_number and io.io_number and rec.io_number != io.io_number:
        return 0.0
    camp = jaccard(tokens(rec.campaign), tokens(io.campaign)) if rec.campaign else 0.5
    return round(0.7 * name_sim(rec, io) + 0.15 * camp + 0.15 * date_overlap(rec, io), 3)


def is_makegood(rec: LineItem) -> bool:
    return bool(MAKEGOOD.search(rec.placement or ""))


def assign(records: list[LineItem], ios: list[LineItem]) -> dict[str, tuple[str, float]]:
    pairs = sorted(((score(r, io), r.record_id, io.record_id) for r in records for io in ios
                    if not is_makegood(r)), reverse=True)
    out, used = {}, set()
    for s, rid, iid in pairs:
        if s < MIN_SCORE or rid in out or iid in used:
            continue
        out[rid] = (iid, s)
        used.add(iid)
    return out


def match(records: list[LineItem]) -> tuple[list[Match], dict[str, str]]:
    """Returns one Match per IO line, plus record_id -> io_id for every matched record."""
    by_src = {s: [r for r in records if r.source == s] for s in ("io", "invoice", "delivery")}
    cite = {r.record_id: r.citation for r in records}
    inv = assign(by_src["invoice"], by_src["io"])
    dlv = assign(by_src["delivery"], by_src["io"])
    inv_by_io = {iid: (rid, s) for rid, (iid, s) in inv.items()}
    dlv_by_io = {iid: (rid, s) for rid, (iid, s) in dlv.items()}
    matches = []
    for io in by_src["io"]:
        i, d = inv_by_io.get(io.record_id), dlv_by_io.get(io.record_id)
        scores = [x[1] for x in (i, d) if x]
        conf = round(sum(scores) / len(scores), 3) if scores else 0.0
        ids = [io.record_id] + [x[0] for x in (i, d) if x]
        matches.append(Match(io.record_id, i and i[0], d and d[0], conf, [cite[x] for x in ids]))
    flat = {rid: iid for rid, (iid, _) in {**inv, **dlv}.items()}
    return matches, flat
