from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gc
import json
import os
import re
import shutil
import tempfile
from pathlib import Path
from typing import Any

import yaml

from mf_faq_assistant.phase0_governance.sources import load_locked_sources

INDEXER_VERSION = "1.0.0"
DEFAULT_CONFIG_PATH = "config/index.yaml"
DEFAULT_SOURCES_PATH = "config/sources.yaml"
DEFAULT_INDEX_ROOT = Path("data/index")
STAGING_DIR = DEFAULT_INDEX_ROOT / "staging"
ACTIVE_DIR = DEFAULT_INDEX_ROOT / "active"
PREVIOUS_DIR = DEFAULT_INDEX_ROOT / "previous"

FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "expense_ratio": ("expense", "ratio", "ter", "fee"),
    "min_sip": ("sip", "minimum", "min", "monthly"),
    "exit_load": ("exit", "load", "redemption", "redeem"),
    "benchmark": ("benchmark",),
    "risk": ("risk", "riskometer"),
    "lock_in": ("lock", "lockin", "lock-in"),
}

TOKEN_PATTERN = re.compile(r"[a-z0-9]+(?:\.[0-9]+%?)?%?|₹[0-9,]+", re.IGNORECASE)


class IndexingError(ValueError):
    pass


@dataclass(frozen=True)
class IndexConfig:
    indexer_version: str
    expected_schemes: int
    expected_embeddings: int
    vector_store: str
    collection_name: str
    distance_metric: str
    keyword_index_enabled: bool


@dataclass(frozen=True)
class IndexingResult:
    document_count: int
    scheme_count: int
    indexed_at_utc: str
    active_dir: str
    meta_path: str


@dataclass(frozen=True)
class IndexHit:
    chunk_id: str
    score: float
    scheme_id: str
    scheme_name: str
    section_name: str
    source_url: str
    embedded_text: str


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_rmtree(path: Path) -> None:
    if not path.exists():
        return
    gc.collect()
    shutil.rmtree(path, ignore_errors=True)


def load_index_config(path: str | Path = DEFAULT_CONFIG_PATH) -> IndexConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise IndexingError(f"Index config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise IndexingError(f"Invalid index config: {config_path}")

    return IndexConfig(
        indexer_version=str(raw.get("indexer_version", INDEXER_VERSION)),
        expected_schemes=int(raw["expected_schemes"]),
        expected_embeddings=int(raw["expected_embeddings"]),
        vector_store=str(raw.get("vector_store", "chromadb")),
        collection_name=str(raw.get("collection_name", "mf_faq_corpus")),
        distance_metric=str(raw.get("distance_metric", "cosine")),
        keyword_index_enabled=bool(raw.get("keyword_index_enabled", True)),
    )


def load_latest_embedding_records(embeddings_root: str | Path = "data/embeddings") -> list[dict[str, Any]]:
    root = Path(embeddings_root)
    if not root.exists():
        raise IndexingError(f"Embeddings root not found: {embeddings_root}")

    records: list[dict[str, Any]] = []
    for source_dir in sorted(root.iterdir()):
        if not source_dir.is_dir():
            continue
        run_dirs = sorted(p for p in source_dir.iterdir() if p.is_dir())
        if not run_dirs:
            continue
        latest = run_dirs[-1]
        emb_path = latest / "embeddings.jsonl"
        meta_path = latest / "meta.json"
        if not emb_path.exists() or not meta_path.exists():
            raise IndexingError(f"Missing embedding artifacts in {latest}")

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        if meta.get("status") != "ok":
            raise IndexingError(f"Embedding run not ok: {latest}")

        for line in emb_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))

    return records


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text.lower()) if token.strip()]


