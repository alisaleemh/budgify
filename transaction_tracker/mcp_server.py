from __future__ import annotations

import anyio
from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP

from transaction_tracker.database import (
    list_unique_merchants,
    summarize_by_category,
    summarize_by_merchant,
    summarize_by_period,
)

server = FastMCP(name="Budgify", instructions="Expose Budgify as an MCP tool")

CATEGORIES = [
    "subscription",
    "car",
    "misc",
    "restaurants",
    "groceries",
    "communications",
    "charity",
    "learning",
    "commute",
    "insurance",
    "medical",
    "fun",
]


def _parse_date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


@server.tool(name="get_categories", description="List available transaction categories")
async def get_categories() -> list[str]:
    return CATEGORIES


@server.tool(
    name="summarize_spend_by_category",
    description="Total spending grouped by category",
)
async def summarize_spend_by_category(
    db_path: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    def _run() -> list[dict]:
        return summarize_by_category(
            db_path,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
        )

    return await anyio.to_thread.run_sync(_run)


@server.tool(
    name="summarize_spend_by_period",
    description="Total spending grouped by month, quarter, or year",
)
async def summarize_spend_by_period(
    db_path: str,
    period: Literal["month", "quarter", "year"],
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
) -> list[dict]:
    def _run() -> list[dict]:
        return summarize_by_period(
            db_path,
            period=period,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            category=category,
        )

    return await anyio.to_thread.run_sync(_run)


@server.tool(
    name="summarize_spend_by_merchant",
    description="Total spending grouped by merchant",
)
async def summarize_spend_by_merchant(
    db_path: str,
    start_date: str | None = None,
    end_date: str | None = None,
    category: str | None = None,
) -> list[dict]:
    def _run() -> list[dict]:
        return summarize_by_merchant(
            db_path,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            category=category,
        )

    return await anyio.to_thread.run_sync(_run)


@server.tool(
    name="list_unique_merchants",
    description="List merchants and the categories they appear in",
)
async def list_unique_merchants_tool(db_path: str) -> list[dict]:
    def _run() -> list[dict]:
        return list_unique_merchants(db_path)

    return await anyio.to_thread.run_sync(_run)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
