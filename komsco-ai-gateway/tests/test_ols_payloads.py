import json

import pytest
from fastapi import HTTPException

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.aiops_contracts import (
    build_rca_context,
    build_runtime_safety_contract,
    build_runtime_tool_plan,
)
from komsco_ai_gateway.main import (
    ChatRequest,
    ImageAttachment,
    build_aiops_answer_contract_text,
    build_attachment_context,
    build_ols_context_handoff,
    build_ols_gateway_context,
    build_ols_payload,
    build_ols_query,
    should_forward_image_attachments_to_ols,
    validate_image_attachments,
)
from komsco_ai_gateway.security import classify_request_policy, safe_subject


def test_validate_image_attachments_accepts_supported_base64_image() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    validate_image_attachments([attachment])
    context = build_attachment_context([attachment])

    assert "cluster.png" in context
    assert "image/png" in context


def test_build_attachment_context_without_vision_uses_metadata_only_language() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="catalog-screen.png",
        size=8,
    )

    context = build_attachment_context([attachment])

    assert "원본 이미지 attachment를 받지 않습니다" in context
    assert "첨부 파일 메타데이터" in context
    assert "사용자 설명" in context
    assert "도구 조회 결과" in context
    assert "이미지 원본 판독은 수행하지 않았습니다" not in context


def test_build_ols_payload_does_not_forward_image_attachments_by_default() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    payload = build_ols_payload("이미지 분석해줘", "conversation-1", [attachment])

    assert payload == {"query": "이미지 분석해줘"}


def test_build_ols_payload_can_disable_image_attachment_forwarding() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    payload = build_ols_payload(
        "이미지 분석해줘",
        "conversation-1",
        [attachment],
        forward_image_attachments=False,
    )

    assert payload == {
        "query": "이미지 분석해줘",
    }


def test_build_ols_payload_never_forwards_unsupported_image_attachments() -> None:
    attachment = ImageAttachment(
        data="iVBORw0KGgo=",
        id="image-1",
        mimeType="image/png",
        name="cluster.png",
        size=8,
    )

    payload = build_ols_payload(
        "이미지 분석해줘",
        "conversation-1",
        [attachment],
        forward_image_attachments=True,
    )

    assert payload == {"query": "이미지 분석해줘"}


def test_image_attachment_forwarding_stays_disabled_with_stale_env(monkeypatch) -> None:
    monkeypatch.setenv("KOMSCO_AI_FORWARD_IMAGE_ATTACHMENTS_TO_OLS", "true")

    assert should_forward_image_attachments_to_ols() is False


def test_build_ols_payload_keeps_gateway_context_out_of_ols_body() -> None:
    plan = build_runtime_tool_plan("default 네임스페이스 pod가 왜 재시작됐어?")
    rca_context = build_rca_context(
        message="default 네임스페이스 pod가 왜 재시작됐어?",
        tool_plan=plan,
        evidence_refs=[],
        run_id="run-ols-context",
        incident_id="inc-ols-context",
    )
    safety_contract = build_runtime_safety_contract(
        mutations_enabled=False,
        unrestricted_commands_enabled=False,
        diagnostics_enabled=False,
        record_store_enabled=False,
        latest_runtime_tool_plan=plan,
        latest_rca_context=rca_context,
    )
    gateway_context = build_ols_gateway_context(
        tool_plan=plan,
        rca_context=rca_context,
        safety_contract=safety_contract,
        policy={"decision": "allow_evidence_collection", "token": "secret-token-value-1234567890"},
        gateway_evidence="safe line\nAuthorization: Bearer secret-token-value-1234567890",
    )

    payload = build_ols_payload(
        "질문",
        "conversation-1",
        [],
        gateway_context=gateway_context,
    )
    rendered = json.dumps(payload, ensure_ascii=False)

    assert payload == {"query": "질문"}
    assert gateway_context["kind"] == "GatewayContext"
    assert gateway_context["toolPlan"]["kind"] == "ToolPlan"
    assert gateway_context["rcaContext"]["kind"] == "RcaContext"
    assert gateway_context["safetyContract"]["mode"] == "evidence_check"
    assert gateway_context["missingEvidence"]
    assert gateway_context["metadata"]["digest"].startswith("sha256:")
    assert gateway_context["metadata"]["rcaContextDigest"] == rca_context["metadata"]["digest"]
    assert "gateway_context" not in payload
    assert "secret-token-value" not in rendered
    assert "Bearer secret" not in rendered


