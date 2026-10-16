# AI Media Reconciliation (prototype)

Check that what you **bought** (insertion orders / media plans), what was **delivered** (Meta, Google Ads,
DSP and publisher reports) and what you're **billed** (vendor invoice PDFs) agree. Find the money that doesn't.

> Synthetic data only. No real client data is used or included.

## The problem
Mid-size agencies and advertisers reconcile media every month by hand: open the IO, the invoice PDF and the
platform export, retype the lines into a spreadsheet, tie them together, then chase differences. It's slow,
it's done by expensive people, and errors slip through: overbilling, underdelivery nobody claims back,
rates that don't match the contract, invoices that never arrive (so accruals are wrong), unclaimed makegoods,
and invoices in the wrong currency or period.

## What it does
1. **Reads** the three sources: IO/media plan (XLSX), invoices (PDF), delivery reports (Meta / Google Ads /
   DSP CSV exports and publisher PDFs) into one common line-item format: vendor, campaign, flight dates,
   placement, contracted units/rate/cost, delivered impressions/clicks/spend, invoiced amount.
2. **Matches** each invoice line and delivery line to its contracted IO line, even when names differ
   (`Feed Prospecting Mobile` vs `FEED - PROSP - MOB` vs `spring_launch_feed_prospecting_mobile`).
   Every match gets a **confidence score** and a **citation** (IO cell, invoice page/line, report row).
3. **Flags exceptions**: overbilling, underdelivery, rate mismatch, missing invoice, makegoods,
   currency mismatch, date mismatch, plus invoice/delivery lines with no contract.
4. **Outputs**: exception list (CSV + XLSX), accruals file (earned vs invoiced per line), and a one-page
   HTML summary showing **dollars at risk**.

Extraction is pluggable: a deterministic offline parser is the default (no keys, no cost). An optional LLM
plugin can read invoices through any OpenAI-compatible endpoint (for example a free local Ollama model);
if it's not configured or fails, it falls back to the offline parser automatically.

## Demo walkthrough
```bash
cd media-reconciliation
python -m venv .venv && source .venv/bin/activate
pip install -e ".[demo,dev]"          # or: pip install -r requirements.txt && pip install -e .

media-recon generate                  # synthetic month -> data/synthetic (6 vendors, 84 source lines, planted errors)
media-recon run                       # -> data/output/exceptions.csv|xlsx, accruals.csv, summary.html
media-recon eval                      # scores against the planted answers
streamlit run app.py                  # demo UI at http://localhost:8501
pytest -q
```
(`python -m media_recon ...` works the same as `media-recon ...`.)

In the UI: pick a seed, optionally turn up "real-world messiness" (typos and dropped words in names), click
**Generate synthetic month**, then walk through the headline numbers → Exceptions (filter by type, each with
its source citation) → Matches (with confidence) → Accruals → One-page summary, and download the files.

Example `media-recon run` on the default month (seed 7):
| Dollars at risk | Overbilled | Undelivered value | Unverified billing | Accrual needed | Exceptions |
|---|---|---|---|---|---|
| $228,580 | $51,648 | $44,845 | $132,087 | $165,524 | 22 on 28 IO lines |

Optional LLM extraction (free/local only):
```bash
export MEDIA_RECON_LLM_URL=http://localhost:11434/v1/chat/completions   # e.g. Ollama
export MEDIA_RECON_LLM_MODEL=llama3.1
media-recon run --llm
```

## Evaluation results
`media-recon eval` generates 5 synthetic months (seeds 1–5; 84 source lines and 22 planted errors each,
110 planted errors total), runs the full pipeline and compares with the known answers.

| Metric | Clean names | Messy names (noise 0.3) | Very messy (noise 0.6) |
|---|---|---|---|
| Extraction field accuracy | 100.0% | 100.0% | 100.0% |
| Match precision / recall | 100.0% / 100.0% | 100.0% / 97.0% | 99.5% / 82.6% |
| Error-detection recall | 100.0% (110/110) | 96.4% | 81.8% |
| Error-detection precision | 100.0% | 93.2% | 65.4% |

Recall by error type, clean: overbilling 30/30, underdelivery 15/15, rate mismatch 15/15, missing invoice
15/15, makegood 15/15, currency 10/10, date 10/10. As names get messier, the misses are lines the tool
couldn't confidently match. They show up as "unmatched" for a person to review instead of being silently
mismatched (match precision stays ≥99.5%).

How to read this: extraction is 100% because the offline parser was written for these file layouts. That
proves the pipeline works end to end. It does not prove the tool can read any vendor's invoice (see Limitations).

### Time saved (estimate)
Per synthetic month (28 IO lines, 84 source lines, ~22 exceptions): **manual ≈ 9.7 h vs tool ≈ 2.8 h
(~71% saved)**. At an assumed 400 IO lines/month that's **~100 hours/month**.

Assumptions (in `media_recon/eval/__init__.py`):
- Manual: 2 min to find and key each source line; 3 min to tie each IO line to its invoice and delivery
  lines; 15 min to investigate and document each exception.
- With the tool: 0.5 min to skim each match and its citation; 7 min per exception (it arrives already
  sourced and quantified); the run itself takes under 1 second.
- These are planning assumptions, not measurements. Validate them with a timed pilot.

## Limitations
- **Synthetic, known formats.** The offline parser handles the generated IO/invoice/report layouts and
  Meta / Google Ads / DSP-style column names. Real vendor PDFs vary widely, and scanned invoices need OCR
  or the LLM plugin. LLM extraction is wired up and tested with a stand-in model, but has not been
  benchmarked against a real model yet.
- One billing period, one invoice per vendor, CPM/CPC buys only (no flat fees, CPCV, tiered or
  added-value terms). No FX conversion: invoices in a different currency are flagged, not converted.
- Matching uses name similarity plus vendor, IO number and dates. Heavily renamed placements fall out as
  "unmatched" and need a person.
- Makegoods are spotted by naming (MG / makegood / bonus). They are not yet tied to the shortfall they make up for.
- Thresholds are fixed (underdelivery below 90%, overbilling tolerance 2%, rate tolerance 0.5%) and not yet adjustable in the UI.
- The summary is HTML. To get a PDF, use the browser's Print → Save as PDF.

## Why this matters for Gainshare
- **Finance / client service:** recover overbilling and close the books with accurate accruals, with every
  number traced back to its source cell or page for audit and vendor disputes.
- **Measurement / analytics:** clean, reconciled spend and delivery data per placement is the input our
  measurement work depends on. Wrong spend means wrong ROI.
- **Commercial:** a concrete, quantified hook ("we found $X at risk in your last month") for mid-size
  agencies and advertisers. It could be a lead-in service or a product.
- **Demand test:** run it on a team's synthetic or anonymized month. If people ask "can it read *our*
  invoices?", that's the signal to invest in real-format extraction.

## Project layout
```
media_recon/
  schema.py        typed records: LineItem, Match, ReconException
  generate/        synthetic IOs (XLSX), invoices (PDF), delivery (CSV/PDF) + gold.json
  extract/         deterministic parsers + optional LLM plugin
  match/           fuzzy one-to-one matching with confidence
  exceptions/      exception rules
  report/          exceptions CSV/XLSX, accruals, one-page HTML summary
  eval/            extraction / matching / detection scoring + time-saved model
  pipeline.py, cli.py
app.py             Streamlit demo
tests/             pytest
```
