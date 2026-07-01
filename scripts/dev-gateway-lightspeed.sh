#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_DIR="${ROOT_DIR}/komsco-ai-gateway"

GATEWAY_HOST="${GATEWAY_HOST:-127.0.0.1}"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
LOCAL_CONNECT_HOST="$GATEWAY_HOST"
if [ "$LOCAL_CONNECT_HOST" = "0.0.0.0" ]; then
  LOCAL_CONNECT_HOST="127.0.0.1"
fi
INSTALL_DEPS="${INSTALL_DEPS:-true}"
OLS_NAMESPACE="${OLS_NAMESPACE:-openshift-lightspeed}"
OLS_SERVICE="${OLS_SERVICE:-lightspeed-app-server}"
OLS_SERVICE_PORT="${OLS_SERVICE_PORT:-8443}"
OLS_LOCAL_PORT="${OLS_LOCAL_PORT:-18443}"
PF_LOG="${PF_LOG:-${ROOT_DIR}/.dev-lightspeed-port-forward.log}"
PF_CHECK_INTERVAL="${PF_CHECK_INTERVAL:-5}"
PF_RESTART_DELAY="${PF_RESTART_DELAY:-2}"
PF_HEALTH_FAILURE_THRESHOLD="${PF_HEALTH_FAILURE_THRESHOLD:-12}"
MANAGE_OLS_PORT_FORWARD="${KUGNUS_MANAGE_OLS_PORT_FORWARD:-true}"
ACTION_EXECUTOR="${ACTION_EXECUTOR:-}"
ACTION_EXECUTOR_PORT_FORWARD="${ACTION_EXECUTOR_PORT_FORWARD:-}"
AIOPS_UNRESTRICTED="${AIOPS_UNRESTRICTED:-${UNRESTRICTED_COMMANDS:-}}"
AIOPS_GATEWAY_MODE="${AIOPS_GATEWAY_MODE:-}"
ACTION_EXECUTOR_NAMESPACE="${ACTION_EXECUTOR_NAMESPACE:-komsco-ai-dev}"
ACTION_EXECUTOR_SERVICE="${ACTION_EXECUTOR_SERVICE:-komsco-ai-action-executor}"
ACTION_EXECUTOR_SERVICE_PORT="${ACTION_EXECUTOR_SERVICE_PORT:-8080}"
ACTION_EXECUTOR_LOCAL_PORT="${ACTION_EXECUTOR_LOCAL_PORT:-18083}"
ACTION_EXECUTOR_PF_LOG="${ACTION_EXECUTOR_PF_LOG:-${ROOT_DIR}/.dev-action-executor-port-forward.log}"

PF_SUPERVISOR_PID=""
ACTION_EXECUTOR_PF_PID=""
ACTION_EXECUTOR_ENABLED="true"
UNRESTRICTED_COMMANDS_ENABLED="true"

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

http_ok() {
  local url="$1"
  local status
  status="$(curl -ksS -o /dev/null -w '%{http_code}' --max-time 8 "$url" 2>/dev/null || true)"
  case "$status" in
    200|204|301|302|304)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

https_responds() {
  local url="$1"
  local status
  status="$(curl -ksS -o /dev/null -w '%{http_code}' --connect-timeout 5 --max-time 8 "$url" 2>/dev/null || true)"
  case "$status" in
    [1-5][0-9][0-9])
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

lightspeed_forward_healthy() {
  https_responds "https://${LOCAL_CONNECT_HOST}:${OLS_LOCAL_PORT}/readiness"
}

action_executor_forward_healthy() {
  http_ok "http://${LOCAL_CONNECT_HOST}:${ACTION_EXECUTOR_LOCAL_PORT}/healthz"
}

wait_for_lightspeed_forward() {
  local attempts="${1:-80}"

  for _ in $(seq 1 "$attempts"); do
    if lightspeed_forward_healthy; then
      return 0
    fi
    sleep 0.5
  done

  return 1
}

wait_for_action_executor_forward() {
  local attempts="${1:-80}"

  for _ in $(seq 1 "$attempts"); do
    if action_executor_forward_healthy; then
      return 0
    fi
    sleep 0.5
  done

  return 1
}

