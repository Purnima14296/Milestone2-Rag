from __future__ import annotations

from dataclasses import dataclass

from mf_faq_assistant.phase0_governance.pii import detect_pii

PII_BLOCK_MESSAGE = (
    "Please do not share personal information such as PAN, Aadhaar, bank account numbers, "
    "OTPs, email addresses, or phone numbers. I can only answer factual questions about "
    "the locked HDFC mutual fund schemes."
)


@dataclass(frozen=True)
class PiiGuardResult:
    blocked: bool
    kinds: tuple[str, ...]


def check_pii(message: str) -> PiiGuardResult:
    findings = detect_pii(message)
    if not findings:
        return PiiGuardResult(blocked=False, kinds=())
    return PiiGuardResult(
        blocked=True,
        kinds=tuple(sorted({finding.kind for finding in findings})),
    )
