import urllib.request
import urllib.parse
import urllib.error
import json
import xml.etree.ElementTree as ET
import sys
import os
import ssl
import time

# Reconfigure stdout/stderr on Windows to handle UTF-8 symbols (e.g. beta symbol β)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# ==============================================================================
# HELPER: SSL Request Handler (Handles proxies & self-signed certificates)
# ==============================================================================
def create_http_request(url):
    """Sends an HTTP GET request to the specified URL with SSL fallback."""
    req = urllib.request.Request(url, headers={'User-Agent': 'MedicalResearchAgent/1.0'})
    
    # 1. Try standard secure SSL verification first
    try:
        context = ssl.create_default_context()
        return urllib.request.urlopen(req, context=context, timeout=20)
    except urllib.error.URLError as e:
        # If failure is due to SSL certificate verification (e.g. proxy/firewall), fallback safely
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            context = ssl._create_unverified_context()
            return urllib.request.urlopen(req, context=context, timeout=20)
        raise e


# ==============================================================================
# SECTION 1: Search PubMed for a Single Query (esearch)
# ==============================================================================
# Contacts the PubMed API to get a list of article ID numbers (PMIDs) matching
# a given search term, requesting up to max_results (default 100).
def search_pubmed_ids(query_term, max_results=100):
    print(f"  -> PubMed Querying: '{query_term}' (max {max_results} results)...")
    
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    
    params = {
        "db": "pubmed",
        "term": query_term,
        "retmax": max_results,
        "retmode": "json"
    }
    
    query_string = urllib.parse.urlencode(params)
    full_url = f"{esearch_url}?{query_string}"
    
    try:
        with create_http_request(full_url) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        id_list = data.get("esearchresult", {}).get("idlist", [])
        print(f"     Found {len(id_list)} PubMed articles.")
        return id_list
        
    except urllib.error.URLError as e:
        print(f"     Error connecting to PubMed for '{query_term}': {e.reason}")
        return []
    except Exception as e:
        print(f"     Unexpected error: {e}")
        return []


def search_europe_pmc(query_term, max_results=50):
    """Queries Europe PMC REST API for multi-database literature coverage."""
    print(f"  -> Europe PMC Querying: '{query_term}' (max {max_results} results)...")
    base_url = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    params = {
        "query": query_term,
        "format": "json",
        "pageSize": max_results
    }
    query_string = urllib.parse.urlencode(params)
    full_url = f"{base_url}?{query_string}"
    
    try:
        with create_http_request(full_url) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        results = data.get("resultList", {}).get("result", [])
        pmids = []
        for r in results:
            pmid = r.get("pmid")
            if pmid:
                pmids.append(str(pmid).strip())
        print(f"     Found {len(pmids)} Europe PMC articles with PMIDs.")
        return pmids
    except Exception as e:
        print(f"     Europe PMC query note: {e}")
        return []


