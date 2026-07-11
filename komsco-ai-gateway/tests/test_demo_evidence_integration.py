import asyncio
import json
from collections.abc import Mapping

import httpx

import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import (
    ChatRequest,
    app,
    build_empty_answer_fallback,
    build_grounded_aiops_answer,
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
