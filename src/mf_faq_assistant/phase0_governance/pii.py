from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


@dataclass(frozen=True)
class PiiFinding:
    kind: str
    match: str
    start: int
    end: int


_PAN = re.compile(r"\b[A-Z]{5}[0-9]{4}[A-Z]\b")
_AADHAAR = re.compile(r"\b\d{4}\s?\d{4}\s?\d{4}\b")
_EMAIL = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
_PHONE = re.compile(r"\b(?:\+?91[\s-]?)?[6-9]\d{9}\b")
_ACCOUNT_LIKE = re.compile(r"\b\d{9,18}\b")
_OTP_HINTED = re.compile(r"\b(?:otp|one[\s-]?time[\s-]?password)\D{0,10}(\d{4,8})\b", re.IGNORECASE)


def detect_pii(text: str) -> list[PiiFinding]:
    findings: list[PiiFinding] = []
    if not text:
        return findings

    def add(kind: str, m: re.Match[str]) -> None:
        findings.append(PiiFinding(kind=kind, match=m.group(0), start=m.start(), end=m.end()))

    for m in _PAN.finditer(text):
        add("pan", m)
    for m in _AADHAAR.finditer(text):
        add("aadhaar", m)
    for m in _EMAIL.finditer(text):
        add("email", m)
    for m in _PHONE.finditer(text):
        add("phone", m)
    for m in _OTP_HINTED.finditer(text):
        # group(0) includes the hint + digits; redact the whole match for safety
        add("otp", m)

    # Account numbers are tricky; treat as "account_like" unless they look like Aadhaar (already captured).
    for m in _ACCOUNT_LIKE.finditer(text):
        if _AADHAAR.fullmatch(m.group(0)):
            continue
        add("account_like", m)

    return sorted(findings, key=lambda f: (f.start, f.end))


def redact_pii(text: str, findings: Iterable[PiiFinding] | None = None) -> tuple[str, list[PiiFinding]]:
    if findings is None:
        findings_list = detect_pii(text)
    else:
        findings_list = list(findings)

    if not findings_list:
        return text, []

    # Replace from left to right using spans to avoid shifting indices.
    out: list[str] = []
    last = 0
    for f in sorted(findings_list, key=lambda x: x.start):
        out.append(text[last : f.start])
        out.append(f"[REDACTED:{f.kind}]")
        last = f.end
    out.append(text[last:])

    return "".join(out), findings_list

