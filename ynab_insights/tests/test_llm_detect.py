"""Provider detection from key prefix."""

from __future__ import annotations

from app.llm import detect_provider


def test_anthropic_keys_detected() -> None:
    assert detect_provider("sk-ant-api03-" + "x" * 40) == "anthropic"
    assert detect_provider("sk-ant-" + "y" * 30) == "anthropic"


def test_openai_keys_detected() -> None:
    # Classic
    assert detect_provider("sk-" + "a" * 32) == "openai"
    # Project-scoped
    assert detect_provider("sk-proj-" + "b" * 40) == "openai"


def test_unknown_keys_return_none() -> None:
    assert detect_provider("") is None
    assert detect_provider("not-a-key") is None
    assert detect_provider("abcdefghij") is None
    # Too short to be either
    assert detect_provider("sk-ant-short") is None
    assert detect_provider("sk-short") is None


def test_anthropic_checked_before_openai() -> None:
    # `sk-ant-...` would also match the looser OpenAI regex; detector must
    # prefer Anthropic so the keys route to the right SDK.
    assert detect_provider("sk-ant-" + "x" * 25) == "anthropic"
