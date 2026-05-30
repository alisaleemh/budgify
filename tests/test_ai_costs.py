from transaction_tracker.ai import config as ai_config
from transaction_tracker.ai.costs import ModelPricing, build_session_cost, estimate_token_cost, get_model_pricing


def test_model_pricing_and_cost_estimation(monkeypatch):
    get_model_pricing.cache_clear()

    def fake_fetch_json(url: str):
        assert url.endswith("/zai-glm-4.7")
        return {
            "pricing": {
                "prompt": "0.00000225",
                "completion": "0.00000275",
            }
        }

    monkeypatch.setattr("transaction_tracker.ai.costs._fetch_json", fake_fetch_json)

    pricing = get_model_pricing("zai-glm-4.7")
    assert pricing == ModelPricing(model="zai-glm-4.7", prompt_per_token=0.00000225, completion_per_token=0.00000275)
    assert estimate_token_cost("zai-glm-4.7", 1_000, 2_000) == 0.00775

    session_cost = build_session_cost(
        request_id="req-1",
        source="beta",
        model_id="zai-glm-4.7",
        prompt_tokens=1_000,
        completion_tokens=2_000,
        cached=False,
    )
    assert session_cost["estimatedCostUsd"] == 0.00775
    assert session_cost["promptRateUsdPerMillion"] == 2.25
    assert session_cost["completionRateUsdPerMillion"] == 2.75
    get_model_pricing.cache_clear()


def test_ai_status_includes_pricing(monkeypatch):
    monkeypatch.setattr(ai_config, "get_model_pricing", lambda model: ModelPricing(model=model, prompt_per_token=0.1, completion_per_token=0.2))
    status = ai_config.ai_status({"AI_PROVIDER": "cerebras", "AI_MODEL": "zai-glm-4.7"})
    assert status["pricing"]["promptPerMillion"] == 100000.0
    assert status["pricing"]["completionPerMillion"] == 200000.0
