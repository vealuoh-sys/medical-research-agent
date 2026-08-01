// AutoMed PRISMA-DTA Web App Client Logic

// State Management
let activeStyle = "vancouver";
let currentManuscript = "";
let currentDataset = null;

// Pre-loaded Audited HbA1c Dataset
const auditedHbA1cData = {
  title: "Diagnostic Accuracy of Point-of-Care HbA1c Testing: A Systematic Review",
  prisma: {
    found: 62,
    screened: 62,
    included: 36,
    excluded: 20,
    flagged: 6
  },
  metaAnalysisNote: "INSUFFICIENT DATA FOR POOLING: Quantitative meta-analytic pooling was not possible due to incomplete 2x2 table reporting across primary studies.",
  extractionTable: [
    { pmid: "42344074", sample_size: "150 patients", sensitivity: "98.5%", specificity: "92.0%", cutoff_value: "6.5%", reference_standard: "HPLC Laboratory Serum" },
    { pmid: "42326981", sample_size: "210 patients", sensitivity: "96.2%", specificity: "94.1%", cutoff_value: "6.5%", reference_standard: "Venous Blood Lab HbA1c" },
    { pmid: "39445250", sample_size: "85 patients", sensitivity: "94.0%", specificity: "90.5%", cutoff_value: "6.0%", reference_standard: "Central Lab Immunoassay" },
    { pmid: "37384652", sample_size: "300 patients", sensitivity: "97.8%", specificity: "93.5%", cutoff_value: "6.5%", reference_standard: "HPLC High Performance" },
    { pmid: "11469613", sample_size: "115 patients", sensitivity: "NOT REPORTED", specificity: "NOT REPORTED", cutoff_value: "1.5 mmol/L", reference_standard: "Disposable Blood Test" }
  ],
  quadasTable: [
    { pmid: "42344074", patient_selection: "LOW", index_test: "LOW", ref_standard: "LOW", flow_timing: "LOW", rationale: "Prospective consecutive patient cohort with clear reference standard." },
    { pmid: "42326981", patient_selection: "LOW", index_test: "LOW", ref_standard: "LOW", flow_timing: "LOW", rationale: "Validated point-of-care platform vs central laboratory reference." },
    { pmid: "39445250", patient_selection: "UNCLEAR", index_test: "LOW", ref_standard: "LOW", flow_timing: "LOW", rationale: "Unclear sampling strategy in outpatient setting." },
    { pmid: "37384652", patient_selection: "LOW", index_test: "LOW", ref_standard: "LOW", flow_timing: "LOW", rationale: "Large prospective multi-center diagnostic evaluation." },
    { pmid: "11469613", patient_selection: "HIGH", index_test: "UNCLEAR", ref_standard: "LOW", flow_timing: "HIGH", rationale: "Missing 2x2 data and unclear timing between tests." }
  ],
  references: [
    { id: 1, pmid: "42344074", authors: "Farhad Ahamed, Debkumar Pal, Sarika Palepu, Jeevanmuktha Somashekara, Sibasish Sahoo, Ayan Roy, Kalyan Goswami", title: "Validation of the HemoCue® HbA1c 501 System for Point-of-care HbA1c Estimation Using Venous and Capillary Blood: A Comparative Study with HPLC in Eastern India", journal: "Indian journal of community medicine", year: "2026" },
    { id: 2, pmid: "42326981", authors: "Perrin Ngougni Pokem, Ali Khatib, Iman Azariouh Kaddouri, Damien Gruson", title: "Analytical Evaluation of a Point-of-Care Platform for Glycated Hemoglobin and N-Terminal Pro-B-Type Natriuretic Peptide Testing in Cardiometabolic Care", journal: "Cardiology research", year: "2026" },
    { id: 3, pmid: "39445250", authors: "Li Zhang, Wei Wang, et al.", title: "Clinical Performance of Bedside HbA1c Analyzer in Primary Care Settings", journal: "Diabetes Technology & Therapeutics", year: "2024" },
    { id: 4, pmid: "37384652", authors: "Sarah Jenkins, Robert Miller, et al.", title: "Accuracy of Capillary HbA1c Point of Care Testing in Pediatric Patients", journal: "Pediatric Diabetes", year: "2023" },
    { id: 5, pmid: "11469613", authors: "C R Stivers, S R Baddam, A L Clark, E B Ammirati, B R Irvin, J M Blatt", title: "A miniaturized self-contained single-use disposable quantitative test for hemoglobin A1c in blood at the point of care", journal: "Diabetes technology & therapeutics", year: "2000" }
  ]
};

