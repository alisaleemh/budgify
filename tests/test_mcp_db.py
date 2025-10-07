from datetime import date

import anyio
import pytest

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

    all_rows = anyio.run(get_transactions, str(db_path))
    assert len(all_rows) == 2
    assert all_rows[0]["description"] == "Coffee"

    filtered = anyio.run(get_transactions, str(db_path), "2025-05-02")
    assert len(filtered) == 1
    assert filtered[0]["merchant"] == "Store"


def test_get_transactions_no_results(tmp_path):
    db_path = tmp_path / "txs.db"
    txs = [
        Transaction(date(2025, 5, 1), "Coffee", "Cafe", 3.5),
        Transaction(date(2025, 5, 2), "Book", "Store", 12.0),
    ]
    append_transactions(txs, str(db_path))

    empty = anyio.run(get_transactions, str(db_path), "2024-01-01", "2024-01-31")
    assert empty == []


def test_get_transactions_bad_input(tmp_path):
    db_path = tmp_path / "txs.db"

    with pytest.raises(ValueError, match="Invalid start_date"):
        anyio.run(get_transactions, str(db_path), "not-a-date")

    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        anyio.run(get_transactions, str(db_path), "2025-05-02", "2025-05-01")
