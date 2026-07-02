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
import ssl
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
DEFAULT_OCP_LADDER_REPORT = REPO_ROOT / "docs/Ver.0.1.5/ocp-connectivity-ladder-report.json"
DEFAULT_OLS_READINESS_URL = "https://127.0.0.1:18443/readiness"

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


def run_oc(args: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["oc", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def oc_identity(timeout: int) -> str:
    result = run_oc(["whoami"], timeout)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"oc identity unavailable: {stderr[:300]}")
    identity = result.stdout.strip()
    if not identity:
        raise RuntimeError("oc identity is empty. Run oc login again and confirm `oc whoami` prints a user.")
    return identity


def oc_server(timeout: int) -> str:
    result = run_oc(["whoami", "--show-server"], timeout)
    return result.stdout.strip() if result.returncode == 0 else ""


def oc_token(timeout: int) -> str:
    result = run_oc(["whoami", "--show-token"], timeout)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"oc login required or OpenShift API unavailable: {stderr[:300]}")
    token = result.stdout.strip()
    if not token:
        raise RuntimeError("oc token is empty. Run oc login first.")
    return token


def safe_error(exc: BaseException) -> str:
    return str(exc).replace("\n", " ")[:500]


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def report_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def summarize_ocp_ladder(payload: dict[str, Any], report_path: Path) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    interpretation = (
        payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    )
    return {
        "readyForStrictLightspeedGate": bool(summary.get("readyForStrictLightspeedGate")),
        "firstFailingLayer": summary.get("firstFailingLayer") or "",
        "message": summary.get("message") or "",
        "likelyCause": interpretation.get("likelyCause") or "",
        "confidence": interpretation.get("confidence") or "",
        "explanation": interpretation.get("explanation") or "",
        "nextActions": interpretation.get("nextActions") or [],
        "report": report_display_path(report_path),
    }


def refresh_ocp_ladder(timeout: int, report_path: Path) -> dict[str, Any]:
    started = time.monotonic()
    script = REPO_ROOT / "scripts/kugnus-ocp-connectivity-ladder.py"
    command = [
        sys.executable,
        str(script),
        "--fast-fail",
        "--timeout",
        str(timeout),
        "--report",
        str(report_path),
    ]
    try:
        result = subprocess.run(
            command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=max(timeout + 10, 20),
        )
    except subprocess.TimeoutExpired as exc:
        payload = load_json(report_path)
        summary = summarize_ocp_ladder(payload, report_path)
        summary.update(
            {
                "refreshReturnCode": None,
                "refreshDurationMs": int((time.monotonic() - started) * 1000),
                "refreshTimeout": True,
                "refreshStdoutPreview": (exc.stdout or "")[:800]
                if isinstance(exc.stdout, str)
                else "",
                "refreshStderrPreview": (exc.stderr or "")[:800]
                if isinstance(exc.stderr, str)
                else "",
            }
        )
        return summary
    payload = load_json(report_path)
    summary = summarize_ocp_ladder(payload, report_path)
    summary.update(
        {
            "refreshReturnCode": result.returncode,
            "refreshDurationMs": int((time.monotonic() - started) * 1000),
            "refreshStdoutPreview": result.stdout.strip()[:800],
            "refreshStderrPreview": result.stderr.strip()[:800],
        }
    )
    return summary


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


def request_ols_readiness(url: str, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    context = ssl._create_unverified_context() if url.startswith("https://") else None
    try:
        with urllib.request.urlopen(request, timeout=timeout, context=context) as response:  # noqa: S310 local verifier
            raw = response.read().decode("utf-8", errors="replace")
            payload: dict[str, Any] = {}
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"raw": raw[:300]}
            ready = payload.get("ready") is True if isinstance(payload, dict) else False
            return {
                "ok": response.status == 200 and ready,
                "statusCode": response.status,
                "ready": ready,
                "error": "",
            }
    except Exception as exc:  # noqa: BLE001 local verifier should persist diagnostics
        return {"ok": False, "statusCode": 0, "ready": False, "error": safe_error(exc)}


