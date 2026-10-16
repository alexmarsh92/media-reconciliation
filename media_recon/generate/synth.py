"""Synthetic data: IO media plans (XLSX), invoices (PDF), delivery reports (CSV/PDF).

Known errors are planted and written to gold.json along with the true value of
every rendered record and the true record->IO-line matches.
"""
from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..schema import LineItem

# vendor, delivery format, campaign, rate type, placements
VENDORS = [
    ("Meta Platforms", "meta_csv", "Spring Launch 2027 Teaser", "CPM",
     ["Feed Prospecting Mobile", "Stories Retargeting", "Reels Prospecting Video",
      "Audience Network Display", "Feed Lookalike Desktop"]),
    ("Google Ads", "google_csv", "Always On Search", "CPC",
     ["Brand Search Exact", "Nonbrand Search Broad", "Competitor Conquest",
      "Shopping Smart Campaign", "Performance Max Prospecting"]),
    ("The Trade Desk", "dsp_csv", "Q3 Brand Awareness", "CPM",
     ["Open Market Display Desktop", "CTV Premium Video", "Audio Streaming",
      "Native Contextual Mobile", "Private Marketplace Video"]),
    ("Amazon Advertising", "dsp_csv", "Q3 Brand Awareness", "CPM",
     ["Sponsored Display Retargeting", "Fire TV Video", "Twitch Prerolls Video",
      "Amazon Publisher Services Display"]),
    ("Hulu Ad Manager", "pub_pdf", "Q3 Brand Awareness", "CPM",
     ["Pause Ad Premium", "Binge Ad Prime Time", "Standard Midroll Video",
      "Gateway Go Interactive"]),
    ("Spotify Advertising", "pub_pdf", "Spring Launch 2027 Teaser", "CPM",
     ["Audio Everywhere", "Podcast Host Read", "Video Takeover Mobile",
      "Sponsored Session Video", "Homepage Leaderboard Desktop"]),
]
ABBREV = {"Mobile": "MOB", "Desktop": "DT", "Prospecting": "PROSP", "Retargeting": "RTG",
          "Video": "VID", "Display": "DISP", "Premium": "PREM", "Search": "SRCH"}
FLIGHT = (date(2026, 9, 1), date(2026, 9, 30))
PLANT = {"overbilling": 3, "underdelivery": 3, "rate_mismatch": 3,
         "missing_invoice": 3, "currency_mismatch": 2, "date_mismatch": 2}
N_MAKEGOODS = 3


def slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


NOISE = {"rng": random.Random(0), "level": 0.0}


def _noisy(words: list[str]) -> list[str]:
    """Optional real-world messiness: drop a word and/or typo a word."""
    rng, lvl = NOISE["rng"], NOISE["level"]
    words = list(words)
    if lvl and len(words) > 2 and rng.random() < lvl:
        words.pop(rng.randrange(len(words)))
    if lvl and rng.random() < lvl:
        i = rng.randrange(len(words))
        w = words[i]
        if len(w) > 3:
            j = rng.randrange(1, len(w) - 1)
            words[i] = w[:j] + w[j + 1:]
    return words


def invoice_name(p: str) -> str:
    return " - ".join(_noisy([ABBREV.get(w, w) for w in p.split()])).upper()


_DNAMES: dict = {}


def delivery_name(p: str, campaign: str) -> str:
    key = (p, campaign)  # stable per placement within one generation run
    if key not in _DNAMES:
        _DNAMES[key] = f"{slug(campaign)[:12]}_{'_'.join(_noisy(p.lower().split()))}"
    return _DNAMES[key]


def cost(units: float, rate: float, rate_type: str) -> float:
    return round(units * rate / (1000 if rate_type == "CPM" else 1), 2)


