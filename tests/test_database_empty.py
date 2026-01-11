from transaction_tracker.database import (
    list_categories,
    list_unique_merchants,
    overview_metrics,
    query_transactions,
    summarize_by_category,
    summarize_by_merchant,
    summarize_by_period,
)


def test_empty_db_queries(tmp_path):
    db_path = tmp_path / "empty.db"

    assert list_categories(str(db_path)) == []
    assert list_unique_merchants(str(db_path)) == []
    assert summarize_by_category(str(db_path)) == []
    assert summarize_by_period(str(db_path), period="month") == []
    assert summarize_by_merchant(str(db_path)) == []
    assert query_transactions(str(db_path)) == []

    overview = overview_metrics(str(db_path))
    assert overview["transactions"] == 0
    assert overview["total"] == 0.0
    assert overview["average"] == 0.0
    assert overview["first_date"] is None
    assert overview["last_date"] is None
