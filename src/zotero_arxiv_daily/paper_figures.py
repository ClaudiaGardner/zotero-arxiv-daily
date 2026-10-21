"""Select a representative paper figure and prepare it for inline email."""

import re
from urllib.parse import urljoin

import pymupdf
import requests
from loguru import logger
from lxml import html

from .protocol import PaperFigure


def figure_score(caption, index):
    score = 3 if index == 0 else 0
    score += 8 if re.search(r"overview|framework|architecture|pipeline|workflow|system design|proposed method", caption, re.I) else 0
    score -= 4 if re.search(r"ablation|learning curve|hyperparameter", caption, re.I) else 0
    return score


def _jpeg(pixmap):
    if pixmap.alpha or pixmap.n > 3:
        pixmap = pymupdf.Pixmap(pymupdf.csRGB, pixmap)
    if pixmap.alpha:
        pixmap = pymupdf.Pixmap(pixmap, 0)
    scale = min(1, 1200 / max(pixmap.width, 1), 1100 / max(pixmap.height, 1))
    if scale < 1:
        pixmap = pymupdf.Pixmap(pixmap, pixmap.width * scale, pixmap.height * scale)
    for quality in (88, 75, 65):
        content = pixmap.tobytes("jpg", jpg_quality=quality)
        if len(content) <= 400_000:
            return content
    pixmap = pymupdf.Pixmap(pixmap, pixmap.width * 0.75, pixmap.height * 0.75)
    content = pixmap.tobytes("jpg", jpg_quality=80)
    return content if len(content) <= 400_000 else None


def html_main_figure(document_html, base_url):
    tree = html.fromstring(document_html)
    candidates = []
    for index, element in enumerate(tree.xpath("//figure[.//img]")[:10]):
        images = element.xpath(".//img/@src")
        # Multi-panel figures are handled from the PDF to preserve all panels.
        if len(images) != 1:
            continue
        caption = " ".join(" ".join(element.xpath(".//figcaption//text()")).split())
        if not caption:
            continue
        candidates.append((figure_score(caption, index), caption, urljoin(base_url, images[0])))
    for _, caption, url in sorted(candidates, key=lambda c: c[0], reverse=True)[:3]:
        try:
            response = requests.get(url, timeout=(8, 20))
            response.raise_for_status()
            if len(response.content) > 10 * 1024 * 1024:
                continue
            try:
                content = _jpeg(pymupdf.Pixmap(response.content))
            except Exception as error:
                # PyMuPDF raises FzErrorFormat for corrupt/truncated images,
                # and it is not a RuntimeError. A missing figure must never
                # abort the whole digest.
                logger.info("Skipping undecodable HTML figure image: {}", type(error).__name__)
                continue
            if content:
                return PaperFigure(content, "image/jpeg", caption, url)
        except (requests.RequestException, ValueError, RuntimeError):
            continue
    return None


def pdf_main_figure(document, source_url):
    candidates = []
    for page_number in range(min(6, len(document))):
        page = document[page_number]
        blocks = page.get_text("blocks")
        for block in blocks:
            if block[6] != 0 or not re.match(r"^\s*(?:Figure|Fig\.)\s*\d+\s*[:.]", block[4], re.I):
                continue
            caption_box = pymupdf.Rect(block[:4])
            caption = " ".join(block[4].split())
            graphics = [pymupdf.Rect(image["bbox"]) for image in page.get_image_info()]
            graphics += [drawing["rect"] for drawing in page.get_drawings()]
            wide_graphic = any(rect.width > page.rect.width * 0.55 and rect.height > 5
                               and rect.y1 <= caption_box.y0 + 2 and rect.y0 >= caption_box.y0 - 380
                               for rect in graphics)
            whole_width = caption_box.width > page.rect.width * 0.55 or wide_graphic
            left = 25 if whole_width else max(20, caption_box.x0 - 10)
            right = page.rect.width - 25 if whole_width or caption_box.x0 > page.rect.width / 2 else page.rect.width / 2 - 10
            region = pymupdf.Rect(left, max(25, caption_box.y0 - 380), right, caption_box.y0 + 2)
            graphics = [rect for rect in graphics if rect.get_area() > 100 and region.contains(rect) and rect.width > 5 and rect.height > 5]
            if not graphics:
                continue
            clip = pymupdf.Rect(graphics[0])
            for rectangle in graphics[1:]:
                clip |= rectangle
            clip = (clip + (-12, -12, 12, 12)) & region
            if clip.width < 80 or clip.height < 50:
                continue
            number = int(re.search(r"\d+", caption).group())
            candidates.append((figure_score(caption, number - 1), page_number, clip, caption))
    for _, page_number, clip, caption in sorted(candidates, key=lambda c: c[0], reverse=True):
        try:
            content = _jpeg(document[page_number].get_pixmap(matrix=pymupdf.Matrix(2, 2), clip=clip, alpha=False))
        except Exception as error:
            logger.info("Skipping undecodable PDF figure: {}", type(error).__name__)
            continue
        if content:
            return PaperFigure(content, "image/jpeg", caption, source_url)
    return None
