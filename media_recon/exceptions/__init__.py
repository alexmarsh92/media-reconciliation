"""Exception rules over matched IO / invoice / delivery triples."""
from __future__ import annotations

from ..match import is_fee, is_makegood
from ..schema import LineItem, Match, ReconException
from ..tunables import load as load_tunables


def per_k(rt: str) -> float:
    return 1000.0 if rt == "CPM" else 1.0


def delivered_units(io: LineItem, d: LineItem | None) -> float | None:
    if d is None:
        return None
    return d.impressions if io.rate_type == "CPM" else d.clicks


def earned(io: LineItem, d: LineItem | None) -> float | None:
    """Value earned by delivery, capped at contract."""
    du = delivered_units(io, d)
    return None if du is None else round(min(du, io.units) * io.rate / per_k(io.rate_type), 2)


def detect(records: list[LineItem], matches: list[Match], matched: dict[str, str]) -> list[ReconException]:
    cfg = load_tunables()
    under_pct = float(cfg.get("underdelivery_pct", 0.90))
    over_tol = float(cfg.get("overbill_tol", 0.02))
    rate_tol = float(cfg.get("rate_tol", 0.005))

    by_id = {r.record_id: r for r in records}
    out: list[ReconException] = []

    def add(t, key, rec, amt, detail, conf, cites):
        out.append(ReconException(t, key, rec.vendor, rec.placement, round(amt, 2), detail, conf,
                                  "; ".join(c for c in cites if c)))

    if cfg.get("enable_grouped", False):
        _detect_grouped(cfg, by_id, matches, add)
    for m in ([] if cfg.get("enable_grouped", False) else matches):
        io = by_id[m.io_id]
        inv, d = by_id.get(m.invoice_id), by_id.get(m.delivery_id)
        cites = m.citations
        earn = earned(io, d)
        du = delivered_units(io, d)
        if d and du is not None and du < under_pct * io.units:
            short = (io.units - du) * io.rate / per_k(io.rate_type)
            add("underdelivery", io.record_id, io, short,
                f"Delivered {du:,.0f} of {io.units:,.0f} contracted ({du / io.units:.0%})", m.confidence, cites)
        if inv is None:
            if d:
                add("missing_invoice", io.record_id, io, earn or 0,
                    f"Delivery of ${earn:,.2f} earned but no invoice line found", m.confidence, cites)
            continue
        if inv.currency != io.currency:
            add("currency_mismatch", io.record_id, io, inv.amount or 0,
                f"Invoiced in {inv.currency}, IO contracted in {io.currency}", m.confidence, cites)
            continue
        if inv.start and inv.end and io.start and io.end and (inv.start < io.start or inv.end > io.end):
            add("date_mismatch", io.record_id, io, inv.amount or 0,
                f"Service period {inv.start}..{inv.end} outside flight {io.start}..{io.end}", m.confidence, cites)
        if inv.rate is not None and io.rate is not None and abs(inv.rate - io.rate) > rate_tol * io.rate:
            excess = (inv.rate - io.rate) * (inv.units or 0) / per_k(io.rate_type)
            add("rate_mismatch", io.record_id, io, max(excess, 0),
                f"Invoice rate {inv.rate:.2f} vs IO rate {io.rate:.2f}", m.confidence, cites)
        if earn is not None and inv.amount is not None and inv.amount > earn * (1 + over_tol):
            add("overbilling", io.record_id, io, inv.amount - earn,
                f"Invoiced ${inv.amount:,.2f} vs earned ${earn:,.2f}", m.confidence, cites)

    for r in records:
        if r.source == "io" or r.record_id in matched:
            continue
        if is_fee(r) and not cfg.get("fee_lines_as_exceptions", False) and cfg.get("enable_grouped", False):
            continue  # non-media fee line (ad serving / tech / production): not an IO line
        if r.source == "delivery" and is_makegood(r):
            add("makegood", r.record_id, r, 0, f"Makegood delivery ({r.impressions or 0:,.0f} impr.) - confirm "
                "it is no-charge and offsets an underdelivered line", 0.9, [r.citation])
        else:
            add(f"unmatched_{r.source}", r.record_id, r, r.amount or 0,
                f"No IO line matched this {r.source} line", 0.5, [r.citation])
    return out


