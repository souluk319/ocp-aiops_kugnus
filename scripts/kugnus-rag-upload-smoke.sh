#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:18080}"
REPORT="${REPORT:-${ROOT_DIR}/docs/Ver.0.1.4/rag-upload-smoke-report.json}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

TOKEN="$(oc whoami -t 2>/dev/null || true)"
if [ -z "${TOKEN}" ]; then
  printf 'RAG upload smoke: FAIL\n[FAIL] oc token is empty. Run oc login first.\n' >&2
  exit 1
fi

UPLOAD_BODY="${TMP_DIR}/upload-body.json"
python3 - "${UPLOAD_BODY}" <<'PY'
import json
import sys
from pathlib import Path
body = {
    "name": "ver-0.1.4-upload-rag-smoke.md",
    "content": """
# Ver.0.1.4 upload RAG smoke document

KUGNUS_UPLOAD_RAG_SMOKE marker.

When a user uploads an operations runbook, the Gateway must persist redacted chunks into pgvector, list the uploaded document, and retrieve it as user-upload evidence for RCA answers.

Safety: uploaded content is never returned as raw storage from the upload endpoint and must remain gateway-only.
""".strip(),
    "labels": {"scenario": "upload_rag_smoke", "safetyClass": "evidence-check"},
    "namespace": "komsco-ai-kugnus",
    "version": "v0.1.4",
    "runId": "ver-0.1.4-upload-rag-smoke",
}
Path(sys.argv[1]).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
PY

curl_json() {
  local name="$1"
  local method="$2"
  local path="$3"
  local output="$4"
  local body_file="${5:-}"
  local curl_args=(-sS -o "${output}" -w '%{http_code}' -X "${method}" -H "Authorization: Bearer ${TOKEN}" -H 'Accept: application/json')
  if [ -n "${body_file}" ]; then
    curl_args+=(-H 'Content-Type: application/json' --data-binary "@${body_file}")
  fi
  local status
  status="$(curl "${curl_args[@]}" "${GATEWAY_URL}${path}" 2>/dev/null || printf '000')"
  printf '%s\t%s\t%s\n' "${name}" "${status}" "${output}"
}

CHECKS="${TMP_DIR}/checks.tsv"
: > "${CHECKS}"
curl_json upload POST /v1/rag/uploads "${TMP_DIR}/upload.json" "${UPLOAD_BODY}" >> "${CHECKS}"
curl_json list GET /v1/rag/uploads "${TMP_DIR}/list.json" >> "${CHECKS}"
cat > "${TMP_DIR}/search-body.json" <<'JSON'
{"query":"KUGNUS_UPLOAD_RAG_SMOKE uploaded runbook","topK":5,"includeContent":true,"filters":{"sourceTypes":["user-upload"]},"runId":"ver-0.1.4-upload-rag-smoke"}
JSON
curl_json search POST /v1/rag/search "${TMP_DIR}/search.json" "${TMP_DIR}/search-body.json" >> "${CHECKS}"

python3 - "${CHECKS}" "${REPORT}" "${GATEWAY_URL}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

checks_tsv = Path(sys.argv[1])
report_path = Path(sys.argv[2])
gateway_url = sys.argv[3]

raw = {}
checks = []
for line in checks_tsv.read_text(encoding="utf-8").splitlines():
    name, status, path = line.split("\t", 2)
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw[name] = payload
    checks.append({"name": name, "statusCode": int(status) if status.isdigit() else 0, "httpOk": status.isdigit() and 200 <= int(status) < 300})

upload_spec = raw.get("upload", {}).get("spec", {})
list_spec = raw.get("list", {}).get("spec", {})
search_spec = raw.get("search", {}).get("spec", {})
document_id = upload_spec.get("document", {}).get("documentId", "")
list_documents = list_spec.get("documents", []) if isinstance(list_spec.get("documents"), list) else []
search_results = search_spec.get("results", []) if isinstance(search_spec.get("results"), list) else []

contract_checks = [
    {"name": "upload-persisted", "ok": upload_spec.get("status") == "persisted", "detail": upload_spec.get("reason", "")},
    {"name": "upload-has-document-id", "ok": bool(document_id), "detail": document_id},
    {"name": "upload-raw-content-hidden", "ok": upload_spec.get("safety", {}).get("rawContentReturned") is False, "detail": "rawContentReturned=false"},
    {"name": "list-includes-upload", "ok": any(item.get("documentId") == document_id for item in list_documents), "detail": f"listCount={len(list_documents)}"},
    {"name": "search-finds-upload", "ok": any(item.get("documentId") == document_id for item in search_results), "detail": f"searchStatus={search_spec.get('status')} resultCount={len(search_results)}"},
]

result = "pass" if all(item["httpOk"] for item in checks) and all(item["ok"] for item in contract_checks) else "fail"
report = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "gatewayUrl": gateway_url,
    "result": result,
    "documentId": document_id,
    "httpChecks": checks,
    "contractChecks": contract_checks,
    "summaries": {
        "upload": {"status": upload_spec.get("status"), "reason": upload_spec.get("reason"), "chunkCount": len(upload_spec.get("chunks", []))},
        "list": {"status": list_spec.get("status"), "count": len(list_documents)},
        "search": {"status": search_spec.get("status"), "count": len(search_results)},
    },
}
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"RAG upload smoke: {result.upper()}")
for check in checks:
    print(f"[{'PASS' if check['httpOk'] else 'FAIL'}] {check['name']} HTTP {check['statusCode']}")
for check in contract_checks:
    print(f"[{'PASS' if check['ok'] else 'FAIL'}] {check['name']} {check['detail']}")
print(f"Report: {report_path}")
if result != "pass":
    raise SystemExit(1)
PY
