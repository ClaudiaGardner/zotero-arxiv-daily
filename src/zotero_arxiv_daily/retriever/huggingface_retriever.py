"""Retrieve Hugging Face Daily Papers through its public Hub endpoint."""

from datetime import datetime, timedelta, timezone

import requests
from loguru import logger

from .base import BaseRetriever, register_retriever
from ..protocol import Paper
from ..publication_dates import publication_date


@register_retriever("huggingface")
class HuggingFaceRetriever(BaseRetriever):
    def _retrieve_raw_papers(self):
        papers = []
        # The overlap covers weekends and is suppressed by persistent sent-state.
        today = datetime.now(timezone.utc).date()
        for offset in range(self.retriever_config.get("lookback_days", 3)):
            try:
                response = requests.get("https://huggingface.co/api/daily_papers",
                                        params={"date": (today - timedelta(days=offset)).isoformat()},
                                        timeout=(10, 30))
                response.raise_for_status()
                papers.extend(response.json())
            except (requests.RequestException, ValueError):
                logger.warning("Hugging Face daily papers unavailable for offset {}", offset)
        return papers

    def convert_to_paper(self, raw):
        paper = raw.get("paper", {})
        paper_id = paper.get("id")
        if not paper_id or not paper.get("title"):
            return None
        return Paper(source=self.name, title=paper["title"],
                     abstract=paper.get("summary") or "",
                     authors=[a.get("name", "") for a in paper.get("authors", [])],
                     url=f"https://arxiv.org/abs/{paper_id}",
                     pdf_url=f"https://arxiv.org/pdf/{paper_id}", is_preprint=True,
                     published_date=publication_date(paper.get("publishedAt")),
                     updated_date=publication_date(paper.get("updatedAt")),
                     publication_date_basis="arXiv 首次发布")