def test_build_ols_payload_can_forward_conversation_id_when_explicitly_enabled(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "OLS_FORWARD_CONVERSATION_ID", True)

    payload = build_ols_payload("질문", "conversation-1", [])

    assert payload == {"query": "질문", "conversation_id": "conversation-1"}


def test_validate_image_attachments_rejects_unsupported_type() -> None:
    attachment = ImageAttachment(
        data="aGVsbG8=",
        id="image-1",
        mimeType="text/plain",
        name="note.txt",
        size=5,
    )

    with pytest.raises(HTTPException):
        validate_image_attachments([attachment])


def test_build_ols_query_defaults_to_minimal_safe_prompt() -> None:
    query = build_ols_query(
        ChatRequest(
            message="최근 OpenShift 경고와 우선 확인할 항목을 정리해줘.",
            pageContext={
                "href": "http://localhost:9000/k8s/cluster/projects",
                "pathname": "/k8s/cluster/projects",
                "title": "개요 · 클러스터 · OKD",
            },
        )
    )

    assert "최근 OpenShift 경고" in query
    assert "[KOMSCO AI Gateway handoff]" not in query
    assert "[User question]" not in query
    assert "Use live OpenShift evidence collection when cluster facts are needed" in query
    assert "Do not invent alert, pod, node, namespace, resource names" in query
    assert "If no screenshot/image is attached" in query
    assert "기본 운영 답변 양식" in query
    assert "상황에 맞는 선택지를 최대 3개까지 번호 목록으로 제안" in query
    assert "Action Plan은 반사적으로 만들거나 노출하지 말고" in query
    assert "Policy decision:" in query
    assert "현재 판단" in query
    assert len(query) < 2000
    assert "title" not in query
    assert "OKD" not in query


def test_build_ols_context_handoff_summarizes_plan_and_redacts_evidence() -> None:
    plan = build_runtime_tool_plan("어제 새벽에 default namespace Pod가 왜 재시작됐어?")
    rca_context = build_rca_context(
        message="어제 새벽에 default namespace Pod가 왜 재시작됐어?",
        tool_plan=plan,
        evidence_refs=[
            {
                "contentDigest": "sha256:event",
                "evidenceId": "ev-event",
                "eventName": "official_namespace_restart_event",
                "eventStatus": "success",
                "evidenceType": "event",
                "summary": "default namespace restart event evidence collected",
            }
        ],
        run_id="run-handoff",
        incident_id="inc-handoff",
    )
    gateway_context = build_ols_gateway_context(
        tool_plan=plan,
        rca_context=rca_context,
        safety_contract=build_runtime_safety_contract(
            mutations_enabled=False,
            unrestricted_commands_enabled=False,
            diagnostics_enabled=False,
            record_store_enabled=False,
            latest_runtime_tool_plan=plan,
            latest_rca_context=rca_context,
        ),
        policy={"decision": "allow_evidence_collection"},
        gateway_evidence="Authorization: Bearer secret-token-value-1234567890\nOOMKilled observed",
    )

    handoff = build_ols_context_handoff(
        gateway_context=gateway_context,
        gateway_evidence="Authorization: Bearer secret-token-value-1234567890\nOOMKilled observed",
    )

    assert "Tool plan: pod_restart_rca" in handoff
    assert "Evidence refs: collected=1" in handoff
    assert "Verified facts collected before final answer" in handoff
    assert "OOMKilled observed" in handoff
    assert "secret-token-value" not in handoff
    assert "Authorization: [REDACTED] [REDACTED]" in handoff


