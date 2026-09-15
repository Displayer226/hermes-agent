"""Routed profiles must bring their own terminal sandbox posture."""

from tui_gateway import server
from tools import terminal_tool


def test_register_session_captures_only_session_cwd(tmp_path, monkeypatch):
    profile_home = tmp_path / "profiles" / "admin"
    profile_home.mkdir(parents=True)
    (profile_home / "config.yaml").write_text(
        "terminal:\n"
        "  backend: docker\n"
        "  docker_image: admin-image\n"
        "  docker_volumes:\n"
        "    - /var/run/docker.sock:/var/run/docker.sock\n"
        "  docker_network: true\n"
        "  docker_extra_args:\n"
        "    - --group-add=987\n"
        "  container_persistent: false\n",
        encoding="utf-8",
    )
    captured = {}
    monkeypatch.setattr(
        server,
        "_terminal_task_cwd_with_source",
        lambda _session: ("/home/maxence/workspace", "session"),
    )
    monkeypatch.setattr(
        terminal_tool,
        "register_task_env_overrides",
        lambda task_id, overrides: captured.update(
            task_id=task_id, overrides=overrides
        ),
    )

    server._register_session_cwd(
        {"session_key": "st-admin", "profile_home": str(profile_home)}
    )

    assert captured["task_id"] == "st-admin"
    # Profile terminal policy is now bound through terminal_scope per turn;
    # session overrides retain only session-owned workspace state.
    assert captured["overrides"] == {
        "cwd": "/home/maxence/workspace",
        "cwd_source": "session",
    }
