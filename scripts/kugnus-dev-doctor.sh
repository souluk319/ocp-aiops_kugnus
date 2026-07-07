#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_API_SERVER="${EXPECTED_API_SERVER:-https://api.ocp.cywell.server:6443}"
PLUGIN_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-cywell-aiops-console-plugin}"
PLUGIN_PORT="${PLUGIN_PORT:-9001}"
CONSOLE_PORT="${CONSOLE_PORT:-9000}"
GATEWAY_PORT="${GATEWAY_PORT:-18080}"
LOCAL_FIXTURE_PORT="${AIOPS_LOCAL_FIXTURE_PORT:-5174}"
OC_TIMEOUT_SECONDS="${KUGNUS_DOCTOR_OC_TIMEOUT_SECONDS:-10}"
OCP_LADDER_REPORT="${KUGNUS_OCP_LADDER_REPORT:-${ROOT_DIR}/docs/Ver.0.1.5/ocp-connectivity-ladder-report.json}"

# shellcheck source=lib/safe-env.sh
. "${ROOT_DIR}/scripts/lib/safe-env.sh"

PASS_COUNT=0
WARN_COUNT=0
FAIL_COUNT=0

print_section() {
  printf '\n== %s ==\n' "$1"
}

pass() {
  PASS_COUNT=$((PASS_COUNT + 1))
  printf '[PASS] %s\n' "$1"
}

warn() {
  WARN_COUNT=$((WARN_COUNT + 1))
  printf '[WARN] %s\n' "$1"
}

fail() {
  FAIL_COUNT=$((FAIL_COUNT + 1))
  printf '[FAIL] %s\n' "$1"
}

info() {
  printf '       %s\n' "$1"
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

is_wsl() {
  grep -qiE 'microsoft|wsl' /proc/version 2>/dev/null
}

is_windows_path() {
  case "$1" in
    /mnt/c/*|/mnt/C/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

path_is_under_repo() {
  local path="$1"

  case "$path" in
    "$ROOT_DIR"|"$ROOT_DIR"/*)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

process_cwd() {
  local pid="$1"

  readlink -f "/proc/${pid}/cwd" 2>/dev/null || true
}

process_args() {
  local pid="$1"

  ps -p "$pid" -o args= 2>/dev/null || true
}

listener_pids_for_port() {
  local port="$1"

  ss -ltnp 2>/dev/null |
    awk -v port=":${port}" '$0 ~ port { print }' |
    sed -n 's/.*pid=\([0-9][0-9]*\).*/\1/p' |
    awk 'NF && !seen[$0]++'
}

listener_lines_for_port() {
  local port="$1"

  ss -ltnp 2>/dev/null | grep ":${port} " || true
}

docker_container_for_host_port() {
  local port="$1"

  docker ps --format '{{.Names}}\t{{.Ports}}' 2>/dev/null |
    awk -v port=":${port}->" '$0 ~ port { print }' |
    sed -n '1p'
}

process_is_expected_for_port() {
  local port="$1"
  local pid="$2"
  local args="$3"
  local cwd="$4"

  if [ -n "$cwd" ] && path_is_under_repo "$cwd"; then
    return 0
  fi
  if [[ "$args" == *"$ROOT_DIR"* ]]; then
    return 0
  fi

  case "$port" in
    18443)
      [[ "$args" == *"oc "*port-forward* && "$args" == *"openshift-lightspeed"* && "$args" == *"lightspeed-app-server"* ]]
      return
      ;;
    18083)
      [[ "$args" == *"oc "*port-forward* && "$args" == *"komsco-ai-dev"* && "$args" == *"komsco-ai-action-executor"* ]]
      return
      ;;
  esac

  return 1
}

