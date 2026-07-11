import asyncio
import base64
import binascii
import hashlib
import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel, Field

from .aiops_core import (
    HOST_DIAGNOSTIC_COLLECTORS,
    AiopsCoreError,
    action_from_plan,
    build_mutation_request,
    deployment_scale_path,
    get_host_diagnostic_collector,
    parameters_from_plan,
    path_segment,
    target_path,
    target_from_plan,
)
from .aiops_contracts import build_rca_context, build_runtime_safety_contract, build_runtime_tool_plan
from .aiops_event_projection import (
    build_kubernetes_event_items,
    build_problem_pod_event_items,
    compact_event_detail,
)
from .answer_planning import (
    GatewayFallbackPlanInput,
    answer_language,
    answer_language_contract,
    answer_section_contract,
    assistant_operating_answer_style_contract,
    build_aiops_answer_contract_text,
    build_gateway_fallback_answer_plan,
    casual_identity_answer,
    general_concept_answer,
    render_answer_plan,
)
from .answer_streaming import (
    normalize_ols_event,
    parse_tool_text_line,
    split_plain_text_events,
    sse,
)
from .app_factory import create_app
from .aiops_read_router import create_aiops_read_router
from .action_router import create_action_router
from .diagnostics_router import create_diagnostics_router
from .evidence_router import create_evidence_router
from .knowledge_router import create_knowledge_router
from . import action_api_service
from . import auth_runtime
from . import diagnostics_service
from . import evidence_service
from . import knowledge_service
from .action_api_service import ActionApiConfig, ActionApiDependencies, ActionApiStores
from .diagnostics_service import DiagnosticsConfig, DiagnosticsDependencies
from .evidence_service import EvidenceDependencies, EvidenceStores
from .knowledge_service import KnowledgeConfig, KnowledgeDependencies, KnowledgeStores
from .aiops_read_service import (
    AiopsReadConfig,
    AiopsReadDependencies,
    AiopsRecordStores,
)
from . import aiops_read_service
from .cluster_anomalies import (
    ClusterSafety,
    build_aiops_anomaly_summary as build_aiops_anomaly_summary_read_model,
)
from .cluster_evidence import (
    CRONJOB_POLICY_ENV_RE,
    SECRET_ENV_RE,
    _prometheus_probe_reason,
    build_active_alerts_rca_evidence,
    build_cluster_operator_status_evidence,
    build_cronjob_activity_evidence,
    build_deployment_rollout_evidence,
    build_node_status_rca_evidence,
    build_pod_status_evidence,
    build_restart_metric_rca_evidence,
    cluster_operator_condition,
    container_spec_index,
    cron_minute_interval,
    cronjob_container_summary,
    cronjob_matches_context,
    format_seconds_duration,
    json_list_summary,
    markdown_table_cell,
    pod_label_summary,
    pod_owner_chain_summary,
    pod_owner_summary,
    rca_probe_event_status,
    replicaset_owner_index,
    requested_minute_interval,
    safe_env_value,
    schedule_interval_summary,
    state_summary,
    last_termination_summary,
    pod_ready_summary,
)
from . import cluster_evidence_runtime, cluster_observability_runtime
from . import action_candidate_plans
from . import namespace_cleanup as namespace_cleanup_runtime
from . import namespace_cleanup_runtime_support
from . import natural_action_orchestration
from . import natural_action_parsing
from . import natural_action_rendering
from . import persistence_runtime
from .cluster_evidence_runtime import (
    ClusterEvidenceRuntimeCallbacks,
    ClusterEvidenceRuntimeConfig,
)
from .cluster_observability_runtime import (
    ClusterObservabilityConfig,
    ClusterObservabilityDependencies,
)
from .cluster_summary import build_cluster_summary as build_cluster_summary_read_model
from .chat_feedback import ChatFeedbackInputError, build_chat_feedback_record
from .chat_models import (
    MAX_IMAGE_ATTACHMENTS,
    MAX_IMAGE_ATTACHMENT_BYTES,
    MAX_IMAGE_ATTACHMENT_TOTAL_BYTES,
    ChatContextMessage,
    ChatRequest,
    ImageAttachment,
)
from .chat_orchestrator import (
    ChatLatestStatePort,
    ChatOrchestrator,
    ChatOrchestratorDependencies,
)
from .chat_pod_count_flow import (
    DirectPodCountFlowDependencies,
    TopPodNamespaceFlowDependencies,
    stream_direct_pod_count,
    stream_top_pod_namespace_count,
)
from .chat_cleanup_flow import CleanupChatFlowDependencies, start_cleanup_chat_flow
from .chat_natural_action_followup_flow import (
    NaturalActionFollowupFlowDependencies,
    stream_chat_natural_action_followup,
)
from .chat_natural_action_proposal_flow import (
    NaturalActionProposalFlowDependencies,
    stream_chat_natural_action_proposal,
)
from .chat_pod_evidence_flow import (
    PodEvidenceFlowDependencies,
    stream_pod_status_evidence,
)
from .chat_attachment_cronjob_flow import (
    AttachmentCronjobFlowDependencies,
    stream_attachment_and_cronjob_preflight,
)
from .chat_restart_evidence_flow import (
    RestartEvidenceFlowDependencies,
    stream_restart_evidence,
)
from .chat_rca_preflight_flow import (
    RcaPreflightCollector,
    RcaPreflightFlowDependencies,
    stream_rca_preflight_evidence,
)
from .chat_rag_evidence_flow import (
    RagEvidenceFlowDependencies,
    stream_rag_evidence,
)
from .chat_ols_answer_flow import (
    OlsAnswerFlowDependencies,
    OlsAnswerState,
    stream_ols_answer_attempts,
)
from .chat_answer_postprocess_flow import (
    AnswerPostprocessDependencies,
    AnswerPostprocessState,
    stream_answer_postprocess,
)
from .chat_test_pod_flow import (
    TestPodFlowDependencies,
    stream_test_pod_create,
)
from .chat_namespace_cleanup_inventory_flow import (
    NamespaceCleanupInventoryDependencies,
    stream_namespace_cleanup_inventory,
)
from .followup_selection import resolve_numeric_followup_message
from .ols_payloads import (
    OlsContextHandoffInput,
    OlsGatewayContextInput,
    OlsPayloadInput,
    build_attachment_context,
    build_ols_gateway_context as build_ols_gateway_context_for_input,
    build_ols_payload as build_ols_payload_for_context,
    build_ols_context_handoff as build_ols_context_handoff_for_limits,
)
from .ols_query_rendering import OlsQueryRenderInput, render_ols_query
from .llm_stream_client import (
    LlmStreamConfig,
    LlmStreamDependencies,
    active_label as active_llm_label_for_config,
    active_stage as active_llm_stage_for_config,
    build_ollama_chat_url as build_ollama_chat_url_for_client,
    call_ollama_chat as call_ollama_chat_with_client,
    call_ols_stream as call_ols_stream_with_client,
    extract_ollama_chat_content as extract_ollama_chat_content_from_response,
    should_use_ollama as should_use_ollama_for_config,
    stream_with_heartbeats as stream_with_client_heartbeats,
)
from .page_context import (
    page_context_aiops_execution_mode,
    page_context_is_pod_workload,
    page_context_namespace,
    page_context_resource_name,
    normalize_console_page_context,
)
from .pod_counting import (
    build_pod_count_investigation,
    build_top_pod_namespace_count_result,
    deployment_matches_identity,
    pod_is_fully_ready,
    pod_is_terminating,
    pod_count_investigation_response,
    pod_display_state,
    pod_matches_deployment_selector,
    pod_matches_target_fallback,
    pod_ready_numbers,
    pod_restart_total,
    selector_matches_labels,
    summarize_counted_pods,
    top_pod_namespace_count_response,
)
from .image_analysis import (
    analyze_image_attachments as analyze_image_attachments_with_model,
    build_grounded_image_question,
    get_vision_config as get_image_analysis_config,
)
from .rca_result_parser import parse_rca_result
from . import rag_pgvector as rag_pgvector
from .rag_pgvector import RAG_SYNC_DIR, RagDocumentUploadCreate, build_rag_answer_citation_text, build_rag_context_detail, build_rag_upload_document, parse_rag_upload_form_labels, row_matches_rag_filters
from .security import (
    build_evidence_reference,
    build_gateway_guardrail,
    build_trace_record,
    canonical_digest,
    classify_request_policy,
    now_rfc3339,
    redact_sensitive,
    safe_subject,
)
from .gateway_state import (
    ACTION_PROPOSALS,
    APPROVAL_DECISIONS,
    AUDIT_RECORDS,
    BREAK_GLASS_REQUESTS,
    CHAT_FEEDBACK,
    CHAT_TRANSCRIPTS,
    DIAGNOSTIC_REQUESTS,
    EVIDENCE_RECORDS,
    EXECUTION_RECORDS,
    METRICS,
    NAMESPACE_CLEANUP_CHAT_CANDIDATES,
    OLS_STREAM_STATUS,
    PREAPPROVED_PATCH_REQUESTS,
    RATE_LIMIT_BUCKETS,
    RUNBOOK_PLANS,
    SEALED_ACTION_PLANS,
    WORKFLOW_RECORDS,
    _AUTO_EXECUTE_TARGET_LOCKS,
    bounded_put,
    increment_metric,
)
from .action_parameters import (
    ActionRecordContext,
    normalize_action_parameters as normalize_action_parameters_for_context,
)
from .action_approvals import (
    ApprovalDecisionRecordInput,
    ExecutionGrantInput,
    approval_already_executed,
    build_action_rejection_record as build_action_rejection_record_for_context,
    build_approval_decision_record as build_approval_decision_record_for_context,
    build_execution_grant_reference as build_execution_grant_reference_for_context,
    find_approval_by_plan_status,
    plan_has_approval_status,
    record_created_at,
    validate_approval_is_active,
    validate_execution_evidence_freshness,
)
from .action_candidates import (
    ACTION_CANDIDATE_FORBIDDEN_VERBS,
    build_aiops_action_candidates as build_aiops_action_candidates_for_runtime,
)
from .action_execution import (
    ActionExecutionConfig,
    append_query as action_execution_append_query,
    create_crashloop_test_pods_execution_result as action_execution_create_crashloop_test_pods_execution_result,
    execute_action_with_executor as action_execution_execute_action_with_executor,
    execute_typed_action_plan as action_execution_execute_typed_action_plan,
    executor_auth_header as action_execution_executor_auth_header,
    fetch_executor_live_state as action_execution_fetch_executor_live_state,
    namespace_cleanup_review_execution_result as action_execution_namespace_cleanup_review_execution_result,
    pod_diagnostic_review_execution_result as action_execution_pod_diagnostic_review_execution_result,
    pod_fix_or_rollback_review_execution_result as action_execution_pod_fix_or_rollback_review_execution_result,
    submit_ocp_request as action_execution_submit_ocp_request,
    test_pod_create_review_execution_result as action_execution_test_pod_create_review_execution_result,
    verify_typed_action_postcondition as action_execution_verify_typed_action_postcondition,
)
from .action_records import (
    SpecialActionRecordConfig,
    build_action_proposal_record as build_action_proposal_record_for_context,
    build_break_glass_request_record as build_break_glass_request_record_for_context,
    build_candidate_action_request as build_candidate_action_request_for_context,
    build_preapproved_patch_record as build_preapproved_patch_record_for_context,
    build_runbook_plan_record as build_runbook_plan_record_for_context,
    build_sealed_action_plan_record as build_sealed_action_plan_record_for_context,
    candidate_action_request_digest,
    default_policy_binding,
    evaluate_runbook_policy as evaluate_runbook_policy_for_context,
    get_break_glass_profile as get_break_glass_profile_for_context,
    get_preapproved_patch_schema as get_preapproved_patch_schema_for_context,
    get_runbook_entry as get_runbook_entry_for_context,
    platform_namespace_requires_explicit_policy,
    sealed_action_plan_digest,
    validate_preapproved_patch_value,
)
from .action_registry import (
    ACTION_REGISTRY_DIGEST,
    ACTION_REGISTRY_ENTRIES,
    ACTION_REGISTRY_VERSION,
    get_action_registry_entry,
    validate_action_target,
)
from .schemas import (
    ActionCandidatePlanCreate,
    ActionCandidateTargetCreate,
    ActionExecutionCreate,
    ActionProposalCreate,
    ActionRejectionCreate,
    ActionTarget,
    ApprovalDecisionCreate,
    BreakGlassRequestCreate,
    BreakGlassTargetNode,
    DiagnosticEvidencePolicy,
    DiagnosticLimits,
    DiagnosticRequestCreate,
    DiagnosticTargetNode,
    DiagnosticTimeRange,
    PatchPreapprovedFieldCreate,
    RagSearchCreate,
    RagSearchFilters,
    RunbookPlanCreate,
    SealedActionPlanCreate,
    UnrestrictedCommandExecuteCreate,
)
from .settings import (
    first_env_value,
    infer_llm_api_style,
    parse_bool,
    parse_float_env,
    parse_int,
    parse_ols_verify,
)
from .test_pod_create import (
    TestPodCreateSettings,
    answer as render_test_pod_create_answer,
    candidate_from_preflight as build_test_pod_create_candidate_from_preflight,
    collect_preflight as collect_test_pod_create_preflight_for_settings,
    count_from_message as parse_test_pod_create_count_from_message,
    disabled_answer as render_test_pod_create_disabled_answer,
    is_ready as test_pod_create_request_is_ready,
    pod_manifest as build_crashloop_test_pod_manifest,
    pod_name as build_crashloop_test_pod_name,
    request_from_message as parse_test_pod_create_request_from_message,
    review_execution_result as build_test_pod_create_review_execution_result,
    tool_plan as build_test_pod_create_tool_plan,
)
from .text_reference_filter import (
    TextReferenceFilter,
    normalize_pod_restart_language,
    should_filter_gateway_api_references,
    should_filter_low_signal_references,
    strip_private_reasoning_sections,
)
PUBLIC_MAIN_REEXPORTS = (ActionCandidateTargetCreate, BreakGlassTargetNode, DiagnosticEvidencePolicy, DiagnosticLimits, DiagnosticTargetNode, DiagnosticTimeRange, get_action_registry_entry, sealed_action_plan_digest, validate_action_target)

RAG_BACKEND_URL, RAG_EMBEDDING_SERVICE_URL, RAG_EMBEDDING_MODEL, RAG_EMBEDDING_API_STYLE, RAG_EMBEDDING_TIMEOUT_SECONDS, PdfReader = (rag_pgvector.RAG_BACKEND_URL, rag_pgvector.RAG_EMBEDDING_SERVICE_URL, rag_pgvector.RAG_EMBEDDING_MODEL, rag_pgvector.RAG_EMBEDDING_API_STYLE, rag_pgvector.RAG_EMBEDDING_TIMEOUT_SECONDS, rag_pgvector.PdfReader)
def sync_rag_pgvector_config() -> None:
    rag_pgvector.RAG_BACKEND_URL, rag_pgvector.RAG_EMBEDDING_SERVICE_URL, rag_pgvector.RAG_EMBEDDING_MODEL, rag_pgvector.RAG_EMBEDDING_API_STYLE, rag_pgvector.RAG_EMBEDDING_TIMEOUT_SECONDS, rag_pgvector.PdfReader = RAG_BACKEND_URL, RAG_EMBEDDING_SERVICE_URL, RAG_EMBEDDING_MODEL, RAG_EMBEDDING_API_STYLE, RAG_EMBEDDING_TIMEOUT_SECONDS, PdfReader
def build_rag_backend_status() -> dict[str, Any]:
    sync_rag_pgvector_config(); return rag_pgvector.build_rag_backend_status()
async def call_embedding_service_async(value: str) -> list[float] | None:
    sync_rag_pgvector_config(); return await rag_pgvector.call_embedding_service_async(value)
def extract_rag_upload_file_content(name: str, mime_type: str, raw: bytes) -> tuple[str, dict[str, Any]]:
    sync_rag_pgvector_config(); return rag_pgvector.extract_rag_upload_file_content(name, mime_type, raw)
def list_pgvector_upload_documents(subject: Mapping[str, Any]) -> tuple[str, str, list[dict[str, Any]]]:
    sync_rag_pgvector_config(); return rag_pgvector.list_pgvector_upload_documents(subject)
