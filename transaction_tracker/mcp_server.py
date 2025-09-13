from __future__ import annotations

import anyio
from mcp.server.fastmcp import FastMCP

from dataclasses import asdict
from datetime import date

from transaction_tracker.cli import main as cli
from transaction_tracker.database import fetch_transactions

server = FastMCP(name="Budgify", instructions="Expose Budgify as an MCP tool")

@server.tool(name="run_budgify", description="Process statements using Budgify")
async def run_budgify(
    statements_dir: str,
    output_format: str = "csv",
    include_payments: bool = False,
    config_path: str = "config.yaml",
    manual_file: str | None = None,
    env_file: str | None = None,
    ai_report: bool = False,
) -> str:
    def _run() -> None:
        cli.callback(
            statements_dir,
            output_format,
            include_payments,
            config_path,
            manual_file,
            env_file,
            ai_report,
        )

    await anyio.to_thread.run_sync(_run)
    return "Completed"


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

    def _run() -> list[dict]:
        start = date.fromisoformat(start_date) if start_date else None
        end = date.fromisoformat(end_date) if end_date else None
        txs = fetch_transactions(db_path, start, end)
        return [asdict(t) for t in txs]

    return await anyio.to_thread.run_sync(_run)


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