# ==============================================================================
# SECTION 2: Fetch Paper Metadata in Batches (efetch)
# ==============================================================================
# Downloads detailed XML metadata for a list of PMIDs in chunks (to prevent URL length limits)
# and extracts title, authors, journal, publication year, abstract, and PMID.
def fetch_paper_details_batch(id_list, batch_size=50):
    if not id_list:
        return []
        
    print(f"\nFetching detailed metadata for {len(id_list)} unique articles in batches...")
    
    efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    all_papers = []
    
    # Process ID list in chunks of batch_size (default 50)
    for i in range(0, len(id_list), batch_size):
        chunk_ids = id_list[i:i + batch_size]
        print(f"  -> Downloading batch {i // batch_size + 1}/{(len(id_list) - 1) // batch_size + 1} ({len(chunk_ids)} articles)...")
        
        params = {
            "db": "pubmed",
            "id": ",".join(chunk_ids),
            "retmode": "xml"
        }
        
        query_string = urllib.parse.urlencode(params)
        full_url = f"{efetch_url}?{query_string}"
        
        try:
            with create_http_request(full_url) as response:
                xml_data = response.read()
                
            root = ET.fromstring(xml_data)
            
            for article in root.findall(".//PubmedArticle"):
                # 1. Extract PMID
                pmid_elem = article.find(".//MedlineCitation/PMID")
                pmid = pmid_elem.text.strip() if pmid_elem is not None and pmid_elem.text else "N/A"
                
                # 2. Extract Title
                title_elem = article.find(".//Article/ArticleTitle")
                if title_elem is not None:
                    title = "".join(title_elem.itertext()).strip()
                else:
                    title = "No title available"
                    
                # 3. Extract Authors
                authors = []
                author_nodes = article.findall(".//AuthorList/Author")
                for auth in author_nodes:
                    last_name = auth.find("LastName")
                    fore_name = auth.find("ForeName")
                    collective_name = auth.find("CollectiveName")
                    
                    if fore_name is not None and last_name is not None:
                        authors.append(f"{fore_name.text} {last_name.text}")
                    elif last_name is not None:
                        authors.append(last_name.text)
                    elif collective_name is not None:
                        authors.append(collective_name.text)
                        
                if not authors:
                    authors = ["Author information unavailable"]
                    
                # 4. Extract Journal Name
                journal_elem = article.find(".//Journal/Title")
                if journal_elem is not None and journal_elem.text:
                    journal = journal_elem.text.strip()
                else:
                    iso_elem = article.find(".//Journal/ISOAbbreviation")
                    journal = iso_elem.text.strip() if iso_elem is not None and iso_elem.text else "Unknown Journal"
                    
                # 5. Extract Publication Year
                year = "Unknown"
                year_elem = article.find(".//JournalIssue/PubDate/Year")
                if year_elem is not None and year_elem.text:
                    year = year_elem.text.strip()
                else:
                    medline_date = article.find(".//JournalIssue/PubDate/MedlineDate")
                    if medline_date is not None and medline_date.text:
                        year = medline_date.text.strip()[:4]
                    else:
                        article_date_year = article.find(".//ArticleDate/Year")
                        if article_date_year is not None and article_date_year.text:
                            year = article_date_year.text.strip()
                            
                # 6. Extract Abstract
                abstract_paragraphs = []
                abstract_nodes = article.findall(".//Abstract/AbstractText")
                for ab_node in abstract_nodes:
                    label = ab_node.get("Label")
                    text = "".join(ab_node.itertext()).strip()
                    if label:
                        abstract_paragraphs.append(f"{label}: {text}")
                    else:
                        abstract_paragraphs.append(text)
                        
                if abstract_paragraphs:
                    abstract = "\n\n".join(abstract_paragraphs)
                else:
                    abstract = "No abstract available"
                    
                paper_data = {
                    "pmid": pmid,
                    "title": title,
                    "authors": authors,
                    "journal": journal,
                    "publication_year": year,
                    "abstract": abstract
                }
                all_papers.append(paper_data)
                
            # Respect NCBI API rate limit (3 requests per second limit without API key)
            time.sleep(0.4)
            
        except urllib.error.URLError as e:
            print(f"     Error downloading batch: {e.reason}")
        except ET.ParseError as e:
            print(f"     XML parse error for batch: {e}")
        except Exception as e:
            print(f"     Unexpected error in batch: {e}")
            
    return all_papers


# ==============================================================================
# SECTION 3: Save Results to JSON File
# ==============================================================================
# Saves the array of paper objects into 'systematic_results.json' in the script folder.
def save_to_json(data, filename="systematic_results.json"):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True, file_path
    except IOError as e:
        print(f"\nError saving results to file '{filename}': {e}")
        return False, None


# ==============================================================================
# SECTION 4: Main Program Execution
# ==============================================================================
def main():
    print("==================================================")
    print("    Systematic PubMed Multi-Query Search Tool     ")
    print("==================================================")
    
    # 4 targeted search queries to execute
    target_queries = [
        "point of care beta-hydroxybutyrate diabetic ketoacidosis diagnostic accuracy",
        "capillary ketone testing DKA sensitivity specificity",
        "breathomics diabetic ketoacidosis",
        "urine ketone blood ketone discordance"
    ]
    
    raw_pmids = []
    
    print("\nExecuting multi-database PubMed & Europe PMC searches...")
    for idx, query in enumerate(target_queries, 1):
        pubmed_ids = search_pubmed_ids(query, max_results=100)
        europe_ids = search_europe_pmc(query, max_results=50)
        raw_pmids.extend(pubmed_ids)
        raw_pmids.extend(europe_ids)
        # Gentle pause between searches for API compliance
        time.sleep(0.3)
        
    # Deduplicate PMIDs while preserving discovery order
    unique_pmids = list(dict.fromkeys(raw_pmids))
    
    print("\n--------------------------------------------------")
    print(f"SEARCH SUMMARY: Total raw PMIDs fetched: {len(raw_pmids)}")
    print(f"                Unique PMIDs (deduplicated across PubMed & Europe PMC): {len(unique_pmids)}")
    print("--------------------------------------------------")
    
    if not unique_pmids:
        print("No papers found across queries.")
        return
        
    # Fetch details in batches of 50
    papers = fetch_paper_details_batch(unique_pmids, batch_size=50)
    
    if not papers:
        print("\nFailed to retrieve paper details.")
        return
        
    # Save to systematic_results.json
    output_filename = "systematic_results.json"
    success, saved_path = save_to_json(papers, filename=output_filename)
    
    if success:
        print("\n==================================================")
        print(f"SUCCESS: Retrieved & saved {len(papers)} unique papers to {output_filename}")
        print("==================================================")
        print(f"File location: {saved_path}")
        sample_title = papers[0]['title'].encode('ascii', errors='replace').decode('ascii')
        print(f"Sample Article 1 Title: {sample_title}")
        print(f"Sample Article 1 PMID:  {papers[0]['pmid']}")
        print("==================================================")


if __name__ == "__main__":
    main()
