#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="${ROOT_DIR}/komsco-ai-console-plugin"

PLUGIN_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-komsco-ai-console-plugin-kugnus}"
PLUGIN_PORT="${PLUGIN_PORT:-9001}"
CONSOLE_PORT="${CONSOLE_PORT:-9000}"
CONSOLE_IMAGE="${CONSOLE_IMAGE:-quay.io/openshift/origin-console:latest}"
CONSOLE_IMAGE_PLATFORM="${CONSOLE_IMAGE_PLATFORM:-linux/amd64}"
CONSOLE_CONTAINER_NAME="${CONSOLE_CONTAINER_NAME:-kugnus-local-console}"
CONSOLE_URL="${CONSOLE_URL:-http://127.0.0.1:${CONSOLE_PORT}/dashboards}"
CONSOLE_HEALTH_URL="${CONSOLE_HEALTH_URL:-http://127.0.0.1:${CONSOLE_PORT}/api/kubernetes/version}"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
PLUGIN_LOG="${PLUGIN_LOG:-${ROOT_DIR}/.dev-console-plugin-webpack.log}"
OPEN_BROWSER="${OPEN_BROWSER:-false}"
OPENSHIFT_RELOGIN_COMMAND="${OPENSHIFT_RELOGIN_COMMAND:-}"
OPENSHIFT_WEB_LOGIN_CALLBACK_PORT="${OPENSHIFT_WEB_LOGIN_CALLBACK_PORT:-8280}"
OPENSHIFT_WEB_LOGIN_TIMEOUT_SECONDS="${OPENSHIFT_WEB_LOGIN_TIMEOUT_SECONDS:-180}"
OPENSHIFT_INSECURE_SKIP_TLS_VERIFY="${OPENSHIFT_INSECURE_SKIP_TLS_VERIFY:-false}"

load_env_file() {
  local file="$1"
  local normalized_file
  if [ ! -f "$file" ]; then
    return
  fi

  normalized_file="$(mktemp)"
  tr -d '\r' <"$file" >"$normalized_file"
  set -a
  # shellcheck source=/dev/null
  . "$normalized_file"
  set +a
  rm -f "$normalized_file"
}

load_env_files() {
  if [ "${KOMSCO_AIOPS_SKIP_ENV_FILES:-false}" = "true" ]; then
    return
  fi

  load_env_file "${ROOT_DIR}/.env"
  load_env_file "${ROOT_DIR}/.env.local"
  OPENSHIFT_API_SERVER="${OPENSHIFT_API_SERVER:-${OPENSHIFT_SERVER:-}}"
  OPENSHIFT_USERNAME="${OPENSHIFT_USERNAME:-${OPENSHIFT_USER:-}}"
  OPENSHIFT_PASSWORD="${OPENSHIFT_PASSWORD:-${OPENSHIFT_PASS:-}}"
}

is_wsl() {
  grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null
}

is_truthy() {
  case "${1,,}" in
    1 | true | yes | y | on) return 0 ;;
    *) return 1 ;;
  esac
}

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

wait_for_port_closed() {
  local port="$1"
  local attempts="${2:-80}"

  for _ in $(seq 1 "$attempts"); do
    if ! port_open 127.0.0.1 "$port"; then
      return 0
    fi
    sleep 0.25
  done

  return 1
}

wait_for_url() {
  local url="$1"
  local attempts="${2:-120}"

  for _ in $(seq 1 "$attempts"); do
    if curl -fsS --max-time 3 "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done

  return 1
}

console_code() {
  curl -ksS -o /dev/null -w "%{http_code}" --max-time 5 "$CONSOLE_HEALTH_URL" 2>/dev/null || true
}

