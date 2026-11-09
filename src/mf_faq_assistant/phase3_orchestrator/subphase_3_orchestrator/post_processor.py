from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.grounding_validator import (
    is_deflection,
)

URL_PATTERN = re.compile(r"https?://\S+")
SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

ADVISORY_PATTERNS = re.compile(
    r"\b(should invest|recommend|better than|best fund|will give|expected return)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FormattedAnswer:
    answer_text: str
    citation_url: str | None
    last_updated_date: str | None
    footer: str | None


def _format_fetched_at(fetched_at: str | None) -> str | None:
    if not fetched_at:
        return None
    try:
        dt = datetime.fromisoformat(fetched_at.replace("Z", "+00:00"))
        return dt.date().isoformat()
    except ValueError:
        return fetched_at[:10] if len(fetched_at) >= 10 else fetched_at


def _limit_sentences(text: str, *, max_sentences: int) -> str:
    sentences = [part.strip() for part in SENTENCE_SPLIT.split(text.strip()) if part.strip()]
    if not sentences:
        return text.strip()
    return " ".join(sentences[:max_sentences])


def format_factual_answer(
    body: str,
    *,
    citation_url: str,
    fetched_at: str | None,
    max_sentences: int = 3,
) -> FormattedAnswer:
    cleaned = URL_PATTERN.sub("", body).strip()
    cleaned = _limit_sentences(cleaned, max_sentences=max_sentences)
    if is_deflection(cleaned):
        raise ValueError("Generated answer contains deflection language")
    if ADVISORY_PATTERNS.search(cleaned):
        raise ValueError("Generated answer contains advisory language")

    last_updated = _format_fetched_at(fetched_at)
    footer = f"Last updated from sources: {last_updated}" if last_updated else None
    answer_text = cleaned if not footer else f"{cleaned}\n{footer}"
    return FormattedAnswer(
        answer_text=answer_text,
        citation_url=citation_url,
        last_updated_date=last_updated,
        footer=footer,
    )


def format_no_link_answer(body: str, *, max_sentences: int = 3) -> FormattedAnswer:
    cleaned = URL_PATTERN.sub("", body).strip()
    cleaned = _limit_sentences(cleaned, max_sentences=max_sentences)
    return FormattedAnswer(
        answer_text=cleaned,
        citation_url=None,
        last_updated_date=None,
        footer=None,
    )
