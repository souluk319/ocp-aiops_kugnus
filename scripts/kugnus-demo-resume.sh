#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/.tmp-kugnus-demo"

OC_TIMEOUT="${KUGNUS_RESUME_OC_TIMEOUT_SECONDS:-10}"
GATEWAY_URL="${KUGNUS_GATEWAY_URL:-http://127.0.0.1:18080}"
CONSOLE_URL="${KUGNUS_CONSOLE_URL:-http://127.0.0.1:9000/dashboards}"
PLUGIN_MANIFEST_URL="${KUGNUS_PLUGIN_MANIFEST_URL:-http://127.0.0.1:9001/plugin-manifest.json}"
STARTUP_ATTEMPTS="${KUGNUS_RESUME_STARTUP_ATTEMPTS:-160}"
RUN_STRICT_GATE="${KUGNUS_RESUME_RUN_STRICT_GATE:-true}"

OLS_NAMESPACE="${OLS_NAMESPACE:-openshift-lightspeed}"
OLS_SERVICE="${OLS_SERVICE:-lightspeed-app-server}"
OLS_LOCAL_PORT="${OLS_LOCAL_PORT:-18443}"
OLS_SERVICE_PORT="${OLS_SERVICE_PORT:-8443}"

ACTION_EXECUTOR_NAMESPACE="${ACTION_EXECUTOR_NAMESPACE:-komsco-ai-dev}"
ACTION_EXECUTOR_SERVICE="${ACTION_EXECUTOR_SERVICE:-komsco-ai-action-executor}"
ACTION_EXECUTOR_LOCAL_PORT="${ACTION_EXECUTOR_LOCAL_PORT:-18083}"
ACTION_EXECUTOR_SERVICE_PORT="${ACTION_EXECUTOR_SERVICE_PORT:-8080}"

mkdir -p "$LOG_DIR"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

fail() {
  printf '[FAIL] %s\n' "$*" >&2
  exit 1
}

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    fail "Missing required command: $1"
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
  local attempts="${3:-$STARTUP_ATTEMPTS}"

  for _ in $(seq 1 "$attempts"); do
    if port_open "$host" "$port"; then
      return 0
    fi
    sleep 0.5
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

require_oc_login() {
  local user=""

  if ! timeout "$OC_TIMEOUT" oc whoami >/tmp/kugnus-demo-oc-whoami.out 2>/tmp/kugnus-demo-oc-whoami.err; then
    printf '[FAIL] oc login is not valid or OpenShift API did not answer within %ss.\n' "$OC_TIMEOUT" >&2
    printf '       Run oc login first, then rerun: task kugnus:demo:resume\n' >&2
    printf '       If this repeats, run: task kugnus:ocp:doctor\n' >&2
    sed -n '1,6p' /tmp/kugnus-demo-oc-whoami.err >&2 || true
    exit 1
  fi

  user="$(tr -d '\r\n' </tmp/kugnus-demo-oc-whoami.out)"
  if [ -z "$user" ]; then
    fail "oc whoami returned an empty user. Run oc login again; if it repeats, run: task kugnus:ocp:doctor"
  fi

  log "oc login OK: ${user}"
  log "oc server: $(timeout "$OC_TIMEOUT" oc whoami --show-server 2>/dev/null || printf 'unknown')"
}

start_background() {
  local name="$1"
  shift
  local log_file="${LOG_DIR}/${name}.log"
  local pid_file="${LOG_DIR}/${name}.pid"

  log "starting ${name}; log=${log_file}"
  : >"$log_file"
  (
    cd "$ROOT_DIR"
    exec "$@"
  ) >>"$log_file" 2>&1 &
  local pid="$!"
  printf '%s\n' "$pid" >"$pid_file"
  log "${name} pid=${pid}"
}

ensure_port_forward() {
  local label="$1"
  local namespace="$2"
  local service="$3"
  local local_port="$4"
  local service_port="$5"
  local log_file="${LOG_DIR}/${label}.log"
  local pid_file="${LOG_DIR}/${label}.pid"

  if port_open "127.0.0.1" "$local_port"; then
    log "${label} already listening on 127.0.0.1:${local_port}"
    return
  fi

  if ! timeout "$OC_TIMEOUT" oc -n "$namespace" get "svc/${service}" >/dev/null 2>"${LOG_DIR}/${label}-oc-get.err"; then
    sed -n '1,20p' "${LOG_DIR}/${label}-oc-get.err" >&2 || true
    fail "cannot read ${namespace}/${service}. Check oc login, VPN, RBAC, and namespace/service name."
  fi
  log "starting ${label}: ${namespace}/${service} ${local_port}:${service_port}"
  : >"$log_file"
  oc -n "$namespace" port-forward \
    --address 0.0.0.0 \
    "svc/${service}" \
    "${local_port}:${service_port}" \
    >>"$log_file" 2>&1 &
  local pid="$!"
  printf '%s\n' "$pid" >"$pid_file"

  if ! wait_for_port "127.0.0.1" "$local_port" 80; then
    sed -n '1,80p' "$log_file" >&2 || true
    fail "${label} did not become ready on port ${local_port}"
  fi
  log "${label} ready on 127.0.0.1:${local_port}"
}

