#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT="${KUGNUS_OCP_LADDER_REPORT:-${ROOT_DIR}/.tmp-kugnus-demo/ocp-connectivity-ladder-wait-report.json}"
ATTEMPTS="${KUGNUS_WAIT_ATTEMPTS:-30}"
INTERVAL_SECONDS="${KUGNUS_WAIT_INTERVAL_SECONDS:-20}"
OCP_TIMEOUT_SECONDS="${KUGNUS_WAIT_OCP_TIMEOUT_SECONDS:-8}"
RUN_RESUME="${KUGNUS_WAIT_RUN_RESUME:-true}"

mkdir -p "$(dirname "$REPORT")"

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*" >&2
}

summary_field() {
  local field="$1"
  python3 - "$REPORT" "$field" <<'PY'
import json
import sys

path, field = sys.argv[1], sys.argv[2]
try:
    with open(path, encoding="utf-8") as handle:
        payload = json.load(handle)
except FileNotFoundError:
    print("")
    raise SystemExit(0)
value = (payload.get("summary") or {}).get(field, "")
print(value if value is not None else "")
PY
}

cd "$ROOT_DIR"

log "Waiting for OCP connectivity before local demo resume"
log "attempts=${ATTEMPTS} interval=${INTERVAL_SECONDS}s ocTimeout=${OCP_TIMEOUT_SECONDS}s"

for attempt in $(seq 1 "$ATTEMPTS"); do
  log "OCP connectivity attempt ${attempt}/${ATTEMPTS}"
  if python3 scripts/kugnus-ocp-connectivity-ladder.py \
    --fast-fail \
    --timeout "$OCP_TIMEOUT_SECONDS" \
    --report "$REPORT"; then
    log "OCP connectivity ladder passed"
    if [ "$RUN_RESUME" = "true" ]; then
      log "Starting local demo resume"
      exec task kugnus:demo:resume
    fi
    log "KUGNUS_WAIT_RUN_RESUME=false; stopping after connectivity PASS"
    exit 0
  fi

  first_layer="$(summary_field firstFailingLayer)"
  message="$(summary_field message)"
  log "Still blocked at layer=${first_layer:-unknown}: ${message:-unknown}"

  if [ "$attempt" = "$ATTEMPTS" ]; then
    break
  fi

  sleep "$INTERVAL_SECONDS"
done

printf '[FAIL] OCP connectivity did not become ready after %s attempt(s).\n' "$ATTEMPTS" >&2
printf '       Last report: %s\n' "$REPORT" >&2
exit 1
