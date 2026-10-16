import json
from pathlib import Path

import pytest

from media_recon.eval import evaluate, score
from media_recon.extract import deterministic as det, llm
from media_recon.generate.synth import generate
from media_recon.match import is_makegood, tokens
from media_recon.pipeline import run


@pytest.fixture(scope="module")
def batch(tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    gold = generate(d, seed=3)
    return d, gold, run(d, d / "out")


def test_generator_writes_all_sources(batch):
    d, gold, _ = batch
    assert len(list((d / "io").glob("*.xlsx"))) == 6
    assert len(list((d / "invoices").glob("*.pdf"))) == 6
    assert {p.suffix for p in (d / "delivery").iterdir()} == {".csv", ".pdf"}
    assert json.loads((d / "gold.json").read_text())["errors"]


def test_outputs_written(batch):
    d, _, res = batch
    for f in ("exceptions.csv", "exceptions.xlsx", "accruals.csv", "summary.html"):
        assert (d / "out" / f).stat().st_size > 0
    assert res["summary"]["dollars_at_risk_usd"] > 0


def test_every_exception_has_citation_and_confidence(batch):
    for e in batch[2]["exceptions"]:
        assert e.citation and 0 <= e.confidence <= 1


def test_clean_data_scores_perfectly(batch):
    _, gold, res = batch
    m = score(gold, res)
    assert m["extraction_field_accuracy"] == 1.0
    assert m["match_precision"] == m["match_recall"] == 1.0
    assert m["error_recall"] == 1.0


def test_noisy_data_still_mostly_matches():
    r = evaluate(seeds=(1, 2), noise=0.3)
    assert r["match_precision"] >= 0.95 and r["match_recall"] >= 0.85


def test_parsers():
    assert det.num("$1,234.50") == 1234.5
    assert str(det.parse_date("September 30, 2026")) == "2026-09-30"
    assert tokens("FEED - PROSP - MOB") == {"feed", "prospecting", "mobile"}
    assert is_makegood(type("R", (), {"placement": "q3_mg_ctv_video_makegood"})())


def test_llm_plugin_falls_back_offline(batch, monkeypatch):
    d = batch[0]
    pdf = next((d / "invoices").glob("*.pdf"))
    monkeypatch.delenv("MEDIA_RECON_LLM_URL", raising=False)
    assert llm.extract_invoice(pdf) == det.extract_invoice(pdf)
    bad = lambda text: "not json"
    assert llm.extract_invoice(pdf, chat=bad) == det.extract_invoice(pdf)


def test_llm_plugin_parses_model_json(batch):
    pdf = next((batch[0] / "invoices").glob("*.pdf"))
    fake = lambda text: json.dumps([{"placement": "X", "start": "2026-09-01", "end": "2026-09-30", "units": "1,000",
                                     "rate": 10, "amount": 10, "currency": "USD", "line_no": 9, "vendor": "V"}])
    (item,) = llm.extract_invoice(pdf, chat=fake)
    assert item.units == 1000 and item.citation.endswith("(llm)")


def test_streamlit_app_renders(monkeypatch, tmp_path):
    import shutil
    from streamlit.testing.v1 import AppTest
    shutil.copy(Path(__file__).parent.parent / "app.py", tmp_path / "app.py")
    monkeypatch.chdir(tmp_path)
    at = AppTest.from_file(str(tmp_path / "app.py"), default_timeout=60).run()
    assert not at.exception and len(at.metric) == 5
