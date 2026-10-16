# Archived runs
- `*_easy_dev*.bak` — saturated easy DEV (1.000), retired.
- `*_hardv1_1to1*.bak` — hard DEV, 1:1 matching only.
- `*_hardv2_grouped_overfit_exp47*.bak` — hard DEV + grouped matching, 1,117 experiments.
  Exp 47 (`min_score 0.3833->0.3231`) raised DEV 0.8364->0.8430 but dropped held-out 0.6892->0.6543;
  every later keep (exps 149/151/194/383; best DEV 0.9220) built on top of it and held-out never recovered.
  All kept changes were tunables-only (no code commits), so the reset restores the exp-9 tunables
  (`pre_exp47_tunables.json`), reproducing DEV 0.836357 / held-out 0.689189 exactly.
