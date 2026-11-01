"""Start the API on API_PORT from .env (default 8000).

Usage (from backend/):  python -m scripts.run_api [--no-reload]
"""

from __future__ import annotations

import argparse

import uvicorn

from src.core.config import get_settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-reload", action="store_true", help="disable auto-reload")
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args(argv)

    settings = get_settings()
    print(f"API on http://{args.host}:{settings.api_port}")
    print(f"Web app expected at {settings.app.frontend_url}")
    uvicorn.run(
        "src.web_app.main:app",
        host=args.host,
        port=settings.api_port,
        reload=not args.no_reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
