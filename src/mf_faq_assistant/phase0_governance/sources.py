from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

import yaml


class SourceConfigError(ValueError):
    pass


@dataclass(frozen=True)
class SourceItem:
    id: str
    scheme_name: str
    url: str
    enabled: bool
    tags: tuple[str, ...] = ()


@dataclass(frozen=True)
class CanonicalizationRules:
    force_https: bool = True
    strip_query: bool = True
    strip_fragment: bool = True
    normalize_trailing_slash: bool = False


def canonicalize_url(url: str, rules: CanonicalizationRules) -> str:
    s = urlsplit(url.strip())

    scheme = "https" if rules.force_https else (s.scheme or "https")
    netloc = s.netloc
    path = s.path

    if rules.normalize_trailing_slash:
        if not path.endswith("/"):
            path = f"{path}/"
    else:
        if path != "/" and path.endswith("/"):
            path = path[:-1]

    query = "" if rules.strip_query else s.query
    fragment = "" if rules.strip_fragment else s.fragment

    return urlunsplit((scheme, netloc, path, query, fragment))


@dataclass(frozen=True)
class LockedSources:
    rules: CanonicalizationRules
    sources: tuple[SourceItem, ...]
    loaded_at_utc: str

    def enabled_sources(self) -> tuple[SourceItem, ...]:
        return tuple(s for s in self.sources if s.enabled)

    def allowlisted_urls(self) -> set[str]:
        return {canonicalize_url(s.url, self.rules) for s in self.enabled_sources()}

    def is_allowed(self, url: str) -> bool:
        return canonicalize_url(url, self.rules) in self.allowlisted_urls()

    def require_allowed(self, url: str) -> str:
        canon = canonicalize_url(url, self.rules)
        if canon not in self.allowlisted_urls():
            raise SourceConfigError(f"URL not allowlisted: {canon}")
        return canon


def _require_str(d: dict[str, Any], key: str) -> str:
    v = d.get(key)
    if not isinstance(v, str) or not v.strip():
        raise SourceConfigError(f"Missing/invalid `{key}`")
    return v.strip()


def _require_bool(d: dict[str, Any], key: str) -> bool:
    v = d.get(key)
    if not isinstance(v, bool):
        raise SourceConfigError(f"Missing/invalid `{key}`")
    return v


def _coerce_tags(d: dict[str, Any]) -> tuple[str, ...]:
    v = d.get("tags", [])
    if v is None:
        return ()
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise SourceConfigError("`tags` must be a list of strings")
    return tuple(x.strip() for x in v if x.strip())


def load_locked_sources(path: str) -> LockedSources:
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise SourceConfigError("sources.yaml must be a mapping")

    canon_raw = raw.get("canonicalization", {}) or {}
    if not isinstance(canon_raw, dict):
        raise SourceConfigError("canonicalization must be a mapping")

    rules = CanonicalizationRules(
        force_https=bool(canon_raw.get("force_https", True)),
        strip_query=bool(canon_raw.get("strip_query", True)),
        strip_fragment=bool(canon_raw.get("strip_fragment", True)),
        normalize_trailing_slash=bool(canon_raw.get("normalize_trailing_slash", False)),
    )

    sources_raw = raw.get("sources")
    if not isinstance(sources_raw, list) or not sources_raw:
        raise SourceConfigError("`sources` must be a non-empty list")

    sources: list[SourceItem] = []
    for item in sources_raw:
        if not isinstance(item, dict):
            raise SourceConfigError("Each source must be a mapping")
        sources.append(
            SourceItem(
                id=_require_str(item, "id"),
                scheme_name=_require_str(item, "scheme_name"),
                url=canonicalize_url(_require_str(item, "url"), rules),
                enabled=_require_bool(item, "enabled"),
                tags=_coerce_tags(item),
            )
        )

    _validate_locked_sources(sources, rules)

    return LockedSources(
        rules=rules,
        sources=tuple(sources),
        loaded_at_utc=datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    )


def _validate_locked_sources(sources: Iterable[SourceItem], rules: CanonicalizationRules) -> None:
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()

    for s in sources:
        if s.id in seen_ids:
            raise SourceConfigError(f"Duplicate source id: {s.id}")
        seen_ids.add(s.id)

        canon_url = canonicalize_url(s.url, rules)
        if canon_url in seen_urls:
            raise SourceConfigError(f"Duplicate source url: {canon_url}")
        seen_urls.add(canon_url)

        if not canon_url.startswith("https://"):
            raise SourceConfigError(f"Non-https URL not allowed after canonicalization: {canon_url}")

