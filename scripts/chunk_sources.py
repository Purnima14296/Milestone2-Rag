from __future__ import annotations

import sys

from mf_faq_assistant.phase1_ingestion.subphase_1_4_chunker.chunker import chunk_all_latest


def main() -> int:
    results = chunk_all_latest(continue_on_error=False)
    total_chunks = sum(r.chunk_count for r in results)
    print(f"Chunked {len(results)} sources into data/chunks/")
    print(f"Total chunks: {total_chunks}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