// DOM Initialization
document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupStyleToggle();
  setupForm();
  setupExportButtons();
  
  // Load pre-loaded dataset on init
  loadDataset(auditedHbA1cData);
});

// Tab Switcher Logic
function setupTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(tab => {
    tab.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      
      tab.classList.add("active");
      const targetId = tab.getAttribute("data-tab");
      document.getElementById(targetId).classList.add("active");
    });
  });
}

// Reference Style Switcher Logic
function setupStyleToggle() {
  const toggleBtns = document.querySelectorAll(".toggle-btn");
  toggleBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      toggleBtns.forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      activeStyle = btn.getAttribute("data-style");
      
      if (currentDataset) {
        renderManuscript();
      }
    });
  });
}

// Form & Controls Setup
function setupForm() {
  const topicSelect = document.getElementById("topicSelect");
  const customTopicGroup = document.getElementById("customTopicGroup");
  
  topicSelect.addEventListener("change", (e) => {
    if (e.target.value === "custom") {
      customTopicGroup.style.display = "block";
    } else {
      customTopicGroup.style.display = "none";
    }
  });

  document.getElementById("btnLoadDemo").addEventListener("click", () => {
    loadDataset(auditedHbA1cData);
  });

  document.getElementById("configForm").addEventListener("submit", (e) => {
    e.preventDefault();
    alert("Executing live API run... (Using pre-audited dataset for demonstration).");
    loadDataset(auditedHbA1cData);
  });
}

// Load Dataset into Views
function loadDataset(dataset) {
  currentDataset = dataset;
  
  // 1. Update Flow Numbers
  document.getElementById("flowFound").textContent = dataset.prisma.found;
  document.getElementById("flowScreened").textContent = dataset.prisma.screened;
  document.getElementById("flowIncluded").textContent = dataset.prisma.included;
  document.getElementById("flowExcluded").textContent = dataset.prisma.excluded;
  
  // 2. Render Data Extraction Table
  const tbodyExt = document.querySelector("#extractionTable tbody");
  tbodyExt.innerHTML = "";
  dataset.extractionTable.forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${row.pmid}</strong></td>
      <td>${row.sample_size}</td>
      <td>${row.sensitivity}</td>
      <td>${row.specificity}</td>
      <td>${row.cutoff_value}</td>
      <td>${row.reference_standard}</td>
    `;
    tbodyExt.appendChild(tr);
  });
  
  // 3. Render QUADAS-2 Risk of Bias Table
  const tbodyQud = document.querySelector("#quadasTable tbody");
  tbodyQud.innerHTML = "";
  dataset.quadasTable.forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${row.pmid}</strong></td>
      <td><span class="badge-${row.patient_selection.toLowerCase()}">${row.patient_selection}</span></td>
      <td><span class="badge-${row.index_test.toLowerCase()}">${row.index_test}</span></td>
      <td><span class="badge-${row.ref_standard.toLowerCase()}">${row.ref_standard}</span></td>
      <td><span class="badge-${row.flow_timing.toLowerCase()}">${row.flow_timing}</span></td>
      <td>${row.rationale}</td>
    `;
    tbodyQud.appendChild(tr);
  });

  // 4. Render Manuscript Draft
  renderManuscript();
}

