#!/usr/bin/env bash
set -e

cd "$(dirname "$0")/backend"
exec uv run python src/main.py
