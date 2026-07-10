from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_restart_evidence_flow import (
    RestartEvidenceFlowDependencies,
    stream_restart_evidence,
)


SUBJECT = {"username": "operator", "uid": "uid-operator"}
OFFICIAL_EVENT = {
    "type": "tool_result",
    "name": "official_restart_event",
    "evidenceType": "event",
    "detail": "official detail",
    "status": "success",
}
CRASH_EVENTS = [
    {
        "type": "tool_result",
        "name": "crash_event",
        "evidenceType": "event",
        "detail": "crash detail",
        "status": "success",
    },
    {
        "type": "tool_result",
        "name": "crash_snapshot",
        "evidenceType": "snapshot",
        "detail": "snapshot detail",
        "status": "success",
    },
]


def _dependencies(
    *,
    crashloop_target: dict[str, Any] | None,
    official_namespace: str,
    official_error: Exception | None = None,
    crashloop_error: Exception | None = None,
    calls: dict[str, list[Any]],
    collect_started: asyncio.Event | None = None,
    collect_release: asyncio.Event | None = None,
) -> RestartEvidenceFlowDependencies:
    async def collect_official(*args: Any):
        calls["official"].append(args)
        if collect_started:
            collect_started.set()
        if collect_release:
            await collect_release.wait()
        if official_error:
            raise official_error
        return [dict(OFFICIAL_EVENT)]

    def official_fallback(**kwargs: Any):
        calls["fallback"].append(kwargs)
        return [
            {
                "type": "tool_result",
                "name": "official_restart_fallback",
                "evidenceType": "event",
                "detail": kwargs["detail"],
                "status": "error",
            }
        ]

    async def collect_crashloop(*args: Any):
        calls["crashloop"].append(args)
        if collect_started:
            collect_started.set()
        if collect_release:
            await collect_release.wait()
        if crashloop_error:
            raise crashloop_error
        return [dict(item) for item in CRASH_EVENTS]

    def references(**kwargs: Any):
        calls["refs"].append(kwargs)
        return [
            {
                "type": "evidence_ref",
                "evidenceType": kwargs["event"]["evidenceType"],
            }
        ]

    return RestartEvidenceFlowDependencies(
        crashloop_target=lambda request: calls["target"].append(request) or crashloop_target,
        official_namespace=lambda plan: calls["namespace"].append(plan) or official_namespace,
        collect_official=collect_official,
        official_fallback=official_fallback,
        collect_crashloop=collect_crashloop,
        append_gateway_evidence=lambda current, detail: f"{current}|{detail}",
        safe_exception_text=lambda exc: f"safe:{exc}",
        build_evidence_reference_events=references,
        sse=lambda value: json.dumps(value, ensure_ascii=False),
    )


async def _collect(dependencies: RestartEvidenceFlowDependencies):
    stream_events = [
        event
        async for event in stream_restart_evidence(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            request=SimpleNamespace(message="restart evidence"),
            request_id="req-1",
            run_id="run-1",
            runtime_tool_plan={"kind": "tool-plan"},
            subject=SUBJECT,
        )
    ]
    return stream_events, [json.loads(event.payload) for event in stream_events]


def _calls() -> dict[str, list[Any]]:
    return {
        name: []
        for name in (
            "official",
            "fallback",
            "crashloop",
            "refs",
            "target",
            "namespace",
        )
    }


def test_official_restart_evidence_contract() -> None:
    calls = _calls()
    dependencies = _dependencies(
        crashloop_target=None,
        official_namespace="team-a",
        calls=calls,
    )
    stream_events, events = asyncio.run(_collect(dependencies))

    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_result",
        "evidence_ref",
    ]
    assert events[0]["name"] == "official_namespace_restart_evidence"
    assert calls["official"] == [("Bearer token", "team-a", "req-1")]
    assert calls["crashloop"] == []
    assert [event.gateway_evidence for event in stream_events if event.gateway_evidence] == [
        "base|official detail"
    ]


