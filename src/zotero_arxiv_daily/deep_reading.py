"""Read paper HTML/PDF for a detailed research digest."""

import re

import requests
import trafilatura
from loguru import logger

from .protocol import Paper


def fetch_reading_text(paper: Paper) -> str | None:
    html_text = None
    match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", paper.url)
    if match:
        paper_id = match.group(1).removesuffix(".pdf")
        try:
            response = requests.get(f"https://arxiv.org/html/{paper_id}", timeout=(8, 25))
            response.raise_for_status()
            from .paper_figures import html_main_figure
            paper.main_figure = html_main_figure(response.text, response.url)
            text = trafilatura.extract(response.text, include_tables=True, include_comments=False)
            if text and len(text) > 1500:
                html_text = text
                paper.reading_basis = "正文（arXiv HTML；长文按方法、实验等段落选取）"
                if paper.main_figure is not None:
                    return text
        except (requests.RequestException, ValueError):
            pass
    if paper.pdf_url:
        try:
            import pymupdf

            with requests.get(paper.pdf_url, timeout=(8, 35), stream=True) as response:
                response.raise_for_status()
                content = bytearray()
                for chunk in response.iter_content(65536):
                    content.extend(chunk)
                    if len(content) > 25 * 1024 * 1024:
                        raise ValueError("PDF exceeds reading download limit")
            with pymupdf.open(stream=bytes(content), filetype="pdf") as document:
                from .paper_figures import pdf_main_figure
                if paper.main_figure is None:
                    paper.main_figure = pdf_main_figure(document, paper.pdf_url)
                # Read the main paper and the last pages for limitations/conclusions.
                pages = sorted(set(range(min(24, len(document)))) | set(range(max(0, len(document) - 3), len(document))))
                text = "\n\n".join(document[p].get_text(sort=True) for p in pages)
            if len(text.strip()) > 1500:
                if html_text is None:
                    paper.reading_basis = "全文片段（PDF，含主要正文及末尾页面）"
                return html_text or text
        except (requests.RequestException, ValueError, RuntimeError):
            pass
    if html_text:
        return html_text
    paper.reading_basis = "仅摘要（全文未取得）"
    logger.info("Detailed reading uses abstract only: {}", paper.title)
    return None


def full_text_excerpt(text, encoding, budget):
    tokens = encoding.encode(text, disallowed_special=())
    if len(tokens) <= budget:
        return text
    # Keep methods/results/limitations instead of spending the context on the intro.
    headings = list(re.finditer(
        r"(?im)^\s*(?:#{1,6}\s*)?(?:\d+(?:\.\d+)*[.\s]+)?"
        r"(?:method(?:ology)?|approach|experiment(?:al)?(?:s| setup)?|results|evaluation|"
        r"ablation(?: studies)?|discussion|limitations|conclusion)\b[^\n]{0,90}$", text,
    ))
    if not headings:
        allocations = [budget // 4] * 4
        starts = [0, len(tokens) // 3, len(tokens) * 2 // 3, max(0, len(tokens) - allocations[-1])]
        return "\n\n[正文节选]\n\n".join(encoding.decode(tokens[start:start + size]) for start, size in zip(starts, allocations))
    intro_budget = budget // 5
    pieces = [encoding.decode(tokens[:intro_budget])]
    selected = headings[:8]
    section_budget = max(1, (budget - intro_budget - 100) // len(selected))
    for heading in selected:
        next_heading = next((h.start() for h in headings if h.start() > heading.start()), len(text))
        section = text[heading.start():next_heading]
        pieces.append(encoding.decode(encoding.encode(section, disallowed_special=())[:section_budget]))
    return "\n\n[正文节选]\n\n".join(pieces)
