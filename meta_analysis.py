import math
import os
import sys

# Reconfigure stdout/stderr on Windows to handle UTF-8 symbols smoothly
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================================
# SECTION 1: Define Raw Study Data & Reconstruct 2x2 Tables
# ==============================================================================
# Input data provided from the 4 primary diagnostic accuracy studies:
# - PMID 21307381: total=516, DKA_positive=54, sensitivity=98.1%, specificity=78.6%
# - PMID 16690813: total=160, DKA_positive=57, sensitivity=98%, specificity=85%
# - PMID 24772583: total=38, DKA_positive=13, sensitivity=100%, specificity=96%
# - PMID 20597827: total=450, DKA_positive=50, sensitivity=99.87%, specificity=92.89%

studies_data = [
    {
        "pmid": "21307381",
        "author_year": "Arora et al. (2011)",
        "total": 516,
        "dka_pos": 54,
        "sens_pct": 98.1,
        "spec_pct": 78.6
    },
    {
        "pmid": "16690813",
        "author_year": "Naunheim et al. (2006)",
        "total": 160,
        "dka_pos": 57,
        "sens_pct": 98.0,
        "spec_pct": 85.0
    },
    {
        "pmid": "24772583",
        "author_year": "Lertwattanarak et al. (2014)",
        "total": 38,
        "dka_pos": 13,
        "sens_pct": 100.0,
        "spec_pct": 96.0
    },
    {
        "pmid": "20597827",
        "author_year": "Voulgari et al. (2010)",
        "total": 450,
        "dka_pos": 50,
        "sens_pct": 99.87,
        "spec_pct": 92.89
    }
]


def reconstruct_2x2_tables(studies):
    """
    Reconstructs integer 2x2 contingency table counts (TP, FN, TN, FP)
    from total sample size, positive DKA cases, sensitivity, and specificity.
    Rounding is applied to the nearest whole patient.
    """
    reconstructed = []
    for s in studies:
        n_pos = s["dka_pos"]
        n_neg = s["total"] - s["dka_pos"]
        
        # Calculate True Positives (TP) and False Negatives (FN)
        tp = round(n_pos * (s["sens_pct"] / 100.0))
        fn = n_pos - tp
        
        # Calculate True Negatives (TN) and False Positives (FP)
        tn = round(n_neg * (s["spec_pct"] / 100.0))
        fp = n_neg - tn
        
        reconstructed.append({
            "pmid": s["pmid"],
            "author_year": s["author_year"],
            "total": s["total"],
            "n_pos": n_pos,
            "n_neg": n_neg,
            "tp": tp,
            "fn": fn,
            "tn": tn,
            "fp": fp,
            "reported_sens": s["sens_pct"],
            "reported_spec": s["spec_pct"],
            "calc_sens": (tp / n_pos) * 100.0 if n_pos > 0 else 0,
            "calc_spec": (tn / n_neg) * 100.0 if n_neg > 0 else 0
        })
    return reconstructed


# ==============================================================================
# SECTION 2: Statistical Pooling Functions (DerSimonian-Laird Random-Effects)
# ==============================================================================
def logit(p):
    """Computes the log-odds (logit) transformation: log(p / (1 - p))."""
    return math.log(p / (1.0 - p))


def inv_logit(x):
    """Converts log-odds back into a probability/proportion: 1 / (1 + exp(-x))."""
    return 1.0 / (1.0 + math.exp(-x))


