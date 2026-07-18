# Per-session Docker workspaces

This opt-in mode lets a trusted integration choose a host directory when it
creates a Hermes TUI/Gateway session. Hermes validates the directory against an
operator-controlled allowlist, bind-mounts it at `/workspace`, and runs that
session's terminal/file/code-execution tools in a dedicated Docker container.

```yaml
terminal:
  backend: docker
  docker_session_cwd_mount: true
  docker_session_cwd_allowed_roots:
    - /home/maxence/dev
  docker_network: false
  docker_run_as_host_user: true
```

Equivalent commands:

```bash
hermes config set terminal.backend docker
hermes config set terminal.docker_session_cwd_mount true
hermes config set terminal.docker_session_cwd_allowed_roots '["/home/maxence/dev"]'
hermes config set terminal.docker_network false
```

The extension/proxy must send an explicit `cwd` in `session.create`. The path
is canonicalised; symlinks cannot escape an allowed root. An empty allowlist
denies every dynamic host mount.

## Choosing the maximum root

For a normal coding-only installation, use a narrow root such as
`/home/maxence/dev`. A proxy running in Docker can expose the same tree through
its own read-only mount and translate it back to the host path before it calls
Hermes.

An administrator may intentionally allow the whole host:

```yaml
terminal:
  docker_session_cwd_allowed_roots: ["/"]
```

This is not a safe default: a selected `/etc`, `/var`, or `/home` is then
writable from the agent's Docker container. Keep the extension/proxy
admin-only, retain command approvals, and prefer `docker_network: false`.
