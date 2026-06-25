#!/usr/bin/env bash

set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXPECTED_API_SERVER="${EXPECTED_API_SERVER:-https://api.ocp.cywell.server:6443}"
PLUGIN_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-komsco-ai-console-plugin-kugnus}"

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
  current_server="$(oc whoami --show-server 2>/dev/null || true)"
  if [ "$current_server" = "$EXPECTED_API_SERVER" ]; then
    pass "oc server is company OCP: $current_server"
  elif [ -n "$current_server" ]; then
    fail "oc server mismatch: $current_server"
    info "expected: $EXPECTED_API_SERVER"
  else
    fail "oc server unavailable; run oc login"
  fi

  current_user="$(oc whoami 2>/dev/null || true)"
  if [ -n "$current_user" ]; then
    pass "oc login user: $current_user"
  else
    fail "oc whoami failed; token likely expired"
  fi

  current_project="$(oc project 2>/dev/null | sed -n '1p' || true)"
  if [ -n "$current_project" ]; then
    pass "$current_project"
  else
    warn "oc project unavailable"
  fi

  if oc -n openshift-lightspeed get svc/lightspeed-app-server >/dev/null 2>&1; then
    pass "Lightspeed service is readable"
  else
    fail "cannot read openshift-lightspeed/lightspeed-app-server"
  fi

  if oc -n komsco-ai-dev get svc/komsco-ai-action-executor >/dev/null 2>&1; then
    pass "Action Executor service is readable"
  else
    warn "cannot read komsco-ai-dev/komsco-ai-action-executor; execute mode may fail"
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

check_port 9000 "console bridge"
check_port 9001 "plugin webpack"
check_port 18080 "gateway"
check_port 18443 "Lightspeed port-forward"
check_port 18083 "Action Executor port-forward"

print_section "Local endpoints"
check_http_get "http://127.0.0.1:18080/healthz" "Gateway healthz"
check_http_head "http://127.0.0.1:9000/dashboards" "Local console dashboard"
check_http_head "http://127.0.0.1:9001/api/plugins/${PLUGIN_NAME}/plugin-manifest.json" "Plugin manifest"

print_section "Task availability"
if have_cmd task; then
  task --list 2>/dev/null | grep -E 'kugnus:dev:be(:| |$)|kugnus:dev:fe|kugnus:dev:doctor' || true
fi

print_section "Summary"
printf 'PASS=%s WARN=%s FAIL=%s\n' "$PASS_COUNT" "$WARN_COUNT" "$FAIL_COUNT"

if [ "$FAIL_COUNT" -gt 0 ]; then
  echo "Doctor result: FAIL"
  echo "Fix FAIL items before starting the demo loop."
  exit 1
fi

if [ "$WARN_COUNT" -gt 0 ]; then
  echo "Doctor result: WARN"
  echo "Warnings may be acceptable if the related service is intentionally already running."
  exit 0
fi

echo "Doctor result: PASS"
