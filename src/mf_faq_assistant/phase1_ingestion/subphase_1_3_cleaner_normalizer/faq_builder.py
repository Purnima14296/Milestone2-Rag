from __future__ import annotations

import re


SKIP_SECTION_START = (
    re.compile(r"^Return calculator$", re.IGNORECASE),
    re.compile(r"^Holdings\s*\(", re.IGNORECASE),
    re.compile(r"^Understand terms$", re.IGNORECASE),
    re.compile(r"^Returns and rankings$", re.IGNORECASE),
    re.compile(r"^Compare similar funds$", re.IGNORECASE),
    re.compile(r"^Fund management$", re.IGNORECASE),
    re.compile(r"^Also manages these schemes$", re.IGNORECASE),
    re.compile(r"^Fund house$", re.IGNORECASE),
)

FOOTER_STOP = (
    re.compile(r"^Terms and Conditions$", re.IGNORECASE),
    re.compile(r"^Mutual Funds:$", re.IGNORECASE),
    re.compile(r"^Stocks:$", re.IGNORECASE),
    re.compile(r"^NSE$", re.IGNORECASE),
    re.compile(r"^Show More$", re.IGNORECASE),
)

RESUME_SECTIONS = (
    re.compile(r"^Minimum investments$", re.IGNORECASE),
    re.compile(r"^Exit load, stamp duty and tax$", re.IGNORECASE),
    re.compile(r"^Investment Objective$", re.IGNORECASE),
    re.compile(r"^About .+", re.IGNORECASE),
)

HEADER_NOISE = (
    re.compile(r"^(All|1M|6M|1Y|3Y|5Y|10Y)$", re.IGNORECASE),
    re.compile(r"^Rating$", re.IGNORECASE),
    re.compile(r"^Return calculator$", re.IGNORECASE),
)

DATE_LINE = re.compile(r"^\d{2} [A-Za-z]{3} \d{4}$")
EXIT_LOAD_RULE = re.compile(r"exit load", re.IGNORECASE)
LOCK_IN = re.compile(r"lock[- ]?in", re.IGNORECASE)


def _find_line(lines: list[str], pattern: re.Pattern[str], start: int = 0) -> int | None:
    for i in range(start, len(lines)):
        if pattern.search(lines[i]):
            return i
    return None


def _matches_any(line: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(p.search(line) for p in patterns)


def _extract_scheme_summary(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _matches_any(line, SKIP_SECTION_START):
            break
        if _matches_any(line, HEADER_NOISE):
            i += 1
            continue

        if re.match(r"^NAV:", line, re.IGNORECASE):
            out.append(line)
            if i + 1 < len(lines) and lines[i + 1].startswith("₹"):
                out.append(lines[i + 1])
                i += 1
        elif re.match(r"^Min\. for SIP$", line, re.IGNORECASE):
            out.append(line)
            if i + 1 < len(lines):
                out.append(lines[i + 1])
                i += 1
        elif re.match(r"^Expense ratio$", line, re.IGNORECASE):
            out.append(line)
            if i + 1 < len(lines):
                out.append(lines[i + 1])
                i += 1
        elif re.match(r"^Fund size \(AUM\)$", line, re.IGNORECASE):
            out.append(line)
            if i + 1 < len(lines):
                out.append(lines[i + 1])
                i += 1
        elif re.search(r"\brisk\b", line, re.IGNORECASE) and len(line) < 80:
            out.append(line)
        i += 1
    return out


def _extract_minimum_investments(lines: list[str]) -> list[str]:
    start = _find_line(lines, re.compile(r"^Minimum investments$", re.IGNORECASE))
    if start is None:
        return []
    end = _find_line(lines, re.compile(r"^Understand terms$", re.IGNORECASE), start + 1)
    if end is None:
        end = len(lines)
    return lines[start:end]


def _extract_exit_load_and_tax(lines: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(lines):
        if DATE_LINE.match(lines[i]) and i + 1 < len(lines) and EXIT_LOAD_RULE.search(lines[i + 1]):
            out.extend([lines[i], lines[i + 1]])
            i += 2
            continue

        if re.match(r"^Exit load, stamp duty and tax$", lines[i], re.IGNORECASE):
            j = i
            while j < len(lines):
                if re.match(r"^(Check past data|Compare similar funds|Fund management)$", lines[j], re.IGNORECASE):
                    break
                out.append(lines[j])
                j += 1
            break
        i += 1
    return out


def _extract_objective_and_benchmark(lines: list[str]) -> list[str]:
    start = _find_line(lines, re.compile(r"^Investment Objective$", re.IGNORECASE))
    if start is None:
        return []
    out: list[str] = []
    i = start
    while i < len(lines):
        line = lines[i]
        if re.match(r"^(Scheme Information Document|Fund house|Compare|Fund management)$", line, re.IGNORECASE):
            break
        if re.match(r"^Scheme Information Document", line, re.IGNORECASE):
            break
        out.append(line)
        i += 1
    return out


def _extract_about_facts(lines: list[str]) -> list[str]:
    start = _find_line(lines, re.compile(r"^About .+", re.IGNORECASE))
    if start is None:
        return []

    block: list[str] = []
    i = start
    while i < len(lines):
        if re.match(r"^Investment Objective$", lines[i], re.IGNORECASE):
            break
        block.append(lines[i])
        i += 1

    text = " ".join(block)
    text = re.sub(r"\.\.\.Read more", "", text, flags=re.IGNORECASE)
    facts: list[str] = []

    patterns = (
        (re.compile(r"rated ([^.]+risk)", re.IGNORECASE), "Risk classification"),
        (re.compile(r"Minimum SIP Investment is set to ([^.]+)", re.IGNORECASE), "Minimum SIP"),
        (re.compile(r"Minimum Lumpsum Investment is set to ([^.]+)", re.IGNORECASE), "Minimum lumpsum"),
        (re.compile(r"(Exit [Ll]oad[^.]+\.)", re.IGNORECASE), None),
        (re.compile(r"(ELSS lock[- ]?in[^.]+\.)", re.IGNORECASE), None),
        (re.compile(r"((?:Very )?(?:High|Moderate|Low)[^\.]*risk[^.]+\.)", re.IGNORECASE), None),
    )
    for pattern, label in patterns:
        match = pattern.search(text)
        if match:
            value = match.group(1).strip()
            facts.append(f"{label}: {value}" if label else value)

    if not facts:
        return []
    return ["About (facts)"] + facts


def _extract_lock_in(lines: list[str]) -> list[str]:
    out: list[str] = []
    for line in lines:
        if LOCK_IN.search(line) and len(line) < 200:
            out.append(line)
    return out[:3]


def build_faq_document(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    # Stop processing at site footer.
    for i, line in enumerate(lines):
        if _matches_any(line, FOOTER_STOP):
            lines = lines[:i]
            break

    sections: list[tuple[str, list[str]]] = [
        ("Scheme summary", _extract_scheme_summary(lines)),
        ("Minimum investments", _extract_minimum_investments(lines)),
        ("Exit load, stamp duty and tax", _extract_exit_load_and_tax(lines)),
        ("Investment objective and benchmark", _extract_objective_and_benchmark(lines)),
        ("About facts", _extract_about_facts(lines)),
        ("Lock-in", _extract_lock_in(lines)),
    ]

    parts: list[str] = []
    for title, content in sections:
        if not content:
            continue
        deduped: list[str] = []
        for line in content:
            if deduped and deduped[-1].lower() == line.lower():
                continue
            deduped.append(line)
        parts.append(f"## {title}")
        parts.extend(deduped)
        parts.append("")

    return "\n".join(parts).strip()
