import sqlite3
import re
from collections import defaultdict
from pathlib import Path
from datetime import date
from typing import Dict, Iterable, List, Literal

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
    category: str | None = None,
    merchant_regex: str | None = None,
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
    category:
        Optional category name to filter transactions.
    merchant_regex:
        Optional regular expression to match merchant names.
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
        if category:
            conditions.append("category = ?")
            params.append(category)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY date"
        rows = conn.execute(query, params).fetchall()
        txs = [
            Transaction(
                date=date.fromisoformat(r[0]),
                description=r[1],
                merchant=r[2],
                amount=float(r[3]),
                category=r[4],
            )
            for r in rows
        ]
        if merchant_regex:
            pattern = re.compile(merchant_regex, re.IGNORECASE)
            txs = [t for t in txs if pattern.search(t.merchant)]
        return txs
    finally:
        conn.close()


def _build_filters(
    start_date: date | None,
    end_date: date | None,
    category: str | None,
) -> tuple[str, list[str]]:
    conditions: list[str] = []
    params: list[str] = []
    if start_date:
        conditions.append("date >= ?")
        params.append(start_date.isoformat())
    if end_date:
        conditions.append("date <= ?")
        params.append(end_date.isoformat())
    if category:
        conditions.append("category = ?")
        params.append(category)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    return where, params


def summarize_by_category(
    db_path: str,
    start_date: date | None = None,
    end_date: date | None = None,
) -> List[Dict[str, object]]:
    """Aggregate spend totals grouped by category."""

    conn = sqlite3.connect(db_path)
    try:
        where, params = _build_filters(start_date, end_date, None)
        rows = conn.execute(
            f"""
            SELECT COALESCE(category, 'uncategorized') AS category,
                   SUM(amount) AS total,
                   COUNT(*) AS count
            FROM transactions
            {where}
            GROUP BY COALESCE(category, 'uncategorized')
            ORDER BY total DESC
            """,
            params,
        ).fetchall()
        return [
            {
                "category": row[0],
                "total": float(row[1] or 0.0),
                "transactions": int(row[2]),
            }
            for row in rows
        ]
    finally:
        conn.close()


_PERIOD_EXPRESSIONS: Dict[str, str] = {
    "month": "strftime('%Y-%m', date)",
    "quarter": (
        "printf('%s-Q%d', strftime('%Y', date), "
        "((CAST(strftime('%m', date) AS INTEGER) - 1) / 3) + 1)"
    ),
    "year": "strftime('%Y', date)",
}


def summarize_by_period(
    db_path: str,
    period: Literal["month", "quarter", "year"],
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
) -> List[Dict[str, object]]:
    """Aggregate spend totals grouped by a given time period."""

    expr = _PERIOD_EXPRESSIONS[period]
    conn = sqlite3.connect(db_path)
    try:
        where, params = _build_filters(start_date, end_date, category)
        rows = conn.execute(
            f"""
            SELECT {expr} AS period,
                   SUM(amount) AS total,
                   COUNT(*) AS count
            FROM transactions
            {where}
            GROUP BY period
            ORDER BY period
            """,
            params,
        ).fetchall()
        return [
            {
                "period": row[0],
                "total": float(row[1] or 0.0),
                "transactions": int(row[2]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def summarize_by_merchant(
    db_path: str,
    start_date: date | None = None,
    end_date: date | None = None,
    category: str | None = None,
) -> List[Dict[str, object]]:
    """Aggregate spend totals grouped by merchant."""

    conn = sqlite3.connect(db_path)
    try:
        where, params = _build_filters(start_date, end_date, category)
        rows = conn.execute(
            f"""
            SELECT merchant,
                   SUM(amount) AS total,
                   COUNT(*) AS count
            FROM transactions
            {where}
            GROUP BY merchant
            ORDER BY total DESC
            """,
            params,
        ).fetchall()
        return [
            {
                "merchant": row[0],
                "total": float(row[1] or 0.0),
                "transactions": int(row[2]),
            }
            for row in rows
        ]
    finally:
        conn.close()


def list_unique_merchants(db_path: str) -> List[Dict[str, object]]:
    """Return merchants and the categories they appear in."""

    conn = sqlite3.connect(db_path)
    try:
        rows = conn.execute(
            """
            SELECT DISTINCT merchant, COALESCE(category, 'uncategorized')
            FROM transactions
            ORDER BY merchant
            """
        ).fetchall()
    finally:
        conn.close()

    categories_by_merchant: Dict[str, set[str]] = defaultdict(set)
    for merchant, category in rows:
        if category:
            categories_by_merchant[merchant].add(category)
    return [
        {
            "merchant": merchant,
            "categories": sorted(categories),
        }
        for merchant, categories in categories_by_merchant.items()
    ]
