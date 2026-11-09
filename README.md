# Mutual Fund FAQ Assistant (Facts-Only RAG)

This repo contains a phase-wise implementation scaffold for a **facts-only** mutual fund FAQ assistant.

## Project constraints (Phase 0)
- **Locked corpus**: only the 10 URLs in `config/sources.yaml` may be fetched, indexed, or cited.
- **No advice**: no recommendations, comparisons, or projections.
- **PII safety**: block PAN/Aadhaar/account/OTP/email/phone.
- **Answer contract** (later phases): max 3 sentences, exactly one citation link, and a last-updated footer.

## Repository layout
- `Docs/`: architecture + edge cases
- `config/`: Phase 0 governance configs (`sources.yaml`, `refusal_taxonomy.yaml`)
- `src/mf_faq_assistant/`: phase folders
  - `phase0_governance/` … `phase3_orchestrator/`: **implemented**
  - `phase4_ui/`: **implemented** (FastAPI backend + Vite SPA)
  - `phase5_eval_observability/`: **implemented** (golden eval, drift checks, observability)
- `scripts/`: helper scripts (Phase 0 validation)
- `tests/`: unit tests

## Setup

```bash
python -m pip install -r requirements.txt
cp .env.example .env
# Add your Groq API key to .env (https://console.groq.com/)
```

Answer generation uses **Groq** (`llama-3.3-70b-versatile`). Embeddings stay local (`bge-small-en-v1.5`).
If `GROQ_API_KEY` is unset, Phase 3 falls back to template-based answers.

## Validate Phase 0

```bash
python -c "import sys; sys.path.insert(0,'src'); from scripts.validate_phase0 import main; raise SystemExit(main())"
```

## Run Phase 1.1 (fetch)

```bash
python -c "import sys; sys.path.insert(0,'src'); from scripts.fetch_sources import main; raise SystemExit(main())"
```

## Run Phase 1.2 + 1.3 (extract + normalize)

```bash
python -c "import sys; sys.path.insert(0,'src'); from scripts.extract_and_normalize import main; raise SystemExit(main())"
```

## Run Phase 1.4 (chunk)

```bash
python -c "import sys; sys.path.insert(0,'src'); from scripts.chunk_sources import main; raise SystemExit(main())"
```

## Run Phase 1.5 (embed)

```bash
python -c "import sys; sys.path.insert(0,'src'); from scripts.embed_sources import main; raise SystemExit(main())"
```

## Run Phase 1.7 (full refresh)

```bash
python -c "import sys; sys.path.insert(0,'src'); from scripts.refresh_corpus import main; raise SystemExit(main())"
```

Re-runs fetch → extract → normalize → chunk → embed → index with health gates.  
Use `--skip-fetch` to rebuild from existing raw HTML, or `--health-only` to validate only.

Scheduled via GitHub Actions: `.github/workflows/refresh_corpus.yml` (weekly + manual).

## Run Phase 1.6 (build index)

```bash
python -c "import sys; sys.path.insert(0,'src'); from scripts.build_index import main; raise SystemExit(main())"
```

Builds a **ChromaDB vector index** + **keyword index** under `data/index/active/`.

## Run Phase 2 (retrieve)

```bash
python scripts/retrieve_query.py "Min SIP for HDFC Small Cap Fund Direct Growth"
```

Optional scheme override:

```bash
python scripts/retrieve_query.py "exit load" --scheme-id hdfc_nifty_50_index_fund_direct_growth
```

## Run Phase 3 (chat)

```bash
python scripts/chat.py "Min SIP for HDFC Small Cap Fund Direct Growth"
```

Unknown, refused, or PII-containing queries return **no citation URL**.

## Run Phase 4 (API + UI)

### Option A — Dev (hot reload)

```bash
# Terminal 1
python scripts/run_api.py

# Terminal 2
cd frontend && npm install && npm run dev
```

Open http://localhost:5173

### Option B — Single server (production build)

```bash
cd frontend && npm install && npm run build
cd .. && python scripts/run_api.py
```

Open http://127.0.0.1:8000

API docs: http://127.0.0.1:8000/docs

Metrics dashboard API: http://127.0.0.1:8000/metrics

## Run Phase 5 (eval & observability)

```bash
python scripts/run_drift_check.py
python scripts/run_eval.py
```

Golden eval and drift checks also run in CI (`.github/workflows/ci.yml`) and after corpus refresh.

## Export embeddings for Parquet visualizer (VS Code / Cursor)

```bash
python scripts/export_embeddings_index.py
```

Then open `data/index/embeddings.parquet` in the editor and use the Parquet visualizer **Query** tab:

```sql
SELECT *
FROM read_parquet('data/index/embeddings.parquet')
LIMIT 1000;
```

Join metadata with:

```sql
SELECT v.id, m.scheme_name, m.section_name, m.expense_ratio, v.embedding
FROM read_parquet('data/index/embeddings.parquet') v
JOIN read_parquet('data/index/embeddings_meta.parquet') m USING (id)
LIMIT 1000;
```

## Run tests

```bash
python -m unittest -v
```

