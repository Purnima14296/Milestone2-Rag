# Phase 5 — Eval & Observability

Implements golden eval, contract validation, dataset drift checks, privacy-safe structured logging, and a metrics dashboard API.

## Components

| Module | Purpose |
|---|---|
| `contract_validator.py` | Enforces answer contract (≤3 sentences, citation rules, footer) |
| `golden_eval.py` | Runs `config/eval_golden.yaml` against `chat()` |
| `drift_checker.py` | Detects index/corpus extraction drift before publish |
| `structured_logger.py` | Appends privacy-safe JSONL events (no raw PII) |
| `metrics_store.py` | Aggregates events into dashboard snapshot |

## Config

- `config/eval.yaml` — golden eval settings
- `config/eval_golden.yaml` — golden Q&A cases
- `config/drift.yaml` — drift detection thresholds
- `config/observability.yaml` — logging paths

## CLI

```bash
python scripts/run_eval.py
python scripts/run_drift_check.py
```

## API

`GET /metrics` — dashboard snapshot (reason counts, retrieval misses, contract violations, latency percentiles, top URLs)

## Outputs

- `data/observability/events.jsonl` — structured chat events
- `data/observability/metrics.json` — latest dashboard snapshot
- `data/observability/eval_report.json` — latest golden eval report
