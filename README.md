# AutoMed PRISMA-DTA — Autonomous Medical Research Agent

An end-to-end AI agent for systematic reviews: literature search, gap analysis,
title generation, screening, data extraction, QUADAS-2 risk-of-bias assessment,
diagnostic meta-analysis pooling, PRISMA manuscript drafting, and real
open-access journal suggestions (via DOAJ) — from a single topic.

---

## Two ways to run this

### 1. Browser app (Hugging Face Spaces)
`app.py` is a Gradio front-end for the pipeline. It needs a real backend to
run Python, so it's deployed on **Hugging Face Spaces**, not GitHub Pages
(GitHub Pages only serves static files and cannot execute Python).

Your `GROQ_API_KEY` is set as a Space **Secret** — it is never entered into
the page and never visible to anyone using the app.

### 2. Local command line
```bash
python run_full_pipeline.py "point of care HbA1c testing diagnostic accuracy"
python run_full_pipeline.py "your topic" --style apa   # apa | ama | ieee | vancouver
```
Requires `GROQ_API_KEY` as an environment variable or in a local `.env` file.

---

## GitHub Pages

`index.html` on GitHub Pages is documentation only — a landing page that
links to the live Hugging Face Space. It does not run the pipeline itself
and does not generate or fabricate any data. (An earlier version of this
page tried to fake pipeline output client-side with hardcoded/invented
PMIDs and authors when the browser-side API call failed silently — that
has been removed. If a stage fails now, the tool stops and says so.)

---

## Pipeline stages

1. Primary PubMed literature search
2. Gap analysis synthesis (LLM) with PMID citation audit
3. Candidate research title generation
4. Multi-query systematic search across PubMed + Europe PMC, deduplicated
5. Deterministic screening (temperature 0) with a post-screening keyword audit
6. Data extraction with a numeric-grounding audit
7. QUADAS-2 methodological risk-of-bias assessment
8. Diagnostic meta-analysis pooling (skipped and clearly flagged if fewer
   than 2 studies have complete 2x2 data — never estimated or guessed)
9. PRISMA-DTA manuscript drafting with programmatically assembled
   references (Vancouver, APA 7th, AMA 11th, or IEEE) and MS Word export
10. Journal suggestions via the DOAJ API — only real, currently-listed
    open-access journals, ranked with free-to-publish options first

## Zero-hallucination guardrails

- Stage 2 audits every cited PMID against the actual search results.
- Stage 6 grounds every extracted number against the source abstract.
- Stage 7 refuses to pool fewer than 2 studies with complete data, and
  refuses to estimate a missing disease-positive count.
- Stage 8 rejects the manuscript draft outright if the LLM writes a pooled
  result while `meta_analysis_results.txt` says pooling wasn't possible.
- Stage 9 only returns journals DOAJ has already editorially vetted —
  never a generated or guessed journal name.

## Deploying the browser app

1. Create a free account at huggingface.co.
2. Create a new **Space** with SDK: **Gradio**.
3. Upload every file in this repo except `index.html` (that stays on
   GitHub Pages) to the Space.
4. In the Space's **Settings -> Variables and secrets**, add a secret
   named `GROQ_API_KEY` with your free Groq API key.
5. The Space builds automatically and gives you a live URL — put that URL
   into `index.html`'s "Open the live app" link.
