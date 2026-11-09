import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, "src")

from mf_faq_assistant.phase1_ingestion.subphase_1_4_chunker.chunker import (
    ATOMIC_SECTIONS,
    ChunkingError,
    build_chunks,
    chunk_all_latest,
    section_to_slug,
)

SAMPLE_CORPUS = {
    "scheme_id": "hdfc_small_cap_fund_direct_growth",
    "scheme_name": "HDFC Small Cap Fund Direct Growth",
    "source_url": "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
    "fetched_at": "2026-06-02T14:01:58Z",
    "extractor_version": "1.2.0",
    "extraction_health": "ok",
    "must_have_anchors": {
        "About": True,
        "Fund Details": True,
        "Minimum Investments": True,
        "Exit Load and Tax": True,
    },
    "sections": [
        {
            "name": "Meta Description",
            "source": "meta_description",
            "text": "HDFC Small Cap Fund Direct Growth - Get latest NAV.",
        },
        {
            "name": "About",
            "source": "html_section",
            "text": "About HDFC Small Cap Fund Direct Growth launched on 10 Dec 1999.",
        },
        {
            "name": "Fund Details",
            "source": "html_section",
            "text": "NAV: 01 Jun '26 ₹151.13 Expense ratio 0.73% Fund benchmark BSE 250 SmallCap Total Return Index",
        },
        {
            "name": "Minimum Investments",
            "source": "html_section",
            "text": "Min. for 1st investment ₹100 Min. for SIP ₹100",
        },
        {
            "name": "Exit Load and Tax",
            "source": "html_section",
            "text": (
                "08 May 2015 Exit load of 1% if redeemed within 1 year "
                "Exit load, stamp duty and tax Exit load Exit load of 1% if redeemed within 1 year "
                "Stamp duty on investment: 0.005% Tax implication taxed at 20%."
            ),
        },
    ],
}

SAMPLE_SHADOW = {
    "expense_ratio": "0.73%",
    "min_sip": "100",
    "exit_load": "Exit load of 1% if redeemed within 1 year",
    "benchmark": "BSE 250 SmallCap Total Return Index",
    "risk": "Very High risk",
}


class TestPhase1Chunker(unittest.TestCase):
    def test_section_to_slug(self) -> None:
        self.assertEqual(section_to_slug("Exit Load and Tax"), "exit_load_and_tax")
        self.assertEqual(section_to_slug("Fund Details"), "fund_details")

    def test_build_chunks_one_per_section(self) -> None:
        chunks = build_chunks(
            SAMPLE_CORPUS,
            run_id="20260602T140158Z",
            shadow_fields=SAMPLE_SHADOW,
        )
        self.assertEqual(len(chunks), 5)
        section_names = [c["section_name"] for c in chunks]
        self.assertEqual(
            section_names,
            [
                "Meta Description",
                "About",
                "Fund Details",
                "Minimum Investments",
                "Exit Load and Tax",
            ],
        )

    def test_atomic_sections_are_single_chunk(self) -> None:
        chunks = build_chunks(
            SAMPLE_CORPUS,
            run_id="20260602T140158Z",
            shadow_fields=SAMPLE_SHADOW,
        )
        for section_name in ATOMIC_SECTIONS:
            matches = [c for c in chunks if c["section_name"] == section_name]
            self.assertEqual(len(matches), 1)
            self.assertEqual(matches[0]["chunk_index"], 0)

    def test_chunk_record_schema(self) -> None:
        chunks = build_chunks(
            SAMPLE_CORPUS,
            run_id="20260602T140158Z",
            shadow_fields=SAMPLE_SHADOW,
        )
        fund_details = next(c for c in chunks if c["section_name"] == "Fund Details")
        self.assertEqual(
            fund_details["chunk_id"],
            "hdfc_small_cap_fund_direct_growth:20260602T140158Z:fund_details:0",
        )
        self.assertEqual(fund_details["source_url"], SAMPLE_CORPUS["source_url"])
        self.assertEqual(fund_details["fetched_at"], SAMPLE_CORPUS["fetched_at"])
        self.assertEqual(fund_details["shadow_fields"], SAMPLE_SHADOW)

    def test_health_gate_rejects_degraded_corpus(self) -> None:
        bad = dict(SAMPLE_CORPUS)
        bad["extraction_health"] = "degraded"
        with self.assertRaises(ChunkingError):
            build_chunks(bad, run_id="run", shadow_fields=SAMPLE_SHADOW)

    def test_health_gate_rejects_missing_anchor(self) -> None:
        bad = dict(SAMPLE_CORPUS)
        bad["must_have_anchors"] = dict(SAMPLE_CORPUS["must_have_anchors"])
        bad["must_have_anchors"]["Fund Details"] = False
        with self.assertRaises(ChunkingError):
            build_chunks(bad, run_id="run", shadow_fields=SAMPLE_SHADOW)

    def test_rejects_excluded_content(self) -> None:
        bad = dict(SAMPLE_CORPUS)
        bad["sections"] = list(SAMPLE_CORPUS["sections"])
        bad["sections"][2] = {
            "name": "Fund Details",
            "source": "html_section",
            "text": "Holdings (319) ICICI Bank Ltd",
        }
        with self.assertRaises(ChunkingError):
            build_chunks(bad, run_id="run", shadow_fields=SAMPLE_SHADOW)

    def test_chunk_all_latest_from_normalized_store(self) -> None:
        results = chunk_all_latest()
        self.assertEqual(len(results), 10)
        self.assertEqual(sum(r.chunk_count for r in results), 50)

        sample = Path(results[0].chunks_path)
        lines = sample.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 5)
        first = json.loads(lines[0])
        self.assertIn("chunk_id", first)
        self.assertIn("section_name", first)
        self.assertIn("shadow_fields", first)


if __name__ == "__main__":
    unittest.main()
