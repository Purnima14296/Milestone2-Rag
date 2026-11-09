from __future__ import annotations

import re
from dataclasses import dataclass

from mf_faq_assistant.phase5_eval_observability.types import ChatResponseLike
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.post_processor import (
    ADVISORY_PATTERNS,
    SENTENCE_SPLIT,
    URL_PATTERN,
)

FOOTER_PREFIX = "Last updated from sources:"
NO_LINK_REASONS = frozenset(
    {
        "not_found",
        "needs_clarification",
        "pii_blocked",
        "out_of_scope",
    }
)

REFUSAL_REASON_PREFIX = "refusal_"


@dataclass(frozen=True)
class ContractViolation:
    code: str
    message: str


def _body_without_footer(answer_text: str) -> str:
    lines = answer_text.splitlines()
    if lines and lines[-1].startswith(FOOTER_PREFIX):
        return "\n".join(lines[:-1]).strip()
    return answer_text.strip()


def _sentence_count(text: str) -> int:
    sentences = [part.strip() for part in SENTENCE_SPLIT.split(text.strip()) if part.strip()]
    return len(sentences)


def validate_chat_contract(
    response: ChatResponseLike,
    *,
    max_sentences: int = 3,
) -> list[ContractViolation]:
    violations: list[ContractViolation] = []
    body = _body_without_footer(response.answer_text)

    if URL_PATTERN.search(body):
        violations.append(
            ContractViolation("url_in_body", "Answer body must not contain URLs")
        )

    if ADVISORY_PATTERNS.search(body) and not response.refusal:
        violations.append(
            ContractViolation("advisory_language", "Factual answer contains advisory language")
        )

    if _sentence_count(body) > max_sentences:
        violations.append(
            ContractViolation(
                "sentence_limit",
                f"Answer body exceeds {max_sentences} sentences",
            )
        )

    is_factual = (
        not response.refusal
        and response.reason is None
        and not (response.reason and response.reason.startswith("refusal_"))
    )

    if is_factual:
        if not response.citation_url:
            violations.append(
                ContractViolation("missing_citation", "Factual answer must include a citation URL")
            )
        if response.citation_url and body.count("http") > 0:
            violations.append(
                ContractViolation("duplicate_citation", "Citation must live in citation_url only")
            )
        if not response.last_updated_date:
            violations.append(
                ContractViolation("missing_footer_date", "Factual answer must include last updated date")
            )
        if FOOTER_PREFIX not in response.answer_text:
            violations.append(
                ContractViolation("missing_footer", "Factual answer must include footer line")
            )
        return violations

    if response.citation_url:
        violations.append(
            ContractViolation("unexpected_citation", "No-link response must not include citation URL")
        )

    if response.reason in NO_LINK_REASONS or (response.reason and response.reason.startswith("refusal_")):
        if response.last_updated_date:
            violations.append(
                ContractViolation("unexpected_footer_date", "No-link response must not include footer date")
            )

    return violations


def contract_is_valid(response: ChatResponseLike, *, max_sentences: int = 3) -> bool:
    return not validate_chat_contract(response, max_sentences=max_sentences)
