from __future__ import annotations

from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import RetrievalResult
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.fact_extractor import (
    extract_grounded_answer,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.groq_generator import generate_with_groq
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.grounding_validator import (
    is_deflection,
    validate_grounded_answer,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.llm_config import (
    LlmConfig,
    load_llm_config,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.template_generator import (
    GroundingError,
    generate_from_templates,
)


def generate_answer(
    retrieval: RetrievalResult,
    *,
    llm_config: LlmConfig | None = None,
) -> str:
    if retrieval.status != "ok" or not retrieval.evidence_chunks:
        raise GroundingError("No evidence available for grounded answer")

    grounded = extract_grounded_answer(retrieval)
    if grounded is None:
        raise GroundingError("Answer not found in retrieved evidence")

    cfg = llm_config or load_llm_config()

    if cfg.provider == "template":
        return grounded

    if cfg.provider == "groq" and cfg.api_key():
        try:
            llm_answer = generate_with_groq(retrieval, cfg, expected_fact=grounded)
            if validate_grounded_answer(llm_answer, retrieval, expected=grounded):
                return llm_answer
        except Exception:
            if not cfg.fallback_to_templates:
                raise

    if is_deflection(grounded):
        raise GroundingError("Refusing to return a non-grounded deflection answer")

    return grounded
