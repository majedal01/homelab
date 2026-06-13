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


def test_model_catalog_drives_allowlist_and_defaults() -> None:
    """The allow-list and per-provider defaults are derived from the catalog,
    so the picker, validation, and defaults can't drift apart."""
    from app.llm import ALLOWED_MODELS, DEFAULT_MODEL_FOR_PROVIDER, MODEL_CATALOG

    for provider, options in MODEL_CATALOG.items():
        assert ALLOWED_MODELS[provider] == frozenset(o.value for o in options)
        # The first catalog entry is the preselected default.
        assert DEFAULT_MODEL_FOR_PROVIDER[provider] == options[0].value

    # Current Anthropic lineup: Opus 4.8 is in; the retired 4.7 is gone.
    assert "claude-opus-4-8" in ALLOWED_MODELS["anthropic"]
    assert "claude-opus-4-7" not in ALLOWED_MODELS["anthropic"]
    assert DEFAULT_MODEL_FOR_PROVIDER["anthropic"] == "claude-haiku-4-5-20251001"
