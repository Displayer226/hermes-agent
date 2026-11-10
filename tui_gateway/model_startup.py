"""Resolve a model-only session pick using the CLI's startup routing rules."""


def resolve_model_only(model: str, cfg: dict):
    from hermes_cli.model_switch import resolve_startup_model_route

    model_cfg = cfg.get("model") or {}
    provider = model_cfg.get("provider", "") if isinstance(model_cfg, dict) else ""
    return resolve_startup_model_route(model, current_provider=provider,
                                       user_providers=cfg.get("providers"),
                                       custom_providers=cfg.get("custom_providers"))
