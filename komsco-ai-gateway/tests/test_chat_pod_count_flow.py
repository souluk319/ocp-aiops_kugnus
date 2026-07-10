from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import httpx

from komsco_ai_gateway.answer_streaming import sse
from komsco_ai_gateway.chat_pod_count_flow import (
    DirectPodCountFlowDependencies,
    TopPodNamespaceFlowDependencies,
    TopPodNamespaceStreamEvent,
    stream_direct_pod_count,
    stream_top_pod_namespace_count,
)
from komsco_ai_gateway.pod_counting import (
    build_pod_count_investigation,
    build_top_pod_namespace_count_result,
    pod_count_investigation_response,
    top_pod_namespace_count_response,
)


class FakeAsyncClient:
    calls: list[dict[str, Any]] = []

    def __init__(self, **kwargs: Any) -> None:
        self.calls.append(kwargs)

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, *_args: Any) -> None:
        return None


def dependencies(
    *,
    api_url: str = "https://api.test:6443",
    fetch_ocp_json=None,
    current_rca_context_event=None,
) -> TopPodNamespaceFlowDependencies:
    async def default_fetch(_client, path: str, authorization: str):
        assert path == "/api/v1/pods"
        assert authorization == "Bearer token"
        return {
            "items": [
                {"metadata": {"name": "a-1", "namespace": "team-a"}},
                {"metadata": {"name": "a-2", "namespace": "team-a"}},
                {"metadata": {"name": "b-1", "namespace": "team-b"}},
            ]
        }

    def build_evidence_events(**_kwargs: Any) -> list[dict[str, Any]]:
        return [
            {"type": "tool_call", "id": "evidence-1", "name": "evidence_ref", "summary": "증거 참조 생성"},
            {
                "type": "tool_result",
                "detail": "evidence detail",
                "id": "evidence-1",
                "name": "evidence_ref",
                "result": {"evidenceId": "evidence-1"},
                "status": "success",
                "summary": "evidence-1 기록",
            },
        ]

    return TopPodNamespaceFlowDependencies(
        openshift_api_url=api_url,
        openshift_api_ca_file="/ca.crt",
        async_client_factory=FakeAsyncClient,
        timeout_factory=lambda timeout, *, connect: {"timeout": timeout, "connect": connect},
        fetch_ocp_json=fetch_ocp_json or default_fetch,
        build_result=build_top_pod_namespace_count_result,
        build_response=top_pod_namespace_count_response,
        build_evidence_events=build_evidence_events,
        current_rca_context_event=current_rca_context_event
        or (lambda phase: {"type": "rca_context", "context": {"metadata": {"phase": phase, "digest": "latest"}}}),
    )


async def collect_events(deps: TopPodNamespaceFlowDependencies) -> list[TopPodNamespaceStreamEvent]:
    return [
        event
        async for event in stream_top_pod_namespace_count(
            authorization="Bearer token",
            dependencies=deps,
            incident_id="inc-1",
            request_id="req-1",
            run_id="run-1",
            subject={"username": "dev-user"},
        )
    ]


def decode_payload(payload: str) -> Mapping[str, Any] | str:
    data = payload.removeprefix("data: ").removesuffix("\n\n")
    return data if data == "[DONE]" else json.loads(data)


