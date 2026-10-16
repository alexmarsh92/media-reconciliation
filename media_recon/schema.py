"""Domain model: one typed record per source line, plus matches and exceptions."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date

SOURCES = ("io", "invoice", "delivery")

# Fields compared in the extraction eval, per source.
FIELDS = {
    "io": ["io_number", "vendor", "campaign", "placement", "start", "end",
           "rate_type", "rate", "units", "amount", "currency"],
    "invoice": ["io_number", "vendor", "campaign", "placement", "start", "end",
                "units", "rate", "amount", "currency"],
    "delivery": ["vendor", "campaign", "placement", "start", "end",
                 "impressions", "clicks", "amount", "currency"],
}

EXCEPTION_TYPES = ("overbilling", "underdelivery", "rate_mismatch", "missing_invoice",
                   "makegood", "currency_mismatch", "date_mismatch",
                   "unmatched_invoice", "unmatched_delivery")


@dataclass
class LineItem:
    """A line from an IO/media plan, an invoice, or a delivery report.

    amount = contracted cost (io) | invoiced amount (invoice) | reported spend (delivery)
    units  = contracted units (io) | invoiced units (invoice)
    """
    record_id: str
    source: str
    vendor: str
    campaign: str
    placement: str
    start: date | None = None
    end: date | None = None
    currency: str = "USD"
    io_number: str = ""
    rate_type: str = ""          # CPM or CPC
    rate: float | None = None
    units: float | None = None
    amount: float | None = None
    impressions: float | None = None
    clicks: float | None = None
    citation: str = ""           # e.g. "invoice_meta.pdf p1 line 9"

    def to_dict(self) -> dict:
        d = asdict(self)
        for k in ("start", "end"):
            d[k] = d[k].isoformat() if d[k] else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "LineItem":
        d = dict(d)
        for k in ("start", "end"):
            d[k] = date.fromisoformat(d[k]) if d.get(k) else None
        return cls(**d)


@dataclass
class Match:
    io_id: str
    invoice_id: str | None
    delivery_id: str | None
    confidence: float
    citations: list[str] = field(default_factory=list)
    # Grouped matching (one-to-many / many-to-one). invoice_id/delivery_id stay the primary line.
    invoice_ids: list[str] = field(default_factory=list)
    delivery_ids: list[str] = field(default_factory=list)
    covered_by: list[str] = field(default_factory=list)   # merged invoice lines (primary on another IO) that also bill this IO


@dataclass
class ReconException:
    type: str
    key: str                 # IO record id, or the orphan record id
    vendor: str
    placement: str
    amount_at_risk: float
    detail: str
    confidence: float
    citation: str
