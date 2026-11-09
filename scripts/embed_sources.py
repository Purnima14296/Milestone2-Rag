from __future__ import annotations

import sys

from mf_faq_assistant.phase1_ingestion.subphase_1_5_embedder.embedder import (
    embed_all_latest,
    load_embedding_config,
)


def main() -> int:
    config = load_embedding_config()
    results = embed_all_latest(continue_on_error=False)
    total_embeddings = sum(r.embedding_count for r in results)
    print(f"Embedded {len(results)} sources into data/embeddings/")
    print(f"Model: {config.embedding_model_id} ({config.dimensions}-dim)")
    print(f"Total embeddings: {total_embeddings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
