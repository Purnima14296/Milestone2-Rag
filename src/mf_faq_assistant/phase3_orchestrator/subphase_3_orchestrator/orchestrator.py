from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time

import yaml

from mf_faq_assistant.phase0_governance.refusal import RefusalTaxonomy, load_refusal_taxonomy
from mf_faq_assistant.phase0_governance.sources import load_locked_sources
from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import (
    load_retrieval_config,
    retrieve,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.scheme_resolver import (
    SchemeMentions,
    resolve_scheme_mentions,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.generator import generate_answer
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.grounding_validator import (
    is_deflection,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.template_generator import (
    GroundingError,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.intent_classifier import (
    Intent,
    classify_intent,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.pii_guard import (
    PII_BLOCK_MESSAGE,
    check_pii,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.post_processor import (
    format_factual_answer,
    format_no_link_answer,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.refusal_composer import (
    compose_clarification,
    compose_not_found,
    compose_refusal,
    compose_unsupported_scheme,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.query_scope import (
    extract_unsupported_fund_reference,
)

ORCHESTRATOR_VERSION = "1.0.0"
DEFAULT_CONFIG_PATH = "config/orchestrator.yaml"


class OrchestratorError(ValueError):
    pass


@dataclass(frozen=True)
class OrchestratorConfig:
    orchestrator_version: str
    sources_path: str
    refusal_taxonomy_path: str
    retrieval_config_path: str
    max_answer_sentences: int
    link_policy_mode: str


@dataclass(frozen=True)
class ChatResponse:
    answer_text: str
    citation_url: str | None
    last_updated_date: str | None
    refusal: bool
    reason: str | None


def load_orchestrator_config(path: str | Path = DEFAULT_CONFIG_PATH) -> OrchestratorConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise OrchestratorError(f"Orchestrator config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise OrchestratorError(f"Invalid orchestrator config: {config_path}")

    link_policy = raw.get("link_policy", {}) or {}
    mode = str(link_policy.get("mode", "contract_b_split"))
    if mode not in ("contract_a_strict", "contract_b_split"):
        raise OrchestratorError("link_policy.mode must be contract_a_strict or contract_b_split")

    return OrchestratorConfig(
        orchestrator_version=str(raw.get("orchestrator_version", ORCHESTRATOR_VERSION)),
        sources_path=str(raw.get("sources_path", "config/sources.yaml")),
        refusal_taxonomy_path=str(raw.get("refusal_taxonomy_path", "config/refusal_taxonomy.yaml")),
        retrieval_config_path=str(raw.get("retrieval_config_path", "config/retrieval.yaml")),
        max_answer_sentences=int(raw.get("max_answer_sentences", 3)),
        link_policy_mode=mode,
    )


def _answer_multi_scheme(
    message: str,
    mentions: SchemeMentions,
    *,
    index: CorpusIndex | None,
    config: OrchestratorConfig,
) -> ChatResponse | None:
    retrieval_config = load_retrieval_config(config.retrieval_config_path)
    answer_parts: list[str] = []
    citation_url: str | None = None
    fetched_at: str | None = None

    for resolution in mentions.resolved:
        retrieval = retrieve(
            message,
            selected_scheme_id=resolution.scheme_id,
            index=index,
            config=retrieval_config,
        )
        if retrieval.status != "ok" or not retrieval.source_url:
            continue
        try:
            body = generate_answer(retrieval)
            if is_deflection(body):
                continue
            answer_parts.append(body.rstrip("."))
            if citation_url is None:
                citation_url = retrieval.source_url
                fetched_at = retrieval.fetched_at
        except GroundingError:
            continue

    for label in mentions.unresolved:
        answer_parts.append(compose_unsupported_scheme(label).rstrip("."))

    if not answer_parts:
        return None

    if citation_url:
        formatted = format_factual_answer(
            ". ".join(answer_parts) + ".",
            citation_url=citation_url,
            fetched_at=fetched_at,
            max_sentences=config.max_answer_sentences,
        )
        return ChatResponse(
            answer_text=formatted.answer_text,
            citation_url=formatted.citation_url,
            last_updated_date=formatted.last_updated_date,
            refusal=False,
            reason=None,
        )

    formatted = format_no_link_answer(
        ". ".join(answer_parts) + ".",
        max_sentences=config.max_answer_sentences,
    )
    return ChatResponse(
        answer_text=formatted.answer_text,
        citation_url=None,
        last_updated_date=None,
        refusal=False,
        reason="not_found",
    )


def _no_link_response(answer_text: str, *, reason: str, refusal: bool) -> ChatResponse:
    formatted = format_no_link_answer(answer_text)
    return ChatResponse(
        answer_text=formatted.answer_text,
        citation_url=None,
        last_updated_date=None,
        refusal=refusal,
        reason=reason,
    )


def _record_chat_event(
    message: str,
    response: ChatResponse,
    *,
    started_at: float,
    max_sentences: int,
    intent: str | None = None,
    scheme_id: str | None = None,
    field_intent: str | None = None,
    retrieval_path: str | None = None,
    retrieval_confidence: float | None = None,
    pii_blocked: bool = False,
    pii_kinds: tuple[str, ...] = (),
) -> ChatResponse:
    try:
        from mf_faq_assistant.phase5_eval_observability.structured_logger import (
            build_observability_context,
            log_chat_event,
        )

        context = build_observability_context(
            message,
            intent=intent,
            scheme_id=scheme_id,
            field_intent=field_intent,
            retrieval_path=retrieval_path,
            retrieval_confidence=retrieval_confidence,
            latency_ms=(time.perf_counter() - started_at) * 1000,
            pii_blocked=pii_blocked,
            pii_kinds=pii_kinds,
        )
        log_chat_event(response, context, max_sentences=max_sentences)
    except Exception:
        pass
    return response


def chat(
    message: str,
    *,
    selected_scheme_id: str | None = None,
    index: CorpusIndex | None = None,
    config: OrchestratorConfig | None = None,
    taxonomy: RefusalTaxonomy | None = None,
) -> ChatResponse:
    started_at = time.perf_counter()
    cfg = config or load_orchestrator_config()
    refusal_taxonomy = taxonomy or load_refusal_taxonomy(cfg.refusal_taxonomy_path)

    def _finish(response: ChatResponse, **kwargs) -> ChatResponse:
        return _record_chat_event(
            message,
            response,
            started_at=started_at,
            max_sentences=cfg.max_answer_sentences,
            **kwargs,
        )

    pii_result = check_pii(message)
    if pii_result.blocked:
        return _finish(
            _no_link_response(PII_BLOCK_MESSAGE, reason="pii_blocked", refusal=True),
            intent="pii_blocked",
            pii_blocked=True,
            pii_kinds=pii_result.kinds,
        )

    intent = classify_intent(message, refusal_taxonomy)
    if intent.intent == Intent.REFUSAL and intent.refusal_category:
        return _finish(
            _no_link_response(
                compose_refusal(intent.refusal_category),
                reason=f"refusal_{intent.refusal_category}",
                refusal=True,
            ),
            intent=intent.refusal_category,
        )

    unsupported_fund = extract_unsupported_fund_reference(message)
    if unsupported_fund:
        return _finish(
            _no_link_response(
                compose_unsupported_scheme(unsupported_fund),
                reason="not_found",
                refusal=False,
            ),
            intent="unsupported_scheme",
        )

    locked = load_locked_sources(cfg.sources_path)
    retrieval_config = load_retrieval_config(cfg.retrieval_config_path)
    scheme_mentions = resolve_scheme_mentions(
        message,
        locked,
        selected_scheme_id=selected_scheme_id,
        min_confidence=retrieval_config.scheme_resolver_min_confidence,
    )
    if scheme_mentions:
        multi_scheme_response = _answer_multi_scheme(
            message,
            scheme_mentions,
            index=index,
            config=cfg,
        )
        if multi_scheme_response:
            return _finish(
                multi_scheme_response,
                intent="factual",
                scheme_id=scheme_mentions.resolved[0].scheme_id if scheme_mentions.resolved else None,
                field_intent=None,
                retrieval_path="multi_scheme",
                retrieval_confidence=1.0 if scheme_mentions.resolved else 0.0,
            )

    retrieval = retrieve(
        message,
        selected_scheme_id=selected_scheme_id,
        index=index,
        locked=locked,
        config=retrieval_config,
    )
    retrieval_context = {
        "scheme_id": retrieval.scheme_id,
        "field_intent": retrieval.field_intent,
        "retrieval_path": retrieval.retrieval_path,
        "retrieval_confidence": retrieval.confidence,
    }

    if retrieval.status == "needs_clarification":
        return _finish(
            _no_link_response(
                compose_clarification(),
                reason="needs_clarification",
                refusal=False,
            ),
            intent="needs_clarification",
            **retrieval_context,
        )

    if retrieval.status != "ok":
        return _finish(
            _no_link_response(
                compose_not_found(),
                reason=retrieval.reason or "not_found",
                refusal=False,
            ),
            intent=retrieval.reason or "not_found",
            **retrieval_context,
        )

    if not retrieval.source_url:
        return _finish(
            _no_link_response(
                compose_not_found(),
                reason="not_found",
                refusal=False,
            ),
            intent="not_found",
            **retrieval_context,
        )

    try:
        body = generate_answer(retrieval)
        if is_deflection(body):
            raise GroundingError("Deflection answer rejected")
        formatted = format_factual_answer(
            body,
            citation_url=retrieval.source_url,
            fetched_at=retrieval.fetched_at,
            max_sentences=cfg.max_answer_sentences,
        )
    except (GroundingError, ValueError):
        return _finish(
            _no_link_response(
                compose_not_found(),
                reason="not_found",
                refusal=False,
            ),
            intent="not_found",
            **retrieval_context,
        )

    return _finish(
        ChatResponse(
            answer_text=formatted.answer_text,
            citation_url=formatted.citation_url,
            last_updated_date=formatted.last_updated_date,
            refusal=False,
            reason=None,
        ),
        intent="factual",
        **retrieval_context,
    )
