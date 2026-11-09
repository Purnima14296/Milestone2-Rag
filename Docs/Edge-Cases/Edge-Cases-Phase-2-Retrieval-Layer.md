# Edge Cases — Phase 2 (Retrieval Layer)

This file captures **edge cases** and expected handling for **Phase 2 — Retrieval Layer** (query normalizer, scheme resolver, hybrid retriever, reranker, confidence gate).

---

## Edge cases & handling

### Ambiguous scheme reference
- **Edge case**: “What is the expense ratio?” (no scheme named).
- **Handling**: Ask a short clarifying question (or show a short scheme picker in UI).
- **Gate**: Do not guess a scheme; avoid returning an arbitrary citation URL.

### Scheme name mismatches / aliases / typos
- **Edge case**: “HDFC midcap”, “HDFC mid cap”, misspellings.
- **Handling**: Fuzzy match against the 10 locked scheme titles/slugs; if confidence is low, ask user to confirm.
- **Gate**: Minimum resolver confidence threshold required before filtering retrieval to a scheme URL.

### Query normalization changes meaning
- **Edge case**: Aggressive normalization removes important tokens (“direct growth”, “ETF FoF”).
- **Handling**: Use conservative normalization; keep a raw query copy for fallback retrieval.
- **Gate**: Golden test set for normalization ensures no meaning loss.

### Hybrid retrieval conflicts (keyword vs vector)
- **Edge case**: Vector retrieves semantically related but wrong scheme; keyword finds exact “Min. for SIP”.
- **Handling**: Weighted merge with field-aware boosting for keyword matches on key-value fields.
- **Gate**: For known fields (expense ratio, min SIP, exit load), require at least one keyword hit or a high-confidence vector hit.

### Retrieval selects the wrong scheme page
- **Edge case**: Shared tokens cause wrong URL to rank first.
- **Handling**:
  - apply scheme-specific boosting when the scheme is resolved
  - enforce scheme filter for scheme-specific questions
- **Gate**: If top evidence URL differs from resolved scheme URL, rerun retrieval constrained to resolved scheme.

### Confidence gate under locked corpus
- **Edge case**: Field isn’t present in extracted text (or extraction drift).
- **Handling**: Return “I couldn’t find this in the current sources” and cite the most relevant allowlisted URL.
- **Gate**: If evidence packet lacks direct mention of the requested field, block generation (no hallucination).

### No cross-source merge (one-citation constraint)
- **Edge case**: Evidence spans multiple URLs.
- **Handling**: Aggregate scores per `source_url` and select one URL only; ignore others.
- **Gate**: Final response must cite exactly one URL.

---

## Acceptance checks (Phase 2)
- **Resolver correctness**: scheme-specific queries resolve to the right allowlisted URL.
- **Retrieval precision**: top results match the intended scheme for golden questions.
- **No hallucination**: unanswered fields return “not found in current sources” behavior.

