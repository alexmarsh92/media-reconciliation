"""Deterministic (offline, rule-based) extraction for the supported public-style formats."""
from __future__ import annotations

import csv
import re
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook
from pypdf import PdfReader

from ..schema import LineItem


def num(s) -> float | None:
    if s is None or s == "":
        return None
    if isinstance(s, (int, float)):
        return float(s)
    return float(re.sub(r"[^0-9.\-]", "", str(s)))


def parse_date(s) -> date | None:
    if s in (None, ""):
        return None
    if isinstance(s, datetime):
        return s.date()
    if isinstance(s, date):
        return s
    base = ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%d.%m.%Y")
    try:
        from ..tunables import load as _load_t
        extra = tuple(_load_t().get("extra_date_formats") or [])
    except Exception:
        extra = ()
    for fmt in base + extra:
        try:
            return datetime.strptime(str(s).strip(), fmt).date()
        except ValueError:
            pass
    return None


def pdf_lines(path: Path) -> list[tuple[int, int, str]]:
    """(page, line_no, text) for every non-empty line."""
    out = []
    for p, page in enumerate(PdfReader(str(path)).pages, start=1):
        for i, text in enumerate((page.extract_text() or "").splitlines(), start=1):
            if text.strip():
                out.append((p, i, text.strip()))
    return out


def extract_io(path: Path) -> list[LineItem]:
    ws = load_workbook(path, data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h).strip().lower() for h in rows[0]]
    col = lambda *names: next(i for i, h in enumerate(hdr) if h in names)
    c = {k: col(*v) for k, v in {
        "io": ("io number", "io #", "io"), "vendor": ("vendor", "publisher", "vendor name", "publisher name"),
        "campaign": ("campaign", "campaign name"),
        "placement": ("placement", "line item", "line item description", "placement name"),
        "start": ("flight start", "start date", "start", "flight start date"),
        "end": ("flight end", "end date", "end", "flight end date"),
        "rt": ("rate type", "buy type", "cost method"),
        "rate": ("rate", "unit price"),
        "units": ("contracted units", "units", "qty", "ordered units", "quantity"),
        "cost": ("contracted cost", "cost", "net cost", "ordered amount"),
        "cur": ("currency", "curr", "currency code")}.items()}
    out = []
    for i, r in enumerate(rows[1:], start=2):
        if not r[c["placement"]]:
            continue
        out.append(LineItem(f"{path.name}#R{i}", "io", str(r[c["vendor"]]), str(r[c["campaign"]]),
                            str(r[c["placement"]]), parse_date(r[c["start"]]), parse_date(r[c["end"]]),
                            str(r[c["cur"]] or "USD"), str(r[c["io"]]), str(r[c["rt"]]).upper(),
                            num(r[c["rate"]]), num(r[c["units"]]), num(r[c["cost"]]),
                            citation=f"{path.name} '{ws.title}'!R{i}"))
    return out


def extract_invoice(path: Path) -> list[LineItem]:
    lines = pdf_lines(path)
    head = {}
    header_map = {
        "vendor": ("vendor", "seller", "seller name", "supplier name", "from"),
        "io": ("io #", "io", "purchase order / io", "buyer reference", "purchase order", "ref"),
        "campaign": ("campaign", "job / campaign", "campaign name"),
        "invoice": ("invoice #", "invoice number", "invoice id"),
    }
    for _, _, t in lines:
        m = re.match(r"([A-Za-z0-9 /#]+):\s*(.+)", t)
        if not m:
            continue
        label, val = m.group(1).strip().lower(), m.group(2).strip()
        for key, aliases in header_map.items():
            if label in aliases or any(label.startswith(a) for a in aliases):
                head[key] = val
                break
        # Ref: INV / IO style
        if label == "ref" and "/" in val:
            parts = [x.strip() for x in val.split("/", 1)]
            head.setdefault("invoice", parts[0])
            head.setdefault("io", parts[1] if len(parts) > 1 else "")
    out = []
    skip_headers = {"placement", "description", "description of goods/services", "item"}
    for page, ln, t in lines:
        sep = "|" if "|" in t else (";" if ";" in t else None)
        if not sep:
            continue
        parts = [p.strip() for p in t.split(sep)]
        if len(parts) != 6:
            continue
        if parts[0].lower() in skip_headers or parts[0].lower().startswith("description"):
            continue
        period = parts[1].replace(" to ", "-").replace(" – ", "-")
        # split on last-ish hyphen between dates
        if "-" in period:
            left, right = period.split("-", 1)
            s, e = parse_date(left.strip()), parse_date(right.strip())
        else:
            s = e = parse_date(period)
        vendor = head.get("vendor", "")
        campaign = head.get("campaign", "")
        io_no = head.get("io", "")
        # strip trailing IO from Ref composites already handled
        out.append(LineItem(f"{path.name}#L{ln}", "invoice", vendor, campaign,
                            parts[0], s, e, parts[5], io_no, "", num(parts[3]),
                            num(parts[2]), num(parts[4]), citation=f"{path.name} p{page} L{ln}"))
    return out


