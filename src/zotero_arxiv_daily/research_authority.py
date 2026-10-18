"""Require academic endorsement before a paper reaches the daily digest.

The digest used to rank papers by topical similarity only, so a technically
on-topic preprint from an unknown group could sit next to a NeurIPS paper from
a leading lab. This module implements one explicit precision gate: a paper is
kept only when at least one independent source of academic authority supports
it -- a recognized venue, a recognized researcher, or a recognized lab /
institution.

Evidence is deliberately conservative:

* Venue evidence comes from structured venue metadata or an explicit arXiv
  acceptance comment; workshops, submissions and "findings" do not count.
* Scholar evidence is an exact full-name match against a curated list. It is a
  whitelist, not a citation metric, and its precision depends on that list.
* Lab evidence is matched against the author/affiliation block of the paper's
  first page. Abstract prose is excluded so "we compare with OpenAI" or the
  word "similar" cannot trigger a match.

Every match keeps the matched text so the email can show why a paper passed.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
import re
import unicodedata

from .protocol import Paper


# Canonical name -> aliases. Aliases are normalized (casefolded, punctuation
# removed) before matching, so "University of California, San Diego" and
# "UC San Diego" share one canonical entry.
DEFAULT_VENUES: dict[str, tuple[str, ...]] = {
    "NeurIPS": ("neurips", "nips", "neural information processing systems"),
    "ICML": ("icml", "international conference on machine learning"),
    "ICLR": ("iclr", "international conference on learning representations"),
    "AAAI": ("aaai", "aaai conference on artificial intelligence"),
    "IJCAI": ("ijcai", "international joint conference on artificial intelligence"),
    "ACL": ("acl", "association for computational linguistics"),
    "EMNLP": ("emnlp", "empirical methods in natural language processing"),
    "NAACL": ("naacl", "north american chapter of the association for computational linguistics"),
    "CVPR": ("cvpr", "computer vision and pattern recognition"),
    "ICCV": ("iccv", "international conference on computer vision"),
    "ECCV": ("eccv", "european conference on computer vision"),
    "CHI": ("chi", "human factors in computing systems"),
    "UIST": ("uist", "user interface software and technology"),
    "CSCW": ("cscw", "computer supported cooperative work"),
    "IUI": ("iui", "intelligent user interfaces"),
    "AAMAS": ("aamas", "autonomous agents and multiagent systems"),
    "CoRL": ("corl", "conference on robot learning"),
    "ICRA": ("icra", "international conference on robotics and automation"),
    "IROS": ("iros", "international conference on intelligent robots and systems"),
    "SIGGRAPH": ("siggraph",),
    "ACM MM": ("acm mm", "acm international conference on multimedia"),
    "KDD": ("kdd", "knowledge discovery and data mining"),
    "WWW": ("the web conference", "world wide web conference"),
    "SIGIR": ("sigir",),
    "COLM": ("colm", "conference on language modeling"),
    "HRI": ("hri", "human robot interaction"),
}


DEFAULT_LABS: dict[str, tuple[str, ...]] = {
    "Google DeepMind": ("google deepmind", "deepmind"),
    "Google Research": ("google research",),
    "OpenAI": ("openai",),
    "Anthropic": ("anthropic",),
    "Meta AI / FAIR": ("meta ai", "fair at meta", "facebook ai research", "meta platforms"),
    "Microsoft Research": ("microsoft research",),
    "NVIDIA Research": ("nvidia research", "nvidia"),
    "Amazon Science": ("amazon science", "amazon aws", "aws ai"),
    "Apple": ("apple research", "apple inc"),
    "Salesforce Research": ("salesforce research",),
    "IBM Research": ("ibm research",),
    "Adobe Research": ("adobe research",),
    "Allen Institute for AI": ("allen institute for ai",),
    "Mila": ("mila",),
    "Vector Institute": ("vector institute",),
    "Max Planck": ("max planck",),
    "ETH Zurich": ("eth zurich",),
    "EPFL": ("epfl",),
    "MIT": ("massachusetts institute of technology", "mit csail", "csail"),
    "Stanford": ("stanford university", "stanford ai lab"),
    "UC Berkeley": ("university of california berkeley", "uc berkeley", "berkeley ai research", "bair"),
    "Carnegie Mellon": ("carnegie mellon",),
    "Oxford": ("university of oxford", "oxford university"),
    "Cambridge": ("university of cambridge", "cambridge university"),
    "Harvard": ("harvard university", "harvard", "kempner institute"),
    "Princeton": ("princeton university",),
    "Caltech": ("california institute of technology", "caltech"),
    "University of Washington": ("university of washington",),
    "Georgia Tech": ("georgia institute of technology", "georgia tech"),
    "UIUC": ("university of illinois urbana champaign", "uiuc"),
    "Cornell": ("cornell university",),
    "UCLA": ("university of california los angeles", "ucla"),
    "UCSD": ("university of california san diego", "uc san diego", "ucsd"),
    "Columbia": ("columbia university",),
    "NYU": ("new york university", "nyu"),
    "University of Toronto": ("university of toronto",),
    "Tsinghua": ("tsinghua university",),
    "Peking University": ("peking university",),
    "Zhejiang University": ("zhejiang university",),
    "Shanghai Jiao Tong": ("shanghai jiao tong university", "sjtu"),
    "Fudan": ("fudan university",),
    "USTC": ("university of science and technology of china", "ustc"),
    "HKUST": ("hong kong university of science and technology", "hkust"),
    "CUHK": ("chinese university of hong kong", "cuhk"),
    "NUS": ("national university of singapore", "nus"),
    "NTU": ("nanyang technological university", "ntu"),
    "University of Tokyo": ("university of tokyo",),
    "KAIST": ("kaist",),
    "Seoul National": ("seoul national university",),
    "BAAI": ("beijing academy of artificial intelligence", "baai"),
    "Shanghai AI Lab": ("shanghai artificial intelligence laboratory", "shanghai ai lab"),
    "Alibaba": ("alibaba",),
    "Tencent": ("tencent",),
    "ByteDance": ("bytedance",),
    "Huawei": ("huawei",),
    "Baidu": ("baidu",),
    "Moonshot AI": ("moonshot ai",),
    "Zhipu": ("zhipu",),
    "MiniMax": ("minimax",),
}


# Exact full-name whitelist. Extend with research.authority.extra_scholars when
# a specific researcher matters. Names are matched after accent/punctuation
# normalization; common homonyms are intentionally omitted.
DEFAULT_SCHOLARS: tuple[str, ...] = (
    "Yoshua Bengio", "Yann LeCun", "Geoffrey Hinton", "Ilya Sutskever",
    "Demis Hassabis", "Oriol Vinyals", "Koray Kavukcuoglu", "David Silver",
    "Nando de Freitas", "Raia Hadsell", "Satinder Singh", "Richard Sutton",
    "Andrew Barto", "Michael Littman", "Doina Precup", "Joelle Pineau",
    "Pieter Abbeel", "Sergey Levine", "Chelsea Finn", "Dorsa Sadigh",
    "Anca Dragan", "Stuart Russell", "Tom Griffiths", "Josh Tenenbaum",
    "Percy Liang", "Dan Klein", "Christopher Manning", "Luke Zettlemoyer",
    "Mohit Iyyer", "Graham Neubig", "Yejin Choi", "Danqi Chen", "Noah Smith",
    "Omer Levy", "Jason Wei", "Denny Zhou", "Quoc Le", "Jeff Dean",
    "Noam Shazeer", "Ashish Vaswani", "Jakob Uszkoreit", "Łukasz Kaiser",
    "Aidan Gomez", "Jan Leike", "Jacob Steinhardt", "Rohin Shah",
    "Subbarao Kambhampati", "Fei-Fei Li", "Jiajun Wu", "Kaiming He",
    "Ross Girshick", "Jitendra Malik", "Alexei Efros", "Trevor Darrell",
    "Antonio Torralba", "Bill Freeman", "Phillip Isola", "Nuno Vasconcelos",
    "Ming-Hsuan Yang", "Chen Change Loy", "Dahua Lin", "Xiaogang Wang",
    "Bolei Zhou", "Ziwei Liu", "Sergey Tulyakov", "Ming-Yu Liu",
    "Jonathan Ho", "Tim Salimans", "William Peebles", "Saining Xie",
    "James Landay", "Terry Winograd", "Scott Klemmer", "Michael Bernstein",
    "Maneesh Agrawala", "Björn Hartmann", "Pedro Lopes", "Patrick Baudisch",
    "Hiroshi Ishii", "Pattie Maes", "Rosalind Picard", "Cynthia Breazeal",
    "Ben Shneiderman", "Meredith Ringel Morris", "Jaime Teevan",
    "Eric Horvitz", "Saleema Amershi", "Ece Kamar",
    "Jennifer Wortman Vaughan", "Hanna Wallach", "Jessica Hullman",
    "Jeffrey Heer", "Fernanda Viégas", "Martin Wattenberg",
    "Julian Togelius", "Georgios Yannakakis", "Michael Bowling",
    "Tim Rocktäschel", "Jakob Foerster", "Roberta Raileanu", "Dieter Fox",
    "Stefan Schaal", "Aude Billard", "Daniela Rus", "Rodney Brooks",
    "Marc Raibert", "Russ Tedrake", "Leslie Kaelbling", "Tomás Lozano-Pérez",
    "Danijar Hafner", "Jürgen Schmidhuber", "Karl Friston",
)


_NEGATIVE_VENUE = re.compile(
    r"\b(?:workshop|companion|adjunct|extended abstract|tutorial|"
    r"doctoral consortium|findings|submitted|under review|rejected)\b"
)
_AFFILIATION_CUE = re.compile(
    r"universit|institut|laborator|\bresearch\b|academy|school of|college|"
    r"department|faculty|\binc\b|\bcorp\b|\bltd\b|gmbh|\bcompany\b|"
    r"\bcenter\b|\bcentre\b|@",
    re.I,
)
_ABSTRACT = re.compile(r"\b(?:abstract|摘要)\b", re.I)
_YEAR = re.compile(r"\b(20\d{2})\b")

_TRANSLITERATION = str.maketrans({"ł": "l", "ø": "o", "ß": "ss", "æ": "ae", "œ": "oe", "đ": "d"})


def _normalize(text: str) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace."""
    if not text:
        return ""
    text = text.casefold()
    text = text.translate(_TRANSLITERATION)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@lru_cache(maxsize=None)
