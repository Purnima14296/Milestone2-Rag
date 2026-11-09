from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from mf_faq_assistant.phase0_governance.refusal import RefusalTaxonomy, classify_refusal


class Intent(str, Enum):
    FACTUAL = "factual"
    REFUSAL = "refusal"


@dataclass(frozen=True)
class IntentResult:
    intent: Intent
    refusal_category: str | None


def classify_intent(message: str, taxonomy: RefusalTaxonomy) -> IntentResult:
    refusal_category = classify_refusal(message, taxonomy)
    if refusal_category:
        return IntentResult(intent=Intent.REFUSAL, refusal_category=refusal_category)
    return IntentResult(intent=Intent.FACTUAL, refusal_category=None)
