---
name: verify-media-reconciliation
description: Prove a change to media-reconciliation works through its CLI, demo UI and sealed gate. Use before opening or merging any PR in this repo.
---

# Verify media-reconciliation

Surface: the `media-recon` CLI (generate → run → eval) and the Streamlit demo (`app.py`, used in the Oct 22 demo). Offline; no keys.

Isolate: use your own `git worktree` and venv (`/workspace/projects/media-reconciliation/.venv` works read-only as an interpreter). Never touch `/workspace/projects/media-reconciliation` itself or the `autoresearch/jump-run` branch while PID 237997 runs. `generate`/`run` write under `data/`, so run them only in your worktree.

1. Tests (same as CI): `python -m pytest -q` → `0 failed`. A `test_guardrails.py` failure names the fix.
2. CLI: `python -m media_recon generate && python -m media_recon run && python -m media_recon eval` → exceptions/accruals files under `data/output/` and an eval score.
3. Demo UI: `streamlit run app.py --server.headless true --server.port 8599 &` then `curl -sf localhost:8599/_stcore/health` → `ok`. For visual checks, open it in the browser, click **Generate synthetic month**, and walk Exceptions → Matches → Accruals → Summary. Kill the server after.
4. Sealed gate (merge time only): `python -m media_recon.eval.sealed_eval` → `composite` ≥ 0.852. The script asserts the sealed tree hash; an assertion error means the sealed data was modified, which is never allowed.

PRs that change shared code under `media_recon/` merge only after the jump run ends (~21:13 UTC Oct 16) or stay open.
