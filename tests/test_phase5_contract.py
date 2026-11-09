import sys
import unittest

sys.path.insert(0, "src")

from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.orchestrator import ChatResponse
from mf_faq_assistant.phase5_eval_observability.contract_validator import (
    contract_is_valid,
    validate_chat_contract,
)


class TestPhase5Contract(unittest.TestCase):
    def test_factual_contract_valid(self) -> None:
        response = ChatResponse(
            answer_text="The minimum SIP is ₹100.\nLast updated from sources: 2026-06-02",
            citation_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
            last_updated_date="2026-06-02",
            refusal=False,
            reason=None,
        )
        self.assertTrue(contract_is_valid(response))

    def test_not_found_must_not_include_citation(self) -> None:
        response = ChatResponse(
            answer_text="I'm sorry, but I wasn't able to find that in the scheme sources I have access to.",
            citation_url=None,
            last_updated_date=None,
            refusal=False,
            reason="not_found",
        )
        self.assertTrue(contract_is_valid(response))

    def test_not_found_with_citation_is_invalid(self) -> None:
        response = ChatResponse(
            answer_text="Not found.",
            citation_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
            last_updated_date=None,
            refusal=False,
            reason="not_found",
        )
        violations = validate_chat_contract(response)
        self.assertTrue(any(v.code == "unexpected_citation" for v in violations))

    def test_factual_missing_footer_is_invalid(self) -> None:
        response = ChatResponse(
            answer_text="The minimum SIP is ₹100.",
            citation_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
            last_updated_date="2026-06-02",
            refusal=False,
            reason=None,
        )
        violations = validate_chat_contract(response)
        self.assertTrue(any(v.code == "missing_footer" for v in violations))


if __name__ == "__main__":
    unittest.main()
