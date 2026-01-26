from __future__ import annotations

import anyio
from datetime import date
from typing import Literal

from mcp.server.fastmcp import FastMCP

from transaction_tracker.database import (
    category_insights,
    compare_spend_between_periods,
    list_unique_merchants,
    summarize_by_category,
    summarize_by_merchant,
    summarize_by_period,
)

server = FastMCP(
    name="Budgify",
    instructions=(
        "Budgify MCP server for querying transaction data.\n"
        "Use ISO-8601 dates (YYYY-MM-DD) for every date argument; ranges are inclusive.\n"
        "Valid `period` values are `month`, `quarter`, or `year`.\n"
        "Examples:\n"
        "- summarize_spend_by_period(db_path, period=\"month\", start_date=\"2025-01-01\", end_date=\"2025-03-31\")\n"
        "- compare_spend_between_periods(db_path, first_start=\"2025-01-01\", first_end=\"2025-01-31\", second_start=\"2025-02-01\", second_end=\"2025-02-28\", category=\"groceries\")"
    ),
)

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


@server.tool(
    name="analyze_category_spend",
    description="Detailed analysis for a category including merchant and trend insights",
)
async def analyze_category_spend(
    db_path: str,
    category: str,
    start_date: str | None = None,
    end_date: str | None = None,
    top_merchants: int = 5,
    top_transactions: int = 5,
) -> dict:
    def _run() -> dict:
        return category_insights(
            db_path,
            category=category,
            start_date=_parse_date(start_date),
            end_date=_parse_date(end_date),
            top_merchants=top_merchants,
            top_transactions=top_transactions,
        )

    return await anyio.to_thread.run_sync(_run)


@server.tool(
    name="compare_spend_between_periods",
    description=(
        "Compare total spending between two date ranges, optionally for a specific category"
    ),
)
async def compare_spend_between_periods_tool(
    db_path: str,
    first_start: str | None,
    first_end: str | None,
    second_start: str | None,
    second_end: str | None,
    category: str | None = None,
) -> dict:
    def _run() -> dict:
        return compare_spend_between_periods(
            db_path,
            first_start=_parse_date(first_start),
            first_end=_parse_date(first_end),
            second_start=_parse_date(second_start),
            second_end=_parse_date(second_end),
            category=category,
        )

    return await anyio.to_thread.run_sync(_run)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
