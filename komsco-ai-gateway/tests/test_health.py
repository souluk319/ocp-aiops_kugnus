import asyncio
import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException

import komsco_ai_gateway.action_executor as action_executor
import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.answer_planning import (
    ANSWER_KIND_RCA,
    ANSWER_KIND_RUNTIME_HEALTH,
    build_gateway_evidence_snapshot,
    classify_fallback_answer_kind,
)
from komsco_ai_gateway.host_diagnostics_collector import collect_host_diagnostics
from komsco_ai_gateway.host_diagnostics_controller import build_diagnostic_job_manifest
from komsco_ai_gateway.followup_selection import (
    extract_numbered_followups,
    resolve_numeric_followup_message,
    selected_followup_index,
)
from komsco_ai_gateway.main import (
    ACTION_PROPOSALS,
    ACTION_REGISTRY_DIGEST,
    ACTION_REGISTRY_ENTRIES,
    APPROVAL_DECISIONS,
    AUDIT_RECORDS,
    BREAK_GLASS_PROFILE_DIGEST,
    BREAK_GLASS_PROFILES,
    BREAK_GLASS_REQUESTS,
    CHAT_FEEDBACK,
    EXECUTION_RECORDS,
    PREAPPROVED_PATCH_REQUESTS,
    RUNBOOK_PLANS,
    RUNBOOK_REGISTRY_DIGEST,
    RUNBOOK_REGISTRY_ENTRIES,
    SEALED_ACTION_PLANS,
    ActionProposalCreate,
    ActionTarget,
    BreakGlassRequestCreate,
    BreakGlassTargetNode,
    CHAT_TRANSCRIPTS,
    ChatRequest,
    DIAGNOSTIC_REQUESTS,
    EVIDENCE_RECORDS,
    HOST_DIAGNOSTIC_COLLECTOR_DIGEST,
    HOST_DIAGNOSTIC_COLLECTORS,
    ImageAttachment,
    RagDocumentUploadCreate,
    METRICS,
    WORKFLOW_RECORDS,
    app,
    build_attachment_context,
    build_action_proposal_record,
    build_action_proposal_fallback,
    build_action_access_review_request,
    build_aiops_answer_contract_text,
    build_aiops_action_candidates,
    build_aiops_anomaly_summary,
    build_aiops_overview,
    build_active_alerts_rca_evidence,
    build_cluster_summary,
    build_deployment_rollout_evidence,
    build_diagnostic_request_candidate,
    build_diagnostic_request_record,
    build_empty_answer_fallback,
    build_grounded_aiops_answer,
    build_evidence_reference_events,
    build_ols_gateway_context,
    build_ols_context_handoff,
    build_ols_payload,
    build_ols_query,
    should_forward_image_attachments_to_ols,
    build_conversation_cleanup_review_candidate,
    build_node_status_rca_evidence,
    build_break_glass_request_record,
    build_ols_required_failure_answer,
    build_preapproved_patch_record,
    build_rag_answer_citation_text,
    build_rag_context_detail,
    build_runbook_plan_record,
    build_rag_upload_document,
    build_sealed_action_plan_record,
    build_restart_metric_rca_evidence,
    candidate_action_request_digest,
    can_subject_read_record,
    compact_controller_submission,
    build_pod_status_evidence,
    cleanup_scope_clarification_response,
    conversation_focus_from_request,
    DiagnosticEvidencePolicy,
    DiagnosticLimits,
    DiagnosticRequestCreate,
    DiagnosticTargetNode,
    DiagnosticTimeRange,
    PatchPreapprovedFieldCreate,
    RunbookPlanCreate,
    diagnostic_request_digest,
    is_followup_execution_request,
    is_ambiguous_cleanup_review_request,
    is_pod_count_query,
    is_pod_list_request,
    page_context_aiops_execution_mode,
    parse_bool,
    parse_natural_action_intent,
    pod_inventory_action_candidates_from_evidence,
    parse_pod_count_query,
    recent_natural_action_request,
    parse_ols_verify,
    parse_unrestricted_chat_command,
    policy_check_summary,
    normalize_console_page_context,
    normalize_controller_phase,
    sealed_action_plan_digest,
    summarize_policy_detail,
    unresolved_natural_action_response,
    validate_execution_evidence_freshness,
    should_collect_cronjob_activity_evidence,
    should_clarify_cleanup_scope,
    should_create_cleanup_review_candidate,
    should_collect_pod_status_evidence,
    should_collect_rca_signal_evidence,
    split_plain_text_events,
    validate_image_attachments,
)
from komsco_ai_gateway.aiops_core import (
    AiopsCoreError,
    build_hpa_bounds_request,
)
from komsco_ai_gateway.aiops_contracts import (
    build_rca_context,
    build_runtime_safety_contract,
    build_runtime_tool_plan,
)
from komsco_ai_gateway.security import (
    build_evidence_reference,
    classify_request_policy,
    redact_sensitive,
    safe_subject,
)


def test_rag_pdf_upload_parser_extracts_page_marked_text(monkeypatch) -> None:
    class FakePage:
        def __init__(self, text: str) -> None:
            self.text = text

        def extract_text(self) -> str:
            return self.text

    class FakeReader:
        is_encrypted = False
        pages = [FakePage("Cluster upgrade runbook"), FakePage("Check oc get co")]

        def __init__(self, _stream) -> None:
            pass

    monkeypatch.setattr(gateway_main, "PdfReader", FakeReader)

    content, report = gateway_main.extract_rag_upload_file_content(
        "운영가이드.pdf",
        "application/pdf",
        b"%PDF-1.7 fake",
    )

    assert "<!-- page: 1 -->" in content
    assert "Cluster upgrade runbook" in content
    assert report["parser"] == "pypdf"
    assert report["documentFormat"] == "pdf"
    assert report["pageCount"] == 2


def test_rag_upload_content_strips_postgres_unsafe_control_chars() -> None:
    record = build_rag_upload_document(
        RagDocumentUploadCreate(
            name="nul-byte-runbook.md",
            content="alpha\x00beta\x07\n\noc get co",
            namespace="komsco-ai-kugnus",
        ),
        {"username": "admin", "uid": "uid-admin", "groups": ["cluster-admins"]},
    )

    combined_content = "\n".join(str(chunk["content"]) for chunk in record["chunks"])
    assert "\x00" not in combined_content
    assert "\x07" not in combined_content
    assert "alpha beta" in combined_content
    assert "oc get co" in combined_content


def test_rag_backend_status_reports_embedding_model_sent_to_service(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "RAG_BACKEND_URL", "postgresql://rag")
    monkeypatch.setattr(gateway_main, "RAG_EMBEDDING_SERVICE_URL", "http://tei.example/v1")
    monkeypatch.setattr(gateway_main, "RAG_EMBEDDING_MODEL", "dragonkue/bge-m3-ko")

    status = gateway_main.build_rag_backend_status()

    assert status["embeddingServiceConfigured"] is True
    assert status["embeddingModelSentToService"] is True
    assert status["embeddingModelConfiguredButIgnored"] is False
    assert status["activeEmbeddingAlgorithm"] == "semantic-service"


def test_embedding_service_uses_role_based_ollama_api(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"embeddings": [[0.1, 0.2, 0.3]]}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, *, json: dict, headers: dict) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(gateway_main, "RAG_EMBEDDING_SERVICE_URL", "http://ollama.example:11434")
    monkeypatch.setattr(gateway_main, "RAG_EMBEDDING_API_STYLE", "ollama")
    monkeypatch.setattr(gateway_main, "RAG_EMBEDDING_MODEL", "nomic-embed-text:latest")
    monkeypatch.setattr(gateway_main, "RAG_EMBEDDING_TIMEOUT_SECONDS", 1.0)

    vec = asyncio.run(gateway_main.call_embedding_service_async("DB 인증 실패 로그"))

    assert captured["url"] == "http://ollama.example:11434/api/embed"
    assert captured["json"] == {
        "model": "nomic-embed-text:latest",
        "input": "DB 인증 실패 로그",
    }
    assert vec == [0.1, 0.2, 0.3]


def test_parse_bool() -> None:
    assert parse_bool("true")
    assert parse_bool("1")
    assert parse_bool("on")
    assert not parse_bool("false")
    assert not parse_bool(None)
    assert parse_bool(None, default=True)


def test_parse_ols_verify() -> None:
    assert parse_ols_verify(None) is True
    assert parse_ols_verify("true") is True
    assert parse_ols_verify("false") is False
    assert parse_ols_verify("/var/run/configmaps/service-ca/service-ca.crt") == (
        "/var/run/configmaps/service-ca/service-ca.crt"
    )


def parse_sse_events(body: str) -> list[dict | str]:
    events: list[dict | str] = []
    for frame in body.split("\n\n"):
        data_lines = [
            line[len("data:") :].strip()
            for line in frame.splitlines()
            if line.startswith("data:")
        ]
        if not data_lines:
            continue
        raw = "\n".join(data_lines)
        events.append("[DONE]" if raw == "[DONE]" else json.loads(raw))
    return events


def assert_post_answer_rca_before_done(events: list[dict | str]) -> dict:
    assert events[-1] == "[DONE]"
    rca_events = [
        (index, event)
        for index, event in enumerate(events)
        if isinstance(event, dict) and event.get("type") == "rca_context"
    ]
    assert rca_events
    latest_index, latest_event = rca_events[-1]
    assert latest_index == len(events) - 2
    context = latest_event["context"]
    assert context["metadata"]["phase"] == "post_answer"
    assert (
        context["evidence"]["summary"]["collectedCount"] > 0
        or context["evidence"]["summary"]["missingCount"] > 0
        or context["confidence"]["level"] == "insufficient_evidence"
    )
    return context


