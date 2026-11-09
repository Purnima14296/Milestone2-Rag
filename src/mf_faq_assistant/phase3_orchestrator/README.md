# Phase 3 — Orchestrator & Guardrails

Turns user messages into facts-only responses with **Contract B** link policy:

- Factual answers → one allowlisted URL + footer
- Not found / clarification / refusal / PII → **no URL**

## LLM (Groq)

- Config: `config/llm.yaml`
- API key: `GROQ_API_KEY` in `.env`
- Default model: `llama-3.3-70b-versatile`
- Falls back to templates if key is missing or API fails

## CLI

```bash
python scripts/chat.py "Min SIP for HDFC Small Cap Fund Direct Growth"
python scripts/chat.py "What is the expense ratio?"
python scripts/chat.py "Should I invest in HDFC Mid Cap?"
```
