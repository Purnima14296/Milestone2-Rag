from __future__ import annotations

import re
from dataclasses import dataclass

WHITESPACE_PATTERN = re.compile(r"\s+")
GENERAL_MARKET_PRICE = re.compile(
    r"\b(stock|share|market|live|spot)\s+price\b",
    re.IGNORECASE,
)
COMMODITY_PRICE_WITHOUT_MF = re.compile(
    r"\b(price\s+of|what\s+is\s+the\s+price\s+of)\s+(gold|silver)\b"
    r"|\b(gold|silver)\s+price\b",
    re.IGNORECASE,
)
MF_CONTEXT = re.compile(
    r"\b(hdfc|mutual\s+fund|scheme|nav|sip|fof|etf\s+fund|direct\s+growth)\b",
    re.IGNORECASE,
)

MF_TERM_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    (r"\bmidcap\b", "mid cap"),
    (r"\bsmallcap\b", "small cap"),
    (r"\bmulticap\b", "multi cap"),
    (r"\bfof\b", "fof"),
    (r"\betf\b", "etf"),
    (r"\bter\b", "expense ratio"),
    (r"\bmin\.?\b", "minimum"),
    (r"\bprice\b", "nav price"),
    (r"\bquote\b", "nav"),
    (r"\bvalue\b", "nav value"),
)

RETRIEVAL_EXPANSIONS: tuple[tuple[str, str], ...] = (
    (r"\bnav\b", "latest nav fund nav scheme nav"),
    (r"\bprice\b", "nav current price value quote"),
    (r"\breturns?\b", "returns performance cagr historical return"),
    (r"\baum\b", "fund size aum asset under management"),
)


@dataclass(frozen=True)
class NormalizedQuery:
    raw: str
    normalized: str


def _should_map_price_to_nav(text: str) -> bool:
    if GENERAL_MARKET_PRICE.search(text):
        return False
    if COMMODITY_PRICE_WITHOUT_MF.search(text) and not MF_CONTEXT.search(text):
        return False
    return True


def normalize_query(query: str) -> NormalizedQuery:
    raw = query.strip()
    text = raw.lower()
    text = WHITESPACE_PATTERN.sub(" ", text)

    for pattern, replacement in MF_TERM_REPLACEMENTS:
        if pattern == r"\bprice\b" and not _should_map_price_to_nav(text):
            continue
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    text = text.replace("₹", "₹").strip()
    return NormalizedQuery(raw=raw, normalized=text)


def expand_query_for_retrieval(normalized: str) -> str:
    expanded = normalized
    extras: list[str] = []
    for pattern, addition in RETRIEVAL_EXPANSIONS:
        if re.search(pattern, normalized, re.IGNORECASE):
            extras.append(addition)
    if extras:
        expanded = f"{normalized} {' '.join(extras)}"
    return expanded.strip()
