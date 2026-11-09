from __future__ import annotations

import sys

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import index_all_latest


def main() -> int:
    result = index_all_latest()
    print(f"Indexed {result.document_count} documents from {result.scheme_count} schemes")
    print(f"Active index: {result.active_dir}")
    print(f"Meta: {result.meta_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
