from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any

import yaml

from mf_faq_assistant.phase0_governance.sources import LockedSources, load_locked_sources
from mf_faq_assistant.phase1_ingestion.subphase_1_1_fetcher.playwright_fetcher import (
    fetch_all_playwright,
)
from mf_faq_assistant.phase1_ingestion.subphase_1_2_extractor.extractor import extract_all_latest
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.corpus_builder import (
    MUST_HAVE_ANCHOR_NAMES,
)
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.normalizer import (
    normalize_all_latest,
)
from mf_faq_assistant.phase1_ingestion.subphase_1_4_chunker.chunker import chunk_all_latest
from mf_faq_assistant.phase1_ingestion.subphase_1_5_embedder.embedder import embed_all_latest
from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import (
    ACTIVE_DIR,
    index_all_latest,
)

REFRESH_VERSION = "1.0.0"
DEFAULT_CONFIG_PATH = "config/refresh.yaml"
DEFAULT_REPORT_PATH = Path("data/refresh/refresh_report.json")

REQUIRED_ANCHORS = MUST_HAVE_ANCHOR_NAMES


class RefreshError(ValueError):
    pass


@dataclass(frozen=True)
class RefreshConfig:
    refresh_version: str
    expected_schemes: int
    expected_chunks_per_scheme: int
    expected_embeddings_per_scheme: int
    expected_index_documents: int
    sources_path: str
    cron: str