stop_matching_port_forward() {
  local namespace="$1"
  local service="$2"
  local local_port="$3"
  local service_port="$4"
  local line pid args matched="false"

  while IFS= read -r line; do
    line="${line#"${line%%[![:space:]]*}"}"
    pid="${line%% *}"
    args="${line#"$pid"}"
    args="${args#"${args%%[![:space:]]*}"}"
    if [[ "$args" != *"oc "*port-forward* ]]; then
      continue
    fi
    if [[ "$args" != *"svc/${service}"* || "$args" != *"${local_port}:${service_port}"* ]]; then
      continue
    fi
    if [[ "$args" != *"-n ${namespace}"* && "$args" != *"--namespace ${namespace}"* ]]; then
      continue
    fi
    echo "Stopping stale port-forward pid=${pid}: ${namespace}/${service} ${local_port}:${service_port}" >&2
    kill "$pid" >/dev/null 2>&1 || true
    matched="true"
  done < <(ps -eo pid=,args=)

  if [ "$matched" = "true" ]; then
    for _ in $(seq 1 20); do
      if ! port_open "$LOCAL_CONNECT_HOST" "$local_port"; then
        return 0
      fi
      sleep 0.25
    done
  fi
}

normalize_bool_option() {
  case "$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" in
    1|true|yes|y|on|enable|enabled)
      printf 'true'
      ;;
    ""|0|false|no|n|off|disable|disabled)
      printf 'false'
      ;;
    *)
      echo "Invalid boolean option: $1. Use on/off or true/false." >&2
      exit 1
      ;;
  esac
}

select_gateway_mode() {
  if [ -n "$AIOPS_GATEWAY_MODE" ]; then
    case "$(printf '%s' "$AIOPS_GATEWAY_MODE" | tr '[:upper:]' '[:lower:]')" in
      1|exec|execute|execution|실행|실행가능)
        printf 'execute'
        ;;
      2|unrestricted|dev-unrestricted|experimental|실험|무제한)
        printf 'unrestricted'
        ;;
      *)
        echo "Invalid AIOPS_GATEWAY_MODE: ${AIOPS_GATEWAY_MODE}. Use execute or unrestricted." >&2
        exit 1
        ;;
    esac
    return
  fi

  if [ -n "$AIOPS_UNRESTRICTED" ]; then
    if [ "$(normalize_bool_option "$AIOPS_UNRESTRICTED")" = "true" ]; then
      printf 'unrestricted'
    else
      printf 'execute'
    fi
    return
  fi

  if [ -n "$ACTION_EXECUTOR_PORT_FORWARD" ]; then
    if [ "$(normalize_bool_option "$ACTION_EXECUTOR_PORT_FORWARD")" = "true" ]; then
      printf 'execute'
    else
      printf 'execute'
    fi
    return
  fi

  if [ -n "$ACTION_EXECUTOR" ]; then
    if [ "$(normalize_bool_option "$ACTION_EXECUTOR")" = "true" ]; then
      printf 'execute'
    else
      printf 'execute'
    fi
    return
  fi

  if [ ! -t 0 ]; then
    printf 'execute'
    return
  fi

  echo "AIOps Gateway mode 선택:" >&2
  echo "  1) 실행 가능  - 승인된 Action Executor 실행 허용" >&2
  echo "  2) 실험용 무제한 - /exec 명령을 Gateway 로컬 권한으로 직접 실행" >&2
  printf "선택 [1/2, 기본 1]: " >&2
  read -r mode_choice

  case "${mode_choice:-1}" in
    1|exec|execute|execution|실행|실행가능)
      printf 'execute'
      ;;
    2|unrestricted|dev-unrestricted|experimental|실험|무제한)
      printf 'unrestricted'
      ;;
    *)
      echo "Invalid mode: ${mode_choice}. Use 1/execute or 2/unrestricted." >&2
      exit 1
      ;;
  esac
}

log_port_forward() {
  printf '[%s] %s\n' "$(date -Is)" "$*" >>"$PF_LOG"
}