def test_page_context_aiops_execution_mode_accepts_unrestricted_aliases() -> None:
    unrestricted_req = ChatRequest(
        message="명령 실행",
        pageContext={"aiopsExecutionMode": "unrestricted"},
    )
    assert (
        page_context_aiops_execution_mode(unrestricted_req)
        == "unrestricted"
    )
    assert gateway_main.execution_mode_allows_immediate_actions(unrestricted_req)
    assert (
        page_context_aiops_execution_mode(
            ChatRequest(
                message="명령 실행",
                pageContext={"aiopsExecutionMode": "실험"},
            )
        )
        == "unrestricted"
    )


def test_parse_unrestricted_chat_command_requires_explicit_prefix() -> None:
    assert parse_unrestricted_chat_command("/exec printf ok") == "printf ok"
    assert parse_unrestricted_chat_command("실행: ```bash\nprintf ok\n```") == "printf ok"
    assert parse_unrestricted_chat_command("파드 목록 조회해줘") == ""


def test_split_plain_text_events_preserves_plain_ols_answer() -> None:
    async def chunks():
        yield "현재 클러스터 노드는 1개이며 Ready 상태입니다.\n---\n참고 링크\n"

    async def run() -> list[dict]:
        return [event async for event in split_plain_text_events(chunks())]

    events = asyncio.run(run())

    assert events
    assert events[0]["type"] == "text"
    assert "Ready 상태" in "".join(str(event.get("content") or "") for event in events)


def test_call_ols_stream_preserves_plain_frames_inside_event_stream(monkeypatch) -> None:
    class FakeStreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def aiter_text(self):
            yield "현재 클러스터 노드는 1개이며 Ready 상태입니다.\\n\\n"

    class FakeStreamContext:
        async def __aenter__(self):
            return FakeStreamResponse()

        async def __aexit__(self, *args) -> None:
            return None

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        def stream(self, *args, **kwargs) -> FakeStreamContext:
            return FakeStreamContext()

    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(gateway_main, "OLS_BASE_URL", "https://ols.test")
    monkeypatch.setattr(gateway_main, "DEV_ECHO", False)

    async def run() -> list[dict]:
        return [
            event
            async for event in gateway_main.call_ols_stream(
                "Bearer test-token",
                "현재 클러스터 노드 상태",
                None,
                [],
            )
        ]

    events = asyncio.run(run())

    assert events
    assert events[0]["type"] == "text"
    assert "Ready 상태" in events[0]["content"]


def test_call_ols_stream_uses_role_based_ollama_chat(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        status_code = 200
        text = ""

        def json(self) -> dict:
            return {"message": {"role": "assistant", "content": "RCA 초안입니다."}}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, *, json: dict, headers: dict) -> FakeResponse:
            captured["url"] = url
            captured["json"] = json
            captured["headers"] = headers
            return FakeResponse()

    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(gateway_main, "LLM_API_STYLE", "ollama")
    monkeypatch.setattr(gateway_main, "LLM_BASE_URL", "http://ollama.example:11434")
    monkeypatch.setattr(gateway_main, "LLM_MODEL", "qwen2.5:7b-instruct")
    monkeypatch.setattr(gateway_main, "LLM_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(gateway_main, "DEV_ECHO", False)

    async def run() -> list[dict]:
        return [
            event
            async for event in gateway_main.call_ols_stream(
                "Bearer test-token",
                "RCA 초안 작성해줘",
                "conv-1",
                [],
            )
        ]

    events = asyncio.run(run())

    assert captured["url"] == "http://ollama.example:11434/api/chat"
    assert captured["json"]["model"] == "qwen2.5:7b-instruct"
    assert captured["json"]["stream"] is False
    assert captured["json"]["think"] is False
    assert events[0]["type"] == "text"
    assert events[0]["content"] == "RCA 초안입니다."
    assert events[-1] == {"type": "end", "conversationId": "conv-1"}


def test_followup_execution_request_accepts_korean_variants() -> None:
    assert is_followup_execution_request("진행해")
    assert is_followup_execution_request("승인해")
    assert is_followup_execution_request("실행해")
    assert is_followup_execution_request("적용")
    assert not is_followup_execution_request("진행 상황 분석해줘")


def test_recent_natural_action_request_uses_previous_user_message() -> None:
    request = ChatRequest(
        message="진행해",
        pageContext={"namespace": "team-a", "aiopsExecutionMode": "unrestricted"},
        recentMessages=[
            {"role": "user", "content": "team-a 네임스페이스의 web-api 파드 4개로 올려줘"},
            {"role": "assistant", "content": "조치 계획을 생성했습니다. 승인하시겠습니까?"},
        ],
    )

    contextual_request = recent_natural_action_request(request)

    assert contextual_request
    assert contextual_request.message == "team-a 네임스페이스의 web-api 파드 4개로 올려줘"
    intent = parse_natural_action_intent(contextual_request)
    assert intent
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "web-api"
    assert intent["parameters"]["replicas"] == 4


def test_unrestricted_command_endpoint_requires_feature_flag(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}

    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", False)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/dev/commands/execute",
                headers={"Authorization": "Bearer test-token"},
                json={"command": "printf should-not-run"},
            )

        assert response.status_code == 403

    asyncio.run(run())


def test_unrestricted_command_endpoint_executes_when_enabled(monkeypatch, tmp_path) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}

    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMAND_CWD", str(tmp_path))
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/dev/commands/execute",
                headers={"Authorization": "Bearer test-token"},
                json={"command": "printf aiops-unrestricted-ok", "timeoutSeconds": 5},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "UnrestrictedCommandExecution"
        assert payload["spec"]["exitCode"] == 0
        assert payload["spec"]["stdout"] == "aiops-unrestricted-ok"
        assert payload["spec"]["timedOut"] is False

    asyncio.run(run())


def test_chat_stream_exec_prefix_runs_unrestricted_command(monkeypatch, tmp_path) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMAND_CWD", str(tmp_path))
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "/exec printf chat-unrestricted-ok",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        command_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "unrestricted_command"
        ]
        text_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        ]
        assert command_results
        assert command_results[0]["status"] == "success"
        assert "chat-unrestricted-ok" in command_results[0]["detail"]
        assert any("chat-unrestricted-ok" in event.get("content", "") for event in text_events)

    asyncio.run(run())




def test_normalize_console_page_context_extracts_namespaced_resource() -> None:
    context = normalize_console_page_context(
        {
            "href": "http://localhost:9000/k8s/ns/team-a/deployments/web",
            "pathname": "/k8s/ns/team-a/deployments/web",
            "title": "ignored browser title",
        }
    )

    assert context["route"] == "k8s"
    assert context["namespace"] == "team-a"
    assert context["resourceList"] == "deployments"
    assert context["resourceKind"] == "Deployment"
    assert context["resourceName"] == "web"
    assert "title" not in context


def test_normalize_console_page_context_extracts_catalog_namespace() -> None:
    context = normalize_console_page_context(
        {
            "href": "http://localhost:9000/catalog/ns/team-a",
            "pathname": "/catalog/ns/team-a",
        }
    )

    assert context["route"] == "catalog"
    assert context["namespace"] == "team-a"
    assert context["resourceKind"] == "Catalog"
    assert context["perspective"] == "developer"


def test_normalize_console_page_context_keeps_aiops_alert_view_context() -> None:
    context = normalize_console_page_context(
        {
            "aiopsViewContext": {
                "pageTitle": "알림 & 이벤트",
                "route": "/dashboards/aiops/alerts",
                "selectedAlert": {"reason": "Readiness 실패 반복 감지"},
                "visibleAlerts": [
                    {
                        "reason": "BackOff 반복 감지",
                        "severity": "risk",
                        "target": "gpu-test-kugnus/Pod/aiops-test-pod-1",
                    }
                ],
            },
            "pathname": "/dashboards/aiops/alerts",
            "title": "ignored browser title",
        }
    )

    assert context["route"] == "dashboards"
    assert context["aiopsViewContext"]["pageTitle"] == "알림 & 이벤트"
    assert context["aiopsViewContext"]["visibleAlerts"][0]["reason"] == "BackOff 반복 감지"
    assert "title" not in context


def test_required_ocp_json_timeout_raises_structured_504() -> None:
    class TimeoutClient:
        async def get(self, *args, **kwargs):
            raise httpx.ConnectTimeout("connect timed out")

    with pytest.raises(HTTPException) as exc:
        asyncio.run(
            gateway_main.fetch_ocp_json(
                TimeoutClient(),
                "/api/v1/nodes",
                "Bearer test-token",
                required=True,
            )
        )

    assert exc.value.status_code == 504
    assert exc.value.detail["code"] == "openshift_api_unavailable"
    assert exc.value.detail["operation"] == "fetch_ocp_json:/api/v1/nodes"


def test_data_source_status_allows_missing_payload_for_unavailable_source() -> None:
    status = gateway_main.data_source_status(
        label="Monitoring public URLs",
        name="monitoring-shared-config",
        path="/api/v1/namespaces/openshift-config-managed/configmaps/monitoring-shared-config",
        reason="OPENSHIFT_API_URL is not configured.",
        status="unavailable",
    )

    assert status["status"] == "unavailable"
    assert status["reason"] == "OPENSHIFT_API_URL is not configured."


def test_redact_sensitive_removes_tokens_and_secret_values() -> None:
    raw = {
        "authorization": "Bearer abcdefghijklmnopqrstuvwxyz",
        "message": "password=supersecret token: sha256~abcdef Bearer abcdefghijklmnopqrstuvwxyz",
        "nested": {"clientSecret": "should-not-leak"},
    }

    redacted = redact_sensitive(raw)

    assert redacted["authorization"] == "[REDACTED]"
    assert "supersecret" not in redacted["message"]
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted["message"]
    assert redacted["nested"]["clientSecret"] == "[REDACTED]"


