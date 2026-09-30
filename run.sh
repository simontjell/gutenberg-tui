#!/usr/bin/env bash
# Start gutenberg-tui. Requires uv (https://docs.astral.sh/uv/).
set -euo pipefail
cd "$(dirname "$0")"
exec uv run gutenberg-tui "$@"
