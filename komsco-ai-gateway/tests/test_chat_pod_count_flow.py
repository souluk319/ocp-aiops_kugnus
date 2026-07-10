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
    TopPodNamespaceFlowDependencies,
    TopPodNamespaceStreamEvent,
    stream_top_pod_namespace_count,
)
from komsco_ai_gateway.pod_counting import (
    build_top_pod_namespace_count_result,
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
