import json
import threading
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import pytest

from transaction_tracker import web
from transaction_tracker.ai.costs import ModelPricing
from transaction_tracker.ai.assistant import query_finance_assistant
from transaction_tracker.ai.config import ai_status, load_ai_config
from transaction_tracker.ai.finance_tools import RAW_LIMIT, ToolValidationError, call_finance_tool
from transaction_tracker.ai.providers import CerebrasProvider
from transaction_tracker.core.models import Transaction
from transaction_tracker.database import append_transactions


def _seed_assistant_transactions(db_path):
    categories = {
        "groceries": ["Costco", "Fresh"],
        "restaurants": ["Cafe", "Pizza"],
        "house": ["Home"],
    }
    txs = [
        Transaction(date=date(2026, 1, 4), description="Bulk groceries", merchant="Costco", amount=120.0),
        Transaction(date=date(2026, 3, 8), description="Bulk groceries", merchant="Costco", amount=180.0),
        Transaction(date=date(2026, 4, 1), description="Dinner", merchant="Pizza Palace", amount=50.0),
        Transaction(date=date(2026, 4, 5), description="Lunch", merchant="Cafe Nero", amount=25.0),
        Transaction(date=date(2026, 4, 8), description="Groceries", merchant="Fresh Market", amount=70.0),
        Transaction(date=date(2026, 5, 2), description="Groceries", merchant="Fresh Market", amount=90.0),
    ]
    append_transactions(txs, str(db_path), categories)


@pytest.fixture(autouse=True)
def _stub_model_pricing(monkeypatch):
    pricing = lambda model: ModelPricing(model=model, prompt_per_token=0.00000225, completion_per_token=0.00000275)
    monkeypatch.setattr(
        "transaction_tracker.ai.costs.get_model_pricing",
        pricing,
    )
    monkeypatch.setattr(
        "transaction_tracker.ai.config.get_model_pricing",
        pricing,
    )


def test_ai_config_defaults_to_cerebras_and_key_file(tmp_path, monkeypatch):
    key_file = tmp_path / "api-key"
    key_file.write_text("  secret-value\n", encoding="utf-8")
    monkeypatch.setattr("pathlib.Path.expanduser", lambda self: key_file if str(self) == "~/api-key" else self)

    config = load_ai_config({"AI_API_KEY_FILE": "~/api-key"})
    status = ai_status({"AI_API_KEY_FILE": "~/api-key"})

    assert config.provider == "cerebras"
    assert isinstance(CerebrasProvider(config), CerebrasProvider)
    assert config.api_key == "secret-value"
    assert status == {
        "provider": "cerebras",
        "baseUrl": "https://api.cerebras.ai/v1",
        "model": "zai-glm-4.7",
        "apiKeyPresent": True,
        "pricing": {
            "model": "zai-glm-4.7",
            "currency": "USD",
            "promptPerToken": 0.00000225,
            "completionPerToken": 0.00000275,
            "promptPerMillion": 2.25,
            "completionPerMillion": 2.75,
        },
    }
    assert "secret-value" not in json.dumps(status)


def test_missing_key_status_does_not_leak_secret():
    status = ai_status({})

    assert status["apiKeyPresent"] is False
    assert "apiKey" not in status


def test_finance_tools_validate_names_and_cap_transactions(tmp_path):
    db_path = tmp_path / "txs.db"
    categories = {"groceries": ["Store"]}
    append_transactions(
        [
            Transaction(date=date(2026, 1, day), description="Store", merchant="Store", amount=float(day))
            for day in range(1, 32)
        ],
        str(db_path),
        categories,
    )
    append_transactions(
        [
            Transaction(date=date(2026, 3, day), description="Store", merchant="Store", amount=float(day))
            for day in range(1, 31)
        ],
        str(db_path),
        categories,
    )

    result = call_finance_tool(str(db_path), "getTransactions", {"limit": 1000})

    assert len(result["transactions"]) == RAW_LIMIT
    assert result["limit"] == RAW_LIMIT
    with pytest.raises(ToolValidationError):
        call_finance_tool(str(db_path), "deleteEverything", {})


def test_finance_tool_example_questions(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_assistant_transactions(db_path)

    costco = call_finance_tool(
        str(db_path),
        "getSpendByMerchant",
        {"merchant": "Costco", "start_date": "2026-01-01", "end_date": "2026-05-18"},
    )
    restaurants = call_finance_tool(
        str(db_path),
        "getSpendByCategory",
        {"category": "restaurants", "start_date": "2026-04-01", "end_date": "2026-04-30"},
    )
    groceries_compare = call_finance_tool(
        str(db_path),
        "compareSpendPeriods",
        {
            "period_a": {"label": "April", "start_date": "2026-04-01", "end_date": "2026-04-30"},
            "period_b": {"label": "May", "start_date": "2026-05-01", "end_date": "2026-05-31"},
            "category": "groceries",
        },
    )

    assert costco["merchants"][0]["merchant"] == "Costco"
    assert costco["merchants"][0]["total"] == 300.0
    assert restaurants["categories"][0]["total"] == 75.0
    assert groceries_compare["period_a"]["total"] == 70.0
    assert groceries_compare["period_b"]["total"] == 90.0


class FakeProvider:
    def __init__(self):
        self.calls = 0
        self.messages = []
        self.config = type("Config", (), {"model": "zai-glm-4.7"})()

    def complete_response(self, messages, *, tools=None, tool_choice=None):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {
                                "name": "getSpendByMerchant",
                                "arguments": json.dumps(
                                    {
                                        "merchant": "Costco",
                                        "start_date": "2026-01-01",
                                        "end_date": "2026-05-18",
                                    }
                                ),
                            },
                        }
                    ],
                },
                "usage": {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125},
            }
        return {
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "summary": "Costco spend is $300.00 year to date.",
                        "bullets": ["3 transactions", "No unusual spikes"],
                        "followup": "Ask for a month-by-month breakdown if needed.",
                    }
                ),
            },
            "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
        }

    def complete(self, messages, *, tools=None, tool_choice=None):
        return self.complete_response(messages, tools=tools, tool_choice=tool_choice)["message"]


