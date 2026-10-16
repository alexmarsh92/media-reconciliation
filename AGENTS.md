# Agent rules

Most rules here are enforced by code. Prose is only for the judgment calls at the bottom.

| Rule | Enforced by |
|---|---|
| Sealed held-out files are never edited; a new sealed set goes in a new dir and the old one moves to `diagnostic/` | `tests/test_guardrails.py::test_sealed_files_match_lock` (hashes in `guardrails.json`) |
| Every file in a sealed dir has a locked hash | `test_every_sealed_file_is_locked` |
| Only checkpoint modules read sealed data; tuning scores dev/validation | `test_only_checkpoint_modules_reference_sealed` |
| Loop runtime state (PID, logs, state.json) is not committed | `test_no_new_runtime_artifacts` |
| Tests pass on every push and PR | `.github/workflows/ci.yml` |

Judgment calls (not enforced):
- Keep a change only if dev improves AND validation improves; dev-only gains are overfitting.
- Prefer structural fixes (new stage, new feature, new matcher) over thresholds or one-off vocabulary.
- Once you analyse misses on a held-out set it is a diagnostic set; build a new sealed one.
- Verify with `.cursor/skills/verify-*/SKILL.md` before opening a PR.
