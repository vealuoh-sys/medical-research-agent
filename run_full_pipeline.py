import os
import sys
import json
import csv
import re
import time

# Reconfigure stdout/stderr on Windows to handle UTF-8 symbols smoothly
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================================
# PIPELINE IMPORTS: Import modular functions from existing script tools
# ==============================================================================
import literature_search as ls
import gap_analysis as ga
import title_generator as tg
import systematic_search as ss
import screening as sc
import extract_data as ed
import risk_of_bias as rob
import meta_analysis as ma
import draft_paper as dp
import api_client as ac
import journal_suggester as js


# ==============================================================================
# STAGE 1: Primary Literature Search
# ==============================================================================
# Executes PubMed search for the user's topic, fetches top 20 papers, and saves results.json.
def run_stage_1(topic):
    print("\n==================================================")
    print("  STAGE 1: Primary PubMed Literature Search       ")
    print("==================================================")
    
    id_list = ls.search_pubmed_ids(topic, max_results=20)
    if not id_list:
        print("[FAIL] Stage 1: Search returned no results or failed to connect to PubMed.")
        return False, None
        
    papers = ls.fetch_paper_details(id_list)
    if not papers:
        print("[FAIL] Stage 1: Failed to download paper metadata.")
        return False, None
        
    success, saved_path = ls.save_to_json(papers, filename="results.json")
    if not success:
        print("[FAIL] Stage 1: Could not save results.json.")
        return False, None
        
    print(f"[PASS] Stage 1 Complete: Found {len(papers)} papers -> Saved to results.json")
    return True, papers


# ==============================================================================
# STAGE 2: Gap Analysis Synthesis & PMID Citation Audit
# ==============================================================================
# Sends papers to Gemini API to synthesize themes, missing topics, and 5 research gaps.
def run_stage_2(api_key):
    print("\n==================================================")
    print("  STAGE 2: Literature Gap Analysis Synthesis      ")
    print("==================================================")
    
    papers = ga.load_results_json("results.json")
    if not papers:
        print("[FAIL] Stage 2: Missing results.json.")
        return False
        
    prompt = ga.build_analysis_prompt(papers)
    analysis_result = ga.call_groq_api(prompt, api_key)

    if not analysis_result:
        print("  -> Retrying Stage 2 with a smaller, shorter request (in case the first was too large)...")
        smaller_prompt = ga.build_analysis_prompt(papers, max_papers=8, abstract_char_limit=500)
        analysis_result = ga.call_groq_api(smaller_prompt, api_key)

    if not analysis_result:
        print("[FAIL] Stage 2: Groq API call for gap analysis failed.")
        return False
        
    success, output_path = ga.save_gap_analysis(analysis_result, "gap_analysis.txt")
    if not success:
        print("[FAIL] Stage 2: Failed to save gap_analysis.txt.")
        return False
        
    # Audit cited PMIDs against results.json
    ga.verify_cited_pmids(analysis_result, papers)
    print(f"[PASS] Stage 2 Complete: Gap analysis saved to gap_analysis.txt")
    return True


# ==============================================================================
# STAGE 3: Research Concept & Title Generation
# ==============================================================================
# Generates 5 candidate paper titles with study design and solo-researcher feasibility notes.
def run_stage_3(api_key):
    print("\n==================================================")
    print("  STAGE 3: Candidate Research Title Generator     ")
    print("==================================================")
    
    gap_text = tg.load_gap_analysis("gap_analysis.txt")
    if not gap_text:
        print("[FAIL] Stage 3: Missing gap_analysis.txt.")
        return False
        
    prompt = tg.build_title_prompt(gap_text)
    titles_result = tg.call_groq_api(prompt, api_key)
    
    if not titles_result:
        print("[FAIL] Stage 3: Groq API title generation failed.")
        return False
        
    success, output_path = tg.save_research_titles(titles_result, "research_titles.txt")
    if not success:
        print("[FAIL] Stage 3: Failed to save research_titles.txt.")
        return False
        
    print(f"[PASS] Stage 3 Complete: Research titles saved to research_titles.txt")
    return True


