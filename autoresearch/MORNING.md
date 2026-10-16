# Morning summary (auto-refreshed)

_Updated: 2026-10-16T02:29:14.837117+00:00_

## Baseline vs best (DEV)
| | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| Baseline | 0.5878 | 0.828 | 0.855 | 0.367 |
| Best | 0.7019 | 0.910 | 0.877 | 0.491 |

Best change path (latest keep): `min_score 0.4379->0.4359; w_name 0.7415->0.7258; soft_vendor->True; vendor_jaccard_min 0.6364->0.6079; expand+coll=collection; alias+verizon media dsp`

## Latest held-out adversarial checkpoint
| checkpoint_exp | composite | match_recall | error_recall | flag_precision |
|---|---|---|---|---|
| 60 | 0.6597 | 0.762 | 0.810 | 0.500 |

## Top changes kept
1. exp 2: min_score 0.4500->0.4379; w_name 0.7000->0.7415; w_campaign 0.1500->0.2680; soft_vendor->False; vendor_jaccard_min 0.5500->0.6364; expand+srch=search; alias+msft (dev 0.5878->0.6210)
2. exp 4: expand+tko=takeover (dev 0.6210->0.6333)
3. exp 22: alias+yahoo (dev 0.6333->0.6684)
4. exp 39: alias+bing (dev 0.6684->0.6882)
5. exp 70: min_score 0.4379->0.4359; w_name 0.7415->0.7258; soft_vendor->True; vendor_jaccard_min 0.6364->0.6079; expand+coll=collection; alias+verizon media dsp (dev 0.6882->0.7019)

## Overfitting check
Last two held-out composites: 0.6597 → 0.6597 (DEV best 0.7019).
No clear overfitting signal at last checkpoint.

## How to read this
- DEV is the selection signal (hard DEV split: generate/dev_hard.py, seeds 424201-424205).
- Held-out adversarial is scored at checkpoints only and must not guide keeps.
- If DEV rises while held-out falls → see `ALERT_OVERFIT`.
