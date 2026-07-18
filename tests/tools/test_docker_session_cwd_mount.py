"""Coverage for opt-in, allowlisted Docker session workspaces."""

from pathlib import Path

import tools.terminal_tool as terminal_tool
import tools.file_tools as file_tools


def test_resolve_allowed_docker_session_cwd_accepts_child_and_rejects_escape(tmp_path: Path):
    allowed = tmp_path / "allowed"
    child = allowed / "project"
    outside = tmp_path / "outside"
    child.mkdir(parents=True)
    outside.mkdir()

    assert terminal_tool._resolve_allowed_docker_session_cwd(str(child), [str(allowed)]) == str(child.resolve())
    assert terminal_tool._resolve_allowed_docker_session_cwd(str(outside), [str(allowed)]) is None
    assert terminal_tool._resolve_allowed_docker_session_cwd(str(child), []) is None


def test_docker_session_cwd_mount_uses_per_task_container_key(monkeypatch):
    task_id = "tui-session-abc"
    monkeypatch.setattr(terminal_tool, "_task_env_overrides", {task_id: {"cwd": "/tmp/project"}})
    monkeypatch.setenv("TERMINAL_ENV", "docker")
    monkeypatch.setenv("TERMINAL_DOCKER_SESSION_CWD_MOUNT", "true")

    assert terminal_tool._resolve_container_task_id(task_id) == task_id


def test_profile_policy_enables_mount_and_network_override(monkeypatch):
    task_id = "profile-session"
    monkeypatch.setenv("TERMINAL_ENV", "docker")
    monkeypatch.setenv("TERMINAL_DOCKER_SESSION_CWD_MOUNT", "false")
    monkeypatch.setattr(
        terminal_tool,
        "_task_env_overrides",
        {
            task_id: {
                "cwd": "/",
                "docker_session_cwd_mount": True,
                "docker_session_cwd_allowed_roots": '["/"]',
                "docker_network": False,
            }
        },
    )

    overrides = terminal_tool.resolve_task_overrides(task_id)
    config = terminal_tool.apply_task_env_config_overrides(
        {
            "docker_session_cwd_mount": False,
            "docker_session_cwd_allowed_roots": [],
            "docker_network": True,
        },
        overrides,
    )

    assert terminal_tool._resolve_container_task_id(task_id) == task_id
    assert config["docker_session_cwd_mount"] is True
    assert config["docker_session_cwd_allowed_roots"] == ["/"]
    assert config["docker_network"] is False


def test_reregistering_live_mounted_session_keeps_container_cwd(monkeypatch):
    task_id = "mounted-session"

    class FakeEnv:
        cwd = "/workspace"

    monkeypatch.setenv("TERMINAL_ENV", "docker")
    monkeypatch.setattr(terminal_tool, "_active_environments", {task_id: FakeEnv()})

    terminal_tool.register_task_env_overrides(
        task_id,
        {
            "cwd": "/home/maxence/.hermes",
            "docker_session_cwd_mount": True,
            "docker_session_cwd_allowed_roots": ["/"],
            "docker_network": False,
        },
    )

    assert terminal_tool._active_environments[task_id].cwd == "/workspace"