run_port_forward_supervisor() {
  local pf_pid=""
  local health_failures=0

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
      health_failures=0
      sleep "$PF_RESTART_DELAY"
    fi

    if [ -z "$pf_pid" ]; then
      if lightspeed_forward_healthy; then
        health_failures=0
        sleep "$PF_CHECK_INTERVAL"
        continue
      fi
      if port_open "$LOCAL_CONNECT_HOST" "$OLS_LOCAL_PORT"; then
        health_failures=$((health_failures + 1))
        if [ "$health_failures" -lt "$PF_HEALTH_FAILURE_THRESHOLD" ]; then
          log_port_forward "Lightspeed local port ${LOCAL_CONNECT_HOST}:${OLS_LOCAL_PORT} is open but readiness probe failed (${health_failures}/${PF_HEALTH_FAILURE_THRESHOLD}); keeping port-forward"
          sleep "$PF_CHECK_INTERVAL"
          continue
        fi
        log_port_forward "Lightspeed local port ${LOCAL_CONNECT_HOST}:${OLS_LOCAL_PORT} failed readiness ${health_failures} times; restarting matching port-forward"
        stop_matching_port_forward "$OLS_NAMESPACE" "$OLS_SERVICE" "$OLS_LOCAL_PORT" "$OLS_SERVICE_PORT"
        health_failures=0
        if port_open "$LOCAL_CONNECT_HOST" "$OLS_LOCAL_PORT"; then
          sleep "$PF_CHECK_INTERVAL"
          continue
        fi
      fi

      log_port_forward "Starting Lightspeed port-forward: ${OLS_NAMESPACE}/${OLS_SERVICE} ${OLS_SERVICE_PORT} -> ${GATEWAY_HOST}:${OLS_LOCAL_PORT}"
      oc -n "$OLS_NAMESPACE" port-forward \
        --address "$GATEWAY_HOST" \
        "svc/${OLS_SERVICE}" \
        "${OLS_LOCAL_PORT}:${OLS_SERVICE_PORT}" \
        >>"$PF_LOG" 2>&1 &
      pf_pid="$!"

      if wait_for_port "$LOCAL_CONNECT_HOST" "$OLS_LOCAL_PORT" 40 && wait_for_lightspeed_forward 40; then
        health_failures=0
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
      health_failures=0
      sleep "$PF_RESTART_DELAY"
      continue
    fi

    if ! lightspeed_forward_healthy; then
      health_failures=$((health_failures + 1))
      if [ "$health_failures" -lt "$PF_HEALTH_FAILURE_THRESHOLD" ]; then
        log_port_forward "Lightspeed local port ${LOCAL_CONNECT_HOST}:${OLS_LOCAL_PORT} failed readiness probe (${health_failures}/${PF_HEALTH_FAILURE_THRESHOLD}); keeping port-forward"
        sleep "$PF_CHECK_INTERVAL"
        continue
      fi
      log_port_forward "Lightspeed local port ${LOCAL_CONNECT_HOST}:${OLS_LOCAL_PORT} failed readiness ${health_failures} times; restarting port-forward"
      kill "$pf_pid" >/dev/null 2>&1 || true
      wait "$pf_pid" >/dev/null 2>&1 || true
      pf_pid=""
      health_failures=0
      sleep "$PF_RESTART_DELAY"
      continue
    fi
    health_failures=0

    sleep "$PF_CHECK_INTERVAL"
  done
}

cleanup() {
  if [ -n "$PF_SUPERVISOR_PID" ] && kill -0 "$PF_SUPERVISOR_PID" >/dev/null 2>&1; then
    kill "$PF_SUPERVISOR_PID" >/dev/null 2>&1 || true
    wait "$PF_SUPERVISOR_PID" >/dev/null 2>&1 || true
  fi
  if [ -n "$ACTION_EXECUTOR_PF_PID" ] && kill -0 "$ACTION_EXECUTOR_PF_PID" >/dev/null 2>&1; then
    kill "$ACTION_EXECUTOR_PF_PID" >/dev/null 2>&1 || true
    wait "$ACTION_EXECUTOR_PF_PID" >/dev/null 2>&1 || true
  fi
}

trap cleanup EXIT INT TERM

require_cmd oc
require_cmd python3

AIOPS_GATEWAY_MODE_SELECTED="$(select_gateway_mode)"
case "$AIOPS_GATEWAY_MODE_SELECTED" in
  execute)
    ACTION_EXECUTOR_ENABLED="true"
    UNRESTRICTED_COMMANDS_ENABLED="true"
    ;;
  unrestricted)
    ACTION_EXECUTOR_ENABLED="true"
    UNRESTRICTED_COMMANDS_ENABLED="true"
    ;;
esac

if ! oc whoami >/dev/null 2>&1; then
  echo "oc login이 필요합니다. VPN/hosts 설정 후 oc login을 먼저 수행하세요." >&2
  exit 1
fi

oc -n "$OLS_NAMESPACE" get "svc/${OLS_SERVICE}" >/dev/null

