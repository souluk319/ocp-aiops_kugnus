from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Any

PRODUCT_CONTRACT = {
    "name": "Cywell AI",
    "mode": "evidence_first_execution",
    "mission": "Evidence-first OpenShift operations assistant for catalog registration work.",
}

EVIDENCE_VERBS = frozenset({"get", "list", "watch"})
FORBIDDEN_ACTIONS = (
    "apply",
    "create",
    "update",
    "replace",
    "patch",
    "delete",
    "exec",
    "portforward",
    "restart",
    "scale",
    "rollout",
    "label",
    "annotate",
    "cordon",
    "drain",
    "uncordon",
)

OPENSHIFT_ADAPTER_TOOLS = (
    {
        "tool": "openshift_context_inspection",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["openshift_api"],
        "description": "Read the current OpenShift console context and accessible resource summary.",
    },
    {
        "tool": "lightspeed_streaming_query",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["openshift"],
        "description": "Ask OpenShift Lightspeed with Gateway-provided evidence-check context.",
    },
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
        "evidenceTypes": ["pod_status", "snapshot"],
        "description": "Read Pod phase, container readiness, restart counts, and last state.",
    },
    {
        "tool": "openshift_pod_snapshot_lookup",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["snapshot"],
        "description": "Read a point-in-time Pod/OCP snapshot for Evidence RCA scene context.",
    },
    {
        "tool": "openshift_pod_list",
        "status": "available",
        "verbs": ["list"],
        "evidenceTypes": ["pod_status"],
        "description": "Read accessible Pods and ready/running status for inventory questions.",
    },
    {
        "tool": "openshift_pod_log_pattern_probe",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["pod_log"],
        "description": "Probe previous Pod logs for safe pattern/digest evidence without exposing raw log text.",
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
        "tool": "openshift_node_status_lookup",
        "status": "available",
        "verbs": ["list"],
        "evidenceTypes": ["node"],
        "description": "Read Node Ready and pressure conditions for RCA correlation.",
    },
    {
        "tool": "openshift_alert_lookup",
        "status": "available",
        "verbs": ["list"],
        "evidenceTypes": ["alert"],
        "description": "Read active alerts for RCA correlation through the monitoring path.",
    },
    {
        "tool": "openshift_metric_query",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["metric"],
        "description": "Read Prometheus/Thanos metrics for RCA correlation.",
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
    {
        "tool": "openshift_job_event_lookup",
        "status": "available",
        "verbs": ["list"],
        "evidenceTypes": ["event"],
        "description": "Read recent Job events related to CronJob activity.",
    },
)