async def persist_rag_upload_document(record: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    sync_rag_pgvector_config(); return await rag_pgvector.persist_rag_upload_document(record)
async def search_pgvector_runbooks(req: RagSearchCreate, subject: Mapping[str, Any] | None = None) -> tuple[str, str, list[dict[str, Any]]]:
    sync_rag_pgvector_config(); return await rag_pgvector.search_pgvector_runbooks(req, subject=subject)
async def sync_rag_directory_on_startup() -> None:
    sync_rag_pgvector_config(); await rag_pgvector.sync_rag_directory_on_startup()

@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await load_record_store()
    if RAG_SYNC_DIR:
        def _on_sync_done(t: asyncio.Task) -> None:
            if not t.cancelled() and (exc := t.exception()):
                import warnings
                warnings.warn(f"RAG directory sync failed at startup: {exc}", RuntimeWarning, stacklevel=1)
        task = asyncio.create_task(sync_rag_directory_on_startup())
        task.add_done_callback(_on_sync_done)
    yield

app = create_app(lifespan=lifespan)


LLM_PROVIDER = first_env_value("KOMSCO_AI_LLM_PROVIDER")
LLM_BASE_URL = first_env_value("KOMSCO_AI_LLM_BASE_URL").rstrip("/")
LLM_MODEL = first_env_value("KOMSCO_AI_LLM_MODEL")
LLM_API_STYLE = (
    first_env_value("KOMSCO_AI_LLM_API_STYLE")
    or infer_llm_api_style(LLM_PROVIDER, LLM_BASE_URL)
).strip().lower()
LLM_TIMEOUT_SECONDS = parse_float_env("KOMSCO_AI_LLM_TIMEOUT_SECONDS", default=300.0)

_LEGACY_OLS_BASE_URL = (
    os.getenv("OLS_BASE_URL") or os.getenv("OPENSHIFT_LIGHTSPEED_BASE_URL", "")
).rstrip("/")
OLS_BASE_URL = LLM_BASE_URL if LLM_API_STYLE == "lightspeed" and LLM_BASE_URL else _LEGACY_OLS_BASE_URL
OLS_CA_FILE = parse_ols_verify(
    os.getenv("OLS_CA_FILE")
    if os.getenv("OLS_CA_FILE") is not None
    else os.getenv("OPENSHIFT_LIGHTSPEED_TLS_VERIFY")
)
OLS_CONNECT_TIMEOUT_SECONDS = parse_float_env(
    "KOMSCO_AI_OLS_CONNECT_TIMEOUT_SECONDS",
    "OPENSHIFT_LIGHTSPEED_CONNECT_TIMEOUT_SECONDS",
    "OPENSHIFT_LIGHTSPEED_TIMEOUT_SECONDS",
    default=min(30.0, LLM_TIMEOUT_SECONDS),
)
OLS_EMPTY_ANSWER_RETRIES = parse_int(os.getenv("KOMSCO_AI_OLS_EMPTY_ANSWER_RETRIES"), default=1, minimum=0, maximum=3)
OLS_QUERY_PROFILE = os.getenv("KOMSCO_AI_OLS_QUERY_PROFILE", "minimal").strip().lower()
OLS_FORWARD_CONVERSATION_ID = parse_bool(
    os.getenv("KOMSCO_AI_OLS_FORWARD_CONVERSATION_ID"),
    default=False,
)
OLS_CONTEXT_HANDOFF_MAX_CHARS = parse_int(
    os.getenv("KOMSCO_AI_OLS_CONTEXT_HANDOFF_MAX_CHARS"),
    default=2200,
    minimum=0,
    maximum=8000,
)
OLS_CONTEXT_HANDOFF_MAX_LINES = parse_int(
    os.getenv("KOMSCO_AI_OLS_CONTEXT_HANDOFF_MAX_LINES"),
    default=24,
    minimum=1,
    maximum=80,
)
DEV_ECHO = parse_bool(os.getenv("KOMSCO_AI_DEV_ECHO"))
OPENSHIFT_API_URL = os.getenv("OPENSHIFT_API_URL", "").rstrip("/")
if not OPENSHIFT_API_URL and os.getenv("KUBERNETES_SERVICE_HOST"):
    kubernetes_host = os.getenv("KUBERNETES_SERVICE_HOST")
    kubernetes_port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
    OPENSHIFT_API_URL = f"https://{kubernetes_host}:{kubernetes_port}"
OPENSHIFT_API_CA_FILE = parse_ols_verify(
    os.getenv(
        "OPENSHIFT_API_CA_FILE",
        "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
        else "",
    )
)
PRODUCT_ACCESS_REVIEW_ENABLED = parse_bool(
    os.getenv("KOMSCO_AI_PRODUCT_ACCESS_REVIEW_ENABLED"),
    default=True,
)
PRODUCT_ACCESS_REVIEW_REQUIRED = parse_bool(
    os.getenv("KOMSCO_AI_PRODUCT_ACCESS_REVIEW_REQUIRED"),
    default=False,
)
PRODUCT_ACCESS_REVIEW_GROUP = os.getenv(
    "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_GROUP",
    "console.openshift.io",
)
PRODUCT_ACCESS_REVIEW_RESOURCE = os.getenv(
    "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_RESOURCE",
    "consoleplugins",
)
PRODUCT_ACCESS_REVIEW_VERB = os.getenv("KOMSCO_AI_PRODUCT_ACCESS_REVIEW_VERB", "get")
PRODUCT_ACCESS_REVIEW_NAME = os.getenv(
    "KOMSCO_AI_PRODUCT_ACCESS_REVIEW_NAME",
    "komsco-ai-console-plugin-kugnus",
)
RATE_LIMIT_PER_MINUTE = int(os.getenv("KOMSCO_AI_RATE_LIMIT_PER_MINUTE", "60"))
AUDIT_MAX_RECORDS = int(os.getenv("KOMSCO_AI_AUDIT_MAX_RECORDS", "1000"))
EVIDENCE_MAX_RECORDS = int(os.getenv("KOMSCO_AI_EVIDENCE_MAX_RECORDS", "1000"))
WORKFLOW_MAX_RECORDS = int(os.getenv("KOMSCO_AI_WORKFLOW_MAX_RECORDS", "1000"))
CHAT_TRANSCRIPT_MAX_RECORDS = int(os.getenv("KOMSCO_AI_CHAT_TRANSCRIPT_MAX_RECORDS", "200"))
CHAT_FEEDBACK_MAX_RECORDS = int(os.getenv("KOMSCO_AI_CHAT_FEEDBACK_MAX_RECORDS", "1000"))
CHAT_TRANSCRIPT_MAX_MESSAGE_CHARS = int(os.getenv("KOMSCO_AI_CHAT_TRANSCRIPT_MAX_MESSAGE_CHARS", "8000"))
CHAT_TRANSCRIPT_MAX_ANSWER_CHARS = int(os.getenv("KOMSCO_AI_CHAT_TRANSCRIPT_MAX_ANSWER_CHARS", "24000"))
CHAT_TRANSCRIPT_JSONL_PATH = os.getenv(
    "KOMSCO_AI_CHAT_TRANSCRIPT_JSONL_PATH",
    "var/aiops/chat-transcripts.jsonl",
).strip()
DIAGNOSTICS_ENABLED = parse_bool(os.getenv("KOMSCO_AI_DIAGNOSTICS_ENABLED"), default=False)
DIAGNOSTIC_MAX_RECORDS = int(os.getenv("KOMSCO_AI_DIAGNOSTIC_MAX_RECORDS", "1000"))
DEMO_NAMESPACE_ALLOWLIST = {
    item.strip()
    for item in os.getenv("KOMSCO_AIOPS_DEMO_NAMESPACE_ALLOWLIST", "komsco-ai-dev,default").split(",")
    if item.strip()
}
# Tool names allowed to skip the human approval/execution click entirely and go
# straight from a sealed plan to an executed action. Empty by default (feature
# off) so this ships inert until an operator opts in. Recommended first value:
# "evict_one_unhealthy_controller_owned_pod" (a single already-unhealthy Pod
# eviction that its owning controller immediately recreates).
AUTO_EXECUTE_TOOL_NAMES = {
    item.strip()
    for item in os.getenv("KOMSCO_AI_AUTO_EXECUTE_TOOL_NAMES", "").split(",")
    if item.strip()
}
# evict_one_unhealthy_controller_owned_pod is only genuinely useful (not just
# "safe") for transient/restart-recoverable findings. ImagePullBackOff and
# similar persistent-failure findings reuse the same tool but would just churn
# the pod forever, so auto-execute additionally requires one of these.
AUTO_EXECUTE_EVICT_ELIGIBLE_SOURCE_TYPES = {"pod_crashloop", "pod_restart_spike", "pod_restart_history"}
HOST_DIAGNOSTICS_CONTROLLER_URL = os.getenv("KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_URL", "").rstrip("/")
HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN = os.getenv(
    "KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN",
    "",
)
RECORD_STORE_ENABLED = parse_bool(os.getenv("KOMSCO_AI_RECORD_STORE_ENABLED"), default=False)
RECORD_STORE_CONFIGMAP = os.getenv("KOMSCO_AI_RECORD_STORE_CONFIGMAP", "komsco-ai-gateway-ledger")
RECORD_STORE_TOKEN_FILE = os.getenv(
    "KOMSCO_AI_RECORD_STORE_TOKEN_FILE",
    "/var/run/secrets/kubernetes.io/serviceaccount/token",
)
RECORD_STORE_NAMESPACE = os.getenv("KOMSCO_AI_RECORD_STORE_NAMESPACE", "")

SERVICEACCOUNT_NAMESPACE_FILE = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
CLUSTER_ID = os.getenv("KOMSCO_AI_CLUSTER_ID", "unknown-cluster")
MUTATIONS_ENABLED = parse_bool(os.getenv("KOMSCO_AI_ENABLE_MUTATIONS"), default=False)
ACTION_PLAN_CAPABILITY_ENABLED = parse_bool(
    os.getenv("KOMSCO_AI_ACTION_PLAN_CAPABILITY_ENABLED"),
    default=True,
)
ACTION_MAX_RECORDS = int(os.getenv("KOMSCO_AI_ACTION_MAX_RECORDS", "1000"))
ACTION_EXECUTOR_TOKEN_FILE = os.getenv(
    "KOMSCO_AI_ACTION_EXECUTOR_TOKEN_FILE",
    "/var/run/secrets/kubernetes.io/serviceaccount/token",
)
ACTION_EXECUTOR_FIELD_MANAGER = os.getenv(
    "KOMSCO_AI_ACTION_EXECUTOR_FIELD_MANAGER",
    "komsco-ai-action-executor",
)
ACTION_EXECUTOR_URL = os.getenv("KOMSCO_AI_ACTION_EXECUTOR_URL", "").rstrip("/")
ACTION_EXECUTOR_SHARED_TOKEN = os.getenv("KOMSCO_AI_ACTION_EXECUTOR_SHARED_TOKEN", "")
APPROVAL_ACCESS_REVIEW_REQUIRED = parse_bool(
    os.getenv("KOMSCO_AI_APPROVAL_ACCESS_REVIEW_REQUIRED"),
    default=False,
)
RUNBOOK_MAX_RECORDS = int(os.getenv("KOMSCO_AI_RUNBOOK_MAX_RECORDS", "1000"))
BREAK_GLASS_ENABLED = parse_bool(os.getenv("KOMSCO_AI_BREAK_GLASS_ENABLED"), default=False)
BREAK_GLASS_MAX_RECORDS = int(os.getenv("KOMSCO_AI_BREAK_GLASS_MAX_RECORDS", "1000"))
BREAK_GLASS_IMAGE_DIGEST = os.getenv("KOMSCO_AI_BREAK_GLASS_IMAGE_DIGEST", "")
UNRESTRICTED_COMMANDS_ENABLED = parse_bool(
    os.getenv("KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS"),
    default=True,
)
UNRESTRICTED_COMMAND_CWD = os.getenv("KOMSCO_AI_UNRESTRICTED_COMMAND_CWD", os.getcwd())
UNRESTRICTED_COMMAND_TIMEOUT_SECONDS = int(
    os.getenv("KOMSCO_AI_UNRESTRICTED_COMMAND_TIMEOUT_SECONDS", "60")
)
UNRESTRICTED_COMMAND_MAX_OUTPUT_BYTES = int(
    os.getenv("KOMSCO_AI_UNRESTRICTED_COMMAND_MAX_OUTPUT_BYTES", "20000")
)
GATEWAY_DIRECT_ANSWER_ENABLED = parse_bool(
    os.getenv("KOMSCO_AI_GATEWAY_DIRECT_ANSWER_ENABLED"),
    default=False,
)
REQUIRE_OLS_FINAL_ANSWER = parse_bool(
    os.getenv("KOMSCO_AI_REQUIRE_OLS_FINAL_ANSWER"),
    default=True,
)
RUN_HEARTBEAT_SECONDS = 5.0
ALLOWED_IMAGE_MIME_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}
AIOPS_ANSWER_QUERY_PLAN_LABEL = "조회 계획:"
POD_STATUS_ANALYSIS_RE = re.compile(
    r"(?i)((pod|pods|파드).*(상태|현황|이력|횟수|많은|높은|분석|확인|조회|"
    r"crashloop|imagepull|backoff|failed|error|pending|교체|replacement|rollout|"
    r"restart\s+(count|history|status|analysis|summary)|"
    r"(many|high|top)\s+restarts)|"
    r"(상태|현황|이력|횟수|많은|높은|분석|확인|조회|crashloop|imagepull|backoff|failed|"
    r"error|pending|교체|replacement|rollout|restart\s+count|"
    r"restart\s+(history|status|analysis|summary)|(many|high|top)\s+restarts).*(pod|pods|파드)|"
    r"(deployment|deployments|디플로이먼트).*(상태|현황|확인|조회|rollout|restart|재시작|교체|replacement)|"
    r"(상태|현황|확인|조회|rollout|restart|재시작|교체|replacement).*(deployment|deployments|디플로이먼트))"
)
POD_LIST_REQUEST_RE = re.compile(
    r"(?i)((pod|pods|파드).*(list|리스트|목록|전체|조회)|"
    r"(list|리스트|목록|전체|조회).*(pod|pods|파드)|"
    r"(pod|pods|파드).*(네임스페이스|namespace).*(알려|찾아|있는|있나|있냐|있었|포함)|"
    r"(네임스페이스|namespace).*(pod|pods|파드).*(알려|찾아|있는|있나|있냐|있었|포함))"
)
POD_NAMESPACE_PATTERN_LOOKUP_RE = re.compile(
    r"(?i)((pod|pods|파드).*(네임스페이스|namespace).*(알려|찾아|있는|있나|있냐|있었|포함)|"
    r"(pod|pods|파드).*(네임스페이스|namespace).*(조회|확인)|"
    r"(네임스페이스|namespace).*(pod|pods|파드).*(알려|찾아|있는|있나|있냐|있었|포함|조회|확인))"
)
AMBIGUOUS_CLEANUP_REQUEST_RE = re.compile(
    r"(?i)(정리(?:를|을)?\s*(?:좀|할까|해도|해야|하면|해볼|할지)|"
    r"없애도|지워도|삭제해도|별\s*의미\s*없|테스트용(?:이면|이라면)|"
    r"cleanup\s*(?:maybe|review)?|should\s+.*cleanup)"
)
CLEANUP_SCOPE_CONFIRMATION_RE = re.compile(
    r"(?i)^\s*(응|그래|좋아|ㅇㅋ|오케이|그\s*범위|그걸로|그대로|yes|ok|proceed)\b|"
    r"(그\s*범위로|그걸로).*(정리|검토|진행|확인)|"
    r"정리\s*검토\s*(해|해줘|진행)"
)
CLEANUP_DELETE_REVIEW_RE = re.compile(
    r"(?i)((최근|최신|나중|마지막|만들어진|생성|created|latest|newest).{0,80}"
    r"(삭제|지워|없애|정리|delete|remove|cleanup)|"
    r"(삭제|지워|없애|정리|delete|remove|cleanup).{0,80}"
    r"(최근|최신|나중|마지막|만들어진|생성|created|latest|newest))"
)
POD_PATTERN_CONTEXT_RE = re.compile(
    r"`(?P<quoted>[a-z0-9][a-z0-9.*-]*(?:pod|pods)[a-z0-9.*-]*)`|"
    r"\b(?P<plain>[a-z0-9][a-z0-9.*-]*(?:pod|pods)[a-z0-9.*-]*)\b",
    re.IGNORECASE,
)
POD_COUNT_QUERY_RE = re.compile(
    r"(?i)((pod|pods|파드).*(몇\s*개|몇개|개수|count|떠\s*있|떠있|띄|running|ready)|"
    r"(몇\s*개|몇개|개수|count|떠\s*있|떠있|띄|running|ready).*(pod|pods|파드))"
)
TOP_POD_NAMESPACE_QUERY_RE = re.compile(
    r"(?i)("
    r"(파드|pod|pods).{0,24}(수|개수|count).{0,24}(제일|가장|최다|많은|많아|top|highest|largest).{0,24}(네임스페이스|namespace)"
    r"|"
    r"(네임스페이스|namespace).{0,24}(파드|pod|pods).{0,24}(수|개수|count).{0,24}(제일|가장|최다|많은|많아|top|highest|largest)"
    r"|"
    r"(제일|가장|최다|많은|많아|top|highest|largest).{0,24}(파드|pod|pods).{0,24}(네임스페이스|namespace)"
    r")"
)
CLUSTER_OPERATOR_ANALYSIS_RE = re.compile(
    r"(?i)(clusteroperator|cluster\s*operator|클러스터\s*오퍼레이터|operator\s+status|오퍼레이터\s*상태)"
)
CRONJOB_ACTIVITY_ANALYSIS_RE = re.compile(
    r"(?i)(cron\s*job|cronjob|크론잡|scheduled\s+job|schedule|스케줄|"
    r"\d+\s*(분|minute|min)|\*/\d+|0/\d+|"
    r"반복\s*(실행|활동)|주기|activity|활동|이벤트)"
)
RCA_SIGNAL_ANALYSIS_RE = re.compile(
    r"(?i)(rca|root\s*cause|원인|왜|장애|이상|anomaly|anomalies|"
    r"alert|alerts|알림|경고|node|nodes|노드|pressure|압력|"
    r"metric|metrics|메트릭|prometheus|thanos|cpu|memory|메모리|restart|재시작|"
    r"crashloop|crashloopbackoff|backoff)"
)
K8S_NAME_RE = r"[a-z0-9](?:[-a-z0-9.]{0,251}[a-z0-9])?"
NAMESPACE_MENTION_RE = re.compile(
    rf"(?:\b(?P<namespace>{K8S_NAME_RE})\s*(?:namespace|네임스페이스)|"
    rf"(?:namespace|네임스페이스)\s*(?P<namespace_after>{K8S_NAME_RE})\b)",
    re.IGNORECASE,
)
DEPLOYMENT_RESOURCE_RE = re.compile(rf"\b(?:deployment|deploy|디플로이먼트)/(?P<name>{K8S_NAME_RE})\b", re.IGNORECASE)
POD_RESOURCE_RE = re.compile(rf"\b(?:pod|pods|파드)/(?P<name>{K8S_NAME_RE})\b", re.IGNORECASE)
POD_COUNT_TARGET_BEFORE_POD_RE = re.compile(
    rf"(?i)(?:^|[^A-Za-z0-9._-])(?P<name>{K8S_NAME_RE})`?\s*"
    r"(?:deployment|deploy|디플로이먼트)?\s*(?:의|에|에서|은|는|이|가)?\s*"
    r"(?:파드|pod|pods)"
)
POD_COUNT_TARGET_AFTER_POD_RE = re.compile(
    rf"(?i)(?:파드|pod|pods)\s*(?:of|for|대상|이름)?\s*(?P<name>{K8S_NAME_RE})"
)
POD_COUNT_RESERVED_TARGET_NAMES = {
    "all",
    "count",
    "list",
    "pod",
    "pods",
    "ready",
    "running",
    "status",
}
HPA_RESOURCE_RE = re.compile(
    rf"\b(?:hpa|horizontalpodautoscaler|horizontalpodautoscalers|오토스케일러)/(?P<name>{K8S_NAME_RE})\b",
    re.IGNORECASE,
)
NAMESPACED_RESOURCE_SHORTHAND_RE = re.compile(rf"\b(?P<namespace>{K8S_NAME_RE})[:/](?P<name>{K8S_NAME_RE})\b")
BACKTICK_RESOURCE_RE = re.compile(r"`(?P<name>[A-Za-z0-9._-]+)`")
SCALE_INTENT_RE = re.compile(
    rf"(?P<name>{K8S_NAME_RE})\s*(?:파드|pod|pods|deployment|deploy)?\s*(?:를|을|은|는)?\s*"
    r"(?P<replicas>[0-9]{1,3})\s*(?:개|대|replica|replicas|pods?)?\s*(?:로|으로)?\s*"
    r"(?:올려|늘려|줄여|맞춰|변경|설정|스케일|scale)",
    re.IGNORECASE,
)
SCALE_REPLICAS_RE = re.compile(
    r"(?P<replicas>[0-9]{1,3})\s*(?:개|대|replica|replicas|pods?)?\s*(?:로|으로)?\s*"
    r"(?:올려|늘려|줄여|맞춰|변경|설정|스케일|scale)",
    re.IGNORECASE,
)
RESTART_INTENT_RE = re.compile(
    rf"(?P<name>{K8S_NAME_RE})\s*(?:deployment|deploy|디플로이먼트|파드|pod|pods)?\s*(?:를|을|은|는)?\s*"
    r"(?:재시작|리스타트|restart|rollout\s+restart)",
    re.IGNORECASE,
)
RESTART_REQUEST_RE = re.compile(r"(?:재시작|리스타트|restart|rollout\s+restart)", re.IGNORECASE)
POD_EVICTION_REQUEST_RE = re.compile(
    r"(?:evict|eviction|퇴거|교체|재생성|pod\s+delete|delete\s+pod|파드\s*삭제|삭제)",
    re.IGNORECASE,
)
ROLLBACK_REQUEST_RE = re.compile(r"(?:rollback|roll\s*back|rollout\s+undo|롤백|되돌려|복구)", re.IGNORECASE)
ROLLBACK_REVISION_RE = re.compile(
    r"(?:revision|rev|리비전)\s*(?P<revision>[0-9]{1,4})|(?P<korean_revision>[0-9]{1,4})\s*번\s*(?:revision|리비전)?",
    re.IGNORECASE,
)
HPA_REQUEST_RE = re.compile(r"(?:\bhpa\b|horizontalpodautoscaler|오토스케일|autoscal)", re.IGNORECASE)
HPA_MIN_RE = re.compile(r"(?:min(?:Replicas)?|최소)\s*(?P<value>[0-9]{1,3})", re.IGNORECASE)
HPA_MAX_RE = re.compile(r"(?:max(?:Replicas)?|최대)\s*(?P<value>[0-9]{1,3})", re.IGNORECASE)
FOLLOWUP_EXECUTION_RE = re.compile(
    r"^\s*(?:승인|승인해|실행|실행해|진행|진행해|수행|수행해|적용|적용해|해|해줘|yes|ok|확인)\s*[.!?。]*\s*$",
    re.IGNORECASE,
)
AIOPS_WORKLOAD_RE = re.compile(
    r"(aiops|komsco[-_.]?ai|cywell[-_.]?aiops|openshift[-_.]?lightspeed|"
    r"lightspeed|trustyai|rhoai|open[-_.]?data[-_.]?hub|\bodh\b|model[-_.]?registry|"
    r"nvidia|gpu|dcgm|\bmig\b|device[-_.]?plugin)",
    re.IGNORECASE,
)
TEST_POD_CREATE_ENABLED = os.getenv("KOMSCO_AI_TEST_POD_CREATE_ENABLED", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
TEST_POD_CREATE_DEFAULT_IMAGE = "registry.access.redhat.com/ubi9/ubi-minimal:latest"
TEST_POD_CREATE_NAME_PREFIX = "aiops-test-pod"
TEST_POD_CREATE_APP_LABEL = "aiops-test-pods"
TEST_POD_CREATE_ALLOWED_NAMESPACES = {
    item.strip()
    for item in os.getenv("KOMSCO_AI_TEST_POD_CREATE_ALLOWED_NAMESPACES", "").split(",")
    if item.strip()
}
TEST_POD_CREATE_FAILURE_COMMAND = [
    "/bin/sh",
    "-c",
    "echo aiops intentional crashloop test pod; exit 1",
]


def test_pod_create_settings() -> TestPodCreateSettings:
    return TestPodCreateSettings(
        enabled=TEST_POD_CREATE_ENABLED,
        default_image=TEST_POD_CREATE_DEFAULT_IMAGE,
        name_prefix=TEST_POD_CREATE_NAME_PREFIX,
        app_label=TEST_POD_CREATE_APP_LABEL,
        allowed_namespaces=frozenset(TEST_POD_CREATE_ALLOWED_NAMESPACES),
        failure_command=tuple(TEST_POD_CREATE_FAILURE_COMMAND),
    )


LAST_RUNTIME_TOOL_PLAN: dict[str, Any] | None = None
LAST_RCA_CONTEXT: dict[str, Any] | None = None
RUNBOOK_REGISTRY_VERSION = "v1"
RUNBOOK_REGISTRY_ENTRIES: dict[str, dict[str, Any]] = {
    "deployment_rollout_restart_v1": {
        "runbookId": "deployment_rollout_restart_v1",
        "runbookVersion": "v1",
        "incidentClass": "deployment_rollout_recovery",
        "targetKind": "Deployment",
        "allowedSteps": [
            {
                "stepId": "restart_deployment",
                "toolName": "rollout_restart_deployment",
                "toolVersion": "v1",
                "requiredParameters": ["restartedAt"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "platformNamespaceRequiresExplicitPolicy": True,
            "ownerReviewRequired": True,
        },
    },
    "deployment_bounded_scale_v1": {
        "runbookId": "deployment_bounded_scale_v1",
        "runbookVersion": "v1",
        "incidentClass": "deployment_capacity_adjustment",
        "targetKind": "Deployment",
        "allowedSteps": [
            {
                "stepId": "set_replicas",
                "toolName": "set_replicas_within_bounds",
                "toolVersion": "v1",
                "requiredParameters": ["replicas", "minReplicas", "maxReplicas"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "platformNamespaceRequiresExplicitPolicy": True,
            "hpaReviewRequired": True,
            "ownerReviewRequired": True,
        },
    },
    "controller_owned_unhealthy_pod_eviction_v1": {
        "runbookId": "controller_owned_unhealthy_pod_eviction_v1",
        "runbookVersion": "v1",
        "incidentClass": "single_unhealthy_controller_owned_pod",
        "targetKind": "Pod",
        "allowedSteps": [
            {
                "stepId": "evict_unhealthy_pod",
                "toolName": "evict_one_unhealthy_controller_owned_pod",
                "toolVersion": "v1",
                "requiredParameters": ["reason"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "controllerOwnerRequired": True,
            "pdbReviewRequired": True,
            "replacementCapacityReviewRequired": True,
        },
    },
    "deployment_rollout_rollback_v1": {
        "runbookId": "deployment_rollout_rollback_v1",
        "runbookVersion": "v1",
        "incidentClass": "deployment_bad_rollout_recovery",
        "targetKind": "Deployment",
        "allowedSteps": [
            {
                "stepId": "rollback_deployment",
                "toolName": "rollback_deployment_to_revision",
                "toolVersion": "v1",
                "requiredParameters": ["revision"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "platformNamespaceRequiresExplicitPolicy": True,
            "ownerReviewRequired": True,
            "rollbackRevisionReviewRequired": True,
        },
    },
    "hpa_bounds_adjustment_v1": {
        "runbookId": "hpa_bounds_adjustment_v1",
        "runbookVersion": "v1",
        "incidentClass": "hpa_scaling_policy_adjustment",
        "targetKind": "HorizontalPodAutoscaler",
        "allowedSteps": [
            {
                "stepId": "set_hpa_bounds",
                "toolName": "set_hpa_bounds",
                "toolVersion": "v1",
                "requiredParameters": ["minReplicas", "maxReplicas"],
            }
        ],
        "policyChecks": {
            "namespaceRequired": True,
            "targetUidRequired": True,
            "platformNamespaceRequiresExplicitPolicy": True,
            "hpaPolicyReviewRequired": True,
        },
    },
}
RUNBOOK_REGISTRY_BUNDLE = {
    "schemaVersion": "v1",
    "version": RUNBOOK_REGISTRY_VERSION,
    "entries": RUNBOOK_REGISTRY_ENTRIES,
}
RUNBOOK_REGISTRY_DIGEST = canonical_digest(RUNBOOK_REGISTRY_BUNDLE)
PREAPPROVED_PATCH_FIELD_SCHEMAS: dict[str, dict[str, Any]] = {
    "deployment_progress_deadline_seconds_v1": {
        "fieldSchemaId": "deployment_progress_deadline_seconds_v1",
        "targetKind": "Deployment",
        "apiVersion": "apps/v1",
        "jsonPointer": "/spec/progressDeadlineSeconds",
        "valueType": "integer",
        "minimum": 30,
        "maximum": 3600,
        "risk": "medium",
    },
    "deployment_revision_history_limit_v1": {
        "fieldSchemaId": "deployment_revision_history_limit_v1",
        "targetKind": "Deployment",
        "apiVersion": "apps/v1",
        "jsonPointer": "/spec/revisionHistoryLimit",
        "valueType": "integer",
        "minimum": 1,
        "maximum": 20,
        "risk": "low",
    },
}
PREAPPROVED_PATCH_FIELD_BUNDLE = {
    "schemaVersion": "v1",
    "version": RUNBOOK_REGISTRY_VERSION,
    "schemas": PREAPPROVED_PATCH_FIELD_SCHEMAS,
}
PREAPPROVED_PATCH_FIELD_DIGEST = canonical_digest(PREAPPROVED_PATCH_FIELD_BUNDLE)
BREAK_GLASS_PROFILE_VERSION = "v1"
BREAK_GLASS_PROFILES: dict[str, dict[str, Any]] = {
    "node_readonly_triage_v1": {
        "profileId": "node_readonly_triage_v1",
        "profileVersion": BREAK_GLASS_PROFILE_VERSION,
        "enabled": BREAK_GLASS_ENABLED and bool(BREAK_GLASS_IMAGE_DIGEST),
        "imageDigest": BREAK_GLASS_IMAGE_DIGEST or "not-configured",
        "fixedEntrypoint": ["/aiops/breakglass-runner", "--profile", "node-readonly-triage"],
        "arbitraryCommandInputAllowed": False,
        "privilegedJob": {
            "enabled": BREAK_GLASS_ENABLED and bool(BREAK_GLASS_IMAGE_DIGEST),
            "hostPID": True,
            "privileged": True,
            "readOnlyRootFilesystem": True,
        },
        "scheduling": {
            "nodeBinding": "targetNodeNameAndUid",
            "tolerations": "profile-defined-only",
            "serviceAccount": "aiops-breakglass",
        },
        "network": {
            "egressPolicy": "deny-except-controller",
        },
        "cleanup": {
            "activeDeadlineSeconds": 300,
            "ttlSecondsAfterFinished": 600,
            "reconciliationCleanupRequired": True,
        },
        "audit": {
            "stream": "aiopsBreakGlassAudit",
            "separateAuditRequired": True,
        },
    }
}
BREAK_GLASS_PROFILE_BUNDLE = {
    "schemaVersion": "v1",
    "version": BREAK_GLASS_PROFILE_VERSION,
    "profiles": BREAK_GLASS_PROFILES,
}
BREAK_GLASS_PROFILE_DIGEST = canonical_digest(BREAK_GLASS_PROFILE_BUNDLE)
HOST_DIAGNOSTIC_COLLECTOR_VERSION = "v1"
HOST_DIAGNOSTIC_COLLECTOR_BUNDLE = {
    "schemaVersion": "v1",
    "version": HOST_DIAGNOSTIC_COLLECTOR_VERSION,
    "collectors": HOST_DIAGNOSTIC_COLLECTORS,
}
HOST_DIAGNOSTIC_COLLECTOR_DIGEST = canonical_digest(HOST_DIAGNOSTIC_COLLECTOR_BUNDLE)
DIAGNOSTIC_REQUEST_DIGEST_FIELDS = (
    "schemaVersion",
    "clusterId",
    "requester",
    "targetNode",
    "collector",
    "collectorVersion",
    "collectorProfile",
    "timeRange",
    "limits",
    "evidencePolicy",
    "policy",
)
RECORD_STORES: dict[str, tuple[dict[str, dict[str, Any]], int, str]] = {
    "chatTranscripts": (CHAT_TRANSCRIPTS, CHAT_TRANSCRIPT_MAX_RECORDS, "chatTranscripts.json"),
    "chatFeedback": (CHAT_FEEDBACK, CHAT_FEEDBACK_MAX_RECORDS, "chatFeedback.json"),
    "diagnosticRequests": (DIAGNOSTIC_REQUESTS, DIAGNOSTIC_MAX_RECORDS, "diagnosticRequests.json"),
    "actionProposals": (ACTION_PROPOSALS, ACTION_MAX_RECORDS, "actionProposals.json"),
    "sealedActionPlans": (SEALED_ACTION_PLANS, ACTION_MAX_RECORDS, "sealedActionPlans.json"),
    "approvalDecisions": (APPROVAL_DECISIONS, ACTION_MAX_RECORDS, "approvalDecisions.json"),
    "executionRecords": (EXECUTION_RECORDS, ACTION_MAX_RECORDS, "executionRecords.json"),
    "runbookPlans": (RUNBOOK_PLANS, RUNBOOK_MAX_RECORDS, "runbookPlans.json"),
    "preapprovedPatchRequests": (
        PREAPPROVED_PATCH_REQUESTS,
        RUNBOOK_MAX_RECORDS,
        "preapprovedPatchRequests.json",
    ),
    "breakGlassRequests": (BREAK_GLASS_REQUESTS, BREAK_GLASS_MAX_RECORDS, "breakGlassRequests.json"),
}


def persistence_runtime_config() -> persistence_runtime.PersistenceRuntimeConfig:
    return persistence_runtime.PersistenceRuntimeConfig(
        record_store_enabled=RECORD_STORE_ENABLED,
        record_store_configmap=RECORD_STORE_CONFIGMAP,
        record_store_token_file=RECORD_STORE_TOKEN_FILE,
        record_store_namespace=RECORD_STORE_NAMESPACE,
        serviceaccount_namespace_file=SERVICEACCOUNT_NAMESPACE_FILE,
        openshift_api_url=OPENSHIFT_API_URL,
        openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
        rate_limit_per_minute=RATE_LIMIT_PER_MINUTE,
        workflow_max_records=WORKFLOW_MAX_RECORDS,
        chat_transcript_max_message_chars=CHAT_TRANSCRIPT_MAX_MESSAGE_CHARS,
        chat_transcript_max_answer_chars=CHAT_TRANSCRIPT_MAX_ANSWER_CHARS,
        chat_transcript_jsonl_path=CHAT_TRANSCRIPT_JSONL_PATH,
    )


def persistence_runtime_stores() -> persistence_runtime.PersistenceRuntimeStores:
    return persistence_runtime.PersistenceRuntimeStores(
        record_stores=RECORD_STORES,
        workflow_records=WORKFLOW_RECORDS,
        rate_limit_buckets=RATE_LIMIT_BUCKETS,
        action_proposals=ACTION_PROPOSALS,
        sealed_action_plans=SEALED_ACTION_PLANS,
        approval_decisions=APPROVAL_DECISIONS,
        execution_records=EXECUTION_RECORDS,
    )


def persistence_runtime_callbacks() -> persistence_runtime.PersistenceRuntimeCallbacks:
    return persistence_runtime.PersistenceRuntimeCallbacks(
        bounded_put=bounded_put,
        canonical_digest=canonical_digest,
        increment_metric=increment_metric,
        now_rfc3339=now_rfc3339,
        redact_sensitive=redact_sensitive,
        safe_subject=safe_subject,
    )


def current_namespace() -> str:
    return persistence_runtime.current_namespace(persistence_runtime_config())


def record_store_auth_header() -> str:
    return persistence_runtime.record_store_auth_header(persistence_runtime_config())


def record_store_path(namespace: str) -> str:
    return persistence_runtime.record_store_path(persistence_runtime_config(), namespace)


async def record_store_request(
    method: str,
    path: str,
    *,
    body: Mapping[str, Any] | None = None,
    content_type: str = "application/json",
) -> httpx.Response:
    return await persistence_runtime.record_store_request(
        persistence_runtime_config(),
        method,
        path,
        body=body,
        content_type=content_type,
        auth_header=record_store_auth_header,
    )


async def load_record_store() -> None:
    await persistence_runtime.load_record_store(
        persistence_runtime_config(),
        persistence_runtime_stores(),
        persistence_runtime_callbacks(),
        record_store_request,
        current_namespace,
        record_store_path,
    )


async def persist_record_store(store_name: str) -> None:
    await persistence_runtime.persist_record_store(
        persistence_runtime_config(),
        persistence_runtime_stores(),
        persistence_runtime_callbacks(),
        store_name,
        record_store_request,
        current_namespace,
        record_store_path,
    )


async def bounded_put_record(
    store_name: str,
    key: str,
    value: dict[str, Any],
) -> None:
    await persistence_runtime.bounded_put_record(
        persistence_runtime_stores(),
        persistence_runtime_callbacks(),
        store_name,
        key,
        value,
        persist_record_store,
    )


def enforce_rate_limit(user_auth_header: str) -> None:
    persistence_runtime.enforce_rate_limit(
        persistence_runtime_config(),
        persistence_runtime_stores(),
        persistence_runtime_callbacks(),
        user_auth_header,
    )


def record_workflow(
    *,
    run_id: str,
    incident_id: str,
    policy: Mapping[str, Any],
    request_id: str,
    stage: str,
    status: str,
    subject: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None = None,
) -> None:
    persistence_runtime.record_workflow(
        persistence_runtime_config(),
        persistence_runtime_stores(),
        persistence_runtime_callbacks(),
        run_id=run_id,
        incident_id=incident_id,
        policy=policy,
        request_id=request_id,
        stage=stage,
        status=status,
        subject=subject,
        target=target,
    )


def truncate_chat_text(value: Any, limit: int) -> str:
    return persistence_runtime.truncate_chat_text(persistence_runtime_callbacks(), value, limit)


def chat_action_record_refs(incident_id: str, run_id: str) -> list[dict[str, Any]]:
    return persistence_runtime.chat_action_record_refs(persistence_runtime_stores(), incident_id, run_id)


def build_chat_transcript_record(
    *,
    req: "ChatRequest",
    answer_text: str,
    answer_contracts: list[str],
    incident_id: str,
    policy: Mapping[str, Any],
    request_id: str,
    rca_context: Mapping[str, Any] | None,
    run_id: str,
    runtime_tool_plan: Mapping[str, Any] | None,
    status: str,
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return persistence_runtime.build_chat_transcript_record(
        persistence_runtime_config(),
        persistence_runtime_stores(),
        persistence_runtime_callbacks(),
        req=req,
        answer_text=answer_text,
        answer_contracts=answer_contracts,
        incident_id=incident_id,
        policy=policy,
        request_id=request_id,
        rca_context=rca_context,
        run_id=run_id,
        runtime_tool_plan=runtime_tool_plan,
        status=status,
        subject=subject,
        truncate_text=truncate_chat_text,
        action_record_refs=chat_action_record_refs,
    )


async def persist_chat_transcript_record(record: dict[str, Any]) -> None:
    await persistence_runtime.persist_chat_transcript_record(
        persistence_runtime_callbacks(),
        record,
        bounded_put_record,
        append_chat_transcript_jsonl,
    )


def write_chat_transcript_jsonl(record: Mapping[str, Any]) -> None:
    persistence_runtime.write_chat_transcript_jsonl(
        persistence_runtime_config(),
        persistence_runtime_callbacks(),
        record,
    )


async def append_chat_transcript_jsonl(record: Mapping[str, Any]) -> None:
    await persistence_runtime.append_chat_transcript_jsonl(
        persistence_runtime_callbacks(),
        record,
        write_chat_transcript_jsonl,
    )


def can_subject_read_record(record: Mapping[str, Any], subject: Mapping[str, Any]) -> bool:
    return persistence_runtime.can_subject_read_record(record, subject)


def evidence_dependencies() -> EvidenceDependencies:
    return EvidenceDependencies(
        stores=EvidenceStores(
            evidence=EVIDENCE_RECORDS,
            workflows=WORKFLOW_RECORDS,
        ),
        verify_bearer_header=verify_bearer_header,
        fetch_self_subject_review=fetch_self_subject_review,
        can_subject_read_record=can_subject_read_record,
    )


def diagnostics_dependencies() -> DiagnosticsDependencies:
    return DiagnosticsDependencies(
        config=DiagnosticsConfig(
            cluster_id=CLUSTER_ID,
            diagnostics_enabled=DIAGNOSTICS_ENABLED,
            controller_url=HOST_DIAGNOSTICS_CONTROLLER_URL,
            controller_shared_token=HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN,
            collector_registry_version=HOST_DIAGNOSTIC_COLLECTOR_VERSION,
            collector_registry_digest=HOST_DIAGNOSTIC_COLLECTOR_DIGEST,
            request_digest_fields=DIAGNOSTIC_REQUEST_DIGEST_FIELDS,
        ),
        diagnostic_requests=DIAGNOSTIC_REQUESTS,
        collectors=HOST_DIAGNOSTIC_COLLECTORS,
        verify_bearer_header=verify_bearer_header,
        fetch_self_subject_review=fetch_self_subject_review,
        can_subject_read_record=can_subject_read_record,
        get_host_diagnostic_collector=get_host_diagnostic_collector,
        canonical_digest=canonical_digest,
        redact_sensitive=redact_sensitive,
        now_rfc3339=now_rfc3339,
        bounded_put_record=bounded_put_record,
        increment_metric=increment_metric,
    )


def diagnostic_request_digest(candidate: Mapping[str, Any]) -> str:
    return diagnostics_service.diagnostic_request_digest(candidate, diagnostics_dependencies())


def build_diagnostic_request_candidate(
    request: "DiagnosticRequestCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return diagnostics_service.build_diagnostic_request_candidate(
        request, subject, diagnostics_dependencies(),
    )


def build_diagnostic_request_record(
    request: "DiagnosticRequestCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return diagnostics_service.build_diagnostic_request_record(
        request, subject, diagnostics_dependencies(),
    )


async def submit_diagnostic_request_to_controller(record: dict[str, Any]) -> dict[str, Any]:
    return await diagnostics_service.submit_diagnostic_request_to_controller(
        record, diagnostics_dependencies(),
    )


def compact_controller_submission(controller_result: Mapping[str, Any]) -> dict[str, Any]:
    return diagnostics_service.compact_controller_submission(
        controller_result, diagnostics_dependencies(),
    )


def normalize_controller_phase(phase: str) -> str:
    return diagnostics_service.normalize_controller_phase(phase)


async def refresh_diagnostic_request_from_controller(record: dict[str, Any]) -> dict[str, Any]:
    return await diagnostics_service.refresh_diagnostic_request_from_controller(
        record, diagnostics_dependencies(),
    )



def action_record_context() -> ActionRecordContext:
    return ActionRecordContext(
        cluster_id=CLUSTER_ID,
        mutations_enabled=MUTATIONS_ENABLED,
        test_pod_create_default_image=TEST_POD_CREATE_DEFAULT_IMAGE,
        test_pod_create_name_prefix=TEST_POD_CREATE_NAME_PREFIX,
        test_pod_create_app_label=TEST_POD_CREATE_APP_LABEL,
        test_pod_create_failure_command=tuple(TEST_POD_CREATE_FAILURE_COMMAND),
    )


def normalize_action_parameters(
    action: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    return normalize_action_parameters_for_context(action, parameters, action_record_context())


def build_candidate_action_request(
    request: "ActionProposalCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return build_candidate_action_request_for_context(request, subject, action_record_context())


def build_action_proposal_record(
    request: "ActionProposalCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return build_action_proposal_record_for_context(request, subject, action_record_context())


def build_sealed_action_plan_record(
    proposal: Mapping[str, Any],
) -> dict[str, Any]:
    return build_sealed_action_plan_record_for_context(proposal, action_record_context())


def build_approval_decision_record(
    plan_record: Mapping[str, Any],
    request: "ApprovalDecisionCreate",
    approver: Mapping[str, Any],
    action_access_review: Mapping[str, Any],
    *,
    allow_self_approval: bool = False,
    auto_policy: bool = False,
) -> dict[str, Any]:
    return build_approval_decision_record_for_context(
        ApprovalDecisionRecordInput(
            plan_record=plan_record,
            request=request,
            approver=approver,
            action_access_review=action_access_review,
            context=action_record_context(),
            allow_self_approval=allow_self_approval,
            auto_policy=auto_policy,
        )
    )


def build_action_rejection_record(
    plan_record: Mapping[str, Any],
    request: "ActionRejectionCreate",
    rejecter: Mapping[str, Any],
) -> dict[str, Any]:
    return build_action_rejection_record_for_context(plan_record, request, rejecter)


def build_execution_grant_reference(
    approval: Mapping[str, Any],
    plan: Mapping[str, Any],
    approver: Mapping[str, Any],
) -> dict[str, Any]:
    return build_execution_grant_reference_for_context(
        ExecutionGrantInput(
            approval=approval,
            plan=plan,
            approver=approver,
            context=action_record_context(),
        )
    )

def special_action_record_config() -> SpecialActionRecordConfig:
    return SpecialActionRecordConfig(
        cluster_id=CLUSTER_ID,
        runbook_registry_entries=RUNBOOK_REGISTRY_ENTRIES,
        runbook_registry_digest=RUNBOOK_REGISTRY_DIGEST,
        preapproved_patch_field_schemas=PREAPPROVED_PATCH_FIELD_SCHEMAS,
        preapproved_patch_field_digest=PREAPPROVED_PATCH_FIELD_DIGEST,
        break_glass_profiles=BREAK_GLASS_PROFILES,
        break_glass_profile_digest=BREAK_GLASS_PROFILE_DIGEST,
    )


def get_runbook_entry(runbook_id: str) -> dict[str, Any]:
    return get_runbook_entry_for_context(runbook_id, special_action_record_config())


def evaluate_runbook_policy(
    runbook: Mapping[str, Any],
    target: "ActionTarget",
    policy: Mapping[str, Any],
) -> dict[str, Any]:
    return evaluate_runbook_policy_for_context(
        runbook, target, policy, platform_namespace_requires_explicit_policy
    )


def build_runbook_plan_record(
    request: "RunbookPlanCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return build_runbook_plan_record_for_context(
        request,
        subject,
        special_action_record_config(),
        runbook_lookup=get_runbook_entry,
        policy_evaluator=evaluate_runbook_policy,
        action_proposal_factory=ActionProposalCreate,
        candidate_builder=build_candidate_action_request,
    )


def get_preapproved_patch_schema(field_schema_id: str) -> dict[str, Any]:
    return get_preapproved_patch_schema_for_context(field_schema_id, special_action_record_config())


def build_preapproved_patch_record(
    request: "PatchPreapprovedFieldCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return build_preapproved_patch_record_for_context(
        request,
        subject,
        special_action_record_config(),
        schema_lookup=get_preapproved_patch_schema,
        value_validator=validate_preapproved_patch_value,
    )


def get_break_glass_profile(profile_id: str) -> dict[str, Any]:
    return get_break_glass_profile_for_context(profile_id, special_action_record_config())


def build_break_glass_request_record(
    request: "BreakGlassRequestCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return build_break_glass_request_record_for_context(
        request,
        subject,
        special_action_record_config(),
        profile_lookup=get_break_glass_profile,
    )


class ChatFeedbackCreate(BaseModel):
    answerContract: str | None = Field(default=None, max_length=160)
    assistantAnswer: str | None = Field(default=None, max_length=4000)
    answerSource: str | None = Field(default=None, max_length=80)
    conversationId: str | None = Field(default=None, max_length=160)
    feedbackId: str | None = Field(default=None, max_length=180)
    intent: str | None = Field(default=None, max_length=120)
    messageId: str = Field(min_length=1, max_length=220)
    mode: str = Field(min_length=1, max_length=60)
    optionalComment: str | None = Field(default=None, max_length=1000)
    rating: str = Field(min_length=1, max_length=16)
    route: str | None = Field(default=None, max_length=240)
    source: str | None = Field(default=None, max_length=80)
    timestamp: str | None = Field(default=None, max_length=80)
    userMessage: str | None = Field(default=None, max_length=2400)




CASUAL_IDENTITY_RE = re.compile(
    r"^\s*(hi|hello|hey|yo|ok|okay|thanks|thank you|who are you|what can you do|"
    r"help|안녕|야|ㅇㅋ|고마워|너\s*뭐야|뭐야|누구야)\s*[.!?。！？]*\s*$",
    re.IGNORECASE,
)
CASUAL_EMOTION_RE = re.compile(
    r"(챗봇|copilot|aiops|멍청|명청|바보|짜증|화나|시발|씨발|좆|개같|"
    r"stupid|dumb|annoying|frustrat|bad bot|broken bot)",
    re.IGNORECASE,
)
OPERATIONAL_CONTEXT_RE = re.compile(
    r"(openshift|오픈시프트|ocp|kubernetes|쿠버네티스|cluster|클러스터|namespace|네임스페이스|"
    r"node|노드|operator|pod|파드|deployment|deploy|배포|event|이벤트|alert|경고|"
    r"action\s*plan|조치|승인|실행|터미널|명령|oc\b|restart|재시작|rollback|scale|delete|create|cleanup|"
    r"crash\s*loop|crashloop|CrashLoopBackOff|ImagePullBackOff|OOMKilled|scenario|시나리오)",
    re.IGNORECASE,
)
GENERAL_CONCEPT_SUBJECT_RE = re.compile(
    r"(openshift|오픈시프트|ocp|kubernetes|쿠버네티스)",
    re.IGNORECASE,
)
GENERAL_CONCEPT_QUESTION_RE = re.compile(
    r"(\bwhat\s+is\b|\bwhat'?s\b|\bexplain\b|\btell\s+me\s+about\b|"
    r"뭐야|무엇|설명|정의|개념)",
    re.IGNORECASE,
)
OPERATIONAL_TASK_RE = re.compile(
    r"(최근|현재|상태|경고|장애|오류|에러|확인|점검|분석|정리|삭제|생성|만들|조회|"
    r"진단|원인|복구|검증|롤백|계획|실행|승인|조치|터미널|명령|"
    r"create|delete|cleanup|diagnos|troubleshoot|restart|rollback|get|list|scale|execute|approve|oc\s+)",
    re.IGNORECASE,
)
NAMESPACE_CLEANUP_REQUEST_RE = re.compile(
    r"(namespace|namespaces|네임스페이스).*(사용\s*중|사용\s*여부|안\s*쓰|오래된|정리|삭제|cleanup|unused|stale)"
    r"|((사용\s*중|안\s*쓰|오래된|정리|삭제|cleanup|unused|stale).*(namespace|namespaces|네임스페이스))",
    re.IGNORECASE,
)
TEST_POD_CREATE_REQUEST_RE = re.compile(
    r"((test|테스트).{0,40}(pod|pods|파드).{0,40}(create|생성|만들))"
    r"|((pod|pods|파드).{0,40}(3|three|세|셋|3개).{0,40}(create|생성|만들))"
    r"|((create|생성|만들).{0,40}(test|테스트).{0,40}(pod|pods|파드))",
    re.IGNORECASE,
)
NAMESPACE_TOKEN_RE = re.compile(r"\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\b")
NAMESPACE_TOKEN_HINT_RE = re.compile(r"(aiops|komsco|cywell|gpu|test|demo|dev|lab)", re.IGNORECASE)
SYSTEM_NAMESPACE_RE = re.compile(r"^(default|kube-|openshift-|redhat-|olm|local)$", re.IGNORECASE)


def is_casual_identity_request(req: ChatRequest) -> bool:
    text = re.sub(r"\s+", " ", req.message or "").strip()
    if not text or len(text) > 120:
        return False
    if OPERATIONAL_CONTEXT_RE.search(text):
        return False
    return bool(CASUAL_IDENTITY_RE.search(text) or CASUAL_EMOTION_RE.search(text))


def is_general_concept_request(req: ChatRequest) -> bool:
    text = re.sub(r"\s+", " ", req.message or "").strip()
    if not text or len(text) > 180:
        return False
    if not GENERAL_CONCEPT_SUBJECT_RE.search(text):
        return False
    if not GENERAL_CONCEPT_QUESTION_RE.search(text):
        return False
    if OPERATIONAL_TASK_RE.search(text):
        return False
    return True


def is_resource_summary_rca_request(req: ChatRequest) -> bool:
    text = re.sub(r"\s+", " ", req.message or "").strip().lower()
    if not text:
        return False
    return (
        "resource_summary_rca" in text
        or "리소스 전체 요약" in text
        or "클러스터 리소스 집계 결과" in text
    )


def resource_summary_rca_answer_contract(req: ChatRequest) -> str:
    if not is_resource_summary_rca_request(req):
        return ""
    return """
Resource summary RCA contract:
- This request is an aggregate cluster resource signal, not one concrete mutation target.
- Do not use the heading `승인 대기 조치` unless the Gateway provides a structured action candidate with namespace, kind, name, action, expected impact, verification, and rollback.
- Do not write `[승인 필요]` for broad recommendations such as Job/CronJob conversion, NFS ACL review, operator reinstall, patch, delete, restart, or scale unless a concrete target and approval-ready Action Plan exists.
- Use `조치 판단 조건` or `상세 확인 플랜` for this answer.
- Explain that Action Plan candidates are created only after failing/waiting Pods, restart-count leaders, owners, affected namespaces, and verification commands are narrowed down.
- Do not include external documentation URLs unless the user explicitly asks for references or the reference is directly tied to the verified signal.
"""


def _conversation_cleanup_dependencies() -> namespace_cleanup_runtime.ConversationCleanupDependencies:
    return namespace_cleanup_runtime.ConversationCleanupDependencies(
        page_context_namespace=page_context_namespace,
        is_resource_summary_rca_request=is_resource_summary_rca_request,
        parse_gateway_current_pod_list_rows=parse_gateway_current_pod_list_rows,
        parse_gateway_pod_evidence_rows=parse_gateway_pod_evidence_rows,
        candidate_cache=NAMESPACE_CLEANUP_CHAT_CANDIDATES,
        forbidden_verbs=ACTION_CANDIDATE_FORBIDDEN_VERBS,
    )


def is_namespace_cleanup_request(req: ChatRequest) -> bool:
    return namespace_cleanup_runtime.is_namespace_cleanup_request(req, _conversation_cleanup_dependencies())


def is_test_pod_create_request(req: ChatRequest) -> bool:
    text = re.sub(r"\s+", " ", req.message or "").strip()
    return bool(text and TEST_POD_CREATE_REQUEST_RE.search(text))


namespace_names_from_message = namespace_cleanup_runtime.namespace_names_from_message
pod_patterns_from_text = namespace_cleanup_runtime.pod_patterns_from_text
normalized_pod_pattern_from_texts = namespace_cleanup_runtime.normalized_pod_pattern_from_texts
focus_namespace_from_text = namespace_cleanup_runtime.focus_namespace_from_text
recent_context_texts = namespace_cleanup_runtime.recent_context_texts


def conversation_focus_from_request(req: ChatRequest) -> dict[str, str]:
    return namespace_cleanup_runtime.conversation_focus_from_request(req, _conversation_cleanup_dependencies())


def is_ambiguous_cleanup_review_request(req: ChatRequest) -> bool:
    return namespace_cleanup_runtime.is_ambiguous_cleanup_review_request(req, _conversation_cleanup_dependencies())


def should_clarify_cleanup_scope(req: ChatRequest, focus: Mapping[str, str] | None = None) -> bool:
    return namespace_cleanup_runtime.should_clarify_cleanup_scope(req, _conversation_cleanup_dependencies(), focus)


def should_create_cleanup_review_candidate(req: ChatRequest, focus: Mapping[str, str] | None = None) -> bool:
    return namespace_cleanup_runtime.should_create_cleanup_review_candidate(req, _conversation_cleanup_dependencies(), focus)


cleanup_delete_count_from_message = namespace_cleanup_runtime.cleanup_delete_count_from_message


def should_create_latest_cleanup_delete_review_candidate(
    req: ChatRequest,
    focus: Mapping[str, str] | None = None,
) -> bool:
    return namespace_cleanup_runtime.should_create_latest_cleanup_delete_review_candidate(
        req, _conversation_cleanup_dependencies(), focus,
    )


def cleanup_scope_clarification_response(req: ChatRequest, focus: Mapping[str, str] | None = None) -> str:
    return namespace_cleanup_runtime.cleanup_scope_clarification_response(req, _conversation_cleanup_dependencies(), focus)


pod_name_matches_pattern = namespace_cleanup_runtime.pod_name_matches_pattern


def cleanup_candidate_pod_rows(
    focus: Mapping[str, str],
    gateway_evidence: str | None,
) -> list[dict[str, str]]:
    return namespace_cleanup_runtime.cleanup_candidate_pod_rows(
        focus,
        gateway_evidence,
        _conversation_cleanup_dependencies(),
    )


def select_latest_cleanup_pod_rows(
    focus: Mapping[str, str],
    gateway_evidence: str | None,
    count: int,
) -> list[dict[str, str]]:
    return namespace_cleanup_runtime.select_latest_cleanup_pod_rows(
        focus,
        gateway_evidence,
        count,
        _conversation_cleanup_dependencies(),
    )


def build_conversation_cleanup_review_candidate(
    focus: Mapping[str, str],
    *,
    incident_id: str,
    run_id: str,
    selected_rows: Sequence[Mapping[str, str]] | None = None,
    requested_count: int = 0,
) -> dict[str, Any]:
    return namespace_cleanup_runtime.build_conversation_cleanup_review_candidate(
        focus, _conversation_cleanup_dependencies(), incident_id=incident_id, run_id=run_id,
        selected_rows=selected_rows, requested_count=requested_count,
    )


def remember_conversation_cleanup_review_candidate(
    focus: Mapping[str, str],
    *,
    incident_id: str,
    run_id: str,
    selected_rows: Sequence[Mapping[str, str]] | None = None,
    requested_count: int = 0,
) -> dict[str, Any]:
    return namespace_cleanup_runtime.remember_conversation_cleanup_review_candidate(
        focus, _conversation_cleanup_dependencies(), incident_id=incident_id, run_id=run_id,
        selected_rows=selected_rows, requested_count=requested_count,
    )


cleanup_latest_delete_review_response = namespace_cleanup_runtime.cleanup_latest_delete_review_response
cleanup_review_candidate_response = namespace_cleanup_runtime.cleanup_review_candidate_response


def cleanup_chat_flow_dependencies(
    current_rca_context_event_callback: Callable[[str], dict[str, Any]],
) -> CleanupChatFlowDependencies:
    return CleanupChatFlowDependencies(
        should_create_latest_candidate=should_create_latest_cleanup_delete_review_candidate,
        should_create_candidate=should_create_cleanup_review_candidate,
        should_clarify_scope=should_clarify_cleanup_scope,
        delete_count_from_message=cleanup_delete_count_from_message,
        select_latest_rows=select_latest_cleanup_pod_rows,
        remember_candidate=remember_conversation_cleanup_review_candidate,
        candidate_response=cleanup_review_candidate_response,
        clarification_response=cleanup_scope_clarification_response,
        redact_sensitive=redact_sensitive,
        current_rca_context_event=current_rca_context_event_callback,
        sse=sse,
    )


def natural_action_followup_flow_dependencies(
    current_rca_context_event_callback: Callable[[str], dict[str, Any]],
) -> NaturalActionFollowupFlowDependencies:
    return NaturalActionFollowupFlowDependencies(
        latest_pending_action_plan_result=latest_pending_action_plan_result,
        recent_natural_action_request=recent_natural_action_request,
        create_natural_action_plan=create_natural_action_plan,
        execute_natural_action_plan_result=execute_natural_action_plan_result,
        redact_sensitive=redact_sensitive,
        natural_action_execution_response=natural_action_execution_response,
        natural_action_plan_response=natural_action_plan_response,
        no_pending_action_plan_response=no_pending_action_plan_response,
        current_rca_context_event=current_rca_context_event_callback,
        sse=sse,
    )


def natural_action_proposal_flow_dependencies(
    current_rca_context_event_callback: Callable[[str], dict[str, Any]],
) -> NaturalActionProposalFlowDependencies:
    return NaturalActionProposalFlowDependencies(
        parse_intent=parse_natural_action_intent,
        execution_mode=page_context_aiops_execution_mode,
        allows_actions=execution_mode_allows_actions,
        allows_immediate_actions=execution_mode_allows_immediate_actions,
        create_plan=create_natural_action_plan,
        execute_plan=execute_natural_action_plan_result,
        unresolved_response=unresolved_natural_action_response,
        evidence_check_response=natural_action_evidence_check_response,
        plan_response=natural_action_plan_response,
        execution_response=natural_action_execution_response,
        redact_sensitive=redact_sensitive,
        current_rca_context_event=current_rca_context_event_callback,
        sse=sse,
    )


def pod_evidence_flow_dependencies() -> PodEvidenceFlowDependencies:
    return PodEvidenceFlowDependencies(
        is_pod_list_request=is_pod_list_request,
        page_context_is_pod_workload=page_context_is_pod_workload,
        pod_list_namespace=pod_list_namespace,
        collect_pod_status_evidence=collect_pod_status_evidence,
        append_gateway_evidence=append_gateway_evidence,
        safe_exception_text=safe_exception_text,
        evidence_summary=_evidence_summary,
        build_evidence_reference_events=build_evidence_reference_events,
        sse=sse,
    )


def attachment_cronjob_flow_dependencies() -> AttachmentCronjobFlowDependencies:
    return AttachmentCronjobFlowDependencies(
        analyze_image_attachments=analyze_image_attachments,
        should_collect_cronjob_activity_evidence=should_collect_cronjob_activity_evidence,
        collect_cronjob_activity_evidence=collect_cronjob_activity_evidence,
        append_gateway_evidence=append_gateway_evidence,
        safe_exception_text=safe_exception_text,
        evidence_summary=_evidence_summary,
        build_evidence_reference_events=build_evidence_reference_events,
        sse=sse,
    )


def restart_evidence_flow_dependencies() -> RestartEvidenceFlowDependencies:
    return RestartEvidenceFlowDependencies(
        crashloop_target=crashloop_demo_target_from_request,
        official_namespace=official_namespace_restart_namespace,
        collect_official=collect_official_namespace_restart_evidence_events,
        official_fallback=official_namespace_restart_skipped_evidence_events,
        collect_crashloop=collect_crashloop_demo_evidence_events,
        append_gateway_evidence=append_gateway_evidence,
        safe_exception_text=safe_exception_text,
        build_evidence_reference_events=build_evidence_reference_events,
        sse=sse,
    )


def rca_preflight_flow_dependencies() -> RcaPreflightFlowDependencies:
    return RcaPreflightFlowDependencies(
        collectors=(
            RcaPreflightCollector(
                "node-status-rca-evidence",
                "node_status_evidence",
                "Node 상태 RCA 조회 결과 수집",
                "node",
                collect_node_status_rca_evidence,
            ),
            RcaPreflightCollector(
                "active-alerts-rca-evidence",
                "active_alerts_evidence",
                "Active Alert RCA 조회 결과 수집",
                "alert",
                collect_active_alerts_rca_evidence,
            ),
            RcaPreflightCollector(
                "restart-metric-rca-evidence",
                "restart_metric_evidence",
                "Restart metric RCA 조회 결과 수집",
                "metric",
                collect_restart_metric_rca_evidence,
            ),
        ),
        append_gateway_evidence=append_gateway_evidence,
        safe_exception_text=safe_exception_text,
        build_evidence_reference_events=build_evidence_reference_events,
        sse=sse,
    )


def rag_evidence_flow_dependencies() -> RagEvidenceFlowDependencies:
    return RagEvidenceFlowDependencies(
        make_request=RagSearchCreate,
        search_runbooks=search_pgvector_runbooks,
        build_context_detail=build_rag_context_detail,
        build_citation_text=build_rag_answer_citation_text,
        append_gateway_evidence=append_gateway_evidence,
        safe_exception_text=safe_exception_text,
        build_evidence_reference_events=build_evidence_reference_events,
        sse=sse,
    )


def ols_answer_flow_dependencies() -> OlsAnswerFlowDependencies:
    return OlsAnswerFlowDependencies(
        empty_answer_retries=OLS_EMPTY_ANSWER_RETRIES,
        require_final_answer=REQUIRE_OLS_FINAL_ANSWER,
        call_ols_stream=call_ols_stream,
        stream_with_heartbeats=stream_with_heartbeats,
        normalize_ols_event=normalize_ols_event,
        redact_sensitive=redact_sensitive,
        answer_language_contract=answer_language_contract,
        safe_exception_text=safe_exception_text,
        update_ols_stream_status=update_ols_stream_status,
        active_llm_stage=active_llm_stage,
        active_llm_label=active_llm_label,
        build_evidence_reference_events=build_evidence_reference_events,
        sse=sse,
    )


def answer_postprocess_dependencies() -> AnswerPostprocessDependencies:
    return AnswerPostprocessDependencies(
        require_final_answer=REQUIRE_OLS_FINAL_ANSWER,
        active_llm_label=active_llm_label,
        update_ols_stream_status=update_ols_stream_status,
        build_required_failure_answer=build_ols_required_failure_answer,
        build_empty_answer_fallback=build_empty_answer_fallback,
        should_forward_image_attachments_to_ols=should_forward_image_attachments_to_ols,
        build_crashloop_answer_contract_text=build_crashloop_demo_answer_contract_text,
        build_aiops_answer_contract_text=build_aiops_answer_contract_text,
        sse=sse,
    )


def remember_test_pod_candidate(candidate: dict[str, Any]) -> None:
    NAMESPACE_CLEANUP_CHAT_CANDIDATES[str(candidate["id"])] = candidate


def test_pod_flow_dependencies() -> TestPodFlowDependencies:
    return TestPodFlowDependencies(
        execution_mode=page_context_aiops_execution_mode,
        answer_language=answer_language,
        parse_request=test_pod_create_request_from_message,
        request_is_ready=test_pod_create_is_ready,
        collect_preflight=collect_test_pod_create_preflight,
        disabled_answer=test_pod_create_disabled_answer,
        action_capable_mode=action_capable_execution_mode,
        candidate_from_preflight=test_pod_create_candidate_from_preflight,
        remember_candidate=remember_test_pod_candidate,
        answer=test_pod_create_answer,
        tool_plan=test_pod_create_tool_plan,
        redact_sensitive=redact_sensitive,
        sse=sse,
    )


def namespace_cleanup_inventory_dependencies() -> NamespaceCleanupInventoryDependencies:
    return NamespaceCleanupInventoryDependencies(
        execution_mode=page_context_aiops_execution_mode,
        answer_language=answer_language,
        namespace_names=namespace_names_from_message,
        collect_inventory=collect_namespace_cleanup_inventory,
        cleanup_candidates=namespace_cleanup_candidates_from_inventory,
        action_capable_mode=action_capable_execution_mode,
        remember_candidates=remember_namespace_cleanup_candidates,
        answer=namespace_cleanup_answer,
        redact_sensitive=redact_sensitive,
        sse=sse,
    )



def execution_mode_allows_actions(req: ChatRequest) -> bool:
    return natural_action_parsing.execution_mode_allows_actions(
        req, execution_mode=page_context_aiops_execution_mode
    )


def execution_mode_allows_immediate_actions(req: ChatRequest) -> bool:
    return natural_action_parsing.execution_mode_allows_immediate_actions(
        req,
        execution_mode=page_context_aiops_execution_mode,
        unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
    )


UNRESTRICTED_COMMAND_PREFIX_RE = re.compile(
    r"(?is)^\s*(?:/exec|exec:|run:|command:|명령\s*실행:|실행:)\s+(?P<command>.+?)\s*$"
)


def parse_unrestricted_chat_command(message: str) -> str:
    match = UNRESTRICTED_COMMAND_PREFIX_RE.match(message)
    if not match:
        return ""
    command = match.group("command").strip()
    if command.startswith("```") and command.endswith("```"):
        command = re.sub(r"^```[A-Za-z0-9_-]*\s*", "", command)
        command = re.sub(r"\s*```$", "", command).strip()
    return command


def is_pod_list_request(message: str) -> bool:
    return bool(POD_LIST_REQUEST_RE.search(message))


def pod_list_namespace(req: ChatRequest) -> str:
    match = NAMESPACE_MENTION_RE.search(req.message.lower())
    if match:
        return match.group("namespace") or match.group("namespace_after") or ""
    return page_context_namespace(req)


def namespace_from_natural_action(req: ChatRequest) -> str:
    match = NAMESPACE_MENTION_RE.search(req.message.lower())
    if match:
        return match.group("namespace") or match.group("namespace_after") or ""
    shorthand_match = NAMESPACED_RESOURCE_SHORTHAND_RE.search(req.message.lower())
    if shorthand_match and shorthand_match.group("namespace") not in {"deployment", "deploy", "디플로이먼트"}:
        return shorthand_match.group("namespace")
    return page_context_namespace(req)


def first_backtick_name(message: str) -> str:
    match = BACKTICK_RESOURCE_RE.search(message)
    return match.group("name") if match else ""


def is_pod_count_query(message: str) -> bool:
    return bool(POD_COUNT_QUERY_RE.search(message))


def is_top_pod_namespace_query(message: str) -> bool:
    return bool(TOP_POD_NAMESPACE_QUERY_RE.search(message))


def pod_count_query_namespace(req: ChatRequest) -> str:
    shorthand_match = NAMESPACED_RESOURCE_SHORTHAND_RE.search(req.message.lower())
    if shorthand_match and shorthand_match.group("namespace") not in {
        "deployment",
        "deploy",
        "pod",
        "pods",
        "디플로이먼트",
        "파드",
    }:
        return shorthand_match.group("namespace")
    return pod_list_namespace(req)


def is_reserved_pod_count_target(name: str) -> bool:
    return name.strip().lower() in POD_COUNT_RESERVED_TARGET_NAMES


def pod_count_query_target_name(req: ChatRequest) -> str:
    deployment_match = DEPLOYMENT_RESOURCE_RE.search(req.message)
    if deployment_match:
        return deployment_match.group("name")

    pod_match = POD_RESOURCE_RE.search(req.message)
    if pod_match:
        return pod_match.group("name")

    backtick_name = first_backtick_name(req.message)
    if backtick_name:
        return backtick_name

    shorthand_match = NAMESPACED_RESOURCE_SHORTHAND_RE.search(req.message.lower())
    if shorthand_match:
        return shorthand_match.group("name")

    before_match = POD_COUNT_TARGET_BEFORE_POD_RE.search(req.message)
    if before_match and not is_reserved_pod_count_target(before_match.group("name")):
        return before_match.group("name")

    after_match = POD_COUNT_TARGET_AFTER_POD_RE.search(req.message)
    if after_match and not is_reserved_pod_count_target(after_match.group("name")):
        return after_match.group("name")

    return page_context_resource_name(req, "Deployment") or page_context_resource_name(req, "Pod")


def parse_pod_count_query(req: ChatRequest) -> dict[str, str] | None:
    if not is_pod_count_query(req.message):
        return None

    target_name = pod_count_query_target_name(req)
    if not target_name:
        return {
            "namespace": pod_count_query_namespace(req),
            "targetName": "",
        }

    return {
        "namespace": pod_count_query_namespace(req),
        "targetName": target_name,
    }


def natural_target_name(
    req: ChatRequest,
    match: re.Match[str] | None,
    *,
    expected_kind: str = "Deployment",
) -> str:
    if expected_kind == "Pod":
        resource_match = POD_RESOURCE_RE.search(req.message)
    elif expected_kind == "HorizontalPodAutoscaler":
        resource_match = HPA_RESOURCE_RE.search(req.message)
    else:
        resource_match = DEPLOYMENT_RESOURCE_RE.search(req.message)
    if resource_match:
        return resource_match.group("name")
    backtick_name = first_backtick_name(req.message)
    if backtick_name:
        return backtick_name
    shorthand_match = NAMESPACED_RESOURCE_SHORTHAND_RE.search(req.message.lower())
    if shorthand_match:
        return shorthand_match.group("name")
    if match and "name" in match.groupdict():
        return match.group("name")
    return page_context_resource_name(req, expected_kind)


def rollback_revision_from_message(message: str) -> int | None:
    return natural_action_parsing.rollback_revision_from_message(
        message, pattern=ROLLBACK_REVISION_RE
    )


def hpa_bounds_from_message(message: str) -> tuple[int, int] | None:
    return natural_action_parsing.hpa_bounds_from_message(
        message, min_pattern=HPA_MIN_RE, max_pattern=HPA_MAX_RE
    )


def is_followup_execution_request(message: str) -> bool:
    return natural_action_parsing.is_followup_execution_request(
        message, pattern=FOLLOWUP_EXECUTION_RE
    )


def recent_natural_action_request(req: ChatRequest) -> ChatRequest | None:
    return natural_action_parsing.recent_natural_action_request(
        req,
        request_factory=ChatRequest,
        is_followup=is_followup_execution_request,
        parse_intent=parse_natural_action_intent,
    )


def parse_natural_action_intent(req: ChatRequest) -> dict[str, Any] | None:
    return natural_action_parsing.parse_natural_action_intent(
        req,
        namespace_from_request=namespace_from_natural_action,
        target_name_from_request=lambda request, match: natural_target_name(request, match),
        hpa_target_name_from_request=lambda request, match: natural_target_name(
            request, match, expected_kind="HorizontalPodAutoscaler"
        ),
        pod_target_name_from_request=lambda request, match: natural_target_name(
            request, match, expected_kind="Pod"
        ),
        hpa_bounds=hpa_bounds_from_message,
        rollback_revision=rollback_revision_from_message,
        page_context_resource_name=page_context_resource_name,
        now_rfc3339=now_rfc3339,
        hpa_request_pattern=HPA_REQUEST_RE,
        scale_intent_pattern=SCALE_INTENT_RE,
        scale_replicas_pattern=SCALE_REPLICAS_RE,
        pod_eviction_pattern=POD_EVICTION_REQUEST_RE,
        pod_resource_pattern=POD_RESOURCE_RE,
        rollback_request_pattern=ROLLBACK_REQUEST_RE,
        restart_intent_pattern=RESTART_INTENT_RE,
        restart_request_pattern=RESTART_REQUEST_RE,
    )


def _natural_action_orchestration_dependencies(
) -> natural_action_orchestration.NaturalActionOrchestrationDependencies:
    return natural_action_orchestration.NaturalActionOrchestrationDependencies(
        openshift_api_url=OPENSHIFT_API_URL,
        openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
        mutations_enabled=MUTATIONS_ENABLED,
        sealed_action_plans=SEALED_ACTION_PLANS,
        execution_records=EXECUTION_RECORDS,
        action_target_type=ActionTarget,
        action_proposal_create_type=ActionProposalCreate,
        approval_decision_create_type=ApprovalDecisionCreate,
        approval_decision_record_input_type=ApprovalDecisionRecordInput,
        execution_grant_input_type=ExecutionGrantInput,
        parse_natural_action_intent=parse_natural_action_intent,
        resolve_natural_action_target=resolve_natural_action_target,
        build_action_proposal_record=build_action_proposal_record,
        build_sealed_action_plan_record=build_sealed_action_plan_record,
        bounded_put_record=bounded_put_record,
        increment_metric=increment_metric,
        can_subject_read_record=can_subject_read_record,
        fetch_action_access_review=fetch_action_access_review,
        enforce_action_access_review=enforce_action_access_review,
        build_approval_decision_record=build_approval_decision_record_for_context,
        validate_approval_is_active=validate_approval_is_active,
        validate_execution_evidence_freshness=validate_execution_evidence_freshness,
        build_execution_grant_reference=build_execution_grant_reference_for_context,
        action_record_context=action_record_context,
        execute_action_with_executor=execute_action_with_executor,
        natural_action_executor_fallback_authorization=natural_action_executor_fallback_authorization,
        now_rfc3339=now_rfc3339,
        redact_sensitive=redact_sensitive,
    )


async def create_natural_action_plan(
    req: ChatRequest,
    authorization: str,
    subject: Mapping[str, Any],
    *,
    incident_id: str,
    run_id: str,
) -> dict[str, Any] | None:
    return await natural_action_orchestration.create_natural_action_plan(
        req,
        authorization,
        subject,
        incident_id=incident_id,
        run_id=run_id,
        dependencies=_natural_action_orchestration_dependencies(),
    )


def _action_candidate_plan_config() -> action_candidate_plans.ActionCandidatePlanConfig:
    return action_candidate_plans.ActionCandidatePlanConfig(
        openshift_api_url=OPENSHIFT_API_URL,
        openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
        test_pod_create_enabled=TEST_POD_CREATE_ENABLED,
        test_pod_create_allowed_namespaces=frozenset(TEST_POD_CREATE_ALLOWED_NAMESPACES),
        test_pod_create_default_image=TEST_POD_CREATE_DEFAULT_IMAGE,
        test_pod_create_name_prefix=TEST_POD_CREATE_NAME_PREFIX,
    )


def _action_candidate_plan_dependencies() -> action_candidate_plans.ActionCandidatePlanDependencies:
    return action_candidate_plans.ActionCandidatePlanDependencies(
        action_candidate_plan_intent=action_candidate_plan_intent,
        action_target_type=ActionTarget,
        action_proposal_create_type=ActionProposalCreate,
        async_client_factory=httpx.AsyncClient,
        timeout_factory=httpx.Timeout,
        now_rfc3339=now_rfc3339,
        path_segment=path_segment,
        fetch_ocp_json=fetch_ocp_json,
        resolve_natural_action_target=resolve_natural_action_target,
        build_action_proposal_record=build_action_proposal_record,
        build_sealed_action_plan_record=build_sealed_action_plan_record,
        bounded_put_record=bounded_put_record,
        increment_metric=increment_metric,
        maybe_auto_approve_and_execute=maybe_auto_approve_and_execute,
    )


def action_candidate_plan_intent(req: ActionCandidatePlanCreate) -> dict[str, Any]:
    dependencies = _action_candidate_plan_dependencies()
    return action_candidate_plans.action_candidate_plan_intent(
        req,
        config=_action_candidate_plan_config(),
        now_rfc3339=dependencies.now_rfc3339,
    )


async def create_plan_from_action_candidate(
    req: ActionCandidatePlanCreate,
    authorization: str,
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return await action_candidate_plans.create_plan_from_action_candidate(
        req,
        authorization,
        subject,
        config=_action_candidate_plan_config(),
        dependencies=_action_candidate_plan_dependencies(),
    )

def natural_action_plan_response(result: Mapping[str, Any]) -> str:
    return natural_action_rendering.natural_action_plan_response(
        result, redact_sensitive=redact_sensitive
    )


def action_plan_result_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    return natural_action_orchestration.action_plan_result_from_record(record)


def plan_has_execution(plan_id: str) -> bool:
    return natural_action_orchestration.plan_has_execution(
        plan_id, execution_records=EXECUTION_RECORDS
    )


def latest_pending_action_plan_result(subject: Mapping[str, Any]) -> dict[str, Any] | None:
    return natural_action_orchestration.latest_pending_action_plan_result(
        subject,
        sealed_action_plans=SEALED_ACTION_PLANS,
        plan_has_execution=plan_has_execution,
        can_subject_read_record=can_subject_read_record,
        action_plan_result_from_record=action_plan_result_from_record,
    )


def no_pending_action_plan_response() -> str:
    return natural_action_rendering.no_pending_action_plan_response()


def unresolved_natural_action_response(req: ChatRequest) -> str:
    return natural_action_rendering.unresolved_natural_action_response(
        req,
        normalize_console_page_context=normalize_console_page_context,
        namespace_from_natural_action=namespace_from_natural_action,
        page_context_resource_name=page_context_resource_name,
        resource_patterns=(
            DEPLOYMENT_RESOURCE_RE,
            POD_RESOURCE_RE,
            HPA_RESOURCE_RE,
            NAMESPACED_RESOURCE_SHORTHAND_RE,
            BACKTICK_RESOURCE_RE,
        ),
    )


async def execute_natural_action_plan_result(
    plan_result: Mapping[str, Any],
    authorization: str,
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    return await natural_action_orchestration.execute_natural_action_plan_result(
        plan_result,
        authorization,
        subject,
        dependencies=_natural_action_orchestration_dependencies(),
    )


def natural_action_execution_response(result: Mapping[str, Any]) -> str:
    return natural_action_rendering.natural_action_execution_response(
        result,
        sealed_action_plans=SEALED_ACTION_PLANS,
        redact_sensitive=redact_sensitive,
    )


def natural_action_evidence_check_response(intent: Mapping[str, Any]) -> str:
    return natural_action_rendering.natural_action_evidence_check_response(
        intent, redact_sensitive=redact_sensitive
    )


def safe_error_text(value: Any, *, limit: int = 500) -> str:
    redacted = redact_sensitive(value)
    if isinstance(redacted, str):
        text = redacted
    else:
        text = json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    text = text.replace("\x00", "").strip()
    if len(text) > limit:
        return f"{text[:limit]}..."
    return text


def safe_exception_text(exc: Exception, *, limit: int = 500) -> str:
    if isinstance(exc, HTTPException):
        return safe_error_text(f"HTTP {exc.status_code}: {exc.detail}", limit=limit)
    return safe_error_text(f"{type(exc).__name__}: {exc}", limit=limit)


def auth_runtime_config() -> auth_runtime.AuthRuntimeConfig:
    return auth_runtime.AuthRuntimeConfig(
        openshift_api_url=OPENSHIFT_API_URL,
        openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
        product_access_review_enabled=PRODUCT_ACCESS_REVIEW_ENABLED,
        product_access_review_required=PRODUCT_ACCESS_REVIEW_REQUIRED,
        product_access_review_group=PRODUCT_ACCESS_REVIEW_GROUP,
        product_access_review_resource=PRODUCT_ACCESS_REVIEW_RESOURCE,
        product_access_review_verb=PRODUCT_ACCESS_REVIEW_VERB,
        product_access_review_name=PRODUCT_ACCESS_REVIEW_NAME,
        mutations_enabled=MUTATIONS_ENABLED,
    )


def auth_runtime_callbacks() -> auth_runtime.AuthRuntimeCallbacks:
    return auth_runtime.AuthRuntimeCallbacks(
        http_client_factory=httpx.AsyncClient,
        redact_sensitive=redact_sensitive,
        safe_exception_text=safe_exception_text,
        safe_subject=safe_subject,
        enforce_rate_limit=enforce_rate_limit,
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def verify_user_access(user_auth_header: str, req: ChatRequest) -> None:
    auth_runtime.verify_user_access(
        auth_runtime_callbacks(),
        user_auth_header,
        req,
    )


def verify_bearer_header(user_auth_header: str | None) -> str:
    return auth_runtime.verify_bearer_header(user_auth_header)


def validate_image_attachments(attachments: list[ImageAttachment]) -> None:
    total_size = 0
    seen_ids: set[str] = set()

    for attachment in attachments:
        if attachment.id in seen_ids:
            raise HTTPException(status_code=400, detail="Duplicate attachment id")
        seen_ids.add(attachment.id)

        if attachment.mimeType not in ALLOWED_IMAGE_MIME_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {attachment.mimeType}")

        try:
            decoded = base64.b64decode(attachment.data, validate=True)
        except binascii.Error as exc:
            raise HTTPException(status_code=400, detail="Invalid image attachment data") from exc

        decoded_size = len(decoded)
        if decoded_size != attachment.size:
            raise HTTPException(status_code=400, detail="Image attachment size mismatch")
        if decoded_size > MAX_IMAGE_ATTACHMENT_BYTES:
            raise HTTPException(status_code=400, detail="Image attachment is too large")

        total_size += decoded_size

    if total_size > MAX_IMAGE_ATTACHMENT_TOTAL_BYTES:
        raise HTTPException(status_code=400, detail="Image attachments are too large")


def build_cluster_summary(
    nodes_payload: Mapping[str, Any],
    node_metrics_payload: Mapping[str, Any] | None,
    cluster_version_payload: Mapping[str, Any] | None,
    cluster_operators_payload: Mapping[str, Any] | None,
    pods_payload: Mapping[str, Any] | None = None,
    deployments_payload: Mapping[str, Any] | None = None,
    replicasets_payload: Mapping[str, Any] | None = None,
    daemonsets_payload: Mapping[str, Any] | None = None,
    statefulsets_payload: Mapping[str, Any] | None = None,
    services_payload: Mapping[str, Any] | None = None,
    routes_payload: Mapping[str, Any] | None = None,
    pvcs_payload: Mapping[str, Any] | None = None,
    namespaces_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return build_cluster_summary_read_model(
        nodes_payload,
        node_metrics_payload,
        cluster_version_payload,
        cluster_operators_payload,
        pods_payload,
        deployments_payload,
        replicasets_payload,
        daemonsets_payload,
        statefulsets_payload,
        services_payload,
        routes_payload,
        pvcs_payload,
        namespaces_payload,
        api_url=OPENSHIFT_API_URL,
    )


def cluster_observability_config() -> ClusterObservabilityConfig:
    return ClusterObservabilityConfig(
        api_url=OPENSHIFT_API_URL,
        api_ca_file=OPENSHIFT_API_CA_FILE,
    )


def cluster_observability_dependencies() -> ClusterObservabilityDependencies:
    return ClusterObservabilityDependencies(
        fetch_ocp_json=fetch_ocp_json,
        fetch_ocp_json_observed=fetch_ocp_json_observed,
        query_thanos_instant=query_thanos_instant,
        data_source_status=data_source_status,
        monitoring_urls_from_config=monitoring_urls_from_config,
        append_gateway_evidence=append_gateway_evidence,
        build_pod_status_evidence=build_pod_status_evidence,
        build_deployment_rollout_evidence=build_deployment_rollout_evidence,
        build_cluster_operator_status_evidence=build_cluster_operator_status_evidence,
        build_pod_count_investigation=build_pod_count_investigation,
        build_cronjob_activity_evidence=build_cronjob_activity_evidence,
        build_node_status_rca_evidence=build_node_status_rca_evidence,
        build_active_alerts_rca_evidence=build_active_alerts_rca_evidence,
        build_restart_metric_rca_evidence=build_restart_metric_rca_evidence,
        rca_probe_event_status=rca_probe_event_status,
        prometheus_probe_reason=_prometheus_probe_reason,
        safe_error_text=safe_error_text,
    )


def data_source_status(
    *,
    label: str,
    name: str,
    path: str,
    payload: Mapping[str, Any] | None = None,
    required: bool = False,
    reason: str = "",
    status: str | None = None,
    http_status: int | None = None,
) -> dict[str, Any]:
    return cluster_observability_runtime.data_source_status(
        label=label,
        name=name,
        path=path,
        payload=payload,
        required=required,
        reason=reason,
        status=status,
        http_status=http_status,
    )


async def fetch_ocp_json_observed(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    label: str,
    name: str,
    required: bool = False,
) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
    return await cluster_observability_runtime.fetch_ocp_json_observed(
        cluster_observability_config(),
        client,
        path,
        authorization,
        label=label,
        name=name,
        required=required,
    )


monitoring_urls_from_config = cluster_observability_runtime.monitoring_urls_from_config

async def query_thanos_instant(thanos_url: str, authorization: str, query: str) -> dict[str, Any]:
    return await cluster_observability_runtime.query_thanos_instant(
        cluster_observability_config(), thanos_url, authorization, query
    )


async def probe_thanos_query(thanos_url: str, authorization: str) -> dict[str, Any]:
    return await query_thanos_instant(thanos_url, authorization, "up")



def build_aiops_anomaly_summary(
    cluster_summary_payload: Mapping[str, Any],
    pods_payload: Mapping[str, Any] | None,
    events_payload: Mapping[str, Any] | None,
    alerts_probe: Mapping[str, Any] | None,
    restart_probe: Mapping[str, Any] | None,
    data_sources: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return build_aiops_anomaly_summary_read_model(
        cluster_summary_payload,
        pods_payload,
        events_payload,
        alerts_probe,
        restart_probe,
        data_sources,
        safety=ClusterSafety(
            mutations_enabled=MUTATIONS_ENABLED,
            unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
        ),
    )


def build_aiops_action_candidates(
    anomaly_summary: Mapping[str, Any] | None,
    data_sources: list[Mapping[str, Any]],
) -> dict[str, Any]:
    return build_aiops_action_candidates_for_runtime(
        anomaly_summary,
        data_sources,
        mutations_enabled=ACTION_PLAN_CAPABILITY_ENABLED,
        action_executor_url=ACTION_EXECUTOR_URL,
        unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
    )


def build_aiops_overview(
    cluster_summary_payload: Mapping[str, Any],
    data_sources: list[Mapping[str, Any]],
    monitoring_urls: Mapping[str, str],
    monitoring_probe: Mapping[str, Any],
    anomaly_summary: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return cluster_observability_runtime.build_aiops_overview(
        cluster_summary_payload,
        data_sources,
        monitoring_urls,
        monitoring_probe,
        anomaly_summary,
        api_url=OPENSHIFT_API_URL,
        action_plan_capability_enabled=ACTION_PLAN_CAPABILITY_ENABLED,
        unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
        build_action_candidates=build_aiops_action_candidates,
        generated_at=now_rfc3339(),
    )


def should_forward_image_attachments_to_ols() -> bool:
    # OLS 1.1.x rejects attachment_type=image. Do not allow a stale runtime
    # environment value to break the entire Lightspeed request with HTTP 422.
    return False


def build_ols_gateway_context(
    *,
    tool_plan: Mapping[str, Any],
    rca_context: Mapping[str, Any],
    safety_contract: Mapping[str, Any],
    policy: Mapping[str, Any],
    gateway_evidence: str | None = None,
) -> dict[str, Any]:
    return build_ols_gateway_context_for_input(
        OlsGatewayContextInput(
            tool_plan=tool_plan,
            rca_context=rca_context,
            safety_contract=safety_contract,
            policy=policy,
            gateway_evidence=gateway_evidence,
        )
    )


def build_ols_payload(
    query: str,
    conversation_id: str | None,
    attachments: list[ImageAttachment],
    *,
    forward_image_attachments: bool = False,
    gateway_context: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return build_ols_payload_for_context(
        OlsPayloadInput(
            query=query,
            conversation_id=conversation_id,
            attachments=attachments,
            forward_image_attachments=forward_image_attachments,
            forward_conversation_id=OLS_FORWARD_CONVERSATION_ID,
            gateway_context=gateway_context,
        )
    )


def build_ols_context_handoff(
    *,
    gateway_context: Mapping[str, Any] | None = None,
    gateway_evidence: str | None = None,
) -> str:
    return build_ols_context_handoff_for_limits(
        OlsContextHandoffInput(
            gateway_context=gateway_context,
            gateway_evidence=gateway_evidence,
            max_chars=OLS_CONTEXT_HANDOFF_MAX_CHARS,
            max_lines=OLS_CONTEXT_HANDOFF_MAX_LINES,
        )
    )


def get_vision_config() -> dict[str, str] | None:
    return get_image_analysis_config()


def should_collect_pod_status_evidence(message: str) -> bool:
    return bool(
        POD_STATUS_ANALYSIS_RE.search(message)
        or POD_LIST_REQUEST_RE.search(message)
        or POD_COUNT_QUERY_RE.search(message)
        or CLUSTER_OPERATOR_ANALYSIS_RE.search(message)
    )


def should_collect_pod_status_evidence_for_request(req: ChatRequest) -> bool:
    return should_collect_pod_status_evidence(req.message) or page_context_is_pod_workload(req)


def should_collect_cronjob_activity_evidence(
    message: str,
    image_analysis: str | None = None,
) -> bool:
    combined = f"{message}\n{image_analysis or ''}".strip()
    return bool(combined and CRONJOB_ACTIVITY_ANALYSIS_RE.search(combined))


def should_collect_rca_signal_evidence(message: str) -> bool:
    return bool(
        should_collect_pod_status_evidence(message)
        or CLUSTER_OPERATOR_ANALYSIS_RE.search(message)
        or RCA_SIGNAL_ANALYSIS_RE.search(message)
    )


def should_collect_rca_signal_evidence_for_request(req: ChatRequest) -> bool:
    return bool(
        should_collect_pod_status_evidence_for_request(req)
        or CLUSTER_OPERATOR_ANALYSIS_RE.search(req.message)
        or RCA_SIGNAL_ANALYSIS_RE.search(req.message)
    )


def append_gateway_evidence(current: str | None, new_evidence: str) -> str:
    if not current:
        return new_evidence

    return f"{current}\n\n{new_evidence}"


def resource_items(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    return namespace_cleanup_runtime_support.resource_items(payload)


def metadata_name(resource: Mapping[str, Any]) -> str:
    return namespace_cleanup_runtime_support.metadata_name(resource)


def metadata_namespace(resource: Mapping[str, Any]) -> str:
    return namespace_cleanup_runtime_support.metadata_namespace(resource)


def resource_labels(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    return namespace_cleanup_runtime_support.resource_labels(resource)


def parse_k8s_timestamp(value: Any) -> datetime | None:
    return namespace_cleanup_runtime_support.parse_k8s_timestamp(value)


def age_days(value: Any) -> int | None:
    return namespace_cleanup_runtime_support.age_days(value)


def namespace_resource_counts(
    namespace: str,
    payloads: Mapping[str, Mapping[str, Any] | None],
) -> dict[str, int]:
    return namespace_cleanup_runtime_support.namespace_resource_counts(namespace, payloads)


def namespace_last_event_age_days(
    namespace: str,
    events_payload: Mapping[str, Any] | None,
) -> int | None:
    return namespace_cleanup_runtime_support.namespace_last_event_age_days(
        namespace, events_payload
    )


def namespace_cleanup_decision(
    namespace: str,
    namespace_resource: Mapping[str, Any] | None,
    counts: Mapping[str, int],
    last_event_age: int | None,
) -> dict[str, str]:
    return namespace_cleanup_runtime_support.namespace_cleanup_decision(
        namespace, namespace_resource, counts, last_event_age
    )


def namespace_cleanup_candidate_from_item(
    item: Mapping[str, Any],
    run_id: str,
    incident_id: str,
) -> dict[str, Any]:
    return namespace_cleanup_runtime_support.namespace_cleanup_candidate_from_item(
        item,
        run_id,
        incident_id,
        namespace_cleanup_runtime_support.NamespaceCleanupCandidateConfig(
            forbidden_verbs=ACTION_CANDIDATE_FORBIDDEN_VERBS
        ),
    )


async def collect_namespace_cleanup_inventory(
    user_auth_header: str,
    requested_names: Sequence[str],
) -> dict[str, Any]:
    return await namespace_cleanup_runtime_support.collect_namespace_cleanup_inventory(
        user_auth_header,
        requested_names,
        namespace_cleanup_runtime_support.NamespaceCleanupInventoryConfig(
            api_url=OPENSHIFT_API_URL,
            api_ca_file=OPENSHIFT_API_CA_FILE,
        ),
        namespace_cleanup_runtime_support.NamespaceCleanupInventoryDependencies(
            fetch_ocp_json=fetch_ocp_json
        ),
    )

def action_capable_execution_mode(mode: str) -> bool:
    return mode in {"execute", "unrestricted"}


def execution_mode_sentence(mode: str, language: str) -> str:
    is_en = language == "en"
    if mode == "unrestricted":
        return (
            "Unrestricted mode: evidence is collected and approval-gated review plans can be created; this path still does not delete namespaces automatically."
            if is_en
            else "실행 무제한 모드: 조회 후 승인 검토 계획을 만들 수 있지만, 이 경로에서 namespace 삭제를 자동 실행하지 않습니다."
        )
    if mode == "execute":
        return (
            "Execution-enabled mode: evidence is collected and approval-gated Action Plan candidates can be created. No change runs before approval."
            if is_en
            else "실행 가능 모드: 조회 후 승인 가능한 Action Plan 후보를 만들 수 있습니다. 승인 전 변경은 실행하지 않습니다."
        )
    return (
        "Read-only mode: evidence and plan candidates can be reviewed, but Action Plan creation, approval, and execution are locked."
        if is_en
        else "읽기 전용 모드: 조회 결과와 계획 후보는 확인할 수 있지만, Action Plan 생성·승인·실행은 잠겨 있습니다."
    )


def action_policy_mode_for_execution_mode(mode: str, candidate_ready: bool) -> str:
    if mode == "unrestricted" and candidate_ready:
        return "unrestricted_pending_approval"
    if mode == "execute" and candidate_ready:
        return "controlled_execution"
    return "read_only_review"


def test_pod_create_count_from_message(message: str) -> int | None:
    return parse_test_pod_create_count_from_message(message)


def test_pod_create_request_from_message(message: str) -> dict[str, Any]:
    return parse_test_pod_create_request_from_message(
        message,
        test_pod_create_settings(),
        namespace_names_from_message,
    )


def test_pod_create_is_ready(request: Mapping[str, Any]) -> bool:
    return test_pod_create_request_is_ready(request, test_pod_create_settings())


def test_pod_create_disabled_answer(request: Mapping[str, Any], language: str) -> str:
    return render_test_pod_create_disabled_answer(request, language)


async def collect_test_pod_create_preflight(
    user_auth_header: str,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    return await collect_test_pod_create_preflight_for_settings(
        request,
        api_ca_file=OPENSHIFT_API_CA_FILE,
        api_url=OPENSHIFT_API_URL,
        fetch_ocp_json=fetch_ocp_json,
        path_segment=path_segment,
        settings=test_pod_create_settings(),
        user_auth_header=user_auth_header,
    )


def test_pod_create_candidate_from_preflight(
    request: Mapping[str, Any],
    preflight: Mapping[str, Any],
    run_id: str,
    incident_id: str,
) -> dict[str, Any]:
    return build_test_pod_create_candidate_from_preflight(
        request,
        preflight,
        run_id,
        incident_id,
        test_pod_create_settings(),
    )


def test_pod_create_answer(
    request: Mapping[str, Any],
    preflight: Mapping[str, Any],
    execution_mode: str,
    language: str,
) -> str:
    return render_test_pod_create_answer(
        request,
        preflight,
        execution_mode_sentence(execution_mode, language),
        action_mode=action_capable_execution_mode(execution_mode),
        language=language,
        settings=test_pod_create_settings(),
    )


def test_pod_create_tool_plan(
    request: Mapping[str, Any],
    execution_mode: str,
    *,
    can_propose: bool | None = None,
) -> dict[str, Any]:
    requested_can_propose = action_capable_execution_mode(execution_mode) if can_propose is None else bool(can_propose)
    action_ready = test_pod_create_is_ready(request) and requested_can_propose
    return build_test_pod_create_tool_plan(request, execution_mode, action_ready=action_ready)


def namespace_cleanup_candidates_from_inventory(
    inventory: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    return namespace_cleanup_runtime_support.namespace_cleanup_candidates_from_inventory(
        inventory
    )


def namespace_cleanup_command_block(inventory: Mapping[str, Any]) -> str:
    return namespace_cleanup_runtime_support.namespace_cleanup_command_block(inventory)


def namespace_cleanup_answer(
    inventory: Mapping[str, Any],
    execution_mode: str,
    language: str,
) -> str:
    return namespace_cleanup_runtime_support.namespace_cleanup_answer(
        inventory,
        execution_mode,
        language,
        namespace_cleanup_runtime_support.NamespaceCleanupRenderDependencies(
            action_capable_mode=action_capable_execution_mode,
            execution_mode_sentence=execution_mode_sentence,
        ),
    )


def remember_namespace_cleanup_candidates(
    inventory: Mapping[str, Any],
    run_id: str,
    incident_id: str,
) -> None:
    namespace_cleanup_runtime_support.remember_namespace_cleanup_candidates(
        inventory,
        run_id,
        incident_id,
        namespace_cleanup_runtime_support.NamespaceCleanupCandidateStoreDependencies(
            candidate_cache=NAMESPACE_CLEANUP_CHAT_CANDIDATES,
            build_candidate=namespace_cleanup_candidate_from_item,
            candidates_from_inventory=namespace_cleanup_candidates_from_inventory,
        ),
    )


def merge_recent_namespace_cleanup_candidates(
    action_candidates: Mapping[str, Any],
) -> dict[str, Any]:
    return namespace_cleanup_runtime_support.merge_recent_namespace_cleanup_candidates(
        action_candidates,
        NAMESPACE_CLEANUP_CHAT_CANDIDATES,
    )

def choose_single_natural_action_target(
    candidates: list[Mapping[str, Any]],
    *,
    target_name: str,
) -> dict[str, Any]:
    if not candidates:
        return {"status": "not_found"}

    exact = [candidate for candidate in candidates if metadata_name(candidate) == target_name]
    narrowed = exact or candidates
    unique_by_namespace_name = {
        (metadata_namespace(candidate), metadata_name(candidate)): candidate for candidate in narrowed
    }
    unique_candidates = list(unique_by_namespace_name.values())
    if len(unique_candidates) == 1:
        return {"status": "found", "target": unique_candidates[0]}

    return {
        "candidates": [
            {
                "kind": str(candidate.get("kind") or ""),
                "name": metadata_name(candidate),
                "namespace": metadata_namespace(candidate),
            }
            for candidate in sorted(unique_candidates, key=lambda item: (metadata_namespace(item), metadata_name(item)))[:10]
        ],
        "status": "ambiguous",
    }


async def resolve_natural_action_target(
    client: httpx.AsyncClient,
    intent: Mapping[str, Any],
    authorization: str,
) -> dict[str, Any]:
    namespace = str(intent.get("namespace") or "")
    target_name = str(intent.get("targetName") or "")
    api_version = str(intent.get("apiVersion") or "apps/v1")
    kind = str(intent.get("kind") or "Deployment")
    lookup_target = {
        "apiVersion": api_version,
        "kind": kind,
        "namespace": namespace,
        "name": target_name,
    }

    if namespace:
        live_target = await fetch_ocp_json(client, target_path(lookup_target), authorization)
        return {"status": "found", "target": live_target} if live_target else {"status": "not_found"}

    if kind != "Deployment" or api_version != "apps/v1":
        return {"status": "missing_namespace"}

    deployments_payload = await fetch_ocp_json(client, "/apis/apps/v1/deployments", authorization)
    deployments = resource_items(deployments_payload)
    identity_matches = [
        deployment for deployment in deployments if deployment_matches_identity(deployment, target_name)
    ]
    identity_result = choose_single_natural_action_target(identity_matches, target_name=target_name)
    if identity_result["status"] in {"found", "ambiguous"}:
        return identity_result

    pods_payload = await fetch_ocp_json(client, "/api/v1/pods", authorization)
    matched_pods = [
        pod for pod in resource_items(pods_payload) if pod_matches_target_fallback(pod, target_name)
    ]
    selector_matches = [
        deployment
        for deployment in deployments
        if any(pod_matches_deployment_selector(pod, deployment) for pod in matched_pods)
    ]
    selector_result = choose_single_natural_action_target(selector_matches, target_name=target_name)
    if selector_result["status"] == "found":
        selector_result["matchStrategy"] = "pod_name_or_standard_labels_to_deployment_selector"
    return selector_result


def trim_context_content(content: str, limit: int = 700) -> str:
    normalized = re.sub(r"\s+", " ", strip_private_reasoning_sections(content)).strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 1]}…"


def build_recent_conversation_context(req: ChatRequest) -> str:
    lines: list[str] = []
    for message in req.recentMessages[-6:]:
        role = message.role.strip().lower()
        if role not in {"user", "assistant"}:
            continue
        content = trim_context_content(redact_sensitive(message.content or ""))
        if not content:
            continue
        label = "사용자" if role == "user" else "AIOps"
        lines.append(f"- {label}: {content}")
    return "\n".join(lines)


def build_ols_query(
    req: ChatRequest,
    image_analysis: str | None = None,
    *,
    policy: Mapping[str, Any] | None = None,
    subject: Mapping[str, Any] | None = None,
    gateway_context: Mapping[str, Any] | None = None,
    gateway_evidence: str | None = None,
) -> str:
    page_context = normalize_console_page_context(req.pageContext)
    language_contract = answer_language_contract(req)
    section_contract = answer_section_contract(req)
    operating_answer_contract = assistant_operating_answer_style_contract(req)
    resource_summary_contract = resource_summary_rca_answer_contract(req)
    forwarded_to_ols = should_forward_image_attachments_to_ols()
    effective_policy = policy or classify_request_policy(req.message)
    subject_metadata = subject or safe_subject(None)
    context_handoff = build_ols_context_handoff(
        gateway_context=gateway_context,
        gateway_evidence=gateway_evidence,
    )
    recent_context = build_recent_conversation_context(req)
    attachment_context = build_attachment_context(
        req.attachments,
        redact_sensitive(image_analysis) if image_analysis else None,
        forwarded_to_ols=forwarded_to_ols,
    )
    model_message = (
        build_grounded_image_question(req.message, image_analysis or "")
        if image_analysis
        else req.message
    )

    return render_ols_query(
        OlsQueryRenderInput(
            profile=OLS_QUERY_PROFILE,
            message=model_message,
            page_context=page_context,
            policy=effective_policy if isinstance(effective_policy, Mapping) else {},
            subject_metadata=subject_metadata if isinstance(subject_metadata, Mapping) else {},
            language_contract=language_contract,
            section_contract=section_contract,
            operating_answer_contract=operating_answer_contract,
            resource_summary_contract=resource_summary_contract,
            attachment_context=attachment_context,
            recent_context=recent_context,
            context_handoff=context_handoff,
            gateway_guardrail=build_gateway_guardrail(effective_policy),
            crashloop_contract=crashloop_demo_prompt_answer_contract(req),
            past_pod_restart_contract=past_pod_restart_demo_prompt_contract(req),
        )
    )


async def analyze_image_attachments(
    attachments: list[ImageAttachment],
    user_message: str,
) -> str | None:
    return await analyze_image_attachments_with_model(attachments, user_message)


def update_ols_stream_status(
    status: str,
    *,
    context_digest: str = "",
    fallback_active: bool = False,
    reason: str = "",
) -> None:
    global OLS_STREAM_STATUS
    now = now_rfc3339()
    previous_started_at = str(OLS_STREAM_STATUS.get("lastStartedAt") or "")
    safe_reason = safe_error_text(reason, limit=500) if reason else ""
    OLS_STREAM_STATUS = {
        "streamProbe": status,
        "lastStatus": status,
        "lastContextDigest": context_digest,
        "lastStartedAt": now if status == "started" else previous_started_at,
        "lastCompletedAt": now if status in {"succeeded", "failed", "dev_echo", "not_configured"} else "",
        "lastError": safe_reason if status in {"failed", "not_configured", "dev_echo"} else "",
        "fallbackActive": fallback_active,
    }


def llm_stream_config() -> LlmStreamConfig:
    return LlmStreamConfig(
        api_style=LLM_API_STYLE,
        base_url=LLM_BASE_URL,
        model=LLM_MODEL,
        timeout_seconds=LLM_TIMEOUT_SECONDS,
        heartbeat_seconds=RUN_HEARTBEAT_SECONDS,
        ols_base_url=OLS_BASE_URL,
        ols_ca_file=OLS_CA_FILE,
        ols_connect_timeout_seconds=OLS_CONNECT_TIMEOUT_SECONDS,
        dev_echo=DEV_ECHO,
        require_final_answer=REQUIRE_OLS_FINAL_ANSWER,
    )


def llm_stream_dependencies() -> LlmStreamDependencies:
    return LlmStreamDependencies(
        build_ols_payload=build_ols_payload,
        forward_image_attachments=should_forward_image_attachments_to_ols,
        parse_tool_text_line=parse_tool_text_line,
        safe_error_text=safe_error_text,
        safe_exception_text=safe_exception_text,
        split_plain_text_events=split_plain_text_events,
        update_status=update_ols_stream_status,
        status_snapshot=lambda: OLS_STREAM_STATUS,
    )


async def stream_with_heartbeats(
    events: AsyncIterator[dict[str, Any]],
    run_id: str,
) -> AsyncIterator[dict[str, Any]]:
    async for event in stream_with_client_heartbeats(
        events,
        run_id,
        config=llm_stream_config(),
    ):
        yield event


def should_use_ollama_llm() -> bool:
    return should_use_ollama_for_config(llm_stream_config())


def active_llm_stage() -> str:
    return active_llm_stage_for_config(llm_stream_config())


def active_llm_label() -> str:
    return active_llm_label_for_config(llm_stream_config())


def build_ollama_chat_url(base_url: str) -> str:
    return build_ollama_chat_url_for_client(base_url)


def extract_ollama_chat_content(data: Mapping[str, Any]) -> str:
    return extract_ollama_chat_content_from_response(data)


async def call_ollama_chat(
    query: str,
    conversation_id: str | None,
    gateway_context: Mapping[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    async for event in call_ollama_chat_with_client(
        query,
        conversation_id,
        gateway_context,
        config=llm_stream_config(),
        dependencies=llm_stream_dependencies(),
    ):
        yield event


async def call_ols_stream(
    user_auth_header: str,
    query: str,
    conversation_id: str | None,
    attachments: list[ImageAttachment],
    gateway_context: Mapping[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    async for event in call_ols_stream_with_client(
        user_auth_header,
        query,
        conversation_id,
        attachments,
        gateway_context,
        config=llm_stream_config(),
        dependencies=llm_stream_dependencies(),
    ):
        yield event


async def fetch_ocp_json(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    required: bool = False,
) -> Mapping[str, Any] | None:
    return await cluster_observability_runtime.fetch_ocp_json(
        cluster_observability_config(),
        client,
        path,
        authorization,
        required=required,
        build_unavailable_detail=build_openshift_api_unavailable_detail,
    )


def crashloop_demo_target_from_request(req: ChatRequest) -> dict[str, str]:
    context = normalize_console_page_context(req.pageContext)
    demo_cycle = context.get("aiopsDemoCycle")
    if not isinstance(demo_cycle, Mapping) or demo_cycle.get("scenarioId") not in {
        "crashloop",
        "evidence-rca-scene",
    }:
        return {}

    target = demo_cycle.get("target")
    if not isinstance(target, Mapping):
        return {}

    kind = str(target.get("kind") or "")
    namespace = str(target.get("namespace") or "")
    name = str(target.get("name") or "")
    if kind.lower() != "pod" or not namespace or not name:
        return {}

    return {
        "kind": "Pod",
        "name": name,
        "namespace": namespace,
    }


def crashloop_demo_prompt_answer_contract(req: ChatRequest) -> str:
    target = crashloop_demo_target_from_request(req)
    if not target:
        return "적용 없음"

    return "\n".join(
        [
            "이 요청은 Ver.0.1.3 공식 Evidence 기반 Pod 재시작 RCA 시연 사이클입니다.",
            "최종 답변에는 아래 5개 섹션명을 이 순서 그대로 포함하세요.",
            "1. `### 확인 결과`",
            "2. `### 가능한 원인 후보`",
            "3. `### 추가 확인 필요`",
            "4. `### Evidence-check 확인 순서`",
            "5. `### 금지 작업`",
            "로그 원문이나 Event message 원문을 출력하지 말고, 수집 여부/상태/digest 중심으로 말하세요.",
            "원인을 확정하지 말고 collected/partial/missing evidence에 맞춰 확인됨과 추정을 분리하세요.",
            "로그 분석은 `grep_tool`의 오류 패턴/digest 결과로 설명하고, 코드블록에 raw `oc logs` 덤프 명령을 넣지 마세요.",
            "공식 최종 답변에는 `RCA`, `즉시 조치`, `재발 방지책`, `참고 증적` 관점을 포함하세요.",
            "`oc apply/delete/patch/scale/exec/rollout restart/replace/create`는 코드블록에 넣지 말고 금지 작업 섹션에서만 언급하세요.",
        ]
    )


def past_pod_restart_demo_active(req: "ChatRequest") -> bool:
    context = normalize_console_page_context(req.pageContext)
    demo_cycle = context.get("aiopsDemoCycle")
    return (
        isinstance(demo_cycle, Mapping)
        and demo_cycle.get("scenarioId") == "past-pod-restart-rca"
    )


def past_pod_restart_demo_prompt_contract(req: "ChatRequest") -> str:
    return cluster_observability_runtime.past_pod_restart_demo_prompt_contract(
        past_pod_restart_demo_active(req)
    )


def collect_past_pod_restart_demo_evidence_events(request_id: str) -> list[dict[str, Any]]:
    return cluster_observability_runtime.collect_past_pod_restart_demo_evidence_events(
        request_id
    )


container_status_rows = cluster_evidence_runtime.container_status_rows
crashloop_container_name = cluster_evidence_runtime.crashloop_container_name
summarize_pod_event_availability = cluster_evidence_runtime.summarize_pod_event_availability
build_resource_access_review_request = cluster_evidence_runtime.build_resource_access_review_request
official_namespace_restart_namespace = cluster_evidence_runtime.official_namespace_restart_namespace
namespace_restart_candidate_rows = cluster_evidence_runtime.namespace_restart_candidate_rows
summarize_namespace_restart_events = cluster_evidence_runtime.summarize_namespace_restart_events


def cluster_evidence_runtime_config() -> ClusterEvidenceRuntimeConfig:
    return ClusterEvidenceRuntimeConfig(
        openshift_api_url=OPENSHIFT_API_URL,
        openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
        demo_namespace_allowlist=frozenset(DEMO_NAMESPACE_ALLOWLIST),
    )


def cluster_evidence_runtime_callbacks() -> ClusterEvidenceRuntimeCallbacks:
    return ClusterEvidenceRuntimeCallbacks(
        fetch_ocp_json=fetch_ocp_json,
        fetch_ocp_text_status=fetch_ocp_text_status,
        fetch_resource_access_review=fetch_resource_access_review,
        fetch_crashloop_demo_access_reviews=fetch_crashloop_demo_access_reviews,
        fetch_ocp_log_pattern_probe=fetch_ocp_log_pattern_probe,
        collect_cluster_wide_restart_fallback_events=collect_cluster_wide_restart_fallback_events,
    )


async def fetch_ocp_text_status(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
) -> dict[str, Any]:
    return await cluster_evidence_runtime.fetch_ocp_text_status(
        cluster_evidence_runtime_config(), client, path, authorization
    )


async def fetch_resource_access_review(
    client: httpx.AsyncClient,
    user_auth_header: str,
    resource_attributes: Mapping[str, Any],
) -> dict[str, Any]:
    return await cluster_evidence_runtime.fetch_resource_access_review(
        cluster_evidence_runtime_config(), client, user_auth_header, resource_attributes
    )


async def fetch_crashloop_demo_access_reviews(
    client: httpx.AsyncClient,
    user_auth_header: str,
    target: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    return await cluster_evidence_runtime.fetch_crashloop_demo_access_reviews(
        cluster_evidence_runtime_config(), client, user_auth_header, target
    )


def crashloop_demo_skipped_evidence_events(
    *,
    request_id: str,
    target: Mapping[str, str],
    reason: str,
    detail: str = "",
) -> list[dict[str, Any]]:
    return cluster_evidence_runtime.crashloop_demo_skipped_evidence_events(
        request_id=request_id,
        target=target,
        reason=reason,
        detail=detail,
    )


async def collect_crashloop_demo_evidence_events(
    user_auth_header: str,
    target: Mapping[str, str],
    request_id: str,
) -> list[dict[str, Any]]:
    return await cluster_evidence_runtime.collect_crashloop_demo_evidence_events(
        cluster_evidence_runtime_config(),
        cluster_evidence_runtime_callbacks(),
        user_auth_header,
        target,
        request_id,
    )


async def fetch_ocp_log_pattern_probe(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
) -> dict[str, Any]:
    return await cluster_evidence_runtime.fetch_ocp_log_pattern_probe(
        cluster_evidence_runtime_config(), client, path, authorization
    )


def official_namespace_restart_skipped_evidence_events(
    *,
    namespace: str,
    request_id: str,
    reason: str,
    detail: str = "",
) -> list[dict[str, Any]]:
    return cluster_evidence_runtime.official_namespace_restart_skipped_evidence_events(
        namespace=namespace,
        request_id=request_id,
        reason=reason,
        detail=detail,
    )


async def collect_cluster_wide_restart_fallback_events(
    user_auth_header: str,
    namespace: str,
    request_id: str,
) -> list[dict[str, Any]]:
    return await cluster_evidence_runtime.collect_cluster_wide_restart_fallback_events(
        cluster_evidence_runtime_config(),
        cluster_evidence_runtime_callbacks(),
        user_auth_header,
        namespace,
        request_id,
    )


async def collect_official_namespace_restart_evidence_events(
    user_auth_header: str,
    namespace: str,
    request_id: str,
) -> list[dict[str, Any]]:
    return await cluster_evidence_runtime.collect_official_namespace_restart_evidence_events(
        cluster_evidence_runtime_config(),
        cluster_evidence_runtime_callbacks(),
        user_auth_header,
        namespace,
        request_id,
    )



async def collect_pod_status_evidence(
    user_auth_header: str,
    *,
    include_pod_list: bool = False,
    list_namespace: str = "",
) -> str:
    return await cluster_observability_runtime.collect_pod_status_evidence(
        cluster_observability_config(),
        cluster_observability_dependencies(),
        user_auth_header,
        include_pod_list=include_pod_list,
        list_namespace=list_namespace,
    )


async def collect_pod_count_investigation(
    user_auth_header: str,
    query: Mapping[str, str],
) -> dict[str, Any]:
    return await cluster_observability_runtime.collect_pod_count_investigation(
        cluster_observability_config(),
        cluster_observability_dependencies(),
        user_auth_header,
        query,
    )


async def collect_cronjob_activity_evidence(user_auth_header: str, context_text: str) -> str:
    return await cluster_observability_runtime.collect_cronjob_activity_evidence(
        cluster_observability_config(),
        cluster_observability_dependencies(),
        user_auth_header,
        context_text,
    )


_data_source_event_status = cluster_observability_runtime._data_source_event_status
_evidence_summary = cluster_observability_runtime._evidence_summary


async def _monitoring_urls_for_rca(user_auth_header: str) -> tuple[dict[str, str], dict[str, Any]]:
    return await cluster_observability_runtime.monitoring_urls_for_rca(
        cluster_observability_config(),
        cluster_observability_dependencies(),
        user_auth_header,
    )


async def collect_node_status_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    return await cluster_observability_runtime.collect_node_status_rca_evidence(
        cluster_observability_config(),
        cluster_observability_dependencies(),
        user_auth_header,
    )


async def collect_active_alerts_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    return await cluster_observability_runtime.collect_active_alerts_rca_evidence(
        cluster_observability_config(),
        cluster_observability_dependencies(),
        user_auth_header,
    )


async def collect_restart_metric_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    return await cluster_observability_runtime.collect_restart_metric_rca_evidence(
        cluster_observability_config(),
        cluster_observability_dependencies(),
        user_auth_header,
    )


def log_audit_record(record: Mapping[str, Any]) -> None:
    safe_record = redact_sensitive(dict(record))
    audit_id = str(safe_record.get("auditId") or f"audit-{uuid.uuid4().hex[:16]}")
    bounded_put(AUDIT_RECORDS, audit_id, safe_record, AUDIT_MAX_RECORDS)
    increment_metric("aiops_audit_records_total")
    print(
        json.dumps({"aiopsAudit": safe_record}, ensure_ascii=False),
        flush=True,
    )


def log_break_glass_audit_record(record: Mapping[str, Any]) -> None:
    print(
        json.dumps({"aiopsBreakGlassAudit": redact_sensitive(dict(record))}, ensure_ascii=False),
        flush=True,
    )


def build_evidence_reference_events(
    *,
    event: Mapping[str, Any],
    incident_id: str,
    run_id: str,
    source_type: str,
    subject: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    evidence_ref = build_evidence_reference(
        event=event,
        incident_id=incident_id,
        run_id=run_id,
        source_type=source_type,
        subject=subject,
    )
    event_status = str(event.get("status") or "unknown")
    evidence_type = event.get("evidenceType") or event.get("evidence_type")
    enriched_ref = {
        **evidence_ref,
        "eventName": event.get("name"),
        "eventStatus": event_status,
        "evidenceType": evidence_type,
        "missingReason": event.get("missingReason"),
        "sourcePath": event.get("sourcePath"),
    }
    enriched_ref = {
        key: value
        for key, value in enriched_ref.items()
        if value is not None and value != ""
    }
    evidence_record = {
        **enriched_ref,
        "detail": redact_sensitive(event.get("detail") or event.get("result") or ""),
    }
    bounded_put(
        EVIDENCE_RECORDS,
        str(evidence_ref["evidenceId"]),
        evidence_record,
        EVIDENCE_MAX_RECORDS,
    )
    increment_metric("aiops_evidence_records_total")
    return [
        {
            "type": "tool_call",
            "id": enriched_ref["evidenceId"],
            "name": "evidence_ref",
            "summary": "증거 참조 생성",
        },
        {
            "type": "tool_result",
            "detail": json.dumps(redact_sensitive(enriched_ref), ensure_ascii=False, indent=2),
            "id": enriched_ref["evidenceId"],
            "name": "evidence_ref",
            "result": enriched_ref,
            "status": "success",
            "summary": f"{enriched_ref['evidenceId']} 기록",
        },
    ]


def evidence_refs_for_run(run_id: str) -> list[dict[str, Any]]:
    refs = [
        redact_sensitive(dict(record))
        for record in EVIDENCE_RECORDS.values()
        if str(record.get("runId") or "") == run_id
    ]
    return sorted(
        refs,
        key=lambda item: str(item.get("collectedAt") or item.get("evidenceId") or ""),
    )


def evidence_ref_bucket(ref: Mapping[str, Any]) -> str:
    status = str(ref.get("eventStatus") or ref.get("status") or "").lower()
    if status in {"recorded", "success", "succeeded", "ok", "completed", "collected"}:
        return "collected"
    if status == "partial":
        return "partial"
    return "missing"


def evidence_type_from_record(ref: Mapping[str, Any]) -> str:
    return str(ref.get("evidenceType") or ref.get("type") or "").lower()


def evidence_contract_line(refs: list[Mapping[str, Any]], evidence_type: str, label: str) -> str:
    typed_refs = [ref for ref in refs if evidence_type_from_record(ref) == evidence_type]
    if not typed_refs:
        return f"- {label}: 확인 불가. 해당 evidence reference가 없습니다."
    preferred = sorted(
        typed_refs,
        key=lambda ref: {"collected": 0, "partial": 1}.get(evidence_ref_bucket(ref), 2),
    )[0]
    bucket = evidence_ref_bucket(preferred)
    digest = str(preferred.get("contentDigest") or "")
    short_digest = digest[:24] if digest else "digest 없음"
    reason = str(preferred.get("missingReason") or preferred.get("summary") or "")
    if bucket == "collected":
        return f"- {label}: 수집됨. evidence `{preferred.get('evidenceId')}`, digest `{short_digest}`."
    if bucket == "partial":
        return (
            f"- {label}: 부분 확인. evidence `{preferred.get('evidenceId')}`, "
            f"digest `{short_digest}`. {safe_error_text(reason, limit=160)}"
        )
    return (
        f"- {label}: 확인 불가. evidence `{preferred.get('evidenceId')}`, "
        f"상태 `{preferred.get('eventStatus') or preferred.get('status') or 'unknown'}`. "
        f"{safe_error_text(reason, limit=160)}"
    )


def build_crashloop_demo_answer_contract_text(req: ChatRequest, run_id: str) -> str:
    target = crashloop_demo_target_from_request(req)
    if not target:
        return ""

    refs = evidence_refs_for_run(run_id)
    namespace = target["namespace"]
    pod_name = target["name"]
    forbidden = ", ".join(ACTION_CANDIDATE_FORBIDDEN_VERBS)
    evidence_lines = [
        evidence_contract_line(refs, "pod_status", "Pod 상태와 재시작 확인 결과"),
        evidence_contract_line(refs, "event", "Pod Event 확인 결과"),
        evidence_contract_line(refs, "pod_log", "이전 로그 가용성"),
        evidence_contract_line(refs, "metric", "Restart/운영 메트릭"),
    ]
    return "\n".join(
        [
            "",
            "## RCA 계약 요약",
            "",
            "### 확인 결과",
            *evidence_lines,
            "",
            "### 가능한 원인 후보",
            "- 현재 시연 컨텍스트는 공식 Evidence RCA 대상 Pod 재시작 질문에 묶여 있습니다.",
            "- 컨테이너 프로세스 반복 종료, 잘못된 command/args, 설정/env 참조, 이미지 또는 애플리케이션 초기화 실패가 후보입니다.",
            "- 이 후보는 수집된 상태/event/메트릭과 이전 로그 가용성 기준의 후보이며, 로그 원문 없이 확정하지 않습니다.",
            "",
            "### RCA",
            "- 공식 시연 기준 RCA는 Event, grep/log-pattern, Metric, Snapshot evidence를 함께 묶어 판단합니다.",
            "- 현재 답변은 수집된 evidence와 누락 evidence를 분리한 원인 후보 분석이며, 단일 원인 확정이 아닙니다.",
            "",
            "### 즉시 조치",
            "- 즉시 실행 전에 증거 확인 순서와 승인 필요 여부를 먼저 제시합니다.",
            "- 영향도가 큰 변경은 action candidate로만 남기고 실행하지 않습니다.",
            "",
            "### 재발 방지책",
            "- restart 추세, resource request/limit, readiness/liveness 설정, 배포 변경 이력, runbook 보완 여부를 후속 점검합니다.",
            "",
            "### 참고 증적",
            "- Pod/Event/Metric/Snapshot evidence의 수집 상태와 digest를 기준으로 참고 증적을 표시합니다.",
            "",
            "### 추가 확인 필요",
            "- Pod log 원문은 민감정보 가능성이 있어 gateway evidence에는 저장하거나 출력하지 않았습니다.",
            "- grep_tool은 로그 원문이 아니라 OOMKilled, Eviction, stack-trace, error 같은 패턴과 digest만 확인 자료로 남겨야 합니다.",
            "- ClusterOperator 및 runbook/RAG 확인 결과는 현재 사이클에서 미수집 상태로 남을 수 있습니다.",
            "- 원인을 확정하려면 승인된 운영 절차 안에서 이벤트 상세, Pod spec, 이전 로그를 추가 확인해야 합니다.",
            "",
            "### Evidence-check 확인 순서",
            "```bash",
            f"oc describe pod {pod_name} -n {namespace}",
            f"oc get events -n {namespace} --field-selector involvedObject.name={pod_name} --sort-by=.lastTimestamp",
            f"oc get pod {pod_name} -n {namespace} -o yaml",
            "```",
            "",
            "### 금지 작업",
            f"- 이 사이클은 증거 확인 전용입니다. `{forbidden}` 계열 작업은 실행하지 않습니다.",
            "- action candidate는 제안만 하며, 승인 전 `apply/delete/patch/scale/exec/rollout/restart`를 수행하지 않습니다.",
        ]
    )


def build_rca_context_stream_event(
    *,
    req: "ChatRequest",
    runtime_tool_plan: Mapping[str, Any],
    run_id: str,
    incident_id: str,
    phase: str,
) -> dict[str, Any]:
    context = redact_sensitive(
        build_rca_context(
            message=req.message,
            tool_plan=runtime_tool_plan,
            evidence_refs=evidence_refs_for_run(run_id),
            page_context=normalize_console_page_context(req.pageContext),
            run_id=run_id,
            incident_id=incident_id,
            phase=phase,
        )
    )
    contract = build_runtime_safety_contract(
        mutations_enabled=MUTATIONS_ENABLED,
        unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
        diagnostics_enabled=DIAGNOSTICS_ENABLED,
        record_store_enabled=RECORD_STORE_ENABLED,
        diagnostics_controller_configured=bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
        lightspeed_status=redact_sensitive(dict(OLS_STREAM_STATUS)),
        latest_runtime_tool_plan=runtime_tool_plan,
        latest_rca_context=context,
    )
    return {
        "type": "rca_context",
        "context": context,
        "evidenceStatus": contract["evidenceStatus"],
        "phase": phase,
        "runId": run_id,
        "status": "success",
    }


def build_product_access_review_request() -> dict[str, Any]:
    return auth_runtime.build_product_access_review_request(auth_runtime_config())


def build_action_access_review_request(plan: Mapping[str, Any]) -> dict[str, Any]:
    return auth_runtime.build_action_access_review_request(plan)


async def fetch_action_access_review(user_auth_header: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    return await auth_runtime.fetch_action_access_review(
        auth_runtime_config(),
        auth_runtime_callbacks(),
        user_auth_header,
        plan,
    )


def enforce_action_access_review(review: Mapping[str, Any]) -> None:
    auth_runtime.enforce_action_access_review(auth_runtime_callbacks(), review)


async def fetch_product_access_review(user_auth_header: str) -> dict[str, Any]:
    return await auth_runtime.fetch_product_access_review(
        auth_runtime_config(),
        auth_runtime_callbacks(),
        user_auth_header,
    )


def product_access_review_status(review: Mapping[str, Any]) -> str:
    return auth_runtime.product_access_review_status(review)


def summarize_product_access_review(review: Mapping[str, Any]) -> str:
    return auth_runtime.summarize_product_access_review(auth_runtime_callbacks(), review)


def enforce_product_access_review(review: Mapping[str, Any]) -> None:
    auth_runtime.enforce_product_access_review(review)


OPENSHIFT_USER_AUTH_FAILURE_MESSAGE = auth_runtime.OPENSHIFT_USER_AUTH_FAILURE_MESSAGE


def build_openshift_user_auth_failure_detail(status_code: int, body: str) -> dict[str, Any]:
    return auth_runtime.build_openshift_user_auth_failure_detail(
        auth_runtime_callbacks(),
        status_code,
        body,
    )


def build_openshift_api_unavailable_detail(operation: str, exc: BaseException) -> dict[str, Any]:
    return auth_runtime.build_openshift_api_unavailable_detail(
        auth_runtime_callbacks(),
        operation,
        exc,
    )


@app.exception_handler(httpx.RequestError)
async def handle_httpx_request_error(_request: Request, exc: httpx.RequestError) -> JSONResponse:
    return JSONResponse(
        status_code=504,
        content={"detail": build_openshift_api_unavailable_detail("httpx_request", exc)},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "gateway_internal_error",
                "message": "Gateway 내부 처리 중 예외가 발생했습니다.",
                "reason": safe_exception_text(exc),
            }
        },
    )


def http_exception_message(exc: HTTPException) -> str:
    return auth_runtime.http_exception_message(auth_runtime_callbacks(), exc)


def is_openshift_user_auth_failure(exc: HTTPException) -> bool:
    return auth_runtime.is_openshift_user_auth_failure(exc)


async def fetch_self_subject_review(user_auth_header: str) -> dict[str, Any]:
    return await auth_runtime.fetch_self_subject_review(
        auth_runtime_config(),
        auth_runtime_callbacks(),
        user_auth_header,
    )


def summarize_policy_detail(policy: Mapping[str, Any]) -> str:
    decision = str(policy.get("decision") or "")
    if decision == "action_proposal_only":
        decision_label = "조치 요청은 Action Plan 경로로 처리"
        decision_explanation = "변경 가능성이 있는 요청이므로 직접 변경하지 않고 조치 계획/승인/실행 경로로 넘깁니다."
    elif decision == "allow_evidence_collection":
        decision_label = "조회 허용"
        decision_explanation = "클러스터 상태 조회와 확인 결과 정리는 허용하며 리소스 변경은 수행하지 않습니다."
    else:
        decision_label = "정책 결정 확인 필요"
        decision_explanation = str(policy.get("reason") or "-")

    risk_label = {
        "low": "낮음",
        "approval_required": "승인 필요",
        "unrestricted": "실험 무제한",
    }.get(str(policy.get("risk") or ""), str(policy.get("risk") or "-"))
    mutation_allowed = "예" if policy.get("mutationAllowed") else "아니오"
    return "\n".join(
        [
            f"정책 결정: {decision_label}",
            f"내부 결정값: {decision or '-'}",
            f"위험도: {risk_label}",
            f"변경 실행 허용: {mutation_allowed}",
            f"설명: {decision_explanation}",
        ]
    )


def policy_check_summary(policy: Mapping[str, Any]) -> str:
    if policy.get("decision") == "action_proposal_only":
        return "조치 요청은 Action Plan 경로로 처리"
    if policy.get("decision") == "allow_evidence_collection":
        return "조회 허용"
    return "정책 결정 확인 필요"


def summarize_subject_detail(subject: Mapping[str, Any], *, live_review: bool) -> str:
    return auth_runtime.summarize_subject_detail(subject, live_review=live_review)


def build_action_proposal_fallback(req: ChatRequest, policy: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "현재 요청은 변경/재시작/삭제/스케일/패치 계열 작업으로 분류되었습니다.",
            "",
            "### 조치 제안",
            f"- 요청: {redact_sensitive(req.message.strip()) or '미지정'}",
            "- 현재 단계: 승인 필요한 조치 계획 검토",
            "- 정책 결정: 승인 전 실행 차단",
            "- 실행 가능 범위: 자연어 요청을 승인 가능한 조치 계획으로 정리한 뒤, 승인된 실행 경로에서만 처리",
            "",
            "### 승인 필요 여부",
            "- 필요함. 실제 변경 작업은 운영자 승인 후 실행 기록을 남기는 경로에서만 허용됩니다.",
            "",
            "### 추가로 필요한 대상 정보",
            "- namespace",
            "- Pod 또는 관리 객체(Deployment/StatefulSet/DaemonSet 등) 이름",
            "- 원하는 작업이 단순 재시작인지, 장애 원인 분석 후 조치인지",
        ]
    )


from .pod_answering import (
    CRASHLOOPBACKOFF_FIRST_SENTENCE_RULE,
    CRASHLOOPBACKOFF_PLAIN_DEFINITION,
    INTERNAL_FALLBACK_DIAGNOSTIC_PATTERNS,
    app_label_from_labels,
    build_empty_answer_fallback,
    build_grounded_aiops_answer,
    build_image_answer_fallback,
    build_ols_required_failure_answer,
    build_pod_evidence_fallback,
    build_pod_list_fallback,
    build_pod_namespace_pattern_lookup_answer,
    choose_gateway_pod_row,
    command_suggests_immediate_exit,
    configure_pod_answering,
    deployment_from_owner_chain,
    is_internal_fallback_diagnostic,
    is_pod_namespace_pattern_lookup_request,
    kubernetes_name_terms,
    looks_non_production_context,
    message_mentions_crashloop,
    parse_gateway_current_pod_list_rows,
    parse_gateway_pod_evidence_rows,
    parse_markdown_table_cells,
    parse_restart_count,
    pod_inventory_action_candidate_from_row,
    pod_inventory_action_candidates_from_evidence,
    pod_inventory_check_commands,
    pod_inventory_message_requests_problem_scope,
    pod_inventory_message_requests_restart_history,
    pod_inventory_restart_observation_rows,
    pod_inventory_selected_rows,
    pod_namespace_lookup_pattern,
    pod_row_has_completed_restart_loop,
    pod_row_has_current_failure,
    pod_row_has_error_exit,
    pod_row_priority,
    pod_row_target,
    public_gateway_evidence_excerpt,
    ready_summary_is_full,
    score_gateway_pod_row,
)

configure_pod_answering(
    is_ambiguous_cleanup_review_request=lambda req: is_ambiguous_cleanup_review_request(req),
    is_pod_list_request=lambda message: is_pod_list_request(message),
    pod_list_namespace=lambda req: pod_list_namespace(req),
    crashloop_demo_target_from_request=lambda req: crashloop_demo_target_from_request(req),
    build_action_proposal_fallback=lambda req, policy: build_action_proposal_fallback(req, policy),
    active_llm_label=lambda: active_llm_label(),
    build_pod_namespace_pattern_lookup_answer=lambda req, gateway_evidence: build_pod_namespace_pattern_lookup_answer(
        req, gateway_evidence
    ),
    build_pod_list_fallback=lambda req, gateway_evidence: build_pod_list_fallback(
        req, gateway_evidence
    ),
    build_pod_evidence_fallback=lambda req, gateway_evidence: build_pod_evidence_fallback(
        req, gateway_evidence
    ),
    build_image_answer_fallback=lambda *args, **kwargs: build_image_answer_fallback(
        *args, **kwargs
    ),
)


def remember_pod_inventory_action_candidates(
    req: ChatRequest,
    gateway_evidence: str | None,
    *,
    incident_id: str,
    run_id: str,
) -> list[dict[str, Any]]:
    candidates = pod_inventory_action_candidates_from_evidence(
        req,
        gateway_evidence,
        incident_id=incident_id,
        run_id=run_id,
    )
    now = datetime.now(UTC)
    for key, candidate in list(NAMESPACE_CLEANUP_CHAT_CANDIDATES.items()):
        expires_at = parse_k8s_timestamp(candidate.get("expiresAt"))
        if expires_at and expires_at < now:
            NAMESPACE_CLEANUP_CHAT_CANDIDATES.pop(key, None)
    for candidate in candidates:
        NAMESPACE_CLEANUP_CHAT_CANDIDATES[str(candidate["id"])] = candidate
    return candidates


def truncate_unrestricted_output(value: bytes) -> tuple[str, bool]:
    truncated = len(value) > UNRESTRICTED_COMMAND_MAX_OUTPUT_BYTES
    if truncated:
        value = value[:UNRESTRICTED_COMMAND_MAX_OUTPUT_BYTES]
    text = value.decode("utf-8", errors="replace")
    return redact_sensitive(text), truncated


def unrestricted_command_timeout(requested_timeout: int | None) -> int:
    default_timeout = max(1, min(UNRESTRICTED_COMMAND_TIMEOUT_SECONDS, 3600))
    if requested_timeout is None:
        return default_timeout
    return max(1, min(int(requested_timeout), 3600))


def unrestricted_command_cwd(requested_cwd: str | None = None) -> str:
    cwd = requested_cwd or UNRESTRICTED_COMMAND_CWD or os.getcwd()
    return os.path.abspath(os.path.expanduser(cwd))


async def execute_unrestricted_command_request(
    req: UnrestrictedCommandExecuteCreate,
    subject: Mapping[str, Any],
    *,
    request_id: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    if not UNRESTRICTED_COMMANDS_ENABLED:
        raise HTTPException(status_code=403, detail="Experimental unrestricted command execution is disabled")

    command = req.command.strip()
    if not command:
        raise HTTPException(status_code=400, detail="Command is empty")

    cwd = unrestricted_command_cwd(req.cwd)
    if not os.path.isdir(cwd):
        raise HTTPException(status_code=400, detail=f"Command cwd does not exist: {cwd}")
    timeout_seconds = unrestricted_command_timeout(req.timeoutSeconds)
    started_at = time.monotonic()
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        executable="/bin/bash",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    timed_out = False
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError:
        timed_out = True
        proc.kill()
        stdout_bytes, stderr_bytes = await proc.communicate()

    duration_ms = int((time.monotonic() - started_at) * 1000)
    stdout_text, stdout_truncated = truncate_unrestricted_output(stdout_bytes)
    stderr_text, stderr_truncated = truncate_unrestricted_output(stderr_bytes)
    exit_code = proc.returncode if proc.returncode is not None else -1
    result = {
        "apiVersion": "aiops.komsco/v1",
        "kind": "UnrestrictedCommandExecution",
        "metadata": {
            "name": f"unrestricted-command-{uuid.uuid4().hex[:16]}",
            "createdAt": now_rfc3339(),
        },
        "spec": {
            "command": redact_sensitive(command),
            "cwd": cwd,
            "durationMs": duration_ms,
            "exitCode": exit_code,
            "requestId": request_id or "",
            "runId": run_id or "",
            "stderr": stderr_text,
            "stderrTruncated": stderr_truncated,
            "stdout": stdout_text,
            "stdoutTruncated": stdout_truncated,
            "subject": redact_sensitive(dict(subject)),
            "timedOut": timed_out,
            "timeoutSeconds": timeout_seconds,
            "warning": "Experimental dev-only unrestricted command execution ran with Gateway local process privileges.",
        },
    }
    log_audit_record(
        build_trace_record(
            action="unrestricted_command_executed",
            incident_id="dev-unrestricted",
            policy={
                "schemaVersion": "v1",
                "phase": "experimental-unrestricted-command",
                "decision": "executed",
                "mutationAllowed": True,
                "risk": "unrestricted",
                "reason": "User selected experimental unrestricted mode.",
            },
            request_id=request_id or f"req-{uuid.uuid4()}",
            run_id=run_id or f"run-{uuid.uuid4()}",
            subject=subject,
            target={
                "command": redact_sensitive(command),
                "cwd": cwd,
                "durationMs": duration_ms,
                "exitCode": exit_code,
                "timedOut": timed_out,
            },
        )
    )
    return result


def unrestricted_command_response(result: Mapping[str, Any]) -> str:
    spec = result.get("spec") if isinstance(result.get("spec"), Mapping) else {}
    stdout_text = str(spec.get("stdout") or "")
    stderr_text = str(spec.get("stderr") or "")
    lines = [
        "실험용 무제한 명령 실행 결과입니다.",
        "",
        f"- Command: `{spec.get('command') or ''}`",
        f"- CWD: `{spec.get('cwd') or ''}`",
        f"- Exit code: `{spec.get('exitCode')}`",
        f"- Duration: `{spec.get('durationMs')}ms`",
        f"- Timed out: `{spec.get('timedOut')}`",
        "",
        "### stdout",
        "```text",
        stdout_text or "(empty)",
        "```",
    ]
    if stderr_text:
        lines.extend(["", "### stderr", "```text", stderr_text, "```"])
    return "\n".join(lines)


def action_execution_config() -> ActionExecutionConfig:
    return ActionExecutionConfig(
        openshift_api_url=OPENSHIFT_API_URL,
        openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
        action_executor_token_file=ACTION_EXECUTOR_TOKEN_FILE,
        action_executor_field_manager=ACTION_EXECUTOR_FIELD_MANAGER,
        action_executor_url=ACTION_EXECUTOR_URL,
        action_executor_shared_token=ACTION_EXECUTOR_SHARED_TOKEN,
        test_pod_create_enabled=TEST_POD_CREATE_ENABLED,
        test_pod_create_default_image=TEST_POD_CREATE_DEFAULT_IMAGE,
        test_pod_create_name_prefix=TEST_POD_CREATE_NAME_PREFIX,
        test_pod_create_app_label=TEST_POD_CREATE_APP_LABEL,
        test_pod_create_allowed_namespaces=frozenset(str(item) for item in TEST_POD_CREATE_ALLOWED_NAMESPACES),
        test_pod_create_failure_command=tuple(TEST_POD_CREATE_FAILURE_COMMAND),
    )


def append_query(path: str, query: Mapping[str, str]) -> str:
    return action_execution_append_query(path, query)


def executor_auth_header() -> str:
    return action_execution_executor_auth_header(action_execution_config())


def natural_action_executor_fallback_authorization() -> str:
    try:
        return executor_auth_header()
    except HTTPException:
        return "Bearer token"


async def _fetch_ocp_json_for_action_execution(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    required: bool = False,
    config: ActionExecutionConfig | None = None,
) -> dict[str, Any] | None:
    _ = config
    return await fetch_ocp_json(client, path, authorization, required=required)


async def fetch_executor_live_state(
    client: httpx.AsyncClient,
    authorization: str,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    return await action_execution_fetch_executor_live_state(
        client,
        authorization,
        plan,
        config=action_execution_config(),
        fetch_ocp_json_func=_fetch_ocp_json_for_action_execution,
    )


async def submit_ocp_request(
    client: httpx.AsyncClient,
    authorization: str,
    *,
    method: str,
    path: str,
    content_type: str,
    body: Mapping[str, Any],
) -> httpx.Response:
    return await action_execution_submit_ocp_request(
        client,
        authorization,
        method=method,
        path=path,
        content_type=content_type,
        body=body,
        config=action_execution_config(),
    )


async def verify_typed_action_postcondition(
    client: httpx.AsyncClient,
    authorization: str,
    sealed_plan: Mapping[str, Any],
) -> dict[str, Any]:
    return await action_execution_verify_typed_action_postcondition(
        client,
        authorization,
        sealed_plan,
        config=action_execution_config(),
        fetch_ocp_json_func=_fetch_ocp_json_for_action_execution,
    )


def namespace_cleanup_review_execution_result(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    return action_execution_namespace_cleanup_review_execution_result(sealed_plan)


def test_pod_create_review_execution_result(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    return action_execution_test_pod_create_review_execution_result(sealed_plan)


def crashloop_test_pod_name(prefix: str, request_id: str, index: int) -> str:
    return build_crashloop_test_pod_name(prefix, request_id, index)


def crashloop_test_pod_manifest(
    *,
    image: str,
    index: int,
    namespace: str,
    pod_name: str,
    request_id: str,
) -> dict[str, Any]:
    return build_crashloop_test_pod_manifest(
        image=image,
        index=index,
        namespace=namespace,
        pod_name=pod_name,
        request_id=request_id,
        settings=test_pod_create_settings(),
    )


async def create_crashloop_test_pods_execution_result(
    sealed_plan: Mapping[str, Any],
    client: httpx.AsyncClient,
    authorization: str,
) -> dict[str, Any]:
    return await action_execution_create_crashloop_test_pods_execution_result(
        sealed_plan,
        client,
        authorization,
        config=action_execution_config(),
        submit_ocp_request_func=submit_ocp_request,
        fetch_ocp_json_func=_fetch_ocp_json_for_action_execution,
    )


def pod_diagnostic_review_execution_result(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    return action_execution_pod_diagnostic_review_execution_result(sealed_plan)


def pod_fix_or_rollback_review_execution_result(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    return action_execution_pod_fix_or_rollback_review_execution_result(sealed_plan)


REVIEW_ONLY_ACTION_TOOLS = {
    "namespace_cleanup_review",
    "test_pod_create_review",
    "pod_diagnostic_review",
    "pod_fix_or_rollback_review",
}


def sealed_plan_is_review_only(sealed_plan: Mapping[str, Any]) -> bool:
    action = sealed_plan.get("action") if isinstance(sealed_plan.get("action"), Mapping) else {}
    tool_name = str(action.get("toolName") or "")
    normalized_parameters = (
        action.get("normalizedParameters")
        if isinstance(action.get("normalizedParameters"), Mapping)
        else {}
    )
    return tool_name in REVIEW_ONLY_ACTION_TOOLS or bool(normalized_parameters.get("reviewOnly"))


async def execute_typed_action_plan(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    return await action_execution_execute_typed_action_plan(
        sealed_plan,
        config=action_execution_config(),
        fetch_ocp_json_func=_fetch_ocp_json_for_action_execution,
        submit_ocp_request_func=submit_ocp_request,
    )


async def execute_action_with_executor(
    sealed_plan: Mapping[str, Any],
    grant_reference: Mapping[str, Any],
    *,
    fallback_authorization: str | None = None,
) -> dict[str, Any]:
    return await action_execution_execute_action_with_executor(
        sealed_plan,
        grant_reference,
        config=action_execution_config(),
        fallback_authorization=fallback_authorization,
        fetch_ocp_json_func=_fetch_ocp_json_for_action_execution,
        submit_ocp_request_func=submit_ocp_request,
    )


def aiops_read_dependencies() -> AiopsReadDependencies:
    return AiopsReadDependencies(
        config=AiopsReadConfig(
            openshift_api_url=OPENSHIFT_API_URL,
            openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
            mutations_enabled=MUTATIONS_ENABLED,
            diagnostics_enabled=DIAGNOSTICS_ENABLED,
            diagnostics_controller_url=HOST_DIAGNOSTICS_CONTROLLER_URL,
            action_executor_url=ACTION_EXECUTOR_URL,
            unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
            record_store_enabled=RECORD_STORE_ENABLED,
            record_store_configmap=RECORD_STORE_CONFIGMAP,
            chat_transcript_jsonl_path=CHAT_TRANSCRIPT_JSONL_PATH,
            latest_runtime_tool_plan=LAST_RUNTIME_TOOL_PLAN,
            latest_rca_context=LAST_RCA_CONTEXT,
        ),
        stores=AiopsRecordStores(
            chat_transcripts=CHAT_TRANSCRIPTS,
            chat_feedback=CHAT_FEEDBACK,
            diagnostic_requests=DIAGNOSTIC_REQUESTS,
            action_proposals=ACTION_PROPOSALS,
            sealed_action_plans=SEALED_ACTION_PLANS,
            approval_decisions=APPROVAL_DECISIONS,
            execution_records=EXECUTION_RECORDS,
        ),
        lightspeed_status=OLS_STREAM_STATUS,
        verify_bearer_header=verify_bearer_header,
        fetch_ocp_json=fetch_ocp_json,
        fetch_ocp_json_observed=fetch_ocp_json_observed,
        build_cluster_summary=build_cluster_summary,
        monitoring_urls_from_config=monitoring_urls_from_config,
        probe_thanos_query=probe_thanos_query,
        query_thanos_instant=query_thanos_instant,
        data_source_status=data_source_status,
        build_aiops_anomaly_summary=build_aiops_anomaly_summary,
        build_aiops_overview=build_aiops_overview,
        aiops_overview=aiops_overview,
        merge_recent_namespace_cleanup_candidates=merge_recent_namespace_cleanup_candidates,
        fetch_self_subject_review=fetch_self_subject_review,
        fetch_product_access_review=fetch_product_access_review,
        build_kubernetes_event_items=build_kubernetes_event_items,
        build_problem_pod_event_items=build_problem_pod_event_items,
        build_aiops_record_event_items=build_aiops_record_event_items,
        now_rfc3339=now_rfc3339,
        safe_subject=safe_subject,
        build_skipped_product_access_review=build_skipped_product_access_review,
        build_status_access_review_failure=build_status_access_review_failure,
        redact_sensitive=redact_sensitive,
        build_rag_backend_status=build_rag_backend_status,
        build_runtime_safety_contract=build_runtime_safety_contract,
        latest_readable_audit_records=latest_readable_audit_records,
        latest_readable_records=latest_readable_records,
    )


async def cluster_summary(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await aiops_read_service.cluster_summary(authorization, aiops_read_dependencies())


async def aiops_overview(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await aiops_read_service.aiops_overview(authorization, aiops_read_dependencies())


async def aiops_anomalies(
    authorization: str | None = Header(default=None),
    namespace: str | None = Query(default=None),
    since_minutes: int = Query(default=60, alias="sinceMinutes", ge=1, le=1440),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return await aiops_read_service.aiops_anomalies(
        authorization, namespace, since_minutes, limit, aiops_read_dependencies(),
    )


async def aiops_action_candidates(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await aiops_read_service.aiops_action_candidates(
        authorization, aiops_read_dependencies(),
    )


app.include_router(create_aiops_read_router(aiops_read_dependencies))


async def auth_subject(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await evidence_service.auth_subject(authorization, evidence_dependencies())


async def list_evidence(
    authorization: str | None = Header(default=None),
    incident_id: str | None = Query(default=None, alias="incidentId"),
    run_id: str | None = Query(default=None, alias="runId"),
) -> dict[str, Any]:
    return await evidence_service.list_evidence(
        authorization, incident_id, run_id, evidence_dependencies(),
    )


async def get_evidence(
    evidence_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await evidence_service.get_evidence(
        evidence_id, authorization, evidence_dependencies(),
    )


async def get_workflow(
    run_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await evidence_service.get_workflow(
        run_id, authorization, evidence_dependencies(),
    )


async def get_diagnostic_collectors(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return diagnostics_service.get_diagnostic_collectors(
        authorization, diagnostics_dependencies(),
    )


async def create_diagnostic_request(
    req: DiagnosticRequestCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await diagnostics_service.create_diagnostic_request(
        req, authorization, diagnostics_dependencies(),
    )


async def get_diagnostic_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await diagnostics_service.get_diagnostic_request(
        request_id, authorization, diagnostics_dependencies(),
    )


app.include_router(create_evidence_router(evidence_dependencies))
app.include_router(create_diagnostics_router(diagnostics_dependencies))


def latest_readable_records(
    store: Mapping[str, dict[str, Any]],
    subject: Mapping[str, Any],
    *,
    product_access_allowed: bool = False,
    limit: int = 8,
) -> list[dict[str, Any]]:
    records = [
        record
        for record in store.values()
        if product_access_allowed or can_subject_read_record(record, subject)
    ]
    records.sort(
        key=lambda record: str(record.get("metadata", {}).get("createdAt") or ""),
        reverse=True,
    )
    return [
        {
            "metadata": record.get("metadata", {}),
            "kind": record.get("kind"),
            "spec": record.get("spec", {}),
        }
        for record in records[:limit]
    ]


def latest_readable_audit_records(
    subject: Mapping[str, Any],
    *,
    product_access_allowed: bool = False,
    limit: int = 12,
) -> list[dict[str, Any]]:
    records = [
        record
        for record in AUDIT_RECORDS.values()
        if product_access_allowed or can_subject_read_record(record, subject)
    ]
    records.sort(key=lambda record: str(record.get("timestamp") or ""), reverse=True)
    return [
        {
            "kind": "AuditRecord",
            "metadata": {
                "createdAt": record.get("timestamp"),
                "name": record.get("auditId"),
            },
            "spec": {
                "action": record.get("action"),
                "incidentId": record.get("incidentId"),
                "policy": record.get("policy", {}),
                "requestId": record.get("requestId"),
                "runId": record.get("runId"),
                "target": record.get("target", {}),
            },
        }
        for record in records[:limit]
    ]





def build_status_access_review_failure(exc: HTTPException) -> dict[str, Any]:
    return auth_runtime.build_status_access_review_failure(auth_runtime_callbacks(), exc)


def build_skipped_product_access_review(reason: str) -> dict[str, Any]:
    return auth_runtime.build_skipped_product_access_review(auth_runtime_config(), reason)


def record_target_label(record: Mapping[str, Any]) -> str:
    spec = record.get("spec", {}) if isinstance(record.get("spec"), Mapping) else {}
    target = spec.get("target")
    if not isinstance(target, Mapping):
        return "-"
    namespace = str(target.get("namespace") or "")
    kind = str(target.get("kind") or target.get("resource") or "")
    name = str(target.get("name") or "")
    label = "/".join(part for part in (kind, name) if part)
    if namespace and label:
        return f"{namespace}/{label}"
    return label or "-"


def record_event_phase(record: Mapping[str, Any]) -> str:
    spec = record.get("spec", {}) if isinstance(record.get("spec"), Mapping) else {}
    status = spec.get("status")
    if isinstance(status, Mapping):
        phase = status.get("phase")
        if phase:
            return str(phase)

    mutation_outcome = spec.get("mutationOutcome")
    if isinstance(mutation_outcome, Mapping) and mutation_outcome.get("status"):
        return str(mutation_outcome["status"])

    policy = spec.get("policy")
    if isinstance(policy, Mapping) and policy.get("decision"):
        return str(policy["decision"])

    action = spec.get("action")
    if action:
        return str(action)

    return "recorded"


def record_event_severity(record: Mapping[str, Any]) -> str:
    phase = record_event_phase(record).lower()
    if any(token in phase for token in ("failed", "denied", "rejected", "error")):
        return "risk"
    if any(token in phase for token in ("pending", "proposed", "requested", "succeeded")):
        return "warn" if any(token in phase for token in ("pending", "proposed", "requested")) else "ok"
    return "ok"


def build_aiops_record_event_items(
    subject: Mapping[str, Any],
    *,
    product_access_allowed: bool = False,
    limit: int = 30,
) -> list[dict[str, Any]]:
    records = [
        *latest_readable_audit_records(subject, product_access_allowed=product_access_allowed, limit=limit),
        *latest_readable_records(DIAGNOSTIC_REQUESTS, subject, product_access_allowed=product_access_allowed, limit=limit),
        *latest_readable_records(ACTION_PROPOSALS, subject, product_access_allowed=product_access_allowed, limit=limit),
        *latest_readable_records(SEALED_ACTION_PLANS, subject, product_access_allowed=product_access_allowed, limit=limit),
        *latest_readable_records(APPROVAL_DECISIONS, subject, product_access_allowed=product_access_allowed, limit=limit),
        *latest_readable_records(EXECUTION_RECORDS, subject, product_access_allowed=product_access_allowed, limit=limit),
    ]

    items: list[dict[str, Any]] = []
    for record in records:
        metadata = record.get("metadata", {}) if isinstance(record.get("metadata"), Mapping) else {}
        spec = record.get("spec", {}) if isinstance(record.get("spec"), Mapping) else {}
        kind = str(record.get("kind") or "AIOpsRecord")
        name = str(metadata.get("name") or kind)
        created_at = str(metadata.get("createdAt") or now_rfc3339())
        phase = record_event_phase(record)
        target = record_target_label(record)
        detail = f"{kind} · phase={phase}"
        if target != "-":
            detail = f"{detail} · target={target}"
        items.append(
            {
                "category": "record",
                "detail": compact_event_detail(detail),
                "id": f"aiops-record-{kind}-{name}-{created_at}",
                "namespace": "",
                "severity": record_event_severity(record),
                "source": "AIOps Gateway",
                "target": target,
                "time": created_at,
                "title": name if kind != "AuditRecord" else str(spec.get("action") or phase),
            }
        )

    items.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return items[:limit]


async def get_aiops_events(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    return await aiops_read_service.get_aiops_events(
        authorization, limit, aiops_read_dependencies(),
    )


async def get_aiops_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await aiops_read_service.get_aiops_status(
        authorization, aiops_read_dependencies(),
    )


def action_api_dependencies() -> ActionApiDependencies:
    return ActionApiDependencies(
        config=ActionApiConfig(
            mutations_enabled=MUTATIONS_ENABLED,
            unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
            approval_access_review_required=APPROVAL_ACCESS_REVIEW_REQUIRED,
            registry_version=ACTION_REGISTRY_VERSION,
            registry_digest=ACTION_REGISTRY_DIGEST,
            registry_entries=ACTION_REGISTRY_ENTRIES,
            auto_execute_tool_names=frozenset(AUTO_EXECUTE_TOOL_NAMES),
            auto_execute_evict_eligible_source_types=frozenset(
                AUTO_EXECUTE_EVICT_ELIGIBLE_SOURCE_TYPES
            ),
        ),
        stores=ActionApiStores(
            action_proposals=ACTION_PROPOSALS,
            sealed_action_plans=SEALED_ACTION_PLANS,
            approval_decisions=APPROVAL_DECISIONS,
            execution_records=EXECUTION_RECORDS,
            auto_execute_target_locks=_AUTO_EXECUTE_TARGET_LOCKS,
        ),
        verify_bearer_header=verify_bearer_header,
        fetch_self_subject_review=fetch_self_subject_review,
        fetch_product_access_review=fetch_product_access_review,
        fetch_action_access_review=fetch_action_access_review,
        enforce_product_access_review=enforce_product_access_review,
        enforce_action_access_review=enforce_action_access_review,
        can_subject_read_record=can_subject_read_record,
        build_action_proposal_record=build_action_proposal_record,
        build_sealed_action_plan_record=build_sealed_action_plan_record,
        build_approval_decision_record=build_approval_decision_record,
        build_action_rejection_record=build_action_rejection_record,
        build_execution_grant_reference=build_execution_grant_reference,
        create_plan_from_action_candidate=create_plan_from_action_candidate,
        bounded_put_record=bounded_put_record,
        increment_metric=increment_metric,
        maybe_auto_approve_and_execute=maybe_auto_approve_and_execute,
        plan_has_approval_status=plan_has_approval_status,
        find_approval_by_plan_status=find_approval_by_plan_status,
        record_created_at=record_created_at,
        validate_approval_is_active=validate_approval_is_active,
        approval_already_executed=approval_already_executed,
        validate_execution_evidence_freshness=validate_execution_evidence_freshness,
        execute_action_with_executor=execute_action_with_executor,
        sealed_plan_is_review_only=sealed_plan_is_review_only,
        now_rfc3339=now_rfc3339,
        redact_sensitive=redact_sensitive,
        aiops_action_candidates=aiops_action_candidates,
    )


app.include_router(create_action_router(action_api_dependencies))


async def get_action_registry(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return action_api_service.get_action_registry(authorization, action_api_dependencies())


async def create_action_proposal(
    req: ActionProposalCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await action_api_service.create_action_proposal(req, authorization, action_api_dependencies())


async def create_action_candidate_plan(
    req: ActionCandidatePlanCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await action_api_service.create_action_candidate_plan(req, authorization, action_api_dependencies())


async def get_action_proposal(
    proposal_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await action_api_service.get_action_proposal(proposal_id, authorization, action_api_dependencies())


async def create_action_plan(
    req: SealedActionPlanCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await action_api_service.create_action_plan(req, authorization, action_api_dependencies())


async def get_action_plan(
    plan_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await action_api_service.get_action_plan(plan_id, authorization, action_api_dependencies())


async def _create_approval_decision_impl(
    req: "ApprovalDecisionCreate",
    user_auth_header: str,
    *,
    auto_policy: bool = False,
) -> dict[str, Any]:
    return await action_api_service.create_approval_decision_impl(
        req, user_auth_header, action_api_dependencies(), auto_policy=auto_policy,
    )


async def create_approval_decision(
    req: ApprovalDecisionCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await action_api_service.create_approval_decision(req, authorization, action_api_dependencies())


async def reject_action_plan(
    req: ActionRejectionCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await action_api_service.reject_action_plan(req, authorization, action_api_dependencies())


async def _execute_action_impl(
    req: "ActionExecutionCreate",
    user_auth_header: str,
    *,
    auto_policy: bool = False,
) -> dict[str, Any]:
    return await action_api_service.execute_action_impl(
        req, user_auth_header, action_api_dependencies(), auto_policy=auto_policy,
    )


async def execute_action(
    req: ActionExecutionCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await action_api_service.execute_action(req, authorization, action_api_dependencies())


def has_recent_auto_action_for_target(
    target: Mapping[str, Any],
    tool_name: str,
    *,
    window_seconds: int = 180,
) -> bool:
    return action_api_service.has_recent_auto_action_for_target(
        target, tool_name, action_api_dependencies(), window_seconds=window_seconds,
    )


async def verify_source_type_for_target(
    user_auth_header: str, target: Mapping[str, Any]
) -> str | None:
    return await action_api_service.verify_source_type_for_target(
        user_auth_header, target, action_api_dependencies(),
    )


async def maybe_auto_approve_and_execute(
    plan_record: Mapping[str, Any],
    user_auth_header: str,
) -> dict[str, Any] | None:
    return await action_api_service.maybe_auto_approve_and_execute(
        plan_record, user_auth_header, action_api_dependencies(),
    )


def knowledge_dependencies() -> KnowledgeDependencies:
    return KnowledgeDependencies(
        config=KnowledgeConfig(
            runbook_registry_version=RUNBOOK_REGISTRY_VERSION,
            runbook_registry_digest=RUNBOOK_REGISTRY_DIGEST,
            runbook_registry_entries=RUNBOOK_REGISTRY_ENTRIES,
            preapproved_patch_field_digest=PREAPPROVED_PATCH_FIELD_DIGEST,
            preapproved_patch_field_schemas=PREAPPROVED_PATCH_FIELD_SCHEMAS,
            break_glass_profile_version=BREAK_GLASS_PROFILE_VERSION,
            break_glass_profile_digest=BREAK_GLASS_PROFILE_DIGEST,
            break_glass_profiles=BREAK_GLASS_PROFILES,
            break_glass_enabled=BREAK_GLASS_ENABLED,
            latest_runtime_tool_plan=LAST_RUNTIME_TOOL_PLAN,
            latest_rca_context=LAST_RCA_CONTEXT,
        ),
        stores=KnowledgeStores(
            runbook_plans=RUNBOOK_PLANS,
            preapproved_patch_requests=PREAPPROVED_PATCH_REQUESTS,
            break_glass_requests=BREAK_GLASS_REQUESTS,
        ),
        verify_bearer_header=verify_bearer_header,
        fetch_self_subject_review=fetch_self_subject_review,
        can_subject_read_record=can_subject_read_record,
        now_rfc3339=now_rfc3339,
        list_rag_upload_documents=list_pgvector_upload_documents,
        build_rag_backend_status=build_rag_backend_status,
        persist_rag_upload_document=persist_rag_upload_document,
        extract_rag_upload_file_content=extract_rag_upload_file_content,
        parse_rag_upload_form_labels=parse_rag_upload_form_labels,
        search_rag_runbooks=search_pgvector_runbooks,
        increment_metric=increment_metric,
        build_runbook_plan_record=build_runbook_plan_record,
        build_preapproved_patch_record=build_preapproved_patch_record,
        build_break_glass_request_record=build_break_glass_request_record,
        bounded_put_record=bounded_put_record,
        log_break_glass_audit_record=log_break_glass_audit_record,
        build_trace_record=build_trace_record,
    )


app.include_router(create_knowledge_router(knowledge_dependencies))


@app.post("/v1/dev/commands/execute")
async def execute_unrestricted_command(
    req: UnrestrictedCommandExecuteCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    return await execute_unrestricted_command_request(req, subject)


async def get_runbook_registry(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return knowledge_service.get_runbook_registry(authorization, knowledge_dependencies())


async def list_rag_uploads(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return await knowledge_service.list_rag_uploads(authorization, knowledge_dependencies())


async def create_rag_upload(
    req: RagDocumentUploadCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await knowledge_service.create_rag_upload(req, authorization, knowledge_dependencies())


async def create_rag_upload_file(
    file: UploadFile = File(...),
    authorization: str | None = Header(default=None),
    labels: str = Form(default="{}"),
    customer: str = Form(default="komsco"),
    namespace: str = Form(default="komsco-ai-kugnus"),
    run_id: str | None = Form(default=None),
    source_type: str = Form(default="user-upload"),
    source_uri: str | None = Form(default=None),
    version: str = Form(default="v0.1.5"),
) -> dict[str, Any]:
    return await knowledge_service.create_rag_upload_file(
        file,
        authorization,
        labels,
        customer,
        namespace,
        run_id,
        source_type,
        source_uri,
        version,
        knowledge_dependencies(),
    )


async def search_rag_runbooks(
    req: RagSearchCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await knowledge_service.search_rag_runbooks(req, authorization, knowledge_dependencies())


async def create_runbook_plan(
    req: RunbookPlanCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await knowledge_service.create_runbook_plan(req, authorization, knowledge_dependencies())


async def get_runbook_plan(
    plan_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await knowledge_service.get_runbook_plan(plan_id, authorization, knowledge_dependencies())


async def create_preapproved_patch_request(
    req: PatchPreapprovedFieldCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await knowledge_service.create_preapproved_patch_request(
        req, authorization, knowledge_dependencies(),
    )


async def get_preapproved_patch_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await knowledge_service.get_preapproved_patch_request(
        request_id, authorization, knowledge_dependencies(),
    )


async def get_break_glass_profiles(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    return knowledge_service.get_break_glass_profiles(authorization, knowledge_dependencies())


async def create_break_glass_request(
    req: BreakGlassRequestCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await knowledge_service.create_break_glass_request(
        req, authorization, knowledge_dependencies(),
    )


async def get_break_glass_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    return await knowledge_service.get_break_glass_request(
        request_id, authorization, knowledge_dependencies(),
    )


async def get_last_rca_context(authorization: str = Header(default="")) -> dict[str, Any]:
    return knowledge_service.get_last_rca_context(authorization, knowledge_dependencies())


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> str:
    lines = []
    for name in sorted(METRICS):
        lines.append(f"# TYPE {name} counter")
        lines.append(f"{name} {METRICS[name]}")
    lines.append("# TYPE aiops_audit_records gauge")
    lines.append(f"aiops_audit_records {len(AUDIT_RECORDS)}")
    lines.append("# TYPE aiops_evidence_records gauge")
    lines.append(f"aiops_evidence_records {len(EVIDENCE_RECORDS)}")
    lines.append("# TYPE aiops_workflow_records gauge")
    lines.append(f"aiops_workflow_records {len(WORKFLOW_RECORDS)}")
    lines.append("# TYPE aiops_chat_transcript_records gauge")
    lines.append(f"aiops_chat_transcript_records {len(CHAT_TRANSCRIPTS)}")
    lines.append("# TYPE aiops_chat_feedback_records gauge")
    lines.append(f"aiops_chat_feedback_records {len(CHAT_FEEDBACK)}")
    lines.append("# TYPE aiops_diagnostic_request_records gauge")
    lines.append(f"aiops_diagnostic_request_records {len(DIAGNOSTIC_REQUESTS)}")
    lines.append("# TYPE aiops_action_proposal_records gauge")
    lines.append(f"aiops_action_proposal_records {len(ACTION_PROPOSALS)}")
    lines.append("# TYPE aiops_sealed_action_plan_records gauge")
    lines.append(f"aiops_sealed_action_plan_records {len(SEALED_ACTION_PLANS)}")
    lines.append("# TYPE aiops_approval_decision_records gauge")
    lines.append(f"aiops_approval_decision_records {len(APPROVAL_DECISIONS)}")
    lines.append("# TYPE aiops_execution_records gauge")
    lines.append(f"aiops_execution_records {len(EXECUTION_RECORDS)}")
    lines.append("# TYPE aiops_runbook_plan_records gauge")
    lines.append(f"aiops_runbook_plan_records {len(RUNBOOK_PLANS)}")
    lines.append("# TYPE aiops_preapproved_patch_request_records gauge")
    lines.append(f"aiops_preapproved_patch_request_records {len(PREAPPROVED_PATCH_REQUESTS)}")
    lines.append("# TYPE aiops_break_glass_request_records gauge")
    lines.append(f"aiops_break_glass_request_records {len(BREAK_GLASS_REQUESTS)}")
    return "\n".join(lines) + "\n"


@app.post("/v1/chat/feedback")
async def create_chat_feedback(
    req: ChatFeedbackCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    try:
        feedback_id, record, response = build_chat_feedback_record(req, subject)
    except ChatFeedbackInputError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await bounded_put_record("chatFeedback", feedback_id, record)
    increment_metric("aiops_chat_feedback_total")
    return response


class _MainChatLatestStatePort:
    def set_runtime_tool_plan(self, value: dict[str, Any] | None) -> None:
        global LAST_RUNTIME_TOOL_PLAN
        LAST_RUNTIME_TOOL_PLAN = value

    def set_rca_context(self, value: dict[str, Any] | None) -> None:
        global LAST_RCA_CONTEXT
        LAST_RCA_CONTEXT = value


def _chat_orchestrator_dependencies() -> ChatOrchestratorDependencies:
    latest_state: ChatLatestStatePort = _MainChatLatestStatePort()
    return ChatOrchestratorDependencies(
        runtime_bindings=dict(globals()),
        latest_state=latest_state,
    )


@app.post("/v1/chat/stream")
async def chat_stream(
    req: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    orchestrator = ChatOrchestrator(_chat_orchestrator_dependencies())
    return StreamingResponse(
        orchestrator.stream(req, authorization),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