check_port_owner() {
  local port="$1"
  local label="$2"
  local required="${3:-false}"
  local listeners
  local docker_owner
  local pids=()
  local pid
  local args
  local cwd
  local saw_expected=false
  local saw_stale=false

  listeners="$(listener_lines_for_port "$port")"
  docker_owner="$(docker_container_for_host_port "$port")"
  mapfile -t pids < <(listener_pids_for_port "$port")

  if [ -z "$listeners" ]; then
    if [ "$required" = "true" ]; then
      fail "$label port $port is not listening"
    else
      pass "$label port $port is free"
    fi
    return
  fi

  printf '%s\n' "$listeners" | sed 's/^/       /'

  if [ "$port" = "$CONSOLE_PORT" ] && [ -n "$docker_owner" ]; then
    if [[ "$docker_owner" == kugnus-local-console$'\t'* ]]; then
      pass "$label port $port belongs to expected Docker console bridge"
      info "$docker_owner"
    else
      fail "$label port $port belongs to unexpected Docker container"
      info "$docker_owner"
    fi
    return
  fi

  if [ "${#pids[@]}" -eq 0 ]; then
    warn "$label port $port is listening but owner pid was not visible"
    return
  fi

  for pid in "${pids[@]}"; do
    args="$(process_args "$pid")"
    cwd="$(process_cwd "$pid")"
    if process_is_expected_for_port "$port" "$pid" "$args" "$cwd"; then
      saw_expected=true
      info "expected pid=${pid} cwd=${cwd:-unknown} args=${args}"
    else
      saw_stale=true
      info "stale pid=${pid} cwd=${cwd:-unknown} args=${args}"
    fi
  done

  if [ "$saw_stale" = "true" ]; then
    fail "$label port $port is occupied by a stale or external process"
  elif [ "$saw_expected" = "true" ]; then
    pass "$label port $port owner matches current repo/expected service"
  else
    warn "$label port $port owner could not be classified"
  fi
}

check_repo_filesystem() {
  local fs_type
  local mount_line
  local remote_mounts

  fs_type="$(stat -f -c %T "$ROOT_DIR" 2>/dev/null || true)"
  mount_line="$(findmnt -T "$ROOT_DIR" -no TARGET,SOURCE,FSTYPE,OPTIONS 2>/dev/null || true)"
  info "filesystem: ${fs_type:-unknown}"
  if [ -n "$mount_line" ]; then
    info "mount: $mount_line"
  fi

  case "$mount_line" in
    *sshfs*|*fuse.sshfs*|*rclone*|*kugnus-home*)
      fail "repo is on SSH/remote mount"
      ;;
    *)
      pass "repo is not on sshfs/rclone/kugnus-home mount"
      ;;
  esac

  remote_mounts="$(mount | grep -Ei '(sshfs|fuse\.sshfs|rclone|kugnus-home)' || true)"
  if [ -n "$remote_mounts" ]; then
    warn "remote mounts exist in WSL"
    printf '%s\n' "$remote_mounts" | sed 's/^/       /'
  else
    pass "no sshfs/rclone/kugnus-home mounts found in WSL"
  fi
}

load_nvm() {
  local nvm_dir="${NVM_DIR:-${HOME}/.nvm}"
  if [ -s "${nvm_dir}/nvm.sh" ]; then
    # shellcheck source=/dev/null
    . "${nvm_dir}/nvm.sh" >/dev/null 2>&1 || true
  fi
}

check_command_path() {
  local name="$1"
  local expected_hint="$2"
  local path

  if ! have_cmd "$name"; then
    fail "$name not found"
    return
  fi

  path="$(command -v "$name")"
  if is_windows_path "$path"; then
    fail "$name resolves to Windows path: $path"
    info "Use WSL/NVM shell, for example: bash -ic 'which $name && $name --version'"
    return
  fi

  pass "$name resolves inside WSL: $path"
  if [ -n "$expected_hint" ]; then
    info "$expected_hint"
  fi
}

check_port() {
  local port="$1"
  local label="$2"
  local listeners

  listeners="$(ss -ltnp 2>/dev/null | grep ":${port} " || true)"
  if [ -n "$listeners" ]; then
    warn "$label port $port is already listening"
    printf '%s\n' "$listeners" | sed 's/^/       /'
  else
    pass "$label port $port is free"
  fi
}

