from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CleanupChatFlowDependencies:
    should_create_latest_candidate: Callable[[Any, Mapping[str, str]], bool]
    should_create_candidate: Callable[[Any, Mapping[str, str]], bool]
    should_clarify_scope: Callable[[Any, Mapping[str, str]], bool]
    delete_count_from_message: Callable[[str], int]
    select_latest_rows: Callable[
        [Mapping[str, str], str | None, int],
        Sequence[Mapping[str, str]],
    ]
    remember_candidate: Callable[..., dict[str, Any]]
    candidate_response: Callable[[Mapping[str, Any]], str]
    clarification_response: Callable[[Any, Mapping[str, str]], str]
    redact_sensitive: Callable[[Any], Any]
    current_rca_context_event: Callable[[str], dict[str, Any]]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class CleanupChatFlowEvent:
    payload: str
    latest_rca_context: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CleanupChatFlowResult:
    handled: bool
    events: Iterator[CleanupChatFlowEvent]


def start_cleanup_chat_flow(
    *,
    cleanup_focus: Mapping[str, str],
    dependencies: CleanupChatFlowDependencies,
    gateway_evidence: str | None,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
) -> CleanupChatFlowResult:
    if dependencies.should_create_latest_candidate(request, cleanup_focus):
        branch = "latest"
    elif dependencies.should_create_candidate(request, cleanup_focus):
        branch = "general"
    elif dependencies.should_clarify_scope(request, cleanup_focus):
        branch = "clarification"
    else:
        return CleanupChatFlowResult(handled=False, events=iter(()))

    return CleanupChatFlowResult(
        handled=True,
        events=_stream_cleanup_branch(
            branch=branch,
            cleanup_focus=cleanup_focus,
            dependencies=dependencies,
            gateway_evidence=gateway_evidence,
            incident_id=incident_id,
            request=request,
            request_id=request_id,
            run_id=run_id,
        ),
    )


def _stream_cleanup_branch(
    *,
    branch: str,
    cleanup_focus: Mapping[str, str],
    dependencies: CleanupChatFlowDependencies,
    gateway_evidence: str | None,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
) -> Iterator[CleanupChatFlowEvent]:
    if branch == "latest":
        requested_count = dependencies.delete_count_from_message(request.message or "")
        selected_rows = dependencies.select_latest_rows(
            cleanup_focus,
            gateway_evidence,
            requested_count,
        )
        cleanup_candidate = dependencies.remember_candidate(
            cleanup_focus,
            incident_id=incident_id,
            run_id=run_id,
            selected_rows=selected_rows,
            requested_count=requested_count,
        )
        yield CleanupChatFlowEvent(
            dependencies.sse(
                {
                    "type": "tool_result",
                    "detail": json.dumps(
                        dependencies.redact_sensitive(
                            {
                                "candidate": {
                                    "id": cleanup_candidate.get("id"),
                                    "parameters": cleanup_candidate.get("parameters"),
                                    "sourceType": cleanup_candidate.get("sourceType"),
                                    "target": cleanup_candidate.get("target"),
                                    "title": cleanup_candidate.get("title"),
                                },
                                "status": "action_candidate_ready",
                            }
                        ),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "id": f"{request_id}-conversation-cleanup-latest-delete-review-candidate",
                    "name": "conversation_cleanup_latest_delete_review_candidate",
                    "result": {
                        "candidateCount": 1,
                        "selectedPodCount": len(selected_rows),
                        "status": "action_candidate_ready",
                    },
                    "status": "success",
                    "summary": "최신 테스트 Pod 삭제 검토 Action Plan 후보 1건 준비",
                }
            )
        )
        yield CleanupChatFlowEvent(
            dependencies.sse(
                {
                    "type": "text",
                    "content": dependencies.candidate_response(cleanup_candidate),
                    "source": "copilot_clarification",
                    "answerContract": "cleanup-latest-delete-review-candidate-v0.2.9",
                }
            )
        )
        yield from _completion_events(
            dependencies,
            run_id=run_id,
            message="Gateway 최신 테스트 Pod 삭제 검토 후보 준비 완료",
        )
        return

    if branch == "general":
        cleanup_candidate = dependencies.remember_candidate(
            cleanup_focus,
            incident_id=incident_id,
            run_id=run_id,
        )
        yield CleanupChatFlowEvent(
            dependencies.sse(
                {
                    "type": "tool_result",
                    "detail": json.dumps(
                        dependencies.redact_sensitive(
                            {
                                "candidate": {
                                    "id": cleanup_candidate.get("id"),
                                    "sourceType": cleanup_candidate.get("sourceType"),
                                    "target": cleanup_candidate.get("target"),
                                    "title": cleanup_candidate.get("title"),
                                },
                                "status": "action_candidate_ready",
                            }
                        ),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "id": f"{request_id}-conversation-cleanup-review-candidate",
                    "name": "conversation_cleanup_review_candidate",
                    "result": {
                        "candidateCount": 1,
                        "status": "action_candidate_ready",
                    },
                    "status": "success",
                    "summary": "테스트 Pod 정리 검토 Action Plan 후보 1건 준비",
                }
            )
        )
        yield CleanupChatFlowEvent(
            dependencies.sse(
                {
                    "type": "text",
                    "content": dependencies.candidate_response(cleanup_candidate),
                    "source": "copilot_clarification",
                    "answerContract": "cleanup-review-candidate-v0.2.9",
                }
            )
        )
        yield from _completion_events(
            dependencies,
            run_id=run_id,
            message="Gateway 테스트 Pod 정리 검토 후보 준비 완료",
        )
        return

    clarification_result = {
        "conversationFocus": cleanup_focus,
        "reason": "ambiguous_cleanup_scope",
        "status": "clarification_required",
    }
    yield CleanupChatFlowEvent(
        dependencies.sse(
            {
                "type": "tool_result",
                "detail": json.dumps(
                    dependencies.redact_sensitive(clarification_result),
                    ensure_ascii=False,
                    indent=2,
                ),
                "id": f"{request_id}-cleanup-scope-clarification",
                "name": "cleanup_scope_clarification",
                "result": clarification_result,
                "status": "skipped",
                "summary": "정리 대상 범위 확인 필요",
            }
        )
    )
    yield CleanupChatFlowEvent(
        dependencies.sse(
            {
                "type": "text",
                "content": dependencies.clarification_response(request, cleanup_focus),
                "source": "copilot_clarification",
                "answerContract": "cleanup-scope-clarification-v0.2.9",
            }
        )
    )
    yield from _completion_events(
        dependencies,
        run_id=run_id,
        message="Gateway 정리 대상 범위 확인 요청 완료",
    )


def _completion_events(
    dependencies: CleanupChatFlowDependencies,
    *,
    run_id: str,
    message: str,
) -> Iterator[CleanupChatFlowEvent]:
    rca_context_event = dependencies.current_rca_context_event("post_answer")
    yield CleanupChatFlowEvent(
        dependencies.sse(rca_context_event),
        latest_rca_context=rca_context_event["context"],
    )
    yield CleanupChatFlowEvent(
        dependencies.sse(
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "completed",
                "message": message,
            }
        )
    )
    yield CleanupChatFlowEvent(dependencies.sse("[DONE]"))
