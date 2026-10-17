from .protocol import Paper
import math
from html import escape
import re
import base64


class EmailHTML(str):
    def __new__(cls, content, inline_images=()):
        value = super().__new__(cls, content)
        value.inline_images = list(inline_images)
        return value

    def standalone(self):
        content = str(self)
        for cid, data, mime in self.inline_images:
            content = content.replace(f'src="cid:{cid}"', f'src="data:{mime};base64,{base64.b64encode(data).decode("ascii")}"')
        return content


def format_digest(text):
    if not text:
        return "暂无解读"
    if "【" not in text:
        return escape(text).replace("\n", "<br>")
    parts = re.split(r"(【[^】\n]{1,30}】)", text)
    html = []
    for part in parts:
        if not part.strip():
            continue
        if part.startswith("【") and part.endswith("】"):
            html.append('<div style="margin-top:14px;color:#243b53;font-weight:bold;">' + escape(part) + '</div>')
        else:
            html.append('<div style="line-height:1.8;margin-top:4px;">' + escape(part.strip()).replace("\n", "<br>") + '</div>')
    return "".join(html)


framework = """
<!DOCTYPE HTML>
<html>
<head>
  <style>
    .star-wrapper {
      font-size: 1.3em; /* 调整星星大小 */
      line-height: 1; /* 确保垂直对齐 */
      display: inline-flex;
      align-items: center; /* 保持对齐 */
    }
    .half-star {
      display: inline-block;
      width: 0.5em; /* 半颗星的宽度 */
      overflow: hidden;
      white-space: nowrap;
      vertical-align: middle;
    }
    .full-star {
      vertical-align: middle;
    }
  </style>
</head>
<body>

<div>
    __CONTENT__
</div>

<br><br>
<div>
To unsubscribe, remove your email in your Github Action setting.
</div>

</body>
</html>
"""

_PIN_BADGE = '<span style="display:inline-block;font-size:12px;font-weight:600;color:#b8860b;background:#fff8e1;border:1px solid #ffe082;border-radius:4px;padding:2px 8px;margin-right:8px;vertical-align:middle;">&#128204; Pinned</span>'
_SECTION_HEADER = '<div style="font-size:16px;font-weight:bold;color:#444;margin:12px 0 6px 0;padding-bottom:4px;border-bottom:2px solid #eee;">{text}</div>'

def get_empty_html():
  block_template = """
  <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
  <tr>
    <td style="font-size: 20px; font-weight: bold; color: #333;">
        No Papers Today. Take a Rest!
    </td>
  </tr>
  </table>
  """
  return block_template

def get_block_html(
    title: str,
    authors: str,
    rate: str | float,
    tldr: str | None,
    pdf_url: str,
    affiliations: str | None = None,
    pinned: bool = False,
    figure_html: str = "",
) -> str:
    badge = _PIN_BADGE if pinned else ''
    block_template = """
    <table border="0" cellpadding="0" cellspacing="0" width="100%" style="font-family: Arial, sans-serif; border: 1px solid #ddd; border-radius: 8px; padding: 16px; background-color: #f9f9f9;">
    <tr>
        <td style="font-size: 20px; font-weight: bold; color: #333;">
            {badge}{title}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #666; padding: 8px 0;">
            {authors}
            <br>
            <i>{affiliations}</i>
        </td>
    </tr>
    <tr>
        <td>{figure_html}</td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>Relevance:</strong> {rate}
        </td>
    </tr>
    <tr>
        <td style="font-size: 14px; color: #333; padding: 8px 0;">
            <strong>论文解读：</strong> {tldr}
        </td>
    </tr>

    <tr>
        <td style="padding: 8px 0;">
            <a href="{pdf_url}" style="display: inline-block; text-decoration: none; font-size: 14px; font-weight: bold; color: #fff; background-color: #d9534f; padding: 8px 16px; border-radius: 4px;">PDF</a>
        </td>
    </tr>
</table>
"""
    return block_template.format(badge=badge, title=title, authors=authors,rate=rate, tldr=format_digest(tldr), pdf_url=pdf_url, affiliations=affiliations, figure_html=figure_html)

