# Jump plan: media-reconciliation (2026-10-16)

## Why tuning stalled
7,039 tunables-only experiments moved DEV 0.836 -> 0.922 while validation (0.723) and the old
held-out (0.689) did not move at all. The error analysis below shows why: the dominant failure is
**vendor identity**, which no threshold can fix. Invoice vendor strings ("Outbrian", "Twitter",
"Samsung TV Plus", "Amazon Ads", "TheTradeDsk") never resolve to the IO vendor, so whole invoices go
unmatched. That produces unmatched_invoice false flags *and* false missing_invoice flags on the IO.
The loop could only add per-vendor aliases from the DEV vocabulary (no transfer). Exps 2835/4500 hit
0.789 on held-out precisely because they lowered `vendor_jaccard_min`. They were the right direction,
but DEV-selection rejected them.

Also found: a normalization bug. `norm_vendor("Amazon Advertising")` strips "advertising" to
"amazon", while the alias "amazon ads" maps to "amazon advertising", so even known aliases missed.

## Error analysis (baseline tunables, before any change; `python tools/error_analysis.py validation adversarial`)
Lift = estimated composite gain if that category alone were fixed (counterfactual on the metric).

**Validation** (4 seeds, composite 0.7231; MR 0.879, ER 0.893, flag precision 0.529)

| kind | category | count | est. lift |
|---|---|---:|---:|
| match miss | vendor name variant (typo/rebrand/suffix) | 18 | +0.021 |
| false flag | unmatched_invoice, caused by the match miss above | 18 | +0.077 |
| false flag | missing_invoice (IO's invoice went unmatched) | 16 | +0.067 |
| match miss | wrong IO, near-duplicate placement (greedy swap) | 4 | +0.005 |
| missed error | overbilling (match miss upstream) | 3 | +0.020 |
| missed error | date_mismatch / rate_mismatch (match miss upstream) | 1 / 1 | +0.004 each |
| false flag | overbilling / underdelivery / rate / currency rule thresholds | 2 / 1 / 1 / 1 | ≤ +0.004 |
| — | allocation splits, date/timezone parse, currency, duplicates, fee filter | 0 | 0 |

**Old held-out (data/adversarial, now diagnostic only)** (composite 0.6892; MR 0.810, ER 0.810, FP 0.531)

| kind | category | count | est. lift |
|---|---|---:|---:|
| match miss | vendor name variant | 8 | +0.039 |
| false flag | unmatched_invoice, caused by the vendor miss | 8 | +0.084 |
| false flag | missing_invoice, caused by the vendor miss | 7 | +0.072 |
| missed error | date_mismatch (match miss upstream) | 2 | +0.037 |
| missed error | overbilling / currency_mismatch (upstream) | 1 / 1 | +0.019 each |

The vendor rows share one root cause, so the fix's combined lift is far above the per-row sum.
Validation and diagnostic both predicted about +0.2 to +0.3.

## Split hygiene
- `data/adversarial` was opened for this analysis, so it is **contaminated**. It is now a dev-like
  *diagnostic* and the loop's non-regression gate.
- **New sealed held-out v2**: `data/sealed_holdout/` (seeds 555011-555013, generator
  `media_recon/generate/sealed.py`). It uses a new author style: a disjoint vendor universe built
  from the failure modes (rebrands with zero shared characters, legal-suffix noise, typos), canonical
  names almost never on invoices, dotted/slashed abbreviations, a new OCR map, and more merges,
  splits and cross-period billing. It was generated and its baseline scored **before** the code
  changes. Nobody inspected its misses.
  SHA256 (tree, excl. out/): `5a83d6c07bcea9ef17698316af44633a5bcb2260fc7271b7bc255a69a62c3ce0`.
  `sealed_eval` asserts the hash. Tests assert the loop reads it only in its checkpoint function.

## Plan (ordered by expected lift / effort)
| # | item | expected lift (val) | effort | status |
|---|---|---|---|---|
| 1 | **Vendor entity resolution onto the IO vendor universe**: IO number, then alias/legal-suffix/char-trigram affinity, then a document-level placement-similarity vote (handles rebrands); ambiguous names stay unresolved | +0.15 to +0.25 | 0.5 d | **done**: val 0.723 -> 0.957 |
| 2 | **Optimal (Hungarian) 1:1 assignment** with a regret guard, so split and monthly lines still join in pass 2 | +0.01 to +0.02 | 0.5 d | **done**: val 0.957 -> 0.974 (alone on baseline: +0.013) |
| 3 | **Objective redesign**: select on mean(DEV, validation); gate = diagnostic adversarial must not drop; sealed v2 at checkpoints only; per-vendor alias proposals disabled (MAX_ALIAS_ADDS=0); loop tunes the resolver knobs instead | prevents the 7k-exp overfit pattern | 0.5 d | **done** |
| 4 | Messier DEV/train generator: rebrands, near-zero canonical names on invoices, duplicate invoices, timezone-shifted delivery dates | unknown on val (already 0.97); targets sealed gap | 1 d | next |
| 5 | Local embedding vendor/placement matcher (e.g. sentence-transformers MiniLM on CPU, free), behind a flag with trigram fallback | +0.0 to +0.02 | 1 d | next |
| 6 | Many-to-many allocation solver (subset-sum over invoice lines vs IO earned values within tolerance) | small on current sets; large on real multi-IO invoices | 1-2 d | later |
| 7 | LLM tie-break for low-margin assignments, flag off by default, offline fallback = current deterministic | unverified | 1 d | later |
| 8 | Duplicate-invoice exception type (new gold type) | new capability | 0.5 d | later |

## Results (baseline tunables throughout; no threshold changes)
| split | before | after items 1+2 |
|---|---:|---:|
| DEV (dev_hard) | 0.8364 | 0.9379 |
| Validation | 0.7231 | **0.9739** (+0.251) |
| Old held-out (diagnostic, contaminated) | 0.6892 | 1.0000 |
| **Sealed held-out v2** | **0.2394** | **0.8521** (+0.613) |

The sealed set is harder than validation (0.85 vs 0.97). The gap is unexplained, by design: we
do not inspect it. Items 4-5 are the hypotheses. Synthetic data only. All numbers come from local
runs on 2026-10-16.