def generate(out: Path, seed: int = 7, noise: float = 0.0) -> dict:
    """noise in [0,1]: probability of dropped words / typos in invoice and delivery names."""
    rng = random.Random(seed)
    NOISE.update(rng=random.Random(seed + 1000), level=noise)
    _DNAMES.clear()
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("io", "invoices", "delivery"):
        (out / sub).mkdir(exist_ok=True)
        for f in (out / sub).iterdir():
            f.unlink()

    # 1. Contracted IO lines.
    lines = []
    for vi, (vendor, fmt, campaign, rtype, placements) in enumerate(VENDORS):
        io_no = f"IO-2026-{101 + vi}"
        for p in placements:
            start = FLIGHT[0] + timedelta(days=rng.choice([0, 0, 0, 7]))
            end = FLIGHT[1] - timedelta(days=rng.choice([0, 0, 0, 5]))
            if rtype == "CPM":
                units, rate = rng.randrange(400, 6000) * 1000, round(rng.uniform(5, 32), 2)
            else:
                units, rate = rng.randrange(2000, 20000), round(rng.uniform(0.8, 3.6), 2)
            lines.append(dict(vendor=vendor, fmt=fmt, campaign=campaign, rate_type=rtype,
                              placement=p, io_number=io_no, start=start, end=end,
                              units=units, rate=rate, amount=cost(units, rate, rtype)))

    # 2. Plant one error per selected line.
    errors, picks = [], rng.sample(range(len(lines)), sum(PLANT.values()))
    for etype, n in PLANT.items():
        for _ in range(n):
            lines[picks.pop()]["error"] = etype

    records, matches = [], {}

    # 3. IO media plans (one XLSX per vendor).
    by_vendor: dict[str, list] = {}
    for ln in lines:
        by_vendor.setdefault(ln["vendor"], []).append(ln)
    for vendor, vlines in by_vendor.items():
        fname = f"io_{slug(vendor)}.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Media Plan"
        ws.append(["IO Number", "Vendor", "Advertiser", "Campaign", "Placement", "Flight Start",
                   "Flight End", "Rate Type", "Rate", "Contracted Units", "Contracted Cost", "Currency"])
        for i, ln in enumerate(vlines, start=2):
            ws.append([ln["io_number"], vendor, "Northwind Outdoor Co. (synthetic)", ln["campaign"],
                       ln["placement"], ln["start"], ln["end"], ln["rate_type"], ln["rate"],
                       ln["units"], ln["amount"], "USD"])
            rid = f"{fname}#R{i}"
            ln["io_id"] = rid
            records.append(LineItem(rid, "io", vendor, ln["campaign"], ln["placement"], ln["start"],
                                    ln["end"], "USD", ln["io_number"], ln["rate_type"], ln["rate"],
                                    ln["units"], ln["amount"], citation=f"{fname} 'Media Plan'!R{i}"))
        wb.save(out / "io" / fname)

    # 4. Delivery (true performance) per line.
    for ln in lines:
        e = ln.get("error")
        factor = rng.uniform(0.70, 0.80) if e == "underdelivery" else rng.uniform(0.98, 1.04)
        ctr = rng.uniform(0.004, 0.02) if ln["rate_type"] == "CPM" else rng.uniform(0.02, 0.08)
        if ln["rate_type"] == "CPM":
            imps = round(ln["units"] * factor)
            clicks = round(imps * ctr)
            billable = min(imps, ln["units"])
        else:
            clicks = round(ln["units"] * factor)
            imps = round(clicks / ctr)
            billable = min(clicks, ln["units"])
        ln.update(impressions=imps, clicks=clicks, billable=billable,
                  spend=cost(billable, ln["rate"], ln["rate_type"]))
        if e:
            errors.append({"type": e, "key": ln["io_id"]})
            if e == "rate_mismatch":   # a higher rate also means overbilling
                errors.append({"type": "overbilling", "key": ln["io_id"]})

    # makegoods: extra delivery rows with no IO line
    makegoods = []
    for ln in rng.sample([l for l in lines if not l.get("error")], N_MAKEGOODS):
        mg = dict(ln, placement=f"MG {ln['placement']} Makegood", error="makegood",
                  impressions=round(ln["impressions"] * 0.08), clicks=round(ln["clicks"] * 0.08),
                  spend=0.0, io_id=None)
        makegoods.append(mg)

    # 5. Delivery reports.
    for vendor, vlines in by_vendor.items():
        rows = vlines + [m for m in makegoods if m["vendor"] == vendor]
        fmt = vlines[0]["fmt"]
        ext = "pdf" if fmt == "pub_pdf" else "csv"
        fname = f"delivery_{slug(vendor)}.{ext}"
        path = out / "delivery" / fname
        locs = _write_delivery(path, fmt, vendor, rows)
        for ln, loc in zip(rows, locs):
            rid = f"{fname}#{loc}"
            records.append(LineItem(rid, "delivery", vendor, ln["campaign"],
                                    delivery_name(ln["placement"], ln["campaign"]),
                                    FLIGHT[0] if fmt == "google_csv" else ln["start"],
                                    FLIGHT[1] if fmt == "google_csv" else ln["end"],
                                    impressions=ln["impressions"], clicks=ln["clicks"],
                                    amount=ln["spend"], citation=f"{fname} {loc}"))
            matches[rid] = ln["io_id"]
            if ln.get("error") == "makegood":
                errors.append({"type": "makegood", "key": rid})

    # 6. Invoices (one PDF per vendor).
    for vi, (vendor, vlines) in enumerate(by_vendor.items()):
        fname = f"invoice_{slug(vendor)}.pdf"
        inv_rows = []
        for ln in vlines:
            e = ln.get("error")
            if e == "missing_invoice":
                continue
            units, rate, cur, end = ln["billable"], ln["rate"], "USD", ln["end"]
            if e == "overbilling":
                units = round(units * rng.uniform(1.10, 1.20))
            if e == "rate_mismatch":
                rate = round(rate * 1.15, 2)
            if e == "currency_mismatch":
                rate, cur = round(rate * 0.92, 2), "EUR"
            if e == "date_mismatch":
                end = end + timedelta(days=12)
            inv_rows.append(dict(ln=ln, placement=invoice_name(ln["placement"]), start=ln["start"],
                                 end=end, units=units, rate=rate, currency=cur,
                                 amount=cost(units, rate, ln["rate_type"])))
        meta = dict(vendor=vendor, invoice_no=f"INV-{seed:02d}{vi + 1:03d}", io_number=vlines[0]["io_number"],
                    campaign=vlines[0]["campaign"])
        locs = _write_invoice(out / "invoices" / fname, meta, inv_rows)
        for r, loc in zip(inv_rows, locs):
            rid = f"{fname}#{loc}"
            records.append(LineItem(rid, "invoice", vendor, meta["campaign"], r["placement"], r["start"],
                                    r["end"], r["currency"], meta["io_number"], "", r["rate"], r["units"],
                                    r["amount"], citation=f"{fname} p1 {loc}"))
            matches[rid] = r["ln"]["io_id"]

    gold = {"seed": seed, "noise": noise, "records": [r.to_dict() for r in records], "matches": matches, "errors": errors}
    (out / "gold.json").write_text(json.dumps(gold, indent=1))
    return gold


