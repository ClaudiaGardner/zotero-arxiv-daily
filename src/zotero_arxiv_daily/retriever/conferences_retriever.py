"""Discover recently indexed proceedings for configured AI and HCI venues."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

from .base import BaseRetriever, register_retriever
from .crossref_metadata import clean_crossref_text
from ..protocol import Paper
from ..research_preferences import CONFERENCE_PATTERN


@register_retriever("conferences")
class ConferencesRetriever(BaseRetriever):
    def _retrieve_raw_papers(self):
        since = (datetime.now(timezone.utc) - timedelta(days=self.retriever_config.lookback_days)).date().isoformat()
        published_since = (datetime.now(timezone.utc) - timedelta(days=30)).date().isoformat()

        def retrieve(venue):
            try:
                response = requests.get("https://api.crossref.org/works", params={
                    "filter": f"type:proceedings-article,from-index-date:{since},from-pub-date:{published_since}",
                    "query.container-title": venue,
                    "sort": "indexed", "order": "desc", "rows": 100,
                    "mailto": self.retriever_config.mailto,
                }, timeout=(10, 40))
                response.raise_for_status()
                # Search is fuzzy: require independently matching venue metadata.
                return [item for item in response.json()["message"]["items"]
                        if CONFERENCE_PATTERN.search(" ".join(item.get("container-title", [])))]
            except (requests.RequestException, ValueError, KeyError):
                logger.warning("Conference metadata unavailable for {}", venue)
                return []

        with ThreadPoolExecutor(max_workers=2) as pool:
            return [item for batch in pool.map(retrieve, self.retriever_config.venues) for item in batch]

    def convert_to_paper(self, raw):
        titles = raw.get("title", [])
        if not titles or not raw.get("DOI"):
            return None
        links = raw.get("link", [])
        pdf = next((link.get("URL") for link in links if link.get("content-type") == "application/pdf"), None)
        return Paper(source=self.name, title=clean_crossref_text(titles[0]),
                     abstract=clean_crossref_text(raw.get("abstract") or ""),
                     authors=[" ".join(filter(None, [a.get("given"), a.get("family")]))
                              for a in raw.get("author", [])],
                     url=f"https://doi.org/{raw['DOI']}", pdf_url=pdf, doi=raw["DOI"],
                     journal="; ".join(raw.get("container-title", [])), is_preprint=False)
