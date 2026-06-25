#!/usr/bin/env python3
"""Verify Ver.0.1.3 CrashLoopBackOff screen-cycle readiness.

This verifier is intentionally WSL/local friendly. It does not launch a browser,
does not call OpenShift mutation APIs, and does not require PowerShell. It checks
that the local dashboard/gateway are reachable when running and that source code
plus existing reports support the intended screen-level demo cycle:

dashboard anomaly -> chat draft/context -> stream answer contract ->
read-only action candidate -> refresh callback.

It is a readiness gate, not a screenshot/pixel proof. A later browser/screenshot
artifact is still required before claiming the visible demo cycle is complete.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.3/crashloop-screen-cycle-readiness-verification.json"


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


def read_text(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def load_json(path: str) -> dict[str, Any]:
    target = REPO_ROOT / path
    if not target.exists():
        return {}
    try:
        payload = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def http_probe(url: str, *, method: str = "GET", timeout: int = 3) -> dict[str, Any]:
    request = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 local verifier
            body = response.read(2048).decode("utf-8", errors="replace") if method != "HEAD" else ""
            return {
                "body": body,
                "ok": 200 <= response.status < 400,
                "status": response.status,
                "url": url,
            }
    except urllib.error.HTTPError as exc:
        return {"body": "", "error": str(exc), "ok": False, "status": exc.code, "url": url}
    except Exception as exc:  # pragma: no cover - local environment dependent
        return {"body": "", "error": str(exc), "ok": False, "status": None, "url": url}


def check_contains(
    checks: list[dict[str, Any]],
    *,
    name: str,
    path: str,
    needles: list[str],
) -> None:
    text = read_text(path)
    missing = [needle for needle in needles if needle not in text]
    checks.append(
        {
            "evidence": {"file": path, "missing": missing, "needles": needles},
            "name": name,
            "ok": not missing,
            "type": "source_contains",
        }
    )


def check_json_condition(
    checks: list[dict[str, Any]],
    *,
    evidence: dict[str, Any],
    name: str,
    ok: bool,
) -> None:
    checks.append({"evidence": evidence, "name": name, "ok": ok, "type": "json_report"})


def evaluate_existing_reports(checks: list[dict[str, Any]]) -> None:
    scenario_report = load_json("docs/Ver.0.1.3/aiops-scenario-evaluation-report.json")
    check_json_condition(
        checks,
        name="scenario_evaluator_10_of_10_pass",
        ok=(
            scenario_report.get("scenarioCount") == 10
            and scenario_report.get("passed") == 10
            and scenario_report.get("failed") == 0
            and scenario_report.get("negativeControlsPassed") is True
        ),
        evidence={
            "failed": scenario_report.get("failed"),
            "negativeControlsPassed": scenario_report.get("negativeControlsPassed"),
            "passed": scenario_report.get("passed"),
            "scenarioCount": scenario_report.get("scenarioCount"),
        },
    )

    demo_report = load_json("docs/Ver.0.1.3/crashloop-demo-cycle-verification.json")
    check_json_condition(
        checks,
        name="offline_crashloop_demo_contract_pass",
        ok=demo_report.get("status") == "pass",
        evidence={"status": demo_report.get("status")},
    )

    live_report = load_json("docs/Ver.0.1.3/crashloop-live-demo-cycle-verification.json")
    live_checks = live_report.get("spec", {}).get("checks") if isinstance(live_report.get("spec"), dict) else []
    live_check_count = len(live_checks) if isinstance(live_checks, list) else 0
    check_json_condition(
        checks,
        name="live_crashloop_demo_contract_pass",
        ok=live_report.get("status") == "pass" and live_check_count > 0,
        evidence={"checkCount": live_check_count, "status": live_report.get("status")},
    )


def evaluate_source_wiring(checks: list[dict[str, Any]]) -> None:
    check_contains(
        checks,
        name="dashboard_anomaly_to_chat_draft_wiring",
        path="komsco-ai-console-plugin/src/pages/AiopsPages.tsx",
        needles=[
            "data-aiops-demo-action=\"seed-chat-prompt\"",
            "setAssistantDraftPrompt(buildFindingDemoDraft(finding, matchingCandidate))",
            "focusAssistant();",
            "findingId: finding.id",
            "readOnlyOnly: true",
            "scenarioId: isCrashLoopFinding(finding) ? 'crashloop'",
            "source: 'aiops-dashboard-anomaly-board'",
            "taskMode: 'troubleshooting'",
        ],
    )
    check_contains(
        checks,
        name="dashboard_action_candidate_read_only_policy_visible",
        path="komsco-ai-console-plugin/src/pages/AiopsPages.tsx",
        needles=[
            "data-action-candidate-execution=\"not-executed\"",
            "data-action-candidate-mode={mode}",
            "제안만 함 / 실행 안 함",
            "mutation disabled. 금지 동작:",
            "approvalRequired ? '승인 전 실행 불가'",
        ],
    )
    check_contains(
        checks,
        name="dashboard_chat_embedded_and_refresh_wired",
        path="komsco-ai-console-plugin/src/pages/AiopsPages.tsx",
        needles=[
            "ref={assistantStageRef}",
            "<AssistantLauncher",
            "defaultOpen",
            "embedded",
            "lockOpen",
            "draftPrompt={assistantDraftPrompt}",
            "onRunComplete={data.refresh}",
        ],
    )
    check_contains(
        checks,
        name="assistant_draft_context_forces_read_only_and_stream_context",
        path="komsco-ai-console-plugin/src/components/AssistantLauncher.tsx",
        needles=[
            "setInput(draftPrompt.prompt)",
            "setDraftPageContext(draftPrompt.pageContext)",
            "setAssistantTaskMode(draftPrompt.taskMode ?? 'troubleshooting')",
            "setExecutionMode('read-only')",
            "activeDraftPageContext?.readOnlyOnly === true ? 'read-only' : executionMode",
            "aiopsDemoCycle: activeDraftPageContext",
        ],
    )
    check_contains(
        checks,
        name="assistant_completion_refresh_callback",
        path="komsco-ai-console-plugin/src/components/AssistantLauncher.tsx",
        needles=[
            "let runCompleted = false",
            "if (runCompleted) {",
            "void onRunComplete?.();",
        ],
    )
    check_contains(
        checks,
        name="gateway_crashloop_answer_contract_and_context_preserved",
        path="komsco-ai-gateway/komsco_ai_gateway/main.py",
        needles=[
            "def normalize_aiops_demo_cycle_context",
            "AIOPS_DEMO_CYCLE_ALLOWED_KEYS",
            "AIOPS_DEMO_CYCLE_TARGET_ALLOWED_KEYS",
            "def crashloop_demo_prompt_answer_contract",
            "def build_crashloop_demo_answer_contract_text",
            '"answerContract": "crashloop-v0.1.3"',
            '"aiopsDemoCycle"',
        ],
    )
    check_contains(
        checks,
        name="gateway_rca_context_preserves_finding_and_scenario",
        path="komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py",
        needles=[
            '"findingId": demo_cycle_context.get("findingId")',
            '"scenarioId": demo_cycle_context.get("scenarioId")',
            '"scenarioContext": scenario_context',
        ],
    )


def evaluate_local_runtime(checks: list[dict[str, Any]]) -> None:
    console = http_probe("http://127.0.0.1:9000/dashboards", method="HEAD")
    gateway = http_probe("http://127.0.0.1:18080/healthz", method="GET")
    plugin = http_probe("http://127.0.0.1:9001/plugin-manifest.json", method="GET")
    checks.append(
        {
            "evidence": console,
            "name": "local_console_dashboard_reachable",
            "ok": console["ok"],
            "type": "local_http_probe",
        }
    )
    checks.append(
        {
            "evidence": {**gateway, "body": gateway.get("body", "")[:120]},
            "name": "local_gateway_healthz_ok",
            "ok": gateway["ok"] and '"status":"ok"' in str(gateway.get("body", "")),
            "type": "local_http_probe",
        }
    )
    checks.append(
        {
            "evidence": {**plugin, "body": plugin.get("body", "")[:120]},
            "name": "local_plugin_dev_server_manifest_reachable",
            "ok": plugin["ok"],
            "type": "local_http_probe",
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT), help="JSON report path")
    parser.add_argument(
        "--skip-runtime",
        action="store_true",
        help="Skip local HTTP probes when dev servers are intentionally down.",
    )
    args = parser.parse_args()

    checks: list[dict[str, Any]] = []
    evaluate_source_wiring(checks)
    evaluate_existing_reports(checks)
    if not args.skip_runtime:
        evaluate_local_runtime(checks)

    missing_evidence = [
        {
            "reason": "This WSL-only verifier does not open a browser, click the anomaly card, or capture pixels.",
            "type": "browser_screenshot",
        },
        {
            "reason": "Live report stores final answer digest/contract checks, not the full answer body snapshot.",
            "type": "answer_body_snapshot",
        },
    ]
    report = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "generatedAt": now_rfc3339(),
        "kind": "CrashLoopScreenCycleReadinessVerification",
        "metadata": {
            "baseRef": git_value(["merge-base", "HEAD", "origin/main"])
            or git_value(["merge-base", "HEAD", "upstream/main"]),
            "branch": git_value(["branch", "--show-current"]),
            "headSha": git_value(["rev-parse", "HEAD"]),
            "name": "ver-0.1.3-crashloop-screen-cycle-readiness",
            "scope": "source-and-local-runtime-readiness",
        },
        "spec": {
            "checks": checks,
            "claim": "readiness_only_not_pixel_complete",
            "missingEvidenceBeforeCompletionClaim": missing_evidence,
            "nextGate": "browser screenshot or UI verifier artifact for /dashboards anomaly-to-chat cycle",
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
