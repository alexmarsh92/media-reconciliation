#!/usr/bin/env bash
# Fixed eval command — prints ONE composite float on messy DEV split.
set -euo pipefail
cd "$(dirname "$0")/.."
exec .venv/bin/python -m media_recon.eval.composite
