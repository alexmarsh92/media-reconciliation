# Autoresearch overnight — media reconciliation

## Objective
Maximize the **DEV composite** metric on the messy synthetic tier (noise=0.75, seeds 1–5):

```
composite = harmonic_mean(match_recall, error_recall, flag_precision)
```

Fixed eval command (prints ONE float):

```bash
python -m media_recon.eval.composite
```

## Rules
1. Edit **only** matching / extraction / threshold code via `media_recon/tunables.json`
   (and, if needed, narrowly scoped keys inside that JSON: min_score, weights,
   exception tolerances, expand aliases, vendor_aliases, date formats, soft_vendor).
2. **Never** train on or select winners using `data/adversarial/` (held-out).
3. Score held-out adversarial at **checkpoints only** (every N kept improvements or every K experiments).
4. Free compute only. No paid APIs. No network model calls.
5. If DEV improves → keep. Else → revert tunables.json to previous best.
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
