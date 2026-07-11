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
    build_product_access_review_request,
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
    product_access_review_status,
    sealed_action_plan_digest,
    summarize_product_access_review,
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


def test_healthz() -> None:
    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/healthz")

        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    asyncio.run(run())


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


def test_verify_bearer_header_rejects_empty_bearer_token() -> None:
    with pytest.raises(HTTPException) as caught:
        gateway_main.verify_bearer_header("Bearer ")

    assert caught.value.status_code == 401


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


def test_chat_stream_persists_chat_transcript_record(monkeypatch, tmp_path) -> None:
    CHAT_TRANSCRIPTS.clear()
    EVIDENCE_RECORDS.clear()
    gateway_main.LAST_RCA_CONTEXT = None
    transcript_jsonl_path = tmp_path / "chat-transcripts.jsonl"

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_ols_stream(*_args, **_kwargs):
        yield {
            "type": "text",
            "content": "현재 확인된 OpenShift 상태를 기준으로 답변합니다.",
        }
        yield {"type": "end", "conversationId": "conv-transcript-test"}

    async def fake_rag_search(*_args, **_kwargs):
        return ("not_configured", "RAG backend not configured", [])

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fake_ols_stream)
    monkeypatch.setattr(gateway_main, "search_pgvector_runbooks", fake_rag_search)
    monkeypatch.setattr(gateway_main, "CHAT_TRANSCRIPT_JSONL_PATH", str(transcript_jsonl_path))

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "conversationId": "conv-transcript-test",
                    "message": "최근 OpenShift 경고를 근거와 추가 확인으로 나눠줘",
                    "runId": "run-transcript-test",
                },
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        assert len(CHAT_TRANSCRIPTS) == 1
        transcript = next(iter(CHAT_TRANSCRIPTS.values()))
        assert transcript["kind"] == "ChatTranscriptRecord"
        assert transcript["spec"]["conversationId"] == "conv-transcript-test"
        assert transcript["spec"]["runId"] == "run-transcript-test"
        assert "최근 OpenShift 경고" in transcript["spec"]["userMessage"]
        assert "현재 확인된 OpenShift 상태" in transcript["spec"]["assistantAnswer"]
        assert transcript["spec"]["observedState"]["rcaContextDigest"].startswith("sha256:")
        assert transcript["spec"]["observedState"]["taskType"]
        assert transcript["spec"]["workflow"]["incidentId"] == "conv-transcript-test"
        assert status_response.json()["spec"]["records"]["chatTranscripts"][0]["kind"] == "ChatTranscriptRecord"
        jsonl_records = [
            json.loads(line)
            for line in transcript_jsonl_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(jsonl_records) == 1
        assert jsonl_records[0]["kind"] == "ChatTranscriptRecord"
        assert jsonl_records[0]["spec"]["conversationId"] == "conv-transcript-test"
        assert "최근 OpenShift 경고" in jsonl_records[0]["spec"]["userMessage"]
        assert "현재 확인된 OpenShift 상태" in jsonl_records[0]["spec"]["assistantAnswer"]

    asyncio.run(run())


def test_chat_stream_collects_stage3_node_alert_metric_evidence_before_answer(monkeypatch) -> None:
    EVIDENCE_RECORDS.clear()
    gateway_main.LAST_RCA_CONTEXT = None

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_pod_evidence(*_args, **_kwargs) -> str:
        return "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`."

    async def fake_node_evidence(_authorization: str) -> dict:
        return {
            "detail": "Gateway-collected Node status evidence from Kubernetes API `/api/v1/nodes`.",
            "evidenceType": "node",
            "sourcePath": "/api/v1/nodes",
            "status": "success",
            "summary": "Node 상태 RCA 조회 결과 수집 완료",
        }

    async def fake_alert_evidence(_authorization: str) -> dict:
        return {
            "detail": 'Gateway-collected Active alert evidence from Thanos query `ALERTS{alertstate="firing"}`.',
            "evidenceType": "alert",
            "missingReason": "Thanos vector result was capped",
            "sourcePath": "/api/v1/query?query=ALERTS",
            "status": "partial",
            "summary": "Active Alert RCA 증거 부분 수집",
        }

    async def fake_metric_evidence(_authorization: str) -> dict:
        return {
            "detail": "Metric RCA evidence unavailable: status=error, reason=Prometheus query failed",
            "evidenceType": "metric",
            "missingReason": "Prometheus query failed",
            "sourcePath": "/api/v1/query?query=increase",
            "status": "error",
            "summary": "Restart metric RCA 조회 결과 수집 불가",
        }

    async def fake_official_restart_evidence(
        _authorization: str,
        namespace: str,
        request_id: str,
    ) -> list[dict]:
        assert namespace == "default"
        return [
            {
                "type": "tool_result",
                "detail": '{"eventCount": 2, "rawEventMessages": "omitted"}',
                "evidenceType": "event",
                "id": f"{request_id}-official-namespace-restart-events",
                "name": "official_namespace_restart_event_evidence",
                "sourcePath": "/api/v1/namespaces/default/events?limit=200",
                "status": "success",
                "summary": "공식 Pod 재시작 namespace Event 조회 결과 수집 완료",
            },
            {
                "type": "tool_result",
                "detail": '{"candidatePods": [{"name": "sample", "restartCount": 3}]}',
                "evidenceType": "snapshot",
                "id": f"{request_id}-official-namespace-restart-snapshot",
                "name": "official_namespace_restart_snapshot",
                "sourcePath": "/api/v1/namespaces/default/pods?limit=200",
                "status": "success",
                "summary": "공식 Pod 재시작 namespace snapshot 조회 결과 수집 완료",
            },
            {
                "type": "tool_result",
                "detail": '{"rawLogDisclosure": false, "patternCounts": {"OOMKilled": 1}}',
                "evidenceType": "pod_log",
                "id": f"{request_id}-official-namespace-restart-log-patterns",
                "matchedPatternIds": ["OOMKilled"],
                "name": "official_namespace_restart_log_pattern_probe",
                "patternCounts": {"OOMKilled": 1},
                "rawLogDisclosure": False,
                "sourcePath": "/api/v1/namespaces/default/pods/sample/log?previous=true",
                "status": "partial",
                "summary": "공식 Pod 재시작 log pattern 증거 부분 수집",
            },
        ]

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "collect_pod_status_evidence", fake_pod_evidence)
    monkeypatch.setattr(
        gateway_main,
        "collect_official_namespace_restart_evidence_events",
        fake_official_restart_evidence,
    )
    monkeypatch.setattr(gateway_main, "collect_node_status_rca_evidence", fake_node_evidence)
    monkeypatch.setattr(gateway_main, "collect_active_alerts_rca_evidence", fake_alert_evidence)
    monkeypatch.setattr(gateway_main, "collect_restart_metric_rca_evidence", fake_metric_evidence)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "어제 새벽에 default namespace Pod가 왜 재시작됐어?",
                    "runId": "run-stage3-preflight",
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        tool_results = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "tool_result"
        ]
        result_by_name = {event.get("name"): event for event in tool_results}
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        pre_answer = next(
            event["context"]
            for event in rca_events
            if event.get("phase") == "pre_answer"
        )
        step_status = {
            item["evidenceType"]: item
            for item in pre_answer["analysisPlan"]["evidenceCollectionSteps"]
        }
        evidence_ref_results = [
            event["result"]
            for event in tool_results
            if event.get("name") == "evidence_ref"
        ]
        evidence_ref_types = {item.get("evidenceType") for item in evidence_ref_results}

        assert result_by_name["node_status_evidence"]["status"] == "success"
        assert result_by_name["official_namespace_restart_event_evidence"]["status"] == "success"
        assert result_by_name["official_namespace_restart_snapshot"]["status"] == "success"
        assert result_by_name["official_namespace_restart_log_pattern_probe"]["status"] == "partial"
        assert result_by_name["active_alerts_evidence"]["status"] == "partial"
        assert result_by_name["restart_metric_evidence"]["status"] == "error"
        assert {"node", "alert", "event", "metric", "pod_log", "snapshot"} <= evidence_ref_types
        assert step_status["node"]["status"] == "collected"
        assert step_status["alert"]["status"] == "partial"
        assert step_status["event"]["status"] == "collected"
        assert step_status["pod_log"]["status"] == "partial"
        assert step_status["snapshot"]["status"] == "collected"
        assert step_status["metric"]["status"] == "failed"
        assert pre_answer["evidence"]["summary"]["partialCount"] >= 2
        assert "test-token" not in response.text

    asyncio.run(run())


def test_chat_stream_unrestricted_executes_natural_scale_action(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return {"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]}

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_action_access_review(_user_auth_header: str, plan: dict) -> dict:
        target = plan["target"]
        return {
            "allowed": True,
            "enabled": True,
            "resourceAttributes": {
                "group": "apps",
                "name": target["name"],
                "namespace": target["namespace"],
                "resource": "deployments",
                "subresource": "scale",
                "verb": "update",
            },
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, *_, **__) -> dict:
        assert "/apis/apps/v1/namespaces/team-a/deployments/web-api" in path
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "web-api",
                "namespace": "team-a",
                "uid": "deployment-uid-a",
            },
        }

    async def fake_execute_action_with_executor(
        sealed_plan: dict,
        _grant_reference: dict,
        *,
        fallback_authorization: str | None = None,
    ) -> dict:
        assert sealed_plan["action"]["toolName"] == "set_replicas_within_bounds"
        assert sealed_plan["action"]["normalizedParameters"]["replicas"] == 3
        assert fallback_authorization == "Bearer token"
        return {
            "mutationOutcome": {
                "status": "mutation_succeeded",
                "reason": "typed_action_executed",
                "httpStatus": 200,
            },
            "remediationOutcome": {
                "status": "verified",
                "reason": "scale_spec_matches",
                "observedReplicas": 3,
            },
            "executorTrace": {
                "mutationSubmitted": True,
                "toolName": "set_replicas_within_bounds",
            },
        }

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_action_access_review", fake_action_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "execute_action_with_executor", fake_execute_action_with_executor)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 3개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        execute_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_execute"
        ]
        text_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        ]
        assert execute_results
        assert execute_results[0]["status"] == "success"
        assert execute_results[0]["result"]["status"] == "executed"
        assert execute_results[0]["result"]["mutationOutcome"]["status"] == "mutation_succeeded"
        assert len(ACTION_PROPOSALS) == 1
        assert len(SEALED_ACTION_PLANS) == 1
        assert len(APPROVAL_DECISIONS) == 1
        assert len(EXECUTION_RECORDS) == 1
        answer_text = "\n".join(event.get("content", "") for event in text_events)
        plan_id = next(iter(SEALED_ACTION_PLANS))
        approval_id = next(iter(APPROVAL_DECISIONS))
        execution_id = next(iter(EXECUTION_RECORDS))
        assert "실행까지 완료" in answer_text
        assert "- Parameters: `" in answer_text
        assert '"replicas": 3' in answer_text
        assert '"hpaReviewed": false' in answer_text
        assert f"- Plan: `{plan_id}`" in answer_text
        assert f"- Approval: `{approval_id}`" in answer_text
        assert f"- Execution: `{execution_id}`" in answer_text
        assert "- Mutation: `mutation_succeeded` / `typed_action_executed`" in answer_text
        assert "- Verification: `verified` / `scale_spec_matches`" in answer_text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_stream_unrestricted_context_does_not_execute_when_server_flag_disabled(
    monkeypatch,
) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        assert req.message == "team-a 네임스페이스의 web-api 파드 3개로 올려줘"
        return {
            "intent": {
                "kind": "Deployment",
                "namespace": "team-a",
                "parameters": {"replicas": 3},
                "targetName": "web-api",
                "toolName": "set_replicas_within_bounds",
            },
            "planId": "plan-unrestricted-disabled",
            "status": "planned",
            "target": {"kind": "Deployment", "namespace": "team-a", "name": "web-api"},
        }

    async def fail_execute_natural_action_plan_result(*_args, **_kwargs):
        raise AssertionError("unrestricted page context must not execute while server flag is disabled")

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action plan responses")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", False)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fail_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 3개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        assert "plan-unrestricted-disabled" in response.text
        assert "natural_action_execute" not in response.text
        assert "실행까지 완료" not in response.text

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


