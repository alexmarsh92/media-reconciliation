# Autoresearch overnight

See `program.md` for objective and rules.

## Start
```bash
# from repo root, after commit
setsid nohup .venv/bin/python -u autoresearch/loop.py >> autoresearch/run.log 2>&1 &
echo $! > autoresearch/PID
```

## Monitor
- `results.tsv` — every experiment
- `live_best.json` / `live_updates.log` — new DEV bests only
- `MORNING.md` — baseline vs best + held-out checkpoints
- `ALERT_OVERFIT` / `ALERT_STALL` — if raised

## Fixed DEV eval (one float)
```bash
./autoresearch/eval_dev.sh
# or: python -m media_recon.eval.composite
```

Held-out (checkpoint only):
```bash
python -m media_recon eval-adversarial
```
