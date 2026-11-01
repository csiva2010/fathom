#!/usr/bin/env bash
# Convenience launcher: starts the Node.js trading bot backend and the Vite
# dev server together, and stops both on Ctrl-C. See README.md for one-time
# setup.
set -euo pipefail
cd "$(dirname "$0")"

cleanup() {
  echo "Stopping…"
  kill "${BACKEND_PID:-0}" "${FRONTEND_PID:-0}" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Starting frontend on http://127.0.0.1:5174 …"
(cd frontend && npm run build && npm run dev) &
FRONTEND_PID=$!

echo "Starting backend on http://127.0.0.1:8001 …"
(cd backend && .venv/bin/python -m scripts.run_api ) & 
BACKEND_PID=$!


wait