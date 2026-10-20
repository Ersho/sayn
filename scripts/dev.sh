#!/usr/bin/env bash
# Starts the backend (http://localhost:8000) and the dashboard (http://localhost:5173). Ctrl+C stops both.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[ -f "$HOME/vibeapping/env.sh" ] && source "$HOME/vibeapping/env.sh"
[ -n "${ANDROID_HOME:-}" ] || { echo "ANDROID_HOME is not set. Run: bash scripts/setup.sh" >&2; exit 1; }

node "$ROOT/scripts/check-node.mjs"

if [ ! -f "$ROOT/dashboard/node_modules/vite/bin/vite.js" ]; then
    echo "Installing dashboard dependencies..."
    (cd "$ROOT/dashboard" && npm install --include=dev)
fi

(cd "$ROOT/backend" && exec uv run uvicorn vibe.api:app --port 8000) &
BACKEND=$!
# Keep Vite as the tracked child process so shutdown stops the server.
(cd "$ROOT/dashboard" && exec node node_modules/vite/bin/vite.js) &
DASHBOARD=$!
stop() { kill "$BACKEND" "$DASHBOARD" 2>/dev/null || true; wait "$BACKEND" "$DASHBOARD" 2>/dev/null || true; }
trap stop EXIT
trap 'exit 0' INT TERM

echo "Backend:   http://localhost:8000"
echo "Dashboard: http://localhost:5173  (Ctrl+C to stop both)"
# wait -n requires Bash 4.3; macOS ships Bash 3.2. Stop both if either exits.
while kill -0 "$BACKEND" 2>/dev/null && kill -0 "$DASHBOARD" 2>/dev/null; do
    sleep 1
done
