from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = "config/llm.yaml"
_ENV_LOADED = False


class LlmConfigError(ValueError):
    pass


@dataclass(frozen=True)
class LlmConfig:
    provider: str
    model_id: str
    temperature: float
    max_tokens: int
    api_key_env: str
    fallback_to_templates: bool

    def api_key(self) -> str | None:
        value = os.environ.get(self.api_key_env, "").strip()
        return value or None


def _load_env_file() -> None:
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass
    _ENV_LOADED = True


def load_llm_config(path: str | Path = DEFAULT_CONFIG_PATH) -> LlmConfig:
    _load_env_file()
    config_path = Path(path)
    if not config_path.exists():
        raise LlmConfigError(f"LLM config not found: {config_path}")

    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    if not isinstance(raw, dict):
        raise LlmConfigError(f"Invalid LLM config: {config_path}")

    provider = str(raw.get("provider", "groq")).lower()
    if provider not in ("groq", "template"):
        raise LlmConfigError(f"Unsupported LLM provider: {provider}")

    return LlmConfig(
        provider=provider,
        model_id=str(raw.get("model_id", "llama-3.3-70b-versatile")),
        temperature=float(raw.get("temperature", 0)),
        max_tokens=int(raw.get("max_tokens", 256)),
        api_key_env=str(raw.get("api_key_env", "GROQ_API_KEY")),
        fallback_to_templates=bool(raw.get("fallback_to_templates", True)),
    )
