from __future__ import annotations

import difflib
import re
from dataclasses import dataclass

from mf_faq_assistant.phase0_governance.sources import LockedSources, SourceItem
from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import _tokenize
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.query_normalizer import (
    normalize_query,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.query_scope import (
    scheme_explicitly_in_query,
)

MATCH_NORMALIZE_PATTERN = re.compile(r"[^a-z0-9]+")
AND_SPLIT_PATTERN = re.compile(r"\s+and\s+", re.IGNORECASE)
SCHEME_SUFFIX_TOKENS = frozenset(
    {"hdfc", "fund", "direct", "growth", "plan", "and", "etf", "fof", "of"}
)
FIELD_ONLY_TOKENS = frozenset(
    {
        "nav",
        "aum",
        "expense",
        "ratio",
        "min",
        "sip",
        "minimum",
        "exit",
        "load",
        "benchmark",
        "risk",
        "lock",
        "manager",
        "tax",
        "stamp",
        "duty",
        "what",
        "is",
        "the",
        "of",
        "for",
        "a",
        "an",
        "tell",
        "me",
        "please",
    }
)
SCHEME_HINT_TOKENS = frozenset(
    {
        "hdfc",
        "mid",
        "small",
        "multi",
        "nifty",
        "equity",
        "balanced",
        "pharma",
        "healthcare",
        "defence",
        "defense",
        "gold",
        "silver",
        "index",
        "hybrid",
        "thematic",
        "sectoral",
        "commodity",
        "large",
        "cap",
        "fof",
        "etf",
    }
)
SCHEME_LABEL_PREFIX = re.compile(
    r"^(?:what\s+is\s+(?:the\s+)?)?"
    r"(?:(?:nav|aum|expense\s+ratio|min(?:imum)?\s+sip|exit\s+load|benchmark|risk|"
    r"lock[- ]?in|fund\s+manager|tax)\s+(?:of\s+)?)+",
    re.IGNORECASE,
)
SUPPORTED_AMC = "hdfc"


@dataclass(frozen=True)
class SchemeResolution:
    resolved: bool
    needs_clarification: bool
    confidence: float
    scheme_id: str | None
    scheme_name: str | None
    source_url: str | None
    candidates: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class SchemeMentions:
    resolved: tuple[SchemeResolution, ...]
    unresolved: tuple[str, ...]


def _normalize_match_text(text: str) -> str:
    return MATCH_NORMALIZE_PATTERN.sub(" ", text.lower()).strip()


def _distinctive_scheme_tokens(source: SourceItem) -> set[str]:
    name_tokens = set(_tokenize(_normalize_match_text(source.scheme_name)))
    id_tokens = set(_tokenize(source.id.replace("_", " ")))
    return (name_tokens | id_tokens) - SCHEME_SUFFIX_TOKENS


def _score_scheme(query: str, source: SourceItem) -> float:
    q_norm = _normalize_match_text(query)
    name_norm = _normalize_match_text(source.scheme_name)

    score = 0.0
    if name_norm and name_norm in q_norm:
        score += 0.55
    elif q_norm and q_norm in name_norm:
        score += 0.35

    q_tokens = set(_tokenize(q_norm))
    name_tokens = set(_tokenize(name_norm))
    id_tokens = set(_tokenize(source.id.replace("_", " ")))
    tag_tokens = set(_tokenize(" ".join(source.tags)))
    distinctive = _distinctive_scheme_tokens(source)

    if distinctive and distinctive.issubset(q_tokens):
        score += 0.4

    if name_tokens:
        score += 0.25 * (len(q_tokens & name_tokens) / len(name_tokens))

    id_overlap = q_tokens & id_tokens
    if id_overlap:
        score += 0.15 * min(1.0, len(id_overlap) / 3)

    tag_overlap = q_tokens & tag_tokens
    if tag_overlap:
        score += 0.12 * min(1.0, len(tag_overlap))

    score += 0.15 * difflib.SequenceMatcher(None, q_norm, name_norm).ratio()
    return min(1.0, score)


def resolve_scheme(
    query: str,
    locked: LockedSources,
    *,
    selected_scheme_id: str | None = None,
    min_confidence: float = 0.45,
) -> SchemeResolution:
    enabled = locked.enabled_sources()
    match_query = normalize_query(query).normalized

    if selected_scheme_id:
        for source in enabled:
            if source.id == selected_scheme_id:
                return SchemeResolution(
                    resolved=True,
                    needs_clarification=False,
                    confidence=1.0,
                    scheme_id=source.id,
                    scheme_name=source.scheme_name,
                    source_url=source.url,
                    candidates=((source.id, 1.0),),
                )
        return SchemeResolution(
            resolved=False,
            needs_clarification=True,
            confidence=0.0,
            scheme_id=None,
            scheme_name=None,
            source_url=None,
            candidates=(),
        )

    ranked = sorted(
        ((_score_scheme(match_query, source), source) for source in enabled),
        key=lambda item: item[0],
        reverse=True,
    )
    candidates = tuple((source.id, score) for score, source in ranked[:3])
    best_score, best_source = ranked[0]

    if best_score < min_confidence:
        return SchemeResolution(
            resolved=False,
            needs_clarification=True,
            confidence=best_score,
            scheme_id=None,
            scheme_name=None,
            source_url=None,
            candidates=candidates,
        )

    if not scheme_explicitly_in_query(match_query, best_source):
        return SchemeResolution(
            resolved=False,
            needs_clarification=True,
            confidence=best_score,
            scheme_id=None,
            scheme_name=None,
            source_url=None,
            candidates=candidates,
        )

    second_score = ranked[1][0] if len(ranked) > 1 else 0.0
    if second_score >= min_confidence and (best_score - second_score) < 0.08:
        return SchemeResolution(
            resolved=False,
            needs_clarification=True,
            confidence=best_score,
            scheme_id=None,
            scheme_name=None,
            source_url=None,
            candidates=candidates,
        )

    return SchemeResolution(
        resolved=True,
        needs_clarification=False,
        confidence=best_score,
        scheme_id=best_source.id,
        scheme_name=best_source.scheme_name,
        source_url=best_source.url,
        candidates=candidates,
    )


def _is_field_only_segment(segment: str) -> bool:
    norm = normalize_query(segment).normalized
    tokens = set(_tokenize(norm))
    if tokens & (SCHEME_HINT_TOKENS - {"cap", "fund"}):
        return False
    if not tokens & FIELD_ONLY_TOKENS:
        return False
    return tokens.issubset(FIELD_ONLY_TOKENS)


def _expand_segment_with_amc(segment: str, *, has_amc: bool) -> str:
    if has_amc and SUPPORTED_AMC not in segment.lower():
        return f"{SUPPORTED_AMC} {segment}"
    return segment


def _format_scheme_label(segment: str) -> str:
    cleaned = SCHEME_LABEL_PREFIX.sub("", segment.strip()).strip().rstrip("?.!")
    if not cleaned:
        cleaned = segment.strip().rstrip("?.!")
    tokens = cleaned.split()
    if tokens and tokens[0].lower() == SUPPORTED_AMC:
        tokens[0] = "HDFC"
    return " ".join(tokens)


def resolve_scheme_mentions(
    query: str,
    locked: LockedSources,
    *,
    selected_scheme_id: str | None = None,
    min_confidence: float = 0.45,
) -> SchemeMentions | None:
    if selected_scheme_id:
        return None

    segments = [part.strip() for part in AND_SPLIT_PATTERN.split(query) if part.strip()]
    if len(segments) < 2:
        return None

    has_amc = any(SUPPORTED_AMC in segment.lower() for segment in segments)
    scheme_segments = [
        segment
        for segment in segments
        if not _is_field_only_segment(segment)
    ]
    if len(scheme_segments) < 2:
        return None

    resolved: list[SchemeResolution] = []
    unresolved: list[str] = []
    seen_ids: set[str] = set()

    for segment in scheme_segments:
        expanded = _expand_segment_with_amc(segment, has_amc=has_amc)
        resolution = resolve_scheme(
            expanded,
            locked,
            min_confidence=min_confidence,
        )
        if resolution.resolved and resolution.scheme_id:
            if resolution.scheme_id in seen_ids:
                continue
            seen_ids.add(resolution.scheme_id)
            resolved.append(resolution)
            continue
        unresolved.append(_format_scheme_label(expanded))

    if len(resolved) + len(unresolved) < 2:
        return None

    return SchemeMentions(
        resolved=tuple(resolved),
        unresolved=tuple(unresolved),
    )
