# PROJECT: AI Media Reconciliation prototype

**Goal:** Demo-ready prototype for Gainshare internal teams (target Thu Oct 22, 2026) to test demand for
AI media reconciliation (IOs vs invoices vs delivery reports). Synthetic data only.

**Repo:** https://github.com/alexmarsh92/media-reconciliation

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
| GitHub repo create + push | Done |
| PR for review | In progress |
