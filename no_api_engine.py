"""
no_api_engine.py — Zero-dependency, zero-cost, zero-rate-limit analysis engine.

This replaces every LLM call in the pipeline (Groq/Gemini) with deterministic,
rule-based Python: word-frequency analysis, keyword/PICO matching, regex
extraction of clinical numbers, and template-based manuscript assembly.

Why: tools like Rayyan and ASReview (real systematic-review software used by
researchers) do NOT call a generative AI API for screening or extraction —
they use classical NLP/statistics. This module follows that same approach.
Nothing here calls the network. Nothing here can be rate-limited. Nothing
here costs money. It also can never hallucinate a number, because every
number it reports is either copied verbatim from a paper's own abstract via
regex, or is a plain count/frequency computed from the paper set itself.

Trade-off, stated honestly: this cannot "understand" nuance the way an LLM
can. Anything it can't confidently extract is marked NOT REPORTED or NEEDS
MANUAL REVIEW rather than guessed — the same zero-hallucination rule the
rest of this pipeline already follows.
"""

import re
from collections import Counter

STOPWORDS = set("""
a an the of and or in on at to for with by from as is are was were be been
being this that these those it its into over under between among within
across per via using use used based study studies patients patient results
result data method methods conclusion conclusions background objective
objectives aim aims we our their than also may can could would should
not no yes vs versus each all some most more less than however therefore
thus which who whom whose what when where how why do does did done
""".split())

DIAGNOSTIC_KEYWORDS = [
    "accuracy", "sensitivity", "specificity", "auc", "roc", "cutoff",
    "cut-off", "performance", "meter", "device", "sensor", "point-of-care",
    "capillary", "diagnostic", "screening", "predictive value", "likelihood ratio"
]


# ==============================================================================
# SECTION 1: Keyword / frequency utilities (used across every stage below)
# ==============================================================================
def _tokenize(text):
    words = re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower())
    return [w for w in words if w not in STOPWORDS]


def _corpus_text(papers):
    return " ".join((p.get("title", "") + " " + p.get("abstract", "")) for p in papers)


def top_keywords(papers, top_n=15):
    counts = Counter(_tokenize(_corpus_text(papers)))
    return counts.most_common(top_n)


def _bigrams(text):
    words = _tokenize(text)
    return [f"{a} {b}" for a, b in zip(words, words[1:])]


def top_bigrams(papers, top_n=10):
    all_bigrams = []
    for p in papers:
        all_bigrams.extend(_bigrams(p.get("title", "") + " " + p.get("abstract", "")))
    return Counter(all_bigrams).most_common(top_n)


