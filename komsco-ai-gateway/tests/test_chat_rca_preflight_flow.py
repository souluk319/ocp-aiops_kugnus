from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from typing import Any

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_rca_preflight_flow import (
    RcaPreflightCollector,
    RcaPreflightFlowDependencies,
    stream_rca_preflight_evidence,
)


SUBJECT = {"username": "operator", "uid": "uid-operator"}


def _dependencies(*, failing: str = "", calls: dict[str, list[Any]], started=None, release=None):
    def collector(name: str, evidence_type: str):
        async def collect(authorization: str):
            calls["collect"].append((name, authorization))
            if started is not None:
                started.set()
            if release is not None:
                await release.wait()
            if name == failing:
                raise RuntimeError(f"{name} failed")
            return {
                "detail": f"{name} detail",
                "evidenceType": evidence_type,
                "missingReason": "",
                "sourcePath": f"/{name}",
                "status": "success",
                "summary": f"{name} complete",
            }

        return collect

    specs = tuple(
        RcaPreflightCollector(
            f"{name}-suffix",
            f"{name}_evidence",
            f"{name} summary",
            evidence_type,
            collector(name, evidence_type),
        )
        for name, evidence_type in (
            ("node", "node"),
            ("alert", "alert"),
            ("metric", "metric"),
        )
    )

    def refs(**kwargs: Any):
        calls["refs"].append(kwargs)
        return [{"type": "evidence_ref", "evidenceType": kwargs["event"]["evidenceType"]}]

    return RcaPreflightFlowDependencies(
        collectors=specs,
        append_gateway_evidence=lambda current, detail: f"{current}|{detail}",
        safe_exception_text=lambda exc: f"safe:{exc}",
        build_evidence_reference_events=refs,
        sse=lambda value: json.dumps(value, ensure_ascii=False),
    )


async def _collect(dependencies):
    stream_events = [
        event
        async for event in stream_rca_preflight_evidence(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )
    ]
    return stream_events, [json.loads(event.payload) for event in stream_events]


def test_rca_preflight_preserves_collector_order_and_accumulated_evidence() -> None:
    calls = {"collect": [], "refs": []}
    stream_events, events = asyncio.run(_collect(_dependencies(calls=calls)))

    assert [event["type"] for event in events] == [
        "tool_call", "tool_result", "evidence_ref",
        "tool_call", "tool_result", "evidence_ref",
        "tool_call", "tool_result", "evidence_ref",
    ]
    assert calls["collect"] == [
        ("node", "Bearer token"),
        ("alert", "Bearer token"),
        ("metric", "Bearer token"),
    ]
    assert [event.gateway_evidence for event in stream_events if event.gateway_evidence] == [
        "base|node detail",
        "base|node detail|alert detail",
        "base|node detail|alert detail|metric detail",
    ]
    assert all(item["subject"] == SUBJECT for item in calls["refs"])
    assert all(item["source_type"] == "gateway-preflight-evidence" for item in calls["refs"])


def test_rca_preflight_maps_collector_failure_and_continues() -> None:
    calls = {"collect": [], "refs": []}
    _, events = asyncio.run(_collect(_dependencies(failing="alert", calls=calls)))
    results = [event for event in events if event["type"] == "tool_result"]

    assert [event["status"] for event in results] == ["success", "error", "success"]
    assert results[1] == {
        "type": "tool_result",
        "detail": "alert summary unavailable: safe:alert failed",
        "evidenceType": "alert",
        "id": "req-1-alert-suffix",
        "missingReason": "safe:alert failed",
        "name": "alert_evidence",
        "status": "error",
        "summary": "alert summary 실패",
    }


def test_tool_call_is_emitted_before_each_collector_wait() -> None:
    async def run() -> None:
        calls = {"collect": [], "refs": []}
        started = asyncio.Event()
        release = asyncio.Event()
        dependencies = _dependencies(calls=calls, started=started, release=release)
        flow = stream_rca_preflight_evidence(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            request_id="req-1",
            run_id="run-1",
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


def test_main_factory_uses_current_collectors(monkeypatch) -> None:
    async def collect(_authorization: str):
        return {}

    monkeypatch.setattr(gateway_main, "collect_node_status_rca_evidence", collect)
    dependencies = gateway_main.rca_preflight_flow_dependencies()
    assert dependencies.collectors[0].collect is collect


def test_rca_preflight_module_does_not_import_main() -> None:
    path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_rca_preflight_flow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    assert not any(module == "main" or module.endswith(".main") for module in imported)
