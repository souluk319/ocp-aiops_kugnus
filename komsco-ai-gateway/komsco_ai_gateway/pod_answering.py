from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .pod_action_candidates import (
    _configure_dependency_provider as _configure_action_dependency_provider,
    pod_inventory_action_candidate_from_row,
    pod_inventory_action_candidates_from_evidence,
    pod_inventory_check_commands,
    pod_row_target,
)
from .pod_evidence_parsing import (
    CRASHLOOPBACKOFF_FIRST_SENTENCE_RULE,
    CRASHLOOPBACKOFF_PLAIN_DEFINITION,
    POD_NAMESPACE_PATTERN_LOOKUP_RE,
    app_label_from_labels,
    choose_gateway_pod_row,
    command_suggests_immediate_exit,
    deployment_from_owner_chain,
    is_pod_namespace_pattern_lookup_request,
    kubernetes_name_terms,
    looks_non_production_context,
    message_mentions_crashloop,
    parse_gateway_current_pod_list_rows,
    parse_gateway_pod_evidence_rows,
    parse_markdown_table_cells,
    parse_restart_count,
    pod_inventory_message_requests_problem_scope,
    pod_inventory_message_requests_restart_history,
    pod_inventory_restart_observation_rows,
    pod_inventory_selected_rows,
    pod_namespace_lookup_pattern,
    pod_row_has_completed_restart_loop,
    pod_row_has_current_failure,
    pod_row_has_error_exit,
    pod_row_priority,
    ready_summary_is_full,
    score_gateway_pod_row,
)
from .pod_fallback_answers import (
    INTERNAL_FALLBACK_DIAGNOSTIC_PATTERNS,
    _configure_dependency_provider as _configure_fallback_dependency_provider,
    build_empty_answer_fallback,
    build_grounded_aiops_answer,
    build_image_answer_fallback,
    build_ols_required_failure_answer,
    build_pod_evidence_fallback,
    build_pod_list_fallback,
    build_pod_namespace_pattern_lookup_answer,
    is_internal_fallback_diagnostic,
    public_gateway_evidence_excerpt,
)

ChatRequest = Any


@dataclass(frozen=True)
class PodAnsweringDependencies:
    is_ambiguous_cleanup_review_request: Callable[[Any], bool]
    is_pod_list_request: Callable[[str], bool]
    pod_list_namespace: Callable[[Any], str]
    crashloop_demo_target_from_request: Callable[[Any], Mapping[str, str]]
    build_action_proposal_fallback: Callable[[Any, Mapping[str, Any]], str]
    active_llm_label: Callable[[], str]
    build_pod_namespace_pattern_lookup_answer: Callable[..., str | None]
    build_pod_list_fallback: Callable[..., str | None]
    build_pod_evidence_fallback: Callable[..., str | None]
    build_image_answer_fallback: Callable[..., str]


_dependencies: PodAnsweringDependencies | None = None


def _require_dependencies() -> PodAnsweringDependencies:
    if _dependencies is None:
        raise RuntimeError(
            "pod_answering dependencies are not configured; "
            "call configure_pod_answering() before using runtime-dependent helpers"
        )
    return _dependencies


_configure_action_dependency_provider(_require_dependencies)
_configure_fallback_dependency_provider(_require_dependencies)


def configure_pod_answering(
    *,
    is_ambiguous_cleanup_review_request: Callable[[Any], bool],
    is_pod_list_request: Callable[[str], bool],
    pod_list_namespace: Callable[[Any], str],
    crashloop_demo_target_from_request: Callable[[Any], Mapping[str, str]],
    build_action_proposal_fallback: Callable[[Any, Mapping[str, Any]], str],
    active_llm_label: Callable[[], str],
    build_pod_namespace_pattern_lookup_answer: Callable[..., str | None],
    build_pod_list_fallback: Callable[..., str | None],
    build_pod_evidence_fallback: Callable[..., str | None],
    build_image_answer_fallback: Callable[..., str],
) -> None:
    global _dependencies

    _dependencies = PodAnsweringDependencies(
        is_ambiguous_cleanup_review_request=is_ambiguous_cleanup_review_request,
        is_pod_list_request=is_pod_list_request,
        pod_list_namespace=pod_list_namespace,
        crashloop_demo_target_from_request=crashloop_demo_target_from_request,
        build_action_proposal_fallback=build_action_proposal_fallback,
        active_llm_label=active_llm_label,
        build_pod_namespace_pattern_lookup_answer=build_pod_namespace_pattern_lookup_answer,
        build_pod_list_fallback=build_pod_list_fallback,
        build_pod_evidence_fallback=build_pod_evidence_fallback,
        build_image_answer_fallback=build_image_answer_fallback,
    )