def test_found_stream_preserves_exact_payloads_and_order() -> None:
    FakeAsyncClient.calls.clear()
    events = asyncio.run(collect_events(dependencies()))
    payloads = [event.payload for event in events]
    result = {
        "rows": [
            {"namespace": "team-a", "podCount": 2},
            {"namespace": "team-b", "podCount": 1},
        ],
        "status": "found",
        "topNamespace": "team-a",
        "topPodCount": 2,
        "totalNamespaces": 2,
        "totalPods": 3,
    }
    answer = top_pod_namespace_count_response(result)

    assert payloads == [
        sse(
            {
                "type": "tool_call",
                "id": "req-1-top-pod-namespace-count",
                "name": "top_pod_namespace_count_lookup",
                "summary": "namespace별 Pod 수 집계",
            }
        ),
        sse(
            {
                "type": "tool_result",
                "detail": answer,
                "id": "req-1-top-pod-namespace-count",
                "name": "top_pod_namespace_count_lookup",
                "result": result,
                "status": "success",
                "summary": "team-a namespace가 Pod 2개로 최다",
            }
        ),
        sse({"type": "tool_call", "id": "evidence-1", "name": "evidence_ref", "summary": "증거 참조 생성"}),
        sse(
            {
                "type": "tool_result",
                "detail": "evidence detail",
                "id": "evidence-1",
                "name": "evidence_ref",
                "result": {"evidenceId": "evidence-1"},
                "status": "success",
                "summary": "evidence-1 기록",
            }
        ),
        sse({"type": "rca_context", "context": {"metadata": {"phase": "post_answer", "digest": "latest"}}}),
        sse(
            {
                "type": "text",
                "content": answer,
                "source": "gateway_direct_lookup",
                "answerContract": "top-pod-namespace-count-v0.2.9",
            }
        ),
        sse(
            {
                "type": "run_status",
                "runId": "run-1",
                "stage": "completed",
                "message": "Gateway namespace별 Pod 수 집계 완료",
            }
        ),
        "data: [DONE]\n\n",
    ]
    assert FakeAsyncClient.calls == [{"verify": "/ca.crt", "timeout": {"timeout": 20.0, "connect": 5.0}}]


def test_url_unavailable_stream_preserves_exact_result_and_skips_client() -> None:
    FakeAsyncClient.calls.clear()
    events = asyncio.run(collect_events(dependencies(api_url="")))
    result = {
        "reason": "OPENSHIFT_API_URL is not configured",
        "rows": [],
        "status": "unavailable",
    }
    answer = (
        "namespace별 Pod 수를 직접 조회하지 못했습니다.\n\n"
        "- 사유: OPENSHIFT_API_URL is not configured\n"
        "- 서버 변경은 실행하지 않았습니다."
    )

    assert [event.payload for event in events] == [
        sse(
            {
                "type": "tool_call",
                "id": "req-1-top-pod-namespace-count",
                "name": "top_pod_namespace_count_lookup",
                "summary": "namespace별 Pod 수 집계",
            }
        ),
        sse(
            {
                "type": "tool_result",
                "detail": answer,
                "id": "req-1-top-pod-namespace-count",
                "name": "top_pod_namespace_count_lookup",
                "result": result,
                "status": "skipped",
                "summary": "namespace별 Pod 수 집계 실패",
            }
        ),
        sse({"type": "tool_call", "id": "evidence-1", "name": "evidence_ref", "summary": "증거 참조 생성"}),
        sse(
            {
                "type": "tool_result",
                "detail": "evidence detail",
                "id": "evidence-1",
                "name": "evidence_ref",
                "result": {"evidenceId": "evidence-1"},
                "status": "success",
                "summary": "evidence-1 기록",
            }
        ),
        sse({"type": "rca_context", "context": {"metadata": {"phase": "post_answer", "digest": "latest"}}}),
        sse(
            {
                "type": "text",
                "content": answer,
                "source": "gateway_direct_lookup",
                "answerContract": "top-pod-namespace-count-v0.2.9",
            }
        ),
        sse(
            {
                "type": "run_status",
                "runId": "run-1",
                "stage": "completed",
                "message": "Gateway namespace별 Pod 수 집계 완료",
            }
        ),
        "data: [DONE]\n\n",
    ]
    assert FakeAsyncClient.calls == []