def test_classify_request_policy_blocks_direct_mutation_intent() -> None:
    policy = classify_request_policy("openshift-monitoring pod 재시작해줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_routes_natural_scale_to_action_proposal() -> None:
    policy = classify_request_policy("web-api 파드 3개로 올려줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_blocks_mutation_action_plan_intent() -> None:
    policy = classify_request_policy("deployment 재시작 계획을 세워줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_routes_action_candidate_button_prompt() -> None:
    policy = classify_request_policy(
        "Deployment `komsco-ai-dev/aiops-two-pod-exec` rollout restart 실행 계획을 생성해줘.\n\n"
        "실행은 바로 하지 말고, 먼저 Action Plan을 만들고 승인 버튼을 기다려."
    )

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_blocks_rollback_action_plan_intent() -> None:
    policy = classify_request_policy("deployment rollout 문제가 있을 때 롤백 계획을 세워줘")

    assert policy["decision"] == "action_proposal_only"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "approval_required"


def test_classify_request_policy_allows_restart_count_analysis() -> None:
    policy = classify_request_policy("현재 클러스터에서 재시작이 많은 Pod를 분석해줘")

    assert policy["decision"] == "allow_evidence_collection"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "low"


def test_classify_request_policy_allows_pod_count_question() -> None:
    policy = classify_request_policy("aiops-two-pod-exec 파드 몇개 띄었어?")

    assert policy["decision"] == "allow_evidence_collection"
    assert policy["mutationAllowed"] is False
    assert policy["risk"] == "low"


def test_parse_pod_count_query_extracts_target_without_hardcoded_name() -> None:
    query = parse_pod_count_query(
        ChatRequest(message="team-a 네임스페이스의 web-api 파드 몇개 떠있어?")
    )

    assert query == {"namespace": "team-a", "targetName": "web-api"}
    assert is_pod_count_query("backend-api pod count 알려줘")
    assert parse_pod_count_query(ChatRequest(message="pod count 알려줘")) == {
        "namespace": "",
        "targetName": "",
    }


def test_pod_status_evidence_trigger_only_for_evidence_check_status_analysis() -> None:
    assert should_collect_pod_status_evidence("현재 클러스터의 Pod 상태와 재시작이 많은 Pod를 분석해줘")
    assert should_collect_pod_status_evidence("파드리스트 조회해줘")
    assert should_collect_pod_status_evidence("aiops-two-pod-exec 파드 몇개 띄었어?")
    assert should_collect_pod_status_evidence("ClusterOperator authentication 상태를 확인해줘")
    assert not should_collect_pod_status_evidence("openshift-monitoring pod 재시작해줘")
    assert should_collect_rca_signal_evidence("최근 경고와 원인을 근거 기준으로 정리해줘")
    assert should_collect_rca_signal_evidence("노드 pressure와 CPU metric도 같이 봐줘")


def test_classify_request_policy_allows_evidence_check_investigation() -> None:
    policy = classify_request_policy("최근 경고와 원인을 근거 기준으로 정리해줘")

    assert policy["decision"] == "allow_evidence_collection"
    assert policy["mutationAllowed"] is False


def test_policy_check_progress_copy_uses_operator_language() -> None:
    evidence_check_policy = classify_request_policy("최근 에러로그 20건 가져와봐")
    action_policy = classify_request_policy("web-api 파드 3개로 올려줘")

    assert policy_check_summary(evidence_check_policy) == "조회 허용"
    assert "Evidence-check evidence allowed" not in policy_check_summary(evidence_check_policy)
    assert "정책 결정: 조회 허용" in summarize_policy_detail(evidence_check_policy)
    assert "내부 결정값: allow_evidence_collection" in summarize_policy_detail(evidence_check_policy)
    assert policy_check_summary(action_policy) == "조치 요청은 Action Plan 경로로 처리"
    assert "Action proposal only" not in policy_check_summary(action_policy)


def test_rag_upload_document_redacts_sensitive_content_before_chunking() -> None:
    request = RagDocumentUploadCreate(
        name="ops-runbook.md",
        content="""
        # 운영 절차

        oc get pods -n openshift-marketplace
        Authorization: Bearer secret-token-value-1234567890
        token: sha256~secret-token-value
        client-key-data: UHJpdmF0ZUtleUJvZHk=
        client-certificate-data: Q2VydGlmaWNhdGVCb2R5
        certificate-authority-data: Q0FCb2R5
        -----BEGIN PRIVATE KEY-----
        PrivateKeyBody
        -----END PRIVATE KEY-----
        """,
        labels={"scenario": "upload_rag"},
    )

    record = build_rag_upload_document(request, {"username": "admin"})
    rendered = json.dumps(record, ensure_ascii=False)

    assert record["document"]["sourceType"] == "user-upload"
    assert record["document"]["chunkCount"] >= 1
    assert record["document"]["checksum"].startswith("sha256:")
    assert "secret-token-value" not in rendered
    assert "PrivateKeyBody" not in rendered
    assert "UHJpdmF0ZUtleUJvZHk" not in rendered
    assert "Q2VydGlmaWNhdGVCb2R5" not in rendered
    assert "Q0FCb2R5" not in rendered
    assert "[REDACTED" in rendered


def test_rag_upload_acl_is_derived_from_current_subject() -> None:
    subject = safe_subject(
        {
            "username": "admin",
            "uid": "uid-admin",
            "groups": ["cluster-admins", "system:authenticated"],
        }
    )

    default_acl_record = build_rag_upload_document(
        RagDocumentUploadCreate(name="ops-runbook.md", content="RAG ACL smoke content."),
        subject,
    )
    restricted_acl_record = build_rag_upload_document(
        RagDocumentUploadCreate(
            name="ops-runbook.md",
            content="RAG ACL smoke content.",
            aclGroups=["cluster-admins"],
        ),
        subject,
    )

    assert set(default_acl_record["document"]["aclGroups"]) == {
        "cluster-admins",
        "uid:uid-admin",
        "user:admin",
    }
    assert "system:authenticated" not in default_acl_record["document"]["aclGroups"]
    assert restricted_acl_record["document"]["aclGroups"] == ["cluster-admins"]

    with pytest.raises(HTTPException) as exc:
        build_rag_upload_document(
            RagDocumentUploadCreate(
                name="ops-runbook.md",
                content="RAG ACL smoke content.",
                aclGroups=["other-team"],
            ),
            subject,
        )
    assert exc.value.status_code == 403


def test_rag_search_acl_filter_hides_other_subject_documents() -> None:
    filters = gateway_main.RagSearchFilters()
    admin_principals = {"cluster-admins", "user:admin", "uid:uid-admin"}
    admin_row = {
        "acl_groups": ["cluster-admins", "user:admin"],
        "customer": "KOMSCO",
        "document_id": "user-upload:admin",
        "namespace": "openshift-marketplace",
        "source_type": "user-upload",
        "version": "v0.1.4",
        "labels": {"freshness": "fresh", "safetyClass": "evidence-check"},
    }
    other_row = {
        "acl_groups": ["other-team", "user:other"],
        "customer": "KOMSCO",
        "document_id": "user-upload:other",
        "namespace": "openshift-marketplace",
        "source_type": "user-upload",
        "version": "v0.1.4",
        "labels": {"freshness": "fresh", "safetyClass": "evidence-check"},
    }

    assert gateway_main.row_matches_rag_filters(admin_row, filters, admin_principals) is True
    assert gateway_main.row_matches_rag_filters(other_row, filters, admin_principals) is False


def test_rag_search_acl_filter_rejects_requested_group_not_owned_by_subject() -> None:
    subject_principals = {"cluster-admins", "user:admin"}
    row = {
        "acl_groups": ["cluster-admins", "user:admin"],
        "customer": "KOMSCO",
        "document_id": "user-upload:admin",
        "namespace": "openshift-marketplace",
        "source_type": "user-upload",
        "version": "v0.1.4",
        "labels": {"freshness": "fresh", "safetyClass": "evidence-check"},
    }

    assert (
        gateway_main.row_matches_rag_filters(
            row,
            gateway_main.RagSearchFilters(aclGroups=["cluster-admins"]),
            subject_principals,
        )
        is True
    )
    assert (
        gateway_main.row_matches_rag_filters(
            row,
            gateway_main.RagSearchFilters(aclGroups=["other-team"]),
            subject_principals,
        )
        is False
    )


def test_rag_search_filter_excludes_stale_and_dangerous_documents_by_default() -> None:
    subject_principals = {"cluster-admins", "user:admin"}
    base_row = {
        "acl_groups": ["cluster-admins", "user:admin"],
        "customer": "KOMSCO",
        "document_id": "user-upload:admin",
        "namespace": "openshift-marketplace",
        "source_type": "user-upload",
        "version": "v0.1.4",
    }

    assert (
        gateway_main.row_matches_rag_filters(
            {**base_row, "labels": {"freshness": "fresh", "safetyClass": "evidence-check"}},
            gateway_main.RagSearchFilters(),
            subject_principals,
        )
        is True
    )
    assert (
        gateway_main.row_matches_rag_filters(
            {**base_row, "labels": {"freshness": "stale", "safetyClass": "evidence-check"}},
            gateway_main.RagSearchFilters(),
            subject_principals,
        )
        is False
    )
    assert (
        gateway_main.row_matches_rag_filters(
            {**base_row, "labels": {"freshness": "fresh", "safetyClass": "dangerous"}},
            gateway_main.RagSearchFilters(),
            subject_principals,
        )
        is False
    )
    assert (
        gateway_main.row_matches_rag_filters(
            {**base_row, "labels": {"freshness": "stale", "safetyClass": "evidence-check"}},
            gateway_main.RagSearchFilters(labels={"freshness": "stale"}),
            subject_principals,
        )
        is True
    )

def test_rag_upload_safety_and_freshness_metadata_are_classified() -> None:
    subject = safe_subject(
        {
            "username": "admin",
            "uid": "uid-admin",
            "groups": ["cluster-admins"],
        }
    )

    stale_evidence_check = build_rag_upload_document(
        RagDocumentUploadCreate(
            name="ops-runbook.md",
            content="Evidence-check runbook. First inspect events and logs.",
            labels={"freshness": "stale", "safetyClass": "evidence-check"},
        ),
        subject,
    )
    dangerous = build_rag_upload_document(
        RagDocumentUploadCreate(
            name="dangerous-runbook.md",
            content="운영자가 승인 없이 oc delete pod bad -n default 를 실행하라고 적은 문서",
            labels={"safetyClass": "evidence-check"},
        ),
        subject,
    )

    assert stale_evidence_check["document"]["labels"]["freshness"] == "stale"
    assert stale_evidence_check["document"]["labels"]["safetyClass"] == "evidence-check"
    assert dangerous["document"]["labels"]["safetyClass"] == "dangerous"
    assert dangerous["chunks"][0]["labels"]["safetyClass"] == "dangerous"


def test_pod_list_request_fallback_returns_list_instead_of_single_pod_analysis() -> None:
    gateway_evidence = "\n".join(
        [
            "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`.",
            "Top container restart counts:",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Last Finished | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | Running (CrashLoopBackOff) / waiting:CrashLoopBackOff | 2026-06-22T00:54:32Z | 0/1 | 158 | Error/1 | 2026-06-22T13:58:35Z | ReplicaSet/sample-crashy-6fd7d7cfd7 |",
            "Current Pod list evidence:",
            "Namespace filter: `team-a`",
            "Rows shown: 2 / 2",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | Running (CrashLoopBackOff) / waiting:CrashLoopBackOff | 2026-06-22T00:54:32Z | 0/1 | 158 | Error/1 | ReplicaSet/sample-crashy-6fd7d7cfd7 |",
            "| team-a | `sleeper-loop-77b4d9c55c-abcde` | `sleeper` | Running / running since 2026-06-22T01:00:00Z | 2026-06-22T00:54:32Z | 1/1 | 374 | Completed/0 | ReplicaSet/sleeper-loop-77b4d9c55c |",
            "| team-a | `healthy-api-7ccbbd8c86-fs28q` | `app` | Running / running since 2026-06-22T00:54:32Z | 2026-06-22T00:54:32Z | 1/1 | 0 | - | ReplicaSet/healthy-api-7ccbbd8c86 |",
        ]
    )

    fallback = build_empty_answer_fallback(
        ChatRequest(message="파드리스트 조회해줘", pageContext={"namespace": "team-a"}),
        classify_request_policy("파드리스트 조회해줘"),
        [],
        gateway_evidence,
    )

    assert "## Pod 상태 목록" in fallback
    assert "### 요약" in fallback
    assert "### 우선순위 표" in fallback
    assert "### 판단" in fallback
    assert "### 다음 확인 명령" in fallback
    assert "### 사용한 확인 결과" in fallback
    assert "문제 의심 Pod/Container" in fallback
    assert "즉시 장애 상태" in fallback
    assert "최근 Error 종료 이력" in fallback
    assert "Completed/0 반복 재시작 이력" in fallback
    assert "우선 확인 대상" in fallback
    assert "`sample-crashy-6fd7d7cfd7-r4nd0`" in fallback
    assert "`sleeper-loop-77b4d9c55c-abcde`" in fallback
    assert "`healthy-api-7ccbbd8c86-fs28q`" in fallback
    assert "oc logs sample-crashy-6fd7d7cfd7-r4nd0 -n team-a -c app --previous --tail=120" in fallback
    assert "oc describe pod sample-crashy-6fd7d7cfd7-r4nd0 -n team-a" in fallback
    assert "장애 확정이 아닙니다" in fallback
    assert "## RCA 보고서" not in fallback
    assert "### 원인 후보" not in fallback
    assert "### 조치 방법" not in fallback
    assert "### 재발 방지" not in fallback
    assert "### 조치 계획" not in fallback
    assert "대상 Pod를 우선 분석" not in fallback
    assert "- 대상:" not in fallback


def test_parse_natural_action_intent_scales_named_deployment() -> None:
    intent = parse_natural_action_intent(
        ChatRequest(message="komsco-ai-dev 네임스페이스의 aiops-two-pod-exec 파드 3개로 올려줘")
    )

    assert intent
    assert intent["toolName"] == "set_replicas_within_bounds"
    assert intent["namespace"] == "komsco-ai-dev"
    assert intent["targetName"] == "aiops-two-pod-exec"
    assert intent["parameters"]["replicas"] == 3


def test_page_context_aiops_execution_mode_defaults_read_only_and_accepts_read_only() -> None:
    assert page_context_aiops_execution_mode(ChatRequest(message="재시작해줘")) == "evidence-check"
    assert not gateway_main.execution_mode_allows_actions(ChatRequest(message="재시작해줘"))

    read_only_req = ChatRequest(
        message="재시작해줘",
        pageContext={"aiopsExecutionMode": "read-only"},
    )
    assert page_context_aiops_execution_mode(read_only_req) == "evidence-check"
    assert not gateway_main.execution_mode_allows_actions(read_only_req)

    evidence_check_req = ChatRequest(
        message="재시작해줘",
        pageContext={"aiopsExecutionMode": "evidence-check"},
    )
    assert page_context_aiops_execution_mode(evidence_check_req) == "evidence-check"
    assert not gateway_main.execution_mode_allows_actions(evidence_check_req)


def test_page_context_aiops_execution_mode_accepts_execute() -> None:
    assert (
        page_context_aiops_execution_mode(
            ChatRequest(
                message="재시작해줘",
                pageContext={"aiopsExecutionMode": "execute"},
            )
        )
        == "execute"
    )


@pytest.mark.parametrize(
    ("message", "expected_namespace", "expected_target", "expected_replicas"),
    [
        ("team-a 네임스페이스의 web-api 파드 5개로 올려줘", "team-a", "web-api", 5),
        ("6:cis 파드 3개로 올려줘", "6", "cis", 3),
        ("cis파드 3개로 올려줘", "", "cis", 3),
        ("komsco-ai-dev/worker 2 replicas로 설정", "komsco-ai-dev", "worker", 2),
        ("batch-worker를 1개로 줄여줘", "prod-a", "batch-worker", 1),
        ("deployment/payment-api 7개로 scale", "payments", "payment-api", 7),
        ("`edge-gateway` pods 4 replicas로 설정", "edge", "edge-gateway", 4),
    ],
)
def test_parse_natural_action_intent_accepts_scale_variants(
    message: str,
    expected_namespace: str,
    expected_target: str,
    expected_replicas: int,
) -> None:
    intent = parse_natural_action_intent(
        ChatRequest(
            message=message,
            pageContext={"namespace": expected_namespace},
        )
    )

    assert intent
    assert intent["toolName"] == "set_replicas_within_bounds"
    assert intent["namespace"] == expected_namespace
    assert intent["targetName"] == expected_target
    assert intent["parameters"]["replicas"] == expected_replicas


def test_parse_natural_action_intent_uses_deployment_page_context_for_scale() -> None:
    intent = parse_natural_action_intent(
        ChatRequest(
            message="3개로 올려줘",
            pageContext={
                "pathname": "/k8s/ns/team-b/deployments/report-api",
            },
        )
    )

    assert intent
    assert intent["toolName"] == "set_replicas_within_bounds"
    assert intent["namespace"] == "team-b"
    assert intent["targetName"] == "report-api"
    assert intent["parameters"]["replicas"] == 3


def test_parse_natural_action_intent_uses_deployment_page_context_for_restart() -> None:
    intent = parse_natural_action_intent(
        ChatRequest(
            message="재시작해줘",
            pageContext={
                "pathname": "/k8s/ns/team-a/deployments/web-api",
            },
        )
    )

    assert intent
    assert intent["toolName"] == "rollout_restart_deployment"
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "web-api"


@pytest.mark.parametrize(
    ("message", "expected_namespace", "expected_target"),
    [
        ("team-c 네임스페이스의 api-gateway 재시작해줘", "team-c", "api-gateway"),
        ("deployment/worker-a rollout restart", "workers", "worker-a"),
        ("`checkout-api` 리스타트", "shop", "checkout-api"),
        (
            "Deployment `komsco-ai-dev/aiops-two-pod-exec` rollout restart 실행 계획을 생성해줘.\n\n"
            "실행은 바로 하지 말고, 먼저 Action Plan을 만들고 승인 버튼을 기다려.",
            "komsco-ai-dev",
            "aiops-two-pod-exec",
        ),
    ],
)
def test_parse_natural_action_intent_accepts_restart_variants(
    message: str,
    expected_namespace: str,
    expected_target: str,
) -> None:
    intent = parse_natural_action_intent(
        ChatRequest(
            message=message,
            pageContext={"namespace": expected_namespace},
        )
    )

    assert intent
    assert intent["toolName"] == "rollout_restart_deployment"
    assert intent["namespace"] == expected_namespace
    assert intent["targetName"] == expected_target


def test_create_natural_action_plan_reports_missing_openshift_api(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "")

    result = asyncio.run(
        gateway_main.create_natural_action_plan(
            ChatRequest(
                message=(
                    "Deployment `komsco-ai-dev/aiops-two-pod-exec` rollout restart 실행 계획을 생성해줘.\n\n"
                    "실행은 바로 하지 말고, 먼저 Action Plan을 만들고 승인 버튼을 기다려."
                ),
                pageContext={"aiopsExecutionMode": "execute"},
            ),
            "Bearer test-token",
            safe_subject({"username": "dev-user", "uid": "uid-dev"}),
            incident_id="incident-test",
            run_id="run-test",
        )
    )

    assert result
    assert result["status"] == "unavailable"
    assert "OpenShift API URL" in gateway_main.natural_action_plan_response(result)


@pytest.mark.parametrize(
    ("message", "expected_namespace", "expected_target", "expected_tool", "expected_kind", "expected_parameters"),
    [
        (
            "team-a 네임스페이스의 deployment/web-api revision 2로 롤백해줘",
            "team-a",
            "web-api",
            "rollback_deployment_to_revision",
            "Deployment",
            {"revision": 2},
        ),
        (
            "team-a 네임스페이스의 deployment/web-api 롤백해줘",
            "team-a",
            "web-api",
            "rollback_deployment_to_revision",
            "Deployment",
            {"revision": None},
        ),
        (
            "team-a 네임스페이스의 pod/web-api-abc 교체해줘",
            "team-a",
            "web-api-abc",
            "evict_one_unhealthy_controller_owned_pod",
            "Pod",
            {"reason": "natural_language_unhealthy_pod_eviction"},
        ),
        (
            "team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘",
            "team-a",
            "web-hpa",
            "set_hpa_bounds",
            "HorizontalPodAutoscaler",
            {"minReplicas": 2, "maxReplicas": 8, "allowMaxIncrease": False},
        ),
    ],
)
def test_parse_natural_action_intent_accepts_agentic_action_variants(
    message: str,
    expected_namespace: str,
    expected_target: str,
    expected_tool: str,
    expected_kind: str,
    expected_parameters: dict[str, object],
) -> None:
    intent = parse_natural_action_intent(ChatRequest(message=message))

    assert intent
    assert intent["toolName"] == expected_tool
    assert intent["kind"] == expected_kind
    assert intent["namespace"] == expected_namespace
    assert intent["targetName"] == expected_target
    for key, value in expected_parameters.items():
        assert intent["parameters"][key] == value


def test_create_natural_action_plan_uses_intent_target_kind(monkeypatch) -> None:
    observed_paths: list[str] = []

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        observed_paths.append(path)
        return {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "metadata": {
                "namespace": "team-a",
                "name": "web-hpa",
                "uid": "hpa-uid-a",
            },
            "spec": {"minReplicas": 1, "maxReplicas": 5},
        }

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)

    result = asyncio.run(
        gateway_main.create_natural_action_plan(
            ChatRequest(message="team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 5로 변경해줘"),
            "Bearer token",
            safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}),
            incident_id="inc-hpa",
            run_id="run-hpa",
        )
    )

    assert result
    assert result["status"] == "planned"
    assert result["target"]["kind"] == "HorizontalPodAutoscaler"
    assert observed_paths == ["/apis/autoscaling/v2/namespaces/team-a/horizontalpodautoscalers/web-hpa"]


