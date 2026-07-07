#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONSOLE_URL="${CONSOLE_URL:-http://localhost:9000/dashboards}"
CONSOLE_HEALTH_URL="${CONSOLE_HEALTH_URL:-http://localhost:9000/api/kubernetes/version}"
PLUGIN_NAME="${KOMSCO_AIOPS_CONSOLE_PLUGIN_NAME:-cywell-aiops-console-plugin}"
PLUGIN_BASE_URL="${PLUGIN_BASE_URL:-http://localhost:9001/api/plugins/${PLUGIN_NAME}}"
PLUGIN_MANIFEST_URL="${PLUGIN_MANIFEST_URL:-${PLUGIN_BASE_URL}/plugin-manifest.json}"
DEFAULT_API_SERVER="https://api.ocp.cywell.server:6443"
EXPECTED_API_SERVER="${DEFAULT_API_SERVER}"
REPAIR="${KUGNUS_OKD_CONSOLE_REPAIR:-true}"
OPEN_AFTER_REPAIR="${KUGNUS_OKD_CONSOLE_OPEN:-false}"

# shellcheck source=lib/safe-env.sh
. "${ROOT_DIR}/scripts/lib/safe-env.sh"

section() {
  printf '\n== %s ==\n' "$1"
}

say() {
  printf '%s\n' "$1"
}

detail() {
  printf '  %s\n' "$1"
}

http_code() {
  curl -ksS -o /dev/null -w "%{http_code}" --max-time 8 "$1" 2>/dev/null || true
}

plugin_asset_report() {
  local path
  local code
  local status=0
  local required_assets=(
    "plugin-manifest.json"
    "plugin-entry.js"
    "exposed-useAssistantOverlay-chunk.js"
    "exposed-NullContextProvider-chunk.js"
    "components_AssistantLauncher_tsx-chunk.js"
  )

  for path in "${required_assets[@]}"; do
    code="$(http_code "${PLUGIN_BASE_URL}/${path}")"
    detail "${PLUGIN_BASE_URL}/${path} -> HTTP ${code:-000}"
    if [ "$code" != "200" ]; then
      status=1
    fi
  done

  return "$status"
}

tcp_open() {
  local host="$1"
  local port="$2"
  timeout 5 bash -lc "</dev/tcp/${host}/${port}" >/dev/null 2>&1
}

load_env_files() {
  if [ "${KOMSCO_AIOPS_SKIP_ENV_FILES:-false}" = "true" ]; then
    return
  fi

  load_env_file "${ROOT_DIR}/.env"
  load_env_file "${ROOT_DIR}/.env.local"
  unset_placeholder_env_vars OPENSHIFT_API_SERVER OPENSHIFT_SERVER OPENSHIFT_NAMESPACE
}

explain_model() {
  section "이게 뭔지"
  say "localhost:9000은 회사 OKD 서버가 아닙니다."
  say "내 PC Docker 컨테이너가 회사 OKD API를 대신 물어보는 로컬 콘솔 브릿지입니다."
  detail "브라우저 -> localhost:9000 -> kugnus-local-console 컨테이너 -> ${EXPECTED_API_SERVER}"
  detail "컨테이너는 시작할 때의 oc 토큰을 복사해서 씁니다."
  detail "그래서 VPN/oc 토큰/컨테이너 토큰 중 하나가 낡으면 화면 껍데기는 떠도 데이터 조회가 끊깁니다."
}

check_company_api() {
  section "회사 API 네트워크"
  local host
  local resolved

  host="$(printf '%s\n' "$EXPECTED_API_SERVER" | sed -E 's#^https?://([^/:]+).*#\1#')"
  resolved="$(getent hosts "$host" | awk '{print $1}' | sed -n '1p' || true)"
  if [ -n "$resolved" ]; then
    detail "${host} -> ${resolved}"
  else
    say "[FAIL] DNS 해석 실패: ${host}"
    detail "FortiClient/VPN 또는 사내 DNS를 먼저 확인해야 합니다."
    return 1
  fi

  if tcp_open "$host" 6443; then
    say "[PASS] ${host}:6443 TCP 연결 가능"
    return 0
  fi

  say "[FAIL] ${host}:6443 TCP 연결 실패"
  detail "이 상태에서는 9000을 재시작해도 OKD 데이터가 뜨지 않습니다."
  detail "FortiClient 로그인 후 다시 실행하세요."
  return 1
}