def test_product_access_review_request_is_config_driven_ssar() -> None:
    request = build_product_access_review_request()

    assert request["apiVersion"] == "authorization.k8s.io/v1"
    assert request["kind"] == "SelfSubjectAccessReview"
    attributes = request["spec"]["resourceAttributes"]
    assert attributes["verb"]
    assert attributes["resource"]
    assert "token" not in str(request).lower()


def test_product_access_review_statuses_are_nonblocking_by_default() -> None:
    review = {
        "allowed": False,
        "enabled": True,
        "reason": "not allowed in this namespace",
        "required": False,
        "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
    }

    assert product_access_review_status(review) == "warning"
    assert "required: False" in summarize_product_access_review(review)


def test_product_access_review_timeout_is_reported_without_500(monkeypatch) -> None:
    class TimeoutClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, *args, **kwargs):
            raise httpx.ConnectTimeout("connect timed out")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example:6443")
    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", TimeoutClient)

    review = asyncio.run(gateway_main.fetch_product_access_review("Bearer test-token"))

    assert review["allowed"] is False
    assert review["enabled"] is True
    assert review["reason"] == "OpenShift API unavailable during product access review"
    assert "openshift_api_unavailable" in review["evaluationError"]


def test_self_subject_review_timeout_raises_structured_504(monkeypatch) -> None:
    class TimeoutClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, *args, **kwargs):
            raise httpx.ConnectTimeout("connect timed out")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.example:6443")
    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", TimeoutClient)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(gateway_main.fetch_self_subject_review("Bearer test-token"))

    assert exc.value.status_code == 504
    assert exc.value.detail["code"] == "openshift_api_unavailable"
    assert exc.value.detail["operation"] == "self_subject_review"


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


def test_numeric_followup_selection_extracts_next_step_options() -> None:
    answer = """
**다음 단계로 무엇을 도와드릴까요?**

1. **비정상 Pod 목록 상세 확인**: 현재 `CrashLoopBackOff` 또는 `Failed` 상태인 Pod들의 이름, 네임스페이스, 최근 로그를 정리해 드릴까요?
2. **원인 분석 (RCA) 시작**: 특정 Pod를 지정해 주시면 Event와 로그를 분석해 정확한 실패 원인을 찾아볼까요?
3. **클러스터 이벤트 점검**: Pod 상태에 영향을 줄 수 있는 Node 이슈나 클러스터 수준 이벤트를 조회해 볼까요?
"""

    assert selected_followup_index("1") == 1
    assert selected_followup_index("2번") == 2
    assert selected_followup_index("세 번째") == 3
    assert extract_numbered_followups(answer) == [
        "비정상 Pod 목록 상세 확인: 현재 CrashLoopBackOff 또는 Failed 상태인 Pod들의 이름, 네임스페이스, 최근 로그를 정리해 드릴까요?",
        "원인 분석 (RCA) 시작: 특정 Pod를 지정해 주시면 Event와 로그를 분석해 정확한 실패 원인을 찾아볼까요?",
        "클러스터 이벤트 점검: Pod 상태에 영향을 줄 수 있는 Node 이슈나 클러스터 수준 이벤트를 조회해 볼까요?",
    ]


def test_numeric_followup_selection_resolves_effective_message_from_recent_answer() -> None:
    answer = """
**다음 단계로 무엇을 도와드릴까요?**

1. **비정상 Pod 목록 상세 확인**: 현재 `CrashLoopBackOff` 또는 `Failed` 상태인 Pod들의 이름, 네임스페이스, 최근 로그를 정리해 드릴까요?
2. **원인 분석 (RCA) 시작**: 특정 Pod를 지정해 주시면 Event와 로그를 분석해 정확한 실패 원인을 찾아볼까요?
3. **클러스터 이벤트 점검**: Pod 상태에 영향을 줄 수 있는 Node 이슈나 클러스터 수준 이벤트를 조회해 볼까요?
"""
    selection = resolve_numeric_followup_message(
        "2",
        [
            {"role": "user", "content": "가능한 AIOps 조치 후보를 정리해줘"},
            {"role": "assistant", "content": answer},
        ],
    )

    assert selection is not None
    assert selection.index == 2
    assert "원인 분석 (RCA) 시작" in selection.effective_message
    assert "2\n" not in selection.effective_message
    assert selection.effective_message.endswith("찾아봐줘")


def test_cleanup_followup_clarifies_recent_test_pod_scope() -> None:
    req = ChatRequest(
        message="안에 있는 파드들이 별 의미없는 테스트용이면 정리좀 할까해서",
        recentMessages=[
            {"role": "user", "content": "테스트 파드가있는 네임스페이스가 뭐가있어?"},
            {
                "role": "assistant",
                "content": "`gpu-test-kugnus` namespace에 `aiops-test-pod-*` 테스트 Pod가 있습니다.",
            },
        ],
    )

    focus = conversation_focus_from_request(req)
    response = cleanup_scope_clarification_response(req, focus)

    assert is_ambiguous_cleanup_review_request(req) is True
    assert should_clarify_cleanup_scope(req, focus) is True
    assert should_create_cleanup_review_candidate(req, focus) is False
    assert focus["namespace"] == "gpu-test-kugnus"
    assert focus["podPattern"] == "aiops-test-pod-*"
    assert "`gpu-test-kugnus`" in response
    assert "`aiops-test-pod-*`" in response
    assert "전체 클러스터" not in response
    assert "Pod 삭제" in response
    assert "직전 대화 기준" not in response
    assert "말하는 것으로 보입니다" not in response
    assert "이 범위로 진행할까요" not in response


def test_resource_summary_rca_prompt_does_not_route_to_namespace_cleanup() -> None:
    req = ChatRequest(
        message=(
            "다음 AIOps for OCP 운영 신호를 RCA 관점으로 분석하고 필요한 경우 "
            "Action Plan 판단 조건까지 제시해줘.\n"
            "대상: 파드 리소스 전체 요약\n"
            "범위: 접근 가능한 전체 namespace\n"
            "신호 성격: 특정 Pod 또는 Deployment 하나가 아니라 클러스터 리소스 집계 결과\n"
            "요청 작업: resource_summary_rca\n"
            "확인 결과:\n"
            "- 리소스 종류: Pod\n"
            "- 전체 수: 309\n"
            "- Ready 수: 208\n"
            "- 이슈 수: 11"
        )
    )

    assert gateway_main.is_resource_summary_rca_request(req) is True
    assert gateway_main.is_namespace_cleanup_request(req) is False
    assert should_clarify_cleanup_scope(req) is False

    plan = build_runtime_tool_plan(req.message)
    assert plan["task_type"] == "resource_summary_rca"
    assert "pod_restart_rca" not in json.dumps(plan, ensure_ascii=False)

    rca_context = build_rca_context(
        message=req.message,
        tool_plan=plan,
        evidence_refs=[
            {
                "contentDigest": "sha256:pod-summary",
                "evidenceId": "ev-pod-summary",
                "eventStatus": "success",
                "evidenceType": "pod_status",
            }
        ],
        run_id="run-resource-summary",
        incident_id="inc-resource-summary",
    )
    contract_text = build_aiops_answer_contract_text(
        policy={"decision": "action_proposal_only"},
        rca_context=rca_context,
        runtime_tool_plan=plan,
    )
    assert "## 조치 판단 조건" in contract_text
    assert "승인 대기 조치" not in contract_text
    assert "[승인 필요]" not in contract_text
    assert "Action Plan 후보를 생성" in contract_text

    ols_query = build_ols_query(req)
    assert "Resource summary RCA contract" in ols_query
    assert "Do not use the heading `승인 대기 조치`" in ols_query
    assert "Do not write `[승인 필요]`" in ols_query


def test_cleanup_scope_confirmation_creates_single_review_candidate() -> None:
    req = ChatRequest(
        message="응, 그 범위로 정리 검토해줘",
        recentMessages=[
            {
                "role": "assistant",
                "content": (
                    "`gpu-test-kugnus`의 `aiops-test-pod-*` 정리 가능 여부를 확인합니다."
                ),
            },
        ],
    )

    focus = conversation_focus_from_request(req)
    candidate = build_conversation_cleanup_review_candidate(
        focus,
        incident_id="incident-test",
        run_id="run-test",
    )

    assert should_create_cleanup_review_candidate(req, focus) is True
    assert candidate["sourceType"] == "test_pod_cleanup_review"
    assert candidate["title"] == "테스트 Pod 정리 검토"
    assert candidate["executable"] is False
    assert candidate["target"]["namespace"] == "gpu-test-kugnus"
    assert candidate["target"]["name"] == "aiops-test-pod-*"
    assert "Pod 재생성 유도" not in json.dumps(candidate, ensure_ascii=False)
    assert "수정/롤백 검토" not in json.dumps(candidate, ensure_ascii=False)


def test_cleanup_followup_latest_delete_uses_common_pod_pattern() -> None:
    req = ChatRequest(
        message="제일 나중에 만들어진 순서대로 2개만 삭제해도 될까",
        recentMessages=[
            {
                "role": "assistant",
                "content": (
                    "`gpu-test-kugnus` 네임스페이스에 테스트 Pod가 있습니다.\n"
                    "- `aiops-test-pod-mr8vpb3y-1`\n"
                    "- `aiops-test-pod-mr8vpb3y-2`\n"
                    "- `aiops-test-pod-mr8vpb3y-3`"
                ),
            },
        ],
    )

    focus = conversation_focus_from_request(req)

    assert focus["intent"] == "cleanup_delete_review"
    assert focus["namespace"] == "gpu-test-kugnus"
    assert focus["podPattern"] == "aiops-test-pod-*"
    assert gateway_main.cleanup_delete_count_from_message(req.message) == 2
    assert gateway_main.should_create_latest_cleanup_delete_review_candidate(req, focus) is True


