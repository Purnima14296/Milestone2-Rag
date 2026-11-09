import sys
import unittest

sys.path.insert(0, "src")

from mf_faq_assistant.phase5_eval_observability.drift_checker import (
    assert_drift_check_passes,
    run_drift_check,
)


class TestPhase5Drift(unittest.TestCase):
    def test_active_index_passes_drift_check(self) -> None:
        report = run_drift_check()
        assert_drift_check_passes(report)
        self.assertEqual(report.scheme_count, 10)
        self.assertEqual(report.document_count, 50)


if __name__ == "__main__":
    unittest.main()
