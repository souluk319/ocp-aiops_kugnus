#!/usr/bin/env python3
"""Upload mock customer PDFs and prove they are searchable through Gateway RAG."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pypdf import PdfReader


ROOT_DIR = Path(__file__).resolve().parents[1]
PACK_DIR = ROOT_DIR / "docs" / "Ver.0.1.6" / "mock-customer-ops-pack"
PDF_DIR = PACK_DIR / "pdf"
DEFAULT_REPORT = ROOT_DIR / "docs" / "Ver.0.1.6" / "rag-mock-customer-smoke-report.json"
CUSTOMER = "mockpay"
NAMESPACE = "mockpay-prod"
VERSION = "v2026.06-mock"
RUN_ID = "mock-customer-ops-pack"

DOC_LABELS = {
    "00-service-map.pdf": {"docKind": "service-map", "freshness": "fresh"},
    "01-incident-runbook.pdf": {"docKind": "incident-runbook", "freshness": "fresh"},
    "02-change-approval-policy.pdf": {"docKind": "change-policy", "freshness": "fresh"},
    "03-incident-retrospective-2025.pdf": {"docKind": "incident-retrospective", "freshness": "stale"},
}

SEARCH_CASES = [
    {
        "name": "crashloop-runbook",
        "query": "MOCKPAY_CRASHLOOP_RUNBOOK payment-api CrashLoopBackOff previous logs",
        "marker": "MOCKPAY_CRASHLOOP_RUNBOOK",
        "labels": {"docKind": "incident-runbook", "source": RUN_ID},
    },
    {
        "name": "pull-secret-runbook",
        "query": "MOCKPAY_PULL_SECRET_CHECK ImagePullBackOff registry mirror pull secret",
        "marker": "MOCKPAY_PULL_SECRET_CHECK",
        "labels": {"docKind": "incident-runbook", "source": RUN_ID},
    },
    {
        "name": "change-policy",
        "query": "MOCKPAY_CHANGE_POLICY read-only approval window MP-CHG",
        "marker": "MOCKPAY_CHANGE_POLICY",
        "labels": {"docKind": "change-policy", "source": RUN_ID},
    },
    {
        "name": "stale-retrospective-explicit",
        "query": "MOCKPAY_STALE_2025_STORAGE_INCIDENT NFS timeout settlement",
        "marker": "MOCKPAY_STALE_2025_STORAGE_INCIDENT",
        "labels": {"docKind": "incident-retrospective", "source": RUN_ID, "freshness": "stale"},
    },
]

NEGATIVE_SEARCH_CASES = [
    {
        "name": "stale-retrospective-hidden-by-default",
        "query": "MOCKPAY_STALE_2025_STORAGE_INCIDENT NFS timeout settlement",
        "marker": "MOCKPAY_STALE_2025_STORAGE_INCIDENT",
        "labels": {"docKind": "incident-retrospective", "source": RUN_ID},
    },
]


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


def curl_json(args: list[str]) -> tuple[dict[str, Any], int, str]:
    proc = run(args)
    body, status = split_curl_status(proc.stdout)
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = {"parseError": body[:1000], "stderr": proc.stderr[:1000]}
    return payload, status, proc.stderr[:1000]


def build_pdfs() -> None:
    proc = run(["python3", "scripts/build-mock-customer-pdfs.py"])
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip())


def summarize_upload(payload: dict[str, Any]) -> dict[str, Any]:
    spec = payload.get("spec", {}) if isinstance(payload.get("spec"), dict) else {}
    document = spec.get("document", {}) if isinstance(spec.get("document"), dict) else {}
    labels = document.get("labels", {}) if isinstance(document.get("labels"), dict) else {}
    chunks = spec.get("chunks", []) if isinstance(spec.get("chunks"), list) else []
    return {
        "status": spec.get("status"),
        "reason": spec.get("reason"),
        "documentId": document.get("documentId"),
        "title": document.get("title"),
        "chunkCount": document.get("chunkCount"),
        "labels": {
            key: labels.get(key)
            for key in ["parser", "documentFormat", "docKind", "freshness", "source", "safetyClass"]
        },
        "returnedChunkCount": len(chunks),
        "rawContentReturned": any(isinstance(chunk, dict) and "content" in chunk for chunk in chunks),
    }


def upload_pdf(gateway_url: str, token: str, pdf: Path) -> tuple[dict[str, Any], int]:
    labels = {"source": RUN_ID, "safetyClass": "read-only", **DOC_LABELS[pdf.name]}
    payload, status, _stderr = curl_json(
        [
            "curl",
            "-sS",
            "-w",
            "\nHTTP_STATUS:%{http_code}\n",
            "-H",
            f"Authorization: Bearer {token}",
            "-F",
            f"file=@{pdf};type=application/pdf",
            "-F",
            f"labels={json.dumps(labels, separators=(',', ':'))}",
            "-F",
            f"customer={CUSTOMER}",
            "-F",
            f"namespace={NAMESPACE}",
            "-F",
            f"version={VERSION}",
            "-F",
            f"run_id={RUN_ID}",
            "-F",
            f"source_uri=mock-customer://{pdf.name}",
            f"{gateway_url}/v1/rag/uploads/file",
        ]
    )
    return summarize_upload(payload), status


def pdf_text_health(pdf: Path) -> dict[str, Any]:
    text = "\n".join(page.extract_text() or "" for page in PdfReader(str(pdf)).pages)
    return {
        "hasHangul": any("가" <= char <= "힣" for char in text),
        "hasNul": "\x00" in text,
        "textPreview": text[:160],
    }


def search(gateway_url: str, token: str, case: dict[str, Any]) -> tuple[dict[str, Any], int]:
    body = {
        "query": case["query"],
        "topK": 5,
        "includeContent": True,
        "filters": {
            "sourceTypes": ["user-upload"],
            "customers": [CUSTOMER],
            "namespaces": [NAMESPACE],
            "labels": case["labels"],
        },
        "runId": f"{RUN_ID}-{case['name']}",
    }
    tmp = Path(os.getenv("TMPDIR", "/tmp")) / f"{RUN_ID}-{case['name']}.json"
    tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    payload, status, _stderr = curl_json(
        [
            "curl",
            "-sS",
            "-w",
            "\nHTTP_STATUS:%{http_code}\n",
            "-H",
            f"Authorization: Bearer {token}",
            "-H",
            "Content-Type: application/json",
            "--data-binary",
            f"@{tmp}",
            f"{gateway_url}/v1/rag/search",
        ]
    )
    return payload, status


def result_text(result: dict[str, Any]) -> str:
    metadata = result.get("metadata", {}) if isinstance(result.get("metadata"), dict) else {}
    return " ".join(
        str(value or "")
        for value in [
            result.get("title"),
            result.get("contentPreview"),
            result.get("content"),
            metadata.get("docKind"),
            metadata.get("freshness"),
        ]
    )


def main() -> int:
    gateway_url = os.getenv("GATEWAY_URL", "http://127.0.0.1:18080").rstrip("/")
    report_path = Path(os.getenv("REPORT", str(DEFAULT_REPORT))).resolve()
    build_pdfs()
    pdfs = [PDF_DIR / name for name in sorted(DOC_LABELS)]
    missing = [str(pdf) for pdf in pdfs if not pdf.is_file()]
    if missing:
        raise RuntimeError(f"mock customer PDF(s) missing: {missing}")

    token = get_oc_token()
    upload_summaries = []
    checks = []
    for pdf in pdfs:
        text_health = pdf_text_health(pdf)
        summary, status = upload_pdf(gateway_url, token, pdf)
        upload_summaries.append({"file": str(pdf), "httpStatus": status, "textHealth": text_health, **summary})
        checks.extend(
            [
                {"name": f"{pdf.name}:hangul-extracts", "ok": text_health["hasHangul"], "detail": text_health["textPreview"]},
                {"name": f"{pdf.name}:no-broken-nul", "ok": not text_health["hasNul"], "detail": "pypdf extracted text has no NUL replacement"},
                {"name": f"{pdf.name}:http-200", "ok": status == 200, "detail": f"HTTP {status}"},
                {"name": f"{pdf.name}:persisted", "ok": summary.get("status") == "persisted", "detail": str(summary.get("reason") or "")},
                {"name": f"{pdf.name}:pdf-parser", "ok": summary.get("labels", {}).get("parser") == "pypdf", "detail": str(summary.get("labels", {}).get("parser"))},
                {"name": f"{pdf.name}:chunks", "ok": int(summary.get("chunkCount") or 0) > 0, "detail": f"chunkCount={summary.get('chunkCount')}"},
                {"name": f"{pdf.name}:raw-hidden", "ok": summary.get("rawContentReturned") is False, "detail": "raw content omitted from upload response"},
            ]
        )

    search_summaries = []
    for case in SEARCH_CASES:
        payload, status = search(gateway_url, token, case)
        spec = payload.get("spec", {}) if isinstance(payload.get("spec"), dict) else {}
        results = spec.get("results", []) if isinstance(spec.get("results"), list) else []
        found = any(case["marker"] in result_text(item) for item in results if isinstance(item, dict))
        search_summaries.append(
            {
                "name": case["name"],
                "httpStatus": status,
                "status": spec.get("status"),
                "resultCount": len(results),
                "markerFound": found,
                "titles": [item.get("title") for item in results if isinstance(item, dict)],
            }
        )
        checks.extend(
            [
                {"name": f"{case['name']}:http-200", "ok": status == 200, "detail": f"HTTP {status}"},
                {"name": f"{case['name']}:marker-found", "ok": found, "detail": f"resultCount={len(results)} marker={case['marker']}"},
            ]
        )

    for case in NEGATIVE_SEARCH_CASES:
        payload, status = search(gateway_url, token, case)
        spec = payload.get("spec", {}) if isinstance(payload.get("spec"), dict) else {}
        results = spec.get("results", []) if isinstance(spec.get("results"), list) else []
        found = any(case["marker"] in result_text(item) for item in results if isinstance(item, dict))
        search_summaries.append(
            {
                "name": case["name"],
                "httpStatus": status,
                "status": spec.get("status"),
                "resultCount": len(results),
                "markerFound": found,
                "negative": True,
            }
        )
        checks.extend(
            [
                {"name": f"{case['name']}:http-200", "ok": status == 200, "detail": f"HTTP {status}"},
                {"name": f"{case['name']}:marker-hidden", "ok": not found, "detail": f"resultCount={len(results)} marker={case['marker']}"},
            ]
        )

    result = "pass" if all(check["ok"] for check in checks) else "fail"
    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "RagMockCustomerSmokeReport",
        "generatedAt": datetime.now(UTC).isoformat(),
        "gatewayUrl": gateway_url,
        "customer": CUSTOMER,
        "namespace": NAMESPACE,
        "result": result,
        "checks": checks,
        "uploads": upload_summaries,
        "searches": search_summaries,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"RAG mock customer smoke: {result.upper()}")
    for check in checks:
        print(f"[{'PASS' if check['ok'] else 'FAIL'}] {check['name']} {check['detail']}")
    print(f"Report: {report_path}")
    return 0 if result == "pass" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"RAG mock customer smoke: FAIL\n[FAIL] {exc}", file=sys.stderr)
        raise SystemExit(1)
