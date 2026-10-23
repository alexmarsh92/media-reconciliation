"""Reruns (e.g. filter clicks) must not rewrite outputs; only input changes do."""
from pathlib import Path

import pytest

AppTest = pytest.importorskip("streamlit.testing.v1").AppTest
ROOT = Path(__file__).resolve().parents[1]


def test_rerun_does_not_rewrite_outputs(monkeypatch):
    monkeypatch.chdir(ROOT)
    at = AppTest.from_file(str(ROOT / "app.py"), default_timeout=120).run()
    assert not at.exception
    xlsx = ROOT / "data/output/exceptions.xlsx"
    before = xlsx.stat().st_mtime_ns
    at.multiselect[0].select(at.multiselect[0].options[0]).run()
    at.run()
    assert not at.exception
    assert xlsx.stat().st_mtime_ns == before


def test_fingerprint_changes_with_inputs(tmp_path):
    from media_recon.pipeline import inputs_fingerprint
    (tmp_path / "a.csv").write_text("x")
    f1 = inputs_fingerprint(tmp_path)
    assert inputs_fingerprint(tmp_path) == f1
    (tmp_path / "a.csv").write_text("xy")
    assert inputs_fingerprint(tmp_path) != f1
