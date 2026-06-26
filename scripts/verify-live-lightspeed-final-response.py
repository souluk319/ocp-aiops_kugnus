#!/usr/bin/env python3
"""Verify that the local Gateway receives final answers from OpenShift Lightspeed.

This verifier is intentionally stricter than the general demo verifiers:
Gateway fallback is a failure, an OLS stream error is a failure, and the final
runtime status must report streamProbe=succeeded with fallbackActive=false.
It does not persist the OpenShift token or full answer bodies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.5/live-lightspeed-final-response-verification.json"

CASES = [
    {
        "id": "cluster-summary",
        "message": (
            "현재 클러스터 상태를 OpenShift Lightspeed 최종 응답으로 "
            "RCA 보고서 형식으로 정리해줘. Gateway fallback이면 안 되고 "
            "Lightspeed가 답해야 한다."
        ),
        "requiredText": ["RCA", "근거"],
    },
    {
        "id": "official-evidence-rca",
        "message": (
            "어제 새벽에 default namespace Pod가 왜 재시작됐어? "
            "Gateway가 수집한 RCA Context와 Runbook evidence를 근거로 "
            "OpenShift Lightspeed 최종 답변까지 생성해줘. 확인 안 된 것은 "
            "확인 불가로 분리해."
        ),
        "requiredText": ["RCA", "확인"],
    },
]


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def git_value(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def oc_token() -> str:
    result = subprocess.run(
        ["oc", "whoami", "--show-token"],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("oc token is empty. Run oc login first.")
    return token


def safe_error(exc: BaseException) -> str:
    return str(exc).replace("\n", " ")[:500]


def request_json_result(url: str, token: str, timeout: int = 45) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 local verifier
            return {
                "ok": True,
                "statusCode": response.status,
                "payload": json.loads(response.read().decode("utf-8")),
            }
    except urllib.error.HTTPError as exc:
        return {
            "ok": False,
            "statusCode": exc.code,
            "error": exc.read().decode("utf-8", errors="replace")[:1000],
        }
    except Exception as exc:  # noqa: BLE001 local verifier should persist diagnostics
        return {"ok": False, "statusCode": 0, "error": safe_error(exc)}


def stream_chat(gateway_url: str, token: str, case: dict[str, Any], timeout: int) -> dict[str, Any]:
    run_id = f"live-lightspeed-final-{case['id']}-{int(time.time())}"
    request = urllib.request.Request(
        f"{gateway_url}/v1/chat/stream",
        data=json.dumps(
            {
                "message": case["message"],
                "pageContext": {
                    "pathname": "/aiops-kugnus",
                    "aiopsExecutionMode": "execute",
                    "source": "live-lightspeed-final-verifier",
                },
                "recentMessages": [],
                "runId": run_id,
            }
        ).encode("utf-8"),
        headers={
            "Accept": "text/event-stream",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    data_lines: list[str] = []
    answer_parts: list[str] = []
    answer_previews: list[str] = []
    event_counts: dict[str, int] = {}
    fallback_events: list[dict[str, Any]] = []
    gateway_errors: list[dict[str, Any]] = []
    lightspeed_errors: list[dict[str, Any]] = []
    status_events: list[dict[str, Any]] = []
    ols_text_events = 0
    done = False
    started_at = time.monotonic()

    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 local verifier
        for raw_line in response:
            if time.monotonic() - started_at > timeout:
                raise TimeoutError(f"{case['id']} exceeded {timeout}s")

            line = raw_line.decode("utf-8", errors="replace").rstrip("\n")
            if line.startswith("data:"):
                data_lines.append(line[len("data:") :].strip())
                continue

            if line != "" or not data_lines:
                continue

            raw_data = "\n".join(data_lines).strip()
            data_lines = []
            if raw_data == "[DONE]":
                done = True
                break

            event = json.loads(raw_data)
            event_type = str(event.get("type") or "unknown")
            event_counts[event_type] = event_counts.get(event_type, 0) + 1

            if event_type == "run_status":
                status_events.append(
                    {
                        "stage": event.get("stage"),
                        "message": event.get("message"),
                        "gatewayContextDigest": event.get("gatewayContextDigest"),
                    }
                )
                continue

            if event_type == "tool_result" and (
                event.get("name") == "lightspeed_stream"
                or event.get("fallbackAnswer") is True
                or event.get("status") == "error"
            ):
                lightspeed_errors.append(
                    {
                        "name": event.get("name"),
                        "status": event.get("status"),
                        "summary": event.get("summary"),
                        "detailPreview": str(event.get("detail") or "")[:240],
                    }
                )
                continue

            if event_type == "error":
                gateway_errors.append(
                    {
                        "message": str(event.get("message") or "")[:300],
                        "detail": str(event.get("detail") or "")[:300],
                        "code": event.get("code"),
                    }
                )
                continue

            if event_type != "text":
                continue

            source = str(event.get("source") or "")
            content = str(event.get("content") or "")
            if event.get("fallbackAnswer") is True or source == "gateway_fallback":
                fallback_events.append(
                    {
                        "source": source,
                        "streamProbe": event.get("streamProbe"),
                        "preview": content.strip()[:240],
                    }
                )
            elif source not in {"gateway_rag_citation", "gateway_answer_contract"}:
                ols_text_events += 1
                answer_parts.append(content)
                if content.strip() and len(answer_previews) < 5:
                    answer_previews.append(content.strip()[:240])

    answer_text = "".join(answer_parts)
    required_text = list(case.get("requiredText") or [])
    return {
        "answerDigest": hashlib.sha256(answer_text.encode("utf-8")).hexdigest() if answer_text else "",
        "answerLength": len(answer_text),
        "answerPreviews": answer_previews,
        "doneReceived": done,
        "durationMs": int((time.monotonic() - started_at) * 1000),
        "eventCounts": event_counts,
        "fallbackEvents": fallback_events,
        "gatewayErrors": gateway_errors,
        "lightspeedErrors": lightspeed_errors,
        "olsTextEvents": ols_text_events,
        "requiredTextPresent": {text: text in answer_text for text in required_text},
        "runStatusStages": [item.get("stage") for item in status_events],
        "statusEvents": status_events,
    }


def evaluate_case(case_id: str, stream: dict[str, Any], status_result: dict[str, Any]) -> dict[str, Any]:
    status_payload = status_result.get("payload") if status_result.get("ok") else {}
    lightspeed_status = (
        status_payload.get("spec", {})
        .get("safetyContract", {})
        .get("lightspeedStatus", {})
    )
    checks = {
        "doneReceived": stream["doneReceived"] is True,
        "lightspeedStageSeen": "lightspeed" in stream["runStatusStages"],
        "completedStageSeen": "completed" in stream["runStatusStages"],
        "olsTextReceived": stream["olsTextEvents"] > 0 and stream["answerLength"] > 0,
        "noGatewayFallbackText": len(stream["fallbackEvents"]) == 0,
        "noGatewayErrorEvent": len(stream["gatewayErrors"]) == 0,
        "noLightspeedErrorToolResult": len(stream["lightspeedErrors"]) == 0,
        "requiredTextPresent": all(stream["requiredTextPresent"].values()),
        "statusEndpointReachable": status_result.get("ok") is True,
        "runtimeStreamProbeSucceeded": lightspeed_status.get("streamProbe") == "succeeded",
        "runtimeLastStatusSucceeded": lightspeed_status.get("lastStatus") == "succeeded",
        "runtimeFallbackInactive": lightspeed_status.get("fallbackActive") is False,
        "runtimeLastErrorEmpty": not lightspeed_status.get("lastError"),
    }
    return {
        "caseId": case_id,
        "ok": all(checks.values()),
        "checks": checks,
        "lightspeedStatus": lightspeed_status,
        "statusEndpoint": {
            "ok": status_result.get("ok") is True,
            "statusCode": status_result.get("statusCode"),
            "errorPreview": str(status_result.get("error") or "")[:300],
        },
        "stream": stream,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway", default="http://127.0.0.1:18080")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--stream-timeout", type=int, default=360)
    args = parser.parse_args()

    report_path = Path(args.report)
    cases: list[dict[str, Any]] = []

    try:
        token = oc_token()
    except Exception as exc:  # noqa: BLE001 local verifier should persist diagnostics
        report = {
            "apiVersion": "aiops.komsco/v1alpha1",
            "kind": "LiveLightspeedFinalResponseVerification",
            "generatedAt": now_rfc3339(),
            "branch": git_value(["branch", "--show-current"]),
            "headSha": git_value(["rev-parse", "HEAD"]),
            "gateway": args.gateway,
            "allSucceeded": False,
            "preflight": {
                "ocTokenAvailable": False,
                "error": safe_error(exc),
            },
            "cases": [],
            "note": "OpenShift token and full answer bodies are intentionally not persisted.",
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Live Lightspeed final response: FAIL")
        print(f"[FAIL] oc token unavailable: {safe_error(exc)}")
        print(f"Report: {report_path}")
        return 1

    for case in CASES:
        try:
            stream = stream_chat(args.gateway.rstrip("/"), token, case, args.stream_timeout)
        except Exception as exc:  # noqa: BLE001 local verifier should persist diagnostics
            cases.append(
                {
                    "caseId": case["id"],
                    "ok": False,
                    "checks": {"streamCompletedWithoutException": False},
                    "error": safe_error(exc),
                }
            )
            continue

        status_result = request_json_result(f"{args.gateway.rstrip('/')}/v1/aiops/status", token)
        cases.append(evaluate_case(case["id"], stream, status_result))

    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "LiveLightspeedFinalResponseVerification",
        "generatedAt": now_rfc3339(),
        "branch": git_value(["branch", "--show-current"]),
        "headSha": git_value(["rev-parse", "HEAD"]),
        "gateway": args.gateway,
        "allSucceeded": all(case["ok"] for case in cases),
        "cases": cases,
        "note": "OpenShift token and full answer bodies are intentionally not persisted.",
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Live Lightspeed final response: {'PASS' if report['allSucceeded'] else 'FAIL'}")
    for case in cases:
        marker = "PASS" if case["ok"] else "FAIL"
        status = case.get("lightspeedStatus") or {}
        stream = case.get("stream") or {}
        print(
            f"[{marker}] {case['caseId']} "
            f"olsText={stream.get('olsTextEvents', 0)} fallback={len(stream.get('fallbackEvents', []))} "
            f"errors={len(stream.get('lightspeedErrors', []))} "
            f"streamProbe={status.get('streamProbe')} fallbackActive={status.get('fallbackActive')}"
        )
        if not case["ok"]:
            failed = [name for name, ok in case["checks"].items() if not ok]
            print(f"       failed checks: {', '.join(failed)}")
    print(f"Report: {report_path}")

    return 0 if report["allSucceeded"] else 1


if __name__ == "__main__":
    sys.exit(main())
