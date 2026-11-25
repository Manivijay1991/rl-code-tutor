import pytest

from coding_tutor.llm.config import LLMConfig, auth_headers, config_from_env, resolved_url


def test_defaults():
    cfg = config_from_env({})
    assert (cfg.provider, cfg.model, cfg.base_url, cfg.api_key) == ("ollama", "gemma4:12b", None, None)


def test_reads_environment():
    env = {
        "CODING_TUTOR_LLM_PROVIDER": "openai",
        "CODING_TUTOR_LLM_MODEL": "m",
        "CODING_TUTOR_LLM_URL": "http://h/v1",
        "CODING_TUTOR_LLM_API_KEY": "k",
        "CODING_TUTOR_LLM_TEMPERATURE": "0.2",
        "CODING_TUTOR_LLM_TIMEOUT": "30",
    }
    cfg = config_from_env(env)
    assert cfg == LLMConfig("openai", "m", "http://h/v1", "k", temperature=0.2, timeout=30)


def test_overrides_win_and_none_is_ignored():
    cfg = config_from_env({"CODING_TUTOR_LLM_MODEL": "env"}, model="flag", base_url=None)
    assert cfg.model == "flag" and cfg.base_url is None


def test_empty_variables_count_as_unset():
    assert config_from_env({"CODING_TUTOR_LLM_API_KEY": ""}).api_key is None


def test_bad_number():
    with pytest.raises(ValueError):
        config_from_env({"CODING_TUTOR_LLM_TIMEOUT": "soon"})


def test_unknown_override_field():
    with pytest.raises(TypeError):
        config_from_env({}, colour="blue")


def test_api_key_hidden_from_repr():
    assert "sk-secret" not in repr(LLMConfig(api_key="sk-secret"))


def test_config_is_immutable():
    with pytest.raises(AttributeError):
        LLMConfig().model = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("cfg", "url"),
    [
        (LLMConfig(), "http://localhost:11434"),
        (LLMConfig(provider="openai"), "http://localhost:8000/v1"),
        (LLMConfig(base_url="http://gpu:11434/"), "http://gpu:11434"),
    ],
)
def test_resolved_url(cfg, url):
    assert resolved_url(cfg) == url


def test_resolved_url_unknown_provider():
    with pytest.raises(ValueError, match="no base_url"):
        resolved_url(LLMConfig(provider="other"))


def test_auth_headers():
    assert auth_headers(LLMConfig()) == {}
    assert auth_headers(LLMConfig(api_key="k")) == {"Authorization": "Bearer k"}
