#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

mkdir -p "$tmp_dir/bin"
cat >"$tmp_dir/bin/oc" <<EOF
#!/usr/bin/env bash
echo call >>"$tmp_dir/calls"
sleep 0.05
exit 7
EOF
chmod +x "$tmp_dir/bin/oc"

set +e
PATH="$tmp_dir/bin:$PATH" \
  KUGNUS_PF_RESTART_DELAY_SECONDS=0.05 \
  timeout 0.45 bash "$ROOT_DIR/scripts/kugnus-port-forward-supervisor.sh" \
    test-forward test-namespace test-service 127.0.0.1 19999 8443 \
    >"$tmp_dir/supervisor.log" 2>&1
timeout_status="$?"
set -e

call_count="$(wc -l <"$tmp_dir/calls")"
if [ "$timeout_status" -ne 124 ] || [ "$call_count" -lt 3 ]; then
  cat "$tmp_dir/supervisor.log" >&2
  printf 'supervisor restart test failed: timeout_status=%s calls=%s\n' "$timeout_status" "$call_count" >&2
  exit 1
fi

if pgrep -f "$tmp_dir/bin/oc" >/dev/null 2>&1; then
  printf 'supervisor left a child oc process running\n' >&2
  exit 1
fi

printf 'supervisor restart test passed: calls=%s\n' "$call_count"
