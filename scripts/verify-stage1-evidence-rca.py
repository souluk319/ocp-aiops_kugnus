#!/usr/bin/env python3
"""Verify Ver.0.1.1 Stage 1 evidence/RCA context contract locally.

This script does not call OpenShift, Docker, the local gateway HTTP server, or
any LLM endpoint. It builds deterministic payloads from the gateway contract
helpers, checks source wiring statically, and writes a JSON evidence artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ROOT = REPO_ROOT / "komsco-ai-gateway"
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.1/stage-1-evidence-rca-context-verification.json"


def ensure_gateway_imports() -> None:
    gateway_path = str(GATEWAY_ROOT)
    if gateway_path not in sys.path:
        sys.path.insert(0, gateway_path)


def require(condition: bool, name: str, detail: str, checks: list[dict[str, Any]]) -> None:
    checks.append({"name": name, "ok": condition, "detail": detail})
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def text_contains(path: Path, needles: list[str]) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    missing = [needle for needle in needles if needle not in text]
    return {
        "file": str(path.relative_to(REPO_ROOT)).replace("\\", "/"),
        "ok": not missing,
        "missing": missing,
        "needles": needles,
    }


def build_stage1_payloads() -> dict[str, Any]:
    ensure_gateway_imports()
    from komsco_ai_gateway.aiops_contracts import (  # pylint: disable=import-outside-toplevel
        build_rca_context,
        build_runtime_safety_contract,
        build_runtime_tool_plan,
    )
    from komsco_ai_gateway.security import build_evidence_reference  # pylint: disable=import-outside-toplevel

    run_id = "stage1-verification-run"
    incident_id = "inc-stage1-verification"
    message = "why did the pod restart in default namespace?"
    tool_plan = build_runtime_tool_plan(message)
    tool_result_event = {
        "type": "tool_result",
        "name": "pod_status_evidence",
        "status": "success",
        "summary": "Pod restart evidence collected from Kubernetes API.",
        "detail": "restartCount=3; lastState=terminated/OOMKilled; namespace=default",
    }
    evidence_ref = build_evidence_reference(
        event=tool_result_event,
        incident_id=incident_id,
        run_id=run_id,
        source_type="gateway-preflight-evidence",
        subject={"username": "stage1@example.com", "groups": ["stage1-reviewer"]},
    )
    evidence_ref_event = {
        "type": "tool_result",
        "name": "evidence_ref",
        "status": "success",
        "summary": f"{evidence_ref['evidenceId']} recorded",
        "result": evidence_ref,
    }
    rca_context = build_rca_context(
        message=message,
        tool_plan=tool_plan,
        evidence_refs=[evidence_ref],
        run_id=run_id,
        incident_id=incident_id,
        phase="post_answer",
    )
    safety_contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
        latest_runtime_tool_plan=tool_plan,
        latest_rca_context=rca_context,
    )
    rca_context_event = {
        "type": "rca_context",
        "phase": "post_answer",
        "context": rca_context,
        "safetyContract": safety_contract,
    }

    missing_plan = build_runtime_tool_plan("check clusteroperator status")
    missing_context = build_rca_context(
        message="check clusteroperator status",
        tool_plan=missing_plan,
        evidence_refs=[],
        run_id="stage1-missing-verification-run",
        incident_id="inc-stage1-missing-verification",
        phase="pre_answer",
    )
    missing_rca_context_event = {
        "type": "rca_context",
        "phase": "pre_answer",
        "context": missing_context,
    }

    return {
        "evidenceRefEvent": evidence_ref_event,
        "rcaContextEvent": rca_context_event,
        "missingRcaContextEvent": missing_rca_context_event,
        "toolPlan": tool_plan,
    }


def verify_payloads(payloads: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    evidence_ref = payloads["evidenceRefEvent"]["result"]
    context = payloads["rcaContextEvent"]["context"]
    missing_context = payloads["missingRcaContextEvent"]["context"]
    safety = payloads["rcaContextEvent"]["safetyContract"]

    require(payloads["evidenceRefEvent"]["name"] == "evidence_ref", "evidence_ref_event_name", "stream event name is evidence_ref", checks)
    require(evidence_ref["schemaVersion"] == "v1", "evidence_record_schema", "EvidenceRecord schemaVersion is v1", checks)
    require(bool(evidence_ref["evidenceId"]), "evidence_record_id", "EvidenceRecord has evidenceId", checks)
    require(bool(evidence_ref["contentDigest"]), "evidence_record_digest", "EvidenceRecord has contentDigest", checks)
    require(context["kind"] == "RcaContext", "rca_context_kind", "RcaContext kind is present", checks)
    require(bool(context["metadata"]["contextId"]), "rca_context_id", "RcaContext metadata.contextId is present", checks)
    require(bool(context["metadata"]["digest"]), "rca_context_digest", "RcaContext metadata.digest is present", checks)
    require(
        context["evidence_refs"][0]["evidenceId"] == evidence_ref["evidenceId"],
        "evidence_ref_linked_to_rca_context",
        "evidence_ref evidenceId is linked in rca_context.evidence_refs",
        checks,
    )
    require(
        context["evidence"]["collectedRefs"][0]["contentDigest"] == evidence_ref["contentDigest"],
        "collected_ref_digest_linked",
        "collectedRefs contentDigest matches evidence_ref contentDigest",
        checks,
    )
    require(context["confidence"]["level"] == "evidence_based", "evidence_based_confidence", "collected evidence sets evidence_based confidence", checks)
    require(
        missing_context["confidence"]["level"] == "insufficient_evidence",
        "missing_evidence_confidence",
        "missing evidence sets insufficient_evidence confidence",
        checks,
    )
    require(bool(missing_context["evidence"]["missing"]), "missing_evidence_list", "missing evidence list is populated", checks)
    require(
        any(item["type"] == "openshift" and item["status"] == "collected" for item in safety["evidenceStatus"]),
        "safety_contract_collected_status",
        "safety contract exposes collected OpenShift evidence",
        checks,
    )
    require(
        any(item["type"] == "metric" and item["status"] == "missing" for item in safety["evidenceStatus"]),
        "safety_contract_missing_status",
        "safety contract separates missing metric evidence",
        checks,
    )
    return checks


def verify_source_wiring() -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    source_checks = [
        text_contains(
            REPO_ROOT / "komsco-ai-gateway/komsco_ai_gateway/main.py",
            [
                "def build_evidence_reference_events",
                '"name": "evidence_ref"',
                "def build_rca_context_stream_event",
                '"type": "rca_context"',
                "yield sse(evidence_event)",
                "yield sse(rca_context_event)",
            ],
        ),
        text_contains(
            REPO_ROOT / "komsco-ai-console-plugin/src/components/AssistantLauncher.tsx",
            [
                "evidenceFooter",
                "event.type === 'rca_context'",
                "collectedRefs",
                "missing",
                "수집 {footer.collectedCount}",
                "추가 확인 {footer.missingCount}",
            ],
        ),
        text_contains(
            REPO_ROOT / "komsco-ai-console-plugin/src/components/assistant.css",
            [
                ".komsco-ai__evidence-footer",
                ".komsco-ai__evidence-pill--collected",
                ".komsco-ai__evidence-pill--missing",
                ".komsco-ai__evidence-missing",
            ],
        ),
    ]
    for item in source_checks:
        require(item["ok"], f"source_wiring:{item['file']}", f"missing={item['missing']}", checks)
    return checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="JSON report path")
    args = parser.parse_args()

    payloads = build_stage1_payloads()
    checks = verify_payloads(payloads)
    checks.extend(verify_source_wiring())

    report = {
        "schemaVersion": "stage1-evidence-rca-verification/v1",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "sampleEvents": {
            "evidenceRefEvent": payloads["evidenceRefEvent"],
            "rcaContextEvent": payloads["rcaContextEvent"],
            "missingRcaContextEvent": payloads["missingRcaContextEvent"],
        },
        "boundaries": {
            "officialOcpWrites": False,
            "usesLocalHttpServer": False,
            "usesLlmEndpoint": False,
            "usesKubeconfig": False,
        },
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"PASS stage1 evidence/RCA verification: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
