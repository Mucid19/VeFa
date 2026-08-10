# -*- coding: utf-8 -*-
"""
VeFa - Canlı Akademik Veritabanı Arama Modülü (Live Academic Search)
CrossRef ve Semantic Scholar açık akademik API'lerini kullanarak gerçek makale,
yazar, yıl, dergi ve DOI bilgilerini canlı olarak sorgular ve LLM'e besler.
"""

import requests
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)


def search_crossref(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search CrossRef Open API for academic publications with fast 5s timeout.
    """
    url = f"https://api.crossref.org/works?query={requests.utils.quote(query)}&rows={max_results}"
    headers = {"User-Agent": "VeFa-AcademicAssistant/2.0 (mailto:academic@vefa.app)"}
    results = []

    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            items = data.get("message", {}).get("items", [])
            for item in items:
                title_list = item.get("title", [])
                title = title_list[0] if title_list else ""
                
                authors = []
                for a in item.get("author", []):
                    given = a.get("given", "")
                    family = a.get("family", "")
                    name = f"{family}, {given}".strip(", ")
                    if name:
                        authors.append(name)

                issued = item.get("issued", {}).get("date-parts", [[None]])
                year = issued[0][0] if issued and issued[0] else None

                container_list = item.get("container-title", [])
                journal = container_list[0] if container_list else "Akademik Dergi"

                doi = item.get("DOI", "")
                link = item.get("URL", f"https://doi.org/{doi}" if doi else "")

                if title:
                    results.append({
                        "title": title,
                        "authors": authors or ["Bilinmeyen Yazar"],
                        "year": year or 2023,
                        "journal": journal,
                        "doi": doi,
                        "url": link,
                        "source": "CrossRef"
                    })
    except Exception as e:
        logger.warning(f"CrossRef API search error: {e}")

    return results


def search_semantic_scholar(query: str, max_results: int = 5) -> List[Dict[str, Any]]:
    """
    Search Semantic Scholar Open API for academic papers with fast 5s timeout.
    """
    url = f"https://api.semanticscholar.org/graph/v1/paper/search?query={requests.utils.quote(query)}&limit={max_results}&fields=title,authors,year,venue,abstract,externalIds"
    headers = {"User-Agent": "VeFa-AcademicAssistant/2.0"}
    results = []

    try:
        r = requests.get(url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            items = data.get("data", [])
            for item in items:
                title = item.get("title", "")
                authors = [a.get("name", "") for a in item.get("authors", []) if a.get("name")]
                year = item.get("year")
                venue = item.get("venue") or "Academic Journal"
                abstract = item.get("abstract", "")
                doi = item.get("externalIds", {}).get("DOI", "")

                if title:
                    results.append({
                        "title": title,
                        "authors": authors or ["Bilinmeyen Yazar"],
                        "year": year or 2023,
                        "journal": venue,
                        "abstract": abstract[:100] if abstract else "",
                        "doi": doi,
                        "source": "Semantic Scholar"
                    })
    except Exception as e:
        logger.warning(f"Semantic Scholar API search error: {e}")

    return results


def fetch_live_academic_context(topic: str, max_items: int = 6) -> str:
    """
    Perform live search on CrossRef & Semantic Scholar, combine and format into a compact context string.
    """
    query_tr = topic
    
    crossref_items = search_crossref(query_tr, max_results=max_items)
    semantic_items = search_semantic_scholar(query_tr, max_results=max_items)

    combined_items = crossref_items + semantic_items
    
    seen_titles = set()
    unique_items = []
    for item in combined_items:
        t_clean = item["title"].lower().strip()
        if t_clean not in seen_titles:
            seen_titles.add(t_clean)
            unique_items.append(item)
            if len(unique_items) >= max_items:
                break

    if not unique_items:
        return ""

    context_lines = ["\n### CANLI AKADEMİK VERİTABANI TARAMASI SONUÇLARI (CrossRef & Semantic Scholar):\n"]
    for idx, item in enumerate(unique_items, 1):
        authors_str = ", ".join(item["authors"][:3])
        if len(item["authors"]) > 3:
            authors_str += " ve ark."
        
        line = f"{idx}. **{item['title']}** ({item['year']}). {authors_str}. *{item['journal']}*."
        if item.get("doi"):
            line += f" DOI: {item['doi']}"
        context_lines.append(line)

    return "\n".join(context_lines)
