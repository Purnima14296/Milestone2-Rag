from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics

from mf_faq_assistant.phase5_eval_observability.config_loader import (
    ObservabilityConfig,
    load_observability_config,
)


@dataclass(frozen=True)
class DashboardSnapshot:
    observability_version: str
    generated_at_utc: str
    total_requests: int
    reason_counts: dict[str, int]
    retrieval_misses: int
    contract_violations: int
    refusal_count: int
    pii_blocked_count: int
    top_urls: list[tuple[str, int]]
    latency_ms: dict[str, float | None]


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = (len(ordered) - 1) * pct
    low = int(rank)
    high = min(low + 1, len(ordered) - 1)
    weight = rank - low
    return ordered[low] * (1 - weight) + ordered[high] * weight


def _load_events(events_path: Path) -> list[dict]:
    if not events_path.exists():
        return []
    events: list[dict] = []
    with open(events_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events


def build_dashboard_snapshot(
    *,
    config: ObservabilityConfig | None = None,
) -> DashboardSnapshot:
    cfg = config or load_observability_config()
    events = _load_events(Path(cfg.events_path))

    reason_counts: dict[str, int] = {}
    url_counts: dict[str, int] = {}
    latencies: list[float] = []
    contract_violations = 0
    refusal_count = 0
    pii_blocked_count = 0
    retrieval_misses = 0

    for event in events:
        reason = str(event.get("reason") or "factual")
        reason_counts[reason] = reason_counts.get(reason, 0) + 1

        if reason in {"not_found", "needs_clarification", "out_of_scope"}:
            retrieval_misses += 1
        if event.get("refusal"):
            refusal_count += 1
        if reason == "pii_blocked":
            pii_blocked_count += 1
        if event.get("contract_violation"):
            contract_violations += 1

        citation_url = event.get("citation_url")
        if citation_url:
            url_counts[str(citation_url)] = url_counts.get(str(citation_url), 0) + 1

        latency = event.get("latency_ms")
        if isinstance(latency, (int, float)):
            latencies.append(float(latency))

    top_urls = sorted(url_counts.items(), key=lambda item: item[1], reverse=True)[:10]

    return DashboardSnapshot(
        observability_version=cfg.observability_version,
        generated_at_utc=_utc_now_z(),
        total_requests=len(events),
        reason_counts=reason_counts,
        retrieval_misses=retrieval_misses,
        contract_violations=contract_violations,
        refusal_count=refusal_count,
        pii_blocked_count=pii_blocked_count,
        top_urls=top_urls,
        latency_ms={
            "p50": _percentile(latencies, 0.5),
            "p95": _percentile(latencies, 0.95),
            "max": max(latencies) if latencies else None,
            "mean": statistics.fmean(latencies) if latencies else None,
        },
    )


def snapshot_to_dict(snapshot: DashboardSnapshot) -> dict:
    return {
        "observability_version": snapshot.observability_version,
        "generated_at_utc": snapshot.generated_at_utc,
        "total_requests": snapshot.total_requests,
        "reason_counts": snapshot.reason_counts,
        "retrieval_misses": snapshot.retrieval_misses,
        "contract_violations": snapshot.contract_violations,
        "refusal_count": snapshot.refusal_count,
        "pii_blocked_count": snapshot.pii_blocked_count,
        "top_urls": [{"url": url, "count": count} for url, count in snapshot.top_urls],
        "latency_ms": snapshot.latency_ms,
    }


def write_metrics_snapshot(
    snapshot: DashboardSnapshot,
    *,
    config: ObservabilityConfig | None = None,
) -> str:
    cfg = config or load_observability_config()
    metrics_path = Path(cfg.metrics_path)
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(snapshot_to_dict(snapshot), indent=2), encoding="utf-8")
    return str(metrics_path)
