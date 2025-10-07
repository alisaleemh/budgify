import anyio
from datetime import date

from transaction_tracker.core.models import Transaction
from transaction_tracker.database import append_transactions
from transaction_tracker.mcp_server import (
    get_categories,
    list_unique_merchants_tool,
    summarize_spend_by_category,
    summarize_spend_by_merchant,
    summarize_spend_by_period,
)


def _setup_db(tmp_path):
    db_path = tmp_path / "tx.db"
    txs = [
        Transaction(date(2025, 1, 10), "Grocery A", "Grocery A", 10),
        Transaction(date(2025, 1, 15), "Restaurant X", "Restaurant X", 20),
        Transaction(date(2025, 2, 5), "Grocery B", "Grocery B", 30),
        Transaction(date(2025, 2, 10), "Restaurant Y", "Restaurant Y", 25),
    ]
    categories = {"groceries": ["grocery"], "restaurants": ["restaurant"]}
    append_transactions(txs, db_path, categories)
    return db_path


def test_get_categories():
    cats = anyio.run(get_categories)
    assert "groceries" in cats
    assert "restaurants" in cats


def test_summarize_spend_by_category(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await summarize_spend_by_category(str(db_path))

    res = anyio.run(run)
    groceries = next(item for item in res if item["category"] == "groceries")
    restaurants = next(item for item in res if item["category"] == "restaurants")
    assert groceries == {"category": "groceries", "total": 40.0, "transactions": 2}
    assert restaurants == {
        "category": "restaurants",
        "total": 45.0,
        "transactions": 2,
    }


def test_summarize_spend_by_period_month_filter(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await summarize_spend_by_period(
            str(db_path), period="month", category="groceries"
        )

    res = anyio.run(run)
    assert res == [
        {"period": "2025-01", "total": 10.0, "transactions": 1},
        {"period": "2025-02", "total": 30.0, "transactions": 1},
    ]


def test_summarize_spend_by_period_quarter(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await summarize_spend_by_period(str(db_path), period="quarter")

    res = anyio.run(run)
    assert res == [
        {"period": "2025-Q1", "total": 85.0, "transactions": 4},
    ]


def test_summarize_spend_by_merchant(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await summarize_spend_by_merchant(str(db_path))

    res = anyio.run(run)
    assert any(item["merchant"] == "Grocery B" and item["total"] == 30.0 for item in res)
    assert any(item["merchant"] == "Restaurant X" and item["transactions"] == 1 for item in res)


def test_list_unique_merchants(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await list_unique_merchants_tool(str(db_path))

    res = anyio.run(run)
    lookup = {item["merchant"]: item for item in res}
    assert lookup["Grocery A"] == {"merchant": "Grocery A", "categories": ["groceries"]}
    assert lookup["Restaurant Y"] == {
        "merchant": "Restaurant Y",
        "categories": ["restaurants"],
    }
