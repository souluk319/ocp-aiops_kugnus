from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RestartEvidenceFlowDependencies:
    crashloop_target: Callable[[Any], Mapping[str, Any] | None]
    official_namespace: Callable[[Mapping[str, Any]], str]
    collect_official: Callable[..., Awaitable[list[dict[str, Any]]]]
    official_fallback: Callable[..., list[dict[str, Any]]]
    collect_crashloop: Callable[..., Awaitable[list[dict[str, Any]]]]
    append_gateway_evidence: Callable[[str | None, str], str]
    safe_exception_text: Callable[[Exception], str]
    build_evidence_reference_events: Callable[..., list[dict[str, Any]]]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class RestartEvidenceStreamEvent:
    payload: str
    gateway_evidence: str | None = None


def _event(dependencies, value, *, gateway_evidence=None):
    return RestartEvidenceStreamEvent(
        payload=dependencies.sse(value),
        gateway_evidence=gateway_evidence,
    )


def _crashloop_fallback(request_id: str, safe_detail: str) -> list[dict[str, Any]]:
    return [
        {
            "type": "tool_result",
            "detail": f"CrashLoop event evidence unavailable: {safe_detail}",
            "evidenceType": "event",
            "id": f"{request_id}-crashloop-event-evidence",
            "missingReason": safe_detail,
            "name": "crashloop_event_evidence",
            "status": "error",
            "summary": "CrashLoop Event 조회 결과 수집 실패",
        },
        {
            "type": "tool_result",
            "detail": f"CrashLoop previous log availability unavailable: {safe_detail}",
            "evidenceType": "pod_log",
            "id": f"{request_id}-crashloop-log-availability",
            "missingReason": safe_detail,
            "name": "crashloop_log_availability",
            "status": "error",
            "summary": "CrashLoop 이전 로그 가용성 확인 실패",
        },
        {
            "type": "tool_result",
            "detail": f"CrashLoop Pod snapshot unavailable: {safe_detail}",
            "evidenceType": "snapshot",
            "id": f"{request_id}-crashloop-pod-snapshot",
            "missingReason": safe_detail,
            "name": "crashloop_pod_snapshot",
            "status": "error",
            "summary": "CrashLoop Pod snapshot 조회 결과 수집 실패",
        },
    ]


async def stream_restart_evidence(
    *,
    authorization: str,
    dependencies: RestartEvidenceFlowDependencies,
    gateway_evidence: str | None,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
    runtime_tool_plan: Mapping[str, Any],
    subject: Mapping[str, Any],
) -> AsyncIterator[RestartEvidenceStreamEvent]:
    crashloop_target = dependencies.crashloop_target(request)
    official_namespace = dependencies.official_namespace(runtime_tool_plan)
    events: list[dict[str, Any]] = []

    if official_namespace and not crashloop_target:
        yield _event(
            dependencies,
            {
                "type": "tool_call",
                "id": f"{request_id}-official-namespace-restart-evidence",
                "name": "official_namespace_restart_evidence",
                "summary": f"공식 Evidence RCA namespace 재시작 조회 결과 수집: `{official_namespace}`",
            },
        )
        try:
            events = await dependencies.collect_official(
                authorization, official_namespace, request_id
            )
        except Exception as exc:
            safe_detail = dependencies.safe_exception_text(exc)
            events = dependencies.official_fallback(
                namespace=official_namespace,
                request_id=request_id,
                reason=safe_detail,
                detail=safe_detail,
            )
    elif crashloop_target:
        yield _event(
            dependencies,
            {
                "type": "tool_call",
                "id": f"{request_id}-crashloop-demo-evidence",
                "name": "crashloop_demo_evidence",
                "summary": "CrashLoopBackOff 시연 조회 결과 수집",
            },
        )
        try:
            events = await dependencies.collect_crashloop(
                authorization, crashloop_target, request_id
            )
        except Exception as exc:
            events = _crashloop_fallback(
                request_id,
                dependencies.safe_exception_text(exc),
            )

    for evidence in events:
        gateway_evidence = dependencies.append_gateway_evidence(
            gateway_evidence,
            str(evidence.get("detail") or evidence.get("summary") or ""),
        )
        yield _event(
            dependencies,
            evidence,
            gateway_evidence=gateway_evidence,
        )
        for reference in dependencies.build_evidence_reference_events(
            event=evidence,
            incident_id=incident_id,
            run_id=run_id,
            source_type="gateway-preflight-evidence",
            subject=subject,
        ):
            yield _event(dependencies, reference)
