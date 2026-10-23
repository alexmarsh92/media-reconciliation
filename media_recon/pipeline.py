"""End-to-end: extract -> match -> detect -> write outputs."""
from __future__ import annotations

import hashlib
from pathlib import Path

from .exceptions import detect
from .extract import extract_dir
from .match import match
from .report import write_outputs


def run(data: Path, out: Path, use_llm: bool = False) -> dict:
    records = extract_dir(data, use_llm=use_llm)
    matches, matched = match(records)
    exc = detect(records, matches, matched)
    summary = write_outputs(out, records, matches, exc)
    return {"records": records, "matches": matches, "matched": matched, "exceptions": exc, "summary": summary}


def inputs_fingerprint(data: Path) -> str:
    """Hash of input file paths, sizes and mtimes; changes only when the inputs change."""
    h = hashlib.sha256()
    for p in sorted(Path(data).rglob("*")):
        if p.is_file():
            st = p.stat()
            h.update(f"{p.relative_to(data)}|{st.st_size}|{st.st_mtime_ns}\n".encode())
    return h.hexdigest()