def build_keyword_index(records: list[dict[str, Any]]) -> dict[str, Any]:
    terms: dict[str, set[str]] = {}
    fields: dict[str, dict[str, set[str]]] = {}

    def add_term(term: str, chunk_id: str) -> None:
        normalized = term.lower().strip()
        if not normalized:
            return
        terms.setdefault(normalized, set()).add(chunk_id)

    for record in records:
        chunk_id = str(record["chunk_id"])
        add_term(str(record.get("section_name", "")), chunk_id)
        for token in _tokenize(str(record.get("scheme_name", ""))):
            add_term(token, chunk_id)
        for token in _tokenize(str(record.get("embedded_text", ""))):
            add_term(token, chunk_id)

        shadow = record.get("shadow_fields") or {}
        for field_name, field_value in shadow.items():
            if not field_value:
                continue
            value = str(field_value)
            fields.setdefault(field_name, {}).setdefault(value, set()).add(chunk_id)
            add_term(field_name.replace("_", " "), chunk_id)
            for token in _tokenize(value):
                add_term(token, chunk_id)
            for alias in FIELD_ALIASES.get(field_name, ()):
                add_term(alias, chunk_id)

    return {
        "indexer_version": INDEXER_VERSION,
        "chunk_count": len(records),
        "terms": {term: sorted(chunk_ids) for term, chunk_ids in sorted(terms.items())},
        "fields": {
            field: {value: sorted(chunk_ids) for value, chunk_ids in sorted(values.items())}
            for field, values in sorted(fields.items())
        },
    }


def _chroma_metadata(record: dict[str, Any]) -> dict[str, str]:
    shadow = record.get("shadow_fields") or {}
    metadata = {
        "chunk_id": str(record["chunk_id"]),
        "scheme_id": str(record["scheme_id"]),
        "scheme_name": str(record["scheme_name"]),
        "section_name": str(record["section_name"]),
        "source_url": str(record["source_url"]),
        "fetched_at": str(record["fetched_at"]),
        "run_id": str(record["run_id"]),
        "embedding_model_id": str(record["embedding_model_id"]),
    }
    for key in ("expense_ratio", "min_sip", "exit_load", "benchmark", "risk", "lock_in"):
        value = shadow.get(key)
        if value:
            metadata[key] = str(value)
    return metadata


def _build_chroma_index(
    records: list[dict[str, Any]],
    *,
    chroma_dir: Path,
    config: IndexConfig,
) -> None:
    if config.vector_store != "chromadb":
        raise IndexingError(f"Unsupported vector store: {config.vector_store}")

    try:
        import chromadb
    except ImportError as exc:
        raise IndexingError(
            "chromadb is required for indexing. Install with: pip install chromadb"
        ) from exc

    _safe_rmtree(chroma_dir)
    chroma_dir.mkdir(parents=True, exist_ok=True)

    client = chromadb.PersistentClient(path=os.fspath(chroma_dir))
    collection = client.get_or_create_collection(
        name=config.collection_name,
        metadata={"hnsw:space": config.distance_metric},
    )

    collection.add(
        ids=[str(record["chunk_id"]) for record in records],
        embeddings=[record["embedding"] for record in records],
        documents=[str(record["embedded_text"]) for record in records],
        metadatas=[_chroma_metadata(record) for record in records],
    )
    del collection
    del client
    gc.collect()


def _validate_records(records: list[dict[str, Any]], config: IndexConfig) -> None:
    if len(records) != config.expected_embeddings:
        raise IndexingError(
            f"Expected {config.expected_embeddings} embeddings, got {len(records)}"
        )

    scheme_ids = {str(record["scheme_id"]) for record in records}
    if len(scheme_ids) != config.expected_schemes:
        raise IndexingError(
            f"Expected {config.expected_schemes} schemes, got {len(scheme_ids)}"
        )

    locked = load_locked_sources(DEFAULT_SOURCES_PATH)
    allowlisted_ids = {source.id for source in locked.enabled_sources()}
    unknown = scheme_ids - allowlisted_ids
    if unknown:
        raise IndexingError(f"Non-allowlisted scheme_ids in embeddings: {sorted(unknown)}")

    model_ids = {str(record["embedding_model_id"]) for record in records}
    if len(model_ids) != 1:
        raise IndexingError(f"Mixed embedding models in corpus: {sorted(model_ids)}")

    dimensions = {len(record["embedding"]) for record in records}
    if len(dimensions) != 1:
        raise IndexingError(f"Mixed embedding dimensions: {sorted(dimensions)}")

    chunk_ids = [str(record["chunk_id"]) for record in records]
    if len(chunk_ids) != len(set(chunk_ids)):
        raise IndexingError("Duplicate chunk_id values found in embedding records")


