"""
AutoMed PRISMA-DTA — Streamlit browser front-end for the real research pipeline.

Deployed on Streamlit Community Cloud (free, connects directly to GitHub —
NOT GitHub Pages, which cannot run Python).

Every stage below calls the same real pipeline code in run_full_pipeline.py:
genuine PubMed / Europe PMC searches, genuine LLM calls, genuine QUADAS-2 and
meta-analysis logic. There is no fallback fake dataset anywhere in this file —
if a stage fails, the app stops and says so honestly, instead of inventing data.

Your GROQ_API_KEY must be set as a Streamlit "Secret"
(App settings -> Secrets), never typed into the page itself.
"""

import contextlib
import io
import os

import streamlit as st

import run_full_pipeline as pipeline

st.set_page_config(page_title="AutoMed PRISMA-DTA", layout="wide")


def _run_stage(log_placeholder, log_lines, fn, *args, **kwargs):
    """Run one pipeline stage, capturing its console output into the log."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args, **kwargs)
    log_lines.append(buf.getvalue())
    log_placeholder.text_area("Pipeline log", "\n".join(log_lines), height=350)
    return result


def _read_if_exists(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


st.title("AutoMed PRISMA-DTA — Medical Research Agent")
st.write(
    "Give it a topic. It searches PubMed and Europe PMC for real papers, finds a research gap, "
    "screens and extracts data, runs QUADAS-2 and meta-analysis, drafts a full manuscript, "
    "and suggests real open-access journals via DOAJ. Every citation and journal below comes "
    "from a real API call — nothing here is invented."
)
st.caption("This can take several minutes for a full run. Please be patient once you click Run.")

col1, col2 = st.columns([3, 1])
with col1:
    topic = st.text_input(
        "Research topic",
        placeholder="e.g. point of care HbA1c testing diagnostic accuracy",
    )
with col2:
    style = st.selectbox("Reference style", ["vancouver", "apa", "ama", "ieee"])

run_clicked = st.button("Run full pipeline", type="primary")

log_placeholder = st.empty()
progress_bar = st.progress(0)

if run_clicked:
    topic = (topic or "").strip()
    log_lines = []

    if not topic:
        st.error("Please enter a research topic.")
        st.stop()

    # API keys are now OPTIONAL. The analysis stages run on deterministic,
    # zero-cost, zero-rate-limit Python (see no_api_engine.py) — nothing
    # below requires a Groq or Gemini key to complete successfully.
    api_key = os.environ.get("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY", None)

    # Optional fallback provider: if GEMINI_API_KEY is set as a Streamlit secret,
    # expose it as an environment variable (kept for backward compatibility;
    # currently unused by the default zero-API pipeline).
    gemini_key = os.environ.get("GEMINI_API_KEY") or st.secrets.get("GEMINI_API_KEY", None)
    if gemini_key and not os.environ.get("GEMINI_API_KEY"):
        os.environ["GEMINI_API_KEY"] = gemini_key

    stages = [
        (0.05, "Stage 1: Searching PubMed", pipeline.run_stage_1, (topic,)),
        (0.15, "Stage 2: Gap analysis", pipeline.run_stage_2, (api_key, topic)),
        (0.25, "Stage 3: Generating candidate titles", pipeline.run_stage_3, (api_key, topic)),
        (0.35, "Stage 4: Multi-query systematic search (up to ~100-200 papers)", pipeline.run_stage_4, (topic,)),
        (0.4, "Stage 4.5: Grey literature (trial registry + recent preprints)", pipeline.run_stage_4_5, (topic,)),
        (0.5, "Stage 5: Screening papers against inclusion criteria", pipeline.run_stage_5, (api_key, topic)),
        (0.6, "Stage 6: Extracting 2x2 diagnostic data", pipeline.run_stage_6, (api_key,)),
        (0.7, "Stage 6.5: QUADAS-2 risk of bias", pipeline.run_stage_6_5, (api_key,)),
        (0.8, "Stage 7: Meta-analysis pooling", pipeline.run_stage_7, ()),
        (0.9, "Stage 8: Drafting the manuscript", pipeline.run_stage_8, (api_key, style, topic)),
    ]

    stopped = False
    for pct, desc, fn, args in stages:
        progress_bar.progress(pct, text=desc)
        result = _run_stage(log_placeholder, log_lines, fn, *args)
        ok = result[0] if isinstance(result, tuple) else result
        if not ok:
            st.error(f"Stopped at: {desc} — see the log above.")
            stopped = True
            break

    if not stopped:
        progress_bar.progress(0.97, text="Stage 9: Finding real open-access journals")
        _run_stage(log_placeholder, log_lines, pipeline.run_stage_9, topic)
        progress_bar.progress(1.0, text="Done")

        manuscript_text = _read_if_exists("research_paper_draft.txt")
        journals_text = _read_if_exists("journal_suggestions.txt")
        trials_text = _read_if_exists("clinical_trials_registry.txt")
        preprints_text = _read_if_exists("recent_preprints.txt")

        st.success("Pipeline complete.")

        tab1, tab2, tab3 = st.tabs(["Manuscript", "Journal suggestions", "Grey literature"])
        with tab1:
            st.text_area("Manuscript draft", manuscript_text, height=500)
        with tab2:
            st.text_area("Real DOAJ-verified open-access journals", journals_text, height=400)
        with tab3:
            st.caption("Supplementary sources — not included in screening, extraction, or pooling.")
            st.text_area("Clinical trial registrations (ClinicalTrials.gov)", trials_text, height=250)
            st.text_area("Recent preprints, last 180 days only (bioRxiv/medRxiv)", preprints_text, height=250)

        dl_col1, dl_col2 = st.columns(2)
        if os.path.exists("research_paper_draft.docx"):
            with open("research_paper_draft.docx", "rb") as f:
                dl_col1.download_button(
                    "Download .docx", f, file_name="research_paper_draft.docx"
                )
        if os.path.exists("research_paper_draft.txt"):
            with open("research_paper_draft.txt", "rb") as f:
                dl_col2.download_button(
                    "Download .txt", f, file_name="research_paper_draft.txt"
                )