# header aliases across Meta / Google Ads / DSP exports
ALIASES = {
    "campaign": ["campaign name", "campaign", "campagn"],
    "placement": ["ad set name", "ad set", "ad group", "placement", "placement name",
                  "line item", "line", "plcement"],
    "start": ["reporting starts", "date start", "start date", "start", "flight start", "from"],
    "end": ["reporting ends", "date end", "end date", "end", "flight end", "to"],
    "impressions": ["impressions", "impr.", "impr"],
    "clicks": ["link clicks", "clicks", "clcks"],
    "spend": ["amount spent (usd)", "cost", "advertiser cost (usd)", "spend (usd)", "spend",
              "media cost", "cost usd", "spend usd"],
}


def extract_delivery(path: Path, vendor: str) -> list[LineItem]:
    if path.suffix.lower() == ".pdf":
        lines = pdf_lines(path)
        hdr_line = next((t for _, _, t in lines
                         if (("|" in t or ";" in t)
                             and any(k in t.lower() for k in ("campaign", "campagn", "placement", "impr")))),
                        None)
        if hdr_line is None:
            return []
        sep = "|" if hdr_line.count("|") >= hdr_line.count(";") else ";"
        table = [(f"L{ln}", f"p{p} L{ln}", [x.strip() for x in t.split(sep)])
                 for p, ln, t in lines if sep in t and t != hdr_line]
        header = [h.strip().lower() for h in hdr_line.split(sep)]
        preamble = [t for _, _, t in lines]
    else:
        # sniff delimiter
        sample = path.read_text(errors="ignore").splitlines()[:5]
        delim = "	" if any("	" in s for s in sample) else ","
        with path.open(newline="") as f:
            raw = list(csv.reader(f, delimiter=delim))
        hi = next(i for i, r in enumerate(raw) if len(r) > 3)  # skip report title lines
        header = [h.strip().lower() for h in raw[hi]]
        table = [(f"R{i + 1}", f"R{i + 1}", r) for i, r in enumerate(raw[hi + 1:], start=hi + 1) if r]
        preamble = [" ".join(r) for r in raw[:hi]]
    idx = {k: next((header.index(a) for a in al if a in header), None) for k, al in ALIASES.items()}
    # report-level period (Google Ads style) if rows carry no dates
    period = None
    for t in preamble:
        m = re.search(r"([A-Za-z]+ \d+, \d{4}|\d{2}/\d{2}/\d{4})\s*-\s*([A-Za-z]+ \d+, \d{4}|\d{2}/\d{2}/\d{4})", t)
        if m:
            period = (parse_date(m.group(1)), parse_date(m.group(2)))
    def get(r, k):
        i = idx[k]
        if i is None or i >= len(r):
            return None
        return r[i]
    out = []
    need = [idx[k] for k in ("campaign", "placement", "impressions") if idx[k] is not None]
    min_len = (max(need) + 1) if need else 1
    for loc, cite, r in table:
        if len(r) < min_len:
            continue
        start = parse_date(get(r, "start")) or (period[0] if period else None)
        end = parse_date(get(r, "end")) or (period[1] if period else None)
        try:
            imps = num(get(r, "impressions"))
            clicks = num(get(r, "clicks"))
            spend = num(get(r, "spend"))
        except (ValueError, TypeError):
            continue
        out.append(LineItem(f"{path.name}#{loc}", "delivery", vendor, get(r, "campaign"), get(r, "placement"),
                            start, end, "USD", impressions=imps, clicks=clicks, amount=spend,
                            citation=f"{path.name} {cite}"))
    return out
