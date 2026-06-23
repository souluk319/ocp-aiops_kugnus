from collections.abc import Mapping
from typing import Any

PRODUCT_CONTRACT = {
    "name": "Cywell AI",
    "mode": "read_only_first",
    "mission": "Evidence-first OpenShift operations assistant for catalog registration work.",
}

READ_ONLY_VERBS = frozenset({"get", "list", "watch"})
FORBIDDEN_ACTIONS = (
    "create",
    "update",
    "patch",
    "delete",
    "exec",
    "portforward",
    "restart",
    "scale",
    "rollout",
)

EVIDENCE_GROUPS = (
    {
        "type": "openshift",
        "matches": frozenset(
            {
                "openshift_api",
                "target_resource",
                "namespace",
                "node",
                "pod",
                "pod_status",
                "pod_log",
                "event",
                "clusterversion",
                "clusteroperator",
                "deployment",
            }
        ),
    },
    {"type": "metric", "matches": frozenset({"metric", "prometheus", "usage"})},
    {"type": "runbook", "matches": frozenset({"runbook", "rag_reference", "procedure"})},
    {"type": "audit", "matches": frozenset({"audit", "record", "execution_record"})},
)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def create_evidence_status(collection: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    collection = collection or {}
    evidence = _as_list(collection.get("evidence"))
    missing = _as_list(collection.get("missing"))

    status = []
    for group in EVIDENCE_GROUPS:
        group_type = str(group["type"])
        matches = group["matches"]
        count = sum(
            1
            for item in evidence
            if isinstance(item, Mapping) and str(item.get("type", "")).lower() in matches
        )
        missing_reasons = [
            item
            for item in missing
            if isinstance(item, Mapping)
            and (
                str(item.get("type", "")).lower() == group_type
                or str(item.get("type", "")).lower() in matches
            )
        ]

        if count > 0:
            status.append({"type": group_type, "status": "collected", "count": count})
        else:
            reason = (
                str(missing_reasons[0].get("reason"))
                if missing_reasons
                else f"{group_type} evidence not collected yet"
            )
            status.append(
                {
                    "type": group_type,
                    "status": "missing",
                    "count": 0,
                    "reason": reason,
                }
            )

    return status


def assert_read_only_tool_plan(tool_plan: Mapping[str, Any] | None) -> dict[str, Any]:
    violations: list[str] = []
    plan = tool_plan or {}
    execution_policy = plan.get("execution_policy")

    if isinstance(execution_policy, Mapping):
        mode = str(execution_policy.get("mode", "")).lower()
        if mode and mode != "read_only":
            violations.append("execution_policy.mode must be read_only")

    for step in _as_list(plan.get("tool_plan")):
        if not isinstance(step, Mapping):
            continue
        verb = str(step.get("verb", "")).lower()
        tool = str(step.get("tool", "")).lower()
        step_id = step.get("step", "unknown")

        if verb and verb not in READ_ONLY_VERBS:
            violations.append(f"step {step_id} uses non-read-only verb {verb}")
        for action in FORBIDDEN_ACTIONS:
            if action in tool:
                violations.append(f"step {step_id} uses forbidden tool {step.get('tool')}")
                break

    return {"ok": not violations, "violations": violations}


def build_runtime_safety_contract(
    *,
    mutations_enabled: bool,
    unrestricted_commands_enabled: bool,
    diagnostics_enabled: bool,
    record_store_enabled: bool,
) -> dict[str, Any]:
    mode = "controlled_execution" if mutations_enabled else "read_only"
    return {
        "product": PRODUCT_CONTRACT,
        "mode": mode,
        "allowedReadOnlyVerbs": sorted(READ_ONLY_VERBS),
        "forbiddenActions": list(FORBIDDEN_ACTIONS),
        "evidenceStatus": create_evidence_status(),
        "capabilityGates": {
            "mutationsEnabled": mutations_enabled,
            "unrestrictedCommandsEnabled": unrestricted_commands_enabled,
            "diagnosticsEnabled": diagnostics_enabled,
            "recordStoreEnabled": record_store_enabled,
        },
        "toolPlanStatus": {
            "source": "gateway_safety_contract",
            "status": "contract_only",
            "latestRuntimePlan": "not_persisted_in_ver_0_1_0",
        },
        "adapterStatus": [
            {
                "name": "OpenShift",
                "status": "available",
                "detail": "UserToken-scoped read-only cluster observation",
            },
            {
                "name": "Linux",
                "status": "planned" if not diagnostics_enabled else "diagnostics_ready",
                "detail": "host diagnostics adapter remains approval-gated",
            },
            {
                "name": "Windows",
                "status": "planned",
                "detail": "Windows event adapter is design scope, not runtime-ready",
            },
        ],
        "lightspeedStatus": {
            "status": "configured",
            "streamProbe": "not_probed_by_status_endpoint",
            "baseService": "openshift-lightspeed/lightspeed-app-server:8443",
        },
    }
