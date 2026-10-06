"""Model-only proxy session creation must use configured routes rather than the profile endpoint."""

import json

import pytest
import yaml

from tui_gateway.methods_session_model_guard import create_overrides

from tui_gateway import server


@pytest.fixture
def profile(tmp_path, monkeypatch):
    home = tmp_path / "profile"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    cfg = {
        "model": {"default": "gemma4-12b", "provider": "custom:litellm",
                  "base_url": "http://proxy.example.test:4000"},
        "custom_providers": [{"name": "litellm", "base_url": "http://proxy.example.test:4000",
                              "models": {"gemma4-12b": {"context_length": 65536}}}],
        "model_aliases": {m: {"model": m, "provider": "openai-codex"}
                          for m in ("gpt-6-luna", "gpt-6.1-sol")},
    }
    (home / "config.yaml").write_text(yaml.safe_dump(cfg))
    (home / "auth.json").write_text(json.dumps({"version": 1, "providers": {
        "openai-codex": {"tokens": {"access_token": "profile-codex-token",
                                     "refresh_token": "profile-refresh"}},
    }}))
    return cfg


@pytest.mark.parametrize("model", ("gpt-6-luna", "gpt-6.1-sol"))
def test_proxy_session_create_model_reaches_codex(profile, model):
    # Exact shape produced by the proxy's session.create({model: ...}) request.
    override, _, _ = create_overrides({"model": model})
    assert override["provider"] is None
    selected, runtime = server._resolve_agent_model_runtime(override, None)
    assert selected == model
    assert runtime["provider"] == "openai-codex"
    assert runtime["base_url"] == "https://chatgpt.com/backend-api/codex"
    assert runtime["api_mode"] == "codex_responses"
    assert runtime["api_key"] == "profile-codex-token"


def test_string_model_override_also_uses_alias(profile):
    model, runtime = server._resolve_agent_model_runtime("gpt-6-luna", None)
    assert model == "gpt-6-luna"
    assert runtime["provider"] == "openai-codex"


def test_unpinned_alias_drops_stale_endpoint_and_credential(profile):
    override = {"model": "gpt-6-luna", "provider": None,
                "base_url": profile["model"]["base_url"], "api_key": "proxy-token",
                "api_mode": "chat_completions"}
    model, runtime = server._resolve_agent_model_runtime(override, None)
    assert model == "gpt-6-luna"
    assert runtime["api_key"] == "profile-codex-token"
    assert runtime["base_url"] != override["base_url"]
    assert runtime["api_mode"] == "codex_responses"
    assert override["api_key"] == "proxy-token"  # no mutation of the caller's session pin


def test_local_model_only_session_keeps_profile_endpoint(profile):
    override, _, _ = create_overrides({"model": "gemma4-12b"})
    model, runtime = server._resolve_agent_model_runtime(override, None)
    assert model == "gemma4-12b"
    assert runtime["base_url"] == profile["model"]["base_url"]
    assert runtime["api_mode"] == "chat_completions"


@pytest.mark.parametrize("pin_source", ("model", "provider_override"))
def test_explicit_provider_remains_authoritative(profile, pin_source):
    from tui_gateway.model_startup import resolve_session_model_alias

    override = {"model": "gpt-6-luna", "base_url": "https://chosen.example.test/v1"}
    if pin_source == "model":
        override["provider"] = "custom:chosen"
    provider_override = "custom:chosen" if pin_source == "provider_override" else None
    assert resolve_session_model_alias(override, provider_override) is override
