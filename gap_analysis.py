import json
import os
import sys
import re

from api_client import make_post_request, get_groq_api_key as get_api_key, call_groq_api


# ==============================================================================
# SECTION 1: Load Article Results from results.json
# ==============================================================================
# Reads the results.json file created by literature_search.py in the script folder.
def load_results_json(filename="results.json"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    if not os.path.exists(file_path):
        print(f"Error: Could not find '{filename}' at {file_path}")
        print("Please run literature_search.py first to generate results.json.")
        return None
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"Error reading '{filename}': {e}")
        return None


# ==============================================================================
# SECTION 2: Build Structured Prompt for Gap Analysis
# ==============================================================================
def build_analysis_prompt(papers):
    prompt_text = (
        "You are an expert medical research assistant conducting a systematic gap analysis. "
        "Below are research papers (with Title, PMID, Journal, Year, and Abstract) retrieved from PubMed.\n\n"
        "Please analyze these papers and provide a structured report with the following three sections:\n\n"
        "1. MAIN THEMES AND FINDINGS:\n"
        "   Summarize the key overarching themes, major discoveries, and medical consensus present across these papers.\n\n"
        "2. UNDER-STUDIED, CONTRADICTORY, OR MISSING SUB-TOPICS:\n"
        "   Identify specific sub-topics, patient subgroups, diagnostic methods, or therapeutic areas that are under-studied, "
        "   show conflicting/contradictory findings, or are completely missing based ONLY on these abstracts.\n\n"
        "3. CONCRETE RESEARCH GAPS:\n"
        "   List 3 to 5 concrete, actionable research gaps. For EACH research gap, provide a clear 1-sentence justification "
        "   referencing the specific paper(s) (by PMID or Author/Title) that highlight or support this gap.\n\n"
        "==================== PAPERS DATA ====================\n\n"
    )
    
    for idx, p in enumerate(papers, 1):
        prompt_text += f"--- PAPER {idx} ---\n"
        prompt_text += f"PMID: {p.get('pmid', 'N/A')}\n"
        prompt_text += f"Title: {p.get('title', 'N/A')}\n"
        prompt_text += f"Journal: {p.get('journal', 'N/A')} ({p.get('publication_year', 'N/A')})\n"
        prompt_text += f"Authors: {', '.join(p.get('authors', []))}\n"
        prompt_text += f"Abstract: {p.get('abstract', 'No abstract available')}\n\n"
        
    return prompt_text


# ==============================================================================
# SECTION 4: Save Analysis Output to File
# ==============================================================================
# Saves the complete gap analysis response to 'gap_analysis.txt' in the script folder.
def save_gap_analysis(text, filename="gap_analysis.txt"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)
        return True, file_path
    except IOError as e:
        print(f"Error saving file '{filename}': {e}")
        return False, None


# ==============================================================================
# SECTION 5: Verification Step (Cross-check PMIDs)
# ==============================================================================
# Extracts all PMIDs mentioned in the LLM analysis text and cross-checks them
# against the PMIDs actually present in results.json to detect any hallucinations.
def verify_cited_pmids(analysis_text, papers):
    print("\n--------------------------------------------------")
    print("           PMID VERIFICATION STEP                 ")
    print("--------------------------------------------------")
    
    # 1. Build a set of all valid PMIDs loaded from results.json
    valid_pmids = set(str(p.get("pmid", "")).strip() for p in papers if p.get("pmid"))
    
    # 2. Extract PMIDs referenced in the analysis text (e.g. PMID: 42220810 or PMID 42220810)
    # Using regular expression to capture digits following 'PMID' or 'PMID:'
    extracted_pmids = set(re.findall(r'PMID[:\s]*(\d+)', analysis_text, re.IGNORECASE))
    
    # Fallback search for any 7 to 8 digit numbers in text if explicit PMID prefix wasn't used
    if not extracted_pmids:
        all_numbers = set(re.findall(r'\b\d{7,8}\b', analysis_text))
        extracted_pmids = all_numbers.intersection(valid_pmids)
        
    if not extracted_pmids:
        print("Notice: No explicit PMIDs were extracted from the analysis text.")
        return
        
    # 3. Compare cited PMIDs against valid PMIDs from results.json
    verified_pmids = extracted_pmids.intersection(valid_pmids)
    hallucinated_pmids = extracted_pmids - valid_pmids
    
    print(f"Total unique PMIDs cited by LLM: {len(extracted_pmids)}")
    print(f"Successfully verified PMIDs:     {len(verified_pmids)}")
    
    if hallucinated_pmids:
        print("\n[WARNING] UNVERIFIED / HALLUCINATED PMIDs DETECTED!")
        print("The following PMIDs were cited by Gemini but DO NOT exist in results.json:")
        for pmid in sorted(hallucinated_pmids):
            print(f"  - PMID: {pmid}")
        print("Caution: Please review these citations before using them in research.")
    else:
        print("VERIFICATION PASSED: All cited PMIDs exist in results.json!")
    print("--------------------------------------------------")


# ==============================================================================
# SECTION 6: Main Script Flow
# ==============================================================================
def main():
    print("==================================================")
    print("        PubMed Literature Gap Analysis Tool       ")
    print("==================================================")
    
    # Step 1: Load results.json
    papers = load_results_json("results.json")
    if not papers:
        return
        
    print(f"Loaded {len(papers)} papers from results.json.")
    
    # Step 2: Get Gemini API Key
    api_key = get_api_key()
    if not api_key:
        print("\nError: GEMINI_API_KEY is required to proceed.")
        print("Set GEMINI_API_KEY in your environment or place it in a .env file.")
        return
        
    # Step 3: Build prompt containing all abstracts
    prompt = build_analysis_prompt(papers)
    
    # Step 4: Send to Groq API
    analysis_result = call_groq_api(prompt, api_key)
    
    if not analysis_result:
        print("\nFailed to generate gap analysis.")
        return
        
    # Step 5: Save output to gap_analysis.txt
    success, output_path = save_gap_analysis(analysis_result, "gap_analysis.txt")
    
    # Step 6: Print analysis results to terminal
    print("\n==================================================")
    print("               GAP ANALYSIS RESULT                ")
    print("==================================================")
    print(analysis_result)
    print("==================================================")
    if success:
        print(f"Full analysis successfully saved to: {output_path}")
        
    # Step 7: Perform PMID verification
    verify_cited_pmids(analysis_result, papers)


if __name__ == "__main__":
    main()
