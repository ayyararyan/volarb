#!/usr/bin/env bash
set -Eeuo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME_DIR="${DHAN_RUNTIME_DIR:-${VOLARB_DATA_DIR:-$HOME/.local/share/volarb}/dhan}"
export DHAN_RUNTIME_DIR="$RUNTIME_DIR"
LOG_DIR="$RUNTIME_DIR/.logs"

LOCAL_HEALTH_URL="http://127.0.0.1:3000/healthz"
NGROK_DOMAIN="${NGROK_DOMAIN:?Set NGROK_DOMAIN privately before starting the tunnel}"
PUBLIC_BASE_URL="https://${NGROK_DOMAIN}"
PUBLIC_HEALTH_URL="${PUBLIC_BASE_URL}/healthz"
PUBLIC_MCP_URL="${PUBLIC_BASE_URL}/mcp"

SERVER_PID=""
NGROK_PID=""
SERVER_MANAGED=0
NGROK_MANAGED=0

mkdir -p "$LOG_DIR"

SERVER_LOG="$LOG_DIR/server.log"
NGROK_LOG="$LOG_DIR/ngrok.log"

log() {
  printf '%s\n' "$*"
}

cleanup() {
  trap - EXIT INT TERM

  log ""
  log "Stopping Dhan MCP server and ngrok..."

  if [ "$NGROK_MANAGED" -eq 1 ] && [ -n "$NGROK_PID" ] && kill -0 "$NGROK_PID" 2>/dev/null; then
    kill "$NGROK_PID" 2>/dev/null || true
    wait "$NGROK_PID" 2>/dev/null || true
  fi

  if [ "$SERVER_MANAGED" -eq 1 ] && [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi

  log "Stopped."
}

trap cleanup EXIT INT TERM

for cmd in npm ngrok curl; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    log "Error: required command '$cmd' was not found."
    exit 1
  fi
done

cd "$PROJECT_DIR"

if [ ! -f package.json ]; then
  log "Error: package.json not found in $PROJECT_DIR"
  exit 1
fi

if [ ! -f "$RUNTIME_DIR/.env" ]; then
  log "Error: .env not found in $RUNTIME_DIR"
  exit 1
fi

if [ ! -d node_modules ]; then
  log "node_modules not found; running locked npm ci..."
  npm ci --ignore-scripts --no-audit --no-fund
fi

log "Starting Dhan MCP..."
log "  project: $PROJECT_DIR"
log "  local:   http://127.0.0.1:3000/mcp"
log "  public:  $PUBLIC_MCP_URL"
log "  logs:    $LOG_DIR"

# Start the MCP server only if one is not already healthy.
if curl -fsS --max-time 2 "$LOCAL_HEALTH_URL" >/dev/null 2>&1; then
  log "Dhan MCP is already healthy on port 3000; reusing it."
else
  : > "$SERVER_LOG"
  npm start >>"$SERVER_LOG" 2>&1 &
  SERVER_PID=$!
  SERVER_MANAGED=1

  log "Waiting for local MCP health check..."
  READY=0
  i=0
  while [ "$i" -lt 30 ]; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      log "Error: Dhan MCP exited before becoming ready."
      tail -n 80 "$SERVER_LOG" 2>/dev/null || true
      exit 1
    fi

    if curl -fsS --max-time 2 "$LOCAL_HEALTH_URL" >/dev/null 2>&1; then
      READY=1
      break
    fi

    i=$((i + 1))
    sleep 1
  done

  if [ "$READY" -ne 1 ]; then
    log "Error: Dhan MCP did not become healthy within 30 seconds."
    tail -n 80 "$SERVER_LOG" 2>/dev/null || true
    exit 1
  fi

  log "Local Dhan MCP is healthy."
fi

# Stop only a stale ngrok process using this exact Dhan endpoint, if present.
STALE_PIDS="$(pgrep -f "ngrok http 3000.*${NGROK_DOMAIN}" 2>/dev/null || true)"
if [ -n "$STALE_PIDS" ]; then
  log "Stopping stale ngrok process for this Dhan endpoint..."
  for pid in $STALE_PIDS; do
    if [ "$pid" != "$$" ]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  sleep 1
fi

if ! ngrok config check --config "$RUNTIME_DIR/.private/ngrok.yml" >/dev/null 2>&1; then
  log "Error: ngrok configuration is invalid."
  ngrok config check --config "$RUNTIME_DIR/.private/ngrok.yml" || true
  exit 1
fi

: > "$NGROK_LOG"
log "Starting ngrok..."
ngrok http 3000 --config "$RUNTIME_DIR/.private/ngrok.yml" \
  --url "$PUBLIC_BASE_URL" \
  --log stdout \
  --log-level info \
  >>"$NGROK_LOG" 2>&1 &

NGROK_PID=$!
NGROK_MANAGED=1

log "Waiting for public endpoint..."
PUBLIC_READY=0
i=0
while [ "$i" -lt 30 ]; do
  if ! kill -0 "$NGROK_PID" 2>/dev/null; then
    log "Error: ngrok exited before the public endpoint became ready."
    tail -n 100 "$NGROK_LOG" 2>/dev/null || true
    exit 1
  fi

  if curl -fsS --max-time 4 "$PUBLIC_HEALTH_URL" >/dev/null 2>&1; then
    PUBLIC_READY=1
    break
  fi

  i=$((i + 1))
  sleep 1
done

if [ "$PUBLIC_READY" -ne 1 ]; then
  log "Error: public endpoint did not become healthy within 30 seconds."
  tail -n 100 "$NGROK_LOG" 2>/dev/null || true
  exit 1
fi

log ""
log "Dhan MCP is online."
log "  Local MCP:  http://127.0.0.1:3000/mcp"
log "  Public MCP: $PUBLIC_MCP_URL"
log "  Health:     $PUBLIC_HEALTH_URL"
log ""
log "Keep this Terminal open. Press Ctrl+C to stop Dhan MCP and ngrok."

# macOS ships an older Bash, so avoid 'wait -n'.
while true; do
  if [ "$SERVER_MANAGED" -eq 1 ] && ! kill -0 "$SERVER_PID" 2>/dev/null; then
    log ""
    log "Error: Dhan MCP stopped unexpectedly."
    tail -n 100 "$SERVER_LOG" 2>/dev/null || true
    exit 1
  fi

  if ! kill -0 "$NGROK_PID" 2>/dev/null; then
    log ""
    log "Error: ngrok stopped unexpectedly."
    tail -n 100 "$NGROK_LOG" 2>/dev/null || true
    exit 1
  fi

  sleep 2
done
