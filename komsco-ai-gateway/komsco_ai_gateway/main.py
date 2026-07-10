import asyncio
import base64
import binascii
import hashlib
import json
import mimetypes
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
    last_termination_summary,
    markdown_table_cell,
    pod_label_summary,
    pod_owner_chain_summary,
    pod_owner_summary,
    pod_ready_summary,
    rca_probe_event_status,
    replicaset_owner_index,
    requested_minute_interval,
    safe_env_value,
    schedule_interval_summary,
    state_summary,
)
from . import cluster_evidence_runtime
from . import action_candidate_plans
from . import namespace_cleanup as namespace_cleanup_runtime
from . import natural_action_orchestration
from . import natural_action_parsing
from . import natural_action_rendering
from .cluster_evidence_runtime import (
    ClusterEvidenceRuntimeCallbacks,
    ClusterEvidenceRuntimeConfig,
)
from .cluster_summary import build_cluster_summary as build_cluster_summary_read_model
from .chat_feedback import ChatFeedbackInputError, build_chat_feedback_record
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
    pod_count_investigation_response,
    pod_display_state,
    pod_is_fully_ready,
    pod_is_terminating,
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
MAX_IMAGE_ATTACHMENTS = 4
MAX_IMAGE_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_ATTACHMENT_TOTAL_BYTES = 6 * 1024 * 1024
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
def current_namespace() -> str:
    if RECORD_STORE_NAMESPACE:
        return RECORD_STORE_NAMESPACE
    try:
        return open(SERVICEACCOUNT_NAMESPACE_FILE, encoding="utf-8").read().strip() or "default"
    except OSError:
        return "default"


def record_store_auth_header() -> str:
    try:
        token = open(RECORD_STORE_TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="record store token is unavailable") from exc
    return f"Bearer {token}"


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


def record_store_path(namespace: str) -> str:
    return f"/api/v1/namespaces/{namespace}/configmaps/{RECORD_STORE_CONFIGMAP}"


async def record_store_request(
    method: str,
    path: str,
    *,
    body: Mapping[str, Any] | None = None,
    content_type: str = "application/json",
) -> httpx.Response:
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")
    headers = {
        "Accept": "application/json",
        "Authorization": record_store_auth_header(),
    }
    if body is not None:
        headers["Content-Type"] = content_type
    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        return await client.request(method, f"{OPENSHIFT_API_URL}{path}", headers=headers, json=body)


async def load_record_store() -> None:
    if not RECORD_STORE_ENABLED:
        return
    namespace = current_namespace()
    try:
        response = await record_store_request("GET", record_store_path(namespace))
        if response.status_code == 404:
            increment_metric("aiops_record_store_loads_total")
            return
        if response.status_code >= 400:
            increment_metric("aiops_record_store_failures_total")
            return
        payload = response.json()
        data = payload.get("data") if isinstance(payload, Mapping) else {}
        if not isinstance(data, Mapping):
            return
        for _store_name, (store, limit, key) in RECORD_STORES.items():
            raw = data.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            loaded = json.loads(raw)
            if not isinstance(loaded, Mapping):
                continue
            store.clear()
            for record_key, record in list(loaded.items())[-limit:]:
                if isinstance(record_key, str) and isinstance(record, Mapping):
                    store[record_key] = dict(record)
        increment_metric("aiops_record_store_loads_total")
    except Exception:
        increment_metric("aiops_record_store_failures_total")


async def persist_record_store(store_name: str) -> None:
    if not RECORD_STORE_ENABLED:
        return
    definition = RECORD_STORES.get(store_name)
    if not definition:
        return
    store, _limit, key = definition
    namespace = current_namespace()
    data_value = json.dumps(redact_sensitive(store), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    patch_body = {"data": {key: data_value}}
    try:
        response = await record_store_request(
            "PATCH",
            record_store_path(namespace),
            body=patch_body,
            content_type="application/merge-patch+json",
        )
        if response.status_code == 404:
            create_body = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": RECORD_STORE_CONFIGMAP,
                    "namespace": namespace,
                    "labels": {"app": "komsco-ai-gateway", "aiops.komsco/store": "ledger"},
                },
                "data": {key: data_value},
            }
            response = await record_store_request(
                "POST",
                f"/api/v1/namespaces/{namespace}/configmaps",
                body=create_body,
            )
        if response.status_code >= 400:
            increment_metric("aiops_record_store_failures_total")
            return
        increment_metric("aiops_record_store_writes_total")
    except Exception:
        increment_metric("aiops_record_store_failures_total")


async def bounded_put_record(
    store_name: str,
    key: str,
    value: dict[str, Any],
) -> None:
    store, limit, _data_key = RECORD_STORES[store_name]
    bounded_put(store, key, value, limit)
    await persist_record_store(store_name)


def enforce_rate_limit(user_auth_header: str) -> None:
    if RATE_LIMIT_PER_MINUTE <= 0:
        return

    now = time.monotonic()
    bucket_key = canonical_digest(user_auth_header)
    bucket = [item for item in RATE_LIMIT_BUCKETS.get(bucket_key, []) if now - item < 60.0]
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        increment_metric("aiops_rate_limited_total")
        raise HTTPException(status_code=429, detail="KOMSCO AI request rate limit exceeded")

    bucket.append(now)
    RATE_LIMIT_BUCKETS[bucket_key] = bucket


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
    existing = WORKFLOW_RECORDS.get(run_id, {})
    record = {
        "schemaVersion": "v1",
        "createdAt": existing.get("createdAt") or now_rfc3339(),
        "incidentId": incident_id,
        "lastUpdatedAt": now_rfc3339(),
        "policy": redact_sensitive(dict(policy)),
        "requestId": request_id,
        "runId": run_id,
        "stage": stage,
        "status": status,
        "subject": redact_sensitive(dict(subject or safe_subject(None))),
        "target": redact_sensitive(dict(target or existing.get("target") or {})),
    }
    bounded_put(WORKFLOW_RECORDS, run_id, record, WORKFLOW_MAX_RECORDS)


def truncate_chat_text(value: Any, limit: int) -> str:
    text = redact_sensitive(str(value or ""))
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}\n[TRUNCATED {len(text) - limit} chars]"


def chat_action_record_refs(incident_id: str, run_id: str) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for store_name, store in (
        ("actionProposals", ACTION_PROPOSALS),
        ("sealedActionPlans", SEALED_ACTION_PLANS),
        ("approvalDecisions", APPROVAL_DECISIONS),
        ("executionRecords", EXECUTION_RECORDS),
    ):
        for record in store.values():
            spec = record.get("spec") if isinstance(record.get("spec"), Mapping) else {}
            if not isinstance(spec, Mapping):
                continue
            if str(spec.get("runId") or "") != run_id and str(spec.get("incidentId") or "") != incident_id:
                continue
            refs.append(
                {
                    "kind": record.get("kind"),
                    "name": record.get("metadata", {}).get("name") if isinstance(record.get("metadata"), Mapping) else "",
                    "store": store_name,
                    "createdAt": record.get("metadata", {}).get("createdAt") if isinstance(record.get("metadata"), Mapping) else "",
                    "phase": spec.get("status", {}).get("phase") if isinstance(spec.get("status"), Mapping) else "",
                }
            )
    refs.sort(key=lambda item: str(item.get("createdAt") or ""))
    return refs


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
    created_at = now_rfc3339()
    context = rca_context if isinstance(rca_context, Mapping) else {}
    context_metadata = context.get("metadata") if isinstance(context.get("metadata"), Mapping) else {}
    evidence = context.get("evidence") if isinstance(context.get("evidence"), Mapping) else {}
    rca_result = context.get("rcaResult") if isinstance(context.get("rcaResult"), Mapping) else {}
    tool_plan_digest = (
        str(context_metadata.get("toolPlanDigest") or "")
        if context_metadata.get("toolPlanDigest")
        else canonical_digest(runtime_tool_plan)
        if isinstance(runtime_tool_plan, Mapping)
        else ""
    )
    rca_context_digest = str(context_metadata.get("digest") or "")
    answer_mode = (
        "action_plan"
        if "aiops-action-v0.1.9" in answer_contracts
        or "natural-action-plan-v0.2.1" in answer_contracts
        or str(policy.get("decision") or "") == "action_proposal_only"
        else "human_rca"
    )
    transcript_projection = {
        "answer": answer_text,
        "conversationId": req.conversationId,
        "requestId": request_id,
        "runId": run_id,
        "userMessage": req.message,
    }
    transcript_id = f"chat-transcript-{canonical_digest(redact_sensitive(transcript_projection)).removeprefix('sha256:')[:16]}"
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ChatTranscriptRecord",
        "metadata": {
            "createdAt": created_at,
            "name": transcript_id,
        },
        "spec": {
            "answerContract": list(dict.fromkeys(answer_contracts)),
            "answerMode": answer_mode,
            "assistantAnswer": truncate_chat_text(answer_text, CHAT_TRANSCRIPT_MAX_ANSWER_CHARS),
            "attachments": len(req.attachments),
            "conversationId": req.conversationId or incident_id,
            "evidenceRefs": {
                "collected": redact_sensitive(evidence.get("collectedRefs", [])),
                "failed": redact_sensitive(evidence.get("failedRefs", [])),
                "missing": redact_sensitive(evidence.get("missing", [])),
            },
            "rcaContextDigest": rca_context_digest,
            "observedState": {
                "evidenceSummary": redact_sensitive(evidence.get("summary", {})),
                "rcaContextDigest": rca_context_digest,
                "rcaResult": redact_sensitive(rca_result),
                "taskType": runtime_tool_plan.get("task_type") if isinstance(runtime_tool_plan, Mapping) else "",
                "toolPlanDigest": tool_plan_digest,
            },
            "policy": redact_sensitive(dict(policy)),
            "requestId": request_id,
            "runId": run_id,
            "status": status,
            "toolPlanDigest": tool_plan_digest,
            "userMessage": truncate_chat_text(req.message, CHAT_TRANSCRIPT_MAX_MESSAGE_CHARS),
            "workflow": {
                "actionRecords": chat_action_record_refs(incident_id, run_id),
                "incidentId": incident_id,
            },
        },
        "subject": redact_sensitive(dict(subject)),
    }


async def persist_chat_transcript_record(record: dict[str, Any]) -> None:
    transcript_id = str(record.get("metadata", {}).get("name") or f"chat-transcript-{uuid.uuid4().hex[:16]}")
    await bounded_put_record("chatTranscripts", transcript_id, record)
    await append_chat_transcript_jsonl(record)
    increment_metric("aiops_chat_transcripts_total")


def write_chat_transcript_jsonl(record: Mapping[str, Any]) -> None:
    if not CHAT_TRANSCRIPT_JSONL_PATH:
        return

    path = Path(CHAT_TRANSCRIPT_JSONL_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(redact_sensitive(dict(record)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
        handle.write("\n")


async def append_chat_transcript_jsonl(record: Mapping[str, Any]) -> None:
    try:
        await asyncio.to_thread(write_chat_transcript_jsonl, record)
    except Exception:
        increment_metric("aiops_chat_transcript_jsonl_write_failures_total")


def can_subject_read_record(record: Mapping[str, Any], subject: Mapping[str, Any]) -> bool:
    record_subject = record.get("originatingSubject") or record.get("subject") or {}
    if not isinstance(record_subject, Mapping):
        return False

    return (
        record_subject.get("username") == subject.get("username")
        and record_subject.get("uid") == subject.get("uid")
        and record_subject.get("groupsDigest") == subject.get("groupsDigest")
    )


def diagnostic_request_digest(candidate: Mapping[str, Any]) -> str:
    projection = {field: candidate.get(field) for field in DIAGNOSTIC_REQUEST_DIGEST_FIELDS}
    return canonical_digest(redact_sensitive(projection))


def build_diagnostic_request_candidate(
    request: "DiagnosticRequestCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        collector_profile = get_host_diagnostic_collector(request.collector)
    except AiopsCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if request.collectorVersion != collector_profile["collectorVersion"]:
        raise HTTPException(status_code=400, detail="collectorVersion does not match the registry")
    if request.collectorProfile != collector_profile["collectorProfile"]:
        raise HTTPException(status_code=400, detail="collectorProfile does not match the registry")
    candidate = {
        "schemaVersion": "v1",
        "clusterId": CLUSTER_ID,
        "requester": redact_sensitive(dict(subject)),
        "targetNode": request.targetNode.model_dump(),
        "collector": request.collector,
        "collectorVersion": request.collectorVersion,
        "collectorProfile": request.collectorProfile,
        "collectorRegistry": {
            "version": HOST_DIAGNOSTIC_COLLECTOR_VERSION,
            "digest": HOST_DIAGNOSTIC_COLLECTOR_DIGEST,
        },
        "collectorConstraints": collector_profile,
        "timeRange": request.timeRange.model_dump(),
        "limits": request.limits.model_dump(),
        "evidencePolicy": request.evidencePolicy.model_dump(),
        "policy": redact_sensitive(dict(request.policy)),
    }
    return candidate


def build_diagnostic_request_record(
    request: "DiagnosticRequestCreate",
    subject: Mapping[str, Any],
) -> dict[str, Any]:
    candidate = build_diagnostic_request_candidate(request, subject)
    request_digest = diagnostic_request_digest(candidate)
    request_id = f"diag-{request_digest.removeprefix('sha256:')[:16]}"
    grant_reference_digest = canonical_digest(
        {
            "audience": "aiops-host-diagnostics-controller",
            "requestDigest": request_digest,
            "requestId": request_id,
        }
    )
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequestRecord",
        "metadata": {
            "name": request_id,
            "createdAt": now_rfc3339(),
        },
        "spec": {
            "candidate": candidate,
            "diagnosticRequestDigest": request_digest,
            "digestSchema": {
                "name": "diagnostic-request-digest-v1",
                "canonicalization": "stable-json-sort-keys",
                "includedFields": list(DIAGNOSTIC_REQUEST_DIGEST_FIELDS),
            },
            "grantRef": {
                "grantId": f"diag-grant-{request_digest.removeprefix('sha256:')[:16]}",
                "grantDigest": grant_reference_digest,
                "bearerGrantStored": False,
            },
            "incidentId": request.incidentId,
            "runId": request.runId,
            "status": {
                "phase": "pending_controller_submission" if DIAGNOSTICS_ENABLED else "disabled",
                "reason": (
                    "Host diagnostics controller submission is enabled."
                    if DIAGNOSTICS_ENABLED
                    else "Host diagnostics controller submission is disabled by configuration."
                ),
                "submittedToController": False,
            },
        },
        "subject": redact_sensitive(dict(subject)),
    }


async def submit_diagnostic_request_to_controller(record: dict[str, Any]) -> dict[str, Any]:
    status = record["spec"]["status"]
    if not DIAGNOSTICS_ENABLED:
        return record
    if not HOST_DIAGNOSTICS_CONTROLLER_URL:
        status.update(
            {
                "phase": "controller_unconfigured",
                "reason": "Host diagnostics controller URL is not configured.",
                "submittedToController": False,
            }
        )
        return record

    headers: dict[str, str] = {}
    if HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN:
        headers["Authorization"] = f"Bearer {HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN}"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            response = await client.post(
                f"{HOST_DIAGNOSTICS_CONTROLLER_URL}/v1/controller/diagnostics/requests",
                headers=headers,
                json={"diagnosticRequest": record},
            )
    except httpx.HTTPError as exc:
        status.update(
            {
                "phase": "controller_submission_failed",
                "reason": f"Host diagnostics controller request failed: {exc.__class__.__name__}",
                "submittedToController": False,
            }
        )
        return record

    if response.status_code >= 400:
        status.update(
            {
                "phase": "controller_submission_failed",
                "reason": f"Host diagnostics controller returned HTTP {response.status_code}",
                "submittedToController": False,
                "controllerError": redact_sensitive(response.text[:1000]),
            }
        )
        return record

    try:
        controller_result = response.json()
    except ValueError:
        controller_result = {"raw": response.text[:1000]}
    status.update(
        {
            "phase": "controller_submitted",
            "reason": "Host diagnostics controller accepted the request.",
            "submittedToController": True,
            "controllerSubmission": redact_sensitive(controller_result),
        }
    )
    return record


def compact_controller_submission(controller_result: Mapping[str, Any]) -> dict[str, Any]:
    compacted = redact_sensitive(dict(controller_result))
    spec = compacted.get("spec") if isinstance(compacted.get("spec"), Mapping) else {}
    collector_pod = spec.get("collectorPod") if isinstance(spec.get("collectorPod"), Mapping) else {}
    log_preview = collector_pod.get("logPreview")
    if isinstance(log_preview, str):
        collector_pod["logPreviewDigest"] = canonical_digest(log_preview)
        collector_pod["logPreviewBytes"] = len(log_preview.encode("utf-8"))
        collector_pod.pop("logPreview", None)
    return compacted


def normalize_controller_phase(phase: str) -> str:
    if phase == "completed":
        return "succeeded"
    return phase


async def refresh_diagnostic_request_from_controller(record: dict[str, Any]) -> dict[str, Any]:
    status = record["spec"]["status"]
    if not DIAGNOSTICS_ENABLED or not HOST_DIAGNOSTICS_CONTROLLER_URL:
        return record
    if status.get("submittedToController") is not True:
        return record
    request_id = str(record["metadata"]["name"])
    headers: dict[str, str] = {}
    if HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN:
        headers["Authorization"] = f"Bearer {HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = await client.get(
                f"{HOST_DIAGNOSTICS_CONTROLLER_URL}/v1/controller/diagnostics/requests/{request_id}",
                headers=headers,
            )
    except httpx.HTTPError:
        return record
    if response.status_code >= 400:
        return record
    try:
        controller_result = response.json()
    except ValueError:
        return record
    controller_spec = (
        controller_result.get("spec") if isinstance(controller_result, Mapping) else {}
    )
    phase = controller_spec.get("phase") if isinstance(controller_spec, Mapping) else None
    if isinstance(phase, str) and phase:
        status["phase"] = f"collector_{normalize_controller_phase(phase)}"
    status["controllerSubmission"] = compact_controller_submission(controller_result)
    return record



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


class ImageAttachment(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=180)
    mimeType: str = Field(min_length=1, max_length=80)
    size: int = Field(ge=1, le=MAX_IMAGE_ATTACHMENT_BYTES)
    data: str = Field(min_length=1)


class ChatContextMessage(BaseModel):
    role: str = Field(min_length=1, max_length=20)
    content: str = Field(default="", max_length=4000)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    pageContext: dict[str, Any] | None = None
    conversationId: str | None = None
    language: str | None = Field(default=None, max_length=16)
    runId: str | None = None
    recentMessages: list[ChatContextMessage] = Field(default_factory=list, max_length=8)
    attachments: list[ImageAttachment] = Field(default_factory=list, max_length=MAX_IMAGE_ATTACHMENTS)


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


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def verify_user_access(user_auth_header: str, req: ChatRequest) -> None:
    if not user_auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    if not req.message.strip() and not req.attachments:
        raise HTTPException(status_code=400, detail="Message or image attachment is required")

    enforce_rate_limit(user_auth_header)


def verify_bearer_header(user_auth_header: str | None) -> str:
    if not user_auth_header or not user_auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    token = user_auth_header.removeprefix("Bearer ").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    return f"Bearer {token}"


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
    resolved_status = status or ("available" if payload is not None else "unavailable")
    item: dict[str, Any] = {
        "label": label,
        "name": name,
        "path": path,
        "required": required,
        "status": resolved_status,
    }
    if reason:
        item["reason"] = reason
    if http_status is not None:
        item["httpStatus"] = http_status
    if isinstance(payload, Mapping):
        metadata = payload.get("metadata")
        if isinstance(metadata, Mapping) and metadata.get("continue"):
            item["status"] = "partial"
            item["reason"] = "Kubernetes list response is paginated; additional pages were not fetched in this evidence summary."
            item["continueTokenPresent"] = True
    return item


async def fetch_ocp_json_observed(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    label: str,
    name: str,
    required: bool = False,
) -> tuple[Mapping[str, Any] | None, dict[str, Any]]:
    try:
        response = await client.get(
            f"{OPENSHIFT_API_URL}{path}",
            headers={
                "Accept": "application/json",
                "Authorization": authorization,
            },
        )
    except httpx.HTTPError as exc:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=str(exc),
            status="error",
        )

    if response.status_code >= 400:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=response.text[:240],
            status="error",
            http_status=response.status_code,
        )

    try:
        payload = response.json()
    except ValueError as exc:
        return None, data_source_status(
            label=label,
            name=name,
            path=path,
            required=required,
            reason=f"Invalid JSON response: {exc}",
            status="error",
        )

    if isinstance(payload, Mapping):
        return payload, data_source_status(
            label=label,
            name=name,
            path=path,
            payload=payload,
            required=required,
        )

    return None, data_source_status(
        label=label,
        name=name,
        path=path,
        required=required,
        reason="OpenShift API response was not a JSON object.",
        status="error",
    )


def monitoring_urls_from_config(configmap_payload: Mapping[str, Any] | None) -> dict[str, str]:
    data = configmap_payload.get("data", {}) if isinstance(configmap_payload, Mapping) else {}
    if not isinstance(data, Mapping):
        data = {}
    return {
        "alertmanager": str(data.get("alertmanagerPublicURL") or ""),
        "prometheus": str(data.get("prometheusPublicURL") or ""),
        "thanos": str(data.get("thanosPublicURL") or ""),
    }


