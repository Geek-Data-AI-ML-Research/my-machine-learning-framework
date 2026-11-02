"""CLI entry: ``python -m mymlfw.mcp`` or ``mymlfw-mcp``."""

from __future__ import annotations

import argparse

from mymlfw.mcp.server import main as run_mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="mymlfw Campaign MCP server (B2 PAT)")
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http", "sse"),
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host")
    parser.add_argument("--port", type=int, default=8100, help="HTTP bind port")
    args = parser.parse_args(argv)
    run_mcp(transport=args.transport, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
