from __future__ import annotations

import asyncio
import json
from dataclasses import FrozenInstanceError, dataclass
from pathlib import Path
from typing import Any

import pytest
import httpx

from komsco_ai_gateway.answer_streaming import sse
from komsco_ai_gateway.chat_cleanup_flow import (
    CleanupChatFlowDependencies,
    CleanupChatFlowEvent,
    CleanupChatFlowResult,
    start_cleanup_chat_flow,
)


FOCUS = {"namespace": "gpu-test", "podPattern": "aiops-test-pod-*"}
CANDIDATE = {
    "id": "candidate-1",
    "parameters": {"selectedPods": ["pod-new", "pod-old"]},
    "sourceType": "test_pod_latest_delete_review",
    "target": {"kind": "Pod", "namespace": "gpu-test", "name": "aiops-test-pod-*"},
    "title": "최신 테스트 Pod 2개 삭제 검토",
}
SELECTED_ROWS = [
    {"namespace": "gpu-test", "pod": "pod-new"},
    {"namespace": "gpu-test", "pod": "pod-old"},
]
RCA_CONTEXT = {"metadata": {"phase": "post_answer", "digest": "sha256:golden"}}


@dataclass
class Request:
    message: str = "cleanup"


def dependencies(
    *,
    latest: bool = False,
    general: bool = False,
    clarify: bool = False,
    calls: dict[str, list[Any]] | None = None,
) -> CleanupChatFlowDependencies:
    observed = calls if calls is not None else {}

    def record(name: str, value: Any) -> None:
        observed.setdefault(name, []).append(value)

    def should_latest(request: Any, focus: Any) -> bool:
        record("latest", (request, focus))
        return latest

    def should_general(request: Any, focus: Any) -> bool:
        record("general", (request, focus))
        return general

    def should_clarify(request: Any, focus: Any) -> bool:
        record("clarify", (request, focus))
        return clarify

    def delete_count(message: str) -> int:
        record("delete_count", message)
        return 2

    def select_rows(focus: Any, evidence: Any, count: int) -> list[dict[str, str]]:
        record("select_rows", (focus, evidence, count))
        return SELECTED_ROWS

    def remember(focus: Any, **kwargs: Any) -> dict[str, Any]:
        record("remember", (focus, kwargs))
        return CANDIDATE

    def redact(value: Any) -> Any:
        record("redact", value)
        return value

    def current_rca(phase: str) -> dict[str, Any]:
        record("rca", phase)
        return {"type": "rca_context", "context": RCA_CONTEXT}

    return CleanupChatFlowDependencies(
        should_create_latest_candidate=should_latest,
        should_create_candidate=should_general,
        should_clarify_scope=should_clarify,
        delete_count_from_message=delete_count,
        select_latest_rows=select_rows,
        remember_candidate=remember,
        candidate_response=lambda candidate: f"candidate answer: {candidate['id']}",
        clarification_response=lambda request, focus: (
            f"clarify: {focus['namespace']} / {request.message}"
        ),
        redact_sensitive=redact,
        current_rca_context_event=current_rca,
        sse=sse,
    )


def run_flow(
    deps: CleanupChatFlowDependencies,
    *,
    request: Request | None = None,
) -> CleanupChatFlowResult:
    return start_cleanup_chat_flow(
        cleanup_focus=FOCUS,
        dependencies=deps,
        gateway_evidence="pod evidence",
        incident_id="incident-1",
        request=request or Request(),
        request_id="request-1",
        run_id="run-1",
    )


def completion_payloads(message: str) -> list[str]:
    return [
        sse({"type": "rca_context", "context": RCA_CONTEXT}),
        sse(
            {
                "type": "run_status",
                "runId": "run-1",
                "stage": "completed",
                "message": message,
            }
        ),
        sse("[DONE]"),
    ]


