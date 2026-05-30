from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

PUBLIC_MODELS_URL = "https://api.cerebras.ai/public/v1/models"
USER_AGENT = "Budgify/0.1"


@dataclass(frozen=True)
class ModelPricing:
    model: str
    prompt_per_token: float
    completion_per_token: float

    @property
    def prompt_per_million(self) -> float:
        return self.prompt_per_token * 1_000_000

    @property
    def completion_per_million(self) -> float:
        return self.completion_per_token * 1_000_000

    def as_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "currency": "USD",
            "promptPerToken": self.prompt_per_token,
            "completionPerToken": self.completion_per_token,
            "promptPerMillion": round(self.prompt_per_million, 4),
            "completionPerMillion": round(self.completion_per_million, 4),
        }


def _fetch_json(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        data = json.load(resp)
    return data if isinstance(data, dict) else {}


@lru_cache(maxsize=32)
def get_model_pricing(model_id: str) -> ModelPricing | None:
    model = model_id.strip()
    if not model:
        return None
    try:
        payload = _fetch_json(f"{PUBLIC_MODELS_URL}/{model}")
    except (urllib.error.HTTPError, urllib.error.URLError, json.JSONDecodeError, TimeoutError, ValueError):
        return None
    pricing = payload.get("pricing")
    if not isinstance(pricing, dict):
        return None
    try:
        prompt = float(pricing.get("prompt"))
        completion = float(pricing.get("completion"))
    except (TypeError, ValueError):
        return None
    return ModelPricing(model=model, prompt_per_token=prompt, completion_per_token=completion)


def estimate_token_cost(model_id: str, prompt_tokens: int, completion_tokens: int) -> float | None:
    pricing = get_model_pricing(model_id)
    if pricing is None:
        return None
    prompt_cost = max(prompt_tokens, 0) * pricing.prompt_per_token
    completion_cost = max(completion_tokens, 0) * pricing.completion_per_token
    return round(prompt_cost + completion_cost, 6)


def build_session_cost(
    *,
    request_id: str,
    source: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached: bool = False,
    cached_tokens: int | None = None,
) -> dict[str, Any]:
    pricing = get_model_pricing(model_id)
    estimated_cost = estimate_token_cost(model_id, prompt_tokens, completion_tokens)
    return {
        "requestId": request_id,
        "source": source,
        "model": model_id,
        "currency": "USD",
        "promptTokens": max(prompt_tokens, 0),
        "completionTokens": max(completion_tokens, 0),
        "totalTokens": max(prompt_tokens, 0) + max(completion_tokens, 0),
        "cachedTokens": max(cached_tokens or 0, 0),
        "promptRateUsdPerToken": pricing.prompt_per_token if pricing else None,
        "completionRateUsdPerToken": pricing.completion_per_token if pricing else None,
        "promptRateUsdPerMillion": pricing.prompt_per_million if pricing else None,
        "completionRateUsdPerMillion": pricing.completion_per_million if pricing else None,
        "estimatedCostUsd": estimated_cost,
        "cached": cached,
        "estimated": pricing is None,
    }
