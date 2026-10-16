"""Held-out adversarial synthetic data — DIFFERENT seed AND logic from generate/synth.py.

Never used by autoresearch to select winners. Checkpoint scoring only.
Covers: vendor aliases/typos, abbreviations, split/merged invoice lines,
multiple invoices per vendor, cross-period flights, partial makegoods,
currency + date-format variance, rounding, OCR noise, unseen layouts,
and decoys designed to provoke false flags.

Also ships a few public-style layout fixtures (generic commercial invoice /
IO column naming drawn from commonly published open examples — not scraped
from private systems).
"""
from __future__ import annotations

import csv
import json
import random
import re
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from ..schema import LineItem

# Intentionally different vendor set + alias surface from synth.VENDORS
VENDORS = [
    # canonical_io_name, alias_variants (invoice/delivery), fmt, campaign, rate_type, placements
    ("Meta Platforms", ["Facebook Ads", "Meta Platforms, Inc.", "FB Ads", "Meta"],
     "meta_messy", "Autumn Push 2026", "CPM",
     ["Feed Prospecting Mobile", "Stories Retargeting", "Reels Prospecting Video",
      "Audience Network Display"]),
    ("Google Ads", ["Google Ads LLC", "AdWords", "Google"],
     "google_eu", "Brand Defense Always-On", "CPC",
     ["Brand Search Exact", "Nonbrand Search Broad", "Shopping Smart Campaign",
      "YouTube Bumper 6s"]),
    ("The Trade Desk", ["TTD", "TheTradeDesk", "Trade Desk"],
     "dsp_pipe", "Holiday Awareness Burst", "CPM",
     ["Open Market Display Desktop", "CTV Premium Video", "Native Contextual Mobile",
      "Private Marketplace Video"]),
    ("Amazon Advertising", ["Amazon DSP", "Amazon Ads", "AMS"],
     "dsp_tab", "Holiday Awareness Burst", "CPM",
     ["Sponsored Display Retargeting", "Fire TV Video", "Twitch Prerolls Video"]),
    ("Hulu Ad Manager", ["Hulu", "Disney Hulu Ads"],
     "pub_alt", "Autumn Push 2026", "CPM",
     ["Pause Ad Premium", "Binge Ad Prime Time", "Standard Midroll Video"]),
    ("Spotify Advertising", ["Spotify Ads", "Spotify"],
     "pub_ocr", "Brand Defense Always-On", "CPM",
     ["Audio Everywhere", "Podcast Host Read", "Video Takeover Mobile"]),
]

ABBREV = {
    "Mobile": "Mob.", "Desktop": "Dsktp", "Prospecting": "Prosp.", "Retargeting": "Re-Tgt",
    "Video": "Vid", "Display": "Disp.", "Premium": "Prem.", "Search": "Srch",
    "Contextual": "Ctx", "Network": "Ntwk", "Audience": "Aud.",
}

OCR_MAP = str.maketrans({"0": "O", "1": "l", "5": "S", "8": "B", "e": "c", "a": "@"})


def slug(name: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in name.lower()).strip("_")


def cost(units: float, rate: float, rate_type: str) -> float:
    return round(units * rate / (1000 if rate_type == "CPM" else 1), 2)


def ocr_noise(s: str, rng: random.Random, p: float = 0.35) -> str:
    if rng.random() > p or len(s) < 4:
        return s
    chars = list(s)
    i = rng.randrange(1, len(chars) - 1)
    chars[i] = chars[i].translate(OCR_MAP)
    if rng.random() < 0.4:
        j = rng.randrange(1, len(chars))
        chars.insert(j, " ")
    return "".join(chars)


def abbrev_name(p: str, rng: random.Random, avoid_pipe: bool = False) -> str:
    words = [ABBREV.get(w, w) for w in p.split()]
    if rng.random() < 0.5 and len(words) > 2:
        words.pop(rng.randrange(len(words)))
    choices = [" - ", "_", " / ", " · "]
    if not avoid_pipe:
        choices.append(" | ")
    sep = rng.choice(choices)
    return sep.join(words).upper()