def test_tool_call_is_yielded_before_blocking_fetch_completes() -> None:
    fetch_started = asyncio.Event()
    release_fetch = asyncio.Event()

    async def blocking_fetch(_client, _path: str, _authorization: str):
        fetch_started.set()
        await release_fetch.wait()
        return {"items": []}

    async def run() -> None:
        stream = stream_top_pod_namespace_count(
            authorization="Bearer token",
            dependencies=dependencies(fetch_ocp_json=blocking_fetch),
            incident_id="inc-1",
            request_id="req-1",
            run_id="run-1",
            subject=None,
        )
        first = await anext(stream)
        assert decode_payload(first.payload)["type"] == "tool_call"
        assert not fetch_started.is_set()

        second_task = asyncio.create_task(anext(stream))
        await fetch_started.wait()
        assert not second_task.done()
        release_fetch.set()
        await second_task
        await stream.aclose()

    asyncio.run(run())


def test_rca_event_carries_latest_context_update_before_payload_is_yielded() -> None:
    latest_context = {"metadata": {"phase": "post_answer", "digest": "fresh"}}
    events = asyncio.run(
        collect_events(
            dependencies(
                current_rca_context_event=lambda phase: {
                    "type": "rca_context",
                    "context": {**latest_context, "phaseArgument": phase},
                }
            )
        )
    )
    rca_event = next(event for event in events if decode_payload(event.payload)["type"] == "rca_context")

    assert rca_event.latest_rca_context == {**latest_context, "phaseArgument": "post_answer"}
    assert decode_payload(rca_event.payload)["context"] == rca_event.latest_rca_context


def test_main_builds_fresh_dependencies_from_monkeypatched_bindings(monkeypatch) -> None:
    import komsco_ai_gateway.main as gateway_main

    captured: list[TopPodNamespaceFlowDependencies] = []
    rca_updates_observed_before_next_yield: list[bool] = []

    async def fake_stream(**kwargs: Any):
        deps = kwargs["dependencies"]
        captured.append(deps)
        latest_context = {"sourceUrl": deps.openshift_api_url}
        yield TopPodNamespaceStreamEvent(
            sse({"type": "rca_context", "context": latest_context}),
            latest_rca_context=latest_context,
        )
        rca_updates_observed_before_next_yield.append(gateway_main.LAST_RCA_CONTEXT is latest_context)
        yield TopPodNamespaceStreamEvent(sse("[DONE]"))

    async def fake_subject_review(_authorization: str) -> dict[str, Any]:
        return {"username": "dev-user", "uid": "uid-dev", "groups": []}

    async def fake_access_review(_authorization: str) -> dict[str, Any]:
        return {"allowed": True, "enabled": True, "required": True}

    async def fetch_one(*_args: Any, **_kwargs: Any):
        return {"items": []}

    async def fetch_two(*_args: Any, **_kwargs: Any):
        return {"items": []}

    monkeypatch.setattr(gateway_main, "stream_top_pod_namespace_count", fake_stream)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_access_review)
    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://first.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fetch_one)

    async def request_once(client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/v1/chat/stream",
            headers={"Authorization": "Bearer token"},
            json={"message": "파드 수가 제일 많은 네임스페이스는 뭐야"},
        )
        assert response.status_code == 200

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await request_once(client)
            monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://second.test:6443")
            monkeypatch.setattr(gateway_main, "fetch_ocp_json", fetch_two)
            await request_once(client)

    asyncio.run(run())

    assert [deps.openshift_api_url for deps in captured] == [
        "https://first.test:6443",
        "https://second.test:6443",
    ]
    assert captured[0].fetch_ocp_json is fetch_one
    assert captured[1].fetch_ocp_json is fetch_two
    assert rca_updates_observed_before_next_yield == [True, True]
    assert gateway_main.LAST_RCA_CONTEXT == {"sourceUrl": "https://second.test:6443"}


def test_flow_module_import_does_not_import_main() -> None:
    package_root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import komsco_ai_gateway.chat_pod_count_flow; "
                "assert 'komsco_ai_gateway.main' not in sys.modules"
            ),
        ],
        cwd=package_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


