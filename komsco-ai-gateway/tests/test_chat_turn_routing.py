from komsco_ai_gateway.aiops_contracts import build_rca_context, build_runtime_tool_plan
from komsco_ai_gateway.chat_turn_routing import classify_chat_turn_intent
from komsco_ai_gateway.page_context import normalize_console_page_context


def test_product_feedback_is_not_an_openshift_incident() -> None:
    message = "답변 개선 후보가 실제 개선에 도움이 될까?"

    assert classify_chat_turn_intent(message) == "product_feedback"

    plan = build_runtime_tool_plan(message)
    assert plan["task_type"] == "product_feedback"
    assert plan["tool_plan"] == []
    assert plan["validation"]["ok"] is True


def test_rca_screen_explanation_uses_ui_intent_without_cluster_tools() -> None:
    page_context = {
        "href": "http://localhost:9000/dashboards/aiops/audit",
        "pathname": "/dashboards/aiops/audit",
        "route": "dashboards",
        "aiopsViewContext": {
            "pageTitle": "RCA 센터",
            "summary": "파드 상태 저하",
        },
    }
    message = "지금 보는 화면에 나오는 시각화 대시보드를 설명해줘"

    assert classify_chat_turn_intent(message, page_context=page_context) == "ui_explanation"

    plan = build_runtime_tool_plan(message, page_context=page_context)
    assert plan["task_type"] == "ui_explanation"
    assert plan["tool_plan"] == []

    context = build_rca_context(
        message=message,
        tool_plan=plan,
        page_context=page_context,
    )
    assert context["analysisPlan"]["answerContract"]["format"] == "ui_explanation"
    assert context["evidence"]["missing"] == []
    assert context["causeCandidates"] == []
    assert context["actionCandidates"] == []


def test_operational_screen_question_remains_operational() -> None:
    page_context = {"route": "/dashboards/aiops/audit"}
    message = "현재 화면의 파드 오류 원인을 분석하고 조치 후보를 알려줘"

    assert classify_chat_turn_intent(message, page_context=page_context) == "operational"

    plan = build_runtime_tool_plan(message, page_context=page_context)
    assert plan["task_type"] != "ui_explanation"
    assert plan["tool_plan"]


def test_runbook_operational_question_is_not_product_feedback() -> None:
    message = "Runbook에 반영된 Pod 재시작 절차를 확인해줘"

    assert classify_chat_turn_intent(message) == "operational"


def test_cluster_operator_question_is_not_product_feedback() -> None:
    assert classify_chat_turn_intent("답변 개선보다 클러스터 상태를 조회해줘") == "operational"
    assert classify_chat_turn_intent("답변 품질 말고 ClusterOperator 상태를 확인해줘") == "operational"


def test_rca_view_context_survives_gateway_normalization() -> None:
    context = normalize_console_page_context(
        {
            "route": "/dashboards/aiops/audit",
            "aiopsViewContext": {
                "pageTitle": "RCA 센터",
                "case": {"caseId": "RCA-TEST-001", "title": "파드 상태 저하"},
                "findings": [{"title": "파드 런타임 이상 신호"}],
                "evidence": [{"field": "실패", "value": "2"}],
            },
        }
    )

    assert context["aiopsViewContext"]["case"]["caseId"] == "RCA-TEST-001"
    assert context["aiopsViewContext"]["findings"][0]["title"] == "파드 런타임 이상 신호"
    assert context["aiopsViewContext"]["evidence"][0]["value"] == "2"
