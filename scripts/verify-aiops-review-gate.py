#!/usr/bin/env python3
"""Run the compact offline Ver.0.1.9 AIOps review gate."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.9/aiops-review-gate-report.json"

GATEWAY_TEST_FILTER = (
    "runtime_tool_plan or rca_context or action_candidates or "
    "execute_mode_action_plan_response_has_post_answer_rca or "
    "chat_action_plan_can_continue_through_standard_approval_api or "
    "unrestricted_executes_natural_scale_action or "
    "execute_action_request_emits_plan_and_post_answer_rca_context or "
    "read_only_action_request_skips_plan_and_emits_post_answer_rca_context"
)


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def rel(path: Path) -> str:
    return str(path.relative_to(REPO_ROOT)).replace("\\", "/")


def run_check(name: str, reviewer: str, cmd: list[str], *, cwd: Path = REPO_ROOT) -> dict[str, Any]:
    started = now_rfc3339()
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return {
        "name": name,
        "reviewer": reviewer,
        "ok": result.returncode == 0,
        "command": " ".join(cmd),
        "cwd": rel(cwd),
        "startedAt": started,
        "returnCode": result.returncode,
        "stdoutPreview": result.stdout[-1600:],
        "stderrPreview": result.stderr[-1600:],
    }


def static_hygiene_check() -> dict[str, Any]:
    new_paths = [
        REPO_ROOT / "docs/Ver.0.2.0/komsco-aiops-agent-brief.html",
        REPO_ROOT / "docs/Ver.0.2.0/시스템아이디어.html",
        REPO_ROOT / "docs/Ver.0.2.0/시스템아이디어.md",
    ]
    protected_existing_paths = [
        REPO_ROOT / "docs/Ver.0.1.9/komsco-aiops-agent-brief.html",
        REPO_ROOT / "docs/Ver.0.1.9/시스템아이디어.html",
        REPO_ROOT / "docs/Ver.0.1.9/시스템아이디어.md",
    ]
    ignored = [
        REPO_ROOT / "docs/Ver.0.1.9/JK_AIOps.png",
        REPO_ROOT / "docs/Ver.0.1.9/KJK_-_AIOps_Semina_slides_01-10.pdf",
    ]
    ignore_results = {
        rel(path): subprocess.run(
            ["git", "check-ignore", "-q", str(path.relative_to(REPO_ROOT))],
            cwd=REPO_ROOT,
        ).returncode
        == 0
        for path in ignored
    }
    stale_memory_ref = "docs/Ver.0.1.9/memory-cards.seed.json" in (
        REPO_ROOT / "docs/Ver.0.2.0/시스템아이디어.md"
    ).read_text(encoding="utf-8")
    ok = (
        all(path.exists() for path in protected_existing_paths)
        and all(path.exists() for path in new_paths)
        and all(ignore_results.values())
        and not stale_memory_ref
    )
    return {
        "name": "0.1.9 document preservation and ignored references",
        "reviewer": "deploy-safety-reviewer",
        "ok": ok,
        "newCopiesPresent": [rel(path) for path in new_paths if path.exists()],
        "protectedExistingPathsPresent": [rel(path) for path in protected_existing_paths if path.exists()],
        "ignoredReferences": ignore_results,
        "staleMemoryCardPathReference": stale_memory_ref,
    }


def static_console_action_button_check() -> dict[str, Any]:
    assistant = (REPO_ROOT / "komsco-ai-console-plugin/src/components/AssistantLauncher.tsx").read_text(
        encoding="utf-8"
    )
    action_buttons = (
        REPO_ROOT / "komsco-ai-console-plugin/src/components/AssistantCreateActionPlanButtons.tsx"
    ).read_text(encoding="utf-8")
    action_records = (
        REPO_ROOT / "komsco-ai-console-plugin/src/components/AssistantActionRecords.tsx"
    ).read_text(encoding="utf-8")
    action_flow_verifier = (REPO_ROOT / "scripts/verify-v029-chatbot-action-history-flow.cjs").read_text(
        encoding="utf-8"
    )
    gateway = (REPO_ROOT / "komsco-ai-console-plugin/src/services/aiGateway.ts").read_text(encoding="utf-8")
    verifier = (REPO_ROOT / "scripts/verify-kugnus-ui.mjs").read_text(encoding="utf-8")
    implementation = "\n".join([assistant, action_buttons, action_records, action_flow_verifier, gateway])
    needles = {
        "answer action container": "data-komsco-answer-action-buttons",
        "candidate create button": "komsco-ai__create-action-plan-button",
        "candidate collapsed group": "data-aiops-action-candidates-expanded",
        "create-plan step": "'create-plan'",
        "approve-plan step": "'approve-plan'",
        "reject-plan step": "'reject-plan'",
        "execute-approval step": "'execute-approval'",
        "action control buttons": "komsco-ai__answer-action-controls",
        "action lifecycle stage": "data-action-lifecycle-stage",
        "action button step marker": "data-answer-action-step",
        "approve API": "approveActionPlan",
        "reject API": "rejectActionPlan",
        "execute API": "executeApprovedAction",
        "browser action flow report": "V029ChatbotActionHistoryFlowVerification",
    }
    missing = [name for name, needle in needles.items() if needle not in implementation]
    verifier_needles = [
        "actionLifecycleText",
        "Proposal:",
        "Plan:",
        "승인",
        "거절",
        "실행",
    ]
    missing_verifier = [needle for needle in verifier_needles if needle not in verifier]
    return {
        "name": "Console action approval button wiring",
        "reviewer": "console-ux-reviewer",
        "ok": not missing and not missing_verifier,
        "contract": "v0.2.9 answer action records + collapsed candidate group + browser action flow report",
        "missingImplementationMarkers": missing,
        "missingVerifierMarkers": missing_verifier,
    }


def taskfile_safety_check() -> dict[str, Any]:
    taskfile = (REPO_ROOT / "Taskfile.yml").read_text(encoding="utf-8")
    needles = [
        "KOMSCO_AIOPS_APPROVE_RUNTIME_APPLY=cywell-aiops",
        "kugnus:aiops:live-verify",
        "python3 scripts/verify-aiops-review-gate.py",
    ]
    missing = [needle for needle in needles if needle not in taskfile]
    return {
        "name": "Taskfile offline/live split and runtime apply approval gate",
        "reviewer": "deploy-safety-reviewer",
        "ok": not missing,
        "missing": missing,
    }


def replacement_char_check() -> dict[str, Any]:
    paths = [
        REPO_ROOT / "komsco-ai-gateway/komsco_ai_gateway/main.py",
        REPO_ROOT / "komsco-ai-gateway/tests/test_health.py",
        REPO_ROOT / "scripts/verify-aiops-review-gate.py",
        REPO_ROOT / "docs/Ver.0.1.9/aiops-recovery-verification.md",
    ]
    counts = {rel(path): path.read_text(encoding="utf-8").count("\ufffd") for path in paths}
    return {
        "name": "UTF-8 replacement character guard",
        "reviewer": "deploy-safety-reviewer",
        "ok": all(count == 0 for count in counts.values()),
        "replacementCharCounts": counts,
    }


def check_by_name(checks: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(check["name"]): check for check in checks}


def load_json_report(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def build_requirement_summary(
    checks: list[dict[str, Any]],
    reviewer_summary: dict[str, dict[str, int]],
) -> list[dict[str, Any]]:
    by_name = check_by_name(checks)

    def passed(names: list[str]) -> bool:
        return all(by_name.get(name, {}).get("ok") is True for name in names)

    return [
        {
            "id": "three-review-agents",
            "title": "검수 에이전트 세 개 역할",
            "ok": len(reviewer_summary) >= 3 and all(summary["failed"] == 0 for summary in reviewer_summary.values()),
            "evidence": sorted(reviewer_summary),
        },
        {
            "id": "at-least-five-review-passes",
            "title": "검수 최소 5회 이상",
            "ok": sum(1 for check in checks if check["ok"]) >= 5,
            "evidence": {"passedChecks": sum(1 for check in checks if check["ok"])},
        },
        {
            "id": "aiops-answer-has-remediation-capability",
            "title": "챗봇 답변에 문제 해결 AIOps 기능 포함",
            "ok": passed(["Gateway ToolPlan/RCA/action contract tests", "AIOps answer experience contract"]),
            "evidence": [
                "execute_mode_action_plan_response_has_post_answer_rca",
                "chat_action_plan_can_continue_through_standard_approval_api",
                "unrestricted_executes_natural_scale_action",
                "execute_action_request_emits_plan_and_post_answer_rca_context",
                "read_only_action_request_skips_plan_and_emits_post_answer_rca_context",
                "default answer hides raw ToolPlan JSON; detail/audit views keep the right projection",
            ],
        },
        {
            "id": "console-shows-action-workflow",
            "title": "콘솔이 조치 후보/승인/거절/실행 흐름을 표시",
            "ok": passed(["Console typecheck", "Console verifier syntax", "Console action approval button wiring"]),
            "evidence": [
                "create-plan",
                "approve-plan",
                "reject-plan",
                "execute-approval",
                "actionLifecycleText",
            ],
        },
        {
            "id": "deployable-package-and-safe-ops",
            "title": "배포 패키징과 운영 안전 게이트",
            "ok": passed(
                [
                    "0.1.9 document preservation and ignored references",
                    "Taskfile offline/live split and runtime apply approval gate",
                    "OLM package",
                    "Diff whitespace",
                ]
            ),
            "evidence": [
                "ignored PDF/PNG references",
                "company runtime apply approval gate",
                "cywell-aiops-operator.v0.1.10",
            ],
        },
    ]


def live_verification_status() -> dict[str, Any]:
    vpn_report_path = REPO_ROOT / ".tmp-kugnus-demo/ocp-vpn-route-report.json"
    ui_report_path = REPO_ROOT / "docs/Ver.0.1.5/ui-verifier-report.json"
    runtime_report_path = REPO_ROOT / "docs/Ver.0.1.6/runtime-smoke-report.json"
    actions_report_path = REPO_ROOT / "docs/Ver.0.1.5/live-action-lifecycle-verification.json"
    lightspeed_report_path = REPO_ROOT / "docs/Ver.0.1.5/live-lightspeed-final-response-verification.json"
    status: dict[str, Any] = {
        "status": "not_proven",
        "preflightCommand": "task kugnus:vpn:doctor",
        "liveGateCommand": "task kugnus:aiops:live-verify",
        "report": rel(vpn_report_path),
    }

    vpn_report = load_json_report(vpn_report_path)
    summary = vpn_report.get("summary") if isinstance(vpn_report.get("summary"), dict) else {}
    interpretation = (
        vpn_report.get("interpretation") if isinstance(vpn_report.get("interpretation"), dict) else {}
    )

    ui_report = load_json_report(ui_report_path)
    runtime_report = load_json_report(runtime_report_path)
    actions_report = load_json_report(actions_report_path)
    lightspeed_report = load_json_report(lightspeed_report_path)

    runtime_checks = runtime_report.get("checks") if isinstance(runtime_report.get("checks"), list) else []
    runtime_rag = next(
        (
            check.get("summary", {})
            for check in runtime_checks
            if isinstance(check, dict) and check.get("name") == "rag-search-contract"
        ),
        {},
    )
    runtime_rag_backend = runtime_rag.get("backend") if isinstance(runtime_rag.get("backend"), dict) else {}
    actions_checks = actions_report.get("checks") if isinstance(actions_report.get("checks"), list) else []
    lightspeed_cases = lightspeed_report.get("cases") if isinstance(lightspeed_report.get("cases"), list) else []

    live_reports = {
        "vpn": bool(summary.get("readyForStrictLightspeedGate")),
        "ui": ui_report.get("ok") is True and not ui_report.get("failed"),
        "runtime": runtime_report.get("result") == "pass",
        "rag": runtime_rag.get("status") == "collected"
        and runtime_rag.get("resultCount", 0) >= 1
        and runtime_rag_backend.get("endpointConfigured") is True,
        "actions": bool(actions_checks) and all(check.get("passed") is True for check in actions_checks),
        "lightspeed": lightspeed_report.get("allSucceeded") is True
        and all(
            case.get("ok") is True
            and len(case.get("stream", {}).get("fallbackEvents", [])) == 0
            and case.get("lightspeedStatus", {}).get("streamProbe") == "succeeded"
            and case.get("lightspeedStatus", {}).get("fallbackActive") is False
            for case in lightspeed_cases
        ),
    }
    proven = all(live_reports.values())
    return {
        **status,
        "status": "proven" if proven else "not_proven",
        "readyForStrictLightspeedGate": bool(summary.get("readyForStrictLightspeedGate")),
        "firstFailingLayer": summary.get("firstFailingLayer"),
        "likelyCause": interpretation.get("likelyCause"),
        "notCodeBlocker": bool(interpretation.get("notCodeBlocker")),
        "reports": {
            "ui": rel(ui_report_path),
            "runtime": rel(runtime_report_path),
            "actions": rel(actions_report_path),
            "lightspeed": rel(lightspeed_report_path),
        },
        "liveReports": live_reports,
        "ui": {
            "ok": ui_report.get("ok"),
            "checked": ui_report.get("checked"),
            "failed": ui_report.get("failed", []),
        },
        "runtime": {
            "result": runtime_report.get("result"),
            "ragStatus": runtime_rag.get("status"),
            "ragResultCount": runtime_rag.get("resultCount"),
            "ragEndpointConfigured": runtime_rag_backend.get("endpointConfigured"),
        },
        "actions": {
            "generatedAt": actions_report.get("generatedAt"),
            "passedChecks": sum(1 for check in actions_checks if check.get("passed") is True),
            "failedChecks": [check.get("name") for check in actions_checks if check.get("passed") is not True],
        },
        "lightspeed": {
            "allSucceeded": lightspeed_report.get("allSucceeded"),
            "generatedAt": lightspeed_report.get("generatedAt"),
            "cases": [
                {
                    "caseId": case.get("caseId"),
                    "ok": case.get("ok"),
                    "olsTextEvents": case.get("stream", {}).get("olsTextEvents"),
                    "fallbackEvents": len(case.get("stream", {}).get("fallbackEvents", [])),
                    "streamProbe": case.get("lightspeedStatus", {}).get("streamProbe"),
                    "fallbackActive": case.get("lightspeedStatus", {}).get("fallbackActive"),
                }
                for case in lightspeed_cases
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    checks: list[dict[str, Any]] = [
        run_check(
            "Gateway syntax",
            "gateway-execution-reviewer",
            [
                "python3",
                "-m",
                "py_compile",
                "komsco-ai-gateway/komsco_ai_gateway/main.py",
                "komsco-ai-gateway/tests/test_health.py",
            ],
        ),
        run_check(
            "Gateway ToolPlan/RCA/action contract tests",
            "gateway-execution-reviewer",
            [
                "komsco-ai-gateway/.venv/bin/python",
                "-m",
                "pytest",
                "komsco-ai-gateway/tests/test_health.py",
                "-q",
                "-k",
                GATEWAY_TEST_FILTER,
            ],
        ),
        run_check(
            "AIOps answer experience contract",
            "gateway-execution-reviewer",
            ["python3", "scripts/verify-aiops-answer-experience.py"],
        ),
        run_check(
            "Console typecheck",
            "console-ux-reviewer",
            ["./node_modules/.bin/tsc", "--noEmit"],
            cwd=REPO_ROOT / "komsco-ai-console-plugin",
        ),
        run_check(
            "Console verifier syntax",
            "console-ux-reviewer",
            ["node", "--check", "scripts/verify-kugnus-ui.mjs"],
        ),
        static_console_action_button_check(),
        static_hygiene_check(),
        taskfile_safety_check(),
        replacement_char_check(),
        run_check("Scenario contract", "gateway-execution-reviewer", ["task", "kugnus:scenario:verify"]),
        run_check("OLM package", "deploy-safety-reviewer", ["task", "kugnus:package"]),
        run_check("Diff whitespace", "deploy-safety-reviewer", ["git", "diff", "--check"]),
    ]

    reviewer_summary: dict[str, dict[str, int]] = {}
    for check in checks:
        summary = reviewer_summary.setdefault(str(check["reviewer"]), {"passed": 0, "failed": 0})
        summary["passed" if check["ok"] else "failed"] += 1

    requirements = build_requirement_summary(checks, reviewer_summary)
    offline_passed = all(check["ok"] for check in checks) and all(req["ok"] for req in requirements)
    live_status = live_verification_status()
    full_goal_completion_proven = offline_passed and live_status.get("status") == "proven"
    report = {
        "schemaVersion": "v1",
        "generatedAt": now_rfc3339(),
        "branch": subprocess.run(
            ["git", "branch", "--show-current"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        ).stdout.strip(),
        "reviewerCount": len(reviewer_summary),
        "minimumReviewPassesRequired": 5,
        "scope": "offline-local-review-gate",
        "reviewPassCount": sum(1 for check in checks if check["ok"]),
        "offlineGatePassed": offline_passed,
        "fullGoalCompletionProven": full_goal_completion_proven,
        "passed": offline_passed,
        "liveVerification": live_status,
        "reviewers": reviewer_summary,
        "requirements": requirements,
        "checks": checks,
    }

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                k: report[k]
                for k in (
                    "passed",
                    "scope",
                    "reviewerCount",
                    "reviewPassCount",
                    "fullGoalCompletionProven",
                    "liveVerification",
                    "requirements",
                )
            },
            ensure_ascii=False,
        )
    )
    if not report["passed"]:
        failed = [check["name"] for check in checks if not check["ok"]]
        print("Failed checks: " + ", ".join(failed), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
