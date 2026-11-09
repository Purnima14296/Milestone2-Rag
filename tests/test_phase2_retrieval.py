import sys
import unittest

sys.path.insert(0, "src")

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import CorpusIndex
from mf_faq_assistant.phase0_governance.sources import load_locked_sources
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.field_intent import (
    detect_field_intent,
    detect_field_intents,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.query_normalizer import (
    normalize_query,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.retriever import (
    load_retrieval_config,
    retrieve,
)
from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.scheme_resolver import (
    resolve_scheme,
    resolve_scheme_mentions,
)


class TestPhase2Retrieval(unittest.TestCase):
    def setUp(self) -> None:
        self.index = CorpusIndex("data/index/active")
        self.locked = load_locked_sources("config/sources.yaml")
        self.config = load_retrieval_config()

    def tearDown(self) -> None:
        self.index.close()

    def _retrieve(self, query: str, *, scheme_id: str | None = None):
        return retrieve(
            query,
            selected_scheme_id=scheme_id,
            index=self.index,
            locked=self.locked,
            config=self.config,
        )

    def test_load_retrieval_config(self) -> None:
        self.assertEqual(self.config.top_k_per_path, 5)
        self.assertEqual(self.config.keyword_weight, 0.55)

    def test_normalize_query_expands_midcap(self) -> None:
        normalized = normalize_query("HDFC midcap expense ratio")
        self.assertIn("mid cap", normalized.normalized)

    def test_detect_field_intent_nav_beats_index_in_scheme_name(self) -> None:
        field = detect_field_intent(
            "what is the nav of hdfc nifty 50 index fund direct growth"
        )
        self.assertIsNotNone(field)
        self.assertEqual(field.field, "nav")

    def test_detect_field_intent_expense_ratio(self) -> None:
        field = detect_field_intent("what is the expense ratio for hdfc small cap")
        self.assertIsNotNone(field)
        self.assertEqual(field.field, "expense_ratio")

    def test_detect_field_intents_nav_and_expense_ratio(self) -> None:
        fields = detect_field_intents(
            "What is the NAV and expense ratio of HDFC Small Cap Fund Direct Growth?"
        )
        self.assertEqual(tuple(intent.field for intent in fields), ("nav", "expense_ratio"))

    def test_resolve_scheme_mentions_mid_and_large_cap(self) -> None:
        mentions = resolve_scheme_mentions(
            "NAV of HDFC mid cap and HDFC large cap funds?",
            self.locked,
            min_confidence=self.config.scheme_resolver_min_confidence,
        )
        self.assertIsNotNone(mentions)
        self.assertEqual(len(mentions.resolved), 1)
        self.assertEqual(mentions.resolved[0].scheme_id, "hdfc_mid_cap_fund_direct_growth")
        self.assertEqual(mentions.unresolved, ("HDFC large cap funds",))

    def test_resolve_scheme_mentions_not_triggered_for_multi_field(self) -> None:
        mentions = resolve_scheme_mentions(
            "NAV and expense ratio of HDFC Small Cap Fund Direct Growth",
            self.locked,
            min_confidence=self.config.scheme_resolver_min_confidence,
        )
        self.assertIsNone(mentions)

    def test_multi_field_retrieval_nav_and_expense_ratio(self) -> None:
        result = self._retrieve(
            "What is the NAV and expense ratio of HDFC Small Cap Fund Direct Growth?"
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.field_intents, ("nav", "expense_ratio"))
        self.assertGreaterEqual(len(result.evidence_chunks), 1)
        combined = " ".join(
            chunk.embedded_text + " " + " ".join(chunk.shadow_fields.values())
            for chunk in result.evidence_chunks
        )
        self.assertIn("151.13", combined)
        self.assertIn("0.73%", combined)

    def test_resolve_scheme_small_cap(self) -> None:
        resolution = resolve_scheme(
            "min sip for hdfc small cap fund direct growth",
            self.locked,
            min_confidence=self.config.scheme_resolver_min_confidence,
        )
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.scheme_id, "hdfc_small_cap_fund_direct_growth")

    def test_resolve_scheme_midcap_alias(self) -> None:
        resolution = resolve_scheme(
            "expense ratio hdfc midcap",
            self.locked,
            min_confidence=self.config.scheme_resolver_min_confidence,
        )
        self.assertTrue(resolution.resolved)
        self.assertEqual(resolution.scheme_id, "hdfc_mid_cap_fund_direct_growth")

    def test_needs_clarification_without_scheme(self) -> None:
        result = self._retrieve("What is the expense ratio?")
        self.assertEqual(result.status, "needs_clarification")
        self.assertEqual(result.field_intent, "expense_ratio")

    def test_out_of_scope_stock_price_of_gold(self) -> None:
        result = self._retrieve("stock price of gold?")
        self.assertEqual(result.status, "not_found")
        self.assertEqual(result.reason, "out_of_scope")

    def test_icici_mid_cap_returns_unsupported_message(self) -> None:
        result = self._retrieve("What is the expense ratio of ICICI mid cap fund")
        self.assertEqual(result.status, "needs_clarification")

    def test_hdfc_mid_cap_expense_ratio_still_works(self) -> None:
        result = self._retrieve("expense ratio for HDFC Mid Cap Fund Direct Growth")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.scheme_id, "hdfc_mid_cap_fund_direct_growth")

    def test_gold_fund_nav_still_works(self) -> None:
        result = self._retrieve("What is the NAV of HDFC Gold ETF Fund of Fund Direct Plan Growth?")
        self.assertEqual(result.status, "ok")
        self.assertIn("48.11", result.evidence_chunks[0].embedded_text)

    def test_extract_unsupported_fund_reference(self) -> None:
        from mf_faq_assistant.phase2_retrieval.subphase_2_retrieval_layer.query_scope import (
            extract_unsupported_fund_reference,
        )

        self.assertEqual(
            extract_unsupported_fund_reference("expense ratio of ICICI mid cap fund"),
            "ICICI mid cap fund",
        )

    def test_field_route_min_sip(self) -> None:
        result = self._retrieve("Min SIP for HDFC Small Cap Fund Direct Growth")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.scheme_id, "hdfc_small_cap_fund_direct_growth")
        self.assertEqual(result.retrieval_path, "field_route")
        self.assertTrue(result.evidence_chunks)
        self.assertEqual(result.evidence_chunks[0].section_name, "Minimum Investments")

    def test_field_route_expense_ratio(self) -> None:
        result = self._retrieve("expense ratio for HDFC Small Cap Fund Direct Growth")
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.retrieval_path, "field_route")
        self.assertEqual(result.evidence_chunks[0].section_name, "Fund Details")
        self.assertIn("0.73%", result.evidence_chunks[0].shadow_fields.get("expense_ratio", ""))

    def test_hybrid_paraphrase_min_sip(self) -> None:
        result = self._retrieve(
            "how much do I need to start a monthly investment in hdfc small cap direct growth"
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.scheme_id, "hdfc_small_cap_fund_direct_growth")
        self.assertIn(
            result.evidence_chunks[0].section_name,
            {"Minimum Investments", "Fund Details"},
        )

    def test_explicit_scheme_override(self) -> None:
        result = self._retrieve(
            "exit load",
            scheme_id="hdfc_nifty_50_index_fund_direct_growth",
        )
        self.assertEqual(result.status, "ok")
        self.assertEqual(result.scheme_id, "hdfc_nifty_50_index_fund_direct_growth")
        self.assertEqual(result.evidence_chunks[0].section_name, "Exit Load and Tax")

    def test_single_citation_url(self) -> None:
        result = self._retrieve("benchmark for HDFC Nifty 50 Index Fund Direct Growth")
        self.assertEqual(result.status, "ok")
        self.assertEqual(
            result.source_url,
            "https://groww.in/mutual-funds/hdfc-nifty-50-index-fund-direct-growth",
        )
        urls = {result.source_url}
        self.assertEqual(len(urls), 1)


if __name__ == "__main__":
    unittest.main()