def perform_meta_analysis_for_measure(studies_2x2, measure_type="sens"):
    """
    Performs Inverse-Variance weighted pooling (Fixed-Effects & DerSimonian-Laird Random-Effects)
    on logit-transformed proportions, with 0.5 continuity correction for zero-count cells.
    
    Returns a summary dictionary with pooled estimates, 95% CIs, and I^2 heterogeneity.
    """
    k = len(studies_2x2)
    y_list = []
    v_list = []
    
    for s in studies_2x2:
        if measure_type == "sens":
            a, b = s["tp"], s["fn"]
        else: # spec
            a, b = s["tn"], s["fp"]
            
        # Apply 0.5 continuity correction if zero cells are present
        if a == 0 or b == 0:
            a_c = a + 0.5
            b_c = b + 0.5
        else:
            a_c = a
            b_c = b
            
        p = a_c / (a_c + b_c)
        y = logit(p)
        v = (1.0 / a_c) + (1.0 / b_c)
        
        y_list.append(y)
        v_list.append(v)
        
    # 1. Fixed-Effects Pooling
    w_fe = [1.0 / v for v in v_list]
    sum_w_fe = sum(w_fe)
    y_fe = sum(w * y for w, y in zip(w_fe, y_list)) / sum_w_fe
    
    # 2. Cochran's Q & Heterogeneity (I^2)
    Q = sum(w * ((y - y_fe) ** 2) for w, y in zip(w_fe, y_list))
    df = k - 1
    I2 = max(0.0, ((Q - df) / Q) * 100.0) if Q > 0 else 0.0
    
    # 3. DerSimonian-Laird Between-Study Variance (Tau^2)
    sum_w_sq = sum(w ** 2 for w in w_fe)
    C = sum_w_fe - (sum_w_sq / sum_w_fe)
    tau2 = max(0.0, (Q - df) / C) if C > 0 else 0.0
    
    # 4. Random-Effects Pooling
    w_re = [1.0 / (v + tau2) for v in v_list]
    sum_w_re = sum(w_re)
    y_re = sum(w * y for w, y in zip(w_re, y_list)) / sum_w_re
    se_re = math.sqrt(1.0 / sum_w_re)
    
    # 5. 95% Confidence Intervals in Logit Space and Inverse-Logit Back Transformation
    ci_lower_logit = y_re - 1.96 * se_re
    ci_upper_logit = y_re + 1.96 * se_re
    
    pooled_est = inv_logit(y_re) * 100.0
    pooled_lower = inv_logit(ci_lower_logit) * 100.0
    pooled_upper = inv_logit(ci_upper_logit) * 100.0
    
    return {
        "pooled_pct": pooled_est,
        "ci_lower": pooled_lower,
        "ci_upper": pooled_upper,
        "Q": Q,
        "df": df,
        "I2": I2,
        "tau2": tau2,
        "y_re": y_re,
        "se_re": se_re
    }


def compute_bivariate_dta_metrics(studies_2x2):
    """
    Computes bivariate diagnostic accuracy metrics:
    - Bivariate logit sensitivity and logit specificity
    - Between-study logit covariance and correlation coefficient (r_sens_spec)
    """
    k = len(studies_2x2)
    if k < 2:
        return None
        
    res_sens = perform_meta_analysis_for_measure(studies_2x2, "sens")
    res_spec = perform_meta_analysis_for_measure(studies_2x2, "spec")
    
    y_sens = []
    y_spec = []
    for s in studies_2x2:
        a_c = s["tp"] + (0.5 if s["tp"] == 0 or s["fn"] == 0 else 0)
        b_c = s["fn"] + (0.5 if s["tp"] == 0 or s["fn"] == 0 else 0)
        c_c = s["tn"] + (0.5 if s["tn"] == 0 or s["fp"] == 0 else 0)
        d_c = s["fp"] + (0.5 if s["tn"] == 0 or s["fp"] == 0 else 0)
        
        y_sens.append(logit(a_c / (a_c + b_c)))
        y_spec.append(logit(c_c / (c_c + d_c)))
        
    mean_sens = sum(y_sens) / k
    mean_spec = sum(y_spec) / k
    
    cov = sum((s - mean_sens) * (p - mean_spec) for s, p in zip(y_sens, y_spec)) / (k - 1)
    var_sens = sum((s - mean_sens) ** 2 for s in y_sens) / (k - 1)
    var_spec = sum((p - mean_spec) ** 2 for p in y_spec) / (k - 1)
    
    denom = math.sqrt(var_sens * var_spec)
    r_sens_spec = cov / denom if denom > 0 else 0.0
    
    return {
        "pooled_sens_pct": res_sens["pooled_pct"],
        "sens_ci_lower": res_sens["ci_lower"],
        "sens_ci_upper": res_sens["ci_upper"],
        "sens_I2": res_sens["I2"],
        "pooled_spec_pct": res_spec["pooled_pct"],
        "spec_ci_lower": res_spec["ci_lower"],
        "spec_ci_upper": res_spec["ci_upper"],
        "spec_I2": res_spec["I2"],
        "bivariate_covariance": cov,
        "bivariate_correlation": r_sens_spec
    }