def test_cleanup_latest_delete_review_candidate_renders_table_and_single_candidate() -> None:
    req = ChatRequest(
        message="제일 나중에 만들어진 순서대로 2개만 삭제해도 될까",
        recentMessages=[
            {
                "role": "assistant",
                "content": (
                    "`gpu-test-kugnus` 네임스페이스에 `aiops-test-pod-*` 테스트 Pod가 있습니다."
                ),
            },
        ],
    )
    gateway_evidence = """
Current Pod list evidence:
Namespace filter: all-accessible-namespaces
Rows shown: 4 / 4
| Namespace | Pod | Container | Current state | Pod start | Ready | Restarts | Last state | Owner |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| gpu-test-kugnus | aiops-test-pod-old-1 | sleeper | Completed | 2026-07-09T08:30:00Z | 0/1 | 0 | Completed/0 | Job/old |
| gpu-test-kugnus | aiops-test-pod-new-1 | sleeper | Completed | 2026-07-09T09:30:00Z | 0/1 | 0 | Completed/0 | Job/new |
| gpu-test-kugnus | aiops-test-pod-new-2 | sleeper | Completed | 2026-07-09T09:35:00Z | 0/1 | 0 | Completed/0 | Job/new |
| other | aiops-test-pod-new-3 | sleeper | Completed | 2026-07-09T09:40:00Z | 0/1 | 0 | Completed/0 | Job/other |
Spec evidence for currently non-healthy or waiting containers:
"""

    focus = conversation_focus_from_request(req)
    selected_rows = gateway_main.select_latest_cleanup_pod_rows(focus, gateway_evidence, 2)
    candidate = build_conversation_cleanup_review_candidate(
        focus,
        incident_id="incident-test",
        run_id="run-test",
        selected_rows=selected_rows,
        requested_count=2,
    )
    answer = gateway_main.cleanup_review_candidate_response(candidate)

    assert [row["pod"] for row in selected_rows] == [
        "aiops-test-pod-new-2",
        "aiops-test-pod-new-1",
    ]
    assert candidate["sourceType"] == "test_pod_latest_delete_review"
    assert candidate["title"] == "최신 테스트 Pod 2개 삭제 검토"
    assert candidate["mutationSubmitted"] is False
    assert candidate["executable"] is False
    assert len(candidate["parameters"]["selectedPods"]) == 2
    assert "| 순서 | Namespace | Pod 이름 | 생성/시작 시간 | 현재 상태 | 삭제 판단 |" in answer
    assert "`aiops-test-pod-new-2`" in answer
    assert "`aiops-test-pod-new-1`" in answer
    assert "직전 대화 기준" not in answer
    assert "말하는 것으로 보입니다" not in answer
    assert "이 범위로 진행할까요" not in answer
    assert "승인 전에는 Pod 삭제" in answer


def test_ambiguous_cleanup_does_not_create_pod_inventory_candidates() -> None:
    req = ChatRequest(
        message="안에 있는 파드들이 별 의미없는 테스트용이면 정리좀 할까해서",
        recentMessages=[
            {
                "role": "assistant",
                "content": "`gpu-test-kugnus` namespace에 `aiops-test-pod-*` 테스트 Pod가 있습니다.",
            },
        ],
    )
    evidence = """
## Pod 인벤토리
| 우선순위 | Namespace | Pod | Container | 현재 상태 | Ready | Restart | Last State | 판단 |
| 높음 | gpu-test-kugnus | `aiops-test-pod-a` | `main` | Running / running | 1/1 | 0 | - | 현재 목록 기준 즉시 장애 신호 낮음 |
"""

    candidates = pod_inventory_action_candidates_from_evidence(
        req,
        evidence,
        incident_id="incident-test",
        run_id="run-test",
    )

    assert candidates == []


def test_pod_namespace_pattern_lookup_renders_grouped_table() -> None:
    req = ChatRequest(message='이름에 "test"가 포함된 파드가 있는 네임스페이스 알려줄래?')
    gateway_evidence = """
Current Pod list evidence:
Namespace filter: `all-accessible-namespaces`
Rows shown: 4 / 4
| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |
| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-1` | `main` | Running / running | 2026-07-09T01:00:00Z | 1/1 | 0 | - | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-2` | `main` | Running / running | 2026-07-09T01:00:00Z | 1/1 | 0 | - | - |
| aiops-demo | `aiops-demo-web-75b5bc6bc7-pmkzh` | `main` | Running / running | 2026-07-09T01:00:00Z | 1/1 | 0 | - | - |
| komsco-ai-dev | `normal-app-pod` | `main` | Running / running | 2026-07-09T01:00:00Z | 1/1 | 0 | - | - |
"""

    answer = gateway_main.build_pod_namespace_pattern_lookup_answer(req, gateway_evidence)

    assert answer is not None
    assert "## 테스트 Pod 네임스페이스" in answer
    assert "- 매칭 Pod 총합: 2개" in answer
    assert "| Namespace | Pod 이름 | 현재 상태 | Ready |" in answer
    assert "| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-1` | Running / running | 1/1 |" in answer
    assert "| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-2` | Running / running | 1/1 |" in answer
    assert "예시 Pod" not in answer
    assert "aiops-test-pod-mr8vpb3y-1" in answer
    assert "aiops-demo-web" not in answer
    assert "모델 추론이 아니라 Gateway" in answer


def test_pod_namespace_pattern_lookup_accepts_compact_korean_query() -> None:
    req = ChatRequest(message="테스트파드가 있는 네임스페이스를 조회할 수있어?")
    gateway_evidence = """
Current Pod list evidence:
Namespace filter: `all-accessible-namespaces`
Rows shown: 3 / 3
| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |
| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-1` | `main` | Running / running | 2026-07-09T01:00:00Z | 1/1 | 0 | - | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-2` | `main` | Running / running | 2026-07-09T01:00:00Z | 1/1 | 0 | - | - |
| cyntra | `cyntra-1-build` | `docker-build` | Failed / terminated:Error/1 | 2026-07-09T01:00:00Z | 0/1 | 0 | - | - |
"""

    answer = gateway_main.build_pod_namespace_pattern_lookup_answer(req, gateway_evidence)
    candidates = gateway_main.pod_inventory_action_candidates_from_evidence(
        req,
        gateway_evidence,
        incident_id="incident-test",
        run_id="run-test",
    )

    assert answer is not None
    assert "- 매칭 Pod 총합: 2개" in answer
    assert "| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-1` | Running / running | 1/1 |" in answer
    assert "| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-2` | Running / running | 1/1 |" in answer
    assert "예시 Pod" not in answer
    assert "cyntra-1-build" not in answer
    assert candidates == []


def test_pod_namespace_pattern_lookup_uses_gateway_answer_even_for_generic_tool_plan() -> None:
    req = ChatRequest(message="테스트파드가있는 네임스페이스가있었나?")
    gateway_evidence = """
Current Pod list evidence:
Namespace filter: `all-accessible-namespaces`
Rows shown: 10 / 10
| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |
| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-1` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-2` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-3` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vv98e-1` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vv98e-2` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vv98e-3` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr9w4ffx-1` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr9w4ffx-2` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr9w4ffx-3` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| default | `normal-app` | `main` | Running / running | 2026-07-09T01:00:00Z | 1/1 | 0 | - | - |
"""

    answer = build_grounded_aiops_answer(
        req,
        {"task_type": "openshift_operational_question"},
        gateway_evidence,
    )
    candidates = gateway_main.pod_inventory_action_candidates_from_evidence(
        req,
        gateway_evidence,
        incident_id="incident-test",
        run_id="run-test",
    )

    assert answer is not None
    assert "## 테스트 Pod 네임스페이스" in answer
    assert "Pod 이름에 `test`가 포함된 Pod는 1개 namespace에서 9개 확인했습니다." in answer
    assert "- 매칭 Pod 총합: 9개" in answer
    assert "| gpu-test-kugnus | `aiops-test-pod-mr9w4ffx-3` | Completed / terminated:Completed/0 | 0/1 |" in answer
    assert "우선순위 표" not in answer
    assert "normal-app" not in answer
    assert candidates == []


def test_pod_namespace_pattern_lookup_handles_past_tense_question_as_table() -> None:
    req = ChatRequest(message="테스트파드가 있는 네임스페이스가 있었나?")
    gateway_evidence = """
Current Pod list evidence:
Namespace filter: `all-accessible-namespaces`
Rows shown: 4 / 4
| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |
| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-1` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-2` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-3` | `main` | Completed / terminated:Completed/0 | 2026-07-09T01:00:00Z | 0/1 | 0 | Completed/0 | - |
| default | `normal-app` | `main` | Running / running | 2026-07-09T01:00:00Z | 1/1 | 0 | - | - |
"""

    answer = gateway_main.build_pod_namespace_pattern_lookup_answer(req, gateway_evidence)

    assert gateway_main.is_pod_namespace_pattern_lookup_request(req.message) is True
    assert answer is not None
    assert "- 매칭 Pod 총합: 3개" in answer
    assert "| Namespace | Pod 이름 | 현재 상태 | Ready |" in answer
    assert "| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-1` | Completed / terminated:Completed/0 | 0/1 |" in answer
    assert "| gpu-test-kugnus | `aiops-test-pod-mr8vpb3y-3` | Completed / terminated:Completed/0 | 0/1 |" in answer
    assert "normal-app" not in answer


def test_runtime_tool_plan_treats_pod_namespace_lookup_as_inventory() -> None:
    plan = build_runtime_tool_plan('이름에 "test"가 포함된 파드가 있는 네임스페이스 알려줄래?')

    assert plan["task_type"] == "pod_inventory"
    assert any(step["tool"] == "openshift_pod_list" for step in plan["tool_plan"])


def test_action_proposal_fallback_is_non_empty_and_requests_target() -> None:
    policy = classify_request_policy("Pod 하나 재시작해줘")
    fallback = build_action_proposal_fallback(ChatRequest(message="Pod 하나 재시작해줘"), policy)

    assert "승인 필요한 조치 계획 검토" in fallback
    assert "승인 전 실행 차단" in fallback
    assert "운영자 승인 후 실행 기록을 남기는 경로" in fallback
    assert "Phase 5 Action Execution" not in fallback
    assert "Approval API와 Action Executor" not in fallback
    assert "ActionProposal/SealedActionPlan" not in fallback
    assert "namespace" in fallback
    assert "Pod 또는 관리 객체" in fallback


def test_empty_answer_fallback_includes_question_and_tool_summary() -> None:
    policy = classify_request_policy("ClusterOperator authentication 상태를 확인해줘")
    fallback = build_empty_answer_fallback(
        ChatRequest(message="ClusterOperator authentication 상태를 확인해줘"),
        policy,
        [
            {
                "name": "resources_list",
                "status": "success",
                "summary": "ClusterOperator authentication 조회 완료",
            }
        ],
    )

    assert "## RCA 보고서" in fallback
    assert "### 현재 판단" in fallback
    assert "### 확인 결과" in fallback
    assert "### 원인 후보" in fallback
    assert "### 조치 방법" in fallback
    assert "### 추가 확인" in fallback
    assert "authentication" in fallback
    assert "resources_list" in fallback
    assert "조회 완료" in fallback


def test_empty_answer_fallback_includes_gateway_evidence_when_ols_fails() -> None:
    policy = classify_request_policy("Failed Pod를 현재 장애로 봐도 되는지 판단해줘")
    fallback = build_empty_answer_fallback(
        ChatRequest(message="Failed Pod를 현재 장애로 봐도 되는지 판단해줘"),
        policy,
        [
            {
                "name": "lightspeed_stream",
                "status": "error",
                "summary": "OpenShift Lightspeed stream failed",
            }
        ],
        (
            "Pod phase/startTime indicate the current Pod object state.\n"
            "ClusterOperator status evidence from Kubernetes API."
        ),
    )

    assert "lightspeed_stream" not in fallback
    assert "OpenShift Lightspeed stream failed" not in fallback
    assert "startTime" in fallback
    assert "ClusterOperator" in fallback
    assert "## RCA 보고서" in fallback
    assert "### 원인 후보" in fallback


