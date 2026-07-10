#!/usr/bin/env bash

set -u

label="${1:?label is required}"
namespace="${2:?namespace is required}"
service="${3:?service is required}"
bind_address="${4:?bind address is required}"
local_port="${5:?local port is required}"
service_port="${6:?service port is required}"
restart_delay="${KUGNUS_PF_RESTART_DELAY_SECONDS:-2}"
max_restart_delay="${KUGNUS_PF_MAX_RESTART_DELAY_SECONDS:-30}"
current_delay="$restart_delay"
child_pid=""

log() {
  printf '[%s] %s\n' "$(date -Is)" "$*"
}

stop_child() {
  if [ -n "$child_pid" ] && kill -0 "$child_pid" >/dev/null 2>&1; then
    kill "$child_pid" >/dev/null 2>&1 || true
    for _ in $(seq 1 20); do
      if ! kill -0 "$child_pid" >/dev/null 2>&1; then
        break
      fi
      sleep 0.1
    done
    if kill -0 "$child_pid" >/dev/null 2>&1; then
      kill -KILL "$child_pid" >/dev/null 2>&1 || true
    fi
    wait "$child_pid" 2>/dev/null || true
  fi
}

trap 'stop_child; exit 0' INT TERM
trap 'stop_child' EXIT

while true; do
  started_at="$SECONDS"
  log "${label}: opening ${namespace}/${service} ${local_port}:${service_port}"
  oc -n "$namespace" port-forward \
    --address "$bind_address" \
    "svc/${service}" \
    "${local_port}:${service_port}" &
  child_pid="$!"

  wait "$child_pid"
  status="$?"
  child_pid=""
  runtime="$((SECONDS - started_at))"
  if [ "$runtime" -ge 30 ]; then
    current_delay="$restart_delay"
  fi
  log "${label}: port-forward exited with status ${status}; retrying in ${current_delay}s"
  sleep "$current_delay"
  current_delay="$(awk -v value="$current_delay" -v maximum="$max_restart_delay" 'BEGIN { value *= 2; print value > maximum ? maximum : value }')"
done
