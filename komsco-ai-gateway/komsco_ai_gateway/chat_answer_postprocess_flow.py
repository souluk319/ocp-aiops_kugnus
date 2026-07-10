from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AnswerPostprocessState:
    transcript_chunks: list[str] = field(default_factory=list)
    answer_contracts: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AnswerPostprocessDependencies:
    require_final_answer: bool
    active_llm_label: Callable[[], str]
    update_ols_stream_status: Callable[..., None]
    build_required_failure_answer: Callable[..., str]
    build_empty_answer_fallback: Callable[..., str]
    should_forward_image_attachments_to_ols: Callable[[], bool]
    build_crashloop_answer_contract_text: Callable[[Any, str], str]
    build_aiops_answer_contract_text: Callable[..., str]
    sse: Callable[[Any], str]


async def stream_answer_postprocess(
    *,
    attempt_count: int,
    dependencies: AnswerPostprocessDependencies,
    emitted_answer_text: bool,
    gateway_context: Mapping[str, Any],
    gateway_evidence: str | None,
    image_analysis: str | None,
    ols_tool_results: Sequence[Mapping[str, Any]],
    policy: Mapping[str, Any],
    pre_answer_rca_context: Mapping[str, Any],
    rag_citation_text: str,
    request: Any,
    run_id: str,
    runtime_tool_plan: Mapping[str, Any],
    state: AnswerPostprocessState,
) -> AsyncIterator[str]:
    context_digest = gateway_context["metadata"]["digest"]
    if not emitted_answer_text:
        fallback_reason = (
            f"{dependencies.active_llm_label()} ended without answer text; final answer was not generated"
            if attempt_count <= 1
            else f"{dependencies.active_llm_label()} ended without answer text after {attempt_count} attempts; final answer was not generated"
        )
        dependencies.update_ols_stream_status(
            "failed",
            context_digest=context_digest,
            fallback_active=not dependencies.require_final_answer,
            reason=fallback_reason,
        )
        if dependencies.require_final_answer:
            fallback_answer = dependencies.build_required_failure_answer(
                request,
                ols_tool_results,
                image_analysis=image_analysis,
                image_forwarded_to_ols=dependencies.should_forward_image_attachments_to_ols(),
            )
            fallback_source = "ols_required_notice"
            fallback_extra = {"finalAnswerUnavailable": True}
        else:
            fallback_answer = dependencies.build_empty_answer_fallback(
                request,
                policy,
                ols_tool_results,
                gateway_evidence,
                image_analysis=image_analysis,
                image_forwarded_to_ols=dependencies.should_forward_image_attachments_to_ols(),
            )
            fallback_source = "gateway_fallback"
            fallback_extra = {"fallbackAnswer": True}
        state.transcript_chunks.append(fallback_answer)
        yield dependencies.sse(
            {
                "type": "text",
                "content": fallback_answer,
                "source": fallback_source,
                "gatewayContextDigest": context_digest,
                "streamProbe": "failed",
                **fallback_extra,
            }
        )

    can_append_contract = emitted_answer_text or not dependencies.require_final_answer
    if can_append_contract and rag_citation_text:
        state.transcript_chunks.append(rag_citation_text)
        yield dependencies.sse(
            {
                "type": "text",
                "content": rag_citation_text,
                "source": "gateway_rag_citation",
                "gatewayContextDigest": context_digest,
            }
        )

    if not can_append_contract:
        return

    crashloop_contract = dependencies.build_crashloop_answer_contract_text(request, run_id)
    if crashloop_contract:
        state.transcript_chunks.append(crashloop_contract)
        state.answer_contracts.append("crashloop-v0.1.3")
        yield dependencies.sse(
            {
                "type": "text",
                "content": crashloop_contract,
                "source": "gateway_answer_contract",
                "answerContract": "crashloop-v0.1.3",
                "gatewayContextDigest": context_digest,
            }
        )
        return

    aiops_contract = dependencies.build_aiops_answer_contract_text(
        policy=policy,
        rca_context=pre_answer_rca_context,
        runtime_tool_plan=runtime_tool_plan,
    )
    if aiops_contract:
        state.transcript_chunks.append(aiops_contract)
        state.answer_contracts.append("aiops-action-v0.1.9")
        yield dependencies.sse(
            {
                "type": "text",
                "content": aiops_contract,
                "source": "gateway_answer_contract",
                "answerContract": "aiops-action-v0.1.9",
                "gatewayContextDigest": context_digest,
            }
        )
