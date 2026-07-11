from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from types import FunctionType
from typing import Any, Protocol


class ChatLatestStatePort(Protocol):
    def set_runtime_tool_plan(self, value: dict[str, Any] | None) -> None: ...

    def set_rca_context(self, value: dict[str, Any] | None) -> None: ...


@dataclass(frozen=True, slots=True)
class ChatOrchestratorDependencies:
    runtime_bindings: Mapping[str, Any]
    latest_state: ChatLatestStatePort


class ChatOrchestrator:
    def __init__(self, dependencies: ChatOrchestratorDependencies) -> None:
        self._dependencies = dependencies

    async def stream(
        self,
        request: Any,
        authorization: str,
    ) -> AsyncIterator[str]:
        runtime_globals = dict(_stream_impl.__globals__)
        runtime_globals.update(self._dependencies.runtime_bindings)
        bound_stream = FunctionType(
            _stream_impl.__code__,
            runtime_globals,
            _stream_impl.__name__,
            _stream_impl.__defaults__,
            _stream_impl.__closure__,
        )
        async for payload in bound_stream(
            request,
            authorization,
            self._dependencies.latest_state,
            self,
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
        runtime = self._dependencies.runtime_bindings
        yield runtime["sse"](
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "completed",
                "message": "Gateway 실행 루프 완료",
            }
        )
        completed_audit_record = runtime["build_trace_record"](
            action="chat_request_completed",
            incident_id=incident_id,
            policy=policy,
            request_id=request_id,
            run_id=run_id,
            subject=subject,
        )
        runtime["log_audit_record"](completed_audit_record)
        runtime["increment_metric"]("aiops_chat_completed_total")
        runtime["record_workflow"](
            run_id=run_id,
            incident_id=incident_id,
            policy=policy,
            request_id=request_id,
            stage="completed",
            status="completed",
            subject=subject,
        )
        yield runtime["sse"]("[DONE]")

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
        runtime = self._dependencies.runtime_bindings
        is_http_error = isinstance(error, runtime["HTTPException"])
        error_message = (
            runtime["http_exception_message"](error)
            if is_http_error
            else runtime["safe_exception_text"](error)
        )
        error_tool_plan = runtime_tool_plan or runtime["build_runtime_tool_plan"](
            request.message,
            page_context=runtime["normalize_console_page_context"](request.pageContext),
            execution_mode=runtime["page_context_aiops_execution_mode"](request),
        )
        rca_context_event = runtime["build_rca_context_stream_event"](
            req=request,
            runtime_tool_plan=error_tool_plan,
            run_id=run_id,
            incident_id=incident_id,
            phase="failed",
        )
        self._dependencies.latest_state.set_rca_context(rca_context_event["context"])
        yield runtime["sse"](rca_context_event)

        failure_target = {"error": error_message}
        if is_http_error:
            failure_target["statusCode"] = error.status_code
        runtime["log_audit_record"](
            runtime["build_trace_record"](
                action="chat_request_failed",
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
                target=failure_target,
            )
        )
        runtime["increment_metric"]("aiops_chat_failed_total")
        runtime["record_workflow"](
            run_id=run_id,
            incident_id=incident_id,
            policy=policy,
            request_id=request_id,
            stage="failed",
            status="failed",
            subject=subject,
            target=failure_target,
        )

        if is_http_error and runtime["is_openshift_user_auth_failure"](error):
            yield runtime["sse"](
                {
                    "type": "tool_result",
                    "detail": error_message,
                    "id": f"{request_id}-subject-review",
                    "name": "subject_review",
                    "result": runtime["redact_sensitive"](error.detail),
                    "status": "error",
                    "summary": "OpenShift 사용자 인증 갱신 필요",
                }
            )
            yield runtime["sse"]({"type": "text", "content": error_message})
            yield runtime["sse"](
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "failed",
                    "message": "OpenShift 사용자 인증 갱신 필요",
                }
            )
            yield runtime["sse"]("[DONE]")
            return

        yield runtime["sse"](
            {
                "type": "run_status",
                "runId": run_id,
                "stage": "failed",
                "message": error_message,
            }
        )
        yield runtime["sse"]({"type": "error", "message": error_message})
        yield runtime["sse"]("[DONE]")


async def _stream_impl(
    req: Any,
    authorization: str,
    latest_state: ChatLatestStatePort,
    orchestrator: ChatOrchestrator,
) -> AsyncIterator[str]:

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
