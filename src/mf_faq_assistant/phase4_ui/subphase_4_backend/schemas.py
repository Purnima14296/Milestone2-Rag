from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)
    selected_scheme: str | None = Field(
        default=None,
        description="Optional locked scheme id from GET /schemes",
    )


class ChatResponseBody(BaseModel):
    answer_text: str
    citation_url: str | None
    last_updated_date: str | None
    refusal: bool
    reason: str | None


class SchemeItem(BaseModel):
    id: str
    scheme_name: str
    url: str
    tags: list[str]


class SchemesResponse(BaseModel):
    schemes: list[SchemeItem]


class UiConfigResponse(BaseModel):
    welcome_message: str
    disclaimer: str
    example_questions: list[str]


class HealthResponse(BaseModel):
    status: str
    index_ready: bool
    scheme_count: int | None
    document_count: int | None


class ErrorResponse(BaseModel):
    detail: str


class MetricsResponse(BaseModel):
    observability_version: str
    generated_at_utc: str
    total_requests: int
    reason_counts: dict[str, int]
    retrieval_misses: int
    contract_violations: int
    refusal_count: int
    pii_blocked_count: int
    top_urls: list[dict[str, str | int]]
    latency_ms: dict[str, float | None]
