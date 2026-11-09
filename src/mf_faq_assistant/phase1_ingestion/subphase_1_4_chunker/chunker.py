from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path
from typing import Any

from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.corpus_builder import (
    MUST_HAVE_ANCHOR_NAMES,
)

CHUNKER_VERSION = "1.0.0"
SUB_CHUNK_CHAR_LIMIT = 1500
OVERLAP_CHARS = 100

ATOMIC_SECTIONS = frozenset({"Fund Details", "Minimum Investments"})
REQUIRED_ANCHORS = MUST_HAVE_ANCHOR_NAMES

EXCLUDED_SNIPPETS = (
    "Holdings (",
    "Return calculator",
    "Would've become",
    "Fund management",
    "faq567Ques",
)

EXIT_LOAD_CURRENT_MARKERS = (
    "Exit load, stamp duty and tax",
    "Stamp duty on investment",
)

DATE_ENTRY_PATTERN = re.compile(r"(?=\d{2} \w{3} \d{4} )")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


class ChunkingError(ValueError):
    pass


@dataclass(frozen=True)
class ChunkingResult:
    scheme_id: str
    scheme_name: str
    run_id: str
    chunk_count: int
    chunked_at_utc: str
    chunks_path: str
    meta_path: str


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def section_to_slug(section_name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", section_name.lower()).strip("_")


def _validate_corpus_health(corpus: dict[str, Any]) -> None:
    if corpus.get("extraction_health") != "ok":
        raise ChunkingError(
            f"Corpus extraction_health is not ok: {corpus.get('extraction_health')}"
        )

    anchors = corpus.get("must_have_anchors") or {}
    missing = [name for name in REQUIRED_ANCHORS if not anchors.get(name)]
    if missing:
        raise ChunkingError(f"Missing required anchors: {missing}")


def _validate_chunk_text(text: str) -> None:
    for snippet in EXCLUDED_SNIPPETS:
        if snippet in text:
            raise ChunkingError(f"Chunk contains excluded content: {snippet!r}")


def _split_with_overlap(parts: list[str], *, overlap_chars: int = OVERLAP_CHARS) -> list[str]:
    if not parts:
        return []

    chunks: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not chunks:
            chunks.append(part)
            continue

        prev = chunks[-1]
        overlap = prev[-overlap_chars:] if len(prev) > overlap_chars else prev
        chunks.append(f"{overlap} {part}".strip())

    return chunks


def _split_long_text(text: str, section_name: str) -> list[str]:
    if len(text) <= SUB_CHUNK_CHAR_LIMIT:
        return [text]

    if section_name == "Exit Load and Tax":
        parts = [p.strip() for p in DATE_ENTRY_PATTERN.split(text) if p.strip()]
        if len(parts) > 1:
            chunks = _split_with_overlap(parts)
            if all(len(c) <= SUB_CHUNK_CHAR_LIMIT for c in chunks):
                return chunks

    sentences = [s.strip() for s in SENTENCE_SPLIT_PATTERN.split(text) if s.strip()]
    if len(sentences) <= 1:
        return [text]

    grouped: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= SUB_CHUNK_CHAR_LIMIT:
            current = candidate
        else:
            if current:
                grouped.append(current)
            current = sentence
    if current:
        grouped.append(current)

    return _split_with_overlap(grouped) if len(grouped) > 1 else grouped


def _section_chunks(
    *,
    corpus: dict[str, Any],
    run_id: str,
    section: dict[str, str],
    shadow_fields: dict[str, str],
) -> list[dict[str, Any]]:
    section_name = str(section["name"])
    section_source = str(section["source"])
    text = str(section["text"]).strip()
    if not text:
        return []

    _validate_chunk_text(text)

    if section_name in ATOMIC_SECTIONS:
        pieces = [text]
    else:
        pieces = _split_long_text(text, section_name)

    slug = section_to_slug(section_name)
    chunks: list[dict[str, Any]] = []
    for index, piece in enumerate(pieces):
        piece = piece.strip()
        if not piece:
            continue
        _validate_chunk_text(piece)
        chunks.append(
            {
                "chunk_id": f"{corpus['scheme_id']}:{run_id}:{slug}:{index}",
                "scheme_id": corpus["scheme_id"],
                "scheme_name": corpus["scheme_name"],
                "source_url": corpus["source_url"],
                "fetched_at": corpus["fetched_at"],
                "run_id": run_id,
                "section_name": section_name,
                "section_source": section_source,
                "chunk_index": index,
                "text": piece,
                "char_count": len(piece),
                "shadow_fields": shadow_fields,
            }
        )

    return chunks


def _validate_exit_load_chunks(chunks: list[dict[str, Any]], shadow_fields: dict[str, str]) -> None:
    exit_chunks = [c for c in chunks if c["section_name"] == "Exit Load and Tax"]
    if not exit_chunks:
        raise ChunkingError("Missing Exit Load and Tax chunk")

    markers = list(EXIT_LOAD_CURRENT_MARKERS)
    exit_load = shadow_fields.get("exit_load")
    if exit_load:
        markers.append(exit_load)

    for chunk in exit_chunks:
        text = chunk["text"]
        if any(marker.lower() in text.lower() for marker in markers):
            return

    raise ChunkingError("Exit Load and Tax chunk missing current rule text")


def _validate_atomic_sections(chunks: list[dict[str, Any]]) -> None:
    for section_name in ATOMIC_SECTIONS:
        section_chunks = [c for c in chunks if c["section_name"] == section_name]
        if len(section_chunks) != 1:
            raise ChunkingError(
                f"{section_name} must be exactly one chunk, got {len(section_chunks)}"
            )


def build_chunks(
    corpus: dict[str, Any],
    *,
    run_id: str,
    shadow_fields: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    _validate_corpus_health(corpus)

    fields = shadow_fields or {}
    all_chunks: list[dict[str, Any]] = []

    for section in corpus.get("sections", []):
        all_chunks.extend(
            _section_chunks(
                corpus=corpus,
                run_id=run_id,
                section=section,
                shadow_fields=fields,
            )
        )

    if not all_chunks:
        raise ChunkingError("No chunks produced from corpus sections")

    _validate_atomic_sections(all_chunks)
    _validate_exit_load_chunks(all_chunks, fields)

    return all_chunks


def chunk_normalized_run(
    normalized_dir: Path,
    out_dir: str | Path = "data/chunks",
) -> ChunkingResult:
    corpus_path = normalized_dir / "normalized.json"
    meta_path = normalized_dir / "meta.json"
    if not corpus_path.exists():
        raise ChunkingError(f"Missing normalized.json in {normalized_dir}")

    with open(corpus_path, encoding="utf-8") as f:
        corpus = json.load(f)

    shadow_fields: dict[str, str] = {}
    if meta_path.exists():
        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)
        raw_shadow = meta.get("shadow_fields") or {}
        shadow_fields = {str(k): str(v) for k, v in raw_shadow.items()}
        run_id = str(meta.get("raw_run_id") or normalized_dir.name)
    else:
        run_id = normalized_dir.name

    chunks = build_chunks(corpus, run_id=run_id, shadow_fields=shadow_fields)

    scheme_id = str(corpus["scheme_id"])
    dst_dir = Path(out_dir) / scheme_id / run_id
    dst_dir.mkdir(parents=True, exist_ok=True)

    chunks_path = dst_dir / "chunks.jsonl"
    out_meta_path = dst_dir / "meta.json"
    chunked_at = _utc_now_z()

    with open(chunks_path, "w", encoding="utf-8") as f:
        for chunk in chunks:
            f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    out_meta = {
        "scheme_id": scheme_id,
        "scheme_name": corpus.get("scheme_name"),
        "run_id": run_id,
        "source_url": corpus.get("source_url"),
        "fetched_at": corpus.get("fetched_at"),
        "status": "ok",
        "chunk_count": len(chunks),
        "chunked_at_utc": chunked_at,
        "chunker_version": CHUNKER_VERSION,
        "chunks_path": "chunks.jsonl",
    }
    out_meta_path.write_text(json.dumps(out_meta, indent=2), encoding="utf-8")

    return ChunkingResult(
        scheme_id=scheme_id,
        scheme_name=str(corpus.get("scheme_name", "")),
        run_id=run_id,
        chunk_count=len(chunks),
        chunked_at_utc=chunked_at,
        chunks_path=os.fspath(chunks_path),
        meta_path=os.fspath(out_meta_path),
    )


def chunk_all_latest(
    normalized_root: str | Path = "data/normalized",
    out_dir: str | Path = "data/chunks",
    continue_on_error: bool = False,
) -> list[ChunkingResult]:
    root = Path(normalized_root)
    if not root.exists():
        raise ChunkingError(f"Normalized root not found: {normalized_root}")

    results: list[ChunkingResult] = []
    for source_dir in sorted(root.iterdir()):
        if not source_dir.is_dir():
            continue
        run_dirs = sorted(p for p in source_dir.iterdir() if p.is_dir())
        if not run_dirs:
            continue
        latest = run_dirs[-1]
        try:
            results.append(chunk_normalized_run(latest, out_dir=out_dir))
        except ChunkingError:
            if not continue_on_error:
                raise
    return results
