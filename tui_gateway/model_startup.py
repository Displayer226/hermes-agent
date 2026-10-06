"""Apply configured model routes to model-only session creation requests."""

from __future__ import annotations

from typing import Any


def resolve_session_model_alias(model_override: Any, provider_override: str | None) -> Any:
    """Resolve an unpinned session model with the same aliases as CLI startup and /model.

    Proxy clients create sessions with a model and no provider. Inheriting the profile's
    custom endpoint then sends ChatGPT slugs to that endpoint instead of Codex. Explicit
    provider selections and persisted runtime pins retain their original authority.
    """
    if isinstance(model_override, dict):
        model = model_override.get("model")
        provider = model_override.get("provider") or provider_override
    else:
        model, provider = model_override, provider_override
    if not isinstance(model, str) or not model.strip() or provider:
        return model_override

    from hermes_cli.model_switch import resolve_startup_model_route

    route = resolve_startup_model_route(model)
    if route is None:
        return model_override

    resolved = dict(model_override) if isinstance(model_override, dict) else {}
    # An unpinned model's old endpoint/credential must not contaminate the alias destination.
    for key in ("base_url", "api_key", "api_mode"):
        resolved.pop(key, None)
    resolved.update(model=route.model, provider=route.provider)
    if route.base_url:
        resolved["base_url"] = route.base_url
    if route.api_key:
        resolved["api_key"] = route.api_key
    return resolved