# ==============================================================================
# SECTION 3: Format & Display Analysis Report
# ==============================================================================
def main():
    print("==================================================")
    print("  Diagnostic Accuracy Meta-Analysis (4 Studies)   ")
    print("==================================================")
    
    # Check package note requirement
    print("\nMETHODOLOGY NOTE:")
    print("  - Python package 'metadta' was checked and is NOT available on PyPI.")
    print("  - Method Used: DerSimonian-Laird Random-Effects Logit Inverse-Variance Pooling.")
    print("  - Classification Label: SIMPLIFIED RANDOM-EFFECTS INVERSE-VARIANCE METHODOLOGY.")
    print("    (Note: This is an inverse-variance random-effects pooling method, not a bivariate Reitsma/HSROC model).")
    
    # 1. Reconstruct 2x2 tables
    tables = reconstruct_2x2_tables(studies_data)
    
    # 2. Perform Meta-Analysis for Sensitivity and Specificity
    res_sens = perform_meta_analysis_for_measure(tables, measure_type="sens")
    res_spec = perform_meta_analysis_for_measure(tables, measure_type="spec")
    
    # Build text output report
    report_lines = []
    report_lines.append("================================================================================")
    report_lines.append("        DIAGNOSTIC ACCURACY META-ANALYSIS REPORT: POINT-OF-CARE KETONES         ")
    report_lines.append("================================================================================")
    report_lines.append("")
    report_lines.append("STATISTICAL METHODOLOGY & PLAIN-ENGLISH EXPLANATION:")
    report_lines.append("--------------------------------------------------------------------------------")
    report_lines.append("1. 2x2 Table Reconstruction:")
    report_lines.append("   - For each study, True Positives (TP), False Negatives (FN), True Negatives (TN),")
    report_lines.append("     and False Positives (FP) were reconstructed by multiplying total disease-positive")
    report_lines.append("     and disease-negative patient counts by reported sensitivity and specificity,")
    report_lines.append("     rounding to the nearest whole patient.")
    report_lines.append("")
    report_lines.append("2. Continuity Correction & Logit Transformation:")
    report_lines.append("   - Proportions (sensitivity/specificity) were transformed into log-odds (logit scale)")
    report_lines.append("     to stabilize variance. For zero-count cells (e.g. 0 false negatives), a standard")
    report_lines.append("     0.5 continuity correction was applied.")
    report_lines.append("")
    report_lines.append("3. DerSimonian-Laird Random-Effects Pooling:")
    report_lines.append("   - Studies were pooled using inverse-variance weights incorporating between-study")
    report_lines.append("     variance (Tau^2). Pooled logit estimates and 95% confidence intervals were back-")
    report_lines.append("     transformed into percentages using the inverse-logit function.")
    report_lines.append("")
    report_lines.append("4. Heterogeneity (I^2 Statistic):")
    report_lines.append("   - I^2 measures the percentage of total variation across studies due to true heterogeneity")
    report_lines.append("     rather than chance. Values of 0-25% indicate low heterogeneity, 25-50% moderate,")
    report_lines.append("     and >75% high heterogeneity.")
    report_lines.append("--------------------------------------------------------------------------------")
    report_lines.append("")
    report_lines.append("INDIVIDUAL STUDY 2x2 CONTINGENCY TABLES:")
    report_lines.append("--------------------------------------------------------------------------------")
    report_lines.append(f"{'PMID':<10} | {'STUDY':<28} | {'TOTAL':<6} | {'TP':<4} | {'FN':<4} | {'TN':<5} | {'FP':<4} | {'SENS (%)':<9} | {'SPEC (%)'}")
    report_lines.append("--------------------------------------------------------------------------------")
    for t in tables:
        report_lines.append(
            f"{t['pmid']:<10} | {t['author_year']:<28} | {t['total']:<6} | {t['tp']:<4} | {t['fn']:<4} | {t['tn']:<5} | {t['fp']:<4} | {t['reported_sens']:<9.1f} | {t['reported_spec']:.2f}"
        )
    report_lines.append("--------------------------------------------------------------------------------")
    report_lines.append("")
    report_lines.append("POOLED META-ANALYSIS RESULTS:")
    report_lines.append("--------------------------------------------------------------------------------")
    report_lines.append(f"1. POOLED SENSITIVITY:")
    report_lines.append(f"   - Pooled Estimate:  {res_sens['pooled_pct']:.2f}% (95% CI: {res_sens['ci_lower']:.2f}% to {res_sens['ci_upper']:.2f}%)")
    report_lines.append(f"   - Between-Study Var (Tau^2): {res_sens['tau2']:.4f}")
    report_lines.append(f"   - Heterogeneity (I^2):       {res_sens['I2']:.1f}% (Cochran's Q = {res_sens['Q']:.2f}, df = {res_sens['df']})")
    report_lines.append("")
    report_lines.append(f"2. POOLED SPECIFICITY:")
    report_lines.append(f"   - Pooled Estimate:  {res_spec['pooled_pct']:.2f}% (95% CI: {res_spec['ci_lower']:.2f}% to {res_spec['ci_upper']:.2f}%)")
    report_lines.append(f"   - Between-Study Var (Tau^2): {res_spec['tau2']:.4f}")
    report_lines.append(f"   - Heterogeneity (I^2):       {res_spec['I2']:.1f}% (Cochran's Q = {res_spec['Q']:.2f}, df = {res_spec['df']})")
    report_lines.append("================================================================================")
    
    full_report = "\n".join(report_lines)
    
    # Save to meta_analysis_results.txt
    script_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(script_dir, "meta_analysis_results.txt")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_report)
        
    # Print report to terminal
    print("\n" + full_report)
    print(f"\nSaved meta-analysis results to: {output_path}")


if __name__ == "__main__":
    main()
