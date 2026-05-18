import anyio
from datetime import date

from transaction_tracker.core.models import Transaction
from transaction_tracker.database import append_transactions
from transaction_tracker.mcp_server import (
    analyze_category_spend,
    budgify_compare_periods,
    budgify_find_transactions,
    budgify_health,
    budgify_insight_context,
    budgify_profile_summary,
    budgify_query_bundle,
    budgify_spend_summary,
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


def test_analyze_category_spend(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await analyze_category_spend(
            str(db_path),
            category="groceries",
            top_merchants=3,
            top_transactions=2,
        )

    result = anyio.run(run)
    assert result["category"] == "groceries"
    assert result["total"] == 40.0
    assert result["transactions"] == 2
    assert result["average_transaction"] == 20.0

    merchants = result["merchants"]
    assert [m["merchant"] for m in merchants] == ["Grocery B", "Grocery A"]
    assert merchants[0]["total"] == 30.0
    assert merchants[0]["spend_share"] == 0.75

    assert result["monthly_trends"] == [
        {"period": "2025-01", "total": 10.0, "transactions": 1},
        {"period": "2025-02", "total": 30.0, "transactions": 1},
    ]

    top_tx = result["top_transactions"]
    assert len(top_tx) == 2
    assert top_tx[0] == {
        "date": "2025-02-05",
        "merchant": "Grocery B",
        "amount": 30.0,
    }

    opp_types = {item["type"] for item in result["optimization_opportunities"]}
    assert "merchant_concentration" in opp_types
    assert "recent_spike" in opp_types


def test_budgify_health_and_profile(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await budgify_health(str(db_path)), await budgify_profile_summary(str(db_path))

    health, profile = anyio.run(run)
    assert health["ok"] is True
    assert health["db"] == "ok"
    assert "spend_summary" in health["capabilities"]
    assert profile["transactionCount"] == 4
    assert profile["categoryCount"] == 2
    assert profile["merchantCount"] == 4


def test_budgify_spend_summary_compact(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await budgify_spend_summary(
            str(db_path),
            startDate="2025-01-01",
            endDate="2025-02-28",
            groupBy="category",
            includeComparison={"mode": "previous_period"},
            limit=10,
        )

    result = anyio.run(run)
    lookup = {item["label"]: item for item in result["groups"]}
    assert result["totalCents"] == 8500
    assert lookup["restaurants"]["totalCents"] == 4500
    assert "deltaCents" in lookup["restaurants"]


def test_budgify_find_transactions_limit_cursor_fields(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        first = await budgify_find_transactions(
            str(db_path),
            startDate="2025-01-01",
            endDate="2025-02-28",
            limit=2,
            fields=["id", "date", "amountCents"],
        )
        second = await budgify_find_transactions(
            str(db_path),
            startDate="2025-01-01",
            endDate="2025-02-28",
            limit=2,
            cursor=first["nextCursor"],
            fields=["id", "date", "amountCents"],
        )
        invalid = await budgify_find_transactions(
            str(db_path),
            startDate="2025-01-01",
            endDate="2025-02-28",
            limit=500,
            fields=["secret"],
        )
        return first, second, invalid

    first, second, invalid = anyio.run(run)
    assert len(first["items"]) == 2
    assert first["nextCursor"] == "2"
    assert len(second["items"]) == 2
    assert set(first["items"][0]) == {"id", "date", "amountCents"}
    assert invalid["error"]["code"] == "INVALID_FIELDS"


def test_budgify_compare_periods(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await budgify_compare_periods(
            str(db_path),
            periodA={"startDate": "2025-02-01", "endDate": "2025-02-28"},
            periodB={"startDate": "2025-01-01", "endDate": "2025-01-31"},
            groupBy="category",
        )

    result = anyio.run(run)
    assert result["periodA"]["totalCents"] == 5500
    assert result["periodB"]["totalCents"] == 3000
    assert result["deltaCents"] == 2500
    assert result["topDrivers"]


def test_budgify_query_bundle_max_subqueries(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        ok = await budgify_query_bundle(
            str(db_path),
            queries=[
                {
                    "id": "jan",
                    "tool": "spend_summary",
                    "args": {"startDate": "2025-01-01", "endDate": "2025-01-31", "groupBy": "category"},
                }
            ],
        )
        too_many = await budgify_query_bundle(
            str(db_path),
            queries=[{"id": str(idx), "tool": "spend_summary", "args": {}} for idx in range(6)],
        )
        return ok, too_many

    ok, too_many = anyio.run(run)
    assert ok["results"]["jan"]["totalCents"] == 3000
    assert too_many["error"]["code"] == "TOO_MANY_QUERIES"


def test_budgify_insight_context_compact(tmp_path):
    db_path = _setup_db(tmp_path)

    async def run():
        return await budgify_insight_context(
            str(db_path),
            startDate="2025-02-01",
            endDate="2025-02-28",
            include=["totals", "top_categories", "drivers"],
            limits={"topCategories": 2, "drivers": 2},
        )

    result = anyio.run(run)
    assert "topCategories" in result
    assert len(result["topCategories"]) <= 2
    assert "drivers" in result
    assert "transactions" not in result
