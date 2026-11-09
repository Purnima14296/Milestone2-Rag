from __future__ import annotations

import argparse
import json
import sys

from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.orchestrator import (
    OrchestratorError,
    chat,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 3 chat orchestrator")
    parser.add_argument("message", help="User message")
    parser.add_argument(
        "--scheme-id",
        default=None,
        help="Optional locked scheme id",
    )
    args = parser.parse_args()

    try:
        result = chat(args.message, selected_scheme_id=args.scheme_id)
        payload = {
            "answer_text": result.answer_text,
            "citation_url": result.citation_url,
            "last_updated_date": result.last_updated_date,
            "refusal": result.refusal,
            "reason": result.reason,
        }
        print(json.dumps(payload, indent=2))
        return 0 if not result.refusal and result.reason is None else 1
    except OrchestratorError as exc:
        print(f"Chat failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
