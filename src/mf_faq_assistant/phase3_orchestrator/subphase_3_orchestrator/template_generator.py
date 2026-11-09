from __future__ import annotations

from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import RetrievalResult
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.fact_extractor import (
    extract_grounded_answer,
)


class GroundingError(ValueError):
    pass


def generate_from_templates(retrieval: RetrievalResult) -> str:
    if retrieval.status != "ok" or not retrieval.evidence_chunks:
        raise GroundingError("No evidence available for grounded answer")

    answer = extract_grounded_answer(retrieval)
    if not answer:
        raise GroundingError("Answer not found in retrieved evidence")

    return answer
