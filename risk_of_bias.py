import csv
import json
import os
import sys

from api_client import get_groq_api_key as get_api_key, call_groq_api

# Reconfigure stdout/stderr on Windows to handle UTF-8 symbols smoothly
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass


# ==============================================================================
# SECTION 1: Load Included Studies from extraction_table.csv & systematic_results.json
# ==============================================================================
def load_extracted_studies():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    ext_csv = os.path.join(script_dir, "extraction_table.csv")
    sys_json = os.path.join(script_dir, "systematic_results.json")
    
    if not os.path.exists(ext_csv):
        print(f"Error: Could not find '{ext_csv}'. Run Stage 6 first.")
        return []
    if not os.path.exists(sys_json):
        print(f"Error: Could not find '{sys_json}'. Run Stage 4 first.")
        return []
        
    ext_rows = []
    try:
        with open(ext_csv, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                ext_rows.append(r)
    except Exception as e:
        print(f"Error reading extraction_table.csv: {e}")
        return []
        
    sys_dict = {}
    try:
        with open(sys_json, "r", encoding="utf-8") as f:
            papers = json.load(f)
            for p in papers:
                sys_dict[str(p.get("pmid", "")).strip()] = p
    except Exception as e:
        print(f"Error reading systematic_results.json: {e}")
        return []
        
    full_studies = []
    for r in ext_rows:
        pmid = str(r.get("pmid", "")).strip()
        p_info = sys_dict.get(pmid, {})
        full_studies.append({
            "pmid": pmid,
            "title": p_info.get("title", "Title unavailable"),
            "abstract": p_info.get("abstract", "No abstract available"),
            "population": r.get("population", "NOT REPORTED"),
            "reference_standard": r.get("reference_standard", "NOT REPORTED"),
            "cutoff_value": r.get("cutoff_value", "NOT REPORTED"),
            "sample_size": r.get("sample_size", "NOT REPORTED")
        })
        
    return full_studies


# ==============================================================================
# SECTION 2: Assess Risk of Bias via Groq API (llama-3.3-70b-versatile)
# ==============================================================================
def evaluate_quadas2_risk_of_bias(studies, api_key, batch_size=5):
    """
    Evaluates studies against standard QUADAS-2 domains in batches:
    1. Patient Selection
    2. Index Test
    3. Reference Standard
    4. Flow and Timing
    Assigns domain judgments: LOW, HIGH, or UNCLEAR with brief clinical rationale.
    """
    print(f"\nEvaluating QUADAS-2 Risk of Bias for {len(studies)} studies in batches of {batch_size}...")
    all_evaluations = []
    
    for i in range(0, len(studies), batch_size):
        batch = studies[i:i + batch_size]
        prompt = (
            "You are an expert systematic review methodologist. "
            "Evaluate the following diagnostic accuracy studies using the QUADAS-2 tool.\n\n"
            "FOR EACH STUDY, ASSIGN A RISK OF BIAS JUDGMENT (LOW, HIGH, or UNCLEAR) FOR EACH OF THE 4 DOMAINS:\n"
            "1. patient_selection_bias: LOW, HIGH, or UNCLEAR\n"
            "2. index_test_bias: LOW, HIGH, or UNCLEAR\n"
            "3. reference_standard_bias: LOW, HIGH, or UNCLEAR\n"
            "4. flow_timing_bias: LOW, HIGH, or UNCLEAR\n"
            "5. rationale: Brief 1-sentence methodological justification summarizing key quality concerns.\n\n"
            "STRICT JSON OUTPUT INSTRUCTIONS:\n"
            "Return ONLY a valid JSON array of objects. Do not include markdown codeblocks or preamble.\n"
            "Each object must have exactly these keys: 'pmid', 'patient_selection_bias', 'index_test_bias', 'reference_standard_bias', 'flow_timing_bias', 'rationale'.\n\n"
            "==================== STUDIES TO EVALUATE ====================\n\n"
        )
        
        for idx, s in enumerate(batch, 1):
            prompt += f"--- STUDY {idx} ---\n"
            prompt += f"PMID: {s['pmid']}\n"
            prompt += f"Title: {s['title']}\n"
            prompt += f"Population: {s['population']}\n"
            prompt += f"Reference Standard: {s['reference_standard']}\n"
            prompt += f"Sample Size: {s['sample_size']}\n"
            prompt += f"Abstract: {s['abstract']}\n\n"
            
        res_text = call_groq_api(prompt, api_key)
        if not res_text:
            print(f"Warning: Failed to receive response for batch starting at index {i}.")
            continue
            
        try:
            cleaned = res_text.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.startswith("```"):
                cleaned = cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
            parsed = json.loads(cleaned.strip())
            if isinstance(parsed, list):
                all_evaluations.extend(parsed)
        except Exception as e:
            print(f"Error parsing QUADAS-2 batch response JSON: {e}")
            
        import time
        time.sleep(1.0)
        
    return all_evaluations


# ==============================================================================
# SECTION 3: Save QUADAS-2 Evaluation to CSV
# ==============================================================================
def save_quadas2_csv(evaluations, filename="risk_of_bias_table.csv"):
    script_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(script_dir, filename)
    
    fieldnames = [
        "pmid",
        "patient_selection_bias",
        "index_test_bias",
        "reference_standard_bias",
        "flow_timing_bias",
        "rationale"
    ]
    
    try:
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for r in evaluations:
                writer.writerow({
                    "pmid": r.get("pmid", ""),
                    "patient_selection_bias": r.get("patient_selection_bias", "UNCLEAR").upper(),
                    "index_test_bias": r.get("index_test_bias", "UNCLEAR").upper(),
                    "reference_standard_bias": r.get("reference_standard_bias", "UNCLEAR").upper(),
                    "flow_timing_bias": r.get("flow_timing_bias", "UNCLEAR").upper(),
                    "rationale": r.get("rationale", "No rationale provided.")
                })
        return True, file_path
    except IOError as e:
        print(f"Error saving QUADAS-2 CSV file '{filename}': {e}")
        return False, None


# ==============================================================================
# SECTION 4: Main Execution Flow
# ==============================================================================
def main():
    print("==================================================")
    print("    Stage 6.5: QUADAS-2 Risk of Bias Assessment  ")
    print("==================================================")
    
    studies = load_extracted_studies()
    if not studies:
        print("No extracted studies found to evaluate.")
        return
        
    api_key = get_api_key()
    if not api_key:
        print("Error: GROQ_API_KEY is required.")
        return
        
    evaluations = evaluate_quadas2_risk_of_bias(studies, api_key)
    if not evaluations:
        print("Failed to generate Risk of Bias evaluations.")
        return
        
    success, out_path = save_quadas2_csv(evaluations, "risk_of_bias_table.csv")
    if success:
        print(f"\n[PASS] Stage 6.5 Complete: Saved QUADAS-2 Risk of Bias table to {out_path}")


if __name__ == "__main__":
    main()
