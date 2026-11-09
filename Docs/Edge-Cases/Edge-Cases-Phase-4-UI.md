# Edge Cases — Phase 4 (UI)

This file captures **edge cases** and expected handling for **Phase 4 — UI** (FastAPI backend + minimal SPA frontend).

---

## Edge cases & handling

### Double-submit / rapid-fire messages
- **Edge case**: User clicks “Send” multiple times; backend receives concurrent requests.
- **Handling**: Frontend disables send during in-flight request; backend rate-limits per session/IP.
- **Gate**: Idempotency key per message (optional) to dedupe retries.

### Streaming vs non-streaming mismatch
- **Edge case**: UI expects streaming tokens, API returns a single blob (or vice versa).
- **Handling**: Pick one mode for MVP; keep a clear API contract.
- **Gate**: Contract tests for response shape.

### Ambiguous query UX
- **Edge case**: User asks “expense ratio?” without scheme.
- **Handling**: UI shows quick buttons or a scheme dropdown for the 10 locked schemes.
- **Gate**: The backend should return `reason: needs_clarification` when scheme resolution fails.

### Displaying citations and footers
- **Edge case**: UI renders multiple clickable links (e.g., auto-linking extra text).
- **Handling**: Render only the explicit `citation_url` field as a link.
- **Gate**: UI sanitization to prevent accidental linkification of other content.

### User pastes PII in the UI
- **Edge case**: User pastes PAN/Aadhaar/OTP/etc.
- **Handling**: Client-side warning (optional) plus server-side hard block.
- **Gate**: Server-side PII block is mandatory; client-side is best-effort.

### Error states
- **Edge case**: Index unavailable, retrieval timeout, or ingestion in progress.
- **Handling**: UI shows a short “temporarily unavailable” message; retries allowed.
- **Gate**: API returns consistent error codes and a safe error message (no stack traces).

---

## Acceptance checks (Phase 4)
- **Usability**: welcome message, 3 example questions, visible disclaimer.
- **Contract display**: answer text, exactly one citation link, last-updated footer rendered cleanly.
- **Safety**: UI does not encourage sharing personal identifiers.

