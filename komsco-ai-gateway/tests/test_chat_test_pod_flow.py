from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_test_pod_flow import (
    TestPodFlowDependencies as PodFlowDependencies,
    stream_test_pod_create,
)


CREATE_REQUEST = {"namespace": "team-a", "count": 2}


def _dependencies(*, ready, ok, action_mode, language="ko", calls):
    async def collect(authorization, request):
        calls["collect"].append((authorization, request))
        return {"ok": ok, "status": "ready" if ok else "missing", "token": "secret"}

    def remember(candidate):
        calls["remember"].append(candidate)

    return PodFlowDependencies(
        execution_mode=lambda request: calls["mode"].append(request) or "execute",
        answer_language=lambda request: calls["language"].append(request) or language,
        parse_request=lambda message: calls["parse"].append(message) or CREATE_REQUEST,
        request_is_ready=lambda request: calls["ready"].append(request) or ready,
        collect_preflight=collect,
        disabled_answer=lambda request, lang: f"disabled:{lang}",
        action_capable_mode=lambda mode: calls["action_mode"].append(mode) or action_mode,
        candidate_from_preflight=lambda request, preflight, run_id, incident_id: {
            "id": "candidate-1",
            "request": request,
            "runId": run_id,
            "incidentId": incident_id,
        },
        remember_candidate=remember,
        answer=lambda request, preflight, mode, lang: f"answer:{preflight['status']}:{mode}:{lang}",
        tool_plan=lambda request, mode, **kwargs: {
            "task_type": "test_pod_create",
            "mode": mode,
            **kwargs,
        },
        redact_sensitive=lambda value: {
            key: "[REDACTED]" if key == "token" else item
            for key, item in value.items()
        },
        sse=lambda value: json.dumps(value, ensure_ascii=False),
    )


async def _collect(dependencies):
    stream_events = [
        event
        async for event in stream_test_pod_create(
            authorization="Bearer token",
            dependencies=dependencies,
            incident_id="inc-1",
            request=SimpleNamespace(message="테스트 Pod 2개 생성"),
            request_id="req-1",
            run_id="run-1",
        )
    ]
    return stream_events, [json.loads(event.payload) for event in stream_events]


def _calls():
    return {name: [] for name in ("collect", "remember", "mode", "language", "parse", "ready", "action_mode")}


def test_disabled_guard_contract() -> None:
    calls = _calls()
    stream_events, events = asyncio.run(
        _collect(_dependencies(ready=False, ok=False, action_mode=False, calls=calls))
    )
    assert [event if isinstance(event, str) else event["type"] for event in events] == [
        "tool_result", "text", "run_status", "[DONE]"
    ]
    assert events[0]["name"] == "test_pod_create_guard"
    assert events[0]["result"]["token"] == "[REDACTED]"
    assert events[1]["answerContract"] == "test-pod-create-guard-v1"
    assert [event.answer_chunk for event in stream_events if event.answer_chunk] == ["disabled:ko"]
    assert calls["remember"] == []


@pytest.mark.parametrize(
    ("ok", "action_mode", "validation", "remembered"),
    [
        (True, True, "action_candidate_ready", 1),
        (True, False, "read_only_preflight_collected", 0),
        (False, True, "missing", 0),
    ],
)
def test_preflight_plan_and_candidate_contract(ok, action_mode, validation, remembered) -> None:
    calls = _calls()
    stream_events, events = asyncio.run(
        _collect(_dependencies(ready=True, ok=ok, action_mode=action_mode, calls=calls))
    )
    assert [event if isinstance(event, str) else event["type"] for event in events] == [
        "run_status", "tool_call", "tool_result", "tool_plan", "text", "run_status", "[DONE]"
    ]
    assert events[1]["name"] == "oc_test_pod_create_preflight"
    assert events[2]["result"]["token"] == "[REDACTED]"
    assert events[3]["plan"]["validation"]["status"] == validation
    assert len(calls["remember"]) == remembered
    assert [event.answer_chunk for event in stream_events if event.answer_chunk] == [
        f"answer:{'ready' if ok else 'missing'}:execute:ko"
    ]


def test_main_factory_uses_current_collector(monkeypatch) -> None:
    async def collect(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(gateway_main, "collect_test_pod_create_preflight", collect)
    assert gateway_main.test_pod_flow_dependencies().collect_preflight is collect


def test_test_pod_flow_module_does_not_import_main() -> None:
    path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_test_pod_flow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(module == "main" or module.endswith(".main") for module in imported)
