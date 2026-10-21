"""Bounded concurrent enrichment for papers selected for final output."""

from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol

from loguru import logger
from omegaconf import DictConfig

from . import llm as llm_transport
from .llm import LlmValue
from .protocol import Paper


class FullTextRetriever(Protocol):
    def fetch_full_text(self, paper: Paper) -> str | None: ...


def enrich_final_papers(
    papers: list[Paper],
    retrievers: Mapping[str, FullTextRetriever],
    client: llm_transport.LlmClient,
    llm_params: Mapping[str, LlmValue] | DictConfig,
    workers: int,
) -> list[Paper]:
    """Fetch missing text and generate one digest per paper in input order."""
    if not papers:
        return []

    worker_count = max(1, min(workers, len(papers)))
    detailed = llm_params.get("analysis_depth") == "detailed"
    if detailed:
        from .deep_reading import fetch_reading_text
        # PyMuPDF does not support concurrent threads. Read PDFs on the caller
        # thread before launching the concurrent LLM requests.
        for paper in papers:
            if paper.full_text is None or not paper.full_text.strip():
                try:
                    paper.full_text = fetch_reading_text(paper)
                except Exception as error:
                    logger.warning(
                        "reading_text failure source={} exception_type={}",
                        paper.source,
                        type(error).__name__,
                    )
                    paper.full_text = None
        logger.info("Detailed reading complete: {}/{} papers with body text, {}/{} with main figures",
                    sum(bool(p.full_text) for p in papers), len(papers),
                    sum(p.main_figure is not None for p in papers), len(papers))

    def enrich_one(paper: Paper) -> Paper:
        from .publication_dates import enrich_publication_date
        if llm_params.get("include_publication_dates", False):
            enrich_publication_date(paper)
        if not detailed and (paper.full_text is None or not paper.full_text.strip()):
            retriever = retrievers.get(paper.source)
            if retriever is not None:
                try:
                    paper.full_text = retriever.fetch_full_text(paper)
                except Exception as error:
                    logger.warning(
                        "final_enrichment full_text_failure source={} exception_type={}",
                        paper.source,
                        type(error).__name__,
                    )
        _ = paper.generate_tldr_and_affiliations(client, llm_params)
        if (llm_params.get("retry_failed_digest", False)
                and llm_params.get("digest_format") == "concise_academic"
                and not all(heading in (paper.tldr or "") for heading in ("【Motivation】", "【方法】", "【创新点】"))):
            logger.info("Retrying incomplete academic digest: {}", paper.title)
            _ = paper.generate_tldr_and_affiliations(client, llm_params)
        return paper

    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        return list(executor.map(enrich_one, papers))
