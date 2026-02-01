from datetime import date

from transaction_tracker.core.models import Transaction
from transaction_tracker.database import (
    append_transactions,
    list_categories,
    overview_metrics,
    query_transactions,
    summarize_by_category,
)


def _seed_transactions(db_path):
    categories = {
        "groceries": ["Fresh"],
        "restaurants": ["Cafe", "Bean"],
        "car": ["Shell"],
        "subscription": ["Stream"],
        "house": ["Home"],
    }
    txs = [
        Transaction(date=date(2025, 1, 5), description="Grocery run", merchant="Fresh Market", amount=45.5, provider="amex"),
        Transaction(date=date(2025, 1, 20), description="Cafe visit", merchant="Bean House", amount=12.0, provider="amex"),
        Transaction(date=date(2025, 2, 1), description="Fuel", merchant="Shell", amount=60.0, provider="tdvisa"),
        Transaction(date=date(2025, 2, 10), description="Streaming", merchant="StreamFlix", amount=15.0, provider="recurring"),
        Transaction(date=date(2025, 2, 12), description="Home repair", merchant="Home Depot", amount=210.0, provider="manual"),
    ]
    append_transactions(txs, str(db_path), categories)


def test_query_transactions_filters_and_sorting(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_transactions(db_path)

    january = query_transactions(
        str(db_path),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 1, 31),
        sort_by="date",
        sort_dir="asc",
    )
    assert [tx["merchant"] for tx in january] == ["Fresh Market", "Bean House"]

    shell = query_transactions(str(db_path), merchant="Shell")
    assert len(shell) == 1
    assert shell[0]["merchant"] == "Shell"

    min_amount = query_transactions(str(db_path), min_amount=50, sort_by="amount", sort_dir="desc")
    assert len(min_amount) == 2
    assert [tx["amount"] for tx in min_amount] == [210.0, 60.0]

    regex = query_transactions(str(db_path), merchant_regex="bean|shell", sort_by="date", sort_dir="asc")
    assert [tx["merchant"] for tx in regex] == ["Bean House", "Shell"]

    provider_rows = query_transactions(str(db_path), provider="tdvisa")
    assert len(provider_rows) == 1
    assert provider_rows[0]["merchant"] == "Shell"

    paged = query_transactions(str(db_path), sort_by="date", sort_dir="asc", limit=2, offset=1)
    assert len(paged) == 2
    assert paged[0]["merchant"] == "Bean House"


def test_overview_metrics_and_categories(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_transactions(db_path)

    overview = overview_metrics(str(db_path), start_date=date(2025, 1, 1), end_date=date(2025, 1, 31))
    assert overview["transactions"] == 2
    assert overview["total"] == 57.5
    assert overview["first_date"] == "2025-01-05"
    assert overview["last_date"] == "2025-01-20"

    regex_overview = overview_metrics(str(db_path), merchant_regex="bean|shell")
    assert regex_overview["transactions"] == 2
    assert regex_overview["total"] == 72.0

    categories = list_categories(str(db_path))
    assert "groceries" in categories
    assert "restaurants" in categories

    provider_overview = overview_metrics(str(db_path), provider="amex")
    assert provider_overview["transactions"] == 2


def test_exclude_category_filters(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_transactions(db_path)

    without_house = query_transactions(str(db_path), exclude_category="house")
    assert all(tx["category"] != "house" for tx in without_house)

    category_summary = summarize_by_category(str(db_path), exclude_category="house")
    assert all(row["category"] != "house" for row in category_summary)


def test_query_transactions_grouped_sort(tmp_path):
    db_path = tmp_path / "txs.db"
    _seed_transactions(db_path)

    grouped = query_transactions(
        str(db_path),
        sort_by="amount",
        sort_dir="desc",
        group_by="category",
    )
    categories = [tx["category"] for tx in grouped]
    assert categories == sorted(categories)
    car_rows = [tx for tx in grouped if tx["category"] == "car"]
    house_rows = [tx for tx in grouped if tx["category"] == "house"]
    assert [tx["amount"] for tx in car_rows] == sorted([tx["amount"] for tx in car_rows], reverse=True)
    assert [tx["amount"] for tx in house_rows] == sorted([tx["amount"] for tx in house_rows], reverse=True)