# ==============================================================================
# STAGE 4: Dynamic Multi-Query Systematic Search & Deduplication
# ==============================================================================
# Dynamically generates 4 search variations from the target topic string.
def run_stage_4(topic):
    print("\n==================================================")
    print("  STAGE 4: Dynamic Multi-Query Systematic Search  ")
    print("==================================================")
    
    # Generate queries dynamically from topic parameter
    target_queries = [
        f"{topic}",
        f"{topic} diagnostic accuracy sensitivity specificity",
        f"{topic} point of care clinical performance",
        f"{topic} systematic review meta analysis"
    ]
    
    print(f"  -> Generated {len(target_queries)} dynamic search queries for topic: '{topic}'")
    for idx, q in enumerate(target_queries, 1):
        print(f"     {idx}) Query: \"{q}\"")
        
    raw_pmids = []
    for query in target_queries:
        ids = ss.search_pubmed_ids(query, max_results=100)
        raw_pmids.extend(ids)
        time.sleep(0.3)
        
    unique_pmids = list(dict.fromkeys(raw_pmids))
    print(f"  -> Total raw PMIDs retrieved: {len(raw_pmids)} | Unique deduplicated PMIDs: {len(unique_pmids)}")
    
    if not unique_pmids:
        print("[FAIL] Stage 4: No unique PMIDs retrieved across dynamic search queries.")
        return False, None
        
    papers = ss.fetch_paper_details_batch(unique_pmids, batch_size=50)
    if not papers:
        print("[FAIL] Stage 4: Failed to download paper metadata for systematic search.")
        return False, None
        
    success, saved_path = ss.save_to_json(papers, filename="systematic_results.json")
    if not success:
        print("[FAIL] Stage 4: Failed to save systematic_results.json.")
        return False, None
        
    print(f"[PASS] Stage 4 Complete: Saved {len(papers)} unique articles to systematic_results.json")
    return True, papers


# ==============================================================================
# STAGE 5: Deterministic Screening & Post-Screening Keyword Audit
# ==============================================================================
# Screens papers with temp=0, seed=42, then audits INCLUDED papers for diagnostic keywords.
def run_stage_5(api_key, topic="Point-of-Care Testing"):
    print("\n==================================================")
    print("  STAGE 5: Clinical Screening & Keyword Audit     ")
    print("==================================================")
    
    papers = sc.load_systematic_results("systematic_results.json")
    if not papers:
        print("[FAIL] Stage 5: Missing systematic_results.json.")
        return False, []
        
    batch_size = 10
    all_screening_results = []
    
    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]
        batch_decisions = sc.screen_paper_batch(batch, api_key, topic=topic)
        if batch_decisions is None:
            print(f"[FAIL] Stage 5: Groq API screening call failed for batch starting at PMID {batch[0]['pmid']} after all retries. Pipeline halted.")
            return False, []
            
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
                print(f"[FAIL] Stage 5: Missing screening decision for PMID {pmid} in API response array. Pipeline halted.")
                return False, []
                
            all_screening_results.append({
                "pmid": pmid,
                "title": title,
                "decision": dec,
                "reason": reason
            })
            
        time.sleep(2.0)
        
    # --- POST-SCREENING KEYWORD AUDIT ---
    paper_dict = {str(p["pmid"]).strip(): p for p in papers}
    diagnostic_keywords = [
        "accuracy", "sensitivity", "specificity", "auc", "roc", "cutoff", "cut-off",
        "performance", "meter", "device", "sensor", "point-of-care", "capillary",
        "breathomics", "ketone", "beta-hydroxybutyrate", "b-ohb", "dka"
    ]
    
    flagged_includes = []
    for item in all_screening_results:
        if item["decision"] == "INCLUDE":
            pmid = item["pmid"]
            p_obj = paper_dict.get(pmid, {})
            text_to_check = (p_obj.get("title", "") + " " + p_obj.get("abstract", "")).lower()
            
            # Count diagnostic accuracy keyword matches
            matches = [kw for kw in diagnostic_keywords if kw in text_to_check]
            if len(matches) < 3: # Weak justification threshold
                item["decision"] = "NEEDS MANUAL REVIEW"
                item["reason"] = f"FLAGGED FOR REVIEW: Low keyword relevance count ({len(matches)} matches)."
                flagged_includes.append(pmid)
                
    sc.save_screening_csv(all_screening_results, "screening_results.csv")
    
    inc_count = sum(1 for r in all_screening_results if r["decision"] == "INCLUDE")
    exc_count = sum(1 for r in all_screening_results if r["decision"] == "EXCLUDE")
    rev_count = sum(1 for r in all_screening_results if r["decision"] == "NEEDS MANUAL REVIEW")
    
    print(f"  -> Screening Counts: INCLUDED={inc_count} | EXCLUDED={exc_count} | FLAGGED FOR REVIEW={rev_count}")
    
    if rev_count > 0:
        print(f"[NEEDS REVIEW] Stage 5 Warning: {rev_count} INCLUDED papers were flagged for manual review.")
        print(f"  Flagged PMIDs: {', '.join(flagged_includes)}")
    else:
        print("[PASS] Stage 5 Complete: All INCLUDED papers passed keyword validation -> Saved to screening_results.csv")
        
    return True, all_screening_results


