import pytest

from coding_tutor.llm import LLMConfig, LLMError, make_llm, ollama, openai_compatible


def recording(reply):
    """A fake transport that records the request and returns `reply`."""
    calls = []

    def transport(url, body, headers, timeout):
        calls.append({"url": url, "body": body, "headers": headers, "timeout": timeout})
        return reply

    return transport, calls


def test_ollama_request_and_reply():
    transport, calls = recording({"message": {"content": "note"}})
    llm = ollama(LLMConfig(model="m", temperature=0.1, max_tokens=50, timeout=9), transport)
    assert llm("sys", "user", 7) == "note"
    (c,) = calls
    assert c["url"] == "http://localhost:11434/api/chat" and c["timeout"] == 9
    assert c["body"]["model"] == "m" and c["body"]["stream"] is False
    assert c["body"]["options"] == {"temperature": 0.1, "seed": 7, "num_predict": 50}
    assert [m["role"] for m in c["body"]["messages"]] == ["system", "user"]
    assert c["headers"] == {}


def test_openai_request_and_reply():
    transport, calls = recording({"choices": [{"message": {"content": "note"}}]})
    llm = openai_compatible(LLMConfig(provider="openai", model="m", base_url="http://h/v1/", api_key="k"), transport)
    assert llm("sys", "user", 3) == "note"
    (c,) = calls
    assert c["url"] == "http://h/v1/chat/completions"
    assert c["body"]["seed"] == 3 and c["body"]["max_tokens"] == 700
    assert c["headers"] == {"Authorization": "Bearer k"}


def test_api_key_sent_to_ollama_too():
    transport, calls = recording({"message": {"content": "x"}})
    ollama(LLMConfig(api_key="k"), transport)("s", "u", 0)
    assert calls[0]["headers"] == {"Authorization": "Bearer k"}


@pytest.mark.parametrize(
    ("factory", "reply"),
    [
        (ollama, {}),
        (ollama, {"message": {"content": None}}),
        (openai_compatible, {"choices": []}),
        (openai_compatible, {"error": "bad key"}),
    ],
    ids=["ollama_missing", "ollama_not_text", "openai_no_choices", "openai_error"],
)
def test_unexpected_replies_raise(factory, reply):
    transport, _ = recording(reply)
    with pytest.raises(LLMError):
        factory(LLMConfig(provider="openai" if factory is openai_compatible else "ollama"), transport)("s", "u", 0)


def test_make_llm_picks_provider():
    transport, calls = recording({"choices": [{"message": {"content": "ok"}}]})
    assert make_llm(LLMConfig(provider="openai"), transport)("s", "u", 0) == "ok"
    assert calls[0]["url"].endswith("/chat/completions")


def test_make_llm_unknown_provider():
    with pytest.raises(ValueError, match="unknown provider"):
        make_llm(LLMConfig(provider="carrier-pigeon"))
