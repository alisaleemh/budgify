import anyio
from datetime import date

from transaction_tracker.core.models import Transaction
from transaction_tracker.database import append_transactions
from transaction_tracker.mcp_server import get_transactions


def test_get_transactions(tmp_path):
    db_path = tmp_path / "txs.db"
    txs = [
        Transaction(date(2025, 5, 1), "Coffee", "Cafe", 3.5),
        Transaction(date(2025, 5, 2), "Book", "Store", 12.0),
    ]
    append_transactions(txs, str(db_path))

    all_rows = anyio.run(lambda: get_transactions(str(db_path)))
    assert len(all_rows["transactions"]) == 2
    assert all_rows["transactions"][0]["description"] == "Coffee"

    filtered = anyio.run(
        lambda: get_transactions(str(db_path), start_date="2025-05-02")
    )
    assert len(filtered["transactions"]) == 1
    assert filtered["transactions"][0]["merchant"] == "Store"
