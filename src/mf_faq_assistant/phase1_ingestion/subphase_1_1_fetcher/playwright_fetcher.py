from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Iterable

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from mf_faq_assistant.phase0_governance.sources import LockedSources, SourceItem


class PlaywrightFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class PlaywrightFetchResult:
    source_id: str
    requested_url: str
    final_url: str
    status: str
    content_length: int
    sha256: str
    fetched_at_utc: str
    raw_path: str
    meta_path: str


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _looks_blocked_html(html: str) -> bool:
    if not html:
        return False
    snippet = html[:12000].lower()
    return any(
        token in snippet
        for token in (
            "captcha",
            "access denied",
            "unusual traffic",
            "verify you are a human",
            "cloudflare",
            "please enable javascript",
        )
    )


def _looks_like_scheme_page(html: str) -> bool:
    # Heuristic signals we reached the actual MF page content.
    if not html:
        return False
    h = html.lower()
    return (
        ("min. for sip" in h)
        or ("minimum sip" in h)
        or ("expense ratio" in h)
        or ("exit load" in h)
        or ("nav" in h and "mutual fund" in h)
    )


def _add_stealth_init_scripts(context) -> None:
    # Best-effort anti-bot reductions (does not guarantee bypass).
    context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    context.add_init_script(
        """
        Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
        Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});
        Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});
        Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
        Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
        """
    )


def fetch_all_playwright(
    locked: LockedSources,
    sources: Iterable[SourceItem] | None = None,
    out_dir: str = "data/raw",
    headless: bool = False,
    nav_timeout_ms: int = 120_000,
    wait_until: str = "domcontentloaded",
    max_retries: int = 2,
    backoff_s: float = 2.0,
    continue_on_error: bool = False,
    wait_for_text: str | None = "Min. for SIP",
    settle_ms: int = 2500,
) -> list[PlaywrightFetchResult]:
    enabled_sources = list(sources) if sources is not None else list(locked.enabled_sources())
    if not enabled_sources:
        return []

    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    results: list[PlaywrightFetchResult] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent="mf-faq-assistant/0.1 (playwright-fetcher)",
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True,
            locale="en-US",
            timezone_id="Asia/Kolkata",
        )

        context.set_extra_http_headers({"Accept-Language": "en-US,en;q=0.9"})
        _add_stealth_init_scripts(context)

        for s in enabled_sources:
            locked.require_allowed(s.url)

            last_exc: Exception | None = None
            for attempt in range(max_retries + 1):
                page = context.new_page()
                try:
                    page.set_default_navigation_timeout(nav_timeout_ms)
                    page.set_default_timeout(nav_timeout_ms)

                    page.goto(s.url, wait_until=wait_until)
                    final_url = page.url
                    locked.require_allowed(final_url)

                    # Wait for expected content if possible.
                    if wait_for_text:
                        try:
                            page.wait_for_selector(f"text={wait_for_text}", timeout=nav_timeout_ms)
                        except Exception:
                            # If selector wait fails, we'll fall back to heuristics.
                            pass

                    # Give the page a moment to populate key sections.
                    page.wait_for_timeout(settle_ms)

                    html = page.content()
                    looks_scheme = _looks_like_scheme_page(html)
                    looks_blocked = _looks_blocked_html(html)
                    if not looks_scheme:
                        raise PlaywrightFetchError(f"Blocked/challenged HTML at {final_url}")

                    body = html.encode("utf-8")
                    fetched_at = _utc_now_z()
                    sha = _sha256_bytes(body)

                    ts_folder = fetched_at.replace(":", "").replace("-", "")
                    dst_dir = out_root / s.id / ts_folder
                    dst_dir.mkdir(parents=True, exist_ok=True)

                    raw_path = dst_dir / "raw.html"
                    meta_path = dst_dir / "meta.json"
                    screenshot_path = dst_dir / "page.png"

                    raw_path.write_bytes(body)
                    page.screenshot(path=os.fspath(screenshot_path), full_page=True)
                    meta = {
                        "source_id": s.id,
                        "scheme_name": s.scheme_name,
                        "requested_url": s.url,
                        "final_url": final_url,
                        "status": "ok",
                        "content_type": "text/html; charset=utf-8",
                        "content_length": len(body),
                        "sha256": sha,
                        "fetched_at_utc": fetched_at,
                        "fetcher": "playwright",
                    }
                    meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")

                    results.append(
                        PlaywrightFetchResult(
                            source_id=s.id,
                            requested_url=s.url,
                            final_url=final_url,
                            status="ok",
                            content_length=len(body),
                            sha256=sha,
                            fetched_at_utc=fetched_at,
                            raw_path=os.fspath(raw_path),
                            meta_path=os.fspath(meta_path),
                        )
                    )
                    break
                except (PlaywrightTimeoutError, PlaywrightFetchError, Exception) as e:  # noqa: BLE001
                    last_exc = e
                    if attempt >= max_retries:
                        if continue_on_error:
                            fetched_at = _utc_now_z()
                            ts_folder = fetched_at.replace(":", "").replace("-", "")
                            dst_dir = out_root / s.id / ts_folder
                            dst_dir.mkdir(parents=True, exist_ok=True)
                            # Save HTML + screenshot for debugging.
                            try:
                                html = page.content()
                                (dst_dir / "blocked.html").write_text(html, encoding="utf-8")
                                page.screenshot(path=os.fspath(dst_dir / "page.png"), full_page=True)
                            except Exception:
                                pass
                            meta_path = dst_dir / "meta.json"
                            meta = {
                                "source_id": s.id,
                                "scheme_name": s.scheme_name,
                                "requested_url": s.url,
                                "status": "failed",
                                "error": str(e),
                                "fetched_at_utc": fetched_at,
                                "fetcher": "playwright",
                            }
                            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
                            break
                        raise PlaywrightFetchError(f"Failed fetching {s.id} ({s.url}): {e}") from e
                    time.sleep(backoff_s * (2**attempt))
                finally:
                    page.close()

        context.close()
        browser.close()

    return results

