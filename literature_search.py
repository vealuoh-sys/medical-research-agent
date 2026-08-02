import urllib.request
import urllib.parse
import urllib.error
import json
import xml.etree.ElementTree as ET
import sys
import os
import ssl

# ==============================================================================
# HELPER: Get SSL Context (Handles environments with local proxy/cert issues)
# ==============================================================================
def create_http_request(url):
    """Sends an HTTP GET request to the specified URL with SSL fallback."""
    req = urllib.request.Request(url, headers={'User-Agent': 'MedicalResearchAgent/1.0'})
    
    # 1. Try standard secure SSL verification first
    try:
        context = ssl.create_default_context()
        return urllib.request.urlopen(req, context=context, timeout=15)
    except urllib.error.URLError as e:
        # If failure is due to SSL certificate verification (e.g. proxy/firewall), fallback safely
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            context = ssl._create_unverified_context()
            return urllib.request.urlopen(req, context=context, timeout=15)
        raise e


# ==============================================================================
# SECTION 1: Get the Research Topic from the User
# ==============================================================================
# This section asks the user to type a medical topic into the terminal.
# If a topic was passed as a command-line argument (e.g., python literature_search.py "topic"),
# it will use that automatically.
def get_user_topic():
    if len(sys.argv) > 1:
        topic = " ".join(sys.argv[1:]).strip()
        print(f"Using topic provided in command line: '{topic}'")
        return topic
    
    try:
        topic = input("Enter a medical research topic to search on PubMed: ").strip()
        while not topic:
            print("Topic cannot be empty. Please try again.")
            topic = input("Enter a medical research topic to search on PubMed: ").strip()
        return topic
    except (KeyboardInterrupt, EOFError):
        print("\nSearch cancelled by user.")
        sys.exit(0)


# ==============================================================================
# SECTION 2: Search PubMed for Matching Article IDs (esearch)
# ==============================================================================
# This section contacts the PubMed API to get a list of article ID numbers (PMIDs)
# matching the user's search query. We request up to 20 results.
def search_pubmed_ids(topic, max_results=20):
    print(f"\nSearching PubMed for: '{topic}'...")
    
    # Base URL for PubMed's search API (esearch)
    esearch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    
    # Parameters sent to the search API
    params = {
        "db": "pubmed",
        "term": topic,
        "retmax": max_results,
        "retmode": "json"
    }
    
    # Encode parameters into URL format (e.g., space becomes %20)
    query_string = urllib.parse.urlencode(params)
    full_url = f"{esearch_url}?{query_string}"
    
    try:
        # Send HTTP request to PubMed
        with create_http_request(full_url) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        # Extract article IDs from the JSON response
        id_list = data.get("esearchresult", {}).get("idlist", [])
        return id_list
        
    except urllib.error.URLError as e:
        print(f"\nError connecting to PubMed: {e.reason}")
        print("Please check your internet connection and try again.")
        return None
    except Exception as e:
        print(f"\nAn unexpected error occurred while searching: {e}")
        return None


# ==============================================================================
# SECTION 3: Fetch Detailed Paper Metadata & Abstract (efetch)
# ==============================================================================
# Using the list of article ID numbers, this section retrieves full details
# for each article in XML format and extracts the title, authors, journal, year,
# abstract, and PMID.
def fetch_paper_details(id_list):
    if not id_list:
        return []
        
    print(f"Fetching details for {len(id_list)} articles...")
    
    # Base URL for PubMed's detail fetching API (efetch)
    efetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    
    params = {
        "db": "pubmed",
        "id": ",".join(id_list),
        "retmode": "xml"
    }
    
    query_string = urllib.parse.urlencode(params)
    full_url = f"{efetch_url}?{query_string}"
    
    try:
        with create_http_request(full_url) as response:
            xml_data = response.read()
            
        # Parse the XML response
        root = ET.fromstring(xml_data)
        papers = []
        
        # Loop through each article in the XML response
        for article in root.findall(".//PubmedArticle"):
            # 1. Extract PMID
            pmid_elem = article.find(".//MedlineCitation/PMID")
            pmid = pmid_elem.text.strip() if pmid_elem is not None and pmid_elem.text else "N/A"
            
            # 2. Extract Title (combining inner text tags if any exist)
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
                    # Often MedlineDate starts with the year, e.g., "2021 Nov-Dec"
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
                
            # Build paper dictionary
            paper_data = {
                "pmid": pmid,
                "title": title,
                "authors": authors,
                "journal": journal,
                "publication_year": year,
                "abstract": abstract
            }
            papers.append(paper_data)
            
        return papers
        
    except urllib.error.URLError as e:
        print(f"\nError downloading details from PubMed: {e.reason}")
        print("Please check your internet connection and try again.")
        return []
    except ET.ParseError as e:
        print(f"\nFailed to parse PubMed response data: {e}")
        return []
    except Exception as e:
        print(f"\nAn unexpected error occurred while fetching details: {e}")
        return []


# ==============================================================================
# SECTION 4: Save Results to JSON File
# ==============================================================================
# This section takes the list of paper details and saves them into a formatted
# 'results.json' file in the exact same folder as this script.
def save_to_json(data, filename="results.json"):
    try:
        # Determine the folder where this script lives
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, filename)
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True, file_path
    except IOError as e:
        print(f"\nError saving results to file '{filename}': {e}")
        return False, None


# ==============================================================================
# SECTION 5: Main Program Flow
# ==============================================================================
# Controls the step-by-step execution: prompt user -> search -> fetch -> save -> summarize.
def main():
    print("==================================================")
    print("          PubMed Literature Search Tool           ")
    print("==================================================")
    
    # Step 1: Get topic from user
    topic = get_user_topic()
    
    # Step 2: Search for matching PubMed IDs
    id_list = search_pubmed_ids(topic, max_results=20)
    
    if id_list is None:
        print("\nSearch could not be completed due to a connection or system error.")
        return
        
    if not id_list:
        print(f"\nNo papers were found for the topic: '{topic}'.")
        print("Tip: Try broader search terms or check for typos.")
        return
        
    print(f"Found {len(id_list)} matching article IDs. Retrieving article metadata...")
    
    # Step 3: Fetch paper details
    papers = fetch_paper_details(id_list)
    
    if not papers:
        print("\nFailed to retrieve article details. Please check your network connection.")
        return
        
    # Step 4: Save results to results.json
    success, saved_path = save_to_json(papers, filename="results.json")
    
    # Step 5: Print summary
    if success:
        print("\n--------------------------------------------------")
        print(f"SUCCESS: Found {len(papers)} papers, saved to results.json")
        print("--------------------------------------------------")
        print(f"Saved at: {saved_path}")
        print(f"Sample Paper 1 Title: {papers[0]['title']}")
        print(f"Sample Paper 1 PMID:  {papers[0]['pmid']}")
        print(f"Sample Paper 1 Year:  {papers[0]['publication_year']}")
        print("==================================================")


if __name__ == "__main__":
    main()
