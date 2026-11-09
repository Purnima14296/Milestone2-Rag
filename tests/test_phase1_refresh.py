import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, "src")

from mf_faq_assistant.phase1_ingestion.subphase_1_7_refresh_health.refresh import (
    RefreshError,
    load_refresh_config,
    run_refresh_pipeline,
    validate_active_index,
    validate_corpus_health,
    write_refresh_report,
)


class TestPhase1Refresh(unittest.TestCase):
    def test_load_refresh_config(self) -> None:
        config = load_refresh_config()
        self.assertEqual(config.expected_schemes, 10)
        self.assertEqual(config.expected_index_documents, 50)
        self.assertEqual(config.expected_chunks_per_scheme, 5)

    def test_validate_corpus_health_on_existing_data(self) -> None:
        rows = validate_corpus_health()
        self.assertEqual(len(rows), 10)
        self.assertTrue(all(row.raw_ok for row in rows))
        self.assertTrue(all(row.normalized_ok for row in rows))
        self.assertTrue(all(row.chunks_ok for row in rows))
        self.assertTrue(all(row.embeddings_ok for row in rows))
        self.assertFalse(any(row.errors for row in rows))

    def test_validate_active_index_on_existing_data(self) -> None:
        meta = validate_active_index()
        self.assertEqual(meta["document_count"], 50)
        self.assertEqual(meta["scheme_count"], 10)
        self.assertEqual(meta["status"], "ok")

    def test_write_refresh_report(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.json"
            out = write_refresh_report({"status": "ok", "scheme_count": 10}, path)
            self.assertTrue(Path(out).exists())
            data = json.loads(Path(out).read_text(encoding="utf-8"))
            self.assertEqual(data["status"], "ok")

    def test_run_refresh_pipeline_skip_fetch(self) -> None:
        tmp = Path(tempfile.mkdtemp())
        try:
            report_path = tmp / "refresh_report.json"
            index_root = tmp / "index"

            def _index_to_temp() -> object:
                from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import (
                    index_all_latest,
                )

                return index_all_latest(index_root=index_root)

            with patch(
                "mf_faq_assistant.phase1_ingestion.subphase_1_7_refresh_health.refresh.index_all_latest",
                side_effect=_index_to_temp,
            ):
                result = run_refresh_pipeline(skip_fetch=True, report_path=report_path)
            self.assertEqual(result.status, "ok")
            self.assertEqual(result.scheme_count, 10)
            self.assertEqual(result.indexed_documents, 50)
            self.assertTrue(Path(result.report_path).exists())
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_validate_corpus_health_fails_for_missing_scheme(self) -> None:
        with patch(
            "mf_faq_assistant.phase1_ingestion.subphase_1_7_refresh_health.refresh._latest_run_dir",
            return_value=None,
        ):
            rows = validate_corpus_health()
            self.assertTrue(any(row.errors for row in rows))


if __name__ == "__main__":
    unittest.main()