def test_latest_cleanup_delete_review_exact_golden_events_and_candidate_args() -> None:
    calls: dict[str, list[Any]] = {}
    request = Request("latest 2 cleanup")
    result = run_flow(dependencies(latest=True, calls=calls), request=request)

    assert result.handled is True
    assert "remember" not in calls
    events = list(result.events)
    detail = json.dumps(
        {
            "candidate": {
                "id": CANDIDATE["id"],
                "parameters": CANDIDATE["parameters"],
                "sourceType": CANDIDATE["sourceType"],
                "target": CANDIDATE["target"],
                "title": CANDIDATE["title"],
            },
            "status": "action_candidate_ready",
        },
        ensure_ascii=False,
        indent=2,
    )
    expected = [
        sse(
            {
                "type": "tool_result",
                "detail": detail,
                "id": "request-1-conversation-cleanup-latest-delete-review-candidate",
                "name": "conversation_cleanup_latest_delete_review_candidate",
                "result": {
                    "candidateCount": 1,
                    "selectedPodCount": 2,
                    "status": "action_candidate_ready",
                },
                "status": "success",
                "summary": "최신 테스트 Pod 삭제 검토 Action Plan 후보 1건 준비",
            }
        ),
        sse(
            {
                "type": "text",
                "content": "candidate answer: candidate-1",
                "source": "copilot_clarification",
                "answerContract": "cleanup-latest-delete-review-candidate-v0.2.9",
            }
        ),
        *completion_payloads("Gateway 최신 테스트 Pod 삭제 검토 후보 준비 완료"),
    ]

    assert [event.payload for event in events] == expected
    assert calls["delete_count"] == ["latest 2 cleanup"]
    assert calls["select_rows"] == [(FOCUS, "pod evidence", 2)]
    assert calls["remember"] == [
        (
            FOCUS,
            {
                "incident_id": "incident-1",
                "run_id": "run-1",
                "selected_rows": SELECTED_ROWS,
                "requested_count": 2,
            },
        )
    ]
    assert calls["redact"] == [
        {
            "candidate": {
                "id": CANDIDATE["id"],
                "parameters": CANDIDATE["parameters"],
                "sourceType": CANDIDATE["sourceType"],
                "target": CANDIDATE["target"],
                "title": CANDIDATE["title"],
            },
            "status": "action_candidate_ready",
        }
    ]


def test_general_cleanup_review_exact_golden_events_and_candidate_args() -> None:
    calls: dict[str, list[Any]] = {}
    events = list(run_flow(dependencies(general=True, calls=calls)).events)
    detail = json.dumps(
        {
            "candidate": {
                "id": CANDIDATE["id"],
                "sourceType": CANDIDATE["sourceType"],
                "target": CANDIDATE["target"],
                "title": CANDIDATE["title"],
            },
            "status": "action_candidate_ready",
        },
        ensure_ascii=False,
        indent=2,
    )
    expected = [
        sse(
            {
                "type": "tool_result",
                "detail": detail,
                "id": "request-1-conversation-cleanup-review-candidate",
                "name": "conversation_cleanup_review_candidate",
                "result": {"candidateCount": 1, "status": "action_candidate_ready"},
                "status": "success",
                "summary": "테스트 Pod 정리 검토 Action Plan 후보 1건 준비",
            }
        ),
        sse(
            {
                "type": "text",
                "content": "candidate answer: candidate-1",
                "source": "copilot_clarification",
                "answerContract": "cleanup-review-candidate-v0.2.9",
            }
        ),
        *completion_payloads("Gateway 테스트 Pod 정리 검토 후보 준비 완료"),
    ]

    assert [event.payload for event in events] == expected
    assert calls["remember"] == [
        (FOCUS, {"incident_id": "incident-1", "run_id": "run-1"})
    ]
    assert "delete_count" not in calls
    assert "select_rows" not in calls


def test_cleanup_scope_clarification_exact_golden_events() -> None:
    calls: dict[str, list[Any]] = {}
    request = Request("maybe cleanup")
    events = list(
        run_flow(dependencies(clarify=True, calls=calls), request=request).events
    )
    clarification = {
        "conversationFocus": FOCUS,
        "reason": "ambiguous_cleanup_scope",
        "status": "clarification_required",
    }
    expected = [
        sse(
            {
                "type": "tool_result",
                "detail": json.dumps(clarification, ensure_ascii=False, indent=2),
                "id": "request-1-cleanup-scope-clarification",
                "name": "cleanup_scope_clarification",
                "result": clarification,
                "status": "skipped",
                "summary": "정리 대상 범위 확인 필요",
            }
        ),
        sse(
            {
                "type": "text",
                "content": "clarify: gpu-test / maybe cleanup",
                "source": "copilot_clarification",
                "answerContract": "cleanup-scope-clarification-v0.2.9",
            }
        ),
        *completion_payloads("Gateway 정리 대상 범위 확인 요청 완료"),
    ]

    assert [event.payload for event in events] == expected
    assert calls["redact"] == [clarification]
    assert "remember" not in calls


def test_branch_priority_is_latest_then_general_then_clarification() -> None:
    calls: dict[str, list[Any]] = {}
    events = list(
        run_flow(
            dependencies(latest=True, general=True, clarify=True, calls=calls)
        ).events
    )

    assert calls["latest"]
    assert "general" not in calls
    assert "clarify" not in calls
    assert "conversation_cleanup_latest_delete_review_candidate" in events[0].payload


