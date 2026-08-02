import json
import os
import sys
import urllib.request
import urllib.parse
import urllib.error
import ssl

# ==============================================================================
# SECTION 1: HTTP Helper (same SSL-fallback pattern as the rest of the pipeline)
# ==============================================================================
def create_http_request(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'MedicalResearchAgent/1.0'})
    try:
        context = ssl.create_default_context()
        return urllib.request.urlopen(req, context=context, timeout=20)
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            context = ssl._create_unverified_context()
            return urllib.request.urlopen(req, context=context, timeout=20)
        raise e


# ==============================================================================
# SECTION 2: Query the Directory of Open Access Journals (DOAJ) — free, no key
# ==============================================================================
# DOAJ only lists journals that have passed its editorial-quality vetting, so
# this never invents journal names — every result is a real, currently-listed
# open-access journal with a live homepage.
def search_doaj_journals(query, max_results=15):
    print(f"\nSearching DOAJ for open-access journals matching: '{query}'...")

    safe_query = urllib.parse.quote(query)
    url = f"https://doaj.org/api/search/journals/{safe_query}?pageSize={max_results}"

    try:
        with create_http_request(url) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as e:
        print(f"\nError connecting to DOAJ: {e.reason}")
        return None
    except Exception as e:
        print(f"\nAn unexpected error occurred while querying DOAJ: {e}")
        return None

    results = data.get("results", [])
    journals = []
    for item in results:
        bib = item.get("bibjson", {})
        title = bib.get("title", "Unknown Journal")
        publisher = bib.get("publisher", {}).get("name", "Unknown Publisher")

        apc = bib.get("apc", {})
        has_apc = apc.get("has_apc", None)
        apc_note = "No listed article-processing charge (free to publish)"
        if has_apc is True:
            amounts = apc.get("max", [])
            if amounts:
                amt = amounts[0]
                apc_note = f"Has an article-processing charge (~{amt.get('price', '?')} {amt.get('currency', '')})"
            else:
                apc_note = "Has an article-processing charge (amount not listed)"
        elif has_apc is False:
            apc_note = "No article-processing charge (free to publish)"

        homepage = ""
        for link in bib.get("link", []):
            if link.get("type") == "homepage":
                homepage = link.get("url", "")
                break

        issns = []
        for ident in bib.get("identifier", []):
            issns.append(f"{ident.get('type', '').upper()}: {ident.get('id', '')}")

        subjects = [s.get("term", "") for s in bib.get("subject", [])]

        journals.append({
            "title": title,
            "publisher": publisher,
            "apc_note": apc_note,
            "homepage": homepage,
            "issn": "; ".join(issns),
            "subjects": ", ".join(subjects[:5])
        })

    return journals


# ==============================================================================
# SECTION 3: Rank — free-to-publish journals first, since that matches a
# solo researcher's constraints; keep everything else after.
# ==============================================================================
def rank_journals(journals):
    free_journals = [j for j in journals if "No " in j["apc_note"] or "No article" in j["apc_note"] or "No listed" in j["apc_note"]]
    other_journals = [j for j in journals if j not in free_journals]
    return free_journals + other_journals


# ==============================================================================
# SECTION 4: Save Results
# ==============================================================================
def save_journal_suggestions(journals, query, filename="journal_suggestions.txt"):
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.join(script_dir, filename)

        lines = [
            "================================================================================",
            "         SUGGESTED JOURNALS FOR PUBLICATION (via DOAJ — verified, real listings)",
            "================================================================================",
            f"Search terms used: '{query}'",
            "Source: Directory of Open Access Journals (doaj.org) — every journal below is",
            "editorially vetted and currently indexed by DOAJ, not generated or guessed.",
            "",
        ]

        if not journals:
            lines.append("No matching journals were found in DOAJ for this topic.")
            lines.append("Try broadening the topic keywords, or search doaj.org manually.")
        else:
            for idx, j in enumerate(journals, 1):
                lines.append(f"{idx}. {j['title']}")
                lines.append(f"   Publisher: {j['publisher']}")
                lines.append(f"   Cost to publish: {j['apc_note']}")
                if j["issn"]:
                    lines.append(f"   {j['issn']}")
                if j["subjects"]:
                    lines.append(f"   Subjects: {j['subjects']}")
                if j["homepage"]:
                    lines.append(f"   Homepage: {j['homepage']}")
                lines.append("")

        lines.append("================================================================================")
        lines.append("Always confirm scope, current APC, and submission guidelines directly on the")
        lines.append("journal's own website before submitting — DOAJ listings can lag behind a")
        lines.append("journal's live policies.")

        with open(file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        return True, file_path
    except IOError as e:
        print(f"\nError saving journal suggestions to file '{filename}': {e}")
        return False, None


# ==============================================================================
# SECTION 5: Standalone CLI Entry Point
# ==============================================================================
def main():
    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:]).strip()
    else:
        query = input("Enter a topic/specialty to find open-access journals for: ").strip()

    journals = search_doaj_journals(query, max_results=15)
    if journals is None:
        print("\nCould not reach DOAJ. Please check your internet connection.")
        return

    ranked = rank_journals(journals)
    success, path = save_journal_suggestions(ranked, query, filename="journal_suggestions.txt")
    if success:
        print(f"\n[PASS] Found {len(ranked)} journals -> saved to {path}")
        free_count = sum(1 for j in ranked if "No " in j["apc_note"])
        print(f"  - {free_count} of these have no listed article-processing charge")


if __name__ == "__main__":
    main()