AI_GATEWAY_ADAPTER_TOOLS = (
    {
        "tool": "gateway_rag_runbook_search",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["runbook"],
        "description": "Search Gateway-controlled pgvector/RAG runbook evidence for RCA correlation.",
    },
    {
        "tool": "gateway_pending_action_plan_lookup",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["audit"],
        "description": "Read pending action plans from the local AI Gateway audit context.",
    },
    {
        "tool": "gateway_safety_policy_check",
        "status": "available",
        "verbs": ["get"],
        "evidenceTypes": ["audit"],
        "description": "Read AI Gateway safety gates before any action candidate is shown.",
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
                "alert",
                "namespace",
                "node",
                "pod",
                "pod_status",
                "pod_log",
                "event",
                "snapshot",
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

NAMESPACE_NAME_PATTERN = r"[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?"
NAMESPACE_MENTION_RES = (
    re.compile(
        rf"\b(?P<namespace>{NAMESPACE_NAME_PATTERN})\s*(?:namespace|네임스페이스)",
        re.IGNORECASE,
    ),
    re.compile(
        rf"(?:namespace|네임스페이스)\s*(?P<namespace>{NAMESPACE_NAME_PATTERN})\b",
        re.IGNORECASE,
    ),
)


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
            "reason": "UserToken-scoped evidence-check OpenShift API observation is available.",
            "detail": "UserToken-scoped evidence-check cluster observation",
            "nextAction": "Resolve Tool Plan steps to OpenShift evidence-check API calls.",
            "supportedTools": [dict(tool) for tool in OPENSHIFT_ADAPTER_TOOLS],
            "disabledReason": "",
            "requirements": ["valid OpenShift user token", "evidence-check RBAC for requested resource"],
        },
        {
            "name": "AI Gateway",
            "type": "ai_gateway",
            "status": "available",
            "reason": "Local Gateway safety and pending action plan inspection is available.",
            "detail": "local Gateway evidence-check audit and safety contract",
            "nextAction": "Resolve Tool Plan steps to local Gateway evidence-check audit checks.",
            "supportedTools": [dict(tool) for tool in AI_GATEWAY_ADAPTER_TOOLS],
            "disabledReason": "",
            "requirements": ["local Gateway process", "evidence-check safety gates"],
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
                    "tool": "gateway_rag_runbook_search",
                    "status": "available",
                    "verbs": ["get"],
                    "evidenceTypes": ["linux_service_log", "runbook"],
                    "description": "Search Gateway RAG runbooks for Linux service diagnosis without running host commands.",
                    "disabledReason": "",
                },
            ]
            + [
                {
                    "tool": tool,
                    "status": linux_status,
                    "verbs": ["get"],
                    "evidenceTypes": ["host_diagnostics"],
                    "description": "Linux host evidence-check diagnostics collector capability.",
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
                    "tool": "gateway_rag_runbook_search",
                    "status": "available",
                    "verbs": ["get"],
                    "evidenceTypes": ["windows_event_log", "runbook"],
                    "description": "Search Gateway RAG runbooks for Windows event diagnosis without running host commands.",
                    "disabledReason": "",
                },
            ]
            + [
                {
                    "tool": tool,
                    "status": "planned",
                    "verbs": ["get"],
                    "evidenceTypes": ["windows_event", "windows_service"],
                    "description": "Planned Windows evidence-check observation capability.",
                    "disabledReason": "Windows adapter has no runtime collector or credential bridge yet.",
                }
                for tool in WINDOWS_ADAPTER_TOOLS
            ],
            "disabledReason": "Windows adapter has no runtime collector or credential bridge yet.",
            "requirements": ["Windows node agent", "evidence-check event log credential", "network path from Gateway"],
        },
    ]


def _adapter_key(value: Any) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "", str(value or "").lower())
    if normalized in {"openshift", "ocp"}:
        return "openshift"
    if normalized in {"openshiftlightspeed", "lightspeed", "ols"}:
        return "openshift"
    if normalized in {"aigateway", "gateway", "localgateway"}:
        return "ai_gateway"
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
    partial = _as_list(collection.get("partialRefs"))
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
        partial_count = sum(
            1
            for item in partial
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
            status.append(
                {
                    "type": group_type,
                    "status": "collected",
                    "count": count,
                    "partialCount": partial_count,
                }
            )
        elif partial_count > 0:
            status.append(
                {
                    "type": group_type,
                    "status": "partial",
                    "count": 0,
                    "partialCount": partial_count,
                    "reason": "one or more evidence sources returned partial data",
                }
            )
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
    explicit_type = str(
        ref.get("evidenceType") or ref.get("evidence_type") or ref.get("type") or ""
    ).strip().lower()
    if explicit_type and explicit_type not in {"tool_call", "tool_result", "text"}:
        return explicit_type

    event_name = str(ref.get("eventName") or ref.get("name") or "").lower()
    source_type = str(ref.get("sourceType") or "").lower()
    summary = str(ref.get("summary") or "").lower()
    detail = str(ref.get("detail") or "").lower()
    combined = " ".join([event_name, source_type, summary, detail])

    if "cluster_operator" in combined or "clusteroperator" in combined:
        return "clusteroperator"
    if (
        "node_status" in combined
        or "node status" in combined
        or "node pressure" in combined
        or "/api/v1/nodes" in combined
        or "node rca" in combined
    ):
        return "node"
    if (
        "active_alert" in combined
        or "active alert" in combined
        or "alertname" in combined
        or "alerts{" in combined
        or "alert evidence" in combined
    ):
        return "alert"
    if "pod_count" in combined or "pod count" in combined or "pod inventory" in combined:
        return "pod_status"
    if "pod_status" in combined or "pod status" in combined:
        return "pod_status"
    if "snapshot" in combined:
        return "snapshot"
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
        "evidenceType": ref.get("evidenceType") or ref.get("evidence_type"),
        "freshnessTtl": ref.get("freshnessTtl"),
        "missingReason": ref.get("missingReason") or ref.get("reason"),
        "byteCount": ref.get("byteCount"),
        "lineCount": ref.get("lineCount"),
        "matchedPatternIds": ref.get("matchedPatternIds"),
        "patternCounts": ref.get("patternCounts"),
        "rawLogDisclosure": ref.get("rawLogDisclosure"),
        "sourcePath": ref.get("sourcePath"),
        "sourceType": ref.get("sourceType"),
        "status": ref.get("eventStatus") or ref.get("status") or "recorded",
        "summary": ref.get("summary") or ref.get("eventName") or "evidence",
        "timeWindow": ref.get("timeWindow"),
        "type": _evidence_type_from_ref(ref),
    }
    return {key: value for key, value in normalized.items() if value is not None and value != ""}


