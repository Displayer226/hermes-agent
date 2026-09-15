"""Regression coverage for profile-routed terminal sandbox configuration."""

import pytest

from tools import file_tools
from tools import terminal_tool
from tools.terminal_scope import reset_terminal_scope, set_terminal_scope


def test_profile_terminal_scope_overrides_launch_profile():
    token = set_terminal_scope({
        "TERMINAL_ENV": "docker",
        "TERMINAL_DOCKER_IMAGE": "admin-image",
        "TERMINAL_DOCKER_VOLUMES": '["/var/run/docker.sock:/var/run/docker.sock"]',
        "TERMINAL_DOCKER_NETWORK": "true",
        "TERMINAL_DOCKER_EXTRA_ARGS": '["--group-add=987"]',
        "TERMINAL_CONTAINER_PERSISTENT": "false",
        "TERMINAL_CWD": "/root",
    })
    try:
        config = terminal_tool._get_env_config()
        assert config["docker_image"] == "admin-image"
        assert config["docker_volumes"] == [
            "/var/run/docker.sock:/var/run/docker.sock"
        ]
        assert config["docker_network"] is True
        assert config["docker_extra_args"] == ["--group-add=987"]
        assert config["cwd"] == "/root"
    finally:
        reset_terminal_scope(token)


@pytest.mark.parametrize(
    ("global_network", "profile_network"),
    [(False, True), (True, False)],
)
def test_file_tools_create_sandbox_from_routed_profile(
    monkeypatch, global_network, profile_network
):
    """A file-tool-first session must not inherit the launch profile posture."""
    captured = {}

    class _DummyEnvironment:
        cwd = "/root"

    def fake_create_environment(*args, **kwargs):
        captured["config"] = args[0]
        captured.update(kwargs)
        return _DummyEnvironment()

    monkeypatch.setattr(terminal_tool, "_create_configured_env", fake_create_environment)
    monkeypatch.setattr(terminal_tool, "_start_cleanup_thread", lambda: None)
    monkeypatch.setattr(terminal_tool, "_active_environments", {})
    monkeypatch.setattr(terminal_tool, "_last_activity", {})
    monkeypatch.setattr(terminal_tool, "_session_cwd", {})
    monkeypatch.setattr(file_tools, "_file_ops_cache", {})

    token = set_terminal_scope({
        "TERMINAL_ENV": "docker",
        "TERMINAL_DOCKER_IMAGE": "profile-image",
        "TERMINAL_DOCKER_NETWORK": str(profile_network).lower(),
        "TERMINAL_DOCKER_EXTRA_ARGS": '["--label=source=profile"]',
        "TERMINAL_CONTAINER_PERSISTENT": "false",
        "TERMINAL_DOCKER_MOUNT_CWD_TO_WORKSPACE": "false",
        "TERMINAL_CWD": "/root",
    })
    try:
        file_tools._get_file_ops(f"profile-network-{profile_network}")
    finally:
        reset_terminal_scope(token)

    assert captured["image"] == "profile-image"
    assert captured["config"]["docker_network"] is profile_network
    assert captured["config"]["docker_extra_args"] == [
        "--label=source=profile"
    ]
