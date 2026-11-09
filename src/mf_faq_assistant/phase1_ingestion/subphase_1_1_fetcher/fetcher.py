from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Iterable

import requests

from mf_faq_assistant.phase0_governance.sources import LockedSources, SourceItem


class FetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class FetchResult:
    source_id: str
    requested_url: str
    final_url: str
    status_code: int
    content_type: str | None
    content_length: int
    sha256: str
    fetched_at_utc: str
    raw_path: str
    meta_path: str


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _looks_blocked(body: bytes, content_type: str | None) -> bool:
    if not body:
        return False
    if content_type and "text/html" not in content_type.lower():
        return False
    snippet = body[:8000].lower()
    return any(
        token in snippet
        for token in (
            b"captcha",
            b"access denied",
            b"unusual traffic",
            b"verify you are a human",
            b"cloudflare",
            b"please enable javascript",
        )
    )


def fetch_all(
    locked: LockedSources,
    sources: Iterable[SourceItem] | None = None,
    out_dir: str = "data/raw",
    timeout_s: float = 30.0,
    user_agent: str = "mf-faq-assistant/0.1 (phase1-fetcher)",
    max_retries: int = 3,
    backoff_s: float = 2.0,
    continue_on_error: bool = False,
) -> list[FetchResult]:
    enabled_sources = list(sources) if sources is not None else list(locked.enabled_sources())
    if not enabled_sources:
        return []

    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": user_agent, "Accept": "*/*"})

    results: list[FetchResult] = []
    for s in enabled_sources:
        locked.require_allowed(s.url)

        for attempt in range(max_retries + 1):
            try:
                resp = session.get(s.url, timeout=timeout_s, allow_redirects=True)
                final_url = resp.url
                locked.require_allowed(final_url)

                body = resp.content or b""
                content_type = resp.headers.get("content-type")

                if resp.status_code in (403, 429) or _looks_blocked(body, content_type):
                    raise FetchError(f"Blocked/challenged: status={resp.status_code}, url={final_url}")

                fetched_at = _utc_now_z()
                content_len = len(body)
                sha = _sha256_bytes(body)

                ts_folder = fetched_at.replace(":", "").replace("-", "")
                dst_dir = out_root / s.id / ts_folder
                dst_dir.mkdir(parents=True, exist_ok=True)

                ext = ".bin"
                if content_type:
                    ct = content_type.lower()
                    if "text/html" in ct:
                        ext = ".html"
                    elif "application/pdf" in ct:
                        ext = ".pdf"
                    elif "application/json" in ct:
                        ext = ".json"

                raw_path = dst_dir / f"raw{ext}"
                meta_path = dst_dir / "meta.json"

                raw_path.write_bytes(body)
                meta = {
                    "source_id": s.id,
                    "scheme_name": s.scheme_name,
                    "requested_url": s.url,
                    "final_url": final_url,
                    "status_code": resp.status_code,
                    "content_type": content_type,
                    "content_length": content_len,
                    "sha256": sha,
                    "fetched_at_utc": fetched_at,
                }
                meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

                results.append(
                    FetchResult(
                        source_id=s.id,
                        requested_url=s.url,
                        final_url=final_url,
                        status_code=resp.status_code,
                        content_type=content_type,
                        content_length=content_len,
                        sha256=sha,
                        fetched_at_utc=fetched_at,
                        raw_path=os.fspath(raw_path),
                        meta_path=os.fspath(meta_path),
                    )
                )
                break
            except Exception as e:  # noqa: BLE001
                # If the request looks blocked/challenged, retries rarely help.
                if isinstance(e, FetchError) and "Blocked/challenged" in str(e):
                    attempt = max_retries

                if attempt >= max_retries:
                    if continue_on_error:
                        fetched_at = _utc_now_z()
                        ts_folder = fetched_at.replace(":", "").replace("-", "")
                        dst_dir = out_root / s.id / ts_folder
                        dst_dir.mkdir(parents=True, exist_ok=True)

                        # Write a minimal failure meta for traceability.
                        meta_path = dst_dir / "meta.json"
                        meta = {
                            "source_id": s.id,
                            "scheme_name": s.scheme_name,
                            "requested_url": s.url,
                            "status": "failed",
                            "error": str(e),
                            "fetched_at_utc": fetched_at,
                        }
                        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                        break

                    raise FetchError(f"Failed fetching {s.id} ({s.url}): {e}") from e
                time.sleep(backoff_s * (2**attempt))

    return results

