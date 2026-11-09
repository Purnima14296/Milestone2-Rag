from __future__ import annotations

import sys

from mf_faq_assistant.phase0_governance.refusal import load_refusal_taxonomy
from mf_faq_assistant.phase0_governance.sources import load_locked_sources


def main() -> int:
    sources = load_locked_sources("config/sources.yaml")
    taxonomy = load_refusal_taxonomy("config/refusal_taxonomy.yaml")

    enabled = sources.enabled_sources()
    if len(enabled) != 10:
        raise SystemExit(f"Expected exactly 10 enabled sources, got {len(enabled)}")

    print("Phase 0 validation OK")
    print(f"- sources: {len(enabled)} enabled")
    print(f"- link_policy: {taxonomy.link_policy_mode}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

