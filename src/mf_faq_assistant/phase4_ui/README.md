# Phase 4 — UI

## Backend + Frontend (implemented)

FastAPI service in `subphase_4_backend/`. Vite SPA in `frontend/`.

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Index readiness |
| `GET` | `/config` | Welcome text, disclaimer, example questions |
| `GET` | `/schemes` | Locked scheme list for dropdown |
| `POST` | `/chat` | Chat orchestration (Phase 3) |
| `GET` | `/metrics` | Observability dashboard snapshot (Phase 5) |

### Run

```bash
python scripts/run_api.py
```

Docs: http://127.0.0.1:8000/docs

## Frontend

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173
npm run build  # output in frontend/dist, served by FastAPI at /
```

See `frontend/README.md` for details.
