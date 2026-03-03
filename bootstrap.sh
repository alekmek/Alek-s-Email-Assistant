#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

SETUP_ONLY=0
if [ "${1:-}" = "--setup-only" ]; then
  SETUP_ONLY=1
fi

BACKEND_PATH="$SCRIPT_DIR/backend"
FRONTEND_PATH="$SCRIPT_DIR/frontend"
RUN_PATH="$SCRIPT_DIR/.run"
BACKEND_ENV_PATH="$BACKEND_PATH/.env"
BACKEND_VENV_PYTHON="$BACKEND_PATH/venv/bin/python"
BACKEND_OUT_LOG="$RUN_PATH/backend.out.log"
BACKEND_ERR_LOG="$RUN_PATH/backend.err.log"
BACKEND_PID_PATH="$RUN_PATH/backend.pid"
FRONTEND_OUT_LOG="$RUN_PATH/frontend.out.log"
FRONTEND_ERR_LOG="$RUN_PATH/frontend.err.log"
FRONTEND_PID_PATH="$RUN_PATH/frontend.pid"

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

if [ ! -x "$BACKEND_VENV_PYTHON" ]; then
  echo "==> Creating backend virtual environment..."
  "$PYTHON_CMD" -m venv "$BACKEND_PATH/venv"
fi

echo "==> Installing backend dependencies..."
"$BACKEND_VENV_PYTHON" -m pip install --upgrade pip
"$BACKEND_VENV_PYTHON" -m pip install -e "$BACKEND_PATH"

if [ ! -f "$BACKEND_ENV_PATH" ]; then
  echo "==> Creating backend/.env from .env.example..."
  cp "$SCRIPT_DIR/.env.example" "$BACKEND_ENV_PATH"
fi

get_env_value() {
  local key="$1"
  local line
  line="$(grep -E "^${key}=" "$BACKEND_ENV_PATH" | tail -n 1 || true)"
  if [ -z "$line" ]; then
    echo ""
  else
    echo "${line#*=}"
  fi
}

set_env_value() {
  local key="$1"
  local value="$2"
  local tmp_file
  tmp_file="$(mktemp)"

  awk -v key="$key" -v value="$value" '
    BEGIN { updated = 0 }
    $0 ~ ("^" key "=") {
      print key "=" value
      updated = 1
      next
    }
    { print }
    END {
      if (!updated) {
        print key "=" value
      }
    }
  ' "$BACKEND_ENV_PATH" > "$tmp_file"

  cat "$tmp_file" > "$BACKEND_ENV_PATH"
  rm -f "$tmp_file"
}

ensure_required_env() {
  local key="$1"
  local label="$2"
  local existing
  local value

  existing="$(get_env_value "$key")"
  if [ -n "$existing" ]; then
    return
  fi

  if [ ! -t 0 ]; then
    echo "$key is required but no interactive terminal was detected. Set it in backend/.env and rerun." >&2
    exit 1
  fi

  while true; do
    read -r -s -p "$label: " value
    echo
    if [ -n "$value" ]; then
      set_env_value "$key" "$value"
      break
    fi
    echo "$key is required."
  done
}

ensure_optional_env() {
  local key="$1"
  local label="$2"
  local existing
  local value

  existing="$(get_env_value "$key")"
  if [ -n "$existing" ]; then
    return
  fi

  if [ ! -t 0 ]; then
    return
  fi

  read -r -p "$label (optional, press Enter to skip): " value
  if [ -n "$value" ]; then
    set_env_value "$key" "$value"
  fi
}

ensure_anthropic_model() {
  local default_model="claude-sonnet-4-20250514"
  local current
  current="$(get_env_value "ANTHROPIC_MODEL" | tr -d '\r' | xargs)"

  if [ -z "$current" ]; then
    set_env_value "ANTHROPIC_MODEL" "$default_model"
    echo "Set ANTHROPIC_MODEL=$default_model"
    return
  fi

  # Guard against accidental API key paste into model field.
  if [[ "$current" == sk-ant-* ]]; then
    echo "ANTHROPIC_MODEL looked like an API key; resetting to $default_model"
    set_env_value "ANTHROPIC_MODEL" "$default_model"
  fi
}

is_port_listening() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
    return
  fi
  if command -v ss >/dev/null 2>&1; then
    ss -ltn | grep -E "[\.\:]$port[[:space:]]" >/dev/null 2>&1
    return
  fi
  if command -v netstat >/dev/null 2>&1; then
    netstat -an 2>/dev/null | grep -E "[\.\:]$port[[:space:]].*LISTEN" >/dev/null 2>&1
    return
  fi
  return 1
}

