from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path

from mf_faq_assistant.phase1_ingestion.subphase_1_2_extractor.extractor import KEY_FIELD_PATTERNS
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.corpus_builder import (
    build_corpus_document,
    corpus_to_plaintext,
)
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.faq_builder import (
    build_faq_document,
)


class NormalizationError(ValueError):
    pass


SHADOW_VALUE_PATTERNS: dict[str, re.Pattern[str]] = {
    "expense_ratio": re.compile(r"expense ratio[^\d]*([\d.]+%)", re.IGNORECASE),
    "min_sip": re.compile(r"(?:min\.?\s*for\s*sip|minimum\s*sip(?:\s*investment)?)[^\d₹]*₹?\s*([\d,]+)", re.IGNORECASE),
    "exit_load": re.compile(r"(exit load[^\n.]{0,160})", re.IGNORECASE),
    "benchmark": re.compile(r"(?:fund benchmark|benchmark index)\s*([^\n#]+)", re.IGNORECASE),
    "risk": re.compile(r"(?:rated |risk classification: )([^.\n]+risk)", re.IGNORECASE),
    "lock_in": re.compile(r"(lock[- ]?in[^\n.]{0,120})", re.IGNORECASE),
    "nav": re.compile(
        r"(?:NAV:\s*([^₹\n]{0,40})\s*₹([\d,.]+)|Latest NAV as of\s+(.+?)\s+is\s+₹([\d,.]+))",
        re.IGNORECASE,
    ),
    "aum": re.compile(r"Fund size \(AUM\)\s*₹([\d,.]+)\s*Cr", re.IGNORECASE),
    "manager": re.compile(
        r"((?:[A-Z][a-z]+\s+){1,3}[A-Z][a-z]+)\s+is the Current Fund Manager of",
        re.IGNORECASE,
    ),
}


@dataclass(frozen=True)
class NormalizationResult:
    source_id: str
    scheme_name: str
    raw_run_id: str
    char_count: int
    shadow_fields: dict[str, str]
    normalized_at_utc: str
    normalized_path: str
    corpus_path: str
    meta_path: str


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _extract_shadow_fields(text: str) -> dict[str, str]:
    shadow: dict[str, str] = {}
    for name, pattern in SHADOW_VALUE_PATTERNS.items():
        match = pattern.search(text)
        if not match:
            continue
        if name == "nav":
            if match.group(1) and match.group(2):
                shadow[name] = f"₹{match.group(2).strip()} as of {match.group(1).strip()}"
            elif match.group(3) and match.group(4):
                shadow[name] = f"₹{match.group(4).strip()} as of {match.group(3).strip()}"
        elif name == "aum":
            shadow[name] = f"₹{match.group(1).strip()} Cr"
        else:
            shadow[name] = match.group(1).strip()
    return shadow


def _validate_corpus_text(text: str, *, min_chars: int = 120) -> dict[str, str]:
    if len(text) < min_chars:
        raise NormalizationError(f"Normalized FAQ text too short ({len(text)} chars)")

    fields_found = [name for name, pattern in KEY_FIELD_PATTERNS.items() if pattern.search(text)]
    if len(fields_found) < 2:
        raise NormalizationError(f"Normalized FAQ text missing expected fields (found: {fields_found})")

    return _extract_shadow_fields(text)


def normalize_text(text: str, *, min_chars: int = 120) -> tuple[str, dict[str, str]]:
    normalized = build_faq_document(text)
    normalized = re.sub(r"\n{3,}", "\n\n", normalized)
    normalized = re.sub(r"[ \t]+", " ", normalized)
    shadow = _validate_corpus_text(normalized, min_chars=min_chars)
    return normalized, shadow


def _resolve_raw_html(raw_root: Path, source_id: str, run_id: str) -> str:
    raw_dir = raw_root / source_id / run_id
    candidates = list(raw_dir.glob("raw.*"))
    if not candidates:
        raise NormalizationError(f"Missing raw HTML in {raw_dir}")
    return candidates[0].read_text(encoding="utf-8", errors="replace")