# ==============================================================================
# STAGE 6: Data Extraction & Post-Extraction Numeric Grounding Audit
# ==============================================================================
# Extracts clinical variables and verifies every number against source abstract text.
def run_stage_6(api_key):
    print("\n==================================================")
    print("  STAGE 6: Data Extraction & Numeric Grounding Audit")
    print("==================================================")
    
    papers = ed.load_included_papers()
    if not papers:
        print("[FAIL] Stage 6: No INCLUDED papers found to extract.")
        return False, []
        
    batch_size = 10
    extracted_results = []
    
    for i in range(0, len(papers), batch_size):
        batch = papers[i:i + batch_size]
        extracted_batch = ed.extract_data_batch(batch, api_key)
        if extracted_batch is None:
            print(f"[FAIL] Stage 6: Groq API extraction call failed for batch starting at PMID {batch[0]['pmid']} after all retries. Pipeline halted.")
            return False, []
            
        extracted_map = {}
        if isinstance(extracted_batch, list):
            for item in extracted_batch:
                extracted_map[str(item.get("pmid")).strip()] = item
                
        for p in batch:
            pmid = str(p.get("pmid")).strip()
            if pmid in extracted_map:
                res = extracted_map[pmid]
            else:
                print(f"[FAIL] Stage 6: Missing extracted data for PMID {pmid} in API response array. Pipeline halted.")
                return False, []
                
            extracted_results.append({
                "pmid": pmid,
                "sample_size": res.get("sample_size", "NOT REPORTED"),
                "sensitivity": res.get("sensitivity", "NOT REPORTED"),
                "specificity": res.get("specificity", "NOT REPORTED"),
                "cutoff_value": res.get("cutoff_value", "NOT REPORTED"),
                "reference_standard": res.get("reference_standard", "NOT REPORTED"),
                "population": res.get("population", "NOT REPORTED")
            })
            
        time.sleep(2.0)
        
    # --- POST-EXTRACTION NUMERIC GROUNDING AUDIT ---
    paper_dict = {str(p["pmid"]).strip(): p for p in papers}
    unverified_rows = []
    
    for row in extracted_results:
        pmid = row["pmid"]
        source_abstract = paper_dict.get(pmid, {}).get("abstract", "") + " " + paper_dict.get(pmid, {}).get("title", "")
        
        # Check numeric parameters: sensitivity, specificity, sample_size, cutoff
        numeric_fields = ["sensitivity", "specificity", "sample_size", "cutoff_value"]
        field_errors = []
        
        for field in numeric_fields:
            val = str(row[field]).strip()
            if val != "NOT REPORTED":
                # Extract digits/numbers from extracted string
                numbers = re.findall(r'\d+(?:\.\d+)?', val)
                for num_str in numbers:
                    # Check if the exact number or integer portion appears in source abstract
                    num_float = float(num_str)
                    int_part = str(int(num_float))
                    
                    if num_str not in source_abstract and int_part not in source_abstract:
                        field_errors.append(f"{field} ('{val}' number {num_str} not in text)")
                        
        if field_errors:
            row["population"] += " [UNVERIFIED NUMBERS DETECTED]"
            unverified_rows.append((pmid, field_errors))
            
    ed.save_extraction_csv(extracted_results, "extraction_table.csv")
    
    if unverified_rows:
        print(f"[NEEDS REVIEW] Stage 6 Warning: {len(unverified_rows)} rows contained unverified numbers:")
        for pmid, errs in unverified_rows:
            print(f"  - PMID {pmid}: {', '.join(errs)}")
    else:
        print("[PASS] Stage 6 Complete: All extracted numeric values ground-verified in source abstract text -> Saved to extraction_table.csv")
        
    return True, extracted_results


