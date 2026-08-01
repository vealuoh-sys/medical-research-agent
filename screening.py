import json
import os
import sys
import time
import csv

from api_client import make_post_request, get_groq_api_key as get_api_key, call_groq_api


# ==============================================================================
# SECTION 1: Load Papers from systematic_results.json
# ==============================================================================
def load_systematic_results(filename="systematic_results.json"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    if not os.path.exists(file_path):
        print(f"Error: Could not find '{filename}' at {file_path}")
        print("Please run systematic_search.py first.")
        return None
        
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading '{filename}': {e}")
        return None


# ==============================================================================
# SECTION 2: Screen a Batch of Papers via Groq API (llama-3.3-70b-versatile)
# ==============================================================================
def screen_paper_batch(paper_batch, api_key, topic="Point-of-Care Testing"):
    masked = api_key[:6] + "..." + api_key[-4:] if api_key and len(api_key) >= 10 else "***"
    print(f"  [Groq Screening Call] Batch PMIDs: {[p['pmid'] for p in paper_batch]} | Key: {masked}")
    
    prompt = (
        "You are an expert systematic review screening reviewer. "
        f"Evaluate the following research papers for inclusion in a systematic review on: '{topic}'.\n\n"
        "INCLUSION CRITERIA (Must meet ALL):\n"
        "- Studies in HUMANS.\n"
        "- Evaluates POINT-OF-CARE or rapid bedside diagnostic accuracy (HbA1c, ketones, blood/breath biomarkers).\n"
        "- Reports diagnostic performance metrics (e.g. sensitivity, specificity, AUC, correlation, accuracy).\n\n"
        "EXCLUSION CRITERIA (Exclude if ANY apply):\n"
        "- Non-human/animal/in vitro studies.\n"
        "- Review articles, editorials, case reports, or meta-analyses without primary data.\n"
        "- Purely therapeutic or management studies without diagnostic accuracy measurements.\n\n"
        "RESPONSE FORMAT:\n"
        "Return ONLY a valid JSON array of objects, formatted as:\n"
        "[\n"
        "  {\n"
        '    "pmid": "12345678",\n'
        '    "decision": "INCLUDE" or "EXCLUDE",\n'
        '    "reason": "1-sentence justification"\n'
        "  }\n"
        "]\n\n"
        "==================== ARTICLES DATA ====================\n\n"
    )
    
    for p in paper_batch:
        prompt += f"PMID: {p.get('pmid', 'N/A')}\n"
        prompt += f"Title: {p.get('title', 'N/A')}\n"
        prompt += f"Abstract: {p.get('abstract', 'No abstract available')}\n\n"
        
    res_text = call_groq_api(prompt, api_key)
    if not res_text:
        return None
        
    text = res_text.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        print(f"Warning: Model response was not valid JSON. Raw snippet: {text[:100]}...")
        return None


# ==============================================================================
# SECTION 3: Save Screening Results to CSV File
# ==============================================================================
def save_screening_csv(results, filename="screening_results.csv"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    try:
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["pmid", "title", "decision", "reason"])
            writer.writeheader()
            for r in results:
                writer.writerow(r)
        return True, file_path
    except IOError as e:
        print(f"Error writing to CSV: {e}")
        return False, None


# ==============================================================================
# SECTION 4: Main Execution Flow
# ==============================================================================
def main():
    print("==================================================")
    print("  Deterministic Study Screening Tool (Groq)  ")
    print("==================================================")
    
    # 1. Load papers from systematic_results.json
    papers = load_systematic_results("systematic_results.json")
    if not papers:
        return
        
    print(f"Loaded {len(papers)} papers for screening.")
    
    # 2. Get API key
    api_key = get_api_key()
    if not api_key:
        print("Error: GROQ_API_KEY is required.")
        return
        
    # 3. Process papers in small batches of 3 papers (safely under Groq TPM limits)
    batch_size = 3
    all_screening_results = []
    
    print(f"\nScreening {len(papers)} papers in batches of {batch_size} with temperature=0 & seed=42...")
    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]
        print(f"  -> Screening batch {i // batch_size + 1}/{(len(papers) - 1) // batch_size + 1} (PMIDs: {', '.join([p['pmid'] for p in batch])})...")
        
        batch_decisions = screen_paper_batch(batch, api_key)
        if batch_decisions is None:
            print(f"\n[FAIL] API call failed for screening batch starting at PMID {batch[0]['pmid']} after retries. Pipeline halted.")
            return
            
        # Build lookup table for decisions
        decision_map = {}
        if isinstance(batch_decisions, list):
            for d in batch_decisions:
                decision_map[str(d.get("pmid")).strip()] = (d.get("decision", "EXCLUDE").upper(), d.get("reason", "No reason provided."))
                
        for p in batch:
            pmid = str(p.get("pmid")).strip()
            title = p.get("title", "No title")
            
            if pmid in decision_map:
                dec, reason = decision_map[pmid]
            else:
                print(f"\n[FAIL] Missing screening decision for PMID {pmid} in API response array. Pipeline halted.")
                return
                
            all_screening_results.append({
                "pmid": pmid,
                "title": title,
                "decision": dec,
                "reason": reason
            })
            
        time.sleep(1.0)
        
    # 4. Save to CSV
    success, csv_path = save_screening_csv(all_screening_results, "screening_results.csv")
    
    # 5. Calculate summary statistics
    included_count = sum(1 for r in all_screening_results if r["decision"] == "INCLUDE")
    excluded_count = sum(1 for r in all_screening_results if r["decision"] == "EXCLUDE")
    
    print("\n==================================================")
    print("                SCREENING SUMMARY                 ")
    print("==================================================")
    print(f"Total Papers Screened: {len(all_screening_results)}")
    print(f"  - INCLUDED:  {included_count}")
    print(f"  - EXCLUDED:  {excluded_count}")
    print("==================================================")
    if success:
        print(f"Results saved to: {csv_path}")
        print("==================================================")


if __name__ == "__main__":
    main()
