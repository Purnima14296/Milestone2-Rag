import sys
import unittest

sys.path.insert(0, "src")

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import (
    EvidenceChunk,
    RetrievalResult,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.fact_extractor import (
    extract_grounded_answer,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.generator import generate_answer
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.grounding_validator import (
    is_deflection,
    validate_grounded_answer,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.llm_config import LlmConfig
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.orchestrator import (
    chat,
    load_orchestrator_config,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.post_processor import (
    format_factual_answer,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.refusal_composer import (
    NOT_FOUND_MESSAGE,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.template_generator import (
    GroundingError,
    generate_from_templates,
)


def _retrieval(
    *,
    field_intent: str,
    chunks: tuple[EvidenceChunk, ...],
    query: str = "test query",
    field_intents: tuple[str, ...] | None = None,
) -> RetrievalResult:
    intents = field_intents or (field_intent,)
    return RetrievalResult(
        status="ok",
        query=query,
        query_normalized=query,
        scheme_id="hdfc_small_cap_fund_direct_growth",
        scheme_name="HDFC Small Cap Fund Direct Growth",
        field_intent=field_intent,
        field_intents=intents,
        source_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
        fetched_at="2026-06-02T14:01:58Z",
        evidence_chunks=chunks,
        retrieval_path="field_route",
        confidence=1.0,
        reason=None,
    )


FUND_DETAILS_CHUNK = EvidenceChunk(
    chunk_id="hdfc_small_cap_fund_direct_growth:run:fund_details:0",
    section_name="Fund Details",
    embedded_text=(
        "HDFC Small Cap Fund Direct Growth | Fund Details: "
        "NAV: 01 Jun '26 ₹151.13 Min. for SIP ₹100 "
        "Fund size (AUM) ₹38,168.18 Cr Expense ratio 0.73%"
    ),
    score=10.0,
    shadow_fields={
        "nav": "₹151.13 as of 01 Jun '26",
        "expense_ratio": "0.73%",
        "min_sip": "100",
    },
)


class TestGroundingValidator(unittest.TestCase):
    def test_is_deflection_rejects_generic_phrases(self) -> None:
        self.assertTrue(is_deflection("The NAV is available in the fund details section."))
        self.assertTrue(is_deflection("Please check the source for more information."))
        self.assertFalse(is_deflection("₹151.13 (as of 01 Jun '26)"))

    def test_validate_grounded_answer_accepts_extracted_fact(self) -> None:
        retrieval = _retrieval(field_intent="nav", chunks=(FUND_DETAILS_CHUNK,))
        answer = "₹151.13 (as of 01 Jun '26)"
        self.assertTrue(validate_grounded_answer(answer, retrieval, expected=answer))


class TestFactExtractor(unittest.TestCase):
    def test_extract_nav_from_shadow_fields(self) -> None:
        retrieval = _retrieval(
            field_intent="nav",
            chunks=(FUND_DETAILS_CHUNK,),
            query="What is the NAV of HDFC Small Cap Fund Direct Growth?",
        )
        answer = extract_grounded_answer(retrieval)
        self.assertIsNotNone(answer)
        self.assertIn("151.13", answer)
        self.assertNotIn("available in", answer.lower())

    def test_extract_aum_from_text(self) -> None:
        retrieval = _retrieval(
            field_intent="aum",
            chunks=(FUND_DETAILS_CHUNK,),
            query="AUM of HDFC Small Cap Fund Direct Growth",
        )
        answer = extract_grounded_answer(retrieval)
        self.assertIsNotNone(answer)
        self.assertIn("38,168.18", answer)

    def test_extract_expense_ratio(self) -> None:
        retrieval = _retrieval(
            field_intent="expense_ratio",
            chunks=(FUND_DETAILS_CHUNK,),
            query="expense ratio for HDFC Small Cap Fund Direct Growth",
        )
        answer = extract_grounded_answer(retrieval)
        self.assertIsNotNone(answer)
        self.assertIn("0.73%", answer)

    def test_extract_nav_and_expense_ratio(self) -> None:
        retrieval = _retrieval(
            field_intent="nav",
            field_intents=("nav", "expense_ratio"),
            chunks=(FUND_DETAILS_CHUNK,),
            query="What is the NAV and expense ratio of HDFC Small Cap Fund Direct Growth?",
        )
        answer = extract_grounded_answer(retrieval)
        self.assertIsNotNone(answer)
        self.assertIn("151.13", answer)
        self.assertIn("0.73%", answer)

    def test_raises_when_no_evidence(self) -> None:
        retrieval = _retrieval(field_intent="nav", chunks=())
        with self.assertRaises(GroundingError):
            generate_from_templates(retrieval)


class TestPostProcessorGrounding(unittest.TestCase):
    def test_rejects_deflection_in_factual_answer(self) -> None:
        with self.assertRaises(ValueError):
            format_factual_answer(
                "The NAV is available in the fund details section.",
                citation_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
                fetched_at="2026-06-02T14:01:58Z",
            )


class TestOrchestratorGrounding(unittest.TestCase):
    def setUp(self) -> None:
        self.index = CorpusIndex("data/index/active")
        self.config = load_orchestrator_config()

    def tearDown(self) -> None:
        self.index.close()

    def test_not_found_message(self) -> None:
        result = chat(
            "What is the lock-in period for HDFC Silver ETF FoF Direct Growth?",
            index=self.index,
            config=self.config,
        )
        self.assertEqual(result.reason, "not_found")
        self.assertIn(NOT_FOUND_MESSAGE, result.answer_text)
        self.assertIsNone(result.citation_url)

    def test_stock_price_of_gold_is_not_found(self) -> None:
        result = chat(
            "stock price of gold?",
            index=self.index,
            config=self.config,
        )
        self.assertEqual(result.reason, "out_of_scope")
        self.assertIn(NOT_FOUND_MESSAGE, result.answer_text)
        self.assertIsNone(result.citation_url)
        self.assertNotIn("48.11", result.answer_text)

    def test_icici_mid_cap_is_unsupported(self) -> None:
        result = chat(
            "What is the expense ratio of ICICI mid cap fund",
            index=self.index,
            config=self.config,
        )
        self.assertEqual(result.reason, "not_found")
        self.assertIn("I'm sorry, but I don't have information about ICICI mid cap fund", result.answer_text)
        self.assertIsNone(result.citation_url)
        self.assertNotIn("0.73%", result.answer_text)

    def test_nav_end_to_end(self) -> None:
        result = chat(
            "What is the NAV of HDFC Small Cap Fund Direct Growth?",
            index=self.index,
            config=self.config,
        )
        self.assertIsNone(result.reason)
        self.assertIn("151.13", result.answer_text)
        self.assertIn("HDFC Small Cap Fund Direct Growth", result.answer_text)
        self.assertFalse(is_deflection(result.answer_text))

    def test_nav_for_index_fund_scheme(self) -> None:
        result = chat(
            "What is the NAV of HDFC Nifty 50 Index Fund Direct Growth?",
            index=self.index,
            config=self.config,
        )
        self.assertIsNone(result.reason)
        self.assertIn("227.64", result.answer_text)
        self.assertIn("HDFC Nifty 50 Index Fund Direct Growth", result.answer_text)
        self.assertNotIn("Benchmark is", result.answer_text.split("Last updated")[0])

    def test_fund_manager_extracts_person_name(self) -> None:
        result = chat(
            "fund manager of HDFC Small Cap Fund Direct Growth",
            index=self.index,
            config=self.config,
        )
        self.assertIsNone(result.reason)
        self.assertIn("Dhruv Muchhal", result.answer_text)
        self.assertIn("HDFC Small Cap Fund Direct Growth", result.answer_text)
        self.assertNotIn("HDFC Small Cap.", result.answer_text)

    def test_aum_end_to_end(self) -> None:
        result = chat(
            "What is the AUM of HDFC Small Cap Fund Direct Growth?",
            index=self.index,
            config=self.config,
        )
        self.assertIsNone(result.reason)
        self.assertIn("38,168.18", result.answer_text)
        self.assertFalse(is_deflection(result.answer_text))

    def test_nav_and_expense_ratio_end_to_end(self) -> None:
        result = chat(
            "What is the NAV and expense ratio of HDFC Small Cap Fund Direct Growth?",
            index=self.index,
            config=self.config,
        )
        self.assertIsNone(result.reason)
        self.assertIn("151.13", result.answer_text)
        self.assertIn("0.73%", result.answer_text)
        self.assertIn("HDFC Small Cap Fund Direct Growth", result.answer_text)

    def test_nav_mid_cap_and_large_cap_end_to_end(self) -> None:
        result = chat(
            "NAV of HDFC mid cap and HDFC large cap funds?",
            index=self.index,
            config=self.config,
        )
        self.assertIsNone(result.reason)
        self.assertIn("218.88", result.answer_text)
        self.assertIn("HDFC Mid Cap Fund Direct Growth", result.answer_text)
        self.assertIn("don't have information about HDFC large cap funds", result.answer_text)
        self.assertIsNotNone(result.citation_url)

    def test_nav_mid_cap_and_small_cap_end_to_end(self) -> None:
        result = chat(
            "NAV of HDFC mid cap and small cap funds",
            index=self.index,
            config=self.config,
        )
        self.assertIsNone(result.reason)
        self.assertIn("218.88", result.answer_text)
        self.assertIn("151.13", result.answer_text)
        self.assertIn("HDFC Mid Cap Fund Direct Growth", result.answer_text)
        self.assertIn("HDFC Small Cap Fund Direct Growth", result.answer_text)

    def test_nav_and_min_sip_end_to_end(self) -> None:
        result = chat(
            "NAV and min SIP for HDFC Small Cap Fund Direct Growth",
            index=self.index,
            config=self.config,
        )
        self.assertIsNone(result.reason)
        self.assertIn("151.13", result.answer_text)
        self.assertIn("100", result.answer_text)


class TestGeneratorGrounding(unittest.TestCase):
    def test_template_provider_returns_grounded_fact(self) -> None:
        retrieval = _retrieval(
            field_intent="min_sip",
            chunks=(
                EvidenceChunk(
                    chunk_id="hdfc_small_cap_fund_direct_growth:run:minimum_investments:0",
                    section_name="Minimum Investments",
                    embedded_text="HDFC Small Cap Fund Direct Growth | Minimum Investments: Min. for SIP ₹100",
                    score=10.0,
                    shadow_fields={"min_sip": "100"},
                ),
            ),
            query="Min SIP for HDFC Small Cap Fund Direct Growth",
        )
        config = LlmConfig(
            provider="template",
            model_id="llama-3.3-70b-versatile",
            temperature=0,
            max_tokens=256,
            api_key_env="GROQ_API_KEY",
            fallback_to_templates=True,
        )
        answer = generate_answer(retrieval, llm_config=config)
        self.assertIn("₹100", answer)
        self.assertFalse(is_deflection(answer))


if __name__ == "__main__":
    unittest.main()
