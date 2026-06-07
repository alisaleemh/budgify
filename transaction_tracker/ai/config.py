from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from transaction_tracker.ai.costs import get_model_pricing

DEFAULT_AI_PROVIDER = "cerebras"
DEFAULT_AI_BASE_URL = "https://api.cerebras.ai/v1"
DEFAULT_AI_MODEL = "zai-glm-4.7"


@dataclass(frozen=True)
class AIConfig:
    provider: str = DEFAULT_AI_PROVIDER
    api_key: str | None = None
    api_key_present: bool = False
    base_url: str = DEFAULT_AI_BASE_URL
    model: str = DEFAULT_AI_MODEL


def _read_key_file(path_value: str | None) -> str | None:
    if not path_value:
        return None
    path = Path(path_value).expanduser()
    try:
        value = path.read_text(encoding="utf-8").strip()
    except (FileNotFoundError, IsADirectoryError, PermissionError):
        return None
    return value or None


def load_ai_config(environ: dict[str, str] | None = None) -> AIConfig:
    env = environ or os.environ
    provider = (env.get("AI_PROVIDER") or DEFAULT_AI_PROVIDER).strip().lower()
    api_key = (env.get("AI_API_KEY") or "").strip() or None
    if api_key is None:
        api_key = _read_key_file(env.get("AI_API_KEY_FILE"))
    base_url = (env.get("AI_BASE_URL") or DEFAULT_AI_BASE_URL).strip().rstrip("/")
    model = (env.get("AI_MODEL") or DEFAULT_AI_MODEL).strip()
    return AIConfig(
        provider=provider,
        api_key=api_key,
        api_key_present=api_key is not None,
        base_url=base_url,
        model=model,
    )


def ai_status(environ: dict[str, str] | None = None) -> dict[str, object]:
    config = load_ai_config(environ)
    pricing = get_model_pricing(config.model)
    env = environ or os.environ
    deploy_commit = (env.get("BUDGIFY_DEPLOY_COMMIT") or env.get("GIT_COMMIT") or "").strip() or None
    return {
        "provider": config.provider,
        "baseUrl": config.base_url,
        "model": config.model,
        "apiKeyPresent": config.api_key_present,
        "deployCommit": deploy_commit,
        "pricing": pricing.as_dict() if pricing else None,
    }
