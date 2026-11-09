from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from mf_faq_assistant.phase0_governance.sources import load_locked_sources
from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex, IndexingError
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.orchestrator import chat
from mf_faq_assistant.phase4_ui.subphase_4_backend.config import ApiConfig
from mf_faq_assistant.phase4_ui.subphase_4_backend.dependencies import get_api_config, get_corpus_index
from mf_faq_assistant.phase4_ui.subphase_4_backend.schemas import (
    ChatRequest,
    ChatResponseBody,
    HealthResponse,
    MetricsResponse,
    SchemesResponse,
    SchemeItem,
    UiConfigResponse,
)
from mf_faq_assistant.phase5_eval_observability.metrics_store import (
    build_dashboard_snapshot,
    snapshot_to_dict,
)

router = APIRouter()


def _index_meta(index_dir: str) -> dict:
    meta_path = Path(index_dir) / "meta.json"
    if not meta_path.exists():
        return {}
    return json.loads(meta_path.read_text(encoding="utf-8"))


@router.get("/health", response_model=HealthResponse)
def health(api_config: ApiConfig = Depends(get_api_config)) -> HealthResponse:
    meta = _index_meta(api_config.index_active_dir)
    index_ready = bool(meta.get("status") == "ok")
    return HealthResponse(
        status="ok" if index_ready else "degraded",
        index_ready=index_ready,
        scheme_count=int(meta["scheme_count"]) if meta.get("scheme_count") is not None else None,
        document_count=int(meta["document_count"]) if meta.get("document_count") is not None else None,
    )


@router.get("/config", response_model=UiConfigResponse)
def ui_config(api_config: ApiConfig = Depends(get_api_config)) -> UiConfigResponse:
    return UiConfigResponse(
        welcome_message=api_config.welcome_message,
        disclaimer=api_config.disclaimer,
        example_questions=list(api_config.example_questions),
    )


@router.get("/schemes", response_model=SchemesResponse)
def list_schemes(api_config: ApiConfig = Depends(get_api_config)) -> SchemesResponse:
    locked = load_locked_sources(api_config.sources_path)
    schemes = [
        SchemeItem(
            id=source.id,
            scheme_name=source.scheme_name,
            url=source.url,
            tags=list(source.tags),
        )
        for source in locked.enabled_sources()
    ]
    return SchemesResponse(schemes=schemes)


@router.get("/metrics", response_model=MetricsResponse)
def metrics() -> MetricsResponse:
    snapshot = build_dashboard_snapshot()
    payload = snapshot_to_dict(snapshot)
    return MetricsResponse(**payload)


@router.post("/chat", response_model=ChatResponseBody)
def post_chat(
    body: ChatRequest,
    index: CorpusIndex = Depends(get_corpus_index),
    api_config: ApiConfig = Depends(get_api_config),
) -> ChatResponseBody:
    meta = _index_meta(api_config.index_active_dir)
    if meta.get("status") != "ok":
        raise HTTPException(
            status_code=503,
            detail="The knowledge index is temporarily unavailable. Please try again later.",
        )

    if body.selected_scheme:
        locked = load_locked_sources(api_config.sources_path)
        valid_ids = {source.id for source in locked.enabled_sources()}
        if body.selected_scheme not in valid_ids:
            raise HTTPException(
                status_code=400,
                detail="selected_scheme must be one of the locked scheme ids from GET /schemes",
            )

    try:
        result = chat(
            body.message.strip(),
            selected_scheme_id=body.selected_scheme,
            index=index,
        )
    except IndexingError as exc:
        raise HTTPException(
            status_code=503,
            detail="The knowledge index is temporarily unavailable. Please try again later.",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Something went wrong while processing your question. Please try again.",
        ) from exc

    return ChatResponseBody(
        answer_text=result.answer_text,
        citation_url=result.citation_url,
        last_updated_date=result.last_updated_date,
        refusal=result.refusal,
        reason=result.reason,
    )
