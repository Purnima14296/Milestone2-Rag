from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import yaml


class RefusalConfigError(ValueError):
    pass


@dataclass(frozen=True)
class RefusalCategory:
    id: str
    patterns: tuple[str, ...]


@dataclass(frozen=True)
class RefusalTaxonomy:
    categories: tuple[RefusalCategory, ...]
    link_policy_mode: str

    def match(self, message: str) -> str | None:
        q = (message or "").lower()
        for c in self.categories:
            for p in c.patterns:
                if p and p.lower() in q:
                    return c.id
        return None


def load_refusal_taxonomy(path: str) -> RefusalTaxonomy:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise RefusalConfigError("refusal_taxonomy.yaml must be a mapping")

    cats_raw = raw.get("refusal_categories")
    if not isinstance(cats_raw, list):
        raise RefusalConfigError("`refusal_categories` must be a list")

    cats: list[RefusalCategory] = []
    for item in cats_raw:
        if not isinstance(item, dict):
            raise RefusalConfigError("Each refusal category must be a mapping")
        cid = item.get("id")
        if not isinstance(cid, str) or not cid.strip():
            raise RefusalConfigError("Category id missing/invalid")
        patterns = item.get("patterns", [])
        if patterns is None:
            patterns = []
        if not isinstance(patterns, list) or not all(isinstance(p, str) for p in patterns):
            raise RefusalConfigError(f"Patterns for {cid} must be a list of strings")
        cats.append(RefusalCategory(id=cid.strip(), patterns=tuple(p.strip() for p in patterns if p.strip())))

    link_policy = raw.get("link_policy", {})
    if not isinstance(link_policy, dict):
        raise RefusalConfigError("`link_policy` must be a mapping")
    mode = link_policy.get("mode", "contract_a_strict")
    if mode not in ("contract_a_strict", "contract_b_split"):
        raise RefusalConfigError("link_policy.mode must be `contract_a_strict` or `contract_b_split`")

    _validate_unique_ids(cats)
    return RefusalTaxonomy(categories=tuple(cats), link_policy_mode=mode)


def _validate_unique_ids(categories: list[RefusalCategory]) -> None:
    seen: set[str] = set()
    for c in categories:
        if c.id in seen:
            raise RefusalConfigError(f"Duplicate refusal category id: {c.id}")
        seen.add(c.id)


def classify_refusal(message: str, taxonomy: RefusalTaxonomy) -> str | None:
    return taxonomy.match(message)

