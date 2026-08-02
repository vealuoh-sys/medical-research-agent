import json
import os
import sys
import time
import csv
import argparse
import export_docx

from api_client import make_post_request, get_groq_api_key as get_api_key, call_groq_api


# ==============================================================================
# SECTION 1: Load All Data Files Required for Manuscript Generation
# ==============================================================================
def load_project_data():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    files = {
        "systematic_results": os.path.join(script_dir, "systematic_results.json"),
        "screening_results": os.path.join(script_dir, "screening_results.csv"),
        "extraction_table": os.path.join(script_dir, "extraction_table.csv"),
        "meta_analysis_results": os.path.join(script_dir, "meta_analysis_results.txt"),
        "gap_analysis": os.path.join(script_dir, "gap_analysis.txt")
    }
    
    loaded_data = {}
    for key, filepath in files.items():
        if not os.path.exists(filepath):
            print(f"Error: Missing required file '{filepath}'.")
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            loaded_data[key] = f.read()
            
    # Load optional risk of bias table if available
    rob_path = os.path.join(script_dir, "risk_of_bias_table.csv")
    if os.path.exists(rob_path):
        with open(rob_path, "r", encoding="utf-8") as f:
            loaded_data["risk_of_bias"] = f.read()
    else:
        loaded_data["risk_of_bias"] = "QUADAS-2 evaluation pending."
            
    return loaded_data


# ==============================================================================
# SECTION 2: Build Detailed PRISMA Manuscript Prompt for Gemini API
# ==============================================================================
def build_manuscript_prompt(data):
    # Parse screening_results CSV into concise PRISMA flow numbers
    screening_raw = data.get('screening_results', '')
    total_screened = 0
    inc_count = 0
    exc_count = 0
    rev_count = 0
    
    for line in screening_raw.splitlines():
        if 'INCLUDE' in line.upper():
            inc_count += 1
            total_screened += 1
        elif 'EXCLUDE' in line.upper():
            exc_count += 1
            total_screened += 1
        elif 'NEEDS MANUAL REVIEW' in line.upper() or 'FLAGGED' in line.upper():
            rev_count += 1
            total_screened += 1

    screening_summary = (
        f"Total Records Screened: {total_screened}\n"
        f"Included Studies: {inc_count}\n"
        f"Excluded Studies: {exc_count}\n"
        f"Flagged for Review: {rev_count}\n"
    )

    prompt = (
        "You are an expert clinical epidemiologist and medical manuscript author. "
        "Your task is to draft a comprehensive, publication-ready systematic review manuscript "
        "following PRISMA-DTA guidelines.\n\n"
        "==================== INPUT DATA SOURCES ====================\n\n"
        "--- 1. VERIFIED DATA EXTRACTION TABLE (extraction_table.csv) ---\n"
        f"{data['extraction_table']}\n\n"
        "--- 2. META-ANALYSIS RESULTS (meta_analysis_results.txt) ---\n"
        f"{data['meta_analysis_results']}\n\n"
        "--- 3. SCREENING SUMMARY (PRISMA Flow Counts) ---\n"
        f"{screening_summary}\n\n"
        "--- 4. GAP ANALYSIS BACKGROUND (gap_analysis.txt) ---\n"
        f"{data['gap_analysis'][:3000]}\n\n"
        "--- 5. QUADAS-2 RISK OF BIAS TABLE (risk_of_bias_table.csv) ---\n"
        f"{data.get('risk_of_bias', 'N/A')}\n\n"
        "=============================================================\n\n"
        "NON-NEGOTIABLE MANUSCRIPT RULES:\n"
        "1. POOLING STATISTIC RULE:\n"
        "   Check the literal content of meta_analysis_results.txt provided above. If it contains 'INSUFFICIENT DATA FOR POOLING', "
        "   the manuscript MUST state plainly in the Results and Abstract that quantitative meta-analytic pooling was NOT possible "
        "   due to incomplete data reporting (missing 2x2 table parameters or sample sizes) across included studies. "
        "   You MUST NOT report or invent any 'pooled sensitivity', 'pooled specificity', pooled confidence intervals, "
        "   or any aggregate pooling statistics anywhere in the document.\n\n"
        "2. SINGLE STUDY REPORTING RULE:\n"
        "   NEVER present a single study's individual sensitivity or specificity value as if it were a pooled or aggregate result "
        "   across multiple studies. If discussing one study's specific numbers, explicitly name that individual study and its PMID.\n\n"
        "3. ACCURATE RUN DATA RULE:\n"
        "   The Methods section's search strategy and the Results section's study counts (number of records searched, screened, included, and extracted) "
        "   MUST be pulled directly and exclusively from the actual data in systematic_results.json, screening_results.csv, and extraction_table.csv for THIS run. "
        "   Do NOT use search queries, PMIDs, or counts from any previous run or different disease topic.\n\n"
        "MANUSCRIPT STRUCTURE AND SECTION INSTRUCTIONS:\n\n"
        "1. TITLE:\n"
        "   Create a clear, descriptive title based on the actual target topic in the provided files.\n\n"
        "2. ABSTRACT:\n"
        "   Format as a structured abstract with subheadings: Background, Methods, Results, Conclusion. "
        "   Accurately reflect whether pooling was performed or deemed impossible due to insufficient 2x2 data.\n\n"
        "3. INTRODUCTION:\n"
        "   Justify the review using background from gap_analysis.txt and clinical rationale.\n\n"
        "4. METHODS:\n"
        "   - Search Strategy & Criteria: Describe the search process and criteria based strictly on the current run data.\n"
        "   - Data Extraction & Pooling Criteria: Describe how studies were extracted and the strict criteria required for quantitative 2x2 table pooling.\n\n"
        "5. RESULTS:\n"
        "   - PRISMA Flow: Detail the exact count of studies found, screened, included, and extracted from screening_results.csv and extraction_table.csv.\n"
        "   - Synthesis: Describe the findings of the individual extracted studies from extraction_table.csv. State clearly if quantitative pooling was not possible.\n\n"
        "6. DISCUSSION & LIMITATIONS:\n"
        "   Interpret the findings, clinical utility, and limitations (including incomplete data reporting in primary literature).\n\n"
        "7. REFERENCES:\n"
        "   List ONLY actual PMIDs present in extraction_table.csv / screening_results.csv for this run. Do NOT invent or hallucinate any additional citations.\n\n"
        "STRICT WRITING STYLE & PROSE INSTRUCTIONS:\n"
        "- Write directly and plainly, as a clinician explaining empirical evidence to colleagues.\n"
        "- Do NOT use generic AI filler phrases.\n"
        "- Ensure EVERY factual claim, statistic, percentage, and number strictly matches the provided input files.\n"
    )
    return prompt


