from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = "config/api.yaml"


class ApiConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ApiConfig:
    api_version: str
    host: str
    port: int
    sources_path: str
    index_active_dir: str
    cors_origins: tuple[str, ...]
    welcome_message: str
    disclaimer: str
    example_questions: tuple[str, ...]


def load_api_config(path: str | Path = DEFAULT_CONFIG_PATH) -> ApiConfig:
    config_path = Path(path)
    if not config_path.exists():
        raise ApiConfigError(f"API config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise ApiConfigError(f"Invalid API config: {config_path}")

    origins = raw.get("cors_origins", [])
    if not isinstance(origins, list):
        raise ApiConfigError("cors_origins must be a list")

    examples = raw.get("example_questions", [])
    if not isinstance(examples, list):
        raise ApiConfigError("example_questions must be a list")

    return ApiConfig(
        api_version=str(raw.get("api_version", "1.0.0")),
        host=str(raw.get("host", "127.0.0.1")),
        port=int(raw.get("port", 8000)),
        sources_path=str(raw.get("sources_path", "config/sources.yaml")),
        index_active_dir=str(raw.get("index_active_dir", "data/index/active")),
        cors_origins=tuple(str(origin) for origin in origins),
        welcome_message=str(raw.get("welcome_message", "")),
        disclaimer=str(raw.get("disclaimer", "Facts-only. No investment advice.")),
        example_questions=tuple(str(q) for q in examples),
    )
