from datetime import date

from media_recon.exceptions import detect
from media_recon.match import match
from media_recon.schema import LineItem


def _io(rid, pl, units=1_000_000, rate=10.0):
    return LineItem(rid, "io", "Snap Inc", "Spring", pl, date(2026, 9, 15), date(2026, 10, 31), "USD",
                    "IO-1", "CPM", rate, units, units * rate / 1000)


def test_split_crossperiod_and_merged_lines_reconcile():
    a, b = _io("io#A", "Story Ads Retargeting"), _io("io#B", "Collection Ads Conversion")
    recs = [a, b,
            LineItem("d#1", "delivery", "Snap", "Spring", "story ads retargeting", a.start, a.end, impressions=1_000_000),
            LineItem("d#2", "delivery", "Snap", "Spring", "collection ads conversion", b.start, b.end, impressions=1_000_000),
            # A billed month-by-month (cross-period), and split in two
            LineItem("i#1", "invoice", "Snap", "Spring", "Story Ads Retargeting (1/2)", date(2026, 9, 15), date(2026, 9, 30),
                     "USD", "IO-1", "", 10.0, 200_000, 2000.0),
            LineItem("i#2", "invoice", "Snap", "Spring", "Story Ads Retargeting (2/2)", date(2026, 9, 15), date(2026, 9, 30),
                     "USD", "IO-1", "", 10.0, 150_000, 1500.0),
            LineItem("i#3", "invoice", "Snap", "Spring", "Story Ads Retargeting", date(2026, 10, 1), date(2026, 10, 31),
                     "USD", "IO-1", "", 10.0, 650_000, 6500.0),
            LineItem("i#4", "invoice", "Snap", "Spring", "Ad Serving Fee", date(2026, 10, 1), date(2026, 10, 31),
                     "USD", "IO-1", "", 300.0, 1, 300.0)]
    ms, flat = match(recs)
    assert {flat[x] for x in ("i#1", "i#2", "i#3")} == {"io#A"}
    exc = detect(recs, ms, flat)
    # B has no own invoice -> missing_invoice is legit; A must reconcile cleanly; fee is not flagged
    assert not [e for e in exc if e.key == "io#A"]
    assert not [e for e in exc if e.key == "i#4"]
    mb = next(m for m in ms if m.io_id == "io#A")
    assert len(mb.invoice_ids) == 3 and len(mb.citations) >= 5


def test_merged_invoice_line_covers_both_ios():
    a, b = _io("io#A", "Story Ads Retargeting"), _io("io#B", "Collection Ads Conversion")
    recs = [a, b,
            LineItem("d#1", "delivery", "Snap", "Spring", "story ads retargeting", a.start, a.end, impressions=1_000_000),
            LineItem("d#2", "delivery", "Snap", "Spring", "collection ads conversion", b.start, b.end, impressions=1_000_000),
            LineItem("i#1", "invoice", "Snap", "Spring", "Story Ads Retargeting & Collection Ads Conversion",
                     a.start, a.end, "USD", "IO-1", "", 10.0, 2_000_000, 20000.0)]
    ms, flat = match(recs)
    exc = detect(recs, ms, flat)
    assert not exc, exc
