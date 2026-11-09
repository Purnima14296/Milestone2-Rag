from __future__ import annotations

import argparse
import sys

from mf_faq_assistant.phase1_ingestion.subphase_1_7_refresh_health.refresh import (
    RefreshError,
    run_refresh_pipeline,
    validate_active_index,
    validate_corpus_health,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run full corpus refresh pipeline (Phase 1.7)")
    parser.add_argument(
        "--skip-fetch",
        action="store_true",
        help="Reuse latest raw HTML; re-run extract through index only",
    )
    parser.add_argument(
        "--health-only",
        action="store_true",
        help="Validate existing corpus and active index without re-running pipeline",
    )
    args = parser.parse_args()

    try:
        if args.health_only:
            health_rows = validate_corpus_health()
            failures = [row for row in health_rows if row.errors]
            if failures:
                for row in failures:
                    print(f"FAIL {row.scheme_id}: {', '.join(row.errors)}")
                return 1
            active_meta = validate_active_index()
            print(f"Health OK: {len(health_rows)} schemes")
            print(f"Active index: {active_meta.get('document_count')} documents")
            return 0

        result = run_refresh_pipeline(skip_fetch=args.skip_fetch)
        print(f"Refresh status: {result.status}")
        print(f"Schemes: {result.scheme_count}")
        print(f"Indexed documents: {result.indexed_documents}")
        print(f"Active index: {result.active_index_path}")
        print(f"Report: {result.report_path}")
        return 0
    except RefreshError as exc:
        print(f"Refresh failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
