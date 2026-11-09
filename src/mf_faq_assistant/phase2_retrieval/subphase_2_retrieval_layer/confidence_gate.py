from __future__ import annotations

from dataclasses import dataclass

from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.field_intent import FieldIntent
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.hybrid_retriever import (
    RetrievalConfig,
    ScoredHit,
    field_has_evidence,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.scheme_resolver import (
    SchemeResolution,
)


@dataclass(frozen=True)
class GateResult:
    passed: bool
    confidence: float
    reason: str | None


def _field_intents_list(
    field_intent: FieldIntent | None,
    field_intents: tuple[FieldIntent, ...] | None,
) -> tuple[FieldIntent, ...]:
    if field_intents:
        return field_intents
    if field_intent:
        return (field_intent,)
    return ()


def evaluate_confidence(
    *,
    hits: list[ScoredHit],
    field_intent: FieldIntent | None,
    resolution: SchemeResolution,
    config: RetrievalConfig,
    field_intents: tuple[FieldIntent, ...] | None = None,
) -> GateResult:
    intents = _field_intents_list(field_intent, field_intents)
    if intents and resolution.needs_clarification:
        return GateResult(passed=False, confidence=resolution.confidence, reason="needs_clarification")

    if not hits:
        return GateResult(passed=False, confidence=0.0, reason="not_found")

    top = hits[0]
    if top.retrieval_path == "field_route":
        if intents and all(
            any(field_has_evidence(intent, hit) for hit in hits[:6])
            for intent in intents
        ):
            return GateResult(passed=True, confidence=0.95, reason=None)
        if intents:
            return GateResult(passed=False, confidence=top.score, reason="not_found")
        return GateResult(passed=True, confidence=0.9, reason=None)

    max_vector = max((hit.vector_score for hit in hits), default=0.0)
    max_keyword = max((hit.keyword_score for hit in hits), default=0.0)

    if intents:
        field_supported = any(
            any(field_has_evidence(intent, hit) for hit in hits[:5])
            for intent in intents
        )
        if not field_supported:
            return GateResult(passed=False, confidence=top.score, reason="not_found")

    if max_vector >= config.vector_min_score:
        confidence = max(max_vector, min(1.0, max_keyword / 10.0))
        return GateResult(passed=True, confidence=confidence, reason=None)

    if max_keyword >= config.keyword_min_score:
        return GateResult(passed=True, confidence=min(1.0, max_keyword / 10.0), reason=None)

    return GateResult(passed=False, confidence=top.score, reason="not_found")
