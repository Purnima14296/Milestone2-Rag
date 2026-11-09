import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "src")

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import (
    CorpusIndex,
    IndexingError,
    build_index,
    build_keyword_index,
    index_all_latest,
    load_index_config,
    load_latest_embedding_records,
)

SAMPLE_RECORD = {
    "chunk_id": "hdfc_small_cap_fund_direct_growth:run:fund_details:0",
    "scheme_id": "hdfc_small_cap_fund_direct_growth",
    "scheme_name": "HDFC Small Cap Fund Direct Growth",
    "source_url": "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
    "fetched_at": "2026-06-02T14:01:58Z",
    "run_id": "run",
    "section_name": "Fund Details",
    "embedded_text": "HDFC Small Cap Fund Direct Growth | Fund Details: Expense ratio 0.73%",
    "embedding_model_id": "BAAI/bge-small-en-v1.5",
    "embedding": [0.1, 0.2, 0.3, 0.4],
    "shadow_fields": {
        "expense_ratio": "0.73%",
        "min_sip": "100",
    },
}


class TestPhase1Indexer(unittest.TestCase):
    def test_load_index_config(self) -> None:
        config = load_index_config()
        self.assertEqual(config.expected_schemes, 10)
        self.assertEqual(config.expected_embeddings, 50)
        self.assertEqual(config.vector_store, "chromadb")

    def test_build_keyword_index_contains_field_terms(self) -> None:
        keyword_index = build_keyword_index([SAMPLE_RECORD])
        self.assertIn("expense", keyword_index["terms"])
        self.assertIn("0.73%", keyword_index["terms"])
        self.assertIn("expense_ratio", keyword_index["fields"])

    def test_build_index_rejects_wrong_count(self) -> None:
        config = load_index_config()
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(IndexingError):
                build_index([SAMPLE_RECORD], staging_dir=Path(tmp) / "staging", config=config)

    def test_index_all_latest_builds_active_index(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        try:
            result = index_all_latest(index_root=tmp)
            self.assertEqual(result.document_count, 50)
            self.assertEqual(result.scheme_count, 10)
            active = Path(result.active_dir)
            self.assertTrue((active / "meta.json").exists())
            self.assertTrue((active / "chroma").exists())
            self.assertTrue((active / "keyword_index.json").exists())
            self.assertTrue((active / "documents.jsonl").exists())

            keyword_index = json.loads((active / "keyword_index.json").read_text(encoding="utf-8"))
            self.assertIn("expense", keyword_index["terms"])
            self.assertIn("expense_ratio", keyword_index["fields"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_corpus_index_keyword_search_on_active_index(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        try:
            result = index_all_latest(index_root=tmp)
            corpus = CorpusIndex(result.active_dir)
            try:
                keyword_hits = corpus.search_keyword("expense ratio HDFC Small Cap")
                self.assertTrue(keyword_hits)
                self.assertIn("Fund Details", {hit.section_name for hit in keyword_hits})
            finally:
                corpus.close()
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_load_latest_embedding_records(self) -> None:
        records = load_latest_embedding_records()
        self.assertEqual(len(records), 50)
        self.assertEqual(len(records[0]["embedding"]), 384)


if __name__ == "__main__":
    unittest.main()
