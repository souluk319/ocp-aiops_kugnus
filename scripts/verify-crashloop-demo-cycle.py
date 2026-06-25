#!/usr/bin/env python3
"""Verify Ver.0.1.3 CrashLoopBackOff demo-cycle contract locally.

This verifier does not call OpenShift, Docker, the local gateway HTTP server,
or any LLM endpoint. It checks that the local source code can carry a selected
CrashLoopBackOff finding through the dashboard prompt bridge into RCA Context
metadata/scenarioContext while preserving read-only and redaction guardrails.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
GATEWAY_ROOT = REPO_ROOT / "komsco-ai-gateway"
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.3/crashloop-demo-cycle-verification.json"


def ensure_gateway_imports() -> None:
    gateway_path = str(GATEWAY_ROOT)
    if gateway_path not in sys.path:
        sys.path.insert(0, gateway_path)


def require(condition: bool, name: str, detail: str, checks: list[dict[str, Any]]) -> None:
    checks.append({"detail": detail, "name": name, "ok": condition})
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def read_source(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def git_value(args: list[str]) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def text_contains(path: str, needles: list[str]) -> dict[str, Any]:
    text = read_source(path)
    missing = [needle for needle in needles if needle not in text]
    return {
        "file": path,
        "missing": missing,
        "needles": needles,
        "ok": not missing,
    }


def build_demo_rca_context() -> dict[str, Any]:
    ensure_gateway_imports()
    from komsco_ai_gateway.aiops_contracts import build_rca_context  # pylint: disable=import-outside-toplevel

    page_context = {
        "aiopsDemoCycle": {
            "candidateId": "action-candidate-demo",
            "candidateStatusLabel": "제안만 함 / 실행 안 함",
            "findingId": "pod-crashloop-demo",
            "findingTitle": "CrashLoopBackOff: komsco-ai-dev/aiops-scenario-1-crashloop",
            "readOnlyOnly": True,
            "scenarioId": "crashloop",
            "selectedAt": "2026-06-25T00:00:00Z",
            "source": "aiops-dashboard-anomaly-board",
            "target": {
                "kind": "Pod",
                "name": "aiops-scenario-1-crashloop-abc",
                "namespace": "komsco-ai-dev",
            },
        },
        "pathname": "/dashboards",
    }
    return build_rca_context(
        message="다음 OpenShift 이상 징후를 read-only로 RCA 분석해줘.",
        tool_plan={
            "metadata": {"planner": "ver-0.1.3-demo-verifier"},
            "missing_evidence": [
                {
                    "reason": "pod-specific previous logs are not collected in the offline verifier",
                    "type": "pod_log",
                },
                {
                    "reason": "pod-specific warning events require live cluster read-only API access",
                    "type": "event",
                },
            ],
            "target": {
                "kind": "Pod",
                "name": "aiops-scenario-1-crashloop-abc",
                "namespace": "komsco-ai-dev",
            },
            "task_type": "pod_restart_rca",
            "tool_plan": [
                {
                    "adapter": "openshift",
                    "evidence_type": "pod_log",
                    "reason": "previous container logs are needed to confirm the app-level crash cause",
                    "step": 1,
                    "tool": "read_pod_logs_previous",
                },
                {
                    "adapter": "openshift",
                    "evidence_type": "event",
                    "reason": "events are needed to confirm CrashLoopBackOff/back-off timing",
                    "step": 2,
                    "tool": "read_pod_events",
                },
            ],
        },
        evidence_refs=[],
        page_context=page_context,
        run_id="ver-0.1.3-demo-run",
        incident_id="ver-0.1.3-demo-incident",
        phase="pre_answer",
    )


def verify_rca_context(checks: list[dict[str, Any]]) -> dict[str, Any]:
    context = build_demo_rca_context()
    metadata = context.get("metadata", {})
    question = context.get("question", {})
    scenario_context = question.get("scenarioContext", {})
    target = scenario_context.get("target", {})
    missing = context.get("evidence", {}).get("missing", [])

    require(
        metadata.get("findingId") == "pod-crashloop-demo",
        "rca_metadata_finding_id",
        "RCA Context metadata preserves selected findingId",
        checks,
    )
    require(
        metadata.get("scenarioId") == "crashloop",
        "rca_metadata_scenario_id",
        "RCA Context metadata preserves selected scenarioId",
        checks,
    )
    require(
        scenario_context.get("findingId") == "pod-crashloop-demo",
        "rca_question_scenario_context_finding_id",
        "question.scenarioContext preserves findingId",
        checks,
    )
    require(
        target.get("namespace") == "komsco-ai-dev",
        "rca_question_scenario_context_target",
        "question.scenarioContext preserves target namespace",
        checks,
    )
    require(
        any(item.get("type") == "pod_log" for item in missing)
        and any(item.get("type") == "event" for item in missing),
        "rca_missing_evidence_for_logs_and_events",
        "offline CrashLoop verifier exposes pod_log/event as missing evidence, not confirmed RCA",
        checks,
    )
    return context


def verify_source_wiring(checks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source_checks = [
        text_contains(
            "komsco-ai-console-plugin/src/pages/AiopsPages.tsx",
            [
                "data-aiops-demo-action=\"seed-chat-prompt\"",
                "crashLoopDemo && (",
                "readOnlyOnly: true",
                "safeEvidenceText(finding.evidence || finding.message",
                "findingId: finding.id",
                "scenarioId: isCrashLoopFinding(finding) ? 'crashloop'",
            ],
        ),
        text_contains(
            "komsco-ai-console-plugin/src/components/AssistantLauncher.tsx",
            [
                "draftPrompt?: AssistantDraftPrompt",
                "onRunComplete?: () => Promise<void> | void",
                "void onRunComplete?.()",
                "setExecutionMode('read-only')",
                "activeDraftPageContext?.readOnlyOnly === true ? 'read-only' : executionMode",
                "aiopsDemoCycle: activeDraftPageContext",
            ],
        ),
        text_contains(
            "komsco-ai-console-plugin/src/pages/AiopsPages.tsx",
            [
                "onRunComplete={data.refresh}",
                "data-aiops-demo-action=\"seed-chat-prompt\"",
            ],
        ),
        text_contains(
            "komsco-ai-gateway/komsco_ai_gateway/main.py",
            [
                '"aiopsDemoCycle"',
                "def normalize_aiops_demo_cycle_context",
                "AIOPS_DEMO_CYCLE_ALLOWED_KEYS",
                "AIOPS_DEMO_CYCLE_TARGET_ALLOWED_KEYS",
                "def build_crashloop_demo_answer_contract_text",
                "def crashloop_demo_prompt_answer_contract",
                '"answerContract": "crashloop-v0.1.3"',
            ],
        ),
        text_contains(
            "komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py",
            [
                '"findingId": demo_cycle_context.get("findingId")',
                '"scenarioId": demo_cycle_context.get("scenarioId")',
                '"scenarioContext": scenario_context',
            ],
        ),
    ]
    for item in source_checks:
        require(item["ok"], f"source_wiring:{item['file']}", f"missing={item['missing']}", checks)
    return source_checks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="JSON report path")
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    source_checks = verify_source_wiring(checks)
    rca_context = verify_rca_context(checks)
    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "kind": "CrashLoopDemoCycleVerification",
        "metadata": {
            "baseRef": git_value(["merge-base", "HEAD", "origin/main"])
            or git_value(["merge-base", "HEAD", "upstream/main"]),
            "branch": git_value(["branch", "--show-current"]),
            "headSha": git_value(["rev-parse", "HEAD"]),
            "name": "ver-0.1.3-crashloop-demo-cycle",
            "scope": "offline-contract-only",
        },
        "spec": {
            "checks": checks,
            "rcaContext": rca_context,
            "sourceChecks": source_checks,
        },
        "status": "pass" if all(item["ok"] for item in checks) else "fail",
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{report['status']}: wrote {report_path}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
