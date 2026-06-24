from collections.abc import Mapping
from datetime import UTC, datetime
import re
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

NAMESPACE_MENTION_RE = re.compile(r"\b(?P<namespace>[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?)\s*네임스페이스")


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


def _message_has_any(message: str, keywords: tuple[str, ...]) -> bool:
    normalized = message.lower()
    return any(keyword in normalized for keyword in keywords)


def _namespace_from_message(message: str, page_context: Mapping[str, Any] | None) -> str | None:
    context_namespace = page_context.get("namespace") if isinstance(page_context, Mapping) else None
    if isinstance(context_namespace, str) and context_namespace.strip():
        return context_namespace.strip()

    match = NAMESPACE_MENTION_RE.search(message)
    return match.group("namespace") if match else None


def build_runtime_tool_plan(
    message: str,
    *,
    page_context: Mapping[str, Any] | None = None,
    execution_mode: str = "read-only",
) -> dict[str, Any]:
    namespace = _namespace_from_message(message, page_context)
    asks_pod = _message_has_any(message, ("pod", "pods", "파드"))
    asks_restart = _message_has_any(
        message,
        ("restart", "재시작", "crashloop", "crashloopbackoff", "imagepull", "backoff", "oom"),
    )
    asks_operator = _message_has_any(message, ("clusteroperator", "cluster operator", "오퍼레이터"))
    asks_cronjob = _message_has_any(message, ("cronjob", "cron job", "크론잡", "스케줄", "schedule"))
    asks_count = _message_has_any(message, ("count", "개수", "몇개", "몇 개", "떠있", "running", "ready"))
    asks_action_followup = message.strip().lower() in {
        "승인",
        "승인해",
        "실행",
        "실행해",
        "진행",
        "진행해",
        "수행",
        "수행해",
        "적용",
        "적용해",
        "yes",
        "ok",
    }
    asks_action = _message_has_any(
        message,
        ("올려", "늘려", "줄여", "변경", "스케일", "scale", "restart", "재시작", "롤백", "rollback"),
    )

    if (asks_action_followup or asks_action) and not (asks_pod and asks_restart):
        task_type = "action_lifecycle_review"
        tool_steps = [
            {
                "step": 1,
                "tool": "gateway_pending_action_plan_lookup",
                "adapter": "AI Gateway",
                "verb": "get",
                "evidence_type": "audit",
                "reason": "승인 또는 실행 전에 기존 proposal/sealed plan 존재 여부 확인",
            },
            {
                "step": 2,
                "tool": "gateway_safety_policy_check",
                "adapter": "AI Gateway",
                "verb": "get",
                "evidence_type": "audit",
                "reason": "read-only 기본 정책과 mutation gate 상태 확인",
            },
        ]
        missing = [
            {
                "type": "execution_record",
                "reason": "execution record exists only after explicit approval/execution path",
            }
        ]
    elif asks_pod and asks_restart:
        task_type = "pod_restart_rca"
        tool_steps = [
            {
                "step": 1,
                "tool": "openshift_event_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "event",
                "reason": "재시작 시점 주변 Event와 reason을 먼저 확인",
            },
            {
                "step": 2,
                "tool": "openshift_pod_status_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "pod_status",
                "reason": "restartCount, lastState, container 상태 확인",
            },
            {
                "step": 3,
                "tool": "openshift_pod_log_tail",
                "adapter": "OpenShift",
                "verb": "get",
                "evidence_type": "pod_log",
                "reason": "Event만으로 부족한 애플리케이션 종료 원인 확인",
            },
        ]
        missing = [
            {"type": "metric", "reason": "Prometheus metric query is not wired in ver.0.1.1 slice 1"},
            {"type": "runbook", "reason": "RAG/runbook retrieval is planned for a later 0.1.1 slice"},
        ]
    elif asks_pod and asks_count:
        task_type = "pod_inventory"
        tool_steps = [
            {
                "step": 1,
                "tool": "openshift_deployment_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "deployment",
                "reason": "Deployment selector와 Pod 매칭 기준 확인",
            },
            {
                "step": 2,
                "tool": "openshift_pod_list",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "pod_status",
                "reason": "접근 가능한 Pod 목록과 ready/running 상태 확인",
            },
        ]
        missing = [{"type": "metric", "reason": "pod usage metrics are optional for inventory questions"}]
    elif asks_operator:
        task_type = "cluster_operator_status"
        tool_steps = [
            {
                "step": 1,
                "tool": "openshift_clusteroperator_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "clusteroperator",
                "reason": "Available/Progressing/Degraded condition 확인",
            },
            {
                "step": 2,
                "tool": "openshift_clusterversion_lookup",
                "adapter": "OpenShift",
                "verb": "get",
                "evidence_type": "clusterversion",
                "reason": "업그레이드 차단/버전 상태 확인",
            },
        ]
        missing = [{"type": "runbook", "reason": "operator별 runbook retrieval is not configured"}]
    elif asks_cronjob:
        task_type = "cronjob_activity"
        tool_steps = [
            {
                "step": 1,
                "tool": "openshift_cronjob_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "cronjob",
                "reason": "schedule, suspend, concurrencyPolicy 확인",
            },
            {
                "step": 2,
                "tool": "openshift_job_event_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "event",
                "reason": "반복 실행 여부와 최근 Job 이벤트 확인",
            },
        ]
        missing = [{"type": "metric", "reason": "cronjob duration metrics are not wired yet"}]
    else:
        task_type = "openshift_operational_question"
        tool_steps = [
            {
                "step": 1,
                "tool": "openshift_context_inspection",
                "adapter": "OpenShift",
                "verb": "get",
                "evidence_type": "openshift_api",
                "reason": "현재 콘솔 컨텍스트와 접근 가능한 리소스 기준으로 안전하게 확인",
            },
            {
                "step": 2,
                "tool": "lightspeed_streaming_query",
                "adapter": "OpenShift Lightspeed",
                "verb": "get",
                "evidence_type": "openshift",
                "reason": "수집된 Gateway context를 포함해 최종 설명 생성",
            },
        ]
        missing = [{"type": "runbook", "reason": "question-specific runbook retrieval is not configured"}]

    plan = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "ToolPlan",
        "metadata": {
            "generatedAt": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "planner": "deterministic_gateway_planner",
            "version": "0.1.1",
        },
        "task_type": task_type,
        "target": {
            "platform": "openshift",
            "namespace": namespace or "all-accessible-namespaces",
        },
        "execution_policy": {
            "mode": "read_only",
            "requestedUiMode": execution_mode,
            "allowed_verbs": sorted(READ_ONLY_VERBS),
            "forbidden_actions": list(FORBIDDEN_ACTIONS),
        },
        "tool_plan": tool_steps,
        "missing_evidence": missing,
    }
    plan["validation"] = assert_read_only_tool_plan(plan)
    return plan


def build_runtime_safety_contract(
    *,
    mutations_enabled: bool,
    unrestricted_commands_enabled: bool,
    diagnostics_enabled: bool,
    record_store_enabled: bool,
    latest_runtime_tool_plan: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mode = "controlled_execution" if mutations_enabled else "read_only"
    tool_plan_status = {
        "source": "deterministic_gateway_planner",
        "status": "runtime_ready" if latest_runtime_tool_plan else "waiting_for_first_question",
        "latestRuntimePlan": dict(latest_runtime_tool_plan) if latest_runtime_tool_plan else None,
    }
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
        "toolPlanStatus": tool_plan_status,
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
