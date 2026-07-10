from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PodEvidenceFlowDependencies:
    is_pod_list_request: Callable[[str], bool]
    page_context_is_pod_workload: Callable[[Any], bool]
    pod_list_namespace: Callable[[Any], str]
    collect_pod_status_evidence: Callable[..., Awaitable[str]]
    append_gateway_evidence: Callable[[str | None, str], str]
    safe_exception_text: Callable[[Exception], str]
    evidence_summary: Callable[[str, str], str]
    build_evidence_reference_events: Callable[..., list[dict[str, Any]]]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class PodEvidenceStreamEvent:
    payload: str
    gateway_evidence: str | None = None


def _event(
    dependencies: PodEvidenceFlowDependencies,
    value: Any,
    *,
    gateway_evidence: str | None = None,
) -> PodEvidenceStreamEvent:
    return PodEvidenceStreamEvent(
        payload=dependencies.sse(value),
        gateway_evidence=gateway_evidence,
    )


def _reference_events(
    dependencies: PodEvidenceFlowDependencies,
    *,
    event: Mapping[str, Any],
    incident_id: str,
    run_id: str,
    subject: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return dependencies.build_evidence_reference_events(
        event=event,
        incident_id=incident_id,
        run_id=run_id,
        source_type="gateway-preflight-evidence",
        subject=subject,
    )


async def stream_pod_status_evidence(
    *,
    authorization: str,
    dependencies: PodEvidenceFlowDependencies,
    gateway_evidence: str | None,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any],
) -> AsyncIterator[PodEvidenceStreamEvent]:
    yield _event(
        dependencies,
        {
            "type": "tool_call",
            "id": f"{request_id}-pod-status-evidence",
            "name": "pod_status_evidence",
            "summary": "Pod 상태/재시작 조회 결과 수집",
        },
    )

    try:
        pod_list_requested = dependencies.is_pod_list_request(
            request.message
        ) or dependencies.page_context_is_pod_workload(request)
        detail = await dependencies.collect_pod_status_evidence(
            authorization,
            include_pod_list=pod_list_requested,
            list_namespace=(
                dependencies.pod_list_namespace(request) if pod_list_requested else ""
            ),
        )
        status = (
            "skipped"
            if detail.startswith("Pod status evidence unavailable:")
            else "success"
        )
        missing_reason = detail if status != "success" else ""
        pod_event = {
            "type": "tool_result",
            "detail": detail,
            "evidenceType": "pod_status",
            "id": f"{request_id}-pod-status-evidence",
            "missingReason": missing_reason,
            "name": "pod_status_evidence",
            "sourcePath": "/api/v1/pods,/apis/apps/v1/deployments,/apis/config.openshift.io/v1/clusteroperators",
            "status": status,
            "summary": dependencies.evidence_summary("Pod 상태/재시작 증거", status),
        }
        snapshot_event = {
            "type": "tool_result",
            "detail": detail,
            "evidenceType": "snapshot",
            "id": f"{request_id}-pod-snapshot-evidence",
            "missingReason": missing_reason,
            "name": "pod_snapshot_evidence",
            "sourcePath": "/api/v1/pods,/apis/apps/v1/deployments,/apis/config.openshift.io/v1/clusteroperators",
            "status": status,
            "summary": dependencies.evidence_summary("Pod snapshot 증거", status),
        }
    except Exception as exc:
        safe_detail = dependencies.safe_exception_text(exc)
        detail = f"Pod status evidence unavailable: {safe_detail}"
        pod_event = {
            "type": "tool_result",
            "detail": detail,
            "id": f"{request_id}-pod-status-evidence",
            "name": "pod_status_evidence",
            "evidenceType": "pod_status",
            "missingReason": safe_detail,
            "status": "error",
            "summary": "Pod 상태/재시작 조회 결과 수집 실패",
        }
        snapshot_event = {
            "type": "tool_result",
            "detail": detail,
            "id": f"{request_id}-pod-snapshot-evidence",
            "name": "pod_snapshot_evidence",
            "evidenceType": "snapshot",
            "missingReason": safe_detail,
            "status": "error",
            "summary": "Pod snapshot 조회 결과 수집 실패",
        }

    updated_evidence = dependencies.append_gateway_evidence(gateway_evidence, detail)
    for index, evidence_event in enumerate((pod_event, snapshot_event)):
        yield _event(
            dependencies,
            evidence_event,
            gateway_evidence=updated_evidence if index == 0 else None,
        )
        for reference_event in _reference_events(
            dependencies,
            event=evidence_event,
            incident_id=incident_id,
            run_id=run_id,
            subject=subject,
        ):
            yield _event(dependencies, reference_event)
