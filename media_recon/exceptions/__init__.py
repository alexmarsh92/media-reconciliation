"""Exception rules over matched IO / invoice / delivery triples."""
from __future__ import annotations

from ..match import is_makegood
from ..schema import LineItem, Match, ReconException

UNDERDELIVERY_PCT = 0.90    # delivered < 90% of contract
OVERBILL_TOL = 0.02         # invoiced > earned by more than 2%
RATE_TOL = 0.005            # 0.5% rate tolerance


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
    by_id = {r.record_id: r for r in records}
    out: list[ReconException] = []

    def add(t, key, rec, amt, detail, conf, cites):
        out.append(ReconException(t, key, rec.vendor, rec.placement, round(amt, 2), detail, conf,
                                  "; ".join(c for c in cites if c)))

    for m in matches:
        io = by_id[m.io_id]
        inv, d = by_id.get(m.invoice_id), by_id.get(m.delivery_id)
        cites = m.citations
        earn = earned(io, d)
        du = delivered_units(io, d)
        if d and du < UNDERDELIVERY_PCT * io.units:
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
            continue  # amounts not comparable without an agreed FX rate
        if inv.start and inv.end and (inv.start < io.start or inv.end > io.end):
            add("date_mismatch", io.record_id, io, inv.amount or 0,
                f"Service period {inv.start}..{inv.end} outside flight {io.start}..{io.end}", m.confidence, cites)
        if inv.rate is not None and abs(inv.rate - io.rate) > RATE_TOL * io.rate:
            excess = (inv.rate - io.rate) * (inv.units or 0) / per_k(io.rate_type)
            add("rate_mismatch", io.record_id, io, max(excess, 0),
                f"Invoice rate {inv.rate:.2f} vs IO rate {io.rate:.2f}", m.confidence, cites)
        if earn is not None and inv.amount > earn * (1 + OVERBILL_TOL):
            add("overbilling", io.record_id, io, inv.amount - earn,
                f"Invoiced ${inv.amount:,.2f} vs earned ${earn:,.2f}", m.confidence, cites)

    for r in records:
        if r.source == "io" or r.record_id in matched:
            continue
        if r.source == "delivery" and is_makegood(r):
            add("makegood", r.record_id, r, 0, f"Makegood delivery ({r.impressions:,.0f} impr.) - confirm "
                "it is no-charge and offsets an underdelivered line", 0.9, [r.citation])
        else:
            add(f"unmatched_{r.source}", r.record_id, r, r.amount or 0,
                f"No IO line matched this {r.source} line", 0.5, [r.citation])
    return out
