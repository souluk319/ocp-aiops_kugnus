#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OC_BIN="${OC_BIN:-oc}"
OC_TIMEOUT="${OC_TIMEOUT:-60s}"
OC_USER_TIMEOUT="${OC_USER_TIMEOUT:-5s}"
EXPECTED_SERVER="${KOMSCO_AIOPS_COMPANY_SERVER:-https://api.ocp.cywell.server:6443}"
NAMESPACE=""
SESSION=""
JSON_OUTPUT=false
DRY_RUN=false

usage() {
  cat <<EOF
Usage: $0 --namespace NAME --session SESSION [--dry-run] [--json]

Deletes only a connected AIOps test namespace that has every required safety
label. Refuses all production/development namespaces and unlabeled namespaces.
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --namespace)
      NAMESPACE="${2:-}"
      shift 2
      ;;
    --session)
      SESSION="${2:-}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --json)
      JSON_OUTPUT=true
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

log() {
  if [ "$JSON_OUTPUT" != "true" ]; then
    printf '%s\n' "$*"
  fi
}

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

oc_run() {
  timeout "$OC_TIMEOUT" "$OC_BIN" "$@"
}

oc_user_optional() {
  timeout "$OC_USER_TIMEOUT" "$OC_BIN" whoami 2>/dev/null || true
}

json_escape() {
  python3 -c 'import json,sys; print(json.dumps(sys.stdin.read().rstrip("\n")))' <<<"$1"
}

emit_json() {
  local status="$1"
  local reason="${2:-}"
  local server user
  server="$(oc_run whoami --show-server 2>/dev/null || true)"
  user="$(oc_user_optional)"
  cat <<EOF
{"status":$(json_escape "$status"),"reason":$(json_escape "$reason"),"namespace":$(json_escape "$NAMESPACE"),"session":$(json_escape "$SESSION"),"server":$(json_escape "$server"),"user":$(json_escape "$user")}
EOF
}

require_inputs() {
  [ -n "$NAMESPACE" ] || fail "--namespace is required"
  [ -n "$SESSION" ] || fail "--session is required"
  if [[ ! "$NAMESPACE" =~ ^aiops-copilot-e2e-[a-zA-Z0-9][a-zA-Z0-9-]{4,40}$ ]]; then
    fail "unsafe namespace name: ${NAMESPACE}"
  fi
}

check_cluster() {
  command -v "$OC_BIN" >/dev/null 2>&1 || fail "oc CLI not found"
  local server
  server="$(oc_run whoami --show-server 2>/dev/null || true)"
  [ "$server" = "$EXPECTED_SERVER" ] || fail "refusing cluster write: current server=${server:-unavailable}, expected=${EXPECTED_SERVER}"
}

label_value() {
  local key="$1"
  oc_run get namespace "$NAMESPACE" -o "go-template={{ index .metadata.labels \"${key}\" }}" 2>/dev/null || true
}

verify_safe_labels() {
  if ! oc_run get namespace "$NAMESPACE" >/dev/null 2>&1; then
    emit_json "not_found" "namespace already absent"
    exit 0
  fi

  local managed safe suite session_label
  managed="$(label_value 'app.kubernetes.io/managed-by')"
  safe="$(label_value 'aiops.komsco/safe-delete')"
  suite="$(label_value 'aiops.komsco/test-suite')"
  session_label="$(label_value 'aiops.komsco/session')"

  [ "$managed" = "komsco-aiops-test" ] || fail "missing managed-by safety label"
  [ "$safe" = "true" ] || fail "missing safe-delete=true safety label"
  [ "$suite" = "v0281-connected" ] || fail "wrong test-suite label: ${suite:-missing}"
  [ "$session_label" = "$SESSION" ] || fail "session label mismatch: ${session_label:-missing} != ${SESSION}"
}

delete_namespace() {
  if [ "$DRY_RUN" = "true" ]; then
    log "[DRY-RUN] would delete namespace $NAMESPACE"
    emit_json "dry_run" "safe labels verified"
    return
  fi

  log "[INFO] deleting connected AIOps sandbox: $NAMESPACE"
  oc_run delete namespace "$NAMESPACE" --wait=true --timeout=180s >/dev/null
  if oc_run get namespace "$NAMESPACE" >/dev/null 2>&1; then
    fail "namespace still exists after cleanup: $NAMESPACE"
  fi
  log "[PASS] namespace deleted: $NAMESPACE"
  emit_json "deleted"
}

main() {
  cd "$ROOT_DIR"
  require_inputs
  check_cluster
  verify_safe_labels
  delete_namespace
}

main "$@"
