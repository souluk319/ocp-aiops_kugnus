import json
from datetime import UTC, datetime, timedelta

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import (
    ChatRequest,
    build_aiops_answer_contract_text,
    build_conversation_cleanup_review_candidate,
    build_grounded_aiops_answer,
    build_ols_query,
    cleanup_scope_clarification_response,
    conversation_focus_from_request,
    is_ambiguous_cleanup_review_request,
    pod_inventory_action_candidates_from_evidence,
    should_clarify_cleanup_scope,
    should_create_cleanup_review_candidate,
)
from komsco_ai_gateway.aiops_contracts import build_rca_context, build_runtime_tool_plan


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
