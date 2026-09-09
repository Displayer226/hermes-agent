"""Regression coverage for profile-routed terminal sandbox configuration."""

import pytest

from tools import file_tools
from tools import terminal_tool


def test_task_terminal_posture_overlays_launch_profile(monkeypatch):
    baseline = {
        "env_type": "docker",
        "docker_image": "common-image",
        "docker_volumes": [],
        "docker_network": False,
        "docker_extra_args": [],
        "container_persistent": False,
        "cwd": "/root",
    }
    monkeypatch.setattr(terminal_tool, "_get_env_config", lambda: dict(baseline))
    terminal_tool.register_task_env_overrides(
        "admin-session",
        {
            "env_type": "docker",
            "docker_image": "admin-image",
            "docker_volumes": ["/var/run/docker.sock:/var/run/docker.sock"],
            "docker_network": True,
            "docker_extra_args": ["--group-add=987"],
            "cwd": "/host/workspace",
            "cwd_source": "session",
        },
    )
    try:
        config = terminal_tool._get_task_env_config("admin-session")
        assert config["docker_image"] == "admin-image"
        assert config["docker_volumes"] == [
            "/var/run/docker.sock:/var/run/docker.sock"
        ]
        assert config["docker_network"] is True
        assert config["docker_extra_args"] == ["--group-add=987"]
        # CWD remains session state, not part of the immutable backend posture.
        assert config["cwd"] == "/root"
        assert terminal_tool._resolve_container_task_id("admin-session") == "admin-session"
    finally:
        terminal_tool.clear_task_env_overrides("admin-session")


@pytest.mark.parametrize(
    ("global_network", "profile_network"),
    [(False, True), (True, False)],
)
def test_file_tools_create_sandbox_from_routed_profile(
    monkeypatch, global_network, profile_network
):
    """A file-tool-first session must not inherit the launch profile posture."""
    baseline = {
        "env_type": "docker",
        "docker_image": "global-image",
        "docker_volumes": [],
        "docker_network": global_network,
        "docker_extra_args": ["--label=source=global"],
        "container_persistent": False,
        "docker_mount_cwd_to_workspace": False,
        "cwd": "/root",
        "timeout": 180,
    }
    captured = {}

    class _DummyEnvironment:
        cwd = "/root"

    def fake_create_environment(**kwargs):
        captured.update(kwargs)
        return _DummyEnvironment()

    monkeypatch.setattr(terminal_tool, "_get_env_config", lambda: dict(baseline))
    monkeypatch.setattr(terminal_tool, "_create_environment", fake_create_environment)
    monkeypatch.setattr(terminal_tool, "_start_cleanup_thread", lambda: None)
    monkeypatch.setattr(terminal_tool, "_active_environments", {})
    monkeypatch.setattr(terminal_tool, "_last_activity", {})
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})
    monkeypatch.setattr(file_tools, "_file_ops_cache", {})

    task_id = f"profile-network-{profile_network}"
    terminal_tool.register_task_env_overrides(
        task_id,
        {
            "env_type": "docker",
            "docker_image": "profile-image",
            "docker_network": profile_network,
            "docker_extra_args": ["--label=source=profile"],
        },
    )
    try:
        file_tools._get_file_ops(task_id)
    finally:
        terminal_tool.clear_task_env_overrides(task_id)

    assert captured["image"] == "profile-image"
    assert captured["container_config"]["docker_network"] is profile_network
    assert captured["container_config"]["docker_extra_args"] == [
        "--label=source=profile"
    ]
