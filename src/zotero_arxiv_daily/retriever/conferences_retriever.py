"""Discover recently indexed proceedings for configured AI and HCI venues."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import re

import requests
from loguru import logger

from .base import BaseRetriever, register_retriever
from .crossref_metadata import clean_crossref_text
from ..protocol import Paper
from ..research_preferences import CONFERENCE_PATTERN
from ..publication_dates import crossref_publication_date


@register_retriever("conferences")
class ConferencesRetriever(BaseRetriever):
    def _retrieve_raw_papers(self):
        published_since = (datetime.now(timezone.utc) - timedelta(days=self.retriever_config.get("publication_lookback_days", 90))).date().isoformat()
        today = datetime.now(timezone.utc).date().isoformat()

        def retrieve(venue):
            try:
                response = requests.get("https://api.crossref.org/works", params={
                    "filter": f"from-pub-date:{published_since},until-pub-date:{today}",
                    "query.container-title": venue,
                    "sort": "score", "order": "desc", "rows": 100,
                    "mailto": self.retriever_config.mailto,
                }, timeout=(10, 40))
                response.raise_for_status()
                # Search is fuzzy: require independently matching venue metadata.
                items = response.json()["message"]["items"]
                matched = [item for item in items
                           if item.get("type") in {"proceedings-article", "book-chapter"}
                           and CONFERENCE_PATTERN.search(" ".join(item.get("container-title", [])))
                           and not re.search(r"workshop|companion|extended abstracts|adjunct", " ".join(item.get("container-title", [])), re.I)
                           and (not crossref_publication_date(item) or published_since <= crossref_publication_date(item) <= today)]
                logger.info("Conference query={} returned={} matched={} sample_venues={}", venue, len(items), len(matched),
                            [item.get("container-title", []) for item in items[:2]])
                return matched
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
                     journal="; ".join(raw.get("container-title", [])), is_preprint=False,
                     published_date=crossref_publication_date(raw),
                     publication_date_basis="会议论文发表")
