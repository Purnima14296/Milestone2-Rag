from __future__ import annotations

import re
from typing import Any

from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.faq_builder import (
    _extract_about_facts,
    _extract_exit_load_and_tax,
    _extract_minimum_investments,
    _extract_objective_and_benchmark,
    _extract_scheme_summary,
)
from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.html_sections import (
    extract_meta_description,
)

EXTRACTOR_VERSION = "1.2.0"

MUST_HAVE_ANCHOR_NAMES = (
    "About",
    "Fund Details",
    "Minimum Investments",
    "Exit Load and Tax",
)


def _dedupe_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    for line in lines:
        if deduped and deduped[-1].lower() == line.lower():
            continue
        deduped.append(line)
    return deduped


def _lines_to_text(lines: list[str]) -> str:
    return " ".join(_dedupe_lines(lines))


def _pair_label_values(lines: list[str]) -> str:
    parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i + 1 < len(lines):
            nxt = lines[i + 1]
            if nxt.startswith("₹") or re.fullmatch(r"[\d.]+%", nxt):
                parts.append(f"{line} {nxt}")
                i += 2
                continue
        parts.append(line)
        i += 1
    return " ".join(parts)


def _extract_about_full(lines: list[str]) -> str:
    start = None
    for i, line in enumerate(lines):
        if line.startswith("About "):
            start = i
            break
    if start is None:
        facts = _extract_about_facts(lines)
        return _lines_to_text(facts)

    block: list[str] = []
    for i in range(start, len(lines)):
        if re.match(r"^Investment Objective$", lines[i], re.IGNORECASE):
            break
        block.append(lines[i])
    text = " ".join(block)
    return re.sub(r"\.\.\.Read more", "", text, flags=re.IGNORECASE).strip()


def _prepare_lines(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    from mf_faq_assistant.phase1_ingestion.subphase_1_3_cleaner_normalizer.faq_builder import (
        FOOTER_STOP,
        _matches_any,
    )

    for i, line in enumerate(lines):
        if _matches_any(line, FOOTER_STOP):
            return lines[:i]
    return lines


def _section(name: str, source: str, text: str) -> dict[str, str]:
    return {"name": name, "source": source, "text": text.strip()}


def build_corpus_document(
    *,
    scheme_id: str,
    scheme_name: str,
    source_url: str,
    fetched_at: str,
    extracted_text: str,
    raw_html: str,
) -> dict[str, Any]:
    lines = _prepare_lines(extracted_text)

    fund_details_lines = _dedupe_lines(_extract_scheme_summary(lines))
    objective_lines = _dedupe_lines(_extract_objective_and_benchmark(lines))
    if objective_lines:
        fund_details_lines.extend(objective_lines)

    min_lines = _extract_minimum_investments(lines)
    if min_lines and min_lines[0].lower() == "minimum investments":
        min_lines = min_lines[1:]

    sections: list[dict[str, str]] = []

    meta_description = extract_meta_description(raw_html)
    if meta_description:
        sections.append(_section("Meta Description", "meta_description", meta_description))

    about_text = _extract_about_full(lines)
    if about_text:
        sections.append(_section("About", "html_section", about_text))

    if fund_details_lines:
        sections.append(_section("Fund Details", "html_section", _pair_label_values(fund_details_lines)))

    if min_lines:
        sections.append(
            _section("Minimum Investments", "html_section", _pair_label_values(min_lines))
        )

    exit_lines = _dedupe_lines(_extract_exit_load_and_tax(lines))
    if exit_lines:
        sections.append(_section("Exit Load and Tax", "html_section", _lines_to_text(exit_lines)))

    present = {s["name"] for s in sections}
    must_have_anchors = {name: name in present for name in MUST_HAVE_ANCHOR_NAMES}

    missing_required = [name for name in MUST_HAVE_ANCHOR_NAMES if not must_have_anchors[name]]
    extraction_health = "ok" if not missing_required else "degraded"

    return {
        "scheme_id": scheme_id,
        "scheme_name": scheme_name,
        "source_url": source_url,
        "fetched_at": fetched_at,
        "extractor_version": EXTRACTOR_VERSION,
        "extraction_health": extraction_health,
        "must_have_anchors": must_have_anchors,
        "sections": sections,
    }


def corpus_to_plaintext(corpus: dict[str, Any]) -> str:
    parts: list[str] = []
    parts.append(f"Scheme: {corpus.get('scheme_name', '')}")
    parts.append(f"Source: {corpus.get('source_url', '')}")
    parts.append("")
    for section in corpus.get("sections", []):
        parts.append(f"## {section.get('name', '')}")
        parts.append(str(section.get("text", "")))
        parts.append("")
    return "\n".join(parts).strip()