def test_terminal_creates_dedicated_container_with_allowed_session_mount(monkeypatch, tmp_path: Path):
    selected = tmp_path / "selected"
    selected.mkdir()
    task_id = "tui-session-abc"
    captured = {}

    class FakeEnv:
        env = {}
        cwd = "/workspace"

        def execute(self, command, **kwargs):
            return {"output": "ok", "returncode": 0}

    config = {
        "env_type": "docker",
        "cwd": "/root",
        "host_cwd": None,
        "timeout": 60,
        "lifetime_seconds": 300,
        "docker_session_cwd_mount": True,
        "docker_session_cwd_allowed_roots": [str(tmp_path)],
        "docker_mount_cwd_to_workspace": False,
        "docker_image": "test-image",
        "container_cpu": 1,
        "container_memory": 512,
        "container_disk": 1024,
        "container_persistent": False,
        "docker_volumes": [],
        "docker_forward_env": [],
        "docker_env": {},
        "docker_run_as_host_user": False,
        "docker_extra_args": [],
        "docker_network": False,
        "docker_persist_across_processes": False,
        "docker_orphan_reaper": False,
    }

    def create_environment(**kwargs):
        captured.update(kwargs)
        return FakeEnv()

    monkeypatch.setattr(terminal_tool, "_task_env_overrides", {task_id: {"cwd": str(selected)}})
    monkeypatch.setenv("TERMINAL_ENV", "docker")
    monkeypatch.setenv("TERMINAL_DOCKER_SESSION_CWD_MOUNT", "true")
    monkeypatch.setattr(terminal_tool, "_active_environments", {})
    monkeypatch.setattr(terminal_tool, "_last_activity", {})
    monkeypatch.setattr(terminal_tool, "_get_env_config", lambda: config)
    monkeypatch.setattr(terminal_tool, "_create_environment", create_environment)
    monkeypatch.setattr(terminal_tool, "_start_cleanup_thread", lambda: None)
    monkeypatch.setattr(terminal_tool, "_check_all_guards", lambda *args, **kwargs: {"approved": True})

    result = terminal_tool.terminal_tool(command="pwd", task_id=task_id)

    assert '"exit_code": 0' in result
    assert captured["cwd"] == "/workspace"
    assert captured["host_cwd"] == str(selected.resolve())
    assert captured["task_id"] == task_id
    assert captured["container_config"]["docker_mount_cwd_to_workspace"] is True


def test_file_tool_first_creates_container_with_allowed_session_mount(monkeypatch, tmp_path: Path):
    selected = tmp_path / "selected"
    selected.mkdir()
    task_id = "tui-session-file-first"
    captured = {}

    class FakeEnv:
        env = {}
        cwd = "/workspace"

    config = {
        "env_type": "docker",
        "cwd": "/root",
        "host_cwd": None,
        "timeout": 60,
        "lifetime_seconds": 300,
        "docker_session_cwd_mount": True,
        "docker_session_cwd_allowed_roots": [str(tmp_path)],
        "docker_mount_cwd_to_workspace": False,
        "docker_image": "test-image",
        "container_cpu": 1,
        "container_memory": 512,
        "container_disk": 1024,
        "container_persistent": False,
        "docker_volumes": [],
        "docker_forward_env": [],
        "docker_run_as_host_user": False,
        "docker_network": False,
    }

    def create_environment(**kwargs):
        captured.update(kwargs)
        return FakeEnv()

    monkeypatch.setattr(terminal_tool, "_task_env_overrides", {task_id: {"cwd": str(selected)}})
    monkeypatch.setenv("TERMINAL_ENV", "docker")
    monkeypatch.setenv("TERMINAL_DOCKER_SESSION_CWD_MOUNT", "true")
    monkeypatch.setattr(terminal_tool, "_active_environments", {})
    monkeypatch.setattr(terminal_tool, "_last_activity", {})
    monkeypatch.setattr(terminal_tool, "_get_env_config", lambda: config)
    monkeypatch.setattr(terminal_tool, "_create_environment", create_environment)
    monkeypatch.setattr(terminal_tool, "_start_cleanup_thread", lambda: None)
    monkeypatch.setattr(file_tools, "_file_ops_cache", {})

    file_tools._get_file_ops(task_id)

    assert captured["cwd"] == "/workspace"
    assert captured["host_cwd"] == str(selected.resolve())
    assert captured["task_id"] == task_id
    assert captured["container_config"]["docker_mount_cwd_to_workspace"] is True


def test_docker_session_cwd_mount_disabled_keeps_shared_container(monkeypatch):
    task_id = "tui-session-abc"
    monkeypatch.setattr(terminal_tool, "_task_env_overrides", {task_id: {"cwd": "/tmp/project"}})
    monkeypatch.setenv("TERMINAL_ENV", "docker")
    monkeypatch.setenv("TERMINAL_DOCKER_SESSION_CWD_MOUNT", "false")

    assert terminal_tool._resolve_container_task_id(task_id) == "default"
