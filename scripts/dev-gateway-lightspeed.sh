#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_DIR="${ROOT_DIR}/komsco-ai-gateway"

GATEWAY_HOST="${GATEWAY_HOST:-127.0.0.1}"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
INSTALL_DEPS="${INSTALL_DEPS:-true}"
OLS_NAMESPACE="${OLS_NAMESPACE:-openshift-lightspeed}"
OLS_SERVICE="${OLS_SERVICE:-lightspeed-app-server}"
OLS_SERVICE_PORT="${OLS_SERVICE_PORT:-8443}"
OLS_LOCAL_PORT="${OLS_LOCAL_PORT:-18443}"
PF_LOG="${PF_LOG:-${ROOT_DIR}/.dev-lightspeed-port-forward.log}"

PF_PID=""

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
  local attempts="${3:-120}"

  for _ in $(seq 1 "$attempts"); do
    if port_open "$host" "$port"; then
      return 0
    fi
    sleep 0.25
  done

  return 1
}

cleanup() {
  if [ -n "$PF_PID" ] && kill -0 "$PF_PID" >/dev/null 2>&1; then
    kill "$PF_PID" >/dev/null 2>&1 || true
    wait "$PF_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

require_cmd oc
require_cmd python3

if ! oc whoami >/dev/null 2>&1; then
  echo "oc login이 필요합니다. VPN/hosts 설정 후 oc login을 먼저 수행하세요." >&2
  exit 1
fi

oc -n "$OLS_NAMESPACE" get "svc/${OLS_SERVICE}" >/dev/null

if port_open "$GATEWAY_HOST" "$OLS_LOCAL_PORT"; then
  echo "Using existing local Lightspeed endpoint: https://${GATEWAY_HOST}:${OLS_LOCAL_PORT}"
else
  : > "$PF_LOG"
  oc -n "$OLS_NAMESPACE" port-forward \
    --address "$GATEWAY_HOST" \
    "svc/${OLS_SERVICE}" \
    "${OLS_LOCAL_PORT}:${OLS_SERVICE_PORT}" \
    >"$PF_LOG" 2>&1 &
  PF_PID="$!"

  if ! wait_for_port "$GATEWAY_HOST" "$OLS_LOCAL_PORT"; then
    echo "Lightspeed port-forward failed. Log: $PF_LOG" >&2
    cat "$PF_LOG" >&2
    exit 1
  fi

  echo "Lightspeed port-forward: ${OLS_NAMESPACE}/${OLS_SERVICE} ${OLS_SERVICE_PORT} -> ${GATEWAY_HOST}:${OLS_LOCAL_PORT}"
  echo "Port-forward log: $PF_LOG"
fi

cd "$GATEWAY_DIR"

if [ ! -d .venv ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate

if [ "$INSTALL_DEPS" = "true" ]; then
  python -m pip install -r requirements-dev.txt
fi

export KOMSCO_AI_DEV_ECHO="${KOMSCO_AI_DEV_ECHO:-false}"
export OLS_BASE_URL="${OLS_BASE_URL:-https://${GATEWAY_HOST}:${OLS_LOCAL_PORT}}"
export OLS_CA_FILE="${OLS_CA_FILE:-false}"
export OPENSHIFT_API_URL="${OPENSHIFT_API_URL:-$(oc whoami --show-server)}"
export OPENSHIFT_API_CA_FILE="${OPENSHIFT_API_CA_FILE:-false}"

echo "Gateway URL: http://${GATEWAY_HOST}:${GATEWAY_PORT}"
echo "OLS_BASE_URL: ${OLS_BASE_URL}"
echo "OLS_CA_FILE: ${OLS_CA_FILE}"
echo "OPENSHIFT_API_URL: ${OPENSHIFT_API_URL}"
echo "OPENSHIFT_API_CA_FILE: ${OPENSHIFT_API_CA_FILE}"

uvicorn komsco_ai_gateway.main:app \
  --reload \
  --host "$GATEWAY_HOST" \
  --port "$GATEWAY_PORT"
