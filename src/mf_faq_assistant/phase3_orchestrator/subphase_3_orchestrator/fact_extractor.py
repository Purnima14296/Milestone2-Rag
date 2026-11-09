from __future__ import annotations

import re

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import _tokenize
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import (
    EvidenceChunk,
    RetrievalResult,
)

SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")
STOP_TOKENS = frozenset(
    {
        "what",
        "is",
        "the",
        "of",
        "for",
        "a",
        "an",
        "in",
        "on",
        "and",
        "or",
        "hdfc",
        "fund",
        "direct",
        "growth",
        "tell",
        "me",
        "about",
        "please",
    }
)

FIELD_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "nav": (
        re.compile(r"NAV:\s*([^₹\n]{0,40})\s*₹([\d,.]+)", re.IGNORECASE),
        re.compile(r"Latest NAV as of\s+(.+?)\s+is\s+₹([\d,.]+)", re.IGNORECASE),
    ),
    "aum": (
        re.compile(r"Fund size \(AUM\)\s*₹([\d,.]+)\s*Cr", re.IGNORECASE),
        re.compile(r"AUM\)\s*of\s*₹([\d,.]+)", re.IGNORECASE),
    ),
    "expense_ratio": (re.compile(r"Expense ratio\s*([\d.]+%)", re.IGNORECASE),),
    "min_sip": (
        re.compile(r"Min\.?\s*for\s*SIP\s*₹([\d,]+)", re.IGNORECASE),
        re.compile(r"Minimum SIP Investment is set to\s*₹([\d,]+)", re.IGNORECASE),
    ),
    "exit_load": (re.compile(r"(Exit load[^\n.]{0,160})", re.IGNORECASE),),
    "benchmark": (
        re.compile(r"Fund benchmark\s+([^\n]+?)(?:\s+Investment Objective|\s*$)", re.IGNORECASE),
    ),
    "risk": (
        re.compile(r"is rated\s+([^.\n]+risk)", re.IGNORECASE),
        re.compile(r"risk classification:\s*([^.\n]+)", re.IGNORECASE),
    ),
    "lock_in": (re.compile(r"(lock[- ]?in[^\n.]{0,120})", re.IGNORECASE),),
    "manager": (
        re.compile(
            r"((?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+)\s+is the Current Fund Manager of",
            re.IGNORECASE,
        ),
    ),
    "tax": (
        re.compile(r"Tax implication\s+(.+?)(?:\.\s|$)", re.IGNORECASE),
        re.compile(r"Stamp duty on investment:\s*([^.]+\.)", re.IGNORECASE),
    ),
}


def _chunk_body(embedded_text: str) -> str:
    if ":" in embedded_text:
        return embedded_text.split(":", 1)[1].strip()
    return embedded_text.strip()


def _format_nav(groups: tuple[str, ...]) -> str | None:
    if len(groups) >= 2 and groups[0] and groups[1]:
        return f"₹{groups[1].strip()} (as of {groups[0].strip()})"
    return None


def _apply_text_pattern(field: str, body: str) -> str | None:
    patterns = FIELD_PATTERNS.get(field, ())
    for pattern in patterns:
        match = pattern.search(body)
        if not match:
            continue
        if field == "nav" and match.lastindex and match.lastindex >= 2:
            formatted = _format_nav((match.group(1), match.group(2)))
            if formatted:
                return formatted
        if field == "aum":
            return f"₹{match.group(1).strip()} Cr"
        if field == "expense_ratio":
            return match.group(1).strip()
        if field == "min_sip":
            return f"₹{match.group(1).strip()}"
        if field in {"exit_load", "lock_in"}:
            return match.group(1).strip()
        if field == "benchmark":
            return match.group(1).strip()
        if field == "risk":
            return match.group(1).strip()
        if field == "manager":
            return match.group(1).strip()
        if field == "tax":
            text = match.group(1).strip()
            if not text.endswith("."):
                text += "."
            return text
    return None


def _normalize_shadow_value(field: str, shadow: str) -> str:
    value = shadow.strip()
    if field == "min_sip" and not value.startswith("₹"):
        return f"₹{value}"
    if field == "nav" and value.startswith("₹") and " as of " in value:
        amount, _, date = value.partition(" as of ")
        return f"{amount.strip()} (as of {date.strip()})"
    if field == "aum" and not value.endswith("Cr"):
        return f"{value} Cr" if value.startswith("₹") else f"₹{value} Cr"
    return value


def _extract_field_from_chunk(field: str, chunk: EvidenceChunk) -> str | None:
    shadow = chunk.shadow_fields.get(field)
    if shadow:
        return _normalize_shadow_value(field, shadow)

    body = _chunk_body(chunk.embedded_text)
    return _apply_text_pattern(field, body)


