from __future__ import annotations

from typing import Protocol


class ChatResponseLike(Protocol):
    answer_text: str
    citation_url: str | None
    last_updated_date: str | None
    refusal: bool
    reason: str | None
