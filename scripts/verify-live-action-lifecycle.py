#!/usr/bin/env python3
"""Verify live Gateway action proposal, approval, and rejection lifecycle.

This verifier uses the current `oc` login token, but never prints or stores it.
It calls `/v1/actions/execute` only for requests that must be rejected before
mutation dispatch, so it proves approval safety without mutating the cluster.
"""

from __future__ import annotations

import argparse
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
DEFAULT_GATEWAY_URL = "http://127.0.0.1:18080"
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.5/live-action-lifecycle-verification.json"


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
    return subprocess.run(["oc", *args], capture_output=True, text=True, timeout=timeout)


def oc_identity(timeout: int) -> str:
    result = run_oc(["whoami"], timeout)
    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(f"oc identity unavailable: {stderr[:300]}")
    identity = result.stdout.strip()
    if not identity:
        raise RuntimeError("oc identity is empty. Run `oc login` first.")
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
        raise RuntimeError("oc token is empty. Run `oc login` first.")
    return token


def safe_error(exc: BaseException) -> str:
    return str(exc).replace("\n", " ")[:500]


def report_display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def request_json(
    method: str,
    url: str,
    token: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    data = None
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            body = json.loads(raw) if raw else {}
            return {"ok": True, "statusCode": response.status, "body": body}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body: Any = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            body = {"raw": raw[:500]}
        return {"ok": False, "statusCode": exc.code, "body": body}
    except urllib.error.URLError as exc:
        return {"ok": False, "statusCode": 0, "body": {"detail": safe_error(exc)}}


def record_check(checks: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    checks.append({"name": name, "passed": bool(passed), "detail": detail})


def body_detail(response: dict[str, Any]) -> str:
    body = response.get("body")
    if isinstance(body, dict):
        detail = body.get("detail")
        if detail:
            return str(detail)
        return json.dumps(body, ensure_ascii=False, sort_keys=True)[:500]
    return str(body)[:500]


def action_proposal_payload(case_id: str) -> dict[str, Any]:
    return {
        "incidentId": f"live-verifier-{case_id}",
        "runId": f"run-{case_id}",
        "toolName": "rollout_restart_deployment",
        "toolVersion": "v1",
        "target": {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "namespace": "komsco-ai-dev",
            "name": "aiops-two-pod-exec",
            "uid": f"live-verifier-{case_id}",
        },
        "parameters": {"restartedAt": now_rfc3339()},
        "evidenceRefs": [
            {
                "source": "live-action-lifecycle-verifier",
                "refId": f"evidence-{case_id}",
                "summary": "Verifier generated evidence reference. No mutation is executed.",
            }
        ],
        "runbookRefs": [
            {
                "runbookId": "deployment_rollout_restart_v1",
                "runbookVersion": "v1",
                "section": "operator approval dry-run gate",
            }
        ],
        "policy": {"approvalMode": "operator", "mutationMode": "approval-required"},
    }


def extract_metadata_name(response: dict[str, Any]) -> str:
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    metadata = body.get("metadata") if isinstance(body.get("metadata"), dict) else {}
    return str(metadata.get("name") or "")


def extract_plan_digest(response: dict[str, Any]) -> str:
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    spec = body.get("spec") if isinstance(body.get("spec"), dict) else {}
    plan = spec.get("sealedActionPlan") if isinstance(spec.get("sealedActionPlan"), dict) else {}
    digest = plan.get("digest") if isinstance(plan.get("digest"), dict) else {}
    return str(digest.get("planDigest") or "")


def extract_decision_status(response: dict[str, Any]) -> str:
    body = response.get("body") if isinstance(response.get("body"), dict) else {}
    spec = body.get("spec") if isinstance(body.get("spec"), dict) else {}
    decision = spec.get("approvalDecision") if isinstance(spec.get("approvalDecision"), dict) else {}
    return str(decision.get("status") or "")


def create_proposal_plan(
    gateway_url: str,
    token: str,
    case_id: str,
    timeout: int,
    checks: list[dict[str, Any]],
) -> tuple[str, str]:
    proposal = request_json(
        "POST",
        f"{gateway_url}/v1/actions/proposals",
        token,
        payload=action_proposal_payload(case_id),
        timeout=timeout,
    )
    proposal_id = extract_metadata_name(proposal)
    record_check(
        checks,
        f"{case_id}: action proposal created",
        proposal["statusCode"] == 200 and proposal_id.startswith("proposal-"),
        f"HTTP {proposal['statusCode']} proposalId={proposal_id or '-'}",
    )

    plan = request_json(
        "POST",
        f"{gateway_url}/v1/actions/plans",
        token,
        payload={"proposalId": proposal_id},
        timeout=timeout,
    )
    plan_id = extract_metadata_name(plan)
    plan_digest = extract_plan_digest(plan)
    record_check(
        checks,
        f"{case_id}: sealed action plan created",
        plan["statusCode"] == 200 and plan_id.startswith("plan-") and plan_digest.startswith("sha256:"),
        f"HTTP {plan['statusCode']} planId={plan_id or '-'} digest={plan_digest or '-'}",
    )
    return plan_id, plan_digest


def verify_lifecycle(gateway_url: str, timeout: int) -> dict[str, Any]:
    started = time.monotonic()
    checks: list[dict[str, Any]] = []
    identity = oc_identity(timeout)
    server = oc_server(timeout)
    token = oc_token(timeout)

    status = request_json("GET", f"{gateway_url}/v1/aiops/status", token, timeout=timeout)
    record_check(
        checks,
        "Gateway status accepts current OpenShift bearer token",
        status["statusCode"] == 200,
        f"HTTP {status['statusCode']}",
    )

    rejected_plan_id, rejected_digest = create_proposal_plan(
        gateway_url,
        token,
        "reject-first",
        timeout,
        checks,
    )
    rejection = request_json(
        "POST",
        f"{gateway_url}/v1/actions/rejections",
        token,
        payload={
            "planId": rejected_plan_id,
            "expectedPlanDigest": rejected_digest,
            "reason": "Live verifier rejects this plan to prove approval is blocked. No execution requested.",
        },
        timeout=timeout,
    )
    rejection_status = extract_decision_status(rejection)
    rejection_id = extract_metadata_name(rejection)
    record_check(
        checks,
        "rejection record created before approval",
        rejection["statusCode"] == 200 and rejection_status == "rejected" and rejection_id.startswith("rejection-"),
        f"HTTP {rejection['statusCode']} rejectionId={rejection_id or '-'} status={rejection_status or '-'}",
    )

    rejected_approval = request_json(
        "POST",
        f"{gateway_url}/v1/actions/approvals",
        token,
        payload={
            "planId": rejected_plan_id,
            "expectedPlanDigest": rejected_digest,
            "approvalScope": "single-target",
        },
        timeout=timeout,
    )
    rejected_detail = body_detail(rejected_approval)
    record_check(
        checks,
        "approval is blocked after rejection",
        rejected_approval["statusCode"] == 409 and "rejected" in rejected_detail.lower(),
        f"HTTP {rejected_approval['statusCode']} detail={rejected_detail}",
    )

    approved_plan_id, approved_digest = create_proposal_plan(
        gateway_url,
        token,
        "approve-first",
        timeout,
        checks,
    )
    approval = request_json(
        "POST",
        f"{gateway_url}/v1/actions/approvals",
        token,
        payload={
            "planId": approved_plan_id,
            "expectedPlanDigest": approved_digest,
            "approvalScope": "single-target",
        },
        timeout=timeout,
    )
    approval_status = extract_decision_status(approval)
    approval_id = extract_metadata_name(approval)
    record_check(
        checks,
        "approval record created without executing mutation",
        approval["statusCode"] == 200 and approval_status == "approved" and approval_id.startswith("approval-"),
        f"HTTP {approval['statusCode']} approvalId={approval_id or '-'} status={approval_status or '-'}",
    )

    stale_execute = request_json(
        "POST",
        f"{gateway_url}/v1/actions/execute",
        token,
        payload={
            "approvalId": approval_id,
            "planId": approved_plan_id,
            "expectedPlanDigest": "sha256:stale-live-verifier",
        },
        timeout=timeout,
    )
    stale_execute_detail = body_detail(stale_execute)
    record_check(
        checks,
        "execute is blocked for stale plan digest before mutation dispatch",
        stale_execute["statusCode"] == 409 and "stale" in stale_execute_detail.lower(),
        f"HTTP {stale_execute['statusCode']} detail={stale_execute_detail}",
    )

    rejected_execute = request_json(
        "POST",
        f"{gateway_url}/v1/actions/execute",
        token,
        payload={
            "approvalId": rejection_id,
            "planId": rejected_plan_id,
            "expectedPlanDigest": rejected_digest,
        },
        timeout=timeout,
    )
    rejected_execute_detail = body_detail(rejected_execute)
    record_check(
        checks,
        "execute is blocked for rejected decision before mutation dispatch",
        rejected_execute["statusCode"] == 409 and "not approved" in rejected_execute_detail.lower(),
        f"HTTP {rejected_execute['statusCode']} detail={rejected_execute_detail}",
    )

    approved_rejection = request_json(
        "POST",
        f"{gateway_url}/v1/actions/rejections",
        token,
        payload={
            "planId": approved_plan_id,
            "expectedPlanDigest": approved_digest,
            "reason": "Live verifier tries to reject after approval and expects a conflict.",
        },
        timeout=timeout,
    )
    approved_rejection_detail = body_detail(approved_rejection)
    record_check(
        checks,
        "rejection is blocked after active approval",
        approved_rejection["statusCode"] == 409 and "active approval" in approved_rejection_detail.lower(),
        f"HTTP {approved_rejection['statusCode']} detail={approved_rejection_detail}",
    )

    all_passed = all(check["passed"] for check in checks)
    return {
        "schemaVersion": "v1",
        "generatedAt": now_rfc3339(),
        "durationSeconds": round(time.monotonic() - started, 3),
        "gatewayUrl": gateway_url,
        "oc": {"identity": identity, "server": server},
        "git": {
            "branch": git_value(["branch", "--show-current"]),
            "commit": git_value(["rev-parse", "--short", "HEAD"]),
        },
        "mutationExecuted": False,
        "executeEndpointCalled": True,
        "executeEndpointOnlyRejectedRequests": True,
        "allPassed": all_passed,
        "checks": checks,
        "summary": {
            "passed": sum(1 for check in checks if check["passed"]),
            "failed": sum(1 for check in checks if not check["passed"]),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gateway-url", default=DEFAULT_GATEWAY_URL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    report_path = args.report
    if not report_path.is_absolute():
        report_path = REPO_ROOT / report_path

    try:
        report = verify_lifecycle(args.gateway_url.rstrip("/"), args.timeout)
    except Exception as exc:  # pragma: no cover - diagnostic CLI path
        report = {
            "schemaVersion": "v1",
            "generatedAt": now_rfc3339(),
            "gatewayUrl": args.gateway_url.rstrip("/"),
            "mutationExecuted": False,
            "executeEndpointCalled": False,
            "executeEndpointOnlyRejectedRequests": False,
            "allPassed": False,
            "fatalError": safe_error(exc),
            "checks": [],
            "summary": {"passed": 0, "failed": 1},
        }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    status = "PASS" if report.get("allPassed") else "FAIL"
    print(f"Live action lifecycle verification: {status}")
    for check in report.get("checks", []):
        marker = "PASS" if check.get("passed") else "FAIL"
        print(f"- [{marker}] {check.get('name')}: {check.get('detail')}")
    if report.get("fatalError"):
        print(f"fatalError: {report['fatalError']}")
    print(f"Report: {report_display_path(report_path)}")
    return 0 if report.get("allPassed") else 1


if __name__ == "__main__":
    sys.exit(main())