open_url() {
  local url="$1"

  if ! is_truthy "$OPEN_BROWSER"; then
    echo "Browser open skipped: ${url}"
    return
  fi

  if command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command "Start-Process '${url}'" >/dev/null
  elif command -v cmd.exe >/dev/null 2>&1; then
    cmd.exe /c start "" "$url" >/dev/null
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$url" >/dev/null 2>&1 || true
  elif command -v gio >/dev/null 2>&1; then
    gio open "$url" >/dev/null 2>&1 || true
  else
    echo "Open this URL: ${url}"
  fi
}

oc_login_from_env() {
  if [ -z "${OPENSHIFT_TOKEN:-}" ] || [ -z "${OPENSHIFT_API_SERVER:-}" ]; then
    return 1
  fi

  local login_args=(login "--token=${OPENSHIFT_TOKEN}" "--server=${OPENSHIFT_API_SERVER}")
  if is_truthy "$OPENSHIFT_INSECURE_SKIP_TLS_VERIFY"; then
    login_args+=(--insecure-skip-tls-verify=true)
  fi
  oc "${login_args[@]}" >/dev/null
}

oc_login_from_credentials() {
  if [ -z "${OPENSHIFT_API_SERVER:-}" ] || [ -z "${OPENSHIFT_USERNAME:-}" ] || [ -z "${OPENSHIFT_PASSWORD:-}" ]; then
    return 1
  fi

  local login_args=(
    login
    "--server=${OPENSHIFT_API_SERVER}"
    "--username=${OPENSHIFT_USERNAME}"
    "--password=${OPENSHIFT_PASSWORD}"
  )
  if is_truthy "$OPENSHIFT_INSECURE_SKIP_TLS_VERIFY"; then
    login_args+=(--insecure-skip-tls-verify=true)
  fi
  oc "${login_args[@]}" >/dev/null
}

oc_login_web() {
  local server="${OPENSHIFT_API_SERVER:-}"
  local log_file
  local login_args=()
  local login_pid
  local login_url=""

  if [ -z "$server" ]; then
    server="$(oc whoami --show-server 2>/dev/null || true)"
  fi
  if [ -z "$server" ]; then
    echo "No OpenShift API server is configured. Run oc login once." >&2
    return 1
  fi

  log_file="$(mktemp)"
  login_args=(login "$server" --web --auto-open-browser=false "--callback-port=${OPENSHIFT_WEB_LOGIN_CALLBACK_PORT}")
  if is_truthy "$OPENSHIFT_INSECURE_SKIP_TLS_VERIFY"; then
    login_args+=(--insecure-skip-tls-verify=true)
  fi

  oc "${login_args[@]}" >"$log_file" 2>&1 &
  login_pid="$!"

  for _ in $(seq 1 40); do
    login_url="$(grep -Eo 'https://[^[:space:]]+' "$log_file" | sed -n '1p' || true)"
    if [ -n "$login_url" ]; then
      break
    fi
    if ! kill -0 "$login_pid" >/dev/null 2>&1; then
      wait "$login_pid" || true
      sed -n '1,80p' "$log_file" >&2
      rm -f "$log_file"
      return 1
    fi
    sleep 0.25
  done

  if [ -z "$login_url" ]; then
    kill "$login_pid" >/dev/null 2>&1 || true
    echo "oc web login did not print a login URL." >&2
    sed -n '1,80p' "$log_file" >&2
    rm -f "$log_file"
    return 1
  fi

  if is_truthy "$OPEN_BROWSER"; then
    echo "Opening OpenShift web login..."
  else
    echo "OpenShift web login URL:"
  fi
  open_url "$login_url"

  for _ in $(seq 1 "$OPENSHIFT_WEB_LOGIN_TIMEOUT_SECONDS"); do
    if ! kill -0 "$login_pid" >/dev/null 2>&1; then
      wait "$login_pid"
      rm -f "$log_file"
      oc whoami >/dev/null
      return 0
    fi
    sleep 1
  done

  kill "$login_pid" >/dev/null 2>&1 || true
  echo "Timed out waiting for OpenShift web login callback." >&2
  rm -f "$log_file"
  return 1
}