def test_build_aiops_answer_contract_exposes_action_path() -> None:
    plan = build_runtime_tool_plan("어제 새벽에 default namespace Pod가 왜 재시작됐어?")
    rca_context = build_rca_context(
        message="어제 새벽에 default namespace Pod가 왜 재시작됐어?",
        tool_plan=plan,
        evidence_refs=[
            {
                "contentDigest": "sha256:event",
                "evidenceId": "ev-event",
                "eventStatus": "success",
                "evidenceType": "event",
            }
        ],
        run_id="run-aiops-answer-contract",
        incident_id="inc-aiops-answer-contract",
    )

    text = build_aiops_answer_contract_text(
        policy={"decision": "action_proposal_only"},
        rca_context=rca_context,
        runtime_tool_plan=plan,
    )

    assert "## 승인 대기 조치" in text
    assert "조회 계획: `pod_restart_rca`" in text
    assert "확인 결과: 수집 1건" in text
    assert "Action Plan" in text
    assert "ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord" not in text
    assert "RCA Context" not in text
    assert "/v1/actions/rejections" not in text
    assert "거절하면 실행은 차단" in text


def test_build_aiops_answer_contract_omits_action_text_for_evidence_check_analysis() -> None:
    plan = build_runtime_tool_plan("최근 OpenShift 경고와 우선 확인할 항목을 정리해줘")
    rca_context = build_rca_context(
        message="최근 OpenShift 경고와 우선 확인할 항목을 정리해줘",
        tool_plan=plan,
        evidence_refs=[
            {
                "contentDigest": "sha256:alert",
                "evidenceId": "ev-alert",
                "eventStatus": "success",
                "evidenceType": "alert",
            }
        ],
        run_id="run-aiops-evidence-check-answer-contract",
        incident_id="inc-aiops-evidence-check-answer-contract",
    )

    text = build_aiops_answer_contract_text(
        policy={"decision": "evidence_check"},
        rca_context=rca_context,
        runtime_tool_plan=plan,
    )

    assert text == ""
    assert "ActionProposal" not in text
    assert "ApprovalDecision" not in text


def test_build_ols_query_minimal_includes_short_verified_context() -> None:
    plan = build_runtime_tool_plan("어제 새벽에 default namespace Pod가 왜 재시작됐어?")
    rca_context = build_rca_context(
        message="어제 새벽에 default namespace Pod가 왜 재시작됐어?",
        tool_plan=plan,
        evidence_refs=[],
        run_id="run-ols-context",
        incident_id="inc-ols-context",
    )
    gateway_context = build_ols_gateway_context(
        tool_plan=plan,
        rca_context=rca_context,
        safety_contract=build_runtime_safety_contract(
            mutations_enabled=False,
            unrestricted_commands_enabled=False,
            diagnostics_enabled=False,
            record_store_enabled=False,
            latest_runtime_tool_plan=plan,
            latest_rca_context=rca_context,
        ),
        policy={"decision": "allow_evidence_collection"},
        gateway_evidence="Event: default/web-0 restarted at 03:14; reason=OOMKilled",
    )

    query = build_ols_query(
        ChatRequest(message="어제 새벽에 default namespace Pod가 왜 재시작됐어?"),
        gateway_context=gateway_context,
        gateway_evidence="Event: default/web-0 restarted at 03:14; reason=OOMKilled",
    )

    assert "Verified operational context:" in query
    assert "Tool plan: pod_restart_rca" in query
    assert "Event: default/web-0 restarted at 03:14; reason=OOMKilled" in query
    assert "[KOMSCO AI Gateway handoff]" not in query
    assert "[User question]" not in query


