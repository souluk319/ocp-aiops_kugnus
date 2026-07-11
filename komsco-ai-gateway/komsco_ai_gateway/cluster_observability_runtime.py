from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from .aiops_core import path_segment


AsyncCallback = Callable[..., Awaitable[Any]]
SyncCallback = Callable[..., Any]


@dataclass(frozen=True)
class ClusterObservabilityConfig:
    api_url: str
    api_ca_file: str | bool


@dataclass(frozen=True)
class ClusterObservabilityDependencies:
    fetch_ocp_json: AsyncCallback
    fetch_ocp_json_observed: AsyncCallback
    query_thanos_instant: AsyncCallback
    data_source_status: SyncCallback
    monitoring_urls_from_config: SyncCallback
    append_gateway_evidence: SyncCallback
    build_pod_status_evidence: SyncCallback
    build_deployment_rollout_evidence: SyncCallback
    build_cluster_operator_status_evidence: SyncCallback
    build_pod_count_investigation: SyncCallback
    build_cronjob_activity_evidence: SyncCallback
    build_node_status_rca_evidence: SyncCallback
    build_active_alerts_rca_evidence: SyncCallback
    build_restart_metric_rca_evidence: SyncCallback
    rca_probe_event_status: SyncCallback
    prometheus_probe_reason: SyncCallback
    safe_error_text: SyncCallback


def past_pod_restart_demo_prompt_contract(active: bool) -> str:
    if not active:
        return "적용 없음"
    return "\n".join(
        [
            "이 요청은 과거 시점 Pod 재시작 RCA 공식 Evidence 시연 사이클입니다.",
            "최종 답변에는 아래 5개 섹션명을 이 순서 그대로 포함하세요.",
            "1. `### 확인 결과`",
            "2. `### 가능한 원인 후보`",
            "3. `### 추가 확인 필요`",
            "4. `### Evidence-check 확인 순서`",
            "5. `### 금지 작업`",
            "수집된 증적(event/snapshot/pod_log/runbook)과 missing 증적(metric/clusteroperator)을 명확히 구분하세요.",
            "원인을 확정하지 말고 missing evidence가 있는 상태에서 조치 후보만 제시하세요.",
            "공식 최종 답변에는 `RCA`, `즉시 조치`, `재발 방지책`, `참고 증적` 관점을 포함하세요.",
            "`oc apply/delete/patch/scale/exec/rollout restart`는 코드블록에 넣지 말고 금지 작업 섹션에서만 언급하세요.",
        ]
    )


