import anyio
from datetime import date

from transaction_tracker.core.models import Transaction
from transaction_tracker.database import append_transactions
from transaction_tracker.mcp_server import (
    get_categories,
    get_transactions,
    get_transactions_by_category_month,
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


def test_get_transactions_filters_and_sum(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await get_transactions(
            str(db_path), category="groceries", merchant_regex="Grocery B"
        )

    res = anyio.run(run)
    assert res["total"] == 30
    assert len(res["transactions"]) == 1
    assert res["transactions"][0]["merchant"] == "Grocery B"


def test_get_transactions_sum_only(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await get_transactions(
            str(db_path), category="groceries", include_transactions=False
        )

    res = anyio.run(run)
    assert res == {"total": 40}


def test_get_transactions_by_category_month(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await get_transactions_by_category_month(str(db_path), "groceries")

    res = anyio.run(run)
    assert res == {"2025-01": 10, "2025-02": 30}
