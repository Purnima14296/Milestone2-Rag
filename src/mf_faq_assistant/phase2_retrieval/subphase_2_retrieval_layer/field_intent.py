from __future__ import annotations

from dataclasses import dataclass

from mf_faq_assistant.phase1_ingestion.subphase_1_6_indexer.indexer import FIELD_ALIASES, _tokenize

FIELD_SECTION_MAP: dict[str, tuple[str, ...]] = {
    "expense_ratio": ("Fund Details",),
    "min_sip": ("Minimum Investments", "Fund Details"),
    "exit_load": ("Exit Load and Tax",),
    "benchmark": ("Fund Details",),
    "risk": ("Fund Details", "About"),
    "lock_in": ("Fund Details", "About"),
}

EXTRA_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "nav": ("nav", "net asset value", "price", "quote"),
    "aum": ("aum", "fund size"),
    "manager": ("manager", "fund manager"),
    "tax": ("tax", "stamp", "duty", "ltcg", "stcg", "capital gains"),
}

EXTRA_FIELD_SECTIONS: dict[str, tuple[str, ...]] = {
    "nav": ("Fund Details", "About"),
    "aum": ("Fund Details", "About"),
    "manager": ("About",),
    "tax": ("Exit Load and Tax",),
}

# Checked before FIELD_ALIASES so explicit nav/aum/manager/tax beats incidental tokens
# (e.g. "index" inside "Index Fund" must not override a NAV question).
PRIORITY_FIELD_SPECS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("nav", EXTRA_FIELD_ALIASES["nav"], EXTRA_FIELD_SECTIONS["nav"]),
    ("aum", EXTRA_FIELD_ALIASES["aum"], EXTRA_FIELD_SECTIONS["aum"]),
    ("manager", EXTRA_FIELD_ALIASES["manager"], EXTRA_FIELD_SECTIONS["manager"]),
    ("tax", EXTRA_FIELD_ALIASES["tax"], EXTRA_FIELD_SECTIONS["tax"]),
)

STANDARD_FIELD_SPECS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = tuple(
    (field, aliases, FIELD_SECTION_MAP.get(field, ("Fund Details",)))
    for field, aliases in FIELD_ALIASES.items()
)


@dataclass(frozen=True)
class FieldIntent:
    field: str
    preferred_sections: tuple[str, ...]
    matched_aliases: tuple[str, ...]


def _aliases_in_query(query: str, aliases: tuple[str, ...]) -> list[str]:
    tokens = set(_tokenize(query))
    matched: list[str] = []
    for alias in aliases:
        alias_tokens = _tokenize(alias)
        if len(alias_tokens) == 1:
            if alias_tokens[0] in tokens:
                matched.append(alias)
        elif all(token in tokens for token in alias_tokens):
            matched.append(alias)
        elif alias in query:
            matched.append(alias)
    return matched


def _alias_position(query: str, alias: str) -> int:
    lowered = query.lower()
    alias_lower = alias.lower()
    if alias_lower in lowered:
        return lowered.index(alias_lower)
    first_token = _tokenize(alias_lower)
    if first_token:
        token = first_token[0]
        if token in lowered.split():
            return lowered.index(token)
    return 10**9


def detect_field_intents(query: str) -> tuple[FieldIntent, ...]:
    candidates: list[tuple[int, str, FieldIntent]] = []

    for field, aliases, sections in (*PRIORITY_FIELD_SPECS, *STANDARD_FIELD_SPECS):
        matched = _aliases_in_query(query, aliases)
        if not matched:
            continue
        position = min(_alias_position(query, alias) for alias in matched)
        candidates.append(
            (
                position,
                field,
                FieldIntent(
                    field=field,
                    preferred_sections=sections,
                    matched_aliases=tuple(matched),
                ),
            )
        )

    candidates.sort(key=lambda item: (item[0], item[1]))
    ordered: list[FieldIntent] = []
    seen: set[str] = set()
    for _, field, intent in candidates:
        if field in seen:
            continue
        seen.add(field)
        ordered.append(intent)
    return tuple(ordered)


def detect_field_intent(query: str) -> FieldIntent | None:
    intents = detect_field_intents(query)
    return intents[0] if intents else None


def preferred_sections_for_field(field: str) -> tuple[str, ...] | None:
    return FIELD_SECTION_MAP.get(field) or EXTRA_FIELD_SECTIONS.get(field)


def field_requires_scheme(field: FieldIntent | None) -> bool:
    return field is not None
