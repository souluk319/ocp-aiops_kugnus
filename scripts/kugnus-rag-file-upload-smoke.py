#!/usr/bin/env python3
"""Smoke-test Gateway multipart RAG file upload without exposing tokens."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_UPLOAD_FILE = ROOT_DIR / "docs" / "Komsco_ai_agent_final.pdf"
DEFAULT_REPORT = ROOT_DIR / "docs" / "Ver.0.1.5" / "rag-file-upload-smoke-report.json"


def run(args: list[str], *, cwd: Path = ROOT_DIR) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, text=True, capture_output=True, check=False)


def get_oc_token() -> str:
    proc = run(["oc", "whoami", "-t"])
    token = proc.stdout.strip()
    if proc.returncode != 0 or not token:
        raise RuntimeError("oc token is empty. Run oc login first.")
    return token


def split_curl_status(stdout: str) -> tuple[str, int]:
    body, marker, status_text = stdout.rpartition("\nHTTP_STATUS:")
    if not marker:
        return stdout, 0
    try:
        return body, int(status_text.strip())
    except ValueError:
        return body, 0


def summarize_upload(payload: dict[str, Any]) -> dict[str, Any]:
    spec = payload.get("spec", {}) if isinstance(payload.get("spec"), dict) else {}
    document = spec.get("document", {}) if isinstance(spec.get("document"), dict) else {}
    labels = document.get("labels", {}) if isinstance(document.get("labels"), dict) else {}
    ingestion_report = (
        spec.get("ingestionReport", {}) if isinstance(spec.get("ingestionReport"), dict) else {}
    )
    chunks = spec.get("chunks", []) if isinstance(spec.get("chunks"), list) else []
    return {
        "status": spec.get("status"),
        "reason": spec.get("reason"),
        "documentId": document.get("documentId"),
        "title": document.get("title"),
        "mimeType": document.get("mimeType"),
        "chunkCount": document.get("chunkCount"),
        "contentBytes": document.get("contentBytes"),
        "labels": {
            key: labels.get(key)
            for key in [
                "parser",
                "documentFormat",
                "originalFileName",
                "originalMimeType",
                "originalBytes",
                "extractedChars",
                "truncated",
            ]
        },
        "ingestionReport": ingestion_report,
        "returnedChunkCount": len(chunks),
        "rawContentReturned": any(isinstance(chunk, dict) and "content" in chunk for chunk in chunks),
    }


def main() -> int:
    gateway_url = os.getenv("GATEWAY_URL", "http://127.0.0.1:18080").rstrip("/")
    upload_file = Path(os.getenv("RAG_UPLOAD_FILE", str(DEFAULT_UPLOAD_FILE))).resolve()
    report_path = Path(os.getenv("REPORT", str(DEFAULT_REPORT))).resolve()
    smoke_version = os.getenv("KUGNUS_RAG_FILE_SMOKE_VERSION", "v0.1.5")
    if not upload_file.is_file():
        raise RuntimeError(f"upload file not found: {upload_file}")

    token = get_oc_token()
    labels = {"source": "demo-pdf-smoke", "version": smoke_version}
    curl = run(
        [
            "curl",
            "-sS",
            "-w",
            "\nHTTP_STATUS:%{http_code}\n",
            "-H",
            f"Authorization: Bearer {token}",
            "-F",
            f"file=@{upload_file};type=application/pdf",
            "-F",
            f"labels={json.dumps(labels, separators=(',', ':'))}",
            "-F",
            "namespace=komsco-ai-kugnus",
            "-F",
            f"version={smoke_version}",
            f"{gateway_url}/v1/rag/uploads/file",
        ]
    )
    body, status_code = split_curl_status(curl.stdout)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {"parseError": body[:1000], "stderr": curl.stderr[:1000]}

    summary = summarize_upload(payload) if isinstance(payload, dict) else {}
    checks = [
        {
            "name": "http-200",
            "ok": status_code == 200,
            "detail": f"HTTP {status_code}",
        },
        {
            "name": "persisted",
            "ok": summary.get("status") == "persisted",
            "detail": str(summary.get("reason") or ""),
        },
        {
            "name": "pdf-parser",
            "ok": summary.get("labels", {}).get("parser") == "pypdf",
            "detail": str(summary.get("labels", {}).get("parser")),
        },
        {
            "name": "document-format-pdf",
            "ok": summary.get("labels", {}).get("documentFormat") == "pdf",
            "detail": str(summary.get("labels", {}).get("documentFormat")),
        },
        {
            "name": "chunks-produced",
            "ok": int(summary.get("chunkCount") or 0) > 0,
            "detail": f"chunkCount={summary.get('chunkCount')}",
        },
        {
            "name": "raw-content-not-returned",
            "ok": summary.get("rawContentReturned") is False,
            "detail": "response chunks do not include raw content",
        },
    ]
    result = "pass" if all(check["ok"] for check in checks) else "fail"
    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "RagFileUploadSmokeReport",
        "generatedAt": datetime.now(UTC).isoformat(),
        "gatewayUrl": gateway_url,
        "uploadFile": str(upload_file),
        "httpStatus": status_code,
        "result": result,
        "checks": checks,
        "summary": summary,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"RAG file upload smoke: {result.upper()}")
    for check in checks:
        print(f"[{'PASS' if check['ok'] else 'FAIL'}] {check['name']} {check['detail']}")
    print(f"Report: {report_path}")
    return 0 if result == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"RAG file upload smoke: FAIL\n[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
