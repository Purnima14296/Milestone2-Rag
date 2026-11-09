import sys
import unittest

sys.path.insert(0, "src")

from fastapi.testclient import TestClient

from mf_faq_assistant.phase4_ui.subphase_4_backend.app import create_app


class TestPhase4Api(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._client_cm = TestClient(create_app())
        cls.client = cls._client_cm.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls._client_cm.__exit__(None, None, None)

    def test_metrics(self) -> None:
        response = self.client.get("/metrics")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("total_requests", data)
        self.assertIn("reason_counts", data)
        self.assertIn("latency_ms", data)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn(data["status"], {"ok", "degraded"})
        self.assertTrue(data["index_ready"])
        self.assertEqual(data["scheme_count"], 10)
        self.assertEqual(data["document_count"], 50)

    def test_ui_config(self) -> None:
        response = self.client.get("/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Facts-only", data["disclaimer"])
        self.assertEqual(len(data["example_questions"]), 3)

    def test_list_schemes(self) -> None:
        response = self.client.get("/schemes")
        self.assertEqual(response.status_code, 200)
        schemes = response.json()["schemes"]
        self.assertEqual(len(schemes), 10)
        self.assertTrue(all("id" in scheme and "scheme_name" in scheme for scheme in schemes))

    def test_chat_factual_answer(self) -> None:
        response = self.client.post(
            "/chat",
            json={"message": "Min SIP for HDFC Small Cap Fund Direct Growth"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["refusal"])
        self.assertIsNone(data["reason"])
        self.assertIsNotNone(data["citation_url"])
        self.assertIn("groww.in", data["citation_url"])
        self.assertIn("₹100", data["answer_text"])

    def test_chat_needs_clarification_has_no_url(self) -> None:
        response = self.client.post("/chat", json={"message": "What is the expense ratio?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["reason"], "needs_clarification")
        self.assertIsNone(data["citation_url"])

    def test_chat_refusal_has_no_url(self) -> None:
        response = self.client.post(
            "/chat",
            json={"message": "Should I invest in HDFC Mid Cap?"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["refusal"])
        self.assertIsNone(data["citation_url"])

    def test_chat_invalid_selected_scheme(self) -> None:
        response = self.client.post(
            "/chat",
            json={"message": "exit load", "selected_scheme": "not_a_real_scheme"},
        )
        self.assertEqual(response.status_code, 400)

    def test_chat_with_selected_scheme(self) -> None:
        response = self.client.post(
            "/chat",
            json={
                "message": "exit load",
                "selected_scheme": "hdfc_nifty_50_index_fund_direct_growth",
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIsNone(data["reason"])
        self.assertIn("nifty-50", data["citation_url"])

    def test_frontend_index_served_when_built(self) -> None:
        response = self.client.get("/")
        if response.status_code == 200 and "text/html" in response.headers.get("content-type", ""):
            self.assertIn("Mutual Fund FAQ Assistant", response.text)
        else:
            self.skipTest("frontend/dist not built")


if __name__ == "__main__":
    unittest.main()
