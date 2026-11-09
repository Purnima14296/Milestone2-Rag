"""
Phase 1 — Ingestion & Corpus Build.
"""

from .subphase_1_1_fetcher import FetchError, FetchResult, fetch_all
from .subphase_1_2_extractor import ExtractionError, ExtractionResult, extract_all_latest
from .subphase_1_3_cleaner_normalizer import (
    NormalizationError,
    NormalizationResult,
    normalize_all_latest,
)

__all__ = [
    "FetchError",
    "FetchResult",
    "fetch_all",
    "ExtractionError",
    "ExtractionResult",
    "extract_all_latest",
    "NormalizationError",
    "NormalizationResult",
    "normalize_all_latest",
]

