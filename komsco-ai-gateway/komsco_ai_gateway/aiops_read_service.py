import asyncio
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException


@dataclass(frozen=True)
class AiopsReadConfig:
    openshift_api_url: str
    openshift_api_ca_file: Any
    mutations_enabled: bool
    diagnostics_enabled: bool
    diagnostics_controller_url: str
    action_executor_url: str
    unrestricted_commands_enabled: bool
    record_store_enabled: bool
    record_store_configmap: str
    chat_transcript_jsonl_path: str
    latest_runtime_tool_plan: Mapping[str, Any] | None
    latest_rca_context: Mapping[str, Any] | None


@dataclass(frozen=True)
class AiopsRecordStores:
    chat_transcripts: Mapping[str, dict[str, Any]]
    chat_feedback: Mapping[str, dict[str, Any]]
    diagnostic_requests: Mapping[str, dict[str, Any]]
    action_proposals: Mapping[str, dict[str, Any]]
    sealed_action_plans: Mapping[str, dict[str, Any]]
    approval_decisions: Mapping[str, dict[str, Any]]
    execution_records: Mapping[str, dict[str, Any]]


@dataclass(frozen=True)
class AiopsReadDependencies:
    config: AiopsReadConfig
    stores: AiopsRecordStores
    lightspeed_status: Mapping[str, Any]
    verify_bearer_header: Callable[..., str]
    fetch_ocp_json: Callable[..., Any]
    fetch_ocp_json_observed: Callable[..., Any]
    build_cluster_summary: Callable[..., dict[str, Any]]
    monitoring_urls_from_config: Callable[..., dict[str, str]]
    probe_thanos_query: Callable[..., Any]
    query_thanos_instant: Callable[..., Any]
    data_source_status: Callable[..., dict[str, Any]]
    build_aiops_anomaly_summary: Callable[..., dict[str, Any]]
    build_aiops_overview: Callable[..., dict[str, Any]]
    aiops_overview: Callable[..., Any]
    merge_recent_namespace_cleanup_candidates: Callable[..., dict[str, Any]]
    fetch_self_subject_review: Callable[..., Any]
    fetch_product_access_review: Callable[..., Any]
    build_kubernetes_event_items: Callable[..., list[dict[str, Any]]]
    build_problem_pod_event_items: Callable[..., list[dict[str, Any]]]
    build_aiops_record_event_items: Callable[..., list[dict[str, Any]]]
    now_rfc3339: Callable[[], str]
    safe_subject: Callable[..., dict[str, Any]]
    build_skipped_product_access_review: Callable[..., dict[str, Any]]
    build_status_access_review_failure: Callable[..., dict[str, Any]]
    redact_sensitive: Callable[..., Any]
    build_rag_backend_status: Callable[[], dict[str, Any]]
    build_runtime_safety_contract: Callable[..., dict[str, Any]]
    latest_readable_audit_records: Callable[..., list[dict[str, Any]]]
    latest_readable_records: Callable[..., list[dict[str, Any]]]


