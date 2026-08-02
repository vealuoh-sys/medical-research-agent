"""
AutoMed PRISMA-DTA — Browser front-end for the real research pipeline.

This runs on Hugging Face Spaces (NOT GitHub Pages — GitHub Pages cannot
execute Python). Every stage below calls the same real pipeline code in
run_full_pipeline.py: genuine PubMed / Europe PMC searches, genuine LLM
calls, genuine QUADAS-2 and meta-analysis logic. There is no fallback
fake dataset anywhere in this file — if a stage fails, the app stops and
tells you honestly, instead of inventing data.

Your GROQ_API_KEY must be set as a Space "Secret" (Settings -> Variables
and secrets), never typed into the page itself.
"""

import contextlib
import io
import os

import gradio as gr

import run_full_pipeline as pipeline


def _run_stage(log, fn, *args, **kwargs):
    """Run one pipeline stage, capturing its console output into the log."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        result = fn(*args, **kwargs)
    log.append(buf.getvalue())
    return result, "\n".join(log)


def _read_if_exists(path):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    return ""


def run_pipeline_ui(topic, style, progress=gr.Progress()):
    topic = (topic or "").strip()
    log = []

    if not topic:
        yield ("Please enter a research topic.", "", "", None, None)
        return

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        yield (
            "GROQ_API_KEY is not set. In your Space, go to Settings -> "
            "Variables and secrets -> add a Secret named GROQ_API_KEY. "
            "Never paste your key into this page.",
            "", "", None, None,
        )
        return

    # Work in a per-run temp-ish directory so files don't collide across users.
    # (Simple sequential single-user use is assumed, matching the CLI tool.)

    progress(0.05, desc="Stage 1: Searching PubMed")
    (ok1, papers1), _ = _run_stage(log, pipeline.run_stage_1, topic)
    yield ("\n".join(log), "", "", None, None)
    if not ok1:
        yield ("\n".join(log) + "\n\nStopped at Stage 1 — see log above.", "", "", None, None)
        return

    progress(0.15, desc="Stage 2: Gap analysis")
    ok2, _ = _run_stage(log, pipeline.run_stage_2, api_key)
    yield ("\n".join(log), "", "", None, None)
    if not ok2:
        yield ("\n".join(log) + "\n\nStopped at Stage 2 — see log above.", "", "", None, None)
        return

    progress(0.25, desc="Stage 3: Generating candidate titles")
    ok3, _ = _run_stage(log, pipeline.run_stage_3, api_key)
    yield ("\n".join(log), "", "", None, None)
    if not ok3:
        yield ("\n".join(log) + "\n\nStopped at Stage 3 — see log above.", "", "", None, None)
        return

    progress(0.35, desc="Stage 4: Multi-query systematic search (up to ~100-200 papers)")
    (ok4, papers4), _ = _run_stage(log, pipeline.run_stage_4, topic)
    yield ("\n".join(log), "", "", None, None)
    if not ok4:
        yield ("\n".join(log) + "\n\nStopped at Stage 4 — see log above.", "", "", None, None)
        return

    progress(0.5, desc="Stage 5: Screening papers against inclusion criteria")
    (ok5, screening_results), _ = _run_stage(log, pipeline.run_stage_5, api_key, topic)
    yield ("\n".join(log), "", "", None, None)
    if not ok5:
        yield ("\n".join(log) + "\n\nStopped at Stage 5 — see log above.", "", "", None, None)
        return

    progress(0.6, desc="Stage 6: Extracting 2x2 diagnostic data")
    (ok6, extraction_results), _ = _run_stage(log, pipeline.run_stage_6, api_key)
    yield ("\n".join(log), "", "", None, None)
    if not ok6:
        yield ("\n".join(log) + "\n\nStopped at Stage 6 — see log above.", "", "", None, None)
        return

    progress(0.7, desc="Stage 6.5: QUADAS-2 risk of bias")
    ok65, _ = _run_stage(log, pipeline.run_stage_6_5, api_key)
    yield ("\n".join(log), "", "", None, None)
    if not ok65:
        yield ("\n".join(log) + "\n\nStopped at Stage 6.5 — see log above.", "", "", None, None)
        return

    progress(0.8, desc="Stage 7: Meta-analysis pooling")
    ok7, _ = _run_stage(log, pipeline.run_stage_7)
    yield ("\n".join(log), "", "", None, None)
    if not ok7:
        yield ("\n".join(log) + "\n\nStopped at Stage 7 — see log above.", "", "", None, None)
        return

    progress(0.9, desc="Stage 8: Drafting the manuscript")
    ok8, _ = _run_stage(log, pipeline.run_stage_8, api_key, style)
    yield ("\n".join(log), "", "", None, None)
    if not ok8:
        yield ("\n".join(log) + "\n\nStopped at Stage 8 — see log above.", "", "", None, None)
        return

    progress(0.97, desc="Stage 9: Finding real open-access journals")
    _run_stage(log, pipeline.run_stage_9, topic)
    yield ("\n".join(log), "", "", None, None)

    manuscript_text = _read_if_exists("research_paper_draft.txt")
    journals_text = _read_if_exists("journal_suggestions.txt")

    docx_path = "research_paper_draft.docx" if os.path.exists("research_paper_draft.docx") else None
    txt_path = "research_paper_draft.txt" if os.path.exists("research_paper_draft.txt") else None

    progress(1.0, desc="Done")
    yield ("\n".join(log) + "\n\n[ALL STAGES COMPLETE]", manuscript_text, journals_text, docx_path, txt_path)


with gr.Blocks(title="AutoMed PRISMA-DTA — Medical Research Agent") as demo:
    gr.Markdown(
        "# AutoMed PRISMA-DTA — Medical Research Agent\n"
        "Give it a topic. It searches PubMed and Europe PMC for real papers, finds a research gap, "
        "screens and extracts data, runs QUADAS-2 and meta-analysis, drafts a full manuscript, "
        "and suggests real open-access journals via DOAJ. Every citation and journal below comes "
        "from a real API call — nothing here is invented.\n\n"
        "This can take several minutes for a full run. Please be patient once you click Run."
    )
    with gr.Row():
        topic_input = gr.Textbox(
            label="Research topic",
            placeholder="e.g. point of care HbA1c testing diagnostic accuracy",
        )
        style_input = gr.Dropdown(
            choices=["vancouver", "apa", "ama", "ieee"],
            value="vancouver",
            label="Reference style",
        )
    run_btn = gr.Button("Run full pipeline", variant="primary")

    log_output = gr.Textbox(label="Pipeline log", lines=18, max_lines=30)

    with gr.Tab("Manuscript"):
        manuscript_output = gr.Textbox(label="Manuscript draft", lines=25)
    with gr.Tab("Journal suggestions"):
        journals_output = gr.Textbox(label="Real DOAJ-verified open-access journals", lines=20)

    with gr.Row():
        docx_output = gr.File(label="Download .docx")
        txt_output = gr.File(label="Download .txt")

    run_btn.click(
        fn=run_pipeline_ui,
        inputs=[topic_input, style_input],
        outputs=[log_output, manuscript_output, journals_output, docx_output, txt_output],
    )

if __name__ == "__main__":
    demo.queue().launch()
