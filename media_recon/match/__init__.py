"""Match invoice and delivery lines to IO lines: grouped (default) or legacy one-to-one greedy."""
from __future__ import annotations

import re

from ..schema import LineItem, Match
from ..tunables import load as load_tunables

MAKEGOOD = re.compile(r"(^|[\s_\-])(mg|makegood|make good|bonus|adu|added.?value|av)($|[\s_\-])", re.IGNORECASE)


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


FEE = re.compile(r"\b(fee|fees|serving|production|platform tech|tech fee|service charge)\b", re.IGNORECASE)
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


def hungarian_max(w: list[list[float]]) -> list[tuple[int, int]]:
    """Maximum-weight one-to-one assignment (pure-Python Hungarian, rectangular ok). Returns (row, col)."""
    n, m = len(w), len(w[0]) if w else 0
    if not n or not m:
        return []
    t = n > m
    if t:
        w = [list(c) for c in zip(*w)]; n, m = m, n
    INF = float("inf")
    u, v, p, way = [0.0] * (n + 1), [0.0] * (m + 1), [0] * (m + 1), [0] * (m + 1)
    for i in range(1, n + 1):
        p[0], j0 = i, 0
        minv, usedc = [INF] * (m + 1), [False] * (m + 1)
        while True:
            usedc[j0] = True
            i0, delta, j1 = p[j0], INF, 0
            for j in range(1, m + 1):
                if not usedc[j]:
                    cur = -w[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j], way[j] = cur, j0
                    if minv[j] < delta:
                        delta, j1 = minv[j], j
            for j in range(m + 1):
                if usedc[j]:
                    u[p[j]] += delta; v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]; p[j0] = p[j1]; j0 = j1
    res = [(p[j] - 1, j - 1) for j in range(1, m + 1) if p[j]]
    return [(c, r) for r, c in res] if t else res


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
    if cfg.get("optimal_assign", True):
        # Optimal one-to-one assignment over candidate edges within `regret` of each line's best IO
        # (fixes greedy near-duplicate swaps). Lines left over join groups in pass 2 rather than
        # being forced onto a worse IO.
        regret = float(cfg.get("optimal_max_regret", 0.15))
        rids = [rid for rid in cleaned if rid not in out]
        iids = [io.record_id for io in ios if io.record_id not in used]
        sm = {(rid, iid): sc for sc, rid, iid in pairs}
        best_row = {r: max((sm.get((r, c), 0.0) for c in iids), default=0.0) for r in rids}
        ok = lambda r, c: sm.get((r, c), 0.0) >= min_score and best_row[r] - sm.get((r, c), 0.0) <= regret
        for i, j in hungarian_max([[sm[(r, c)] if ok(r, c) else 0.0 for c in iids] for r in rids]):
            if ok(rids[i], iids[j]):
                out[rids[i]] = (iids[j], sm[(rids[i], iids[j])])
                used.add(iids[j])
    else:
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


def _compact(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (v or "").lower())


def _trigrams(v: str) -> set[str]:
    c = f"  {_compact(v)} "
    return {c[i:i + 3] for i in range(len(c) - 2)}


def _strip_corp(v: str) -> str:
    k = re.sub(r"\s+", " ", (v or "").lower().strip(" .,"))
    k = re.sub(r"\b(inc|llc|ltd|co|corp|corporation|advertising|ads|platforms|media|marketing|solutions|sa|s\.a)\b\.?", "", k)
    return _compact(k)


def name_affinity(v: str, io_vendor: str) -> float:
    """String-level similarity of a vendor string to an IO vendor (0..1), alias- and typo-tolerant."""
    if norm_vendor(v) == norm_vendor(io_vendor):
        return 1.0
    a, b = _strip_corp(v), _strip_corp(io_vendor)
    if a and b and (a == b or (min(len(a), len(b)) >= 4 and (a in b or b in a))):
        return 0.95
    ca, cb = _compact(v), _compact(io_vendor)
    if ca and cb and (ca in cb or cb in ca) and min(len(ca), len(cb)) >= 4:
        return 0.9
    return jaccard(_trigrams(a or v), _trigrams(b or io_vendor))


def resolve_vendors(records: list[LineItem]) -> list[LineItem]:
    """Entity resolution of invoice/delivery vendor strings onto the IO vendor universe.

    Evidence, strongest first: IO number on the line, string affinity (aliases, legal suffixes,
    typos via char trigrams), then a document-level vote of placement similarity against each IO
    vendor's placements (handles rebrands like Twitter -> X with no shared characters).
    """
    from dataclasses import replace
    cfg = _cfg()
    if not cfg.get("vendor_resolve", True):
        return records
    ios = [r for r in records if r.source == "io"]
    io_vendors = sorted({r.vendor for r in ios})
    if not io_vendors:
        return records
    by_ion = {}
    for r in ios:
        if r.io_number:
            by_ion.setdefault(r.io_number.strip().upper(), set()).add(r.vendor)
    aff_min = float(cfg.get("vendor_affinity_min", 0.5))
    vote_margin = float(cfg.get("vendor_vote_margin", 0.1))
    groups: dict[str, list[LineItem]] = {}
    for r in records:
        if r.source != "io":
            groups.setdefault(r.vendor, []).append(r)
    mapping = {}
    for v, rs in groups.items():
        if v in io_vendors:
            continue
        ion = {x for r in rs if r.io_number for x in by_ion.get(r.io_number.strip().upper(), ())}
        if len(ion) == 1:
            mapping[v] = next(iter(ion)); continue
        aff = sorted(((name_affinity(v, iv), iv) for iv in io_vendors), reverse=True)
        if aff[0][0] >= aff_min and (len(aff) == 1 or aff[0][0] - aff[1][0] >= 0.05):
            mapping[v] = aff[0][1]; continue
        vote = []
        for iv in io_vendors:
            pls = [io for io in ios if io.vendor == iv]
            sims = [max(name_sim(_clean(r), io) for io in pls) for r in rs]
            vote.append((sum(sims) / len(sims) + 0.2 * name_affinity(v, iv), iv))
        vote.sort(reverse=True)
        if len(vote) == 1 or vote[0][0] - vote[1][0] >= vote_margin:
            mapping[v] = vote[0][1]
    return [replace(r, vendor=mapping[r.vendor]) if r.source != "io" and r.vendor in mapping else r for r in records]


def match(records: list[LineItem]) -> tuple[list[Match], dict[str, str]]:
    """Returns one Match per IO line, plus record_id -> io_id for every matched record."""
    records = resolve_vendors(records)
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
