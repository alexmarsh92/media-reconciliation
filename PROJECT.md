# PROJECT: AI Media Reconciliation prototype

**Goal:** Demo-ready prototype for Gainshare internal teams (target Thu Oct 22, 2026) to test demand for
AI media reconciliation (IOs vs invoices vs delivery reports). Synthetic data only.

**Repo:** TBD. **Pending:** create a new repo in Alex's personal GitHub account and push. GitHub auth is still in progress.
The local git repo is initialized and committed and ready to push (`git remote add origin <url> && git push -u origin main`).

## Tasks
| Task | Status |
|---|---|
| Domain model (schema.py) | Done |
| Synthetic generator: IO XLSX, invoice PDFs, Meta/Google/DSP CSV + publisher PDF, planted errors, gold.json | Done |
| Deterministic extraction (offline) | Done |
| Pluggable LLM extraction with fallback (OpenAI-compatible, free/local) | Done (not benchmarked against a live model) |
| Matching with confidence + citations | Done |
| Exception rules (overbilling, underdelivery, rate, missing invoice, makegood, currency, date) | Done |
| Outputs: exceptions CSV/XLSX, accruals, one-page HTML summary | Done |
| CLI (generate / run / eval) | Done |
| Streamlit demo | Done (`streamlit run app.py`) |
| Eval harness + time-saved model | Done |
| README with eval results | Done |
| Tests (pytest) | Done (9 passing) |
| GitHub repo create + push | **Pending (blocked on GitHub auth)** |
