"""Match invoice and delivery lines to IO lines: grouped (default) or legacy one-to-one greedy."""
from __future__ import annotations

import re

from ..schema import LineItem, Match
from ..tunables import load as load_tunables

MAKEGOOD = re.compile(r"(^|[\s_\-])(mg|makegood|make good|bonus|adu|added.?value|av)($|[\s_\-])", re.I)


def _cfg():
    return load_tunables()


def norm_vendor(v: str) -> str:
    cfg = _cfg()
    key = re.sub(r"\s+", " ", (v or "").lower().strip(" .,"))
    aliases = cfg.get("vendor_aliases", {})
    if key in aliases:
        return aliases[key]
    key2 = re.sub(r"\b(inc|llc|ltd|co|corp|corporation|advertising|ads|platforms)\b\.?", "", key)
    key2 = re.sub(r"\s+", " ", key2).strip(" .,")
    return aliases.get(key2, key2 or key)


def tokens(s: str) -> set[str]:
    expand = _cfg().get("expand", {})
    return {expand.get(t, t) for t in re.split(r"[^a-z0-9]+", (s or "").lower()) if t}


def jaccard(a: set, b: set) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def vendors_compatible(a: str, b: str) -> bool:
    cfg = _cfg()
    na, nb = norm_vendor(a), norm_vendor(b)
    if na == nb:
        return True
    if not cfg.get("soft_vendor", True):
        return False
    return jaccard(tokens(na), tokens(nb)) >= float(cfg.get("vendor_jaccard_min", 0.55))


def name_sim(rec: LineItem, io: LineItem) -> float:
    r = tokens(rec.placement) - tokens(rec.campaign)
    return jaccard(r or tokens(rec.placement), tokens(io.placement))


def date_overlap(a: LineItem, b: LineItem) -> float:
    if not (a.start and a.end and b.start and b.end):
        return 0.5
    inter = (min(a.end, b.end) - max(a.start, b.start)).days + 1
    span = (max(a.end, b.end) - min(a.start, b.start)).days + 1
    return max(inter, 0) / span


def score(rec: LineItem, io: LineItem) -> float:
    cfg = _cfg()
    if not vendors_compatible(rec.vendor, io.vendor):
        return 0.0
    if rec.io_number and io.io_number:
        a, b = rec.io_number.strip().upper(), io.io_number.strip().upper()
        if a != b and a not in b and b not in a:
            return 0.0
    camp = jaccard(tokens(rec.campaign), tokens(io.campaign)) if rec.campaign else 0.5
    wn = float(cfg.get("w_name", 0.70))
    wc = float(cfg.get("w_campaign", 0.15))
    wd = float(cfg.get("w_date", 0.15))
    total = wn + wc + wd
    if total <= 0:
        total = 1.0
    return round((wn * name_sim(rec, io) + wc * camp + wd * date_overlap(rec, io)) / total, 3)


def is_makegood(rec: LineItem) -> bool:
    return bool(MAKEGOOD.search(rec.placement or ""))


def assign(records: list[LineItem], ios: list[LineItem]) -> dict[str, tuple[str, float]]:
    min_score = float(_cfg().get("min_score", 0.45))
    pairs = sorted(((score(r, io), r.record_id, io.record_id) for r in records for io in ios
                    if not is_makegood(r)), reverse=True)
    out, used = {}, set()
    for s, rid, iid in pairs:
        if s < min_score or rid in out or iid in used:
            continue
        out[rid] = (iid, s)
        used.add(iid)
    return out


FEE = re.compile(r"\b(fee|fees|serving|production|platform tech|tech fee|service charge)\b", re.I)
SPLIT_SUFFIX = re.compile(r"\s*\(\d+\s*/\s*\d+\)\s*$")
MERGE_SEP = re.compile(r"\s+&\s+|\s+\+\s+")


def is_fee(rec: LineItem) -> bool:
    return rec.source == "invoice" and bool(FEE.search(rec.placement or ""))


def _clean(rec: LineItem, placement: str | None = None) -> LineItem:
    from dataclasses import replace
    return replace(rec, placement=SPLIT_SUFFIX.sub("", placement if placement is not None else rec.placement or ""))


def _within_window(rec: LineItem, io: LineItem, days: int) -> bool:
    if not (rec.start and rec.end and io.start and io.end):
        return True
    return (rec.start - io.end).days <= days and (io.start - rec.end).days <= days


