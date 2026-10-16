"""Outputs: exception list (CSV + XLSX), accruals file, one-page HTML summary."""
from __future__ import annotations

import html
from dataclasses import asdict
from pathlib import Path

import pandas as pd

from ..exceptions import earned
from ..schema import LineItem, Match, ReconException

LABELS = {"overbilling": "Overbilling", "rate_mismatch": "Rate mismatch", "underdelivery": "Underdelivery",
          "missing_invoice": "Missing invoice", "currency_mismatch": "Currency mismatch",
          "date_mismatch": "Date mismatch", "makegood": "Makegood", "unmatched_invoice": "Unmatched invoice",
          "unmatched_delivery": "Unmatched delivery"}
# Buckets for the headline numbers
RECOVERABLE = {"overbilling"}               # rate excess is already inside overbilling
UNVERIFIED = {"currency_mismatch", "date_mismatch", "unmatched_invoice"}


def accruals(records: list[LineItem], matches: list[Match]) -> pd.DataFrame:
    by_id = {r.record_id: r for r in records}
    rows = []
    for m in matches:
        io, inv, d = by_id[m.io_id], by_id.get(m.invoice_id), by_id.get(m.delivery_id)
        earn = earned(io, d) or 0.0
        invoiced = inv.amount if inv and inv.currency == io.currency else 0.0
        note = "" if not inv else ("invoice in " + inv.currency + " - excluded" if inv.currency != io.currency else "")
        rows.append({"io_line": m.io_id, "vendor": io.vendor, "placement": io.placement,
                     "contracted_cost": io.amount, "earned_to_date": earn, "invoiced_usd": invoiced,
                     "accrual_usd": round(max(earn - invoiced, 0), 2),
                     "dispute_usd": round(max(invoiced - earn, 0), 2), "note": note,
                     "match_confidence": m.confidence})
    return pd.DataFrame(rows)


def summarize(exc: list[ReconException], acc: pd.DataFrame) -> dict:
    s = lambda types: round(sum(e.amount_at_risk for e in exc if e.type in types), 2)
    return {"overbilled_usd": s(RECOVERABLE), "unverified_billing_usd": s(UNVERIFIED),
            "undelivered_value_usd": s({"underdelivery"}), "unbilled_accrual_usd": round(acc.accrual_usd.sum(), 2),
            "exceptions": len(exc), "io_lines": len(acc),
            "dollars_at_risk_usd": s(RECOVERABLE | UNVERIFIED | {"underdelivery"})}


def write_outputs(out: Path, records, matches, exc) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([asdict(e) for e in exc]) if exc else pd.DataFrame(columns=list(ReconException.__annotations__))
    df = df.sort_values("amount_at_risk", ascending=False)
    df.to_csv(out / "exceptions.csv", index=False)
    acc = accruals(records, matches)
    acc.to_csv(out / "accruals.csv", index=False)
    with pd.ExcelWriter(out / "exceptions.xlsx") as xw:
        df.to_excel(xw, sheet_name="Exceptions", index=False)
        acc.to_excel(xw, sheet_name="Accruals", index=False)
        pd.DataFrame([asdict(m) | {"citations": "; ".join(m.citations)} for m in matches]).to_excel(
            xw, sheet_name="Matches", index=False)
    summary = summarize(exc, acc)
    (out / "summary.html").write_text(render_html(summary, df))
    return summary


def render_html(s: dict, df: pd.DataFrame) -> str:
    money = lambda v: f"${v:,.0f}"
    by_type = df.groupby("type").agg(n=("type", "size"), usd=("amount_at_risk", "sum")) if len(df) else None
    type_rows = "".join(f"<tr><td>{LABELS.get(t, t)}</td><td>{r.n}</td><td>{money(r.usd)}</td></tr>"
                        for t, r in (by_type.sort_values("usd", ascending=False).iterrows() if by_type is not None else []))
    top = "".join(f"<tr><td>{LABELS.get(r.type, r.type)}</td><td>{html.escape(r.vendor)}</td>"
                  f"<td>{html.escape(r.placement)}</td><td>{money(r.amount_at_risk)}</td>"
                  f"<td>{html.escape(r.detail)}</td><td class=c>{html.escape(r.citation)}</td></tr>"
                  for r in df.head(10).itertuples())
    cards = [("Dollars at risk", s["dollars_at_risk_usd"]), ("Overbilled (recoverable)", s["overbilled_usd"]),
             ("Undelivered value", s["undelivered_value_usd"]), ("Unverified billing", s["unverified_billing_usd"]),
             ("Unbilled accrual", s["unbilled_accrual_usd"])]
    card_html = "".join(f"<div class=card><div class=v>{money(v)}</div><div>{k}</div></div>" for k, v in cards)
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Media Reconciliation Summary</title>
<style>body{{font-family:Helvetica,Arial,sans-serif;max-width:1000px;margin:24px auto;color:#222;font-size:13px}}
.cards{{display:flex;gap:10px}}.card{{flex:1;border:1px solid #ddd;border-radius:6px;padding:10px;text-align:center}}
.v{{font-size:22px;font-weight:bold;color:#b00020}}table{{border-collapse:collapse;width:100%;margin-top:10px}}
td,th{{border-bottom:1px solid #eee;padding:4px;text-align:left;vertical-align:top}}.c{{color:#777;font-size:11px}}
@media print{{body{{margin:0}}}}</style></head><body>
<h2>Media Reconciliation Summary</h2>
<p>{s['io_lines']} contracted line items reconciled against invoices and delivery reports;
{s['exceptions']} exceptions flagged. Synthetic data only.</p>
<div class=cards>{card_html}</div>
<h3>Exceptions by type</h3><table><tr><th>Type</th><th>Count</th><th>$ impact</th></tr>{type_rows}</table>
<h3>Top 10 exceptions</h3><table><tr><th>Type</th><th>Vendor</th><th>Placement</th><th>$</th><th>Detail</th>
<th>Source</th></tr>{top}</table>
<p class=c>Dollars at risk = overbilling + underdelivered value + billing that cannot be verified (currency/date
issues, invoices with no IO). Every row cites the IO cell, invoice page/line and delivery row it came from.</p>
</body></html>"""
