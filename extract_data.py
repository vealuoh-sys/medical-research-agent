import json
import os
import sys
import time
import csv

from api_client import make_post_request, get_groq_api_key as get_api_key, call_groq_api


# ==============================================================================
# SECTION 1: Load Included PMIDs and Matching Abstracts
# ==============================================================================
# Reads screening_results.csv to get PMIDs marked as INCLUDE, then loads their
# full abstract text from systematic_results.json.
def load_included_papers():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "screening_results.csv")
    json_path = os.path.join(script_dir, "systematic_results.json")
    
    if not os.path.exists(csv_path):
        print(f"Error: Could not find '{csv_path}'. Run screening.py first.")
        return []
    if not os.path.exists(json_path):
        print(f"Error: Could not find '{json_path}'. Run systematic_search.py first.")
        return []
        
    included_pmids = set()
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("decision", "").strip().upper() == "INCLUDE":
                    included_pmids.add(row.get("pmid", "").strip())
    except Exception as e:
        print(f"Error reading screening_results.csv: {e}")
        return []
        
    print(f"Found {len(included_pmids)} INCLUDED papers in screening_results.csv.")
    
    # Load abstracts from systematic_results.json
    matched_papers = []
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            all_papers = json.load(f)
            for p in all_papers:
                pmid = str(p.get("pmid", "")).strip()
                if pmid in included_pmids:
                    matched_papers.append(p)
    except Exception as e:
        print(f"Error reading systematic_results.json: {e}")
        return []
        
    return matched_papers


# ==============================================================================
# SECTION 2: Extract Data Variables Using Groq API (llama-3.3-70b-versatile)
# ==============================================================================
def extract_data_batch(paper_batch, api_key):
    masked = api_key[:6] + "..." + api_key[-4:] if api_key and len(api_key) >= 10 else "***"
    print(f"  [Groq Extraction Call] Batch PMIDs: {[p['pmid'] for p in paper_batch]} | Key: {masked}")
    
    prompt = (
        "You are an expert systematic review data extraction assistant. "
        "Extract specific quantitative clinical variables from the abstracts of the research papers provided below.\n\n"
        "FOR EACH PAPER, EXTRACT EXACTLY THESE 6 VARIABLES:\n"
        "1. sample_size: Total number of patients or samples in the study (e.g. '150 patients').\n"
        "2. sensitivity: Reported sensitivity percentage or ratio (e.g. '98.5%').\n"
        "3. specificity: Reported specificity percentage or ratio (e.g. '92.0%').\n"
        "4. cutoff_value: Diagnostic threshold cut-off value used (e.g. '1.5 mmol/L', '3.0 mmol/L').\n"
        "5. reference_standard: Comparator or gold standard reference test (e.g. 'laboratory serum BHB', 'urine dipstick', 'nitroprusside reaction').\n"
        "6. population: Clinical population or setting (e.g. 'pediatric ED', 'adult emergency room', 'T1D outpatients').\n\n"
        "CRITICAL EXTRACTION RULE:\n"
        "- Extract ONLY information explicitly stated in the text.\n"
        "- If any variable is NOT explicitly reported in the abstract, you MUST write exactly 'NOT REPORTED' for that variable. Do NOT guess, estimate, or assume numbers.\n\n"
        "RESPONSE FORMAT:\n"
        "Return ONLY a valid JSON array of objects, formatted as:\n"
        "[\n"
        "  {\n"
        '    "pmid": "12345678",\n'
        '    "sample_size": "150 patients",\n'
        '    "sensitivity": "98.5%",\n'
        '    "specificity": "92.0%",\n'
        '    "cutoff_value": "1.5 mmol/L",\n'
        '    "reference_standard": "laboratory serum BHB",\n'
        '    "population": "pediatric ED"\n'
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
# SECTION 3: Save Extracted Data to extraction_table.csv
# ==============================================================================
def save_extraction_csv(data, filename="extraction_table.csv"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    fieldnames = [
        "pmid",
        "sample_size",
        "sensitivity",
        "specificity",
        "cutoff_value",
        "reference_standard",
        "population"
    ]
    
    try:
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in data:
                writer.writerow(r)
        return True, file_path
    except IOError as e:
        print(f"Error writing to CSV: {e}")
        return False, None


# ==============================================================================
# SECTION 4: Main Program Execution
# ==============================================================================
def main():
    print("==================================================")
    print("      Systematic Data Extraction Tool (Groq)    ")
    print("==================================================")
    
    # 1. Load included papers
    papers = load_included_papers()
    if not papers:
        print("No included papers found to process.")
        return
        
    print(f"Extracting clinical parameters for {len(papers)} included papers...")
    
    # 2. Get API key
    api_key = get_api_key()
    if not api_key:
        print("Error: GROQ_API_KEY is required.")
        return
        
    # 3. Extract data in small batches of 3 papers (safely under Groq TPM limits)
    batch_size = 3
    extracted_results = []
    
    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]
        print(f"  -> Processing batch {i // batch_size + 1}/{(len(papers) - 1) // batch_size + 1} (PMIDs: {', '.join([p['pmid'] for p in batch])})...")
        
        extracted_batch = extract_data_batch(batch, api_key)
        if extracted_batch is None:
            print(f"\n[FAIL] API call failed for extraction batch starting at PMID {batch[0]['pmid']} after retries. Pipeline halted.")
            return
            
        # Build lookup table
        extracted_map = {}
        if isinstance(extracted_batch, list):
            for item in extracted_batch:
                extracted_map[str(item.get("pmid")).strip()] = item
                
        for p in batch:
            pmid = str(p.get("pmid")).strip()
            if pmid in extracted_map:
                res = extracted_map[pmid]
            else:
                print(f"\n[FAIL] Missing extracted data for PMID {pmid} in API response array. Pipeline halted.")
                return
                
            extracted_results.append({
                "pmid": pmid,
                "sample_size": res.get("sample_size", "NOT REPORTED"),
                "sensitivity": res.get("sensitivity", "NOT REPORTED"),
                "specificity": res.get("specificity", "NOT REPORTED"),
                "cutoff_value": res.get("cutoff_value", "NOT REPORTED"),
                "reference_standard": res.get("reference_standard", "NOT REPORTED"),
                "population": res.get("population", "NOT REPORTED")
            })
            
        time.sleep(1.0)
        
    # 4. Save to extraction_table.csv
    success, csv_path = save_extraction_csv(extracted_results, "extraction_table.csv")
    
    if success:
        print("\n==================================================")
        print(f"SUCCESS: Extracted data for {len(extracted_results)} papers to extraction_table.csv")
        print("==================================================")
        print(f"File saved at: {csv_path}")
        print("==================================================")
        
    # 5. Print full table to terminal
    print("\nFULL EXTRACTION TABLE (extraction_table.csv):")
    print("------------------------------------------------------------------------------------------------------------------------")
    print(f"{'PMID':<9} | {'SAMPLE SIZE':<15} | {'SENSITIVITY':<12} | {'SPECIFICITY':<12} | {'CUTOFF':<14} | {'REFERENCE STANDARD':<22} | {'POPULATION'}")
    print("------------------------------------------------------------------------------------------------------------------------")
    for r in extracted_results:
        print(f"{r['pmid']:<9} | {r['sample_size']:<15} | {r['sensitivity']:<12} | {r['specificity']:<12} | {r['cutoff_value']:<14} | {r['reference_standard']:<22} | {r['population']}")
    print("------------------------------------------------------------------------------------------------------------------------")


if __name__ == "__main__":
    main()
