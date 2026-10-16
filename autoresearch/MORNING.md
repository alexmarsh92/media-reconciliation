# Morning summary (auto-refreshed)

_Updated: 2026-10-16T02:24:49.799103+00:00_

## Baseline vs best (DEV)
| | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| Baseline | 0.9958 | 0.996 | 1.000 | 0.991 |
| Best | 1.0000 | 1.000 | 1.000 | 1.000 |

Best change path (latest keep): `min_score 0.3819->0.3293; w_name 0.8900->0.8900; w_campaign 0.2739->0.2798; w_date 0.3328->0.3328; underdelivery_pct 0.9005->0.9010; overbill_tol 0.0106->0.0050; rate_tol 0.0053->0.0056; expand+aud=audience`

## Latest held-out adversarial checkpoint
| checkpoint_exp | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| 90 | 0.6400 | 0.762 | 0.762 | 0.485 |

## Top changes kept
1. exp 12: min_score 0.3819->0.3293; w_name 0.8900->0.8900; w_campaign 0.2739->0.2798; w_date 0.3328->0.3328; underdelivery_pct 0.9005->0.9010; overbill_tol 0.0106->0.0050; rate_tol 0.0053->0.0056; expand+aud=audience (dev 0.9958->1.0000)

## Overfitting check
Last two held-out composites: 0.6400 → 0.6400 (DEV best 1.0000).
No clear overfitting signal at last checkpoint.

## How to read this
- DEV is the selection signal (messy noise=0.75).
- Held-out adversarial is scored at checkpoints only and must not guide keeps.
- If DEV rises while held-out falls → see `ALERT_OVERFIT`.
