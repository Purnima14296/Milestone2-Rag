# Phase 2 — Retrieval Layer

Scheme-first, field-aware hybrid retrieval over `data/index/active/`.

## Modules (`subphase_2_retrieval_layer/`)

- `query_normalizer.py` — conservative query cleanup + MF synonyms
- `scheme_resolver.py` — fuzzy match to 10 locked schemes
- `field_intent.py` — field detection + section routing map
- `hybrid_retriever.py` — RRF vector + keyword merge, section boosts
- `confidence_gate.py` — rule-based answerability checks
- `retriever.py` — `retrieve()` orchestrator

## CLI

```bash
python scripts/retrieve_query.py "Min SIP for HDFC Small Cap Fund Direct Growth"
```

