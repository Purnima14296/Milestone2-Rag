from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
from typing import Any, Callable

import yaml

EMBEDDER_VERSION = "1.0.0"
DEFAULT_CONFIG_PATH = "config/embedding.yaml"
EMBEDDED_TEXT_TEMPLATE = "{scheme_name} | {section_name}: {text}"


class EmbeddingError(ValueError):
    pass


@dataclass(frozen=True)
class EmbeddingConfig:
    embedding_model_id: str
    library: str
    dimensions: int
    normalize: bool
    expected_chunks_per_scheme: int


@dataclass(frozen=True)
class EmbeddingResult:
    scheme_id: str
    scheme_name: str
    run_id: str
    embedding_count: int
    embedded_at_utc: str
    embeddings_path: str
    meta_path: str


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load_embedding_config(path: str | Path = DEFAULT_CONFIG_PATH) -> EmbeddingConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise EmbeddingError(f"Embedding config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise EmbeddingError(f"Invalid embedding config: {config_path}")

    return EmbeddingConfig(
        embedding_model_id=str(raw["embedding_model_id"]),
        library=str(raw.get("library", "sentence-transformers")),
        dimensions=int(raw["dimensions"]),
        normalize=bool(raw.get("normalize", True)),
        expected_chunks_per_scheme=int(raw.get("expected_chunks_per_scheme", 5)),
    )


def build_embedded_text(chunk: dict[str, Any]) -> str:
    scheme_name = str(chunk.get("scheme_name", "")).strip()
    section_name = str(chunk.get("section_name", "")).strip()
    text = str(chunk.get("text", "")).strip()
    if not scheme_name or not section_name or not text:
        raise EmbeddingError(f"Chunk missing fields for embedded text: {chunk.get('chunk_id')}")

    return EMBEDDED_TEXT_TEMPLATE.format(
        scheme_name=scheme_name,
        section_name=section_name,
        text=text,
    )


def _load_chunks(chunks_path: Path) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    with open(chunks_path, encoding="utf-8") as f:
        for line_no, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EmbeddingError(f"Invalid JSON in {chunks_path} line {line_no}") from exc
            if not isinstance(chunk, dict):
                raise EmbeddingError(f"Invalid chunk object in {chunks_path} line {line_no}")
            chunks.append(chunk)
    return chunks


def _validate_chunk_run_meta(meta: dict[str, Any], config: EmbeddingConfig) -> None:
    if meta.get("status") != "ok":
        raise EmbeddingError(f"Chunk run status is not ok: {meta.get('status')}")

    chunk_count = meta.get("chunk_count")
    if chunk_count != config.expected_chunks_per_scheme:
        raise EmbeddingError(
            f"Expected chunk_count {config.expected_chunks_per_scheme}, got {chunk_count}"
        )


def _validate_vectors(
    vectors: list[list[float]],
    *,
    config: EmbeddingConfig,
) -> None:
    if not vectors:
        raise EmbeddingError("No embedding vectors produced")

    for index, vector in enumerate(vectors):
        if not vector:
            raise EmbeddingError(f"Empty embedding vector at index {index}")
        if len(vector) != config.dimensions:
            raise EmbeddingError(
                f"Vector dimension mismatch at index {index}: "
                f"expected {config.dimensions}, got {len(vector)}"
            )
        if all(abs(value) < 1e-12 for value in vector):
            raise EmbeddingError(f"Zero-length embedding vector at index {index}")
        if config.normalize:
            norm = math.sqrt(sum(value * value for value in vector))
            if abs(norm - 1.0) > 1e-3:
                raise EmbeddingError(
                    f"Normalized vector norm expected ~1.0, got {norm:.6f} at index {index}"
                )


_MODEL_CACHE: dict[str, Any] = {}


def _default_encode(texts: list[str], config: EmbeddingConfig) -> list[list[float]]:
    if config.library != "sentence-transformers":
        raise EmbeddingError(f"Unsupported embedding library: {config.library}")

    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise EmbeddingError(
            "sentence-transformers is required for embedding. "
            "Install with: pip install sentence-transformers"
        ) from exc

    if config.embedding_model_id not in _MODEL_CACHE:
        _MODEL_CACHE[config.embedding_model_id] = SentenceTransformer(config.embedding_model_id)

    model = _MODEL_CACHE[config.embedding_model_id]
    encoded = model.encode(
        texts,
        batch_size=len(texts),
        normalize_embeddings=config.normalize,
        show_progress_bar=False,
    )
    return [vector.tolist() for vector in encoded]


def build_embedding_records(
    chunks: list[dict[str, Any]],
    vectors: list[list[float]],
    *,
    config: EmbeddingConfig,
    embedded_at: str,
) -> list[dict[str, Any]]:
    if len(chunks) != len(vectors):
        raise EmbeddingError(
            f"Chunk/vector count mismatch: {len(chunks)} chunks, {len(vectors)} vectors"
        )

    _validate_vectors(vectors, config=config)

    records: list[dict[str, Any]] = []
    for chunk, vector in zip(chunks, vectors):
        embedded_text = build_embedded_text(chunk)
        if not embedded_text.startswith(f"{chunk['scheme_name']} | {chunk['section_name']}:"):
            raise EmbeddingError(
                f"embedded_text format invalid for chunk_id {chunk.get('chunk_id')}"
            )

        shadow_fields = chunk.get("shadow_fields") or {}
        records.append(
            {
                "chunk_id": chunk["chunk_id"],
                "scheme_id": chunk["scheme_id"],
                "scheme_name": chunk["scheme_name"],
                "source_url": chunk["source_url"],
                "fetched_at": chunk["fetched_at"],
                "run_id": chunk["run_id"],
                "section_name": chunk["section_name"],
                "embedded_text": embedded_text,
                "embedding_model_id": config.embedding_model_id,
                "embedding_dimensions": config.dimensions,
                "embedding": vector,
                "shadow_fields": shadow_fields,
                "embedded_at_utc": embedded_at,
            }
        )

    chunk_ids = {str(c["chunk_id"]) for c in chunks}
    record_ids = {str(r["chunk_id"]) for r in records}
    if chunk_ids != record_ids:
        raise EmbeddingError("Embedding records do not cover all chunk_id values")

    return records


def embed_chunks(
    chunks: list[dict[str, Any]],
    *,
    config: EmbeddingConfig | None = None,
    encode_fn: Callable[[list[str], EmbeddingConfig], list[list[float]]] | None = None,
    embedded_at: str | None = None,
) -> list[dict[str, Any]]:
    if not chunks:
        raise EmbeddingError("No chunks to embed")

    cfg = config or load_embedding_config()
    texts = [build_embedded_text(chunk) for chunk in chunks]
    encoder = encode_fn or _default_encode
    vectors = encoder(texts, cfg)
    timestamp = embedded_at or _utc_now_z()
    return build_embedding_records(chunks, vectors, config=cfg, embedded_at=timestamp)


def _load_validated_chunk_run(
    chunks_dir: Path,
    config: EmbeddingConfig,
) -> tuple[Path, list[dict[str, Any]]]:
    chunks_path = chunks_dir / "chunks.jsonl"
    chunk_meta_path = chunks_dir / "meta.json"
    if not chunks_path.exists():
        raise EmbeddingError(f"Missing chunks.jsonl in {chunks_dir}")
    if not chunk_meta_path.exists():
        raise EmbeddingError(f"Missing chunk meta.json in {chunks_dir}")

    with open(chunk_meta_path, encoding="utf-8") as f:
        chunk_meta = json.load(f)
    _validate_chunk_run_meta(chunk_meta, config)

    chunks = _load_chunks(chunks_path)
    if len(chunks) != config.expected_chunks_per_scheme:
        raise EmbeddingError(
            f"Expected {config.expected_chunks_per_scheme} chunks in {chunks_path}, got {len(chunks)}"
        )
    return chunks_path, chunks


def _write_embedding_run(
    *,
    chunks_path: Path,
    chunks: list[dict[str, Any]],
    records: list[dict[str, Any]],
    out_dir: Path,
    config: EmbeddingConfig,
    embedded_at: str,
) -> EmbeddingResult:
    scheme_id = str(chunks[0]["scheme_id"])
    run_id = str(chunks[0]["run_id"])
    dst_dir = out_dir / scheme_id / run_id
    dst_dir.mkdir(parents=True, exist_ok=True)

    embeddings_path = dst_dir / "embeddings.jsonl"
    out_meta_path = dst_dir / "meta.json"

    with open(embeddings_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    out_meta = {
        "scheme_id": scheme_id,
        "scheme_name": chunks[0].get("scheme_name"),
        "run_id": run_id,
        "status": "ok",
        "embedding_count": len(records),
        "embedding_model_id": config.embedding_model_id,
        "embedding_dimensions": config.dimensions,
        "embedder_version": EMBEDDER_VERSION,
        "embedded_at_utc": embedded_at,
        "source_chunks_path": chunks_path.as_posix(),
    }
    out_meta_path.write_text(json.dumps(out_meta, indent=2), encoding="utf-8")

    return EmbeddingResult(
        scheme_id=scheme_id,
        scheme_name=str(chunks[0].get("scheme_name", "")),
        run_id=run_id,
        embedding_count=len(records),
        embedded_at_utc=embedded_at,
        embeddings_path=os.fspath(embeddings_path),
        meta_path=os.fspath(out_meta_path),
    )


def embed_chunk_run(
    chunks_dir: Path,
    out_dir: str | Path = "data/embeddings",
    *,
    config: EmbeddingConfig | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    encode_fn: Callable[[list[str], EmbeddingConfig], list[list[float]]] | None = None,
) -> EmbeddingResult:
    cfg = config or load_embedding_config(config_path)
    chunks_path, chunks = _load_validated_chunk_run(chunks_dir, cfg)

    embedded_at = _utc_now_z()
    records = embed_chunks(chunks, config=cfg, encode_fn=encode_fn, embedded_at=embedded_at)
    return _write_embedding_run(
        chunks_path=chunks_path,
        chunks=chunks,
        records=records,
        out_dir=Path(out_dir),
        config=cfg,
        embedded_at=embedded_at,
    )


def embed_all_latest(
    chunks_root: str | Path = "data/chunks",
    out_dir: str | Path = "data/embeddings",
    *,
    config: EmbeddingConfig | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
    encode_fn: Callable[[list[str], EmbeddingConfig], list[list[float]]] | None = None,
    continue_on_error: bool = False,
) -> list[EmbeddingResult]:
    root = Path(chunks_root)
    if not root.exists():
        raise EmbeddingError(f"Chunks root not found: {chunks_root}")

    cfg = config or load_embedding_config(config_path)
    runs: list[tuple[Path, Path, list[dict[str, Any]]]] = []

    for source_dir in sorted(root.iterdir()):
        if not source_dir.is_dir():
            continue
        run_dirs = sorted(p for p in source_dir.iterdir() if p.is_dir())
        if not run_dirs:
            continue
        latest = run_dirs[-1]
        try:
            chunks_path, chunks = _load_validated_chunk_run(latest, cfg)
            runs.append((latest, chunks_path, chunks))
        except EmbeddingError:
            if not continue_on_error:
                raise

    if not runs:
        raise EmbeddingError(f"No chunk runs found under {chunks_root}")

    all_chunks = [chunk for _, _, chunks in runs for chunk in chunks]
    embedded_at = _utc_now_z()
    all_records = embed_chunks(
        all_chunks,
        config=cfg,
        encode_fn=encode_fn,
        embedded_at=embedded_at,
    )

    records_by_chunk_id = {str(record["chunk_id"]): record for record in all_records}
    results: list[EmbeddingResult] = []
    out_path = Path(out_dir)

    for _, chunks_path, chunks in runs:
        records = [records_by_chunk_id[str(chunk["chunk_id"])] for chunk in chunks]
        results.append(
            _write_embedding_run(
                chunks_path=chunks_path,
                chunks=chunks,
                records=records,
                out_dir=out_path,
                config=cfg,
                embedded_at=embedded_at,
            )
        )

    return results
