#!/usr/bin/env bash
# Fixed eval command — prints ONE composite float on the hard DEV split (dev_hard, seeds 424201-424205).
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m media_recon.eval.composite
