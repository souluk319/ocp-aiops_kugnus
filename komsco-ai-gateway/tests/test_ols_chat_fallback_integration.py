import asyncio
import json
from collections.abc import Mapping

import httpx
from fastapi import HTTPException

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.answer_planning import (
    ANSWER_KIND_RCA,
    ANSWER_KIND_RUNTIME_HEALTH,
    build_gateway_evidence_snapshot,
    classify_fallback_answer_kind,
)
from komsco_ai_gateway.followup_selection import (
    extract_numbered_followups,
    resolve_numeric_followup_message,
    selected_followup_index,
)
from komsco_ai_gateway.main import (
    ChatRequest,
    ImageAttachment,
    app,
    build_action_proposal_fallback,
    build_empty_answer_fallback,
    build_ols_required_failure_answer,
)
from komsco_ai_gateway.security import classify_request_policy, safe_subject


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