def test_create_natural_action_plan_resolves_namespace_from_cluster_deployments(monkeypatch) -> None:
    observed_paths: list[str] = []

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        observed_paths.append(path)
        if path == "/apis/apps/v1/deployments":
            return {
                "items": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {
                            "name": "cis",
                            "namespace": "cis",
                            "uid": "deployment-cis-uid",
                        },
                        "spec": {"replicas": 1},
                    }
                ]
            }
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)

    result = asyncio.run(
        gateway_main.create_natural_action_plan(
            ChatRequest(message="cis파드 3개로 올려줘"),
            "Bearer token",
            safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}),
            incident_id="inc-cis-scale",
            run_id="run-cis-scale",
        )
    )

    assert result
    assert result["status"] == "planned"
    assert result["target"]["namespace"] == "cis"
    assert result["target"]["name"] == "cis"
    assert result["parameters"]["replicas"] == 3
    assert observed_paths == ["/apis/apps/v1/deployments"]


def test_create_natural_action_plan_reports_ambiguous_cluster_matches(monkeypatch) -> None:
    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        if path == "/apis/apps/v1/deployments":
            return {
                "items": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {"name": "web", "namespace": "team-a", "uid": "deployment-a"},
                    },
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {"name": "web", "namespace": "team-b", "uid": "deployment-b"},
                    },
                ]
            }
        raise AssertionError(f"unexpected path: {path}")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)

    result = asyncio.run(
        gateway_main.create_natural_action_plan(
            ChatRequest(message="web 파드 2개로 올려줘"),
            "Bearer token",
            safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}),
            incident_id="inc-web-scale",
            run_id="run-web-scale",
        )
    )

    assert result
    assert result["status"] == "ambiguous"
    assert result["candidates"] == [
        {"kind": "Deployment", "name": "web", "namespace": "team-a"},
        {"kind": "Deployment", "name": "web", "namespace": "team-b"},
    ]