def test_assistant_tool_call_loop_uses_fake_provider(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_assistant_transactions(db_path)
    provider = FakeProvider()

    result = query_finance_assistant(str(db_path), "How much at Costco YTD?", provider=provider)

    assert result.answer == "Costco spend is $300.00 year to date.\n\n- 3 transactions\n- No unusual spikes\n\nNext: Ask for a month-by-month breakdown if needed."
    assert result.summary == "Costco spend is $300.00 year to date."
    assert result.bullets == ["3 transactions", "No unusual spikes"]
    assert result.followup == "Ask for a month-by-month breakdown if needed."
    assert result.data_used[0]["tool"] == "getSpendByMerchant"
    assert result.data_used[0]["result"]["merchants"][0]["total"] == 300.0
    assert result.cards[0]["kind"] == "metric"
    assert result.tables[0]["title"] == "Merchant breakdown"
    assert result.sessionCost["model"] == "zai-glm-4.7"
    assert result.sessionCost["totalTokens"] == 245
    assert result.sessionCost["cached"] is False
    assert provider.calls == 2


def test_assistant_handles_raw_chat_completion_shape(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_assistant_transactions(db_path)

    class RawProvider(FakeProvider):
        def complete_response(self, messages, *, tools=None, tool_choice=None):
            self.calls += 1
            self.messages.append(messages)
            if self.calls == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "getSpendByMerchant",
                                            "arguments": json.dumps(
                                                {
                                                    "merchant": "Costco",
                                                    "start_date": "2026-01-01",
                                                    "end_date": "2026-05-18",
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125},
                }
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": json.dumps(
                                {
                                    "summary": "Costco spend is $300.00 year to date.",
                                    "bullets": ["3 transactions", "No unusual spikes"],
                                    "followup": "Ask for a month-by-month breakdown if needed.",
                                }
                            ),
                        }
                    }
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
            }

    result = query_finance_assistant(str(db_path), "How much at Costco YTD?", provider=RawProvider())
    assert result.summary == "Costco spend is $300.00 year to date."
    assert result.answer.startswith("Costco spend is $300.00 year to date.")
    assert result.sessionCost["totalTokens"] == 245


def test_assistant_strips_fenced_json_response(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_assistant_transactions(db_path)

    class FencedProvider(FakeProvider):
        def complete_response(self, messages, *, tools=None, tool_choice=None):
            self.calls += 1
            self.messages.append(messages)
            if self.calls == 1:
                return {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "getSpendByMerchant",
                                            "arguments": json.dumps(
                                                {
                                                    "merchant": "Costco",
                                                    "start_date": "2026-01-01",
                                                    "end_date": "2026-05-18",
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 25, "total_tokens": 125},
                }
            return {
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "```json\n"
                            + json.dumps(
                                {
                                    "summary": "Costco spend is $300.00 year to date.",
                                    "bullets": ["3 transactions", "No unusual spikes"],
                                    "followup": "Ask for a month-by-month breakdown if needed.",
                                }
                            )
                            + "\n```",
                        }
                    }
                ],
                "usage": {"prompt_tokens": 80, "completion_tokens": 40, "total_tokens": 120},
            }

    result = query_finance_assistant(str(db_path), "How much at Costco YTD?", provider=FencedProvider())

    assert result.summary == "Costco spend is $300.00 year to date."
    assert result.bullets == ["3 transactions", "No unusual spikes"]
    assert result.followup == "Ask for a month-by-month breakdown if needed."
    assert result.answer.startswith("Costco spend is $300.00 year to date.")
    assert "```" not in result.answer


def test_assistant_endpoint_with_fake_provider(tmp_path, monkeypatch):
    db_path = tmp_path / "txs.db"
    _seed_assistant_transactions(db_path)
    monkeypatch.setattr(
        web,
        "query_finance_assistant",
        lambda path, question: query_finance_assistant(path, question, provider=FakeProvider()),
    )
    handler = type(
        "TestHandler",
        (web.BudgifyWebHandler,),
        {"db_path": str(db_path), "static_dir": web.STATIC_DIR, "password_file": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        payload = json.dumps({"question": "How much at Costco YTD?"}).encode("utf-8")
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/assistant/query",
            data=payload,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as resp:
            body = json.load(resp)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert body["answer"] == "Costco spend is $300.00 year to date.\n\n- 3 transactions\n- No unusual spikes\n\nNext: Ask for a month-by-month breakdown if needed."
    assert body["summary"] == "Costco spend is $300.00 year to date."
    assert body["bullets"] == ["3 transactions", "No unusual spikes"]
    assert body["followup"] == "Ask for a month-by-month breakdown if needed."
    assert body["dataUsed"][0]["tool"] == "getSpendByMerchant"
    assert body["cards"][0]["kind"] == "metric"
    assert body["tables"][0]["title"] == "Merchant breakdown"
    assert body["sessionCost"]["totalTokens"] == 245


def test_assistant_endpoint_rejects_missing_question(tmp_path):
    handler = type(
        "TestHandler",
        (web.BudgifyWebHandler,),
        {"db_path": str(tmp_path / "txs.db"), "static_dir": web.STATIC_DIR, "password_file": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        req = urllib.request.Request(
            f"http://127.0.0.1:{server.server_port}/api/assistant/query",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with pytest.raises(urllib.error.HTTPError) as excinfo:
            urllib.request.urlopen(req)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert excinfo.value.code == 400
