from __future__ import annotations

import argparse
import json
import sys

from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import (
    RetrievalError,
    retrieve,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 2 retrieval against the active index")
    parser.add_argument("query", help="User question")
    parser.add_argument(
        "--scheme-id",
        default=None,
        help="Optional locked scheme id to constrain retrieval",
    )
    args = parser.parse_args()

    try:
        result = retrieve(args.query, selected_scheme_id=args.scheme_id)
        payload = {
            "status": result.status,
            "scheme_id": result.scheme_id,
            "scheme_name": result.scheme_name,
            "source_url": result.source_url,
            "field_intent": result.field_intent,
            "retrieval_path": result.retrieval_path,
            "confidence": result.confidence,
            "reason": result.reason,
            "evidence_chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "section_name": chunk.section_name,
                    "score": chunk.score,
                    "embedded_text": chunk.embedded_text,
                }
                for chunk in result.evidence_chunks
            ],
        }
        print(json.dumps(payload, indent=2))
        return 0 if result.status == "ok" else 1
    except RetrievalError as exc:
        print(f"Retrieval failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
