#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLUGIN_DIR="${ROOT_DIR}/komsco-ai-console-plugin"

# shellcheck source=lib/safe-env.sh
. "${ROOT_DIR}/scripts/lib/safe-env.sh"

load_env_files() {
  if [ "${KOMSCO_AIOPS_SKIP_ENV_FILES:-false}" = "true" ]; then
    return
  fi

  load_env_file "${ROOT_DIR}/.env"
  load_env_file "${ROOT_DIR}/.env.local"
  unset_placeholder_env_vars OPENSHIFT_API_SERVER OPENSHIFT_SERVER OPENSHIFT_NAMESPACE
  OPENSHIFT_API_SERVER="${OPENSHIFT_API_SERVER:-${OPENSHIFT_SERVER:-}}"
  OPENSHIFT_USERNAME="${OPENSHIFT_USERNAME:-${OPENSHIFT_USER:-}}"
  OPENSHIFT_PASSWORD="${OPENSHIFT_PASSWORD:-${OPENSHIFT_PASS:-}}"
}

load_env_files

is_wsl() {
  grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null
}

PLUGIN_HOST="${PLUGIN_HOST:-127.0.0.1}"
PLUGIN_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-cywell-aiops-console-plugin}"
PLUGIN_PORT="${PLUGIN_PORT:-9001}"
CONSOLE_PORT="${CONSOLE_PORT:-9000}"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
GATEWAY_ENDPOINT="$(normalize_gateway_endpoint_for_console_bridge "${GATEWAY_ENDPOINT:-}" "$GATEWAY_PORT")"
INSTALL_DEPS="${INSTALL_DEPS:-false}"
PLUGIN_LOG="${PLUGIN_LOG:-${ROOT_DIR}/.dev-console-plugin-webpack.log}"
CONSOLE_LOG="${CONSOLE_LOG:-${ROOT_DIR}/.dev-console-plugin-console.log}"
YARN_CLI="${YARN_CLI:-${PLUGIN_DIR}/.yarn/releases/yarn-4.13.0.cjs}"
CONSOLE_TOKEN_CHECK_INTERVAL="${CONSOLE_TOKEN_CHECK_INTERVAL:-60}"
CONSOLE_HEALTH_URL="${CONSOLE_HEALTH_URL:-http://127.0.0.1:${CONSOLE_PORT}/api/kubernetes/version}"
PLUGIN_STARTUP_WAIT_ATTEMPTS="${PLUGIN_STARTUP_WAIT_ATTEMPTS:-1200}"
CONSOLE_STARTUP_WAIT_ATTEMPTS="${CONSOLE_STARTUP_WAIT_ATTEMPTS:-1200}"
OPENSHIFT_INSECURE_SKIP_TLS_VERIFY="${OPENSHIFT_INSECURE_SKIP_TLS_VERIFY:-false}"
OPENSHIFT_RELOGIN_COMMAND="${OPENSHIFT_RELOGIN_COMMAND:-}"

PLUGIN_PID=""
CONSOLE_PID=""
TOKEN_FINGERPRINT=""

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

run_yarn() {
  if command -v yarn >/dev/null 2>&1; then
    yarn "$@"
    return
  fi

  if [ -f "$YARN_CLI" ]; then
    node "$YARN_CLI" "$@"
    return
  fi

  echo "Missing yarn. Install yarn or keep ${YARN_CLI} available." >&2
  exit 1
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

wait_for_port_closed() {
  local host="$1"
  local port="$2"
  local attempts="${3:-80}"

  for _ in $(seq 1 "$attempts"); do
    if ! port_open "$host" "$port"; then
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

  local descendants=()
  if command -v pgrep >/dev/null 2>&1; then
    mapfile -t descendants < <(descendant_pids "$pid")
  fi

  if [ "${#descendants[@]}" -gt 0 ]; then
    kill -TERM "${descendants[@]}" >/dev/null 2>&1 || true
  fi
  kill "$pid" >/dev/null 2>&1 || true
  wait "$pid" >/dev/null 2>&1 || true
}

descendant_pids() {
  local parent="$1"
  local child

  while IFS= read -r child; do
    descendant_pids "$child"
    echo "$child"
  done < <(pgrep -P "$parent" 2>/dev/null || true)
}

is_truthy() {
  case "${1,,}" in
    1 | true | yes | y | on) return 0 ;;
    *) return 1 ;;
  esac
}