def test_image_empty_answer_fallback_hides_internal_diagnostics_and_unverified_forwarding() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="alerts.png",
        size=8,
    )
    policy = classify_request_policy("이거 무슨 상황이야")

    fallback = build_empty_answer_fallback(
        ChatRequest(message="이거 무슨 상황이야", attachments=[attachment]),
        policy,
        [
            {
                "name": "lightspeed_stream",
                "status": "error",
                "summary": "OpenShift Lightspeed request failed; Gateway fallback will answer from collected evidence",
            }
        ],
        (
            "RAG evidence unavailable: pgvector search failed: expected 768 dimensions, not 1024\n"
            "Gateway-collected Pod status evidence from Kubernetes API."
        ),
        image_forwarded_to_ols=True,
    )

    assert "첨부 화면 분석 답변을 완성하지 못했습니다" in fallback
    assert "이미지 수신: 1건" in fallback
    assert "Lightspeed attachments로 전달 시도" not in fallback
    assert "전달했습니다" not in fallback
    assert "Gateway-collected Pod status evidence" in fallback
    assert "pgvector" not in fallback
    assert "expected 768 dimensions" not in fallback
    assert "lightspeed_stream" not in fallback
    assert "Gateway fallback" not in fallback


def test_image_empty_answer_fallback_uses_gateway_vision_analysis_when_available() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="alerts.png",
        size=8,
    )
    policy = classify_request_policy("이거 무슨 상황이야")

    fallback = build_empty_answer_fallback(
        ChatRequest(message="이거 무슨 상황이야", attachments=[attachment]),
        policy,
        [],
        "",
        image_analysis="화면에는 BackOff 반복 감지 알림과 Pod 상태 이상 알림이 보입니다.",
        image_forwarded_to_ols=True,
    )

    assert "첨부 화면에서 확인한 내용을 기준으로 정리합니다" in fallback
    assert "BackOff 반복 감지" in fallback
    assert "첨부 화면 분석 답변을 완성하지 못했습니다" not in fallback
    assert "## 다음 확인" in fallback
    assert "Gateway 조회 결과 기준" not in fallback
    assert "모델의 최종 요약" not in fallback
    assert "Live 조회" not in fallback


def test_empty_answer_fallback_keeps_crashloop_rca_when_policy_is_action_proposal_only() -> None:
    message = (
        "다음 OpenShift 이상 징후를 RCA 분석하고, 승인 필요한 조치 후보까지 정리해줘.\n"
        "대상: komsco-ai-dev/Pod/aiops-scenario-1-crashloop-7448bf8897-2pnvz\n"
        "다음 확인: oc logs aiops-scenario-1-crashloop-7448bf8897-2pnvz -n komsco-ai-dev -c crashloop --previous\n"
        "연결된 조치 후보: CrashLoopBackOff 조치 후보 / 승인 후 실행 계획 생성 가능\n"
        "주의: 로그 원문은 민감정보 가능성이 있으니 원문 노출 없이 필요 여부와 확인 방법만 정리해줘. "
        "실제 변경은 계획, 승인, 검증 조건을 거쳐야 한다."
    )
    page_context = {
        "aiopsDemoCycle": {
            "scenarioId": "crashloop",
            "target": {
                "kind": "Pod",
                "namespace": "komsco-ai-dev",
                "name": "aiops-scenario-1-crashloop-7448bf8897-2pnvz",
            },
        }
    }
    req = ChatRequest(
        message=message,
        pageContext=page_context,
    )
    policy = classify_request_policy(message)
    fallback = build_empty_answer_fallback(
        req,
        policy,
        [
            {
                "name": "lightspeed_stream",
                "status": "error",
                "summary": "OpenShift Lightspeed stream failed",
            }
        ],
        "Pod waiting.reason=CrashLoopBackOff, restartCount=34",
    )

    assert policy["decision"] == "action_proposal_only"
    assert "현재 요청은 변경/재시작/삭제/스케일/패치 계열 작업으로 분류되었습니다." not in fallback
    assert "CrashLoopBackOff" in fallback
    assert fallback.startswith("CrashLoopBackOff는 컨테이너가 시작된 뒤 곧바로 종료되고")
    assert "## RCA 보고서" in fallback


def test_fallback_answer_planner_separates_health_from_rca_contract() -> None:
    health_policy = classify_request_policy("작동하는가")
    rca_policy = classify_request_policy("Failed Pod를 현재 장애로 봐도 되는지 판단해줘")

    assert classify_fallback_answer_kind("작동하는가", health_policy) == ANSWER_KIND_RUNTIME_HEALTH
    assert (
        classify_fallback_answer_kind("Failed Pod를 현재 장애로 봐도 되는지 판단해줘", rca_policy)
        == ANSWER_KIND_RCA
    )


def test_gateway_evidence_snapshot_models_component_statuses() -> None:
    snapshot = build_gateway_evidence_snapshot(
        [
            {
                "name": "lightspeed_stream",
                "status": "error",
                "summary": "OpenShift Lightspeed stream failed",
            }
        ],
        "Gateway-collected RAG evidence from `/v1/rag/search`.",
    )

    components = {component.id: component for component in snapshot.components}
    assert components["gateway_fallback"].status == "ok"
    assert components["lightspeed_stream"].status == "failed"
    assert components["rag_search"].status == "ok"


def test_generic_runtime_health_fallback_does_not_force_rca_template() -> None:
    policy = classify_request_policy("작동하는가")
    fallback = build_empty_answer_fallback(
        ChatRequest(message="작동하는가"),
        policy,
        [
            {
                "name": "lightspeed_stream",
                "status": "error",
                "summary": "OpenShift Lightspeed stream failed; Gateway fallback will answer from collected evidence",
            }
        ],
        "Gateway-collected RAG evidence from `/v1/rag/search`.",
    )

    assert "## RCA 보고서" not in fallback
    assert "### 상태 확인" in fallback
    assert "부분적으로 작동합니다" in fallback
    assert "Gateway fallback" in fallback
    assert "Lightspeed stream: 실패" in fallback
    assert "RAG 검색 결과가 있다는 사실만으로 전체 서비스가 정상이라고 단정하지 않습니다" in fallback


def test_ols_required_failure_answer_does_not_render_gateway_rca_fallback() -> None:
    answer = build_ols_required_failure_answer(
        ChatRequest(message="이거 무슨 상황이야", attachments=[]),
        [
            {
                "name": "lightspeed_stream",
                "status": "error",
                "summary": "OpenShift Lightspeed request failed; final answer was not generated",
            }
        ],
    )

    assert "최종 답변을 받지 못해 RCA 답변을 생성하지 않았습니다" in answer
    assert "## RCA 보고서" not in answer
    assert "### 원인 후보" not in answer
    assert "oc get" not in answer
    assert "Gateway fallback" not in answer


def test_chat_stream_routes_gateway_grounded_answer_to_lightspeed_by_default(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    def fake_grounded_answer(*_args, **_kwargs) -> str:
        return "DIRECT GATEWAY ANSWER"

    async def answer_call_ols_stream(*_args, **kwargs):
        gateway_context = kwargs.get("gateway_context")
        context_digest = ""
        if isinstance(gateway_context, Mapping) and isinstance(gateway_context.get("metadata"), Mapping):
            context_digest = str(gateway_context["metadata"].get("digest") or "")
        gateway_main.update_ols_stream_status("succeeded", context_digest=context_digest)
        yield {"type": "text", "content": "Lightspeed에서 생성한 최종 답변입니다.\n", "source": "ols"}
        yield {"type": "end", "conversationId": "conversation-final"}

    monkeypatch.setattr(gateway_main, "GATEWAY_DIRECT_ANSWER_ENABLED", False)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "build_grounded_aiops_answer", fake_grounded_answer)
    monkeypatch.setattr(gateway_main, "call_ols_stream", answer_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "현재 클러스터에서 에러 상태인 pod 목록을 확인하고 원인 분석해줘"},
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        answer_text = "".join(
            str(event.get("content") or "")
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        )
        lightspeed_run_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "run_status"
            and event.get("stage") == "lightspeed"
        ]
        gateway_direct_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "text"
            and event.get("source") == "gateway_evidence_renderer"
        ]

        assert lightspeed_run_events
        assert "Lightspeed에서 생성한 최종 답변입니다" in answer_text
        assert "DIRECT GATEWAY ANSWER" not in answer_text
        assert gateway_direct_events == []

    asyncio.run(run())


def test_chat_stream_marks_lightspeed_context_digest_on_ols_required_notice(monkeypatch) -> None:
    gateway_main.OLS_STREAM_STATUS = {
        "streamProbe": "not_started",
        "lastStatus": "not_started",
        "lastContextDigest": "",
        "lastStartedAt": "",
        "lastCompletedAt": "",
        "lastError": "",
        "fallbackActive": False,
    }

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    captured_context: dict[str, object] = {}

    async def fail_call_ols_stream(
        _user_auth_header: str,
        _query: str,
        _conversation_id: str | None,
        _attachments: list[ImageAttachment],
        gateway_context: Mapping[str, object] | None = None,
    ):
        assert gateway_context is not None
        assert gateway_context["kind"] == "GatewayContext"
        metadata = gateway_context["metadata"]
        assert isinstance(metadata, Mapping)
        context_digest = str(metadata.get("digest") or "")
        assert context_digest.startswith("sha256:")
        captured_context["digest"] = context_digest
        if False:
            yield {}
        raise RuntimeError("synthetic OLS outage")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "최근 OpenShift 경고와 우선 확인할 항목을 정리해줘."},
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        events = parse_sse_events(response.text)
        context_digest = str(captured_context["digest"])
        lightspeed_run_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "run_status"
            and event.get("stage") == "lightspeed"
        ]
        ols_error_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "lightspeed_stream"
        ]
        ols_notice_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "text"
            and event.get("source") == "ols_required_notice"
        ]

        assert lightspeed_run_events[-1]["gatewayContextDigest"] == context_digest
        assert ols_error_events[-1]["gatewayContextDigest"] == context_digest
        assert ols_error_events[-1]["finalAnswerUnavailable"] is True
        assert ols_notice_events[-1]["gatewayContextDigest"] == context_digest
        assert ols_notice_events[-1]["finalAnswerUnavailable"] is True
        assert "최종 답변을 받지 못해 RCA 답변을 생성하지 않았습니다" in ols_notice_events[-1]["content"]
        assert "## RCA 보고서" not in ols_notice_events[-1]["content"]
        assert "Gateway fallback" not in ols_notice_events[-1]["content"]
        assert gateway_main.OLS_STREAM_STATUS["streamProbe"] == "failed"
        assert gateway_main.OLS_STREAM_STATUS["fallbackActive"] is False
        assert gateway_main.OLS_STREAM_STATUS["lastContextDigest"] == context_digest

        lightspeed_status = status_response.json()["spec"]["safetyContract"]["lightspeedStatus"]
        assert lightspeed_status["streamProbe"] == "failed"
        assert lightspeed_status["fallbackActive"] is False
        assert lightspeed_status["lastContextDigest"] == context_digest

    asyncio.run(run())


def test_chat_stream_redacts_secret_bearing_ols_errors(monkeypatch) -> None:
    gateway_main.OLS_STREAM_STATUS = {
        "streamProbe": "not_started",
        "lastStatus": "not_started",
        "lastContextDigest": "",
        "lastStartedAt": "",
        "lastCompletedAt": "",
        "lastError": "",
        "fallbackActive": False,
    }

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        if False:
            yield {}
        raise HTTPException(
            status_code=502,
            detail="OLS upstream failed Authorization: Bearer abcdefghijklmnopqrstuvwxyz token=supersecret",
        )

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "최근 OpenShift 경고와 우선 확인할 항목을 정리해줘."},
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        assert "supersecret" not in response.text
        assert "abcdefghijklmnopqrstuvwxyz" not in response.text
        assert "Bearer abc" not in response.text
        assert "supersecret" not in json.dumps(status_response.json(), ensure_ascii=False)
        assert "[REDACTED]" in response.text
        lightspeed_status = status_response.json()["spec"]["safetyContract"]["lightspeedStatus"]
        assert lightspeed_status["fallbackActive"] is False
        assert "supersecret" not in lightspeed_status["lastError"]

    asyncio.run(run())


