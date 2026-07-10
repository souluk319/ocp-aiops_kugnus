from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class OlsAnswerState:
    emitted_answer_text: bool = False
    tool_results: list[Mapping[str, Any]] = field(default_factory=list)
    attempt_count: int = 0
    answer_chunks: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class OlsAnswerFlowDependencies:
    empty_answer_retries: int
    require_final_answer: bool
    call_ols_stream: Callable[..., Any]
    stream_with_heartbeats: Callable[..., Any]
    normalize_ols_event: Callable[[Any], Mapping[str, Any]]
    redact_sensitive: Callable[[Any], Any]
    answer_language_contract: Callable[[Any], str]
    safe_exception_text: Callable[[Exception], str]
    update_ols_stream_status: Callable[..., None]
    active_llm_stage: Callable[[], str]
    active_llm_label: Callable[[], str]
    build_evidence_reference_events: Callable[..., list[dict[str, Any]]]
    sse: Callable[[Any], str]


async def stream_ols_answer_attempts(
    *,
    authorization: str,
    dependencies: OlsAnswerFlowDependencies,
    gateway_context: Mapping[str, Any],
    incident_id: str,
    ols_query: str,
    request: Any,
    request_id: str,
    run_id: str,
    state: OlsAnswerState,
    subject: Mapping[str, Any],
    text_reference_filter: Any,
) -> AsyncIterator[str]:
    context_digest = gateway_context["metadata"]["digest"]
    for attempt in range(dependencies.empty_answer_retries + 1):
        attempt_emitted_answer_text = False
        state.attempt_count = attempt + 1
        active_query = ols_query
        if attempt > 0:
            active_query = (
                f"{dependencies.redact_sensitive(request.message).strip()}\n\n"
                "Previous OpenShift Lightspeed response ended before final answer text. "
                "Do not call tools again in this retry. "
                f"{dependencies.answer_language_contract(request)} "
                "Return a concise final answer using the OpenShift evidence already observed in this conversation. "
                "If the available facts do not confirm the cause, say exactly what is unconfirmed. "
                "Do not print secrets or raw credentials."
            )

        try:
            async for ols_event in dependencies.stream_with_heartbeats(
                dependencies.call_ols_stream(
                    authorization,
                    active_query,
                    request.conversationId,
                    request.attachments,
                    gateway_context,
                ),
                run_id,
            ):
                normalized = dependencies.normalize_ols_event(ols_event)
                if normalized.get("type") == "text":
                    filtered = text_reference_filter.filter(
                        str(normalized.get("content") or "")
                    )
                    if filtered:
                        if filtered.strip():
                            state.emitted_answer_text = True
                            attempt_emitted_answer_text = True
                            state.answer_chunks.append(filtered)
                        text_event: dict[str, Any] = {"type": "text", "content": filtered}
                        for key in (
                            "fallbackAnswer",
                            "gatewayContextDigest",
                            "source",
                            "streamProbe",
                        ):
                            if key in normalized:
                                text_event[key] = normalized[key]
                        yield dependencies.sse(text_event)
                    continue

                if normalized.get("type") == "end":
                    final_text = text_reference_filter.flush()
                    if final_text:
                        if final_text.strip():
                            state.emitted_answer_text = True
                            attempt_emitted_answer_text = True
                            state.answer_chunks.append(final_text)
                        yield dependencies.sse({"type": "text", "content": final_text})
                    if (
                        not attempt_emitted_answer_text
                        and attempt < dependencies.empty_answer_retries
                    ):
                        continue

                yield dependencies.sse(normalized)
                if normalized.get("type") == "tool_result":
                    state.tool_results.append(dict(normalized))
                    for evidence_event in dependencies.build_evidence_reference_events(
                        event=normalized,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="ols-tool-result",
                        subject=subject,
                    ):
                        yield dependencies.sse(evidence_event)
        except Exception as exc:
            safe_detail = dependencies.safe_exception_text(exc)
            dependencies.update_ols_stream_status(
                "failed",
                context_digest=context_digest,
                fallback_active=(
                    not dependencies.require_final_answer
                    and attempt >= dependencies.empty_answer_retries
                ),
                reason=safe_detail,
            )
            error_event = {
                "type": "tool_result",
                "detail": safe_detail,
                "id": f"{request_id}-{dependencies.active_llm_stage()}-stream",
                "name": f"{dependencies.active_llm_stage()}_stream",
                "status": "error",
                "summary": f"{dependencies.active_llm_label()} request failed; final answer was not generated",
                "gatewayContextDigest": context_digest,
                "finalAnswerUnavailable": True,
            }
            state.tool_results.append(error_event)
            if attempt < dependencies.empty_answer_retries:
                yield dependencies.sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": f"{dependencies.active_llm_stage()}_retry",
                        "message": f"{dependencies.active_llm_label()} 오류로 원 질문만 사용해 재시도",
                        "gatewayContextDigest": context_digest,
                        "attempt": attempt + 2,
                    }
                )
                continue
            yield dependencies.sse(error_event)
            break

        if state.emitted_answer_text:
            break
        if attempt < dependencies.empty_answer_retries:
            yield dependencies.sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": f"{dependencies.active_llm_stage()}_retry",
                    "message": f"{dependencies.active_llm_label()}가 빈 응답으로 종료되어 같은 증거로 재시도",
                    "gatewayContextDigest": context_digest,
                    "attempt": attempt + 2,
                }
            )
