#!/usr/bin/env python3
"""Verify the official Evidence RCA demo scene contract.

Authoritative scenario:
docs/Ver.0.1.3/Evidence_RCA_Scene.md

This verifier is offline and read-only. It does not call OpenShift, Docker,
the local gateway HTTP server, or any LLM endpoint. It proves that the local
contract can represent the official demo flow:

1. Agentic Tool Plan: event_tool, grep_tool, metric_tool, snapshot_tool.
2. Evidence analysis: events, log patterns/digest, metrics, snapshot.
3. RCA Context: evidence, cause candidates, confidence, action candidates.
4. Lightspeed handoff/final answer: RCA, immediate action, prevention, evidence.
5. Safety: readOnlyOnly is authoritative and raw logs are not requested in the
   official demo answer contract.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ROOT = REPO_ROOT / "komsco-ai-gateway"
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.3/evidence-rca-scene-verification.json"
OFFICIAL_SCENE_DOC = REPO_ROOT / "docs/Ver.0.1.3/Evidence_RCA_Scene.md"
REQUIRED_TOOL_ALIASES = {"event_tool", "grep_tool", "metric_tool", "runbook_tool", "snapshot_tool"}
REQUIRED_EVIDENCE_TYPES = {"event", "pod_log", "metric", "runbook", "snapshot"}
REQUIRED_FINAL_SECTIONS = ["RCA", "즉시 조치", "재발 방지책", "참고 증적"]
RAW_LOG_COMMAND_RE = re.compile(r"(?im)^\s*oc\s+logs\b")
MUTATION_COMMAND_RE = re.compile(
    r"(?im)^\s*(?:oc|kubectl)\s+"
    r"(?:apply|delete|patch|scale|exec|replace|create|edit|set|adm\s+drain|rollout\s+restart)\b"
)


def ensure_gateway_imports() -> None:
    gateway_path = str(GATEWAY_ROOT)
    if gateway_path not in sys.path:
        sys.path.insert(0, gateway_path)


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def git_value(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def require(checks: list[dict[str, Any]], name: str, ok: bool, evidence: dict[str, Any]) -> None:
    checks.append({"evidence": evidence, "name": name, "ok": ok})
    if not ok:
        raise AssertionError(f"{name}: {evidence}")


def evidence_ref(
    evidence_type: str,
    *,
    digest_suffix: str,
    summary: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "collectedAt": "2026-06-25T00:00:00Z",
        "contentDigest": f"sha256:official-{digest_suffix}",
        "evidenceId": f"official-{digest_suffix}",
        "evidenceType": evidence_type,
        "eventName": f"official_{evidence_type}_evidence",
        "eventStatus": "success",
        "sourceType": "gateway-official-scene-fixture",
        "summary": summary,
    }
    if extra:
        payload.update(extra)
    return payload


def build_official_context() -> dict[str, Any]:
    ensure_gateway_imports()
    from komsco_ai_gateway.aiops_contracts import (  # pylint: disable=import-outside-toplevel
        build_rca_context,
        build_runtime_tool_plan,
    )

    question = "어제 새벽에 default namespace Pod가 왜 재시작됐어?"
    unscoped_plan = build_runtime_tool_plan(question, execution_mode="read-only")
    page_context = {
        "namespace": "default",
        "resourceKind": "Pod",
        "resourceName": "sample-restart-pod",
        "pathname": "/k8s/ns/default/pods/sample-restart-pod",
        "aiopsDemoCycle": {
            "findingId": "official-evidence-rca-default-pod-restart",
            "findingTitle": "default namespace Pod restart RCA",
            "readOnlyOnly": True,
            "scenarioId": "evidence-rca-scene",
            "selectedAt": "2026-06-25T00:00:00Z",
            "source": "official-evidence-rca-scene",
            "target": {
                "kind": "Pod",
                "name": "sample-restart-pod",
                "namespace": "default",
            },
        },
    }
    plan = build_runtime_tool_plan(question, page_context=page_context, execution_mode="unrestricted")
    refs = [
        evidence_ref(
            "event",
            digest_suffix="event-tool",
            summary="event_tool: restart window events include BackOff/Killing/OOMKilled candidates",
        ),
        evidence_ref(
            "pod_log",
            digest_suffix="grep-tool",
            summary="grep_tool: raw logs withheld; pattern counts extracted for OOMKilled, Exception, Back-off",
            extra={
                "lineCount": 0,
                "matchedPatternIds": ["OOMKilled", "Exception", "Back-off"],
                "patternCounts": {"Back-off": 1, "Exception": 0, "OOMKilled": 1},
                "rawLogDisclosure": False,
            },
        ),
        evidence_ref(
            "metric",
            digest_suffix="metric-tool",
            summary="metric_tool: CPU, memory, node pressure, restart trend evidence collected",
        ),
        evidence_ref(
            "snapshot",
            digest_suffix="snapshot-tool",
            summary="snapshot_tool: Pod status snapshot includes restartCount, lastState, container state",
        ),
        evidence_ref(
            "runbook",
            digest_suffix="runbook-tool",
            summary="runbook_tool: pgvector/RAG runbook evidence retrieved for RCA action candidates and prevention guidance",
            extra={
                "sourcePath": "upload://user-upload:official-runbook/pod-restart-rca.md#chunk-0",
                "sourceType": "gateway-rag-runbook-search",
            },
        ),
    ]
    context = build_rca_context(
        message=question,
        tool_plan=plan,
        evidence_refs=refs,
        page_context=page_context,
        run_id="official-evidence-rca-run",
        incident_id="official-evidence-rca-incident",
        phase="official_scene_verifier",
    )
    return {
        "context": context,
        "pageContext": page_context,
        "plan": plan,
        "question": question,
        "unscopedPlan": unscoped_plan,
    }


def verify_official_scene_doc(checks: list[dict[str, Any]]) -> None:
    text = OFFICIAL_SCENE_DOC.read_text(encoding="utf-8")
    required = [
        "Evidence 기반 AI 장애 분석 시나리오",
        "어제 새벽에 default namespace Pod가 왜 재시작됐어?",
        "event_tool",
        "grep_tool",
        "metric_tool",
        "snapshot_tool",
        "RCA Context JSON",
        "OpenShift Lightspeed",
    ]
    missing = [item for item in required if item not in text]
    require(checks, "official_scene_doc_present", not missing, {"missing": missing})


def verify_plan_and_context(checks: list[dict[str, Any]], payload: dict[str, Any]) -> None:
    plan = payload["plan"]
    unscoped_plan = payload["unscopedPlan"]
    context = payload["context"]
    steps = plan.get("tool_plan") if isinstance(plan.get("tool_plan"), list) else []
    aliases = {str(step.get("official_tool")) for step in steps if step.get("official_tool")}
    tools = {str(step.get("tool")) for step in steps if step.get("tool")}
    evidence_types = {str(step.get("evidence_type")) for step in steps if step.get("evidence_type")}
    official_scene = context.get("officialScene") if isinstance(context.get("officialScene"), dict) else {}
    refs = context.get("evidence", {}).get("collectedRefs", [])
    missing = context.get("evidence", {}).get("missing", [])
    collected_types = {str(ref.get("type")) for ref in refs if isinstance(ref, dict)}
    missing_types = {str(item.get("type")) for item in missing if isinstance(item, dict)}

    require(
        checks,
        "official_question_parses_default_namespace_without_page_context",
        unscoped_plan.get("target", {}).get("namespace") == "default",
        {"target": unscoped_plan.get("target"), "question": payload["question"]},
    )
    require(
        checks,
        "official_tool_aliases_present",
        REQUIRED_TOOL_ALIASES <= aliases,
        {"actualAliases": sorted(aliases), "requiredAliases": sorted(REQUIRED_TOOL_ALIASES), "tools": sorted(tools)},
    )
    require(
        checks,
        "official_evidence_types_planned",
        REQUIRED_EVIDENCE_TYPES <= evidence_types,
        {"actualEvidenceTypes": sorted(evidence_types), "requiredEvidenceTypes": sorted(REQUIRED_EVIDENCE_TYPES)},
    )
    require(
        checks,
        "official_evidence_types_collected_in_context",
        REQUIRED_EVIDENCE_TYPES <= collected_types,
        {"collectedTypes": sorted(collected_types)},
    )
    require(
        checks,
        "official_required_evidence_not_missing_in_context",
        not (REQUIRED_EVIDENCE_TYPES & missing_types),
        {"missingTypes": sorted(missing_types), "requiredEvidenceTypes": sorted(REQUIRED_EVIDENCE_TYPES)},
    )
    require(
        checks,
        "official_scene_embedded_in_rca_context",
        official_scene.get("name") == "Evidence 기반 AI 장애 분석 시나리오"
        and set(official_scene.get("requiredToolAliases", [])) == REQUIRED_TOOL_ALIASES,
        {"officialScene": official_scene},
    )
    require(
        checks,
        "rca_context_structures_cause_confidence_action",
        isinstance(context.get("causeCandidates"), list)
        and len(context["causeCandidates"]) >= 3
        and isinstance(context.get("actionCandidates"), list)
        and len(context["actionCandidates"]) >= 2
        and isinstance(context.get("confidence"), dict),
        {
            "actionCandidateCount": len(context.get("actionCandidates", [])),
            "causeCandidateCount": len(context.get("causeCandidates", [])),
            "confidence": context.get("confidence"),
        },
    )
    pod_log_refs = [
        ref
        for ref in refs
        if isinstance(ref, dict) and ref.get("type") == "pod_log"
    ]
    require(
        checks,
        "pod_log_is_pattern_digest_not_raw_text",
        bool(pod_log_refs)
        and all(ref.get("rawLogDisclosure") is False for ref in pod_log_refs)
        and all(ref.get("contentDigest") for ref in pod_log_refs)
        and all(ref.get("matchedPatternIds") for ref in pod_log_refs),
        {"podLogRefs": pod_log_refs},
    )


def verify_server_side_readonly_and_answer_contract(
    checks: list[dict[str, Any]],
    payload: dict[str, Any],
) -> None:
    ensure_gateway_imports()
    from komsco_ai_gateway.main import (  # pylint: disable=import-outside-toplevel
        ChatRequest,
        build_crashloop_demo_answer_contract_text,
        crashloop_demo_prompt_answer_contract,
        page_context_aiops_execution_mode,
    )

    request = ChatRequest(
        message=payload["question"],
        pageContext={
            **payload["pageContext"],
            "aiopsExecutionMode": "unrestricted",
        },
    )
    mode = page_context_aiops_execution_mode(request)
    prompt_contract = crashloop_demo_prompt_answer_contract(request)
    answer_contract = build_crashloop_demo_answer_contract_text(request, "official-evidence-rca-run")
    final_sections_present = all(section in prompt_contract + answer_contract for section in REQUIRED_FINAL_SECTIONS)
    raw_log_command_present = bool(RAW_LOG_COMMAND_RE.search(prompt_contract) or RAW_LOG_COMMAND_RE.search(answer_contract))
    mutation_command_present = bool(
        MUTATION_COMMAND_RE.search(prompt_contract) or MUTATION_COMMAND_RE.search(answer_contract)
    )

    require(
        checks,
        "server_forces_readonly_for_readonly_demo_context",
        mode == "read-only",
        {"mode": mode, "submittedMode": "unrestricted"},
    )
    require(
        checks,
        "official_final_answer_sections_present",
        final_sections_present,
        {"requiredSections": REQUIRED_FINAL_SECTIONS},
    )
    require(
        checks,
        "official_answer_contract_has_no_raw_log_dump_command",
        not raw_log_command_present,
        {"rawLogCommandPattern": RAW_LOG_COMMAND_RE.pattern},
    )
    require(
        checks,
        "official_answer_contract_has_no_mutation_command",
        not mutation_command_present,
        {"mutationCommandPattern": MUTATION_COMMAND_RE.pattern},
    )


def verify_runtime_snapshot_collector_source(checks: list[dict[str, Any]]) -> None:
    gateway_source = (GATEWAY_ROOT / "komsco_ai_gateway/main.py").read_text(encoding="utf-8")
    required_tokens = [
        '"evidenceType": "snapshot"',
        '"name": "pod_snapshot_evidence"',
        '"name": "crashloop_pod_snapshot"',
        '"name": "official_namespace_restart_event_evidence"',
        '"name": "official_namespace_restart_log_pattern_probe"',
        '"name": "official_namespace_restart_snapshot"',
    ]
    missing = [token for token in required_tokens if token not in gateway_source]
    require(
        checks,
        "runtime_snapshot_evidence_collector_wired",
        not missing,
        {"missingSourceTokens": missing, "source": "komsco-ai-gateway/komsco_ai_gateway/main.py"},
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="JSON report path")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    verify_official_scene_doc(checks)
    payload = build_official_context()
    verify_plan_and_context(checks, payload)
    verify_server_side_readonly_and_answer_contract(checks, payload)
    verify_runtime_snapshot_collector_source(checks)

    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "generatedAt": now_rfc3339(),
        "kind": "EvidenceRcaSceneVerification",
        "metadata": {
            "baseRef": git_value(["merge-base", "HEAD", "origin/main"])
            or git_value(["merge-base", "HEAD", "upstream/main"]),
            "branch": git_value(["branch", "--show-current"]),
            "headSha": git_value(["rev-parse", "HEAD"]),
            "name": "ver-0.1.3-official-evidence-rca-scene",
            "source": str(OFFICIAL_SCENE_DOC.relative_to(REPO_ROOT)),
        },
        "spec": {
            "checks": checks,
            "officialQuestion": payload["question"],
            "rcaContextDigest": payload["context"].get("metadata", {}).get("digest"),
            "toolAliases": sorted(
                {
                    str(step.get("official_tool"))
                    for step in payload["plan"].get("tool_plan", [])
                    if step.get("official_tool")
                }
            ),
        },
        "status": "pass" if all(check["ok"] for check in checks) else "fail",
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: wrote {report_path}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
