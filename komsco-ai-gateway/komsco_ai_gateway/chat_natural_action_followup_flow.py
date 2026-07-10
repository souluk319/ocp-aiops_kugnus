from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NaturalActionFollowupFlowDependencies:
    latest_pending_action_plan_result: Callable[[Mapping[str, Any]], dict[str, Any] | None]
    recent_natural_action_request: Callable[[Any], Any | None]
    create_natural_action_plan: Callable[..., Awaitable[dict[str, Any] | None]]
    execute_natural_action_plan_result: Callable[..., Awaitable[dict[str, Any]]]
    redact_sensitive: Callable[[Any], Any]
    natural_action_execution_response: Callable[[Mapping[str, Any]], str]
    natural_action_plan_response: Callable[[Mapping[str, Any]], str]
    no_pending_action_plan_response: Callable[[], str]
    current_rca_context_event: Callable[[str], dict[str, Any]]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class NaturalActionFollowupStreamEvent:
    payload: str
    latest_rca_context: dict[str, Any] | None = None


def _stream_event(
    dependencies: NaturalActionFollowupFlowDependencies,
    event: Any,
    *,
    latest_rca_context: dict[str, Any] | None = None,
) -> NaturalActionFollowupStreamEvent:
    return NaturalActionFollowupStreamEvent(
        dependencies.sse(event),
        latest_rca_context=latest_rca_context,
    )


def _result_event(
    *,
    dependencies: NaturalActionFollowupFlowDependencies,
    request_id: str,
    result: Mapping[str, Any],
    status: str,
    summary: str,
) -> NaturalActionFollowupStreamEvent:
    return _stream_event(
        dependencies,
        {
            "type": "tool_result",
            "detail": json.dumps(
                dependencies.redact_sensitive(result),
                ensure_ascii=False,
                indent=2,
            ),
            "id": f"{request_id}-natural-action-followup",
            "name": "natural_action_followup",
            "result": result,
            "status": status,
            "summary": summary,
        },
    )


def _rca_event(
    dependencies: NaturalActionFollowupFlowDependencies,
) -> NaturalActionFollowupStreamEvent:
    rca_context_event = dependencies.current_rca_context_event("post_answer")
    return _stream_event(
        dependencies,
        rca_context_event,
        latest_rca_context=rca_context_event["context"],
    )


async def stream_chat_natural_action_followup(
    *,
    authorization: str,
    dependencies: NaturalActionFollowupFlowDependencies,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any],
) -> AsyncIterator[NaturalActionFollowupStreamEvent]:
    pending_plan_result = dependencies.latest_pending_action_plan_result(subject)
    contextual_plan = False
    plan_result = pending_plan_result

    if not plan_result:
        contextual_request = dependencies.recent_natural_action_request(request)
        if contextual_request:
            plan_result = await dependencies.create_natural_action_plan(
                contextual_request,
                authorization,
                subject,
                incident_id=incident_id,
                run_id=run_id,
            )
            contextual_plan = bool(plan_result)

        if plan_result and plan_result.get("status") != "planned":
            yield _result_event(
                dependencies=dependencies,
                request_id=request_id,
                result=plan_result,
                status="failed",
                summary="최근 대화의 AIOps 조치 대상 확인 실패",
            )
            yield _stream_event(
                dependencies,
                {
                    "type": "text",
                    "content": dependencies.natural_action_plan_response(plan_result),
                },
            )
            yield _rca_event(dependencies)
            yield _stream_event(
                dependencies,
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "completed",
                    "message": "Gateway 최근 맥락 조치 대상 확인 실패",
                },
            )
            yield _stream_event(dependencies, "[DONE]")
            return

        if not plan_result:
            no_plan_result = {
                "status": "not_found",
                "reason": "no_pending_action_plan",
            }
            yield _result_event(
                dependencies=dependencies,
                request_id=request_id,
                result=no_plan_result,
                status="skipped",
                summary="실행할 Gateway Action Plan 없음",
            )
            yield _stream_event(
                dependencies,
                {
                    "type": "text",
                    "content": dependencies.no_pending_action_plan_response(),
                },
            )
            yield _rca_event(dependencies)
            yield _stream_event(
                dependencies,
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "completed",
                    "message": "Gateway 후속 실행 대상 없음",
                },
            )
            yield _stream_event(dependencies, "[DONE]")
            return

    yield _stream_event(
        dependencies,
        {
            "type": "tool_call",
            "id": f"{request_id}-natural-action-followup",
            "name": "natural_action_followup",
            "summary": (
                "최근 대화의 AIOps 조치 요청 후속 실행"
                if contextual_plan
                else "최근 AIOps Action Plan 후속 실행"
            ),
        },
    )
    execution_result = await dependencies.execute_natural_action_plan_result(
        plan_result,
        authorization,
        subject,
    )
    yield _result_event(
        dependencies=dependencies,
        request_id=request_id,
        result=execution_result,
        status="success" if execution_result.get("status") == "executed" else "failed",
        summary=(
            "최근 대화의 AIOps 조치 후속 실행 완료"
            if contextual_plan
            else "최근 AIOps Action Plan 후속 실행 완료"
        ),
    )
    yield _stream_event(
        dependencies,
        {
            "type": "text",
            "content": dependencies.natural_action_execution_response(execution_result),
        },
    )
    yield _stream_event(
        dependencies,
        {
            "type": "run_status",
            "runId": run_id,
            "stage": "completed",
            "message": (
                "Gateway 최근 맥락 조치 실행 완료"
                if contextual_plan
                else "Gateway 후속 조치 실행 완료"
            ),
        },
    )
    yield _rca_event(dependencies)
    yield _stream_event(dependencies, "[DONE]")
