"""Interest-based corpus and evidence-based venue preference for a personal digest."""

import re
from datetime import datetime

from .protocol import CorpusPaper, Paper


CONFERENCE_PATTERN = re.compile(
    r"\b(?:NeurIPS|NIPS|ICML|ICLR|AAAI|IJCAI|ACL|EMNLP|NAACL|CVPR|ICCV|ECCV|"
    r"CHI|UIST|AAMAS|CoRL|ICRA|IROS|ACM MM|SIGGRAPH)\b|"
    r"neural information processing systems|international conference on machine learning|"
    r"learning representations|human factors in computing systems|"
    r"user interface software and technology|computer vision and pattern recognition|"
    r"association for computational linguistics|empirical methods in natural language|"
    r"autonomous agents and multiagent systems|ACM international conference on multimedia",
    re.IGNORECASE,
)


def interest_corpus(topics) -> list[CorpusPaper]:
    """Use explicit interests as the retrieval target without requiring Zotero."""
    return [
        CorpusPaper(title=topic.title, abstract=topic.abstract,
                    added_date=datetime.now(), paths=["Research interests"])
        for topic in topics
    ]


def author_conference_note(comment: str | None) -> str | None:
    """Retain explicit author-declared acceptance, distinct from venue records."""
    if not comment or not CONFERENCE_PATTERN.search(comment):
        return None
    if re.search(r"\b(?:submitted|submission|under review|rejected|workshop|companion)\b|not\s+accepted", comment, re.I):
        return None
    if not re.search(r"\b(?:accepted|to appear|published in)\b", comment, re.I):
        return None
    return comment.strip()[:500]


def is_conference(paper: Paper) -> bool:
    return paper.source == "conferences" or bool(CONFERENCE_PATTERN.search(paper.journal or "")) or bool(paper.author_venue_note)


def prioritize_venues(papers: list[Paper], bonus: float) -> list[Paper]:
    # Preserve the relevance score; venue priority only changes ordering.
    return sorted(papers, key=lambda p: (p.score or 0) + (bonus if is_conference(p) else 0), reverse=True)


def limit_journals(papers: list[Paper], maximum: int) -> list[Paper]:
    result = []
    journal_count = 0
    for paper in papers:
        journal = bool(paper.journal) and paper.is_preprint is False and not is_conference(paper)
        if journal:
            if journal_count >= maximum:
                continue
            journal_count += 1
        result.append(paper)
    return result


def deduplicate_research_papers(papers: list[Paper]) -> list[Paper]:
    """Collapse HF/arXiv copies, also merging independently indexed proceedings."""
    from .paper_identity import paper_identity

    seen_ids = {}
    seen_titles = {}
    result = []
    for paper in papers:
        identity = paper_identity(paper)
        title = re.sub(r"\W+", "", paper.title.casefold())
        winner = seen_ids.get(identity) or seen_titles.get(title)
        if winner is not None:
            winner.abstract = winner.abstract or paper.abstract
            winner.pdf_url = winner.pdf_url or paper.pdf_url
            if not winner.published_date and paper.published_date:
                winner.published_date = paper.published_date
                winner.publication_date_basis = paper.publication_date_basis
            winner.updated_date = winner.updated_date or paper.updated_date
            winner.author_venue_note = winner.author_venue_note or paper.author_venue_note
            if is_conference(paper) and not is_conference(winner):
                winner.journal = paper.journal
            continue
        if identity:
            seen_ids[identity] = paper
        if title:
            seen_titles[title] = paper
        result.append(paper)
    return result
