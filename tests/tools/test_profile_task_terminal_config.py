"""Regression coverage for profile-routed terminal sandbox configuration."""

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
