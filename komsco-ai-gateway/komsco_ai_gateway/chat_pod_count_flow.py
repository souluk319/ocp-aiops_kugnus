from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .answer_streaming import sse


@dataclass(frozen=True, slots=True)
class TopPodNamespaceFlowDependencies:
    openshift_api_url: str
    openshift_api_ca_file: Any
    async_client_factory: Callable[..., Any]
    timeout_factory: Callable[..., Any]
    fetch_ocp_json: Callable[..., Awaitable[Mapping[str, Any] | None]]
    build_result: Callable[[Mapping[str, Any] | None], dict[str, Any]]
    build_response: Callable[[Mapping[str, Any]], str]
    build_evidence_events: Callable[..., list[dict[str, Any]]]
    current_rca_context_event: Callable[[str], dict[str, Any]]


@dataclass(frozen=True, slots=True)
class TopPodNamespaceStreamEvent:
    payload: str
    latest_rca_context: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DirectPodCountFlowDependencies:
    openshift_api_url: str
    openshift_api_ca_file: Any
    async_client_factory: Callable[..., Any]
    timeout_factory: Callable[..., Any]
    fetch_ocp_json: Callable[..., Awaitable[Mapping[str, Any] | None]]
    path_segment: Callable[[str], str]
    resource_items: Callable[[Mapping[str, Any] | None], list[Mapping[str, Any]]]
    metadata_name: Callable[[Mapping[str, Any]], str]
    metadata_namespace: Callable[[Mapping[str, Any]], str]
    build_investigation: Callable[..., dict[str, Any]]
    build_response: Callable[[Mapping[str, Any]], str]
    redact_sensitive: Callable[[Any], Any]
    build_evidence_events: Callable[..., list[dict[str, Any]]]
    current_rca_context_event: Callable[[str], dict[str, Any]]


async def stream_top_pod_namespace_count(
    *,
    authorization: str,
    dependencies: TopPodNamespaceFlowDependencies,
    incident_id: str,
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any] | None,
) -> AsyncIterator[TopPodNamespaceStreamEvent]:
    tool_id = f"{request_id}-top-pod-namespace-count"
    yield TopPodNamespaceStreamEvent(
        sse(
            {
                "type": "tool_call",
                "id": tool_id,
                "name": "top_pod_namespace_count_lookup",
                "summary": "namespace별 Pod 수 집계",
            }
        )
    )

    if not dependencies.openshift_api_url:
        top_namespace_result = {
            "reason": "OPENSHIFT_API_URL is not configured",
            "rows": [],
            "status": "unavailable",
        }
    else:
        async with dependencies.async_client_factory(
            verify=dependencies.openshift_api_ca_file,
            timeout=dependencies.timeout_factory(20.0, connect=5.0),
        ) as client:
            pods_payload = await dependencies.fetch_ocp_json(
                client,
                "/api/v1/pods",
                authorization,
            )
        top_namespace_result = dependencies.build_result(pods_payload)

    top_namespace_text = dependencies.build_response(top_namespace_result)
    top_namespace_event = {
        "type": "tool_result",
        "detail": top_namespace_text,
        "id": tool_id,
        "name": "top_pod_namespace_count_lookup",
        "result": top_namespace_result,
        "status": "success" if top_namespace_result.get("status") == "found" else "skipped",
        "summary": (
            f"{top_namespace_result.get('topNamespace')} namespace가 Pod {top_namespace_result.get('topPodCount')}개로 최다"
            if top_namespace_result.get("status") == "found"
            else "namespace별 Pod 수 집계 실패"
        ),
    }
    yield TopPodNamespaceStreamEvent(sse(top_namespace_event))
    for evidence_event in dependencies.build_evidence_events(
        event=top_namespace_event,
        incident_id=incident_id,
        run_id=run_id,
        source_type="gateway-direct-evidence",
        subject=subject,
    ):
        yield TopPodNamespaceStreamEvent(sse(evidence_event))

    rca_context_event = dependencies.current_rca_context_event("post_answer")
    yield TopPodNamespaceStreamEvent(
        sse(rca_context_event),
        latest_rca_context=rca_context_event["context"],
    )
    yield TopPodNamespaceStreamEvent(
        sse(
            {
                "type": "text",
                "content": top_namespace_text,
                "source": "gateway_direct_lookup",
                "answerContract": "top-pod-namespace-count-v0.2.9",
            }
        )
    )
    yield TopPodNamespaceStreamEvent(
        sse(
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "completed",
                "message": "Gateway namespace별 Pod 수 집계 완료",
            }
        )
    )
    yield TopPodNamespaceStreamEvent(sse("[DONE]"))