DIRECT_DEPLOYMENTS = {
    "items": [
        {
            "metadata": {"name": "web", "namespace": "team-a"},
            "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "web"}}},
            "status": {"availableReplicas": 1, "readyReplicas": 1, "updatedReplicas": 1},
        }
    ]
}
DIRECT_PODS = {
    "items": [
        {
            "metadata": {"labels": {"app": "web"}, "name": "web-abc", "namespace": "team-a"},
            "status": {"containerStatuses": [{"ready": True, "restartCount": 0}], "phase": "Running"},
        }
    ]
}
DIRECT_FOUND_RESULT = {
    "matchStrategy": "deployment_selector",
    "namespace": "team-a",
    "rows": [
        {
            "phaseCounts": {"Running": 1},
            "podDetails": [
                {"name": "web-abc", "phase": "Running", "ready": "1/1", "restarts": 0, "terminating": False}
            ],
            "readyPods": 1,
            "runningPods": 1,
            "terminatingPods": 0,
            "totalPods": 1,
            "unhealthyPods": 0,
            "availableReplicas": 1,
            "desiredReplicas": 1,
            "kind": "Deployment",
            "namespace": "team-a",
            "observedGeneration": None,
            "readyReplicas": 1,
            "targetName": "web",
            "updatedReplicas": 1,
        }
    ],
    "status": "found",
    "targetName": "web",
}


def direct_dependencies(*, api_url: str = "https://api.test:6443", fetch_ocp_json=None, evidence_calls=None):
    async def default_fetch(_client, path: str, authorization: str):
        assert authorization == "Bearer token"
        return DIRECT_DEPLOYMENTS if "deployments" in path else DIRECT_PODS

    def items(payload):
        return [item for item in (payload or {}).get("items", []) if isinstance(item, Mapping)]

    def evidence(**kwargs: Any) -> list[dict[str, Any]]:
        if evidence_calls is not None:
            evidence_calls.append(kwargs)
        return [
            {"type": "tool_call", "id": "evidence-direct", "name": "evidence_ref", "summary": "증거 참조 생성"},
            {
                "type": "tool_result",
                "detail": "direct evidence detail",
                "id": "evidence-direct",
                "name": "evidence_ref",
                "result": {"evidenceId": "evidence-direct"},
                "status": "success",
                "summary": "evidence-direct 기록",
            },
        ]

    return DirectPodCountFlowDependencies(
        openshift_api_url=api_url,
        openshift_api_ca_file="/ca.crt",
        async_client_factory=FakeAsyncClient,
        timeout_factory=lambda timeout, *, connect: {"timeout": timeout, "connect": connect},
        fetch_ocp_json=fetch_ocp_json or default_fetch,
        path_segment=lambda value: value,
        resource_items=items,
        metadata_name=lambda resource: str(resource.get("metadata", {}).get("name") or ""),
        metadata_namespace=lambda resource: str(resource.get("metadata", {}).get("namespace") or ""),
        build_investigation=build_pod_count_investigation,
        build_response=pod_count_investigation_response,
        redact_sensitive=lambda value: value,
        build_evidence_events=evidence,
        current_rca_context_event=lambda phase: {
            "type": "rca_context",
            "context": {"metadata": {"phase": phase, "digest": "direct-latest"}},
        },
    )


async def collect_direct_events(query, deps=None) -> list[TopPodNamespaceStreamEvent]:
    return [
        event
        async for event in stream_direct_pod_count(
            authorization="Bearer token",
            dependencies=deps or direct_dependencies(),
            incident_id="inc-direct",
            pod_count_query=query,
            request_id="req-direct",
            run_id="run-direct",
            subject={"username": "dev-user"},
        )
    ]


