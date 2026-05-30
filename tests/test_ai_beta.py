import json
import threading
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import pytest

from transaction_tracker import web
from transaction_tracker.ai.costs import ModelPricing
from transaction_tracker.ai.beta import (
    BetaCitation,
    ask_beta_question,
    clear_beta_cache,
    generate_beta_briefing,
    parse_beta_response,
)
from transaction_tracker.core.models import Transaction
from transaction_tracker.database import append_transactions
from transaction_tracker.mcp_server import _recurring_impl, _spend_summary_impl


def _seed_beta_transactions(db_path):
    categories = {
        "groceries": ["Fresh", "Market"],
        "restaurants": ["Cafe"],
        "subscription": ["Stream"],
    }
    txs = [
        Transaction(date=date(2026, 5, 2), description="Groceries", merchant="Fresh Market", amount=85.0, provider="amex"),
        Transaction(date=date(2026, 5, 5), description="Dinner", merchant="Cafe Nero", amount=42.0, provider="amex"),
        Transaction(date=date(2026, 5, 8), description="Streaming", merchant="StreamFlix", amount=15.0, provider="visa"),
        Transaction(date=date(2026, 4, 8), description="Streaming", merchant="StreamFlix", amount=15.0, provider="visa"),
        Transaction(date=date(2026, 3, 8), description="Streaming", merchant="StreamFlix", amount=15.0, provider="visa"),
    ]
    append_transactions(txs, str(db_path), categories)


@pytest.fixture(autouse=True)
def _stub_model_pricing(monkeypatch):
    monkeypatch.setattr(
        "transaction_tracker.ai.costs.get_model_pricing",
        lambda model: ModelPricing(model=model, prompt_per_token=0.00000225, completion_per_token=0.00000275),
    )


class FakeBetaProvider:
    def __init__(self):
        self.calls = 0
        self.config = type("Config", (), {"model": "zai-glm-4.7"})()

    def complete_response(self, messages, *, tools=None, tool_choice=None):
        self.calls += 1
        context_message = next(message for message in messages if message["role"] == "system" and message["content"].startswith("Budgify MCP context"))
        context = json.loads(context_message["content"].split("Budgify MCP context:\n", 1)[1])
        tx_id = context["transactions"][0]["id"]
        return {
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "summary": "Recent spending is led by groceries.",
                        "insights": [
                            {
                                "title": "Groceries led recent spend",
                                "body": "Fresh Market is the largest recent transaction in the MCP context.",
                                "why": "This transaction is in the latest briefing range.",
                                "citationIds": [tx_id, "not-a-real-id"],
                            }
                        ],
                        "recommendations": [
                            {
                                "title": "Review grocery plan",
                                "body": "Check whether the larger grocery run was expected.",
                                "estimated": False,
                                "citationIds": [tx_id],
                            }
                        ],
                        "citations": [tx_id],
                        "estimated": False,
                    }
                ),
            },
            "usage": {"prompt_tokens": 50, "completion_tokens": 20, "total_tokens": 70},
        }

    def complete(self, messages, *, tools=None, tool_choice=None):
        return self.complete_response(messages, tools=tools, tool_choice=tool_choice)["message"]


def test_beta_briefing_uses_mcp_context_and_filters_citations(tmp_path):
    clear_beta_cache()
    db_path = tmp_path / "txs.db"
    _seed_beta_transactions(db_path)

    result = generate_beta_briefing(str(db_path), provider=FakeBetaProvider(), today=date(2026, 5, 30))

    assert result.summary == "Recent spending is led by groceries."
    assert result.context["tools"][0] == "budgify.profile_summary"
    assert result.citations
    assert result.insights[0].citationIds == [result.citations[0].id]
    assert result.estimated is False
    assert result.sessionCost["model"] == "zai-glm-4.7"
    assert result.sessionCost["totalTokens"] == 70


