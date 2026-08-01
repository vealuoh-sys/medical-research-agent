# AutoMed PRISMA-DTA — Autonomous Medical Research Agent

An end-to-end automated AI agent for systematic reviews, QUADAS-2 methodological risk of bias assessment, diagnostic meta-analysis pooling, and PRISMA manuscript generation with MS Word (.docx) export.

---

## 🌐 Deploy to GitHub Pages (2 Easy Steps)

1. **Push to GitHub**:
   ```bash
   git add .
   git commit -m "Deploy AutoMed PRISMA-DTA Web Agent to GitHub Pages"
   git push origin main
   ```

2. **Enable GitHub Pages**:
   - Go to your repository settings on GitHub: **Settings** -> **Pages**.
   - Under **Source**, select `Deploy from a branch`.
   - Select `main` branch and `/ (root)` folder, then click **Save**.
   - Your web app will be live at `https://<your-username>.github.io/<repository-name>/`!

---

## 🚀 Features

- **Multi-Database Search**: Queries PubMed & Europe PMC REST APIs with automatic deduplication.
- **QUADAS-2 Risk of Bias Assessment**: Evaluates included studies across 4 methodological domains (*Patient Selection, Index Test, Reference Standard, Flow & Timing*).
- **Zero-Hallucination Guardrails**: Enforces empirical 2x2 data ground-truth verification and rejects aggregate claims if pooling data is insufficient.
- **Reference Citation Style Switcher**: Toggle between **Vancouver**, **APA 7th**, **AMA 11th**, and **IEEE** styles live in the browser or via CLI (`--style apa`).
- **MS Word (.docx) & Plain Text (.txt) Export**: Generates styled Word documents with embedded QUADAS-2 tables.

---

## 💻 Local CLI Execution

```bash
# Run full pipeline with default Vancouver references
uv run python run_full_pipeline.py "point of care HbA1c testing diagnostic accuracy"

# Run full pipeline with APA reference styling
uv run python run_full_pipeline.py "point of care HbA1c testing diagnostic accuracy" --style apa

# Generate manuscript draft directly
uv run python draft_paper.py --style ieee
```