def test_chat_stream_marks_empty_ols_success_as_fallback_status(monkeypatch) -> None:
    gateway_main.OLS_STREAM_STATUS = {
        "streamProbe": "not_started",
        "lastStatus": "not_started",
        "lastContextDigest": "",
        "lastStartedAt": "",
        "lastCompletedAt": "",
        "lastError": "",
        "fallbackActive": False,
    }

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def empty_call_ols_stream(*_args, **_kwargs):
        yield {"type": "end", "conversationId": "conversation-empty"}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", empty_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "최근 OpenShift 경고와 우선 확인할 항목을 정리해줘."},
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        events = parse_sse_events(response.text)
        ols_notice_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "text"
            and event.get("source") == "ols_required_notice"
        ]
        assert ols_notice_events
        assert "최종 답변을 받지 못해 RCA 답변을 생성하지 않았습니다" in ols_notice_events[-1]["content"]
        assert "## RCA 보고서" not in ols_notice_events[-1]["content"]
        lightspeed_status = status_response.json()["spec"]["safetyContract"]["lightspeedStatus"]
        assert lightspeed_status["streamProbe"] == "failed"
        assert lightspeed_status["fallbackActive"] is False
        assert lightspeed_status["lastContextDigest"] == ols_notice_events[-1]["gatewayContextDigest"]

    asyncio.run(run())


def test_chat_stream_retries_empty_ols_answer_before_fallback(monkeypatch) -> None:
    gateway_main.OLS_STREAM_STATUS = {
        "streamProbe": "not_started",
        "lastStatus": "not_started",
        "lastContextDigest": "",
        "lastStartedAt": "",
        "lastCompletedAt": "",
        "lastError": "",
        "fallbackActive": False,
    }
    monkeypatch.setattr(gateway_main, "OLS_EMPTY_ANSWER_RETRIES", 1)

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    queries: list[str] = []

    async def empty_then_answer_call_ols_stream(
        _user_auth_header: str,
        query: str,
        _conversation_id: str | None,
        _attachments: list[ImageAttachment],
        gateway_context: Mapping[str, object] | None = None,
    ):
        assert gateway_context is not None
        metadata = gateway_context["metadata"]
        assert isinstance(metadata, Mapping)
        context_digest = str(metadata.get("digest") or "")
        gateway_main.update_ols_stream_status("started", context_digest=context_digest)
        queries.append(query)
        if len(queries) == 1:
            gateway_main.update_ols_stream_status("succeeded", context_digest=context_digest)
            yield {"type": "end", "conversationId": "conversation-empty"}
            return

        gateway_main.update_ols_stream_status("succeeded", context_digest=context_digest)
        yield {
            "type": "text",
            "content": "## RCA 보고서\n\n### 현재 판단\n재시도 후 Lightspeed 답변입니다.\n\n### 확인 결과\nGateway evidence.",
        }
        yield {"type": "end", "conversationId": "conversation-answer"}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", empty_then_answer_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={"message": "최근 OpenShift 경고와 우선 확인할 항목을 정리해줘."},
            )
            status_response = await client.get(
                "/v1/aiops/status",
                headers={"Authorization": "Bearer test-token"},
            )

        assert response.status_code == 200
        assert status_response.status_code == 200
        events = parse_sse_events(response.text)
        retry_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "run_status"
            and event.get("stage") == "lightspeed_retry"
        ]
        fallback_text_events = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "text"
            and event.get("fallbackAnswer") is True
        ]
        answer_text = "".join(
            str(event.get("content") or "")
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        )

        assert len(queries) == 2
        assert "[Gateway 빈 응답 재시도 지시]" not in queries[0]
        assert "[Gateway 빈 응답 재시도 지시]" not in queries[1]
        assert "Previous OpenShift Lightspeed response ended" in queries[1]
        assert "최근 OpenShift 경고" in queries[1]
        assert retry_events
        assert not fallback_text_events
        assert "재시도 후 Lightspeed 답변" in answer_text
        lightspeed_status = status_response.json()["spec"]["safetyContract"]["lightspeedStatus"]
        assert lightspeed_status["streamProbe"] == "succeeded"
        assert lightspeed_status["fallbackActive"] is False

    asyncio.run(run())


def test_chat_stream_handles_openshift_user_auth_401_without_raw_status(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        raise HTTPException(
            status_code=401,
            detail=gateway_main.build_openshift_user_auth_failure_detail(
                401,
                '{"kind":"Status","apiVersion":"v1","status":"Failure","message":"Unauthorized","reason":"Unauthorized","code":401}',
            ),
        )

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)

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

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer expired-token"},
                json={"message": "aiops-scenario-1-crashloop 이거 왜 재시작해?"},
            )

        assert response.status_code == 200
        body = response.text
        events = parse_sse_events(body)
        text_events = [event for event in events if isinstance(event, dict) and event.get("type") == "text"]
        subject_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "subject_review"
        ]

        assert subject_results[-1]["status"] == "error"
        assert "사용자 인증이 만료" in text_events[-1]["content"]
        assert "새로고침" in text_events[-1]["content"]
        assert "OpenShift subject review failed" not in body
        assert '"kind":"Status"' not in body
        assert events[-1] == "[DONE]"

    asyncio.run(run())


def test_empty_answer_fallback_summarizes_pod_evidence_without_truncating_raw_table() -> None:
    policy = classify_request_policy(
        "team-a 네임스페이스의 sample-crashy 파드가 왜 장애인지 분석하고 조치 계획을 제안해줘"
    )
    gateway_evidence = "\n".join(
        [
            "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`.",
            "x" * 2500,
            "Currently non-healthy or waiting container evidence:",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | Running (CrashLoopBackOff) / waiting:CrashLoopBackOff | 2026-06-22T00:54:32Z | 0/1 | 9 | Error/1 | ReplicaSet/sample-crashy-6fd7d7cfd7 |",
            "Spec evidence for currently non-healthy or waiting containers:",
            "Use command/args/image/labels below as concrete evidence for root-cause and remediation planning.",
            "| Namespace | Pod | Container | Image | Command | Args | Pod Labels | Owner Chain |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | registry.example.com/team-a/sample-crashy:v2 | [\"python\", \"-c\", \"raise SystemExit('boom')\"] | - | app=sample-crashy, aiops.komsco/scenario=sample, pod-template-hash=6fd7d7cfd7 | ReplicaSet/sample-crashy-6fd7d7cfd7 -> Deployment/sample-crashy |",
        ]
    )

    fallback = build_empty_answer_fallback(
        ChatRequest(message="team-a 네임스페이스의 sample-crashy 파드가 왜 장애인지 분석하고 조치 계획을 제안해줘"),
        policy,
        [],
        gateway_evidence,
    )

    assert "Gateway가 수집한 Kubernetes 확인 결과 기준" in fallback
    assert fallback.startswith("CrashLoopBackOff는 컨테이너가 시작된 뒤 곧바로 종료되고")
    assert "모델의 최종 요약" not in fallback
    assert "Live 조회" not in fallback
    assert "... truncated ..." not in fallback
    assert "Gateway 사전 수집 증거" not in fallback
    assert "sample-crashy-6fd7d7cfd7-r4nd0" in fallback
    assert "raise SystemExit('boom')" in fallback
    assert "즉시 종료" in fallback
    assert "`deployment/sample-crashy`" in fallback
    assert "oc rollout status deployment/sample-crashy -n team-a" in fallback
    assert "oc get pod -n team-a -l app=sample-crashy" in fallback
    assert "<app-label>" not in fallback


def test_grounded_pod_screen_rca_uses_evidence_renderer_instead_of_generic_answer() -> None:
    gateway_evidence = "\n".join(
        [
            "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`.",
            "Currently non-healthy or waiting container evidence:",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | Running (CrashLoopBackOff) / waiting:CrashLoopBackOff | 2026-06-22T00:54:32Z | 0/1 | 158 | Error/1 | ReplicaSet/sample-crashy-6fd7d7cfd7 |",
            "Spec evidence for currently non-healthy or waiting containers:",
            "Use command/args/image/labels below as concrete evidence for root-cause and remediation planning.",
            "| Namespace | Pod | Container | Image | Command | Args | Pod Labels | Owner Chain |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
            "| team-a | `sample-crashy-6fd7d7cfd7-r4nd0` | `app` | registry.example.com/team-a/sample-crashy:v2 | [\"python\", \"-c\", \"raise SystemExit('boom')\"] | - | app=sample-crashy, aiops.komsco/scenario=sample, pod-template-hash=6fd7d7cfd7 | ReplicaSet/sample-crashy-6fd7d7cfd7 -> Deployment/sample-crashy |",
        ]
    )

    answer = build_grounded_aiops_answer(
        ChatRequest(
            message="현재 화면의 대상 리소스에 대해 가능한 안전 조회를 실행하고, 확인 결과와 원인 후보, 승인 가능한 조치 후보를 정리해줘.",
            pageContext={"resourceKind": "Pod", "namespace": "team-a", "resourceName": "sample-crashy-6fd7d7cfd7-r4nd0"},
        ),
        {"task_type": "pod_screen_rca"},
        gateway_evidence,
    )

    assert answer is not None
    assert answer.startswith("CrashLoopBackOff는 컨테이너가 시작된 뒤 곧바로 종료되고")
    assert "Gateway가 수집한 Kubernetes 확인 결과 기준" in answer
    assert "sample-crashy-6fd7d7cfd7-r4nd0" in answer
    assert "raise SystemExit('boom')" in answer
    assert "즉시 종료" in answer
    assert "조치 후보, 조치 계획, 승인, 실행 기록을 만들지 않았습니다" in answer
    assert "실행 기록이 필요하면 실행 가능 모드에서 `조치 계획 생성`을 명시" in answer
    assert "ActionProposal/SealedActionPlan/Approval/ExecutionRecord" not in answer
    assert "조치 레코드" not in answer
    assert "DB, API" not in answer


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


def test_chat_stream_unrestricted_followup_without_plan_stays_in_gateway(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

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
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        followup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_followup"
        ]
        assert followup_results
        assert followup_results[0]["status"] == "skipped"
        assert "실행할 Gateway AIOps Action Plan이 없습니다" in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


