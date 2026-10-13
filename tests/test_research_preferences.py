from omegaconf import OmegaConf

from zotero_arxiv_daily.protocol import Paper
from zotero_arxiv_daily.research_preferences import (
    interest_corpus, deduplicate_research_papers, prioritize_venues, limit_journals,
)
from zotero_arxiv_daily.retriever.huggingface_retriever import HuggingFaceRetriever
from zotero_arxiv_daily.retriever.conferences_retriever import ConferencesRetriever


def paper(**kwargs):
    return Paper(source=kwargs.pop("source", "arxiv"), title=kwargs.pop("title", "Game agents"),
                 authors=[], abstract=kwargs.pop("abstract", "A game-playing agent."),
                 url=kwargs.pop("url", "https://arxiv.org/abs/2610.12345"), **kwargs)


def test_hf_and_arxiv_versions_collapse_and_merge_abstract():
    hf = paper(source="huggingface", abstract="", url="https://arxiv.org/abs/2610.12345")
    arxiv = paper(url="https://arxiv.org/abs/2610.12345v2", title="Game Agents!")
    assert deduplicate_research_papers([hf, arxiv]) == [hf]
    assert hf.abstract == arxiv.abstract


def test_conference_preference_preserves_relevance_and_does_not_infer_acceptance():
    confirmed = paper(source="conferences", score=5.2, journal="CHI 2026")
    preprint = paper(title="Better game agent", score=5.6, is_preprint=True)
    assert prioritize_venues([preprint, confirmed], 0.8) == [confirmed, preprint]
    assert confirmed.score == 5.2


def test_journals_capped_but_preprints_and_conferences_retained():
    journals = [paper(title=str(i), journal="Some Journal", is_preprint=False) for i in range(3)]
    accepted = paper(source="conferences", journal="CHI", is_preprint=False)
    preprint = paper(is_preprint=True)
    assert limit_journals(journals + [accepted, preprint], 1) == [journals[0], accepted, preprint]


def test_interest_corpus_does_not_require_zotero():
    topics = OmegaConf.create([{"title": "Game agents", "abstract": "World models"}])
    corpus = interest_corpus(topics)
    assert corpus[0].title == "Game agents"
    assert corpus[0].abstract == "World models"


def test_hf_conversion_uses_arxiv_identity():
    retriever = object.__new__(HuggingFaceRetriever)
    result = retriever.convert_to_paper({"paper": {"id": "2610.12345", "title": "Agent", "summary": "World models", "authors": [{"name": "A"}]}})
    assert result.url == "https://arxiv.org/abs/2610.12345"
    assert result.authors == ["A"]
    assert result.is_preprint


def test_proceedings_conversion_retains_venue_evidence():
    retriever = object.__new__(ConferencesRetriever)
    result = retriever.convert_to_paper({"title": ["Agent"], "DOI": "10.1145/123", "container-title": ["CHI 2026"], "abstract": "<jats:p>World model</jats:p>"})
    assert result.journal == "CHI 2026"
    assert result.abstract == "World model"
    assert result.is_preprint is False


def test_qq_465_uses_ssl_directly(config, monkeypatch):
    from zotero_arxiv_daily.utils import send_email
    import smtplib
    from tests.canned_responses import make_stub_smtp

    sent = []
    config.email.smtp_port = 465
    monkeypatch.setattr(smtplib, "SMTP_SSL", make_stub_smtp(sent))
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: (_ for _ in ()).throw(AssertionError("Port 465 must use SSL")))
    send_email(config, "<html>hello</html>")
    assert len(sent) == 1
