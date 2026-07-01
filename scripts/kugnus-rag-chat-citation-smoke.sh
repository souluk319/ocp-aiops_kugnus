#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GATEWAY_URL="${GATEWAY_URL:-http://127.0.0.1:18080}"
REPORT="${REPORT:-${ROOT_DIR}/docs/Ver.0.1.4/rag-chat-citation-smoke-report.json}"
RUN_ID="${KUGNUS_RAG_CHAT_SMOKE_RUN_ID:-ver-0.1.4-rag-chat-citation-smoke}"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}"' EXIT

TOKEN="$(oc whoami -t 2>/dev/null || true)"
if [ -z "${TOKEN}" ]; then
  printf 'RAG chat citation smoke: FAIL\n[FAIL] oc token is empty. Run oc login first.\n' >&2
  exit 1
fi

BODY="${TMP_DIR}/chat-body.json"
OUT="${TMP_DIR}/chat-stream.sse"
python3 - "${BODY}" "${RUN_ID}" <<'PY'
import json
import sys
from pathlib import Path

run_id = sys.argv[2]
body = {
    "message": "KUGNUS_UPLOAD_RAG_SMOKE uploaded runbook 근거를 참고해서 사용자 업로드 RAG 동작을 요약해줘",
    "runId": run_id,
    "conversationId": run_id,
    "pageContext": {"aiopsExecutionMode": "evidence-check"},
}
Path(sys.argv[1]).write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
PY

STATUS="$(
  curl -sS --max-time 90 \
    -o "${OUT}" \
    -w '%{http_code}' \
    -X POST "${GATEWAY_URL}/v1/chat/stream" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H 'Accept: text/event-stream' \
    -H 'Content-Type: application/json' \
    --data-binary "@${BODY}" 2>/dev/null || printf '000'
)"

python3 - "${OUT}" "${REPORT}" "${GATEWAY_URL}" "${STATUS}" <<'PY'
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

stream_path = Path(sys.argv[1])
report_path = Path(sys.argv[2])
gateway_url = sys.argv[3]
status = sys.argv[4]
text = stream_path.read_text(encoding="utf-8", errors="replace")

checks = [
    {
        "name": "chat-stream-http-200",
        "ok": status.isdigit() and 200 <= int(status) < 300,
        "detail": f"HTTP {status}",
    },
    {
        "name": "rag-context-tool-event",
        "ok": "rag_context_evidence" in text,
        "detail": "rag_context_evidence appears in SSE stream",
    },
    {
        "name": "rag-answer-citation-text",
        "ok": "RAG 근거" in text,
        "detail": "answer stream includes RAG citation section",
    },
    {
        "name": "uploaded-document-source-visible",
        "ok": "user-upload:" in text or "ver-0.1.4-upload-rag-smoke.md" in text,
        "detail": "uploaded document id/title appears in RAG stream evidence",
    },
]
result = "pass" if all(item["ok"] for item in checks) else "fail"
report = {
    "generatedAt": datetime.now(timezone.utc).isoformat(),
    "gatewayUrl": gateway_url,
    "result": result,
    "httpStatus": int(status) if status.isdigit() else 0,
    "checks": checks,
    "streamBytes": len(text.encode("utf-8")),
}
report_path.parent.mkdir(parents=True, exist_ok=True)
report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

print(f"RAG chat citation smoke: {result.upper()}")
for check in checks:
    print(f"[{'PASS' if check['ok'] else 'FAIL'}] {check['name']} {check['detail']}")
print(f"Report: {report_path}")
if result != "pass":
    print("--- stream tail ---")
    print("\n".join(text.splitlines()[-30:]))
    raise SystemExit(1)
PY