def get_stars(score:float):
    full_star = '<span class="full-star">⭐</span>'
    half_star = '<span class="half-star">⭐</span>'
    low = 6
    high = 8
    if score <= low:
        return ''
    elif score >= high:
        return full_star * 5
    else:
        interval = (high-low) / 10
        star_num = math.ceil((score-low) / interval)
        full_star_num = int(star_num/2)
        half_star_num = star_num - full_star_num * 2
        return '<div class="star-wrapper">'+full_star * full_star_num + half_star * half_star_num + '</div>'


def _render_paper_block(p:Paper, pinned:bool=False) -> str:
    rate = round(p.score, 1) if p.score is not None else 'Unknown'
    author_list = [a for a in p.authors]
    num_authors = len(author_list)
    if num_authors <= 5:
        authors = ', '.join(author_list)
    else:
        authors = ', '.join(author_list[:3] + ['...'] + author_list[-2:])
    if p.affiliations is not None:
        affiliations = p.affiliations[:5]
        affiliations = ', '.join(affiliations)
        if len(p.affiliations) > 5:
            affiliations += ', ...'
    else:
        affiliations = 'Unknown Affiliation'
    metadata = escape(p.journal or ("预印本，会议录用状态未确认" if p.is_preprint else ""))
    source = escape(p.source)
    paper_link = '<div style="margin:6px 0;color:#666;font-size:13px;">来源：' + source
    if metadata:
        paper_link += ' · ' + metadata
    if p.author_venue_note:
        paper_link += ' · 会议信息（作者声明）：' + escape(p.author_venue_note)
    date_label = p.publication_date_basis or "论文发表"
    paper_link += ' · 发布时间（' + escape(date_label) + '）：' + escape(p.published_date or "未取得，见论文页面")
    if p.updated_date and p.updated_date != p.published_date:
        paper_link += ' · 最近更新：' + escape(p.updated_date)
    if p.selection_reason:
        paper_link += ' · 入选依据：' + escape(p.selection_reason)
    if p.reading_basis is not None and not (p.tldr or "").startswith("【阅读依据】"):
        paper_link += ' · 阅读依据：' + escape(p.reading_basis)
    paper_link += ' · <a href="' + escape(p.url, quote=True) + '">论文页面</a></div>'
    if p.source == "huggingface":
        paper_id = p.url.rsplit("/", 1)[-1]
        paper_link += '<a href="https://huggingface.co/papers/' + escape(paper_id, quote=True) + '">Hugging Face 讨论</a>'
    figure_html = ""
    if p.main_figure is not None:
        figure = p.main_figure
        figure_html = ('<div style="margin:12px 0;"><a href="' + escape(figure.url, quote=True) + '">'
                       '<img src="cid:' + figure.cid + '" alt="论文主图" style="display:block;width:100%;max-width:800px;height:auto;"></a>'
                       '<div style="font-size:12px;line-height:1.6;color:#666;margin-top:8px;">原文图注：' + escape(figure.caption) + '</div></div>')
    elif p.reading_basis is not None:
        figure_html = '<div style="font-size:12px;color:#666;">未取得可用主图，可通过文末 PDF 链接查看原文。</div>'
    block = get_block_html(p.title, authors, rate, p.tldr, p.pdf_url or p.url, affiliations, pinned=pinned, figure_html=figure_html)
    return paper_link + block.replace("<strong>Relevance:</strong>", "<strong>主题相似度（非质量分）:</strong>")


def render_email(papers:list[Paper]) -> str:
    if len(papers) == 0 :
        return framework.replace('__CONTENT__', get_empty_html())

    # Keyword-pinned papers are expected to come first in `papers` (the executor
    # prepends them). Render them under a distinct header so they're clearly
    # separated from the algorithm's recommendations.
    pinned = [p for p in papers if getattr(p, "pinned", False)]
    others = [p for p in papers if not getattr(p, "pinned", False)]

    parts = []
    images = []
    for index, paper in enumerate(papers):
        if paper.main_figure:
            paper.main_figure.cid = f"paper-figure-{index}"
            images.append((paper.main_figure.cid, paper.main_figure.content, paper.main_figure.mime_type))
    if pinned:
        parts.append(_SECTION_HEADER.format(text="&#128204; Pinned by keywords"))
        parts.extend(_render_paper_block(p, pinned=True) for p in pinned)
        if others:
            parts.append(_SECTION_HEADER.format(text="Recommended for you"))
    parts.extend(_render_paper_block(p, pinned=False) for p in others)

    content = '<br>' + '</br><br>'.join(parts) + '</br>'
    return EmailHTML(framework.replace('__CONTENT__', content), images)