if [ "$(normalize_bool_option "$MANAGE_OLS_PORT_FORWARD")" = "true" ]; then
  : > "$PF_LOG"
  run_port_forward_supervisor &
  PF_SUPERVISOR_PID="$!"

  if ! wait_for_port "$LOCAL_CONNECT_HOST" "$OLS_LOCAL_PORT"; then
    echo "Lightspeed port-forward failed. Log: $PF_LOG" >&2
    cat "$PF_LOG" >&2
    exit 1
  fi
  if ! wait_for_lightspeed_forward; then
    echo "Lightspeed port-forward opened a socket but did not answer HTTPS. Log: $PF_LOG" >&2
    cat "$PF_LOG" >&2
    exit 1
  fi

  echo "Lightspeed endpoint supervised: ${OLS_NAMESPACE}/${OLS_SERVICE} ${OLS_SERVICE_PORT} -> ${GATEWAY_HOST}:${OLS_LOCAL_PORT}"
  echo "Port-forward log: $PF_LOG"
else
  if ! wait_for_lightspeed_forward; then
    echo "Existing Lightspeed port-forward did not answer HTTPS on ${LOCAL_CONNECT_HOST}:${OLS_LOCAL_PORT}." >&2
    echo "Set KUGNUS_MANAGE_OLS_PORT_FORWARD=true or rerun task kugnus:demo:resume to restore it." >&2
    exit 1
  fi

  echo "Lightspeed endpoint verified without local supervisor: ${OLS_NAMESPACE}/${OLS_SERVICE} ${OLS_SERVICE_PORT} -> ${LOCAL_CONNECT_HOST}:${OLS_LOCAL_PORT}"
fi

if [ "$ACTION_EXECUTOR_ENABLED" = "true" ]; then
  oc -n "$ACTION_EXECUTOR_NAMESPACE" get "svc/${ACTION_EXECUTOR_SERVICE}" >/dev/null
  : > "$ACTION_EXECUTOR_PF_LOG"
  if action_executor_forward_healthy; then
    echo "Action Executor endpoint already healthy: http://${LOCAL_CONNECT_HOST}:${ACTION_EXECUTOR_LOCAL_PORT}/healthz"
  elif port_open "$LOCAL_CONNECT_HOST" "$ACTION_EXECUTOR_LOCAL_PORT"; then
    echo "Action Executor local port is open but healthz failed; restarting matching port-forward" >&2
    stop_matching_port_forward "$ACTION_EXECUTOR_NAMESPACE" "$ACTION_EXECUTOR_SERVICE" "$ACTION_EXECUTOR_LOCAL_PORT" "$ACTION_EXECUTOR_SERVICE_PORT"
    if port_open "$LOCAL_CONNECT_HOST" "$ACTION_EXECUTOR_LOCAL_PORT"; then
      echo "Action Executor port ${ACTION_EXECUTOR_LOCAL_PORT} is still occupied but healthz failed." >&2
      ss -ltnp | grep ":${ACTION_EXECUTOR_LOCAL_PORT}" >&2 || true
      exit 1
    fi
  fi

  if ! action_executor_forward_healthy; then
    : > "$ACTION_EXECUTOR_PF_LOG"
    oc -n "$ACTION_EXECUTOR_NAMESPACE" port-forward \
      --address "$GATEWAY_HOST" \
      "svc/${ACTION_EXECUTOR_SERVICE}" \
      "${ACTION_EXECUTOR_LOCAL_PORT}:${ACTION_EXECUTOR_SERVICE_PORT}" \
      >>"$ACTION_EXECUTOR_PF_LOG" 2>&1 &
    ACTION_EXECUTOR_PF_PID="$!"
    if ! wait_for_port "$LOCAL_CONNECT_HOST" "$ACTION_EXECUTOR_LOCAL_PORT"; then
      echo "Action Executor port-forward failed. Log: $ACTION_EXECUTOR_PF_LOG" >&2
      cat "$ACTION_EXECUTOR_PF_LOG" >&2
      exit 1
    fi
    if ! wait_for_action_executor_forward; then
      echo "Action Executor port-forward opened a socket but healthz did not answer. Log: $ACTION_EXECUTOR_PF_LOG" >&2
      cat "$ACTION_EXECUTOR_PF_LOG" >&2
      exit 1
    fi
  else
    ACTION_EXECUTOR_PF_PID=""
  fi
  export KOMSCO_AI_ACTION_EXECUTOR_URL="${KOMSCO_AI_ACTION_EXECUTOR_URL:-http://${LOCAL_CONNECT_HOST}:${ACTION_EXECUTOR_LOCAL_PORT}}"
  echo "Action Executor endpoint: ${KOMSCO_AI_ACTION_EXECUTOR_URL}"
  echo "Action Executor port-forward log: $ACTION_EXECUTOR_PF_LOG"
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
export OLS_BASE_URL="${OLS_BASE_URL:-https://${LOCAL_CONNECT_HOST}:${OLS_LOCAL_PORT}}"
export OLS_CA_FILE="${OLS_CA_FILE:-false}"
export KOMSCO_AI_LLM_PROVIDER="${KOMSCO_AI_LLM_PROVIDER:-lightspeed}"
export KOMSCO_AI_LLM_API_STYLE="${KOMSCO_AI_LLM_API_STYLE:-lightspeed}"
export KOMSCO_AI_LLM_BASE_URL="${KOMSCO_AI_LLM_BASE_URL:-$OLS_BASE_URL}"
export OPENSHIFT_API_URL="${OPENSHIFT_API_URL:-$(oc whoami --show-server)}"
export OPENSHIFT_API_CA_FILE="${OPENSHIFT_API_CA_FILE:-false}"
export KOMSCO_AI_SECURITY_PHASE="${KOMSCO_AI_SECURITY_PHASE:-phase5-action-execution}"
export KOMSCO_AI_PRODUCT_ACCESS_REVIEW_NAME="${KOMSCO_AI_PRODUCT_ACCESS_REVIEW_NAME:-komsco-ai-console-plugin-kugnus}"
export KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS="${KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS:-$UNRESTRICTED_COMMANDS_ENABLED}"
export KOMSCO_AI_UNRESTRICTED_COMMAND_CWD="${KOMSCO_AI_UNRESTRICTED_COMMAND_CWD:-$ROOT_DIR}"
if [ "$ACTION_EXECUTOR_ENABLED" = "true" ]; then
  export KOMSCO_AI_ENABLE_MUTATIONS="${KOMSCO_AI_ENABLE_MUTATIONS:-true}"