token_fingerprint() {
  local token="$1"
  if [ -z "$token" ]; then
    return 1
  fi

  printf "%s" "$token" | sha256sum | awk '{print $1}'
}

has_relogin_credentials() {
  [ -n "${OPENSHIFT_API_SERVER:-}" ] && [ -n "${OPENSHIFT_USERNAME:-}" ] && [ -n "${OPENSHIFT_PASSWORD:-}" ]
}

oc_login_from_credentials() {
  if ! has_relogin_credentials; then
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

  timeout "${OPENSHIFT_LOGIN_TIMEOUT_SECONDS:-30}s" oc "${login_args[@]}" >/dev/null

  if [ -n "${OPENSHIFT_NAMESPACE:-}" ]; then
    oc_quick project "$OPENSHIFT_NAMESPACE" >/dev/null
  fi

  oc_quick whoami >/dev/null
}

run_relogin_command() {
  local reason="$1"

  echo "Refreshing oc login: ${reason}"

  if [ -n "${OPENSHIFT_RELOGIN_COMMAND:-}" ]; then
    run_shell_with_timeout "$OPENSHIFT_RELOGIN_COMMAND" >/dev/null

    if [ -n "${OPENSHIFT_NAMESPACE:-}" ]; then
      oc_quick project "$OPENSHIFT_NAMESPACE" >/dev/null
    fi

    oc_quick whoami >/dev/null
    return $?
  fi

  oc_login_from_credentials
}

ensure_oc_login() {
  load_env_files

  if [ -n "${OPENSHIFT_RELOGIN_COMMAND:-}" ] || has_relogin_credentials; then
    if oc_quick whoami >/dev/null 2>&1; then
      return 0
    fi

    if ! run_relogin_command "current oc login is invalid"; then
      echo "OPENSHIFT_RELOGIN_COMMAND or OPENSHIFT_USERNAME/PASSWORD did not produce a valid oc login." >&2
      return 1
    fi
    return 0
  fi

  oc_quick whoami >/dev/null 2>&1
}

current_token_fingerprint() {
  if ! ensure_oc_login >/dev/null 2>&1; then
    return 1
  fi

  local token
  token="$(oc_quick whoami -t 2>/dev/null || true)"
  if [ -z "$token" ]; then
    return 1
  fi
  token_fingerprint "$token"
}

console_health_status() {
  curl -ksS -o /dev/null -w "%{http_code}" --max-time 10 "$CONSOLE_HEALTH_URL" 2>/dev/null || true
}

stop_console() {
  if [ -n "$CONSOLE_PID" ]; then
    kill_tree "$CONSOLE_PID"
    CONSOLE_PID=""
  fi
  wait_for_port_closed "127.0.0.1" "$CONSOLE_PORT" || true
}

start_console() {
  TOKEN_FINGERPRINT="$(current_token_fingerprint || true)"
  if [ -z "$TOKEN_FINGERPRINT" ]; then
    echo "oc login이 필요합니다. VPN/hosts 설정 후 oc login을 먼저 수행하세요." >&2
    return 1
  fi

  if port_open "127.0.0.1" "$CONSOLE_PORT"; then
    echo "Console port ${CONSOLE_PORT} is already in use. Stop the old local console bridge first." >&2
    return 1
  fi

  printf '[%s] Starting local console bridge with current oc token\n' "$(date -Is)" >>"$CONSOLE_LOG"
  run_yarn start-console >>"$CONSOLE_LOG" 2>&1 &
  CONSOLE_PID="$!"

  if ! wait_for_port "127.0.0.1" "$CONSOLE_PORT" "$CONSOLE_STARTUP_WAIT_ATTEMPTS"; then
    echo "Console bridge failed. Log: $CONSOLE_LOG" >&2
    cat "$CONSOLE_LOG" >&2
    return 1
  fi

  echo "Console bridge log: $CONSOLE_LOG"
}

restart_console() {
  local reason="$1"

  echo "Restarting local console bridge: ${reason}"
  stop_console
  if ! wait_for_port_closed "127.0.0.1" "$CONSOLE_PORT"; then
    echo "Console port ${CONSOLE_PORT} is still open after restart request." >&2
    return 1
  fi
  start_console
}

