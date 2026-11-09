#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mf_faq_assistant.phase5_eval_observability.config_loader import load_drift_config
from mf_faq_assistant.phase5_eval_observability.drift_checker import (
    assert_drift_check_passes,
    report_to_dict,
    run_drift_check,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5 dataset drift checks")
    parser.add_argument("--config", default="config/drift.yaml")
    parser.add_argument("--json", action="store_true", help="Print JSON report to stdout")
    args = parser.parse_args()

    cfg = load_drift_config(args.config)
    report = run_drift_check(config=cfg)

    if args.json:
        print(json.dumps(report_to_dict(report), indent=2))
    else:
        status = "PASSED" if report.passed else "FAILED"
        print(f"Drift check: {status}")
        print(f"Schemes: {report.scheme_count}, Documents: {report.document_count}")
        for issue in report.issues:
            print(f"  {issue.scheme_id} [{issue.code}] {issue.message}")

    try:
        assert_drift_check_passes(report)
    except AssertionError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
