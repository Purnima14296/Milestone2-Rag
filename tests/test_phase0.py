import sys
import unittest

sys.path.insert(0, "src")

from mf_faq_assistant.phase0_governance.pii import detect_pii, redact_pii
from mf_faq_assistant.phase0_governance.refusal import load_refusal_taxonomy
from mf_faq_assistant.phase0_governance.sources import load_locked_sources


class TestPhase0Sources(unittest.TestCase):
    def test_load_sources_has_exactly_10_enabled(self) -> None:
        sources = load_locked_sources("config/sources.yaml")
        self.assertEqual(len(sources.enabled_sources()), 10)

    def test_allowlist_rejects_non_allowlisted(self) -> None:
        sources = load_locked_sources("config/sources.yaml")
        self.assertFalse(sources.is_allowed("https://example.com/not-allowed"))


class TestPhase0Pii(unittest.TestCase):
    def test_detects_pan(self) -> None:
        findings = detect_pii("my PAN is ABCDE1234F")
        self.assertTrue(any(f.kind == "pan" for f in findings))

    def test_redacts_email(self) -> None:
        redacted, findings = redact_pii("contact me at test@example.com")
        self.assertTrue(findings)
        self.assertIn("[REDACTED:email]", redacted)


class TestPhase0Refusal(unittest.TestCase):
    def test_taxonomy_loads(self) -> None:
        taxonomy = load_refusal_taxonomy("config/refusal_taxonomy.yaml")
        self.assertIn(taxonomy.link_policy_mode, ("contract_a_strict", "contract_b_split"))


if __name__ == "__main__":
    unittest.main()

