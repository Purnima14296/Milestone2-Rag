# Mutual Fund FAQ — Frontend

Minimal Vite SPA for Phase 4.

## Dev (hot reload)

Terminal 1 — API:

```bash
python scripts/run_api.py
```

Terminal 2 — frontend:

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## Production build (served by FastAPI)

```bash
cd frontend
npm install
npm run build
python scripts/run_api.py
```

Open http://127.0.0.1:8000
