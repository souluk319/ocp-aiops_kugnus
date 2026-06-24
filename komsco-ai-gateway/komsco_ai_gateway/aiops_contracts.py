from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
import json
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

OPENSHIFT_ADAPTER_TOOLS = (
    {
        "tool": "openshift_event_lookup",
        "status": "available",
        "verbs": ["list"],
        "evidenceTypes": ["event"],
        "description": "Read namespaced OpenShift Events through the user-scoped API token.",
    },
    {
        "tool": "openshift_pod_status_lookup",
        "status": "available",
        "verbs": ["list"],
        "evidenceTypes": ["pod_status"],
        "description": "Read Pod phase, container readiness, restart counts, and last state.",
    },
    {
        "tool": "openshift_pod_log_tail",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["pod_log"],
        "description": "Read Pod logs when the user token has log access.",
    },
    {
        "tool": "openshift_deployment_lookup",
        "status": "available",
        "verbs": ["list", "get"],
        "evidenceTypes": ["deployment"],
        "description": "Read Deployment selectors and rollout status.",
    },
    {
        "tool": "openshift_clusteroperator_lookup",
        "status": "available",
        "verbs": ["list"],
        "evidenceTypes": ["clusteroperator"],
        "description": "Read ClusterOperator Available/Progressing/Degraded conditions.",
    },
    {
        "tool": "openshift_clusterversion_lookup",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["clusterversion"],
        "description": "Read ClusterVersion update and upgrade-blocking state.",
    },
    {
        "tool": "openshift_cronjob_lookup",
        "status": "available",
        "verbs": ["list"],
        "evidenceTypes": ["cronjob"],
        "description": "Read CronJob schedule, suspend, and recent job state.",
    },
)

LINUX_ADAPTER_TOOLS = (
    "journalctl_readonly_tail",
    "systemctl_status_readonly",
    "dmesg_readonly_tail",
    "df_readonly",
    "free_readonly",
)

WINDOWS_ADAPTER_TOOLS = (
    "get_winevent_readonly",
    "get_service_readonly",
    "get_counter_readonly",
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
                "cronjob",
                "deployment",
                "openshift",
            }
        ),
    },
    {"type": "metric", "matches": frozenset({"metric", "prometheus", "usage"})},
    {"type": "runbook", "matches": frozenset({"runbook", "rag_reference", "procedure"})},
    {"type": "audit", "matches": frozenset({"audit", "record", "execution_record"})},
)

NAMESPACE_MENTION_RE = re.compile(r"\b(?P<namespace>[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?)\s*네임스페이스")