def direct_tail(result: dict[str, Any]) -> list[Mapping[str, Any] | str]:
    answer = pod_count_investigation_response(result)
    investigation = {
        "type": "tool_result",
        "detail": answer,
        "id": "req-direct-pod-count-investigation",
        "name": "pod_count_investigation",
        "result": result,
        "status": "success" if result.get("status") == "found" else "skipped",
        "summary": "Pod 개수 직접 조회 완료",
    }
    return [
        {"type": "tool_call", "id": "req-direct-pod-count-investigation", "name": "pod_count_investigation", "summary": "Pod 개수 조회 결과 정리"},
        investigation,
        {"type": "tool_call", "id": "evidence-direct", "name": "evidence_ref", "summary": "증거 참조 생성"},
        {"type": "tool_result", "detail": "direct evidence detail", "id": "evidence-direct", "name": "evidence_ref", "result": {"evidenceId": "evidence-direct"}, "status": "success", "summary": "evidence-direct 기록"},
        {"type": "rca_context", "context": {"metadata": {"phase": "post_answer", "digest": "direct-latest"}}},
        {"type": "text", "content": answer},
        {"type": "run_status", "runId": "run-direct", "stage": "completed", "message": "Gateway Pod 개수 직접 조회 완료"},
        "[DONE]",
    ]


def scope_events(query: dict[str, str]) -> list[Mapping[str, Any]]:
    namespace = query.get("namespace") or ""
    target = query.get("targetName") or ""
    scope = f"namespace `{namespace}` 범위에서 조회" if namespace else "접근 가능한 전체 namespace에서 조회"
    return [
        {"type": "tool_call", "id": "req-direct-pod-count-scope", "name": "pod_count_scope_resolve", "summary": "요청에서 대상 이름과 namespace 범위 해석"},
        {
            "type": "tool_result",
            "detail": json.dumps({"namespace": namespace or "all-accessible-namespaces", "scope": scope, "targetName": target or "missing"}, ensure_ascii=False, indent=2),
            "id": "req-direct-pod-count-scope",
            "name": "pod_count_scope_resolve",
            "result": query,
            "status": "success" if target else "skipped",
            "summary": f"대상 `{target}`, {scope}" if target else f"대상 이름 미확인, {scope}",
        },
    ]


def lookup_events(*, pods_payload: Mapping[str, Any] | None = DIRECT_PODS) -> list[Mapping[str, Any]]:
    pods_count = len((pods_payload or {}).get("items", []))
    return [
        {"type": "tool_call", "id": "req-direct-pod-count-deployments", "name": "pod_count_deployment_lookup", "summary": "Deployment 목록 조회: `/apis/apps/v1/namespaces/team-a/deployments`"},
        {
            "type": "tool_result",
            "detail": json.dumps({"matchedDeployments": 1, "path": "/apis/apps/v1/namespaces/team-a/deployments", "receivedItems": 1, "targetName": "web"}, ensure_ascii=False, indent=2),
            "id": "req-direct-pod-count-deployments",
            "name": "pod_count_deployment_lookup",
            "result": {"matchedDeployments": 1, "path": "/apis/apps/v1/namespaces/team-a/deployments"},
            "status": "success",
            "summary": "Deployment `web` 후보 1건 확인",
        },
        {"type": "tool_call", "id": "req-direct-pod-count-pods", "name": "pod_count_pod_lookup", "summary": "Pod 목록 조회: `/api/v1/namespaces/team-a/pods`"},
        {
            "type": "tool_result",
            "detail": json.dumps({"path": "/api/v1/namespaces/team-a/pods", "receivedItems": pods_count, "targetName": "web"}, ensure_ascii=False, indent=2),
            "id": "req-direct-pod-count-pods",
            "name": "pod_count_pod_lookup",
            "result": {"path": "/api/v1/namespaces/team-a/pods", "receivedItems": pods_count},
            "status": "success" if pods_payload else "skipped",
            "summary": f"Pod 목록 {pods_count}건 수신" if pods_payload else "Pod 목록을 받지 못함",
        },
    ]


