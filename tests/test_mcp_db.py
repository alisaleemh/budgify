import anyio
from datetime import date

from transaction_tracker.core.models import Transaction
from transaction_tracker.database import append_transactions
from transaction_tracker.mcp_server import summarize_spend_by_category


def test_summarize_spend_by_category_respects_dates(tmp_path):
    db_path = tmp_path / "txs.db"
    txs = [
        Transaction(date(2025, 5, 1), "Coffee", "Cafe", 3.5),
        Transaction(date(2025, 5, 2), "Book", "Store", 12.0),
    ]
    append_transactions(txs, str(db_path))

    async def run_all():
        return await summarize_spend_by_category(str(db_path))

    all_rows = anyio.run(run_all)
    assert all_rows == [
        {
            "category": "misc",
            "total": 15.5,
            "transactions": 2,
        }
    ]

    async def run_filtered():
        return await summarize_spend_by_category(
            str(db_path), start_date="2025-05-02"
        )

    filtered = anyio.run(run_filtered)
    assert filtered == [
        {
            "category": "misc",
            "total": 12.0,
            "transactions": 1,
        }
    ]