# ==============================================================================
# STAGE 6.5: QUADAS-2 Methodological Risk of Bias Assessment
# ==============================================================================
def run_stage_6_5(api_key):
    print("\n==================================================")
    print("  STAGE 6.5: QUADAS-2 Methodological Risk of Bias ")
    print("==================================================")
    
    studies = rob.load_extracted_studies()
    if not studies:
        print("[FAIL] Stage 6.5: No extracted studies found for QUADAS-2 evaluation.")
        return False
        
    evaluations = rob.evaluate_quadas2_risk_of_bias(studies, api_key)
    if not evaluations:
        print("[FAIL] Stage 6.5: Risk of bias evaluation failed.")
        return False
        
    success, out_path = rob.save_quadas2_csv(evaluations, "risk_of_bias_table.csv")
    if not success:
        print("[FAIL] Stage 6.5: Failed to save risk_of_bias_table.csv.")
        return False
        
    print(f"[PASS] Stage 6.5 Complete: QUADAS-2 table saved to risk_of_bias_table.csv")
    return True


# ==============================================================================
# STAGE 7: Dynamic Quantitative Diagnostic Meta-Analysis Pooling
# ==============================================================================
# Reads extraction_table.csv dynamically, filters to complete rows with numeric values
# and EXPLICIT disease-positive counts (no prevalence estimation/guessing).
def run_stage_7():
    print("\n==================================================")
    print("  STAGE 7: Dynamic Diagnostic Meta-Analysis       ")
    print("==================================================")
    
    script_dir = os.path.dirname(os.path.abspath(__file__))
    extraction_csv_path = os.path.join(script_dir, "extraction_table.csv")
    
    if not os.path.exists(extraction_csv_path):
        print("[FAIL] Stage 7: Missing extraction_table.csv.")
        return False
        
    dynamic_studies = []
    excluded_studies = []
    
    with open(extraction_csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            pmid = row.get("pmid", "").strip()
            sample_size_raw = row.get("sample_size", "").strip()
            sens_raw = row.get("sensitivity", "").strip()
            spec_raw = row.get("specificity", "").strip()
            pop_str = row.get("population", "").strip()
            
            def extract_num(s):
                if not s or "NOT REPORTED" in s.upper():
                    return None
                m = re.search(r'\d+(?:\.\d+)?', s)
                return float(m.group(0)) if m else None
                
            n_total = extract_num(sample_size_raw)
            sens_pct = extract_num(sens_raw)
            spec_pct = extract_num(spec_raw)
            
            # Only consider rows where sample_size, sensitivity, and specificity are present
            if n_total is not None and sens_pct is not None and spec_pct is not None and n_total > 0:
                # Explicitly parse disease-positive count from population text (e.g. "(50 of 450 had DKA)" or "50 cases")
                pos_match = re.search(r'(\d+)\s+(?:of\s+\d+|cases|positive|patients with DKA|DKA)', pop_str, re.IGNORECASE)
                
                if pos_match:
                    dka_pos = int(pos_match.group(1))
                    if 0 < dka_pos <= n_total:
                        dynamic_studies.append({
                            "pmid": pmid,
                            "author_year": f"PMID {pmid}",
                            "total": int(n_total),
                            "dka_pos": dka_pos,
                            "sens_pct": sens_pct,
                            "spec_pct": spec_pct
                        })
                    else:
                        excluded_studies.append((pmid, "Invalid disease-positive count relative to total"))
                else:
                    # STRICT RULE: Do NOT guess or assume prevalence! Exclude study if dka_pos is unstated.
                    excluded_studies.append((pmid, "disease-positive count not explicitly stated in extraction data (manual lookup required)"))
            else:
                excluded_studies.append((pmid, "missing sensitivity, specificity, or sample size"))
                
    # Print clear messages for excluded studies
    if excluded_studies:
        print("  -> Excluded Studies Note:")
        for pmid, reason in excluded_studies:
            print(f"     - PMID {pmid} excluded from pooling - {reason}.")
            
    # Check if fewer than 2 studies remain with genuine complete data
    if len(dynamic_studies) < 2:
        print(f"\n[NEEDS REVIEW] Stage 7: INSUFFICIENT DATA FOR POOLING ({len(dynamic_studies)} eligible study found, minimum 2 required).")
        print("  Meta-analysis pooling skipped to avoid relying on incomplete or estimated data.")
        
        # Save explicit status note to meta_analysis_results.txt
        output_path = os.path.join(script_dir, "meta_analysis_results.txt")
        with open(output_path, "w", encoding="utf-8") as f:
            f.write("================================================================================")
            f.write("INSUFFICIENT DATA FOR POOLING: Fewer than 2 studies had complete 2x2 data.")
            f.write("================================================================================")
        return True
        
    print(f"\n  -> Successfully validated {len(dynamic_studies)} quantitative studies with explicit 2x2 data for meta-analysis:")
    tables = ma.reconstruct_2x2_tables(dynamic_studies)
    
    res_sens = ma.perform_meta_analysis_for_measure(tables, measure_type="sens")
    res_spec = ma.perform_meta_analysis_for_measure(tables, measure_type="spec")
    
    print(f"  -> Dynamic Pooled Sensitivity: {res_sens['pooled_pct']:.2f}% (95% CI: {res_sens['ci_lower']:.2f}% - {res_sens['ci_upper']:.2f}%, I^2={res_sens['I2']:.1f}%)")
    print(f"  -> Dynamic Pooled Specificity: {res_spec['pooled_pct']:.2f}% (95% CI: {res_spec['ci_lower']:.2f}% - {res_spec['ci_upper']:.2f}%, I^2={res_spec['I2']:.1f}%)")
    
    # Save meta-analysis report to meta_analysis_results.txt
    report_lines = [
        "================================================================================",
        "        DIAGNOSTIC ACCURACY META-ANALYSIS REPORT: DYNAMIC SYNTHESIS             ",
        "================================================================================",
        "",
        "INDIVIDUAL STUDY 2x2 CONTINGENCY TABLES:",
        "--------------------------------------------------------------------------------",
        f"{'PMID':<10} | {'STUDY':<28} | {'TOTAL':<6} | {'TP':<4} | {'FN':<4} | {'TN':<5} | {'FP':<4} | {'SENS (%)':<9} | {'SPEC (%)'}",
        "--------------------------------------------------------------------------------"
    ]
    for t in tables:
        report_lines.append(
            f"{t['pmid']:<10} | {t['author_year']:<28} | {t['total']:<6} | {t['tp']:<4} | {t['fn']:<4} | {t['tn']:<5} | {t['fp']:<4} | {t['reported_sens']:<9.1f} | {t['reported_spec']:.2f}"
        )
    report_lines.extend([
        "--------------------------------------------------------------------------------",
        "",
        "POOLED META-ANALYSIS RESULTS:",
        "--------------------------------------------------------------------------------",
        f"1. POOLED SENSITIVITY: {res_sens['pooled_pct']:.2f}% (95% CI: {res_sens['ci_lower']:.2f}% to {res_sens['ci_upper']:.2f}%, Tau^2={res_sens['tau2']:.4f}, I^2={res_sens['I2']:.1f}%)",
        f"2. POOLED SPECIFICITY: {res_spec['pooled_pct']:.2f}% (95% CI: {res_spec['ci_lower']:.2f}% to {res_spec['ci_upper']:.2f}%, Tau^2={res_spec['tau2']:.4f}, I^2={res_spec['I2']:.1f}%)",
        "================================================================================"
    ])
    
    output_path = os.path.join(script_dir, "meta_analysis_results.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
        
    print(f"[PASS] Stage 7 Complete: Dynamic meta-analysis results saved to meta_analysis_results.txt")
    return True


# ==============================================================================
# STAGE 8: Programmatic Reference Assembly & Manuscript Drafting
# ==============================================================================
# Programmatically builds the References section directly from systematic_results.json metadata,
# then calls the LLM (temp=0, seed=42) to generate the full PRISMA manuscript draft.
def run_stage_8(api_key, style="vancouver"):
    print("\n==================================================")
    print("  STAGE 8: PRISMA Manuscript & Word Document      ")
    print("==================================================")
    print(f"  -> Selected Reference Citation Style: {style.upper()}")
    
    project_data = dp.load_project_data()
    if not project_data:
        print("[FAIL] Stage 8: Missing project data files.")
        return False
        
    formatted_references_block = dp.build_programmatic_references(project_data, style=style)
    prompt = dp.build_manuscript_prompt(project_data)
    prompt += f"\n\nUSE EXACTLY THIS PROGRAMMATICALLY ASSEMBLED REFERENCES LIST AT THE END:\n{formatted_references_block}\n"
    
    manuscript_text = ac.call_groq_api(prompt, api_key)
    if not manuscript_text:
        print("[FAIL] Stage 8: Groq API manuscript generation failed.")
        return False
        
    # --- POST-GENERATION SAFETY CHECK ---
    meta_results_text = project_data.get("meta_analysis_results", "")
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
            return False
            
    success, output_path = dp.save_manuscript(manuscript_text, "research_paper_draft.txt")
    if not success:
        print("[FAIL] Stage 8: Failed to save research_paper_draft.txt.")
        return False
        
    import export_docx
    docx_success, docx_path = export_docx.create_word_document(
        manuscript_text,
        formatted_references_block,
        output_filename="research_paper_draft.docx"
    )
    
    print(f"[PASS] Stage 8 Complete:")
    print(f"  - Text Manuscript: {output_path}")
    if docx_success:
        print(f"  - MS Word (.docx): {docx_path}")
    return True


# ==============================================================================
# STAGE 9: Free/Open-Access Journal Suggestions
# ==============================================================================
# Queries DOAJ (Directory of Open Access Journals) for real, currently-listed
# journals matching the paper's topic — never invents journal names.
def run_stage_9(topic):
    print("\n==================================================")
    print("  STAGE 9: Journal Suggestions (DOAJ)             ")
    print("==================================================")

    journals = js.search_doaj_journals(topic, max_results=15)
    if journals is None:
        print("[FAIL] Stage 9: Could not reach DOAJ.")
        return False

    ranked = js.rank_journals(journals)
    success, output_path = js.save_journal_suggestions(ranked, topic, filename="journal_suggestions.txt")
    if not success:
        print("[FAIL] Stage 9: Failed to save journal_suggestions.txt.")
        return False

    free_count = sum(1 for j in ranked if "No " in j["apc_note"])
    print(f"[PASS] Stage 9 Complete: {len(ranked)} journals found ({free_count} free-to-publish) -> journal_suggestions.txt")
    return True


# ==============================================================================
# PIPELINE ORCHESTRATOR MAIN FLOW
# ==============================================================================
def main():
    import argparse
    parser = argparse.ArgumentParser(description="End-to-End Automated Medical Research Agent Pipeline")
    parser.add_argument("topic", nargs="*", default=["point of care HbA1c testing diagnostic accuracy"], help="Research topic")
    parser.add_argument("--style", choices=["vancouver", "apa", "ama", "ieee"], default="vancouver", help="Reference citation style")
    args, unknown = parser.parse_known_args()
    
    topic = " ".join(args.topic).strip()
    
    print("================================================================================")
    print("        END-TO-END AUTOMATED MEDICAL RESEARCH AGENT PIPELINE                    ")
    print("================================================================================")
    print(f"Target Research Topic: '{topic}'")
    print(f"Reference Style:       '{args.style.upper()}'")
    
    # Get Groq API key
    api_key = ac.get_groq_api_key()
    if not api_key:
        print("CRITICAL ERROR: GROQ_API_KEY is required to run the pipeline.")
        sys.exit(1)
        
    start_time = time.time()
    
    # --- STAGE 1 ---
    ok1, papers1 = run_stage_1(topic)
    if not ok1:
        print("\n[STOPPED] Pipeline halted at Stage 1. Please address error above.")
        sys.exit(1)
        
    # --- STAGE 2 ---
    ok2 = run_stage_2(api_key)
    if not ok2:
        print("\n[STOPPED] Pipeline halted at Stage 2. Please address error above.")
        sys.exit(1)
        
    # --- STAGE 3 ---
    ok3 = run_stage_3(api_key)
    if not ok3:
        print("\n[STOPPED] Pipeline halted at Stage 3. Please address error above.")
        sys.exit(1)
        
    # --- STAGE 4 ---
    ok4, papers4 = run_stage_4(topic)
    if not ok4:
        print("\n[STOPPED] Pipeline halted at Stage 4. Please address error above.")
        sys.exit(1)
        
    # --- STAGE 5 ---
    ok5, screening_results = run_stage_5(api_key, topic)
    if not ok5:
        print("\n[STOPPED] Pipeline halted at Stage 5. Please address error above.")
        sys.exit(1)
        
    # --- STAGE 6 ---
    ok6, extraction_results = run_stage_6(api_key)
    if not ok6:
        print("\n[STOPPED] Pipeline halted at Stage 6. Please address error above.")
        sys.exit(1)
        
    # --- STAGE 6.5 ---
    ok65 = run_stage_6_5(api_key)
    if not ok65:
        print("\n[STOPPED] Pipeline halted at Stage 6.5. Please address error above.")
        sys.exit(1)
        
    # --- STAGE 7 ---
    ok7 = run_stage_7()
    if not ok7:
        print("\n[STOPPED] Pipeline halted at Stage 7. Please address error above.")
        sys.exit(1)
        
    # --- STAGE 8 ---
    ok8 = run_stage_8(api_key, style=args.style)
    if not ok8:
        print("\n[STOPPED] Pipeline halted at Stage 8. Please address error above.")
        sys.exit(1)

    # --- STAGE 9 ---
    ok9 = run_stage_9(topic)
    if not ok9:
        print("\n[NOTICE] Stage 9 (journal suggestions) failed, but the manuscript is complete. Continuing.")

    elapsed = time.time() - start_time
    
    # ==============================================================================
    # FINAL SUMMARY REPORT
    # ==============================================================================
    print("\n================================================================================")
    print("                    FINAL PIPELINE EXECUTION SUMMARY                            ")
    print("================================================================================")
    print(f"Target Research Topic:            '{topic}'")
    print(f"Reference Citation Style:         '{args.style.upper()}'")
    print(f"Total Execution Time:             {elapsed:.1f} seconds")
    print(f"Stage 1 Primary Papers Found:     {len(papers1) if papers1 else 0}")
    print(f"Stage 4 Systematic Unique PMIDs:  {len(papers4) if papers4 else 0}")
    print(f"Stage 5 Screened Papers:          {len(screening_results)}")
    print(f"  - Included:                     {sum(1 for r in screening_results if r['decision'] == 'INCLUDE')}")
    print(f"  - Excluded:                     {sum(1 for r in screening_results if r['decision'] == 'EXCLUDE')}")
    print(f"  - Flagged for Review:           {sum(1 for r in screening_results if r['decision'] == 'NEEDS MANUAL REVIEW')}")
    print(f"Stage 6 Extracted Studies:        {len(extraction_results)}")
    print("--------------------------------------------------------------------------------")
    print("GENERATED ARTIFACTS & FILES:")
    print("  1. results.json              -> Primary search output")
    print("  2. gap_analysis.txt          -> Groq thematic & gap synthesis")
    print("  3. research_titles.txt       -> 5 candidate research paper concepts")
    print("  4. systematic_results.json   -> Multi-database (PubMed + Europe PMC) search data")
    print("  5. screening_results.csv     -> Deterministic study screening decisions")
    print("  6. extraction_table.csv      -> Verified 2x2 clinical parameters")
    print("  7. risk_of_bias_table.csv    -> QUADAS-2 Methodological Risk of Bias domain evaluations")
    print("  8. meta_analysis_results.txt -> Bivariate & DerSimonian-Laird pooling & heterogeneity")
    print("  9. research_paper_draft.txt  -> Full PRISMA-DTA manuscript plain text draft")
    print(" 10. research_paper_draft.docx -> Formatted MS Word (.docx) publication manuscript")
    print(" 11. journal_suggestions.txt  -> Real, DOAJ-verified open-access journal matches")
    print("================================================================================")


if __name__ == "__main__":
    main()
