"""Configured ChatGPT routes must resolve Codex credentials even from a local proxy session."""

import json

import pytest
import hermes_yaml as yaml


@pytest.fixture
def codex_config(tmp_path, monkeypatch):
    home = tmp_path / "profile"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    models = ("gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol")
    cfg = {
        "model": {
            "default": "gemma4-12b", "provider": "custom:litellm",
            "base_url": "http://proxy.example.test:4000",
        },
        "custom_providers": [{
            "name": "litellm", "base_url": "http://proxy.example.test:4000",
            "models": {"gemma4-12b": {"context_length": 65536}},
        }],
        "model_aliases": {m: {"model": m, "provider": "openai-codex"} for m in models},
    }
    (home / "config.yaml").write_text(yaml.safe_dump(cfg))
    (home / "auth.json").write_text(json.dumps({
        "version": 1,
        "providers": {"openai-codex": {"tokens": {
            "access_token": "test-profile-codex-token", "refresh_token": "test-refresh",
        }}},
    }))
    return cfg


@pytest.mark.parametrize("model", ("gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol"))
@pytest.mark.parametrize("current_provider", ("custom", "custom:litellm"))
def test_chatgpt_switch_uses_profile_codex_credential(codex_config, model, current_provider):
    from hermes_cli.model_switch import switch_model

    result = switch_model(
        model, current_provider, "gemma4-12b", codex_config["model"]["base_url"],
        "test-proxy-token", custom_providers=codex_config["custom_providers"],
    )
    assert result.success, result.error_message
    assert result.target_provider == "openai-codex"
    assert result.base_url == "https://chatgpt.com/backend-api/codex"
    assert result.api_mode == "codex_responses"
    assert result.api_key == "test-profile-codex-token"
    assert result.api_key != "test-proxy-token"


@pytest.mark.parametrize("model", ("gpt-6-luna", "gpt-6-sol", "gpt-6.1-sol"))
def test_chatgpt_startup_uses_same_configured_route(codex_config, model):
    from hermes_cli.model_switch import resolve_startup_model_route
    from hermes_cli.runtime_provider import resolve_runtime_provider

    route = resolve_startup_model_route(model, current_provider="custom:litellm")
    assert route.model == model
    assert route.provider == "openai-codex"
    runtime = resolve_runtime_provider(requested=route.provider, target_model=route.model)
    assert runtime["api_key"] == "test-profile-codex-token"
    assert runtime["base_url"] == "https://chatgpt.com/backend-api/codex"
    assert runtime["api_mode"] == "codex_responses"


def test_local_gemma_keeps_its_configured_proxy(codex_config):
    from hermes_cli.model_switch import resolve_startup_model_route
    from hermes_cli.runtime_provider import resolve_runtime_provider

    assert resolve_startup_model_route("gemma4-12b", current_provider="custom:litellm") is None
    runtime = resolve_runtime_provider(requested="custom:litellm", target_model="gemma4-12b")
    assert runtime["base_url"] == codex_config["model"]["base_url"]
    assert runtime["api_mode"] == "chat_completions"
    assert runtime["api_key"] != "test-profile-codex-token"