cleanup() {
  kill_tree "$CONSOLE_PID"
  kill_tree "$PLUGIN_PID"
}

trap cleanup EXIT INT TERM

require_cmd oc
require_cmd curl
require_cmd sha256sum
require_cmd node

if ! ensure_oc_login; then
  echo "oc login이 필요합니다. OPENSHIFT_TOKEN을 env에 넣지 말고 oc login 후 현재 토큰을 oc whoami -t로 조회하게 하세요." >&2
  exit 1
fi

cd "$PLUGIN_DIR"

if [ "$INSTALL_DEPS" = "true" ]; then
  run_yarn install
elif [ ! -d node_modules ]; then
  echo "node_modules가 없습니다. INSTALL_DEPS=true task fe:dev 또는 cd komsco-ai-console-plugin && yarn install을 실행하세요." >&2
  exit 1
fi

if port_open "$PLUGIN_HOST" "$PLUGIN_PORT"; then
  echo "Using existing plugin dev server: http://${PLUGIN_HOST}:${PLUGIN_PORT}"
else
  : > "$PLUGIN_LOG"
  run_yarn start >"$PLUGIN_LOG" 2>&1 &
  PLUGIN_PID="$!"

  if ! wait_for_port "$PLUGIN_HOST" "$PLUGIN_PORT" "$PLUGIN_STARTUP_WAIT_ATTEMPTS"; then
    echo "Plugin dev server failed. Log: $PLUGIN_LOG" >&2
    cat "$PLUGIN_LOG" >&2
    exit 1
  fi

  echo "Plugin dev server: http://${PLUGIN_HOST}:${PLUGIN_PORT}"
  echo "Plugin dev log: $PLUGIN_LOG"
fi

export CONSOLE_PORT
EXPECTED_PROXY_PATH="/api/proxy/plugin/${PLUGIN_NAME}/ai-gateway/"
if [ -n "${BRIDGE_PLUGIN_PROXY:-}" ] &&
  [ "${KOMSCO_AIOPS_ALLOW_CUSTOM_BRIDGE_PROXY:-false}" = "true" ] &&
  [[ "$BRIDGE_PLUGIN_PROXY" == *"$EXPECTED_PROXY_PATH"* ]]; then
  :
else
  BRIDGE_PLUGIN_PROXY=$(printf '{"services":[{"consoleAPIPath":"/api/proxy/plugin/%s/ai-gateway/","endpoint":"%s","authorize":true}]}' "$PLUGIN_NAME" "$GATEWAY_ENDPOINT")
fi
export BRIDGE_PLUGIN_PROXY

echo "Gateway proxy endpoint: ${GATEWAY_ENDPOINT}"
echo "Bridge plugin proxy path: ${EXPECTED_PROXY_PATH}"
echo "Console URL: http://localhost:${CONSOLE_PORT}"

start_console

while true; do
  sleep "$CONSOLE_TOKEN_CHECK_INTERVAL"

  if [ -n "$CONSOLE_PID" ] && ! kill -0 "$CONSOLE_PID" >/dev/null 2>&1; then
    wait "$CONSOLE_PID" >/dev/null 2>&1 || true
    CONSOLE_PID=""
    restart_console "console process exited"
    continue
  fi

  next_fingerprint="$(current_token_fingerprint || true)"
  if [ -z "$next_fingerprint" ]; then
    if run_relogin_command "periodic oc login check failed"; then
      restart_console "oc login refreshed"
    else
      echo "oc login is not valid. Refresh oc login; the bridge will restart after a valid token is available." >&2
      stop_console
    fi
    continue
  fi

  if [ -z "$CONSOLE_PID" ]; then
    start_console
    continue
  fi

  if [ "$next_fingerprint" != "$TOKEN_FINGERPRINT" ]; then
    restart_console "oc token changed"
    continue
  fi

  health_status="$(console_health_status)"
  if [ "$health_status" = "401" ] || [ "$health_status" = "403" ]; then
    if run_relogin_command "Kubernetes API returned HTTP ${health_status}"; then
      restart_console "oc login refreshed after Kubernetes API HTTP ${health_status}"
    else
      echo "Kubernetes API returned HTTP ${health_status}; no valid auto-refresh credential source is configured." >&2
      stop_console
    fi
    continue
  fi
done
