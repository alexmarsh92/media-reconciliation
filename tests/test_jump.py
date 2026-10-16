from pathlib import Path

from media_recon.match import hungarian_max, name_affinity, resolve_vendors
from media_recon.schema import LineItem


def _li(rid, src, vendor, placement, io_number=""):
    return LineItem(rid, src, vendor, "Camp", placement, io_number=io_number)


def test_name_affinity_typos_and_suffixes():
    assert name_affinity("Outbrian", "Outbrain") > name_affinity("Outbrian", "Taboola")
    assert name_affinity("Amazon Ads", "Amazon Advertising") >= 0.9
    assert name_affinity("Samsuung Ads", "Samsung Ads") >= 0.5
    assert name_affinity("Outbrain", "Taboola") < 0.3


def test_resolve_vendor_by_placement_vote_for_rebrand():
    recs = [_li("io1", "io", "X Ads", "Promoted Post Awareness"), _li("io2", "io", "X Ads", "Trend Takeover Homepage"),
            _li("io3", "io", "Quora Ads", "Question Targeting Text"), _li("io4", "io", "Quora Ads", "Lead Gen Form Ads"),
            _li("i1", "invoice", "Twitter", "Promoted Post Awareness"), _li("i2", "invoice", "Twitter", "Trend Homepage")]
    out = {r.record_id: r.vendor for r in resolve_vendors(recs)}
    assert out["i1"] == out["i2"] == "X Ads"


def test_resolve_vendor_by_io_number():
    recs = [_li("io1", "io", "Kargo", "Breakout", "IO-9"), _li("io2", "io", "Vevo Ads", "Preroll", "IO-7"),
            _li("i1", "invoice", "Zzz Holdings", "Something", "IO-9")]
    assert {r.record_id: r.vendor for r in resolve_vendors(recs)}["i1"] == "Kargo"


def test_ambiguous_vendor_left_unresolved():
    recs = [_li("io1", "io", "Alpha Media", "Video"), _li("io2", "io", "Beta Media", "Video"),
            _li("i1", "invoice", "Gamma", "Video")]
    assert {r.record_id: r.vendor for r in resolve_vendors(recs)}["i1"] == "Gamma"


def test_hungarian_beats_greedy():
    # greedy takes (0,0)=0.9 then (1,1)=0.1; optimal is (0,1)+(1,0)=1.6
    assert sorted(hungarian_max([[0.9, 0.8], [0.8, 0.1]])) == [(0, 1), (1, 0)]
    assert len(hungarian_max([[0.5, 0.2, 0.9]])) == 1


def test_sealed_holdout_hash_intact_and_not_read_by_loop():
    from media_recon.eval.sealed_eval import ROOT, tree_hash
    assert tree_hash(ROOT) == (ROOT / "SHA256").read_text().split()[0]
    loop = Path(__file__).resolve().parents[1].joinpath("autoresearch", "loop.py").read_text()
    # sealed set is only used through the checkpoint function, never in selection/gate
    assert loop.count("evaluate_sealed()") == 1
    ea = Path(__file__).resolve().parents[1].joinpath("tools", "error_analysis.py").read_text()
    assert "sealed" not in ea
