from __future__ import annotations

from fastapi import HTTPException, Request

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex
from mf_faq_assistant.phase4_ui.subphase_4_backend.config import ApiConfig, load_api_config

_INDEX_UNAVAILABLE = "The knowledge index is temporarily unavailable. Please try again later."


def get_api_config() -> ApiConfig:
    return load_api_config()


def get_corpus_index(request: Request) -> CorpusIndex:
    index = getattr(request.app.state, "corpus_index", None)
    if index is None:
        raise HTTPException(status_code=503, detail=_INDEX_UNAVAILABLE)
    return index