@dataclass
class SchemeHealth:
    scheme_id: str
    raw_ok: bool = False
    extracted_ok: bool = False
    normalized_ok: bool = False
    chunks_ok: bool = False
    embeddings_ok: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RefreshResult:
    status: str
    scheme_count: int
    indexed_documents: int
    refreshed_at_utc: str
    report_path: str
    active_index_path: str


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_refresh_config(path: str | Path = DEFAULT_CONFIG_PATH) -> RefreshConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise RefreshError(f"Refresh config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise RefreshError(f"Invalid refresh config: {config_path}")

    return RefreshConfig(
        refresh_version=str(raw.get("refresh_version", REFRESH_VERSION)),
        expected_schemes=int(raw["expected_schemes"]),
        expected_chunks_per_scheme=int(raw["expected_chunks_per_scheme"]),
        expected_embeddings_per_scheme=int(raw["expected_embeddings_per_scheme"]),
        expected_index_documents=int(raw["expected_index_documents"]),
        sources_path=str(raw.get("sources_path", "config/sources.yaml")),
        cron=str(raw.get("cron", "0 2 * * 0")),
    )


def _latest_run_dir(root: Path, scheme_id: str) -> Path | None:
    scheme_dir = root / scheme_id
    if not scheme_dir.is_dir():
        return None
    run_dirs = sorted(p for p in scheme_dir.iterdir() if p.is_dir())
    return run_dirs[-1] if run_dirs else None


def _read_meta(run_dir: Path) -> dict[str, Any]:
    meta_path = run_dir / "meta.json"
    if not meta_path.exists():
        raise RefreshError(f"Missing meta.json in {run_dir}")
    with open(meta_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise RefreshError(f"Invalid meta.json in {run_dir}")
    return data


def _validate_scheme_layers(
    scheme_id: str,
    *,
    config: RefreshConfig,
) -> SchemeHealth:
    health = SchemeHealth(scheme_id=scheme_id)

    raw_run = _latest_run_dir(Path("data/raw"), scheme_id)
    if raw_run is None:
        health.errors.append("missing raw run")
    else:
        raw_meta = _read_meta(raw_run)
        health.raw_ok = raw_meta.get("status") == "ok"
        if not health.raw_ok:
            health.errors.append(f"raw status={raw_meta.get('status')}")

    extracted_run = _latest_run_dir(Path("data/extracted"), scheme_id)
    if extracted_run is None:
        health.errors.append("missing extracted run")
    else:
        extracted_meta = _read_meta(extracted_run)
        health.extracted_ok = extracted_meta.get("status") == "ok"
        if not health.extracted_ok:
            health.errors.append(f"extracted status={extracted_meta.get('status')}")

    normalized_run = _latest_run_dir(Path("data/normalized"), scheme_id)
    if normalized_run is None:
        health.errors.append("missing normalized run")
    else:
        norm_meta = _read_meta(normalized_run)
        corpus_path = normalized_run / "normalized.json"
        health.normalized_ok = norm_meta.get("status") == "ok" and corpus_path.exists()
        if not health.normalized_ok:
            health.errors.append(f"normalized status={norm_meta.get('status')}")
        else:
            with open(corpus_path, encoding="utf-8") as f:
                corpus = json.load(f)
            if corpus.get("extraction_health") != "ok":
                health.normalized_ok = False
                health.errors.append("extraction_health not ok")
            anchors = corpus.get("must_have_anchors") or {}
            missing = [name for name in REQUIRED_ANCHORS if not anchors.get(name)]
            if missing:
                health.normalized_ok = False
                health.errors.append(f"missing anchors: {missing}")

    chunk_run = _latest_run_dir(Path("data/chunks"), scheme_id)
    if chunk_run is None:
        health.errors.append("missing chunk run")
    else:
        chunk_meta = _read_meta(chunk_run)
        health.chunks_ok = (
            chunk_meta.get("status") == "ok"
            and chunk_meta.get("chunk_count") == config.expected_chunks_per_scheme
        )
        if not health.chunks_ok:
            health.errors.append(f"chunk_count={chunk_meta.get('chunk_count')}")

    embedding_run = _latest_run_dir(Path("data/embeddings"), scheme_id)
    if embedding_run is None:
        health.errors.append("missing embedding run")
    else:
        emb_meta = _read_meta(embedding_run)
        health.embeddings_ok = (
            emb_meta.get("status") == "ok"
            and emb_meta.get("embedding_count") == config.expected_embeddings_per_scheme
        )
        if not health.embeddings_ok:
            health.errors.append(f"embedding_count={emb_meta.get('embedding_count')}")

    return health


def validate_corpus_health(
    locked: LockedSources | None = None,
    *,
    config: RefreshConfig | None = None,
) -> list[SchemeHealth]:
    cfg = config or load_refresh_config()
    sources = locked or load_locked_sources(cfg.sources_path)
    enabled = [s for s in sources.enabled_sources()]

    if len(enabled) != cfg.expected_schemes:
        raise RefreshError(
            f"Expected {cfg.expected_schemes} enabled sources, got {len(enabled)}"
        )

    return [_validate_scheme_layers(source.id, config=cfg) for source in enabled]


def validate_active_index(
    *,
    config: RefreshConfig | None = None,
    active_dir: Path = ACTIVE_DIR,
) -> dict[str, Any]:
    cfg = config or load_refresh_config()
    meta_path = active_dir / "meta.json"
    if not meta_path.exists():
        raise RefreshError(f"Active index missing: {meta_path}")

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)

    if meta.get("status") != "ok":
        raise RefreshError(f"Active index status not ok: {meta.get('status')}")
    if meta.get("document_count") != cfg.expected_index_documents:
        raise RefreshError(
            f"Expected {cfg.expected_index_documents} indexed documents, "
            f"got {meta.get('document_count')}"
        )
    if meta.get("scheme_count") != cfg.expected_schemes:
        raise RefreshError(
            f"Expected {cfg.expected_schemes} indexed schemes, got {meta.get('scheme_count')}"
        )
    if not (active_dir / "chroma").exists():
        raise RefreshError("Active Chroma store missing")
    if not (active_dir / "keyword_index.json").exists():
        raise RefreshError("Active keyword index missing")

    return meta


def _assert_all_healthy(health_rows: list[SchemeHealth]) -> None:
    failures = [row for row in health_rows if row.errors]
    if failures:
        details = "; ".join(f"{row.scheme_id}: {', '.join(row.errors)}" for row in failures)
        raise RefreshError(f"Corpus health check failed: {details}")


def write_refresh_report(
    report: dict[str, Any],
    path: str | Path = DEFAULT_REPORT_PATH,
) -> str:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return os.fspath(report_path)


def run_refresh_pipeline(
    *,
    config: RefreshConfig | None = None,
    skip_fetch: bool = False,
    report_path: str | Path = DEFAULT_REPORT_PATH,
) -> RefreshResult:
    cfg = config or load_refresh_config()
    locked = load_locked_sources(cfg.sources_path)
    refreshed_at = _utc_now_z()
    phase_timings: dict[str, str] = {}

    try:
        if not skip_fetch:
            phase_timings["fetch_started"] = _utc_now_z()
            fetch_all_playwright(locked, continue_on_error=False)
            phase_timings["fetch_completed"] = _utc_now_z()

        phase_timings["extract_normalize_started"] = _utc_now_z()
        extract_all_latest(continue_on_error=False)
        normalize_all_latest(continue_on_error=False)
        phase_timings["extract_normalize_completed"] = _utc_now_z()

        health_after_normalize = validate_corpus_health(locked, config=cfg)
        _assert_all_healthy(health_after_normalize)

        phase_timings["chunk_started"] = _utc_now_z()
        chunk_all_latest(continue_on_error=False)
        phase_timings["chunk_completed"] = _utc_now_z()

        health_after_chunk = validate_corpus_health(locked, config=cfg)
        _assert_all_healthy(health_after_chunk)

        phase_timings["embed_started"] = _utc_now_z()
        embed_all_latest(continue_on_error=False)
        phase_timings["embed_completed"] = _utc_now_z()

        health_after_embed = validate_corpus_health(locked, config=cfg)
        _assert_all_healthy(health_after_embed)

        phase_timings["index_started"] = _utc_now_z()
        index_result = index_all_latest()
        phase_timings["index_completed"] = _utc_now_z()

        active_meta = validate_active_index(config=cfg)
        health_rows = validate_corpus_health(locked, config=cfg)

        report = {
            "status": "ok",
            "refresh_version": cfg.refresh_version,
            "refreshed_at_utc": refreshed_at,
            "scheme_count": len(health_rows),
            "indexed_documents": index_result.document_count,
            "active_index_path": index_result.active_dir,
            "indexed_at_utc": active_meta.get("indexed_at_utc"),
            "embedding_model_id": active_meta.get("embedding_model_id"),
            "phase_timings": phase_timings,
            "schemes": [
                {
                    "scheme_id": row.scheme_id,
                    "raw_ok": row.raw_ok,
                    "extracted_ok": row.extracted_ok,
                    "normalized_ok": row.normalized_ok,
                    "chunks_ok": row.chunks_ok,
                    "embeddings_ok": row.embeddings_ok,
                    "errors": row.errors,
                }
                for row in health_rows
            ],
        }
        out_path = write_refresh_report(report, report_path)
        return RefreshResult(
            status="ok",
            scheme_count=len(health_rows),
            indexed_documents=index_result.document_count,
            refreshed_at_utc=refreshed_at,
            report_path=out_path,
            active_index_path=index_result.active_dir,
        )
    except Exception as exc:
        failed_report = {
            "status": "failed",
            "refresh_version": cfg.refresh_version,
            "refreshed_at_utc": refreshed_at,
            "error": str(exc),
            "phase_timings": phase_timings,
            "note": "Active index unchanged if indexing step did not complete.",
        }
        write_refresh_report(failed_report, report_path)
        raise RefreshError(str(exc)) from exc