def test_unhandled_returns_no_events_without_candidate_side_effects() -> None:
    calls: dict[str, list[Any]] = {}
    result = run_flow(dependencies(calls=calls))

    assert result.handled is False
    assert list(result.events) == []
    assert list(calls) == ["latest", "general", "clarify"]


def test_rca_context_is_marked_on_the_rca_event_only_and_done_is_single() -> None:
    events = list(run_flow(dependencies(general=True)).events)

    marked = [event for event in events if event.latest_rca_context is not None]
    assert marked == [
        CleanupChatFlowEvent(
            sse({"type": "rca_context", "context": RCA_CONTEXT}),
            latest_rca_context=RCA_CONTEXT,
        )
    ]
    assert events[-1].payload == sse("[DONE]")
    assert sum(event.payload == sse("[DONE]") for event in events) == 1


def test_dependencies_are_frozen_and_main_factory_uses_current_bindings(monkeypatch) -> None:
    import komsco_ai_gateway.main as gateway_main

    def first(*_args: Any, **_kwargs: Any) -> bool:
        return False

    def second(*_args: Any, **_kwargs: Any) -> bool:
        return True

    monkeypatch.setattr(
        gateway_main,
        "should_create_latest_cleanup_delete_review_candidate",
        first,
    )
    current_rca = lambda phase: {"type": "rca_context", "context": {"phase": phase}}
    first_dependencies = gateway_main.cleanup_chat_flow_dependencies(current_rca)
    monkeypatch.setattr(
        gateway_main,
        "should_create_latest_cleanup_delete_review_candidate",
        second,
    )
    second_dependencies = gateway_main.cleanup_chat_flow_dependencies(current_rca)

    assert first_dependencies.should_create_latest_candidate is first
    assert second_dependencies.should_create_latest_candidate is second
    assert second_dependencies.remember_candidate is gateway_main.remember_conversation_cleanup_review_candidate
    assert second_dependencies.select_latest_rows is gateway_main.select_latest_cleanup_pod_rows
    assert second_dependencies.current_rca_context_event is current_rca
    with pytest.raises(FrozenInstanceError):
        second_dependencies.sse = lambda value: str(value)  # type: ignore[misc]


def test_main_updates_rca_context_before_cleanup_iterator_resumes(monkeypatch) -> None:
    import komsco_ai_gateway.main as gateway_main

    latest_context = {"metadata": {"digest": "cleanup-main-marker"}}
    update_observed: list[bool] = []

    def fake_start(**_kwargs: Any) -> CleanupChatFlowResult:
        def events():
            yield CleanupChatFlowEvent(
                sse({"type": "rca_context", "context": latest_context}),
                latest_rca_context=latest_context,
            )
            update_observed.append(gateway_main.LAST_RCA_CONTEXT is latest_context)
            yield CleanupChatFlowEvent(sse("[DONE]"))

        return CleanupChatFlowResult(handled=True, events=events())

    async def fake_subject_review(_authorization: str) -> dict[str, Any]:
        return {"username": "dev-user", "uid": "uid-dev", "groups": []}

    async def fake_access_review(_authorization: str) -> dict[str, Any]:
        return {"allowed": True, "enabled": True, "required": True}

    monkeypatch.setattr(gateway_main, "start_cleanup_chat_flow", fake_start)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_access_review)
    monkeypatch.setattr(
        gateway_main,
        "conversation_focus_from_request",
        lambda _request: FOCUS,
    )

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer token"},
                json={"message": "정리 범위를 확인해줘"},
            )
        assert response.status_code == 200

    asyncio.run(run())
    assert update_observed == [True]


def test_extracted_module_has_no_main_import_and_domain_helpers_remain_owners() -> None:
    import komsco_ai_gateway.main as gateway_main
    import komsco_ai_gateway.namespace_cleanup as namespace_cleanup

    module_path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_cleanup_flow.py"
    source = module_path.read_text(encoding="utf-8")

    assert "from .main import" not in source
    assert "import komsco_ai_gateway.main" not in source
    assert gateway_main.cleanup_delete_count_from_message is namespace_cleanup.cleanup_delete_count_from_message
    assert gateway_main.select_latest_cleanup_pod_rows.__module__ == gateway_main.__name__
    assert gateway_main.cleanup_review_candidate_response is namespace_cleanup.cleanup_review_candidate_response
