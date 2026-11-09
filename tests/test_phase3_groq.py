import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, "src")

from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import EvidenceChunk
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.generator import generate_answer
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.llm_config import (
    LlmConfig,
    load_llm_config,
)
from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.template_generator import (
    generate_from_templates,
)

SAMPLE_RETRIEVAL = type(
    "RetrievalResult",
    (),
    {
        "status": "ok",
        "query": "Min SIP for HDFC Small Cap Fund Direct Growth",
        "scheme_name": "HDFC Small Cap Fund Direct Growth",
        "field_intent": "min_sip",
        "evidence_chunks": (
            EvidenceChunk(
                chunk_id="hdfc_small_cap_fund_direct_growth:run:minimum_investments:0",
                section_name="Minimum Investments",
                embedded_text="HDFC Small Cap Fund Direct Growth | Minimum Investments: Min. for SIP ₹100",
                score=10.0,
                shadow_fields={"min_sip": "100"},
            ),
        ),
    },
)()


class TestPhase3Groq(unittest.TestCase):
    def test_load_llm_config(self) -> None:
        config = load_llm_config()
        self.assertEqual(config.provider, "groq")
        self.assertEqual(config.model_id, "llama-3.3-70b-versatile")
        self.assertTrue(config.fallback_to_templates)

    def test_template_generator_min_sip(self) -> None:
        answer = generate_from_templates(SAMPLE_RETRIEVAL)
        self.assertIn("₹100", answer)

    def test_generate_answer_uses_template_when_provider_template(self) -> None:
        config = LlmConfig(
            provider="template",
            model_id="llama-3.3-70b-versatile",
            temperature=0,
            max_tokens=256,
            api_key_env="GROQ_API_KEY",
            fallback_to_templates=True,
        )
        answer = generate_answer(SAMPLE_RETRIEVAL, llm_config=config)
        self.assertIn("₹100", answer)

    @patch("groq.Groq")
    def test_generate_answer_uses_groq_when_key_present(self, mock_groq_cls: MagicMock) -> None:
        mock_client = MagicMock()
        mock_groq_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(message=MagicMock(content="The minimum SIP is ₹100."))]
        )

        config = LlmConfig(
            provider="groq",
            model_id="llama-3.3-70b-versatile",
            temperature=0,
            max_tokens=256,
            api_key_env="GROQ_API_KEY",
            fallback_to_templates=True,
        )

        with patch.dict("os.environ", {"GROQ_API_KEY": "test-key"}):
            answer = generate_answer(SAMPLE_RETRIEVAL, llm_config=config)

        self.assertIn("₹100", answer)
        mock_client.chat.completions.create.assert_called_once()
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], "llama-3.3-70b-versatile")

    def test_generate_answer_falls_back_without_api_key(self) -> None:
        config = LlmConfig(
            provider="groq",
            model_id="llama-3.3-70b-versatile",
            temperature=0,
            max_tokens=256,
            api_key_env="GROQ_API_KEY",
            fallback_to_templates=True,
        )
        with patch.dict("os.environ", {}, clear=True):
            answer = generate_answer(SAMPLE_RETRIEVAL, llm_config=config)
        self.assertIn("₹100", answer)


if __name__ == "__main__":
    unittest.main()
