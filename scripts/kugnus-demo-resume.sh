#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="${ROOT_DIR}/.tmp-kugnus-demo"

OC_TIMEOUT="${KUGNUS_RESUME_OC_TIMEOUT_SECONDS:-10}"
GATEWAY_URL="${KUGNUS_GATEWAY_URL:-http://127.0.0.1:18080}"
CONSOLE_URL="${KUGNUS_CONSOLE_URL:-http://127.0.0.1:9000/dashboards}"
CONSOLE_HEALTH_URL="${KUGNUS_CONSOLE_HEALTH_URL:-http://127.0.0.1:9000/api/kubernetes/version}"
PLUGIN_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-cywell-aiops-console-plugin}"
PLUGIN_BASE_URL="${KUGNUS_PLUGIN_BASE_URL:-http://127.0.0.1:9001/api/plugins/${PLUGIN_NAME}}"
PLUGIN_MANIFEST_URL="${KUGNUS_PLUGIN_MANIFEST_URL:-${PLUGIN_BASE_URL}/plugin-manifest.json}"
STARTUP_ATTEMPTS="${KUGNUS_RESUME_STARTUP_ATTEMPTS:-160}"
RUN_STRICT_GATE="${KUGNUS_RESUME_RUN_STRICT_GATE:-true}"
ENSURE_RAG_BACKEND="${KUGNUS_RESUME_ENSURE_RAG_BACKEND:-true}"

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

plugin_assets_healthy() {
  local path
  local required_assets=(
    "plugin-manifest.json"
    "plugin-entry.js"
    "exposed-useAssistantOverlay-chunk.js"
    "exposed-NullContextProvider-chunk.js"
    "components_AssistantLauncher_tsx-chunk.js"
  )

  for path in "${required_assets[@]}"; do
    if ! http_ok "${PLUGIN_BASE_URL}/${path}"; then
      return 1
    fi
  done

  return 0
}

port_forward_healthy() {
  local label="$1"
  local local_port="$2"

  case "$label" in
    lightspeed-port-forward)
      https_responds "https://127.0.0.1:${local_port}/"
      ;;
    action-executor-port-forward)
      http_ok "http://127.0.0.1:${local_port}/healthz"
      ;;
    *)
      port_open "127.0.0.1" "$local_port"
      ;;
  esac
}

wait_for_port_forward_health() {
  local label="$1"
  local local_port="$2"
  local attempts="${3:-40}"

  for _ in $(seq 1 "$attempts"); do
    if port_forward_healthy "$label" "$local_port"; then
      return 0
    fi
    sleep 0.5
  done

  return 1
}