def test_chat_stream_unrestricted_followup_uses_recent_user_action_context(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        assert req.message == "team-a 네임스페이스의 web-api 파드 4개로 올려줘"
        return {
            "intent": {
                "toolName": "set_replicas_within_bounds",
                "targetName": "web-api",
                "namespace": "team-a",
                "parameters": {"replicas": 4},
            },
            "parameters": {"replicas": 4},
            "planDigest": "sha256:test-plan",
            "planId": "plan-contextual",
            "proposalId": "proposal-contextual",
            "risk": "medium",
            "status": "planned",
            "target": {
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "namespace": "team-a",
                "name": "web-api",
                "uid": "uid-web-api",
            },
        }

    async def fake_execute_natural_action_plan_result(plan_result, *_args, **_kwargs):
        return {
            "approvalId": "approval-contextual",
            "executionId": "execution-contextual",
            "mutationOutcome": {"status": "mutation_succeeded", "reason": "typed_action_executed"},
            "plan": dict(plan_result),
            "remediationOutcome": {
                "status": "verified",
                "reason": "scale_spec_matches",
                "observedReplicas": 4,
            },
            "status": "executed",
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for contextual followup execution")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fake_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                    "recentMessages": [
                        {
                            "role": "user",
                            "content": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                        },
                        {
                            "role": "assistant",
                            "content": "조치 계획을 생성했습니다. 승인하시겠습니까?",
                        },
                    ],
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        followup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_followup"
        ]
        assert followup_results
        assert followup_results[0]["status"] == "success"
        assert "team-a/web-api" in response.text
        assert "scale_spec_matches" in response.text
        assert "lightspeed_stream" not in response.text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_stream_unrestricted_followup_executes_pending_action_with_post_answer_rca(
    monkeypatch,
) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    def fake_latest_pending_action_plan_result(_subject: Mapping[str, object]) -> dict:
        return {
            "intent": {
                "kind": "Deployment",
                "namespace": "team-a",
                "parameters": {"replicas": 4},
                "targetName": "web-api",
                "toolName": "set_replicas_within_bounds",
            },
            "planId": "plan-pending",
            "status": "planned",
            "target": {"kind": "Deployment", "namespace": "team-a", "name": "web-api"},
        }

    async def fake_execute_natural_action_plan_result(plan_result, *_args, **_kwargs):
        return {
            "approvalId": "approval-pending",
            "executionId": "execution-pending",
            "mutationOutcome": {"status": "mutation_succeeded", "reason": "typed_action_executed"},
            "plan": dict(plan_result),
            "remediationOutcome": {"status": "verified", "reason": "pending_plan_verified"},
            "status": "executed",
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for pending followup execution")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(
        gateway_main,
        "latest_pending_action_plan_result",
        fake_latest_pending_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fake_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        followup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_followup"
        ]
        assert followup_results
        assert followup_results[0]["status"] == "success"
        assert "pending_plan_verified" in response.text
        assert "lightspeed_stream" not in response.text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_stream_execute_mode_action_plan_response_has_post_answer_rca(
    monkeypatch,
) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        assert req.message == "team-a 네임스페이스의 web-api 파드 4개로 올려줘"
        return {
            "intent": {
                "kind": "Deployment",
                "namespace": "team-a",
                "parameters": {"replicas": 4},
                "targetName": "web-api",
                "toolName": "set_replicas_within_bounds",
            },
            "planDigest": "sha256:execute-mode-plan",
            "planId": "plan-execute-mode",
            "status": "planned",
            "target": {"kind": "Deployment", "namespace": "team-a", "name": "web-api"},
        }

    async def fail_execute_natural_action_plan_result(*_args, **_kwargs):
        raise AssertionError("execute mode should stop at plan response unless unrestricted")

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action plan responses")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fail_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        tool_plan_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict) and event.get("type") == "tool_plan"
        )
        plan_result_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        )
        plan_results = [events[plan_result_index]]
        answer_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "text"
            and "자연어 조치 요청을 승인 가능한 Action Plan으로 정리했습니다." in event.get("content", "")
        )
        post_answer_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "rca_context"
            and event.get("context", {}).get("metadata", {}).get("phase") == "post_answer"
        )
        run_completed_index = next(
            index
            for index, event in enumerate(events)
            if isinstance(event, dict)
            and event.get("type") == "run_status"
            and event.get("stage") == "completed"
            and "조치 계획 생성 완료" in event.get("message", "")
        )
        assert [
            tool_plan_index,
            plan_result_index,
            answer_index,
            run_completed_index,
            post_answer_index,
            len(events) - 1,
        ] == sorted(
            [
                tool_plan_index,
                plan_result_index,
                answer_index,
                run_completed_index,
                post_answer_index,
                len(events) - 1,
            ]
        )
        assert events[-1] == "[DONE]"
        assert plan_results[0]["result"]["planDigest"] == "sha256:execute-mode-plan"
        assert plan_results
        assert plan_results[0]["status"] == "success"
        answer_text = events[answer_index]["content"]
        assert "자연어 조치 요청을 승인 가능한 Action Plan으로 정리했습니다." in answer_text
        assert "plan-execute-mode" not in answer_text
        assert "sha256:execute-mode-plan" not in answer_text
        assert "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord" not in answer_text
        assert "natural_action_execute" not in answer_text
        assert "lightspeed_stream" not in answer_text
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_action_plan_can_continue_through_standard_approval_api(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    requester = safe_subject({"username": "requester@example.com", "uid": "uid-requester", "groups": ["ops"]})
    approver = safe_subject({"username": "approver@example.com", "uid": "uid-approver", "groups": ["ops"]})

    async def fake_subject_review(user_auth_header: str) -> dict:
        return requester if user_auth_header == "Bearer requester-token" else approver

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_action_access_review(_user_auth_header: str, plan: dict) -> dict:
        target = plan["target"]
        return {
            "allowed": True,
            "enabled": True,
            "resourceAttributes": {
                "group": "apps",
                "name": target["name"],
                "namespace": target["namespace"],
                "resource": "deployments",
                "subresource": "scale",
                "verb": "update",
            },
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, *_, **__) -> dict:
        assert "/apis/apps/v1/namespaces/team-a/deployments/web-api" in path
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "web-api",
                "namespace": "team-a",
                "uid": "deployment-uid-a",
            },
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action plan responses")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", False)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_action_access_review", fake_action_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            chat_response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer requester-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )
            events = parse_sse_events(chat_response.text)
            plan_result = next(
                event["result"]
                for event in events
                if isinstance(event, dict)
                and event.get("type") == "tool_result"
                and event.get("name") == "natural_action_plan"
            )
            approval_response = await client.post(
                "/v1/actions/approvals",
                headers={"Authorization": "Bearer approver-token"},
                json={
                    "planId": plan_result["planId"],
                    "expectedPlanDigest": plan_result["planDigest"],
                },
            )
            approval_id = approval_response.json()["metadata"]["name"]
            execution_response = await client.post(
                "/v1/actions/execute",
                headers={"Authorization": "Bearer approver-token"},
                json={
                    "approvalId": approval_id,
                    "planId": plan_result["planId"],
                    "expectedPlanDigest": plan_result["planDigest"],
                },
            )

        assert chat_response.status_code == 200
        assert approval_response.status_code == 200
        assert execution_response.status_code == 403
        assert execution_response.json()["detail"]["mutationOutcome"]["status"] == "mutation_disabled"
        assert len(ACTION_PROPOSALS) == 1
        assert len(SEALED_ACTION_PLANS) == 1
        assert len(APPROVAL_DECISIONS) == 1
        assert len(EXECUTION_RECORDS) == 1
        execution_record = next(iter(EXECUTION_RECORDS.values()))
        assert execution_record["spec"]["planId"] == plan_result["planId"]
        assert execution_record["spec"]["planDigest"] == plan_result["planDigest"]
        visible_text = "\n".join(
            event.get("content", "")
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        )
        assert "Action Plan" in visible_text
        assert "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord" not in visible_text
        context = assert_post_answer_rca_before_done(events)
        assert context["metadata"]["phase"] == "post_answer"

    asyncio.run(run())


def test_chat_stream_action_candidate_pod_prompt_prefers_action_plan_over_pod_count(
    monkeypatch,
) -> None:
    prompt = (
        "Pod `komsco-ai-dev/aiops-scenario-1-crashloop-7448bf8897-57pjz` evict 실행 계획을 생성해줘.\n\n"
        "조치 후보: CrashLoopBackOff: komsco-ai-dev/aiops-scenario-1-crashloop-7448bf8897-57pjz 조치 후보\n"
        "대상: komsco-ai-dev/Pod/aiops-scenario-1-crashloop-7448bf8897-57pjz\n"
        "위험도: 높음\n"
        "근거: container=crashloop, waiting.reason=CrashLoopBackOff, restartCount=2321, "
        "message=back-off 5m0s restarting failed container=crashloop "
        "pod=aiops-scenario-1-crashloop-7448bf8897-57pjz_komsco-ai-dev(f0119e12-b8d1-4fc4-82df-a6516de8e800)\n"
        "선행 확인: oc describe pod aiops-scenario-1-crashloop-7448bf8897-57pjz -n komsco-ai-dev\n"
        "예상 영향: komsco-ai-dev/Pod/aiops-scenario-1-crashloop-7448bf8897-57pjz 회복 가능성이 있지만 "
        "잘못된 변경은 재시작 또는 서비스 영향으로 이어질 수 있습니다.\n\n"
        "실행은 바로 하지 말고, 먼저 Action Plan을 만들고 승인 버튼을 기다려."
    )

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        assert req.message == prompt
        return {
            "intent": {
                "kind": "Pod",
                "namespace": "komsco-ai-dev",
                "parameters": {"reason": "natural_language_unhealthy_pod_eviction"},
                "targetName": "aiops-scenario-1-crashloop-7448bf8897-57pjz",
                "toolName": "evict_one_unhealthy_controller_owned_pod",
            },
            "parameters": {"reason": "natural_language_unhealthy_pod_eviction"},
            "planId": "plan-action-candidate-pod",
            "proposalId": "proposal-action-candidate-pod",
            "risk": "medium",
            "status": "planned",
            "target": {
                "kind": "Pod",
                "namespace": "komsco-ai-dev",
                "name": "aiops-scenario-1-crashloop-7448bf8897-57pjz",
            },
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action candidate plan responses")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": prompt,
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        plan_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        ]
        assert plan_results
        assert "plan-action-candidate-pod" in response.text
        assert "pod_count_investigation" not in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


@pytest.mark.parametrize(
    ("scenario_id", "recent_messages", "expected_action_message"),
    [
        (
            "3-user-turn",
            [
                {
                    "role": "user",
                    "content": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                },
                {
                    "role": "assistant",
                    "content": "조치 계획을 생성했습니다. 승인하시겠습니까?",
                },
                {"role": "user", "content": "위험도도 같이 봐줘"},
                {"role": "assistant", "content": "중간 위험도이며 승인 후 실행 가능합니다."},
            ],
            "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
        ),
        (
            "4-user-turn",
            [
                {
                    "role": "user",
                    "content": "team-a 네임스페이스의 deployment/web-api revision 2로 롤백해줘",
                },
                {
                    "role": "assistant",
                    "content": "rollback_deployment_to_revision 계획을 만들 수 있습니다.",
                },
                {"role": "user", "content": "리비전 2 대상이 맞는지 다시 설명해줘"},
                {"role": "assistant", "content": "대상은 team-a/web-api revision 2입니다."},
                {"role": "user", "content": "서비스 영향은?"},
                {"role": "assistant", "content": "rollout 과정에서 일시적인 replacement가 발생할 수 있습니다."},
            ],
            "team-a 네임스페이스의 deployment/web-api revision 2로 롤백해줘",
        ),
        (
            "5-user-turn",
            [
                {
                    "role": "user",
                    "content": "team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘",
                },
                {
                    "role": "assistant",
                    "content": "set_hpa_bounds 계획을 만들 수 있습니다.",
                },
                {"role": "user", "content": "대상 HPA 이름 다시 말해줘"},
                {"role": "assistant", "content": "대상은 team-a/web-hpa입니다."},
                {"role": "user", "content": "최소 최대 값도 다시 확인해줘"},
                {"role": "assistant", "content": "minReplicas 2, maxReplicas 8입니다."},
                {"role": "user", "content": "운영 영향은?"},
                {"role": "assistant", "content": "autoscaling bounds 변경으로 scale range가 달라집니다."},
            ],
            "team-a 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘",
        ),
    ],
)
def test_chat_stream_unrestricted_followup_uses_3_4_5_turn_contexts(
    monkeypatch,
    scenario_id: str,
    recent_messages: list[dict[str, str]],
    expected_action_message: str,
) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()
    created_from_messages: list[str] = []

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_create_natural_action_plan(req, *_args, **_kwargs):
        created_from_messages.append(req.message)
        intent = parse_natural_action_intent(req)
        assert intent, scenario_id
        return {
            "intent": dict(intent),
            "parameters": dict(intent["parameters"]),
            "planDigest": f"sha256:{scenario_id}",
            "planId": f"plan-{scenario_id}",
            "proposalId": f"proposal-{scenario_id}",
            "risk": "medium",
            "status": "planned",
            "target": {
                "apiVersion": intent.get("apiVersion"),
                "kind": intent.get("kind"),
                "namespace": intent.get("namespace"),
                "name": intent.get("targetName"),
                "uid": f"uid-{scenario_id}",
            },
        }

    async def fake_execute_natural_action_plan_result(plan_result, *_args, **_kwargs):
        return {
            "approvalId": f"approval-{scenario_id}",
            "executionId": f"execution-{scenario_id}",
            "mutationOutcome": {"status": "mutation_succeeded", "reason": "typed_action_executed"},
            "plan": dict(plan_result),
            "remediationOutcome": {"status": "verified", "reason": "scenario_verified"},
            "status": "executed",
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError(f"OLS must not be called for {scenario_id} contextual followup execution")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", fake_create_natural_action_plan)
    monkeypatch.setattr(
        gateway_main,
        "execute_natural_action_plan_result",
        fake_execute_natural_action_plan_result,
    )
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                    "recentMessages": recent_messages,
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        followup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_followup"
        ]
        assert followup_results, scenario_id
        assert followup_results[0]["status"] == "success"
        assert "scenario_verified" in response.text
        assert "lightspeed_stream" not in response.text
        assert created_from_messages == [expected_action_message]
        context = assert_post_answer_rca_before_done(events)
        assert context["confidence"]["level"] == "insufficient_evidence"

    asyncio.run(run())