ensure_oc_login() {
  if oc whoami >/dev/null 2>&1; then
    return 0
  fi

  if [ -n "${OPENSHIFT_RELOGIN_COMMAND:-}" ] && bash -lc "$OPENSHIFT_RELOGIN_COMMAND" >/dev/null 2>&1 && oc whoami >/dev/null 2>&1; then
    return 0
  fi

  if oc_login_from_env >/dev/null 2>&1 && oc whoami >/dev/null 2>&1; then
    return 0
  fi

  if oc_login_from_credentials >/dev/null 2>&1 && oc whoami >/dev/null 2>&1; then
    return 0
  fi

  oc_login_web
}

ensure_plugin() {
  local manifest_url="http://127.0.0.1:${PLUGIN_PORT}/api/plugins/${PLUGIN_NAME}/plugin-manifest.json"

  if curl -fsS --max-time 3 "$manifest_url" >/dev/null 2>&1; then
    return 0
  fi

  if port_open 127.0.0.1 "$PLUGIN_PORT"; then
    echo "Port ${PLUGIN_PORT} is open but plugin manifest is not healthy: ${manifest_url}" >&2
    return 1
  fi

  if [ ! -d "${PLUGIN_DIR}/node_modules" ]; then
    echo "node_modules missing. Run: cd komsco-ai-console-plugin && yarn install" >&2
    return 1
  fi

  echo "Starting plugin dev server..."
  : >"$PLUGIN_LOG"
  (
    cd "$PLUGIN_DIR"
    exec bash -ic 'yarn start'
  ) >"$PLUGIN_LOG" 2>&1 &

  wait_for_url "$manifest_url" 120 || {
    echo "Plugin dev server did not become healthy. Log: ${PLUGIN_LOG}" >&2
    sed -n '1,120p' "$PLUGIN_LOG" >&2
    return 1
  }
}

stop_console_bridge() {
  local ids=()
  local id

  mapfile -t ids < <(docker ps --filter "name=^/${CONSOLE_CONTAINER_NAME}$" --format '{{.ID}}')
  mapfile -t ids < <(
    {
      printf '%s\n' "${ids[@]}"
      docker ps --filter "ancestor=${CONSOLE_IMAGE}" --format '{{.ID}}'
    } | awk 'NF && !seen[$0]++'
  )

  for id in "${ids[@]}"; do
    if docker port "$id" 9000/tcp 2>/dev/null | grep -q ":${CONSOLE_PORT}$"; then
      docker rm -f "$id" >/dev/null 2>&1 || true
    fi
  done

  if ! wait_for_port_closed "$CONSOLE_PORT"; then
    echo "Port ${CONSOLE_PORT} is still busy:" >&2
    ss -ltnp | grep ":${CONSOLE_PORT} " >&2 || true
    return 1
  fi
}

