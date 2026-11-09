# Edge Cases — Phase 5 (Eval & Observability)

This file captures **edge cases** and expected handling for **Phase 5 — Eval & Observability** (test suites, CI gates, structured logs, dashboard).

---

## Edge cases & handling

### Golden set becomes brittle as pages change
- **Edge case**: Groww page layout changes cause extraction differences; golden assertions fail even though system is still usable.
- **Handling**: Separate tests into:
  - **contract tests** (must always pass: link count, sentence limit, no advice, footer presence)
  - **field presence tests** (warn/fail depending on severity)
- **Gate**: Contract tests are hard blockers; field tests can be configured as soft/hard.

### Silent extraction drift
- **Edge case**: Extractor returns nav/footer text; retrieval still “works” but answers degrade.
- **Handling**: Drift detectors:
  - minimum content length
  - presence of key labels (“Min. for SIP”, “Expense ratio”, “Exit load”) where expected
- **Gate**: Block index publish if drift triggers; keep last-known-good.

### Logging accidentally captures PII
- **Edge case**: Full user message stored in logs; user pasted PAN/OTP.
- **Handling**:
  - redact at ingestion (before log write)
  - store hashed message IDs + high-level intent only
- **Gate**: Lint/CI check on logging statements (no raw `message` field).

### Citation contract violations in production
- **Edge case**: A bug emits 0 links or 2 links.
- **Handling**: Emit a structured event (`contract_violation`) and auto-fallback to a safe refusal/not-found response.
- **Gate**: Dashboard alert on violations > threshold; CI prevents release if reproducible.

### Latency spikes
- **Edge case**: Hybrid retrieval or LLM call slows; UI times out.
- **Handling**: Timeouts + graceful fallback; cache popular questions.
- **Gate**: SLOs (e.g., p95 latency) and alerting.

---

## Acceptance checks (Phase 5)
- **CI gates** enforce: ≤3 sentences, exactly one citation (per chosen contract), footer rules, refusal rules.
- **Privacy**: logs contain no sensitive identifiers.
- **Operational visibility**: dashboard shows contract violations, retrieval misses, latency percentiles, and per-URL usage stats.