def _evidence_ref_status_bucket(ref: Mapping[str, Any]) -> str:
    status = str(ref.get("status") or "").lower()
    if status in {"recorded", "success", "succeeded", "ok", "completed", "collected"}:
        return "collected"
    if status == "partial":
        return "partial"
    return "failed"


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
    collected_refs = [ref for ref in refs if _evidence_ref_status_bucket(ref) == "collected"]
    partial_refs = [ref for ref in refs if _evidence_ref_status_bucket(ref) == "partial"]
    failed_refs = [ref for ref in refs if _evidence_ref_status_bucket(ref) == "failed"]
    covered_types = {
        str(ref.get("type") or "").lower()
        for ref in [*collected_refs, *partial_refs]
        if ref.get("type")
    }
    missing_evidence = [
        dict(item)
        for item in _as_list(plan.get("missing_evidence"))
        if isinstance(item, Mapping)
        and str(item.get("type") or "").lower() not in covered_types
    ]
    for ref in failed_refs:
        ref_type = str(ref.get("type") or "openshift").lower()
        if ref_type in covered_types:
            continue
        missing_evidence.append(
            {
                "contentDigest": ref.get("contentDigest"),
                "evidenceId": ref.get("evidenceId"),
                "reason": ref.get("missingReason")
                or f"{ref.get('summary', 'evidence')} returned status {ref.get('status')}",
                "type": ref_type,
            }
        )
    if not collected_refs and not partial_refs:
        missing_evidence.append(
            {
                "type": "openshift",
                "reason": "no runtime evidence reference has been recorded for this chat run yet",
            }
        )

    page_context = page_context or {}
    target = plan.get("target") if isinstance(plan.get("target"), Mapping) else {}
    tool_steps = [dict(item) for item in _as_list(plan.get("tool_plan")) if isinstance(item, Mapping)]

    def step_execution_status(step: Mapping[str, Any]) -> dict[str, Any]:
        evidence_type = str(step.get("evidence_type") or "openshift")
        collected = next((ref for ref in collected_refs if ref.get("type") == evidence_type), None)
        if collected:
            return {
                "status": "collected",
                "evidenceId": collected.get("evidenceId"),
                "contentDigest": collected.get("contentDigest"),
                "sourcePath": collected.get("sourcePath") or collected.get("sourceType"),
            }

        partial = next((ref for ref in partial_refs if ref.get("type") == evidence_type), None)
        if partial:
            return {
                "status": "partial",
                "evidenceId": partial.get("evidenceId"),
                "contentDigest": partial.get("contentDigest"),
                "missingReason": partial.get("missingReason")
                or partial.get("summary")
                or "evidence source returned partial data",
                "sourcePath": partial.get("sourcePath") or partial.get("sourceType"),
            }

        failed = next((ref for ref in failed_refs if ref.get("type") == evidence_type), None)
        if failed:
            return {
                "status": "failed",
                "evidenceId": failed.get("evidenceId"),
                "contentDigest": failed.get("contentDigest"),
                "missingReason": failed.get("missingReason")
                or failed.get("summary")
                or failed.get("status"),
                "sourcePath": failed.get("sourcePath") or failed.get("sourceType"),
            }

        missing = next(
            (
                item
                for item in missing_evidence
                if str(item.get("type") or "").lower() == evidence_type.lower()
            ),
            None,
        )
        if missing:
            return {
                "status": "missing",
                "evidenceId": missing.get("evidenceId"),
                "contentDigest": missing.get("contentDigest"),
                "missingReason": missing.get("reason"),
            }

        return {
            "status": "not_attempted",
            "missingReason": f"{evidence_type} evidence was planned but not collected yet",
        }

    evidence_collection_steps = [
        {
            "step": step.get("step"),
            "tool": step.get("tool"),
            "adapter": step.get("adapter"),
            "evidenceType": step.get("evidence_type"),
            "reason": step.get("reason"),
            **step_execution_status(step),
        }
        for step in tool_steps
    ]
    query_plan = [
        {
            "step": item.get("step"),
            "tool": item.get("tool"),
            "adapter": item.get("adapter"),
            "evidenceType": item.get("evidenceType"),
            "reason": item.get("reason"),
            "status": item.get("status"),
        }
        for item in evidence_collection_steps
    ]
    official_tool_aliases = [
        str(step.get("official_tool"))
        for step in tool_steps
        if isinstance(step.get("official_tool"), str) and str(step.get("official_tool")).strip()
    ]
    generated_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    demo_cycle_context = page_context.get("aiopsDemoCycle")
    if not isinstance(demo_cycle_context, Mapping):
        demo_cycle_context = {}
    scenario_context = {
        key: demo_cycle_context.get(key)
        for key in (
            "candidateId",
            "candidateStatusLabel",
            "findingId",
            "findingTitle",
            "evidenceOnly",
            "scenarioId",
            "selectedAt",
            "source",
            "target",
        )
        if demo_cycle_context.get(key) is not None and demo_cycle_context.get(key) != ""
    }
    context: dict[str, Any] = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "RcaContext",
        "metadata": {
            "generatedAt": generated_at,
            "findingId": demo_cycle_context.get("findingId"),
            "incidentId": incident_id,
            "phase": phase,
            "planner": str(plan.get("metadata", {}).get("planner", "deterministic_gateway_planner"))
            if isinstance(plan.get("metadata"), Mapping)
            else "deterministic_gateway_planner",
            "runId": run_id,
            "scenarioId": demo_cycle_context.get("scenarioId"),
            "toolPlanDigest": _canonical_digest(plan),
            "version": "0.1.3",
        },
        "question": {
            "digest": _canonical_digest({"message": message}),
            "pageContext": {
                key: page_context.get(key)
                for key in ("namespace", "resourceKind", "resourceName", "route", "pathname")
                if page_context.get(key)
            },
            "scenarioContext": scenario_context,
            "taskType": plan.get("task_type", "generic_openshift_question"),
            "target": dict(target),
        },
        "analysisPlan": {
            "mode": "evidence_first",
            "evidenceCollectionSteps": evidence_collection_steps,
            "queryPlan": query_plan,
            "answerContract": {
                "format": "operations_rca_report",
                "requiredSections": [
                    "원인 후보",
                    "확인한 증적",
                    "권장 조치",
                    "추가 확인",
                    "재발 방지",
                ],
                "mustNotInventEvidence": True,
                "mustSeparateUnknowns": True,
                "mustNotExposeRawToolPlanInDefaultAnswer": True,
                "mustNotExecuteWithoutApproval": True,
                "supportedExecutionModes": ["evidence_check", "controlled_execution", "unrestricted"],
            },
            "stopConditions": [
                "required evidence source failed",
                "user token lacks requested read permission",
                "target resource is not identified",
            ],
        },
        "officialScene": {
            "name": "Evidence 기반 AI 장애 분석 시나리오",
            "questionExample": "어제 새벽에 default namespace Pod가 왜 재시작됐어?",
            "toolPlanAliases": official_tool_aliases,
            "requiredToolAliases": ["event_tool", "grep_tool", "metric_tool", "runbook_tool", "snapshot_tool"],
            "rcaContextContract": {
                "mustStructure": [
                    "collected evidence",
                    "root cause candidates",
                    "confidence",
                    "action candidates",
                    "lightspeed handoff",
                ],
                "rootCauseCandidates": [
                    "OOMKilled",
                    "Eviction",
                    "NodePressure",
                    "application error pattern",
                    "configuration or dependency failure",
                ],
                "actionCandidateMode": "proposal_only_evidence",
                "lightspeedHandoff": {
                    "includeRcaContext": True,
                    "includeRunbook": "when available",
                },
                "finalAnswerSections": ["RCA", "즉시 조치", "재발 방지책", "참고 증적"],
            },
        },
        "evidence": {
            "collectedRefs": collected_refs,
            "partialRefs": partial_refs,
            "failedRefs": failed_refs,
            "missing": missing_evidence,
            "summary": {
                "collectedCount": len(collected_refs),
                "partialCount": len(partial_refs),
                "failedCount": len(failed_refs),
                "missingCount": len(missing_evidence),
            },
        },
        "answerExperience": {
            "defaultAnswerMode": "human_rca",
            "detailView": "human_query_plan",
            "auditView": "raw_tool_plan_and_rca_context_json",
            "queryPlan": query_plan,
        },
        "causeCandidates": [
            {
                "basis": ["event_tool", "snapshot_tool", "metric_tool", "grep_tool"],
                "confidence": "candidate",
                "evidenceRequired": ["event", "snapshot", "metric", "pod_log"],
                "id": "oom-or-memory-pressure",
                "label": "OOMKilled 또는 Memory/Node Pressure",
                "status": "candidate_until_evidence_confirms",
            },
            {
                "basis": ["grep_tool", "snapshot_tool"],
                "confidence": "candidate",
                "evidenceRequired": ["pod_log", "snapshot"],
                "id": "application-error-pattern",
                "label": "애플리케이션 예외 또는 실행 명령 오류",
                "status": "candidate_until_log_pattern_confirms",
            },
            {
                "basis": ["event_tool", "snapshot_tool"],
                "confidence": "candidate",
                "evidenceRequired": ["event", "snapshot"],
                "id": "eviction-or-scheduling-pressure",
                "label": "Eviction, node pressure, scheduling 관련 영향",
                "status": "candidate_until_event_confirms",
            },
        ],
        "actionCandidates": [
            {
                "approvalRequired": True,
                "mode": "proposal_only_evidence",
                "risk": "medium",
                "title": "Event, snapshot, metric, log-pattern evidence를 먼저 확인",
            },
            {
                "approvalRequired": True,
                "mode": "proposal_only_evidence",
                "risk": "high",
                "title": "원인 확정 전 rollout/delete/patch/scale 실행 금지",
            },
        ],
        "evidence_refs": refs,
        "safety": {
            "mode": plan.get("execution_policy", {}).get("mode", "evidence_check")
            if isinstance(plan.get("execution_policy"), Mapping)
            else "evidence_check",
            "validation": plan.get("validation", {"ok": False, "violations": ["tool plan missing"]}),
        },
        "confidence": {
            "level": "evidence_based"
            if collected_refs
            else "partial_evidence"
            if partial_refs
            else "insufficient_evidence",
            "reason": (
                "runtime evidence references are attached"
                if collected_refs
                else "partial runtime evidence references are attached"
                if partial_refs
                else "missing runtime evidence prevents confirmation"
            ),
        },
    }
    digest = _canonical_digest(context)
    context["metadata"]["digest"] = digest
    context["metadata"]["contextId"] = f"rca-{digest.removeprefix('sha256:')[:16]}"
    return context


