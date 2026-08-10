#!/usr/bin/env python3
"""
ABOUTME: DuckDuckGo Search API client for free web search
ABOUTME: Requires no API key and provides web search results via DuckDuckGo
"""

import logging
import re
from typing import Optional, Dict, Any, List
import requests
from bs4 import BeautifulSoup
from urllib.parse import unquote, urlparse
from .base import BaseAPIClient, USER_AGENTS

logger = logging.getLogger(__name__)


class DuckDuckGoClient(BaseAPIClient):
    """
    DuckDuckGo client for free web search without API keys.
    """

    def __init__(
        self,
        rate_limit_per_second: float = 2.0,
        timeout: int = 10,
        max_retries: int = 2,
    ):
        """
        Initialize DuckDuckGo Client.
        """
        super().__init__(
            base_url="https://html.duckduckgo.com",
            rate_limit_per_second=rate_limit_per_second,
            timeout=timeout,
            max_retries=max_retries,
        )

    def search_paper(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Search DuckDuckGo web results and return top result formatted as a source.

        Args:
            query: Search query string

        Returns:
            Dict containing title, url, snippet, year, publisher, authors, etc.
        """
        headers = {
            "User-Agent": USER_AGENTS[0],
            "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://html.duckduckgo.com/",
        }

        try:
            # Request DuckDuckGo HTML search page
            res = requests.post(
                "https://html.duckduckgo.com/html/",
                data={"q": query, "b": ""},
                headers=headers,
                timeout=self.timeout,
            )

            if res.status_code != 200 or not res.text:
                logger.debug(f"DuckDuckGo returned status {res.status_code}")
                return None

            soup = BeautifulSoup(res.text, "html.parser")
            results = soup.find_all("div", class_=re.compile(r"result\s+results_links"))
            if not results:
                # Try generic result class
                results = soup.find_all("a", class_="result__url")
                if not results:
                    return None

            for result in soup.find_all("div", class_="result"):
                title_elem = result.find("a", class_="result__a")
                snippet_elem = result.find("a", class_="result__snippet")
                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                raw_url = title_elem.get("href", "")
                snippet = snippet_elem.get_text(strip=True) if snippet_elem else ""

                # Extract actual target URL from DuckDuckGo redirect link
                url = raw_url
                if "/l/?" in raw_url:
                    match = re.search(r"uddg=([^&]+)", raw_url)
                    if match:
                        url = unquote(match.group(1))

                # Determine publisher from URL domain
                domain = urlparse(url).netloc.replace("www.", "")
                import datetime
                current_year = datetime.datetime.now().year

                return {
                    "title": title,
                    "authors": [f"{domain.capitalize()} Editörleri"],
                    "year": current_year,
                    "url": url,
                    "doi": None,
                    "journal": domain,
                    "publisher": domain,
                    "abstract": snippet[:800],
                    "source_type": "web",
                    "confidence": 0.75,
                    "source": "DuckDuckGo",
                }

        except Exception as e:
            logger.warning(f"DuckDuckGo search error: {e}")
            return None

        return None