def test_official_failure_uses_existing_fallback_contract() -> None:
    calls = _calls()
    dependencies = _dependencies(
        crashloop_target=None,
        official_namespace="team-a",
        official_error=RuntimeError("cluster down"),
        calls=calls,
    )
    _, events = asyncio.run(_collect(dependencies))

    assert calls["fallback"] == [
        {
            "namespace": "team-a",
            "request_id": "req-1",
            "reason": "safe:cluster down",
            "detail": "safe:cluster down",
        }
    ]
    assert events[1]["name"] == "official_restart_fallback"


def test_crashloop_target_takes_precedence_and_accumulates_evidence() -> None:
    calls = _calls()
    target = {"namespace": "team-a", "name": "broken-pod"}
    dependencies = _dependencies(
        crashloop_target=target,
        official_namespace="team-a",
        calls=calls,
    )
    stream_events, events = asyncio.run(_collect(dependencies))

    assert events[0]["name"] == "crashloop_demo_evidence"
    assert calls["official"] == []
    assert calls["crashloop"] == [("Bearer token", target, "req-1")]
    assert [event.gateway_evidence for event in stream_events if event.gateway_evidence] == [
        "base|crash detail",
        "base|crash detail|snapshot detail",
    ]
    assert [item["source_type"] for item in calls["refs"]] == [
        "gateway-preflight-evidence",
        "gateway-preflight-evidence",
    ]
    assert all(item["subject"] == SUBJECT for item in calls["refs"])


def test_crashloop_failure_emits_three_typed_error_results() -> None:
    calls = _calls()
    dependencies = _dependencies(
        crashloop_target={"name": "broken-pod"},
        official_namespace="",
        crashloop_error=RuntimeError("api failed"),
        calls=calls,
    )
    _, events = asyncio.run(_collect(dependencies))

    results = [event for event in events if event["type"] == "tool_result"]
    assert [event["evidenceType"] for event in results] == [
        "event",
        "pod_log",
        "snapshot",
    ]
    assert all(event["status"] == "error" for event in results)
    assert all(event["missingReason"] == "safe:api failed" for event in results)


def test_no_restart_target_emits_nothing() -> None:
    calls = _calls()
    dependencies = _dependencies(
        crashloop_target=None,
        official_namespace="",
        calls=calls,
    )
    stream_events, events = asyncio.run(_collect(dependencies))
    assert stream_events == []
    assert events == []


@pytest.mark.parametrize("official", [True, False])
def test_tool_call_is_emitted_before_collector_wait(official: bool) -> None:
    async def run() -> None:
        calls = _calls()
        started = asyncio.Event()
        release = asyncio.Event()
        dependencies = _dependencies(
            crashloop_target=None if official else {"name": "broken-pod"},
            official_namespace="team-a" if official else "",
            calls=calls,
            collect_started=started,
            collect_release=release,
        )
        flow = stream_restart_evidence(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            request=SimpleNamespace(message="restart"),
            request_id="req-1",
            run_id="run-1",
            runtime_tool_plan={},
            subject=SUBJECT,
        )
        assert json.loads((await anext(flow)).payload)["type"] == "tool_call"
        pending = asyncio.create_task(anext(flow))
        await started.wait()
        assert not pending.done()
        release.set()
        assert json.loads((await pending).payload)["type"] == "tool_result"
        await flow.aclose()

    asyncio.run(run())


def test_main_factory_uses_current_callbacks(monkeypatch) -> None:
    async def collect(*_args: Any, **_kwargs: Any):
        return []

    monkeypatch.setattr(
        gateway_main,
        "collect_crashloop_demo_evidence_events",
        collect,
    )
    dependencies = gateway_main.restart_evidence_flow_dependencies()
    assert dependencies.collect_crashloop is collect


def test_restart_evidence_module_does_not_import_main() -> None:
    module_path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_restart_evidence_flow.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(module == "main" or module.endswith(".main") for module in imported)
