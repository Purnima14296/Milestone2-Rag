from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.parse import urlparse

from mf_faq_assistant.phase5_eval_observability.types import ChatResponseLike
from mf_faq_assistant.phase5_eval_observability.config_loader import (
    ObservabilityConfig,
    load_observability_config,
)
from mf_faq_assistant.phase5_eval_observability.contract_validator import validate_chat_contract
from mf_faq_assistant.phase5_eval_observability.metrics_store import (
    build_dashboard_snapshot,
    write_metrics_snapshot,
)


@dataclass(frozen=True)
class ChatObservabilityContext:
    message_hash: str
    intent: str | None = None
    scheme_id: str | None = None
    field_intent: str | None = None
    retrieval_path: str | None = None
    retrieval_confidence: float | None = None
    latency_ms: float | None = None
    pii_blocked: bool = False
    pii_kinds: tuple[str, ...] = ()


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def hash_message(message: str) -> str:
    return hashlib.sha256(message.encode("utf-8")).hexdigest()[:16]


def build_observability_context(
    message: str,
    *,
    pii_blocked: bool = False,
    pii_kinds: tuple[str, ...] = (),
    intent: str | None = None,
    scheme_id: str | None = None,
    field_intent: str | None = None,
    retrieval_path: str | None = None,
    retrieval_confidence: float | None = None,
    latency_ms: float | None = None,
) -> ChatObservabilityContext:
    return ChatObservabilityContext(
        message_hash=hash_message(message),
        intent=intent,
        scheme_id=scheme_id,
        field_intent=field_intent,
        retrieval_path=retrieval_path,
        retrieval_confidence=retrieval_confidence,
        latency_ms=latency_ms,
        pii_blocked=pii_blocked,
        pii_kinds=pii_kinds,
    )


def _citation_host(citation_url: str | None) -> str | None:
    if not citation_url:
        return None
    parsed = urlparse(citation_url)
    return parsed.netloc or None


def log_chat_event(
    response: ChatResponseLike,
    context: ChatObservabilityContext,
    *,
    config: ObservabilityConfig | None = None,
    max_sentences: int = 3,
) -> None:
    cfg = config or load_observability_config()
    if not cfg.enabled:
        return

    violations = validate_chat_contract(response, max_sentences=max_sentences)
    event = {
        "timestamp_utc": _utc_now_z(),
        "message_hash": context.message_hash,
        "intent": context.intent,
        "scheme_id": context.scheme_id,
        "field_intent": context.field_intent,
        "retrieval_path": context.retrieval_path,
        "retrieval_confidence": context.retrieval_confidence,
        "latency_ms": context.latency_ms,
        "reason": response.reason,
        "refusal": response.refusal,
        "citation_host": _citation_host(response.citation_url),
        "contract_violation": bool(violations),
        "contract_codes": [v.code for v in violations],
        "pii_blocked": context.pii_blocked,
        "pii_kinds": list(context.pii_kinds),
    }

    events_path = Path(cfg.events_path)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with open(events_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=True) + "\n")

    snapshot = build_dashboard_snapshot(config=cfg)
    write_metrics_snapshot(snapshot, config=cfg)
