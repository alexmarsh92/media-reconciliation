"""Structural guardrails for agents. Config lives in guardrails.json at the repo root (single source of truth).

1. Sealed held-out files match their locked sha256 and every file under a sealed dir is locked.
2. Only the listed checkpoint modules may reference sealed data; everything else scores dev/validation.
3. Loop runtime artifacts (PID files, logs, state) may not be newly tracked by git.
"""
import fnmatch, hashlib, json, re, subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CFG = json.loads((ROOT / "guardrails.json").read_text())
SEALED_TOKEN = re.compile(r"sealed", re.I)


def _tracked():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return out.split()


def _sha(p):
    return hashlib.sha256((ROOT / p).read_bytes()).hexdigest()


def test_sealed_files_match_lock():
    bad = [p for p, h in CFG["sealed_files"].items() if not (ROOT / p).is_file() or _sha(p) != h]
    assert not bad, (f"Sealed held-out files changed or missing: {bad}. Sealed sets are never edited. "
                     "Build a NEW sealed set in a new dir, demote the old one to diagnostic/, and update guardrails.json in the same PR.")


def test_every_sealed_file_is_locked():
    unlocked = [p for p in _tracked() if any(fnmatch.fnmatch(p, g) for g in CFG["sealed_globs"])
                and p not in CFG["sealed_files"] and p not in CFG.get("sealed_unhashed", [])]
    assert not unlocked, f"Files in sealed dirs without a sha256 in guardrails.json: {unlocked}"


def test_only_checkpoint_modules_reference_sealed():
    readers = set(CFG["sealed_readers"]) | {"tests/test_guardrails.py"}
    offenders = [p for p in _tracked() if p.endswith(".py") and p not in readers
                 and not any(fnmatch.fnmatch(p, g) for g in CFG["sealed_globs"])
                 and SEALED_TOKEN.search((ROOT / p).read_text(errors="ignore"))]
    assert not offenders, (f"{offenders} reference sealed held-out data. Search/tuning code must score dev/validation only; "
                           f"get the sealed score through {CFG['sealed_entrypoint']}.")


def test_no_new_runtime_artifacts():
    pats = CFG["runtime_patterns"]
    new = [p for p in _tracked() if any(fnmatch.fnmatch(p, g) for g in pats) and p not in CFG["runtime_baseline"]]
    assert not new, (f"Loop runtime artifacts are tracked: {new}. Add them to .gitignore and `git rm --cached` them; "
                     "loop state belongs on the loop branch or outside git.")