@pytest.mark.parametrize(
    (
        "scenario_id",
        "message",
        "page_context",
        "recent_messages",
        "expected_tool",
        "expected_kind",
        "expected_namespace",
        "expected_target",
    ),
    [
        (
            "S01-explicit-scale",
            "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
            {},
            [],
            "set_replicas_within_bounds",
            "Deployment",
            "team-a",
            "web-api",
        ),
        (
            "S02-contextual-followup-scale",
            "진행해",
            {"aiopsExecutionMode": "unrestricted"},
            [{"role": "user", "content": "team-a 네임스페이스의 web-api 파드 4개로 올려줘"}],
            "set_replicas_within_bounds",
            "Deployment",
            "team-a",
            "web-api",
        ),
        (
            "S03-page-context-rollout-restart",
            "재시작해줘",
            {"pathname": "/k8s/ns/team-a/deployments/web-api"},
            [],
            "rollout_restart_deployment",
            "Deployment",
            "team-a",
            "web-api",
        ),
        (
            "S04-rollback-revision",
            "team-a 네임스페이스의 deployment/web-api revision 2로 롤백해줘",
            {},
            [],
            "rollback_deployment_to_revision",
            "Deployment",
            "team-a",
            "web-api",
        ),
        (
            "S05-unhealthy-pod-eviction",
            "team-a 네임스페이스의 pod/web-api-abc 교체해줘",
            {},
            [],
            "evict_one_unhealthy_controller_owned_pod",
            "Pod",
            "team-a",
            "web-api-abc",
        ),
        (
            "S06-hpa-bounds",
            "team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘",
            {},
            [],
            "set_hpa_bounds",
            "HorizontalPodAutoscaler",
            "team-a",
            "web-hpa",
        ),
    ],
)
def test_agentic_action_scenario_matrix_parses_typed_actions(
    scenario_id: str,
    message: str,
    page_context: dict[str, object],
    recent_messages: list[dict[str, str]],
    expected_tool: str,
    expected_kind: str,
    expected_namespace: str,
    expected_target: str,
) -> None:
    request = ChatRequest(
        message=message,
        pageContext=page_context,
        recentMessages=recent_messages,
    )
    contextual = recent_natural_action_request(request) if is_followup_execution_request(message) else None
    intent = parse_natural_action_intent(contextual or request)

    assert intent, scenario_id
    assert intent["toolName"] == expected_tool
    assert intent["kind"] == expected_kind
    assert intent["namespace"] == expected_namespace
    assert intent["targetName"] == expected_target


def test_agentic_safety_and_evidence_scenario_matrix_covers_non_mutating_paths() -> None:
    ambiguous = ChatRequest(
        message="파드 하나 재시작해줘",
        pageContext={"aiopsExecutionMode": "unrestricted"},
    )
    pod_inventory_plan = build_runtime_tool_plan("문제있는 파드 목록 가져와")
    pod_list_policy = classify_request_policy("team-a 네임스페이스 파드 리스트 조회해줘")
    crashloop_policy = classify_request_policy("CrashLoopBackOff 파드 원인 분석해줘")
    diagnostic_request = DiagnosticRequestCreate(
        collector="node_os_readonly_triage",
        targetNode=DiagnosticTargetNode(name="worker-a", uid="node-uid-a"),
        timeRange=DiagnosticTimeRange(since="2026-06-22T00:00:00Z", until="2026-06-22T00:05:00Z"),
        limits=DiagnosticLimits(),
        evidencePolicy=DiagnosticEvidencePolicy(
            classification="restricted",
            rawStorageAllowed=False,
            redactionPolicyDigest="sha256:test-redaction-policy",
        ),
    )
    diagnostic_candidate = build_diagnostic_request_candidate(
        diagnostic_request,
        safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["ops"]}),
    )

    assert parse_natural_action_intent(ambiguous) is None
    assert "대상 리소스 이름이 명확하지 않습니다" in unresolved_natural_action_response(ambiguous)
    assert is_pod_list_request("team-a 네임스페이스 파드 리스트 조회해줘")
    assert pod_inventory_plan["task_type"] == "pod_inventory"
    assert any(step["tool"] == "openshift_pod_list" for step in pod_inventory_plan["tool_plan"])
    assert pod_list_policy["decision"] == "allow_evidence_collection"
    assert should_collect_pod_status_evidence("CrashLoopBackOff 파드 원인 분석해줘")
    assert crashloop_policy["decision"] == "allow_evidence_collection"
    assert diagnostic_candidate["collector"] == "node_os_readonly_triage"
    assert diagnostic_candidate["targetNode"]["name"] == "worker-a"
    assert diagnostic_request_digest(diagnostic_candidate).startswith("sha256:")


def test_cronjob_activity_evidence_trigger_for_15_minute_activity() -> None:
    assert should_collect_cronjob_activity_evidence("여기 15분 단위로 이러는데 맞아?")
    assert should_collect_cronjob_activity_evidence("notebook-cleaner CronJob 이 정상인지 확인해줘")
    assert not should_collect_cronjob_activity_evidence("현재 노드 상태 요약해줘")


