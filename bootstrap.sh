#!/usr/bin/env bash
set -euo pipefail

echo
echo "==> Bootstrapping Alek's Email Assistant"
echo

if command -v python3 >/dev/null 2>&1; then
  PYTHON_CMD="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_CMD="python"
else
  echo "Python 3.10+ was not found. Install Python and retry." >&2
  exit 1
fi

if ! command -v node >/dev/null 2>&1; then
  echo "Node.js 18+ was not found. Install Node.js and retry." >&2
  exit 1
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "npm was not found. Install Node.js/npm and retry." >&2
  exit 1
fi

if [ ! -x "backend/venv/bin/python" ]; then
  echo "==> Creating backend virtual environment..."
  "$PYTHON_CMD" -m venv backend/venv
fi

echo "==> Installing backend dependencies..."
backend/venv/bin/python -m pip install --upgrade pip
backend/venv/bin/python -m pip install -e backend

if [ ! -f "backend/.env" ]; then
  echo "==> Creating backend/.env from .env.example..."
  cp .env.example backend/.env
fi

echo "==> Installing frontend dependencies..."
(cd frontend && npm install)

echo
echo "Bootstrap complete."
echo
echo "Next steps:"
echo "1) Edit backend/.env and add your API credentials."
echo "2) Start backend:  cd backend && ./venv/bin/python -m app.main"
echo "3) Start frontend: cd frontend && npm run dev"
echo "4) Open http://localhost:5173"
echo
