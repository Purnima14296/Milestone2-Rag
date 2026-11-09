from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from mf_faq_assistant.phase0_governance.sources import load_locked_sources
from mf_faq_assistant.phase5_eval_observability.config_loader import DriftConfig, load_drift_config


@dataclass(frozen=True)
class DriftIssue:
    scheme_id: str
    code: str
    message: str


@dataclass(frozen=True)
class DriftReport:
    drift_version: str
    ran_at_utc: str
    scheme_count: int
    document_count: int
    issues: tuple[DriftIssue, ...]

    @property
    def passed(self) -> bool:
        return not self.issues


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_documents(index_dir: Path) -> list[dict]:
    documents_path = index_dir / "documents.jsonl"
    if not documents_path.exists():
        raise ValueError(f"Missing documents manifest: {documents_path}")

    rows: list[dict] = []
    with open(documents_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def _load_index_meta(index_dir: Path) -> dict:
    meta_path = index_dir / "meta.json"
    if not meta_path.exists():
        raise ValueError(f"Missing index meta: {meta_path}")
    return json.loads(meta_path.read_text(encoding="utf-8"))


def run_drift_check(*, config: DriftConfig | None = None) -> DriftReport:
    cfg = config or load_drift_config()
    index_dir = Path(cfg.index_active_dir)
    meta = _load_index_meta(index_dir)
    documents = _load_documents(index_dir)
    locked = load_locked_sources(cfg.sources_path)
    enabled_ids = {source.id for source in locked.enabled_sources()}

    issues: list[DriftIssue] = []

    if meta.get("status") != "ok":
        issues.append(DriftIssue("index", "index_status", f"status={meta.get('status')!r}"))

    scheme_count = int(meta.get("scheme_count", 0))
    document_count = int(meta.get("document_count", 0))
    if scheme_count != cfg.expected_schemes:
        issues.append(
            DriftIssue("index", "scheme_count", f"expected {cfg.expected_schemes}, got {scheme_count}")
        )
    if document_count != cfg.expected_documents:
        issues.append(
            DriftIssue("index", "document_count", f"expected {cfg.expected_documents}, got {document_count}")
        )

    by_scheme: dict[str, list[dict]] = {}
    for doc in documents:
        scheme_id = str(doc.get("scheme_id", ""))
        by_scheme.setdefault(scheme_id, []).append(doc)

    for scheme_id in sorted(enabled_ids):
        scheme_docs = by_scheme.get(scheme_id, [])
        if not scheme_docs:
            issues.append(DriftIssue(scheme_id, "missing_scheme", "no indexed documents"))
            continue

        sections = {str(doc.get("section_name", "")) for doc in scheme_docs}
        for section in cfg.required_sections:
            if section not in sections:
                issues.append(
                    DriftIssue(scheme_id, "missing_section", f"missing section {section!r}")
                )

        fund_details = [doc for doc in scheme_docs if doc.get("section_name") == "Fund Details"]
        if fund_details:
            doc = fund_details[0]
            shadow = doc.get("shadow_fields") or {}
            text = str(doc.get("embedded_text", ""))
            for field in cfg.required_shadow_fields:
                if not shadow.get(field):
                    issues.append(
                        DriftIssue(scheme_id, "missing_shadow_field", f"missing shadow field {field!r}")
                    )
            for label in cfg.required_text_labels:
                if label not in text:
                    issues.append(
                        DriftIssue(scheme_id, "missing_text_label", f"missing label {label!r}")
                    )

    return DriftReport(
        drift_version=cfg.drift_version,
        ran_at_utc=_utc_now_z(),
        scheme_count=scheme_count,
        document_count=document_count,
        issues=tuple(issues),
    )


def report_to_dict(report: DriftReport) -> dict:
    return {
        "drift_version": report.drift_version,
        "ran_at_utc": report.ran_at_utc,
        "passed": report.passed,
        "scheme_count": report.scheme_count,
        "document_count": report.document_count,
        "issue_count": len(report.issues),
        "issues": [
            {"scheme_id": issue.scheme_id, "code": issue.code, "message": issue.message}
            for issue in report.issues
        ],
    }


def assert_drift_check_passes(report: DriftReport) -> None:
    if report.passed:
        return
    details = "; ".join(f"{issue.scheme_id}/{issue.code}: {issue.message}" for issue in report.issues)
    raise AssertionError(f"Drift check failed: {details}")
