import email

import pymupdf

from tests.canned_responses import make_sample_paper, make_stub_smtp
from zotero_arxiv_daily.paper_figures import figure_score, pdf_main_figure
from zotero_arxiv_daily.protocol import PaperFigure
from zotero_arxiv_daily.construct_email import render_email
from zotero_arxiv_daily.utils import send_email


def test_framework_figure_preferred_over_ablation_plot():
    assert figure_score("Figure 2: Overview of the proposed framework", 1) > figure_score("Figure 1: Ablation learning curve", 0)


def test_pdf_diagram_is_cropped_with_caption_retained():
    with pymupdf.open() as document:
        page = document.new_page(width=600, height=800)
        page.draw_rect(pymupdf.Rect(40, 80, 550, 250), color=(0, 0, 1), fill=(0.9, 0.9, 1))
        page.insert_text((40, 270), "Figure 1: Overview of our agent framework.")
        figure = pdf_main_figure(document, "https://arxiv.org/pdf/2610.12345")
    assert figure is not None and figure.caption.startswith("Figure 1:")
    pixmap = pymupdf.Pixmap(figure.content)
    assert pixmap.width > pixmap.height
    assert figure.mime_type == "image/jpeg"


def test_inline_image_attachments_match_html_cids(config, monkeypatch):
    paper = make_sample_paper(tldr="【核心方法】A method.")
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 100), False)
    pixmap.clear_with(255)
    paper.main_figure = PaperFigure(pixmap.tobytes("jpg"), "image/jpeg", "Figure 1: Framework", paper.url)
    content = render_email([paper])
    assert "cid:paper-figure-0" in content
    assert "data:image/jpeg;base64," in content.standalone()
    sent = []
    import smtplib
    monkeypatch.setattr(smtplib, "SMTP", make_stub_smtp(sent))
    send_email(config, content)
    message = email.message_from_string(sent[0][2])
    figures = [part for part in message.walk() if part.get_content_maintype() == "image"]
    assert len(figures) == 1
    assert figures[0]["Content-ID"] == "<paper-figure-0>"
    assert figures[0].get_payload(decode=True) == paper.main_figure.content


def test_preview_image_ids_with_shared_prefixes_remain_distinct():
    from zotero_arxiv_daily.construct_email import EmailHTML
    import base64
    content = EmailHTML('<img src="cid:paper-figure-1"><img src="cid:paper-figure-10">',
                        [("paper-figure-1", b"first", "image/jpeg"), ("paper-figure-10", b"tenth", "image/jpeg")])
    preview = content.standalone()
    assert base64.b64encode(b"first").decode() + '"' in preview
    assert base64.b64encode(b"tenth").decode() + '"' in preview
