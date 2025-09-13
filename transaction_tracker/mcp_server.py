from __future__ import annotations

import anyio
from dataclasses import asdict
from datetime import date
from mcp.server.fastmcp import FastMCP

from transaction_tracker.database import fetch_transactions

server = FastMCP(name="Budgify", instructions="Expose Budgify as an MCP tool")

CATEGORIES = ["subscription", "car", "misc", "restaurants", "groceries", "communications", "charity", "learning", "commute", "insurance", "medical", "fun"]


@server.tool(name="get_categories", description="List available transaction categories")
async def get_categories() -> list[str]:
    return CATEGORIES


@server.tool(name="get_transactions", description="Fetch transactions from the SQLite database")
async def get_transactions(
    db_path: str,
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
    merchant_regex: str | None = None,
) -> dict:
    """Return transactions and total amount from ``db_path``.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    start_date, end_date:
        Optional ISO formatted date strings bounding the query.
    category:
        Optional category name to filter transactions.
    merchant_regex:
        Optional regular expression to match merchant names.
    """

    def _run() -> dict:
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None
        txs = fetch_transactions(
            db_path,
            start,
            end,
            category=category,
            merchant_regex=merchant_regex,
        )
        data = [asdict(t) for t in txs]
        total = sum(t.amount for t in txs)
        return {"transactions": data, "total": total}

    return await anyio.to_thread.run_sync(_run)


@server.tool(
    name="get_transactions_by_category_month",
    description="Fetch transactions for a category grouped by month",
)
async def get_transactions_by_category_month(db_path: str, category: str) -> dict:
    """Return transactions grouped by ``YYYY-MM`` for the given category."""

    def _run() -> dict:
        txs = fetch_transactions(db_path, category=category)
        result: dict[str, dict] = {}
        for t in txs:
            key = t.date.strftime("%Y-%m")
            bucket = result.setdefault(key, {"transactions": [], "total": 0.0})
            bucket["transactions"].append(asdict(t))
            bucket["total"] += t.amount
        return result

    return await anyio.to_thread.run_sync(_run)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
