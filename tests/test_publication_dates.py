from datetime import datetime, timezone

from zotero_arxiv_daily.publication_dates import publication_date, crossref_publication_date, read_arxiv_dates
from zotero_arxiv_daily.protocol import Paper
from zotero_arxiv_daily.construct_email import render_email
from zotero_arxiv_daily.retriever.huggingface_retriever import HuggingFaceRetriever


def test_dates_preserve_source_precision_and_reject_invalid_days():
    assert publication_date("2026") == "2026"
    assert publication_date("2026-10") == "2026-10"
    assert publication_date("2026-02-30") is None
    assert publication_date(datetime(2026, 10, 16, tzinfo=timezone.utc)) == "2026-10-16"
    assert crossref_publication_date({"indexed": {"date-time": "2026-10-17"}, "published": {"date-parts": [[2026, 7]]}}) == "2026-07"
    assert crossref_publication_date({"issued": {"date-parts": [[2013, 6, 3]]}, "published-online": {"date-parts": [[2026, 10, 17]]}}) == "2013-06-03"


def test_hf_uses_paper_first_publication_not_daily_recommendation_date():
    retriever = object.__new__(HuggingFaceRetriever)
    paper = retriever.convert_to_paper({"submittedOnDailyAt": "2026-10-17T00:00:00Z", "paper": {
        "id": "2610.00001", "title": "Agent", "publishedAt": "2026-10-08T17:42:00Z", "updatedAt": "2026-10-16T09:00:00Z"}})
    assert paper.published_date == "2026-10-08"
    assert paper.updated_date == "2026-10-16"


def test_arxiv_history_keeps_first_release_separate_from_latest_version():
    paper = Paper(source="arxiv", title="Agent", authors=[], abstract="", url="https://arxiv.org/abs/2610.00001", score=5)
    read_arxiv_dates(paper, '<meta name="citation_date" content="2026/10/16"><div>[v1] Thu, 8 Oct 2026 17:42:00 UTC<br>[v2] Fri, 16 Oct 2026 09:00:00 UTC</div>')
    assert paper.published_date == "2026-10-08"
    assert paper.updated_date == "2026-10-16"
    html = render_email([paper])
    assert "发布时间（arXiv 首次发布）：2026-10-08" in html
    assert "最近更新：2026-10-16" in html
    assert "非质量分" in html


def test_missing_date_is_explicit_and_not_replaced_by_today():
    paper = Paper(source="arxiv", title="Agent", authors=[], abstract="", url="https://arxiv.org/abs/2610.00001")
    assert "发布时间（论文发表）：未取得，见论文页面" in render_email([paper])
