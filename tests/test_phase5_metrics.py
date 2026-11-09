import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, "src")

from mf_faq_assistant.phase3_orchestrator.subphase_3_orchestrator.orchestrator import ChatResponse
from mf_faq_assistant.phase5_eval_observability.config_loader import ObservabilityConfig
from mf_faq_assistant.phase5_eval_observability.metrics_store import build_dashboard_snapshot
from mf_faq_assistant.phase5_eval_observability.structured_logger import (
    build_observability_context,
    hash_message,
    log_chat_event,
)


class TestPhase5Metrics(unittest.TestCase):
    def test_hash_message_is_stable(self) -> None:
        self.assertEqual(hash_message("hello"), hash_message("hello"))
        self.assertNotEqual(hash_message("hello"), hash_message("world"))

    def test_structured_log_updates_dashboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            events_path = Path(tmp) / "events.jsonl"
            metrics_path = Path(tmp) / "metrics.json"
            cfg = ObservabilityConfig(
                observability_version="1.0.0",
                enabled=True,
                events_path=str(events_path),
                metrics_path=str(metrics_path),
                log_raw_message=False,
            )
            response = ChatResponse(
                answer_text="I'm sorry, but I wasn't able to find that in the scheme sources I have access to.",
                citation_url=None,
                last_updated_date=None,
                refusal=False,
                reason="not_found",
            )
            context = build_observability_context(
                "stock price of gold?",
                intent="out_of_scope",
                latency_ms=12.5,
            )
            log_chat_event(response, context, config=cfg)

            snapshot = build_dashboard_snapshot(config=cfg)
            self.assertEqual(snapshot.total_requests, 1)
            self.assertEqual(snapshot.reason_counts.get("not_found"), 1)
            self.assertTrue(metrics_path.exists())


if __name__ == "__main__":
    unittest.main()