check_http_head() {
  local url="$1"
  local label="$2"
  local status

  status="$(curl -fsSI "$url" 2>/dev/null | sed -n '1p' || true)"
  if [ -n "$status" ]; then
    pass "$label responds: $status"
  else
    warn "$label is not responding: $url"
  fi
}

check_http_status() {
  local url="$1"
  local label="$2"
  local expected="$3"
  local status

  status="$(curl -ksS -o /dev/null -w "%{http_code}" --max-time 5 "$url" 2>/dev/null || true)"
  if [ "$status" = "$expected" ]; then
    pass "$label responds: HTTP ${status}"
  else
    fail "$label unhealthy: HTTP ${status:-000}"
    info "$url"
  fi
}

check_windows_curl_status() {
  local url="$1"
  local label="$2"
  local expected="$3"
  local status

  if ! have_cmd curl.exe; then
    warn "Windows curl.exe is not available for $label"
    return
  fi

  status="$(curl.exe -k -s -o NUL -w '%{http_code}' --connect-timeout 2 --max-time 5 "$url" 2>/dev/null | tr -d '\r\n')"
  if [ "$status" = "$expected" ]; then
    pass "Windows curl $label responds: HTTP ${status}"
  else
    fail "Windows curl $label unhealthy: HTTP ${status:-000}"
    info "$url"
  fi
}

check_plugin_assets() {
  local base_url="http://127.0.0.1:${PLUGIN_PORT}/api/plugins/${PLUGIN_NAME}"
  local asset
  local required_assets=(
    "plugin-manifest.json"
    "plugin-entry.js"
    "exposed-useAssistantOverlay-chunk.js"
    "exposed-NullContextProvider-chunk.js"
    "components_AssistantLauncher_tsx-chunk.js"
  )

  for asset in "${required_assets[@]}"; do
    check_http_status "${base_url}/${asset}" "Plugin asset ${asset}" "200"
  done
}

check_console_bridge_env() {
  local expected_gateway
  local proxy
  local plugins

  if ! have_cmd docker; then
    fail "docker not found; cannot inspect local console bridge env"
    return
  fi
  if ! docker inspect kugnus-local-console >/dev/null 2>&1; then
    fail "kugnus-local-console container not found"
    return
  fi

  expected_gateway="$(normalize_gateway_endpoint_for_console_bridge "${GATEWAY_ENDPOINT:-}" "$GATEWAY_PORT")"
  proxy="$(docker inspect kugnus-local-console --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep '^BRIDGE_PLUGIN_PROXY=' || true)"
  plugins="$(docker inspect kugnus-local-console --format '{{range .Config.Env}}{{println .}}{{end}}' 2>/dev/null | grep '^BRIDGE_PLUGINS=' || true)"

  if [[ "$proxy" == *"\"endpoint\":\"${expected_gateway}\""* ]]; then
    pass "Console bridge Gateway proxy uses ${expected_gateway}"
  else
    fail "Console bridge Gateway proxy endpoint mismatch"
    info "expected endpoint: ${expected_gateway}"
    info "${proxy:-BRIDGE_PLUGIN_PROXY missing}"
  fi

  if [[ "$plugins" == *"http://host.docker.internal:${PLUGIN_PORT}/api/plugins/${PLUGIN_NAME}"* ]]; then
    pass "Console bridge plugin URL uses host.docker.internal:${PLUGIN_PORT}"
  else
    fail "Console bridge plugin URL mismatch"
    info "${plugins:-BRIDGE_PLUGINS missing}"
  fi
}

check_http_get() {
  local url="$1"
  local label="$2"
  local body

  body="$(curl -fsS "$url" 2>/dev/null || true)"
  if [ -n "$body" ]; then
    pass "$label responds"
    info "$body"
  else
    warn "$label is not responding: $url"
  fi
}

