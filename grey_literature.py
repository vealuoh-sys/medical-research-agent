"""
grey_literature.py — Trial registry + recent preprint coverage.

Neither source works like PubMed/Europe PMC, so neither is merged into the
main paper list. They're saved as separate, clearly-labeled files:

- ClinicalTrials.gov: real keyword search, no API key needed. Surfaces
  trials that are ongoing or completed but never published — this is what
  grey-literature searching is actually for (catching publication bias).

- bioRxiv/medRxiv: IMPORTANT — the public API has no keyword search endpoint
  at all, only date-range browsing. This function pulls a recent window
  (default 180 days) and filters locally by title/abstract keyword match.
  That means it covers RECENT preprints only, not the full archive. This
  is a real limitation of the source, not a shortcut taken here — stated
  plainly in the output file so it's never mistaken for a full search.
"""

import json
import re
import time
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

from systematic_search import create_http_request


# ==============================================================================
# SECTION 1: ClinicalTrials.gov (real keyword search, v2 REST API)
# ==============================================================================
def search_clinical_trials(topic, max_results=20):
    print(f"  -> ClinicalTrials.gov querying: '{topic}' (max {max_results} results)...")
    base_url = "https://clinicaltrials.gov/api/v2/studies"
    params = {
        "query.term": topic,
        "pageSize": max_results,
        "format": "json",
    }
    full_url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        with create_http_request(full_url) as response:
            data = json.loads(response.read().decode("utf-8"))

        trials = []
        for study in data.get("studies", []):
            protocol = study.get("protocolSection", {})
            ident = protocol.get("identificationModule", {})
            status = protocol.get("statusModule", {})
            design = protocol.get("designModule", {})

            trials.append({
                "nct_id": ident.get("nctId", "UNKNOWN"),
                "title": ident.get("briefTitle", "No title"),
                "status": status.get("overallStatus", "UNKNOWN"),
                "phase": ", ".join(design.get("phases", [])) or "N/A",
                "url": f"https://clinicaltrials.gov/study/{ident.get('nctId', '')}",
            })
        print(f"     Found {len(trials)} registered trials.")
        return trials
    except Exception as e:
        print(f"     ClinicalTrials.gov query note: {e}")
        return []


def save_clinical_trials(trials, topic, filename="clinical_trials_registry.txt"):
    lines = [
        f"CLINICAL TRIAL REGISTRY SEARCH: {topic}",
        "=" * 70,
        f"Source: ClinicalTrials.gov (real keyword search, {len(trials)} results)",
        "",
        "Purpose: identifies ongoing or completed-but-unpublished trials on this",
        "topic — relevant for assessing publication bias. These are registry",
        "entries, not published papers, and are NOT included in the screening,",
        "extraction, or meta-analysis stages.",
        "",
    ]
    if not trials:
        lines.append("No registered trials found matching this topic.")
    else:
        for t in trials:
            lines.append(f"- {t['nct_id']} | {t['status']} | Phase: {t['phase']}")
            lines.append(f"  {t['title']}")
            lines.append(f"  {t['url']}")
            lines.append("")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True, filename


# ==============================================================================
# SECTION 2: bioRxiv / medRxiv (date-range browsing only — no keyword search)
# ==============================================================================
def _tokenize(text):
    return set(re.findall(r"[a-zA-Z][a-zA-Z\-]{2,}", text.lower()))


def search_recent_preprints(topic, servers=("biorxiv", "medrxiv"), days_back=180, max_per_server=200):
    topic_terms = _tokenize(topic)
    end_date = datetime.utcnow().date()
    start_date = end_date - timedelta(days=days_back)

    matches = []
    for server in servers:
        cursor = 0
        pulled = 0
        while pulled < max_per_server:
            url = f"https://api.biorxiv.org/details/{server}/{start_date}/{end_date}/{cursor}"
            try:
                with create_http_request(url) as response:
                    data = json.loads(response.read().decode("utf-8"))
            except Exception as e:
                print(f"     {server} query note: {e}")
                break

            records = data.get("collection", [])
            if not records:
                break

            for r in records:
                text = (r.get("title", "") + " " + r.get("abstract", ""))
                if topic_terms & _tokenize(text):
                    matches.append({
                        "server": server,
                        "doi": r.get("doi", ""),
                        "title": r.get("title", "No title"),
                        "date": r.get("date", ""),
                        "url": f"https://doi.org/{r.get('doi', '')}",
                    })

            pulled += len(records)
            cursor += 100
            time.sleep(0.2)
            if len(records) < 100:
                break  # last page for this server

    print(f"  -> Preprint scan: {len(matches)} keyword matches across {servers} in the last {days_back} days.")
    return matches


def save_recent_preprints(matches, topic, days_back, filename="recent_preprints.txt"):
    lines = [
        f"RECENT PREPRINT SCAN: {topic}",
        "=" * 70,
        f"Source: bioRxiv / medRxiv, last {days_back} days only",
        "",
        "IMPORTANT LIMITATION: bioRxiv/medRxiv's public API has no keyword",
        "search — this list was built by pulling every preprint posted in the",
        "date window above and filtering locally for topic keyword matches.",
        "It does NOT cover the full preprint archive, only the recent window.",
        "These are unreviewed preprints, not peer-reviewed papers, and are",
        "NOT included in screening, extraction, or meta-analysis.",
        "",
    ]
    if not matches:
        lines.append("No keyword matches found in this window.")
    else:
        for m in matches:
            lines.append(f"- [{m['server']}] {m['date']} | {m['title']}")
            lines.append(f"  {m['url']}")
            lines.append("")

    with open(filename, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return True, filename
