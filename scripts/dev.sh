#!/usr/bin/env bash
# Starts the backend (http://localhost:8000) and the dashboard (http://localhost:5173). Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$HOME/vibeapping/env.sh" ] && source "$HOME/vibeapping/env.sh"
[ -n "${ANDROID_HOME:-}" ] || { echo "ANDROID_HOME is not set. Run: bash scripts/setup.sh" >&2; exit 1; }

if [ ! -d "$ROOT/dashboard/node_modules" ]; then
    echo "Installing dashboard dependencies..."
    (cd "$ROOT/dashboard" && npm install)
fi

(cd "$ROOT/backend" && exec uv run uvicorn vibe.api:app --port 8000) &
BACKEND=$!
(cd "$ROOT/dashboard" && exec npm run dev) &
DASHBOARD=$!
stop() { kill "$BACKEND" "$DASHBOARD" 2>/dev/null; wait "$BACKEND" "$DASHBOARD" 2>/dev/null || true; }
trap 'stop; exit 0' INT TERM

echo "Backend:   http://localhost:8000"
echo "Dashboard: http://localhost:5173  (Ctrl+C to stop both)"
wait -n "$BACKEND" "$DASHBOARD" || true
stop