def typo_vendor(name: str, rng: random.Random) -> str:
    if len(name) < 5 or rng.random() < 0.4:
        return name
    chars = list(name)
    i = rng.randrange(1, len(chars) - 1)
    if rng.random() < 0.5:
        chars[i] = ""  # drop
    else:
        chars[i], chars[i - 1] = chars[i - 1], chars[i]
    return "".join(chars)


def fmt_date(d: date, style: str) -> str:
    if style == "iso":
        return d.isoformat()
    if style == "us":
        return f"{d:%m/%d/%Y}"
    if style == "eu":
        return f"{d:%d-%m-%Y}"
    if style == "dot":
        return f"{d:%Y.%m.%d}"
    if style == "slash_y":
        return f"{d:%Y/%m/%d}"
    if style == "mon":
        return f"{d:%b %d %Y}"
    return f"{d:%d/%m/%Y}"


def generate(out: Path, seed: int = 909091) -> dict:
    """Build adversarial batch. Seed default is far from synth seeds 1-7."""
    rng = random.Random(seed)
    out.mkdir(parents=True, exist_ok=True)
    for sub in ("io", "invoices", "delivery", "fixtures"):
        (out / sub).mkdir(exist_ok=True)
        for f in (out / sub).iterdir():
            if f.is_file():
                f.unlink()

    period_a = (date(2026, 9, 15), date(2026, 10, 14))  # cross-month on purpose
    period_b = (date(2026, 10, 1), date(2026, 10, 31))

    lines = []
    for vi, (canon, aliases, fmt, campaign, rtype, placements) in enumerate(VENDORS):
        io_no = f"IO/2026/{200 + vi}"  # different numbering style
        flight = period_a if vi % 2 == 0 else period_b
        for p in placements:
            start = flight[0] + timedelta(days=rng.choice([0, 0, 3, 7]))
            end = flight[1] - timedelta(days=rng.choice([0, 0, 2, 5]))
            if rtype == "CPM":
                units, rate = rng.randrange(300, 5000) * 1000, round(rng.uniform(4.5, 28), 2)
            else:
                units, rate = rng.randrange(1500, 18000), round(rng.uniform(0.7, 3.2), 2)
            lines.append(dict(
                vendor=canon, aliases=aliases, fmt=fmt, campaign=campaign, rate_type=rtype,
                placement=p, io_number=io_no, start=start, end=end,
                units=units, rate=rate, amount=cost(units, rate, rtype),
                flight=flight, error=None, tags=[],
            ))

    # Plant adversarial error tags (different mix than synth.PLANT)
    n = len(lines)
    plant_plan = [
        ("overbilling", 4), ("underdelivery", 4), ("rate_mismatch", 3),
        ("missing_invoice", 3), ("currency_mismatch", 2), ("date_mismatch", 2),
        ("split_invoice", 3), ("merged_invoice", 2), ("partial_makegood", 3),
        ("rounding_decoy", 3), ("ocr_name", 4),
    ]
    pool = list(range(n))
    rng.shuffle(pool)
    for etype, count in plant_plan:
        for _ in range(count):
            if not pool:
                break
            idx = pool.pop()
            if lines[idx]["error"] is None:
                lines[idx]["error"] = etype
            else:
                lines[idx]["tags"].append(etype)

    # Decoy lines: tiny legitimate variance that should NOT flag
    decoy_idxs = pool[:4]
    for idx in decoy_idxs:
        lines[idx]["tags"].append("decoy_ok")

    errors, records, matches = [], [], {}
    by_vendor: dict[str, list] = {}
    for ln in lines:
        by_vendor.setdefault(ln["vendor"], []).append(ln)

    # --- IO plans with alternate column headers (unseen layouts) ---
    for vendor, vlines in by_vendor.items():
        fname = f"media_plan_{slug(vendor)}.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "Insertion Order"
        # Unseen header names vs synth ("Line Item Description", "Buy Type", ...)
        ws.append(["IO #", "Publisher", "Advertiser", "Campaign Name", "Line Item Description",
                   "Start", "End", "Buy Type", "Unit Price", "Qty", "Net Cost", "Curr"])
        for i, ln in enumerate(vlines, start=2):
            ws.append([ln["io_number"], vendor, "Acme Outdoor (public demo)", ln["campaign"],
                       ln["placement"], ln["start"], ln["end"], ln["rate_type"], ln["rate"],
                       ln["units"], ln["amount"], "USD"])
            rid = f"{fname}#R{i}"
            ln["io_id"] = rid
            records.append(LineItem(rid, "io", vendor, ln["campaign"], ln["placement"], ln["start"],
                                    ln["end"], "USD", ln["io_number"], ln["rate_type"], ln["rate"],
                                    ln["units"], ln["amount"], citation=f"{fname} 'Insertion Order'!R{i}"))
        wb.save(out / "io" / fname)

    # Need extract_io to understand these headers — patch aliases via a companion
    # adversarial extract helper registered in extract_dir when folder has marker.
    (out / "ADVERSARIAL").write_text(
        "held-out adversarial set; do not use for selection\n"
        f"seed={seed}\n"
    )

    # Delivery truth
    for ln in lines:
        e = ln["error"]
        factor = rng.uniform(0.68, 0.82) if e == "underdelivery" else rng.uniform(0.97, 1.03)
        if "decoy_ok" in ln["tags"]:
            factor = rng.uniform(0.995, 1.005)  # tiny variance
        ctr = rng.uniform(0.004, 0.02) if ln["rate_type"] == "CPM" else rng.uniform(0.02, 0.08)
        if ln["rate_type"] == "CPM":
            imps = round(ln["units"] * factor)
            clicks = round(imps * ctr)
            billable = min(imps, ln["units"])
        else:
            clicks = round(ln["units"] * factor)
            imps = round(clicks / ctr)
            billable = min(clicks, ln["units"])
        spend = cost(billable, ln["rate"], ln["rate_type"])
        if "decoy_ok" in ln["tags"]:
            spend = round(spend + rng.choice([-0.02, -0.01, 0.01, 0.02]), 2)  # rounding decoy
        ln.update(impressions=imps, clicks=clicks, billable=billable, spend=spend)
        if e and e not in ("split_invoice", "merged_invoice", "ocr_name", "rounding_decoy",
                           "partial_makegood"):
            errors.append({"type": e if e != "rounding_decoy" else "overbilling", "key": ln["io_id"]})
            if e == "rate_mismatch":
                errors.append({"type": "overbilling", "key": ln["io_id"]})
        if e == "underdelivery":
            pass  # already added
        if e in ("overbilling", "underdelivery", "rate_mismatch", "missing_invoice",
                 "currency_mismatch", "date_mismatch"):
            pass

    # Fix error planting for types we skipped above
    errors = []
    for ln in lines:
        e = ln["error"]
        if e in ("overbilling", "underdelivery", "rate_mismatch", "missing_invoice",
                 "currency_mismatch", "date_mismatch"):
            errors.append({"type": e, "key": ln["io_id"]})
            if e == "rate_mismatch":
                errors.append({"type": "overbilling", "key": ln["io_id"]})
        # rounding_decoy and decoy_ok intentionally plant NO gold error

    # Partial makegoods
    makegoods = []
    for ln in [l for l in lines if l["error"] == "partial_makegood"]:
        mg = dict(ln, placement=f"AV Bonus {ln['placement']}", error="makegood",
                  impressions=round(ln["impressions"] * 0.05), clicks=round(ln["clicks"] * 0.05),
                  spend=0.0, io_id=None)
        makegoods.append(mg)
        # still underdelivered on parent — ensure underdelivery gold if not already
        if not any(e["key"] == ln["io_id"] and e["type"] == "underdelivery" for e in errors):
            # force shortfall on parent delivery
            ln["impressions"] = round(ln["units"] * 0.75)
            ln["billable"] = min(ln["impressions"], ln["units"])
            ln["spend"] = cost(ln["billable"], ln["rate"], ln["rate_type"])
            errors.append({"type": "underdelivery", "key": ln["io_id"]})
        errors.append({"type": "makegood", "key": "PENDING_MG"})  # filled after delivery write

    # Delivery reports (unseen layouts)
    mg_error_slots = [e for e in errors if e["type"] == "makegood" and e["key"] == "PENDING_MG"]
    mg_i = 0
    for vendor, vlines in by_vendor.items():
        rows = vlines + [m for m in makegoods if m["vendor"] == vendor]
        fmt = vlines[0]["fmt"]
        ext = "pdf" if fmt.startswith("pub") else "csv"
        fname = f"delivery_{slug(vendor)}.{ext}"
        path = out / "delivery" / fname
        date_style = rng.choice(["iso", "us", "eu", "dot", "slash_y", "mon"])
        locs = _write_delivery(path, fmt, vendor, rows, rng, date_style)
        for ln, loc in zip(rows, locs):
            place = abbrev_name(ln["placement"], rng)
            if ln.get("error") == "ocr_name" or "ocr_name" in ln.get("tags", []):
                place = ocr_noise(place, rng, 0.9)
            # vendor alias on delivery
            vname = rng.choice(ln.get("aliases", [vendor]) + [vendor])
            if rng.random() < 0.25:
                vname = typo_vendor(vname, rng)
            rid = f"{fname}#{loc}"
            start = ln["flight"][0] if fmt == "google_eu" else ln["start"]
            end = ln["flight"][1] if fmt == "google_eu" else ln["end"]
            records.append(LineItem(rid, "delivery", vname, ln["campaign"], place,
                                    start, end, impressions=ln["impressions"], clicks=ln["clicks"],
                                    amount=ln["spend"], citation=f"{fname} {loc}"))
            matches[rid] = ln.get("io_id")
            if ln.get("error") == "makegood":
                if mg_i < len(mg_error_slots):
                    mg_error_slots[mg_i]["key"] = rid
                    mg_i += 1
                else:
                    errors.append({"type": "makegood", "key": rid})

    # Invoices: multiple per vendor, split/merge, currencies, date formats, OCR
    for vi, (vendor, vlines) in enumerate(by_vendor.items()):
        # split into two invoices for vendors with enough lines
        mid = max(1, len(vlines) // 2)
        chunks = [vlines[:mid], vlines[mid:]] if len(vlines) >= 4 else [vlines]
        for ci, chunk in enumerate(chunks):
            fname = f"invoice_{slug(vendor)}_{ci + 1}.pdf"
            inv_rows = []
            # merged_invoice: combine two lines into one invoice row
            skip = set()
            merge_pairs = [l for l in chunk if l["error"] == "merged_invoice"]
            for ln in chunk:
                if ln["io_id"] in skip:
                    continue
                e = ln["error"]
                if e == "missing_invoice":
                    continue
                if e == "merged_invoice" and len(merge_pairs) >= 1:
                    # merge this with next non-error sibling if possible
                    partner = next((x for x in chunk if x is not ln and x["error"] != "missing_invoice"
                                    and x["io_id"] not in skip), None)
                    if partner:
                        skip.add(partner["io_id"])
                        units = ln["billable"] + partner["billable"]
                        rate = ln["rate"]
                        amount = cost(ln["billable"], ln["rate"], ln["rate_type"]) + \
                                 cost(partner["billable"], partner["rate"], partner["rate_type"])
                        place = abbrev_name(ln["placement"], rng) + " + " + abbrev_name(partner["placement"], rng)
                        inv_rows.append(dict(lns=[ln, partner], placement=place, start=min(ln["start"], partner["start"]),
                                             end=max(ln["end"], partner["end"]), units=units, rate=rate,
                                             currency="USD", amount=round(amount, 2), split=False))
                        continue
                if e == "split_invoice":
                    # two invoice lines for one IO
                    for half, frac in enumerate((0.55, 0.45)):
                        units = round(ln["billable"] * frac)
                        rate = ln["rate"]
                        cur, end = "USD", ln["end"]
                        amount = cost(units, rate, ln["rate_type"])
                        place = abbrev_name(ln["placement"], rng) + f" (part {half + 1})"
                        inv_rows.append(dict(lns=[ln], placement=place, start=ln["start"], end=end,
                                             units=units, rate=rate, currency=cur, amount=amount, split=True))
                    continue
                units, rate, cur, end = ln["billable"], ln["rate"], "USD", ln["end"]
                if e == "overbilling":
                    units = round(units * rng.uniform(1.12, 1.22))
                if e == "rate_mismatch":
                    rate = round(rate * 1.18, 2)
                if e == "currency_mismatch":
                    rate, cur = round(rate * 0.91, 2), rng.choice(["EUR", "GBP"])
                if e == "date_mismatch":
                    end = end + timedelta(days=rng.choice([10, 14, 21]))
                if e == "rounding_decoy" or "decoy_ok" in ln["tags"]:
                    # tiny amount bump that should stay under overbill tolerance
                    pass
                amount = cost(units, rate, ln["rate_type"])
                if e == "rounding_decoy" or "decoy_ok" in ln["tags"]:
                    amount = round(amount + 0.01, 2)
                place = abbrev_name(ln["placement"], rng)
                if e == "ocr_name":
                    place = ocr_noise(place, rng, 0.95)
                inv_rows.append(dict(lns=[ln], placement=place, start=ln["start"], end=end,
                                     units=units, rate=rate, currency=cur, amount=amount, split=False))

            alias = rng.choice(vlines[0]["aliases"])
            if rng.random() < 0.3:
                alias = typo_vendor(alias, rng)
            date_style = rng.choice(["us", "eu", "dot", "slash_y", "mon", "iso"])
            layout = rng.choice(["pipe", "public_commercial", "labeled_rows"])
            meta = dict(vendor=alias, invoice_no=f"ADV-{seed % 10000}-{vi + 1}-{ci + 1}",
                        io_number=vlines[0]["io_number"], campaign=vlines[0]["campaign"],
                        date_style=date_style, layout=layout)
            locs = _write_invoice(out / "invoices" / fname, meta, inv_rows)
            for r, loc in zip(inv_rows, locs):
                rid = f"{fname}#{loc}"
                # For split: both parts map to same IO; for merge: map to first IO (gold notes secondary)
                primary = r["lns"][0]
                records.append(LineItem(rid, "invoice", alias, meta["campaign"], r["placement"],
                                        r["start"], r["end"], r["currency"], meta["io_number"], "",
                                        r["rate"], r["units"], r["amount"],
                                        citation=f"{fname} p1 {loc}"))
                matches[rid] = primary["io_id"]
                if len(r["lns"]) > 1:
                    # secondary IO expected unmatched on invoice side — note in gold meta
                    errors.append({"type": "unmatched_expected_merge", "key": r["lns"][1]["io_id"],
                                   "note": "merged into sibling invoice line; soft gold"})

    # Drop soft merge annotations from scored error set — keep only real planted types
    scored_errors = [e for e in errors if e["type"] in {
        "overbilling", "underdelivery", "rate_mismatch", "missing_invoice",
        "makegood", "currency_mismatch", "date_mismatch",
    } and e["key"] != "PENDING_MG"]

    # Public-style layout fixtures (documentation only + extractable samples)
    _write_public_fixtures(out / "fixtures", rng)

    gold = {
        "seed": seed,
        "generator": "adversarial",
        "held_out": True,
        "do_not_use_for_selection": True,
        "records": [r.to_dict() for r in records],
        "matches": matches,
        "errors": scored_errors,
        "notes": [
            "Vendor names on invoices/delivery intentionally use aliases/typos.",
            "IO headers use alternate vocabulary (Publisher, Line Item Description, ...).",
            "Split/merged invoice lines and multi-invoice-per-vendor are present.",
            "rounding_decoy / decoy_ok lines must NOT produce false flags.",
            "Public fixtures under fixtures/ are layout references; not in gold matches.",
        ],
    }
    (out / "gold.json").write_text(json.dumps(gold, indent=1))
    return gold


def _write_delivery(path: Path, fmt: str, vendor: str, rows: list, rng, date_style: str) -> list[str]:
    if fmt.startswith("pub"):
        if fmt == "pub_ocr":
            header = "Campagn | Plcement | From | To | Impr. | Clcks | Cost USD"  # OCR-ish header
        else:
            header = "Campaign Name ; Placement Name ; Flight Start ; Flight End ; Impressions ; Clicks ; Media Cost"
        sep = " | " if fmt == "pub_ocr" else " ; "
        lines = [f"Publisher Delivery — {vendor}", f"Window: {fmt_date(rows[0]['flight'][0], date_style)} to {fmt_date(rows[0]['flight'][1], date_style)}",
                 header]
        locs = []
        for r in rows:
            place = abbrev_name(r["placement"], rng, avoid_pipe=(sep.strip() == "|"))
            if r.get("error") == "ocr_name":
                place = ocr_noise(place, rng, 0.9)
            lines.append(sep.join([
                r["campaign"], place,
                fmt_date(r["start"], date_style), fmt_date(r["end"], date_style),
                f"{r['impressions']:,}", f"{r['clicks']:,}", f"{r['spend']:,.2f}",
            ]))
            locs.append(f"L{len(lines)}")
        _pdf(path, lines)
        return locs

    with path.open("w", newline="") as f:
        w = csv.writer(f, delimiter="\t" if fmt == "dsp_tab" else ",")
        if fmt == "meta_messy":
            w.writerow(["Campaign", "Ad set", "Start", "End", "Impressions", "Clicks", "Spend USD"])
            for r in rows:
                place = abbrev_name(r["placement"], rng)
                if r.get("error") == "ocr_name":
                    place = ocr_noise(place, rng, 0.9)
                w.writerow([r["campaign"], place, fmt_date(r["start"], date_style),
                            fmt_date(r["end"], date_style), r["impressions"], r["clicks"],
                            f"{r['spend']:.2f}"])
            return [f"R{i}" for i in range(2, len(rows) + 2)]
        if fmt == "google_eu":
            w.writerow(["Google Ads export (synthetic adversarial)"])
            w.writerow([f"{fmt_date(rows[0]['flight'][0], 'mon')} - {fmt_date(rows[0]['flight'][1], 'mon')}"])
            w.writerow(["Campaign", "Ad group", "Currency", "Impr.", "Clicks", "Cost"])
            for r in rows:
                place = abbrev_name(r["placement"], rng)
                w.writerow([r["campaign"], place, "USD", f"{r['impressions']:,}",
                            f"{r['clicks']:,}", f"{r['spend']:,.2f}"])
            return [f"R{i}" for i in range(4, len(rows) + 4)]
        # dsp_pipe / dsp_tab
        w.writerow(["Advertiser", "Campaign", "Line", "Date Start", "Date End",
                    "Impressions", "Clicks", "Cost"])
        for r in rows:
            place = abbrev_name(r["placement"], rng)
            w.writerow(["Acme Outdoor", r["campaign"], place, fmt_date(r["start"], date_style),
                        fmt_date(r["end"], date_style), r["impressions"], r["clicks"],
                        f"{r['spend']:.2f}"])
        return [f"R{i}" for i in range(2, len(rows) + 2)]


def _write_invoice(path: Path, meta: dict, rows: list) -> list[str]:
    ds = meta["date_style"]
    layout = meta["layout"]
    if layout == "public_commercial":
        # Modeled on commonly published generic commercial-invoice field labels
        lines = [
            "COMMERCIAL INVOICE (synthetic / public-style layout)",
            f"Seller: {meta['vendor']}",
            f"Invoice Number: {meta['invoice_no']}",
            f"Purchase Order / IO: {meta['io_number']}",
            f"Job / Campaign: {meta['campaign']}",
            f"Invoice Date: {fmt_date(date(2026, 10, 8), ds)}",
            "Buyer: Acme Outdoor Co. (demo)",
            "Description | Period | Quantity | Unit Price | Line Total | Currency",
        ]
    elif layout == "labeled_rows":
        lines = [
            "TAX INVOICE",
            f"From: {meta['vendor']}",
            f"Ref: {meta['invoice_no']} / {meta['io_number']}",
            f"Campaign: {meta['campaign']}",
            "Item ; Service Dates ; Qty ; Rate ; Amount ; CC",
        ]
    else:
        lines = [
            "INVOICE",
            f"Vendor: {meta['vendor']}",
            f"Invoice #: {meta['invoice_no']}",
            f"IO #: {meta['io_number']}",
            f"Campaign: {meta['campaign']}",
            f"Invoice Date: {fmt_date(date(2026, 10, 8), ds)}",
            "Placement | Service Period | Units | Rate | Amount | Currency",
        ]
    sep = " ; " if layout == "labeled_rows" else " | "
    locs = []
    for r in rows:
        period = f"{fmt_date(r['start'], ds)}-{fmt_date(r['end'], ds)}"
        place = r["placement"].replace("|", "/") if sep.strip() == "|" else r["placement"]
        lines.append(sep.join([
            place, period, f"{r['units']:,}", f"{r['rate']:.2f}",
            f"{r['amount']:,.2f}", r["currency"],
        ]))
        locs.append(f"L{len(lines)}")
    lines.append(f"Total: {sum(r['amount'] for r in rows):,.2f}")
    _pdf(path, lines)
    return locs


def _write_public_fixtures(folder: Path, rng: random.Random) -> None:
    """Tiny public-style layout samples for docs / future parser work (not in gold)."""
    # Generic IO CSV mirroring publicly documented media-plan column ideas
    with (folder / "public_style_io_headers.csv").open("w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["IO Number", "Vendor Name", "Campaign", "Placement Name",
                    "Flight Start Date", "Flight End Date", "Cost Method", "Rate",
                    "Ordered Units", "Ordered Amount", "Currency Code"])
        w.writerow(["IO-PUBLIC-1", "Example Publisher Co", "Demo Campaign",
                    "Homepage Takeover", "2026-09-01", "2026-09-30", "CPM", "12.50",
                    "1000000", "12500.00", "USD"])
    lines = [
        "SAMPLE INVOICE — public domain style fields (synthetic amounts)",
        "Supplier Name: Example Publisher Co",
        "Invoice ID: PUB-1001",
        "Buyer Reference: IO-PUBLIC-1",
        "Description of Goods/Services | Service Period | Qty | Rate | Amount | Currency",
        "Homepage Takeover | 09/01/2026-09/30/2026 | 1,000,000 | 12.50 | 12,500.00 | USD",
        "Total Amount Due: 12,500.00 USD",
    ]
    _pdf(folder / "public_style_invoice.pdf", lines)
    (folder / "README.md").write_text(
        "# Public-style layout fixtures\n\n"
        "Synthetic samples using field labels commonly seen in public commercial-invoice\n"
        "and media-plan examples. No real client data. Not part of gold.json scoring.\n"
    )


def _pdf(path: Path, lines: list[str]) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 750
    for i, text in enumerate(lines):
        c.setFont("Helvetica-Bold" if i == 0 else "Helvetica", 12 if i == 0 else 7)
        c.drawString(36, y, text[:110])
        y -= 18 if i == 0 else 12
        if y < 40:
            c.showPage()
            y = 750
    c.save()