else
  export KOMSCO_AI_ENABLE_MUTATIONS="${KOMSCO_AI_ENABLE_MUTATIONS:-false}"
fi

echo "Gateway URL: http://${GATEWAY_HOST}:${GATEWAY_PORT}"
echo "AIOPS_GATEWAY_MODE: ${AIOPS_GATEWAY_MODE_SELECTED}"
echo "ACTION_EXECUTOR: ${ACTION_EXECUTOR_ENABLED}"
echo "KOMSCO_AI_LLM_PROVIDER: ${KOMSCO_AI_LLM_PROVIDER}"
echo "KOMSCO_AI_LLM_API_STYLE: ${KOMSCO_AI_LLM_API_STYLE}"
echo "KOMSCO_AI_LLM_BASE_URL: ${KOMSCO_AI_LLM_BASE_URL}"
echo "KOMSCO_AI_LLM_MODEL: ${KOMSCO_AI_LLM_MODEL:-}"
echo "KOMSCO_AI_EMBEDDING_PROVIDER: ${KOMSCO_AI_EMBEDDING_PROVIDER:-}"
echo "KOMSCO_AI_EMBEDDING_API_STYLE: ${KOMSCO_AI_EMBEDDING_API_STYLE:-}"
echo "KOMSCO_AI_EMBEDDING_BASE_URL: ${KOMSCO_AI_EMBEDDING_BASE_URL:-}"
echo "KOMSCO_AI_EMBEDDING_MODEL: ${KOMSCO_AI_EMBEDDING_MODEL:-}"
echo "KOMSCO_AI_EMBEDDING_DIMENSIONS: ${KOMSCO_AI_EMBEDDING_DIMENSIONS:-}"
echo "OLS_BASE_URL: ${OLS_BASE_URL}"
echo "OLS_CA_FILE: ${OLS_CA_FILE}"
echo "OPENSHIFT_API_URL: ${OPENSHIFT_API_URL}"
echo "OPENSHIFT_API_CA_FILE: ${OPENSHIFT_API_CA_FILE}"
echo "KOMSCO_AI_SECURITY_PHASE: ${KOMSCO_AI_SECURITY_PHASE}"
echo "KOMSCO_AI_ENABLE_MUTATIONS: ${KOMSCO_AI_ENABLE_MUTATIONS}"
echo "KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS: ${KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS}"
echo "KOMSCO_AI_UNRESTRICTED_COMMAND_CWD: ${KOMSCO_AI_UNRESTRICTED_COMMAND_CWD}"
echo "KOMSCO_AI_ACTION_EXECUTOR_URL: ${KOMSCO_AI_ACTION_EXECUTOR_URL:-}"

uvicorn komsco_ai_gateway.main:app \
  --reload \
  --host "$GATEWAY_HOST" \
  --port "$GATEWAY_PORT"
