"""Bridge context survives deferred construction and compute-host transport."""
import threading
import io
from contextlib import ExitStack
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from tui_gateway import server
from tui_gateway.contracts.sessions import SessionCreateParams
from tui_gateway.compute_host import ComputeHost
from tui_gateway.bridge_context import prompt


def test_bridge_context_contract_and_deferred_frame():
    context = {"system_context": "character", "persona_context": "user persona",
               "persona_reminder": "remember user", "persona_version": "version-only"}
    assert SessionCreateParams.model_validate(context).model_dump(exclude_unset=True) == context
    session = {"session_key": "key", "history": [{"role": "user", "content": "previous"}],
               "history_lock": threading.Lock(), "bridge_context": context}
    assert server._deferred_build_agent_kwargs(session, None)["bridge_context"] == context
    frame = server._compute_host_turn_frame("request", "sid", session, "current")
    assert frame["bridge_context"] == context
    assert frame["history"] == session["history"]
    assert frame["text"] == "current"


def test_model_only_alias_uses_startup_route_without_old_pins(monkeypatch):
    from hermes_cli import model_switch
    monkeypatch.setattr(server, "_load_cfg", lambda: {"model": {"provider": "old"}})
    monkeypatch.setattr(model_switch, "resolve_startup_model_route", lambda *a, **kw:
                        SimpleNamespace(model="resolved", provider="new", base_url="", api_key=""))
    calls = []
    monkeypatch.setattr(server, "_resolve_runtime_with_fallback", lambda kw:
                        calls.append(kw) or SimpleNamespace(used_fallback=False, runtime={"provider": "new"}))
    model, runtime = server._resolve_agent_model_runtime({"model": "alias"}, None)
    assert model == "resolved"
    assert calls[0]["requested"] == "new"
    assert runtime == {"provider": "new"}


def test_model_route_preserves_explicit_provider_and_saved_runtime(monkeypatch):
    from hermes_cli import model_switch
    monkeypatch.setattr(model_switch, "resolve_startup_model_route", lambda *a, **kw:
                        (_ for _ in ()).throw(AssertionError("pinned route must not be resolved as an alias")))
    monkeypatch.setattr(server, "_resolve_runtime_with_fallback", lambda kw:
                        SimpleNamespace(used_fallback=False, runtime={"provider": kw["requested"]}))
    monkeypatch.setattr(server, "_rederive_per_model_route", lambda *args: None)
    model, runtime = server._resolve_agent_model_runtime(
        {"model": "chosen", "provider": "pinned", "base_url": "https://pinned.invalid", "api_key": "synthetic"}, None)
    assert model == "chosen"
    assert runtime == {"provider": "pinned", "base_url": "https://pinned.invalid", "api_key": "synthetic"}


def test_model_alias_is_resolved_before_create_conflict_check(monkeypatch):
    from hermes_cli import model_switch
    monkeypatch.setattr(model_switch, "DIRECT_ALIASES", {"gpt-5.5": model_switch.DirectAlias("custom-model", "custom", "https://alias.invalid")})
    monkeypatch.setattr("hermes_cli.runtime_provider.resolve_requested_provider", lambda: "anthropic")
    monkeypatch.setattr(server, "_sessions", {})
    monkeypatch.setattr(server, "_profile_home", lambda *a: None)
    monkeypatch.setattr(server, "_load_cfg", lambda: {"model": {"provider": "anthropic"}})
    monkeypatch.setattr(server, "_enable_gateway_prompts", lambda: None)
    monkeypatch.setattr(server, "_schedule_agent_build", lambda *a: None)
    monkeypatch.setattr(server, "_schedule_session_cap_enforcement", lambda: None)
    monkeypatch.setattr(server, "_register_session_cwd", lambda *a: None)
    monkeypatch.setattr(server, "_project_info_for_cwd", lambda *a: None)
    response = server.handle_request({"id": "create", "method": "session.create", "params": {"model": "gpt-5.5"}})
    assert "result" in response, response


