import sys
import unittest

sys.path.insert(0, "src")

from mf_faq_assistant.phase1_ingestion.subphase_1_2_extractor.extractor import (
    ExtractionError,
    extract_all_latest,
    extract_html,
)
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.corpus_builder import (
    build_corpus_document,
)
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.faq_builder import build_faq_document
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.normalizer import (
    normalize_text,
)


SAMPLE_HTML = """
<html><body>
  <nav>Home Mutual Funds</nav>
  <main>
    <h1>HDFC Gold ETF Fund of Fund Direct Plan Growth</h1>
    <div>Expense ratio 0.20%</div>
    <div>Min. for SIP ₹100</div>
    <div>Exit load of 1%, if redeemed within 15 days.</div>
    <div>Fund benchmark Domestic Price of Gold</div>
  </main>
  <footer>© Groww</footer>
</body></html>
"""


class TestPhase1Extractor(unittest.TestCase):
    def test_extract_html_finds_key_fields(self) -> None:
        text, fields = extract_html(SAMPLE_HTML, min_chars=50, min_fields=2)
        self.assertIn("expense_ratio", fields)
        self.assertIn("exit_load", fields)
        self.assertIn("Expense ratio 0.20%", text)

    def test_extract_html_rejects_empty(self) -> None:
        with self.assertRaises(ExtractionError):
            extract_html("<html><body></body></html>", min_chars=10, min_fields=1)


class TestPhase1Normalizer(unittest.TestCase):
    def test_build_faq_document_keeps_facts_and_drops_noise(self) -> None:
        raw = """
NAV: 01 Jun '26
₹100
Min. for SIP
₹100
Expense ratio
0.20%
Return calculator
Would've become
Holdings (319)
ICICI Bank Ltd
Minimum investments
Min. for 1st investment
₹100
Understand terms
Returns and rankings
01 Jan 2020
Exit load of 1%, if redeemed within 15 days.
Exit load, stamp duty and tax
Stamp duty on investment: 0.005%
Tax implication
Taxed at 12.5%
Fund management
Manager bio
Investment Objective
Generate capital appreciation.
Fund benchmark
NIFTY 50
Terms and Conditions
"""
        doc = build_faq_document(raw)
        self.assertIn("Expense ratio", doc)
        self.assertIn("Minimum investments", doc)
        self.assertIn("Fund benchmark", doc)
        self.assertNotIn("Holdings (319)", doc)
        self.assertNotIn("Return calculator", doc)
        self.assertNotIn("Would've become", doc)
        self.assertNotIn("Fund management", doc)
        self.assertNotIn("Terms and Conditions", doc)

    def test_normalize_text_strips_footer_and_dedupes(self) -> None:
        raw = """NAV: 01 Jun '26
₹48.11
Min. for SIP
₹100
Expense ratio
0.20%
Return calculator
Holdings (3)
Minimum investments
Min. for 1st investment
₹100
Exit load of 1%, if redeemed within 15 days.
Exit load, stamp duty and tax
Stamp duty on investment: 0.005%
Investment Objective
Capital appreciation.
Fund benchmark
Domestic Price of Gold"""
        normalized, shadow = normalize_text(raw, min_chars=80)
        self.assertIn("expense_ratio", shadow)
        self.assertNotIn("Holdings", normalized)


class TestPhase1CorpusBuilder(unittest.TestCase):
    SAMPLE_HTML = """
<html><head>
<meta name="description" content="HDFC Small Cap Fund Direct Growth - Get latest NAV, SIP Returns & Rank">
</head><body></body></html>
"""

    SAMPLE_EXTRACTED = """
About HDFC Small Cap Fund Direct Growth
This fund invests in small cap stocks.
NAV: 01 Jun '26
₹48.11
Min. for SIP
₹100
Expense ratio
0.73%
Fund size (AUM)
₹30,000 Cr
Minimum investments
Min. for 1st investment
₹100
Min. for 2nd investment
₹100
Min. for SIP
₹100
Exit load of 1%, if redeemed within 365 days.
Exit load, stamp duty and tax
Stamp duty on investment: 0.005%
Investment Objective
Capital appreciation.
Fund benchmark
BSE 250 SmallCap Total Return Index
"""

    def test_build_corpus_document_has_required_fields(self) -> None:
        corpus = build_corpus_document(
            scheme_id="hdfc_small_cap_fund_direct_growth",
            scheme_name="HDFC Small Cap Fund Direct Growth",
            source_url="https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
            fetched_at="2026-06-02T14:01:58Z",
            extracted_text=self.SAMPLE_EXTRACTED,
            raw_html=self.SAMPLE_HTML,
        )
        self.assertEqual(corpus["scheme_id"], "hdfc_small_cap_fund_direct_growth")
        self.assertEqual(corpus["scheme_name"], "HDFC Small Cap Fund Direct Growth")
        self.assertEqual(corpus["source_url"], "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth")
        self.assertEqual(corpus["fetched_at"], "2026-06-02T14:01:58Z")
        self.assertEqual(corpus["extractor_version"], "1.2.0")
        self.assertIn("must_have_anchors", corpus)
        self.assertTrue(corpus["must_have_anchors"]["About"])
        self.assertTrue(corpus["must_have_anchors"]["Fund Details"])

        section_names = [s["name"] for s in corpus["sections"]]
        self.assertIn("Meta Description", section_names)
        self.assertIn("About", section_names)
        self.assertIn("Fund Details", section_names)
        self.assertIn("Minimum Investments", section_names)
        self.assertIn("Exit Load and Tax", section_names)
        self.assertNotIn("FAQ", section_names)

        meta_section = next(s for s in corpus["sections"] if s["name"] == "Meta Description")
        self.assertEqual(meta_section["source"], "meta_description")
        self.assertIn("NAV", meta_section["text"])


class TestPhase1PipelineIntegration(unittest.TestCase):
    def test_extract_all_latest_from_raw_store(self) -> None:
        results = extract_all_latest()
        self.assertEqual(len(results), 10)


if __name__ == "__main__":
    unittest.main()
