from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from .answer_contracts import (
    ChatAnswerRequest,
    answer_language,
    answer_language_contract,
    answer_section_contract,
    build_aiops_answer_contract_text,
    casual_identity_answer,
    general_concept_answer,
    message_looks_english,
    page_context_aiops_ui_language,
)
from .answer_fallbacks import (
    AnswerPlan,
    ComponentDefinition,
    ComponentStatus,
    EvidenceComponent,
    EvidenceSignal,
    FAILED_TOOL_STATUSES,
    GatewayEvidenceSnapshot,
    GatewayFallbackPlanInput,
    OK_TOOL_STATUSES,
    build_casual_plan,
    build_component,
    build_gateway_evidence_snapshot,
    build_gateway_fallback_answer_plan as _build_gateway_fallback_answer_plan,
    build_platform_concept_plan,
    build_runtime_health_plan,
    build_tool_component,
    render_answer_plan,
    render_runtime_health_plan,
    signal_status,
    truncate_text,
)
from .answer_intents import (
    ANSWER_KIND_ACTION_PROPOSAL,
    ANSWER_KIND_CASUAL,
    ANSWER_KIND_PLATFORM_CONCEPT,
    ANSWER_KIND_RCA,
    ANSWER_KIND_RUNTIME_HEALTH,
    INTENT_RULES,
    IntentRule,
    RUNTIME_HEALTH_EXCLUDE_RE,
    classify_fallback_answer_kind,
    is_platform_concept_question,
    normalize_message,
)


def build_gateway_fallback_answer_plan(
    request: GatewayFallbackPlanInput | str,
    *legacy_args: Mapping[str, Any] | Sequence[Mapping[str, Any]] | str | None,
) -> AnswerPlan | None:
    if isinstance(request, GatewayFallbackPlanInput):
        return _build_gateway_fallback_answer_plan(request)

    policy = legacy_args[0] if len(legacy_args) > 0 and isinstance(legacy_args[0], Mapping) else {}
    tool_results = legacy_args[1] if len(legacy_args) > 1 and isinstance(legacy_args[1], Sequence) else ()
    gateway_evidence = legacy_args[2] if len(legacy_args) > 2 and isinstance(legacy_args[2], str) else None
    return _build_gateway_fallback_answer_plan(
        GatewayFallbackPlanInput(
            message=request,
            policy=policy,
            tool_results=tool_results,
            gateway_evidence=gateway_evidence,
        )
    )


__all__ = [
    "ANSWER_KIND_ACTION_PROPOSAL",
    "ANSWER_KIND_CASUAL",
    "ANSWER_KIND_PLATFORM_CONCEPT",
    "ANSWER_KIND_RCA",
    "ANSWER_KIND_RUNTIME_HEALTH",
    "FAILED_TOOL_STATUSES",
    "INTENT_RULES",
    "OK_TOOL_STATUSES",
    "RUNTIME_HEALTH_EXCLUDE_RE",
    "AnswerPlan",
    "ChatAnswerRequest",
    "ComponentDefinition",
    "ComponentStatus",
    "EvidenceComponent",
    "EvidenceSignal",
    "GatewayEvidenceSnapshot",
    "GatewayFallbackPlanInput",
    "IntentRule",
    "answer_language",
    "answer_language_contract",
    "answer_section_contract",
    "build_aiops_answer_contract_text",
    "build_casual_plan",
    "build_component",
    "build_gateway_evidence_snapshot",
    "build_gateway_fallback_answer_plan",
    "build_platform_concept_plan",
    "build_runtime_health_plan",
    "build_tool_component",
    "casual_identity_answer",
    "classify_fallback_answer_kind",
    "general_concept_answer",
    "is_platform_concept_question",
    "message_looks_english",
    "normalize_message",
    "page_context_aiops_ui_language",
    "render_answer_plan",
    "render_runtime_health_plan",
    "signal_status",
    "truncate_text",
]