def test_direct_found_stream_has_exact_golden_sequence_and_evidence_args() -> None:
    FakeAsyncClient.calls.clear()
    evidence_calls: list[dict[str, Any]] = []
    query = {"namespace": "team-a", "targetName": "web"}
    events = asyncio.run(collect_direct_events(query, direct_dependencies(evidence_calls=evidence_calls)))
    match_events = [
        {"type": "tool_call", "id": "req-direct-pod-count-match", "name": "pod_count_selector_match", "summary": "Deployment selector와 Pod label/name 매칭"},
        {
            "type": "tool_result",
            "detail": json.dumps(DIRECT_FOUND_RESULT, ensure_ascii=False, indent=2),
            "id": "req-direct-pod-count-match",
            "name": "pod_count_selector_match",
            "result": {"matchedPods": 1, "matchStrategy": "deployment_selector", "status": "found"},
            "status": "success",
            "summary": "`deployment_selector` 방식으로 Pod 1개 매칭",
        },
    ]
    assert [decode_payload(event.payload) for event in events] == scope_events(query) + lookup_events() + match_events + direct_tail(DIRECT_FOUND_RESULT)
    assert evidence_calls == [{"event": direct_tail(DIRECT_FOUND_RESULT)[1], "incident_id": "inc-direct", "run_id": "run-direct", "source_type": "gateway-direct-evidence", "subject": {"username": "dev-user"}}]
    assert FakeAsyncClient.calls == [{"verify": "/ca.crt", "timeout": {"timeout": 20.0, "connect": 5.0}}]


def test_direct_url_unavailable_has_exact_golden_sequence() -> None:
    FakeAsyncClient.calls.clear()
    query = {"namespace": "team-a", "targetName": "web"}
    result = {"namespace": "team-a", "reason": "OPENSHIFT_API_URL is not configured", "status": "unavailable", "targetName": "web"}
    events = asyncio.run(collect_direct_events(query, direct_dependencies(api_url="")))
    assert [decode_payload(event.payload) for event in events] == scope_events(query) + direct_tail(result)
    assert FakeAsyncClient.calls == []


def test_direct_missing_target_has_exact_golden_sequence() -> None:
    FakeAsyncClient.calls.clear()
    query = {"namespace": "team-a", "targetName": ""}
    result = {"namespace": "team-a", "reason": "target_name_missing", "status": "missing_target"}
    events = asyncio.run(collect_direct_events(query, direct_dependencies()))
    assert [decode_payload(event.payload) for event in events] == scope_events(query) + direct_tail(result)
    assert FakeAsyncClient.calls == []


def test_direct_pods_unavailable_has_exact_golden_sequence_without_match() -> None:
    async def fetch(_client, path: str, _authorization: str):
        return DIRECT_DEPLOYMENTS if "deployments" in path else None

    query = {"namespace": "team-a", "targetName": "web"}
    result = {"namespace": "team-a", "reason": "Kubernetes API pod list was not returned for /api/v1/namespaces/team-a/pods", "status": "unavailable", "targetName": "web"}
    events = asyncio.run(collect_direct_events(query, direct_dependencies(fetch_ocp_json=fetch)))
    decoded = [decode_payload(event.payload) for event in events]
    assert decoded == scope_events(query) + lookup_events(pods_payload=None) + direct_tail(result)
    assert not any(isinstance(event, Mapping) and event.get("name") == "pod_count_selector_match" for event in decoded)


def test_direct_deployment_and_pod_tool_calls_precede_each_blocking_await() -> None:
    deployment_started, release_deployment = asyncio.Event(), asyncio.Event()
    pod_started, release_pod = asyncio.Event(), asyncio.Event()

    async def blocking_fetch(_client, path: str, _authorization: str):
        started, release, payload = (
            (deployment_started, release_deployment, DIRECT_DEPLOYMENTS)
            if "deployments" in path
            else (pod_started, release_pod, DIRECT_PODS)
        )
        started.set()
        await release.wait()
        return payload

    async def run() -> None:
        stream = stream_direct_pod_count(
            authorization="Bearer token",
            dependencies=direct_dependencies(fetch_ocp_json=blocking_fetch),
            incident_id="inc-direct",
            pod_count_query={"namespace": "team-a", "targetName": "web"},
            request_id="req-direct",
            run_id="run-direct",
            subject=None,
        )
        assert decode_payload((await anext(stream)).payload)["name"] == "pod_count_scope_resolve"
        assert decode_payload((await anext(stream)).payload)["name"] == "pod_count_scope_resolve"
        assert decode_payload((await anext(stream)).payload)["name"] == "pod_count_deployment_lookup"
        assert not deployment_started.is_set()
        deployment_result = asyncio.create_task(anext(stream))
        await deployment_started.wait()
        assert not deployment_result.done()
        release_deployment.set()
        assert decode_payload((await deployment_result).payload)["type"] == "tool_result"
        assert decode_payload((await anext(stream)).payload)["name"] == "pod_count_pod_lookup"
        assert not pod_started.is_set()
        pod_result = asyncio.create_task(anext(stream))
        await pod_started.wait()
        assert not pod_result.done()
        release_pod.set()
        assert decode_payload((await pod_result).payload)["type"] == "tool_result"
        await stream.aclose()

    asyncio.run(run())


