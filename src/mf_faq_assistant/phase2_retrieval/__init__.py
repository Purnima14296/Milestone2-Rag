"""
Phase 2 — Retrieval Layer.

Scheme-first, field-aware hybrid retrieval over the active corpus index.
"""

from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer import (
    EvidenceChunk,
    RetrievalResult,
    load_retrieval_config,
    retrieve,
)

__all__ = [
    "EvidenceChunk",
    "RetrievalResult",
    "load_retrieval_config",
    "retrieve",
]
