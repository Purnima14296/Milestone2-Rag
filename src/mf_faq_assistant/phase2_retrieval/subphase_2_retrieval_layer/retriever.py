from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml

from mf_faq_assistant.phase0_governance.sources import LockedSources, load_locked_sources
from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.confidence_gate import (
    GateResult,
    evaluate_confidence,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.field_intent import (
    FieldIntent,
    detect_field_intents,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.hybrid_retriever import (
    RetrievalConfig,
    ScoredHit,
    hybrid_retrieve,
    route_field_intents,
    select_winning_url,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.query_normalizer import (
    expand_query_for_retrieval,
    normalize_query,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.query_scope import (
    extract_unsupported_fund_reference,
    is_out_of_scope_query,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.scheme_resolver import (
    resolve_scheme,
)

RETRIEVAL_VERSION = "1.0.0"
DEFAULT_CONFIG_PATH = "config/retrieval.yaml"


class RetrievalError(ValueError):
    pass


@dataclass(frozen=True)
class EvidenceChunk:
    chunk_id: str
    section_name: str
    embedded_text: str
    score: float
    shadow_fields: dict[str, str]


@dataclass(frozen=True)
class RetrievalResult:
    status: str
    query: str
    query_normalized: str
    scheme_id: str | None
    scheme_name: str | None
    source_url: str | None
    fetched_at: str | None
    field_intent: str | None
    field_intents: tuple[str, ...]
    retrieval_path: str | None
    confidence: float
    reason: str | None
    evidence_chunks: tuple[EvidenceChunk, ...]


def load_retrieval_config(path: str | Path = DEFAULT_CONFIG_PATH) -> RetrievalConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise RetrievalError(f"Retrieval config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise RetrievalError(f"Invalid retrieval config: {config_path}")

    return RetrievalConfig(
        retrieval_version=str(raw.get("retrieval_version", RETRIEVAL_VERSION)),
        sources_path=str(raw.get("sources_path", "config/sources.yaml")),
        index_active_dir=str(raw.get("index_active_dir", "data/index/active")),
        top_k_per_path=int(raw.get("top_k_per_path", 5)),
        rrf_k=int(raw.get("rrf_k", 60)),
        keyword_weight=float(raw.get("keyword_weight", 0.55)),
        vector_weight=float(raw.get("vector_weight", 0.45)),
        scheme_resolver_min_confidence=float(raw.get("scheme_resolver_min_confidence", 0.45)),
        vector_min_score=float(raw.get("vector_min_score", 0.55)),
        keyword_min_score=float(raw.get("keyword_min_score", 2.0)),
        field_route_score=float(raw.get("field_route_score", 10.0)),
        section_boost=float(raw.get("section_boost", 1.2)),
        meta_description_weight=float(raw.get("meta_description_weight", 0.5)),
        max_evidence_chunks=int(raw.get("max_evidence_chunks", 2)),
    )


def _evidence_limit(field_intents: tuple[FieldIntent, ...], config: RetrievalConfig) -> int:
    if len(field_intents) > 1:
        return min(6, max(config.max_evidence_chunks, len(field_intents) * 2))
    return config.max_evidence_chunks


def _field_names(fields: tuple[FieldIntent, ...]) -> tuple[str, ...]:
    return tuple(intent.field for intent in fields)


def _to_evidence_chunks(hits: list[ScoredHit], *, limit: int) -> tuple[EvidenceChunk, ...]:
    return tuple(
        EvidenceChunk(
            chunk_id=hit.chunk_id,
            section_name=hit.section_name,
            embedded_text=hit.embedded_text,
            score=hit.score,
            shadow_fields=hit.shadow_fields,
        )
        for hit in hits[:limit]
    )


def _result_from_hits(
    *,
    query: str,
    query_normalized: str,
    resolution,
    fields: tuple[FieldIntent, ...],
    hits: list[ScoredHit],
    gate: GateResult,
    retrieval_path: str,
    config: RetrievalConfig,
) -> RetrievalResult:
    winning_url, url_hits = select_winning_url(hits, resolution=resolution)
    evidence_source = url_hits or hits
    fetched_at = evidence_source[0].fetched_at if evidence_source else None
    field_names = _field_names(fields)
    evidence_limit = _evidence_limit(fields, config)

    if not gate.passed:
        status = gate.reason or "not_found"
        return RetrievalResult(
            status=status,
            query=query,
            query_normalized=query_normalized,
            scheme_id=resolution.scheme_id,
            scheme_name=resolution.scheme_name,
            source_url=winning_url or resolution.source_url,
            fetched_at=fetched_at,
            field_intent=field_names[0] if field_names else None,
            field_intents=field_names,
            retrieval_path=retrieval_path,
            confidence=gate.confidence,
            reason=gate.reason,
            evidence_chunks=_to_evidence_chunks(evidence_source, limit=evidence_limit),
        )

    return RetrievalResult(
        status="ok",
        query=query,
        query_normalized=query_normalized,
        scheme_id=resolution.scheme_id,
        scheme_name=resolution.scheme_name,
        source_url=winning_url,
        fetched_at=fetched_at,
        field_intent=field_names[0] if field_names else None,
        field_intents=field_names,
        retrieval_path=retrieval_path,
        confidence=gate.confidence,
        reason=None,
        evidence_chunks=_to_evidence_chunks(evidence_source, limit=evidence_limit),
    )


def retrieve(
    query: str,
    *,
    selected_scheme_id: str | None = None,
    index: CorpusIndex | None = None,
    locked: LockedSources | None = None,
    config: RetrievalConfig | None = None,
) -> RetrievalResult:
    cfg = config or load_retrieval_config()
    sources = locked or load_locked_sources(cfg.sources_path)
    normalized = normalize_query(query)
    if is_out_of_scope_query(normalized.normalized):
        return RetrievalResult(
            status="not_found",
            query=normalized.raw,
            query_normalized=normalized.normalized,
            scheme_id=None,
            scheme_name=None,
            source_url=None,
            fetched_at=None,
            field_intent=None,
            field_intents=(),
            retrieval_path=None,
            confidence=0.0,
            reason="out_of_scope",
            evidence_chunks=(),
        )

    fields = detect_field_intents(normalized.normalized)
    resolution = resolve_scheme(
        normalized.normalized,
        sources,
        selected_scheme_id=selected_scheme_id,
        min_confidence=cfg.scheme_resolver_min_confidence,
    )

    corpus_index = index or CorpusIndex(cfg.index_active_dir)
    should_close = index is None

    try:
        if fields and resolution.needs_clarification:
            field_names = _field_names(fields)
            return RetrievalResult(
                status="needs_clarification",
                query=normalized.raw,
                query_normalized=normalized.normalized,
                scheme_id=None,
                scheme_name=None,
                source_url=None,
                fetched_at=None,
                field_intent=field_names[0],
                field_intents=field_names,
                retrieval_path=None,
                confidence=resolution.confidence,
                reason="needs_clarification",
                evidence_chunks=(),
            )

        routed_hits: list[ScoredHit] = []
        if fields and resolution.resolved:
            routed_hits = route_field_intents(
                corpus_index,
                resolution=resolution,
                field_intents=fields,
                config=cfg,
            )

        primary_field = fields[0] if fields else None
        if routed_hits:
            gate = evaluate_confidence(
                hits=routed_hits,
                field_intent=primary_field,
                field_intents=fields,
                resolution=resolution,
                config=cfg,
            )
            if gate.passed:
                return _result_from_hits(
                    query=normalized.raw,
                    query_normalized=normalized.normalized,
                    resolution=resolution,
                    fields=fields,
                    hits=routed_hits,
                    gate=gate,
                    retrieval_path="field_route",
                    config=cfg,
                )

        search_query = expand_query_for_retrieval(normalized.normalized)
        hybrid_hits = hybrid_retrieve(
            corpus_index,
            search_query,
            resolution=resolution,
            field_intent=primary_field,
            config=cfg,
        )
        gate = evaluate_confidence(
            hits=hybrid_hits,
            field_intent=primary_field,
            field_intents=fields,
            resolution=resolution,
            config=cfg,
        )
        return _result_from_hits(
            query=normalized.raw,
            query_normalized=normalized.normalized,
            resolution=resolution,
            fields=fields,
            hits=hybrid_hits,
            gate=gate,
            retrieval_path="hybrid",
            config=cfg,
        )
    finally:
        if should_close:
            corpus_index.close()