async def cluster_summary(
    authorization: str | None,
    deps: AiopsReadDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    config = deps.config
    if not config.openshift_api_url:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    async with httpx.AsyncClient(
        verify=config.openshift_api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        payloads = await asyncio.gather(
            deps.fetch_ocp_json(client, "/api/v1/nodes", user_auth_header, required=True),
            deps.fetch_ocp_json(client, "/apis/metrics.k8s.io/v1beta1/nodes", user_auth_header),
            deps.fetch_ocp_json(
                client,
                "/apis/config.openshift.io/v1/clusterversions/version",
                user_auth_header,
            ),
            deps.fetch_ocp_json(
                client,
                "/apis/config.openshift.io/v1/clusteroperators",
                user_auth_header,
            ),
            deps.fetch_ocp_json(client, "/api/v1/pods", user_auth_header),
            deps.fetch_ocp_json(client, "/apis/apps/v1/deployments", user_auth_header),
            deps.fetch_ocp_json(client, "/apis/apps/v1/replicasets", user_auth_header),
            deps.fetch_ocp_json(client, "/apis/apps/v1/daemonsets", user_auth_header),
            deps.fetch_ocp_json(client, "/apis/apps/v1/statefulsets", user_auth_header),
            deps.fetch_ocp_json(client, "/api/v1/services", user_auth_header),
            deps.fetch_ocp_json(client, "/apis/route.openshift.io/v1/routes", user_auth_header),
            deps.fetch_ocp_json(client, "/api/v1/persistentvolumeclaims", user_auth_header),
            deps.fetch_ocp_json(client, "/api/v1/namespaces", user_auth_header),
        )

    return deps.build_cluster_summary(payloads[0] or {"items": []}, *payloads[1:])


async def aiops_overview(
    authorization: str | None,
    deps: AiopsReadDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    config = deps.config
    if not config.openshift_api_url:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    async with httpx.AsyncClient(
        verify=config.openshift_api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        nodes_payload, nodes_status = await deps.fetch_ocp_json_observed(
            client, "/api/v1/nodes", user_auth_header,
            label="Node inventory", name="nodes", required=True,
        )
        node_metrics_payload, metrics_status = await deps.fetch_ocp_json_observed(
            client, "/apis/metrics.k8s.io/v1beta1/nodes", user_auth_header,
            label="Node metrics", name="metrics.k8s.io",
        )
        cluster_version_payload, version_status = await deps.fetch_ocp_json_observed(
            client, "/apis/config.openshift.io/v1/clusterversions/version", user_auth_header,
            label="Cluster version", name="clusterversion",
        )
        cluster_operators_payload, operators_status = await deps.fetch_ocp_json_observed(
            client, "/apis/config.openshift.io/v1/clusteroperators", user_auth_header,
            label="Cluster operators", name="clusteroperators",
        )
        monitoring_config_payload, monitoring_config_status = await deps.fetch_ocp_json_observed(
            client,
            "/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config",
            user_auth_header,
            label="Monitoring public URLs", name="monitoring-shared-config",
        )
        pods_payload, pods_status = await deps.fetch_ocp_json_observed(
            client, "/api/v1/pods?limit=500", user_auth_header,
            label="Pod anomaly signals", name="pods", required=True,
        )
        events_payload, events_status = await deps.fetch_ocp_json_observed(
            client, "/api/v1/events?limit=500", user_auth_header,
            label="Warning events", name="events", required=True,
        )

    monitoring_urls = deps.monitoring_urls_from_config(monitoring_config_payload)
    thanos_url = monitoring_urls.get("thanos", "")
    monitoring_probe = await deps.probe_thanos_query(thanos_url, user_auth_header)
    alerts_probe = await deps.query_thanos_instant(
        thanos_url, user_auth_header, 'ALERTS{alertstate="firing"}',
    )
    restart_probe = await deps.query_thanos_instant(
        thanos_url,
        user_auth_header,
        "increase(kube_pod_container_status_restarts_total[1h]) > 0",
    )
    monitoring_probe_status = deps.data_source_status(
        label="Thanos query probe", name="thanos-query", path="/api/v1/query?query=up",
        payload=monitoring_probe if monitoring_probe.get("status") == "available" else None,
        reason=str(monitoring_probe.get("reason") or ""),
        status=str(monitoring_probe.get("status") or "unavailable"),
        http_status=monitoring_probe.get("httpStatus")
        if isinstance(monitoring_probe.get("httpStatus"), int) else None,
    )
    alerts_probe_status = deps.data_source_status(
        label="Active alerts", name="alerts",
        path='/api/v1/query?query=ALERTS{alertstate="firing"}',
        payload=alerts_probe if alerts_probe.get("status") == "available" else None,
        reason=str(alerts_probe.get("reason") or ""),
        status=str(alerts_probe.get("status") or "unavailable"),
        http_status=alerts_probe.get("httpStatus")
        if isinstance(alerts_probe.get("httpStatus"), int) else None,
    )
    restart_probe_status = deps.data_source_status(
        label="Restart increase metric", name="restart-metrics",
        path="/api/v1/query?query=increase(kube_pod_container_status_restarts_total[1h]) > 0",
        payload=restart_probe if restart_probe.get("status") == "available" else None,
        reason=str(restart_probe.get("reason") or ""),
        status=str(restart_probe.get("status") or "unavailable"),
        http_status=restart_probe.get("httpStatus")
        if isinstance(restart_probe.get("httpStatus"), int) else None,
    )

    summary = deps.build_cluster_summary(
        nodes_payload or {"items": []},
        node_metrics_payload,
        cluster_version_payload,
        cluster_operators_payload,
    )
    data_sources = [
        nodes_status, metrics_status, version_status, operators_status,
        monitoring_config_status, monitoring_probe_status, pods_status,
        events_status, alerts_probe_status, restart_probe_status,
    ]
    anomaly_summary = deps.build_aiops_anomaly_summary(
        summary, pods_payload, events_payload, alerts_probe, restart_probe, data_sources,
    )
    return deps.build_aiops_overview(
        summary, data_sources, monitoring_urls, monitoring_probe, anomaly_summary,
    )


async def aiops_anomalies(
    authorization: str | None,
    namespace: str | None,
    since_minutes: int,
    limit: int,
    deps: AiopsReadDependencies,
) -> dict[str, Any]:
    overview = await deps.aiops_overview(authorization)
    anomalies = overview.get("spec", {}).get("anomalies")
    if not isinstance(anomalies, dict):
        return {}

    filtered = dict(anomalies)
    spec = dict(filtered.get("spec", {})) if isinstance(filtered.get("spec"), Mapping) else {}
    findings = spec.get("findings") if isinstance(spec.get("findings"), list) else []
    if namespace:
        findings = [
            finding
            for finding in findings
            if isinstance(finding, Mapping)
            and (
                finding.get("namespace") == namespace
                or not finding.get("namespace")
                or str(finding.get("namespace")) == "cluster-scoped"
            )
        ]
    spec["findings"] = findings[:limit]
    spec["query"] = {
        "limit": limit,
        "namespace": namespace or "",
        "sinceMinutes": since_minutes,
    }
    filtered["spec"] = spec
    return filtered


async def aiops_action_candidates(
    authorization: str | None,
    deps: AiopsReadDependencies,
) -> dict[str, Any]:
    overview = await deps.aiops_overview(authorization)
    action_candidates = overview.get("spec", {}).get("actionCandidates")
    if not isinstance(action_candidates, dict):
        return {}
    return deps.merge_recent_namespace_cleanup_candidates(action_candidates)


async def get_aiops_events(
    authorization: str | None,
    limit: int,
    deps: AiopsReadDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    product_access_review = await deps.fetch_product_access_review(user_auth_header)
    product_access_allowed = bool(product_access_review.get("allowed"))

    events_payload: Mapping[str, Any] | None = None
    pods_payload: Mapping[str, Any] | None = None
    sources = ["AIOps Gateway"]
    config = deps.config
    if config.openshift_api_url:
        async with httpx.AsyncClient(
            verify=config.openshift_api_ca_file,
            timeout=httpx.Timeout(20.0, connect=5.0),
        ) as client:
            events_payload, pods_payload = await asyncio.gather(
                deps.fetch_ocp_json(client, "/api/v1/events?limit=500", user_auth_header),
                deps.fetch_ocp_json(client, "/api/v1/pods", user_auth_header),
            )
        sources.extend(["Kubernetes Event", "Pod status"])

    items = [
        *deps.build_kubernetes_event_items(events_payload, limit=limit),
        *deps.build_problem_pod_event_items(pods_payload, limit=limit),
        *deps.build_aiops_record_event_items(
            subject, product_access_allowed=product_access_allowed, limit=limit,
        ),
    ]
    items.sort(
        key=lambda item: (str(item.get("time") or ""), str(item.get("source") or "")),
        reverse=True,
    )
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsEventFeed",
        "metadata": {"generatedAt": deps.now_rfc3339(), "name": "activity-feed"},
        "spec": {"items": items[:limit], "pollIntervalSeconds": 30, "sources": sources},
    }


async def get_aiops_status(
    authorization: str | None,
    deps: AiopsReadDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    access_review_status: dict[str, Any] = {
        "status": "success",
        "recordsVisible": True,
        "reason": "",
    }
    try:
        subject = await deps.fetch_self_subject_review(user_auth_header)
    except HTTPException as exc:
        subject = deps.safe_subject(None)
        product_access_review = deps.build_skipped_product_access_review(
            "not evaluated because OpenShift subject review is unavailable"
        )
        product_access_allowed = False
        access_review_status = deps.build_status_access_review_failure(exc)
    else:
        product_access_review = await deps.fetch_product_access_review(user_auth_header)
        product_access_allowed = bool(product_access_review.get("allowed"))
        if product_access_review.get("evaluationError"):
            access_review_status = {
                "status": "degraded",
                "recordsVisible": product_access_allowed,
                "reason": "OpenShift product access review returned an evaluation error.",
                "productAccessReview": deps.redact_sensitive(product_access_review),
            }

    config = deps.config
    stores = deps.stores
    latest_records = deps.latest_readable_records
    records = {
        "auditRecords": deps.latest_readable_audit_records(
            subject, product_access_allowed=product_access_allowed,
        ),
        "chatTranscripts": latest_records(
            stores.chat_transcripts, subject, product_access_allowed=product_access_allowed,
        ),
        "chatFeedback": latest_records(
            stores.chat_feedback, subject, product_access_allowed=product_access_allowed,
        ),
        "diagnosticRequests": latest_records(
            stores.diagnostic_requests, subject, product_access_allowed=product_access_allowed,
        ),
        "actionProposals": latest_records(
            stores.action_proposals, subject, product_access_allowed=product_access_allowed,
        ),
        "sealedActionPlans": latest_records(
            stores.sealed_action_plans, subject, product_access_allowed=product_access_allowed,
        ),
        "approvalDecisions": latest_records(
            stores.approval_decisions, subject, product_access_allowed=product_access_allowed,
        ),
        "executionRecords": latest_records(
            stores.execution_records, subject, product_access_allowed=product_access_allowed,
        ),
    }
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsRuntimeStatus",
        "metadata": {"name": "runtime-status", "generatedAt": deps.now_rfc3339()},
        "spec": {
            "capabilities": {
                "mutationsEnabled": config.mutations_enabled,
                "diagnosticsEnabled": config.diagnostics_enabled,
                "diagnosticsControllerConfigured": bool(config.diagnostics_controller_url),
                "actionExecutorConfigured": bool(config.action_executor_url),
                "unrestrictedCommandsEnabled": config.unrestricted_commands_enabled,
                "recordStoreEnabled": config.record_store_enabled,
                "recordStoreConfigMap": config.record_store_configmap if config.record_store_enabled else "",
                "chatTranscriptJsonlPath": config.chat_transcript_jsonl_path,
                "rag": deps.build_rag_backend_status(),
            },
            "safetyContract": deps.build_runtime_safety_contract(
                mutations_enabled=config.mutations_enabled,
                unrestricted_commands_enabled=config.unrestricted_commands_enabled,
                diagnostics_enabled=config.diagnostics_enabled,
                record_store_enabled=config.record_store_enabled,
                diagnostics_controller_configured=bool(config.diagnostics_controller_url),
                lightspeed_status=deps.redact_sensitive(dict(deps.lightspeed_status)),
                latest_runtime_tool_plan=config.latest_runtime_tool_plan,
                latest_rca_context=config.latest_rca_context,
            ),
            "accessReviewStatus": access_review_status,
            "productAccessReview": deps.redact_sensitive(product_access_review),
            "subject": deps.redact_sensitive(dict(subject)),
            "records": records,
        },
    }
