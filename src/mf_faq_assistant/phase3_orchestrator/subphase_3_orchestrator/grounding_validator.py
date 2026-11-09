from __future__ import annotations

import re

from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import RetrievalResult

DEFLECTION_PATTERNS = re.compile(
    r"(?i)"
    r"(available in (?:the )?fund details|"
    r"noted in the fund details|"
    r"described in the about|"
    r"listed in the exit load|"
    r"please check|"
    r"refer to (?:the )?(?:source|documentation)|"
    r"check (?:the )?source|"
    r"information is not available|"
    r"here are factual details|"
    r"i don't have access|"
    r"contact (?:the )?(?:amc|provider))"
)

NUMERIC_PATTERN = re.compile(r"[\d]+%?|₹[\d,.]+")


def is_deflection(answer: str) -> bool:
    return bool(DEFLECTION_PATTERNS.search(answer))


def _evidence_corpus(retrieval: RetrievalResult) -> str:
    parts: list[str] = []
    for chunk in retrieval.evidence_chunks:
        parts.append(chunk.embedded_text)
        for value in (chunk.shadow_fields or {}).values():
            parts.append(str(value))
    return " ".join(parts).lower()


def validate_grounded_answer(
    answer: str,
    retrieval: RetrievalResult,
    *,
    expected: str | None = None,
) -> bool:
    if not answer or not answer.strip():
        return False
    if is_deflection(answer):
        return False

    corpus = _evidence_corpus(retrieval)
    answer_lower = answer.lower()

    if expected:
        expected_norm = expected.lower()
        numeric_in_expected = NUMERIC_PATTERN.findall(expected)
        if numeric_in_expected:
            if not any(num.lower() in answer_lower for num in numeric_in_expected):
                return False
            return any(num.lower() in corpus for num in numeric_in_expected)
        if expected_norm in corpus or expected_norm in answer_lower:
            return True
        return any(
            token in answer_lower and token in corpus
            for token in expected_norm.split()
            if len(token) > 3
        )

    numbers = NUMERIC_PATTERN.findall(answer)
    if numbers:
        return any(num.lower() in corpus for num in numbers)

    answer_tokens = {t for t in re.findall(r"[a-z0-9%₹,.]+", answer_lower) if len(t) > 3}
    return bool(answer_tokens & set(corpus.split()))