def test_compute_build_adoption_and_rebuild(monkeypatch):
    host = ComputeHost(stdout=io.StringIO(), heartbeat_secs=0)
    captured = []
    monkeypatch.setattr(server, "_make_agent", lambda *a, **kw:
                        captured.append(kw) or SimpleNamespace(session_id="key"))
    monkeypatch.setattr(server, "_transfer_db_to_agent", lambda *a: False)
    monkeypatch.setattr(server, "_init_session", lambda sid, key, agent, history, **kw:
                        monkeypatch.setitem(server._sessions, sid, {"agent": agent, "session_key": key}))
    monkeypatch.setattr(server, "_config_model_target", lambda: ("", ""))
    context = {"system_context": "character", "persona_context": "user", "persona_version": "secret-version"}
    frame = {"sid": "bridge-context-test", "session_key": "key", "bridge_context": context}
    try:
        session = host._ensure_server_session(server, frame)
        assert captured[0]["bridge_context"] == context
        assert session["bridge_context"] == context
        host._ensure_server_session(server, frame)
        assert len(captured) == 1
        host._ensure_server_session(server, {"sid": frame["sid"]})
        assert session["bridge_context"] == context
        host._ensure_server_session(server, {**frame, "bridge_context": {}})
        assert len(captured) == 1
        assert session["bridge_context"] == {}
        server._rebuild_session_agent(frame["sid"], session)
        assert not captured[-1].get("bridge_context")
        assert prompt("base", context) == "base\n\ncharacter\n\nuser"
        assert prompt("base", {"persona_version": "secret-version"}) == "base"
    finally:
        server._sessions.pop(frame["sid"], None)
        host.close()


def test_create_preserves_seed_and_context(monkeypatch, tmp_path):
    from hermes_state import SessionDB
    db = SessionDB(db_path=tmp_path / "state.db")
    monkeypatch.setattr(server, "_get_db", lambda: db)
    monkeypatch.setattr(server, "_schedule_agent_build", lambda sid: None)
    monkeypatch.setattr(server, "_schedule_session_cap_enforcement", lambda: None)
    monkeypatch.setattr(server, "_register_session_cwd", lambda session: None)
    result = server.handle_request({"id": "create", "method": "session.create", "params": {
        "messages": [{"role": "user", "content": "previous"}], "system_context": "character",
        "persona_version": "version"}})
    assert "result" in result, result
    sid = result["result"]["session_id"]
    try:
        session = server._sessions[sid]
        assert session["bridge_context"] == {"system_context": "character", "persona_version": "version"}
        assert [entry["content"] for entry in session["history"]] == ["previous"]
        assert [entry["content"] for entry in db.get_messages_as_conversation(session["session_key"])] == ["previous"]
    finally:
        server._sessions.pop(sid, None)
        db.close()


def test_agent_receives_text_once_and_never_version():
    from tests.tui_gateway.test_make_agent_personality_prompt import _runtime
    context = {"system_context": "character", "persona_context": "user persona",
               "persona_reminder": "reminder", "persona_version": "metadata-only"}
    with ExitStack() as stack:
        for name, value in (("_load_cfg", {"agent": {"system_prompt": "base"}}),
                            ("_get_db", MagicMock()), ("_load_tool_progress_mode", "compact"),
                            ("_load_reasoning_config", None), ("_load_service_tier", None),
                            ("_load_enabled_toolsets", None), ("_resolve_startup_runtime", ("test-model", None))):
            stack.enter_context(patch(f"tui_gateway.server.{name}", return_value=value))
        stack.enter_context(patch("hermes_cli.runtime_provider.resolve_runtime_provider", return_value=_runtime()))
        agent = stack.enter_context(patch("run_agent.AIAgent"))
        server._make_agent("sid", "key", bridge_context=context)
        kwargs = agent.call_args.kwargs
    assert kwargs["ephemeral_system_prompt"] == "base\n\ncharacter\n\nuser persona\n\nreminder"
    assert "metadata-only" not in repr(kwargs)


def test_rebuild_inherits_context_and_accepts_explicit_clear(monkeypatch):
    calls = []
    monkeypatch.setattr(server, "_make_agent", lambda *args, **kwargs:
                        calls.append(kwargs) or SimpleNamespace(_session_db=None, _owns_session_db=False))
    monkeypatch.setattr(server, "_config_model_target", lambda: ("", ""))
    session = {"agent": None, "session_key": "key", "bridge_context": {"system_context": "character"}}
    server._rebuild_session_agent("sid", session)
    server._rebuild_session_agent("sid", session, bridge_context={})
    assert calls[0]["bridge_context"] == {"system_context": "character"}
    assert calls[1]["bridge_context"] == {}
    assert session["bridge_context"] == {}
    server._rebuild_session_agent("sid", session)
    assert not calls[2].get("bridge_context")