start_detached() {
  local __pid_var="$1"
  local log_file="$2"
  shift 2

  if command -v setsid >/dev/null 2>&1; then
    setsid "$@" </dev/null >>"$log_file" 2>&1 &
  else
    nohup "$@" </dev/null >>"$log_file" 2>&1 &
  fi
  printf -v "$__pid_var" '%s' "$!"
  disown "${!__pid_var}" >/dev/null 2>&1 || true
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
    log "stopping stale port-forward pid=${pid}: ${namespace}/${service} ${local_port}:${service_port}"
    kill "$pid" >/dev/null 2>&1 || true
    matched="true"
  done < <(ps -eo pid=,args=)

  if [ "$matched" = "true" ]; then
    for _ in $(seq 1 20); do
      if ! port_open "127.0.0.1" "$local_port"; then
        return 0
      fi
      sleep 0.25
    done
  fi
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
  local pid=""
  start_detached pid "$log_file" bash -c 'cd "$1" && shift && exec "$@"' bash "$ROOT_DIR" "$@"
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
    if port_forward_healthy "$label" "$local_port"; then
      log "${label} already healthy on 127.0.0.1:${local_port}"
      return
    fi
    log "${label} is listening on 127.0.0.1:${local_port}, but its service probe failed; restarting matching port-forward"
    stop_matching_port_forward "$namespace" "$service" "$local_port" "$service_port"
    if port_open "127.0.0.1" "$local_port"; then
      ss -ltnp | grep ":${local_port}" >&2 || true
      fail "${label} port ${local_port} is still occupied but failed its service probe. Stop the stale listener, then rerun."
    fi
  fi

  if ! timeout "$OC_TIMEOUT" oc -n "$namespace" get "svc/${service}" >/dev/null 2>"${LOG_DIR}/${label}-oc-get.err"; then
    sed -n '1,20p' "${LOG_DIR}/${label}-oc-get.err" >&2 || true
    fail "cannot read ${namespace}/${service}. Check oc login, VPN, RBAC, and namespace/service name."
  fi
  log "starting ${label}: ${namespace}/${service} ${local_port}:${service_port}"
  : >"$log_file"
  local pid=""
  start_detached pid "$log_file" oc -n "$namespace" port-forward \
    --address 0.0.0.0 \
    "svc/${service}" \
    "${local_port}:${service_port}"
  printf '%s\n' "$pid" >"$pid_file"

  if ! wait_for_port "127.0.0.1" "$local_port" 80; then
    sed -n '1,80p' "$log_file" >&2 || true
    fail "${label} did not become ready on port ${local_port}"
  fi
  if ! wait_for_port_forward_health "$label" "$local_port" 40; then
    sed -n '1,120p' "$log_file" >&2 || true
    fail "${label} opened port ${local_port}, but the service probe did not answer"
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

  start_background "gateway" env INSTALL_DEPS=false KUGNUS_MANAGE_OLS_PORT_FORWARD=false task kugnus:dev:be:execute:rag
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

ensure_rag_backend() {
  local log_file="${LOG_DIR}/rag-pgvector.log"

  if [ "$ENSURE_RAG_BACKEND" != "true" ]; then
    log "RAG pgvector backend skipped by KUGNUS_RESUME_ENSURE_RAG_BACKEND=false"
    return
  fi

  log "ensuring RAG pgvector backend; log=${log_file}"
  : >"$log_file"
  if ! bash "${ROOT_DIR}/scripts/kugnus-rag-pgvector-dev.sh" >>"$log_file" 2>&1; then
    sed -n '1,160p' "$log_file" >&2 || true
    fail "RAG pgvector backend did not become ready"
  fi
  log "RAG pgvector backend ready"
}

ensure_console() {
  if http_ok "$CONSOLE_HEALTH_URL" && plugin_assets_healthy; then
    log "Console bridge already healthy: ${CONSOLE_HEALTH_URL}"
    log "Plugin assets healthy: ${PLUGIN_BASE_URL}"
    return
  fi

  log "repairing local OKD console bridge with real API health check"
  KUGNUS_OKD_CONSOLE_REPAIR=true \
    KUGNUS_OKD_CONSOLE_OPEN=false \
    bash "${ROOT_DIR}/scripts/kugnus-okd-console-morning.sh"

  if http_ok "$CONSOLE_HEALTH_URL" && plugin_assets_healthy; then
    log "Console ready: ${CONSOLE_URL}"
    return
  fi

  fail "Console bridge did not become healthy after repair. Check ${CONSOLE_HEALTH_URL} and plugin assets under ${PLUGIN_BASE_URL}."
}

ensure_plugin_manifest_state() {
  if plugin_assets_healthy; then
    log "Plugin assets healthy: ${PLUGIN_BASE_URL}"
    return
  fi

  if port_open "127.0.0.1" 9001; then
    ss -ltnp | grep ':9001' >&2 || true
    fail "port 9001 is listening, but required plugin assets are incomplete under ${PLUGIN_BASE_URL}. Stop the stale webpack dev server first."
  fi

  log "Plugin assets are not healthy yet; frontend task will start webpack."
}

run_verification() {
  log "running doctor"
  KUGNUS_DOCTOR_OC_TIMEOUT_SECONDS="$OC_TIMEOUT" task kugnus:dev:doctor

  log "running runtime smoke"
  task kugnus:runtime:smoke

  if [ "$RUN_STRICT_GATE" = "true" ]; then
    local lightspeed_status=0
    local audit_status=0

    log "running strict Lightspeed final response gate"
    task kugnus:lightspeed:live-verify || lightspeed_status=$?

    log "running strict demo audit"
    task kugnus:strict:audit || audit_status=$?

    if [ "$lightspeed_status" -ne 0 ]; then
      return "$lightspeed_status"
    fi
    if [ "$audit_status" -ne 0 ]; then
      return "$audit_status"
    fi
  else
    log "strict Lightspeed final response gate skipped by KUGNUS_RESUME_RUN_STRICT_GATE=false"
  fi
}

main() {
  need_cmd bash
  need_cmd curl
  need_cmd docker
  need_cmd oc
  need_cmd task
  need_cmd timeout

  cd "$ROOT_DIR"
  log "Kugnus local demo resume started"
  log "repo=${ROOT_DIR}"

  require_oc_login
  ensure_rag_backend
  ensure_port_forward "lightspeed-port-forward" "$OLS_NAMESPACE" "$OLS_SERVICE" "$OLS_LOCAL_PORT" "$OLS_SERVICE_PORT"
  ensure_port_forward "action-executor-port-forward" "$ACTION_EXECUTOR_NAMESPACE" "$ACTION_EXECUTOR_SERVICE" "$ACTION_EXECUTOR_LOCAL_PORT" "$ACTION_EXECUTOR_SERVICE_PORT"
  ensure_gateway

  ensure_plugin_manifest_state
  ensure_console
  run_verification

  log "Kugnus local demo resume finished"
}

main "$@"
