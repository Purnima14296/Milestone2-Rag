from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RawRun:
    source_id: str
    run_id: str
    raw_dir: Path
    raw_path: Path
    meta_path: Path
    meta: dict


def _load_meta(meta_path: Path) -> dict:
    with open(meta_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid meta.json: {meta_path}")
    return data


def discover_latest_raw_runs(raw_root: str | Path = "data/raw") -> list[RawRun]:
    root = Path(raw_root)
    if not root.exists():
        return []

    runs: list[RawRun] = []
    for source_dir in sorted(root.iterdir()):
        if not source_dir.is_dir():
            continue

        run_dirs = sorted(p for p in source_dir.iterdir() if p.is_dir())
        if not run_dirs:
            continue

        latest = run_dirs[-1]
        meta_path = latest / "meta.json"
        if not meta_path.exists():
            continue

        meta = _load_meta(meta_path)
        if meta.get("status") != "ok":
            continue

        raw_candidates = list(latest.glob("raw.*"))
        if not raw_candidates:
            continue

        runs.append(
            RawRun(
                source_id=source_dir.name,
                run_id=latest.name,
                raw_dir=latest,
                raw_path=raw_candidates[0],
                meta_path=meta_path,
                meta=meta,
            )
        )

    return runs
