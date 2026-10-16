# Morning summary (auto-refreshed)

_Updated: 2026-10-16T03:07:33.825814+00:00_

## Baseline vs best (DEV)
| | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| Baseline | 0.8364 | 0.941 | 0.896 | 0.710 |
| Best | 0.8364 | 0.941 | 0.896 | 0.710 |

Best change path (latest keep): `(baseline)`

## Latest held-out adversarial checkpoint
| checkpoint_exp | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| — | — | — | — | — |

## Validation gate (keep only if DEV improves AND validation does not drop)
Baseline validation: 0.7231 | current best validation: 0.7231 | gate rejections: 0

## Top changes kept
_None yet._

## Overfitting check
_Need at least two held-out checkpoints._

## How to read this
- DEV is the selection signal (hard DEV split: generate/dev_hard.py, seeds 424201-424205).
- Held-out adversarial is scored at checkpoints only and must not guide keeps.
- If DEV rises while held-out falls → see `ALERT_OVERFIT`.
