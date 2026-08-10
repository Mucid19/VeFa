#!/usr/bin/env python3
"""
ABOUTME: Wikipedia API client for encyclopedic search and citation lookup
ABOUTME: Completely free and open REST API with no API key requirement
"""

import logging
from typing import Optional, Dict, Any, List
import requests
from urllib.parse import quote
from .base import BaseAPIClient

logger = logging.getLogger(__name__)


class WikipediaClient(BaseAPIClient):
    """
    Wikipedia API client for search and article summary retrieval.
    Supports English and Turkish Wikipedia endpoints.
    """

    def __init__(
        self,
        language: str = "tr",
        rate_limit_per_second: float = 5.0,
        timeout: int = 10,
        max_retries: int = 2,
    ):
        """
        Initialize Wikipedia API client.

        Args:
            language: 'tr' or 'en'
            rate_limit_per_second: Request rate limit
            timeout: Timeout in seconds
            max_retries: Retry count
        """
        base_url = f"https://{language}.wikipedia.org/w/api.php"
        super().__init__(
            base_url=base_url,
            rate_limit_per_second=rate_limit_per_second,
            timeout=timeout,
            max_retries=max_retries,
        )
        self.language = language

    def search_paper(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search Wikipedia for a query and return formatted metadata.

        Args:
            query: Search term

        Returns:
            Dict containing title, snippet, url, authors, year, journal="Wikipedia"
        """
        # Step 1: Search Wikipedia titles
        search_params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "format": "json",
            "srlimit": 3,
        }
        res = self._make_request(method="GET", params=search_params)
        if not res or "query" not in res or not res["query"].get("search"):
            # Fallback to English Wikipedia if TR returns no results
            if self.language != "en":
                logger.debug(f"Wikipedia (TR): No results for '{query[:40]}', trying EN Wikipedia...")
                en_client = WikipediaClient(language="en")
                return en_client.search_paper(query)
            return None

        search_results = res["query"]["search"]
        top_item = search_results[0]
        page_title = top_item.get("title", "")
        snippet = top_item.get("snippet", "").replace('<span class="searchmatch">', '').replace('</span>', '')

        # Step 2: Fetch page extract (summary)
        summary_params = {
            "action": "query",
            "prop": "extracts",
            "exintro": True,
            "explaintext": True,
            "titles": page_title,
            "format": "json",
        }
        summary_res = self._make_request(method="GET", params=summary_params)
        abstract_text = snippet
        if summary_res and "query" in summary_res:
            pages = summary_res["query"].get("pages", {})
            for page_id, page_info in pages.items():
                if "extract" in page_info and page_info["extract"]:
                    abstract_text = page_info["extract"][:800]
                    break

        page_url = f"https://{self.language}.wikipedia.org/wiki/{quote(page_title.replace(' ', '_'))}"
        import datetime
        current_year = datetime.datetime.now().year

        return {
            "title": page_title,
            "authors": ["Wikipedia Katkıda Bulunanları"],
            "year": current_year,
            "url": page_url,
            "doi": None,
            "journal": f"Wikipedia ({self.language.upper()})",
            "publisher": "Wikimedia Foundation",
            "abstract": abstract_text,
            "source_type": "encyclopedia",
            "confidence": 0.80,
            "source": "Wikipedia",
        }
