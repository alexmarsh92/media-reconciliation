"""Hard DEV split for autoresearch selection — DIFFERENT seed space AND logic from
both generate/synth.py (old easy DEV) and generate/adversarial.py (held-out).

Differences vs held-out adversarial:
- Disjoint vendor universe (TikTok, Snap, Pinterest, LinkedIn, Reddit, Microsoft, Yahoo DSP, Roku)
  and disjoint placement vocabulary / abbreviation + OCR confusion tables.
- Errors drawn per-line by probability (not a fixed plant plan); multiple campaigns per vendor.
- Cross-period flights are billed as month-by-month invoices in separate files.
- Decoys: agency/serving fee lines, near-duplicate placement names, sub-cent rounding,
  in-tolerance under-delivery (~92-95%).
- Seeds live in the 4242xx range (held-out uses 909091; old DEV used 1-5).

Failure types mirrored: vendor aliases/typos, abbreviations, split/merged lines,
multi-invoice per vendor, cross-period flights, partial makegoods, currency/date
variance, rounding, OCR noise, alternate layouts, decoys.
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

DEV_SEEDS = (424201, 424202, 424203, 424204, 424205)

VENDORS = [
    ("TikTok For Business", ["TikTok", "TikTok Ads", "Bytedance Ads", "Tik Tok"], "CPM",
     ["In-Feed Awareness Video 15s", "In-Feed Awareness Video 6s", "TopView Takeover", "Spark Ads Conversion"]),
    ("Snap Inc", ["Snapchat", "Snap Ads", "Snap Inc."], "CPM",
     ["Story Ads Retargeting", "Commercials Non-Skippable", "Collection Ads Conversion"]),
    ("Pinterest", ["Pinterest Inc", "Pinterest Ads", "Pintrest"], "CPC",
     ["Shopping Catalog Conversion", "Idea Pins Awareness", "Standard Pins Consideration"]),
    ("LinkedIn Marketing Solutions", ["LinkedIn", "LinkedIn Ads", "LI Marketing"], "CPC",
     ["Sponsored Content Lead Gen", "Message Ads Consideration", "Text Ads Desktop"]),
    ("Reddit Ads", ["Reddit Inc", "Reddit"], "CPM",
     ["Promoted Post Conversation", "Takeover Homepage", "Promoted Post Awareness"]),
    ("Microsoft Advertising", ["Bing Ads", "Microsoft Ads", "MSFT Advertising"], "CPC",
     ["Search Brand Exact", "Search Generic Phrase", "Audience Network Native"]),
    ("Yahoo DSP", ["Yahoo", "Yahoo Advertising", "Verizon Media DSP"], "CPM",
     ["Native Prospecting Desktop", "Native Prospecting Mobile", "Video Outstream Retargeting"]),
    ("Roku Advertising", ["Roku", "Roku Ads", "The Roku Channel"], "CPM",
     ["CTV Home Screen Masthead", "CTV Prime Time Video 30s", "Sponsored Themes"]),
]
CAMPAIGNS = ["Spring Refresh 2026", "Q4 Gifting Always-On", "New Market Launch", "Loyalty Win-Back"]

ABBR = {
    "Awareness": "AWR", "Conversion": "CONV", "Consideration": "CNSD", "Retargeting": "RTG",
    "Prospecting": "PRSP", "Video": "VID", "Desktop": "DT", "Mobile": "MOB", "Sponsored": "Spons",
    "Generic": "Gen", "Homepage": "HP", "Network": "Ntwk", "Native": "NTV", "Catalog": "Cat",
    "Shopping": "Shop", "Takeover": "TKO", "Collection": "Coll", "Commercials": "Comm",
}
OCR = str.maketrans({"o": "0", "O": "0", "l": "1", "i": "1", "S": "5", "B": "8", "g": "q", "n": "m"})
DATE_STYLES = ["%m-%d-%Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%b %d %Y", "%Y/%m/%d"]
# Difficulty knobs (calibrated so baseline DEV composite lands ~0.6-0.8)
CROSS_P, SPLIT_P, FEE_P, MERGE_P, ABBR_P = 0.1, 0.05, 0.12, 0.2, 0.4
INV_CANON_W, INV_TYPO_P = 10, 0.05
INV_DATE_STYLES = ["%d %b %Y", "%Y/%m/%d", "%b %d %Y", "%m/%d/%Y"]  # hyphen-free (period uses ' to ')
P_ERR = {  # per-line probabilities (independent draws, first hit wins)
    "overbilling": 0.09, "underdelivery": 0.09, "rate_mismatch": 0.07, "missing_invoice": 0.06,
    "currency_mismatch": 0.05, "date_mismatch": 0.06, "partial_makegood": 0.06,
}


def _slug(s: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in s.lower()).strip("_")


def _cost(u, r, rt):
    return round(u * r / (1000 if rt == "CPM" else 1), 2)


def _abbr(p: str, rng) -> str:
    w = [ABBR.get(x, x) if rng.random() < ABBR_P else x for x in p.split()]
    s = rng.choice(["_", " ", "-", " :: "]).join(w)
    return s.lower() if rng.random() < 0.3 else s


def _ocr(s: str, rng, k=2) -> str:
    c = list(s)
    for _ in range(k):
        if len(c) > 3:
            i = rng.randrange(1, len(c) - 1)
            c[i] = c[i].translate(OCR)
    return "".join(c)


def _typo(s: str, rng) -> str:
    if len(s) < 5:
        return s
    i = rng.randrange(1, len(s) - 1)
    return s[:i] + s[i + 1] + s[i] + s[i + 2:] if rng.random() < 0.5 else s[:i] + s[i] + s[i:]


def _pdf(path: Path, lines: list[str]) -> None:
    c = canvas.Canvas(str(path), pagesize=letter)
    y = 760
    for i, t in enumerate(lines):
        c.setFont("Courier" if i else "Times-Bold", 7 if i else 11)
        c.drawString(30, y, t[:120])
        y -= 11
        if y < 40:
            c.showPage(); y = 760
    c.save()


def generate(out: Path, seed: int = DEV_SEEDS[0]) -> dict:
    rng = random.Random(seed)
    for sub in ("io", "invoices", "delivery"):
        (out / sub).mkdir(parents=True, exist_ok=True)
        for f in (out / sub).iterdir():
            f.unlink()
    vendors = rng.sample(VENDORS, 7)
    lines, records, matches, errors = [], [], {}, []
    for vi, (canon, aliases, rt, places) in enumerate(vendors):
        camp = rng.choice(CAMPAIGNS)
        io_no = f"{_slug(canon)[:4].upper()}-{seed % 1000}-{vi}"
        cross = rng.random() < CROSS_P
        f0 = date(2026, 9, rng.choice([8, 15, 22])) if cross else date(2026, 10, 1)
        f1 = date(2026, 10, rng.choice([20, 31])) if cross else date(2026, 10, 31)
        for p in places:
            units = rng.randrange(200, 6000) * 1000 if rt == "CPM" else rng.randrange(2000, 25000)
            rate = round(rng.uniform(3.0, 35.0), 2) if rt == "CPM" else round(rng.uniform(0.5, 6.0), 2)
            err = next((e for e, pr in P_ERR.items() if rng.random() < pr), None)
            lines.append(dict(vendor=canon, aliases=aliases, rt=rt, placement=p, campaign=camp,
                              io=io_no, start=f0, end=f1, units=units, rate=rate,
                              amount=_cost(units, rate, rt), cross=cross, err=err,
                              split=rng.random() < SPLIT_P, decoy=rng.random() < 0.15))
    by_v: dict[str, list] = {}
    for ln in lines:
        by_v.setdefault(ln["vendor"], []).append(ln)

    # IO: public-style column vocabulary, mixed sheet titles
    for v, vl in by_v.items():
        fn = f"io_{_slug(v)}.xlsx"
        wb = Workbook(); ws = wb.active; ws.title = rng.choice(["Media Plan", "IO", "Schedule A"])
        ws.append(["IO Number", "Vendor Name", "Campaign", "Placement Name", "Flight Start Date",
                   "Flight End Date", "Cost Method", "Rate", "Ordered Units", "Ordered Amount", "Currency Code"])
        for i, ln in enumerate(vl, start=2):
            ws.append([ln["io"], v, ln["campaign"], ln["placement"], ln["start"], ln["end"], ln["rt"],
                       ln["rate"], ln["units"], ln["amount"], "USD"])
            ln["io_id"] = f"{fn}#R{i}"
            records.append(LineItem(ln["io_id"], "io", v, ln["campaign"], ln["placement"], ln["start"], ln["end"],
                                    "USD", ln["io"], ln["rt"], ln["rate"], ln["units"], ln["amount"],
                                    citation=f"{fn} '{ws.title}'!R{i}"))
        wb.save(out / "io" / fn)

    # delivery truth
    for ln in lines:
        e = ln["err"]
        if e == "underdelivery":
            f = rng.uniform(0.6, 0.86)
        elif e == "partial_makegood":
            f = rng.uniform(0.7, 0.85)
        elif ln["decoy"]:
            f = rng.uniform(0.92, 0.96)  # in-tolerance shortfall: must NOT flag
        else:
            f = rng.uniform(0.985, 1.04)
        ctr = rng.uniform(0.003, 0.015) if ln["rt"] == "CPM" else rng.uniform(0.01, 0.06)
        if ln["rt"] == "CPM":
            imps = round(ln["units"] * f); clicks = round(imps * ctr); bill = min(imps, ln["units"])
        else:
            clicks = round(ln["units"] * f); imps = round(clicks / ctr); bill = min(clicks, ln["units"])
        ln.update(imps=imps, clicks=clicks, bill=bill, spend=_cost(bill, ln["rate"], ln["rt"]))
        if e in ("overbilling", "underdelivery", "rate_mismatch", "missing_invoice",
                 "currency_mismatch", "date_mismatch"):
            errors.append({"type": e, "key": ln["io_id"]})
            if e == "rate_mismatch":
                errors.append({"type": "overbilling", "key": ln["io_id"]})
        if e == "partial_makegood":
            errors.append({"type": "underdelivery", "key": ln["io_id"]})

    # delivery files: 3 layouts, alias placement names, OCR, makegood rows
    for v, vl in by_v.items():
        layout = rng.choice(["meta_like", "tsv", "pdf_semi"])
        ds = rng.choice(DATE_STYLES)
        rows = []
        for ln in vl:
            nm = _abbr(ln["placement"], rng)
            if rng.random() < 0.2:
                nm = _ocr(nm, rng)
            rows.append((ln, nm, ln["imps"], ln["clicks"], ln["spend"], False))
            if ln["err"] == "partial_makegood":
                tag = rng.choice(["MG", "Bonus", "Added Value", "ADU"])
                rows.append((ln, f"{tag} - {_abbr(ln['placement'], rng)}", round(ln["imps"] * 0.08),
                             round(ln["clicks"] * 0.08), 0.0, True))
        rng.shuffle(rows)
        ext = {"meta_like": "csv", "tsv": "tsv", "pdf_semi": "pdf"}[layout]
        fn = f"delivery_{_slug(v)}.{ext}"
        locs = []
        if layout == "pdf_semi":
            txt = [f"Delivery statement - {rng.choice(vl[0]['aliases'])}", "Generated (synthetic dev)",
                   "Campaign Name ; Placement Name ; Flight Start ; Flight End ; Impressions ; Clicks ; Media Cost"]
            for ln, nm, im, cl, sp, mg in rows:
                txt.append(" ; ".join([ln["campaign"], nm, ln["start"].strftime(ds), ln["end"].strftime(ds),
                                       f"{im:,}", f"{cl:,}", f"{sp:,.2f}"]))
                locs.append(f"L{len(txt)}")
            _pdf(out / "delivery" / fn, txt)
        else:
            with (out / "delivery" / fn).open("w", newline="") as fh:
                w = csv.writer(fh, delimiter="\t" if layout == "tsv" else ",")
                if layout == "meta_like":
                    w.writerow(["Reporting starts", "Reporting ends", "Campaign name", "Ad set name",
                                "Impressions", "Link clicks", "Amount spent (USD)"])
                    for ln, nm, im, cl, sp, mg in rows:
                        w.writerow([ln["start"].strftime(ds), ln["end"].strftime(ds), ln["campaign"], nm, im, cl, f"{sp:.2f}"])
                else:
                    w.writerow(["Campaign Name", "Line Item", "Start Date", "End Date", "Impr", "Clicks", "Spend"])
                    for ln, nm, im, cl, sp, mg in rows:
                        w.writerow([ln["campaign"], nm, ln["start"].strftime(ds), ln["end"].strftime(ds), im, cl, f"{sp:.2f}"])
            locs = [f"R{i}" for i in range(2, len(rows) + 2)]
        for (ln, nm, im, cl, sp, mg), loc in zip(rows, locs):
            rid = f"{fn}#{loc}"
            records.append(LineItem(rid, "delivery", v, ln["campaign"], nm, ln["start"], ln["end"], "USD",
                                    impressions=im, clicks=cl, amount=sp, citation=f"{fn} {loc}"))
            matches[rid] = None if mg else ln["io_id"]
            if mg:
                errors.append({"type": "makegood", "key": rid})

    # invoices: monthly billing for cross-period flights, splits, merges, fee decoys
    for vi, (v, vl) in enumerate(by_v.items()):
        months = [(date(2026, 9, 1), date(2026, 9, 30)), (date(2026, 10, 1), date(2026, 10, 31))] \
            if vl[0]["cross"] else [(date(2026, 10, 1), date(2026, 10, 31))]
        inv_rows = {m: [] for m in range(len(months))}
        total_days = (vl[0]["end"] - vl[0]["start"]).days + 1
        merge_done = False
        for ln in vl:
            e = ln["err"]
            if e == "missing_invoice":
                continue
            units, rate, cur, end = ln["bill"], ln["rate"], "USD", ln["end"]
            if e == "overbilling":
                units = round(units * rng.uniform(1.08, 1.25))
            if e == "rate_mismatch":
                rate = round(rate * rng.uniform(1.07, 1.2), 2)
            if e == "currency_mismatch":
                cur = rng.choice(["CAD", "EUR", "GBP"])
            if e == "date_mismatch":
                end = end + timedelta(days=rng.choice([7, 12, 30]))
            # monthly split
            for mi, (m0, m1) in enumerate(months):
                s, en = max(ln["start"], m0), min(end, m1) if mi < len(months) - 1 else end
                frac = 1.0 if len(months) == 1 else ((min(ln["end"], m1) - max(ln["start"], m0)).days + 1) / total_days
                u = round(units * frac)
                parts = [(0.6, " (1/2)"), (0.4, " (2/2)")] if ln["split"] and e is None else [(1.0, "")]
                for pf, suf in parts:
                    uu = round(u * pf)
                    amt = _cost(uu, rate, ln["rt"])
                    if ln["decoy"]:
                        amt = round(amt + rng.choice([-0.01, 0.01, 0.02]), 2)
                    nm = _abbr(ln["placement"], rng)
                    if rng.random() < 0.25:
                        nm = _ocr(nm, rng)
                    inv_rows[mi].append(dict(lns=[ln], placement=nm + suf, start=s, end=en, units=uu,
                                             rate=rate, cur=cur, amount=amt))
        # merge two clean rows into one (sum line), once per vendor sometimes
        for mi, rows in inv_rows.items():
            clean = [r for r in rows if r["lns"][0]["err"] is None and not r["lns"][0]["split"]]
            if not merge_done and len(clean) >= 2 and rng.random() < MERGE_P:
                a, b = clean[0], clean[1]
                rows.remove(b)
                a.update(lns=a["lns"] + b["lns"], placement=f"{a['placement']} & {b['placement']}",
                         units=a["units"] + b["units"], amount=round(a["amount"] + b["amount"], 2))
                merge_done = True
            if rng.random() < FEE_P:  # fee decoy: legit non-media line
                rows.append(dict(lns=[], placement=rng.choice(["Ad Serving Fee", "Platform Tech Fee", "Creative Production"]),
                                 start=months[mi][0], end=months[mi][1], units=1,
                                 rate=round(rng.uniform(150, 900), 2), cur="USD", amount=0))
                rows[-1]["amount"] = rows[-1]["rate"]
        alias = rng.choice(vl[0]["aliases"] + [v] * INV_CANON_W)
        if rng.random() < INV_TYPO_P:
            alias = _typo(alias, rng)
        for mi, rows in inv_rows.items():
            if not rows:
                continue
            fn = f"inv_{_slug(v)}_{months[mi][0]:%Y%m}.pdf"
            ds = rng.choice(INV_DATE_STYLES)
            lay = rng.choice(["supplier", "taxinv", "classic"])
            invno = f"D{seed % 997}-{vi}{mi}"
            if lay == "supplier":
                txt = ["Statement of Charges", f"Supplier Name: {alias}", f"Invoice ID: {invno}",
                       f"Buyer Reference: {vl[0]['io']}", f"Campaign Name: {vl[0]['campaign']}",
                       "Description | Service Period | Qty | Rate | Amount | Currency"]
                sep = " | "
            elif lay == "taxinv":
                txt = ["TAX INVOICE", f"From: {alias}", f"Ref: {invno} / {vl[0]['io']}",
                       f"Campaign: {vl[0]['campaign']}", "Item ; Service Dates ; Qty ; Rate ; Amount ; CC"]
                sep = " ; "
            else:
                txt = ["INVOICE", f"Vendor: {alias}", f"Invoice #: {invno}", f"IO #: {vl[0]['io']}",
                       f"Campaign: {vl[0]['campaign']}", "Placement | Service Period | Units | Rate | Amount | Currency"]
                sep = " | "
            locs = []
            for r in rows:
                pl = r["placement"].replace("|", "/").replace(";", ",")
                txt.append(sep.join([pl, f"{r['start'].strftime(ds)} to {r['end'].strftime(ds)}",
                                     f"{r['units']:,}", f"{r['rate']:.2f}", f"{r['amount']:,.2f}", r["cur"]]))
                locs.append(f"L{len(txt)}")
            txt.append(f"Amount Due: {sum(r['amount'] for r in rows):,.2f}")
            _pdf(out / "invoices" / fn, txt)
            for r, loc in zip(rows, locs):
                rid = f"{fn}#{loc}"
                records.append(LineItem(rid, "invoice", alias, vl[0]["campaign"], r["placement"], r["start"], r["end"],
                                        r["cur"], vl[0]["io"], "", r["rate"], r["units"], r["amount"],
                                        citation=f"{fn} p1 {loc}"))
                matches[rid] = r["lns"][0]["io_id"] if r["lns"] else None

    gold = {"seed": seed, "generator": "dev_hard", "held_out": False, "records": [r.to_dict() for r in records],
            "matches": matches, "errors": errors}
    (out / "gold.json").write_text(json.dumps(gold, indent=1, default=str))
    return gold
