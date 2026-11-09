from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import (
    CorpusIndex,
    FIELD_ALIASES,
    IndexHit,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.field_intent import FieldIntent
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.scheme_resolver import (
    SchemeResolution,
)


@dataclass(frozen=True)
class RetrievalConfig:
    retrieval_version: str
    sources_path: str
    index_active_dir: str
    top_k_per_path: int
    rrf_k: int
    keyword_weight: float
    vector_weight: float
    scheme_resolver_min_confidence: float
    vector_min_score: float
    keyword_min_score: float
    field_route_score: float
    section_boost: float
    meta_description_weight: float
    max_evidence_chunks: int


@dataclass(frozen=True)
class ScoredHit:
    chunk_id: str
    score: float
    scheme_id: str
    scheme_name: str
    section_name: str
    source_url: str
    fetched_at: str
    embedded_text: str
    shadow_fields: dict[str, str]
    retrieval_path: str
    vector_score: float = 0.0
    keyword_score: float = 0.0


def _rrf_contribution(rank: int, *, weight: float, k: int) -> float:
    return weight / (k + rank + 1)


def _section_weight(section_name: str, field_intent: FieldIntent | None, config: RetrievalConfig) -> float:
    if section_name == "Meta Description":
        return config.meta_description_weight

    if not field_intent:
        return 1.0

    if section_name in field_intent.preferred_sections:
        return config.section_boost

    return 1.0


def _hit_from_document(doc: dict[str, Any], *, score: float, retrieval_path: str) -> ScoredHit:
    return ScoredHit(
        chunk_id=str(doc["chunk_id"]),
        score=score,
        scheme_id=str(doc.get("scheme_id", "")),
        scheme_name=str(doc.get("scheme_name", "")),
        section_name=str(doc.get("section_name", "")),
        source_url=str(doc.get("source_url", "")),
        fetched_at=str(doc.get("fetched_at", "")),
        embedded_text=str(doc.get("embedded_text", "")),
        shadow_fields={str(k): str(v) for k, v in (doc.get("shadow_fields") or {}).items()},
        retrieval_path=retrieval_path,
    )


def _hit_from_index_hit(hit: IndexHit, *, score: float, retrieval_path: str, shadow_fields: dict[str, str]) -> ScoredHit:
    return ScoredHit(
        chunk_id=hit.chunk_id,
        score=score,
        scheme_id=hit.scheme_id,
        scheme_name=hit.scheme_name,
        section_name=hit.section_name,
        source_url=hit.source_url,
        fetched_at="",
        embedded_text=hit.embedded_text,
        shadow_fields=shadow_fields,
        retrieval_path=retrieval_path,
    )


def _filter_hits_by_scheme(hits: list[ScoredHit], scheme_id: str | None) -> list[ScoredHit]:
    if not scheme_id:
        return hits
    return [hit for hit in hits if hit.scheme_id == scheme_id]


def route_field_intent(
    index: CorpusIndex,
    *,
    resolution: SchemeResolution,
    field_intent: FieldIntent,
    config: RetrievalConfig,
) -> list[ScoredHit]:
    return route_field_intents(
        index,
        resolution=resolution,
        field_intents=(field_intent,),
        config=config,
    )


def route_field_intents(
    index: CorpusIndex,
    *,
    resolution: SchemeResolution,
    field_intents: tuple[FieldIntent, ...],
    config: RetrievalConfig,
) -> list[ScoredHit]:
    if not resolution.resolved or not resolution.scheme_id or not field_intents:
        return []

    docs = index.get_documents_for_scheme(resolution.scheme_id)
    section_order: list[str] = []
    seen_sections: set[str] = set()
    for intent in field_intents:
        for section_name in intent.preferred_sections:
            if section_name not in seen_sections:
                section_order.append(section_name)
                seen_sections.add(section_name)

    hits: list[ScoredHit] = []
    for section_name in section_order:
        for doc in docs:
            if str(doc.get("section_name")) != section_name:
                continue
            hits.append(
                _hit_from_document(
                    doc,
                    score=config.field_route_score,
                    retrieval_path="field_route",
                )
            )
            break

    return hits


def merge_hybrid_hits(
    vector_hits: list[IndexHit],
    keyword_hits: list[IndexHit],
    *,
    index: CorpusIndex,
    field_intent: FieldIntent | None,
    config: RetrievalConfig,
) -> list[ScoredHit]:
    chunk_scores: dict[str, float] = {}
    chunk_meta: dict[str, IndexHit] = {}
    vector_scores: dict[str, float] = {}
    keyword_scores: dict[str, float] = {}

    for rank, hit in enumerate(vector_hits):
        chunk_scores[hit.chunk_id] = chunk_scores.get(hit.chunk_id, 0.0) + _rrf_contribution(
            rank, weight=config.vector_weight, k=config.rrf_k
        )
        chunk_meta[hit.chunk_id] = hit
        vector_scores[hit.chunk_id] = max(vector_scores.get(hit.chunk_id, 0.0), hit.score)

    for rank, hit in enumerate(keyword_hits):
        chunk_scores[hit.chunk_id] = chunk_scores.get(hit.chunk_id, 0.0) + _rrf_contribution(
            rank, weight=config.keyword_weight, k=config.rrf_k
        )
        chunk_meta[hit.chunk_id] = hit
        keyword_scores[hit.chunk_id] = max(keyword_scores.get(hit.chunk_id, 0.0), hit.score)

    scored: list[ScoredHit] = []
    for chunk_id, score in chunk_scores.items():
        hit = chunk_meta[chunk_id]
        doc = index._documents.get(chunk_id, {})
        shadow_fields = {str(k): str(v) for k, v in (doc.get("shadow_fields") or {}).items()}
        weighted = score * _section_weight(hit.section_name, field_intent, config)
        scored.append(
            ScoredHit(
                chunk_id=hit.chunk_id,
                score=weighted,
                scheme_id=hit.scheme_id,
                scheme_name=hit.scheme_name,
                section_name=hit.section_name,
                source_url=hit.source_url,
                fetched_at=str(doc.get("fetched_at", "")),
                embedded_text=hit.embedded_text,
                shadow_fields=shadow_fields,
                retrieval_path="hybrid",
                vector_score=vector_scores.get(chunk_id, 0.0),
                keyword_score=keyword_scores.get(chunk_id, 0.0),
            )
        )

    return sorted(scored, key=lambda item: item.score, reverse=True)


def hybrid_retrieve(
    index: CorpusIndex,
    query: str,
    *,
    resolution: SchemeResolution,
    field_intent: FieldIntent | None,
    config: RetrievalConfig,
) -> list[ScoredHit]:
    vector_hits = index.search_vector(query, top_k=config.top_k_per_path)
    keyword_hits = index.search_keyword(query, top_k=config.top_k_per_path)
    merged = merge_hybrid_hits(
        vector_hits,
        keyword_hits,
        index=index,
        field_intent=field_intent,
        config=config,
    )
    return _filter_hits_by_scheme(merged, resolution.scheme_id if resolution.resolved else None)


def aggregate_url_scores(hits: list[ScoredHit]) -> dict[str, float]:
    scores: dict[str, float] = {}
    for hit in hits:
        scores[hit.source_url] = scores.get(hit.source_url, 0.0) + hit.score
    return scores


def select_winning_url(
    hits: list[ScoredHit],
    *,
    resolution: SchemeResolution,
) -> tuple[str | None, list[ScoredHit]]:
    if not hits:
        return None, []

    if resolution.resolved and resolution.source_url:
        constrained = [hit for hit in hits if hit.source_url == resolution.source_url]
        if constrained:
            hits = constrained

    url_scores = aggregate_url_scores(hits)
    winning_url = max(url_scores, key=url_scores.get)
    url_hits = sorted(
        (hit for hit in hits if hit.source_url == winning_url),
        key=lambda item: item.score,
        reverse=True,
    )
    return winning_url, url_hits


def field_has_evidence(field_intent: FieldIntent, hit: ScoredHit) -> bool:
    value = hit.shadow_fields.get(field_intent.field)
    if value:
        return True

    text = hit.embedded_text.lower()
    field = field_intent.field

    if field == "nav":
        return "nav" in text and "₹" in hit.embedded_text
    if field == "aum":
        return "aum" in text or "fund size" in text
    if field == "manager":
        return "current fund manager" in text
    if field == "tax":
        return "tax implication" in text or "stamp duty" in text
    if field == "expense_ratio":
        return "expense ratio" in text
    if field == "min_sip":
        return "sip" in text and "₹" in hit.embedded_text
    if field == "exit_load":
        return "exit load" in text
    if field == "benchmark":
        return "fund benchmark" in text or "benchmark" in text
    if field == "risk":
        return "risk" in text
    if field == "lock_in":
        return "lock-in" in text or "lock in" in text

    if any(alias in text for alias in field_intent.matched_aliases):
        return True

    return False