print_ocp_ladder_interpretation() {
  if [ ! -f "$OCP_LADDER_REPORT" ] || ! have_cmd python3; then
    info "Run task kugnus:ocp:doctor for DNS/TCP/TLS/auth layer details."
    return
  fi

  python3 - "$OCP_LADDER_REPORT" <<'PY'
import json
import sys
import textwrap

path = sys.argv[1]
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
except (OSError, json.JSONDecodeError):
    raise SystemExit(0)

summary = payload.get("summary") or {}
interpretation = payload.get("interpretation") or {}
first = summary.get("firstFailingLayer") or "unknown"
message = summary.get("message") or "unknown"
likely = interpretation.get("likelyCause") or "unknown"
explanation = interpretation.get("explanation") or ""

print(f"       latest ocp ladder: firstFailingLayer={first} message={message}")
print(f"       latest interpretation: {likely}")
if explanation:
    for line in textwrap.wrap(explanation, width=92):
        print(f"       {line}")
PY
  info "Rerun task kugnus:ocp:doctor to refresh this diagnosis."
}

run_oc() {
  timeout "${OC_TIMEOUT_SECONDS}" oc "$@" 2>/dev/null || true
}

oc_ok() {
  timeout "${OC_TIMEOUT_SECONDS}" oc "$@" >/dev/null 2>&1
}

cd "$ROOT_DIR" || {
  echo "Cannot enter repo root: $ROOT_DIR" >&2
  exit 1
}

print_section "Ref stamp"
if have_cmd git; then
  git status --short --branch
  git log -1 --oneline --decorate 2>/dev/null || true
else
  fail "git not found"
fi

print_section "WSL and toolchain"
if is_wsl; then
  pass "running inside WSL/Ubuntu"
else
  fail "not running inside WSL; run this from Ubuntu terminal"
fi

load_nvm

info "repo: $ROOT_DIR"
if is_windows_path "$ROOT_DIR"; then
  warn "repo is under /mnt/c; webpack/build can be slow"
else
  pass "repo is under native Linux filesystem"
fi
check_repo_filesystem

check_command_path node "Node should normally come from /home/kugnus/.nvm/..."
if have_cmd node; then
  info "node version: $(node --version 2>/dev/null || true)"
fi

check_command_path corepack "Corepack should normally come from /home/kugnus/.nvm/..."
if have_cmd corepack; then
  info "corepack path: $(command -v corepack)"
fi

if have_cmd task; then
  pass "Go Task found: $(task --version 2>/dev/null || true)"
else
  fail "task not found; install Go Task, not taskwarrior"
fi

if have_cmd python3; then
  pass "python3 found: $(python3 --version 2>/dev/null || true)"
else
  fail "python3 not found"
fi

if [ -d "${ROOT_DIR}/komsco-ai-console-plugin" ]; then
  yarn_version="$(
    cd "${ROOT_DIR}/komsco-ai-console-plugin" &&
      bash -ic 'corepack yarn --version' 2>/dev/null
  )"
  if [ -n "$yarn_version" ]; then
    pass "Yarn available through bash -ic: $yarn_version"
  else
    warn "Yarn check through bash -ic failed"
  fi
fi

print_section "OpenShift context"
if have_cmd oc; then
  pass "oc found: $(oc version --client 2>/dev/null | sed -n '1p')"
  OCP_IDENTITY_OK=false
  current_server="$(run_oc whoami --show-server)"
  if [ "$current_server" = "$EXPECTED_API_SERVER" ]; then
    pass "oc server is company OCP: $current_server"
  elif [ -n "$current_server" ]; then
    fail "oc server mismatch: $current_server"
    info "expected: $EXPECTED_API_SERVER"
  else
    fail "oc server unavailable; run oc login"
    info "oc check timeout: ${OC_TIMEOUT_SECONDS}s"
  fi

  current_user="$(run_oc whoami)"
  if [ -n "$current_user" ]; then
    OCP_IDENTITY_OK=true
    pass "oc login user: $current_user"
  else
    fail "oc whoami failed; live OpenShift API or CLI auth is not healthy"
    info "Run oc login if the API route is reachable; if this repeats, diagnose the network/auth ladder."
    print_ocp_ladder_interpretation
  fi

  current_project="$(run_oc project | sed -n '1p')"
  if [ -n "$current_project" ]; then
    pass "$current_project"
  else
    warn "oc project unavailable"
  fi

  if oc_ok -n openshift-lightspeed get svc/lightspeed-app-server; then
    pass "Lightspeed service is readable"
  else
    fail "cannot read openshift-lightspeed/lightspeed-app-server"
    if [ "$OCP_IDENTITY_OK" != "true" ]; then
      info "This is expected while oc identity/API connectivity is unhealthy."
    fi
  fi

  if oc_ok -n komsco-ai-dev get svc/komsco-ai-action-executor; then
    pass "Action Executor service is readable"
  else
    warn "cannot read komsco-ai-dev/komsco-ai-action-executor; execute mode may fail"
    if [ "$OCP_IDENTITY_OK" != "true" ]; then
      info "This is expected while oc identity/API connectivity is unhealthy."
    fi
  fi
