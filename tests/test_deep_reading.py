import json

import requests
import tiktoken

from tests import make_recording_client
from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.paper_generation import _build_messages
from zotero_arxiv_daily.deep_reading import fetch_reading_text, full_text_excerpt
from zotero_arxiv_daily.construct_email import format_digest


def test_detailed_digest_requests_methods_metrics_limitations_and_preserves_basis():
    paper = make_sample_paper(full_text="Full paper: Method M beats baseline by 12% on game G.")
    paper.reading_basis = "Full text"
    client, calls = make_recording_client(json.dumps({"tldr": "【核心方法】M\n【实验与证据】12% on G", "affiliations": []}))
    digest, _ = paper.generate_tldr_and_affiliations(client, {"analysis_depth": "detailed"})
    prompt = calls[0]["messages"][1]["content"]
    assert "【核心方法】" in prompt and "【实验与证据】" in prompt and "【局限与边界】" in prompt
    assert "Do not invent numbers" in prompt
    assert digest.startswith("【阅读依据】Full text")
    assert len(calls) == 1


def test_full_text_excerpt_includes_late_results_instead_of_only_intro():
    encoding = tiktoken.encoding_for_model("gpt-4o")
    text = "Introduction\n" + "intro " * 15000 + "\n4 Experiments\nRESULT_MARKER\nWin rate 72%.\n5 Limitations\nLIMIT_MARKER\nOnly tested in one game."
    excerpt = full_text_excerpt(text, encoding, 3000)
    assert "RESULT_MARKER" in excerpt and "LIMIT_MARKER" in excerpt
    assert len(encoding.encode(excerpt)) <= 3000


def test_detailed_prompt_keeps_results_within_input_budget():
    paper = make_sample_paper(full_text="intro " * 20000 + "\n4 Experiments\nRESULT_MARKER\nWinning rate 72%.")
    messages = _build_messages(paper, {"analysis_depth": "detailed", "max_input_tokens": 4000})
    assert "RESULT_MARKER" in messages[1]["content"]
    assert len(tiktoken.encoding_for_model("gpt-4o").encode(messages[1]["content"])) <= 4000


def test_failed_fulltext_is_marked_abstract_only(monkeypatch):
    def unavailable(*a, **k): raise requests.ConnectionError("unavailable")
    monkeypatch.setattr(requests, "get", unavailable)
    paper = make_sample_paper(url="https://arxiv.org/abs/2610.12345", pdf_url="https://arxiv.org/pdf/2610.12345")
    assert fetch_reading_text(paper) is None
    assert paper.reading_basis == "仅摘要（全文未取得）"


def test_sectioned_email_escapes_generated_html():
    html = format_digest("【核心方法】\n<script>bad()</script>\n【实验与证据】\nWin rate 72%")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
    assert "Win rate 72%" in html


def test_pdf_reading_runs_on_calling_thread_before_parallel_generation(monkeypatch):
    import threading
    from zotero_arxiv_daily import deep_reading
    from zotero_arxiv_daily.final_enrichment import enrich_final_papers
    caller = threading.get_ident()
    reads = []
    def read(paper):
        assert threading.get_ident() == caller
        reads.append(paper.title)
        return "Full paper text"
    monkeypatch.setattr(deep_reading, "fetch_reading_text", read)
    papers = [make_sample_paper(title=str(i), full_text=None) for i in range(3)]
    client, calls = make_recording_client()
    enrich_final_papers(papers, {}, client, {"analysis_depth": "detailed"}, workers=3)
    assert reads == ["0", "1", "2"]
    assert len(calls) == 3


def test_concise_academic_note_contains_only_requested_sections():
    paper = make_sample_paper(full_text="Method M addresses inefficient game planning.")
    text = "【Motivation】Planning is inefficient.\n【核心方法】M plans with a learned model.\n【创新点】M reuses predicted states.\n【讨论】Unrequested discussion."
    client, _ = make_recording_client(json.dumps({"tldr": text, "affiliations": []}))
    digest, _ = paper.generate_tldr_and_affiliations(client, {"analysis_depth": "detailed", "digest_format": "concise_academic"})
    assert digest.count("【") == 3
    assert "M plans with a learned model." in digest
    assert "Unrequested discussion" not in digest
