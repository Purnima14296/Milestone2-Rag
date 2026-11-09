from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex, IndexingError
from mf_faq_assistant.phase4_ui.subphase_4_backend.config import load_api_config
from mf_faq_assistant.phase4_ui.subphase_4_backend.routes import router

PROJECT_ROOT = Path(__file__).resolve().parents[4]
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"

API_TITLE = "Mutual Fund FAQ Assistant API"
API_DESCRIPTION = "Facts-only RAG API for locked HDFC mutual fund schemes."


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = load_api_config()
    index: CorpusIndex | None = None
    try:
        index = CorpusIndex(config.index_active_dir)
        app.state.corpus_index = index
        yield
    except IndexingError:
        app.state.corpus_index = None
        yield
    finally:
        if index is not None:
            index.close()


def create_app() -> FastAPI:
    config = load_api_config()
    app = FastAPI(
        title=API_TITLE,
        description=API_DESCRIPTION,
        version=config.api_version,
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    _mount_frontend(app)
    return app


def _mount_frontend(app: FastAPI) -> None:
    if FRONTEND_DIST.is_dir() and (FRONTEND_DIST / "index.html").exists():
        app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


app = create_app()
