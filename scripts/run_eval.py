#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mf_faq_assistant.phase5_eval_observability.config_loader import load_eval_config
from mf_faq_assistant.phase5_eval_observability.golden_eval import (
    assert_golden_eval_passes,
    report_to_dict,
    run_golden_eval,
    write_eval_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5 golden eval suite")
    parser.add_argument("--config", default="config/eval.yaml")
    parser.add_argument("--report", default=None, help="Override eval report output path")
    parser.add_argument("--json", action="store_true", help="Print full JSON report to stdout")
    args = parser.parse_args()

    cfg = load_eval_config(args.config)
    report = run_golden_eval(config=cfg)
    report_path = write_eval_report(report, args.report or cfg.report_path)

    if args.json:
        import json

        print(json.dumps(report_to_dict(report), indent=2))
    else:
        print(f"Golden eval: {report.hard_passed}/{report.hard_total} hard cases passed")
        print(f"Overall: {report.passed}/{report.total} passed")
        print(f"Contract violations: {report.contract_violations}")
        print(f"Report: {report_path}")
        for row in report.results:
            if not row.passed:
                print(f"  FAIL [{row.severity}] {row.case_id}: {', '.join(row.failures)}")

    try:
        assert_golden_eval_passes(report, min_hard_pass_rate=cfg.min_hard_pass_rate)
    except AssertionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
