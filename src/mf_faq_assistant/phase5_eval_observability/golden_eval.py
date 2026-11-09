from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.orchestrator import (
    ChatResponse,
    chat,
    load_orchestrator_config,
)
from mf_faq_assistant.phase5_eval_observability.config_loader import (
    EvalConfig,
    load_eval_config,
    load_golden_cases,
)
from mf_faq_assistant.phase5_eval_observability.contract_validator import (
    validate_chat_contract,
)


@dataclass(frozen=True)
class GoldenCaseResult:
    case_id: str
    severity: str
    passed: bool
    failures: tuple[str, ...]


@dataclass(frozen=True)
class GoldenEvalReport:
    eval_version: str
    ran_at_utc: str
    total: int
    passed: int
    failed: int
    hard_total: int
    hard_passed: int
    hard_pass_rate: float
    contract_violations: int
    results: tuple[GoldenCaseResult, ...]


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _check_expectations(case: dict, response: ChatResponse) -> list[str]:
    failures: list[str] = []
    expect = case.get("expect", {}) or {}

    if "reason" in expect and response.reason != expect["reason"]:
        failures.append(f"reason expected {expect['reason']!r}, got {response.reason!r}")

    if "refusal" in expect and response.refusal != expect["refusal"]:
        failures.append(f"refusal expected {expect['refusal']!r}, got {response.refusal!r}")

    if expect.get("has_citation") is True and not response.citation_url:
        failures.append("expected citation URL")
    if expect.get("has_citation") is False and response.citation_url:
        failures.append("expected no citation URL")

    answer_lower = response.answer_text.lower()
    for fragment in expect.get("answer_contains", []) or []:
        if str(fragment).lower() not in answer_lower:
            failures.append(f"answer missing fragment: {fragment!r}")

    for fragment in expect.get("answer_not_contains", []) or []:
        if str(fragment).lower() in answer_lower:
            failures.append(f"answer must not contain: {fragment!r}")

    citation = response.citation_url or ""
    if expect.get("citation_contains") and expect["citation_contains"] not in citation:
        failures.append(f"citation missing fragment: {expect['citation_contains']!r}")

    return failures


def run_golden_eval(
    *,
    config: EvalConfig | None = None,
    index: CorpusIndex | None = None,
) -> GoldenEvalReport:
    cfg = config or load_eval_config()
    cases = load_golden_cases(cfg.golden_path)
    orch_config = load_orchestrator_config()

    should_close = index is None
    corpus_index = index or CorpusIndex(cfg.index_active_dir)

    results: list[GoldenCaseResult] = []
    contract_violations = 0

    try:
        for case in cases:
            case_id = str(case["id"])
            severity = str(case.get("severity", "hard"))
            response = chat(
                str(case["message"]),
                index=corpus_index,
                config=orch_config,
            )
            failures = _check_expectations(case, response)
            violations = validate_chat_contract(response, max_sentences=orch_config.max_answer_sentences)
            if violations:
                contract_violations += 1
                failures.extend(f"contract:{v.code}" for v in violations)

            results.append(
                GoldenCaseResult(
                    case_id=case_id,
                    severity=severity,
                    passed=not failures,
                    failures=tuple(failures),
                )
            )
    finally:
        if should_close:
            corpus_index.close()

    passed = sum(1 for row in results if row.passed)
    hard_rows = [row for row in results if row.severity == "hard"]
    hard_passed = sum(1 for row in hard_rows if row.passed)
    hard_total = len(hard_rows)

    return GoldenEvalReport(
        eval_version=cfg.eval_version,
        ran_at_utc=_utc_now_z(),
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        hard_total=hard_total,
        hard_passed=hard_passed,
        hard_pass_rate=(hard_passed / hard_total) if hard_total else 1.0,
        contract_violations=contract_violations,
        results=tuple(results),
    )


def report_to_dict(report: GoldenEvalReport) -> dict:
    return {
        "eval_version": report.eval_version,
        "ran_at_utc": report.ran_at_utc,
        "total": report.total,
        "passed": report.passed,
        "failed": report.failed,
        "hard_total": report.hard_total,
        "hard_passed": report.hard_passed,
        "hard_pass_rate": report.hard_pass_rate,
        "contract_violations": report.contract_violations,
        "results": [
            {
                "case_id": row.case_id,
                "severity": row.severity,
                "passed": row.passed,
                "failures": list(row.failures),
            }
            for row in report.results
        ],
    }


def write_eval_report(report: GoldenEvalReport, path: str | Path) -> str:
    report_path = Path(path)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report_to_dict(report), indent=2), encoding="utf-8")
    return str(report_path)


def assert_golden_eval_passes(
    report: GoldenEvalReport,
    *,
    min_hard_pass_rate: float = 1.0,
) -> None:
    if report.hard_pass_rate < min_hard_pass_rate:
        failed = [row for row in report.results if row.severity == "hard" and not row.passed]
        details = "; ".join(f"{row.case_id}: {', '.join(row.failures)}" for row in failed)
        raise AssertionError(f"Golden eval failed ({report.hard_pass_rate:.0%} hard pass): {details}")