async def query_thanos_instant(thanos_url: str, authorization: str, query: str) -> dict[str, Any]:
    if not thanos_url:
        return {
            "query": query,
            "status": "unavailable",
            "reason": "thanosPublicURL is not published in monitoring-shared-config.",
        }

    try:
        async with httpx.AsyncClient(
            verify=OPENSHIFT_API_CA_FILE,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.get(
                f"{thanos_url.rstrip('/')}/api/v1/query",
                headers={"Accept": "application/json", "Authorization": authorization},
                params={"query": query},
            )
    except httpx.HTTPError as exc:
        return {"query": query, "status": "error", "reason": str(exc)}

    if response.status_code >= 400:
        return {
            "httpStatus": response.status_code,
            "query": query,
            "reason": response.text[:240],
            "status": "error",
        }

    try:
        payload = response.json()
    except ValueError as exc:
        return {"query": query, "status": "error", "reason": f"Invalid JSON response: {exc}"}

    if not isinstance(payload, Mapping):
        return {"query": query, "status": "error", "reason": "Thanos response was not a JSON object."}
    prometheus_status = str(payload.get("status") or "")
    if prometheus_status and prometheus_status != "success":
        reason = (
            str(payload.get("error") or payload.get("errorType") or "Prometheus query failed")
        )
        return {"query": query, "status": "error", "reason": reason[:240]}

    data = payload.get("data", {}) if isinstance(payload, Mapping) else {}
    result = data.get("result", []) if isinstance(data, Mapping) else []
    if not isinstance(result, list):
        return {"query": query, "status": "error", "reason": "Thanos query result was not a vector list."}
    return {
        "query": query,
        "result": result[:50],
        "resultCount": len(result),
        "status": "partial" if len(result) > 50 else "available",
        **(
            {"reason": "Thanos vector result was capped at 50 series for dashboard summary."}
            if len(result) > 50
            else {}
        ),
    }


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
    health_score = int(cluster_summary_payload.get("healthScore") or 0)
    nodes = cluster_summary_payload.get("nodes", {}) if isinstance(cluster_summary_payload.get("nodes"), Mapping) else {}
    operators = (
        cluster_summary_payload.get("operators", {})
        if isinstance(cluster_summary_payload.get("operators"), Mapping)
        else {}
    )
    required_errors = [
        item
        for item in data_sources
        if item.get("required") and item.get("status") != "available"
    ]
    attention_count = (
        int(nodes.get("notReady") or 0)
        + int(nodes.get("pressureCount") or 0)
        + int(operators.get("degraded") or 0)
        + int(operators.get("unavailable") or 0)
        + int(operators.get("progressing") or 0)
    )
    if required_errors:
        tower_status = "error"
        tower_label = "필수 데이터 소스 확인 실패"
    elif health_score >= 90 and attention_count == 0:
        tower_status = "healthy"
        tower_label = "회사 OCP 승인 실행 관제 정상"
    elif health_score >= 65:
        tower_status = "attention"
        tower_label = "운영 확인 필요"
    else:
        tower_status = "risk"
        tower_label = "즉시 확인 필요"

    anomaly_spec = (
        anomaly_summary.get("spec", {})
        if isinstance(anomaly_summary, Mapping) and isinstance(anomaly_summary.get("spec"), Mapping)
        else {}
    )
    anomaly_status = str(anomaly_spec.get("status") or "")
    anomaly_totals = (
        anomaly_spec.get("totals", {}) if isinstance(anomaly_spec.get("totals"), Mapping) else {}
    )
    anomaly_total = int(anomaly_totals.get("total") or 0)
    if anomaly_status in {"error", "unknown"}:
        tower_status = "error"
        tower_label = str(anomaly_spec.get("statusLabel") or "이상 징후 데이터 소스 확인 필요")
    elif anomaly_status == "risk":
        tower_status = "risk"
        tower_label = str(anomaly_spec.get("statusLabel") or "위험 이상 징후 확인 필요")
    elif anomaly_status in {"attention", "warning"} and tower_status == "healthy":
        tower_status = "attention"
        tower_label = str(anomaly_spec.get("statusLabel") or "이상 징후 확인 필요")
    action_candidates = build_aiops_action_candidates(anomaly_summary, data_sources)

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsOverview",
        "metadata": {"generatedAt": now_rfc3339(), "name": "kugnus-control-tower"},
        "spec": {
            "clusterSummary": cluster_summary_payload,
            "controlTower": {
                "name": "Cywell AI 관제탑",
                "mode": "execute",
                "status": tower_status,
                "statusLabel": tower_label,
                "attentionCount": attention_count + anomaly_total,
                "healthScore": health_score,
                "target": cluster_summary_payload.get("apiUrl") or OPENSHIFT_API_URL,
            },
            "dataSources": list(data_sources),
            "anomalies": dict(anomaly_summary or {}),
            "actionCandidates": action_candidates,
            "monitoring": {
                "probe": dict(monitoring_probe),
                "urls": {
                    "alertmanagerConfigured": bool(monitoring_urls.get("alertmanager")),
                    "prometheusConfigured": bool(monitoring_urls.get("prometheus")),
                    "thanosConfigured": bool(monitoring_urls.get("thanos")),
                },
            },
            "safety": {
                "mutationsEnabled": ACTION_PLAN_CAPABILITY_ENABLED,
                "executionDefault": ACTION_PLAN_CAPABILITY_ENABLED,
                "unrestrictedCommandsEnabled": UNRESTRICTED_COMMANDS_ENABLED,
            },
        },
    }


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
    if not payload:
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def metadata_name(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    return str(metadata.get("name") or "")


def metadata_namespace(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    return str(metadata.get("namespace") or "")


def resource_labels(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    labels = metadata.get("labels")
    return labels if isinstance(labels, Mapping) else {}


def parse_k8s_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_days(value: Any) -> int | None:
    timestamp = parse_k8s_timestamp(value)
    if not timestamp:
        return None
    return max(0, int((datetime.now(UTC) - timestamp).total_seconds() // 86400))


def namespace_resource_counts(namespace: str, payloads: Mapping[str, Mapping[str, Any] | None]) -> dict[str, int]:
    def count_for(payload_name: str) -> int:
        return len(
            [
                item
                for item in resource_items(payloads.get(payload_name))
                if metadata_namespace(item) == namespace
            ]
        )

    return {
        "deployments": count_for("deployments"),
        "events": count_for("events"),
        "pods": count_for("pods"),
        "pvcs": count_for("pvcs"),
        "routes": count_for("routes"),
        "services": count_for("services"),
    }


def namespace_last_event_age_days(namespace: str, events_payload: Mapping[str, Any] | None) -> int | None:
    latest: datetime | None = None
    for event in resource_items(events_payload):
        if metadata_namespace(event) != namespace:
            continue
        event_time = (
            event.get("lastTimestamp")
            or event.get("eventTime")
            or event.get("firstTimestamp")
            or event.get("metadata", {}).get("creationTimestamp")
        )
        parsed = parse_k8s_timestamp(event_time)
        if parsed and (latest is None or parsed > latest):
            latest = parsed
    if not latest:
        return None
    return max(0, int((datetime.now(UTC) - latest).total_seconds() // 86400))


def namespace_cleanup_decision(
    namespace: str,
    namespace_resource: Mapping[str, Any] | None,
    counts: Mapping[str, int],
    last_event_age: int | None,
) -> dict[str, str]:
    if namespace_resource is None:
        return {
            "label": "확인 불가",
            "reason": "namespace가 조회 결과에 없습니다",
            "next": "이름을 다시 확인",
        }
    if SYSTEM_NAMESPACE_RE.search(namespace):
        return {
            "label": "보호",
            "reason": "시스템 또는 기본 namespace",
            "next": "삭제 계획 제외",
        }

    workload_count = int(counts.get("pods") or 0) + int(counts.get("deployments") or 0)
    exposure_count = int(counts.get("services") or 0) + int(counts.get("routes") or 0) + int(counts.get("pvcs") or 0)
    if workload_count > 0 or exposure_count > 0:
        return {
            "label": "사용 중",
            "reason": (
                f"workload {workload_count}개, service/route/pvc {exposure_count}개 확인"
            ),
            "next": "소유자와 실제 서비스 영향 확인",
        }

    if last_event_age is not None and last_event_age <= 7:
        return {
            "label": "삭제 보류",
            "reason": f"최근 이벤트가 {last_event_age}일 전 확인",
            "next": "최근 작업 목적 확인",
        }

    return {
        "label": "정리 검토 가능",
        "reason": "workload, service, route, pvc가 없고 최근 활동 신호가 약함",
        "next": "소유자/백업/PVC 재확인 후 승인 검토",
    }


def namespace_cleanup_candidate_from_item(item: Mapping[str, Any], run_id: str, incident_id: str) -> dict[str, Any]:
    namespace = str(item.get("namespace") or "")
    uid = str(item.get("uid") or f"namespace-{namespace}")
    candidate_id = f"action-candidate-namespace-cleanup-{hashlib.sha256(namespace.encode()).hexdigest()[:12]}"
    return {
        "approvalRequired": True,
        "blockedActions": list(ACTION_CANDIDATE_FORBIDDEN_VERBS),
        "blockedReasons": ["approval-required", "review-only-plan"],
        "confidence": "medium",
        "evidence": str(item.get("reason") or "namespace read-only inventory"),
        "evidenceRefs": [
            {
                "evidenceType": "namespace_inventory",
                "findingId": f"namespace-cleanup-{namespace}",
                "sourceType": "namespace_cleanup_review",
                "status": "collected",
            }
        ],
        "executable": False,
        "executionPolicy": {
            "executionEnabled": False,
            "mode": "review-only",
            "mutationVerbsDisabled": True,
            "proposalOnly": True,
        },
        "expectedImpact": "정리 후보를 승인 검토 계획으로 고정합니다. 이 후보 자체는 namespace 삭제를 실행하지 않습니다.",
        "id": candidate_id,
        "mutationSubmitted": False,
        "priority": 40,
        "prerequisiteChecks": ["소유자 확인", "PVC/Route 잔존 여부 재확인", "백업 필요 여부 확인"],
        "recommendationSteps": ["namespace 사용 신호 재확인", "정리 검토 Action Plan 생성", "별도 삭제 승인 정책 확인"],
        "riskLevel": "medium",
        "riskLabel": "중간",
        "severity": "확인 필요",
        "sourceFindingId": f"namespace-cleanup-{namespace}",
        "sourceType": "namespace_cleanup_review",
        "statusLabel": "승인 필요",
        "target": {
            "apiVersion": "v1",
            "kind": "Namespace",
            "name": namespace,
            "namespace": namespace,
            "uid": uid,
        },
        "title": "Namespace 정리 검토",
        "verificationChecks": ["Action Plan 생성 후에도 namespace가 존재하는지 확인", "삭제 실행 기록이 없는지 확인"],
        "chatRunId": run_id,
        "incidentId": incident_id,
        "expiresAt": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
    }


async def collect_namespace_cleanup_inventory(
    user_auth_header: str,
    requested_names: Sequence[str],
) -> dict[str, Any]:
    if not OPENSHIFT_API_URL:
        return {
            "error": "OPENSHIFT_API_URL is not configured",
            "inspected": [],
            "ok": False,
            "requestedNames": list(requested_names),
            "server": "",
            "status": "missing_api_url",
            "totalNamespaces": 0,
        }

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(15.0, connect=5.0),
    ) as client:
        namespaces_payload, pods_payload, deployments_payload, services_payload, routes_payload, pvcs_payload, events_payload = await asyncio.gather(
            fetch_ocp_json(client, "/api/v1/namespaces?limit=500", user_auth_header),
            fetch_ocp_json(client, "/api/v1/pods?limit=500", user_auth_header),
            fetch_ocp_json(client, "/apis/apps/v1/deployments?limit=500", user_auth_header),
            fetch_ocp_json(client, "/api/v1/services?limit=500", user_auth_header),
            fetch_ocp_json(client, "/apis/route.openshift.io/v1/routes?limit=500", user_auth_header),
            fetch_ocp_json(client, "/api/v1/persistentvolumeclaims?limit=500", user_auth_header),
            fetch_ocp_json(client, "/api/v1/events?limit=500", user_auth_header),
        )

    namespace_items = resource_items(namespaces_payload)
    namespace_by_name = {metadata_name(item): item for item in namespace_items}
    names = [name for name in requested_names if name]
    if not names:
        names = [
            name
            for name in sorted(namespace_by_name)
            if not SYSTEM_NAMESPACE_RE.search(name)
        ][:12]

    payloads = {
        "deployments": deployments_payload,
        "events": events_payload,
        "pods": pods_payload,
        "pvcs": pvcs_payload,
        "routes": routes_payload,
        "services": services_payload,
    }
    inspected: list[dict[str, Any]] = []
    for namespace in names[:12]:
        namespace_resource = namespace_by_name.get(namespace)
        metadata = (
            namespace_resource.get("metadata", {})
            if isinstance(namespace_resource, Mapping) and isinstance(namespace_resource.get("metadata"), Mapping)
            else {}
        )
        counts = namespace_resource_counts(namespace, payloads)
        last_event_age = namespace_last_event_age_days(namespace, events_payload)
        decision = namespace_cleanup_decision(namespace, namespace_resource, counts, last_event_age)
        inspected.append(
            {
                "counts": counts,
                "createdAgeDays": age_days(metadata.get("creationTimestamp")),
                "decision": decision,
                "eventCount": counts["events"],
                "lastEventAgeDays": last_event_age,
                "namespace": namespace,
                "ok": namespace_resource is not None,
                "reason": decision["reason"],
                "uid": str(metadata.get("uid") or ""),
            }
        )

    return {
        "inspected": inspected,
        "ok": bool(namespace_items),
        "requestedNames": names[:12],
        "server": OPENSHIFT_API_URL,
        "status": "success" if namespace_items else "empty_namespace_inventory",
        "totalNamespaces": len(namespace_items),
    }


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


def namespace_cleanup_candidates_from_inventory(inventory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in inventory.get("inspected", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("decision"), Mapping)
        and item["decision"].get("label") == "정리 검토 가능"
    ]


def namespace_cleanup_command_block(inventory: Mapping[str, Any]) -> str:
    names = [
        str(item.get("namespace") or "")
        for item in inventory.get("inspected", [])
        if isinstance(item, Mapping) and item.get("namespace")
    ]
    lines = ["```bash", "oc whoami --show-server", "oc get namespaces"]
    for namespace in names[:12]:
        lines.append(f"oc get all,pvc,route,event -n {namespace} --ignore-not-found")
        lines.append(f"oc get namespace {namespace} -o yaml")
    lines.append("```")
    return "\n".join(lines)


def namespace_cleanup_answer(inventory: Mapping[str, Any], execution_mode: str, language: str) -> str:
    is_en = language == "en"

    def english_decision_label(value: Any) -> str:
        mapping = {
            "확인 불가": "Unknown",
            "보호": "Protected",
            "사용 중": "In use",
            "삭제 보류": "Hold",
            "정리 검토 가능": "Cleanup review candidate",
        }
        return mapping.get(str(value or ""), str(value or "-"))

    def english_decision_reason(value: Any) -> str:
        text = str(value or "-")
        replacements = {
            "namespace가 조회 결과에 없습니다": "namespace was not found in the query result",
            "시스템 또는 기본 namespace": "system or default namespace",
            "소유자와 실제 서비스 영향 확인": "confirm owner and service impact",
            "최근 작업 목적 확인": "confirm the purpose of recent activity",
            "삭제 계획 제외": "exclude from deletion plans",
            "이름을 다시 확인": "recheck the namespace name",
            "소유자/백업/PVC 재확인 후 승인 검토": "confirm owner, backup, and PVC state before approval review",
            "workload, service, route, pvc가 없고 최근 활동 신호가 약함": "no workload, service, route, or PVC was found and recent activity evidence is weak",
        }
        for source, target in replacements.items():
            text = text.replace(source, target)
        text = re.sub(r"workload\s+(\d+)개,\s+service/route/pvc\s+(\d+)개\s+확인", r"workload \1, service/route/pvc \2 found", text)
        text = re.sub(r"최근 이벤트가\s+(\d+)일 전 확인", r"latest event was \1 days ago", text)
        return text

    if not inventory.get("ok"):
        if is_en:
            return "\n".join(
                [
                    "## Current Status",
                    "AIOps for OCP could not run the OpenShift read-only namespace query.",
                    "",
                    "## Failure Point",
                    f"- {inventory.get('status')}: {inventory.get('error') or 'namespace inventory unavailable'}",
                    "",
                    "## Next Step",
                    "- First verify `oc whoami --show-server` and `oc get namespaces` from the terminal.",
                    "- No cleanup candidate is decided until read-only evidence is collected.",
                ]
            )
        return "\n".join(
            [
                "## 현재 상태",
                "AIOps for OCP가 OpenShift namespace read-only 조회를 실행하지 못했습니다.",
                "",
                "## 실패 지점",
                f"- {inventory.get('status')}: {inventory.get('error') or 'namespace inventory unavailable'}",
                "",
                "## 다음 조치",
                "- 터미널에서 `oc whoami --show-server`와 `oc get namespaces`가 되는지 먼저 확인해야 합니다.",
                "- 조회 결과가 정리되기 전에는 정리 후보를 판정하지 않습니다.",
            ]
        )

    cleanup_candidates = namespace_cleanup_candidates_from_inventory(inventory)
    action_mode = action_capable_execution_mode(execution_mode)
    if is_en:
        mode_line = (
            f"{execution_mode_sentence(execution_mode, language)} "
            + (
                "Cleanup review candidates exist, so an approval-gated Action Plan candidate can be created."
                if action_mode and cleanup_candidates
                else "No safe cleanup review candidate was found."
                if action_mode
                else ""
            )
        ).strip()
        lines = [
            "## Current Assessment",
            mode_line,
            "",
            "## Query Evidence",
            f"- API server: {inventory.get('server') or '-'}",
            f"- Accessible namespaces: {inventory.get('totalNamespaces')}",
            f"- Query scope: {', '.join(inventory.get('requestedNames') or [])}",
            "",
            "## Namespace Decisions",
            "| Namespace | Decision | Evidence | Next Step |",
            "|---|---|---|---|",
        ]
        for item in inventory.get("inspected", []):
            if not isinstance(item, Mapping):
                continue
            decision = item.get("decision") if isinstance(item.get("decision"), Mapping) else {}
            lines.append(
                f"| {item.get('namespace')} | {english_decision_label(decision.get('label'))} | {english_decision_reason(decision.get('reason'))} | {english_decision_reason(decision.get('next'))} |"
            )
        lines.extend(
            [
                "",
                "## Action Plan",
                (
                    f"- Approval-required candidates: {', '.join(f'`{item.get('namespace')}`' for item in cleanup_candidates)}"
                    if action_mode and cleanup_candidates
                    else "- Status: execution mode is enabled, but no safe cleanup candidate was found."
                    if action_mode
                    else "- Status: read-only mode shows cleanup review candidates only; switch to execution-enabled mode to create an Action Plan."
                ),
                "- This review plan does not delete a namespace by itself.",
                "- Deletion requires a separate owner/backup/PVC/Route confirmation policy.",
                "- Read-only terminal checks include `oc get namespaces` and `oc get all,pvc,route,event` for each reviewed namespace.",
                "",
                "## Terminal Check Commands",
                namespace_cleanup_command_block(inventory),
            ]
        )
        return "\n".join(lines)

    mode_line = (
        f"{execution_mode_sentence(execution_mode, language)} "
        + (
            "정리 검토 후보가 있어 Action Plan 후보를 만들 수 있습니다."
            if action_mode and cleanup_candidates
            else "안전한 정리 검토 후보가 없습니다."
            if action_mode
            else ""
        )
    ).strip()
    lines = [
        "## 현재 판단",
        mode_line,
        "",
        "## 조회 결과",
        f"- API 서버: {inventory.get('server') or '-'}",
        f"- 접근 가능한 namespace: {inventory.get('totalNamespaces')}개",
        f"- 조회 범위: {', '.join(inventory.get('requestedNames') or [])}",
        "",
        "## 네임스페이스별 판단",
        "| Namespace | 판단 | 확인 결과 | 다음 조치 |",
        "|---|---|---|---|",
    ]
    for item in inventory.get("inspected", []):
        if not isinstance(item, Mapping):
            continue
        decision = item.get("decision") if isinstance(item.get("decision"), Mapping) else {}
        lines.append(
            f"| {item.get('namespace')} | {decision.get('label')} | {decision.get('reason')} | {decision.get('next')} |"
        )
    lines.extend(
        [
            "",
            "## Action Plan",
            (
                f"- 승인 필요 후보: {', '.join(f'`{item.get('namespace')}`' for item in cleanup_candidates)}"
                if action_mode and cleanup_candidates
                else "- 상태: 실행 가능 모드이지만 안전한 정리 후보가 없어 Action Plan 버튼을 만들지 않습니다."
                if action_mode
                else "- 상태: 읽기 전용 모드에서는 정리 검토 후보만 표시하고, Action Plan 생성은 실행 가능 모드에서 진행합니다."
            ),
            "- 이 검토 계획은 namespace 삭제를 직접 실행하지 않습니다.",
            "- 실제 삭제는 소유자 확인, PVC/Route 잔존 여부, 백업 필요 여부를 별도로 승인해야 합니다.",
            "",
            "## 터미널 확인 명령",
            namespace_cleanup_command_block(inventory),
        ]
    )
    return "\n".join(lines)


def remember_namespace_cleanup_candidates(inventory: Mapping[str, Any], run_id: str, incident_id: str) -> None:
    candidates = [
        namespace_cleanup_candidate_from_item(item, run_id, incident_id)
        for item in namespace_cleanup_candidates_from_inventory(inventory)
    ]
    now = datetime.now(UTC)
    for key, candidate in list(NAMESPACE_CLEANUP_CHAT_CANDIDATES.items()):
        expires_at = parse_k8s_timestamp(candidate.get("expiresAt"))
        if expires_at and expires_at < now:
            NAMESPACE_CLEANUP_CHAT_CANDIDATES.pop(key, None)
    for candidate in candidates:
        NAMESPACE_CLEANUP_CHAT_CANDIDATES[str(candidate["id"])] = candidate


def merge_recent_namespace_cleanup_candidates(action_candidates: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(action_candidates)
    spec = dict(merged.get("spec", {})) if isinstance(merged.get("spec"), Mapping) else {}
    candidates = list(spec.get("candidates") or []) if isinstance(spec.get("candidates"), list) else []
    now = datetime.now(UTC)
    recent = []
    for candidate in NAMESPACE_CLEANUP_CHAT_CANDIDATES.values():
        expires_at = parse_k8s_timestamp(candidate.get("expiresAt"))
        if expires_at and expires_at >= now:
            recent.append({key: value for key, value in candidate.items() if key != "expiresAt"})
    existing_ids = {str(candidate.get("id") or "") for candidate in candidates if isinstance(candidate, Mapping)}
    candidates.extend(candidate for candidate in recent if str(candidate.get("id") or "") not in existing_ids)
    candidates = sorted(
        [candidate for candidate in candidates if isinstance(candidate, Mapping)],
        key=lambda item: (
            0 if item.get("chatRunId") else 1,
            int(item.get("priority") or 999),
            str(item.get("id") or ""),
        ),
    )
    spec["candidates"] = candidates[:8]
    totals = dict(spec.get("totals", {})) if isinstance(spec.get("totals"), Mapping) else {}
    totals["approvalRequired"] = len(candidates)
    totals["shown"] = min(len(candidates), 8)
    totals["total"] = len(candidates)
    spec["totals"] = totals
    if recent and spec.get("status") in {None, "", "idle"}:
        spec["status"] = "candidates"
        spec["statusLabel"] = f"승인 기반 조치 후보 {len(candidates)}건"
    merged["spec"] = spec
    return merged


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


async def stream_with_heartbeats(
    events: AsyncIterator[dict[str, Any]],
    run_id: str,
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | BaseException | None] = asyncio.Queue()
    started_at = time.monotonic()

    async def produce() -> None:
        try:
            async for event in events:
                await queue.put(event)
        except BaseException as exc:
            await queue.put(exc)
        finally:
            await queue.put(None)

    producer = asyncio.create_task(produce())

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=RUN_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "waiting",
                    "message": f"{active_llm_label()} 응답 대기 중",
                    "elapsedMs": int((time.monotonic() - started_at) * 1000),
                }
                continue

            if item is None:
                break

            if isinstance(item, BaseException):
                raise item

            yield item
    finally:
        if not producer.done():
            producer.cancel()


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


def should_use_ollama_llm() -> bool:
    return LLM_API_STYLE == "ollama" and bool(LLM_BASE_URL)


def active_llm_stage() -> str:
    return "ollama" if should_use_ollama_llm() else "lightspeed"


def active_llm_label() -> str:
    return "Ollama LLM" if should_use_ollama_llm() else "OpenShift Lightspeed"


def build_ollama_chat_url(base_url: str) -> str:
    url = base_url.rstrip("/")
    if url.endswith("/api/chat"):
        return url
    if url.endswith("/api"):
        return f"{url}/chat"
    return f"{url}/api/chat"


def extract_ollama_chat_content(data: Mapping[str, Any]) -> str:
    message = data.get("message")
    if isinstance(message, Mapping):
        content = message.get("content")
        if isinstance(content, str):
            return content
    response = data.get("response")
    if isinstance(response, str):
        return response
    return ""


async def call_ollama_chat(
    query: str,
    conversation_id: str | None,
    gateway_context: Mapping[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    context_digest = (
        str(gateway_context.get("metadata", {}).get("digest") or "")
        if isinstance(gateway_context, Mapping) and isinstance(gateway_context.get("metadata"), Mapping)
        else ""
    )
    if not LLM_BASE_URL or not LLM_MODEL:
        reason = "KOMSCO_AI_LLM_BASE_URL or KOMSCO_AI_LLM_MODEL is not configured"
        update_ols_stream_status(
            "not_configured",
            context_digest=context_digest,
            fallback_active=not REQUIRE_OLS_FINAL_ANSWER,
            reason=reason,
        )
        if REQUIRE_OLS_FINAL_ANSWER:
            raise RuntimeError(reason)
        yield {
            "type": "text",
            "content": "DEV_ECHO: Gateway is running. Configure KOMSCO_AI_LLM_BASE_URL and KOMSCO_AI_LLM_MODEL.\n\n",
            "source": "gateway_fallback",
            "fallbackAnswer": True,
            "gatewayContextDigest": context_digest,
            "streamProbe": "not_configured",
        }
        yield {"type": "end", "conversationId": conversation_id}
        return

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {
                "role": "system",
	                "content": (
	                    "너는 KOMSCO AIOps 운영 분석가다. 확인 결과와 추정을 분리하고, "
	                    "위험한 조치는 승인 전 실행 지시로 쓰지 않는다. "
	                    "답변은 `현재 판단`, `원인 후보`, `확인 결과`, `조치 방법`, `추가 확인` 순서를 우선한다. "
	                    "코드블록 안에는 실행 가능한 명령만 넣고, "
	                    "`Tip`, 주의사항, 확인 항목, 제목, 목록 문장은 코드블록 밖에 둔다. "
	                    "공용 웹 URL은 기본 답변에 출력하지 마세요."
	                ),
            },
            {"role": "user", "content": query},
        ],
        "stream": False,
        "think": False,
    }
    update_ols_stream_status("started", context_digest=context_digest)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(LLM_TIMEOUT_SECONDS, connect=10.0),
        ) as client:
            response = await client.post(
                build_ollama_chat_url(LLM_BASE_URL),
                json=payload,
                headers={"Content-Type": "application/json"},
            )
            if response.status_code >= 400:
                detail = safe_error_text(response.text[:1000], limit=1000)
                update_ols_stream_status(
                    "failed",
                    context_digest=context_digest,
                    fallback_active=not REQUIRE_OLS_FINAL_ANSWER,
                    reason=f"HTTP {response.status_code}: {detail}",
                )
                raise HTTPException(status_code=response.status_code, detail=detail)
            data = response.json()

        if not isinstance(data, Mapping):
            raise ValueError("Ollama chat response is not a JSON object")
        content = extract_ollama_chat_content(data)
        if not content.strip():
            raise ValueError("Ollama chat response did not include message.content")

        update_ols_stream_status("succeeded", context_digest=context_digest)
        yield {
            "type": "text",
            "content": content,
            "source": "ollama_chat",
            "gatewayContextDigest": context_digest,
            "streamProbe": "succeeded",
        }
        yield {"type": "end", "conversationId": conversation_id}
    except Exception as exc:
        if OLS_STREAM_STATUS.get("lastStatus") != "failed":
            update_ols_stream_status(
                "failed",
                context_digest=context_digest,
                fallback_active=not REQUIRE_OLS_FINAL_ANSWER,
                reason=safe_exception_text(exc),
            )
        raise


async def call_ols_stream(
    user_auth_header: str,
    query: str,
    conversation_id: str | None,
    attachments: list[ImageAttachment],
    gateway_context: Mapping[str, Any] | None = None,
) -> AsyncIterator[dict[str, Any]]:
    context_digest = (
        str(gateway_context.get("metadata", {}).get("digest") or "")
        if isinstance(gateway_context, Mapping) and isinstance(gateway_context.get("metadata"), Mapping)
        else ""
    )
    if should_use_ollama_llm():
        async for event in call_ollama_chat(query, conversation_id, gateway_context):
            yield event
        return

    if DEV_ECHO or not OLS_BASE_URL:
        fallback_status = "dev_echo" if DEV_ECHO else "not_configured"
        fallback_reason = "DEV_ECHO enabled" if DEV_ECHO else "OLS_BASE_URL is not configured"
        update_ols_stream_status(
            fallback_status,
            context_digest=context_digest,
            fallback_active=not REQUIRE_OLS_FINAL_ANSWER,
            reason=fallback_reason,
        )
        if REQUIRE_OLS_FINAL_ANSWER:
            raise RuntimeError(fallback_reason)
        yield {
            "type": "text",
            "content": "DEV_ECHO: Gateway is running. Configure OLS_BASE_URL for Lightspeed streaming.\n\n",
            "source": "gateway_fallback",
            "fallbackAnswer": True,
            "gatewayContextDigest": context_digest,
            "streamProbe": fallback_status,
        }
        yield {
            "type": "text",
            "content": query[:1200],
            "source": "gateway_fallback",
            "fallbackAnswer": True,
            "gatewayContextDigest": context_digest,
            "streamProbe": fallback_status,
        }
        yield {"type": "end", "conversationId": conversation_id}
        return

    payload = build_ols_payload(
        query,
        conversation_id,
        attachments,
        forward_image_attachments=should_forward_image_attachments_to_ols(),
        gateway_context=gateway_context,
    )
    update_ols_stream_status("started", context_digest=context_digest)

    try:
        async with httpx.AsyncClient(
            verify=OLS_CA_FILE,
            timeout=httpx.Timeout(LLM_TIMEOUT_SECONDS, connect=OLS_CONNECT_TIMEOUT_SECONDS),
        ) as client:
            async with client.stream(
                "POST",
                f"{OLS_BASE_URL}/v1/streaming_query",
                headers={
                    "Accept": "text/event-stream",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json=payload,
            ) as response:
                if response.status_code >= 400:
                    body = await response.aread()
                    detail = body.decode("utf-8", errors="replace")
                    safe_detail = safe_error_text(detail, limit=1000)
                    update_ols_stream_status(
                        "failed",
                        context_digest=context_digest,
                        fallback_active=not REQUIRE_OLS_FINAL_ANSWER,
                        reason=f"HTTP {response.status_code}: {safe_detail}",
                    )
                    raise HTTPException(status_code=response.status_code, detail=safe_detail)

                content_type = response.headers.get("content-type", "")
                if "text/event-stream" not in content_type:
                    async for event in split_plain_text_events(response.aiter_text()):
                        yield event
                    update_ols_stream_status("succeeded", context_digest=context_digest)
                    return

                buffer = ""
                async for chunk in response.aiter_text():
                    if not chunk:
                        continue

                    buffer += chunk
                    frames = buffer.split("\n\n")
                    buffer = frames.pop() or ""

                    for frame in frames:
                        data_lines = [
                            line[len("data:") :].strip()
                            for line in frame.splitlines()
                            if line.startswith("data:")
                        ]
                        if not data_lines:
                            async def iter_frame() -> AsyncIterator[str]:
                                yield frame + "\n"

                            async for event in split_plain_text_events(iter_frame()):
                                yield event
                            continue

                        raw = "\n".join(data_lines)
                        if not raw or raw == "[DONE]":
                            continue

                        try:
                            event = json.loads(raw)
                        except json.JSONDecodeError:
                            tool_event = parse_tool_text_line(raw)
                            if tool_event:
                                yield tool_event
                            else:
                                yield {"type": "text", "content": raw}
                            continue

                        yield event

                if buffer.strip() and not buffer.lstrip().startswith("data:"):
                    async def iter_buffer() -> AsyncIterator[str]:
                        yield buffer

                    async for event in split_plain_text_events(iter_buffer()):
                        yield event
                update_ols_stream_status("succeeded", context_digest=context_digest)
    except Exception as exc:
        if OLS_STREAM_STATUS.get("lastStatus") != "failed":
            update_ols_stream_status(
                "failed",
                context_digest=context_digest,
                fallback_active=not REQUIRE_OLS_FINAL_ANSWER,
                reason=safe_exception_text(exc),
            )
        raise


async def fetch_ocp_json(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    required: bool = False,
) -> Mapping[str, Any] | None:
    try:
        response = await client.get(
            f"{OPENSHIFT_API_URL}{path}",
            headers={
                "Accept": "application/json",
                "Authorization": authorization,
            },
        )
    except httpx.RequestError as exc:
        if required:
            raise HTTPException(
                status_code=504,
                detail=build_openshift_api_unavailable_detail(f"fetch_ocp_json:{path}", exc),
            ) from exc
        return None
    if response.status_code >= 400:
        if required:
            body = response.text[:500]
            raise HTTPException(
                status_code=response.status_code,
                detail=f"OpenShift API request failed for {path}: {body}",
            )

        return None

    payload = response.json()
    if isinstance(payload, Mapping):
        return payload

    return None


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
    if not past_pod_restart_demo_active(req):
        return "적용 없음"
    return "\n".join([
        "이 요청은 과거 시점 Pod 재시작 RCA 공식 Evidence 시연 사이클입니다.",
        "최종 답변에는 아래 5개 섹션명을 이 순서 그대로 포함하세요.",
        "1. `### 확인 결과`",
        "2. `### 가능한 원인 후보`",
        "3. `### 추가 확인 필요`",
        "4. `### Evidence-check 확인 순서`",
        "5. `### 금지 작업`",
        "수집된 증적(event/snapshot/pod_log/runbook)과 missing 증적(metric/clusteroperator)을 명확히 구분하세요.",
        "원인을 확정하지 말고 missing evidence가 있는 상태에서 조치 후보만 제시하세요.",
        "공식 최종 답변에는 `RCA`, `즉시 조치`, `재발 방지책`, `참고 증적` 관점을 포함하세요.",
        "`oc apply/delete/patch/scale/exec/rollout restart`는 코드블록에 넣지 말고 금지 작업 섹션에서만 언급하세요.",
    ])


def collect_past_pod_restart_demo_evidence_events(request_id: str) -> list[dict[str, Any]]:
    """Scenario 11 mock evidence — 어제 새벽 OOMKilled past-pod-restart-rca."""
    return [
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-event",
            "name": "openshift_event_lookup",
            "evidenceType": "event",
            "eventStatus": "success",
            "sourceType": "gateway-evidence",
            "status": "success",
            "summary": "Gateway-collected Pod Event evidence",
            "detail": (
                "openshift_event_lookup collected evidence — "
                "2026-06-28 02:14:33 KST · Namespace: default · "
                "Pod: webapp-deploy-7f94d-k8z2p · Reason: OOMKilled · "
                "Message: Container exceeded memory limit of 512Mi"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-snapshot",
            "name": "openshift_pod_snapshot_lookup",
            "evidenceType": "snapshot",
            "eventStatus": "success",
            "sourceType": "gateway-evidence",
            "status": "success",
            "summary": "Gateway-collected Pod snapshot evidence",
            "detail": (
                "openshift_pod_snapshot_lookup collected evidence — "
                "Pod webapp-deploy-7f94d-k8z2p: phase=Running, restartCount=3, "
                "lastState.terminated.reason=OOMKilled, "
                "lastState.terminated.finishedAt=2026-06-28T02:14:30Z, memoryLimit=512Mi"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-pod-status",
            "name": "openshift_pod_status_lookup",
            "evidenceType": "pod_status",
            "eventStatus": "success",
            "sourceType": "gateway-evidence",
            "status": "success",
            "summary": "Gateway-collected Pod status evidence",
            "detail": (
                "openshift_pod_status_lookup collected evidence — "
                "Pod 목록 조회 완료: webapp-deploy-7f94d-k8z2p STATUS=Running RESTARTS=3 AGE=2h10m"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-log",
            "name": "openshift_pod_log_pattern_probe",
            "evidenceType": "pod_log",
            "eventStatus": "success",
            "sourceType": "gateway-evidence",
            "status": "success",
            "summary": "Gateway-collected pod log pattern evidence",
            "detail": (
                "openshift_pod_log_pattern_probe collected evidence — "
                "이전 컨테이너 로그 패턴 검출: 'java.lang.OutOfMemoryError: Java heap space' (02:14:28), "
                "'GC overhead limit exceeded' (02:14:15), heap 증가 추세 확인됨"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-runbook",
            "name": "gateway_rag_runbook_search",
            "evidenceType": "runbook",
            "eventStatus": "success",
            "sourceType": "rag-evidence",
            "status": "success",
            "summary": "Gateway-collected RAG evidence",
            "detail": (
                "gateway_rag_runbook_search collected evidence — "
                "OOMKilled 대응 런북 조회 완료: 메모리 limit 증설 절차, "
                "JVM heap 설정 점검, HPA 메모리 기반 스케일 정책 확인 포함"
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-metric-missing",
            "name": "openshift_metric_query",
            "evidenceType": "metric",
            "eventStatus": "missing",
            "sourceType": "not-collected",
            "status": "skipped",
            "missingReason": "metric_tool Prometheus 연결은 v0.1.9 예정",
            "summary": "Metric evidence missing",
            "detail": (
                "openshift_metric_query missing evidence — "
                "Prometheus/Thanos 메모리 장기 추이 조회 미수행. "
                "metric_tool Prometheus 연결은 v0.1.9 예정."
            ),
        },
        {
            "type": "tool_result",
            "id": f"{request_id}-past-restart-clusteroperator-missing",
            "name": "openshift_clusteroperator_lookup",
            "evidenceType": "clusteroperator",
            "eventStatus": "missing",
            "sourceType": "not-collected",
            "status": "skipped",
            "missingReason": "ClusterOperator 상태 조회 미수행",
            "summary": "ClusterOperator evidence missing",
            "detail": "openshift_clusteroperator_lookup missing evidence — ClusterOperator 상태 조회 미수행",
        },
    ]


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
    if not OPENSHIFT_API_URL:
        return "Pod status evidence unavailable: OPENSHIFT_API_URL is not configured."

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        pods_payload = await fetch_ocp_json(client, "/api/v1/pods", user_auth_header)
        deployments_payload = await fetch_ocp_json(
            client,
            "/apis/apps/v1/deployments",
            user_auth_header,
        )
        replicasets_payload = await fetch_ocp_json(
            client,
            "/apis/apps/v1/replicasets",
            user_auth_header,
        )
        cluster_operators_payload = await fetch_ocp_json(
            client,
            "/apis/config.openshift.io/v1/clusteroperators",
            user_auth_header,
        )

    if not pods_payload:
        return (
            "Pod status evidence unavailable: Kubernetes API pod list was not returned. "
            "This may be a permission or API availability issue."
        )

    evidence = build_pod_status_evidence(
        pods_payload,
        replicasets_payload,
        include_pod_list=include_pod_list,
        list_namespace=list_namespace,
    )
    if deployments_payload:
        evidence = append_gateway_evidence(
            evidence,
            build_deployment_rollout_evidence(deployments_payload, replicasets_payload, pods_payload),
        )
    if cluster_operators_payload:
        evidence = append_gateway_evidence(
            evidence,
            build_cluster_operator_status_evidence(cluster_operators_payload),
        )

    return evidence


async def collect_pod_count_investigation(
    user_auth_header: str,
    query: Mapping[str, str],
) -> dict[str, Any]:
    namespace = str(query.get("namespace") or "")
    if not OPENSHIFT_API_URL:
        return {
            "namespace": namespace,
            "reason": "OPENSHIFT_API_URL is not configured",
            "status": "unavailable",
            "targetName": str(query.get("targetName") or ""),
        }

    if namespace:
        deployments_path = f"/apis/apps/v1/namespaces/{path_segment(namespace)}/deployments"
        pods_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods"
    else:
        deployments_path = "/apis/apps/v1/deployments"
        pods_path = "/api/v1/pods"

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        deployments_payload = await fetch_ocp_json(client, deployments_path, user_auth_header)
        pods_payload = await fetch_ocp_json(client, pods_path, user_auth_header)

    if not pods_payload:
        return {
            "namespace": namespace,
            "reason": f"Kubernetes API pod list was not returned for {pods_path}",
            "status": "unavailable",
            "targetName": str(query.get("targetName") or ""),
        }

    return build_pod_count_investigation(query, deployments_payload, pods_payload)


async def collect_cronjob_activity_evidence(user_auth_header: str, context_text: str) -> str:
    if not OPENSHIFT_API_URL:
        return "CronJob activity evidence unavailable: OPENSHIFT_API_URL is not configured."

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        cronjobs_payload = await fetch_ocp_json(client, "/apis/batch/v1/cronjobs", user_auth_header)
        jobs_payload = await fetch_ocp_json(client, "/apis/batch/v1/jobs?limit=500", user_auth_header)

    if not cronjobs_payload:
        return (
            "CronJob activity evidence unavailable: Kubernetes API CronJob list was not returned. "
            "This may be a permission or API availability issue."
        )

    return build_cronjob_activity_evidence(
        cronjobs_payload,
        jobs_payload,
        context_text=context_text,
    )


def _data_source_event_status(source: Mapping[str, Any] | None) -> str:
    status = str((source or {}).get("status") or "unavailable").lower()
    if status == "available":
        return "success"
    if status == "partial":
        return "partial"
    if status == "error":
        return "error"
    return "skipped"


def _evidence_summary(label: str, status: str) -> str:
    if status == "success":
        return f"{label} 수집 완료"
    if status == "partial":
        return f"{label} 부분 수집"
    return f"{label} 수집 불가"


async def _monitoring_urls_for_rca(user_auth_header: str) -> tuple[dict[str, str], dict[str, Any]]:
    if not OPENSHIFT_API_URL:
        return {}, data_source_status(
            label="Monitoring public URLs",
            name="monitoring-shared-config",
            path="/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config",
            reason="OPENSHIFT_API_URL is not configured.",
            status="unavailable",
        )

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        monitoring_config_payload, monitoring_config_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config",
            user_auth_header,
            label="Monitoring public URLs",
            name="monitoring-shared-config",
        )

    return monitoring_urls_from_config(monitoring_config_payload), monitoring_config_status


async def collect_node_status_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    source_path = "/api/v1/nodes"
    metrics_path = "/apis/metrics.k8s.io/v1beta1/nodes"
    if not OPENSHIFT_API_URL:
        reason = "OPENSHIFT_API_URL is not configured."
        return {
            "detail": f"Node status evidence unavailable: {reason}",
            "evidenceType": "node",
            "missingReason": reason,
            "sourcePath": source_path,
            "status": "skipped",
            "summary": _evidence_summary("Node 상태 RCA 증거", "skipped"),
        }

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        nodes_payload, nodes_status = await fetch_ocp_json_observed(
            client,
            source_path,
            user_auth_header,
            label="RCA Node status",
            name="nodes",
            required=True,
        )
        node_metrics_payload, metrics_status = await fetch_ocp_json_observed(
            client,
            metrics_path,
            user_auth_header,
            label="RCA Node metrics",
            name="metrics.k8s.io",
        )

    if not nodes_payload:
        reason = safe_error_text(nodes_status.get("reason") or "Kubernetes API node list was not returned.")
        status = _data_source_event_status(nodes_status)
        return {
            "detail": f"Node status evidence unavailable: {reason}",
            "evidenceType": "node",
            "missingReason": reason,
            "sourcePath": source_path,
            "status": status,
            "summary": _evidence_summary("Node 상태 RCA 증거", status),
        }

    metrics_event_status = _data_source_event_status(metrics_status)
    status = "partial" if metrics_event_status != "success" else "success"
    detail = build_node_status_rca_evidence(
        nodes_payload,
        node_metrics_payload,
        metrics_status=metrics_status,
    )
    return {
        "detail": detail,
        "evidenceType": "node",
        "missingReason": safe_error_text(metrics_status.get("reason") or "", limit=240)
        if status == "partial"
        else "",
        "sourcePath": f"{source_path},{metrics_path}",
        "status": status,
        "summary": _evidence_summary("Node 상태 RCA 증거", status),
    }


async def collect_active_alerts_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    monitoring_urls, monitoring_status = await _monitoring_urls_for_rca(user_auth_header)
    alerts_probe = await query_thanos_instant(
        monitoring_urls.get("thanos", ""),
        user_auth_header,
        'ALERTS{alertstate="firing"}',
    )
    status = rca_probe_event_status(alerts_probe)
    detail = build_active_alerts_rca_evidence(alerts_probe)
    if status == "skipped" and _data_source_event_status(monitoring_status) == "error":
        status = "error"
    reason = _prometheus_probe_reason(alerts_probe)
    return {
        "detail": detail,
        "evidenceType": "alert",
        "missingReason": reason if status != "success" else "",
        "sourcePath": '/api/v1/query?query=ALERTS{alertstate="firing"}',
        "status": status,
        "summary": _evidence_summary("Active Alert RCA 증거", status),
    }


async def collect_restart_metric_rca_evidence(user_auth_header: str) -> dict[str, Any]:
    query = "increase(kube_pod_container_status_restarts_total[1h]) > 0"
    monitoring_urls, monitoring_status = await _monitoring_urls_for_rca(user_auth_header)
    restart_probe = await query_thanos_instant(
        monitoring_urls.get("thanos", ""),
        user_auth_header,
        query,
    )
    status = rca_probe_event_status(restart_probe)
    detail = build_restart_metric_rca_evidence(restart_probe)
    if status == "skipped" and _data_source_event_status(monitoring_status) == "error":
        status = "error"
    reason = _prometheus_probe_reason(restart_probe)
    return {
        "detail": detail,
        "evidenceType": "metric",
        "missingReason": reason if status != "success" else "",
        "sourcePath": f"/api/v1/query?query={query}",
        "status": status,
        "summary": _evidence_summary("Restart metric RCA 증거", status),
    }


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
    resource_attributes: dict[str, Any] = {
        "resource": PRODUCT_ACCESS_REVIEW_RESOURCE,
        "verb": PRODUCT_ACCESS_REVIEW_VERB,
    }
    if PRODUCT_ACCESS_REVIEW_GROUP:
        resource_attributes["group"] = PRODUCT_ACCESS_REVIEW_GROUP
    if PRODUCT_ACCESS_REVIEW_NAME:
        resource_attributes["name"] = PRODUCT_ACCESS_REVIEW_NAME

    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": resource_attributes},
    }


def build_action_access_review_request(plan: Mapping[str, Any]) -> dict[str, Any]:
    action = plan.get("action") if isinstance(plan.get("action"), Mapping) else {}
    target = plan.get("target") if isinstance(plan.get("target"), Mapping) else {}
    authorization = action.get("authorization") if isinstance(action.get("authorization"), Mapping) else {}
    resource_attributes: dict[str, Any] = {
        "group": authorization.get("apiGroup") or "",
        "resource": authorization.get("resource") or "",
        "subresource": authorization.get("subresource") or "",
        "verb": authorization.get("verb") or "",
        "namespace": target.get("namespace") or "",
        "name": target.get("name") or "",
    }
    if resource_attributes["verb"] == "create":
        resource_attributes.pop("name", None)
    if not resource_attributes["group"]:
        resource_attributes.pop("group", None)
    if not resource_attributes["subresource"]:
        resource_attributes.pop("subresource", None)
    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": resource_attributes},
    }


async def fetch_action_access_review(user_auth_header: str, plan: Mapping[str, Any]) -> dict[str, Any]:
    review_request = build_action_access_review_request(plan)
    if not OPENSHIFT_API_URL:
        return {
            "allowed": not MUTATIONS_ENABLED,
            "enabled": True,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "skipped": True,
            "reason": "OPENSHIFT_API_URL is not configured",
        }

    try:
        async with httpx.AsyncClient(
            verify=OPENSHIFT_API_CA_FILE,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.post(
                f"{OPENSHIFT_API_URL}/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
                headers={
                    "Accept": "application/json",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json=review_request,
            )
    except httpx.RequestError as exc:
        return {
            "allowed": False,
            "enabled": True,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": "OpenShift API unavailable during action access review",
            "evaluationError": json.dumps(
                {
                    "code": "openshift_api_unavailable",
                    "message": "OpenShift API 응답 지연 또는 연결 실패로 action access review를 완료하지 못했습니다.",
                    "operation": "action_access_review",
                    "remediation": "VPN/OCP API 연결을 확인한 뒤 요청을 다시 실행하세요.",
                    "upstreamReason": safe_exception_text(exc),
                },
                ensure_ascii=False,
            ),
        }

    if response.status_code >= 400:
        return {
            "allowed": False,
            "enabled": True,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": f"SelfSubjectAccessReview failed with HTTP {response.status_code}",
            "evaluationError": response.text[:500],
        }

    payload = response.json()
    status_payload = payload.get("status", {}) if isinstance(payload, Mapping) else {}
    status_map = status_payload if isinstance(status_payload, Mapping) else {}
    return {
        "allowed": bool(status_map.get("allowed")),
        "denied": bool(status_map.get("denied")),
        "enabled": True,
        "evaluationError": status_map.get("evaluationError") or "",
        "reason": status_map.get("reason") or "",
        "resourceAttributes": review_request["spec"]["resourceAttributes"],
        "skipped": False,
    }


def enforce_action_access_review(review: Mapping[str, Any]) -> None:
    if review.get("allowed") is True:
        return
    raise HTTPException(
        status_code=403,
        detail={
            "reason": "action_authorization_denied",
            "message": "Approver is not authorized for the exact Kubernetes action.",
            "review": redact_sensitive(dict(review)),
        },
    )


async def fetch_product_access_review(user_auth_header: str) -> dict[str, Any]:
    if not PRODUCT_ACCESS_REVIEW_ENABLED:
        return {
            "allowed": True,
            "enabled": False,
            "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
            "skipped": True,
            "reason": "product access review disabled",
        }

    review_request = build_product_access_review_request()
    if not OPENSHIFT_API_URL:
        return {
            "allowed": not PRODUCT_ACCESS_REVIEW_REQUIRED,
            "enabled": True,
            "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "skipped": True,
            "reason": "OPENSHIFT_API_URL is not configured",
        }

    try:
        async with httpx.AsyncClient(
            verify=OPENSHIFT_API_CA_FILE,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.post(
                f"{OPENSHIFT_API_URL}/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
                headers={
                    "Accept": "application/json",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json=review_request,
            )
    except httpx.RequestError as exc:
        return {
            "allowed": False,
            "enabled": True,
            "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": "OpenShift API unavailable during product access review",
            "evaluationError": json.dumps(
                {
                    "code": "openshift_api_unavailable",
                    "message": "OpenShift API 응답 지연 또는 연결 실패로 product access review를 완료하지 못했습니다.",
                    "operation": "product_access_review",
                    "remediation": "VPN/OCP API 연결을 확인한 뒤 요청을 다시 실행하세요.",
                    "upstreamReason": safe_exception_text(exc),
                },
                ensure_ascii=False,
            ),
        }

    if response.status_code >= 400:
        return {
            "allowed": False,
            "enabled": True,
            "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
            "reason": f"SelfSubjectAccessReview failed with HTTP {response.status_code}",
            "evaluationError": response.text[:500],
        }

    payload = response.json()
    status_payload = payload.get("status", {}) if isinstance(payload, Mapping) else {}
    status_map = status_payload if isinstance(status_payload, Mapping) else {}
    return {
        "allowed": bool(status_map.get("allowed")),
        "denied": bool(status_map.get("denied")),
        "enabled": True,
        "evaluationError": status_map.get("evaluationError") or "",
        "reason": status_map.get("reason") or "",
        "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
        "resourceAttributes": review_request["spec"]["resourceAttributes"],
        "skipped": False,
    }


def product_access_review_status(review: Mapping[str, Any]) -> str:
    if review.get("skipped"):
        return "skipped"
    if review.get("allowed") is True:
        return "success"
    if review.get("required") is True:
        return "error"
    return "warning"


def summarize_product_access_review(review: Mapping[str, Any]) -> str:
    if review.get("enabled") is False:
        return "Product access SSAR is disabled by configuration."

    attributes = review.get("resourceAttributes")
    attributes_text = json.dumps(redact_sensitive(attributes), ensure_ascii=False)
    return "\n".join(
        [
            f"enabled: {review.get('enabled')}",
            f"required: {review.get('required')}",
            f"allowed: {review.get('allowed')}",
            f"denied: {review.get('denied', False)}",
            f"resourceAttributes: {attributes_text}",
            f"reason: {review.get('reason') or '-'}",
            f"evaluationError: {review.get('evaluationError') or '-'}",
        ]
    )


def enforce_product_access_review(review: Mapping[str, Any]) -> None:
    if review.get("required") is True and review.get("allowed") is not True:
        reason = review.get("reason") or review.get("evaluationError") or "product access denied"
        raise HTTPException(status_code=403, detail=f"KOMSCO AI product access denied: {reason}")


OPENSHIFT_USER_AUTH_FAILURE_MESSAGE = (
    "OpenShift 사용자 인증이 만료되었거나 Gateway로 전달된 사용자 토큰이 유효하지 않습니다. "
    "OpenShift 콘솔을 새로고침하거나 다시 로그인한 뒤 요청을 재시도하세요."
)


def build_openshift_user_auth_failure_detail(status_code: int, body: str) -> dict[str, Any]:
    upstream_reason = ""
    try:
        payload = json.loads(body)
        if isinstance(payload, Mapping):
            upstream_reason = str(payload.get("reason") or payload.get("message") or "")
    except json.JSONDecodeError:
        upstream_reason = body[:120]
    return {
        "code": "openshift_user_auth_failed",
        "message": OPENSHIFT_USER_AUTH_FAILURE_MESSAGE,
        "remediation": "OpenShift 콘솔 세션을 갱신한 뒤 AIOps 요청을 다시 실행하세요.",
        "upstreamStatus": status_code,
        "upstreamReason": redact_sensitive(upstream_reason),
    }


def build_openshift_api_unavailable_detail(operation: str, exc: BaseException) -> dict[str, Any]:
    return {
        "code": "openshift_api_unavailable",
        "message": "OpenShift API 응답 지연 또는 연결 실패로 Gateway가 현재 클러스터 증거를 수집하지 못했습니다.",
        "operation": operation,
        "remediation": "VPN/OCP API 연결을 확인한 뒤 요청을 다시 실행하세요.",
        "upstreamReason": safe_exception_text(exc),
    }


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
    detail = exc.detail
    if isinstance(detail, Mapping):
        message = detail.get("message")
        if message:
            return str(message)
        return json.dumps(redact_sensitive(detail), ensure_ascii=False)
    return str(detail) or exc.__class__.__name__


def is_openshift_user_auth_failure(exc: HTTPException) -> bool:
    detail = exc.detail
    return (
        exc.status_code == 401
        and isinstance(detail, Mapping)
        and detail.get("code") == "openshift_user_auth_failed"
    )


async def fetch_self_subject_review(user_auth_header: str) -> dict[str, Any]:
    if not OPENSHIFT_API_URL:
        return safe_subject(None)

    try:
        async with httpx.AsyncClient(
            verify=OPENSHIFT_API_CA_FILE,
            timeout=httpx.Timeout(10.0, connect=5.0),
        ) as client:
            response = await client.post(
                f"{OPENSHIFT_API_URL}/apis/authentication.k8s.io/v1/selfsubjectreviews",
                headers={
                    "Accept": "application/json",
                    "Authorization": user_auth_header,
                    "Content-Type": "application/json",
                },
                json={
                    "apiVersion": "authentication.k8s.io/v1",
                    "kind": "SelfSubjectReview",
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=504,
            detail=build_openshift_api_unavailable_detail("self_subject_review", exc),
        ) from exc

    if response.status_code >= 400:
        body = response.text[:500]
        if response.status_code == 401:
            raise HTTPException(
                status_code=401,
                detail=build_openshift_user_auth_failure_detail(response.status_code, body),
            )
        raise HTTPException(
            status_code=response.status_code,
            detail=f"OpenShift subject review failed: {body}",
        )

    payload = response.json()
    user_info = payload.get("status", {}).get("userInfo", {}) if isinstance(payload, Mapping) else {}
    return safe_subject(user_info if isinstance(user_info, Mapping) else None)


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
    if not live_review:
        return "OPENSHIFT_API_URL 미설정: bearer 형식만 확인했고 live SelfSubjectReview는 건너뜀"

    return "\n".join(
        [
            f"username: {subject.get('username')}",
            f"uid: {subject.get('uid')}",
            f"groupsDigest: {subject.get('groupsDigest')}",
            f"authenticatedByCluster: {subject.get('authenticatedByCluster')}",
        ]
    )


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


@app.get("/v1/cluster/summary")
async def cluster_summary(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        (
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
        ) = await asyncio.gather(
            fetch_ocp_json(
                client,
                "/api/v1/nodes",
                user_auth_header,
                required=True,
            ),
            fetch_ocp_json(
                client,
                "/apis/metrics.k8s.io/v1beta1/nodes",
                user_auth_header,
            ),
            fetch_ocp_json(
                client,
                "/apis/config.openshift.io/v1/clusterversions/version",
                user_auth_header,
            ),
            fetch_ocp_json(
                client,
                "/apis/config.openshift.io/v1/clusteroperators",
                user_auth_header,
            ),
            fetch_ocp_json(client, "/api/v1/pods", user_auth_header),
            fetch_ocp_json(client, "/apis/apps/v1/deployments", user_auth_header),
            fetch_ocp_json(client, "/apis/apps/v1/replicasets", user_auth_header),
            fetch_ocp_json(client, "/apis/apps/v1/daemonsets", user_auth_header),
            fetch_ocp_json(client, "/apis/apps/v1/statefulsets", user_auth_header),
            fetch_ocp_json(client, "/api/v1/services", user_auth_header),
            fetch_ocp_json(client, "/apis/route.openshift.io/v1/routes", user_auth_header),
            fetch_ocp_json(client, "/api/v1/persistentvolumeclaims", user_auth_header),
            fetch_ocp_json(client, "/api/v1/namespaces", user_auth_header),
        )

    return build_cluster_summary(
        nodes_payload or {"items": []},
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
    )


@app.get("/v1/aiops/overview")
async def aiops_overview(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        nodes_payload, nodes_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/nodes",
            user_auth_header,
            label="Node inventory",
            name="nodes",
            required=True,
        )
        node_metrics_payload, metrics_status = await fetch_ocp_json_observed(
            client,
            "/apis/metrics.k8s.io/v1beta1/nodes",
            user_auth_header,
            label="Node metrics",
            name="metrics.k8s.io",
        )
        cluster_version_payload, version_status = await fetch_ocp_json_observed(
            client,
            "/apis/config.openshift.io/v1/clusterversions/version",
            user_auth_header,
            label="Cluster version",
            name="clusterversion",
        )
        cluster_operators_payload, operators_status = await fetch_ocp_json_observed(
            client,
            "/apis/config.openshift.io/v1/clusteroperators",
            user_auth_header,
            label="Cluster operators",
            name="clusteroperators",
        )
        monitoring_config_payload, monitoring_config_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config",
            user_auth_header,
            label="Monitoring public URLs",
            name="monitoring-shared-config",
        )
        pods_payload, pods_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/pods?limit=500",
            user_auth_header,
            label="Pod anomaly signals",
            name="pods",
            required=True,
        )
        events_payload, events_status = await fetch_ocp_json_observed(
            client,
            "/api/v1/events?limit=500",
            user_auth_header,
            label="Warning events",
            name="events",
            required=True,
        )

    monitoring_urls = monitoring_urls_from_config(monitoring_config_payload)
    monitoring_probe = await probe_thanos_query(monitoring_urls.get("thanos", ""), user_auth_header)
    alerts_probe = await query_thanos_instant(
        monitoring_urls.get("thanos", ""),
        user_auth_header,
        'ALERTS{alertstate="firing"}',
    )
    restart_probe = await query_thanos_instant(
        monitoring_urls.get("thanos", ""),
        user_auth_header,
        "increase(kube_pod_container_status_restarts_total[1h]) > 0",
    )
    monitoring_probe_status = data_source_status(
        label="Thanos query probe",
        name="thanos-query",
        path="/api/v1/query?query=up",
        payload=monitoring_probe if monitoring_probe.get("status") == "available" else None,
        reason=str(monitoring_probe.get("reason") or ""),
        status=str(monitoring_probe.get("status") or "unavailable"),
        http_status=monitoring_probe.get("httpStatus")
        if isinstance(monitoring_probe.get("httpStatus"), int)
        else None,
    )
    alerts_probe_status = data_source_status(
        label="Active alerts",
        name="alerts",
        path='/api/v1/query?query=ALERTS{alertstate="firing"}',
        payload=alerts_probe if alerts_probe.get("status") == "available" else None,
        reason=str(alerts_probe.get("reason") or ""),
        status=str(alerts_probe.get("status") or "unavailable"),
        http_status=alerts_probe.get("httpStatus")
        if isinstance(alerts_probe.get("httpStatus"), int)
        else None,
    )
    restart_probe_status = data_source_status(
        label="Restart increase metric",
        name="restart-metrics",
        path="/api/v1/query?query=increase(kube_pod_container_status_restarts_total[1h]) > 0",
        payload=restart_probe if restart_probe.get("status") == "available" else None,
        reason=str(restart_probe.get("reason") or ""),
        status=str(restart_probe.get("status") or "unavailable"),
        http_status=restart_probe.get("httpStatus")
        if isinstance(restart_probe.get("httpStatus"), int)
        else None,
    )

    summary = build_cluster_summary(
        nodes_payload or {"items": []},
        node_metrics_payload,
        cluster_version_payload,
        cluster_operators_payload,
    )
    data_sources = [
        nodes_status,
        metrics_status,
        version_status,
        operators_status,
        monitoring_config_status,
        monitoring_probe_status,
        pods_status,
        events_status,
        alerts_probe_status,
        restart_probe_status,
    ]
    anomaly_summary = build_aiops_anomaly_summary(
        summary,
        pods_payload,
        events_payload,
        alerts_probe,
        restart_probe,
        data_sources,
    )

    return build_aiops_overview(
        summary,
        data_sources,
        monitoring_urls,
        monitoring_probe,
        anomaly_summary,
    )


@app.get("/v1/aiops/anomalies")
async def aiops_anomalies(
    authorization: str | None = Header(default=None),
    namespace: str | None = Query(default=None),
    since_minutes: int = Query(default=60, alias="sinceMinutes", ge=1, le=1440),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    overview = await aiops_overview(authorization)
    anomalies = overview.get("spec", {}).get("anomalies")
    if not isinstance(anomalies, dict):
        return {}

    filtered = dict(anomalies)
    spec = dict(filtered.get("spec", {})) if isinstance(filtered.get("spec"), Mapping) else {}
    findings = spec.get("findings") if isinstance(spec.get("findings"), list) else []
    if namespace:
        findings = [
            finding
            for finding in findings
            if isinstance(finding, Mapping)
            and (
                finding.get("namespace") == namespace
                or not finding.get("namespace")
                or str(finding.get("namespace")) == "cluster-scoped"
            )
        ]
    spec["findings"] = findings[:limit]
    spec["query"] = {
        "limit": limit,
        "namespace": namespace or "",
        "sinceMinutes": since_minutes,
    }
    filtered["spec"] = spec
    return filtered


@app.get("/v1/aiops/action-candidates")
async def aiops_action_candidates(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    overview = await aiops_overview(authorization)
    action_candidates = overview.get("spec", {}).get("actionCandidates")
    if not isinstance(action_candidates, dict):
        return {}
    return merge_recent_namespace_cleanup_candidates(action_candidates)


@app.get("/v1/auth/subject")
async def auth_subject(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    return await fetch_self_subject_review(user_auth_header)


@app.get("/v1/evidence")
async def list_evidence(
    authorization: str | None = Header(default=None),
    incident_id: str | None = Query(default=None, alias="incidentId"),
    run_id: str | None = Query(default=None, alias="runId"),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    items = []
    for record in EVIDENCE_RECORDS.values():
        if incident_id and record.get("incidentId") != incident_id:
            continue
        if run_id and record.get("runId") != run_id:
            continue
        if not can_subject_read_record(record, subject):
            continue
        items.append({key: value for key, value in record.items() if key != "detail"})

    return {
        "apiVersion": "aiops.komsco/v1",
        "items": items,
        "kind": "EvidenceReferenceList",
    }


@app.get("/v1/evidence/{evidence_id}")
async def get_evidence(
    evidence_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = EVIDENCE_RECORDS.get(evidence_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Evidence not found")

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "Evidence",
        "metadata": {"name": evidence_id},
        "spec": record,
    }


@app.get("/v1/workflows/{run_id}")
async def get_workflow(
    run_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = WORKFLOW_RECORDS.get(run_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "Workflow",
        "metadata": {"name": run_id},
        "spec": record,
    }


@app.get("/v1/diagnostics/collectors")
async def get_diagnostic_collectors(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "HostDiagnosticCollectorRegistry",
        "metadata": {
            "name": "host-diagnostic-collector-registry",
            "version": HOST_DIAGNOSTIC_COLLECTOR_VERSION,
        },
        "spec": {
            "digest": HOST_DIAGNOSTIC_COLLECTOR_DIGEST,
            "diagnosticsEnabled": DIAGNOSTICS_ENABLED,
            "controllerConfigured": bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
            "collectors": list(HOST_DIAGNOSTIC_COLLECTORS.values()),
        },
    }


@app.post("/v1/diagnostics/requests")
async def create_diagnostic_request(
    req: DiagnosticRequestCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_diagnostic_request_record(req, subject)
    record = await submit_diagnostic_request_to_controller(record)
    request_id = str(record["metadata"]["name"])
    await bounded_put_record("diagnosticRequests", request_id, record)
    increment_metric("aiops_diagnostic_requests_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/diagnostics/requests/{request_id}")
async def get_diagnostic_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = DIAGNOSTIC_REQUESTS.get(request_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Diagnostic request not found")
    record = await refresh_diagnostic_request_from_controller(record)
    await bounded_put_record("diagnosticRequests", request_id, record)

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


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
    detail = exc.detail
    if isinstance(detail, Mapping):
        safe_detail: Any = redact_sensitive(dict(detail))
    else:
        safe_detail = http_exception_message(exc)
    return {
        "status": "degraded",
        "recordsVisible": False,
        "reason": "OpenShift subject review unavailable; runtime safety status is returned without user-scoped records.",
        "subjectReview": {
            "ok": False,
            "statusCode": exc.status_code,
            "detail": safe_detail,
        },
    }


def build_skipped_product_access_review(reason: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "enabled": PRODUCT_ACCESS_REVIEW_ENABLED,
        "required": PRODUCT_ACCESS_REVIEW_REQUIRED,
        "resourceAttributes": build_product_access_review_request()["spec"]["resourceAttributes"],
        "skipped": True,
        "reason": reason,
    }


def compact_event_detail(value: Any, *, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def parse_kubernetes_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def aiops_event_timestamp(event: Mapping[str, Any]) -> str:
    for key in ("eventTime", "lastTimestamp", "firstTimestamp"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value

    metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), Mapping) else {}
    value = metadata.get("creationTimestamp")
    return str(value or now_rfc3339())


def aiops_event_involved_target(event: Mapping[str, Any]) -> tuple[str, str, str, str]:
    metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), Mapping) else {}
    involved = event.get("involvedObject", {})
    involved = involved if isinstance(involved, Mapping) else {}
    namespace = str(involved.get("namespace") or metadata.get("namespace") or "")
    kind = str(involved.get("kind") or "Resource")
    name = str(involved.get("name") or metadata.get("name") or "unknown")
    target = f"{kind}/{name}" if not namespace else f"{namespace}/{kind}/{name}"
    return namespace, kind, name, target


def aiops_event_severity(reason: str, event_type: str, message: str = "") -> str:
    text = f"{reason} {event_type} {message}".lower()
    risk_tokens = (
        "crashloopbackoff",
        "errimagepull",
        "failed",
        "failedmount",
        "failedscheduling",
        "imagepullbackoff",
        "oomkilled",
        "unhealthy",
    )
    warn_tokens = ("backoff", "notready", "unavailable", "warning")
    if any(token in text for token in risk_tokens):
        return "risk"
    if str(event_type).lower() == "warning" or any(token in text for token in warn_tokens):
        return "warn"
    return "ok"


def build_kubernetes_event_items(
    events_payload: Mapping[str, Any] | None,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    ok_budget = max(2, limit // 10)
    ok_count = 0
    for event in resource_items(events_payload):
        metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), Mapping) else {}
        reason = str(event.get("reason") or "Event")
        event_type = str(event.get("type") or "Normal")
        message = compact_event_detail(event.get("message"))
        namespace, kind, name, target = aiops_event_involved_target(event)
        severity = aiops_event_severity(reason, event_type, message)
        if severity == "ok":
            if ok_count >= ok_budget:
                continue
            ok_count += 1

        event_id = str(metadata.get("uid") or f"{namespace}-{kind}-{name}-{reason}-{aiops_event_timestamp(event)}")
        items.append(
            {
                "category": "event",
                "detail": message or f"{event_type} event observed.",
                "id": f"k8s-event-{event_id}",
                "namespace": namespace,
                "severity": severity,
                "source": "Kubernetes Event",
                "target": target,
                "time": aiops_event_timestamp(event),
                "title": f"{reason} · {kind}/{name}",
            }
        )

    items.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return items[:limit]


def pod_container_signal_summary(pod: Mapping[str, Any]) -> str:
    status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
    statuses = status.get("containerStatuses")
    if not isinstance(statuses, list):
        return "-"

    signals: list[str] = []
    for container_status in statuses:
        if not isinstance(container_status, Mapping):
            continue
        name = str(container_status.get("name") or "container")
        state = state_summary(container_status)
        last_state, _finished_at = last_termination_summary(container_status)
        restarts = int(container_status.get("restartCount") or 0)
        if state == "running" and restarts < 3 and last_state == "-":
            continue
        suffix = f"{name} {state} restart={restarts}"
        if last_state != "-":
            suffix = f"{suffix} last={last_state}"
        signals.append(suffix)

    return "; ".join(signals[:4]) if signals else "-"


def pod_has_recent_restart(pod: Mapping[str, Any], *, hours: int = 6) -> bool:
    status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
    statuses = status.get("containerStatuses")
    if not isinstance(statuses, list):
        return False

    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    for container_status in statuses:
        if not isinstance(container_status, Mapping):
            continue
        if int(container_status.get("restartCount") or 0) <= 0:
            continue
        _last_state, finished_at = last_termination_summary(container_status)
        finished_at_dt = parse_kubernetes_timestamp(finished_at)
        if finished_at_dt is not None and finished_at_dt >= cutoff:
            return True

    return False


def is_openshift_build_pod(pod: Mapping[str, Any]) -> bool:
    metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
    labels = metadata.get("labels", {}) if isinstance(metadata.get("labels"), Mapping) else {}
    owner_refs = metadata.get("ownerReferences", [])
    if labels.get("openshift.io/build.name") or labels.get("openshift.io/build-config.name"):
        return True
    if labels.get("buildconfig") and str(metadata.get("name") or "").endswith("-build"):
        return True
    if isinstance(owner_refs, list):
        return any(isinstance(ref, Mapping) and str(ref.get("kind") or "").lower() == "build" for ref in owner_refs)
    return False


def build_problem_pod_event_items(
    pods_payload: Mapping[str, Any] | None,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    observed_at = now_rfc3339()
    for pod in resource_items(pods_payload):
        metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        name = str(metadata.get("name") or "")
        namespace = str(metadata.get("namespace") or "")
        if is_openshift_build_pod(pod):
            continue
        phase = str(status.get("phase") or "Unknown")
        restarts = pod_restart_total(pod)
        ready = pod_ready_summary(pod)
        terminating = pod_is_terminating(pod)
        recent_restart = pod_has_recent_restart(pod)
        problem = (
            terminating
            or phase not in {"Running", "Succeeded"}
            or (phase == "Running" and not pod_is_fully_ready(pod))
            or (phase != "Succeeded" and restarts >= 3 and recent_restart)
        )
        if not problem:
            continue

        created_at = str(metadata.get("creationTimestamp") or now_rfc3339())
        created_at_dt = parse_kubernetes_timestamp(created_at)
        if (
            phase in {"Failed", "Succeeded"}
            and created_at_dt is not None
            and datetime.now(UTC) - created_at_dt > timedelta(hours=24)
        ):
            continue

        container_signal = pod_container_signal_summary(pod)
        ready_count, ready_total = pod_ready_numbers(pod)
        signal_text = container_signal.lower()
        severity = (
            "risk"
            if (
                phase in {"Failed", "Unknown"}
                or (phase == "Running" and ready_total > 0 and ready_count == 0 and restarts > 0)
                or any(token in signal_text for token in ("crashloopbackoff", "errimagepull", "imagepullbackoff", "oomkilled"))
            )
            else "warn"
        )
        if (phase == "Pending" or terminating) and severity != "risk":
            severity = "warn"
        target = f"{namespace}/Pod/{name}" if namespace else f"Pod/{name}"
        detail_parts = [
            f"phase={phase}",
            f"ready={ready}",
            f"restart={restarts}",
            f"created={created_at}",
            "terminating=true" if terminating else "",
            pod_container_signal_summary(pod),
        ]
        items.append(
            {
                "category": "pod",
                "detail": compact_event_detail(" · ".join(part for part in detail_parts if part and part != "-")),
                "id": f"pod-signal-{namespace}-{name}",
                "namespace": namespace,
                "severity": severity,
                "source": "Pod status",
                "target": target,
                "time": observed_at,
                "title": f"Pod 상태 이상 · {name}",
            }
        )

    severity_order = {"risk": 2, "warn": 1, "ok": 0}
    items.sort(
        key=lambda item: (
            severity_order.get(str(item.get("severity") or "ok"), 0),
            str(item.get("time") or ""),
        ),
        reverse=True,
    )
    return items[:limit]


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


@app.get("/v1/aiops/events")
async def get_aiops_events(
    authorization: str | None = Header(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    product_access_review = await fetch_product_access_review(user_auth_header)
    product_access_allowed = bool(product_access_review.get("allowed"))

    events_payload: Mapping[str, Any] | None = None
    pods_payload: Mapping[str, Any] | None = None
    sources = ["AIOps Gateway"]
    if OPENSHIFT_API_URL:
        async with httpx.AsyncClient(
            verify=OPENSHIFT_API_CA_FILE,
            timeout=httpx.Timeout(20.0, connect=5.0),
        ) as client:
            events_payload, pods_payload = await asyncio.gather(
                fetch_ocp_json(client, "/api/v1/events?limit=500", user_auth_header),
                fetch_ocp_json(client, "/api/v1/pods", user_auth_header),
            )
        sources.extend(["Kubernetes Event", "Pod status"])

    items = [
        *build_kubernetes_event_items(events_payload, limit=limit),
        *build_problem_pod_event_items(pods_payload, limit=limit),
        *build_aiops_record_event_items(
            subject,
            product_access_allowed=product_access_allowed,
            limit=limit,
        ),
    ]
    items.sort(
        key=lambda item: (
            str(item.get("time") or ""),
            str(item.get("source") or ""),
        ),
        reverse=True,
    )

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsEventFeed",
        "metadata": {
            "generatedAt": now_rfc3339(),
            "name": "activity-feed",
        },
        "spec": {
            "items": items[:limit],
            "pollIntervalSeconds": 30,
            "sources": sources,
        },
    }


@app.get("/v1/aiops/status")
async def get_aiops_status(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    access_review_status: dict[str, Any] = {
        "status": "success",
        "recordsVisible": True,
        "reason": "",
    }
    try:
        subject = await fetch_self_subject_review(user_auth_header)
    except HTTPException as exc:
        subject = safe_subject(None)
        product_access_review = build_skipped_product_access_review(
            "not evaluated because OpenShift subject review is unavailable"
        )
        product_access_allowed = False
        access_review_status = build_status_access_review_failure(exc)
    else:
        product_access_review = await fetch_product_access_review(user_auth_header)
        product_access_allowed = bool(product_access_review.get("allowed"))
        if product_access_review.get("evaluationError"):
            access_review_status = {
                "status": "degraded",
                "recordsVisible": product_access_allowed,
                "reason": "OpenShift product access review returned an evaluation error.",
                "productAccessReview": redact_sensitive(product_access_review),
            }
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsRuntimeStatus",
        "metadata": {
            "name": "runtime-status",
            "generatedAt": now_rfc3339(),
        },
        "spec": {
            "capabilities": {
                "mutationsEnabled": MUTATIONS_ENABLED,
                "diagnosticsEnabled": DIAGNOSTICS_ENABLED,
                "diagnosticsControllerConfigured": bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
                "actionExecutorConfigured": bool(ACTION_EXECUTOR_URL),
                "unrestrictedCommandsEnabled": UNRESTRICTED_COMMANDS_ENABLED,
                "recordStoreEnabled": RECORD_STORE_ENABLED,
                "recordStoreConfigMap": RECORD_STORE_CONFIGMAP if RECORD_STORE_ENABLED else "",
                "chatTranscriptJsonlPath": CHAT_TRANSCRIPT_JSONL_PATH,
                "rag": build_rag_backend_status(),
            },
            "safetyContract": build_runtime_safety_contract(
                mutations_enabled=MUTATIONS_ENABLED,
                unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
                diagnostics_enabled=DIAGNOSTICS_ENABLED,
                record_store_enabled=RECORD_STORE_ENABLED,
                diagnostics_controller_configured=bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
                lightspeed_status=redact_sensitive(dict(OLS_STREAM_STATUS)),
                latest_runtime_tool_plan=LAST_RUNTIME_TOOL_PLAN,
                latest_rca_context=LAST_RCA_CONTEXT,
            ),
            "accessReviewStatus": access_review_status,
            "productAccessReview": redact_sensitive(product_access_review),
            "subject": redact_sensitive(dict(subject)),
            "records": {
                "auditRecords": latest_readable_audit_records(
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "chatTranscripts": latest_readable_records(
                    CHAT_TRANSCRIPTS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "chatFeedback": latest_readable_records(
                    CHAT_FEEDBACK,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "diagnosticRequests": latest_readable_records(
                    DIAGNOSTIC_REQUESTS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "actionProposals": latest_readable_records(
                    ACTION_PROPOSALS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "sealedActionPlans": latest_readable_records(
                    SEALED_ACTION_PLANS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "approvalDecisions": latest_readable_records(
                    APPROVAL_DECISIONS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
                "executionRecords": latest_readable_records(
                    EXECUTION_RECORDS,
                    subject,
                    product_access_allowed=product_access_allowed,
                ),
            },
        },
    }


@app.get("/v1/actions/registry")
async def get_action_registry(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionRegistry",
        "metadata": {
            "name": "mutation-action-registry",
            "version": ACTION_REGISTRY_VERSION,
        },
        "spec": {
            "digest": ACTION_REGISTRY_DIGEST,
            "mutationsEnabled": MUTATIONS_ENABLED,
            "entries": list(ACTION_REGISTRY_ENTRIES.values()),
        },
    }


@app.post("/v1/actions/proposals")
async def create_action_proposal(
    req: ActionProposalCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_action_proposal_record(req, subject)
    proposal_id = str(record["metadata"]["name"])
    await bounded_put_record("actionProposals", proposal_id, record)
    increment_metric("aiops_action_proposals_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionProposal",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/actions/candidate-plans")
async def create_action_candidate_plan(
    req: ActionCandidatePlanCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    return await create_plan_from_action_candidate(req, user_auth_header, subject)


@app.get("/v1/actions/proposals/{proposal_id}")
async def get_action_proposal(
    proposal_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = ACTION_PROPOSALS.get(proposal_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Action proposal not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionProposal",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/actions/plans")
async def create_action_plan(
    req: SealedActionPlanCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    proposal = ACTION_PROPOSALS.get(req.proposalId)
    if not proposal or not can_subject_read_record(proposal, subject):
        raise HTTPException(status_code=404, detail="Action proposal not found")
    record = build_sealed_action_plan_record(proposal)
    plan_id = str(record["metadata"]["name"])
    await bounded_put_record("sealedActionPlans", plan_id, record)
    increment_metric("aiops_action_plans_total")
    auto_result = await maybe_auto_approve_and_execute(record, user_auth_header)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "SealedActionPlan",
        "metadata": record["metadata"],
        "spec": {**record["spec"], **(auto_result or {})},
    }


@app.get("/v1/actions/plans/{plan_id}")
async def get_action_plan(
    plan_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = SEALED_ACTION_PLANS.get(plan_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "SealedActionPlan",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


async def _create_approval_decision_impl(
    req: "ApprovalDecisionCreate",
    user_auth_header: str,
    *,
    auto_policy: bool = False,
) -> dict[str, Any]:
    subject = await fetch_self_subject_review(user_auth_header)
    product_access_review = await fetch_product_access_review(user_auth_header)
    if APPROVAL_ACCESS_REVIEW_REQUIRED:
        enforce_product_access_review(
            {
                **product_access_review,
                "required": True,
            }
        )
    plan = SEALED_ACTION_PLANS.get(req.planId)
    if not plan:
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    if not can_subject_read_record(plan, subject) and product_access_review.get("allowed") is not True:
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    plan_digest = plan["spec"]["sealedActionPlan"]["digest"]["planDigest"]
    if req.expectedPlanDigest != plan_digest:
        raise HTTPException(status_code=409, detail="expectedPlanDigest does not match the sealed plan")
    plan_created_at = record_created_at(plan)
    if plan_has_approval_status(plan_digest, {"rejected"}, not_before=plan_created_at):
        raise HTTPException(status_code=409, detail="Action plan has been rejected")
    existing_approval = find_approval_by_plan_status(
        plan_digest,
        {"approved", "executed"},
        not_before=plan_created_at,
    )
    if existing_approval is not None:
        return {
            "apiVersion": "aiops.komsco/v1",
            "kind": "ApprovalDecision",
            "metadata": existing_approval["metadata"],
            "spec": existing_approval["spec"],
        }
    action_access_review = await fetch_action_access_review(
        user_auth_header,
        plan["spec"]["sealedActionPlan"],
    )
    enforce_action_access_review(action_access_review)
    action = plan["spec"]["sealedActionPlan"].get("action", {})
    review_only_action = (
        isinstance(action, Mapping)
        and str(action.get("toolName") or "")
        in {
            "namespace_cleanup_review",
            "test_pod_create_review",
            "pod_diagnostic_review",
            "pod_fix_or_rollback_review",
        }
    )
    record = build_approval_decision_record_for_context(
        ApprovalDecisionRecordInput(
            plan_record=plan,
            request=req,
            approver=subject,
            action_access_review=action_access_review,
            context=action_record_context(),
            allow_self_approval=auto_policy or review_only_action,
            auto_policy=auto_policy,
        )
    )
    approval_id = str(record["metadata"]["name"])
    await bounded_put_record("approvalDecisions", approval_id, record)
    increment_metric("aiops_approval_decisions_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ApprovalDecision",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/actions/approvals")
async def create_approval_decision(
    req: ApprovalDecisionCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    unrestricted_auto_policy = req.approvalScope == "lab-auto-unrestricted"
    if unrestricted_auto_policy and not UNRESTRICTED_COMMANDS_ENABLED:
        raise HTTPException(
            status_code=403,
            detail="lab-auto-unrestricted approval requires unrestricted command gate",
        )
    return await _create_approval_decision_impl(
        req,
        user_auth_header,
        auto_policy=unrestricted_auto_policy,
    )


@app.post("/v1/actions/rejections")
async def reject_action_plan(
    req: ActionRejectionCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    product_access_review = await fetch_product_access_review(user_auth_header)
    product_access_allowed = bool(product_access_review.get("allowed"))
    plan = SEALED_ACTION_PLANS.get(req.planId)
    if not plan or (
        not can_subject_read_record(plan, subject) and not product_access_allowed
    ):
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    plan_digest = plan["spec"]["sealedActionPlan"]["digest"]["planDigest"]
    if plan_has_approval_status(
        plan_digest,
        {"approved", "executed"},
        not_before=record_created_at(plan),
    ):
        raise HTTPException(status_code=409, detail="Action plan already has an active approval")
    record = build_action_rejection_record(plan, req, subject)
    rejection_id = str(record["metadata"]["name"])
    await bounded_put_record("approvalDecisions", rejection_id, record)
    increment_metric("aiops_approval_decisions_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ApprovalDecision",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


async def _execute_action_impl(
    req: "ActionExecutionCreate",
    user_auth_header: str,
    *,
    auto_policy: bool = False,
) -> dict[str, Any]:
    subject = await fetch_self_subject_review(user_auth_header)
    product_access_review = await fetch_product_access_review(user_auth_header)
    product_access_allowed = bool(product_access_review.get("allowed"))
    plan = SEALED_ACTION_PLANS.get(req.planId)
    approval = APPROVAL_DECISIONS.get(req.approvalId)
    if not plan or (
        not can_subject_read_record(plan, subject) and not product_access_allowed
    ):
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    if not approval or (
        not can_subject_read_record(approval, subject) and not product_access_allowed
    ):
        raise HTTPException(status_code=404, detail="Approval decision not found")

    sealed_plan = plan["spec"]["sealedActionPlan"]
    plan_digest = sealed_plan["digest"]["planDigest"]
    approval_decision = approval["spec"]["approvalDecision"]
    if req.expectedPlanDigest != plan_digest or approval_decision["planDigest"] != plan_digest:
        raise HTTPException(status_code=409, detail="Execution request is stale for this sealed plan")
    if approval_decision["status"] != "approved":
        raise HTTPException(status_code=409, detail="Approval decision is not approved")
    validate_approval_is_active(approval_decision)
    if approval_already_executed(req.approvalId):
        raise HTTPException(status_code=409, detail="Approval decision has already been used for execution")
    execution_access_review = await fetch_action_access_review(user_auth_header, sealed_plan)
    enforce_action_access_review(execution_access_review)
    validate_execution_evidence_freshness(sealed_plan)

    grant_reference = build_execution_grant_reference_for_context(
        ExecutionGrantInput(
            approval=approval,
            plan=plan,
            approver=subject,
            context=action_record_context(),
        )
    )
    execution_id = f"execution-{uuid.uuid4()}"
    review_only_execution = sealed_plan_is_review_only(sealed_plan)
    if MUTATIONS_ENABLED or review_only_execution:
        executor_result = await execute_action_with_executor(
            sealed_plan,
            grant_reference,
            fallback_authorization=user_auth_header,
        )
    else:
        executor_result = {
            "mutationOutcome": {
                "status": "mutation_disabled",
                "reason": "KOMSCO_AI_ENABLE_MUTATIONS is false.",
            },
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False},
        }
    record = {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutionRecord",
        "metadata": {"name": execution_id, "createdAt": now_rfc3339()},
        "spec": {
            "executionId": execution_id,
            "approvalId": req.approvalId,
            "planId": req.planId,
            "planDigest": plan_digest,
            "executionGrantRef": {
                key: value for key, value in grant_reference.items() if key != "claims"
            },
            "mutationOutcome": executor_result["mutationOutcome"],
            "remediationOutcome": executor_result["remediationOutcome"],
            "executorTrace": redact_sensitive(executor_result.get("executorTrace") or {}),
            "executionAuthorization": redact_sensitive(execution_access_review),
            **(
                {
                    "decidedBy": "auto-policy",
                    "decisionPolicy": {
                        "toolName": sealed_plan["action"].get("toolName"),
                        "triggeredBy": "sealed-plan-creation",
                    },
                }
                if auto_policy
                else {}
            ),
        },
        "subject": redact_sensitive(dict(subject)),
    }
    await bounded_put_record("executionRecords", execution_id, record)
    approval_decision["status"] = "executed"
    approval_decision["executedAt"] = record["metadata"]["createdAt"]
    await bounded_put_record("approvalDecisions", req.approvalId, approval)
    increment_metric("aiops_execution_requests_total")
    if not MUTATIONS_ENABLED and not review_only_execution:
        raise HTTPException(status_code=403, detail=record["spec"])
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutionRecord",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/actions/execute")
async def execute_action(
    req: ActionExecutionCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    return await _execute_action_impl(req, user_auth_header)


def has_recent_auto_action_for_target(
    target: Mapping[str, Any],
    tool_name: str,
    *,
    window_seconds: int = 180,
) -> bool:
    """True if an auto-policy approval already exists for this exact target
    and tool within the last `window_seconds`. Used inside the per-target lock
    in `maybe_auto_approve_and_execute` so two near-simultaneous requests for
    the same target (e.g. a retried webhook, or two overlapping chat turns)
    can't each independently auto-execute their own separate sealed plan.
    """
    now = datetime.now(UTC)
    for record in APPROVAL_DECISIONS.values():
        decision = record.get("spec", {}).get("approvalDecision", {})
        if decision.get("decidedBy") != "auto-policy":
            continue
        decision_target = decision.get("target") or {}
        if (
            decision_target.get("namespace") != target.get("namespace")
            or decision_target.get("name") != target.get("name")
            or decision_target.get("kind") != target.get("kind")
        ):
            continue
        if decision.get("action", {}).get("toolName") != tool_name:
            continue
        try:
            approved_at = datetime.fromisoformat(str(decision.get("approvedAt", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - approved_at).total_seconds() <= window_seconds:
            return True
    return False


async def verify_source_type_for_target(
    user_auth_header: str, target: Mapping[str, Any]
) -> str | None:
    """Look up the live, server-computed action-candidates list and return the
    real sourceType for this target, rather than trusting any client-supplied
    value. Returns None if the target isn't currently listed as an action
    candidate (already resolved, or the lookup itself fails), so callers can
    fail closed instead of trusting an unverifiable claim.
    """
    try:
        candidates = await aiops_action_candidates(user_auth_header)
    except Exception:  # noqa: BLE001
        return None
    namespace = target.get("namespace")
    name = target.get("name")
    for candidate in candidates.get("spec", {}).get("candidates", []) or []:
        candidate_target = candidate.get("target") or {}
        if candidate_target.get("namespace") == namespace and candidate_target.get("name") == name:
            return candidate.get("sourceType")
    return None


async def maybe_auto_approve_and_execute(
    plan_record: Mapping[str, Any],
    user_auth_header: str,
) -> dict[str, Any] | None:
    """If the sealed plan's tool is on the narrow AUTO_EXECUTE_TOOL_NAMES
    allowlist (empty/off by default), skip the human approve/execute clicks
    and drive the same internal approval + execution logic immediately.
    Every server-side check those two paths already perform (mutation gate,
    action executor availability, target liveness, approval expiry/reuse)
    still runs unchanged; only the human click is skipped. Returns None when
    the plan isn't eligible, so callers should treat that as "do nothing."

    `evict_one_unhealthy_controller_owned_pod` is reused for every unhealthy
    Pod target regardless of why it's unhealthy, but eviction only helps
    transient/restart-recoverable states (crashloop, restart spikes) — it does
    nothing for a persistent-failure state like ImagePullBackOff (bad image,
    registry down) and would just churn the pod forever. So beyond the tool
    allowlist, this tool specifically also requires the finding's sourceType
    to be one of the transient-restart categories.

    The `source_type` parameter as passed in by callers is caller-supplied (it
    round-trips through client-controlled request fields), so it is NEVER
    trusted for the eligibility decision below. The real check re-derives
    sourceType from the live, server-computed action-candidates list keyed by
    this plan's actual target, so a caller can't defeat the persistent-failure
    guard by mislabeling a request's sourceType. If the target can't be
    matched against a current server-computed finding at all (e.g. it already
    resolved, or the candidates lookup errors), this fails closed — the
    eviction stays ineligible for auto-execute and falls back to the normal
    manual approve/execute flow.
    """
    if not MUTATIONS_ENABLED:
        return None

    plan = plan_record["spec"]["sealedActionPlan"]
    tool_name = plan["action"].get("toolName")
    if not tool_name or tool_name not in AUTO_EXECUTE_TOOL_NAMES:
        return None
    if tool_name == "evict_one_unhealthy_controller_owned_pod":
        verified_source_type = await verify_source_type_for_target(
            user_auth_header, plan["target"]
        )
        if verified_source_type not in AUTO_EXECUTE_EVICT_ELIGIBLE_SOURCE_TYPES:
            return None

    target = plan["target"]
    target_key = f"{target.get('namespace')}/{target.get('kind')}/{target.get('name')}"
    lock = _AUTO_EXECUTE_TARGET_LOCKS.setdefault(target_key, asyncio.Lock())

    async with lock:
        # Re-check after acquiring the lock: a concurrent request for the same
        # target (e.g. a retried webhook) may have already auto-executed a
        # different sealed plan for it while we were waiting.
        if has_recent_auto_action_for_target(target, tool_name):
            return {"autoExecuted": False, "autoExecuteFailed": True, "reason": "duplicate auto-execute for this target was already handled"}

        plan_id = str(plan_record["metadata"]["name"])
        plan_digest = plan["digest"]["planDigest"]
        try:
            approval_response = await _create_approval_decision_impl(
                ApprovalDecisionCreate(
                    planId=plan_id,
                    expectedPlanDigest=plan_digest,
                    approvalScope="auto-policy",
                ),
                user_auth_header,
                auto_policy=True,
            )
            approval_id = str(approval_response["metadata"]["name"])
            execution_response = await _execute_action_impl(
                ActionExecutionCreate(
                    approvalId=approval_id,
                    planId=plan_id,
                    expectedPlanDigest=plan_digest,
                ),
                user_auth_header,
                auto_policy=True,
            )
        except HTTPException as exc:
            return {"autoExecuted": False, "autoExecuteFailed": True, "reason": str(exc.detail)}
        except Exception as exc:  # noqa: BLE001
            # Auto-execute is best-effort: the plan/proposal are already persisted,
            # so a downstream failure (e.g. Action Executor unreachable) must degrade
            # to the normal manual approve/execute flow, not fail the whole request.
            return {"autoExecuted": False, "autoExecuteFailed": True, "reason": str(exc)}

        return {
            "autoExecuted": True,
            "approval": approval_response,
            "execution": execution_response,
        }


@app.post("/v1/dev/commands/execute")
async def execute_unrestricted_command(
    req: UnrestrictedCommandExecuteCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    return await execute_unrestricted_command_request(req, subject)


@app.get("/v1/runbooks/registry")
async def get_runbook_registry(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookRegistry",
        "metadata": {"name": "restricted-runbook-registry", "version": RUNBOOK_REGISTRY_VERSION},
        "spec": {
            "digest": RUNBOOK_REGISTRY_DIGEST,
            "entries": list(RUNBOOK_REGISTRY_ENTRIES.values()),
            "preapprovedPatchFieldDigest": PREAPPROVED_PATCH_FIELD_DIGEST,
            "preapprovedPatchFieldSchemas": list(PREAPPROVED_PATCH_FIELD_SCHEMAS.values()),
        },
    }


@app.get("/v1/rag/uploads")
async def list_rag_uploads(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    status, reason, documents = list_pgvector_upload_documents(subject)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagUploadedDocumentList",
        "metadata": {"name": "uploaded-rag-documents", "generatedAt": now_rfc3339()},
        "spec": {
            "status": status,
            "reason": reason,
            "backend": build_rag_backend_status(),
            "documents": documents,
            "totals": {"documents": len(documents)},
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "rawContentReturned": False,
            },
        },
    }


@app.post("/v1/rag/uploads")
async def create_rag_upload(
    req: RagDocumentUploadCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_rag_upload_document(req, subject)
    status, reason, document = await persist_rag_upload_document(record)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagUploadIngestionResult",
        "metadata": {"name": record["document"]["documentId"], "generatedAt": now_rfc3339()},
        "spec": {
            "status": status,
            "reason": reason,
            "backend": build_rag_backend_status(),
            "document": document or record["document"],
            "chunks": [
                {
                    "chunkId": chunk["chunkId"],
                    "chunkIndex": chunk["chunkIndex"],
                    "textHash": chunk["textHash"],
                    "checksum": chunk["checksum"],
                    "charLength": len(chunk["content"]),
                    "sourceUri": chunk["sourceUri"],
                }
                for chunk in record["chunks"]
            ],
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "rawContentReturned": False,
                "redactionAppliedBeforeChunking": True,
            },
        },
    }


@app.post("/v1/rag/uploads/file")
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
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    filename = os.path.basename(file.filename or "upload").strip() or "upload"
    mime_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    raw = await file.read()
    content, parser_report = extract_rag_upload_file_content(filename, mime_type, raw)
    requested_labels = parse_rag_upload_form_labels(labels)
    parser_labels = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in parser_report.items()
        if value is not None
    }
    req = RagDocumentUploadCreate(
        name=filename,
        mimeType=mime_type,
        content=content,
        sourceUri=source_uri,
        sourceType=source_type,
        customer=customer,
        namespace=namespace,
        version=version,
        labels={
            **requested_labels,
            **parser_labels,
            "source": requested_labels.get("source", "chat-attachment"),
        },
        runId=run_id,
    )
    record = build_rag_upload_document(req, subject)
    status, reason, document = await persist_rag_upload_document(record)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagUploadIngestionResult",
        "metadata": {"name": record["document"]["documentId"], "generatedAt": now_rfc3339()},
        "spec": {
            "status": status,
            "reason": reason,
            "backend": build_rag_backend_status(),
            "document": document or record["document"],
            "ingestionReport": parser_report,
            "chunks": [
                {
                    "chunkId": chunk["chunkId"],
                    "chunkIndex": chunk["chunkIndex"],
                    "textHash": chunk["textHash"],
                    "checksum": chunk["checksum"],
                    "charLength": len(chunk["content"]),
                    "sourceUri": chunk["sourceUri"],
                }
                for chunk in record["chunks"]
            ],
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "rawContentReturned": False,
                "redactionAppliedBeforeChunking": True,
                "parserBoundary": "gateway-multipart-upload",
            },
        },
    }


@app.post("/v1/rag/search")
async def search_rag_runbooks(
    req: RagSearchCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    backend = build_rag_backend_status()
    request_id = f"rag-search-{uuid.uuid4()}"
    increment_metric("aiops_rag_search_requests_total")
    search_status, reason, results = await search_pgvector_runbooks(req, subject=subject)
    evidence_status = "collected" if results else ("missing" if search_status == "not_configured" else search_status)
    collected_refs = [result.get("evidenceRef", {}) for result in results if isinstance(result.get("evidenceRef"), Mapping)]
    missing = [] if collected_refs else [{"type": "runbook", "reason": reason}]
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagSearchResult",
        "metadata": {
            "name": request_id,
            "generatedAt": now_rfc3339(),
        },
        "spec": {
            "query": req.query,
            "topK": req.topK,
            "filters": req.filters.model_dump(),
            "includeContent": req.includeContent,
            "runId": req.runId or request_id,
            "status": search_status,
            "reason": reason,
            "backend": backend,
            "results": results,
            "evidence": {
                "type": "runbook",
                "status": evidence_status,
                "reason": reason,
                "collectedRefs": collected_refs,
                "missing": missing,
            },
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "aclRequired": True,
                "mockResultsAreProductionEvidence": False,
            },
        },
    }


@app.post("/v1/runbooks/plans")
async def create_runbook_plan(
    req: RunbookPlanCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_runbook_plan_record(req, subject)
    plan_id = str(record["metadata"]["name"])
    await bounded_put_record("runbookPlans", plan_id, record)
    increment_metric("aiops_runbook_plans_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookPlan",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/runbooks/plans/{plan_id}")
async def get_runbook_plan(
    plan_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = RUNBOOK_PLANS.get(plan_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Runbook plan not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookPlan",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.post("/v1/runbooks/patch-preapproved-field")
async def create_preapproved_patch_request(
    req: PatchPreapprovedFieldCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_preapproved_patch_record(req, subject)
    request_id = str(record["metadata"]["name"])
    await bounded_put_record("preapprovedPatchRequests", request_id, record)
    increment_metric("aiops_preapproved_patch_requests_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "PatchPreapprovedFieldRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/runbooks/patch-preapproved-field/{request_id}")
async def get_preapproved_patch_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = PREAPPROVED_PATCH_REQUESTS.get(request_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Preapproved patch request not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "PatchPreapprovedFieldRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/breakglass/profiles")
async def get_break_glass_profiles(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassProfileRegistry",
        "metadata": {"name": "break-glass-profile-registry", "version": BREAK_GLASS_PROFILE_VERSION},
        "spec": {
            "enabled": BREAK_GLASS_ENABLED,
            "digest": BREAK_GLASS_PROFILE_DIGEST,
            "profiles": list(BREAK_GLASS_PROFILES.values()),
        },
    }


@app.post("/v1/breakglass/requests")
async def create_break_glass_request(
    req: BreakGlassRequestCreate,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = build_break_glass_request_record(req, subject)
    request_id = str(record["metadata"]["name"])
    await bounded_put_record("breakGlassRequests", request_id, record)
    increment_metric("aiops_break_glass_requests_total")
    log_break_glass_audit_record(
        build_trace_record(
            action="break_glass_request_recorded",
            incident_id=req.incidentId or request_id,
            policy=record["spec"]["policy"],
            request_id=request_id,
            run_id=req.runId or request_id,
            subject=subject,
            target={
                "profileId": req.profileId,
                "targetNode": req.targetNode.model_dump(),
                "phase": record["spec"]["status"]["phase"],
                "jobSubmitted": False,
            },
        )
    )
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/breakglass/requests/{request_id}")
async def get_break_glass_request(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    subject = await fetch_self_subject_review(user_auth_header)
    record = BREAK_GLASS_REQUESTS.get(request_id)
    if not record or not can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Break-glass request not found")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


@app.get("/v1/rca/last")
async def get_last_rca_context(authorization: str = Header(default="")) -> dict[str, Any]:
    """최근 채팅 실행의 Tool Plan + Evidence 상태 + RCA 결과를 반환.

    인증 토큰이 없거나 만료된 경우 401을 반환합니다.
    아직 채팅 기록이 없으면 404를 반환합니다.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header with Bearer token is required")
    if LAST_RCA_CONTEXT is None:
        raise HTTPException(status_code=404, detail="No RCA context available yet — send a chat message first")
    return {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "RcaContextSummary",
        "toolPlan": LAST_RUNTIME_TOOL_PLAN,
        "rcaContext": LAST_RCA_CONTEXT,
    }


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


@app.post("/v1/chat/stream")
async def chat_stream(
    req: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    async def generate() -> AsyncIterator[str]:
        global LAST_RCA_CONTEXT, LAST_RUNTIME_TOOL_PLAN

        run_id = req.runId or f"run-{uuid.uuid4()}"
        request_id = f"req-{uuid.uuid4()}"
        incident_id = req.conversationId or f"inc-{uuid.uuid4()}"
        followup_selection = resolve_numeric_followup_message(req.message, req.recentMessages)
        if followup_selection:
            req.message = followup_selection.effective_message
        policy = classify_request_policy(req.message)
        subject = safe_subject(None)
        product_access_review: dict[str, Any] | None = None
        gateway_evidence: str | None = None
        rag_answer_citation_text = ""
        text_reference_filter = TextReferenceFilter(
            filter_gateway_api_references=should_filter_gateway_api_references(req.message),
            filter_low_signal_references=should_filter_low_signal_references(req.message),
            normalize_restart_language=should_collect_pod_status_evidence_for_request(req),
        )
        runtime_tool_plan: dict[str, Any] | None = None
        transcript_answer_chunks: list[str] = []
        transcript_answer_contracts: list[str] = []
        increment_metric("aiops_chat_requests_total")
        record_workflow(
            run_id=run_id,
            incident_id=incident_id,
            policy=policy,
            request_id=request_id,
            stage="started",
            status="running",
            subject=subject,
            target={
                "attachments": len(req.attachments),
                "messageLength": len(req.message),
                "pageContext": normalize_console_page_context(req.pageContext),
            },
        )

        try:
            if is_general_concept_request(req):
                answer_text = general_concept_answer(req)
                transcript_answer_chunks.append(answer_text)
                yield sse(
                    {
                        "type": "text",
                        "content": answer_text,
                        "source": "copilot_reply",
                    }
                )
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed",
                        "message": (
                            "OCP concept guide completed"
                            if answer_language(req) == "en"
                            else "OCP 개념 안내 완료"
                        ),
                    }
                )
                yield sse("[DONE]")
                return

            if is_casual_identity_request(req):
                answer_text = casual_identity_answer(req)
                transcript_answer_chunks.append(answer_text)
                yield sse(
                    {
                        "type": "text",
                        "content": answer_text,
                        "source": "copilot_reply",
                    }
                )
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed",
                        "message": (
                            "AIOps for OCP guide completed"
                            if answer_language(req) == "en"
                            else "AIOps for OCP 안내 완료"
                        ),
                    }
                )
                yield sse("[DONE]")
                return

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "started",
                    "message": "Gateway 실행 루프 시작",
                    "elapsedMs": 0,
                }
            )
            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-security-boundary",
                    "name": "security_boundary",
                    "summary": "실행 보안 경계 적용",
                }
            )
            yield sse(
                {
                    "type": "tool_result",
                    "detail": (
                        "UserToken은 Gateway 내부와 OLS forwarding에만 사용합니다.\n"
                        "Agent/Model prompt, audit payload, evidence event에는 redacted metadata만 전달합니다.\n"
                        "변경 작업은 운영자 승인과 실행 기록 경로에서만 실행합니다.\n"
                        "실험용 무제한 모드는 KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS=true이고 UI가 unrestricted 모드일 때만 동작합니다.\n"
                        "이 모드에서는 `/exec` 셸 명령과 지원되는 자연어 AIOps 조치를 즉시 실행할 수 있습니다."
                    ),
                    "id": f"{request_id}-security-boundary",
                    "name": "security_boundary",
                    "status": "success",
                    "summary": "Gateway credential boundary 확인",
                }
            )
            yield sse({"type": "tool_call", "name": "access_check"})
            await verify_user_access(authorization, req)
            validate_image_attachments(req.attachments)
            yield sse({"type": "tool_result", "name": "access_check", "result": "ok"})

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-subject-review",
                    "name": "subject_review",
                    "summary": "API 서버 관찰 주체 확인",
                }
            )
            subject = await fetch_self_subject_review(authorization)
            live_review = bool(OPENSHIFT_API_URL)
            yield sse(
                {
                    "type": "tool_result",
                    "detail": summarize_subject_detail(subject, live_review=live_review),
                    "id": f"{request_id}-subject-review",
                    "name": "subject_review",
                    "result": subject,
                    "status": "success" if live_review else "skipped",
                    "summary": "주체 확인 완료" if live_review else "주체 확인 생략",
                }
            )

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-product-access-review",
                    "name": "product_access_review",
                    "summary": "제품 접근 SelfSubjectAccessReview 확인",
                }
            )
            product_access_review = await fetch_product_access_review(authorization)
            increment_metric("aiops_product_access_reviews_total")
            yield sse(
                {
                    "type": "tool_result",
                    "detail": summarize_product_access_review(product_access_review),
                    "id": f"{request_id}-product-access-review",
                    "name": "product_access_review",
                    "result": product_access_review,
                    "status": product_access_review_status(product_access_review),
                    "summary": "제품 접근 확인 완료",
                }
            )
            enforce_product_access_review(product_access_review)
            record_workflow(
                run_id=run_id,
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                stage="authorized",
                status="running",
                subject=subject,
                target={
                    "attachments": len(req.attachments),
                    "messageLength": len(req.message),
                    "pageContext": normalize_console_page_context(req.pageContext),
                    "productAccessReview": product_access_review,
                },
            )

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-policy-check",
                    "name": "policy_check",
                    "summary": "요청 정책 분류",
                }
            )
            yield sse(
                {
                    "type": "tool_result",
                    "detail": summarize_policy_detail(policy),
                    "id": f"{request_id}-policy-check",
                    "name": "policy_check",
                    "result": policy,
                    "status": "success",
                    "summary": policy_check_summary(policy),
                }
            )
            if is_test_pod_create_request(req) and TEST_POD_CREATE_ENABLED:
                runtime_tool_plan = test_pod_create_tool_plan(
                    test_pod_create_request_from_message(req.message),
                    page_context_aiops_execution_mode(req),
                )
            else:
                runtime_tool_plan = build_runtime_tool_plan(
                    req.message,
                    page_context=normalize_console_page_context(req.pageContext),
                    execution_mode=page_context_aiops_execution_mode(req),
                )
            LAST_RUNTIME_TOOL_PLAN = runtime_tool_plan
            def current_rca_context_event(phase: str) -> dict[str, Any]:
                return build_rca_context_stream_event(
                    req=req,
                    runtime_tool_plan=runtime_tool_plan or {},
                    run_id=run_id,
                    incident_id=incident_id,
                    phase=phase,
                )

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-runtime-tool-plan",
                    "name": "runtime_tool_plan",
                    "summary": f"질문별 Tool Plan 생성: {runtime_tool_plan.get('task_type')}",
                }
            )
            yield sse(
                {
                    "type": "tool_plan",
                    "plan": redact_sensitive(runtime_tool_plan),
                    "runId": run_id,
                    "status": (
                        "success"
                        if runtime_tool_plan.get("validation", {}).get("ok")
                        else "failed"
                    ),
                }
            )
            yield sse(
                {
                    "type": "tool_result",
                    "detail": json.dumps(
                        redact_sensitive(runtime_tool_plan),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "id": f"{request_id}-runtime-tool-plan",
                    "name": "runtime_tool_plan",
                    "result": redact_sensitive(runtime_tool_plan),
                    "status": (
                        "success"
                        if runtime_tool_plan.get("validation", {}).get("ok")
                        else "failed"
                    ),
                    "summary": "실행형 Tool Plan 검증 완료",
                }
            )
            rca_context_event = current_rca_context_event("plan_ready")
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            accepted_audit_record = build_trace_record(
                action="chat_request_accepted",
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
                target={
                    "attachments": len(req.attachments),
                    "messageLength": len(req.message),
                    "pageContext": normalize_console_page_context(req.pageContext),
                    "productAccessReview": product_access_review,
                },
            )
            log_audit_record(accepted_audit_record)
            yield sse(
                {
                    "type": "tool_result",
                    "detail": json.dumps(
                        redact_sensitive(accepted_audit_record),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "id": accepted_audit_record["auditId"],
                    "name": "audit_record",
                    "status": "success",
                    "summary": "감사 레코드 기록",
                }
            )

            if is_test_pod_create_request(req):
                execution_mode = page_context_aiops_execution_mode(req)
                language = answer_language(req)
                request = test_pod_create_request_from_message(req.message)
                if not test_pod_create_is_ready(request):
                    preflight = await collect_test_pod_create_preflight(authorization, request)
                    answer_text = test_pod_create_disabled_answer(request, language)
                    transcript_answer_chunks.append(answer_text)
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": json.dumps(redact_sensitive(preflight), ensure_ascii=False, indent=2),
                            "id": f"{request_id}-test-pod-create-disabled",
                            "name": "test_pod_create_guard",
                            "result": redact_sensitive(preflight),
                            "status": "skipped",
                            "summary": "테스트 Pod 생성은 현재 제품 조건에서 비활성",
                        }
                    )
                    yield sse(
                        {
                            "type": "text",
                            "content": answer_text,
                            "source": "gateway_direct",
                            "answerContract": "test-pod-create-guard-v1",
                        }
                    )
                    yield sse(
                        {
                            "type": "run_status",
                            "runId": run_id,
                            "stage": "completed",
                            "message": "Gateway 테스트 Pod 생성 가드 확인 완료",
                        }
                    )
                    yield sse("[DONE]")
                    return
                action_mode = action_capable_execution_mode(execution_mode)
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "started",
                        "message": (
                            "Test Pod creation preflight started"
                            if language == "en"
                            else "테스트 Pod 생성 사전 확인 시작"
                        ),
                    }
                )
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-test-pod-create-preflight",
                        "name": "oc_test_pod_create_preflight",
                        "summary": (
                            "Target namespace and server check"
                            if language == "en"
                            else "대상 namespace 및 서버 확인"
                        ),
                    }
                )
                preflight = await collect_test_pod_create_preflight(authorization, request)
                can_propose = action_mode and bool(preflight.get("ok"))
                if can_propose:
                    candidate = test_pod_create_candidate_from_preflight(request, preflight, run_id, incident_id)
                    NAMESPACE_CLEANUP_CHAT_CANDIDATES[str(candidate["id"])] = candidate
                answer_text = test_pod_create_answer(request, preflight, execution_mode, language)
                transcript_answer_chunks.append(answer_text)
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(redact_sensitive(preflight), ensure_ascii=False, indent=2),
                        "id": f"{request_id}-test-pod-create-preflight",
                        "name": "oc_test_pod_create_preflight",
                        "result": redact_sensitive(preflight),
                        "status": "success" if preflight.get("ok") else "failed",
                        "summary": (
                            f"{request.get('namespace')} namespace preflight"
                            if language == "en"
                            else f"{request.get('namespace')} namespace 사전 확인"
                        ),
                    }
                )
                yield sse(
                    {
                        "type": "tool_plan",
                        "plan": {
                            **test_pod_create_tool_plan(request, execution_mode, can_propose=can_propose),
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
                    }
                )
                yield sse(
                    {
                        "type": "text",
                        "content": answer_text,
                        "source": "gateway_direct" if preflight.get("ok") else "gateway_fallback",
                    }
                )
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed" if preflight.get("ok") else "failed",
                        "message": (
                            "Test Pod creation preflight completed"
                            if language == "en"
                            else "테스트 Pod 생성 사전 확인 완료"
                        ),
                    }
                )
                yield sse("[DONE]")
                return

            if is_namespace_cleanup_request(req):
                execution_mode = page_context_aiops_execution_mode(req)
                language = answer_language(req)
                requested_names = namespace_names_from_message(req.message)
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "started",
                        "message": (
                            "Namespace usage check started"
                            if language == "en"
                            else "네임스페이스 사용 여부 확인 시작"
                        ),
                    }
                )
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-namespace-cleanup-inventory",
                        "name": "namespace_cleanup_inventory",
                        "summary": (
                            "Namespace usage read-only inventory"
                            if language == "en"
                            else "namespace 사용 여부 read-only 조회"
                        ),
                    }
                )
                inventory = await collect_namespace_cleanup_inventory(authorization, requested_names)
                cleanup_candidates = namespace_cleanup_candidates_from_inventory(inventory)
                if action_capable_execution_mode(execution_mode) and cleanup_candidates:
                    remember_namespace_cleanup_candidates(inventory, run_id, incident_id)
                answer_text = namespace_cleanup_answer(inventory, execution_mode, language)
                transcript_answer_chunks.append(answer_text)
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(redact_sensitive(inventory), ensure_ascii=False, indent=2),
                        "id": f"{request_id}-namespace-cleanup-inventory",
                        "name": "namespace_cleanup_inventory",
                        "result": redact_sensitive(inventory),
                        "status": "success" if inventory.get("ok") else "failed",
                        "summary": (
                            f"namespace {len(inventory.get('inspected') or [])} read-only checks"
                            if language == "en"
                            else f"namespace {len(inventory.get('inspected') or [])}개 read-only 조회"
                        ),
                    }
                )
                yield sse(
                    {
                        "type": "tool_plan",
                        "plan": {
                            "task_type": "namespace_cleanup_review",
                            "execution_policy": {
                                "mode": execution_mode,
                                "mutations_enabled": False,
                                "proposal_only": True,
                                "review_only": True,
                            },
                            "tool_plan": [
                                {
                                    "step": 1,
                                    "adapter": "oc",
                                    "tool": "oc_get_namespaces",
                                    "verb": "list",
                                    "purpose": "접근 가능한 namespace 목록 확인",
                                },
                                {
                                    "step": 2,
                                    "adapter": "oc",
                                    "tool": "oc_get_namespace_inventory",
                                    "verb": "get",
                                    "purpose": "workload, PVC, Route, Event 잔존 확인",
                                },
                                *(
                                    [
                                        {
                                            "step": 3,
                                            "adapter": "aiops-gateway",
                                            "tool": "namespace_cleanup_review_plan",
                                            "verb": "propose",
                                            "purpose": "승인 필요 Namespace 정리 검토 Action Plan 후보 생성",
                                        }
                                    ]
                                    if action_capable_execution_mode(execution_mode) and cleanup_candidates
                                    else []
                                ),
                            ],
                            "validation": {
                                "ok": bool(inventory.get("ok")),
                                "status": (
                                    "action_candidate_ready"
                                    if action_capable_execution_mode(execution_mode) and cleanup_candidates
                                    else "read_only_inventory_collected"
                                    if inventory.get("ok")
                                    else inventory.get("status")
                                ),
                            },
                        },
                        "runId": run_id,
                        "status": "success" if inventory.get("ok") else "failed",
                    }
                )
                yield sse(
                    {
                        "type": "text",
                        "content": answer_text,
                        "source": "gateway_direct" if inventory.get("ok") else "gateway_fallback",
                    }
                )
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed" if inventory.get("ok") else "failed",
                        "message": (
                            "Namespace usage check completed"
                            if language == "en"
                            else "네임스페이스 사용 여부 확인 완료"
                        ),
                    }
                )
                yield sse("[DONE]")
                return

            unrestricted_command = parse_unrestricted_chat_command(req.message)
            if execution_mode_allows_immediate_actions(req) and unrestricted_command:
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-unrestricted-command",
                        "name": "unrestricted_command",
                        "summary": "실험용 무제한 명령 실행",
                    }
                )
                command_result = await execute_unrestricted_command_request(
                    UnrestrictedCommandExecuteCreate(command=unrestricted_command),
                    subject,
                    request_id=request_id,
                    run_id=run_id,
                )
                spec = command_result["spec"]
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(redact_sensitive(spec), ensure_ascii=False, indent=2),
                        "id": f"{request_id}-unrestricted-command",
                        "name": "unrestricted_command",
                        "result": command_result,
                        "status": "failed" if spec.get("exitCode") else "success",
                        "summary": f"명령 종료 코드 {spec.get('exitCode')}",
                    }
                )
                rca_context_event = current_rca_context_event("post_answer")
                LAST_RCA_CONTEXT = rca_context_event["context"]
                yield sse(rca_context_event)
                yield sse({"type": "text", "content": unrestricted_command_response(command_result)})
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed",
                        "message": "Gateway 실험용 명령 실행 완료",
                    }
                )
                yield sse("[DONE]")
                return

            if is_top_pod_namespace_query(req.message or "") and policy.get("decision") != "action_proposal_only":
                dependencies = TopPodNamespaceFlowDependencies(
                    openshift_api_url=OPENSHIFT_API_URL,
                    openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
                    async_client_factory=httpx.AsyncClient,
                    timeout_factory=httpx.Timeout,
                    fetch_ocp_json=fetch_ocp_json,
                    build_result=build_top_pod_namespace_count_result,
                    build_response=top_pod_namespace_count_response,
                    build_evidence_events=build_evidence_reference_events,
                    current_rca_context_event=current_rca_context_event,
                )
                async for stream_event in stream_top_pod_namespace_count(
                    authorization=authorization,
                    dependencies=dependencies,
                    incident_id=incident_id,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                ):
                    if stream_event.latest_rca_context is not None:
                        LAST_RCA_CONTEXT = stream_event.latest_rca_context
                    yield stream_event.payload
                return

            pod_count_query = parse_pod_count_query(req)
            if (
                pod_count_query
                and policy.get("decision") != "action_proposal_only"
                and not crashloop_demo_target_from_request(req)
            ):
                dependencies = DirectPodCountFlowDependencies(
                    openshift_api_url=OPENSHIFT_API_URL,
                    openshift_api_ca_file=OPENSHIFT_API_CA_FILE,
                    async_client_factory=httpx.AsyncClient,
                    timeout_factory=httpx.Timeout,
                    fetch_ocp_json=fetch_ocp_json,
                    path_segment=path_segment,
                    resource_items=resource_items,
                    metadata_name=metadata_name,
                    metadata_namespace=metadata_namespace,
                    build_investigation=build_pod_count_investigation,
                    build_response=pod_count_investigation_response,
                    redact_sensitive=redact_sensitive,
                    build_evidence_events=build_evidence_reference_events,
                    current_rca_context_event=current_rca_context_event,
                )
                async for stream_event in stream_direct_pod_count(
                    authorization=authorization,
                    dependencies=dependencies,
                    incident_id=incident_id,
                    pod_count_query=pod_count_query,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                ):
                    if stream_event.latest_rca_context is not None:
                        LAST_RCA_CONTEXT = stream_event.latest_rca_context
                    yield stream_event.payload
                return

            cleanup_focus = conversation_focus_from_request(req)
            cleanup_flow = start_cleanup_chat_flow(
                cleanup_focus=cleanup_focus,
                dependencies=cleanup_chat_flow_dependencies(current_rca_context_event),
                gateway_evidence=gateway_evidence,
                incident_id=incident_id,
                request=req,
                request_id=request_id,
                run_id=run_id,
            )
            if cleanup_flow.handled:
                for stream_event in cleanup_flow.events:
                    if stream_event.latest_rca_context is not None:
                        LAST_RCA_CONTEXT = stream_event.latest_rca_context
                    yield stream_event.payload
                return

            if (
                execution_mode_allows_immediate_actions(req)
                and is_followup_execution_request(req.message)
            ):
                followup_flow = stream_chat_natural_action_followup(
                    authorization=authorization,
                    dependencies=natural_action_followup_flow_dependencies(
                        current_rca_context_event
                    ),
                    incident_id=incident_id,
                    request=req,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                )
                async for stream_event in followup_flow:
                    if stream_event.latest_rca_context is not None:
                        LAST_RCA_CONTEXT = stream_event.latest_rca_context
                    yield stream_event.payload
                return

            if (
                policy.get("decision") == "action_proposal_only"
                and not crashloop_demo_target_from_request(req)
            ):
                proposal_flow = stream_chat_natural_action_proposal(
                    authorization=authorization,
                    dependencies=natural_action_proposal_flow_dependencies(
                        current_rca_context_event
                    ),
                    incident_id=incident_id,
                    request=req,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                )
                handled = False
                async for stream_event in proposal_flow:
                    handled = True
                    if stream_event.latest_rca_context is not None:
                        LAST_RCA_CONTEXT = stream_event.latest_rca_context
                    yield stream_event.payload
                if handled:
                    return

            if req.attachments:
                yield sse({"type": "tool_call", "name": "attachment_check"})
                yield sse(
                    {
                        "type": "tool_result",
                        "name": "attachment_check",
                        "result": {
                            "images": len(req.attachments),
                            "totalBytes": sum(item.size for item in req.attachments),
                            "forwardedToLightspeed": False,
                        },
                        "summary": "첨부 이미지 수신 및 형식 확인 완료",
                    }
                )

            image_analysis = None
            if req.attachments:
                yield sse({"type": "tool_call", "name": "vision_analysis"})
                image_analysis = await analyze_image_attachments(req.attachments, req.message)
                yield sse(
                    {
                        "type": "tool_result",
                        "name": "vision_analysis",
                        "result": "ok" if image_analysis else "not_configured",
                    }
                )

            if should_collect_cronjob_activity_evidence(req.message, image_analysis):
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-cronjob-activity-evidence",
                        "name": "cronjob_activity_evidence",
                        "summary": "CronJob/Activity 주기 조회 결과 수집",
                    }
                )
                try:
                    cronjob_context = "\n".join(
                        item for item in [req.message, image_analysis] if item
                    )
                    cronjob_evidence = await collect_cronjob_activity_evidence(
                        authorization,
                        cronjob_context,
                    )
                    evidence_status = (
                        "skipped"
                        if cronjob_evidence.startswith("CronJob activity evidence unavailable:")
                        else "success"
                    )
                    gateway_evidence = append_gateway_evidence(gateway_evidence, cronjob_evidence)
                    cronjob_event = {
                        "type": "tool_result",
                        "detail": cronjob_evidence,
                        "evidenceType": "cronjob",
                        "id": f"{request_id}-cronjob-activity-evidence",
                        "missingReason": cronjob_evidence
                        if evidence_status != "success"
                        else "",
                        "name": "cronjob_activity_evidence",
                        "sourcePath": "/apis/batch/v1/cronjobs,/apis/batch/v1/jobs?limit=500",
                        "status": evidence_status,
                        "summary": _evidence_summary(
                            "CronJob/Activity 주기 증거",
                            evidence_status,
                        ),
                    }
                    yield sse(cronjob_event)
                    for evidence_event in build_evidence_reference_events(
                        event=cronjob_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)
                except Exception as exc:
                    cronjob_evidence = f"CronJob activity evidence unavailable: {safe_exception_text(exc)}"
                    gateway_evidence = append_gateway_evidence(gateway_evidence, cronjob_evidence)
                    cronjob_event = {
                        "type": "tool_result",
                        "detail": cronjob_evidence,
                        "id": f"{request_id}-cronjob-activity-evidence",
                        "name": "cronjob_activity_evidence",
                        "evidenceType": "cronjob",
                        "missingReason": safe_exception_text(exc),
                        "status": "error",
                        "summary": "CronJob/Activity 주기 조회 결과 수집 실패",
                    }
                    yield sse(cronjob_event)
                    for evidence_event in build_evidence_reference_events(
                        event=cronjob_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)

            if should_collect_pod_status_evidence_for_request(req):
                async for stream_event in stream_pod_status_evidence(
                    authorization=authorization,
                    dependencies=pod_evidence_flow_dependencies(),
                    gateway_evidence=gateway_evidence,
                    incident_id=incident_id,
                    request=req,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                ):
                    if stream_event.gateway_evidence is not None:
                        gateway_evidence = stream_event.gateway_evidence
                    yield stream_event.payload

            crashloop_demo_target = crashloop_demo_target_from_request(req)
            official_restart_namespace = official_namespace_restart_namespace(runtime_tool_plan)
            if official_restart_namespace and not crashloop_demo_target:
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-official-namespace-restart-evidence",
                        "name": "official_namespace_restart_evidence",
                        "summary": f"공식 Evidence RCA namespace 재시작 조회 결과 수집: `{official_restart_namespace}`",
                    }
                )
                try:
                    official_restart_events = await collect_official_namespace_restart_evidence_events(
                        authorization,
                        official_restart_namespace,
                        request_id,
                    )
                except Exception as exc:
                    safe_detail = safe_exception_text(exc)
                    official_restart_events = official_namespace_restart_skipped_evidence_events(
                        namespace=official_restart_namespace,
                        request_id=request_id,
                        reason=safe_detail,
                        detail=safe_detail,
                    )

                for official_restart_event in official_restart_events:
                    gateway_evidence = append_gateway_evidence(
                        gateway_evidence,
                        str(
                            official_restart_event.get("detail")
                            or official_restart_event.get("summary")
                            or ""
                        ),
                    )
                    yield sse(official_restart_event)
                    for evidence_event in build_evidence_reference_events(
                        event=official_restart_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)

            if crashloop_demo_target:
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-crashloop-demo-evidence",
                        "name": "crashloop_demo_evidence",
                        "summary": "CrashLoopBackOff 시연 조회 결과 수집",
                    }
                )
                try:
                    crashloop_events = await collect_crashloop_demo_evidence_events(
                        authorization,
                        crashloop_demo_target,
                        request_id,
                    )
                except Exception as exc:
                    safe_detail = safe_exception_text(exc)
                    crashloop_events = [
                        {
                            "type": "tool_result",
                            "detail": f"CrashLoop event evidence unavailable: {safe_detail}",
                            "evidenceType": "event",
                            "id": f"{request_id}-crashloop-event-evidence",
                            "missingReason": safe_detail,
                            "name": "crashloop_event_evidence",
                            "status": "error",
                            "summary": "CrashLoop Event 조회 결과 수집 실패",
                        },
                        {
                            "type": "tool_result",
                            "detail": f"CrashLoop previous log availability unavailable: {safe_detail}",
                            "evidenceType": "pod_log",
                            "id": f"{request_id}-crashloop-log-availability",
                            "missingReason": safe_detail,
                            "name": "crashloop_log_availability",
                            "status": "error",
                            "summary": "CrashLoop 이전 로그 가용성 확인 실패",
                        },
                        {
                            "type": "tool_result",
                            "detail": f"CrashLoop Pod snapshot unavailable: {safe_detail}",
                            "evidenceType": "snapshot",
                            "id": f"{request_id}-crashloop-pod-snapshot",
                            "missingReason": safe_detail,
                            "name": "crashloop_pod_snapshot",
                            "status": "error",
                            "summary": "CrashLoop Pod snapshot 조회 결과 수집 실패",
                        },
                    ]

                for crashloop_event in crashloop_events:
                    gateway_evidence = append_gateway_evidence(
                        gateway_evidence,
                        str(crashloop_event.get("detail") or crashloop_event.get("summary") or ""),
                    )
                    yield sse(crashloop_event)
                    for evidence_event in build_evidence_reference_events(
                        event=crashloop_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)

            if past_pod_restart_demo_active(req):
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-past-pod-restart-demo-evidence",
                        "name": "past_pod_restart_demo_evidence",
                        "summary": "과거 Pod 재시작 RCA 시연 증적 수집 (Scenario 11)",
                    }
                )
                for demo_event in collect_past_pod_restart_demo_evidence_events(request_id):
                    gateway_evidence = append_gateway_evidence(
                        gateway_evidence,
                        str(demo_event.get("detail") or demo_event.get("summary") or ""),
                    )
                    yield sse(demo_event)
                    for evidence_event in build_evidence_reference_events(
                        event=demo_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-demo-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_event)

            if (
                str(policy.get("decision") or "") == "allow_evidence_collection"
                and should_collect_rca_signal_evidence_for_request(req)
            ):
                rca_preflight_collectors = [
                    (
                        "node-status-rca-evidence",
                        "node_status_evidence",
                        "Node 상태 RCA 조회 결과 수집",
                        collect_node_status_rca_evidence,
                    ),
                    (
                        "active-alerts-rca-evidence",
                        "active_alerts_evidence",
                        "Active Alert RCA 조회 결과 수집",
                        collect_active_alerts_rca_evidence,
                    ),
                    (
                        "restart-metric-rca-evidence",
                        "restart_metric_evidence",
                        "Restart metric RCA 조회 결과 수집",
                        collect_restart_metric_rca_evidence,
                    ),
                ]
                for suffix, event_name, call_summary, collector in rca_preflight_collectors:
                    event_id = f"{request_id}-{suffix}"
                    yield sse(
                        {
                            "type": "tool_call",
                            "id": event_id,
                            "name": event_name,
                            "summary": call_summary,
                        }
                    )
                    try:
                        evidence_result = await collector(authorization)
                        evidence_detail = str(evidence_result.get("detail") or "")
                        gateway_evidence = append_gateway_evidence(gateway_evidence, evidence_detail)
                        evidence_event = {
                            "type": "tool_result",
                            "detail": evidence_detail,
                            "evidenceType": evidence_result.get("evidenceType"),
                            "id": event_id,
                            "missingReason": evidence_result.get("missingReason"),
                            "name": event_name,
                            "sourcePath": evidence_result.get("sourcePath"),
                            "status": evidence_result.get("status") or "error",
                            "summary": evidence_result.get("summary") or f"{call_summary} 완료",
                        }
                    except Exception as exc:
                        safe_detail = safe_exception_text(exc)
                        evidence_type = (
                            "node"
                            if event_name == "node_status_evidence"
                            else "alert"
                            if event_name == "active_alerts_evidence"
                            else "metric"
                        )
                        evidence_detail = f"{call_summary} unavailable: {safe_detail}"
                        gateway_evidence = append_gateway_evidence(gateway_evidence, evidence_detail)
                        evidence_event = {
                            "type": "tool_result",
                            "detail": evidence_detail,
                            "evidenceType": evidence_type,
                            "id": event_id,
                            "missingReason": safe_detail,
                            "name": event_name,
                            "status": "error",
                            "summary": f"{call_summary} 실패",
                        }

                    yield sse(evidence_event)
                    for evidence_ref_event in build_evidence_reference_events(
                        event=evidence_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        source_type="gateway-preflight-evidence",
                        subject=subject,
                    ):
                        yield sse(evidence_ref_event)

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-rag-context-evidence",
                    "name": "rag_context_evidence",
                    "summary": "RAG 참고 문서 검색",
                }
            )
            try:
                rag_request = RagSearchCreate(
                    query=req.message,
                    topK=3,
                    includeContent=False,
                    runId=run_id,
                )
                rag_status, rag_reason, rag_results = await search_pgvector_runbooks(
                    rag_request,
                    subject=subject,
                )
                rag_detail = build_rag_context_detail(rag_results, rag_reason)
                gateway_evidence = append_gateway_evidence(gateway_evidence, rag_detail)
                rag_answer_citation_text = build_rag_answer_citation_text(rag_results)
                rag_event = {
                    "type": "tool_result",
                    "detail": rag_detail,
                    "evidenceType": "runbook",
                    "id": f"{request_id}-rag-context-evidence",
                    "missingReason": "" if rag_results else rag_reason,
                    "name": "rag_context_evidence",
                    "result": {
                        "query": req.message,
                        "resultCount": len(rag_results),
                        "results": [
                            {
                                "documentId": result.get("documentId"),
                                "score": result.get("score"),
                                "sourceType": result.get("sourceType"),
                                "sourceUri": result.get("sourceUri"),
                                "title": result.get("title"),
                            }
                            for result in rag_results
                        ],
                        "status": rag_status,
                    },
                    "sourcePath": "/v1/rag/search",
                    "status": "success" if rag_results else "skipped",
                    "summary": (
                        f"RAG 참고 문서 {len(rag_results)}건 검색"
                        if rag_results
                        else "RAG 참고 문서 검색 결과 없음"
                    ),
                }
            except Exception as exc:
                rag_detail = f"RAG evidence unavailable: {safe_exception_text(exc)}"
                gateway_evidence = append_gateway_evidence(gateway_evidence, rag_detail)
                rag_event = {
                    "type": "tool_result",
                    "detail": rag_detail,
                    "evidenceType": "runbook",
                    "id": f"{request_id}-rag-context-evidence",
                    "missingReason": safe_exception_text(exc),
                    "name": "rag_context_evidence",
                    "sourcePath": "/v1/rag/search",
                    "status": "error",
                    "summary": "RAG 참고 문서 검색 실패",
                }
            yield sse(rag_event)
            for evidence_ref_event in build_evidence_reference_events(
                event=rag_event,
                incident_id=incident_id,
                run_id=run_id,
                source_type="gateway-rag-evidence",
                subject=subject,
            ):
                yield sse(evidence_ref_event)

            pod_inventory_candidates: list[dict[str, Any]] = []
            if (
                action_capable_execution_mode(page_context_aiops_execution_mode(req))
                and not is_pod_namespace_pattern_lookup_request(req.message)
            ):
                pod_inventory_candidates = remember_pod_inventory_action_candidates(
                    req,
                    gateway_evidence,
                    incident_id=incident_id,
                    run_id=run_id,
                )
            if pod_inventory_candidates:
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": json.dumps(
                            {
                                "candidateCount": len(pod_inventory_candidates),
                                "candidates": [
                                    {
                                        "id": candidate.get("id"),
                                        "sourceType": candidate.get("sourceType"),
                                        "target": candidate.get("target"),
                                        "title": candidate.get("title"),
                                    }
                                    for candidate in pod_inventory_candidates
                                ],
                            },
                            ensure_ascii=False,
                            indent=2,
                        ),
                        "id": f"{request_id}-pod-inventory-action-candidates",
                        "name": "pod_inventory_action_candidates",
                        "result": {
                            "candidateCount": len(pod_inventory_candidates),
                            "status": "action_candidate_ready",
                        },
                        "status": "success",
                        "summary": f"Pod 원인 확인 Action Plan 후보 {len(pod_inventory_candidates)}건 준비",
                    }
                )

            rca_context_event = current_rca_context_event("pre_answer")
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            grounded_answer = build_grounded_aiops_answer(
                req,
                runtime_tool_plan,
                gateway_evidence,
            )
            if grounded_answer and GATEWAY_DIRECT_ANSWER_ENABLED:
                transcript_answer_chunks.append(grounded_answer)
                transcript_answer_contracts.append("evidence-grounded-pod-rca-v0.2.2")
                yield sse(
                    {
                        "type": "text",
                        "content": grounded_answer,
                        "source": "gateway_evidence_renderer",
                        "answerContract": "evidence-grounded-pod-rca-v0.2.2",
                        "gatewayContextDigest": rca_context_event["context"]["metadata"]["digest"],
                    }
                )
                rca_context_event = current_rca_context_event("post_answer")
                rca_result = parse_rca_result(grounded_answer, [])
                rca_context_event["context"]["rcaResult"] = {
                    "cause_candidates": rca_result.cause_candidates,
                    "action_candidates": rca_result.action_candidates,
                    "confidence": rca_result.confidence,
                    "evidence_types": rca_result.evidence_types,
                    "extractedAt": now_rfc3339(),
                }
                LAST_RCA_CONTEXT = rca_context_event["context"]
                yield sse(rca_context_event)
                await persist_chat_transcript_record(
                    build_chat_transcript_record(
                        req=req,
                        answer_text="".join(transcript_answer_chunks),
                        answer_contracts=transcript_answer_contracts,
                        incident_id=incident_id,
                        policy=policy,
                        request_id=request_id,
                        rca_context=rca_context_event["context"],
                        run_id=run_id,
                        runtime_tool_plan=runtime_tool_plan,
                        status="completed",
                        subject=subject,
                    )
                )
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "completed",
                        "message": "Gateway evidence 기반 RCA 답변 완료",
                    }
                )
                completed_audit_record = build_trace_record(
                    action="chat_request_completed",
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                )
                log_audit_record(completed_audit_record)
                increment_metric("aiops_chat_completed_total")
                record_workflow(
                    run_id=run_id,
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    stage="completed",
                    status="completed",
                    subject=subject,
                )
                yield sse("[DONE]")
                return
            pre_ols_safety_contract = build_runtime_safety_contract(
                mutations_enabled=MUTATIONS_ENABLED,
                unrestricted_commands_enabled=UNRESTRICTED_COMMANDS_ENABLED,
                diagnostics_enabled=DIAGNOSTICS_ENABLED,
                record_store_enabled=RECORD_STORE_ENABLED,
                diagnostics_controller_configured=bool(HOST_DIAGNOSTICS_CONTROLLER_URL),
                lightspeed_status=redact_sensitive(dict(OLS_STREAM_STATUS)),
                latest_runtime_tool_plan=runtime_tool_plan,
                latest_rca_context=rca_context_event["context"],
            )
            ols_gateway_context = build_ols_gateway_context(
                tool_plan=runtime_tool_plan,
                rca_context=rca_context_event["context"],
                safety_contract=pre_ols_safety_contract,
                policy=policy,
                gateway_evidence=gateway_evidence,
            )

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": active_llm_stage(),
                    "message": f"실제 {active_llm_label()}로 요청 전달",
                    "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                    "rcaContextDigest": rca_context_event["context"]["metadata"]["digest"],
                }
            )
            ols_query = build_ols_query(
                req,
                image_analysis,
                policy=policy,
                subject=subject,
                gateway_context=ols_gateway_context,
                gateway_evidence=gateway_evidence,
            )
            emitted_answer_text = False
            ols_tool_results: list[Mapping[str, Any]] = []
            ols_attempt_count = 0
            _accumulated_answer_chunks: list[str] = []
            for ols_attempt in range(OLS_EMPTY_ANSWER_RETRIES + 1):
                attempt_emitted_answer_text = False
                ols_attempt_count = ols_attempt + 1
                active_ols_query = ols_query
                if ols_attempt > 0:
                    active_ols_query = (
                        f"{redact_sensitive(req.message).strip()}\n\n"
                        "Previous OpenShift Lightspeed response ended before final answer text. "
                        "Do not call tools again in this retry. "
                        f"{answer_language_contract(req)} "
                        "Return a concise final answer using the OpenShift evidence already observed in this conversation. "
                        "If the available facts do not confirm the cause, say exactly what is unconfirmed. "
                        "Do not print secrets or raw credentials."
                    )

                try:
                    async for ols_event in stream_with_heartbeats(
                        call_ols_stream(
                            authorization,
                            active_ols_query,
                            req.conversationId,
                            req.attachments,
                            ols_gateway_context,
                        ),
                        run_id,
                    ):
                        normalized_event = normalize_ols_event(ols_event)
                        if normalized_event.get("type") == "text":
                            filtered_content = text_reference_filter.filter(
                                str(normalized_event.get("content") or "")
                            )
                            if filtered_content:
                                if filtered_content.strip():
                                    emitted_answer_text = True
                                    attempt_emitted_answer_text = True
                                    _accumulated_answer_chunks.append(filtered_content)
                                    transcript_answer_chunks.append(filtered_content)
                                text_event: dict[str, Any] = {"type": "text", "content": filtered_content}
                                for key in (
                                    "fallbackAnswer",
                                    "gatewayContextDigest",
                                    "source",
                                    "streamProbe",
                                ):
                                    if key in normalized_event:
                                        text_event[key] = normalized_event[key]
                                yield sse(text_event)
                            continue

                        if normalized_event.get("type") == "end":
                            final_text = text_reference_filter.flush()
                            if final_text:
                                if final_text.strip():
                                    emitted_answer_text = True
                                    attempt_emitted_answer_text = True
                                    _accumulated_answer_chunks.append(final_text)
                                    transcript_answer_chunks.append(final_text)
                                yield sse({"type": "text", "content": final_text})
                            if not attempt_emitted_answer_text and ols_attempt < OLS_EMPTY_ANSWER_RETRIES:
                                continue

                        yield sse(normalized_event)
                        if normalized_event.get("type") == "tool_result":
                            ols_tool_results.append(dict(normalized_event))
                            for evidence_event in build_evidence_reference_events(
                                event=normalized_event,
                                incident_id=incident_id,
                                run_id=run_id,
                                source_type="ols-tool-result",
                                subject=subject,
                            ):
                                yield sse(evidence_event)
                except Exception as exc:
                    safe_detail = safe_exception_text(exc)
                    update_ols_stream_status(
                        "failed",
                        context_digest=ols_gateway_context["metadata"]["digest"],
                        fallback_active=(
                            not REQUIRE_OLS_FINAL_ANSWER and ols_attempt >= OLS_EMPTY_ANSWER_RETRIES
                        ),
                        reason=safe_detail,
                    )
                    ols_error_event = {
                        "type": "tool_result",
                        "detail": safe_detail,
                        "id": f"{request_id}-{active_llm_stage()}-stream",
                        "name": f"{active_llm_stage()}_stream",
                        "status": "error",
                        "summary": f"{active_llm_label()} request failed; final answer was not generated",
                        "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                        "finalAnswerUnavailable": True,
                    }
                    ols_tool_results.append(ols_error_event)
                    if ols_attempt < OLS_EMPTY_ANSWER_RETRIES:
                        yield sse(
                            {
                                "type": "run_status",
                                "runId": run_id,
                                "stage": f"{active_llm_stage()}_retry",
                                "message": f"{active_llm_label()} 오류로 원 질문만 사용해 재시도",
                                "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                                "attempt": ols_attempt + 2,
                            }
                        )
                        continue
                    yield sse(ols_error_event)
                    break

                if emitted_answer_text:
                    break

                if ols_attempt < OLS_EMPTY_ANSWER_RETRIES:
                    yield sse(
                        {
                            "type": "run_status",
                            "runId": run_id,
                            "stage": f"{active_llm_stage()}_retry",
                            "message": f"{active_llm_label()}가 빈 응답으로 종료되어 같은 증거로 재시도",
                            "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                            "attempt": ols_attempt + 2,
                        }
                    )
            if not emitted_answer_text:
                fallback_reason = (
                    f"{active_llm_label()} ended without answer text; final answer was not generated"
                    if ols_attempt_count <= 1
                    else f"{active_llm_label()} ended without answer text after {ols_attempt_count} attempts; final answer was not generated"
                )
                update_ols_stream_status(
                    "failed",
                    context_digest=ols_gateway_context["metadata"]["digest"],
                    fallback_active=not REQUIRE_OLS_FINAL_ANSWER,
                    reason=fallback_reason,
                )
                if REQUIRE_OLS_FINAL_ANSWER:
                    fallback_answer = build_ols_required_failure_answer(
                        req,
                        ols_tool_results,
                        image_analysis=image_analysis,
                        image_forwarded_to_ols=should_forward_image_attachments_to_ols(),
                    )
                    fallback_source = "ols_required_notice"
                    fallback_event_extra: dict[str, Any] = {
                        "finalAnswerUnavailable": True,
                    }
                else:
                    fallback_answer = build_empty_answer_fallback(
                        req,
                        policy,
                        ols_tool_results,
                        gateway_evidence,
                        image_analysis=image_analysis,
                        image_forwarded_to_ols=should_forward_image_attachments_to_ols(),
                    )
                    fallback_source = "gateway_fallback"
                    fallback_event_extra = {
                        "fallbackAnswer": True,
                    }
                transcript_answer_chunks.append(fallback_answer)
                yield sse(
                    {
                        "type": "text",
                        "content": fallback_answer,
                        "source": fallback_source,
                        "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                        "streamProbe": "failed",
                        **fallback_event_extra,
                    }
                )

            can_append_gateway_contract_text = emitted_answer_text or not REQUIRE_OLS_FINAL_ANSWER

            if can_append_gateway_contract_text and rag_answer_citation_text:
                transcript_answer_chunks.append(rag_answer_citation_text)
                yield sse(
                    {
                        "type": "text",
                        "content": rag_answer_citation_text,
                        "source": "gateway_rag_citation",
                        "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                    }
                )

            if can_append_gateway_contract_text:
                crashloop_answer_contract = build_crashloop_demo_answer_contract_text(req, run_id)
                if crashloop_answer_contract:
                    transcript_answer_chunks.append(crashloop_answer_contract)
                    transcript_answer_contracts.append("crashloop-v0.1.3")
                    yield sse(
                        {
                            "type": "text",
                            "content": crashloop_answer_contract,
                            "source": "gateway_answer_contract",
                            "answerContract": "crashloop-v0.1.3",
                            "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                        }
                    )
                else:
                    aiops_answer_contract = build_aiops_answer_contract_text(
                        policy=policy,
                        rca_context=rca_context_event["context"],
                        runtime_tool_plan=runtime_tool_plan,
                    )
                    if aiops_answer_contract:
                        transcript_answer_chunks.append(aiops_answer_contract)
                        transcript_answer_contracts.append("aiops-action-v0.1.9")
                        yield sse(
                            {
                                "type": "text",
                                "content": aiops_answer_contract,
                                "source": "gateway_answer_contract",
                                "answerContract": "aiops-action-v0.1.9",
                                "gatewayContextDigest": ols_gateway_context["metadata"]["digest"],
                            }
                        )

            rca_context_event = current_rca_context_event("post_answer")
            rca_result = parse_rca_result(
                "".join(_accumulated_answer_chunks),
                list(ols_tool_results),
            )
            rca_context_event["context"]["rcaResult"] = {
                "cause_candidates": rca_result.cause_candidates,
                "action_candidates": rca_result.action_candidates,
                "confidence": rca_result.confidence,
                "evidence_types": rca_result.evidence_types,
                "extractedAt": now_rfc3339(),
            }
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            await persist_chat_transcript_record(
                build_chat_transcript_record(
                    req=req,
                    answer_text="".join(transcript_answer_chunks),
                    answer_contracts=transcript_answer_contracts,
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    rca_context=rca_context_event["context"],
                    run_id=run_id,
                    runtime_tool_plan=runtime_tool_plan,
                    status="completed",
                    subject=subject,
                )
            )

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "completed",
                    "message": "Gateway 실행 루프 완료",
                }
            )
            completed_audit_record = build_trace_record(
                action="chat_request_completed",
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
            )
            log_audit_record(completed_audit_record)
            increment_metric("aiops_chat_completed_total")
            record_workflow(
                run_id=run_id,
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                stage="completed",
                status="completed",
                subject=subject,
            )
            yield sse("[DONE]")
        except HTTPException as exc:
            error_message = http_exception_message(exc)
            error_tool_plan = runtime_tool_plan or build_runtime_tool_plan(
                req.message,
                page_context=normalize_console_page_context(req.pageContext),
                execution_mode=page_context_aiops_execution_mode(req),
            )
            rca_context_event = build_rca_context_stream_event(
                req=req,
                runtime_tool_plan=error_tool_plan,
                run_id=run_id,
                incident_id=incident_id,
                phase="failed",
            )
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            log_audit_record(
                build_trace_record(
                    action="chat_request_failed",
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                    target={"error": error_message, "statusCode": exc.status_code},
                )
            )
            increment_metric("aiops_chat_failed_total")
            record_workflow(
                run_id=run_id,
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                stage="failed",
                status="failed",
                subject=subject,
                target={"error": error_message, "statusCode": exc.status_code},
            )

            if is_openshift_user_auth_failure(exc):
                yield sse(
                    {
                        "type": "tool_result",
                        "detail": error_message,
                        "id": f"{request_id}-subject-review",
                        "name": "subject_review",
                        "result": redact_sensitive(exc.detail),
                        "status": "error",
                        "summary": "OpenShift 사용자 인증 갱신 필요",
                    }
                )
                yield sse({"type": "text", "content": error_message})
                yield sse(
                    {
                        "type": "run_status",
                        "runId": run_id,
                        "stage": "failed",
                        "message": "OpenShift 사용자 인증 갱신 필요",
                    }
                )
                yield sse("[DONE]")
                return

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "failed",
                    "message": error_message,
                }
            )
            yield sse({"type": "error", "message": error_message})
            yield sse("[DONE]")
        except Exception as exc:
            safe_detail = safe_exception_text(exc)
            error_tool_plan = runtime_tool_plan or build_runtime_tool_plan(
                req.message,
                page_context=normalize_console_page_context(req.pageContext),
                execution_mode=page_context_aiops_execution_mode(req),
            )
            rca_context_event = build_rca_context_stream_event(
                req=req,
                runtime_tool_plan=error_tool_plan,
                run_id=run_id,
                incident_id=incident_id,
                phase="failed",
            )
            LAST_RCA_CONTEXT = rca_context_event["context"]
            yield sse(rca_context_event)
            log_audit_record(
                build_trace_record(
                    action="chat_request_failed",
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                    target={"error": safe_detail},
                )
            )
            increment_metric("aiops_chat_failed_total")
            record_workflow(
                run_id=run_id,
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                stage="failed",
                status="failed",
                subject=subject,
                target={"error": safe_detail},
            )
            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "failed",
                    "message": safe_detail,
                }
            )
            yield sse({"type": "error", "message": safe_detail})
            yield sse("[DONE]")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
