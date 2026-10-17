"""Source publication dates, never discovery or recommendation timestamps."""

from datetime import date, datetime
from email.utils import parsedate_to_datetime
from html import unescape
from html.parser import HTMLParser
import re

import requests

from .protocol import Paper


def publication_date(value) -> str | None:
    if isinstance(value, (date, datetime)):
        return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    if not isinstance(value, str):
        return None
    value = value.strip().replace("/", "-")
    match = re.fullmatch(r"(\d{4})(?:-(\d{2})(?:-(\d{2}))?)?(?:T.*)?", value)
    if not match:
        return None
    year, month, day = match.groups()
    try:
        date(int(year), int(month or 1), int(day or 1))
    except ValueError:
        return None
    return "-".join(part for part in (year, month, day) if part is not None)


def crossref_publication_date(raw) -> str | None:
    dates = []
    for key in ("issued", "published", "published-online", "published-print"):
        parts = raw.get(key, {}).get("date-parts", [])
        if parts and 1 <= len(parts[0]) <= 3:
            value = "-".join(f"{int(part):0{4 if i == 0 else 2}d}" for i, part in enumerate(parts[0]))
            if result := publication_date(value):
                if key == "issued":
                    return result  # Crossref's earliest known publication date.
                dates.append(result)
    return min(dates) if dates else None


class _CitationMetadata(HTMLParser):
    def __init__(self):
        super().__init__()
        self.values = {}

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if tag == "meta" and values.get("name", "").startswith("citation_"):
            self.values[values["name"]] = values.get("content", "")


def read_arxiv_dates(paper: Paper, source: str) -> None:
    metadata = _CitationMetadata()
    metadata.feed(source)
    text = unescape(re.sub(r"<[^>]+>", " ", source))
    history = re.findall(r"\[v(\d+)\]\s*(\w{3},\s*\d{1,2}\s+\w{3}\s+\d{4}\s+\d{2}:\d{2}:\d{2}\s+(?:UTC|GMT))", text)
    versions = {int(version): parsedate_to_datetime(stamp).date().isoformat() for version, stamp in history}
    first = versions.get(1) or publication_date(metadata.values.get("citation_date"))
    if first:
        paper.published_date = first
        paper.publication_date_basis = "arXiv 首次发布"
    if versions:
        paper.updated_date = versions[max(versions)]
    venue = metadata.values.get("citation_conference_title") or metadata.values.get("citation_journal_title")
    if venue and not paper.journal:
        paper.journal = venue


def enrich_publication_date(paper: Paper) -> None:
    if paper.published_date:
        return
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", paper.url)
    if not match:
        return
    paper_id = match.group(1).removesuffix(".pdf")
    try:
        response = requests.get(f"https://arxiv.org/abs/{paper_id}", timeout=(8, 20))
        response.raise_for_status()
        read_arxiv_dates(paper, response.text)
    except (requests.RequestException, ValueError):
        # Missing publication dates are displayed explicitly, never fabricated.
        return
