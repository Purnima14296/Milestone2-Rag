from __future__ import annotations

import re

from mf_faq_assistant.phase0_governance.sources import SourceItem
from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import _tokenize

GENERAL_MARKET_PRICE = re.compile(
    r"\b(stock|share|market|live|spot)\s+price\b",
    re.IGNORECASE,
)
COMMODITY_PRICE = re.compile(
    r"\b(price\s+of|current\s+price\s+of|what\s+is\s+the\s+price\s+of)\s+(gold|silver|oil|crude)\b"
    r"|\b(gold|silver|oil|crude)\s+price\b",
    re.IGNORECASE,
)
MF_CONTEXT = re.compile(
    r"\b("
    r"hdfc|mutual\s+fund|scheme|nav|aum|sip|expense|ratio|exit\s+load|"
    r"benchmark|fund\s+manager|minimum|investment|direct\s+growth|fof|etf\s+fund"
    r")\b",
    re.IGNORECASE,
)

SUPPORTED_AMC_TOKENS = frozenset({"hdfc"})

UNSUPPORTED_AMC_TOKENS = frozenset(
    {
        "icici",
        "sbi",
        "axis",
        "kotak",
        "nippon",
        "mirae",
        "parag",
        "uti",
        "dsp",
        "bandhan",
        "motilal",
        "quant",
        "invesco",
        "franklin",
        "tata",
        "aditya",
        "birla",
        "bajaj",
        "edelweiss",
        "pgim",
        "hsbc",
        "baroda",
        "lic",
        "samco",
        "ppfas",
        "canara",
        "robeco",
        "jm",
        "mahindra",
        "boi",
        "union",
        "trust",
        "iti",
        "groww",
        "zerodha",
    }
)

TAG_ONLY_TOKENS = frozenset(
    {
        "gold",
        "silver",
        "pharma",
        "healthcare",
        "defence",
        "defense",
        "thematic",
        "sectoral",
        "commodity",
        "hybrid",
        "index",
        "equity",
    }
)

GENERIC_SCHEME_TOKENS = frozenset(
    {
        "mid",
        "cap",
        "small",
        "multi",
        "nifty",
        "equity",
        "balanced",
        "pharma",
        "healthcare",
        "defence",
        "defense",
        "gold",
        "silver",
        "index",
        "hybrid",
        "thematic",
        "sectoral",
        "commodity",
        "fof",
        "etf",
    }
)


def has_mutual_fund_context(query: str) -> bool:
    return bool(MF_CONTEXT.search(query))


def is_out_of_scope_query(query: str) -> bool:
    if GENERAL_MARKET_PRICE.search(query):
        return True
    if COMMODITY_PRICE.search(query) and not has_mutual_fund_context(query):
        return True
    return False


def _normalize_match_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _format_fund_reference(reference: str) -> str:
    cleaned = reference.strip().rstrip("?.!")
    tokens = cleaned.split()
    if not tokens:
        return cleaned
    tokens[0] = tokens[0].upper()
    return " ".join(tokens)


def extract_unsupported_fund_reference(query: str) -> str | None:
    q_norm = _normalize_match_text(query)
    q_tokens = set(_tokenize(q_norm))

    if q_tokens & SUPPORTED_AMC_TOKENS:
        return None

    for amc in sorted(UNSUPPORTED_AMC_TOKENS, key=len, reverse=True):
        if amc not in q_tokens:
            continue
        pattern = re.compile(rf"\b{re.escape(amc)}\b", re.IGNORECASE)
        match = pattern.search(query)
        if not match:
            continue
        reference = query[match.start() :].strip().rstrip("?.!")
        return _format_fund_reference(reference)

    return None


def scheme_explicitly_in_query(query: str, source: SourceItem) -> bool:
    if extract_unsupported_fund_reference(query):
        return False

    q_norm = _normalize_match_text(query)
    name_norm = _normalize_match_text(source.scheme_name)
    q_tokens = set(_tokenize(q_norm))
    name_tokens = set(_tokenize(name_norm))

    suffix = frozenset({"hdfc", "fund", "direct", "growth", "plan", "and", "etf", "fof", "of"})
    distinctive = (name_tokens | set(_tokenize(source.id.replace("_", " ")))) - suffix

    if name_norm and name_norm in q_norm:
        return True

    overlap = q_tokens & distinctive
    if overlap and overlap.issubset(GENERIC_SCHEME_TOKENS) and "hdfc" not in q_tokens:
        return False

    if len(overlap) >= 2:
        return True

    if "hdfc" in q_tokens and overlap:
        return True

    if len(overlap) == 1:
        token = next(iter(overlap))
        if token in TAG_ONLY_TOKENS:
            return False
        return "hdfc" in q_tokens or len(q_tokens & name_tokens) >= 2

    return False
