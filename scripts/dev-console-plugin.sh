#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="${ROOT_DIR}/komsco-ai-console-plugin"

PLUGIN_HOST="${PLUGIN_HOST:-127.0.0.1}"
PLUGIN_PORT="${PLUGIN_PORT:-9001}"
CONSOLE_PORT="${CONSOLE_PORT:-9000}"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
GATEWAY_ENDPOINT="${GATEWAY_ENDPOINT:-http://localhost:${GATEWAY_PORT}}"
INSTALL_DEPS="${INSTALL_DEPS:-false}"
PLUGIN_LOG="${PLUGIN_LOG:-${ROOT_DIR}/.dev-console-plugin-webpack.log}"

PLUGIN_PID=""
CONSOLE_PID=""

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

port_open() {
  local host="$1"
  local port="$2"
  (echo >"/dev/tcp/${host}/${port}") >/dev/null 2>&1
}

wait_for_port() {
  local host="$1"
  local port="$2"
  local attempts="${3:-160}"

  for _ in $(seq 1 "$attempts"); do
    if port_open "$host" "$port"; then
      return 0
    fi
    sleep 0.25
  done

  return 1
}

kill_tree() {
  local pid="$1"
  if [ -z "$pid" ] || ! kill -0 "$pid" >/dev/null 2>&1; then
    return
  fi

  if command -v pkill >/dev/null 2>&1; then
    pkill -TERM -P "$pid" >/dev/null 2>&1 || true
  fi

  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" >/dev/null 2>&1 || true
}

cleanup() {
  kill_tree "$CONSOLE_PID"
  kill_tree "$PLUGIN_PID"
}

trap cleanup EXIT INT TERM

require_cmd oc
require_cmd yarn

if ! oc whoami >/dev/null 2>&1; then
  echo "oc login이 필요합니다. VPN/hosts 설정 후 oc login을 먼저 수행하세요." >&2
  exit 1
fi

cd "$PLUGIN_DIR"

if [ "$INSTALL_DEPS" = "true" ]; then
  yarn install
elif [ ! -d node_modules ]; then
  echo "node_modules가 없습니다. INSTALL_DEPS=true task fe:dev 또는 cd komsco-ai-console-plugin && yarn install을 실행하세요." >&2
  exit 1
fi

if port_open "$PLUGIN_HOST" "$PLUGIN_PORT"; then
  echo "Using existing plugin dev server: http://${PLUGIN_HOST}:${PLUGIN_PORT}"
else
  : > "$PLUGIN_LOG"
  yarn start >"$PLUGIN_LOG" 2>&1 &
  PLUGIN_PID="$!"

  if ! wait_for_port "$PLUGIN_HOST" "$PLUGIN_PORT"; then
    echo "Plugin dev server failed. Log: $PLUGIN_LOG" >&2
    cat "$PLUGIN_LOG" >&2
    exit 1
  fi

  echo "Plugin dev server: http://${PLUGIN_HOST}:${PLUGIN_PORT}"
  echo "Plugin dev log: $PLUGIN_LOG"
fi

export CONSOLE_PORT
if [ -z "${BRIDGE_PLUGIN_PROXY:-}" ]; then
  BRIDGE_PLUGIN_PROXY=$(printf '{"services":[{"consoleAPIPath":"/api/proxy/plugin/komsco-ai-console-plugin/ai-gateway/","endpoint":"%s","authorize":true}]}' "$GATEWAY_ENDPOINT")
fi
export BRIDGE_PLUGIN_PROXY

echo "Gateway proxy endpoint: ${GATEWAY_ENDPOINT}"
echo "Console URL: http://localhost:${CONSOLE_PORT}"

yarn start-console &
CONSOLE_PID="$!"
wait "$CONSOLE_PID"