# ==============================================================================
# SECTION 2: Gap analysis (replaces Stage 2 LLM call)
# ==============================================================================
def generate_gap_analysis(papers, topic):
    """
    Identifies dominant themes (high-frequency terms across many papers) and
    candidate gaps (terms that appear in only one or two papers — i.e. under-
    studied angles relative to the rest of the set). Every PMID cited is
    real, taken directly from the paper list, never invented.
    """
    kw = top_keywords(papers, top_n=20)
    bg = top_bigrams(papers, top_n=10)

    # Per-term document frequency (how many distinct papers mention it)
    doc_freq = Counter()
    for p in papers:
        terms = set(_tokenize(p.get("title", "") + " " + p.get("abstract", "")))
        for t in terms:
            doc_freq[t] += 1

    n_papers = len(papers)
    dominant = [t for t, c in doc_freq.most_common(30) if c >= max(2, n_papers // 3)][:8]
    under_studied = [t for t, c in doc_freq.items() if c == 1 and len(t) > 4]
    under_studied = sorted(under_studied)[:8]

    lines = []
    lines.append(f"LITERATURE GAP ANALYSIS: {topic}")
    lines.append("=" * 70)
    lines.append(f"Papers analyzed: {n_papers}")
    lines.append("")
    lines.append("DOMINANT THEMES (appear across multiple papers):")
    for t in dominant:
        citing = [p["pmid"] for p in papers if t in _tokenize(p.get("title", "") + " " + p.get("abstract", ""))][:4]
        lines.append(f"  - {t}  (PMIDs: {', '.join(citing)})")
    lines.append("")
    lines.append("MOST FREQUENT KEY TERMS:")
    for term, count in kw[:15]:
        lines.append(f"  - {term}: {count} mentions")
    lines.append("")
    lines.append("RECURRING PHRASES:")
    for phrase, count in bg[:8]:
        lines.append(f"  - \"{phrase}\": {count} occurrences")
    lines.append("")
    lines.append("CANDIDATE RESEARCH GAPS (terms mentioned in only one retrieved paper —")
    lines.append("possible under-studied angles; verify by reading the source paper before relying on this):")
    for t in under_studied:
        citing = [p["pmid"] for p in papers if t in _tokenize(p.get("title", "") + " " + p.get("abstract", ""))][:1]
        lines.append(f"  - {t}  (PMID: {citing[0] if citing else 'N/A'})")
    lines.append("")
    lines.append("NOTE: This analysis is generated by deterministic keyword-frequency")
    lines.append("analysis, not a generative AI model. Every term and PMID above is")
    lines.append("computed directly from results.json — nothing is inferred or invented.")

    return "\n".join(lines)


# ==============================================================================
# SECTION 3: Title generation (replaces Stage 3 LLM call)
# ==============================================================================
DESIGN_TEMPLATES = [
    ("Diagnostic accuracy of {topic}: a systematic review and meta-analysis",
     "Systematic review + diagnostic meta-analysis", "Feasible solo — relies on published data only, no primary recruitment."),
    ("{topic}: a systematic review of {theme}",
     "Systematic review (narrative + quantitative synthesis)", "Feasible solo — literature-based."),
    ("Evaluating {theme} in {topic}: a diagnostic test accuracy review",
     "Diagnostic test accuracy (DTA) systematic review", "Feasible solo if >=2 studies report full 2x2 data."),
    ("Comparative performance of {topic} across clinical settings: a meta-analytic review",
     "Meta-analysis of published diagnostic accuracy studies", "Feasible solo — depends on data availability in Stage 7."),
    ("Current evidence and research gaps in {topic}: a scoping review",
     "Scoping review", "Feasible solo — lowest data burden, good fallback if meta-analysis is underpowered."),
]


def generate_titles(gap_text, topic, papers):
    kw = top_keywords(papers, top_n=6)
    theme = kw[0][0] if kw else "clinical performance"

    lines = [f"CANDIDATE RESEARCH TITLES: {topic}", "=" * 70, ""]
    for i, (template, design, feasibility) in enumerate(DESIGN_TEMPLATES, 1):
        title = template.format(topic=topic, theme=theme)
        lines.append(f"{i}. {title}")
        lines.append(f"   Study design: {design}")
        lines.append(f"   Solo-researcher feasibility: {feasibility}")
        lines.append("")
    lines.append("NOTE: Generated from template + keyword-frequency data, not a")
    lines.append("generative AI model. Pick the option that matches what Stage 7's")
    lines.append("meta-analysis actually finds enough data to support.")
    return "\n".join(lines)


# ==============================================================================
# SECTION 4: Screening (replaces Stage 5 LLM call)
# ==============================================================================
def rule_based_screen(papers, topic):
    """
    INCLUDE/EXCLUDE/NEEDS MANUAL REVIEW using the same diagnostic-keyword
    logic the pipeline already used as a post-hoc *audit* on top of the LLM —
    promoted here to be the primary decision method. Transparent, reproducible,
    and re-runs identically every time (unlike a rate-limited API call).
    """
    topic_terms = set(_tokenize(topic))
    results = []
    for p in papers:
        text = (p.get("title", "") + " " + p.get("abstract", "")).lower()
        diag_matches = [kw for kw in DIAGNOSTIC_KEYWORDS if kw in text]
        topic_matches = [t for t in topic_terms if t in text]

        if len(diag_matches) >= 3 and len(topic_matches) >= 1:
            decision, reason = "INCLUDE", f"Matched {len(diag_matches)} diagnostic-accuracy terms and {len(topic_matches)} topic terms."
        elif len(diag_matches) >= 1 or len(topic_matches) >= 1:
            decision, reason = "NEEDS MANUAL REVIEW", f"Partial match only ({len(diag_matches)} diagnostic terms, {len(topic_matches)} topic terms) — read abstract to confirm."
        else:
            decision, reason = "EXCLUDE", "No diagnostic-accuracy or topic keyword matches found in title/abstract."

        results.append({
            "pmid": str(p.get("pmid", "")).strip(),
            "title": p.get("title", "No title"),
            "decision": decision,
            "reason": reason,
        })
    return results


# ==============================================================================
# SECTION 5: Data extraction (replaces Stage 6 LLM call)
# ==============================================================================
_NUM = r"(\d+(?:\.\d+)?)"

PATTERNS = {
    "sample_size": [
        rf"\bn\s*=\s*{_NUM}",
        rf"{_NUM}\s+(?:patients|participants|subjects|children|infants|cases)\b",
    ],
    "sensitivity": [
        rf"sensitivit(?:y|ies)[^.\d]{{0,30}}{_NUM}\s*%",
        rf"{_NUM}\s*%[^.]{{0,15}}sensitivit",
    ],
    "specificity": [
        rf"specificit(?:y|ies)[^.\d]{{0,30}}{_NUM}\s*%",
        rf"{_NUM}\s*%[^.]{{0,15}}specificit",
    ],
    "cutoff_value": [
        rf"cut[\s\-]?off[^.\d]{{0,20}}{_NUM}",
        rf"threshold[^.\d]{{0,20}}{_NUM}",
    ],
}

REFERENCE_STANDARD_TERMS = ["gold standard", "reference standard", "confirmed by", "verified by", "biopsy", "culture", "pcr", "arterial blood gas", "venous blood gas"]


def regex_extract_row(paper):
    text = (paper.get("title", "") + " " + paper.get("abstract", ""))

    def find_first(patterns):
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1)
        return "NOT REPORTED"

    ref_standard = "NOT REPORTED"
    text_lower = text.lower()
    for term in REFERENCE_STANDARD_TERMS:
        if term in text_lower:
            ref_standard = term
            break

    sens = find_first(PATTERNS["sensitivity"])
    spec = find_first(PATTERNS["specificity"])
    n = find_first(PATTERNS["sample_size"])
    cutoff = find_first(PATTERNS["cutoff_value"])

    return {
        "pmid": str(paper.get("pmid", "")).strip(),
        "sample_size": n if n == "NOT REPORTED" else n,
        "sensitivity": sens if sens == "NOT REPORTED" else f"{sens}%",
        "specificity": spec if spec == "NOT REPORTED" else f"{spec}%",
        "cutoff_value": cutoff,
        "reference_standard": ref_standard,
        "population": "Extracted via regex from abstract — verify against full text before publication.",
    }


# ==============================================================================
# SECTION 6: QUADAS-2 (replaces Stage 6.5 LLM call)
# ==============================================================================
QUADAS_DOMAIN_HINTS = {
    "Patient Selection": (["consecutive", "random sample", "cohort"], ["case-control", "convenience sample"]),
    "Index Test": (["blind", "blinded", "independent"], ["not blinded", "unblinded"]),
    "Reference Standard": (["gold standard", "confirmed by", "reference standard"], []),
    "Flow and Timing": (["all patients", "same reference standard", "appropriate interval"], ["excluded", "lost to follow"]),
}


def quadas2_rule_based(paper):
    text = (paper.get("title", "") + " " + paper.get("abstract", "")).lower()
    judgments = {}
    for domain, (low_risk_terms, high_risk_terms) in QUADAS_DOMAIN_HINTS.items():
        if any(t in text for t in high_risk_terms):
            judgments[domain] = "HIGH RISK (keyword-flagged — verify manually)"
        elif any(t in text for t in low_risk_terms):
            judgments[domain] = "LOW RISK (keyword-supported — verify manually)"
        else:
            judgments[domain] = "UNCLEAR (insufficient info in abstract — read full text)"
    return judgments


# ==============================================================================
# SECTION 7: Manuscript assembly (replaces Stage 8 LLM call)
# ==============================================================================
def draft_manuscript(topic, gap_text, titles_text, papers, screening_results,
                      extraction_results, meta_text, references_block, style="vancouver"):
    n_found = len(papers)
    n_included = sum(1 for r in screening_results if r["decision"] == "INCLUDE")
    n_excluded = sum(1 for r in screening_results if r["decision"] == "EXCLUDE")
    n_review = sum(1 for r in screening_results if r["decision"] == "NEEDS MANUAL REVIEW")

    first_title = titles_text.split("\n")[2].split(". ", 1)[-1] if len(titles_text.split("\n")) > 2 else topic

    parts = []
    parts.append(f"TITLE: {first_title}")
    parts.append("")
    parts.append("ABSTRACT")
    parts.append("-" * 70)
    parts.append(
        f"Background: {topic} is an area of active clinical research. This review "
        f"screened {n_found} records identified through PubMed and Europe PMC.\n"
        f"Methods: Following a PRISMA-DTA approach, {n_found} records were screened; "
        f"{n_included} met inclusion criteria, {n_excluded} were excluded, and "
        f"{n_review} require manual review before a final decision.\n"
        f"Results: See the pooled diagnostic accuracy results below.\n"
        f"Conclusion: See Discussion."
    )
    parts.append("")
    parts.append("INTRODUCTION")
    parts.append("-" * 70)
    parts.append(gap_text)
    parts.append("")
    parts.append("METHODS")
    parts.append("-" * 70)
    parts.append(
        "Search strategy: PubMed and Europe PMC were searched using the primary topic "
        "term plus three derived queries (diagnostic accuracy / point-of-care / "
        "systematic review variants). Records were deduplicated by PMID.\n\n"
        "Screening: Records were screened against inclusion criteria using a "
        "reproducible, deterministic keyword-matching rule (diagnostic-accuracy terms "
        "plus topic terms), not a generative model — the same screen produces the same "
        "result on every run.\n\n"
        "Data extraction: Sample size, sensitivity, specificity, cutoff value, and "
        "reference standard were extracted via pattern matching directly against each "
        "abstract's own text. Fields not explicitly stated are marked NOT REPORTED "
        "rather than estimated.\n\n"
        "Risk of bias: Assessed using QUADAS-2 domains (patient selection, index test, "
        "reference standard, flow and timing), keyword-flagged per domain and marked "
        "for manual verification.\n\n"
        "Meta-analysis: Studies with complete, explicit 2x2 diagnostic data were pooled; "
        "studies lacking an explicit disease-positive count were excluded from pooling "
        "rather than having that count estimated."
    )
    parts.append("")
    parts.append("RESULTS")
    parts.append("-" * 70)
    parts.append(f"Of {n_found} records identified, {n_included} were included, {n_excluded} excluded, "
                  f"and {n_review} flagged for manual review (see screening_results.csv for the full list "
                  f"with reasons per PMID).")
    parts.append("")
    parts.append("Extraction summary (extraction_table.csv):")
    for row in extraction_results[:20]:
        parts.append(f"  - PMID {row['pmid']}: n={row['sample_size']}, sensitivity={row['sensitivity']}, "
                      f"specificity={row['specificity']}, reference standard={row['reference_standard']}")
    parts.append("")
    parts.append(meta_text)
    parts.append("")
    parts.append("DISCUSSION")
    parts.append("-" * 70)
    parts.append(
        "This draft was assembled deterministically from the data above — it does not "
        "contain generated interpretive prose. Before submission, the author should "
        "write the Discussion manually: compare pooled results (if available) against "
        "prior literature, note the candidate research gaps listed in the Introduction, "
        "and state limitations, including that screening and extraction here used "
        "rule-based methods that should be spot-checked against full-text papers, not "
        "abstracts alone."
    )
    parts.append("")
    parts.append("REFERENCES")
    parts.append("-" * 70)
    parts.append(references_block)

    return "\n".join(parts)
