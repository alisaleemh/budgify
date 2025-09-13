import sqlite3
from pathlib import Path
from datetime import date
from typing import Iterable, List

from transaction_tracker.core.models import Transaction
from transaction_tracker.core.categorizer import categorize


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY,
            date TEXT NOT NULL,
            description TEXT NOT NULL,
            merchant TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            UNIQUE(date, description, merchant, amount)
        )
        """
    )
    conn.commit()


def append_transactions(
    transactions: Iterable[Transaction],
    db_path: str,
    categories: dict | None = None,
) -> None:
    """Persist transactions into a SQLite database.

    Parameters
    ----------
    transactions:
        Iterable of Transaction objects to store.
    db_path:
        Path to the SQLite database file.
    categories:
        Mapping of category names to keyword lists for auto-categorization.
    """
    if not transactions:
        return

    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        _init_db(conn)
        cat_map = categories or {}
        rows = []
        for tx in transactions:
            cat = categorize(tx, cat_map)
            rows.append(
                (
                    tx.date.isoformat(),
                    tx.description.strip(),
                    tx.merchant.strip(),
                    float(tx.amount),
                    cat,
                )
            )
        conn.executemany(
            """
            INSERT OR IGNORE INTO transactions
            (date, description, merchant, amount, category)
            VALUES (?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def fetch_transactions(
    db_path: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> List[Transaction]:
    """Retrieve transactions from a SQLite database.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    start_date:
        Optional start date to filter transactions (inclusive).
    end_date:
        Optional end date to filter transactions (inclusive).
    """
    conn = sqlite3.connect(db_path)
    try:
        query = (
            "SELECT date, description, merchant, amount, category FROM transactions"
        )
        params: list[str] = []
        conditions: list[str] = []
        if start_date:
            conditions.append("date >= ?")
            params.append(start_date.isoformat())
        if end_date:
            conditions.append("date <= ?")
            params.append(end_date.isoformat())
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY date"
        rows = conn.execute(query, params).fetchall()
        return [
            Transaction(
                date=date.fromisoformat(r[0]),
                description=r[1],
                merchant=r[2],
                amount=float(r[3]),
                category=r[4],
            )
            for r in rows
        ]
    finally:
        conn.close()