def test_chat_stream_pod_count_question_directly_investigates_cluster(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        if path == "/apis/apps/v1/deployments":
            return {
                "items": [
                    {
                        "metadata": {"name": "aiops-two-pod-exec", "namespace": "komsco-ai-dev"},
                        "spec": {
                            "replicas": 3,
                            "selector": {"matchLabels": {"app": "aiops-two-pod-exec"}},
                        },
                        "status": {
                            "availableReplicas": 3,
                            "readyReplicas": 3,
                            "updatedReplicas": 3,
                        },
                    }
                ]
            }
        if path == "/api/v1/pods":
            return {
                "items": [
                    {
                        "metadata": {
                            "labels": {"app": "aiops-two-pod-exec"},
                            "name": f"aiops-two-pod-exec-69c85d74cc-{suffix}",
                            "namespace": "komsco-ai-dev",
                        },
                        "status": {
                            "containerStatuses": [{"ready": True, "restartCount": 0}],
                            "phase": "Running",
                        },
                    }
                    for suffix in ["aaa", "bbb", "ccc"]
                ]
            }
        raise AssertionError(f"unexpected OpenShift path: {path}")

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for direct pod count questions")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "aiops-two-pod-exec 파드 몇개 띄었어?",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        event_names = [
            event.get("name")
            for event in events
            if isinstance(event, dict) and event.get("type") in {"tool_call", "tool_result"}
        ]
        pod_count_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "pod_count_investigation"
        ]
        for expected_name in [
            "pod_count_scope_resolve",
            "pod_count_deployment_lookup",
            "pod_count_pod_lookup",
            "pod_count_selector_match",
            "pod_count_investigation",
        ]:
            assert expected_name in event_names
        assert pod_count_results
        assert pod_count_results[0]["status"] == "success"
        assert pod_count_results[0]["result"]["rows"][0]["totalPods"] == 3
        evidence_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "evidence_ref"
            and event.get("result", {}).get("sourceType") == "gateway-direct-evidence"
        ]
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        assert evidence_results
        assert rca_events
        latest_context = rca_events[-1]["context"]
        assert latest_context["metadata"]["phase"] == "post_answer"
        assert latest_context["evidence"]["summary"]["collectedCount"] >= 1
        assert latest_context["evidence"]["collectedRefs"][0]["evidenceId"] == evidence_results[-1]["result"]["evidenceId"]
        assert (
            latest_context["evidence"]["collectedRefs"][0]["contentDigest"]
            == evidence_results[-1]["result"]["contentDigest"]
        )
        assert "`komsco-ai-dev/aiops-two-pod-exec` 기준 현재 Pod는 총 3개" in response.text
        assert "natural_action_unresolved" not in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


def test_chat_stream_top_pod_namespace_question_stays_brief_and_skips_ols(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    def pod_item(namespace: str, index: int) -> dict:
        return {
            "metadata": {"name": f"{namespace}-pod-{index}", "namespace": namespace},
            "status": {"phase": "Running"},
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, **_kwargs):
        if path == "/api/v1/pods":
            return {
                "items": [
                    *[pod_item("openshift-marketplace", index) for index in range(24)],
                    *[pod_item("cywell-aiops", index) for index in range(16)],
                    *[pod_item("cyntra", index) for index in range(15)],
                    *[pod_item("komsco-ai-dev", index) for index in range(14)],
                    *[pod_item("openshift-monitoring", index) for index in range(13)],
                    *[pod_item("nginx-gateway", index) for index in range(1)],
                ]
            }
        raise AssertionError(f"unexpected OpenShift path: {path}")

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for top pod namespace count questions")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "파드 수가 제일 많은 네임스페이스는 뭐야",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        lookup_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "top_pod_namespace_count_lookup"
        ]
        text = "".join(
            event.get("content", "")
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        )

        assert lookup_results
        assert lookup_results[0]["status"] == "success"
        assert "`openshift-marketplace`입니다." in text
        assert "| 1 | `openshift-marketplace` | 24 |" in text
        assert "| 5 | `openshift-monitoring` | 13 |" in text
        assert "nginx-gateway" not in text
        assert "Gathering data about your cluster" not in text
        assert not any(
            event.get("name") == "lightspeed_stream"
            for event in events
            if isinstance(event, dict)
        )

    asyncio.run(run())


def test_chat_stream_unparsed_mutation_request_does_not_fall_through_to_ols(monkeypatch) -> None:
    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for unresolved mutation requests")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "파드 하나 재시작해줘",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        unresolved_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_unresolved"
        ]
        assert unresolved_results
        assert unresolved_results[0]["status"] == "skipped"
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        assert rca_events
        assert rca_events[-1]["context"]["metadata"]["phase"] == "post_answer"
        assert rca_events[-1]["context"]["confidence"]["level"] == "insufficient_evidence"
        assert "대상 리소스 이름이 명확하지 않습니다" in response.text
        assert "lightspeed_stream" not in response.text

    asyncio.run(run())


def test_chat_stream_execute_action_request_emits_plan_and_post_answer_rca_context(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, *_, **__) -> dict:
        assert "/apis/apps/v1/namespaces/team-a/deployments/web-api" in path
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "metadata": {
                "name": "web-api",
                "namespace": "team-a",
                "uid": "deployment-uid-a",
            },
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for action plan responses")

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 3개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        action_plan_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        ]
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        text_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        ]
        assert action_plan_results
        assert action_plan_results[0]["status"] == "success"
        assert action_plan_results[0]["result"]["status"] == "planned"
        assert rca_events
        assert rca_events[-1]["context"]["metadata"]["phase"] == "post_answer"
        assert rca_events[-1]["context"]["safety"]["mode"] == "controlled_execution"
        assert rca_events[-1]["context"]["evidence"]["summary"]["collectedCount"] == 0
        assert any(
            event.get("answerContract") == "natural-action-plan-v0.2.1"
            for event in text_events
        )
        visible_text = "\n".join(event.get("content", "") for event in text_events)
        assert "자연어 조치 요청을 승인 가능한 Action Plan으로 정리했습니다." in visible_text
        assert "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord" not in visible_text
        assert "natural_action_execute" not in visible_text
        assert "lightspeed_stream" not in visible_text
        assert len(ACTION_PROPOSALS) == 1
        assert len(SEALED_ACTION_PLANS) == 1
        assert len(APPROVAL_DECISIONS) == 0
        assert len(EXECUTION_RECORDS) == 0

    asyncio.run(run())


def test_chat_stream_read_only_action_request_skips_plan_and_emits_post_answer_rca_context(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fail_call_ols_stream(*_args, **_kwargs):
        raise AssertionError("OLS must not be called for read-only action gate responses")

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "call_ols_stream", fail_call_ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 3개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "read-only"},
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        read_only_results = [
            event
            for event in events
            if isinstance(event, dict)
            and event.get("type") == "tool_result"
            and event.get("name") == "natural_action_plan"
        ]
        rca_events = [
            event
            for event in events
            if isinstance(event, dict) and event.get("type") == "rca_context"
        ]
        assert read_only_results
        assert read_only_results[0]["status"] == "skipped"
        assert read_only_results[0]["result"]["executionMode"] == "evidence-check"
        assert rca_events
        assert rca_events[-1]["context"]["metadata"]["phase"] == "post_answer"
        assert rca_events[-1]["context"]["safety"]["mode"] == "evidence_check"
        assert "읽기 전용" in response.text
        assert "조치 후보만 정리" in response.text
        assert "natural_action_execute" not in response.text
        assert "lightspeed_stream" not in response.text
        assert len(ACTION_PROPOSALS) == 0
        assert len(SEALED_ACTION_PLANS) == 0
        assert len(APPROVAL_DECISIONS) == 0
        assert len(EXECUTION_RECORDS) == 0

    asyncio.run(run())


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




def test_workflow_and_metrics_endpoints_expose_non_secret_runtime_state() -> None:
    WORKFLOW_RECORDS.clear()
    METRICS["aiops_chat_requests_total"] = 3
    subject = safe_subject(None)
    WORKFLOW_RECORDS["run-test"] = {
        "runId": "run-test",
        "status": "completed",
        "subject": subject,
        "target": {"messageLength": 10},
    }

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            workflow_response = await client.get(
                "/v1/workflows/run-test",
                headers={"Authorization": "Bearer test-token"},
            )
            metrics_response = await client.get("/metrics")

        assert workflow_response.status_code == 200
        assert workflow_response.json()["spec"]["status"] == "completed"
        assert metrics_response.status_code == 200
        assert "aiops_chat_requests_total 3" in metrics_response.text
        assert "Bearer" not in metrics_response.text

    asyncio.run(run())


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