wait_for_url() {
  local url="$1"
  local timeout_seconds="$2"
  local i
  for ((i = 0; i < timeout_seconds; i++)); do
    if command -v curl >/dev/null 2>&1; then
      if curl -fsS "$url" >/dev/null 2>&1; then
        return 0
      fi
    else
      if "$PYTHON_CMD" -c "import urllib.request,sys; urllib.request.urlopen('$url', timeout=3); sys.exit(0)" >/dev/null 2>&1; then
        return 0
      fi
    fi
    sleep 1
  done
  return 1
}

open_url() {
  local url="$1"
  if command -v open >/dev/null 2>&1; then
    open "$url" >/dev/null 2>&1 &
    return
  fi
  if command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 &
    return
  fi
  echo "Open this URL manually: $url"
}

echo "==> Capturing API credentials..."
ensure_required_env "ANTHROPIC_API_KEY" "Enter ANTHROPIC_API_KEY"
ensure_anthropic_model
ensure_required_env "NYLAS_API_KEY" "Enter NYLAS_API_KEY"
ensure_required_env "NYLAS_CLIENT_ID" "Enter NYLAS_CLIENT_ID"
ensure_required_env "NYLAS_CLIENT_SECRET" "Enter NYLAS_CLIENT_SECRET"

NYLAS_GRANT_ID_VALUE="$(get_env_value "NYLAS_GRANT_ID")"
NYLAS_SID_VALUE="$(get_env_value "NYLAS_SID")"
if [ -z "$NYLAS_GRANT_ID_VALUE" ] && [ -z "$NYLAS_SID_VALUE" ]; then
  ensure_required_env "NYLAS_GRANT_ID" "Enter NYLAS_GRANT_ID (preferred) or set NYLAS_SID in backend/.env"
fi

ensure_required_env "DEEPGRAM_API_KEY" "Enter DEEPGRAM_API_KEY"
ensure_required_env "CARTESIA_API_KEY" "Enter CARTESIA_API_KEY"

echo "==> Installing frontend dependencies..."
(cd "$FRONTEND_PATH" && npm install)

echo
echo "Bootstrap complete."
echo

if [ "$SETUP_ONLY" -eq 1 ]; then
  echo "Setup-only mode enabled. Skipping service startup."
  exit 0
fi

mkdir -p "$RUN_PATH"

if ! is_port_listening 8000; then
  echo "==> Starting backend server on http://localhost:8000 ..."
  (
    cd "$BACKEND_PATH"
    nohup ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >"$BACKEND_OUT_LOG" 2>"$BACKEND_ERR_LOG" &
    echo $! > "$BACKEND_PID_PATH"
  )
else
  echo "==> Backend already listening on port 8000."
fi

if ! is_port_listening 5173; then
  echo "==> Starting frontend dashboard on http://localhost:5173 ..."
  (
    cd "$FRONTEND_PATH"
    nohup npm run dev -- --host 0.0.0.0 --port 5173 >"$FRONTEND_OUT_LOG" 2>"$FRONTEND_ERR_LOG" &
    echo $! > "$FRONTEND_PID_PATH"
  )
else
  echo "==> Frontend already listening on port 5173."
fi

echo "==> Waiting for backend health..."
BACKEND_READY=0
if wait_for_url "http://localhost:8000/health" 120; then
  BACKEND_READY=1
fi

echo "==> Waiting for frontend..."
FRONTEND_READY=0
if wait_for_url "http://localhost:5173/" 120; then
  FRONTEND_READY=1
fi

if [ "$BACKEND_READY" -eq 1 ] && [ "$FRONTEND_READY" -eq 1 ]; then
  echo "==> Services are ready. Opening browser..."
  open_url "http://localhost:5173/"
else
  echo "One or more services did not become ready in time."
  echo "Backend logs:  $BACKEND_ERR_LOG"
  echo "Frontend logs: $FRONTEND_ERR_LOG"
fi

echo
echo "Run status:"
if [ "$BACKEND_READY" -eq 1 ]; then
  echo "Backend health:  ready"
else
  echo "Backend health:  not ready"
fi
if [ "$FRONTEND_READY" -eq 1 ]; then
  echo "Frontend status: ready"
else
  echo "Frontend status: not ready"
fi
echo "Backend PID file:  $BACKEND_PID_PATH"
echo "Frontend PID file: $FRONTEND_PID_PATH"
echo
echo "To stop services:"
echo "  kill \$(cat \"$BACKEND_PID_PATH\" \"$FRONTEND_PID_PATH\")"
