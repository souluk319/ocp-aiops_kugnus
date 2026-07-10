from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NaturalActionProposalFlowDependencies:
    parse_intent: Callable[[Any], Mapping[str, Any] | None]
    execution_mode: Callable[[Any], str]
    allows_actions: Callable[[Any], bool]
    allows_immediate_actions: Callable[[Any], bool]
    create_plan: Callable[..., Awaitable[dict[str, Any] | None]]
    execute_plan: Callable[..., Awaitable[dict[str, Any]]]
    unresolved_response: Callable[[Any], str]
    evidence_check_response: Callable[[Mapping[str, Any]], str]
    plan_response: Callable[[Mapping[str, Any]], str]
    execution_response: Callable[[Mapping[str, Any]], str]
    redact_sensitive: Callable[[Any], Any]
    current_rca_context_event: Callable[[str], dict[str, Any]]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class NaturalActionProposalStreamEvent:
    payload: str
    latest_rca_context: dict[str, Any] | None = None


def _event(
    dependencies: NaturalActionProposalFlowDependencies,
    value: Any,
    *,
    latest_rca_context: dict[str, Any] | None = None,
) -> NaturalActionProposalStreamEvent:
    return NaturalActionProposalStreamEvent(
        payload=dependencies.sse(value),
        latest_rca_context=latest_rca_context,
    )


def _result_event(
    dependencies: NaturalActionProposalFlowDependencies,
    *,
    detail_value: Mapping[str, Any],
    event_id: str,
    name: str,
    result: Mapping[str, Any],
    status: str,
    summary: str,
) -> NaturalActionProposalStreamEvent:
    return _event(
        dependencies,
        {
            "type": "tool_result",
            "detail": json.dumps(
                dependencies.redact_sensitive(detail_value),
                ensure_ascii=False,
                indent=2,
            ),
            "id": event_id,
            "name": name,
            "result": result,
            "status": status,
            "summary": summary,
        },
    )


def _rca_event(
    dependencies: NaturalActionProposalFlowDependencies,
) -> NaturalActionProposalStreamEvent:
    event = dependencies.current_rca_context_event("post_answer")
    return _event(
        dependencies,
        event,
        latest_rca_context=event["context"],
    )


async def stream_chat_natural_action_proposal(
    *,
    authorization: str,
    dependencies: NaturalActionProposalFlowDependencies,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any],
) -> AsyncIterator[NaturalActionProposalStreamEvent]:
    intent = dependencies.parse_intent(request)
    if not intent:
        unresolved = {
            "executionMode": dependencies.execution_mode(request),
            "message": request.message,
            "status": "unresolved",
        }
        yield _result_event(
            dependencies,
            detail_value=unresolved,
            event_id=f"{request_id}-natural-action-unresolved",
            name="natural_action_unresolved",
            result=unresolved,
            status="skipped",
            summary="변경 요청 대상 해석 실패",
        )
        yield _event(
            dependencies,
            {"type": "text", "content": dependencies.unresolved_response(request)},
        )
        yield _rca_event(dependencies)
        yield _event(
            dependencies,
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "completed",
                "message": "Gateway 변경 요청 해석 실패",
            },
        )
        yield _event(dependencies, "[DONE]")
        return

    if not dependencies.allows_actions(request):
        skipped = {
            "executionMode": dependencies.execution_mode(request),
            "intent": intent,
            "status": "skipped",
        }
        yield _result_event(
            dependencies,
            detail_value=skipped,
            event_id=f"{request_id}-natural-action-execute-gate",
            name="natural_action_plan",
            result=skipped,
            status="skipped",
            summary="읽기 전용 모드로 조치 계획 생성 생략",
        )
        yield _event(
            dependencies,
            {
                "type": "text",
                "content": dependencies.evidence_check_response(intent),
            },
        )
        yield _rca_event(dependencies)
        yield _event(
            dependencies,
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "completed",
                "message": "Gateway 읽기 전용 모드 안내 완료",
            },
        )
        yield _event(dependencies, "[DONE]")
        return

    plan = await dependencies.create_plan(
        request,
        authorization,
        subject,
        incident_id=incident_id,
        run_id=run_id,
    )
    if not plan:
        return

    yield _result_event(
        dependencies,
        detail_value=plan,
        event_id=f"{request_id}-natural-action-plan",
        name="natural_action_plan",
        result=plan,
        status="success" if plan.get("status") == "planned" else "failed",
        summary="자연어 조치 요청을 Action Plan으로 변환",
    )

    if dependencies.allows_immediate_actions(request) and plan.get("status") == "planned":
        yield _event(
            dependencies,
            {
                "type": "tool_call",
                "id": f"{request_id}-natural-action-execute",
                "name": "natural_action_execute",
                "summary": "실험용 자연어 AIOps 조치 즉시 실행",
            },
        )
        execution = await dependencies.execute_plan(plan, authorization, subject)
        yield _result_event(
            dependencies,
            detail_value=execution,
            event_id=f"{request_id}-natural-action-execute",
            name="natural_action_execute",
            result=execution,
            status="success" if execution.get("status") == "executed" else "failed",
            summary="자연어 AIOps 조치 실행 완료",
        )
        yield _event(
            dependencies,
            {"type": "text", "content": dependencies.execution_response(execution)},
        )
        yield _event(
            dependencies,
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "completed",
                "message": "Gateway 자연어 조치 실행 완료",
            },
        )
        yield _rca_event(dependencies)
        yield _event(dependencies, "[DONE]")
        return

    text_event = {"type": "text", "content": dependencies.plan_response(plan)}
    if plan.get("status") == "planned":
        text_event["answerContract"] = "natural-action-plan-v0.2.1"
    yield _event(dependencies, text_event)
    yield _event(
        dependencies,
        {
            "type": "run_status",
            "runId": run_id,
            "stage": "completed",
            "message": "Gateway 자연어 조치 계획 생성 완료",
        },
    )
    yield _rca_event(dependencies)
    yield _event(dependencies, "[DONE]")