def assign_grouped(records: list[LineItem], ios: list[LineItem]):
    """Grouped assignment.

    Pass 0: merged lines ("A & B") are split into parts; each part is scored, the record is assigned to
            the best part's IO and the other parts' IOs are recorded as covered (many-to-one).
    Pass 1: one-to-one greedy (as before) on cleaned placements (split suffixes like "(1/2)" stripped).
    Pass 2: leftovers join an already-matched IO (one-to-many: split lines, month-by-month billing) when
            score >= min_score * group_min_score_factor and within the flight window.
    Returns (assign: rid -> (io_id, score), covered: rid -> [io_id, ...]).
    """
    cfg = _cfg()
    min_score = float(cfg.get("min_score", 0.45))
    factor = float(cfg.get("group_min_score_factor", 0.85))
    window = int(cfg.get("group_date_window_days", 45))
    part_min = float(cfg.get("merge_part_min_score", 0.35))
    pool = [r for r in records if not is_makegood(r) and not (is_fee(r) and not cfg.get("fee_lines_as_exceptions"))]
    out: dict[str, tuple[str, float]] = {}
    covered: dict[str, list[str]] = {}
    used: set[str] = set()
    if cfg.get("merge_split", True):
        for r in pool:
            parts = [p for p in MERGE_SEP.split(r.placement or "") if p.strip()]
            if len(parts) < 2:
                continue
            picks = []
            for p in parts:
                c = _clean(r, p)
                best = max(((score(c, io), io.record_id) for io in ios if io.record_id not in used), default=(0, None))
                if best[1] and best[0] >= part_min and best[1] not in [x[1] for x in picks]:
                    picks.append(best)
            if len(picks) >= 2:
                picks.sort(reverse=True)
                out[r.record_id] = (picks[0][1], round(sum(x[0] for x in picks) / len(picks), 3))
                covered[r.record_id] = [x[1] for x in picks[1:]]
                used.update(x[1] for x in picks)
    cleaned = {r.record_id: _clean(r) for r in pool if r.record_id not in out}
    pairs = sorted(((score(c, io), rid, io.record_id) for rid, c in cleaned.items() for io in ios), reverse=True)
    for sc, rid, iid in pairs:
        if sc < min_score or rid in out or iid in used:
            continue
        out[rid] = (iid, sc)
        used.add(iid)
    io_by = {io.record_id: io for io in ios}
    for sc, rid, iid in pairs:
        if rid in out or iid not in used or sc < min_score * factor:
            continue
        if not _within_window(cleaned[rid], io_by[iid], window):
            continue
        out[rid] = (iid, sc)
    return out, covered


def match(records: list[LineItem]) -> tuple[list[Match], dict[str, str]]:
    """Returns one Match per IO line, plus record_id -> io_id for every matched record."""
    if not _cfg().get("enable_grouped", False):
        return _match_1to1(records)
    by_src = {s: [r for r in records if r.source == s] for s in ("io", "invoice", "delivery")}
    cite = {r.record_id: r.citation for r in records}
    inv, inv_cov = assign_grouped(by_src["invoice"], by_src["io"])
    dlv, _ = assign_grouped(by_src["delivery"], by_src["io"])
    groups = {io.record_id: {"inv": [], "dlv": [], "cov": []} for io in by_src["io"]}
    for rid, (iid, s) in sorted(inv.items(), key=lambda x: -x[1][1]):
        groups[iid]["inv"].append((rid, s))
    for rid, (iid, s) in sorted(dlv.items(), key=lambda x: -x[1][1]):
        groups[iid]["dlv"].append((rid, s))
    for rid, iids in inv_cov.items():
        for iid in iids:
            groups[iid]["cov"].append(rid)
    matches = []
    for io in by_src["io"]:
        g = groups[io.record_id]
        scores = [s for _, s in g["inv"][:1] + g["dlv"][:1]]
        conf = round(sum(scores) / len(scores), 3) if scores else 0.0
        if len(g["inv"]) > 1 or len(g["dlv"]) > 1 or g["cov"]:
            conf = round(conf * 0.95, 3)  # grouped matches are slightly less certain
        ids = [io.record_id] + [r for r, _ in g["inv"]] + [r for r, _ in g["dlv"]] + g["cov"]
        matches.append(Match(io.record_id, g["inv"][0][0] if g["inv"] else None,
                             g["dlv"][0][0] if g["dlv"] else None, conf, [cite[x] for x in ids],
                             invoice_ids=[r for r, _ in g["inv"]], delivery_ids=[r for r, _ in g["dlv"]],
                             covered_by=g["cov"]))
    flat = {rid: iid for rid, (iid, _) in {**inv, **dlv}.items()}
    return matches, flat


def _match_1to1(records: list[LineItem]) -> tuple[list[Match], dict[str, str]]:
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
