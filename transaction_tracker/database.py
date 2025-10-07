import sqlite3
import re
from collections import defaultdict
from pathlib import Path
from datetime import date
from typing import Dict, Iterable, List, Literal, Tuple

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


def _summarize_range(
    conn: sqlite3.Connection,
    start_date: date | None,
    end_date: date | None,
    category: str | None,
) -> Tuple[float, int]:
    """Return the total spend and transaction count for a date range."""

    where, params = _build_filters(start_date, end_date, category)
    row = conn.execute(
        f"""
        SELECT COALESCE(SUM(amount), 0.0) AS total,
               COUNT(*) AS count
        FROM transactions
        {where}
        """,
        params,
    ).fetchone()
    total = float(row[0] or 0.0)
    count = int(row[1] or 0)
    return total, count


def compare_spend_between_periods(
    db_path: str,
    first_start: date | None,
    first_end: date | None,
    second_start: date | None,
    second_end: date | None,
    category: str | None = None,
) -> Dict[str, object]:
    """Compare total spend between two date ranges.

    The function returns totals for each range, the absolute difference between
    them (second minus first) and a percent change when the first total is not
    zero. When *category* is omitted all transactions are considered.
    """

    conn = sqlite3.connect(db_path)
    try:
        first_total, first_count = _summarize_range(
            conn, first_start, first_end, category
        )
        second_total, second_count = _summarize_range(
            conn, second_start, second_end, category
        )

        diff = second_total - first_total
        pct_change = diff / first_total if first_total else None

        return {
            "category": category,
            "first_period": {
                "start": first_start.isoformat() if first_start else None,
                "end": first_end.isoformat() if first_end else None,
                "total": first_total,
                "transactions": first_count,
            },
            "second_period": {
                "start": second_start.isoformat() if second_start else None,
                "end": second_end.isoformat() if second_end else None,
                "total": second_total,
                "transactions": second_count,
            },
            "difference": diff,
            "percent_change": pct_change,
        }
    finally:
        conn.close()


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


def category_insights(
    db_path: str,
    category: str,
    start_date: date | None = None,
    end_date: date | None = None,
    *,
    top_merchants: int = 5,
    top_transactions: int = 5,
    max_periods: int = 12,
    max_opportunities: int = 3,
) -> Dict[str, object]:
    """Return a compact analysis for a specific spending category.

    The result focuses on aggregate metrics, merchant concentration, simple
    monthly trends and a minimal set of notable transactions so the response
    remains small enough for LLM consumption.
    """

    if not category:
        raise ValueError("category must be provided for category_insights")

    conn = sqlite3.connect(db_path)
    try:
        where, params = _build_filters(start_date, end_date, category)
        params_list = list(params)

        total_row = conn.execute(
            f"""
            SELECT COALESCE(SUM(amount), 0.0) AS total,
                   COUNT(*) AS count,
                   COALESCE(AVG(amount), 0.0) AS average
            FROM transactions
            {where}
            """,
            params_list,
        ).fetchone()

        total = float(total_row[0] or 0.0)
        count = int(total_row[1] or 0)
        average = float(total_row[2] or 0.0) if count else 0.0

        merchant_rows = conn.execute(
            f"""
            SELECT merchant,
                   SUM(amount) AS total,
                   COUNT(*) AS count
            FROM transactions
            {where}
            GROUP BY merchant
            ORDER BY total DESC
            LIMIT ?
            """,
            params_list + [top_merchants],
        ).fetchall()

        merchants = [
            {
                "merchant": row[0],
                "total": float(row[1] or 0.0),
                "transactions": int(row[2] or 0),
                "spend_share": (float(row[1] or 0.0) / total) if total else 0.0,
            }
            for row in merchant_rows
        ]

        month_rows = conn.execute(
            f"""
            SELECT {_PERIOD_EXPRESSIONS['month']} AS period,
                   SUM(amount) AS total,
                   COUNT(*) AS count
            FROM transactions
            {where}
            GROUP BY period
            ORDER BY period
            """,
            params_list,
        ).fetchall()

        monthly_trends = [
            {
                "period": row[0],
                "total": float(row[1] or 0.0),
                "transactions": int(row[2] or 0),
            }
            for row in month_rows
        ]
        if max_periods > 0:
            monthly_trends = monthly_trends[-max_periods:]

        transaction_rows = conn.execute(
            f"""
            SELECT date, merchant, amount
            FROM transactions
            {where}
            ORDER BY amount DESC
            LIMIT ?
            """,
            params_list + [top_transactions],
        ).fetchall()

        top_tx = [
            {
                "date": row[0],
                "merchant": row[1],
                "amount": float(row[2] or 0.0),
            }
            for row in transaction_rows
        ]

        opportunities: List[Dict[str, object]] = []
        if total > 0 and merchants:
            dominant = merchants[0]
            if dominant["spend_share"] >= 0.3:
                opportunities.append(
                    {
                        "type": "merchant_concentration",
                        "merchant": dominant["merchant"],
                        "spend_share": round(dominant["spend_share"], 4),
                        "message": (
                            f"{dominant['merchant']} accounts for "
                            f"{dominant['spend_share'] * 100:.1f}% of {category} "
                            "spend. Review recurring charges or alternative providers."
                        ),
                    }
                )

            high_freq = max(merchants, key=lambda item: item["transactions"])
            if high_freq["transactions"] >= 3 and high_freq["transactions"] >= max(1, int(count * 0.4)):
                opportunities.append(
                    {
                        "type": "high_frequency_merchant",
                        "merchant": high_freq["merchant"],
                        "transactions": high_freq["transactions"],
                        "message": (
                            f"{high_freq['merchant']} appears {high_freq['transactions']} times. "
                            "Consider batching purchases or checking for unnecessary repeats."
                        ),
                    }
                )

        if len(monthly_trends) > 1 and total > 0:
            recent = monthly_trends[-1]
            avg_monthly = total / len(monthly_trends)
            if avg_monthly and recent["total"] > avg_monthly * 1.2:
                opportunities.append(
                    {
                        "type": "recent_spike",
                        "period": recent["period"],
                        "total": recent["total"],
                        "average": round(avg_monthly, 2),
                        "message": (
                            f"Spending in {recent['period']} ({recent['total']:.2f}) "
                            f"exceeds the {avg_monthly:.2f} monthly average. Investigate recent changes."
                        ),
                    }
                )

        if max_opportunities > 0:
            opportunities = opportunities[:max_opportunities]

        return {
            "category": category,
            "total": total,
            "transactions": count,
            "average_transaction": average,
            "merchants": merchants,
            "monthly_trends": monthly_trends,
            "top_transactions": top_tx,
            "optimization_opportunities": opportunities,
        }
    finally:
        conn.close()