def _detect_grouped(cfg, by_id, matches, add) -> None:
    """Exception rules over grouped matches: invoice/delivery lines are aggregated per IO line, so
    split lines and month-by-month (cross-period) billing reconcile in aggregate within tolerance, and
    a merged invoice line is checked against the combined earned value of every IO line it covers."""
    from datetime import timedelta
    under_pct = float(cfg.get("underdelivery_pct", 0.90))
    rate_tol = float(cfg.get("rate_tol", 0.005))
    rel = float(cfg.get("alloc_rel_tol", cfg.get("overbill_tol", 0.02)))
    abs_tol = float(cfg.get("alloc_abs_tol", 1.0))
    dtol = timedelta(days=int(cfg.get("date_tol_days", 0)))

    def agg_earned(io, d_ids):
        ds = [by_id[x] for x in d_ids]
        if not ds:
            return None, None
        du = sum((d.impressions if io.rate_type == "CPM" else d.clicks) or 0 for d in ds)
        return du, round(min(du, io.units) * io.rate / per_k(io.rate_type), 2)

    earned_by_io = {m.io_id: agg_earned(by_id[m.io_id], m.delivery_ids)[1] for m in matches}
    for m in matches:
        io = by_id[m.io_id]
        invs = [by_id[x] for x in m.invoice_ids]
        du, earn = agg_earned(io, m.delivery_ids)
        cites = m.citations
        if du is not None and du < under_pct * io.units:
            short = (io.units - du) * io.rate / per_k(io.rate_type)
            add("underdelivery", io.record_id, io, short,
                f"Delivered {du:,.0f} of {io.units:,.0f} contracted ({du / io.units:.0%})"
                + (f" across {len(m.delivery_ids)} lines" if len(m.delivery_ids) > 1 else ""), m.confidence, cites)
        if not invs:
            if m.delivery_ids and not m.covered_by:
                add("missing_invoice", io.record_id, io, earn or 0,
                    f"Delivery of ${earn or 0:,.2f} earned but no invoice line found", m.confidence, cites)
            continue
        if any(i.currency != io.currency for i in invs):
            bad = next(i for i in invs if i.currency != io.currency)
            add("currency_mismatch", io.record_id, io, sum(i.amount or 0 for i in invs),
                f"Invoiced in {bad.currency}, IO contracted in {io.currency}", m.confidence, cites)
            continue
        starts = [i.start for i in invs if i.start]; ends = [i.end for i in invs if i.end]
        if starts and ends and io.start and io.end and (min(starts) < io.start - dtol or max(ends) > io.end + dtol):
            add("date_mismatch", io.record_id, io, sum(i.amount or 0 for i in invs),
                f"Service period {min(starts)}..{max(ends)} outside flight {io.start}..{io.end}", m.confidence, cites)
        bad_rate = [i for i in invs if i.rate is not None and io.rate is not None and abs(i.rate - io.rate) > rate_tol * io.rate]
        if bad_rate:
            excess = sum((i.rate - io.rate) * (i.units or 0) / per_k(io.rate_type) for i in bad_rate)
            add("rate_mismatch", io.record_id, io, max(excess, 0),
                f"Invoice rate {bad_rate[0].rate:.2f} vs IO rate {io.rate:.2f}", m.confidence, cites)
        if earn is None:
            continue
        # a merged invoice line billed on this IO also covers other IO lines: add their earned value
        extra = 0.0
        for x in m.invoice_ids:
            for om in matches:
                if x in om.covered_by:
                    extra += earned_by_io.get(om.io_id) or 0
        total, basis = sum(i.amount or 0 for i in invs), earn + extra
        if total > basis * (1 + rel) + abs_tol:
            n = len(invs)
            add("overbilling", io.record_id, io, total - basis,
                f"Invoiced ${total:,.2f}" + (f" over {n} lines" if n > 1 else "") + f" vs earned ${basis:,.2f}",
                m.confidence, cites)