def wait_for_ols_readiness(
    url: str,
    *,
    attempts: int,
    stable_count: int,
    interval_seconds: float,
    timeout: int,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    stable = 0
    started = time.monotonic()

    for attempt in range(1, attempts + 1):
        check = request_ols_readiness(url, timeout)
        checks.append(
            {
                "attempt": attempt,
                "ok": check["ok"],
                "statusCode": check["statusCode"],
                "ready": check["ready"],
                "error": check.get("error", ""),
            }
        )
        stable = stable + 1 if check["ok"] else 0
        if stable >= stable_count:
            return {
                "ok": True,
                "url": url,
                "attempts": attempt,
                "stableCount": stable,
                "durationMs": int((time.monotonic() - started) * 1000),
                "last": check,
                "checks": checks[-stable_count:],
            }
        time.sleep(interval_seconds)

    return {
        "ok": False,
        "url": url,
        "attempts": attempts,
        "stableCount": stable,
        "durationMs": int((time.monotonic() - started) * 1000),
        "last": checks[-1] if checks else {},
        "checks": checks[-5:],
    }


def stream_chat(gateway_url: str, token: str, case: dict[str, Any], timeout: int) -> dict[str, Any]:
    run_id = f"live-lightspeed-final-{case['id']}-{int(time.time())}"
    request = urllib.request.Request(
        f"{gateway_url}/v1/chat/stream",
        data=json.dumps(
            {
                "message": case["message"],
                "pageContext": {
                    "pathname": "/dashboards/aiops",
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
    answer_contract_events: list[dict[str, Any]] = []
    answer_previews: list[str] = []
    event_counts: dict[str, int] = {}
    evidence_ref_events: list[dict[str, Any]] = []
    fallback_events: list[dict[str, Any]] = []
    gateway_errors: list[dict[str, Any]] = []
    lightspeed_errors: list[dict[str, Any]] = []
    rca_context_phases: list[str] = []
    status_events: list[dict[str, Any]] = []
    tool_plan_events: list[dict[str, Any]] = []
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

            if event_type == "tool_plan":
                plan = event.get("plan") if isinstance(event.get("plan"), dict) else {}
                tool_plan_events.append(
                    {
                        "runId": event.get("runId"),
                        "taskType": plan.get("task_type") or event.get("kind"),
                        "toolCount": len(plan.get("tool_plan") or []),
                    }
                )
                continue

            if event_type == "rca_context":
                context = event.get("context") if isinstance(event.get("context"), dict) else {}
                metadata = context.get("metadata") if isinstance(context.get("metadata"), dict) else {}
                phase = str(metadata.get("phase") or "")
                if phase:
                    rca_context_phases.append(phase)
                continue

            if event_type == "tool_result" and event.get("name") == "evidence_ref":
                result = event.get("result") if isinstance(event.get("result"), dict) else {}
                evidence_ref_events.append(
                    {
                        "status": event.get("status"),
                        "summary": event.get("summary"),
                        "evidenceId": result.get("evidenceId") or event.get("evidenceId") or event.get("id"),
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
            if source == "gateway_answer_contract":
                answer_contract_events.append(
                    {
                        "answerContract": event.get("answerContract"),
                        "hasAiopsActionFeature": "AIOps 조치 기능" in content and "조치 후보" in content,
                        "hasActionExecutionPath": (
                            "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord"
                            in content
                        ),
                        "hasRejectionPath": (
                            "거절 경로" in content
                            and "/v1/actions/rejections" in content
                            and "rejected" in content
                        ),
                        "preview": content.strip()[:240],
                    }
                )
                continue
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
        "answerContractEvents": answer_contract_events,
        "answerPreviews": answer_previews,
        "doneReceived": done,
        "durationMs": int((time.monotonic() - started_at) * 1000),
        "evidenceRefEvents": evidence_ref_events,
        "eventCounts": event_counts,
        "fallbackEvents": fallback_events,
        "gatewayErrors": gateway_errors,
        "lightspeedErrors": lightspeed_errors,
        "olsTextEvents": ols_text_events,
        "rcaContextPhases": rca_context_phases,
        "requiredTextPresent": {text: text in answer_text for text in required_text},
        "runStatusStages": [item.get("stage") for item in status_events],
        "statusEvents": status_events,
        "toolPlanEvents": tool_plan_events,
    }


def evaluate_case(case_id: str, stream: dict[str, Any], status_result: dict[str, Any]) -> dict[str, Any]:
    status_payload = status_result.get("payload") if status_result.get("ok") else {}
    lightspeed_status = (
        status_payload.get("spec", {})
        .get("safetyContract", {})
        .get("lightspeedStatus", {})
    )
    access_review_status = status_payload.get("spec", {}).get("accessReviewStatus", {})
    checks = {
        "doneReceived": stream["doneReceived"] is True,
        "lightspeedStageSeen": "lightspeed" in stream["runStatusStages"],
        "completedStageSeen": "completed" in stream["runStatusStages"],
        "olsTextReceived": stream["olsTextEvents"] > 0 and stream["answerLength"] > 0,
        "toolPlanSeen": len(stream.get("toolPlanEvents", [])) > 0,
        "evidenceRefSeen": len(stream.get("evidenceRefEvents", [])) > 0,
        "rcaContextPreAnswerSeen": "pre_answer" in stream.get("rcaContextPhases", []),
        "rcaContextPostAnswerSeen": "post_answer" in stream.get("rcaContextPhases", []),
        "noGatewayFallbackText": len(stream["fallbackEvents"]) == 0,
        "noGatewayErrorEvent": len(stream["gatewayErrors"]) == 0,
        "noLightspeedErrorToolResult": len(stream["lightspeedErrors"]) == 0,
        "requiredTextPresent": all(stream["requiredTextPresent"].values()),
        "aiopsActionContractPresent": any(
            event.get("answerContract") == "aiops-action-v0.1.9"
            and event.get("hasAiopsActionFeature") is True
            and event.get("hasActionExecutionPath") is True
            and event.get("hasRejectionPath") is True
            for event in stream.get("answerContractEvents", [])
        ),
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
        "accessReviewStatus": access_review_status,
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
    parser.add_argument("--ocp-ladder-report", default=str(DEFAULT_OCP_LADDER_REPORT))
    parser.add_argument("--oc-timeout", type=int, default=12)
    parser.add_argument("--ols-readiness-url", default=DEFAULT_OLS_READINESS_URL)
    parser.add_argument("--readiness-attempts", type=int, default=20)
    parser.add_argument("--readiness-stable-count", type=int, default=3)
    parser.add_argument("--readiness-interval", type=float, default=0.5)
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    parser.add_argument("--stream-timeout", type=int, default=360)
    args = parser.parse_args()

    report_path = Path(args.report)
    cases: list[dict[str, Any]] = []
    identity = ""
    server = ""

    ocp_ladder_report = Path(args.ocp_ladder_report)

    try:
        identity = oc_identity(args.oc_timeout)
        server = oc_server(args.oc_timeout)
        token = oc_token(args.oc_timeout)
    except Exception as exc:  # noqa: BLE001 local verifier should persist diagnostics
        ocp_connectivity = refresh_ocp_ladder(args.oc_timeout, ocp_ladder_report)
        report = {
            "apiVersion": "aiops.komsco/v1alpha1",
            "kind": "LiveLightspeedFinalResponseVerification",
            "generatedAt": now_rfc3339(),
            "branch": git_value(["branch", "--show-current"]),
            "headSha": git_value(["rev-parse", "HEAD"]),
            "gateway": args.gateway,
            "allSucceeded": False,
            "preflight": {
                "ocIdentityAvailable": False,
                "ocIdentity": "",
                "ocServer": server,
                "ocTokenAvailable": False,
                "ocTimeoutSeconds": args.oc_timeout,
                "error": safe_error(exc),
                "ocpConnectivity": ocp_connectivity,
            },
            "cases": [],
            "note": "OpenShift token and full answer bodies are intentionally not persisted.",
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Live Lightspeed final response: FAIL")
        print(f"[FAIL] oc token unavailable: {safe_error(exc)}")
        if ocp_connectivity.get("firstFailingLayer"):
            print(
                "[OCP] "
                f"firstFailingLayer={ocp_connectivity.get('firstFailingLayer')} "
                f"likelyCause={ocp_connectivity.get('likelyCause')}"
            )
        print(f"Report: {report_path}")
        return 1

    ols_readiness = wait_for_ols_readiness(
        args.ols_readiness_url,
        attempts=args.readiness_attempts,
        stable_count=args.readiness_stable_count,
        interval_seconds=args.readiness_interval,
        timeout=args.oc_timeout,
    )
    if not ols_readiness["ok"]:
        ocp_connectivity = refresh_ocp_ladder(args.oc_timeout, ocp_ladder_report)
        report = {
            "apiVersion": "aiops.komsco/v1alpha1",
            "kind": "LiveLightspeedFinalResponseVerification",
            "generatedAt": now_rfc3339(),
            "branch": git_value(["branch", "--show-current"]),
            "headSha": git_value(["rev-parse", "HEAD"]),
            "gateway": args.gateway,
            "allSucceeded": False,
            "preflight": {
                "ocIdentityAvailable": True,
                "ocIdentity": identity,
                "ocServer": server,
                "ocTokenAvailable": True,
                "ocTimeoutSeconds": args.oc_timeout,
                "olsReadiness": ols_readiness,
                "ocpConnectivity": ocp_connectivity,
            },
            "cases": [],
            "note": "OpenShift token and full answer bodies are intentionally not persisted.",
        }
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Live Lightspeed final response: FAIL")
        print(
            "[FAIL] OLS local readiness did not become stable: "
            f"url={args.ols_readiness_url} last={ols_readiness.get('last')}"
        )
        if ocp_connectivity.get("firstFailingLayer"):
            print(
                "[OCP] "
                f"firstFailingLayer={ocp_connectivity.get('firstFailingLayer')} "
                f"likelyCause={ocp_connectivity.get('likelyCause')}"
            )
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
        "preflight": {
            "ocIdentityAvailable": True,
            "ocIdentity": identity,
            "ocServer": server,
            "ocTokenAvailable": True,
            "ocTimeoutSeconds": args.oc_timeout,
            "olsReadiness": ols_readiness,
        },
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
