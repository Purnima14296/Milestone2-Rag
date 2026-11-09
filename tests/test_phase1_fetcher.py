import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, "src")

from mf_faq_assistant.phase0_governance.sources import load_locked_sources
from mf_faq_assistant.phase1_ingestion.subphase_1_1_fetcher.fetcher import FetchError, fetch_all


class TestPhase1Fetcher(unittest.TestCase):
    def test_blocks_non_allowlisted_redirect(self) -> None:
        locked = load_locked_sources("config/sources.yaml")

        # Mock response that redirects to a non-allowlisted URL.
        resp = Mock()
        resp.url = "https://example.com/not-allowed"
        resp.status_code = 200
        resp.headers = {"content-type": "text/html"}
        resp.content = b"<html>ok</html>"

        session = Mock()
        session.get.return_value = resp
        session.headers = {}

        with patch(
            "mf_faq_assistant.phase1_ingestion.subphase_1_1_fetcher.fetcher.requests.Session",
            return_value=session,
        ):
            with self.assertRaises(FetchError):
                fetch_all(locked, sources=[locked.enabled_sources()[0]], out_dir="data/test_raw")

    def test_rejects_blocked_status(self) -> None:
        locked = load_locked_sources("config/sources.yaml")
        s = locked.enabled_sources()[0]

        resp = Mock()
        resp.url = s.url
        resp.status_code = 403
        resp.headers = {"content-type": "text/html"}
        resp.content = b"Access denied"

        session = Mock()
        session.get.return_value = resp
        session.headers = {}

        with patch(
            "mf_faq_assistant.phase1_ingestion.subphase_1_1_fetcher.fetcher.requests.Session",
            return_value=session,
        ):
            with self.assertRaises(FetchError):
                fetch_all(locked, sources=[s], out_dir="data/test_raw", max_retries=0)


if __name__ == "__main__":
    unittest.main()

