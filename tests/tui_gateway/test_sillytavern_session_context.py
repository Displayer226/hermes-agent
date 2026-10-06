"""SillyTavern persona contracts survive creation and runtime reconstruction."""

import logging
import threading
import types

from tui_gateway import server
from tests.tui_gateway.test_tui_gateway_server import (
    _session, _neuter_agent_prewarm_timer, _reap_leaked_notification_pollers,
)


def test_compute_host_turn_frame_carries_exact_sillytavern_context(monkeypatch):
    context = {
        "system_context": "\n  synthetic system  \n",
        "persona_context": "  synthetic persona\n",
        "persona_reminder": "\nsynthetic reminder  ",
        "persona_version": " version-1 ",
    }
    record = _session(
        agent=None, session_key="host-key", history=[], history_lock=threading.Lock(),
        cwd="/tmp", cols=80, sillytavern_context=context)
    monkeypatch.setattr(server, "_session_cwd", lambda session: "/tmp")

    frame = server._compute_host_turn_frame("rid", "sid-host", record, "hello")

    assert frame["sillytavern_context"] == context
    assert set(frame["sillytavern_context"]) == {
        "system_context", "persona_context", "persona_reminder", "persona_version"
    }


def test_compute_host_turn_frame_omits_context_for_ordinary_session(monkeypatch):
    record = _session(agent=None, session_key="ordinary-key", history=[], history_lock=threading.Lock(), cwd="/tmp")
    monkeypatch.setattr(server, "_session_cwd", lambda session: "/tmp")

    frame = server._compute_host_turn_frame("rid", "sid-ordinary", record, "hello")

    assert "sillytavern_context" not in frame


def test_session_create_records_stable_sillytavern_context(monkeypatch):
    monkeypatch.setattr(server, "_enable_gateway_prompts", lambda: None)
    monkeypatch.setattr(server, "_start_agent_build", lambda *a, **k: None)
    try:
        resp = server._methods["session.create"](
            "r1",
            {
                "source": "sillytavern",
                "messages": [
                    {"role": "user", "content": "Earlier question"},
                    {"role": "assistant", "content": "Earlier answer"},
                ],
                "system_context": "\n  response contract  \n",
                "persona_context": "  # ARIA\n",
                "persona_reminder": "\nAnswer as ARIA.  ",
                "persona_version": " persona-v1 ",
            },
        )
        session = server._sessions[resp["result"]["session_id"]]
        assert [{"role": m["role"], "content": m["content"]} for m in session["history"]] == [
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
        ]
        assert session["sillytavern_context"] == {
            "system_context": "\n  response contract  \n",
            "persona_context": "  # ARIA\n",
            "persona_reminder": "\nAnswer as ARIA.  ",
            "persona_version": " persona-v1 ",
        }
    finally:
        server._sessions.clear()


def test_session_create_contract_accepts_sillytavern_context(monkeypatch):
    """JSON-RPC validation accepts bridge context but still rejects unknown fields."""
    monkeypatch.setattr(server, "_enable_gateway_prompts", lambda: None)
    monkeypatch.setattr(server, "_start_agent_build", lambda *a, **k: None)
    context = {
        "system_context": "response contract",
        "persona_context": "# ARIA",
        "persona_reminder": "Answer as ARIA.",
        "persona_version": "persona-v1",
    }
    try:
        response = server.handle_request(
            {"id": "contract-create", "method": "session.create", "params": context}
        )
        assert response is not None
        assert "error" not in response
        session = server._sessions[response["result"]["session_id"]]
        assert session["sillytavern_context"] == context

        rejected = server.handle_request(
            {
                "id": "contract-unknown",
                "method": "session.create",
                "params": {"unknown_sillytavern_field": "nope"},
            }
        )
        assert rejected is not None
        assert rejected["error"]["code"] == 4000
    finally:
        server._sessions.clear()


