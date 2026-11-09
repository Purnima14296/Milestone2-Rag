import sys
import unittest

sys.path.insert(0, "src")

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.orchestrator import (
    chat,
    load_orchestrator_config,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.pii_guard import check_pii
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.post_processor import (
    format_factual_answer,
    format_no_link_answer,
)


class TestPhase3Orchestrator(unittest.TestCase):
    def setUp(self) -> None:
        self.index = CorpusIndex("data/index/active")
        self.config = load_orchestrator_config()

    def tearDown(self) -> None:
        self.index.close()

    def _chat(self, message: str, *, scheme_id: str | None = None):
        return chat(
            message,
            selected_scheme_id=scheme_id,
            index=self.index,
            config=self.config,
        )

    def test_pii_guard_blocks_message(self) -> None:
        result = check_pii("My PAN is ABCDE1234F")
        self.assertTrue(result.blocked)
        self.assertIn("pan", result.kinds)

    def test_pii_chat_has_no_url(self) -> None:
        result = self._chat("My email is user@example.com, what is the expense ratio?")
        self.assertTrue(result.refusal)
        self.assertEqual(result.reason, "pii_blocked")
        self.assertIsNone(result.citation_url)
        self.assertNotIn("http", result.answer_text)

    def test_refusal_has_no_url(self) -> None:
        result = self._chat("Which HDFC fund is better than the other?")
        self.assertTrue(result.refusal)
        self.assertIsNone(result.citation_url)
        self.assertIn("compare", result.answer_text.lower())

    def test_not_found_has_no_url(self) -> None:
        result = self._chat("What is the lock-in period for HDFC Silver ETF FoF Direct Growth?")
        self.assertFalse(result.refusal)
        self.assertEqual(result.reason, "not_found")
        self.assertIsNone(result.citation_url)
        self.assertIn("wasn't able to find that", result.answer_text.lower())

    def test_needs_clarification_has_no_url(self) -> None:
        result = self._chat("What is the expense ratio?")
        self.assertEqual(result.reason, "needs_clarification")
        self.assertIsNone(result.citation_url)

    def test_factual_answer_has_single_url_and_footer(self) -> None:
        result = self._chat("Min SIP for HDFC Small Cap Fund Direct Growth")
        self.assertIsNone(result.reason)
        self.assertFalse(result.refusal)
        self.assertIsNotNone(result.citation_url)
        self.assertIn("groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth", result.citation_url)
        self.assertIn("Last updated from sources:", result.answer_text)
        self.assertIsNotNone(result.last_updated_date)
        self.assertIn("₹100", result.answer_text)

    def test_expense_ratio_answer(self) -> None:
        result = self._chat("expense ratio for HDFC Small Cap Fund Direct Growth")
        self.assertIsNone(result.reason)
        self.assertIn("0.73%", result.answer_text)
        self.assertIsNotNone(result.citation_url)

    def test_nav_answer_includes_value(self) -> None:
        result = self._chat("What is the NAV of HDFC Small Cap Fund Direct Growth?")
        self.assertIsNone(result.reason)
        self.assertIn("151.13", result.answer_text)
        self.assertIn("HDFC Small Cap Fund Direct Growth", result.answer_text)
        self.assertNotIn("available in the fund details section", result.answer_text.lower())
        self.assertIsNotNone(result.citation_url)

    def test_format_no_link_removes_urls(self) -> None:
        formatted = format_no_link_answer("No link here https://example.com/path.")
        self.assertIsNone(formatted.citation_url)
        self.assertNotIn("http", formatted.answer_text)

    def test_format_factual_enforces_footer(self) -> None:
        formatted = format_factual_answer(
            "The minimum SIP is ₹100.",
            citation_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
            fetched_at="2026-06-02T14:01:58Z",
        )
        self.assertEqual(formatted.last_updated_date, "2026-06-02")
        self.assertIn("Last updated from sources: 2026-06-02", formatted.answer_text)


if __name__ == "__main__":
    unittest.main()
