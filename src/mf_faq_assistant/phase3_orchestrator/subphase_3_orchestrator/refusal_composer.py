from __future__ import annotations

REFUSAL_MESSAGES: dict[str, str] = {
    "advice_request": (
        "I can't provide investment advice or recommendations. "
        "I can only share factual information from the current scheme sources."
    ),
    "comparison_request": (
        "I can't compare funds or say which scheme is better. "
        "I can share factual details for one scheme at a time."
    ),
    "return_projection": (
        "I can't predict or calculate future returns. "
        "I can only share factual scheme details from the current sources."
    ),
    "out_of_scope": (
        "That question is outside the locked scheme sources I can use."
    ),
}

CLARIFICATION_MESSAGE = (
    "I can help with factual scheme details, but I need to know which fund you mean. "
    "Which HDFC scheme should I look up?"
)

NOT_FOUND_MESSAGE = (
    "I'm sorry, but I wasn't able to find that in the scheme sources I have access to. "
    "Please try asking about a specific HDFC fund, or rephrase your question."
)


def compose_unsupported_scheme(fund_reference: str) -> str:
    reference = fund_reference.strip().rstrip("?.!")
    if not reference:
        return NOT_FOUND_MESSAGE
    return f"I'm sorry, but I don't have information about {reference}."


def compose_refusal(category_id: str) -> str:
    return REFUSAL_MESSAGES.get(
        category_id,
        "I can't help with that request under the facts-only scope of this assistant.",
    )


def compose_clarification() -> str:
    return CLARIFICATION_MESSAGE


def compose_not_found() -> str:
    return NOT_FOUND_MESSAGE
