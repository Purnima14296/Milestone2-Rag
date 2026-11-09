# Problem Statement: Mutual Fund FAQ Assistant (Facts-Only Q&A)

## Context

Retail investors and support teams routinely need quick, objective answers about mutual fund schemes — expense ratio, minimum SIP, exit load, NAV, benchmark, risk classification, and similar facts. These answers exist on public scheme pages, but finding the right value often means navigating long pages, dealing with stale bookmarks, or relying on general-purpose chat tools that may hallucinate numbers or drift into investment advice.

This project addresses that gap by building a **facts-only FAQ assistant** grounded in a **locked, curated corpus** of scheme pages. Groww mutual fund pages serve as the reference product context; the assistant retrieves and extracts verifiable facts from those pages only — never inventing values and never offering recommendations.

---

## Problem

Users need a trustworthy way to ask natural-language questions about mutual fund schemes and receive **short, precise, source-backed answers**. The system must:

1. Answer **objective, verifiable** questions (NAV, AUM, expense ratio, min SIP, exit load, benchmark, risk, lock-in, tax notes, etc.).
2. **Refuse** advisory, comparative, or speculative queries (“Should I invest?”, “Which fund is better?”).
3. **Protect privacy** by never collecting or echoing PAN, Aadhaar, account numbers, OTPs, email, or phone.
4. **Cite exactly one source** when a confident factual answer exists, with a clear last-updated date.
5. Return **no citation link** when the answer is unknown, needs clarification, or is a refusal — avoiding misleading “best guess” links.

A core failure mode to eliminate is **non-answers**: responses that deflect (“check the fund details section”) or speak generically instead of extracting the actual value from retrieved context.

---

## Objective

Design and implement a lightweight **Retrieval-Augmented Generation (RAG)** assistant that:

- Retrieves evidence from a **fixed allowlist** of scheme URLs
- Extracts **exact factual values** from retrieved context (structured fields and text)
- Produces **concise, grounded responses** with strict guardrails
- Exposes a **minimal web UI** for interactive Q&A

The system prioritizes **accuracy and compliance over conversational flair**. When data is missing, it says so plainly rather than guessing.

---

## Target Users

| User | Need |
|---|---|
| **Retail investors** | Quick factual lookups while comparing schemes (without receiving advice) |
| **Customer support / content teams** | Consistent, source-backed answers to repetitive scheme questions |
| **Engineers / reviewers** | A reproducible RAG pipeline with tests, configs, and phase-wise architecture |

---

## Scope

### 1. Locked corpus

- **One AMC focus:** HDFC Mutual Fund (via Groww scheme pages)
- **10 locked URLs** defined in `config/sources.yaml` — the only pages that may be fetched, indexed, embedded, or cited
- No third-party blogs, aggregators, or ad-hoc URLs outside the allowlist

Representative schemes include Small Cap, Mid Cap, Nifty 50 Index, Balanced Advantage, Gold ETF FoF, Silver ETF FoF, and others on the locked list.

### 2. Supported query types (facts-only)

The assistant answers questions such as:

- What is the **NAV** / **AUM** of a scheme?
- What is the **expense ratio**?
- What is the **minimum SIP** or lumpsum?
- What is the **exit load**?
- What is the **benchmark** or **risk** classification?
- What is the **lock-in** period (e.g., ELSS)?
- Who is the **fund manager**?
- What are **tax** or stamp-duty notes stated on the page?

Answers must be **extracted from evidence**, not paraphrased into vague guidance.

### 3. Answer contract (factual responses)

When retrieval succeeds and a grounded fact is found:

| Rule | Requirement |
|---|---|
| Length | Maximum **3 sentences** (footer excluded) |
| Citation | Exactly **one** allowlisted Groww URL |
| Footer | `Last updated from sources: YYYY-MM-DD` |
| Tone | Direct answer first — no preamble, no suggestions unless asked |

When retrieval fails, clarification is needed, or the query is refused:

| Rule | Requirement |
|---|---|
| Citation | **No URL** |
| Message | Clear, polite limitation (e.g., *“I'm sorry, but I wasn't able to find that in the scheme sources I have access to.”*) |

### 4. Refusal handling

The assistant must **politely refuse** non-factual or advisory queries, including:

- Investment recommendations (“Should I invest in this fund?”)
- Scheme comparisons (“Which HDFC fund is better?”)
- Return projections or performance opinions

Refusal responses reinforce the **facts-only** boundary and do **not** attach a citation URL.

### 5. Privacy and PII safety

The system must **not** collect, store, log, or echo:

- PAN or Aadhaar numbers
- Bank / demat account numbers
- OTPs
- Email addresses or phone numbers

If a user includes PII in a message, the assistant blocks processing and returns a safe response **without** a source link.

### 6. User interface (minimal)

A simple SPA with:

- Welcome message and short product description
- Scheme selector (optional) and chat input
- **Three example questions**
- Visible disclaimer: **“Facts-only. No investment advice.”**

---

## Constraints

### Data and sources

- Fetch and cite **only** URLs in `config/sources.yaml`
- Treat page content as **untrusted evidence** (prompt-injection resistant)
- Scheduled refresh rebuilds the corpus from the same locked list

### Content restrictions

- **No** investment advice, opinions, or recommendations
- **No** performance comparisons between schemes
- **No** fabricated numbers, dates, or attributes
- **No** deflection phrases (“check the source”, “available in fund details section”)

### Technical expectations

- **Local embeddings** for retrieval (e.g., `BAAI/bge-small-en-v1.5`)
- **LLM for answer generation** (e.g., Groq) with deterministic extraction fallback
- **Hybrid retrieval:** scheme resolution → field-aware routing → vector + keyword search
- **Automated tests** for grounding, refusals, PII blocking, and citation policy

---

## Out of scope

- Personalized portfolio advice or suitability assessment
- Live market data, order placement, or account operations
- Corpus expansion beyond the 10 locked URLs without explicit governance update
- Multi-source answer merging (one question → one best source URL)

---

## Success criteria

| Criterion | Measure |
|---|---|
| **Grounded answers** | NAV, AUM, ratios, and other fields returned as exact values from retrieved context |
| **No hallucination** | Missing facts → explicit “not found” response, not invented data |
| **No deflection** | Zero generic “check the documentation” style replies when evidence exists |
| **Citation discipline** | Factual answers include one valid URL + footer; unknown/refusal/PII → no URL |
| **Refusal quality** | Advisory/comparison queries declined clearly and consistently |
| **Privacy** | PII detected and blocked without echoing sensitive input |
| **Usability** | Minimal UI loads, accepts questions, and displays answers with citation when applicable |

---

## Expected deliverables

1. **Runnable application** — FastAPI backend + Vite frontend (`POST /chat`, health/config endpoints)
2. **Ingestion pipeline** — fetch, extract, normalize, chunk, embed, index with refresh automation
3. **RAG orchestrator** — PII guard, intent classifier, retriever, grounded generator, post-processor
4. **Configuration** — locked sources, refusal taxonomy, retrieval and LLM settings
5. **Documentation** — README, phase-wise architecture, this problem statement
6. **Test suite** — unit and integration tests for retrieval, grounding, and API behavior

---

## Summary

The goal is a **trustworthy, transparent, and compliant** mutual fund FAQ assistant that answers only what the locked corpus supports. Users get verifiable facts with a single source link when confidence is high, and honest boundaries everywhere else. The system is designed to be auditable, testable, and safe by default — accuracy over intelligence, extraction over speculation.

**Disclaimer (product copy):** *Facts-only. No investment advice.*
