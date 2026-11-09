# Edge Cases — Phase 1 (Ingestion & Corpus Build)

This file captures **edge cases** and expected handling for **Phase 1 — Ingestion & Corpus Build** (Fetcher → Extractor → Cleaner/Normalizer → Chunker → Embedder → Indexer → Refresh/Health).

---

## 1.1 Fetcher

### Exact-URL allowlist enforcement
- **Edge case**: Fetcher allows any `groww.in` URL (domain allowlist), expanding beyond the 10 approved URLs.
- **Handling**: Enforce **exact URL** allowlist (after canonicalization).
- **Gate**: Reject any request where canonical URL not in `sources.yaml`.

### Redirect drift
- **Edge case**: URL redirects to a different path (or appends tracking params).
- **Handling**: Follow redirects but validate the **final URL** against allowlist.
- **Gate**: If final URL not allowlisted → mark source `failed_redirect` and do not index.

### Bot protection / rate limiting
- **Edge case**: 403/429/captcha/JS challenge returned as HTML.
- **Handling**: Backoff + retry; mark `blocked` after threshold.
- **Gate**: Block indexing if page classified as captcha/challenge.

---

## 1.2 Extractor

### JS-rendered pages / empty extraction
- **Edge case**: Extractor pulls mostly navigation, or empty content.
- **Handling**: Use main-content heuristics; keep multiple extraction strategies (readability, CSS selectors).
- **Gate**: Fail if extracted text below minimum length or missing key-value sections.

### Layout changes
- **Edge case**: Groww page structure changes; selectors break.
- **Handling**: Drift detection (key fields missing); alert + keep last-known-good index.
- **Gate**: Refresh should not publish a “broken” index.

---

## 1.3 Cleaner & Normalizer

### Noisy boilerplate
- **Edge case**: Footer/legal blocks dominate embeddings and retrieval.
- **Handling**: Strip repeated boilerplate; de-duplicate repeated sections.
- **Gate**: Maintain a blocklist of boilerplate patterns and validate reduction ratio.

### Numeric formatting inconsistencies
- **Edge case**: “₹100” vs “100”, commas, percent formatting.
- **Handling**: Preserve original text but add normalized “shadow fields” in metadata for matching.
- **Gate**: Do not rewrite evidence text used for quoting; use normalization only for retrieval features.

---

## 1.4 Chunker

### Table split (exit load, fees)
- **Edge case**: Exit load conditions split across chunks.
- **Handling**: Table-aware chunking + overlap.
- **Gate**: Ensure at least one chunk contains the full rule statement.

### Over/under chunking
- **Edge case**: Too small → loses context; too large → retrieval becomes fuzzy.
- **Handling**: Tune chunk size and overlap; keep headings in chunk metadata.
- **Gate**: Monitor retrieval precision on a golden set.

---

## 1.5 Embedder

### Model/version drift
- **Edge case**: Embedding model changes cause retrieval regressions.
- **Handling**: Pin `embedding_model_id` and store it with each embedding batch.
- **Gate**: Never mix embeddings from different models in one active index.

---

## 1.6 Indexer

### Partial index updates
- **Edge case**: Some sources indexed, others failed; retrieval becomes inconsistent.
- **Handling**: Build index in a staging namespace and swap atomically.
- **Gate**: Publish only if all 10 sources pass minimum extraction health (or keep last-known-good).

### Vector/keyword mismatch
- **Edge case**: “Min SIP” requires keyword hit; vector alone misses.
- **Handling**: Maintain keyword index and use hybrid retrieval.
- **Gate**: Hybrid retrieval required for short factual fields.

---

## 1.7 Refresh & Health

### Silent degradation
- **Edge case**: Refresh completes but content quality degraded (missing key fields).
- **Handling**: Health checks (field presence), diff-based alerts, regression tests.
- **Gate**: Block refresh publish on drift failures.

---

## Acceptance checks (Phase 1)
- **All 10 sources**: fetched, extracted, normalized, and indexed successfully (or last-known-good retained).
- **Traceability**: raw + normalized + checksum + `last_fetched_at` stored per URL.
- **No corpus expansion**: no non-allowlisted URL present anywhere in stores or indices.

