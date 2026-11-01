"""Write the OpenAPI schema to a file so the frontend can generate typed API clients.

Usage (from backend/):  python -m scripts.export_openapi ../frontend/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from src.web_app.main import create_app


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    target = Path(args[0] if args else "openapi.json")
    schema = create_app().openapi()
    target.write_text(json.dumps(schema, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {target} ({len(schema['paths'])} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