def collect_past_pod_restart_demo_evidence_events(
    request_id: str,
) -> list[dict[str, Any]]:
    """Return the fixed Scenario 11 OOMKilled evidence projection."""
    return [
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-event",
            "name": "openshift_event_lookup",
            "evidenceType": "event",
            "eventStatus": "success",
            "sourceType": "gateway-evidence",
            "status": "success",
            "summary": "Gateway-collected Pod Event evidence",
            "detail": (
                "openshift_event_lookup collected evidence — "
                "2026-06-28 02:14:33 KST · Namespace: default · "
                "Pod: webapp-deploy-7f94d-k8z2p · Reason: OOMKilled · "
                "Message: Container exceeded memory limit of 512Mi"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-snapshot",
            "name": "openshift_pod_snapshot_lookup",
            "evidenceType": "snapshot",
            "eventStatus": "success",
            "sourceType": "gateway-evidence",
            "status": "success",
            "summary": "Gateway-collected Pod snapshot evidence",
            "detail": (
                "openshift_pod_snapshot_lookup collected evidence — "
                "Pod webapp-deploy-7f94d-k8z2p: phase=Running, restartCount=3, "
                "lastState.terminated.reason=OOMKilled, "
                "lastState.terminated.finishedAt=2026-06-28T02:14:30Z, memoryLimit=512Mi"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-pod-status",
            "name": "openshift_pod_status_lookup",
            "evidenceType": "pod_status",
            "eventStatus": "success",
            "sourceType": "gateway-evidence",
            "status": "success",
            "summary": "Gateway-collected Pod status evidence",
            "detail": (
                "openshift_pod_status_lookup collected evidence — "
                "Pod 목록 조회 완료: webapp-deploy-7f94d-k8z2p STATUS=Running RESTARTS=3 AGE=2h10m"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-log",
            "name": "openshift_pod_log_pattern_probe",
            "evidenceType": "pod_log",
            "eventStatus": "success",
            "sourceType": "gateway-evidence",
            "status": "success",
            "summary": "Gateway-collected pod log pattern evidence",
            "detail": (
                "openshift_pod_log_pattern_probe collected evidence — "
                "이전 컨테이너 로그 패턴 검출: 'java.lang.OutOfMemoryError: Java heap space' (02:14:28), "
                "'GC overhead limit exceeded' (02:14:15), heap 증가 추세 확인됨"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-runbook",
            "name": "gateway_rag_runbook_search",
            "evidenceType": "runbook",
            "eventStatus": "success",
            "sourceType": "rag-evidence",
            "status": "success",
            "summary": "Gateway-collected RAG evidence",
            "detail": (
                "gateway_rag_runbook_search collected evidence — "
                "OOMKilled 대응 런북 조회 완료: 메모리 limit 증설 절차, "
                "JVM heap 설정 점검, HPA 메모리 기반 스케일 정책 확인 포함"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-metric-missing",
            "name": "openshift_metric_query",
            "evidenceType": "metric",
            "eventStatus": "missing",
            "sourceType": "not-collected",
            "status": "skipped",
            "missingReason": "metric_tool Prometheus 연결은 v0.1.9 예정",
            "summary": "Metric evidence missing",
            "detail": (
                "openshift_metric_query missing evidence — "
                "Prometheus/Thanos 메모리 장기 추이 조회 미수행. "
                "metric_tool Prometheus 연결은 v0.1.9 예정."
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-clusteroperator-missing",
            "name": "openshift_clusteroperator_lookup",
            "evidenceType": "clusteroperator",
            "eventStatus": "missing",
            "sourceType": "not-collected",
            "status": "skipped",
            "missingReason": "ClusterOperator 상태 조회 미수행",
            "summary": "ClusterOperator evidence missing",
            "detail": "openshift_clusteroperator_lookup missing evidence — ClusterOperator 상태 조회 미수행",
        },
    ]


async def fetch_ocp_json(
    config: ClusterObservabilityConfig,
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    required: bool = False,
    build_unavailable_detail: SyncCallback,
) -> Mapping[str, Any] | None:
    try:
        response = await client.get(
            f"{config.api_url}{path}",
            headers={"Accept": "application/json", "Authorization": authorization},
        )
    except httpx.RequestError as exc:
        if required:
            raise HTTPException(
                status_code=504,
                detail=build_unavailable_detail(f"fetch_ocp_json:{path}", exc),
            ) from exc
        return None
    if response.status_code >= 400:
        if required:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"OpenShift API request failed for {path}: {response.text[:500]}",
            )
        return None
    payload = response.json()
    return payload if isinstance(payload, Mapping) else None


def data_source_status(
    *,
    label: str,
    name: str,
    path: str,
    payload: Mapping[str, Any] | None = None,
    required: bool = False,
    reason: str = "",
    status: str | None = None,
    http_status: int | None = None,
) -> dict[str, Any]:
    resolved_status = status or ("available" if payload is not None else "unavailable")
    item: dict[str, Any] = {
        "label": label,
        "name": name,
        "path": path,
        "required": required,
        "status": resolved_status,
    }
    if reason:
        item["reason"] = reason
    if http_status is not None:
        item["httpStatus"] = http_status
    if isinstance(payload, Mapping):
        metadata = payload.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("continue"):
            item["status"] = "partial"
            item["reason"] = (
                "Kubernetes list response is paginated; additional pages were not fetched "
                "in this evidence summary."
            )
            item["continueTokenPresent"] = True
    return item


async def fetch_ocp_json_observed(
    config: ClusterObservabilityConfig,
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    label: str,
    name: str,
    required: bool = False,
) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
    try:
        response = await client.get(
            f"{config.api_url}{path}",
            headers={"Accept": "application/json", "Authorization": authorization},
        )
    except httpx.HTTPError as exc:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=str(exc),
            status="error",
        )

    if response.status_code >= 400:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=response.text[:240],
            status="error",
            http_status=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=f"Invalid JSON response: {exc}",
            status="error",
        )

    if isinstance(payload, Mapping):
        return payload, data_source_status(
            label=label,
            name=name,
            path=path,
            payload=payload,
            required=required,
        )
    return None, data_source_status(
        label=label,
        name=name,
        path=path,
        required=required,
        reason="OpenShift API response was not a JSON object.",
        status="error",
    )


def monitoring_urls_from_config(configmap_payload: Mapping[str, Any] | None) -> dict[str, str]:
    data = configmap_payload.get("data", {}) if isinstance(configmap_payload, Mapping) else {}
    if not isinstance(data, Mapping):
        data = {}
    return {
        "alertmanager": str(data.get("alertmanagerPublicURL") or ""),
        "prometheus": str(data.get("prometheusPublicURL") or ""),
        "thanos": str(data.get("thanosPublicURL") or ""),
    }


def build_aiops_overview(
    cluster_summary_payload: Mapping[str, Any],
    data_sources: list[Mapping[str, Any]],
    monitoring_urls: Mapping[str, str],
    monitoring_probe: Mapping[str, Any],
    anomaly_summary: Mapping[str, Any] | None,
    *,
    api_url: str,
    action_plan_capability_enabled: bool,
    unrestricted_commands_enabled: bool,
    build_action_candidates: SyncCallback,
    generated_at: str,
) -> dict[str, Any]:
    health_score = int(cluster_summary_payload.get("healthScore") or 0)
    nodes = (
        cluster_summary_payload.get("nodes", {})
        if isinstance(cluster_summary_payload.get("nodes"), Mapping)
        else {}
    )
    operators = (
        cluster_summary_payload.get("operators", {})
        if isinstance(cluster_summary_payload.get("operators"), Mapping)
        else {}
    )
    required_errors = [
        item
        for item in data_sources
        if item.get("required") and item.get("status") != "available"
    ]
    attention_count = sum(
        int(value or 0)
        for value in (
            nodes.get("notReady"),
            nodes.get("pressureCount"),
            operators.get("degraded"),
            operators.get("unavailable"),
            operators.get("progressing"),
        )
    )
    if required_errors:
        tower_status, tower_label = "error", "필수 데이터 소스 확인 실패"
    elif health_score >= 90 and attention_count == 0:
        tower_status, tower_label = "healthy", "회사 OCP 승인 실행 관제 정상"
    elif health_score >= 65:
        tower_status, tower_label = "attention", "운영 확인 필요"
    else:
        tower_status, tower_label = "risk", "즉시 확인 필요"

    anomaly_spec = (
        anomaly_summary.get("spec", {})
        if isinstance(anomaly_summary, Mapping)
        and isinstance(anomaly_summary.get("spec"), Mapping)
        else {}
    )
    anomaly_status = str(anomaly_spec.get("status") or "")
    anomaly_totals = (
        anomaly_spec.get("totals", {})
        if isinstance(anomaly_spec.get("totals"), Mapping)
        else {}
    )
    anomaly_total = int(anomaly_totals.get("total") or 0)
    if anomaly_status in {"error", "unknown"}:
        tower_status = "error"
        tower_label = str(
            anomaly_spec.get("statusLabel") or "이상 징후 데이터 소스 확인 필요"
        )
    elif anomaly_status == "risk":
        tower_status = "risk"
        tower_label = str(anomaly_spec.get("statusLabel") or "위험 이상 징후 확인 필요")
    elif anomaly_status in {"attention", "warning"} and tower_status == "healthy":
        tower_status = "attention"
        tower_label = str(anomaly_spec.get("statusLabel") or "이상 징후 확인 필요")

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsOverview",
        "metadata": {"generatedAt": generated_at, "name": "kugnus-control-tower"},
        "spec": {
            "clusterSummary": cluster_summary_payload,
            "controlTower": {
                "name": "Cywell AI 관제탑",
                "mode": "execute",
                "status": tower_status,
                "statusLabel": tower_label,
                "attentionCount": attention_count + anomaly_total,
                "healthScore": health_score,
                "target": cluster_summary_payload.get("apiUrl") or api_url,
            },
            "dataSources": list(data_sources),
            "anomalies": dict(anomaly_summary or {}),
            "actionCandidates": build_action_candidates(anomaly_summary, data_sources),
            "monitoring": {
                "probe": dict(monitoring_probe),
                "urls": {
                    "alertmanagerConfigured": bool(monitoring_urls.get("alertmanager")),
                    "prometheusConfigured": bool(monitoring_urls.get("prometheus")),
                    "thanosConfigured": bool(monitoring_urls.get("thanos")),
                },
            },
            "safety": {
                "mutationsEnabled": action_plan_capability_enabled,
                "executionDefault": action_plan_capability_enabled,
                "unrestrictedCommandsEnabled": unrestricted_commands_enabled,
            },
        },
    }


async def query_thanos_instant(
    config: ClusterObservabilityConfig,
    thanos_url: str,
    authorization: str,
    query: str,
) -> dict[str, Any]:
    if not thanos_url:
        return {
            "query": query,
            "status": "unavailable",
            "reason": "thanosPublicURL is not published in monitoring-shared-config.",
        }
    try:
        async with httpx.AsyncClient(
            verify=config.api_ca_file,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.get(
                f"{thanos_url.rstrip('/')}/api/v1/query",
                headers={"Accept": "application/json", "Authorization": authorization},
                params={"query": query},
            )
    except httpx.HTTPError as exc:
        return {"query": query, "status": "error", "reason": str(exc)}
    if response.status_code >= 400:
        return {
            "httpStatus": response.status_code,
            "query": query,
            "reason": response.text[:240],
            "status": "error",
        }
    try:
        payload = response.json()
    except ValueError as exc:
        return {"query": query, "status": "error", "reason": f"Invalid JSON response: {exc}"}
    if not isinstance(payload, Mapping):
        return {
            "query": query,
            "status": "error",
            "reason": "Thanos response was not a JSON object.",
        }
    prometheus_status = str(payload.get("status") or "")
    if prometheus_status and prometheus_status != "success":
        reason = str(payload.get("error") or payload.get("errorType") or "Prometheus query failed")
        return {"query": query, "status": "error", "reason": reason[:240]}
    data = payload.get("data", {})
    result = data.get("result", []) if isinstance(data, Mapping) else []
    if not isinstance(result, list):
        return {
            "query": query,
            "status": "error",
            "reason": "Thanos query result was not a vector list.",
        }
    return {
        "query": query,
        "result": result[:50],
        "resultCount": len(result),
        "status": "partial" if len(result) > 50 else "available",
        **(
            {"reason": "Thanos vector result was capped at 50 series for dashboard summary."}
            if len(result) > 50
            else {}
        ),
    }


async def collect_pod_status_evidence(
    config: ClusterObservabilityConfig,
    dependencies: ClusterObservabilityDependencies,
    user_auth_header: str,
    *,
    include_pod_list: bool = False,
    list_namespace: str = "",
) -> str:
    if not config.api_url:
        return "Pod status evidence unavailable: OPENSHIFT_API_URL is not configured."
    async with httpx.AsyncClient(
        verify=config.api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        pods_payload = await dependencies.fetch_ocp_json(client, "/api/v1/pods", user_auth_header)
        deployments_payload = await dependencies.fetch_ocp_json(
            client, "/apis/apps/v1/deployments", user_auth_header
        )
        replicasets_payload = await dependencies.fetch_ocp_json(
            client, "/apis/apps/v1/replicasets", user_auth_header
        )
        cluster_operators_payload = await dependencies.fetch_ocp_json(
            client, "/apis/config.openshift.io/v1/clusteroperators", user_auth_header
        )
    if not pods_payload:
        return (
            "Pod status evidence unavailable: Kubernetes API pod list was not returned. "
            "This may be a permission or API availability issue."
        )
    evidence = dependencies.build_pod_status_evidence(
        pods_payload,
        replicasets_payload,
        include_pod_list=include_pod_list,
        list_namespace=list_namespace,
    )
    if deployments_payload:
        evidence = dependencies.append_gateway_evidence(
            evidence,
            dependencies.build_deployment_rollout_evidence(
                deployments_payload, replicasets_payload, pods_payload
            ),
        )
    if cluster_operators_payload:
        evidence = dependencies.append_gateway_evidence(
            evidence,
            dependencies.build_cluster_operator_status_evidence(cluster_operators_payload),
        )
    return evidence


async def collect_pod_count_investigation(
    config: ClusterObservabilityConfig,
    dependencies: ClusterObservabilityDependencies,
    user_auth_header: str,
    query: Mapping[str, str],
) -> dict[str, Any]:
    namespace = str(query.get("namespace") or "")
    if not config.api_url:
        return {
            "namespace": namespace,
            "reason": "OPENSHIFT_API_URL is not configured",
            "status": "unavailable",
            "targetName": str(query.get("targetName") or ""),
        }
    if namespace:
        deployments_path = f"/apis/apps/v1/namespaces/{path_segment(namespace)}/deployments"
        pods_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods"
    else:
        deployments_path = "/apis/apps/v1/deployments"
        pods_path = "/api/v1/pods"
    async with httpx.AsyncClient(
        verify=config.api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        deployments_payload = await dependencies.fetch_ocp_json(
            client, deployments_path, user_auth_header
        )
        pods_payload = await dependencies.fetch_ocp_json(client, pods_path, user_auth_header)
    if not pods_payload:
        return {
            "namespace": namespace,
            "reason": f"Kubernetes API pod list was not returned for {pods_path}",
            "status": "unavailable",
            "targetName": str(query.get("targetName") or ""),
        }
    return dependencies.build_pod_count_investigation(
        query, deployments_payload, pods_payload
    )


async def collect_cronjob_activity_evidence(
    config: ClusterObservabilityConfig,
    dependencies: ClusterObservabilityDependencies,
    user_auth_header: str,
    context_text: str,
) -> str:
    if not config.api_url:
        return "CronJob activity evidence unavailable: OPENSHIFT_API_URL is not configured."
    async with httpx.AsyncClient(
        verify=config.api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        cronjobs_payload = await dependencies.fetch_ocp_json(
            client, "/apis/batch/v1/cronjobs", user_auth_header
        )
        jobs_payload = await dependencies.fetch_ocp_json(
            client, "/apis/batch/v1/jobs?limit=500", user_auth_header
        )
    if not cronjobs_payload:
        return (
            "CronJob activity evidence unavailable: Kubernetes API CronJob list was not returned. "
            "This may be a permission or API availability issue."
        )
    return dependencies.build_cronjob_activity_evidence(
        cronjobs_payload, jobs_payload, context_text=context_text
    )


def _data_source_event_status(source: Mapping[str, Any] | None) -> str:
    status = str((source or {}).get("status") or "unavailable").lower()
    return {
        "available": "success",
        "partial": "partial",
        "error": "error",
    }.get(status, "skipped")


def _evidence_summary(label: str, status: str) -> str:
    if status == "success":
        return f"{label} 수집 완료"
    if status == "partial":
        return f"{label} 부분 수집"
    return f"{label} 수집 불가"


async def monitoring_urls_for_rca(
    config: ClusterObservabilityConfig,
    dependencies: ClusterObservabilityDependencies,
    user_auth_header: str,
) -> tuple[dict[str, str], dict[str, Any]]:
    path = "/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config"
    if not config.api_url:
        return {}, dependencies.data_source_status(
            label="Monitoring public URLs",
            name="monitoring-shared-config",
            path=path,
            reason="OPENSHIFT_API_URL is not configured.",
            status="unavailable",
        )
    async with httpx.AsyncClient(
        verify=config.api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        payload, status = await dependencies.fetch_ocp_json_observed(
            client,
            path,
            user_auth_header,
            label="Monitoring public URLs",
            name="monitoring-shared-config",
        )
    return dependencies.monitoring_urls_from_config(payload), status


async def collect_node_status_rca_evidence(
    config: ClusterObservabilityConfig,
    dependencies: ClusterObservabilityDependencies,
    user_auth_header: str,
) -> dict[str, Any]:
    source_path = "/api/v1/nodes"
    metrics_path = "/apis/metrics.k8s.io/v1beta1/nodes"
    if not config.api_url:
        reason = "OPENSHIFT_API_URL is not configured."
        return {
            "detail": f"Node status evidence unavailable: {reason}",
            "evidenceType": "node",
            "missingReason": reason,
            "sourcePath": source_path,
            "status": "skipped",
            "summary": _evidence_summary("Node 상태 RCA 증거", "skipped"),
        }
    async with httpx.AsyncClient(
        verify=config.api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        nodes_payload, nodes_status = await dependencies.fetch_ocp_json_observed(
            client,
            source_path,
            user_auth_header,
            label="RCA Node status",
            name="nodes",
            required=True,
        )
        node_metrics_payload, metrics_status = await dependencies.fetch_ocp_json_observed(
            client,
            metrics_path,
            user_auth_header,
            label="RCA Node metrics",
            name="metrics.k8s.io",
        )
    if not nodes_payload:
        reason = dependencies.safe_error_text(
            nodes_status.get("reason") or "Kubernetes API node list was not returned."
        )
        status = _data_source_event_status(nodes_status)
        return {
            "detail": f"Node status evidence unavailable: {reason}",
            "evidenceType": "node",
            "missingReason": reason,
            "sourcePath": source_path,
            "status": status,
            "summary": _evidence_summary("Node 상태 RCA 증거", status),
        }
    status = (
        "success"
        if _data_source_event_status(metrics_status) == "success"
        else "partial"
    )
    return {
        "detail": dependencies.build_node_status_rca_evidence(
            nodes_payload, node_metrics_payload, metrics_status=metrics_status
        ),
        "evidenceType": "node",
        "missingReason": dependencies.safe_error_text(
            metrics_status.get("reason") or "", limit=240
        )
        if status == "partial"
        else "",
        "sourcePath": f"{source_path},{metrics_path}",
        "status": status,
        "summary": _evidence_summary("Node 상태 RCA 증거", status),
    }


async def _collect_prometheus_rca_evidence(
    config: ClusterObservabilityConfig,
    dependencies: ClusterObservabilityDependencies,
    user_auth_header: str,
    *,
    query: str,
    evidence_type: str,
    label: str,
    detail_builder: SyncCallback,
) -> dict[str, Any]:
    monitoring_urls, monitoring_status = await monitoring_urls_for_rca(
        config, dependencies, user_auth_header
    )
    probe = await dependencies.query_thanos_instant(
        monitoring_urls.get("thanos", ""), user_auth_header, query
    )
    status = dependencies.rca_probe_event_status(probe)
    if status == "skipped" and _data_source_event_status(monitoring_status) == "error":
        status = "error"
    reason = dependencies.prometheus_probe_reason(probe)
    return {
        "detail": detail_builder(probe),
        "evidenceType": evidence_type,
        "missingReason": reason if status != "success" else "",
        "sourcePath": f"/api/v1/query?query={query}",
        "status": status,
        "summary": _evidence_summary(label, status),
    }


async def collect_active_alerts_rca_evidence(
    config: ClusterObservabilityConfig,
    dependencies: ClusterObservabilityDependencies,
    user_auth_header: str,
) -> dict[str, Any]:
    return await _collect_prometheus_rca_evidence(
        config,
        dependencies,
        user_auth_header,
        query='ALERTS{alertstate="firing"}',
        evidence_type="alert",
        label="Active Alert RCA 증거",
        detail_builder=dependencies.build_active_alerts_rca_evidence,
    )


async def collect_restart_metric_rca_evidence(
    config: ClusterObservabilityConfig,
    dependencies: ClusterObservabilityDependencies,
    user_auth_header: str,
) -> dict[str, Any]:
    return await _collect_prometheus_rca_evidence(
        config,
        dependencies,
        user_auth_header,
        query="increase(kube_pod_container_status_restarts_total[1h]) > 0",
        evidence_type="metric",
        label="Restart metric RCA 증거",
        detail_builder=dependencies.build_restart_metric_rca_evidence,
    )