def _write_delivery(path: Path, fmt: str, vendor: str, rows: list) -> list[str]:
    """Write a platform-style report. Returns a locator per row (CSV row / PDF line no.)."""
    if fmt == "pub_pdf":
        lines = [f"Delivery Report - {vendor}", f"Reporting period: {FLIGHT[0]:%m/%d/%Y} - {FLIGHT[1]:%m/%d/%Y}",
                 "Campaign | Placement | Start | End | Impressions | Clicks | Spend (USD)"]
        locs = []
        for r in rows:
            lines.append(f"{r['campaign']} | {delivery_name(r['placement'], r['campaign'])} | {r['start']:%m/%d/%Y} | "
                         f"{r['end']:%m/%d/%Y} | {r['impressions']:,} | {r['clicks']:,} | ${r['spend']:,.2f}")
            locs.append(f"L{len(lines)}")
        _pdf(path, lines)
        return locs
    with path.open("w", newline="") as f:
        w = csv.writer(f)
        if fmt == "meta_csv":   # Ads Manager export style
            w.writerow(["Campaign name", "Ad set name", "Reporting starts", "Reporting ends",
                        "Impressions", "Link clicks", "Amount spent (USD)"])
            for r in rows:
                w.writerow([r["campaign"], delivery_name(r["placement"], r["campaign"]), r["start"].isoformat(),
                            r["end"].isoformat(), r["impressions"], r["clicks"], f"{r['spend']:.2f}"])
            return [f"R{i}" for i in range(2, len(rows) + 2)]
        if fmt == "google_csv":  # Google Ads report style: title + date-range lines, then table
            w.writerow(["Ad group report"])
            w.writerow([f"{FLIGHT[0]:%B %-d, %Y} - {FLIGHT[1]:%B %-d, %Y}"])
            w.writerow(["Campaign", "Ad group", "Currency code", "Impr.", "Clicks", "Cost"])
            for r in rows:
                w.writerow([r["campaign"], delivery_name(r["placement"], r["campaign"]), "USD",
                            f"{r['impressions']:,}", f"{r['clicks']:,}", f"{r['spend']:,.2f}"])
            return [f"R{i}" for i in range(4, len(rows) + 4)]
        # dsp_csv: The Trade Desk / Amazon DSP style
        w.writerow(["Advertiser", "Campaign", "Ad Group", "Date Start", "Date End",
                    "Impressions", "Clicks", "Advertiser Cost (USD)"])
        for r in rows:
            w.writerow(["Northwind Outdoor Co.", r["campaign"], delivery_name(r["placement"], r["campaign"]),
                        f"{r['start']:%m/%d/%Y}", f"{r['end']:%m/%d/%Y}", r["impressions"], r["clicks"],
                        f"{r['spend']:.2f}"])
        return [f"R{i}" for i in range(2, len(rows) + 2)]


def _write_invoice(path: Path, meta: dict, rows: list) -> list[str]:
    lines = ["INVOICE", f"Vendor: {meta['vendor']}", f"Invoice #: {meta['invoice_no']}",
             f"IO #: {meta['io_number']}", f"Campaign: {meta['campaign']}", "Invoice Date: 10/05/2026",
             "Bill To: Northwind Outdoor Co. (synthetic)",
             "Placement | Service Period | Units | Rate | Amount | Currency"]
    locs = []
    for r in rows:
        lines.append(f"{r['placement']} | {r['start']:%m/%d/%Y}-{r['end']:%m/%d/%Y} | {r['units']:,} | "
                     f"{r['rate']:.2f} | {r['amount']:,.2f} | {r['currency']}")
        locs.append(f"L{len(lines)}")
    lines.append(f"Total Due: {sum(r['amount'] for r in rows):,.2f}")
    _pdf(path, lines)
    return locs


def _pdf(path: Path, lines: list[str]) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 750
    for i, text in enumerate(lines):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 14 if i == 0 else 7.5)
        c.drawString(40, y, text)
        y -= 20 if i == 0 else 13
    c.save()