def build_adapter_registry(
    *,
    diagnostics_enabled: bool,
    diagnostics_controller_configured: bool = False,
) -> list[dict[str, Any]]:
    linux_status = "diagnostics_ready" if diagnostics_enabled and diagnostics_controller_configured else "disabled"
    linux_reason = (
        "Linux host diagnostics controller is configured and diagnostics gate is enabled."
        if linux_status == "diagnostics_ready"
        else (
            "Diagnostics gate is enabled, but host diagnostics controller URL is not configured."
            if diagnostics_enabled
            else "KOMSCO_AI_DIAGNOSTICS_ENABLED is false; Linux host diagnostics stay disabled."
        )
    )
    linux_next_action = (
        "Submit diagnostics requests through the approved collector API."
        if linux_status == "diagnostics_ready"
        else "Enable diagnostics and configure KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_URL before Linux collectors can run."
    )

    return [
        {
            "name": "OpenShift",
            "type": "openshift",
            "status": "available",
            "reason": "UserToken-scoped read-only OpenShift API observation is available.",
            "detail": "UserToken-scoped read-only cluster observation",
            "nextAction": "Resolve Tool Plan steps to OpenShift read-only API calls.",
            "supportedTools": [dict(tool) for tool in OPENSHIFT_ADAPTER_TOOLS],
            "disabledReason": "",
            "requirements": ["valid OpenShift user token", "read-only RBAC for requested resource"],
        },
        {
            "name": "Linux",
            "type": "linux",
            "status": linux_status,
            "reason": linux_reason,
            "detail": "host diagnostics adapter remains approval-gated",
            "nextAction": linux_next_action,
            "supportedTools": [
                {
                    "tool": tool,
                    "status": linux_status,
                    "verbs": ["get"],
                    "evidenceTypes": ["host_diagnostics"],
                    "description": "Linux host read-only diagnostics collector capability.",
                    "disabledReason": "" if linux_status == "diagnostics_ready" else linux_reason,
                }
                for tool in LINUX_ADAPTER_TOOLS
            ],
            "disabledReason": "" if linux_status == "diagnostics_ready" else linux_reason,
            "requirements": [
                "diagnostics gate enabled",
                "host diagnostics controller URL configured",
                "approved collector profile",
            ],
        },
        {
            "name": "Windows",
            "type": "windows",
            "status": "planned",
            "reason": "Windows event/service adapter is design scope only in Ver.0.1.1.",
            "detail": "Windows event adapter is design scope, not runtime-ready",
            "nextAction": "Define a Windows node agent or remote event bridge before exposing runtime results.",
            "supportedTools": [
                {
                    "tool": tool,
                    "status": "planned",
                    "verbs": ["get"],
                    "evidenceTypes": ["windows_event", "windows_service"],
                    "description": "Planned Windows read-only observation capability.",
                    "disabledReason": "Windows adapter has no runtime collector or credential bridge yet.",
                }
                for tool in WINDOWS_ADAPTER_TOOLS
            ],
            "disabledReason": "Windows adapter has no runtime collector or credential bridge yet.",
            "requirements": ["Windows node agent", "read-only event log credential", "network path from Gateway"],
        },
    ]