def test_make_agent_combines_sillytavern_context_with_config_prompt(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("run_agent.AIAgent", FakeAgent)
    monkeypatch.setattr(server, "_load_cfg", lambda: {"agent": {}})
    monkeypatch.setattr(
        "hermes_cli.config.resolve_ephemeral_system_prompt_from_config",
        lambda _cfg: "configured prompt",
    )
    monkeypatch.setattr(server, "_resolve_startup_runtime", lambda: ("model", "provider"))
    monkeypatch.setattr(
        server,
        "_resolve_runtime_with_fallback",
        lambda _kwargs: server._RuntimeFallbackResolution(
            {"provider": "provider", "base_url": "http://example", "api_key": "key"},
            None,
            False,
        ),
    )
    monkeypatch.setattr(server, "_get_db", lambda: None)

    server._make_agent(
        "sid",
        "key",
        sillytavern_context={
            "system_context": "\n  response contract  \n",
            "persona_context": "  # ARIA\n",
            "persona_reminder": "\nAnswer as ARIA.  ",
            "persona_version": " persona-v1 ",
        },
    )

    assert captured["ephemeral_system_prompt"] == (
        "configured prompt\n\n"
        "[SillyTavern bridge context]\n\n  response contract  \n\n\n"
        "[SillyTavern combined character and user context]\n  # ARIA\n\n\n"
        "[SillyTavern persona reminder]\n\nAnswer as ARIA.  "
    )
    assert " persona-v1 " not in captured["ephemeral_system_prompt"]


def test_make_agent_ignores_non_string_sillytavern_context(monkeypatch, caplog):
    captured = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("run_agent.AIAgent", FakeAgent)
    monkeypatch.setattr(server, "_load_cfg", lambda: {"agent": {}})
    monkeypatch.setattr(
        "hermes_cli.config.resolve_ephemeral_system_prompt_from_config",
        lambda _cfg: "configured prompt",
    )
    monkeypatch.setattr(server, "_resolve_startup_runtime", lambda: ("model", "provider"))
    monkeypatch.setattr(
        server,
        "_resolve_runtime_with_fallback",
        lambda _kwargs: server._RuntimeFallbackResolution(
            {"provider": "provider", "base_url": "http://example", "api_key": "key"},
            None,
            False,
        ),
    )
    monkeypatch.setattr(server, "_get_db", lambda: None)
    invalid_list = ["synthetic-list-value"]
    invalid_dict = {"version": "synthetic-dict-value"}

    with caplog.at_level(logging.DEBUG):
        server._make_agent(
            "sid",
            "key",
            sillytavern_context={
                "system_context": invalid_list,
                "persona_context": "  valid persona\n",
                "persona_reminder": "\nvalid reminder  ",
                "persona_version": invalid_dict,
            },
        )

    prompt = captured["ephemeral_system_prompt"]
    assert "synthetic-list-value" not in prompt
    assert "synthetic-dict-value" not in prompt
    assert "  valid persona\n" in prompt
    assert "\nvalid reminder  " in prompt
    assert "synthetic-list-value" not in caplog.text
    assert "synthetic-dict-value" not in caplog.text


def test_rebuild_session_agent_preserves_sillytavern_context_without_prompt_version(monkeypatch):
    captured = {}
    context = {
        "system_context": "\n  synthetic system  \n",
        "persona_context": "  synthetic persona\n",
        "persona_reminder": "\nsynthetic reminder  ",
        "persona_version": " version-1 ",
    }
    new_agent = types.SimpleNamespace(model="test")
    session = _session(agent=types.SimpleNamespace(), sillytavern_context=context)

    def make_agent(*_args, **kwargs):
        captured.update(kwargs)
        return new_agent

    monkeypatch.setattr(server, "_make_agent", make_agent)
    monkeypatch.setattr(server, "_config_model_target", lambda: ("", ""))
    monkeypatch.setattr(server, "_transfer_db_to_agent", lambda *_args: False)

    server._rebuild_session_agent("sid", session, session_id=session["session_key"])

    assert captured["sillytavern_context"] == {
        "system_context": "\n  synthetic system  \n",
        "persona_context": "  synthetic persona\n",
        "persona_reminder": "\nsynthetic reminder  ",
    }
    assert session["sillytavern_context"] == context
    assert " version-1 " not in str(captured["sillytavern_context"])


def test_rebuild_session_agent_without_sillytavern_context_keeps_ordinary_kwargs(monkeypatch):
    captured = {}
    session = _session(agent=types.SimpleNamespace())

    def make_agent(*_args, **kwargs):
        captured.update(kwargs)
        return types.SimpleNamespace(model="test")

    monkeypatch.setattr(server, "_make_agent", make_agent)
    monkeypatch.setattr(server, "_config_model_target", lambda: ("", ""))
    monkeypatch.setattr(server, "_transfer_db_to_agent", lambda *_args: False)

    server._rebuild_session_agent("sid", session, session_id=session["session_key"])

    assert "sillytavern_context" not in captured
