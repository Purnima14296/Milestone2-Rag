# Edge Cases — Phase 3 (Orchestrator & Guardrails)

This file captures **edge cases** and expected handling for **Phase 3 — Orchestrator & Guardrails** (PII guard, intent classifier, generator, post-processor, refusal composer).

---

## Edge cases & handling

### PII appears in the user message
- **Edge case**: User includes PAN/Aadhaar/account/OTP/email/phone.
- **Handling**: Block the request, warn the user not to share, and do not store the raw content in logs.
- **Gate**: PII guard runs before intent classification, retrieval, generation, and logging.

### Prompt injection (user or retrieved text)
- **Edge case**: “Ignore rules…”, or retrieved snippets contain instruction-like text.
- **Handling**: Treat all retrieved text as untrusted; generator uses it as evidence only.
- **Gate**: A policy validator rejects any output that violates the facts-only constraints even if “instructed”.

### Mixed intent: advice + factual
- **Edge case**: “Should I invest in HDFC Mid Cap? What is the expense ratio?”
- **Handling**: Apply a consistent precedence rule:
  - strict: any advice → refusal
  - split: answer factual part + refuse advice (still no recommendation)
- **Gate**: Ensure the response still satisfies the link/sentence contract.

### Generator adds content not present in evidence
- **Edge case**: Evidence shows min SIP, model adds tax implications, recommendations, comparisons, or return projections.
- **Handling**: Evidence-only generation + block unsupported claims.
- **Gate**: Validator rejects outputs with unsupported factual claims or advisory language.

### Generator emits multiple links
- **Edge case**: Output contains multiple URLs.
- **Handling**: Regenerate or trim to one link (deterministic).
- **Gate**: Hard fail if more than one URL remains after post-processing.

### Sentence limit violated
- **Edge case**: Model outputs 4–6 sentences.
- **Handling**: Prefer regeneration with stricter constraints; only truncate if it doesn’t change meaning.
- **Gate**: Reject outputs >3 sentences (excluding footer line).

### Footer breaks formatting rules
- **Edge case**: Footer counted as a 4th sentence.
- **Handling**: Render footer as a separate line: `Last updated from sources: YYYY-MM-DD`.
- **Gate**: Sentence counter excludes the footer line.

### Refusal link policy under locked corpus
- **Edge case**: Refusal templates want AMFI/SEBI educational links, but only the 10 Groww URLs are allowed.
- **Handling**: Choose one and enforce:
  - **Contract A (strict)**: refusals include exactly one link from the 10 URLs
  - **Contract B (split)**: refusals include no link; factual answers include exactly one link
- **Gate**: Validator enforces the chosen contract consistently.

### Comparisons needing two citations
- **Edge case**: “Which is better: HDFC Small Cap vs Mid Cap?”
- **Handling**: Refuse comparisons; if a link is required, cite only one URL (deterministic selection rule).
- **Gate**: Never output two scheme links.

### “Not found” behavior
- **Edge case**: User asks for a field not present in extracted evidence (layout drift or missing content).
- **Handling**: Respond “I couldn’t find this in the current sources” (no hallucination); attach **no URL** (Contract B).
- **Gate**: Evidence must contain a direct mention of the requested fact to answer positively.

---

## Acceptance checks (Phase 3)
- **No PII** stored or echoed back.
- **No advice/comparisons/projections** in any response.
- **Output contract** enforced: ≤3 sentences; factual answers include exactly one citation + footer; unknown/refusal/PII responses include **no citation**.

