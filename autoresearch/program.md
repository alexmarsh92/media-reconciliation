# Autoresearch overnight — media reconciliation

## Objective
Maximize the **DEV composite** metric on the **hard DEV split** (`media_recon/generate/dev_hard.py`,
seeds 424201–424205). Restarted 2026-10-16: the old messy-synthetic DEV (noise=0.75, seeds 1–5)
saturated at 1.000 and gave no signal; it is retired (old log: `results_easy_dev.tsv.bak`).

The hard DEV split mirrors adversarial failure types (vendor aliases/typos, abbreviations,
split/merged lines, multi-invoice per vendor, cross-period monthly billing, partial makegoods,
currency/date variance, rounding, OCR noise, alternate layouts, fee/near-duplicate decoys) but uses a
**different seed space, vendor universe, vocabulary and generator logic** from the held-out set.
Baseline (original default tunables) ≈ 0.59.

```
composite = harmonic_mean(match_recall, error_recall, flag_precision)
```

Fixed eval command (prints ONE float):

```bash
python -m media_recon.eval.composite
```

## 2026-10-16 restart #2 — grouped matching
The 1:1 match cap was the bottleneck (flag precision ~0.49 even after tuning). A hand-written
**grouped-matching baseline** now lives in `media_recon/match` + `media_recon/exceptions`:
one-to-many (split lines, month-by-month cross-period billing), many-to-one (merged "A & B"
invoice lines cover both IO lines), aggregate reconciliation within allocation tolerances,
non-media fee lines not flagged, citations/confidence kept on every grouped match.
Same tunables, 1:1 → grouped: DEV 0.702 → 0.828 (flag precision 0.491 → 0.696).
Previous 1:1 hard-DEV run archived as `*_hardv1_1to1*.bak`.

The loop still edits **tunables.json only** (no free-form code edits overnight — unsafe to revert
reliably), but now also tunes the grouped knobs: `enable_grouped`, `group_min_score_factor`,
`group_date_window_days`, `merge_split`, `merge_part_min_score`, `alloc_rel_tol`, `alloc_abs_tol`,
`date_tol_days`. Structural changes are made by a human/agent between runs, then the loop re-tunes.

## 2026-10-16 restart #3 — overfit fix + validation gate
Exp 47 (`min_score 0.3833->0.3231`) overfit: DEV up, held-out 0.6892 -> 0.6543, never recovered.
Reset to the pre-exp-47 tunables (`autoresearch/pre_exp47_tunables.json`, = exp 9 state).
Prior run archived as `*_hardv2_grouped_overfit_exp47*.bak` (see ARCHIVE_NOTE.md).

Three splits now:
| split | generator | seeds | role |
|---|---|---|---|
| DEV | `generate/dev_hard.py` | 424201–424205 | selection signal |
| VALIDATION | `generate/validation.py` (disjoint vendors, vocab, abbreviation/OCR tables, error mix) | 771301–771304 | non-regression gate |
| HELD-OUT | `data/adversarial/` (seed 909091) | fixed | checkpoints only, never selection |

**Keep rule:** keep a change only if DEV improves AND validation does not drop.
**Over-specificity caps:** at most 3 vendor-specific alias entries added beyond the baseline table
(`AUTORESEARCH_MAX_ALIAS_ADDS`); single-string alias-only changes must improve DEV by >= 0.005
(`AUTORESEARCH_SPECIFIC_MIN_GAIN`); vendor-alias proposals are sampled far less often than generic
abbreviation expansions. Validation vendors share no aliases with DEV, so only general changes can help it.

## Rules
1. Edit **only** matching / extraction / threshold code via `media_recon/tunables.json`
   (and, if needed, narrowly scoped keys inside that JSON: min_score, weights,
   exception tolerances, expand aliases, vendor_aliases, date formats, soft_vendor).
2. **Never** train on or select winners using `data/adversarial/` (held-out, seed 909091).
   Mutation candidate tables in loop.py are drawn from DEV vocabulary only.
3. Score held-out adversarial at **checkpoints only** (every N kept improvements or every K experiments).
4. Free compute only. No paid APIs. No network model calls.
5. If DEV improves AND validation does not drop → keep. Else → revert tunables.json to previous best.
6. Log every experiment to `autoresearch/results.tsv`.
7. On each new best DEV score, update `autoresearch/live_best.json` and append
   `autoresearch/live_updates.log` (for the live monitor).
8. If a checkpoint shows DEV↑ but held-out↓ vs previous checkpoint → write
   `autoresearch/ALERT_OVERFIT`.
9. On stall/crash → write `autoresearch/ALERT_STALL`.
10. Do not merge PRs. Do not force-push.

## Search strategy
Structured random / evolutionary search over tunables.json (no LLM required):
- Perturb thresholds (min_score, underdelivery_pct, overbill_tol, rate_tol, weights)
- Mutate expand + vendor_aliases tables
- Toggle soft_vendor / vendor_jaccard_min
