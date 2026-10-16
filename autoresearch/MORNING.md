# Morning summary (auto-refreshed)

_Status: loop not finished yet. This file is rewritten by the overnight loop / summarizer._

## Baseline vs best (DEV)
| | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| Baseline | TBD | TBD | TBD | TBD |
| Best | TBD | TBD | TBD | TBD |

## Latest held-out adversarial checkpoint
| checkpoint_exp | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| — | — | — | — | — |

## Top changes kept
_None yet._

## Overfitting check
_No checkpoint comparison yet._

## How to read this
- DEV is the selection signal (messy noise=0.6).
- Held-out adversarial is scored at checkpoints only and must not guide keeps.
- If DEV rises while held-out falls → see `ALERT_OVERFIT`.