def test_build_cluster_summary_returns_real_operational_counts() -> None:
    nodes_payload = {
        "items": [
            {
                "metadata": {
                    "name": "node-1",
                    "labels": {
                        "node-role.kubernetes.io/control-plane": "",
                        "node-role.kubernetes.io/worker": "",
                    },
                },
                "status": {
                    "conditions": [
                        {"type": "Ready", "status": "True"},
                        {"type": "DiskPressure", "status": "False"},
                        {"type": "MemoryPressure", "status": "False"},
                        {"type": "PIDPressure", "status": "False"},
                    ],
                    "nodeInfo": {"kubeletVersion": "v1.33.1", "osImage": "RHEL CoreOS 9.6"},
                },
            }
        ]
    }
    node_metrics_payload = {
        "items": [
            {
                "metadata": {"name": "node-1"},
                "usage": {"cpu": "123m", "memory": "456Mi"},
            }
        ]
    }
    cluster_version_payload = {
        "status": {
            "desired": {"version": "4.20.23"},
            "channel": "stable-4.20",
            "availableUpdates": [{"version": "4.20.24"}],
            "conditions": [{"type": "Upgradeable", "status": "False", "reason": "AdminAck"}],
        }
    }
    cluster_operators_payload = {
        "items": [
            {
                "metadata": {"name": "console"},
                "status": {
                    "conditions": [
                        {"type": "Available", "status": "True"},
                        {"type": "Degraded", "status": "False"},
                        {"type": "Progressing", "status": "False"},
                    ]
                },
            },
            {
                "metadata": {"name": "marketplace"},
                "status": {
                    "conditions": [
                        {"type": "Available", "status": "True"},
                        {
                            "type": "Degraded",
                            "status": "True",
                            "reason": "CatalogPodNotReady",
                            "message": "catalog pod is not ready",
                        },
                        {"type": "Progressing", "status": "False"},
                    ]
                },
            },
        ]
    }
    pods_payload = {
        "items": [
            {
                "metadata": {"name": "cywell-aiops-gateway-1", "namespace": "cywell-aiops"},
                "status": {
                    "containerStatuses": [{"name": "gateway", "ready": True, "restartCount": 0}],
                    "phase": "Running",
                },
            },
            {
                "metadata": {"name": "broken-1", "namespace": "prod"},
                "status": {
                    "containerStatuses": [{"name": "app", "ready": False, "restartCount": 4}],
                    "phase": "Running",
                },
            },
        ]
    }
    deployments_payload = {
        "items": [
            {
                "metadata": {"generation": 1, "name": "cywell-aiops-gateway", "namespace": "cywell-aiops"},
                "spec": {"replicas": 1},
                "status": {"availableReplicas": 1, "observedGeneration": 1, "readyReplicas": 1, "replicas": 1, "updatedReplicas": 1},
            }
        ]
    }
    replicasets_payload = {"items": []}
    daemonsets_payload = {"items": []}
    statefulsets_payload = {"items": []}
    services_payload = {"items": [{"metadata": {"name": "cywell-aiops-gateway", "namespace": "cywell-aiops"}}]}
    routes_payload = {
        "items": [
            {
                "metadata": {"name": "aiops", "namespace": "cywell-aiops"},
                "status": {"ingress": [{"conditions": [{"status": "True", "type": "Admitted"}]}]},
            }
        ]
    }
    pvcs_payload = {"items": []}
    namespaces_payload = {
        "items": [
            {"metadata": {"name": "cywell-aiops"}, "status": {"phase": "Active"}},
            {"metadata": {"name": "old"}, "status": {"phase": "Terminating"}},
        ]
    }

    summary = build_cluster_summary(
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
    )

    assert summary["nodes"]["total"] == 1
    assert summary["nodes"]["ready"] == 1
    assert summary["nodes"]["items"][0]["usage"]["cpu"] == "123m"
    assert summary["operators"]["degraded"] == 1
    assert summary["operators"]["issues"][0]["name"] == "marketplace"
    assert summary["version"]["updateAvailable"] is True
    assert summary["version"]["availableUpdates"] == ["4.20.24"]
    assert summary["version"]["upgradeable"] is False
    assert summary["resources"]["issues"] >= 2
    assert {item["id"] for item in summary["resources"]["items"]} >= {"pods", "deployments", "routes", "namespaces"}
    assert summary["aiopsWorkloads"]["total"] == 1
    assert summary["aiopsWorkloads"]["deployments"][0]["name"] == "cywell-aiops-gateway"
    assert summary["healthScore"] < 100


def test_build_aiops_anomaly_summary_orders_stage2_signals() -> None:
    cluster_summary = {
        "operators": {
            "issues": [
                {
                    "available": False,
                    "degraded": True,
                    "message": "OAuth route unavailable",
                    "name": "authentication",
                    "progressing": False,
                    "reason": "RouteHealth_Failed",
                    "upgradeable": "True",
                }
            ]
        },
        "version": {
            "channel": "stable-4.20",
            "upgradeable": False,
            "upgradeableMessage": "AdminAckRequired blocks upgrade",
            "upgradeableReason": "AdminAckRequired",
            "version": "4.20.23",
        },
    }
    pods_payload = {
        "items": [
            {
                "metadata": {"name": "api-1", "namespace": "prod"},
                "status": {
                    "containerStatuses": [
                        {
                            "lastState": {"terminated": {"reason": "Error"}},
                            "name": "api",
                            "restartCount": 12,
                            "state": {"waiting": {"message": "back-off restarting", "reason": "CrashLoopBackOff"}},
                        }
                    ],
                    "phase": "Running",
                },
            },
            {
                "metadata": {"name": "worker-1", "namespace": "prod"},
                "status": {
                    "containerStatuses": [
                        {
                            "name": "worker",
                            "restartCount": 0,
                            "state": {"waiting": {"message": "manifest unknown", "reason": "ImagePullBackOff"}},
                        }
                    ],
                    "phase": "Pending",
                },
            },
        ]
    }
    events_payload = {
        "items": [
            {
                "involvedObject": {"kind": "Pod", "name": "worker-1", "namespace": "prod"},
                "message": "0/3 nodes are available",
                "metadata": {"name": "worker-schedule", "namespace": "prod"},
                "reason": "FailedScheduling",
                "type": "Warning",
            }
        ]
    }
    alerts_probe = {
        "result": [
            {"metric": {"alertname": "Watchdog"}},
            {"metric": {"alertname": "KubePodCrashLooping", "namespace": "prod", "pod": "api-1", "severity": "warning"}},
        ],
        "status": "available",
    }
    restart_probe = {
        "result": [
            {"metric": {"container": "api", "namespace": "prod", "pod": "api-1"}, "value": [1, "3"]},
        ],
        "status": "available",
    }
    data_sources = [
        {"label": "Cluster operators", "name": "clusteroperators", "path": "", "required": False, "status": "available"},
        {"label": "Pod anomaly signals", "name": "pods", "path": "", "required": True, "status": "available"},
        {"label": "Warning events", "name": "events", "path": "", "required": True, "status": "available"},
        {"label": "Active alerts", "name": "alerts", "path": "", "required": False, "status": "available"},
        {"label": "Restart increase metric", "name": "restart-metrics", "path": "", "required": False, "status": "available"},
    ]

    summary = build_aiops_anomaly_summary(
        cluster_summary,
        pods_payload,
        events_payload,
        alerts_probe,
        restart_probe,
        data_sources,
    )

    spec = summary["spec"]
    findings = spec["findings"]
    finding_types = {finding["type"] for finding in findings}

    assert spec["status"] == "risk"
    assert spec["totals"]["danger"] >= 2
    assert "clusteroperator_condition" in finding_types
    assert "pod_crashloop" in finding_types
    assert "pod_image_pull" in finding_types
    assert "pod_pending" in finding_types
    assert "warning_event" in finding_types
    assert "active_alert" in finding_types
    assert "pod_restart_spike" in finding_types
    assert "upgrade_blocked" in finding_types
    assert [finding["priority"] for finding in findings] == sorted(finding["priority"] for finding in findings)
    assert findings[0]["resource"]["kind"] == "ClusterOperator"
    assert all("candidateCause" in finding and "evidence" in finding for finding in findings)
    assert spec["excludedAlerts"] == [
        {"alertname": "Watchdog", "reason": "Watchdog is an always-firing pipeline health alert."}
    ]


def test_build_aiops_anomaly_summary_does_not_report_false_normal_on_source_gap() -> None:
    cluster_summary = {
        "operators": {"issues": []},
        "version": {"upgradeable": True},
    }

    missing_optional = build_aiops_anomaly_summary(
        cluster_summary,
        {"items": []},
        {"items": []},
        {"status": "unavailable", "result": []},
        {"status": "available", "result": []},
        [
            {"label": "Pod anomaly signals", "name": "pods", "path": "", "required": True, "status": "available"},
            {"label": "Warning events", "name": "events", "path": "", "required": True, "status": "available"},
            {"label": "Active alerts", "name": "alerts", "path": "", "required": False, "status": "unavailable"},
        ],
    )
    failed_required = build_aiops_anomaly_summary(
        cluster_summary,
        None,
        {"items": []},
        {"status": "available", "result": []},
        {"status": "available", "result": []},
        [
            {"label": "Pod anomaly signals", "name": "pods", "path": "", "required": True, "status": "error"},
            {"label": "Warning events", "name": "events", "path": "", "required": True, "status": "available"},
        ],
    )

    assert missing_optional["spec"]["status"] == "unknown"
    assert "정상" not in missing_optional["spec"]["statusLabel"]
    assert failed_required["spec"]["status"] == "error"
    assert failed_required["spec"]["statusLabel"] == "필수 이상 징후 데이터 소스 확인 실패"


