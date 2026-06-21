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
PF_CHECK_INTERVAL="${PF_CHECK_INTERVAL:-5}"
PF_RESTART_DELAY="${PF_RESTART_DELAY:-2}"

PF_SUPERVISOR_PID=""

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

log_port_forward() {
  printf '[%s] %s\n' "$(date -Is)" "$*" >>"$PF_LOG"
}

run_port_forward_supervisor() {
  local pf_pid=""

  cleanup_supervisor() {
    if [ -n "$pf_pid" ] && kill -0 "$pf_pid" >/dev/null 2>&1; then
      kill "$pf_pid" >/dev/null 2>&1 || true
      wait "$pf_pid" >/dev/null 2>&1 || true
    fi
  }

  trap 'cleanup_supervisor; exit 0' INT TERM
  trap cleanup_supervisor EXIT

  while true; do
    if [ -n "$pf_pid" ] && ! kill -0 "$pf_pid" >/dev/null 2>&1; then
      wait "$pf_pid" >/dev/null 2>&1 || true
      log_port_forward "Lightspeed port-forward exited; restarting after ${PF_RESTART_DELAY}s"
      pf_pid=""
      sleep "$PF_RESTART_DELAY"
    fi

    if [ -z "$pf_pid" ]; then
      if port_open "$GATEWAY_HOST" "$OLS_LOCAL_PORT"; then
        sleep "$PF_CHECK_INTERVAL"
        continue
      fi

      log_port_forward "Starting Lightspeed port-forward: ${OLS_NAMESPACE}/${OLS_SERVICE} ${OLS_SERVICE_PORT} -> ${GATEWAY_HOST}:${OLS_LOCAL_PORT}"
      oc -n "$OLS_NAMESPACE" port-forward \
        --address "$GATEWAY_HOST" \
        "svc/${OLS_SERVICE}" \
        "${OLS_LOCAL_PORT}:${OLS_SERVICE_PORT}" \
        >>"$PF_LOG" 2>&1 &
      pf_pid="$!"

      if wait_for_port "$GATEWAY_HOST" "$OLS_LOCAL_PORT" 40; then
        sleep "$PF_CHECK_INTERVAL"
        continue
      fi

      if kill -0 "$pf_pid" >/dev/null 2>&1; then
        log_port_forward "Lightspeed port-forward did not become ready; restarting after ${PF_RESTART_DELAY}s"
        kill "$pf_pid" >/dev/null 2>&1 || true
        wait "$pf_pid" >/dev/null 2>&1 || true
      else
        wait "$pf_pid" >/dev/null 2>&1 || true
        log_port_forward "Lightspeed port-forward exited before becoming ready; restarting after ${PF_RESTART_DELAY}s"
      fi

      pf_pid=""
      sleep "$PF_RESTART_DELAY"
      continue
    fi

    if ! port_open "$GATEWAY_HOST" "$OLS_LOCAL_PORT"; then
      log_port_forward "Lightspeed local port ${GATEWAY_HOST}:${OLS_LOCAL_PORT} is unavailable; restarting port-forward"
      kill "$pf_pid" >/dev/null 2>&1 || true
      wait "$pf_pid" >/dev/null 2>&1 || true
      pf_pid=""
      sleep "$PF_RESTART_DELAY"
      continue
    fi

    sleep "$PF_CHECK_INTERVAL"
  done
}

cleanup() {
  if [ -n "$PF_SUPERVISOR_PID" ] && kill -0 "$PF_SUPERVISOR_PID" >/dev/null 2>&1; then
    kill "$PF_SUPERVISOR_PID" >/dev/null 2>&1 || true
    wait "$PF_SUPERVISOR_PID" >/dev/null 2>&1 || true
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

: > "$PF_LOG"
run_port_forward_supervisor &
PF_SUPERVISOR_PID="$!"

if ! wait_for_port "$GATEWAY_HOST" "$OLS_LOCAL_PORT"; then
  echo "Lightspeed port-forward failed. Log: $PF_LOG" >&2
  cat "$PF_LOG" >&2
  exit 1
fi

echo "Lightspeed endpoint supervised: ${OLS_NAMESPACE}/${OLS_SERVICE} ${OLS_SERVICE_PORT} -> ${GATEWAY_HOST}:${OLS_LOCAL_PORT}"
echo "Port-forward log: $PF_LOG"

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
export KOMSCO_AI_SECURITY_PHASE="${KOMSCO_AI_SECURITY_PHASE:-phase0-1}"
export KOMSCO_AI_ENABLE_MUTATIONS="${KOMSCO_AI_ENABLE_MUTATIONS:-false}"

echo "Gateway URL: http://${GATEWAY_HOST}:${GATEWAY_PORT}"
echo "OLS_BASE_URL: ${OLS_BASE_URL}"
echo "OLS_CA_FILE: ${OLS_CA_FILE}"
echo "OPENSHIFT_API_URL: ${OPENSHIFT_API_URL}"
echo "OPENSHIFT_API_CA_FILE: ${OPENSHIFT_API_CA_FILE}"
echo "KOMSCO_AI_SECURITY_PHASE: ${KOMSCO_AI_SECURITY_PHASE}"
echo "KOMSCO_AI_ENABLE_MUTATIONS: ${KOMSCO_AI_ENABLE_MUTATIONS}"

uvicorn komsco_ai_gateway.main:app \
  --reload \
  --host "$GATEWAY_HOST" \
  --port "$GATEWAY_PORT"
