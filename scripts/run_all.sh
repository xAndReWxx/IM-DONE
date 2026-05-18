#!/usr/bin/env bash
# ============================================================
# PhysioAI Pro V2 — Run both services
# ============================================================
# Convenience launcher that:
#   1) Activates (or creates) a backend venv
#   2) Installs backend deps if missing
#   3) Starts the backend on :8000
#   4) Starts the frontend dev server on :5173
#   5) Forwards Ctrl+C to both
#
# Linux/macOS only. Windows users: run the two commands at the
# bottom of the README in separate terminals.
# ============================================================
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

echo "─── PhysioAI Pro V2 launcher ───"
echo "ROOT      : $ROOT"
echo "BACKEND   : $BACKEND"
echo "FRONTEND  : $FRONTEND"

# ── Backend setup ──
cd "$BACKEND"
if [[ ! -d .venv ]]; then
  echo "[backend] Creating venv..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -q -r requirements.txt

# ── Frontend setup ──
cd "$FRONTEND"
if [[ ! -d node_modules ]]; then
  echo "[frontend] Installing npm deps..."
  npm install --silent --no-audit --no-fund
fi

# ── Launch ──
echo
echo "─── Starting backend on :8000 ───"
cd "$BACKEND"
.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!

echo "─── Starting frontend on :5173 ───"
cd "$FRONTEND"
npm run dev -- --host 0.0.0.0 &
FRONTEND_PID=$!

cleanup() {
  echo
  echo "─── Shutting down… ───"
  kill "$BACKEND_PID" 2>/dev/null || true
  kill "$FRONTEND_PID" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap cleanup INT TERM

wait