def test_build_ols_query_treats_console_path_as_context_not_image() -> None:
    query = build_ols_query(
        ChatRequest(
            message="현재 보고 있는 콘솔 화면이 무엇인지 설명해줘.",
            pageContext={
                "href": "http://localhost:9000/catalog/ns/team-a",
                "pathname": "/catalog/ns/team-a",
                "namespace": "team-a",
            },
        )
    )

    assert "첨부 이미지 없음" in query
    assert "/catalog/ns/team-a" in query
    assert '"namespace": "team-a"' in query
    assert '"route": "catalog"' in query
    assert '"resourceKind": "Catalog"' in query
    assert "If no screenshot/image is attached" in query


def test_build_ols_query_includes_aiops_alert_view_context() -> None:
    query = build_ols_query(
        ChatRequest(
            message="이 화면 무슨 상황이야?",
            pageContext={
                "aiopsViewContext": {
                    "pageTitle": "알림 & 이벤트",
                    "route": "/dashboards/aiops/alerts",
                    "visibleAlerts": [
                        {
                            "count": 3,
                            "reason": "BackOff 반복 감지",
                            "severity": "risk",
                            "target": "gpu-test-kugnus/Pod/aiops-test-pod-1",
                            "title": "BackOff 반복 감지",
                        }
                    ],
                },
                "pathname": "/dashboards/aiops/alerts",
            },
        )
    )

    assert "알림 & 이벤트" in query
    assert "BackOff 반복 감지" in query
    assert "gpu-test-kugnus/Pod/aiops-test-pod-1" in query
    assert "ignored browser title" not in query


def test_build_ols_query_includes_security_guardrail_and_redacts_user_secrets() -> None:
    policy = classify_request_policy("deployment restart 해줘 token=my-secret-token-value")
    query = build_ols_query(
        ChatRequest(message="deployment restart 해줘 token=my-secret-token-value"),
        policy=policy,
        subject=safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["a"]}),
    )

    assert "action_proposal_only" in query
    assert "[KOMSCO AI Gateway handoff]" not in query
    assert "Do not print Secret, token, password" in query
    assert "user@example.com" not in query
    assert "my-secret-token-value" not in query
    assert "[REDACTED]" in query


def test_build_ols_query_context_profile_includes_gateway_evidence(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "OLS_QUERY_PROFILE", "context")
    query = build_ols_query(
        ChatRequest(message="현재 클러스터의 Pod 상태를 분석해줘"),
        gateway_evidence="Top container restart counts:\nopenshift-lightspeed exporter restartCount=44",
    )

    assert "Verified operational context:" in query
    assert "openshift-lightspeed exporter restartCount=44" in query
    assert "RCA 또는 운영 상태 질문에는 가능한 경우 아래 순서를 사용하세요" in query
    assert "기본 운영 답변 양식" in query
    assert "상위 N개 표 정리" in query
    assert "현재 판단" in query
    assert "확인 결과" in query
    assert "추가 확인" in query
    monkeypatch.setattr(gateway_main, "OLS_QUERY_PROFILE", "minimal")


def test_build_ols_query_includes_sanitized_recent_conversation_context() -> None:
    query = build_ols_query(
        ChatRequest(
            message="안에 있는 파드들이 별 의미없는 테스트용이면 정리좀 할까해서",
            recentMessages=[
                {"role": "user", "content": "테스트 파드가있는 네임스페이스가 뭐가있어?"},
                {
                    "role": "assistant",
                    "content": (
                        "gpu-test-kugnus 네임스페이스에 aiops-test-pod-* 테스트 파드가 있습니다.\n"
                        "<|channel|>thought <channel>\n"
                        "thought The user wants internal reasoning.\n"
                    ),
                },
            ],
        )
    )

    assert "Recent conversation context:" in query
    assert "테스트 파드가있는 네임스페이스" in query
    assert "gpu-test-kugnus" in query
    assert "aiops-test-pod" in query
    assert "안에 있는 파드" in query
    assert "<|channel|>" not in query
    assert "thought The user" not in query
