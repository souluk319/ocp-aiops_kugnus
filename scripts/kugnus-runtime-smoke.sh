#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:18080}"
REPORT="${REPORT:-${ROOT_DIR}/docs/Ver.0.1.3/runtime-smoke-report.json}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

TOKEN="$(oc whoami -t 2>/dev/null || true)"
if [ -z "${TOKEN}" ] || ! oc whoami >/dev/null 2>&1; then
  printf 'Runtime smoke: FAIL\n[FAIL] oc login is not valid. Run oc login again, then rerun this smoke.\n' >&2
  exit 1
fi

CHECKS_TSV="${TMP_DIR}/checks.tsv"
: > "${CHECKS_TSV}"

request_json() {
  local name="$1"
  local method="$2"
  local path="$3"
  local auth="$4"
  local body="${5:-}"
  local body_file="${TMP_DIR}/${name}.json"
  local status
  local curl_args=(-sS -o "${body_file}" -w '%{http_code}' -X "${method}")

  if [ "${auth}" = "auth" ]; then
    curl_args+=(-H "Authorization: Bearer ${TOKEN}")
  fi
  if [ -n "${body}" ]; then
    curl_args+=(-H 'content-type: application/json' -d "${body}")
  fi

  status="$(curl "${curl_args[@]}" "${GATEWAY_URL}${path}" 2>/dev/null || printf '000')"
  if [ "${status}" -ge 200 ] 2>/dev/null && [ "${status}" -lt 300 ] 2>/dev/null; then
    printf '%s\ttrue\t%s\t%s\n' "${name}" "${status}" "${body_file}" >> "${CHECKS_TSV}"
  else
    printf '%s\tfalse\t%s\t%s\n' "${name}" "${status}" "${body_file}" >> "${CHECKS_TSV}"
  fi
}

request_json healthz GET /healthz none
request_json auth-subject GET /v1/auth/subject auth
request_json cluster-summary GET /v1/cluster/summary auth
request_json aiops-overview GET /v1/aiops/overview auth
request_json runbooks-registry GET /v1/runbooks/registry auth
request_json rag-search-contract POST /v1/rag/search auth '{"query":"pod restart OOMKilled runbook","topK":3}'

python3 - "${CHECKS_TSV}" "${REPORT}" "${GATEWAY_URL}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

checks_tsv = Path(sys.argv[1])
report_path = Path(sys.argv[2])
gateway_url = sys.argv[3]


def load_json(path: str):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return {"parseError": str(exc), "text": Path(path).read_text(encoding="utf-8", errors="replace")[:500] if Path(path).exists() else ""}


def summarize(name, payload):
    if name == "cluster-summary":
        nodes = payload.get("nodes", {}) if isinstance(payload.get("nodes"), dict) else {}
        operators = payload.get("operators", {}) if isinstance(payload.get("operators"), dict) else {}
        return {
            "healthScore": payload.get("healthScore"),
            "apiUrl": payload.get("apiUrl"),
            "nodes": {"ready": nodes.get("ready"), "total": nodes.get("total"), "metricsAvailable": nodes.get("metricsAvailable")},
            "operators": {"available": operators.get("available"), "total": operators.get("total"), "degraded": operators.get("degraded"), "progressing": operators.get("progressing")},
        }
    if name == "aiops-overview":
        spec = payload.get("spec", {}) if isinstance(payload.get("spec"), dict) else {}
        tower = spec.get("controlTower", {}) if isinstance(spec.get("controlTower"), dict) else {}
        sources = spec.get("dataSources", []) if isinstance(spec.get("dataSources"), list) else []
        return {
            "controlTower": {"status": tower.get("status"), "statusLabel": tower.get("statusLabel"), "healthScore": tower.get("healthScore")},
            "dataSources": [{"name": item.get("name"), "status": item.get("status"), "required": item.get("required"), "reason": item.get("reason", "")} for item in sources if isinstance(item, dict)],
        }
    if name == "runbooks-registry":
        spec = payload.get("spec", {}) if isinstance(payload.get("spec"), dict) else {}
        entries = spec.get("entries", []) if isinstance(spec.get("entries"), list) else []
        return {"digest": spec.get("digest"), "entryCount": len(entries), "runbookIds": [entry.get("runbookId") for entry in entries if isinstance(entry, dict)]}
    if name == "rag-search-contract":
        spec = payload.get("spec", {}) if isinstance(payload.get("spec"), dict) else {}
        backend = spec.get("backend", {}) if isinstance(spec.get("backend"), dict) else {}
        return {
            "status": spec.get("status"),
            "reason": spec.get("reason"),
            "resultCount": len(spec.get("results", [])) if isinstance(spec.get("results"), list) else 0,
            "backend": {"status": backend.get("status"), "backendType": backend.get("backendType"), "collection": backend.get("collection"), "endpointConfigured": backend.get("endpointConfigured")},
        }
    if name == "auth-subject":
        return {"username": payload.get("username"), "authenticatedByCluster": payload.get("authenticatedByCluster"), "groupsDigest": payload.get("groupsDigest")}
    return payload

checks = []
for line in checks_tsv.read_text(encoding="utf-8").splitlines():
    name, ok, status, body_file = line.split("\t", 3)
    payload = load_json(body_file)
    checks.append({"name": name, "ok": ok == "true", "statusCode": int(status) if status.isdigit() else 0, "summary": summarize(name, payload)})

report = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "gatewayUrl": gateway_url,
    "result": "pass" if all(check["ok"] for check in checks) else "fail",
    "checks": checks,
}
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"Runtime smoke: {report['result'].upper()}")
for check in checks:
    marker = "PASS" if check["ok"] else "FAIL"
    print(f"[{marker}] {check['name']} HTTP {check['statusCode']}")
    summary = check["summary"]
    if check["name"] == "cluster-summary":
        print(f"       health={summary.get('healthScore')} nodes={summary.get('nodes', {}).get('ready')}/{summary.get('nodes', {}).get('total')} operators={summary.get('operators', {}).get('available')}/{summary.get('operators', {}).get('total')}")
    if check["name"] == "rag-search-contract":
        backend = summary.get("backend", {})
        print(f"       rag={summary.get('status')} backend={backend.get('backendType')} configured={backend.get('endpointConfigured')} results={summary.get('resultCount')}")
print(f"Report: {report_path}")
PY
