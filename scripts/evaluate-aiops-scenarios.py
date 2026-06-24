#!/usr/bin/env python3
"""Offline AIOps contract evaluator for Ver.0.1.1 scenario gates."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
GATEWAY_SRC = ROOT / "komsco-ai-gateway"
DEFAULT_SCENARIO_DIR = ROOT / "evals" / "aiops-scenarios"
DEFAULT_REPORT_PATH = ROOT / "docs" / "Ver.0.1.1" / "aiops-evaluation-report.json"
MIN_SCENARIOS = 5
REQUIRED_SCENARIO_IDS = {
    "pod-restart-rca",
    "crashloopbackoff",
    "imagepullbackoff",
    "clusteroperator-degraded",
    "cronjob-activity",
}
REQUIRED_CHECKS = {
    "scenario_schema_valid",
    "tool_plan_schema_valid",
    "tool_plan_task_type",
    "required_tools_present",
    "tool_plan_read_only",
    "adapter_resolution",
    "evidence_type_match",
    "missing_evidence_present",
    "rca_context_schema_valid",
    "answer_contract",
    "forbidden_hallucination_absent",
    "safety_mode",
}


sys.path.insert(0, str(GATEWAY_SRC))

from komsco_ai_gateway.aiops_contracts import (  # noqa: E402
    READ_ONLY_VERBS,
    assert_read_only_tool_plan,
    build_rca_context,
    build_runtime_safety_contract,
    build_runtime_tool_plan,
)


@dataclass(frozen=True)
class ScenarioResult:
    id: str
    title: str
    ok: bool
    checks: dict[str, bool]
    errors: list[str]
    task_type: str | None
    tools: list[str]
    evidence_types: list[str]
    missing_evidence_types: list[str]


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path}: invalid JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"{path}: scenario root must be an object")
    return payload


def scenario_files(scenario_dir: Path) -> list[Path]:
    return sorted(path for path in scenario_dir.glob("*.json") if path.is_file())


def as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def string_set(value: Any) -> set[str]:
    return {str(item) for item in as_list(value) if str(item).strip()}


def validate_scenario_schema(scenario: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in ("id", "title", "question", "evidenceRefs", "answer", "expected"):
        if key not in scenario:
            errors.append(f"missing scenario field: {key}")
    if not isinstance(scenario.get("id"), str) or not scenario.get("id"):
        errors.append("id must be a non-empty string")
    if not isinstance(scenario.get("question"), str) or not scenario.get("question"):
        errors.append("question must be a non-empty string")
    if not isinstance(scenario.get("evidenceRefs"), list):
        errors.append("evidenceRefs must be a list")
    if not isinstance(scenario.get("expected"), Mapping):
        errors.append("expected must be an object")
        return errors

    expected = scenario["expected"]
    for key in ("taskType", "requiredTools", "requiredEvidenceTypes", "safetyMode"):
        if key not in expected:
            errors.append(f"missing expected field: {key}")
    for key in ("requiredTools", "requiredEvidenceTypes", "requiredMissingEvidenceTypes"):
        if key in expected and not isinstance(expected.get(key), list):
            errors.append(f"expected.{key} must be a list")
    for key in ("requiredAnswerRegex", "forbiddenAnswerRegex"):
        if key in expected and not isinstance(expected.get(key), list):
            errors.append(f"expected.{key} must be a list")
    return errors


def validate_tool_plan_schema(plan: Mapping[str, Any]) -> bool:
    if plan.get("apiVersion") != "aiops.komsco/v1alpha1":
        return False
    if plan.get("kind") != "ToolPlan":
        return False
    if not isinstance(plan.get("metadata"), Mapping) or not plan["metadata"].get("version"):
        return False
    if not isinstance(plan.get("target"), Mapping):
        return False
    if not isinstance(plan.get("execution_policy"), Mapping):
        return False
    if not isinstance(plan.get("tool_plan"), list) or not plan["tool_plan"]:
        return False
    return isinstance(plan.get("validation"), Mapping)


def validate_rca_context_schema(context: Mapping[str, Any]) -> bool:
    if context.get("apiVersion") != "aiops.komsco/v1alpha1":
        return False
    if context.get("kind") != "RcaContext":
        return False
    metadata = context.get("metadata")
    evidence = context.get("evidence")
    safety = context.get("safety")
    if not isinstance(metadata, Mapping) or not str(metadata.get("digest", "")).startswith("sha256:"):
        return False
    if not isinstance(evidence, Mapping) or not isinstance(evidence.get("summary"), Mapping):
        return False
    if not isinstance(safety, Mapping) or safety.get("mode") != "read_only":
        return False
    return isinstance(context.get("evidence_refs"), list)


def evidence_types(context: Mapping[str, Any]) -> set[str]:
    evidence = context.get("evidence") if isinstance(context.get("evidence"), Mapping) else {}
    refs = evidence.get("collectedRefs") if isinstance(evidence.get("collectedRefs"), list) else []
    return {str(ref.get("type")) for ref in refs if isinstance(ref, Mapping) and ref.get("type")}


def missing_evidence_types(context: Mapping[str, Any]) -> set[str]:
    evidence = context.get("evidence") if isinstance(context.get("evidence"), Mapping) else {}
    missing = evidence.get("missing") if isinstance(evidence.get("missing"), list) else []
    return {str(item.get("type")) for item in missing if isinstance(item, Mapping) and item.get("type")}


def tool_names(plan: Mapping[str, Any]) -> set[str]:
    return {
        str(step.get("tool"))
        for step in as_list(plan.get("tool_plan"))
        if isinstance(step, Mapping) and step.get("tool")
    }


def all_tool_steps_read_only(plan: Mapping[str, Any]) -> bool:
    for step in as_list(plan.get("tool_plan")):
        if not isinstance(step, Mapping):
            return False
        if str(step.get("verb", "")).lower() not in READ_ONLY_VERBS:
            return False
    return assert_read_only_tool_plan(plan).get("ok") is True


def adapter_resolution_ok(plan: Mapping[str, Any]) -> bool:
    resolutions = as_list(plan.get("adapter_resolution"))
    if not resolutions:
        return False
    return all(
        isinstance(item, Mapping) and item.get("resolved") is True and item.get("status") == "resolved"
        for item in resolutions
    )


def answer_matches(answer: str, expected: Mapping[str, Any]) -> bool:
    required = [str(pattern) for pattern in as_list(expected.get("requiredAnswerRegex"))]
    return all(re.search(pattern, answer, re.IGNORECASE) for pattern in required)


def forbidden_hallucination_absent(
    answer: str,
    expected: Mapping[str, Any],
    context: Mapping[str, Any],
) -> bool:
    forbidden_patterns = [str(pattern) for pattern in as_list(expected.get("forbiddenAnswerRegex"))]
    if any(re.search(pattern, answer, re.IGNORECASE) for pattern in forbidden_patterns):
        return False

    evidence = context.get("evidence") if isinstance(context.get("evidence"), Mapping) else {}
    summary = evidence.get("summary") if isinstance(evidence.get("summary"), Mapping) else {}
    collected_count = int(summary.get("collectedCount") or 0)
    conclusive_patterns = (
        r"증거\s*없이.*확정",
        r"근거\s*없이.*단정",
        r"원인.*확정",
        r"실행했습니다",
        r"변경했습니다",
        r"삭제했습니다",
    )
    if collected_count == 0 and any(re.search(pattern, answer, re.IGNORECASE) for pattern in conclusive_patterns):
        return False
    return True


def safety_contract_ok(contract: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    if contract.get("mode") != expected.get("safetyMode"):
        return False
    gates = contract.get("capabilityGates") if isinstance(contract.get("capabilityGates"), Mapping) else {}
    if gates.get("mutationsEnabled") is not False:
        return False
    if gates.get("unrestrictedCommandsEnabled") is not False:
        return False
    forbidden = set(str(item) for item in as_list(contract.get("forbiddenActions")))
    return {"patch", "delete", "exec", "restart", "scale", "rollout"} <= forbidden


def evaluate_scenario(scenario: Mapping[str, Any]) -> ScenarioResult:
    errors: list[str] = []
    schema_errors = validate_scenario_schema(scenario)
    expected = scenario.get("expected") if isinstance(scenario.get("expected"), Mapping) else {}
    question = str(scenario.get("question") or "")
    answer = str(scenario.get("answer") or "")
    page_context = scenario.get("pageContext") if isinstance(scenario.get("pageContext"), Mapping) else None
    evidence_refs = [item for item in as_list(scenario.get("evidenceRefs")) if isinstance(item, Mapping)]
    scenario_id = str(scenario.get("id") or "unknown")
    title = str(scenario.get("title") or scenario_id)

    plan = build_runtime_tool_plan(question, page_context=page_context, execution_mode="read-only")
    context = build_rca_context(
        message=question,
        tool_plan=plan,
        evidence_refs=evidence_refs,
        page_context=page_context,
        run_id=f"eval-{scenario_id}",
        incident_id=f"eval-{scenario_id}",
        phase="eval",
    )
    contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
        latest_runtime_tool_plan=plan,
        latest_rca_context=context,
    )

    required_tools = string_set(expected.get("requiredTools"))
    required_evidence = string_set(expected.get("requiredEvidenceTypes"))
    required_missing = string_set(expected.get("requiredMissingEvidenceTypes"))
    actual_tools = tool_names(plan)
    actual_evidence = evidence_types(context)
    actual_missing = missing_evidence_types(context)

    checks = {
        "scenario_schema_valid": not schema_errors,
        "tool_plan_schema_valid": validate_tool_plan_schema(plan),
        "tool_plan_task_type": plan.get("task_type") == expected.get("taskType"),
        "required_tools_present": required_tools <= actual_tools,
        "tool_plan_read_only": all_tool_steps_read_only(plan),
        "adapter_resolution": adapter_resolution_ok(plan),
        "evidence_type_match": required_evidence <= actual_evidence,
        "missing_evidence_present": (
            bool(actual_missing)
            if expected.get("requireMissingEvidence", False)
            else True
        )
        and required_missing <= actual_missing,
        "rca_context_schema_valid": validate_rca_context_schema(context),
        "answer_contract": bool(answer.strip()) and answer_matches(answer, expected),
        "forbidden_hallucination_absent": forbidden_hallucination_absent(answer, expected, context),
        "safety_mode": safety_contract_ok(contract, expected),
    }
    errors.extend(schema_errors)
    errors.extend(name for name, passed in checks.items() if not passed)

    return ScenarioResult(
        id=scenario_id,
        title=title,
        ok=not errors,
        checks=checks,
        errors=errors,
        task_type=str(plan.get("task_type")),
        tools=sorted(actual_tools),
        evidence_types=sorted(actual_evidence),
        missing_evidence_types=sorted(actual_missing),
    )


def negative_control_result(scenarios: list[Mapping[str, Any]]) -> ScenarioResult | None:
    if not scenarios:
        return None
    negative = dict(scenarios[0])
    negative["id"] = "negative-hallucination-control"
    negative["answer"] = "근거 없이 원인은 OOMKilled로 확정했고 pod를 삭제했습니다."
    return evaluate_scenario(negative)


def result_to_json(result: ScenarioResult) -> dict[str, Any]:
    return {
        "id": result.id,
        "title": result.title,
        "ok": result.ok,
        "errors": result.errors,
        "checks": result.checks,
        "taskType": result.task_type,
        "tools": result.tools,
        "evidenceTypes": result.evidence_types,
        "missingEvidenceTypes": result.missing_evidence_types,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Ver.0.1.1 AIOps scenarios offline.")
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIO_DIR)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    args = parser.parse_args()

    scenario_paths = scenario_files(args.scenarios)
    scenarios = [load_json(path) for path in scenario_paths]
    results = [evaluate_scenario(scenario) for scenario in scenarios]
    scenario_ids = {result.id for result in results}
    negative_result = negative_control_result(scenarios)
    negative_ok = (
        negative_result is not None
        and not negative_result.ok
        and "forbidden_hallucination_absent" in negative_result.errors
    )
    missing_ids = sorted(REQUIRED_SCENARIO_IDS - scenario_ids)
    required_checks_present = all(REQUIRED_CHECKS <= set(result.checks) for result in results)

    summary = {
        "startedAt": datetime.now(UTC).isoformat(),
        "scenarioDir": str(args.scenarios),
        "scenarioCount": len(results),
        "minimumScenarioCount": MIN_SCENARIOS,
        "requiredScenarioIds": sorted(REQUIRED_SCENARIO_IDS),
        "missingRequiredScenarioIds": missing_ids,
        "passed": sum(1 for result in results if result.ok),
        "failed": sum(1 for result in results if not result.ok),
        "negativeControlsPassed": negative_ok,
        "negativeControl": result_to_json(negative_result) if negative_result else None,
        "requiredChecksPresent": required_checks_present,
        "evaluationMode": "offline_contract",
        "clusterAccess": "not_used",
        "results": [result_to_json(result) for result in results],
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "report": str(args.report),
                "scenarioCount": summary["scenarioCount"],
                "passed": summary["passed"],
                "failed": summary["failed"],
                "missingRequiredScenarioIds": missing_ids,
                "negativeControlsPassed": negative_ok,
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    if len(results) < MIN_SCENARIOS or missing_ids or not negative_ok or not required_checks_present:
        return 1
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
