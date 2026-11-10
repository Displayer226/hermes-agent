"""Stable client-supplied startup context carried across agent construction."""

FIELDS = ("system_context", "persona_context", "persona_reminder", "persona_version")
TEXT_FIELDS = FIELDS[:3]


def from_params(params: dict) -> dict:
    return {key: params[key] or "" for key in FIELDS if key in params}


def prompt(base: str, context: dict | None) -> str:
    context = context or {}
    return "\n\n".join(part for part in (base, *(context.get(k) for k in TEXT_FIELDS)) if part)