def _ordered_chunks(
    chunks: tuple[EvidenceChunk, ...],
    preferred_sections: tuple[str, ...] | None,
) -> list[EvidenceChunk]:
    if not preferred_sections:
        return list(chunks)
    ordered: list[EvidenceChunk] = []
    seen: set[str] = set()
    for section in preferred_sections:
        for chunk in chunks:
            if chunk.section_name == section and chunk.chunk_id not in seen:
                ordered.append(chunk)
                seen.add(chunk.chunk_id)
    for chunk in chunks:
        if chunk.chunk_id not in seen:
            ordered.append(chunk)
    return ordered


def extract_field_value(
    field: str,
    chunks: tuple[EvidenceChunk, ...],
    *,
    preferred_sections: tuple[str, ...] | None = None,
) -> str | None:
    for chunk in _ordered_chunks(chunks, preferred_sections):
        value = _extract_field_from_chunk(field, chunk)
        if value:
            return value
    return None


def _format_field_answer(field: str, value: str, *, scheme_name: str | None = None) -> str:
    scheme = scheme_name or "this scheme"
    formats = {
        "expense_ratio": f"The expense ratio for {scheme} is {value}.",
        "min_sip": (
            f"The minimum SIP for {scheme} is {value}."
            if value.startswith("₹")
            else f"The minimum SIP for {scheme} is ₹{value}."
        ),
        "exit_load": f"The exit load for {scheme} is {value}.",
        "benchmark": f"The benchmark for {scheme} is {value}.",
        "risk": f"The risk level for {scheme} is {value}.",
        "lock_in": f"The lock-in period for {scheme} is {value}.",
        "nav": (
            f"The NAV of {scheme} is {value}."
            if value.startswith("₹")
            else f"The NAV of {scheme} is {value}."
        ),
        "aum": (
            f"The AUM of {scheme} is {value}."
            if value.startswith("₹")
            else f"The AUM of {scheme} is {value}."
        ),
        "manager": f"The fund manager of {scheme} is {value}.",
        "tax": (
            f"For {scheme}, {value}"
            if value.lower().startswith(("if you", "stamp duty"))
            else f"The tax implication for {scheme} is {value}"
        ),
    }
    answer = formats.get(field, f"For {scheme}, {value}")
    if answer.endswith(".."):
        return answer[:-1]
    if not answer.endswith("."):
        answer += "."
    return answer


def _query_tokens(query: str) -> set[str]:
    return {t for t in _tokenize(query) if t not in STOP_TOKENS and len(t) > 2}


def extract_general_answer(
    query: str,
    chunks: tuple[EvidenceChunk, ...],
    *,
    scheme_name: str | None = None,
) -> str | None:
    tokens = _query_tokens(query)
    if not tokens:
        return None

    for chunk in chunks:
        body = _chunk_body(chunk.embedded_text)
        for sentence in SENTENCE_SPLIT.split(body):
            sentence = sentence.strip()
            if not sentence:
                continue
            sentence_tokens = set(_tokenize(sentence))
            if tokens & sentence_tokens and len(sentence) >= 12:
                if not sentence.endswith((".", "!", "?")):
                    sentence += "."
                if scheme_name and scheme_name.lower() not in sentence.lower():
                    return f"For {scheme_name}, {sentence[0].lower()}{sentence[1:]}"
                return sentence
    return None


def _requested_fields(retrieval: RetrievalResult) -> tuple[str, ...]:
    field_intents = getattr(retrieval, "field_intents", ())
    if field_intents:
        return field_intents
    if retrieval.field_intent:
        return (retrieval.field_intent,)
    return ()


def extract_grounded_answer(retrieval: RetrievalResult) -> str | None:
    if not retrieval.evidence_chunks:
        return None

    chunks = retrieval.evidence_chunks
    fields = _requested_fields(retrieval)
    scheme_name = retrieval.scheme_name

    if fields:
        from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.field_intent import (
            preferred_sections_for_field,
        )

        if len(fields) == 1:
            field = fields[0]
            preferred = preferred_sections_for_field(field)
            value = extract_field_value(field, chunks, preferred_sections=preferred)
            if not value:
                return None
            return _format_field_answer(field, value, scheme_name=scheme_name)

        parts: list[str] = []
        for field in fields:
            preferred = preferred_sections_for_field(field)
            value = extract_field_value(field, chunks, preferred_sections=preferred)
            if not value:
                return None
            parts.append(_format_field_answer(field, value, scheme_name=scheme_name))
        return " ".join(parts)

    return extract_general_answer(
        retrieval.query_normalized or retrieval.query,
        chunks,
        scheme_name=scheme_name,
    )
