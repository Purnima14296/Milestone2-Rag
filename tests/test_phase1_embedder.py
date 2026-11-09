import json
import math
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "src")

from mf_faq_assistant.phase1_ingestion.subphase_1_5_embedder.embedder import (
    EmbeddingConfig,
    EmbeddingError,
    build_embedded_text,
    build_embedding_records,
    embed_all_latest,
    embed_chunks,
    load_embedding_config,
)

SAMPLE_CHUNK = {
    "chunk_id": "hdfc_small_cap_fund_direct_growth:20260602T140158Z:fund_details:0",
    "scheme_id": "hdfc_small_cap_fund_direct_growth",
    "scheme_name": "HDFC Small Cap Fund Direct Growth",
    "source_url": "https://groww.in/mutual-funds/hdfc-small-cap-fund-direct-growth",
    "fetched_at": "2026-06-02T14:01:58Z",
    "run_id": "20260602T140158Z",
    "section_name": "Fund Details",
    "section_source": "html_section",
    "chunk_index": 0,
    "text": "NAV: 01 Jun '26 ₹151.13 Expense ratio 0.73%",
    "char_count": 45,
    "shadow_fields": {
        "expense_ratio": "0.73%",
        "min_sip": "100",
    },
}

SAMPLE_CONFIG = EmbeddingConfig(
    embedding_model_id="BAAI/bge-small-en-v1.5",
    library="sentence-transformers",
    dimensions=4,
    normalize=True,
    expected_chunks_per_scheme=5,
)


def _mock_encode(texts: list[str], config: EmbeddingConfig) -> list[list[float]]:
    vectors: list[list[float]] = []
    for index, text in enumerate(texts):
        seed = float(len(text) + index + 1)
        raw = [seed, seed / 2, seed / 3, seed / 4]
        norm = math.sqrt(sum(value * value for value in raw))
        vectors.append([value / norm for value in raw])
    return vectors


class TestPhase1Embedder(unittest.TestCase):
    def test_load_embedding_config(self) -> None:
        config = load_embedding_config()
        self.assertEqual(config.embedding_model_id, "BAAI/bge-small-en-v1.5")
        self.assertEqual(config.dimensions, 384)
        self.assertTrue(config.normalize)
        self.assertEqual(config.expected_chunks_per_scheme, 5)

    def test_build_embedded_text(self) -> None:
        text = build_embedded_text(SAMPLE_CHUNK)
        self.assertEqual(
            text,
            "HDFC Small Cap Fund Direct Growth | Fund Details: NAV: 01 Jun '26 ₹151.13 Expense ratio 0.73%",
        )

    def test_embed_chunks_produces_records(self) -> None:
        records = embed_chunks(
            [SAMPLE_CHUNK],
            config=SAMPLE_CONFIG,
            encode_fn=_mock_encode,
            embedded_at="2026-06-05T12:00:00Z",
        )
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertEqual(record["chunk_id"], SAMPLE_CHUNK["chunk_id"])
        self.assertEqual(record["embedding_model_id"], "BAAI/bge-small-en-v1.5")
        self.assertEqual(record["embedding_dimensions"], 4)
        self.assertEqual(len(record["embedding"]), 4)
        self.assertEqual(record["shadow_fields"], SAMPLE_CHUNK["shadow_fields"])
        self.assertTrue(record["embedded_text"].startswith("HDFC Small Cap Fund Direct Growth | Fund Details:"))

    def test_build_embedding_records_rejects_mismatched_counts(self) -> None:
        with self.assertRaises(EmbeddingError):
            build_embedding_records(
                [SAMPLE_CHUNK],
                [],
                config=SAMPLE_CONFIG,
                embedded_at="2026-06-05T12:00:00Z",
            )

    def test_build_embedding_records_rejects_zero_vector(self) -> None:
        with self.assertRaises(EmbeddingError):
            build_embedding_records(
                [SAMPLE_CHUNK],
                [[0.0, 0.0, 0.0, 0.0]],
                config=SAMPLE_CONFIG,
                embedded_at="2026-06-05T12:00:00Z",
            )

    def test_embed_all_latest_from_chunk_store(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            results = embed_all_latest(
                out_dir=tmp,
                config=SAMPLE_CONFIG,
                encode_fn=_mock_encode,
            )
            self.assertEqual(len(results), 10)
            self.assertEqual(sum(r.embedding_count for r in results), 50)

            sample = Path(results[0].embeddings_path)
            lines = sample.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 5)
            first = json.loads(lines[0])
            self.assertIn("embedding", first)
            self.assertIn("embedded_text", first)
            self.assertEqual(first["embedding_dimensions"], SAMPLE_CONFIG.dimensions)


if __name__ == "__main__":
    unittest.main()
