from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AttachmentCronjobFlowDependencies:
    analyze_image_attachments: Callable[..., Awaitable[str | None]]
    should_collect_cronjob_activity_evidence: Callable[[str, str | None], bool]
    collect_cronjob_activity_evidence: Callable[[str, str], Awaitable[str]]
    append_gateway_evidence: Callable[[str | None, str], str]
    safe_exception_text: Callable[[Exception], str]
    evidence_summary: Callable[[str, str], str]
    build_evidence_reference_events: Callable[..., list[dict[str, Any]]]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class AttachmentCronjobStreamEvent:
    payload: str
    gateway_evidence: str | None = None
    image_analysis: str | None = None
    image_analysis_updated: bool = False


def _event(
    dependencies: AttachmentCronjobFlowDependencies,
    value: Any,
    *,
    gateway_evidence: str | None = None,
    image_analysis: str | None = None,
    image_analysis_updated: bool = False,
) -> AttachmentCronjobStreamEvent:
    return AttachmentCronjobStreamEvent(
        payload=dependencies.sse(value),
        gateway_evidence=gateway_evidence,
        image_analysis=image_analysis,
        image_analysis_updated=image_analysis_updated,
    )


async def stream_attachment_and_cronjob_preflight(
    *,
    authorization: str,
    dependencies: AttachmentCronjobFlowDependencies,
    gateway_evidence: str | None,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any],
) -> AsyncIterator[AttachmentCronjobStreamEvent]:
    image_analysis: str | None = None
    if request.attachments:
        yield _event(dependencies, {"type": "tool_call", "name": "attachment_check"})
        yield _event(
            dependencies,
            {
                "type": "tool_result",
                "name": "attachment_check",
                "result": {
                    "images": len(request.attachments),
                    "totalBytes": sum(item.size for item in request.attachments),
                    "forwardedToLightspeed": False,
                },
                "summary": "첨부 이미지 수신 및 형식 확인 완료",
            },
        )
        yield _event(dependencies, {"type": "tool_call", "name": "vision_analysis"})
        image_analysis = await dependencies.analyze_image_attachments(
            request.attachments,
            request.message,
        )
        yield _event(
            dependencies,
            {
                "type": "tool_result",
                "name": "vision_analysis",
                "result": "ok" if image_analysis else "not_configured",
            },
            image_analysis=image_analysis,
            image_analysis_updated=True,
        )

    if not dependencies.should_collect_cronjob_activity_evidence(
        request.message,
        image_analysis,
    ):
        return

    yield _event(
        dependencies,
        {
            "type": "tool_call",
            "id": f"{request_id}-cronjob-activity-evidence",
            "name": "cronjob_activity_evidence",
            "summary": "CronJob/Activity 주기 조회 결과 수집",
        },
    )
    try:
        cronjob_context = "\n".join(
            item for item in [request.message, image_analysis] if item
        )
        detail = await dependencies.collect_cronjob_activity_evidence(
            authorization,
            cronjob_context,
        )
        status = (
            "skipped"
            if detail.startswith("CronJob activity evidence unavailable:")
            else "success"
        )
        cronjob_event = {
            "type": "tool_result",
            "detail": detail,
            "evidenceType": "cronjob",
            "id": f"{request_id}-cronjob-activity-evidence",
            "missingReason": detail if status != "success" else "",
            "name": "cronjob_activity_evidence",
            "sourcePath": "/apis/batch/v1/cronjobs,/apis/batch/v1/jobs?limit=500",
            "status": status,
            "summary": dependencies.evidence_summary(
                "CronJob/Activity 주기 증거",
                status,
            ),
        }
        gateway_evidence = dependencies.append_gateway_evidence(gateway_evidence, detail)
        yield _event(
            dependencies,
            cronjob_event,
            gateway_evidence=gateway_evidence,
        )
        for evidence_event in dependencies.build_evidence_reference_events(
            event=cronjob_event,
            incident_id=incident_id,
            run_id=run_id,
            source_type="gateway-preflight-evidence",
            subject=subject,
        ):
            yield _event(dependencies, evidence_event)
    except Exception as exc:
        safe_detail = dependencies.safe_exception_text(exc)
        detail = f"CronJob activity evidence unavailable: {safe_detail}"
        cronjob_event = {
            "type": "tool_result",
            "detail": detail,
            "id": f"{request_id}-cronjob-activity-evidence",
            "name": "cronjob_activity_evidence",
            "evidenceType": "cronjob",
            "missingReason": safe_detail,
            "status": "error",
            "summary": "CronJob/Activity 주기 조회 결과 수집 실패",
        }
        gateway_evidence = dependencies.append_gateway_evidence(gateway_evidence, detail)
        yield _event(
            dependencies,
            cronjob_event,
            gateway_evidence=gateway_evidence,
        )
        for evidence_event in dependencies.build_evidence_reference_events(
            event=cronjob_event,
            incident_id=incident_id,
            run_id=run_id,
            source_type="gateway-preflight-evidence",
            subject=subject,
        ):
            yield _event(dependencies, evidence_event)
