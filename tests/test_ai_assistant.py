import json
import threading
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import pytest

from transaction_tracker import web
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

    def complete(self, messages, *, tools=None, tool_choice=None):
        self.calls += 1
        self.messages.append(messages)
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "type": "function",
                        "function": {
                            "name": "getSpendByMerchant",
                            "arguments": json.dumps({
                                "merchant": "Costco",
                                "start_date": "2026-01-01",
                                "end_date": "2026-05-18",
                            }),
                        },
                    }
                ],
            }
        return {"role": "assistant", "content": "Costco year-to-date spend is $300.00."}


def test_assistant_tool_call_loop_uses_fake_provider(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_assistant_transactions(db_path)
    provider = FakeProvider()

    result = query_finance_assistant(str(db_path), "How much at Costco YTD?", provider=provider)

    assert result.answer == "Costco year-to-date spend is $300.00."
    assert result.data_used[0]["tool"] == "getSpendByMerchant"
    assert result.data_used[0]["result"]["merchants"][0]["total"] == 300.0
    assert provider.calls == 2


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

    assert body["answer"] == "Costco year-to-date spend is $300.00."
    assert body["dataUsed"][0]["tool"] == "getSpendByMerchant"


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