def test_create_crashloop_test_pods_action_posts_fixed_failure_pod_manifests(monkeypatch) -> None:
    submitted: list[tuple[str, dict[str, object]]] = []

    class FakeResponse:
        status_code = 201
        text = "{}"

    async def fake_submit_ocp_request(_client, _authorization, *, method, path, content_type, body):
        assert method == "POST"
        assert content_type == "application/json"
        submitted.append((path, body))
        return FakeResponse()

    async def fake_fetch_ocp_json(_client, path, _authorization, **_kwargs):
        assert "labelSelector=" in path
        return {"items": [{"metadata": {"name": f"pod-{index}"}} for index in range(3)]}

    monkeypatch.setattr(gateway_main, "submit_ocp_request", fake_submit_ocp_request)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ENABLED", True)
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ALLOWED_NAMESPACES", {"gpu-test-kugnus"})

    sealed_plan = {
        "metadata": {"idempotencyKey": "idem-test-pods"},
        "target": {
            "apiVersion": "v1",
            "kind": "Namespace",
            "namespace": "gpu-test-kugnus",
            "name": "gpu-test-kugnus",
            "uid": "namespace-uid",
        },
        "action": {
            "toolName": "create_crashloop_test_pods",
            "normalizedParameters": {
                "appLabel": "aiops-test-pods",
                "count": 3,
                "failureMode": "crashloop",
                "fixedCommand": ["/bin/sh", "-c", "echo aiops intentional crashloop test pod; exit 1"],
                "image": "registry.access.redhat.com/ubi9/ubi-minimal:latest",
                "namePrefix": "aiops-test-pod",
            },
        },
        "digest": {"planDigest": "sha256:test-plan"},
    }

    result = asyncio.run(
        gateway_main.create_crashloop_test_pods_execution_result(sealed_plan, object(), "Bearer executor-token")
    )

    dry_runs = [item for item in submitted if "dryRun=All" in item[0]]
    mutations = [item for item in submitted if "dryRun=All" not in item[0]]
    assert result["mutationOutcome"]["status"] == "mutation_succeeded"
    assert len(dry_runs) == 3
    assert len(mutations) == 3
    first_body = mutations[0][1]
    assert first_body["metadata"]["namespace"] == "gpu-test-kugnus"
    assert first_body["metadata"]["labels"]["app"] == "aiops-test-pods"
    assert first_body["metadata"]["labels"]["aiops.komsco/scenario"] == "crashloop-test"
    assert first_body["spec"]["restartPolicy"] == "Always"
    assert first_body["spec"]["containers"][0]["command"] == [
        "/bin/sh",
        "-c",
        "echo aiops intentional crashloop test pod; exit 1",
    ]


def test_test_pod_create_count_from_korean_and_english_words() -> None:
    assert gateway_main.test_pod_create_count_from_message(
        "gpu-test-kugnus 네임스페이스에 테스트pod 두개만 생성해봐"
    ) == 2
    assert gateway_main.test_pod_create_count_from_message(
        "gpu-test-kugnus 네임스페이스에 테스트 pod 두 개 생성"
    ) == 2
    assert gateway_main.test_pod_create_count_from_message(
        "gpu-test-kugnus namespace test pod two create"
    ) == 2
    assert gateway_main.test_pod_create_request_from_message(
        "gpu-test-kugnus 네임스페이스에 테스트pod 두개만 생성해봐"
    )["count"] == 2


def test_chat_stream_test_pod_create_is_disabled_by_default(monkeypatch) -> None:
    gateway_main.NAMESPACE_CLEANUP_CHAT_CANDIDATES.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ENABLED", False)
    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "gpu-test-kugnus 네임스페이스에 테스트pod 두개만 생성해봐",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                    "runId": "run-test-pod-disabled",
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        text = "\n".join(
            event.get("content", "")
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        )
        assert "검증 전용 경로" in text
        assert "Action Plan 후보를 만들지 않습니다" in text
        assert not [
            candidate
            for candidate in gateway_main.NAMESPACE_CLEANUP_CHAT_CANDIDATES.values()
            if candidate.get("sourceType") == "create_crashloop_test_pods"
        ]

    asyncio.run(run())


def test_chat_stream_test_pod_create_keeps_requested_count_in_gateway_candidate(monkeypatch) -> None:
    gateway_main.NAMESPACE_CLEANUP_CHAT_CANDIDATES.clear()

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {
            "allowed": True,
            "enabled": True,
            "required": True,
            "resourceAttributes": {"resource": "consoleplugins", "verb": "get"},
        }

    async def fake_test_pod_preflight(_user_auth_header: str, request: Mapping[str, object]) -> dict:
        assert request["namespace"] == "gpu-test-kugnus"
        assert request["count"] == 2
        return {
            "namespace": "gpu-test-kugnus",
            "ok": True,
            "server": "https://api.test:6443",
            "status": "namespace_ready",
            "uid": "namespace-uid-gpu-test",
        }

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ENABLED", True)
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ALLOWED_NAMESPACES", {"gpu-test-kugnus"})
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "collect_test_pod_create_preflight", fake_test_pod_preflight)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": "Bearer test-token"},
                json={
                    "message": "gpu-test-kugnus 네임스페이스에 테스트pod 두개만 생성해봐",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                    "runId": "run-test-pod-two",
                },
            )

        assert response.status_code == 200
        events = parse_sse_events(response.text)
        text = "\n".join(
            event.get("content", "")
            for event in events
            if isinstance(event, dict) and event.get("type") == "text"
        )
        assert "생성 수량: `2`" in text
        candidates = [
            candidate
            for candidate in gateway_main.NAMESPACE_CLEANUP_CHAT_CANDIDATES.values()
            if candidate.get("sourceType") == "create_crashloop_test_pods"
        ]
        assert candidates
        latest = candidates[-1]
        assert latest["parameters"]["count"] == 2
        assert latest["target"]["namespace"] == "gpu-test-kugnus"
        assert "2개" in latest["title"]

    asyncio.run(run())




def test_pod_inventory_evidence_creates_review_only_action_candidates() -> None:
    req = ChatRequest(
        message="현재 클러스터에서 에러 상태인 pod 목록을 확인하고 원인 분석해줘",
        pageContext={"aiopsExecutionMode": "execute"},
    )
    gateway_evidence = """
Current Pod list evidence:
Namespace filter: `all-accessible-namespaces`
Rows shown: 2
| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State | Owner |
| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |
| openshift-operators | nginx-gateway-fabric-controller-manager-85458465f9-4njg9 | manager | Running | 2026-07-08T01:00:00Z | 0/1 | 61 | Error/1 | ReplicaSet/nginx-gateway-fabric-controller-manager-85458465f9 |
| appscan-nfs-provisioner | appscan-nfs-provisioner-nfs-subdir-external-provisioner-74b6rsb | nfs-subdir-external-provisioner | Running | 2026-07-08T01:00:00Z | 1/1 | 19 | Error/255 | ReplicaSet/appscan-nfs-provisioner-nfs-subdir-external-provisioner-74b6rsb |
| komsco-ai-dev | aiops-two-pod-exec-0 | sleeper | Running | 2026-07-08T01:00:00Z | 1/1 | 374 | Completed/0 | ReplicaSet/aiops-two-pod-exec |
| komsco-ai-dev | healthy-api-0 | api | Running | 2026-07-08T01:00:00Z | 1/1 | 0 | - | ReplicaSet/healthy-api |
"""

    candidates = gateway_main.pod_inventory_action_candidates_from_evidence(
        req,
        gateway_evidence,
        incident_id="inc-test",
        run_id="run-test",
    )

    assert len(candidates) == 2
    assert {candidate["sourceType"] for candidate in candidates} == {"pod_diagnostic_review"}
    assert all(candidate["approvalRequired"] is True for candidate in candidates)
    assert all(candidate["executable"] is False for candidate in candidates)
    assert all(candidate["executionPolicy"]["proposalOnly"] is True for candidate in candidates)
    assert all(candidate["mutationSubmitted"] is False for candidate in candidates)
    assert all(candidate["target"]["kind"] == "Pod" for candidate in candidates)
    assert {candidate["target"]["namespace"] for candidate in candidates} == {
        "appscan-nfs-provisioner",
        "openshift-operators",
    }
    assert all("delete" in set(candidate["blockedActions"]) for candidate in candidates)
    assert all("Pod 삭제" in candidate["expectedImpact"] for candidate in candidates)

    answer = build_grounded_aiops_answer(req, {"task_type": "pod_inventory"}, gateway_evidence)
    assert answer is not None
    assert "## Pod 상태 목록" in answer
    assert "nginx-gateway-fabric-controller-manager-85458465f9-4njg9" in answer
    assert "appscan-nfs-provisioner-nfs-subdir-external-provisioner-74b6rsb" in answer
    assert "aiops-two-pod-exec-0" not in answer
    assert "healthy-api-0" not in answer
    assert "단순 재시작 이력만 있는 항목은 기본 표에서 제외" in answer
    assert "docs.openshift.com" not in answer


def test_pod_inventory_error_answer_caps_display_rows() -> None:
    req = ChatRequest(message="현재 클러스터에서 에러 상태인 pod 목록을 확인해줘")
    rows = "\n".join(
        f"| ns-{index} | pod-error-{index} | app | Error | 2026-07-08T01:00:00Z | 0/1 | 1 | Error/1 | ReplicaSet/app-{index} |"
        for index in range(12)
    )
    gateway_evidence = f"""
Current Pod list evidence:
Namespace filter: `all-accessible-namespaces`
Rows shown: 12
| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State | Owner |
| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |
{rows}
"""

    answer = build_grounded_aiops_answer(req, {"task_type": "pod_inventory"}, gateway_evidence)

    assert answer is not None
    assert "에러/비정상 Pod/Container 12건" in answer
    assert "추가 2건은 상세 확인 대상" in answer
    assert "pod-error-0" in answer
    assert "pod-error-9" in answer
    assert "pod-error-10" not in answer
    assert answer.count("| 높음 |") == 10


def test_pod_inventory_restart_request_can_include_restart_only_rows() -> None:
    req = ChatRequest(message="현재 클러스터에서 재시작 횟수가 높은 pod 목록을 확인해줘")
    gateway_evidence = """
Current Pod list evidence:
Namespace filter: `all-accessible-namespaces`
Rows shown: 2
| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State | Owner |
| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |
| komsco-ai-dev | aiops-two-pod-exec-0 | sleeper | Running | 2026-07-08T01:00:00Z | 1/1 | 374 | Completed/0 | ReplicaSet/aiops-two-pod-exec |
| komsco-ai-dev | healthy-api-0 | api | Running | 2026-07-08T01:00:00Z | 1/1 | 0 | - | ReplicaSet/healthy-api |
"""

    answer = build_grounded_aiops_answer(req, {"task_type": "pod_inventory"}, gateway_evidence)

    assert answer is not None
    assert "aiops-two-pod-exec-0" in answer
    assert "healthy-api-0" not in answer
    assert "Completed/0 반복 재시작 이력" in answer


def test_recent_chat_action_candidates_are_not_trimmed_by_overview_priority() -> None:
    gateway_main.NAMESPACE_CLEANUP_CHAT_CANDIDATES.clear()
    try:
        recent_candidate = {
            "id": "recent-chat-pod-diagnostic",
            "chatRunId": "run-current",
            "priority": 99,
            "sourceType": "pod_diagnostic_review",
            "target": {"kind": "Pod", "namespace": "team-a", "name": "pod-a"},
            "title": "Pod 원인 확인 플랜",
            "expiresAt": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
        }
        gateway_main.NAMESPACE_CLEANUP_CHAT_CANDIDATES[recent_candidate["id"]] = recent_candidate
        overview_candidates = {
            "apiVersion": "aiops.komsco/v1",
            "kind": "AIOpsActionCandidateSummary",
            "metadata": {"name": "overview"},
            "spec": {
                "candidates": [
                    {
                        "id": f"overview-{index}",
                        "priority": index,
                        "sourceType": "pod_restart_spike",
                        "target": {"kind": "Pod", "namespace": "team-b", "name": f"pod-{index}"},
                        "title": "Overview candidate",
                    }
                    for index in range(1, 10)
                ],
                "totals": {},
            },
        }

        merged = gateway_main.merge_recent_namespace_cleanup_candidates(overview_candidates)
        candidates = merged["spec"]["candidates"]

        assert candidates[0]["id"] == "recent-chat-pod-diagnostic"
        assert candidates[0]["chatRunId"] == "run-current"
        assert len(candidates) == 8
    finally:
        gateway_main.NAMESPACE_CLEANUP_CHAT_CANDIDATES.clear()




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