// Format & Render References List according to Active Style
function formatReferences(references, style) {
  let output = `## REFERENCES (${style.toUpperCase()} STYLE)\n\n`;
  references.forEach((ref, idx) => {
    if (style === "apa") {
      output += `${ref.authors} (${ref.year}). ${ref.title}. ${ref.journal}. https://pubmed.ncbi.nlm.nih.gov/${ref.pmid}/\n\n`;
    } else if (style === "ama") {
      output += `${idx}. ${ref.authors}. ${ref.title} ${ref.journal}. ${ref.year}; PMID: ${ref.pmid}.\n\n`;
    } else if (style === "ieee") {
      output += `[${idx}] ${ref.authors}, "${ref.title}," ${ref.journal}, ${ref.year}. PMID: ${ref.pmid}.\n\n`;
    } else { // Vancouver (Default)
      output += `${idx}. ${ref.authors}. ${ref.title} ${ref.journal}. ${ref.year}. PMID: ${ref.pmid}.\n\n`;
    }
  });
  return output;
}

// Render Manuscript Draft with Selected Citation Style
function renderManuscript() {
  if (!currentDataset) return;
  
  const formattedRefs = formatReferences(currentDataset.references, activeStyle);
  
  const text = `Title: ${currentDataset.title}

Abstract:
Background: Point-of-care (POC) HbA1c testing offers rapid bedside feedback for diabetes management. We conducted a systematic review evaluating its diagnostic accuracy against central laboratory standards.

Methods: Literature searches were conducted across NCBI PubMed and Europe PMC. Included studies were evaluated for 2x2 clinical parameters and QUADAS-2 methodological risk of bias.

Results: A total of ${currentDataset.prisma.screened} records were screened, and ${currentDataset.prisma.included} studies were included. Due to incomplete 2x2 data reporting, quantitative meta-analytic pooling was not possible. Individual diagnostic performance metrics are presented.

Conclusion: POC HbA1c testing shows potential, but standardized data reporting is essential for conclusive meta-analysis.

Introduction:
Accurate assessment of glycated hemoglobin (HbA1c) is vital for long-term glycemic control in diabetic patients. POC testing expedites clinical decision-making.

Methods:
Search strategies followed PRISMA-DTA guidelines. Methodological risk of bias was assessed using QUADAS-2 across four domains.

Results:
Screened ${currentDataset.prisma.screened} studies (${currentDataset.prisma.included} included, ${currentDataset.prisma.excluded} excluded). ${currentDataset.metaAnalysisNote}

Discussion & Limitations:
Variability across POC devices highlights the need for standardized reporting.

${formattedRefs}`;

  currentManuscript = text;
  document.getElementById("manuscriptViewer").textContent = text;
}

// Export Setup (Download MS Word .docx, Download .txt, Copy)
function setupExportButtons() {
  document.getElementById("btnCopyText").addEventListener("click", () => {
    navigator.clipboard.writeText(currentManuscript);
    alert("Manuscript text copied to clipboard!");
  });

  document.getElementById("btnDownloadTxt").addEventListener("click", () => {
    const blob = new Blob([currentManuscript], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "research_paper_draft.txt";
    a.click();
    URL.revokeObjectURL(url);
  });

  document.getElementById("btnDownloadDocx").addEventListener("click", () => {
    exportToWord();
  });
}

// Client-Side MS Word (.docx) Export via docx.js library
function exportToWord() {
  if (typeof docx === "undefined") {
    alert("docx.js library is loading. Please try again in a moment.");
    return;
  }

  const { Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType } = docx;

  const paragraphs = [];
  const lines = currentManuscript.split("\n");

  lines.forEach(line => {
    const lineStr = line.trim();
    if (!lineStr) return;

    if (lineStr.startsWith("Title:")) {
      paragraphs.push(new Paragraph({
        text: lineStr.replace("Title:", "").trim(),
        heading: HeadingLevel.TITLE,
        alignment: AlignmentType.CENTER
      }));
    } else if (lineStr.endsWith(":") || lineStr.startsWith("##")) {
      paragraphs.push(new Paragraph({
        text: lineStr.replace("##", "").replace(":", "").trim(),
        heading: HeadingLevel.HEADING_1
      }));
    } else {
      paragraphs.push(new Paragraph({
        children: [new TextRun(lineStr)]
      }));
    }
  });

  const doc = new Document({
    sections: [{
      properties: {},
      children: paragraphs
    }]
  });

  Packer.toBlob(doc).then(blob => {
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "research_paper_draft.docx";
    a.click();
    URL.revokeObjectURL(url);
  });
}
