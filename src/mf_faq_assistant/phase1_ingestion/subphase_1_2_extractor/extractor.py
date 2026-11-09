from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
import re
from pathlib import Path

from bs4 import BeautifulSoup

from mf_faq_assistant.phase1_ingestion._shared.raw_store import RawRun, discover_latest_raw_runs


class ExtractionError(ValueError):
    pass


KEY_FIELD_PATTERNS: dict[str, re.Pattern[str]] = {
    "expense_ratio": re.compile(r"expense ratio", re.IGNORECASE),
    "min_sip": re.compile(r"(min\.?\s*for\s*sip|minimum\s*sip)", re.IGNORECASE),
    "exit_load": re.compile(r"exit load", re.IGNORECASE),
    "benchmark": re.compile(r"fund benchmark|benchmark index", re.IGNORECASE),
    "nav": re.compile(r"\bnav\b", re.IGNORECASE),
}

BLOCKED_PATTERNS: tuple[str, ...] = (
    "captcha",
    "access denied",
    "unusual traffic",
    "verify you are a human",
)

BOILERPLATE_TAGS = ("script", "style", "noscript", "svg", "iframe", "header", "footer", "nav")


@dataclass(frozen=True)
class ExtractionResult:
    source_id: str
    scheme_name: str
    raw_run_id: str
    char_count: int
    fields_found: tuple[str, ...]
    extracted_at_utc: str
    extracted_path: str
    meta_path: str


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _detect_fields(text: str) -> list[str]:
    found: list[str] = []
    for name, pattern in KEY_FIELD_PATTERNS.items():
        if pattern.search(text):
            found.append(name)
    return found


def _looks_blocked(text: str) -> bool:
    snippet = text[:8000].lower()
    return any(token in snippet for token in BLOCKED_PATTERNS)


def _focus_scheme_content(text: str) -> str:
    lines = text.splitlines()
    start = 0
    for i, line in enumerate(lines):
        if re.search(r"direct growth|direct plan growth|etf fof", line, re.IGNORECASE):
            start = i
            break
        if re.search(r"expense ratio|min\.?\s*for\s*sip|nav\s*:", line, re.IGNORECASE):
            start = max(0, i - 1)
            break
    return "\n".join(lines[start:]).strip()


def extract_html(html: str, *, min_chars: int = 500, min_fields: int = 2) -> tuple[str, tuple[str, ...]]:
    soup = BeautifulSoup(html, "html.parser")

    for tag_name in BOILERPLATE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Groww pages often keep the meaningful content in the body.
    root = soup.body or soup
    text = root.get_text("\n", strip=True)
    text = _focus_scheme_content(text)
    text = re.sub(r"\n{3,}", "\n\n", text)

    if not text or len(text) < min_chars:
        raise ExtractionError(f"Extracted text too short ({len(text)} chars)")

    if _looks_blocked(text):
        raise ExtractionError("Extracted content looks like a blocked/challenge page")

    fields = _detect_fields(text)
    if len(fields) < min_fields:
        raise ExtractionError(f"Missing expected scheme fields (found: {fields})")

    return text, tuple(fields)


def extract_run(
    run: RawRun,
    out_dir: str | Path = "data/extracted",
) -> ExtractionResult:
    html = run.raw_path.read_text(encoding="utf-8", errors="replace")
    text, fields = extract_html(html)

    dst_dir = Path(out_dir) / run.source_id / run.run_id
    dst_dir.mkdir(parents=True, exist_ok=True)

    extracted_path = dst_dir / "extracted.txt"
    meta_path = dst_dir / "meta.json"
    extracted_at = _utc_now_z()

    extracted_path.write_text(text, encoding="utf-8")
    meta = {
        "source_id": run.source_id,
        "scheme_name": run.meta.get("scheme_name"),
        "raw_run_id": run.run_id,
        "requested_url": run.meta.get("requested_url"),
        "final_url": run.meta.get("final_url"),
        "status": "ok",
        "char_count": len(text),
        "fields_found": list(fields),
        "extracted_at_utc": extracted_at,
        "raw_sha256": run.meta.get("sha256"),
        "fetched_at_utc": run.meta.get("fetched_at_utc"),
    }
    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

    return ExtractionResult(
        source_id=run.source_id,
        scheme_name=str(run.meta.get("scheme_name", "")),
        raw_run_id=run.run_id,
        char_count=len(text),
        fields_found=fields,
        extracted_at_utc=extracted_at,
        extracted_path=os.fspath(extracted_path),
        meta_path=os.fspath(meta_path),
    )


def extract_all_latest(
    raw_root: str | Path = "data/raw",
    out_dir: str | Path = "data/extracted",
    continue_on_error: bool = False,
) -> list[ExtractionResult]:
    runs = discover_latest_raw_runs(raw_root)
    if not runs:
        raise ExtractionError(f"No successful raw runs found under {raw_root}")

    results: list[ExtractionResult] = []
    for run in runs:
        try:
            results.append(extract_run(run, out_dir=out_dir))
        except ExtractionError:
            if not continue_on_error:
                raise
    return results