# ==============================================================================
# SECTION 3: Send Prompt to Groq API (llama-3.3-70b-versatile)
# ==============================================================================
# Uses call_groq_api imported from api_client.py.


# ==============================================================================
# SECTION 4: Save Manuscript to File
# ==============================================================================
def save_manuscript(text, filename="research_paper_draft.txt"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return True, file_path
    except IOError as e:
        print(f"Error saving manuscript: {e}")
        return False, None


# ==============================================================================
# HELPER: Build Programmatic References Section
# ==============================================================================
def build_programmatic_references(data, style="vancouver"):
    """
    Programmatically builds the References section directly from systematic_results.json
    for all PMIDs present in extraction_table.csv, preventing LLM reference hallucination.
    Supports reference styles: 'vancouver', 'apa', 'ama', 'ieee'.
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sys_path = os.path.join(script_dir, "systematic_results.json")
    
    sys_papers = []
    if os.path.exists(sys_path):
        try:
            with open(sys_path, "r", encoding="utf-8") as f:
                sys_papers = json.load(f)
        except Exception:
            pass
            
    sys_dict = {str(p.get("pmid", "")).strip(): p for p in sys_papers} if sys_papers else {}
    
    ext_csv_path = os.path.join(script_dir, "extraction_table.csv")
    included_pmids = []
    if os.path.exists(ext_csv_path):
        try:
            with open(ext_csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    pmid = row.get("pmid", "").strip()
                    if pmid and pmid not in included_pmids:
                        included_pmids.append(pmid)
        except Exception:
            pass
            
    style_key = style.lower().strip()
    ref_lines = [f"## REFERENCES ({style_key.upper()} STYLE)\n"]
    
    for idx, pmid in enumerate(included_pmids, 1):
        p = sys_dict.get(pmid, {})
        authors_list = p.get("authors", ["Author info unavailable"])
        authors_str = ", ".join(authors_list)
        title_str = p.get("title", "Title unavailable")
        journal_str = p.get("journal", "Journal unavailable")
        year_str = p.get("publication_year", "Year unavailable")
        
        if style_key == "apa":
            ref_entry = f"{authors_str} ({year_str}). {title_str}. {journal_str}. https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        elif style_key == "ama":
            ref_entry = f"{idx}. {authors_str}. {title_str} {journal_str}. {year_str}; PMID: {pmid}."
        elif style_key == "ieee":
            ref_entry = f"[{idx}] {authors_str}, \"{title_str},\" {journal_str}, {year_str}. PMID: {pmid}."
        else: # Default: vancouver
            ref_entry = f"{idx}. {authors_str}. {title_str} {journal_str}. {year_str}. PMID: {pmid}."
            
        ref_lines.append(ref_entry)
        
    return "\n".join(ref_lines)


# ==============================================================================
# SECTION 5: Main Execution Flow
# ==============================================================================
def main():
    parser = argparse.ArgumentParser(description="PRISMA Manuscript Generator with Word Export & Citation Styling")
    parser.add_argument("--style", choices=["vancouver", "apa", "ama", "ieee"], default="vancouver", help="Reference citation style")
    parser.add_argument("--docx", action="store_true", default=True, help="Generate MS Word (.docx) document")
    args, unknown = parser.parse_known_args()
    
    print("==================================================")
    print("      PRISMA Manuscript Draft Generator           ")
    print("==================================================")
    print(f"  -> Selected Reference Citation Style: {args.style.upper()}")
    
    # 1. Load project data files
    data = load_project_data()
    if not data:
        return
        
    print("Successfully loaded all 5 project data files.")
    
    # 2. Get API key
    api_key = get_api_key()
    if not api_key:
        print("Error: GROQ_API_KEY is required.")
        return
        
    # 3. Build prompt and inject pre-built programmatic references list with selected style
    prompt = build_manuscript_prompt(data)
    formatted_references_block = build_programmatic_references(data, style=args.style)
    prompt += f"\n\nUSE EXACTLY THIS PROGRAMMATICALLY ASSEMBLED REFERENCES LIST AT THE END:\n{formatted_references_block}\n"
    
    # 4. Call Groq API
    manuscript_text = call_groq_api(prompt, api_key)
    
    if not manuscript_text:
        print("Failed to generate manuscript.")
        return
        
    # --- POST-GENERATION SAFETY CHECK ---
    meta_results_text = data.get("meta_analysis_results", "")
    if "INSUFFICIENT DATA FOR POOLING" in meta_results_text:
        lower_text = manuscript_text.lower()
        prohibited_phrases = [
            "pooled sensitivity",
            "pooled specificity",
            "aggregate sensitivity",
            "aggregate specificity",
            "combined sensitivity",
            "combined specificity",
            "overall pooled",
            "meta-analytic estimate"
        ]
        found_prohibited = [phrase for phrase in prohibited_phrases if phrase in lower_text]
        if found_prohibited:
            print("\n[REJECTED] Post-generation safety check failed!")
            print(f"ERROR: Draft contains prohibited cross-study aggregate phrasing ({found_prohibited}) despite meta_analysis_results.txt stating INSUFFICIENT DATA FOR POOLING.")
            print("Draft rejected and file will NOT be saved.")
            return
            
    # 5. Save to research_paper_draft.txt
    success, output_path = save_manuscript(manuscript_text, "research_paper_draft.txt")
    
    # 6. Export MS Word (.docx) Document
    docx_success, docx_path = False, None
    if args.docx:
        docx_success, docx_path = export_docx.create_word_document(
            manuscript_text,
            formatted_references_block,
            output_filename="research_paper_draft.docx"
        )
    
    # 7. Print summary output
    print("\n==================================================")
    print("             MANUSCRIPT DRAFT SUMMARY             ")
    print("==================================================")
    print(f"Reference Style Applied: {args.style.upper()}")
    print(f"Total Character Count:   {len(manuscript_text)} characters")
    print(f"Total Word Count:        {len(manuscript_text.split())} words")
    print("==================================================")
    if success:
        print(f"Full text draft saved to: {output_path}")
    if docx_success:
        print(f"MS Word document saved to: {docx_path}")
    print("==================================================")


if __name__ == "__main__":
    main()