async def stream_direct_pod_count(
    *,
    authorization: str,
    dependencies: DirectPodCountFlowDependencies,
    incident_id: str,
    pod_count_query: Mapping[str, str],
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any] | None,
) -> AsyncIterator[TopPodNamespaceStreamEvent]:
    target_name = str(pod_count_query.get("targetName") or "")
    namespace = str(pod_count_query.get("namespace") or "")
    scope_summary = (
        f"namespace `{namespace}` 범위에서 조회"
        if namespace
        else "접근 가능한 전체 namespace에서 조회"
    )
    yield TopPodNamespaceStreamEvent(
        sse(
            {
                "type": "tool_call",
                "id": f"{request_id}-pod-count-scope",
                "name": "pod_count_scope_resolve",
                "summary": "요청에서 대상 이름과 namespace 범위 해석",
            }
        )
    )
    yield TopPodNamespaceStreamEvent(
        sse(
            {
                "type": "tool_result",
                "detail": json.dumps(
                    {
                        "namespace": namespace or "all-accessible-namespaces",
                        "scope": scope_summary,
                        "targetName": target_name or "missing",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                "id": f"{request_id}-pod-count-scope",
                "name": "pod_count_scope_resolve",
                "result": pod_count_query,
                "status": "success" if target_name else "skipped",
                "summary": (
                    f"대상 `{target_name}`, {scope_summary}"
                    if target_name
                    else f"대상 이름 미확인, {scope_summary}"
                ),
            }
        )
    )

    if namespace:
        deployments_path = f"/apis/apps/v1/namespaces/{dependencies.path_segment(namespace)}/deployments"
        pods_path = f"/api/v1/namespaces/{dependencies.path_segment(namespace)}/pods"
    else:
        deployments_path = "/apis/apps/v1/deployments"
        pods_path = "/api/v1/pods"

    deployments_payload: Mapping[str, Any] | None = None
    pods_payload: Mapping[str, Any] | None = None
    pod_count_result: dict[str, Any] | None = None
    if not target_name:
        pod_count_result = dependencies.build_investigation(
            pod_count_query,
            deployments_payload,
            pods_payload,
        )
    elif not dependencies.openshift_api_url:
        pod_count_result = {
            "namespace": namespace,
            "reason": "OPENSHIFT_API_URL is not configured",
            "status": "unavailable",
            "targetName": target_name,
        }
    else:
        async with dependencies.async_client_factory(
            verify=dependencies.openshift_api_ca_file,
            timeout=dependencies.timeout_factory(20.0, connect=5.0),
        ) as client:
            yield TopPodNamespaceStreamEvent(
                sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-pod-count-deployments",
                        "name": "pod_count_deployment_lookup",
                        "summary": f"Deployment 목록 조회: `{deployments_path}`",
                    }
                )
            )
            deployments_payload = await dependencies.fetch_ocp_json(
                client,
                deployments_path,
                authorization,
            )
            deployment_items = dependencies.resource_items(deployments_payload)
            matched_deployment_count = sum(
                1
                for deployment in deployment_items
                if dependencies.metadata_name(deployment) == target_name
                and (not namespace or dependencies.metadata_namespace(deployment) == namespace)
            )
            deployment_status = "success" if deployments_payload else "skipped"
            yield TopPodNamespaceStreamEvent(
                sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(
                            {
                                "matchedDeployments": matched_deployment_count,
                                "path": deployments_path,
                                "receivedItems": len(deployment_items),
                                "targetName": target_name,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "id": f"{request_id}-pod-count-deployments",
                        "name": "pod_count_deployment_lookup",
                        "result": {
                            "matchedDeployments": matched_deployment_count,
                            "path": deployments_path,
                        },
                        "status": deployment_status,
                        "summary": (
                            f"Deployment `{target_name}` 후보 {matched_deployment_count}건 확인"
                            if deployments_payload
                            else "Deployment 목록을 받지 못해 Pod fallback 조회 준비"
                        ),
                    }
                )
            )

            yield TopPodNamespaceStreamEvent(
                sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-pod-count-pods",
                        "name": "pod_count_pod_lookup",
                        "summary": f"Pod 목록 조회: `{pods_path}`",
                    }
                )
            )
            pods_payload = await dependencies.fetch_ocp_json(client, pods_path, authorization)
            pod_items = dependencies.resource_items(pods_payload)
            yield TopPodNamespaceStreamEvent(
                sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(
                            {
                                "path": pods_path,
                                "receivedItems": len(pod_items),
                                "targetName": target_name,
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "id": f"{request_id}-pod-count-pods",
                        "name": "pod_count_pod_lookup",
                        "result": {"path": pods_path, "receivedItems": len(pod_items)},
                        "status": "success" if pods_payload else "skipped",
                        "summary": f"Pod 목록 {len(pod_items)}건 수신" if pods_payload else "Pod 목록을 받지 못함",
                    }
                )
            )

        if not pods_payload:
            pod_count_result = {
                "namespace": namespace,
                "reason": f"Kubernetes API pod list was not returned for {pods_path}",
                "status": "unavailable",
                "targetName": target_name,
            }
        else:
            yield TopPodNamespaceStreamEvent(
                sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-pod-count-match",
                        "name": "pod_count_selector_match",
                        "summary": "Deployment selector와 Pod label/name 매칭",
                    }
                )
            )
            pod_count_result = dependencies.build_investigation(
                pod_count_query,
                deployments_payload,
                pods_payload,
            )
            result_rows = pod_count_result.get("rows")
            matched_pods = sum(
                int(row.get("totalPods") or 0)
                for row in (result_rows if isinstance(result_rows, list) else [])
                if isinstance(row, Mapping)
            )
            match_strategy = str(pod_count_result.get("matchStrategy") or "none")
            yield TopPodNamespaceStreamEvent(
                sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(
                            dependencies.redact_sensitive(pod_count_result),
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "id": f"{request_id}-pod-count-match",
                        "name": "pod_count_selector_match",
                        "result": {
                            "matchedPods": matched_pods,
                            "matchStrategy": match_strategy,
                            "status": pod_count_result.get("status"),
                        },
                        "status": "success" if pod_count_result.get("status") == "found" else "skipped",
                        "summary": (
                            f"`{match_strategy}` 방식으로 Pod {matched_pods}개 매칭"
                            if pod_count_result.get("status") == "found"
                            else "매칭되는 Deployment/Pod 없음"
                        ),
                    }
                )
            )

    yield TopPodNamespaceStreamEvent(
        sse(
            {
                "type": "tool_call",
                "id": f"{request_id}-pod-count-investigation",
                "name": "pod_count_investigation",
                "summary": "Pod 개수 조회 결과 정리",
            }
        )
    )
    pod_count_result = pod_count_result or {
        "namespace": namespace,
        "reason": "Pod count investigation did not produce a result",
        "status": "unavailable",
        "targetName": target_name,
    }
    pod_count_text = dependencies.build_response(pod_count_result)
    result_status = str(pod_count_result.get("status") or "")
    pod_count_event = {
        "type": "tool_result",
        "detail": pod_count_text,
        "id": f"{request_id}-pod-count-investigation",
        "name": "pod_count_investigation",
        "result": pod_count_result,
        "status": "success" if result_status == "found" else "skipped",
        "summary": "Pod 개수 직접 조회 완료",
    }
    yield TopPodNamespaceStreamEvent(sse(pod_count_event))
    for evidence_event in dependencies.build_evidence_events(
        event=pod_count_event,
        incident_id=incident_id,
        run_id=run_id,
        source_type="gateway-direct-evidence",
        subject=subject,
    ):
        yield TopPodNamespaceStreamEvent(sse(evidence_event))
    rca_context_event = dependencies.current_rca_context_event("post_answer")
    yield TopPodNamespaceStreamEvent(
        sse(rca_context_event),
        latest_rca_context=rca_context_event["context"],
    )
    yield TopPodNamespaceStreamEvent(sse({"type": "text", "content": pod_count_text}))
    yield TopPodNamespaceStreamEvent(
        sse(
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "completed",
                "message": "Gateway Pod 개수 직접 조회 완료",
            }
        )
    )
    yield TopPodNamespaceStreamEvent(sse("[DONE]"))
