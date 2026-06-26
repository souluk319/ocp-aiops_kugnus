#!/usr/bin/env python3
"""Strict local demo audit for the Kugnus RCA/Lightspeed objective.

This is the "do not overclaim" gate. It reads existing evidence reports and
allows the success claim only when local RCA evidence and the strict
Lightspeed final-response gate are both proven.
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
DEFAULT_REPORT = REPO_ROOT / "docs/Ver.0.1.5/strict-demo-audit-report.json"


REPORTS = {
    "runtime_smoke": REPO_ROOT / "docs/Ver.0.1.3/runtime-smoke-report.json",
    "scenario_contract": REPO_ROOT / "docs/Ver.0.1.3/aiops-scenario-evaluation-report.json",
    "evidence_rca_scene": REPO_ROOT / "docs/Ver.0.1.3/evidence-rca-scene-verification.json",
    "live_demo_cycle": REPO_ROOT / "docs/Ver.0.1.3/crashloop-live-demo-cycle-verification.json",
    "screen_readiness": REPO_ROOT / "docs/Ver.0.1.3/crashloop-screen-cycle-readiness-verification.json",
    "rag_file_upload": REPO_ROOT / "docs/Ver.0.1.5/rag-file-upload-smoke-report.json",
    "ui_verifier": REPO_ROOT / "docs/Ver.0.1.5/ui-verifier-report.json",
    "ocp_ladder_contract": REPO_ROOT / "docs/Ver.0.1.5/ocp-connectivity-ladder-contract-verification.json",
    "ocp_connectivity": REPO_ROOT / "docs/Ver.0.1.5/ocp-connectivity-ladder-report.json",
    "strict_lightspeed": REPO_ROOT / "docs/Ver.0.1.5/live-lightspeed-final-response-verification.json",
}


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


def load_json(path: Path) -> tuple[dict[str, Any], str]:
    try:
        return json.loads(path.read_text(encoding="utf-8")), ""
    except FileNotFoundError:
        return {}, "missing"
    except json.JSONDecodeError as exc:
        return {}, f"invalid_json: {exc}"


def iter_check_lists(payload: dict[str, Any], keys: tuple[str, ...]) -> list[tuple[str, list[Any]]]:
    lists: list[tuple[str, list[Any]]] = []
    for key in keys:
        items = payload.get(key)
        if isinstance(items, list):
            lists.append((key, items))
    for parent_key in ("spec", "status"):
        parent = payload.get(parent_key)
        if not isinstance(parent, dict):
            continue
        for key in keys:
            items = parent.get(key)
            if isinstance(items, list):
                lists.append((f"{parent_key}.{key}", items))
    return lists


def all_named_checks_ok(payload: dict[str, Any], keys: tuple[str, ...] = ("checks", "results")) -> tuple[bool, list[str]]:
    failed: list[str] = []
    check_lists = iter_check_lists(payload, keys)
    for key, items in check_lists:
        for index, item in enumerate(items):
            if not isinstance(item, dict) or "ok" not in item:
                continue
            if item.get("ok") is not True:
                failed.append(str(item.get("name") or item.get("id") or f"{key}[{index}]"))
    if not check_lists:
        return False, ["no checks/results list"]
    return not failed, failed


def gate(name: str, path: Path, ok: bool, requirement: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": ok,
        "requirement": requirement,
        "report": str(path.relative_to(REPO_ROOT)),
        "details": details or {},
    }


def check_runtime_smoke(path: Path, payload: dict[str, Any], error: str) -> dict[str, Any]:
    if error:
        return gate("runtime_smoke", path, False, "runtime smoke report exists and all checks pass", {"error": error})
    ok, failed = all_named_checks_ok(payload)
    return gate("runtime_smoke", path, ok, "local Gateway runtime smoke checks all pass", {"failedChecks": failed})


def check_scenario_contract(path: Path, payload: dict[str, Any], error: str) -> dict[str, Any]:
    if error:
        return gate("scenario_contract", path, False, "ten scenario evaluator report exists", {"error": error})
    ok = (
        payload.get("scenarioCount") == 10
        and payload.get("expectedScenarioCount") == 10
        and payload.get("passed") == 10
        and payload.get("failed") == 0
        and payload.get("negativeControlsPassed") is True
    )
    return gate(
        "scenario_contract",
        path,
        ok,
        "10/10 operation scenarios pass and negative controls pass",
        {
            "scenarioCount": payload.get("scenarioCount"),
            "expectedScenarioCount": payload.get("expectedScenarioCount"),
            "passed": payload.get("passed"),
            "failed": payload.get("failed"),
            "negativeControlsPassed": payload.get("negativeControlsPassed"),
        },
    )


def check_named_checks_report(name: str, path: Path, payload: dict[str, Any], error: str, requirement: str) -> dict[str, Any]:
    if error:
        return gate(name, path, False, requirement, {"error": error})
    ok, failed = all_named_checks_ok(payload)
    return gate(name, path, ok, requirement, {"failedChecks": failed})


def check_ui_verifier(path: Path, payload: dict[str, Any], error: str) -> dict[str, Any]:
    if error:
        return gate("ui_verifier", path, False, "UI verifier report exists", {"error": error})
    failed_value = payload.get("failed")
    failed_count = len(failed_value) if isinstance(failed_value, list) else int(failed_value or 0)
    ok = payload.get("ok") is True and failed_count == 0 and int(payload.get("checked") or 0) >= 100
    return gate(
        "ui_verifier",
        path,
        ok,
        "UI verifier passes at least 100 checks with zero failures",
        {"ok": payload.get("ok"), "checked": payload.get("checked"), "failedCount": failed_count},
    )


def check_ocp_ladder_contract(path: Path, payload: dict[str, Any], error: str) -> dict[str, Any]:
    if error:
        return gate("ocp_ladder_contract", path, False, "OCP ladder contract verifier exists", {"error": error})
    return gate(
        "ocp_ladder_contract",
        path,
        payload.get("allPassed") is True,
        "OCP ladder parsing and likely-cause contract passes",
        {"allPassed": payload.get("allPassed"), "checkCount": len(payload.get("checks") or [])},
    )


def check_ocp_connectivity(path: Path, payload: dict[str, Any], error: str) -> dict[str, Any]:
    if error:
        return gate("ocp_connectivity", path, False, "OCP connectivity ladder report exists", {"error": error})
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    interpretation = payload.get("interpretation") if isinstance(payload.get("interpretation"), dict) else {}
    ok = summary.get("readyForStrictLightspeedGate") is True
    return gate(
        "ocp_connectivity",
        path,
        ok,
        "OCP connectivity ladder is ready for strict Lightspeed gate",
        {
            "readyForStrictLightspeedGate": summary.get("readyForStrictLightspeedGate"),
            "firstFailingLayer": summary.get("firstFailingLayer"),
            "message": summary.get("message"),
            "likelyCause": interpretation.get("likelyCause"),
            "nextActions": interpretation.get("nextActions") or [],
        },
    )


def check_strict_lightspeed(path: Path, payload: dict[str, Any], error: str) -> dict[str, Any]:
    if error:
        return gate("strict_lightspeed", path, False, "strict Lightspeed report exists", {"error": error})
    preflight = payload.get("preflight") if isinstance(payload.get("preflight"), dict) else {}
    ocp = preflight.get("ocpConnectivity") if isinstance(preflight.get("ocpConnectivity"), dict) else {}
    return gate(
        "strict_lightspeed",
        path,
        payload.get("allSucceeded") is True,
        "fallback-free Lightspeed final response allSucceeded=true",
        {
            "allSucceeded": payload.get("allSucceeded"),
            "preflightError": preflight.get("error"),
            "ocpFirstFailingLayer": ocp.get("firstFailingLayer"),
            "ocpLikelyCause": ocp.get("likelyCause"),
        },
    )


def build_audit() -> dict[str, Any]:
    payloads: dict[str, tuple[dict[str, Any], str]] = {
        name: load_json(path) for name, path in REPORTS.items()
    }
    gates = [
        check_runtime_smoke(REPORTS["runtime_smoke"], *payloads["runtime_smoke"]),
        check_scenario_contract(REPORTS["scenario_contract"], *payloads["scenario_contract"]),
        check_named_checks_report(
            "evidence_rca_scene",
            REPORTS["evidence_rca_scene"],
            *payloads["evidence_rca_scene"],
            "official Evidence/RCA scene checks all pass",
        ),
        check_named_checks_report(
            "live_demo_cycle",
            REPORTS["live_demo_cycle"],
            *payloads["live_demo_cycle"],
            "CrashLoop live demo cycle checks all pass",
        ),
        check_named_checks_report(
            "screen_readiness",
            REPORTS["screen_readiness"],
            *payloads["screen_readiness"],
            "CrashLoop screen readiness checks all pass",
        ),
        check_named_checks_report(
            "rag_file_upload",
            REPORTS["rag_file_upload"],
            *payloads["rag_file_upload"],
            "PDF upload RAG smoke checks all pass",
        ),
        check_ui_verifier(REPORTS["ui_verifier"], *payloads["ui_verifier"]),
        check_ocp_ladder_contract(REPORTS["ocp_ladder_contract"], *payloads["ocp_ladder_contract"]),
        check_ocp_connectivity(REPORTS["ocp_connectivity"], *payloads["ocp_connectivity"]),
        check_strict_lightspeed(REPORTS["strict_lightspeed"], *payloads["strict_lightspeed"]),
    ]
    blocking = [item for item in gates if not item["ok"]]
    local_rca_gate_names = {
        "runtime_smoke",
        "scenario_contract",
        "evidence_rca_scene",
        "live_demo_cycle",
        "screen_readiness",
        "rag_file_upload",
        "ui_verifier",
        "ocp_ladder_contract",
    }
    local_rca_ready = all(item["ok"] for item in gates if item["name"] in local_rca_gate_names)
    strict_lightspeed_ready = all(
        item["ok"] for item in gates if item["name"] in {"ocp_connectivity", "strict_lightspeed"}
    )
    return {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "StrictDemoAuditReport",
        "generatedAt": now_rfc3339(),
        "branch": git_value(["branch", "--show-current"]),
        "headSha": git_value(["rev-parse", "HEAD"]),
        "localRcaReady": local_rca_ready,
        "strictLightspeedReady": strict_lightspeed_ready,
        "successClaimAllowed": not blocking,
        "blockingGates": [item["name"] for item in blocking],
        "gates": gates,
        "rule": "Do not claim Lightspeed final-response success unless successClaimAllowed=true.",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    audit = build_audit()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Strict demo audit: {'PASS' if audit['successClaimAllowed'] else 'FAIL'}")
    print(f"localRcaReady={audit['localRcaReady']} strictLightspeedReady={audit['strictLightspeedReady']}")
    if audit["blockingGates"]:
        print(f"blockingGates={', '.join(audit['blockingGates'])}")
        for item in audit["gates"]:
            if not item["ok"]:
                details = item.get("details") or {}
                likely = details.get("likelyCause") or details.get("ocpLikelyCause")
                first = details.get("firstFailingLayer") or details.get("ocpFirstFailingLayer")
                if first or likely:
                    print(f"[FAIL] {item['name']}: firstFailingLayer={first} likelyCause={likely}")
                else:
                    print(f"[FAIL] {item['name']}: {details}")
    print(f"Report: {report_path}")
    return 0 if audit["successClaimAllowed"] else 1


if __name__ == "__main__":
    sys.exit(main())