def assert_evidence_check_tool_plan(tool_plan: Mapping[str, Any] | None) -> dict[str, Any]:
    violations: list[str] = []
    plan = tool_plan or {}
    execution_policy = plan.get("execution_policy")

    if isinstance(execution_policy, Mapping):
        mode = str(execution_policy.get("mode", "")).lower()
        if mode and mode not in {"evidence_check", "controlled_execution", "unrestricted"}:
            violations.append("execution_policy.mode must be an AIOps execution policy mode")

    for step in _as_list(plan.get("tool_plan")):
        if not isinstance(step, Mapping):
            continue
        verb = str(step.get("verb", "")).lower()
        tool = str(step.get("tool", "")).lower()
        step_id = step.get("step", "unknown")

        if verb and verb not in EVIDENCE_VERBS:
            violations.append(f"step {step_id} uses non-evidence-collection verb {verb}")
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

    for pattern in NAMESPACE_MENTION_RES:
        match = pattern.search(message)
        if match:
            return match.group("namespace")
    return None


def build_runtime_tool_plan(
    message: str,
    *,
    page_context: Mapping[str, Any] | None = None,
    execution_mode: str = "execute",
) -> dict[str, Any]:
    requested_ui_mode = str(execution_mode or "execute").strip().lower()
    execution_policy_mode = (
        "unrestricted"
        if requested_ui_mode in {"unrestricted", "dev-unrestricted", "experimental", "실험", "무제한"}
        else "evidence_check"
        if requested_ui_mode in {"read-only", "read_only", "readonly", "evidence-check", "evidence_check", "점검", "조회"}
        else "controlled_execution"
    )
    namespace = _namespace_from_message(message, page_context)
    asks_pod = _message_has_any(message, ("pod", "pods", "파드"))
    asks_restart = _message_has_any(
        message,
        ("restart", "재시작", "crashloop", "crashloopbackoff", "imagepull", "backoff", "oom"),
    )
    asks_operator = _message_has_any(message, ("clusteroperator", "cluster operator", "오퍼레이터"))
    asks_cronjob = _message_has_any(message, ("cronjob", "cron job", "크론잡", "scheduled job"))
    asks_count = _message_has_any(
        message,
        (
            "count",
            "개수",
            "몇개",
            "몇 개",
            "떠있",
            "running",
            "ready",
            "notready",
            "not ready",
            "pending",
            "스케줄링",
            "scheduling",
            "scheduler",
            "taint",
            "toleration",
            "pvc",
            "affinity",
            "node selector",
        ),
    )
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
        (
            "올려",
            "늘려",
            "줄여",
            "변경",
            "스케일",
            "scale",
            "restart",
            "재시작",
            "롤백",
            "rollback",
            "조치",
            "대응",
            "action",
            "candidate",
        ),
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
                "reason": "evidence-check 기본 정책과 mutation gate 상태 확인",
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
                "official_tool": "event_tool",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "event",
                "reason": "재시작 시점 주변 Event와 reason을 먼저 확인",
            },
            {
                "step": 2,
                "tool": "openshift_pod_snapshot_lookup",
                "official_tool": "snapshot_tool",
                "adapter": "OpenShift",
                "verb": "get",
                "evidence_type": "snapshot",
                "reason": "Pod phase, container state, restartCount, lastState를 시점 스냅샷으로 구조화",
            },
            {
                "step": 3,
                "tool": "openshift_pod_status_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "pod_status",
                "reason": "restartCount, lastState, container 상태 확인",
            },
            {
                "step": 4,
                "tool": "openshift_pod_log_pattern_probe",
                "official_tool": "grep_tool",
                "adapter": "OpenShift",
                "verb": "get",
                "evidence_type": "pod_log",
                "reason": "Event만으로 부족한 애플리케이션 종료 원인을 원문 저장 없이 오류 패턴 중심으로 확인",
            },
            {
                "step": 5,
                "tool": "openshift_clusteroperator_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "clusteroperator",
                "reason": "관리 namespace 또는 platform component 영향 여부 확인",
            },
            {
                "step": 6,
                "tool": "openshift_node_status_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "node",
                "reason": "Node Ready/Pressure 상태가 Pod 이상에 영향을 주는지 확인",
            },
            {
                "step": 7,
                "tool": "openshift_alert_lookup",
                "adapter": "OpenShift",
                "verb": "list",
                "evidence_type": "alert",
                "reason": "관련 active alert가 RCA 우선순위에 영향을 주는지 확인",
            },
            {
                "step": 8,
                "tool": "openshift_metric_query",
                "official_tool": "metric_tool",
                "adapter": "OpenShift",
                "verb": "get",
                "evidence_type": "metric",
                "reason": "최근 restart 증가량, CPU/Memory 압력 같은 metric 근거 확인",
            },
            {
                "step": 9,
                "tool": "gateway_rag_runbook_search",
                "official_tool": "runbook_tool",
                "adapter": "AI Gateway",
                "verb": "get",
                "evidence_type": "runbook",
                "reason": "pgvector/RAG에 등록된 운영 Runbook을 검색해 RCA 조치 후보와 재발 방지 근거에 연결",
            },
        ]
        missing = [
            {
                "type": "clusteroperator",
                "reason": "ClusterOperator evidence may be included in pod status evidence, but is not a separate RCA evidence ref yet",
            },
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
    elif _message_has_any(
        message,
        ("journalctl", "systemctl", "dmesg", "linux service", "service crash", "서비스 오류", "서비스 장애"),
    ):
        task_type = "linux_service_diagnosis"
        tool_steps = [
            {
                "step": 1,
                "tool": "gateway_rag_runbook_search",
                "official_tool": "runbook_tool",
                "adapter": "linux",
                "verb": "get",
                "evidence_type": "linux_service_log",
                "reason": "Linux 서비스 장애 패턴 런북 조회",
            },
            {
                "step": 2,
                "tool": "lightspeed_streaming_query",
                "adapter": "OpenShift Lightspeed",
                "verb": "get",
                "evidence_type": "openshift",
                "reason": "수집된 런북 context를 포함해 Linux 서비스 진단 가이드 생성",
            },
        ]
        missing = [
            {
                "type": "linux_command_output",
                "reason": "Linux OS adapter not yet wired (v0.1.9+); journalctl/systemctl output unavailable",
            }
        ]
    elif _message_has_any(
        message,
        ("windows", "event log", "get-winevent", "iis", "윈도우", "윈도즈"),
    ):
        task_type = "windows_event_diagnosis"
        tool_steps = [
            {
                "step": 1,
                "tool": "gateway_rag_runbook_search",
                "official_tool": "runbook_tool",
                "adapter": "windows",
                "verb": "get",
                "evidence_type": "windows_event_log",
                "reason": "Windows 이벤트 장애 패턴 런북 조회",
            },
            {
                "step": 2,
                "tool": "lightspeed_streaming_query",
                "adapter": "OpenShift Lightspeed",
                "verb": "get",
                "evidence_type": "openshift",
                "reason": "수집된 런북 context를 포함해 Windows 이벤트 진단 가이드 생성",
            },
        ]
        missing = [
            {
                "type": "windows_command_output",
                "reason": "Windows OS adapter not yet wired (v0.1.9+); Get-WinEvent/Get-Content output unavailable",
            }
        ]
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
            "version": "0.1.3",
        },
        "task_type": task_type,
        "target": {
            "platform": "openshift",
            "namespace": namespace or "all-accessible-namespaces",
        },
        "execution_policy": {
            "mode": execution_policy_mode,
            "requestedUiMode": execution_mode,
            "allowed_verbs": sorted(EVIDENCE_VERBS),
            "forbidden_actions": list(FORBIDDEN_ACTIONS),
        },
        "tool_plan": tool_steps,
        "missing_evidence": missing,
    }
    plan["validation"] = assert_evidence_check_tool_plan(plan)
    plan["adapter_resolution"] = resolve_tool_plan_adapters(plan)
    return plan


def build_runtime_safety_contract(
    *,
    mutations_enabled: bool,
    unrestricted_commands_enabled: bool,
    diagnostics_enabled: bool,
    record_store_enabled: bool,
    diagnostics_controller_configured: bool = False,
    lightspeed_status: Mapping[str, Any] | None = None,
    latest_runtime_tool_plan: Mapping[str, Any] | None = None,
    latest_rca_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    mode = "controlled_execution" if mutations_enabled else "evidence_check"
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
        "allowedReadOnlyVerbs": sorted(EVIDENCE_VERBS),
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
            "baseService": "openshift-lightspeed/lightspeed-app-server:8443",
            **(dict(lightspeed_status) if lightspeed_status else {"streamProbe": "not_started"}),
        },
    }
