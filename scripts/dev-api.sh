#!/bin/sh
set -eu

cd "$(dirname "$0")/.."
uv run --project apps/api alembic -c apps/api/alembic.ini upgrade head
uv run --project apps/api uvicorn skysort_api.main:app --app-dir apps/api/src --reload --port 8000
