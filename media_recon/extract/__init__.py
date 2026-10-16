"""Extraction layer. `extract_dir` picks the LLM plugin for PDFs when configured."""
from __future__ import annotations

from pathlib import Path

from ..generate.synth import slug
from ..schema import LineItem
from . import deterministic as det
from . import llm


def extract_dir(data: Path, use_llm: bool = False) -> list[LineItem]:
    ios = [r for p in sorted((data / "io").glob("*.xlsx")) for r in det.extract_io(p)]
    vendors = {slug(r.vendor): r.vendor for r in ios}
    inv_fn = llm.extract_invoice if use_llm else det.extract_invoice
    invoices = [r for p in sorted((data / "invoices").glob("*.pdf")) for r in inv_fn(p)]
    deliveries = []
    for p in sorted((data / "delivery").iterdir()):
        vendor_slug = p.stem.removeprefix("delivery_")
        deliveries += det.extract_delivery(p, vendors.get(vendor_slug, vendor_slug.replace("_", " ").title()))
    return ios + invoices + deliveries
