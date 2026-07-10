from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RcaPreflightCollector:
    suffix: str
    event_name: str
    call_summary: str
    evidence_type: str
    collect: Callable[[str], Awaitable[Mapping[str, Any]]]


@dataclass(frozen=True, slots=True)
class RcaPreflightFlowDependencies:
    collectors: Sequence[RcaPreflightCollector]
    append_gateway_evidence: Callable[[str | None, str], str]
    safe_exception_text: Callable[[Exception], str]
    build_evidence_reference_events: Callable[..., list[dict[str, Any]]]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class RcaPreflightStreamEvent:
    payload: str
    gateway_evidence: str | None = None


def _event(dependencies, value, *, gateway_evidence=None):
    return RcaPreflightStreamEvent(
        payload=dependencies.sse(value),
        gateway_evidence=gateway_evidence,
    )


async def stream_rca_preflight_evidence(
    *,
    authorization: str,
    dependencies: RcaPreflightFlowDependencies,
    gateway_evidence: str | None,
    incident_id: str,
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any],
) -> AsyncIterator[RcaPreflightStreamEvent]:
    for spec in dependencies.collectors:
        event_id = f"{request_id}-{spec.suffix}"
        yield _event(
            dependencies,
            {
                "type": "tool_call",
                "id": event_id,
                "name": spec.event_name,
                "summary": spec.call_summary,
            },
        )
        try:
            result = await spec.collect(authorization)
            detail = str(result.get("detail") or "")
            gateway_evidence = dependencies.append_gateway_evidence(
                gateway_evidence,
                detail,
            )
            evidence_event = {
                "type": "tool_result",
                "detail": detail,
                "evidenceType": result.get("evidenceType"),
                "id": event_id,
                "missingReason": result.get("missingReason"),
                "name": spec.event_name,
                "sourcePath": result.get("sourcePath"),
                "status": result.get("status") or "error",
                "summary": result.get("summary") or f"{spec.call_summary} 완료",
            }
        except Exception as exc:
            safe_detail = dependencies.safe_exception_text(exc)
            detail = f"{spec.call_summary} unavailable: {safe_detail}"
            gateway_evidence = dependencies.append_gateway_evidence(
                gateway_evidence,
                detail,
            )
            evidence_event = {
                "type": "tool_result",
                "detail": detail,
                "evidenceType": spec.evidence_type,
                "id": event_id,
                "missingReason": safe_detail,
                "name": spec.event_name,
                "status": "error",
                "summary": f"{spec.call_summary} 실패",
            }

        yield _event(
            dependencies,
            evidence_event,
            gateway_evidence=gateway_evidence,
        )
        for reference in dependencies.build_evidence_reference_events(
            event=evidence_event,
            incident_id=incident_id,
            run_id=run_id,
            source_type="gateway-preflight-evidence",
            subject=subject,
        ):
            yield _event(dependencies, reference)