def _adapter_key(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    if normalized in {"openshift", "ocp"}:
        return "openshift"
    if normalized in {"linux", "hostlinux"}:
        return "linux"
    if normalized in {"windows", "win"}:
        return "windows"
    return normalized


def resolve_tool_plan_adapters(
    tool_plan: Mapping[str, Any] | None,
    *,
    adapter_registry: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    registry = adapter_registry or build_adapter_registry(
        diagnostics_enabled=False,
        diagnostics_controller_configured=False,
    )
    adapters = {_adapter_key(adapter.get("name")): adapter for adapter in registry}
    resolutions: list[dict[str, Any]] = []

    for step in _as_list((tool_plan or {}).get("tool_plan")):
        if not isinstance(step, Mapping):
            continue
        adapter_name = str(step.get("adapter") or "")
        adapter_key = _adapter_key(adapter_name)
        tool = str(step.get("tool") or "")
        base = {
            "step": step.get("step"),
            "tool": tool,
            "adapter": adapter_name,
            "verb": step.get("verb"),
            "evidenceType": step.get("evidence_type"),
        }
        adapter = adapters.get(adapter_key)
        if not adapter:
            resolutions.append(
                {
                    **base,
                    "status": "not_os_adapter",
                    "resolved": False,
                    "reason": f"{adapter_name or 'unknown'} is not part of the OS-aware adapter registry.",
                }
            )
            continue

        capability = next(
            (
                item
                for item in _as_list(adapter.get("supportedTools"))
                if isinstance(item, Mapping) and item.get("tool") == tool
            ),
            None,
        )
        if not capability:
            resolutions.append(
                {
                    **base,
                    "status": "unsupported_tool",
                    "resolved": False,
                    "reason": f"{tool} is not listed under {adapter.get('name')} supported tools.",
                }
            )
            continue

        capability_status = str(capability.get("status") or adapter.get("status") or "unknown")
        resolved = capability_status in {"available", "diagnostics_ready"}
        resolutions.append(
            {
                **base,
                "status": "resolved" if resolved else capability_status,
                "resolved": resolved,
                "capability": capability.get("tool"),
                "reason": (
                    f"{tool} resolves to {adapter.get('name')} adapter capability."
                    if resolved
                    else str(capability.get("disabledReason") or adapter.get("disabledReason") or adapter.get("reason"))
                ),
            }
        )

    return resolutions


def _canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def create_evidence_status(collection: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
    collection = collection or {}
    evidence = _as_list(collection.get("evidence")) or _as_list(collection.get("collectedRefs"))
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


def _evidence_type_from_ref(ref: Mapping[str, Any]) -> str:
    explicit_type = str(ref.get("type") or "").strip().lower()
    if explicit_type:
        return explicit_type

    event_name = str(ref.get("eventName") or ref.get("name") or "").lower()
    source_type = str(ref.get("sourceType") or "").lower()
    summary = str(ref.get("summary") or "").lower()
    detail = str(ref.get("detail") or "").lower()
    combined = " ".join([event_name, source_type, summary, detail])

    if "cluster_operator" in combined or "clusteroperator" in combined:
        return "clusteroperator"
    if "pod_count" in combined or "pod count" in combined or "pod inventory" in combined:
        return "pod_status"
    if "pod_status" in combined or "pod status" in combined:
        return "pod_status"
    if "cronjob" in combined:
        return "cronjob"
    if "deployment" in combined:
        return "deployment"
    if "metric" in combined or "prometheus" in combined:
        return "metric"
    if "runbook" in combined or "rag" in combined:
        return "runbook"
    if "audit" in combined:
        return "audit"
    if "ols-tool-result" in source_type or "lightspeed" in combined:
        return "openshift"
    return "openshift"


def _normalize_evidence_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    normalized = {
        "collectedAt": ref.get("collectedAt"),
        "contentDigest": ref.get("contentDigest"),
        "evidenceId": ref.get("evidenceId"),
        "freshnessTtl": ref.get("freshnessTtl"),
        "sourceType": ref.get("sourceType"),
        "status": ref.get("eventStatus") or ref.get("status") or "recorded",
        "summary": ref.get("summary") or ref.get("eventName") or "evidence",
        "type": _evidence_type_from_ref(ref),
    }
    return {key: value for key, value in normalized.items() if value not in {None, ""}}


def _is_collected_evidence_ref(ref: Mapping[str, Any]) -> bool:
    status = str(ref.get("status") or "").lower()
    return status in {"recorded", "success", "succeeded", "ok", "completed"}


def build_rca_context(
    *,
    message: str,
    tool_plan: Mapping[str, Any] | None,
    evidence_refs: list[Mapping[str, Any]] | None = None,
    page_context: Mapping[str, Any] | None = None,
    run_id: str | None = None,
    incident_id: str | None = None,
    phase: str = "pre_answer",
) -> dict[str, Any]:
    plan = tool_plan or {}
    refs = [_normalize_evidence_ref(ref) for ref in evidence_refs or []]
    collected_refs = [ref for ref in refs if _is_collected_evidence_ref(ref)]
    failed_refs = [ref for ref in refs if not _is_collected_evidence_ref(ref)]
    missing_evidence = [
        dict(item)
        for item in _as_list(plan.get("missing_evidence"))
        if isinstance(item, Mapping)
    ]
    for ref in failed_refs:
        missing_evidence.append(
            {
                "contentDigest": ref.get("contentDigest"),
                "evidenceId": ref.get("evidenceId"),
                "reason": f"{ref.get('summary', 'evidence')} returned status {ref.get('status')}",
                "type": ref.get("type", "openshift"),
            }
        )
    if not collected_refs:
        missing_evidence.append(
            {
                "type": "openshift",
                "reason": "no runtime evidence reference has been recorded for this chat run yet",
            }
        )

    page_context = page_context or {}
    target = plan.get("target") if isinstance(plan.get("target"), Mapping) else {}
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    context: dict[str, Any] = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "RcaContext",
        "metadata": {
            "generatedAt": generated_at,
            "incidentId": incident_id,
            "phase": phase,
            "planner": str(plan.get("metadata", {}).get("planner", "deterministic_gateway_planner"))
            if isinstance(plan.get("metadata"), Mapping)
            else "deterministic_gateway_planner",
            "runId": run_id,
            "version": "0.1.1",
        },
        "question": {
            "digest": _canonical_digest({"message": message}),
            "pageContext": {
                key: page_context.get(key)
                for key in ("namespace", "resourceKind", "resourceName", "route", "pathname")
                if page_context.get(key)
            },
            "taskType": plan.get("task_type", "generic_openshift_question"),
            "target": dict(target),
        },
        "evidence": {
            "collectedRefs": collected_refs,
            "failedRefs": failed_refs,
            "missing": missing_evidence,
            "summary": {
                "collectedCount": len(collected_refs),
                "failedCount": len(failed_refs),
                "missingCount": len(missing_evidence),
            },
        },
        "evidence_refs": refs,
        "safety": {
            "mode": plan.get("execution_policy", {}).get("mode", "read_only")
            if isinstance(plan.get("execution_policy"), Mapping)
            else "read_only",
            "validation": plan.get("validation", {"ok": False, "violations": ["tool plan missing"]}),
        },
        "confidence": {
            "level": "evidence_based" if collected_refs else "insufficient_evidence",
            "reason": (
                "runtime evidence references are attached"
                if collected_refs
                else "missing runtime evidence prevents confirmation"
            ),
        },
    }
    digest = _canonical_digest(context)
    context["metadata"]["digest"] = digest
    context["metadata"]["contextId"] = f"rca-{digest.removeprefix('sha256:')[:16]}"
    return context


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
    plan["adapter_resolution"] = resolve_tool_plan_adapters(plan)
    return plan


def build_runtime_safety_contract(
    *,
    mutations_enabled: bool,
    unrestricted_commands_enabled: bool,
    diagnostics_enabled: bool,
    record_store_enabled: bool,
    diagnostics_controller_configured: bool = False,
    latest_runtime_tool_plan: Mapping[str, Any] | None = None,
    latest_rca_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mode = "controlled_execution" if mutations_enabled else "read_only"
    adapter_registry = build_adapter_registry(
        diagnostics_enabled=diagnostics_enabled,
        diagnostics_controller_configured=diagnostics_controller_configured,
    )
    latest_context = dict(latest_rca_context) if latest_rca_context else None
    tool_plan_status = {
        "source": "deterministic_gateway_planner",
        "status": "runtime_ready" if latest_runtime_tool_plan else "waiting_for_first_question",
        "latestRuntimePlan": dict(latest_runtime_tool_plan) if latest_runtime_tool_plan else None,
        "adapterResolution": resolve_tool_plan_adapters(
            latest_runtime_tool_plan,
            adapter_registry=adapter_registry,
        )
        if latest_runtime_tool_plan
        else [],
    }
    context_evidence = latest_context.get("evidence", {}) if latest_context else {}
    rca_context_status = {
        "digest": latest_context.get("metadata", {}).get("digest") if latest_context else None,
        "latestContext": latest_context,
        "source": "chat_stream",
        "status": "available" if latest_context else "waiting_for_first_question",
    }
    return {
        "product": PRODUCT_CONTRACT,
        "mode": mode,
        "allowedReadOnlyVerbs": sorted(READ_ONLY_VERBS),
        "forbiddenActions": list(FORBIDDEN_ACTIONS),
        "evidenceStatus": create_evidence_status(context_evidence),
        "capabilityGates": {
            "mutationsEnabled": mutations_enabled,
            "unrestrictedCommandsEnabled": unrestricted_commands_enabled,
            "diagnosticsEnabled": diagnostics_enabled,
            "recordStoreEnabled": record_store_enabled,
        },
        "toolPlanStatus": tool_plan_status,
        "rcaContextStatus": rca_context_status,
        "adapterStatus": adapter_registry,
        "lightspeedStatus": {
            "status": "configured",
            "streamProbe": "not_probed_by_status_endpoint",
            "baseService": "openshift-lightspeed/lightspeed-app-server:8443",
        },
    }