def test_beta_briefing_cache_skips_llm_until_transactions_change(tmp_path):
    clear_beta_cache()
    db_path = tmp_path / "txs.db"
    _seed_beta_transactions(db_path)
    provider = FakeBetaProvider()

    first = generate_beta_briefing(str(db_path), provider=provider, today=date(2026, 5, 30))
    second = generate_beta_briefing(str(db_path), provider=provider, today=date(2026, 5, 30))

    assert first.summary == second.summary
    assert provider.calls == 1
    assert second.cacheHit is True
    assert second.sessionCost["cached"] is True

    append_transactions(
        [Transaction(date=date(2026, 5, 12), description="Groceries", merchant="Fresh Market", amount=12.0, provider="amex")],
        str(db_path),
        {"groceries": ["Fresh"]},
    )
    generate_beta_briefing(str(db_path), provider=provider, today=date(2026, 5, 30))

    assert provider.calls == 2


def test_beta_ask_cache_includes_question_and_transactions(tmp_path):
    clear_beta_cache()
    db_path = tmp_path / "txs.db"
    _seed_beta_transactions(db_path)
    provider = FakeBetaProvider()

    ask_beta_question(str(db_path), "Why was spending high?", provider=provider, today=date(2026, 5, 30))
    ask_beta_question(str(db_path), "Why was spending high?", provider=provider, today=date(2026, 5, 30))
    ask_beta_question(str(db_path), "What subscriptions should I cancel?", provider=provider, today=date(2026, 5, 30))

    assert provider.calls == 2


def test_beta_ask_rejects_empty_question(tmp_path):
    with pytest.raises(ValueError):
        ask_beta_question(str(tmp_path / "txs.db"), " ")


def test_beta_parser_schema_rejects_unknown_citation_ids():
    lookup = {
        "tx-1": BetaCitation(
            id="tx-1",
            date="2026-05-02",
            merchant="Fresh Market",
            amount=85.0,
            amountCents=8500,
            category="groceries",
        )
    }

    parsed = parse_beta_response(
        {
            "summary": "Grounded summary.",
            "insights": [{"title": "One", "body": "Body", "citationIds": ["tx-1", "tx-2"]}],
            "recommendations": [{"title": "Do", "body": "Body", "citationIds": ["tx-2"]}],
            "citations": ["tx-2"],
        },
        lookup,
    )

    assert parsed["citationIds"] == ["tx-1"]
    assert parsed["insights"][0].citationIds == ["tx-1"]
    assert parsed["recommendations"][0].citationIds == []


def test_mcp_beta_summary_and_recurring_tools(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_beta_transactions(db_path)

    summary = _spend_summary_impl(str(db_path), "2026-03-01", "2026-05-31", "merchant")
    recurring = _recurring_impl(str(db_path), "2026-03-01", "2026-05-31", minOccurrences=3)

    assert summary["count"] == 5
    assert any(item["label"] == "Fresh Market" for item in summary["groups"])
    assert recurring["items"][0]["merchant"] == "StreamFlix"


def test_beta_routes_do_not_replace_classic_route(tmp_path, monkeypatch):
    db_path = tmp_path / "txs.db"
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<div id='root'>classic</div>", encoding="utf-8")
    monkeypatch.setattr(
        web,
        "generate_beta_briefing",
        lambda path: generate_beta_briefing(path, provider=FakeBetaProvider(), today=date(2026, 5, 30)),
    )
    _seed_beta_transactions(db_path)
    handler = type(
        "TestHandler",
        (web.BudgifyWebHandler,),
        {"db_path": str(db_path), "static_dir": static_dir, "password_file": None},
    )
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/") as resp:
            classic = resp.read().decode("utf-8")
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/beta") as resp:
            beta_shell = resp.read().decode("utf-8")
        with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/beta/briefing") as resp:
            beta_payload = json.load(resp)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert classic == "<div id='root'>classic</div>"
    assert beta_shell == classic
    assert beta_payload["summary"] == "Recent spending is led by groceries."