def _alias_regex(alias: str) -> re.Pattern[str]:
    parts = [re.escape(part) for part in alias.split()]
    return re.compile(r"(?<![a-z])" + r"\s+".join(parts) + r"(?![a-z])")


def _normalize_name(name: str) -> str:
    if "," in name:
        last, first = name.split(",", 1)
        name = f"{first.strip()} {last.strip()}"
    return _normalize(name)


def _affiliation_region(page_text: str) -> str:
    """Author/affiliation block of page one, without abstract prose."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in page_text.splitlines()]
    lines = [line for line in lines if line]
    joined = " ".join(lines)
    match = _ABSTRACT.search(joined)
    if match:
        if match.start() >= 10:
            head = joined[: match.start()]
        else:
            # The page may start with an "Abstract" heading; cut at the next
            # occurrence instead of falling back to prose later on the page.
            following = _ABSTRACT.search(joined, match.end())
            head = joined[: following.start()] if following else joined[:2500]
    else:
        head = joined[:2500]
    cue_lines = [line for line in lines if _AFFILIATION_CUE.search(line) and len(line) < 240]
    return head + "\n" + "\n".join(cue_lines[:40])


@dataclass(frozen=True)
class AuthoritySettings:
    enabled: bool = False
    reserve: int = 15
    venues: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: DEFAULT_VENUES)
    labs: Mapping[str, tuple[str, ...]] = field(default_factory=lambda: DEFAULT_LABS)
    scholars: tuple[tuple[str, str], ...] = ()


@dataclass
class AuthorityResult:
    passed: bool
    summary: str | None = None
    signals: list[str] = field(default_factory=list)


def _normalized_map(raw: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    return {canonical: tuple(_normalize(alias) for alias in aliases) for canonical, aliases in raw.items()}


def build_authority_settings(research_config) -> AuthoritySettings:
    """Read research.authority, keeping the curated defaults as the base."""
    raw = {}
    if research_config is not None and hasattr(research_config, "get"):
        raw = research_config.get("authority", {}) or {}
    enabled = bool(raw.get("enabled", False))
    try:
        reserve = max(0, int(raw.get("reserve", 15)))
    except (TypeError, ValueError):
        reserve = 15

    venues = dict(DEFAULT_VENUES)
    for item in raw.get("extra_venues", []) or []:
        venues[str(item)] = (str(item),)
    labs = dict(DEFAULT_LABS)
    for item in raw.get("extra_labs", []) or []:
        labs[str(item)] = (str(item),)

    scholars = []
    for name in DEFAULT_SCHOLARS:
        scholars.append((name, _normalize_name(name)))
    for name in raw.get("extra_scholars", []) or []:
        scholars.append((str(name), _normalize_name(str(name))))
    # Preserve order, drop duplicates.
    seen = set()
    unique_scholars = []
    for display, normalized in scholars:
        if normalized and normalized not in seen:
            seen.add(normalized)
            unique_scholars.append((display, normalized))

    return AuthoritySettings(
        enabled=enabled,
        reserve=reserve,
        venues=_normalized_map(venues),
        labs=_normalized_map(labs),
        scholars=tuple(unique_scholars),
    )


def venue_signal(paper: Paper, venues: Mapping[str, tuple[str, ...]]) -> str | None:
    """Match explicit venue metadata or an author acceptance note."""
    candidates = [paper.journal or "", paper.author_venue_note or ""]
    for text in candidates:
        normalized = _normalize(text)
        if not normalized:
            continue
        for canonical, aliases in venues.items():
            for alias in aliases:
                match = _alias_regex(alias).search(normalized)
                if not match:
                    continue
                window = normalized[max(0, match.start() - 80): match.end() + 80]
                if _NEGATIVE_VENUE.search(window):
                    continue
                year = _YEAR.search(window)
                return f"{canonical} {year.group(1)}" if year else canonical
    return None


def scholar_signal(paper: Paper, scholars: tuple[tuple[str, str], ...]) -> str | None:
    """Exact full-name match against the curated researcher whitelist."""
    if not paper.authors or not scholars:
        return None
    author_names = {_normalize_name(author) for author in paper.authors if author}
    for display, normalized in scholars:
        if normalized and normalized in author_names:
            return display
    return None


def lab_signal(paper: Paper, labs: Mapping[str, tuple[str, ...]]) -> list[str]:
    """Match recognized labs/institutions in the first-page affiliation block."""
    text = getattr(paper, "affiliation_text", None) or ""
    if not text:
        return []
    normalized = _normalize(_affiliation_region(text))
    if not normalized:
        return []
    hits: list[str] = []
    for canonical, aliases in labs.items():
        for alias in aliases:
            if _alias_regex(alias).search(normalized):
                hits.append(canonical)
                break
    return hits


def assess_authority(
    paper: Paper,
    settings: AuthoritySettings,
    fetch_affiliation: Callable[[Paper], str | None] | None = None,
) -> AuthorityResult:
    """Pass when venue, scholar or lab evidence is present.

    Affiliation text is fetched only when the cheaper venue/scholar checks did
    not already pass, so the network cost is paid only for borderline papers.
    """
    venue = venue_signal(paper, settings.venues)
    scholar = scholar_signal(paper, settings.scholars)

    labs: list[str] = []
    if not venue and not scholar:
        if not getattr(paper, "affiliation_text", None) and fetch_affiliation is not None:
            paper.affiliation_text = fetch_affiliation(paper)
        labs = lab_signal(paper, settings.labs)

    signals: list[str] = []
    if venue:
        signals.append(f"{venue}（会议）")
    if scholar:
        signals.append(f"{scholar}（学者）")
    if labs:
        signals.append("、".join(labs[:2]) + "（实验室）")

    return AuthorityResult(
        passed=bool(signals),
        summary="；".join(signals) if signals else None,
        signals=signals,
    )