write_bridge_env() {
  local env_file="$1"
  local plugin_host="localhost"
  local gateway_endpoint="${GATEWAY_ENDPOINT:-}"
  local endpoint
  local token
  local prometheus=""
  local thanos=""
  local alertmanager=""
  local gitops_hostname=""

  if is_wsl; then
    plugin_host="host.docker.internal"
    gateway_endpoint="${gateway_endpoint:-http://host.docker.internal:${GATEWAY_PORT}}"
  else
    gateway_endpoint="${gateway_endpoint:-http://localhost:${GATEWAY_PORT}}"
  fi

  endpoint="$(oc whoami --show-server)"
  token="$(oc whoami --show-token)"
  prometheus="$(oc -n openshift-config-managed get configmap monitoring-shared-config -o jsonpath='{.data.prometheusPublicURL}' 2>/dev/null || true)"
  thanos="$(oc -n openshift-config-managed get configmap monitoring-shared-config -o jsonpath='{.data.thanosPublicURL}' 2>/dev/null || true)"
  alertmanager="$(oc -n openshift-config-managed get configmap monitoring-shared-config -o jsonpath='{.data.alertmanagerPublicURL}' 2>/dev/null || true)"
  gitops_hostname="$(oc -n openshift-gitops get route cluster -o jsonpath='{.spec.host}' 2>/dev/null || true)"

  {
    echo "BRIDGE_USER_AUTH=disabled"
    echo "BRIDGE_K8S_MODE=off-cluster"
    echo "BRIDGE_K8S_AUTH=bearer-token"
    echo "BRIDGE_K8S_MODE_OFF_CLUSTER_SKIP_VERIFY_TLS=true"
    echo "BRIDGE_K8S_MODE_OFF_CLUSTER_ENDPOINT=${endpoint}"
    echo "BRIDGE_K8S_AUTH_BEARER_TOKEN=${token}"
    echo "BRIDGE_USER_SETTINGS_LOCATION=localstorage"
    echo "BRIDGE_I18N_NAMESPACES=plugin__${PLUGIN_NAME}"
    echo "BRIDGE_PROMETHEUS_PUBLIC_URL=${prometheus}"
    echo "BRIDGE_THANOS_PUBLIC_URL=${thanos}"
    echo "BRIDGE_ALERMANAGER_PUBLIC_URL=${alertmanager}"
    echo "BRIDGE_K8S_MODE_OFF_CLUSTER_THANOS=${thanos}"
    echo "BRIDGE_K8S_MODE_OFF_CLUSTER_ALERTMANAGER=${alertmanager}"
    echo "BRIDGE_PLUGINS=${PLUGIN_NAME}=http://${plugin_host}:${PLUGIN_PORT}/api/plugins/${PLUGIN_NAME}"
    printf 'BRIDGE_PLUGIN_PROXY={"services":[{"consoleAPIPath":"/api/proxy/plugin/%s/ai-gateway/","endpoint":"%s","authorize":true}]}\n' "$PLUGIN_NAME" "$gateway_endpoint"
    if [ -n "$gitops_hostname" ]; then
      echo "BRIDGE_K8S_MODE_OFF_CLUSTER_GITOPS=https://${gitops_hostname}"
    fi
  } >"$env_file"
}

start_console_bridge() {
  local env_file
  local code

  env_file="$(mktemp)"
  write_bridge_env "$env_file"
  docker rm -f "$CONSOLE_CONTAINER_NAME" >/dev/null 2>&1 || true
  docker run -d --name "$CONSOLE_CONTAINER_NAME" --platform "$CONSOLE_IMAGE_PLATFORM" -p "${CONSOLE_PORT}:9000" --env-file "$env_file" "$CONSOLE_IMAGE" >/dev/null
  rm -f "$env_file"

  for _ in $(seq 1 120); do
    code="$(console_code)"
    if [ "$code" = "200" ]; then
      return 0
    fi
    sleep 0.5
  done

  echo "Console bridge did not become healthy. HTTP ${code:-000}" >&2
  docker logs --tail 120 "$CONSOLE_CONTAINER_NAME" >&2 || true
  return 1
}

ensure_console() {
  local code

  code="$(console_code)"
  if [ "$code" = "200" ]; then
    return 0
  fi

  if port_open 127.0.0.1 "$CONSOLE_PORT"; then
    echo "Restarting stale console bridge: ${CONSOLE_HEALTH_URL} returned HTTP ${code:-000}"
  else
    echo "Starting console bridge..."
  fi

  stop_console_bridge
  start_console_bridge
}

main() {
  load_env_files
  require_cmd oc
  require_cmd curl
  require_cmd docker

  cd "$ROOT_DIR"
  ensure_oc_login
  ensure_plugin
  ensure_console
  open_url "$CONSOLE_URL"

  echo "OKD console ready: ${CONSOLE_URL}"
  echo "Console API health: ${CONSOLE_HEALTH_URL} -> $(console_code)"
}

main "$@"
