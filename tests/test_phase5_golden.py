import sys
import unittest

sys.path.insert(0, "src")

from mf_faq_assistant.phase5_eval_observability.golden_eval import (
    assert_golden_eval_passes,
    run_golden_eval,
)


class TestPhase5Golden(unittest.TestCase):
    def test_golden_eval_passes(self) -> None:
        report = run_golden_eval()
        assert_golden_eval_passes(report)
        self.assertGreaterEqual(report.hard_pass_rate, 1.0)
        self.assertEqual(report.contract_violations, 0)


if __name__ == "__main__":
    unittest.main()