def test_build_aiops_action_candidates_are_execute_candidates_and_not_action_records() -> None:
    before_counts = {
        "approvals": len(APPROVAL_DECISIONS),
        "executions": len(EXECUTION_RECORDS),
        "plans": len(SEALED_ACTION_PLANS),
        "proposals": len(ACTION_PROPOSALS),
    }
    cluster_summary = {
        "healthScore": 62,
        "nodes": {"notReady": 0, "pressureCount": 0},
        "operators": {"degraded": 0, "issues": [], "progressing": 0, "unavailable": 0},
        "version": {"upgradeable": True},
    }
    pods_payload = {
        "items": [
            {
                "metadata": {"name": "api-1", "namespace": "prod"},
                "status": {
                    "containerStatuses": [
                        {
                            "lastState": {"terminated": {"reason": "Error"}},
                            "name": "api",
                            "restartCount": 9,
                            "state": {"waiting": {"message": "back-off restarting", "reason": "CrashLoopBackOff"}},
                        }
                    ],
                    "phase": "Running",
                },
            }
        ]
    }
    data_sources = [
        {"label": "Cluster operators", "name": "clusteroperators", "path": "", "required": False, "status": "available"},
        {"label": "Pod anomaly signals", "name": "pods", "path": "", "required": True, "status": "available"},
        {"label": "Warning events", "name": "events", "path": "", "required": True, "status": "available"},
        {"label": "Active alerts", "name": "alerts", "path": "", "required": False, "status": "available"},
        {"label": "Restart increase metric", "name": "restart-metrics", "path": "", "required": False, "status": "available"},
    ]

    anomaly_summary = build_aiops_anomaly_summary(
        cluster_summary,
        pods_payload,
        {"items": []},
        {"result": [], "status": "available"},
        {"result": [], "status": "available"},
        data_sources,
    )
    action_candidates = build_aiops_action_candidates(anomaly_summary, data_sources)
    overview = build_aiops_overview(
        cluster_summary,
        data_sources,
        {"thanos": "https://thanos.test"},
        {"query": "up", "resultCount": 1, "status": "available"},
        anomaly_summary,
    )

    candidate_spec = action_candidates["spec"]
    candidate = candidate_spec["candidates"][0]
    titles = [item["title"] for item in candidate_spec["candidates"]]

    assert action_candidates["kind"] == "AIOpsActionCandidateSummary"
    assert candidate_spec["status"] == "candidates"
    assert candidate_spec["safety"]["mode"] == "execute"
    assert candidate_spec["safety"]["proposalOnly"] is True
    assert candidate_spec["safety"]["mutationsEnabled"] is True
    assert titles[:3] == ["원인 확인 플랜", "Pod 재생성 유도", "수정/롤백 검토 플랜"]
    assert candidate["approvalRequired"] is True
    assert candidate["executable"] is False
    assert candidate["mutationSubmitted"] is False
    assert candidate["executionPolicy"]["executionEnabled"] is False
    assert candidate["statusLabel"] == "원인 확인 플랜"
    assert candidate["sourceType"] == "pod_diagnostic_review"
    assert candidate["riskLevel"] == "low"
    assert candidate["prerequisiteChecks"]
    assert candidate["expectedImpact"]
    assert candidate["verificationChecks"]
    assert candidate["evidenceRefs"][0]["status"] == "collected"
    assert {"apply", "delete", "patch", "scale", "exec"}.issubset(set(candidate["blockedActions"]))
    restart_candidate = candidate_spec["candidates"][1]
    assert restart_candidate["title"] == "Pod 재생성 유도"
    assert restart_candidate["sourceType"] == "pod_crashloop"
    assert restart_candidate["riskLevel"] == "high"
    assert "planId" not in candidate
    assert "approvalId" not in candidate
    assert "executionId" not in candidate
    assert "sealedActionPlan" not in candidate
    assert overview["spec"]["actionCandidates"]["spec"]["candidates"][0]["id"] == candidate["id"]
    assert before_counts == {
        "approvals": len(APPROVAL_DECISIONS),
        "executions": len(EXECUTION_RECORDS),
        "plans": len(SEALED_ACTION_PLANS),
        "proposals": len(ACTION_PROPOSALS),
    }


def test_build_aiops_action_candidates_use_execution_gate_when_available(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "ACTION_EXECUTOR_URL", "http://action-executor.test")

    anomaly_summary = {
        "spec": {
            "findings": [
                {
                    "id": "finding-1",
                    "priority": 1,
                    "resource": {"kind": "Deployment", "name": "api", "namespace": "prod"},
                    "severity": "danger",
                    "source": "pods",
                    "title": "CrashLoopBackOff",
                    "type": "pod_crashloop",
                }
            ],
            "status": "attention",
        }
    }
    data_sources = [
        {"label": "Pod anomaly signals", "name": "pods", "required": True, "status": "available"},
        {
            "label": "Warning events",
            "name": "events",
            "reason": "Kubernetes list response is paginated",
            "required": True,
            "status": "partial",
        },
    ]

    action_candidates = build_aiops_action_candidates(anomaly_summary, data_sources)
    candidate_spec = action_candidates["spec"]
    candidate = candidate_spec["candidates"][0]

    assert candidate_spec["status"] == "candidates"
    assert candidate_spec["safety"]["mode"] == "execute"
    assert candidate_spec["safety"]["proposalOnly"] is False
    assert candidate_spec["safety"]["mutationsEnabled"] is True
    assert candidate["executable"] is True
    assert candidate["executionPolicy"]["executionEnabled"] is True
    assert candidate["executionPolicy"]["proposalOnly"] is False
    assert candidate["statusLabel"] == "승인 후 실행 계획 생성 가능"
    assert candidate["blockedActions"] == []


def test_data_source_status_marks_paginated_lists_as_partial() -> None:
    status = gateway_main.data_source_status(
        label="Pod anomaly signals",
        name="pods",
        path="/api/v1/pods?limit=500",
        payload={"items": [], "metadata": {"continue": "next-page-token"}},
        required=True,
    )

    assert status["status"] == "partial"
    assert status["continueTokenPresent"] is True
    assert "paginated" in status["reason"]


def test_build_node_alert_metric_rca_evidence_summarizes_real_sources() -> None:
    node_evidence = build_node_status_rca_evidence(
        {
            "items": [
                {
                    "metadata": {
                        "labels": {"node-role.kubernetes.io/worker": ""},
                        "name": "worker-a",
                    },
                    "status": {
                        "conditions": [
                            {"type": "Ready", "status": "True"},
                            {"type": "DiskPressure", "status": "False"},
                            {"type": "MemoryPressure", "status": "True"},
                            {"type": "PIDPressure", "status": "False"},
                        ],
                        "nodeInfo": {"kubeletVersion": "v1.33.1"},
                    },
                }
            ]
        },
        {"items": [{"metadata": {"name": "worker-a"}, "usage": {"cpu": "120m", "memory": "512Mi"}}]},
        metrics_status={"status": "available"},
    )
    alert_evidence = build_active_alerts_rca_evidence(
        {
            "result": [
                {"metric": {"alertname": "Watchdog"}},
                {
                    "metric": {
                        "alertname": "KubePodCrashLooping",
                        "namespace": "prod",
                        "pod": "api-1",
                        "severity": "warning",
                    }
                },
            ],
            "resultCount": 2,
            "status": "available",
        }
    )
    metric_evidence = build_restart_metric_rca_evidence(
        {
            "result": [
                {
                    "metric": {"container": "api", "namespace": "prod", "pod": "api-1"},
                    "value": [1, "5"],
                }
            ],
            "resultCount": 1,
            "status": "available",
        }
    )

    assert "EvidenceType: node" in node_evidence
    assert "memory" in node_evidence
    assert "120m" in node_evidence
    assert "EvidenceType: alert" in alert_evidence
    assert "KubePodCrashLooping" in alert_evidence
    assert "excludedWatchdog=1" in alert_evidence
    assert "EvidenceType: metric" in metric_evidence
    assert "Restart increase 1h" in metric_evidence
    assert "| prod | `api-1` | `api` | 5 |" in metric_evidence


def test_build_alert_and_metric_rca_evidence_reports_unavailable_sources() -> None:
    alert_evidence = build_active_alerts_rca_evidence(
        {"status": "unavailable", "reason": "thanosPublicURL is not published"}
    )
    metric_evidence = build_restart_metric_rca_evidence(
        {"status": "error", "reason": "Authorization: Bearer secret-token-value token=raw-secret"}
    )

    assert "Active alert evidence unavailable" in alert_evidence
    assert "thanosPublicURL" in alert_evidence
    assert "Metric RCA evidence unavailable" in metric_evidence
    assert "secret-token-value" not in metric_evidence
    assert "raw-secret" not in metric_evidence


def test_query_thanos_instant_surfaces_prometheus_error_and_partial_results(monkeypatch) -> None:
    class FakeResponse:
        def __init__(self, payload: Mapping[str, object], status_code: int = 200) -> None:
            self._payload = payload
            self.status_code = status_code
            self.text = json.dumps(payload)

        def json(self) -> Mapping[str, object]:
            return self._payload

    class FakeAsyncClient:
        payload: Mapping[str, object] = {"status": "success", "data": {"result": []}}

        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def get(self, *args, **kwargs) -> FakeResponse:
            return FakeResponse(self.payload)

    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", FakeAsyncClient)

    async def run() -> None:
        FakeAsyncClient.payload = {
            "error": "bad_data: query failed",
            "errorType": "bad_data",
            "status": "error",
        }
        error_probe = await gateway_main.query_thanos_instant(
            "https://thanos.test",
            "Bearer token",
            "ALERTS",
        )
        FakeAsyncClient.payload = {
            "data": {"result": [{"metric": {"pod": f"pod-{index}"}, "value": [1, "1"]} for index in range(55)]},
            "status": "success",
        }
        partial_probe = await gateway_main.query_thanos_instant(
            "https://thanos.test",
            "Bearer token",
            "up",
        )

        assert error_probe["status"] == "error"
        assert "bad_data" in error_probe["reason"]
        assert partial_probe["status"] == "partial"
        assert partial_probe["resultCount"] == 55
        assert len(partial_probe["result"]) == 50
        assert "capped" in partial_probe["reason"]

    asyncio.run(run())


def test_split_plain_text_events_extracts_tool_lines() -> None:
    async def chunks():
        yield 'Tool call: {"name": "get_alerts", "args": {"active": true}, "id": "tool-1"}\n'
        yield 'Tool result: {"name": "get_alerts", "status": "success", "content": "{\\"alerts\\":[{},{}]}", "id": "tool-1"}\n'
        yield "현재 확인된 경고를 정리합니다."

    async def run() -> list[dict]:
        return [event async for event in split_plain_text_events(chunks())]

    events = asyncio.run(run())

    assert events[0]["type"] == "tool_call"
    assert events[0]["name"] == "get_alerts"
    assert events[1]["type"] == "tool_result"
    assert events[1]["summary"] == "경고 2건 조회"
    assert events[2] == {"type": "text", "content": "현재 확인된 경고를 정리합니다."}


