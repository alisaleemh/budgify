from __future__ import annotations

import anyio
from mcp.server.fastmcp import FastMCP

from transaction_tracker.cli import main as cli

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


def main() -> None:
    server.run()


if __name__ == "__main__":
    main()
