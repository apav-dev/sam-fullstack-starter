#!/usr/bin/env bash
# Local development: FastAPI on :8000 (in-memory db — no AWS needed) and
# Vite dev server on :5173 (proxies /api → :8000).
#
# Run this, then in a second terminal:  cd frontend && pnpm dev
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "API → http://localhost:8000   (frontend: cd frontend && pnpm dev → http://localhost:5173)"
uv run uvicorn api.main:app --reload --port 8000
