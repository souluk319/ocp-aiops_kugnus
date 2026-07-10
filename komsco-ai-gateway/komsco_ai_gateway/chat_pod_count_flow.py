from __future__ import annotations

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