ensure_gateway() {
  if http_ok "${GATEWAY_URL}/healthz"; then
    log "Gateway already healthy: ${GATEWAY_URL}/healthz"
    return
  fi

  if port_open "127.0.0.1" 18080; then
    ss -ltnp | grep ':18080' >&2 || true
    fail "port 18080 is listening, but ${GATEWAY_URL}/healthz is not healthy. Stop the stale gateway first."
  fi

  start_background "gateway" env INSTALL_DEPS=false task kugnus:dev:be:execute:rag
  for _ in $(seq 1 "$STARTUP_ATTEMPTS"); do
    if http_ok "${GATEWAY_URL}/healthz"; then
      log "Gateway ready: ${GATEWAY_URL}/healthz"
      return
    fi
    sleep 0.5
  done

  sed -n '1,160p' "${LOG_DIR}/gateway.log" >&2 || true
  fail "Gateway did not become healthy"
}

ensure_console() {
  if http_ok "$CONSOLE_URL"; then
    log "Console already healthy: ${CONSOLE_URL}"
    return
  fi

  if port_open "127.0.0.1" 9000; then
    ss -ltnp | grep ':9000' >&2 || true
    fail "port 9000 is listening, but ${CONSOLE_URL} is not healthy. Stop the stale console bridge first."
  fi

  start_background "frontend" env INSTALL_DEPS=false task kugnus:dev:fe
  for _ in $(seq 1 "$STARTUP_ATTEMPTS"); do
    if http_ok "$CONSOLE_URL"; then
      log "Console ready: ${CONSOLE_URL}"
      return
    fi
    sleep 0.5
  done

  sed -n '1,180p' "${LOG_DIR}/frontend.log" >&2 || true
  fail "Console bridge did not become healthy"
}

ensure_plugin_manifest_state() {
  if http_ok "$PLUGIN_MANIFEST_URL"; then
    log "Plugin manifest healthy: ${PLUGIN_MANIFEST_URL}"
    return
  fi

  if port_open "127.0.0.1" 9001; then
    ss -ltnp | grep ':9001' >&2 || true
    fail "port 9001 is listening, but ${PLUGIN_MANIFEST_URL} is not healthy. Stop the stale webpack dev server first."
  fi

  log "Plugin manifest is not healthy yet; frontend task will start webpack."
}

run_verification() {
  log "running doctor"
  KUGNUS_DOCTOR_OC_TIMEOUT_SECONDS="$OC_TIMEOUT" task kugnus:dev:doctor

  log "running runtime smoke"
  task kugnus:runtime:smoke

  if [ "$RUN_STRICT_GATE" = "true" ]; then
    log "running strict Lightspeed final response gate"
    task kugnus:lightspeed:live-verify
  else
    log "strict Lightspeed final response gate skipped by KUGNUS_RESUME_RUN_STRICT_GATE=false"
  fi
}

main() {
  need_cmd bash
  need_cmd curl
  need_cmd oc
  need_cmd task
  need_cmd timeout

  cd "$ROOT_DIR"
  log "Kugnus local demo resume started"
  log "repo=${ROOT_DIR}"

  require_oc_login
  ensure_port_forward "lightspeed-port-forward" "$OLS_NAMESPACE" "$OLS_SERVICE" "$OLS_LOCAL_PORT" "$OLS_SERVICE_PORT"
  ensure_port_forward "action-executor-port-forward" "$ACTION_EXECUTOR_NAMESPACE" "$ACTION_EXECUTOR_SERVICE" "$ACTION_EXECUTOR_LOCAL_PORT" "$ACTION_EXECUTOR_SERVICE_PORT"
  ensure_gateway

  ensure_plugin_manifest_state
  ensure_console
  run_verification

  log "Kugnus local demo resume finished"
}

main "$@"
