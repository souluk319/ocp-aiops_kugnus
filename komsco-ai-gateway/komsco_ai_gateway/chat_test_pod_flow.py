from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class TestPodFlowDependencies:
    execution_mode: Callable[[Any], str]
    answer_language: Callable[[Any], str]
    parse_request: Callable[[str], Mapping[str, Any]]
    request_is_ready: Callable[[Mapping[str, Any]], bool]
    collect_preflight: Callable[..., Awaitable[dict[str, Any]]]
    disabled_answer: Callable[..., str]
    action_capable_mode: Callable[[str], bool]
    candidate_from_preflight: Callable[..., dict[str, Any]]
    remember_candidate: Callable[[dict[str, Any]], None]
    answer: Callable[..., str]
    tool_plan: Callable[..., Mapping[str, Any]]
    redact_sensitive: Callable[[Any], Any]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class TestPodStreamEvent:
    payload: str
    answer_chunk: str | None = None


def _event(dependencies, value, *, answer_chunk=None):
    return TestPodStreamEvent(dependencies.sse(value), answer_chunk=answer_chunk)


async def stream_test_pod_create(
    *,
    authorization: str,
    dependencies: TestPodFlowDependencies,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
) -> AsyncIterator[TestPodStreamEvent]:
    execution_mode = dependencies.execution_mode(request)
    language = dependencies.answer_language(request)
    create_request = dependencies.parse_request(request.message)
    if not dependencies.request_is_ready(create_request):
        preflight = await dependencies.collect_preflight(authorization, create_request)
        answer_text = dependencies.disabled_answer(create_request, language)
        yield _event(
            dependencies,
            {
                "type": "tool_result",
                "detail": json.dumps(dependencies.redact_sensitive(preflight), ensure_ascii=False, indent=2),
                "id": f"{request_id}-test-pod-create-disabled",
                "name": "test_pod_create_guard",
                "result": dependencies.redact_sensitive(preflight),
                "status": "skipped",
                "summary": "테스트 Pod 생성은 현재 제품 조건에서 비활성",
            },
        )
        yield _event(
            dependencies,
            {
                "type": "text",
                "content": answer_text,
                "source": "gateway_direct",
                "answerContract": "test-pod-create-guard-v1",
            },
            answer_chunk=answer_text,
        )
        yield _event(
            dependencies,
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "completed",
                "message": "Gateway 테스트 Pod 생성 가드 확인 완료",
            },
        )
        yield _event(dependencies, "[DONE]")
        return

    action_mode = dependencies.action_capable_mode(execution_mode)
    yield _event(
        dependencies,
        {
            "type": "run_status",
            "runId": run_id,
            "stage": "started",
            "message": "Test Pod creation preflight started" if language == "en" else "테스트 Pod 생성 사전 확인 시작",
        },
    )
    yield _event(
        dependencies,
        {
            "type": "tool_call",
            "id": f"{request_id}-test-pod-create-preflight",
            "name": "oc_test_pod_create_preflight",
            "summary": "Target namespace and server check" if language == "en" else "대상 namespace 및 서버 확인",
        },
    )
    preflight = await dependencies.collect_preflight(authorization, create_request)
    can_propose = action_mode and bool(preflight.get("ok"))
    if can_propose:
        dependencies.remember_candidate(
            dependencies.candidate_from_preflight(
                create_request,
                preflight,
                run_id,
                incident_id,
            )
        )
    answer_text = dependencies.answer(create_request, preflight, execution_mode, language)
    redacted_preflight = dependencies.redact_sensitive(preflight)
    yield _event(
        dependencies,
        {
            "type": "tool_result",
            "detail": json.dumps(redacted_preflight, ensure_ascii=False, indent=2),
            "id": f"{request_id}-test-pod-create-preflight",
            "name": "oc_test_pod_create_preflight",
            "result": redacted_preflight,
            "status": "success" if preflight.get("ok") else "failed",
            "summary": (
                f"{create_request.get('namespace')} namespace preflight"
                if language == "en"
                else f"{create_request.get('namespace')} namespace 사전 확인"
            ),
        },
    )
    yield _event(
        dependencies,
        {
            "type": "tool_plan",
            "plan": {
                **dependencies.tool_plan(create_request, execution_mode, can_propose=can_propose),
                "validation": {
                    "ok": bool(preflight.get("ok")),
                    "status": (
                        "action_candidate_ready"
                        if can_propose
                        else "read_only_preflight_collected"
                        if preflight.get("ok")
                        else preflight.get("status")
                    ),
                },
            },
            "runId": run_id,
            "status": "success" if preflight.get("ok") else "failed",
        },
    )
    yield _event(
        dependencies,
        {
            "type": "text",
            "content": answer_text,
            "source": "gateway_direct" if preflight.get("ok") else "gateway_fallback",
        },
        answer_chunk=answer_text,
    )
    yield _event(
        dependencies,
        {
            "type": "run_status",
            "runId": run_id,
            "stage": "completed" if preflight.get("ok") else "failed",
            "message": "Test Pod creation preflight completed" if language == "en" else "테스트 Pod 생성 사전 확인 완료",
        },
    )
    yield _event(dependencies, "[DONE]")