def test_split_plain_text_events_summarizes_resource_get_progress() -> None:
    async def chunks():
        yield (
            'Tool call: {"name": "resources_get", "args": {"apiVersion": "v1", '
            '"kind": "Pod", "namespace": "example-namespace", '
            '"name": "example-catalog-pod"}, "id": "tool-1"}\n'
        )
        yield (
            'Tool result: {"name": "resources_get", "status": "success", '
            '"content": "apiVersion: v1\\nkind: Pod\\nmetadata:\\n  name: '
            'example-catalog-pod\\n  namespace: example-namespace\\n", '
            '"id": "tool-1"}\n'
        )
        yield (
            'Tool result: {"name": "resources_get", "status": "error", '
            '"content": "Tool failed: resource not allowed", "id": "tool-2"}\n'
        )

    async def run() -> list[dict]:
        return [event async for event in split_plain_text_events(chunks())]

    events = asyncio.run(run())

    assert events[0]["summary"] == "Pod example-namespace/example-catalog-pod 상세 조회"
    assert events[1]["summary"] == "Pod example-namespace/example-catalog-pod 조회 완료"
    assert events[2]["summary"] == "조회 실패: Tool failed: resource not allowed"


def test_can_subject_read_record_requires_same_observed_identity() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    other_subject = safe_subject({"username": "other@example.com", "uid": "uid-2", "groups": ["ops"]})
    record = {"originatingSubject": subject}

    assert can_subject_read_record(record, subject)
    assert not can_subject_read_record(record, other_subject)


def test_chat_feedback_api_persists_rating_comment_and_redacts_secrets(monkeypatch) -> None:
    previous_feedback = dict(CHAT_FEEDBACK)
    previous_metric = METRICS.get("aiops_chat_feedback_total", 0)
    CHAT_FEEDBACK.clear()
    METRICS["aiops_chat_feedback_total"] = 0

    subject = {"username": "tester@example.com", "uid": "uid-tester", "groups": ["ops"]}

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return subject

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {"allowed": True}

    async def fake_persist_record_store(_store_name: str) -> None:
        return None

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "persist_record_store", fake_persist_record_store)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/feedback",
                headers=headers,
                json={
                    "answerContract": "v0281-fixture",
                    "assistantAnswer": "답변에 token=assistant-secret 이 있으면 안 됩니다.",
                    "answerSource": "gateway_direct",
                    "conversationId": "conversation-feedback-test",
                    "feedbackId": "feedback-contract-test",
                    "intent": "namespace_cleanup",
                    "messageId": "message-feedback-test",
                    "mode": "execute",
                    "optionalComment": (
                        "답변은 좋지 않았고 Authorization: Bearer secret-token-value-1234567890 "
                        "token=raw-secret 이 노출되면 안 됩니다."
                    ),
                    "rating": "down",
                    "route": "/dashboards/aiops",
                    "source": "gateway_direct",
                    "timestamp": "2026-07-06T09:00:00Z",
                    "userMessage": "왜 Authorization: Bearer user-secret 이 화면에 보이나요?",
                },
            )
            status_response = await client.get("/v1/aiops/status", headers=headers)
            metrics_response = await client.get("/metrics")

        assert response.status_code == 200
        payload = response.json()
        assert payload["kind"] == "ChatFeedback"
        assert payload["metadata"]["name"] == "feedback-contract-test"
        spec = payload["spec"]
        assert spec["rating"] == "down"
        assert spec["mode"] == "execute"
        assert spec["intent"] == "namespace_cleanup"
        assert spec["source"] == "gateway_direct"
        assert spec["optionalComment"].count("[REDACTED]") >= 2
        assert "secret-token-value" not in spec["optionalComment"]
        assert "raw-secret" not in spec["optionalComment"]
        assert "assistant-secret" not in spec["assistantAnswer"]
        assert "user-secret" not in spec["userMessage"]

        stored = CHAT_FEEDBACK["feedback-contract-test"]
        assert stored["spec"] == spec
        assert stored["subject"]["username"] == "tester@example.com"

        assert status_response.status_code == 200
        status_payload = status_response.json()
        feedback_records = status_payload["spec"]["records"]["chatFeedback"]
        assert len(feedback_records) == 1
        assert feedback_records[0]["metadata"]["name"] == "feedback-contract-test"
        assert feedback_records[0]["spec"]["optionalComment"] == spec["optionalComment"]

        assert metrics_response.status_code == 200
        assert "aiops_chat_feedback_total 1" in metrics_response.text
        assert "aiops_chat_feedback_records 1" in metrics_response.text
        assert "secret-token-value" not in metrics_response.text

    try:
        asyncio.run(run())
    finally:
        CHAT_FEEDBACK.clear()
        CHAT_FEEDBACK.update(previous_feedback)
        METRICS["aiops_chat_feedback_total"] = previous_metric


def test_chat_feedback_api_rejects_records_without_question_and_answer(monkeypatch) -> None:
    previous_feedback = dict(CHAT_FEEDBACK)
    previous_metric = METRICS.get("aiops_chat_feedback_total", 0)
    CHAT_FEEDBACK.clear()
    METRICS["aiops_chat_feedback_total"] = 0

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "tester@example.com", "uid": "uid-tester", "groups": ["ops"]}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/feedback",
                headers=headers,
                json={
                    "answerContract": "v029",
                    "answerSource": "ols_unavailable",
                    "feedbackId": "feedback-empty-transcript",
                    "messageId": "message-empty-transcript",
                    "mode": "read-only",
                    "rating": "down",
                    "route": "/dashboards/aiops/alerts",
                    "timestamp": "2026-07-10T02:28:00Z",
                },
            )

        assert response.status_code == 400
        assert "userMessage and assistantAnswer are required" in response.text
        assert "feedback-empty-transcript" not in CHAT_FEEDBACK
        assert METRICS["aiops_chat_feedback_total"] == 0

    try:
        asyncio.run(run())
    finally:
        CHAT_FEEDBACK.clear()
        CHAT_FEEDBACK.update(previous_feedback)
        METRICS["aiops_chat_feedback_total"] = previous_metric


def test_controller_submission_compaction_keeps_digest_not_raw_log() -> None:
    compacted = compact_controller_submission(
        {
            "spec": {
                "phase": "completed",
                "collectorPod": {
                    "podPhase": "Succeeded",
                    "logPreview": '{"kind":"HostDiagnosticEvidence","spec":{"requestId":"diag-a"}}',
                    "evidenceSummary": {"sections": ["kernel_summary"]},
                },
            }
        }
    )
    collector_pod = compacted["spec"]["collectorPod"]

    assert normalize_controller_phase("completed") == "succeeded"
    assert "logPreview" not in collector_pod
    assert collector_pod["logPreviewDigest"].startswith("sha256:")
    assert collector_pod["logPreviewBytes"] > 0
    assert collector_pod["evidenceSummary"]["sections"] == ["kernel_summary"]


def test_action_registry_contains_allowed_actions() -> None:
    assert ACTION_REGISTRY_DIGEST.startswith("sha256:")
    assert set(ACTION_REGISTRY_ENTRIES) == {
        "rollout_restart_deployment",
        "set_replicas_within_bounds",
        "evict_one_unhealthy_controller_owned_pod",
        "rollback_deployment_to_revision",
        "set_deployment_container_command",
        "set_hpa_bounds",
        "namespace_cleanup_review",
        "test_pod_create_review",
        "create_crashloop_test_pods",
        "pod_diagnostic_review",
        "pod_fix_or_rollback_review",
    }
    assert "patch_resource" not in ACTION_REGISTRY_ENTRIES
    assert "apply_manifest" not in ACTION_REGISTRY_ENTRIES
    assert "run_command" not in ACTION_REGISTRY_ENTRIES


def test_core_action_hpa_bounds_blocks_unreviewed_max_increase() -> None:
    plan = {
        "target": {
            "apiVersion": "autoscaling/v2",
            "kind": "HorizontalPodAutoscaler",
            "namespace": "team-a",
            "name": "web-hpa",
            "uid": "hpa-uid-a",
        },
        "action": {
            "toolName": "set_hpa_bounds",
            "normalizedParameters": {
                "minReplicas": 2,
                "maxReplicas": 8,
                "allowMaxIncrease": False,
            },
        },
    }
    hpa = {
        "metadata": {"namespace": "team-a", "name": "web-hpa", "uid": "hpa-uid-a"},
        "spec": {"minReplicas": 1, "maxReplicas": 5},
    }

    with pytest.raises(AiopsCoreError):
        build_hpa_bounds_request(plan, hpa)

    approved_plan = {
        **plan,
        "action": {
            **plan["action"],
            "normalizedParameters": {
                **plan["action"]["normalizedParameters"],
                "allowMaxIncrease": True,
            },
        },
    }
    request = build_hpa_bounds_request(approved_plan, hpa)

    assert request.path.endswith("/horizontalpodautoscalers/web-hpa")
    assert request.body == {"spec": {"minReplicas": 2, "maxReplicas": 8}}


def test_rag_context_detail_and_answer_citation_hide_source_uri_and_scores() -> None:
    results = [
        {
            "contentPreview": "업로드 문서 preview",
            "documentId": "user-upload:abc123",
            "score": 0.91,
            "sourceType": "user-upload",
            "sourceUri": "upload://user-upload:abc123/ops.md#chunk-0",
            "title": "ops.md",
        }
    ]

    detail = build_rag_context_detail(results, "ok")
    citation = build_rag_answer_citation_text(results)

    assert "Gateway-collected local document evidence" in detail
    assert "ops.md" in detail
    assert "user-upload" in detail
    assert "업로드 문서 preview" in detail
    assert "[ 참고 자료 ]" in citation
    assert "ops.md" in citation
    assert "upload://user-upload:abc123/ops.md#chunk-0" not in detail
    assert "upload://user-upload:abc123/ops.md#chunk-0" not in citation
    assert "score=" not in citation
    assert "0.91" not in detail
    assert "0.91" not in citation
    assert "source:" not in citation
    assert "rawContent" not in citation
