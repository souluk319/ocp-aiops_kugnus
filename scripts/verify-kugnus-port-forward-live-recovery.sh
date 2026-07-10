#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
label="${1:-lightspeed-port-forward}"
health_url="${2:-https://127.0.0.1:18443/readiness}"
pid_file="${ROOT_DIR}/.tmp-kugnus-demo/${label}.pid"

supervisor_pid="$(tr -dc '0-9' <"$pid_file")"
old_child="$(pgrep -P "$supervisor_pid" -x oc | head -1)"
before_http="$(curl -sk -o /dev/null -w '%{http_code}' "$health_url")"
printf 'supervisor_pid=%s old_child=%s before_http=%s\n' "$supervisor_pid" "$old_child" "$before_http"

test -n "$old_child"
test "$before_http" = "200"
kill "$old_child"

new_child=""
after_http="000"
for _ in $(seq 1 30); do
  new_child="$(pgrep -P "$supervisor_pid" -x oc | head -1 || true)"
  if [ -n "$new_child" ] && [ "$new_child" != "$old_child" ]; then
    after_http="$(curl -sk -o /dev/null -w '%{http_code}' "$health_url" || true)"
    if [ "$after_http" = "200" ]; then
      break
    fi
  fi
  sleep 0.5
done

printf 'new_child=%s after_http=%s\n' "$new_child" "$after_http"
test -n "$new_child"
test "$new_child" != "$old_child"
test "$after_http" = "200"
kill -0 "$supervisor_pid"
printf 'live auto-recovery test passed\n'