def _write_documents_manifest(records: list[dict[str, Any]], path: Path) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for record in records:
            row = {
                "chunk_id": record["chunk_id"],
                "scheme_id": record["scheme_id"],
                "scheme_name": record["scheme_name"],
                "section_name": record["section_name"],
                "source_url": record["source_url"],
                "fetched_at": record["fetched_at"],
                "embedded_text": record["embedded_text"],
                "shadow_fields": record.get("shadow_fields") or {},
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_index(
    records: list[dict[str, Any]],
    *,
    staging_dir: Path,
    config: IndexConfig,
    indexed_at: str | None = None,
) -> dict[str, Any]:
    _validate_records(records, config)

    _safe_rmtree(staging_dir)
    staging_dir.mkdir(parents=True, exist_ok=True)

    timestamp = indexed_at or _utc_now_z()
    _build_chroma_index(records, chroma_dir=staging_dir / "chroma", config=config)

    keyword_index: dict[str, Any] | None = None
    if config.keyword_index_enabled:
        keyword_index = build_keyword_index(records)
        keyword_index["indexed_at_utc"] = timestamp
        (staging_dir / "keyword_index.json").write_text(
            json.dumps(keyword_index, indent=2),
            encoding="utf-8",
        )

    _write_documents_manifest(records, staging_dir / "documents.jsonl")

    scheme_ids = sorted({str(record["scheme_id"]) for record in records})
    meta = {
        "status": "ok",
        "indexer_version": config.indexer_version,
        "indexed_at_utc": timestamp,
        "document_count": len(records),
        "scheme_count": len(scheme_ids),
        "scheme_ids": scheme_ids,
        "embedding_model_id": records[0]["embedding_model_id"],
        "embedding_dimensions": len(records[0]["embedding"]),
        "vector_store": config.vector_store,
        "collection_name": config.collection_name,
        "distance_metric": config.distance_metric,
        "keyword_index_enabled": config.keyword_index_enabled,
        "keyword_index_path": "keyword_index.json" if keyword_index else None,
        "documents_path": "documents.jsonl",
        "chroma_path": "chroma",
    }
    (staging_dir / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return meta


def _copy_replace_dir(src: Path, dst: Path) -> None:
    _safe_rmtree(dst)
    if dst.exists():
        raise IndexingError(f"Unable to remove destination directory: {dst}")
    shutil.copytree(src, dst)


def publish_staging_index(
    staging_dir: Path = STAGING_DIR,
    active_dir: Path = ACTIVE_DIR,
    previous_dir: Path = PREVIOUS_DIR,
) -> None:
    if not staging_dir.exists() or not (staging_dir / "meta.json").exists():
        raise IndexingError(f"Staging index incomplete: {staging_dir}")

    index_root = active_dir.parent
    index_root.mkdir(parents=True, exist_ok=True)

    pending_active = index_root / f".active_pending_{os.getpid()}"
    _safe_rmtree(pending_active)
    shutil.copytree(staging_dir, pending_active)

    _safe_rmtree(previous_dir)
    if active_dir.exists():
        try:
            active_dir.replace(previous_dir)
        except OSError:
            _copy_replace_dir(active_dir, previous_dir)
            _safe_rmtree(active_dir)

    try:
        pending_active.replace(active_dir)
    except OSError as exc:
        _safe_rmtree(pending_active)
        raise IndexingError(f"Failed to publish active index: {exc}") from exc

    _safe_rmtree(staging_dir)


def index_all_latest(
    embeddings_root: str | Path = "data/embeddings",
    index_root: Path = DEFAULT_INDEX_ROOT,
    *,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> IndexingResult:
    config = load_index_config(config_path)
    records = load_latest_embedding_records(embeddings_root)
    index_root.mkdir(parents=True, exist_ok=True)
    _safe_rmtree(index_root / "staging")
    staging_dir = Path(tempfile.mkdtemp(prefix="staging_", dir=index_root))
    try:
        meta = build_index(records, staging_dir=staging_dir, config=config)
        publish_staging_index(
            staging_dir=staging_dir,
            active_dir=index_root / "active",
            previous_dir=index_root / "previous",
        )
    finally:
        _safe_rmtree(staging_dir)

    active_dir = index_root / "active"
    return IndexingResult(
        document_count=int(meta["document_count"]),
        scheme_count=int(meta["scheme_count"]),
        indexed_at_utc=str(meta["indexed_at_utc"]),
        active_dir=os.fspath(active_dir),
        meta_path=os.fspath(active_dir / "meta.json"),
    )


class CorpusIndex:
    def __init__(self, active_dir: str | Path = ACTIVE_DIR) -> None:
        self.active_dir = Path(active_dir)
        meta_path = self.active_dir / "meta.json"
        if not meta_path.exists():
            raise IndexingError(f"Active index not found: {meta_path}")

        with open(meta_path, encoding="utf-8") as f:
            self.meta = json.load(f)

        self._documents = {
            row["chunk_id"]: row
            for row in self._load_documents(self.active_dir / "documents.jsonl")
        }

        keyword_path = self.active_dir / "keyword_index.json"
        self._keyword_index = None
        if keyword_path.exists():
            with open(keyword_path, encoding="utf-8") as f:
                self._keyword_index = json.load(f)

        try:
            import chromadb
        except ImportError as exc:
            raise IndexingError("chromadb is required to query the index") from exc

        self._client = chromadb.PersistentClient(path=os.fspath(self.active_dir / "chroma"))
        self._collection = self._client.get_collection(name=str(self.meta["collection_name"]))

    def get_documents_for_scheme(self, scheme_id: str) -> list[dict[str, Any]]:
        return [
            doc
            for doc in self._documents.values()
            if str(doc.get("scheme_id")) == scheme_id
        ]

    def close(self) -> None:
        if hasattr(self, "_collection"):
            del self._collection
        if hasattr(self, "_client"):
            del self._client
        gc.collect()

    @staticmethod
    def _load_documents(path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
        return rows

    def search_vector(self, query: str, *, top_k: int = 5) -> list[IndexHit]:
        from mf_faq_assistant.phase1_ingestion.subphase_1_5_embedder.embedder import (
            _default_encode,
            load_embedding_config,
        )

        cfg = load_embedding_config()
        vector = _default_encode([query], cfg)[0]
        result = self._collection.query(
            query_embeddings=[vector],
            n_results=min(top_k, len(self._documents)),
            include=["metadatas", "documents", "distances"],
        )

        hits: list[IndexHit] = []
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for chunk_id, distance in zip(ids, distances):
            doc = self._documents.get(chunk_id, {})
            # Chroma cosine distance: lower is better; convert to similarity-like score.
            score = 1.0 - float(distance)
            hits.append(
                IndexHit(
                    chunk_id=chunk_id,
                    score=score,
                    scheme_id=str(doc.get("scheme_id", "")),
                    scheme_name=str(doc.get("scheme_name", "")),
                    section_name=str(doc.get("section_name", "")),
                    source_url=str(doc.get("source_url", "")),
                    embedded_text=str(doc.get("embedded_text", "")),
                )
            )
        return hits

    def search_keyword(self, query: str, *, top_k: int = 5) -> list[IndexHit]:
        if not self._keyword_index:
            return []

        query_tokens = _tokenize(query)
        if not query_tokens:
            return []

        scores: dict[str, float] = {}
        terms = self._keyword_index.get("terms", {})
        fields = self._keyword_index.get("fields", {})

        for token in query_tokens:
            for chunk_id in terms.get(token, []):
                scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0

        for field_name, alias_terms in FIELD_ALIASES.items():
            if any(alias in query_tokens for alias in alias_terms):
                for value_map in fields.get(field_name, {}).values():
                    for chunk_id in value_map:
                        scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.5

        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
        hits: list[IndexHit] = []
        for chunk_id, score in ranked:
            doc = self._documents.get(chunk_id, {})
            hits.append(
                IndexHit(
                    chunk_id=chunk_id,
                    score=score,
                    scheme_id=str(doc.get("scheme_id", "")),
                    scheme_name=str(doc.get("scheme_name", "")),
                    section_name=str(doc.get("section_name", "")),
                    source_url=str(doc.get("source_url", "")),
                    embedded_text=str(doc.get("embedded_text", "")),
                )
            )
        return hits
