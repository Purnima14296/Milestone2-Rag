from __future__ import annotations

import sys

from mf_faq_assistant.phase1_ingestion.subphase_1_2_extractor.extractor import extract_all_latest
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.normalizer import (
    normalize_all_latest,
)


def main() -> int:
    extracted = extract_all_latest(continue_on_error=False)
    normalized = normalize_all_latest(continue_on_error=False)
    print(f"Extracted {len(extracted)} sources into data/extracted/")
    print(f"Normalized {len(normalized)} sources into data/normalized/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
