from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol


class ChatLatestStatePort(Protocol):
    def set_runtime_tool_plan(self, value: dict[str, Any] | None) -> None: ...

    def set_rca_context(self, value: dict[str, Any] | None) -> None: ...


class ChatRuntimeBinding(str, Enum):
    ANSWER_POSTPROCESS_STATE = "AnswerPostprocessState"
    DIAGNOSTICS_ENABLED = "DIAGNOSTICS_ENABLED"
    DIRECT_POD_COUNT_FLOW_DEPENDENCIES = "DirectPodCountFlowDependencies"
    GATEWAY_DIRECT_ANSWER_ENABLED = "GATEWAY_DIRECT_ANSWER_ENABLED"
    HOST_DIAGNOSTICS_CONTROLLER_URL = "HOST_DIAGNOSTICS_CONTROLLER_URL"
    HTTP_EXCEPTION = "HTTPException"
    HTTP_EXCEPTION_MESSAGE = "http_exception_message"
    MUTATIONS_ENABLED = "MUTATIONS_ENABLED"
    OLS_STREAM_STATUS = "OLS_STREAM_STATUS"
    OPENSHIFT_API_CA_FILE = "OPENSHIFT_API_CA_FILE"
    OPENSHIFT_API_URL = "OPENSHIFT_API_URL"
    OLS_ANSWER_STATE = "OlsAnswerState"
    RECORD_STORE_ENABLED = "RECORD_STORE_ENABLED"
    TEST_POD_CREATE_ENABLED = "TEST_POD_CREATE_ENABLED"
    TEXT_REFERENCE_FILTER = "TextReferenceFilter"
    TOP_POD_NAMESPACE_FLOW_DEPENDENCIES = "TopPodNamespaceFlowDependencies"
    UNRESTRICTED_COMMANDS_ENABLED = "UNRESTRICTED_COMMANDS_ENABLED"
    UNRESTRICTED_COMMAND_EXECUTE_CREATE = "UnrestrictedCommandExecuteCreate"
    ACTION_CAPABLE_EXECUTION_MODE = "action_capable_execution_mode"
    ACTIVE_LLM_LABEL = "active_llm_label"
    ACTIVE_LLM_STAGE = "active_llm_stage"
    ANSWER_LANGUAGE = "answer_language"
    ANSWER_POSTPROCESS_DEPENDENCIES = "answer_postprocess_dependencies"
    APPEND_GATEWAY_EVIDENCE = "append_gateway_evidence"
    ATTACHMENT_CRONJOB_FLOW_DEPENDENCIES = "attachment_cronjob_flow_dependencies"
    BUILD_CHAT_TRANSCRIPT_RECORD = "build_chat_transcript_record"
    BUILD_EVIDENCE_REFERENCE_EVENTS = "build_evidence_reference_events"
    BUILD_GROUNDED_AIOPS_ANSWER = "build_grounded_aiops_answer"
    BUILD_OLS_GATEWAY_CONTEXT = "build_ols_gateway_context"
    BUILD_OLS_QUERY = "build_ols_query"
    BUILD_POD_COUNT_INVESTIGATION = "build_pod_count_investigation"
    BUILD_RCA_CONTEXT_STREAM_EVENT = "build_rca_context_stream_event"
    BUILD_RUNTIME_SAFETY_CONTRACT = "build_runtime_safety_contract"
    BUILD_RUNTIME_TOOL_PLAN = "build_runtime_tool_plan"
    BUILD_TOP_POD_NAMESPACE_COUNT_RESULT = "build_top_pod_namespace_count_result"
    BUILD_TRACE_RECORD = "build_trace_record"
    CASUAL_IDENTITY_ANSWER = "casual_identity_answer"
    CLASSIFY_REQUEST_POLICY = "classify_request_policy"
    CLEANUP_CHAT_FLOW_DEPENDENCIES = "cleanup_chat_flow_dependencies"
    COLLECT_PAST_POD_RESTART_DEMO_EVIDENCE_EVENTS = "collect_past_pod_restart_demo_evidence_events"
    CONVERSATION_FOCUS_FROM_REQUEST = "conversation_focus_from_request"
    CRASHLOOP_DEMO_TARGET_FROM_REQUEST = "crashloop_demo_target_from_request"
    ENFORCE_PRODUCT_ACCESS_REVIEW = "enforce_product_access_review"
    EXECUTE_UNRESTRICTED_COMMAND_REQUEST = "execute_unrestricted_command_request"
    EXECUTION_MODE_ALLOWS_IMMEDIATE_ACTIONS = "execution_mode_allows_immediate_actions"
    FETCH_OCP_JSON = "fetch_ocp_json"
    FETCH_PRODUCT_ACCESS_REVIEW = "fetch_product_access_review"
    FETCH_SELF_SUBJECT_REVIEW = "fetch_self_subject_review"
    GENERAL_CONCEPT_ANSWER = "general_concept_answer"
    HTTPX = "httpx"
    INCREMENT_METRIC = "increment_metric"
    IS_CASUAL_IDENTITY_REQUEST = "is_casual_identity_request"
    IS_FOLLOWUP_EXECUTION_REQUEST = "is_followup_execution_request"
    IS_GENERAL_CONCEPT_REQUEST = "is_general_concept_request"
    IS_OPENSHIFT_USER_AUTH_FAILURE = "is_openshift_user_auth_failure"
    IS_NAMESPACE_CLEANUP_REQUEST = "is_namespace_cleanup_request"
    IS_POD_NAMESPACE_PATTERN_LOOKUP_REQUEST = "is_pod_namespace_pattern_lookup_request"
    IS_TEST_POD_CREATE_REQUEST = "is_test_pod_create_request"
    IS_TOP_POD_NAMESPACE_QUERY = "is_top_pod_namespace_query"
    JSON = "json"
    LOG_AUDIT_RECORD = "log_audit_record"
    METADATA_NAME = "metadata_name"
    METADATA_NAMESPACE = "metadata_namespace"
    NAMESPACE_CLEANUP_INVENTORY_DEPENDENCIES = "namespace_cleanup_inventory_dependencies"
    NATURAL_ACTION_FOLLOWUP_FLOW_DEPENDENCIES = "natural_action_followup_flow_dependencies"
    NATURAL_ACTION_PROPOSAL_FLOW_DEPENDENCIES = "natural_action_proposal_flow_dependencies"
    NORMALIZE_CONSOLE_PAGE_CONTEXT = "normalize_console_page_context"
    NOW_RFC3339 = "now_rfc3339"
    OLS_ANSWER_FLOW_DEPENDENCIES = "ols_answer_flow_dependencies"
    PAGE_CONTEXT_AIOPS_EXECUTION_MODE = "page_context_aiops_execution_mode"
    PARSE_POD_COUNT_QUERY = "parse_pod_count_query"
    PARSE_RCA_RESULT = "parse_rca_result"
    PARSE_UNRESTRICTED_CHAT_COMMAND = "parse_unrestricted_chat_command"
    PAST_POD_RESTART_DEMO_ACTIVE = "past_pod_restart_demo_active"
    PATH_SEGMENT = "path_segment"
    PERSIST_CHAT_TRANSCRIPT_RECORD = "persist_chat_transcript_record"
    POD_COUNT_INVESTIGATION_RESPONSE = "pod_count_investigation_response"
    POD_EVIDENCE_FLOW_DEPENDENCIES = "pod_evidence_flow_dependencies"
    POLICY_CHECK_SUMMARY = "policy_check_summary"
    PRODUCT_ACCESS_REVIEW_STATUS = "product_access_review_status"
    RAG_EVIDENCE_FLOW_DEPENDENCIES = "rag_evidence_flow_dependencies"
    RCA_PREFLIGHT_FLOW_DEPENDENCIES = "rca_preflight_flow_dependencies"
    RECORD_WORKFLOW = "record_workflow"
    REDACT_SENSITIVE = "redact_sensitive"
    REMEMBER_POD_INVENTORY_ACTION_CANDIDATES = "remember_pod_inventory_action_candidates"
    RESOLVE_NUMERIC_FOLLOWUP_MESSAGE = "resolve_numeric_followup_message"
    RESOURCE_ITEMS = "resource_items"
    RESTART_EVIDENCE_FLOW_DEPENDENCIES = "restart_evidence_flow_dependencies"
    SAFE_SUBJECT = "safe_subject"
    SAFE_EXCEPTION_TEXT = "safe_exception_text"
    SHOULD_COLLECT_POD_STATUS_EVIDENCE_FOR_REQUEST = "should_collect_pod_status_evidence_for_request"
    SHOULD_COLLECT_RCA_SIGNAL_EVIDENCE_FOR_REQUEST = "should_collect_rca_signal_evidence_for_request"
    SHOULD_FILTER_GATEWAY_API_REFERENCES = "should_filter_gateway_api_references"
    SHOULD_FILTER_LOW_SIGNAL_REFERENCES = "should_filter_low_signal_references"
    SSE = "sse"
    START_CLEANUP_CHAT_FLOW = "start_cleanup_chat_flow"
    STREAM_ANSWER_POSTPROCESS = "stream_answer_postprocess"
    STREAM_ATTACHMENT_AND_CRONJOB_PREFLIGHT = "stream_attachment_and_cronjob_preflight"
    STREAM_CHAT_NATURAL_ACTION_FOLLOWUP = "stream_chat_natural_action_followup"
    STREAM_CHAT_NATURAL_ACTION_PROPOSAL = "stream_chat_natural_action_proposal"
    STREAM_DIRECT_POD_COUNT = "stream_direct_pod_count"
    STREAM_NAMESPACE_CLEANUP_INVENTORY = "stream_namespace_cleanup_inventory"
    STREAM_OLS_ANSWER_ATTEMPTS = "stream_ols_answer_attempts"
    STREAM_POD_STATUS_EVIDENCE = "stream_pod_status_evidence"
    STREAM_RAG_EVIDENCE = "stream_rag_evidence"
    STREAM_RCA_PREFLIGHT_EVIDENCE = "stream_rca_preflight_evidence"
    STREAM_RESTART_EVIDENCE = "stream_restart_evidence"
    STREAM_TEST_POD_CREATE = "stream_test_pod_create"
    STREAM_TOP_POD_NAMESPACE_COUNT = "stream_top_pod_namespace_count"
    SUMMARIZE_POLICY_DETAIL = "summarize_policy_detail"
    SUMMARIZE_PRODUCT_ACCESS_REVIEW = "summarize_product_access_review"
    SUMMARIZE_SUBJECT_DETAIL = "summarize_subject_detail"
    TEST_POD_CREATE_REQUEST_FROM_MESSAGE = "test_pod_create_request_from_message"
    TEST_POD_CREATE_TOOL_PLAN = "test_pod_create_tool_plan"
    TEST_POD_FLOW_DEPENDENCIES = "test_pod_flow_dependencies"
    TOP_POD_NAMESPACE_COUNT_RESPONSE = "top_pod_namespace_count_response"
    UNRESTRICTED_COMMAND_RESPONSE = "unrestricted_command_response"
    UUID = "uuid"
    VALIDATE_IMAGE_ATTACHMENTS = "validate_image_attachments"
    VERIFY_USER_ACCESS = "verify_user_access"


