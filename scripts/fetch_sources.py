from __future__ import annotations

import sys

from mf_faq_assistant.phase0_governance.sources import load_locked_sources
from mf_faq_assistant.phase1_ingestion.subphase_1_1_fetcher.playwright_fetcher import (
    fetch_all_playwright,
 )


def main() -> int:
    locked = load_locked_sources("config/sources.yaml")
    results = fetch_all_playwright(locked, continue_on_error=True)
    print(
        f"Fetched {len(results)} sources into data/raw/ using Playwright "
        f"(some may have failed; see meta.json under each source_id)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

