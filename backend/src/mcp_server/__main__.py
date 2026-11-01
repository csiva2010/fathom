"""Entry point Claude Desktop runs: `python -m src.mcp_server` over stdio (MCP-03).

Stdout carries the MCP protocol, so logs go to stderr (Claude Desktop shows them in its
MCP log files).
"""

from __future__ import annotations

import logging
import sys

from src.mcp_server.api_client import ApiConfig, FinanceApi
from src.mcp_server.server import build_server


def main() -> int:
    logging.basicConfig(stream=sys.stderr, level=logging.INFO)
    try:
        config = ApiConfig.from_env()
    except ValueError as error:
        print(f"finance-assistant MCP server: {error}", file=sys.stderr)
        return 2
    build_server(FinanceApi(config)).run("stdio")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
