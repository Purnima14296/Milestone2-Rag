from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import yaml


class EvalConfigError(ValueError):
    pass


@dataclass(frozen=True)
class EvalConfig:
    eval_version: str
    golden_path: str
    index_active_dir: str
    sources_path: str
    min_hard_pass_rate: float
    report_path: str


@dataclass(frozen=True)
class ObservabilityConfig:
    observability_version: str
    enabled: bool
    events_path: str
    metrics_path: str
    log_raw_message: bool


@dataclass(frozen=True)
class DriftConfig:
    drift_version: str
    index_active_dir: str
    sources_path: str
    expected_schemes: int
    expected_documents: int
    required_sections: tuple[str, ...]
    required_shadow_fields: tuple[str, ...]
    required_text_labels: tuple[str, ...]


def _load_yaml(path: str | Path) -> dict:
    config_path = Path(path)
    if not config_path.exists():
        raise EvalConfigError(f"Config not found: {config_path}")
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise EvalConfigError(f"Invalid config: {config_path}")
    return raw


def load_eval_config(path: str | Path = "config/eval.yaml") -> EvalConfig:
    raw = _load_yaml(path)
    return EvalConfig(
        eval_version=str(raw.get("eval_version", "1.0.0")),
        golden_path=str(raw.get("golden_path", "config/eval_golden.yaml")),
        index_active_dir=str(raw.get("index_active_dir", "data/index/active")),
        sources_path=str(raw.get("sources_path", "config/sources.yaml")),
        min_hard_pass_rate=float(raw.get("min_hard_pass_rate", 1.0)),
        report_path=str(raw.get("report_path", "data/observability/eval_report.json")),
    )


def load_observability_config(path: str | Path = "config/observability.yaml") -> ObservabilityConfig:
    raw = _load_yaml(path)
    return ObservabilityConfig(
        observability_version=str(raw.get("observability_version", "1.0.0")),
        enabled=bool(raw.get("enabled", True)),
        events_path=str(raw.get("events_path", "data/observability/events.jsonl")),
        metrics_path=str(raw.get("metrics_path", "data/observability/metrics.json")),
        log_raw_message=bool(raw.get("log_raw_message", False)),
    )


def load_drift_config(path: str | Path = "config/drift.yaml") -> DriftConfig:
    raw = _load_yaml(path)
    return DriftConfig(
        drift_version=str(raw.get("drift_version", "1.0.0")),
        index_active_dir=str(raw.get("index_active_dir", "data/index/active")),
        sources_path=str(raw.get("sources_path", "config/sources.yaml")),
        expected_schemes=int(raw.get("expected_schemes", 10)),
        expected_documents=int(raw.get("expected_documents", 50)),
        required_sections=tuple(raw.get("required_sections", [])),
        required_shadow_fields=tuple(raw.get("required_shadow_fields", [])),
        required_text_labels=tuple(raw.get("required_text_labels", [])),
    )


def load_golden_cases(path: str | Path) -> list[dict]:
    raw = _load_yaml(path)
    cases = raw.get("cases", [])
    if not isinstance(cases, list) or not cases:
        raise EvalConfigError(f"No golden cases in {path}")
    return cases