class ChatRuntimeBindings(Protocol):
    def resolve(self, binding: ChatRuntimeBinding) -> Any: ...


@dataclass(frozen=True, slots=True)
class ChatOrchestratorDependencies:
    runtime: ChatRuntimeBindings
    latest_state: ChatLatestStatePort


class ChatOrchestrator:
    def __init__(self, dependencies: ChatOrchestratorDependencies) -> None:
        self._dependencies = dependencies

    async def stream(
        self,
        request: Any,
        authorization: str,
    ) -> AsyncIterator[str]:
        async for payload in _stream_impl(
            request,
            authorization,
            self._dependencies.latest_state,
            self,
            self._dependencies.runtime,
        ):
            yield payload

    async def _stream_finalization(
        self,
        *,
        incident_id: str,
        policy: Mapping[str, Any],
        request_id: str,
        run_id: str,
        subject: Mapping[str, Any],
    ) -> AsyncIterator[str]:
        runtime = self._dependencies.runtime
        sse = runtime.resolve(ChatRuntimeBinding.SSE)
        build_trace_record = runtime.resolve(ChatRuntimeBinding.BUILD_TRACE_RECORD)
        log_audit_record = runtime.resolve(ChatRuntimeBinding.LOG_AUDIT_RECORD)
        increment_metric = runtime.resolve(ChatRuntimeBinding.INCREMENT_METRIC)
        record_workflow = runtime.resolve(ChatRuntimeBinding.RECORD_WORKFLOW)
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

    async def _stream_failure(
        self,
        *,
        error: Exception,
        incident_id: str,
        policy: Mapping[str, Any],
        request: Any,
        request_id: str,
        run_id: str,
        runtime_tool_plan: dict[str, Any] | None,
        subject: Mapping[str, Any],
    ) -> AsyncIterator[str]:
        runtime = self._dependencies.runtime
        resolve = runtime.resolve
        sse = resolve(ChatRuntimeBinding.SSE)
        http_exception = resolve(ChatRuntimeBinding.HTTP_EXCEPTION)
        is_http_error = isinstance(error, http_exception)
        error_message = (
            resolve(ChatRuntimeBinding.HTTP_EXCEPTION_MESSAGE)(error)
            if is_http_error
            else resolve(ChatRuntimeBinding.SAFE_EXCEPTION_TEXT)(error)
        )
        error_tool_plan = runtime_tool_plan or resolve(ChatRuntimeBinding.BUILD_RUNTIME_TOOL_PLAN)(
            request.message,
            page_context=resolve(ChatRuntimeBinding.NORMALIZE_CONSOLE_PAGE_CONTEXT)(request.pageContext),
            execution_mode=resolve(ChatRuntimeBinding.PAGE_CONTEXT_AIOPS_EXECUTION_MODE)(request),
        )
        rca_context_event = resolve(ChatRuntimeBinding.BUILD_RCA_CONTEXT_STREAM_EVENT)(
            req=request,
            runtime_tool_plan=error_tool_plan,
            run_id=run_id,
            incident_id=incident_id,
            phase="failed",
        )
        self._dependencies.latest_state.set_rca_context(rca_context_event["context"])
        yield sse(rca_context_event)

        failure_target = {"error": error_message}
        if is_http_error:
            failure_target["statusCode"] = error.status_code
        resolve(ChatRuntimeBinding.LOG_AUDIT_RECORD)(
            resolve(ChatRuntimeBinding.BUILD_TRACE_RECORD)(
                action="chat_request_failed",
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
                target=failure_target,
            )
        )
        resolve(ChatRuntimeBinding.INCREMENT_METRIC)("aiops_chat_failed_total")
        resolve(ChatRuntimeBinding.RECORD_WORKFLOW)(
            run_id=run_id,
            incident_id=incident_id,
            policy=policy,
            request_id=request_id,
            stage="failed",
            status="failed",
            subject=subject,
            target=failure_target,
        )

        if is_http_error and resolve(ChatRuntimeBinding.IS_OPENSHIFT_USER_AUTH_FAILURE)(error):
            yield sse(
                {
                    "type": "tool_result",
                    "detail": error_message,
                    "id": f"{request_id}-subject-review",
                    "name": "subject_review",
                    "result": resolve(ChatRuntimeBinding.REDACT_SENSITIVE)(error.detail),
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


async def _stream_impl(
    req: Any,
    authorization: str,
    latest_state: ChatLatestStatePort,
    orchestrator: ChatOrchestrator,
    runtime: ChatRuntimeBindings,
) -> AsyncIterator[str]:
    # Bind once per request so main-module monkeypatches remain request scoped.
    AnswerPostprocessState = runtime.resolve(ChatRuntimeBinding.ANSWER_POSTPROCESS_STATE)
    DIAGNOSTICS_ENABLED = runtime.resolve(ChatRuntimeBinding.DIAGNOSTICS_ENABLED)
    DirectPodCountFlowDependencies = runtime.resolve(ChatRuntimeBinding.DIRECT_POD_COUNT_FLOW_DEPENDENCIES)
    GATEWAY_DIRECT_ANSWER_ENABLED = runtime.resolve(ChatRuntimeBinding.GATEWAY_DIRECT_ANSWER_ENABLED)
    HOST_DIAGNOSTICS_CONTROLLER_URL = runtime.resolve(ChatRuntimeBinding.HOST_DIAGNOSTICS_CONTROLLER_URL)
    HTTPException = runtime.resolve(ChatRuntimeBinding.HTTP_EXCEPTION)
    MUTATIONS_ENABLED = runtime.resolve(ChatRuntimeBinding.MUTATIONS_ENABLED)
    OLS_STREAM_STATUS = runtime.resolve(ChatRuntimeBinding.OLS_STREAM_STATUS)
    OPENSHIFT_API_CA_FILE = runtime.resolve(ChatRuntimeBinding.OPENSHIFT_API_CA_FILE)
    OPENSHIFT_API_URL = runtime.resolve(ChatRuntimeBinding.OPENSHIFT_API_URL)
    OlsAnswerState = runtime.resolve(ChatRuntimeBinding.OLS_ANSWER_STATE)
    RECORD_STORE_ENABLED = runtime.resolve(ChatRuntimeBinding.RECORD_STORE_ENABLED)
    TEST_POD_CREATE_ENABLED = runtime.resolve(ChatRuntimeBinding.TEST_POD_CREATE_ENABLED)
    TextReferenceFilter = runtime.resolve(ChatRuntimeBinding.TEXT_REFERENCE_FILTER)
    TopPodNamespaceFlowDependencies = runtime.resolve(ChatRuntimeBinding.TOP_POD_NAMESPACE_FLOW_DEPENDENCIES)
    UNRESTRICTED_COMMANDS_ENABLED = runtime.resolve(ChatRuntimeBinding.UNRESTRICTED_COMMANDS_ENABLED)
    UnrestrictedCommandExecuteCreate = runtime.resolve(ChatRuntimeBinding.UNRESTRICTED_COMMAND_EXECUTE_CREATE)
    action_capable_execution_mode = runtime.resolve(ChatRuntimeBinding.ACTION_CAPABLE_EXECUTION_MODE)
    active_llm_label = runtime.resolve(ChatRuntimeBinding.ACTIVE_LLM_LABEL)
    active_llm_stage = runtime.resolve(ChatRuntimeBinding.ACTIVE_LLM_STAGE)
    answer_language = runtime.resolve(ChatRuntimeBinding.ANSWER_LANGUAGE)
    answer_postprocess_dependencies = runtime.resolve(ChatRuntimeBinding.ANSWER_POSTPROCESS_DEPENDENCIES)
    append_gateway_evidence = runtime.resolve(ChatRuntimeBinding.APPEND_GATEWAY_EVIDENCE)
    attachment_cronjob_flow_dependencies = runtime.resolve(ChatRuntimeBinding.ATTACHMENT_CRONJOB_FLOW_DEPENDENCIES)
    build_chat_transcript_record = runtime.resolve(ChatRuntimeBinding.BUILD_CHAT_TRANSCRIPT_RECORD)
    build_evidence_reference_events = runtime.resolve(ChatRuntimeBinding.BUILD_EVIDENCE_REFERENCE_EVENTS)
    build_grounded_aiops_answer = runtime.resolve(ChatRuntimeBinding.BUILD_GROUNDED_AIOPS_ANSWER)
    build_ols_gateway_context = runtime.resolve(ChatRuntimeBinding.BUILD_OLS_GATEWAY_CONTEXT)
    build_ols_query = runtime.resolve(ChatRuntimeBinding.BUILD_OLS_QUERY)
    build_pod_count_investigation = runtime.resolve(ChatRuntimeBinding.BUILD_POD_COUNT_INVESTIGATION)
    build_rca_context_stream_event = runtime.resolve(ChatRuntimeBinding.BUILD_RCA_CONTEXT_STREAM_EVENT)
    build_runtime_safety_contract = runtime.resolve(ChatRuntimeBinding.BUILD_RUNTIME_SAFETY_CONTRACT)
    build_runtime_tool_plan = runtime.resolve(ChatRuntimeBinding.BUILD_RUNTIME_TOOL_PLAN)
    build_top_pod_namespace_count_result = runtime.resolve(ChatRuntimeBinding.BUILD_TOP_POD_NAMESPACE_COUNT_RESULT)
    build_trace_record = runtime.resolve(ChatRuntimeBinding.BUILD_TRACE_RECORD)
    casual_identity_answer = runtime.resolve(ChatRuntimeBinding.CASUAL_IDENTITY_ANSWER)
    classify_request_policy = runtime.resolve(ChatRuntimeBinding.CLASSIFY_REQUEST_POLICY)
    cleanup_chat_flow_dependencies = runtime.resolve(ChatRuntimeBinding.CLEANUP_CHAT_FLOW_DEPENDENCIES)
    collect_past_pod_restart_demo_evidence_events = runtime.resolve(ChatRuntimeBinding.COLLECT_PAST_POD_RESTART_DEMO_EVIDENCE_EVENTS)
    conversation_focus_from_request = runtime.resolve(ChatRuntimeBinding.CONVERSATION_FOCUS_FROM_REQUEST)
    crashloop_demo_target_from_request = runtime.resolve(ChatRuntimeBinding.CRASHLOOP_DEMO_TARGET_FROM_REQUEST)
    enforce_product_access_review = runtime.resolve(ChatRuntimeBinding.ENFORCE_PRODUCT_ACCESS_REVIEW)
    execute_unrestricted_command_request = runtime.resolve(ChatRuntimeBinding.EXECUTE_UNRESTRICTED_COMMAND_REQUEST)
    execution_mode_allows_immediate_actions = runtime.resolve(ChatRuntimeBinding.EXECUTION_MODE_ALLOWS_IMMEDIATE_ACTIONS)
    fetch_ocp_json = runtime.resolve(ChatRuntimeBinding.FETCH_OCP_JSON)
    fetch_product_access_review = runtime.resolve(ChatRuntimeBinding.FETCH_PRODUCT_ACCESS_REVIEW)
    fetch_self_subject_review = runtime.resolve(ChatRuntimeBinding.FETCH_SELF_SUBJECT_REVIEW)
    general_concept_answer = runtime.resolve(ChatRuntimeBinding.GENERAL_CONCEPT_ANSWER)
    httpx = runtime.resolve(ChatRuntimeBinding.HTTPX)
    increment_metric = runtime.resolve(ChatRuntimeBinding.INCREMENT_METRIC)
    is_casual_identity_request = runtime.resolve(ChatRuntimeBinding.IS_CASUAL_IDENTITY_REQUEST)
    is_followup_execution_request = runtime.resolve(ChatRuntimeBinding.IS_FOLLOWUP_EXECUTION_REQUEST)
    is_general_concept_request = runtime.resolve(ChatRuntimeBinding.IS_GENERAL_CONCEPT_REQUEST)
    is_namespace_cleanup_request = runtime.resolve(ChatRuntimeBinding.IS_NAMESPACE_CLEANUP_REQUEST)
    is_pod_namespace_pattern_lookup_request = runtime.resolve(ChatRuntimeBinding.IS_POD_NAMESPACE_PATTERN_LOOKUP_REQUEST)
    is_test_pod_create_request = runtime.resolve(ChatRuntimeBinding.IS_TEST_POD_CREATE_REQUEST)
    is_top_pod_namespace_query = runtime.resolve(ChatRuntimeBinding.IS_TOP_POD_NAMESPACE_QUERY)
    json = runtime.resolve(ChatRuntimeBinding.JSON)
    log_audit_record = runtime.resolve(ChatRuntimeBinding.LOG_AUDIT_RECORD)
    metadata_name = runtime.resolve(ChatRuntimeBinding.METADATA_NAME)
    metadata_namespace = runtime.resolve(ChatRuntimeBinding.METADATA_NAMESPACE)
    namespace_cleanup_inventory_dependencies = runtime.resolve(ChatRuntimeBinding.NAMESPACE_CLEANUP_INVENTORY_DEPENDENCIES)
    natural_action_followup_flow_dependencies = runtime.resolve(ChatRuntimeBinding.NATURAL_ACTION_FOLLOWUP_FLOW_DEPENDENCIES)
    natural_action_proposal_flow_dependencies = runtime.resolve(ChatRuntimeBinding.NATURAL_ACTION_PROPOSAL_FLOW_DEPENDENCIES)
    normalize_console_page_context = runtime.resolve(ChatRuntimeBinding.NORMALIZE_CONSOLE_PAGE_CONTEXT)
    now_rfc3339 = runtime.resolve(ChatRuntimeBinding.NOW_RFC3339)
    ols_answer_flow_dependencies = runtime.resolve(ChatRuntimeBinding.OLS_ANSWER_FLOW_DEPENDENCIES)
    page_context_aiops_execution_mode = runtime.resolve(ChatRuntimeBinding.PAGE_CONTEXT_AIOPS_EXECUTION_MODE)
    parse_pod_count_query = runtime.resolve(ChatRuntimeBinding.PARSE_POD_COUNT_QUERY)
    parse_rca_result = runtime.resolve(ChatRuntimeBinding.PARSE_RCA_RESULT)
    parse_unrestricted_chat_command = runtime.resolve(ChatRuntimeBinding.PARSE_UNRESTRICTED_CHAT_COMMAND)
    past_pod_restart_demo_active = runtime.resolve(ChatRuntimeBinding.PAST_POD_RESTART_DEMO_ACTIVE)
    path_segment = runtime.resolve(ChatRuntimeBinding.PATH_SEGMENT)
    persist_chat_transcript_record = runtime.resolve(ChatRuntimeBinding.PERSIST_CHAT_TRANSCRIPT_RECORD)
    pod_count_investigation_response = runtime.resolve(ChatRuntimeBinding.POD_COUNT_INVESTIGATION_RESPONSE)
    pod_evidence_flow_dependencies = runtime.resolve(ChatRuntimeBinding.POD_EVIDENCE_FLOW_DEPENDENCIES)
    policy_check_summary = runtime.resolve(ChatRuntimeBinding.POLICY_CHECK_SUMMARY)
    product_access_review_status = runtime.resolve(ChatRuntimeBinding.PRODUCT_ACCESS_REVIEW_STATUS)
    rag_evidence_flow_dependencies = runtime.resolve(ChatRuntimeBinding.RAG_EVIDENCE_FLOW_DEPENDENCIES)
    rca_preflight_flow_dependencies = runtime.resolve(ChatRuntimeBinding.RCA_PREFLIGHT_FLOW_DEPENDENCIES)
    record_workflow = runtime.resolve(ChatRuntimeBinding.RECORD_WORKFLOW)
    redact_sensitive = runtime.resolve(ChatRuntimeBinding.REDACT_SENSITIVE)
    remember_pod_inventory_action_candidates = runtime.resolve(ChatRuntimeBinding.REMEMBER_POD_INVENTORY_ACTION_CANDIDATES)
    resolve_numeric_followup_message = runtime.resolve(ChatRuntimeBinding.RESOLVE_NUMERIC_FOLLOWUP_MESSAGE)
    resource_items = runtime.resolve(ChatRuntimeBinding.RESOURCE_ITEMS)
    restart_evidence_flow_dependencies = runtime.resolve(ChatRuntimeBinding.RESTART_EVIDENCE_FLOW_DEPENDENCIES)
    safe_subject = runtime.resolve(ChatRuntimeBinding.SAFE_SUBJECT)
    should_collect_pod_status_evidence_for_request = runtime.resolve(ChatRuntimeBinding.SHOULD_COLLECT_POD_STATUS_EVIDENCE_FOR_REQUEST)
    should_collect_rca_signal_evidence_for_request = runtime.resolve(ChatRuntimeBinding.SHOULD_COLLECT_RCA_SIGNAL_EVIDENCE_FOR_REQUEST)
    should_filter_gateway_api_references = runtime.resolve(ChatRuntimeBinding.SHOULD_FILTER_GATEWAY_API_REFERENCES)
    should_filter_low_signal_references = runtime.resolve(ChatRuntimeBinding.SHOULD_FILTER_LOW_SIGNAL_REFERENCES)
    sse = runtime.resolve(ChatRuntimeBinding.SSE)
    start_cleanup_chat_flow = runtime.resolve(ChatRuntimeBinding.START_CLEANUP_CHAT_FLOW)
    stream_answer_postprocess = runtime.resolve(ChatRuntimeBinding.STREAM_ANSWER_POSTPROCESS)
    stream_attachment_and_cronjob_preflight = runtime.resolve(ChatRuntimeBinding.STREAM_ATTACHMENT_AND_CRONJOB_PREFLIGHT)
    stream_chat_natural_action_followup = runtime.resolve(ChatRuntimeBinding.STREAM_CHAT_NATURAL_ACTION_FOLLOWUP)
    stream_chat_natural_action_proposal = runtime.resolve(ChatRuntimeBinding.STREAM_CHAT_NATURAL_ACTION_PROPOSAL)
    stream_direct_pod_count = runtime.resolve(ChatRuntimeBinding.STREAM_DIRECT_POD_COUNT)
    stream_namespace_cleanup_inventory = runtime.resolve(ChatRuntimeBinding.STREAM_NAMESPACE_CLEANUP_INVENTORY)
    stream_ols_answer_attempts = runtime.resolve(ChatRuntimeBinding.STREAM_OLS_ANSWER_ATTEMPTS)
    stream_pod_status_evidence = runtime.resolve(ChatRuntimeBinding.STREAM_POD_STATUS_EVIDENCE)
    stream_rag_evidence = runtime.resolve(ChatRuntimeBinding.STREAM_RAG_EVIDENCE)
    stream_rca_preflight_evidence = runtime.resolve(ChatRuntimeBinding.STREAM_RCA_PREFLIGHT_EVIDENCE)
    stream_restart_evidence = runtime.resolve(ChatRuntimeBinding.STREAM_RESTART_EVIDENCE)
    stream_test_pod_create = runtime.resolve(ChatRuntimeBinding.STREAM_TEST_POD_CREATE)
    stream_top_pod_namespace_count = runtime.resolve(ChatRuntimeBinding.STREAM_TOP_POD_NAMESPACE_COUNT)
    summarize_policy_detail = runtime.resolve(ChatRuntimeBinding.SUMMARIZE_POLICY_DETAIL)
    summarize_product_access_review = runtime.resolve(ChatRuntimeBinding.SUMMARIZE_PRODUCT_ACCESS_REVIEW)
    summarize_subject_detail = runtime.resolve(ChatRuntimeBinding.SUMMARIZE_SUBJECT_DETAIL)
    test_pod_create_request_from_message = runtime.resolve(ChatRuntimeBinding.TEST_POD_CREATE_REQUEST_FROM_MESSAGE)
    test_pod_create_tool_plan = runtime.resolve(ChatRuntimeBinding.TEST_POD_CREATE_TOOL_PLAN)
    test_pod_flow_dependencies = runtime.resolve(ChatRuntimeBinding.TEST_POD_FLOW_DEPENDENCIES)
    top_pod_namespace_count_response = runtime.resolve(ChatRuntimeBinding.TOP_POD_NAMESPACE_COUNT_RESPONSE)
    unrestricted_command_response = runtime.resolve(ChatRuntimeBinding.UNRESTRICTED_COMMAND_RESPONSE)
    uuid = runtime.resolve(ChatRuntimeBinding.UUID)
    validate_image_attachments = runtime.resolve(ChatRuntimeBinding.VALIDATE_IMAGE_ATTACHMENTS)
    verify_user_access = runtime.resolve(ChatRuntimeBinding.VERIFY_USER_ACCESS)

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
        latest_state.set_runtime_tool_plan(runtime_tool_plan)
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
        latest_state.set_rca_context(rca_context_event["context"])
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
            async for stream_event in stream_test_pod_create(
                authorization=authorization,
                dependencies=test_pod_flow_dependencies(),
                incident_id=incident_id,
                request=req,
                request_id=request_id,
                run_id=run_id,
            ):
                if stream_event.answer_chunk is not None:
                    transcript_answer_chunks.append(stream_event.answer_chunk)
                yield stream_event.payload
            return
        if is_namespace_cleanup_request(req):
            async for stream_event in stream_namespace_cleanup_inventory(
                authorization=authorization,
                dependencies=namespace_cleanup_inventory_dependencies(),
                incident_id=incident_id,
                request=req,
                request_id=request_id,
                run_id=run_id,
            ):
                if stream_event.answer_chunk is not None:
                    transcript_answer_chunks.append(stream_event.answer_chunk)
                yield stream_event.payload
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
            latest_state.set_rca_context(rca_context_event["context"])
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
                    latest_state.set_rca_context(stream_event.latest_rca_context)
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
                    latest_state.set_rca_context(stream_event.latest_rca_context)
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
                    latest_state.set_rca_context(stream_event.latest_rca_context)
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
                    latest_state.set_rca_context(stream_event.latest_rca_context)
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
                    latest_state.set_rca_context(stream_event.latest_rca_context)
                yield stream_event.payload
            if handled:
                return

        image_analysis = None
        async for stream_event in stream_attachment_and_cronjob_preflight(
            authorization=authorization,
            dependencies=attachment_cronjob_flow_dependencies(),
            gateway_evidence=gateway_evidence,
            incident_id=incident_id,
            request=req,
            request_id=request_id,
            run_id=run_id,
            subject=subject,
        ):
            if stream_event.gateway_evidence is not None:
                gateway_evidence = stream_event.gateway_evidence
            if stream_event.image_analysis_updated:
                image_analysis = stream_event.image_analysis
            yield stream_event.payload

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

        async for stream_event in stream_restart_evidence(
            authorization=authorization,
            dependencies=restart_evidence_flow_dependencies(),
            gateway_evidence=gateway_evidence,
            incident_id=incident_id,
            request=req,
            request_id=request_id,
            run_id=run_id,
            runtime_tool_plan=runtime_tool_plan,
            subject=subject,
        ):
            if stream_event.gateway_evidence is not None:
                gateway_evidence = stream_event.gateway_evidence
            yield stream_event.payload
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
            async for stream_event in stream_rca_preflight_evidence(
                authorization=authorization,
                dependencies=rca_preflight_flow_dependencies(),
                gateway_evidence=gateway_evidence,
                incident_id=incident_id,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
            ):
                if stream_event.gateway_evidence is not None:
                    gateway_evidence = stream_event.gateway_evidence
                yield stream_event.payload

        async for stream_event in stream_rag_evidence(
            dependencies=rag_evidence_flow_dependencies(),
            gateway_evidence=gateway_evidence,
            incident_id=incident_id,
            message=req.message,
            request_id=request_id,
            run_id=run_id,
            subject=subject,
        ):
            if stream_event.gateway_evidence is not None:
                gateway_evidence = stream_event.gateway_evidence
            if stream_event.citation_text_updated:
                rag_answer_citation_text = stream_event.citation_text or ""
            yield stream_event.payload

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
        latest_state.set_rca_context(rca_context_event["context"])
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
            latest_state.set_rca_context(rca_context_event["context"])
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
        ols_answer_state = OlsAnswerState()
        async for payload in stream_ols_answer_attempts(
            authorization=authorization,
            dependencies=ols_answer_flow_dependencies(),
            gateway_context=ols_gateway_context,
            incident_id=incident_id,
            ols_query=ols_query,
            request=req,
            request_id=request_id,
            run_id=run_id,
            state=ols_answer_state,
            subject=subject,
            text_reference_filter=text_reference_filter,
        ):
            yield payload
        transcript_answer_chunks.extend(ols_answer_state.answer_chunks)
        emitted_answer_text = ols_answer_state.emitted_answer_text
        ols_tool_results = ols_answer_state.tool_results
        ols_attempt_count = ols_answer_state.attempt_count
        _accumulated_answer_chunks = ols_answer_state.answer_chunks
        postprocess_state = AnswerPostprocessState()
        async for payload in stream_answer_postprocess(
            attempt_count=ols_attempt_count,
            dependencies=answer_postprocess_dependencies(),
            emitted_answer_text=emitted_answer_text,
            gateway_context=ols_gateway_context,
            gateway_evidence=gateway_evidence,
            image_analysis=image_analysis,
            ols_tool_results=ols_tool_results,
            policy=policy,
            pre_answer_rca_context=rca_context_event["context"],
            rag_citation_text=rag_answer_citation_text,
            request=req,
            run_id=run_id,
            runtime_tool_plan=runtime_tool_plan,
            state=postprocess_state,
        ):
            yield payload
        transcript_answer_chunks.extend(postprocess_state.transcript_chunks)
        transcript_answer_contracts.extend(postprocess_state.answer_contracts)
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
        latest_state.set_rca_context(rca_context_event["context"])
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

        async for payload in orchestrator._stream_finalization(
            incident_id=incident_id,
            policy=policy,
            request_id=request_id,
            run_id=run_id,
            subject=subject,
        ):
            yield payload
    except HTTPException as exc:
        async for payload in orchestrator._stream_failure(
            error=exc,
            incident_id=incident_id,
            policy=policy,
            request=req,
            request_id=request_id,
            run_id=run_id,
            runtime_tool_plan=runtime_tool_plan,
            subject=subject,
        ):
            yield payload
    except Exception as exc:
        async for payload in orchestrator._stream_failure(
            error=exc,
            incident_id=incident_id,
            policy=policy,
            request=req,
            request_id=request_id,
            run_id=run_id,
            runtime_tool_plan=runtime_tool_plan,
            subject=subject,
        ):
            yield payload