else
  fail "oc not found"
fi

print_section "Docker and ports"
if have_cmd docker; then
  if docker version >/tmp/kugnus-docker-version.$$ 2>&1; then
    pass "Docker daemon is reachable"
  else
    fail "Docker daemon is not reachable"
    sed 's/^/       /' /tmp/kugnus-docker-version.$$ 2>/dev/null | sed -n '1,8p'
  fi
  rm -f /tmp/kugnus-docker-version.$$
else
  fail "docker not found"
fi

check_console_bridge_env
check_port_owner "$CONSOLE_PORT" "console bridge" true
check_port_owner "$PLUGIN_PORT" "plugin webpack" true
check_port_owner "$GATEWAY_PORT" "gateway" true
check_port_owner 18443 "Lightspeed port-forward" true
check_port_owner 18083 "Action Executor port-forward" true
check_port_owner 5173 "legacy portal dev default" false
check_port_owner "$LOCAL_FIXTURE_PORT" "standalone fixture portal" true

print_section "Local endpoints"
check_http_get "http://127.0.0.1:18080/healthz" "Gateway healthz"
check_http_head "http://127.0.0.1:9000/dashboards" "Local console dashboard"
check_http_status "http://127.0.0.1:9000/api/kubernetes/version" "Local console Kubernetes API proxy" "200"
check_http_status "http://127.0.0.1:9000/api/proxy/plugin/${PLUGIN_NAME}/ai-gateway/healthz" "Local console Gateway proxy" "200"
check_plugin_assets

print_section "Windows localhost endpoints"
check_windows_curl_status "http://127.0.0.1:18080/healthz" "Gateway healthz" "200"
check_windows_curl_status "http://127.0.0.1:9000/api/kubernetes/version" "Local console Kubernetes API proxy" "200"
check_windows_curl_status "http://127.0.0.1:9000/api/proxy/plugin/${PLUGIN_NAME}/ai-gateway/healthz" "Local console Gateway proxy" "200"
check_windows_curl_status "http://127.0.0.1:${LOCAL_FIXTURE_PORT}/healthz" "5174 fixture healthz" "200"
check_windows_curl_status "http://127.0.0.1:${LOCAL_FIXTURE_PORT}/v1/cluster/summary" "5174 fixture API" "200"
check_windows_curl_status "http://127.0.0.1:${LOCAL_FIXTURE_PORT}/dashboards/aiops" "5174 portal HTML" "200"

print_section "Task availability"
if have_cmd task; then
  task --list 2>/dev/null | grep -E 'kugnus:dev:be(:| |$)|kugnus:dev:fe|kugnus:dev:console:(morning|open|repair)|kugnus:dev:doctor' || true
fi

print_section "Summary"
printf 'PASS=%s WARN=%s FAIL=%s\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "Doctor result: FAIL"
  echo "Fix FAIL items before starting the demo loop."
  echo "For localhost:9000 morning startup, run: task kugnus:dev:console:morning"
  exit 1
fi

if [ "$WARN_COUNT" -gt 0 ]; then
  echo "Doctor result: WARN"
  echo "Warnings may be acceptable if the related service is intentionally already running."
  exit 0
fi

echo "Doctor result: PASS"
