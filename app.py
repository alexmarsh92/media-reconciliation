"""Streamlit demo:  streamlit run app.py"""
from pathlib import Path

import pandas as pd
import streamlit as st

from media_recon.generate.synth import generate
from media_recon.pipeline import inputs_fingerprint, run
from media_recon.report import LABELS

DATA, OUT = Path("data/synthetic"), Path("data/output")
st.set_page_config(page_title="Media Reconciliation", layout="wide")
st.title("AI Media Reconciliation — demo")
st.caption("IOs vs vendor invoices vs platform delivery. Synthetic data only; runs fully offline.")

with st.sidebar:
    st.header("1. Data")
    seed = st.number_input("Seed", 1, 999, 7)
    noise = st.slider("Real-world messiness (name typos)", 0.0, 1.0, 0.0, 0.1)
    if st.button("Generate synthetic month") or not (DATA / "gold.json").exists():
        g = generate(DATA, seed=int(seed), noise=noise)
        st.success(f"{len(g['records'])} source lines, {len(g['errors'])} planted errors")
    st.write({d: sorted(p.name for p in (DATA / d).iterdir()) for d in ("io", "invoices", "delivery")})



@st.cache_resource(show_spinner=False)
def _run_once(fingerprint: str) -> dict:
    # Rewrite outputs only when the inputs change; filter clicks reuse the cached result,
    # so reads never race a rewrite of exceptions.xlsx.
    return run(DATA, OUT)


s = _run_once(inputs_fingerprint(DATA))["summary"]
c = st.columns(5)
for col, (k, label) in zip(c, [("dollars_at_risk_usd", "Dollars at risk"), ("overbilled_usd", "Overbilled"),
                                ("undelivered_value_usd", "Undelivered value"),
                                ("unverified_billing_usd", "Unverified billing"),
                                ("unbilled_accrual_usd", "Accrual needed")]):
    col.metric(label, f"${s[k]:,.0f}")

tab1, tab2, tab3, tab4 = st.tabs(["Exceptions", "Matches", "Accruals", "One-page summary"])
with tab1:
    ex = pd.read_csv(OUT / "exceptions.csv")
    ex["type"] = ex["type"].map(lambda t: LABELS.get(t, t))
    pick = st.multiselect("Filter type", sorted(ex["type"].unique()))
    st.dataframe(ex[ex["type"].isin(pick)] if pick else ex, width="stretch", hide_index=True)
with tab2:
    st.dataframe(pd.read_excel(OUT / "exceptions.xlsx", sheet_name="Matches"), width="stretch",
                 hide_index=True)
with tab3:
    st.dataframe(pd.read_csv(OUT / "accruals.csv"), width="stretch", hide_index=True)
with tab4:
    st.html((OUT / "summary.html").read_text())

st.subheader("Downloads")
d = st.columns(4)
for col, f in zip(d, ["exceptions.csv", "exceptions.xlsx", "accruals.csv", "summary.html"]):
    col.download_button(f, (OUT / f).read_bytes(), file_name=f)
