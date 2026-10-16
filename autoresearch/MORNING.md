# Morning summary (auto-refreshed)

_Updated: 2026-10-16T11:09:35.378814+00:00_

## Baseline vs best (DEV)
| | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| Baseline | 0.8364 | 0.941 | 0.896 | 0.710 |
| Best | 0.9220 | 0.969 | 0.960 | 0.848 |

Best change path (latest keep): `min_score 0.3833->0.3534; w_name 0.8900->0.8111; w_campaign 0.2739->0.2939; w_date 0.3328->0.1655; overbill_tol 0.0106->0.0053; vendor_jaccard_min 0.6079->0.6430; alloc_rel_tol 0.0200->0.0198; alloc_abs_tol 1.0000->5.9028; expand+olv=online`

## Latest held-out adversarial checkpoint
| checkpoint_exp | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| 7035 | 0.6892 | 0.810 | 0.810 | 0.531 |

## Validation gate (keep only if DEV improves AND validation does not drop)
Baseline validation: 0.7231 | current best validation: 0.7231 | gate rejections: 1

## Top changes kept
1. exp 63: alias+pintrest (dev 0.8364->0.8937)
2. exp 74: expand+prsp=prospecting (dev 0.8937->0.9023)
3. exp 99: expand+conv=conversion (dev 0.9023->0.9092)
4. exp 335: min_score 0.3833->0.3534; w_name 0.8900->0.8111; w_campaign 0.2739->0.2939; w_date 0.3328->0.1655; overbill_tol 0.0106->0.0053; vendor_jaccard_min 0.6079->0.6430; alloc_rel_tol 0.0200->0.0198; alloc_abs_tol 1.0000->5.9028; expand+olv=online (dev 0.9092->0.9220)

## Overfitting check
Last two held-out composites: 0.6892 → 0.6892 (DEV best 0.9220).
No clear overfitting signal at last checkpoint.

## How to read this
- DEV is the selection signal (hard DEV split: generate/dev_hard.py, seeds 424201-424205).
- Held-out adversarial is scored at checkpoints only and must not guide keeps.
- If DEV rises while held-out falls → see `ALERT_OVERFIT`.
