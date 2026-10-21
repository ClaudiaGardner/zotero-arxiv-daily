import json

import pytest
from omegaconf import OmegaConf

from zotero_arxiv_daily import research_selection as module
from zotero_arxiv_daily.protocol import Paper
from zotero_arxiv_daily.executor import Executor


def config():
    return OmegaConf.create({"llm": {"api_mode": "chat_completion", "generation_kwargs": {"model": "test"}}, "research": {
        "interests": [{"title": "agents", "abstract": "agents and world models"}],
        "digest_size": 25, "selection": {"max_candidates": 100, "max_per_topic": 2}}})


def paper(title, score=5):
    return Paper(source="arxiv", title=title, authors=[], abstract="Methods and evaluation.", url="https://arxiv.org/abs/" + title, score=score)


def test_rejects_high_keyword_similarity_with_low_method_value_and_balances_topics(monkeypatch):
    papers = [paper(str(i), 10-i) for i in range(5)]
    rows = [{"id": i, "fit": 4, "method_value": 4 if i else 1, "evidence": 3,
             "recommend": True, "topic": "world_models" if i < 4 else "hci", "reason": "具体的机制与评估设计"} for i in range(5)]
    def request(client, params, messages):
        assert params["generation_kwargs"]["response_format"] == {"type": "json_object"}
        assert json.loads(messages[1]["content"])["candidates"][0]["title"] == "0"
        return json.dumps({"papers": rows})
    monkeypatch.setattr(module, "_request_llm", request)
    result = module.select_research_papers(papers, None, config())
    assert [p.title for p in result] == ["1", "2", "4"]
    assert all(p.selection_reason for p in result)


def test_failed_screening_does_not_silently_send_unscreened_papers(monkeypatch):
    monkeypatch.setattr(module, "_request_llm", lambda *a: '{"papers": []}')
    with pytest.raises(RuntimeError, match="unscreened"):
        module.select_research_papers([paper("A")], None, config())


def test_selection_can_return_a_backfill_pool(monkeypatch):
    topics = ["agents", "hci", "llm", "mllm", "generative", "world_models"]
    papers = [paper(str(i), 10 - i) for i in range(6)]
    rows = [{"id": i, "fit": 4, "method_value": 4, "evidence": 3, "recommend": True,
             "topic": topics[i], "reason": "具体的机制与评估设计"} for i in range(6)]
    monkeypatch.setattr(module, "_request_llm", lambda *a: json.dumps({"papers": rows}))
    result = module.select_research_papers(papers, None, config(), limit=4)
    assert [p.title for p in result] == ["0", "1", "2", "3"]


def test_duplicate_model_ids_rejected():
    row = {"id": 0, "fit": 4, "method_value": 4, "evidence": 3, "recommend": True, "topic": "hci", "reason": "设计"}
    with pytest.raises(ValueError, match="repeated"):
        module._parse_assessments(json.dumps({"papers": [row, row]}), 2)


def test_jepa_is_a_supported_topic():
    row = {"id": 0, "fit": 4, "method_value": 4, "evidence": 3,
           "recommend": True, "topic": "jepa", "reason": "潜空间预测目标"}
    rows = module._parse_assessments(json.dumps({"papers": [row]}), 1)
    assert rows[0]["topic"] == "jepa"


def test_keyword_overflow_never_overtakes_higher_ranked_nonmatches():
    executor = object.__new__(Executor)
    executor.config = OmegaConf.create({"executor": {"pin_keywords": ["world"], "max_pinned_num": 1}})
    papers = [paper("world best", 6), paper("hci", 5.5), paper("world weak", 3.6), paper("llm", 3.5)]
    pinned, remaining = executor._select_pinned(papers)
    assert pinned == papers[:1]
    assert remaining == papers[1:]


def test_academic_digest_retries_an_incomplete_response_once(monkeypatch):
    from zotero_arxiv_daily.final_enrichment import enrich_final_papers
    p = paper("Agent")
    calls = []
    def generate(client, params):
        calls.append(True)
        p.tldr = "fallback abstract" if len(calls) == 1 else "【Motivation】动机【方法】方法【创新点】创新"
        return p.tldr, []
    monkeypatch.setattr(p, "generate_tldr_and_affiliations", generate)
    result = enrich_final_papers([p], {}, None, {"digest_format": "concise_academic", "retry_failed_digest": True}, 1)
    assert len(calls) == 2
    assert "【方法】" in result[0].tldr
