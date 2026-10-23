"""Academic authority evidence and the pre-digest precision gate."""

from omegaconf import OmegaConf

from tests.canned_responses import make_sample_paper
from zotero_arxiv_daily.construct_email import render_email
from zotero_arxiv_daily.executor import Executor
from zotero_arxiv_daily.research_authority import (
    assess_authority,
    build_authority_settings,
    lab_signal,
    scholar_signal,
    venue_signal,
)


def settings():
    return build_authority_settings({"authority": {"enabled": True}})


def test_venue_signal_accepts_explicit_acceptance_note():
    paper = make_sample_paper(author_venue_note="Accepted to NeurIPS 2026")
    assert venue_signal(paper, settings().venues) == "NeurIPS 2026"


def test_venue_signal_rejects_workshop_submission_and_findings():
    assert venue_signal(make_sample_paper(author_venue_note="Accepted to the CHI 2026 Workshop"), settings().venues) is None
    assert venue_signal(make_sample_paper(author_venue_note="Submitted to ICML 2026"), settings().venues) is None
    assert venue_signal(make_sample_paper(journal="Findings of ACL 2026"), settings().venues) is None


def test_venue_signal_reads_proceedings_metadata():
    paper = make_sample_paper(journal="Proceedings of the 2026 CHI Conference on Human Factors in Computing Systems")
    assert venue_signal(paper, settings().venues) == "CHI 2026"


def test_scholar_signal_normalizes_accents_and_initials():
    paper = make_sample_paper(authors=["Lukasz Kaiser", "Some Student"])
    assert scholar_signal(paper, settings().scholars) == "Łukasz Kaiser"
    paper = make_sample_paper(authors=["Jurgen Schmidhuber"])
    assert scholar_signal(paper, settings().scholars) == "Jürgen Schmidhuber"


def test_scholar_signal_requires_full_name_match():
    assert scholar_signal(make_sample_paper(authors=["Jason"]), settings().scholars) is None
    assert scholar_signal(make_sample_paper(authors=["Wei Wang"]), settings().scholars) is None


def test_extra_scholars_extend_the_whitelist():
    custom = build_authority_settings({"authority": {"enabled": True, "extra_scholars": ["Jane Doe"]}})
    assert scholar_signal(make_sample_paper(authors=["Jane Doe"]), custom.scholars) == "Jane Doe"


def test_settings_read_omegaconf_values():
    config = OmegaConf.create({"authority": {"enabled": True, "reserve": 5}})
    settings = build_authority_settings(config)
    assert settings.enabled is True
    assert settings.reserve == 5


def test_jepa_scholars_and_inria_are_recognized():
    current = settings()
    assert scholar_signal(make_sample_paper(authors=["Adrien Bardes"]), current.scholars) == "Adrien Bardes"
    paper = make_sample_paper(affiliation_text="Inria Paris\nAbstract")
    assert "Inria" in lab_signal(paper, current.labs)


def test_lab_signal_ignores_abstract_prose_and_substrings():
    paper = make_sample_paper(
        affiliation_text=(
            "A paper about agents\n"
            "ABSTRACT Our approach is similar to Mila and we compare with OpenAI models."
        )
    )
    assert lab_signal(paper, settings().labs) == []


def test_lab_signal_reads_digit_prefixed_affiliations():
    paper = make_sample_paper(
        affiliation_text="1FAIR at Meta, 2Meta AI, 3Harvard\nABSTRACT A study."
    )
    hits = lab_signal(paper, settings().labs)
    assert "Meta AI / FAIR" in hits
    assert "Harvard" in hits


def test_lab_signal_reads_footnote_affiliation_after_abstract():
    paper = make_sample_paper(
        affiliation_text="Title\nAbstract text.\nWei Cai is also with Peking University."
    )
    assert "Peking University" in lab_signal(paper, settings().labs)


def test_assess_authority_fetches_affiliation_only_when_needed():
    calls = []

    def fetch(paper):
        calls.append(paper)
        return "1Google DeepMind\nAbstract"

    endorsed = make_sample_paper(author_venue_note="Accepted to ICML 2026")
    result = assess_authority(endorsed, settings(), fetch)
    assert result.passed
    assert calls == []

    unknown = make_sample_paper(affiliation_text=None)
    result = assess_authority(unknown, settings(), fetch)
    assert result.passed
    assert result.summary == "Google DeepMind（实验室）"
    assert calls == [unknown]


def test_assess_authority_fails_without_any_evidence():
    paper = make_sample_paper(affiliation_text="Chongqing University Cancer Hospital\nAbstract")
    result = assess_authority(paper, settings())
    assert not result.passed
    assert result.summary is None


def test_authority_gate_keeps_target_and_drops_unendorsed():
    executor = object.__new__(Executor)
    executor.config = OmegaConf.create({"executor": {}})
    venue = make_sample_paper(title="venue", author_venue_note="Accepted to ICML 2026")
    unknown = make_sample_paper(title="unknown", affiliation_text="Chongqing University\nAbstract")
    lab = make_sample_paper(title="lab", affiliation_text="1Google DeepMind\nAbstract")
    scholar = make_sample_paper(title="scholar", authors=["Yoshua Bengio"])

    kept = executor._apply_authority_gate([venue, unknown, lab, scholar], 2, settings())

    assert [p.title for p in kept] == ["venue", "lab"]
    assert kept[0].authority_summary == "ICML 2026（会议）"
    assert kept[1].authority_summary == "Google DeepMind（实验室）"


def test_email_renders_authority_evidence():
    paper = make_sample_paper(
        title="Endorsed Paper",
        authority_summary="NeurIPS 2026（会议）；Yoshua Bengio（学者）",
    )
    html = render_email([paper])
    assert "学术背书：NeurIPS 2026（会议）；Yoshua Bengio（学者）" in html


def test_embodied_and_edge_coverage_is_recognized():
    current = settings()
    embodied = make_sample_paper(affiliation_text="Physical Intelligence\nAbstract")
    edge = make_sample_paper(affiliation_text="Qualcomm AI Research\nAbstract")
    assert "Physical Intelligence" in lab_signal(embodied, current.labs)
    assert "Qualcomm AI Research" in lab_signal(edge, current.labs)
    assert scholar_signal(make_sample_paper(authors=["Jim Fan"]), current.scholars) == "Jim Fan"
    assert scholar_signal(make_sample_paper(authors=["Song Han"]), current.scholars) == "Song Han"
