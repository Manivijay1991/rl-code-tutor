"""LLM settings: provider, model, endpoint and API key.

Build a config in code (`LLMConfig(...)`), or from the environment with `config_from_env()`:

    CODING_TUTOR_LLM_PROVIDER   ollama (default) | openai
    CODING_TUTOR_LLM_MODEL      default: gemma4:12b
    CODING_TUTOR_LLM_URL        default: the provider's local URL
    CODING_TUTOR_LLM_API_KEY    optional; sent as a Bearer token

The API key is excluded from repr() and never written to logs, errors or scenario files.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

ENV_PREFIX = "CODING_TUTOR_LLM_"
DEFAULT_PROVIDER = "ollama"
DEFAULT_MODEL = "gemma4:12b"
DEFAULT_URLS = {"ollama": "http://localhost:11434", "openai": "http://localhost:8000/v1"}


@dataclass(frozen=True)
class LLMConfig:
    """Settings for one chat model. Plain data; the key is hidden from repr()."""

    provider: str = DEFAULT_PROVIDER
    model: str = DEFAULT_MODEL
    base_url: str | None = None  # None = the provider's default local URL
    api_key: str | None = field(default=None, repr=False)
    temperature: float = 0.8
    max_tokens: int = 700
    timeout: int = 300


def resolved_url(config: LLMConfig) -> str:
    """Return the base URL without a trailing slash, falling back to the provider default.

    Raises:
        ValueError: No URL is set and the provider has no default.
    """
    url = config.base_url or DEFAULT_URLS.get(config.provider)
    if not url:
        raise ValueError(f"no base_url for provider {config.provider!r}")
    return url.rstrip("/")


def auth_headers(config: LLMConfig) -> dict[str, str]:
    """Return the Authorization header when an API key is set, else nothing."""
    return {"Authorization": f"Bearer {config.api_key}"} if config.api_key else {}


def config_from_env(env: Mapping[str, str] | None = None, **overrides: object) -> LLMConfig:
    """Build a config from CODING_TUTOR_LLM_* variables, then apply non-None `overrides`.

    Args:
        env: Variables to read; defaults to os.environ (injectable for tests).
        **overrides: LLMConfig fields (e.g. model="llama3.1:8b"); None values are ignored.

    Raises:
        ValueError: A numeric variable is not a number.
    """
    env = os.environ if env is None else env

    def get(name: str) -> str | None:
        return env.get(ENV_PREFIX + name) or None

    base = LLMConfig(
        provider=get("PROVIDER") or DEFAULT_PROVIDER,
        model=get("MODEL") or DEFAULT_MODEL,
        base_url=get("URL"),
        api_key=get("API_KEY"),
    )
    if get("TEMPERATURE"):
        base = replace(base, temperature=float(get("TEMPERATURE")))
    if get("TIMEOUT"):
        base = replace(base, timeout=int(get("TIMEOUT")))
    return replace(base, **{k: v for k, v in overrides.items() if v is not None})