def test_direct_rca_event_carries_context_update_before_payload_yield() -> None:
    events = asyncio.run(collect_direct_events({"namespace": "team-a", "targetName": "web"}))
    rca_event = next(event for event in events if decode_payload(event.payload)["type"] == "rca_context")
    assert rca_event.latest_rca_context == {"metadata": {"phase": "post_answer", "digest": "direct-latest"}}
    assert decode_payload(rca_event.payload)["context"] == rca_event.latest_rca_context


def test_main_builds_fresh_direct_dependencies_and_updates_rca_before_next_yield(monkeypatch) -> None:
    import komsco_ai_gateway.main as gateway_main

    captured: list[DirectPodCountFlowDependencies] = []
    update_observed: list[bool] = []

    async def fake_stream(**kwargs: Any):
        deps = kwargs["dependencies"]
        captured.append(deps)
        latest_context = {"sourceUrl": deps.openshift_api_url}
        yield TopPodNamespaceStreamEvent(
            sse({"type": "rca_context", "context": latest_context}),
            latest_rca_context=latest_context,
        )
        update_observed.append(gateway_main.LAST_RCA_CONTEXT is latest_context)
        yield TopPodNamespaceStreamEvent(sse("[DONE]"))

    async def fake_subject_review(_authorization: str) -> dict[str, Any]:
        return {"username": "dev-user", "uid": "uid-dev", "groups": []}

    async def fake_access_review(_authorization: str) -> dict[str, Any]:
        return {"allowed": True, "enabled": True, "required": True}

    async def fetch_one(*_args: Any, **_kwargs: Any):
        return {"items": []}

    async def fetch_two(*_args: Any, **_kwargs: Any):
        return {"items": []}

    monkeypatch.setattr(gateway_main, "stream_direct_pod_count", fake_stream)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_access_review)
    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://first.test:6443")
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fetch_one)

    async def request_once(client: httpx.AsyncClient) -> None:
        response = await client.post(
            "/v1/chat/stream",
            headers={"Authorization": "Bearer token"},
            json={"message": "web pod count 알려줘"},
        )
        assert response.status_code == 200

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            await request_once(client)
            monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://second.test:6443")
            monkeypatch.setattr(gateway_main, "fetch_ocp_json", fetch_two)
            await request_once(client)

    asyncio.run(run())
    assert [deps.openshift_api_url for deps in captured] == ["https://first.test:6443", "https://second.test:6443"]
    assert captured[0].fetch_ocp_json is fetch_one
    assert captured[1].fetch_ocp_json is fetch_two
    assert captured[1].path_segment is gateway_main.path_segment
    assert captured[1].resource_items is gateway_main.resource_items
    assert captured[1].metadata_name is gateway_main.metadata_name
    assert captured[1].metadata_namespace is gateway_main.metadata_namespace
    assert captured[1].build_investigation is gateway_main.build_pod_count_investigation
    assert captured[1].build_response is gateway_main.pod_count_investigation_response
    assert captured[1].redact_sensitive is gateway_main.redact_sensitive
    assert captured[1].build_evidence_events is gateway_main.build_evidence_reference_events
    assert update_observed == [True, True]
    assert gateway_main.LAST_RCA_CONTEXT == {"sourceUrl": "https://second.test:6443"}
