"""LLM clients (Ollama, OpenAI-compatible) with injectable config, API key and transport.

    from coding_tutor.llm import LLMConfig, config_from_env, make_llm

    llm = make_llm(config_from_env(model="gemma4:12b"))
    text = llm("system prompt", "user prompt", seed=1)

The LLM only writes text (clinical notes). It never decides answers.
"""

from coding_tutor.llm.config import LLMConfig, config_from_env
from coding_tutor.llm.providers import LLM, PROVIDERS, make_llm, ollama, openai_compatible
from coding_tutor.llm.transport import LLMError, Transport, http_post_json

__all__ = [
    "LLM",
    "PROVIDERS",
    "LLMConfig",
    "LLMError",
    "Transport",
    "config_from_env",
    "http_post_json",
    "make_llm",
    "ollama",
    "openai_compatible",
]
