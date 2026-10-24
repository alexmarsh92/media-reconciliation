# Agent-friendly plan: media-reconciliation

Self-approved 2026-10-16. Order: structure → static checks → minimal prose → human review.

## Evidence (13 commits, PRs #1–#4; the only PR comment is the agent's own #3 closing note)

| # | Recurring pitfall | Count | Evidence |
|---|---|---|---|
| 1 | Overnight loop gains that were DEV-only / overfit | 4 | c4ed313 (saturated DEV), 0837691 (replace easy DEV), 5236b3f (reset overfit run), PR #3 closed (exp 335: val/held-out flat, 2 tests fail) |
| 2 | Held-out or vendor-specific knowledge leaking into the search space | 2 | 0837691 (drop held-out vocab from mutation candidates), 5236b3f (cap vendor-specific alias changes) |
| 3 | Thresholds tuned where the bottleneck was structural | 2 | PR #3 → #4 (vendor identity resolution, optimal assignment) |
| 4 | Eval wiring errors / dead code | 2 (1 each) | 8cfeb21 (wrong held-out key), 8003871 (dead schema code) |
| 5 | Loop runtime artifacts tracked | 1 | autoresearch/nohup.out |

Pitfalls 1 and 3 were already fixed structurally by PR #4 (validation gate, redesigned objective, sealed v2 with a tree hash asserted in `sealed_eval.py`).

## Changes
1. **PR (this):** `guardrails.json` + `tests/test_guardrails.py`: per-file sealed hashes for all 74 sealed files, a sealed-reader allowlist (pitfall 2: new tuning code that touches `sealed_holdout` fails CI and is pointed at `evaluate_sealed()`), runtime-artifact guard (pitfall 5). CI runs pytest. Test/CI only; no code under `media_recon/` changes, so the jump run and the Oct 22 demo are unaffected.
2. **Next (after 21:13 UTC jump run):** move vendor alias tables behind one typed `VendorRegistry` so loops can't add per-vendor aliases outside the cap (pitfall 2 at the type level); add `ruff` with unused-symbol rules to CI (pitfall 4).
3. Prose: `AGENTS.md` rule table. Verification: `.cursor/skills/verify-media-reconciliation/SKILL.md`.
