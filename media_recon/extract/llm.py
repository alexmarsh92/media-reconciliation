"""Optional LLM extraction plugin.

Off by default. Set MEDIA_RECON_LLM_URL to any OpenAI-compatible chat endpoint
(e.g. a local Ollama server: http://localhost:11434/v1/chat/completions) and
MEDIA_RECON_LLM_MODEL. Optional MEDIA_RECON_LLM_KEY. On any error, or when no
endpoint is configured, the deterministic parser is used, so the demo never
needs a paid key.
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from ..schema import LineItem
from . import deterministic as det

PROMPT = """Extract every invoice line item from the text below as a JSON list of objects
with keys: placement, start (YYYY-MM-DD), end (YYYY-MM-DD), units, rate, amount, currency, line_no
(the 1-based line number where the item appears). Also include top-level fields in each object:
vendor, campaign, io_number. Return JSON only.\n\n"""


def configured() -> bool:
    return bool(os.environ.get("MEDIA_RECON_LLM_URL"))


def _chat(text: str) -> str:
    body = json.dumps({"model": os.environ.get("MEDIA_RECON_LLM_MODEL", "llama3.1"), "temperature": 0,
                       "messages": [{"role": "user", "content": PROMPT + text}]}).encode()
    req = urllib.request.Request(os.environ["MEDIA_RECON_LLM_URL"], body, {"Content-Type": "application/json"})
    if os.environ.get("MEDIA_RECON_LLM_KEY"):
        req.add_header("Authorization", f"Bearer {os.environ['MEDIA_RECON_LLM_KEY']}")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.load(r)["choices"][0]["message"]["content"]


def extract_invoice(path: Path, chat=None) -> list[LineItem]:
    chat = chat or (_chat if configured() else None)
    if chat is None:
        return det.extract_invoice(path)
    try:
        text = "\n".join(f"{ln}: {t}" for _, ln, t in det.pdf_lines(path))
        raw = chat(text).strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        items = json.loads(raw)
        return [LineItem(f"{path.name}#L{it['line_no']}", "invoice", it.get("vendor", ""), it.get("campaign", ""),
                         it["placement"], det.parse_date(it.get("start")), det.parse_date(it.get("end")),
                         it.get("currency", "USD"), it.get("io_number", ""), "", det.num(it.get("rate")),
                         det.num(it.get("units")), det.num(it.get("amount")),
                         citation=f"{path.name} p1 L{it['line_no']} (llm)") for it in items]
    except Exception:
        return det.extract_invoice(path)
