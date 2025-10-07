from __future__ import annotations

import anyio
from mcp.server.fastmcp import FastMCP

from dataclasses import asdict
from datetime import date

from pathlib import Path

from transaction_tracker.database import fetch_transactions

server = FastMCP(name="Budgify", instructions="Expose Budgify as an MCP tool")

@server.tool(
    name="get_transactions", description="Fetch transactions from the SQLite database"
)
async def get_transactions(
    db_path: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> list[dict]:
    """Return a list of transactions from ``db_path``.

    Parameters
    ----------
    db_path:
        Path to the SQLite database file.
    start_date, end_date:
        Optional ISO formatted date strings bounding the query.
    """

    try:
        start = date.fromisoformat(start_date) if start_date else None
    except ValueError as exc:
        raise ValueError(f"Invalid start_date: {start_date}") from exc

    try:
        end = date.fromisoformat(end_date) if end_date else None
    except ValueError as exc:
        raise ValueError(f"Invalid end_date: {end_date}") from exc

    if start and end and start > end:
        raise ValueError("start_date must be on or before end_date")

    if not Path(db_path).exists():
        raise FileNotFoundError(f"Database not found: {db_path}")

    def _run() -> list[dict]:
        txs = fetch_transactions(db_path, start, end)
        return [asdict(t) for t in txs]

    return await anyio.to_thread.run_sync(_run)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