def normalize_extracted_run(
    extracted_dir: Path,
    out_dir: str | Path = "data/normalized",
    raw_root: str | Path = "data/raw",
) -> NormalizationResult:
    meta_path = extracted_dir / "meta.json"
    extracted_path = extracted_dir / "extracted.txt"
    if not meta_path.exists() or not extracted_path.exists():
        raise NormalizationError(f"Missing extracted artifacts in {extracted_dir}")

    with open(meta_path, encoding="utf-8") as f:
        meta = json.load(f)
    if meta.get("status") != "ok":
        raise NormalizationError(f"Extracted run not ok: {extracted_dir}")

    source_id = str(meta["source_id"])
    run_id = str(meta["raw_run_id"])
    text = extracted_path.read_text(encoding="utf-8")
    raw_html = _resolve_raw_html(Path(raw_root), source_id, run_id)

    scheme_name = str(meta.get("scheme_name", ""))
    source_url = str(meta.get("final_url") or meta.get("requested_url") or "")
    fetched_at = str(meta.get("fetched_at_utc") or "")

    corpus = build_corpus_document(
        scheme_id=source_id,
        scheme_name=scheme_name,
        source_url=source_url,
        fetched_at=fetched_at,
        extracted_text=text,
        raw_html=raw_html,
    )

    plaintext = corpus_to_plaintext(corpus)
    shadow = _validate_corpus_text(plaintext)

    dst_dir = Path(out_dir) / source_id / run_id
    dst_dir.mkdir(parents=True, exist_ok=True)

    corpus_path = dst_dir / "normalized.json"
    normalized_path = dst_dir / "normalized.txt"
    out_meta_path = dst_dir / "meta.json"
    normalized_at = _utc_now_z()

    corpus_path.write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")
    normalized_path.write_text(plaintext, encoding="utf-8")
    out_meta = {
        "source_id": source_id,
        "scheme_id": source_id,
        "scheme_name": scheme_name,
        "raw_run_id": run_id,
        "requested_url": meta.get("requested_url"),
        "final_url": meta.get("final_url"),
        "source_url": source_url,
        "status": "ok",
        "char_count": len(plaintext),
        "shadow_fields": shadow,
        "normalized_at_utc": normalized_at,
        "extracted_at_utc": meta.get("extracted_at_utc"),
        "fetched_at_utc": fetched_at,
        "extractor_version": corpus.get("extractor_version"),
        "extraction_health": corpus.get("extraction_health"),
        "must_have_anchors": corpus.get("must_have_anchors"),
        "format": "structured_corpus_v1",
        "corpus_path": "normalized.json",
    }
    out_meta_path.write_text(json.dumps(out_meta, indent=2), encoding="utf-8")

    return NormalizationResult(
        source_id=source_id,
        scheme_name=scheme_name,
        raw_run_id=run_id,
        char_count=len(plaintext),
        shadow_fields=shadow,
        normalized_at_utc=normalized_at,
        normalized_path=os.fspath(normalized_path),
        corpus_path=os.fspath(corpus_path),
        meta_path=os.fspath(out_meta_path),
    )


def normalize_all_latest(
    extracted_root: str | Path = "data/extracted",
    out_dir: str | Path = "data/normalized",
    raw_root: str | Path = "data/raw",
    continue_on_error: bool = False,
) -> list[NormalizationResult]:
    root = Path(extracted_root)
    if not root.exists():
        raise NormalizationError(f"Extracted root not found: {extracted_root}")

    results: list[NormalizationResult] = []
    for source_dir in sorted(root.iterdir()):
        if not source_dir.is_dir():
            continue
        run_dirs = sorted(p for p in source_dir.iterdir() if p.is_dir())
        if not run_dirs:
            continue
        latest = run_dirs[-1]
        try:
            results.append(
                normalize_extracted_run(latest, out_dir=out_dir, raw_root=raw_root)
            )
        except NormalizationError:
            if not continue_on_error:
                raise
    return results