check_oc_login() {
  section "oc 로그인"
  local server
  local user

  server="$(oc_quick whoami --show-server 2>/dev/null || true)"
  if [ "$server" != "$EXPECTED_API_SERVER" ]; then
    say "[FAIL] oc 서버가 회사 서버가 아닙니다."
    detail "현재: ${server:-비어 있음}"
    detail "기대: ${EXPECTED_API_SERVER}"
    detail "다시 로그인: oc login --token=토큰값 --server=${EXPECTED_API_SERVER}"
    return 1
  fi

  user="$(oc_quick whoami 2>/dev/null || true)"
  if [ -z "$user" ]; then
    say "[FAIL] oc 토큰이 만료되었거나 로그인되어 있지 않습니다."
    detail "다시 로그인: oc login --token=토큰값 --server=${EXPECTED_API_SERVER}"
    return 1
  fi

  say "[PASS] oc 로그인 정상: ${user}"
  return 0
}

check_local_endpoints() {
  section "localhost:9000 실제 상태"
  local dashboard_code
  local api_code
  local plugin_status=0

  dashboard_code="$(http_code "$CONSOLE_URL")"
  api_code="$(http_code "$CONSOLE_HEALTH_URL")"

  detail "${CONSOLE_URL} -> HTTP ${dashboard_code:-000}"
  detail "${CONSOLE_HEALTH_URL} -> HTTP ${api_code:-000}"
  plugin_asset_report || plugin_status=$?

  if [ "$api_code" = "200" ] && [ "$plugin_status" = "0" ]; then
    say "[PASS] 9000은 OKD API와 플러그인까지 실제 연결됨"
    return 0
  fi

  if [ "$api_code" = "401" ] || [ "$api_code" = "403" ]; then
    say "[FAIL] 9000 컨테이너가 낡은 oc 토큰을 들고 있습니다."
    detail "해결은 컨테이너 재생성입니다: task kugnus:dev:console:repair"
    return 2
  fi

  if [ "$api_code" = "502" ] || [ "$api_code" = "000" ]; then
    say "[FAIL] 9000 컨테이너가 회사 OKD API로 못 나갑니다."
    detail "VPN/네트워크가 방금 살아났다면 컨테이너 재생성이 필요합니다."
    return 2
  fi

  if [ "$plugin_status" != "0" ]; then
    say "[FAIL] 9001 플러그인 dev server 또는 필수 chunk가 준비되지 않았습니다."
    detail "open-okd-console.sh가 필요하면 플러그인 dev server를 시작합니다."
    return 2
  fi

  say "[FAIL] 9000 상태를 정상으로 판정할 수 없습니다."
  return 2
}

repair_console() {
  section "자동 수리"
  if [ "$REPAIR" != "true" ]; then
    say "자동 수리 비활성화됨: KUGNUS_OKD_CONSOLE_REPAIR=${REPAIR}"
    return 2
  fi

  say "새 oc 토큰으로 local 9000 콘솔 브릿지를 다시 만듭니다."
  OPEN_BROWSER=false "${ROOT_DIR}/scripts/open-okd-console.sh"
}

final_check() {
  section "최종 확인"
  local api_code
  local plugin_status=0

  api_code="$(http_code "$CONSOLE_HEALTH_URL")"
  detail "${CONSOLE_HEALTH_URL} -> HTTP ${api_code:-000}"
  plugin_asset_report || plugin_status=$?

  if [ "$api_code" = "200" ] && [ "$plugin_status" = "0" ]; then
    say "[PASS] OKD 콘솔 사용 가능: ${CONSOLE_URL}"
    if [ "$OPEN_AFTER_REPAIR" = "true" ]; then
      OPEN_BROWSER=true "${ROOT_DIR}/scripts/open-okd-console.sh"
    fi
    return 0
  fi

  say "[FAIL] 수리 후에도 정상 아님"
  detail "api=${api_code:-000}, plugin-assets=${plugin_status}"
  detail "docker logs --tail 120 kugnus-local-console"
  return 1
}

main() {
  cd "$ROOT_DIR"
  load_env_files
  EXPECTED_API_SERVER="${OPENSHIFT_API_SERVER:-${OPENSHIFT_SERVER:-${DEFAULT_API_SERVER}}}"

  explain_model
  check_company_api
  check_oc_login

  if check_local_endpoints; then
    final_check
    return
  fi

  repair_console
  final_check
}

main "$@"
