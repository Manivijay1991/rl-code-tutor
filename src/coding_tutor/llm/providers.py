"""Chat clients. Each returns an `LLM`: a function `(system, user, seed) -> text`.

    ollama             Ollama's /api/chat (local, default)
    openai             any OpenAI-compatible /chat/completions endpoint
                       (LM Studio, vLLM, llama.cpp server, or a hosted API with an API key)

Use `make_llm(config)` to pick by `config.provider`; pass `transport=` to replace HTTP.
"""

from __future__ import annotations

from collections.abc import Callable

from coding_tutor.llm.config import LLMConfig, auth_headers, resolved_url
from coding_tutor.llm.transport import LLMError, Transport, http_post_json

LLM = Callable[[str, str, int], str]  # (system, user, seed) -> text


def _messages(system: str, user: str) -> list[dict[str, str]]:
    """Return a system + user chat message list."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _text(reply: dict, *path: str | int) -> str:
    """Return the string at `path` in a provider reply.

    Raises:
        LLMError: The reply does not have that shape.
    """
    node: object = reply
    try:
        for key in path:
            node = node[key]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        raise LLMError(f"unexpected reply shape; expected {'/'.join(map(str, path))}") from None
    if not isinstance(node, str):
        raise LLMError("reply text is not a string")
    return node


def ollama_body(config: LLMConfig, system: str, user: str, seed: int) -> dict:
    """Return the request body for Ollama's /api/chat."""
    return {
        "model": config.model,
        "stream": False,
        "think": False,
        "messages": _messages(system, user),
        "options": {"temperature": config.temperature, "seed": seed, "num_predict": config.max_tokens},
    }


def openai_body(config: LLMConfig, system: str, user: str, seed: int) -> dict:
    """Return the request body for an OpenAI-compatible /chat/completions endpoint."""
    return {
        "model": config.model,
        "messages": _messages(system, user),
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "seed": seed,
    }


def ollama(config: LLMConfig, transport: Transport = http_post_json) -> LLM:
    """Return an LLM backed by Ollama's /api/chat."""
    url = f"{resolved_url(config)}/api/chat"

    def call(system: str, user: str, seed: int) -> str:
        reply = transport(url, ollama_body(config, system, user, seed), auth_headers(config), config.timeout)
        return _text(reply, "message", "content")

    return call


def openai_compatible(config: LLMConfig, transport: Transport = http_post_json) -> LLM:
    """Return an LLM backed by an OpenAI-compatible /chat/completions endpoint."""
    url = f"{resolved_url(config)}/chat/completions"

    def call(system: str, user: str, seed: int) -> str:
        reply = transport(url, openai_body(config, system, user, seed), auth_headers(config), config.timeout)
        return _text(reply, "choices", 0, "message", "content")

    return call


PROVIDERS: dict[str, Callable[[LLMConfig, Transport], LLM]] = {
    "ollama": ollama,
    "openai": openai_compatible,
}


def make_llm(config: LLMConfig, transport: Transport = http_post_json) -> LLM:
    """Return the LLM for `config.provider`.

    Raises:
        ValueError: Unknown provider.
    """
    if config.provider not in PROVIDERS:
        raise ValueError(f"unknown provider {config.provider!r}; one of {sorted(PROVIDERS)}")
    return PROVIDERS[config.provider](config, transport)
