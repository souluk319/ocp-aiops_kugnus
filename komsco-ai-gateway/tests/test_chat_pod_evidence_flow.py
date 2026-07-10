from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_pod_evidence_flow import (
    PodEvidenceFlowDependencies,
    stream_pod_status_evidence,
)


SUBJECT = {"username": "operator", "uid": "uid-operator"}


def _sse(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _dependencies(
    *,
    detail: str = "pod evidence",
    error: Exception | None = None,
    pod_list_request: bool = False,
    page_is_pod: bool = False,
    calls: dict[str, list[Any]],
    collect_started: asyncio.Event | None = None,
    collect_release: asyncio.Event | None = None,
) -> PodEvidenceFlowDependencies:
    async def collect(authorization: str, **kwargs: Any) -> str:
        calls["collect"].append((authorization, kwargs))
        if collect_started is not None:
            collect_started.set()
        if collect_release is not None:
            await collect_release.wait()
        if error is not None:
            raise error
        return detail

    def build_refs(**kwargs: Any) -> list[dict[str, Any]]:
        calls["refs"].append(kwargs)
        return [
            {
                "type": "evidence_ref",
                "evidenceType": kwargs["event"]["evidenceType"],
            }
        ]

    return PodEvidenceFlowDependencies(
        is_pod_list_request=lambda message: calls["messages"].append(message) or pod_list_request,
        page_context_is_pod_workload=lambda request: calls["pages"].append(request) or page_is_pod,
        pod_list_namespace=lambda request: calls["namespaces"].append(request) or "team-a",
        collect_pod_status_evidence=collect,
        append_gateway_evidence=lambda current, new: f"{current}|{new}",
        safe_exception_text=lambda exc: f"safe:{exc}",
        evidence_summary=lambda label, status: f"{label}:{status}",
        build_evidence_reference_events=build_refs,
        sse=_sse,
    )


async def _collect(
    dependencies: PodEvidenceFlowDependencies,
    request: Any | None = None,
):
    stream_events = [
        event
        async for event in stream_pod_status_evidence(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            request=request or SimpleNamespace(message="pod status"),
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )
    ]
    return stream_events, [json.loads(event.payload) for event in stream_events]


@pytest.mark.parametrize(
    ("case", "detail", "error", "expected_status", "expected_missing"),
    [
        ("success", "pod evidence", None, "success", ""),
        (
            "skipped",
            "Pod status evidence unavailable: disabled",
            None,
            "skipped",
            "Pod status evidence unavailable: disabled",
        ),
        ("error", "unused", RuntimeError("cluster down"), "error", "safe:cluster down"),
    ],
)
def test_pod_evidence_flow_preserves_event_order_and_status(
    case: str,
    detail: str,
    error: Exception | None,
    expected_status: str,
    expected_missing: str,
) -> None:
    calls = {name: [] for name in ("collect", "refs", "messages", "pages", "namespaces")}
    dependencies = _dependencies(detail=detail, error=error, calls=calls)

    stream_events, events = asyncio.run(_collect(dependencies))

    assert [event["type"] for event in events] == [
        "tool_call",
        "tool_result",
        "evidence_ref",
        "tool_result",
        "evidence_ref",
    ]
    pod_event, snapshot_event = events[1], events[3]
    assert pod_event["name"] == "pod_status_evidence"
    assert pod_event["status"] == expected_status
    assert pod_event["missingReason"] == expected_missing
    assert snapshot_event["name"] == "pod_snapshot_evidence"
    assert snapshot_event["status"] == expected_status
    assert snapshot_event["missingReason"] == expected_missing
    assert [event["evidenceType"] for event in (pod_event, snapshot_event)] == [
        "pod_status",
        "snapshot",
    ]
    assert [item["event"] for item in calls["refs"]] == [pod_event, snapshot_event]
    assert all(item["incident_id"] == "inc-1" for item in calls["refs"])
    assert all(item["run_id"] == "run-1" for item in calls["refs"])
    assert all(item["subject"] == SUBJECT for item in calls["refs"])
    assert all(item["source_type"] == "gateway-preflight-evidence" for item in calls["refs"])

    updated = [event.gateway_evidence for event in stream_events if event.gateway_evidence]
    expected_detail = (
        "Pod status evidence unavailable: safe:cluster down"
        if case == "error"
        else detail
    )
    assert updated == [f"base|{expected_detail}"]


@pytest.mark.parametrize(
    (
        "pod_list_request",
        "page_is_pod",
        "include_list",
        "namespace_calls",
        "page_calls",
    ),
    [
        (False, False, False, 0, 1),
        (True, False, True, 1, 0),
        (False, True, True, 1, 1),
    ],
)
def test_pod_evidence_flow_builds_list_scope(
    pod_list_request: bool,
    page_is_pod: bool,
    include_list: bool,
    namespace_calls: int,
    page_calls: int,
) -> None:
    calls = {name: [] for name in ("collect", "refs", "messages", "pages", "namespaces")}
    dependencies = _dependencies(
        pod_list_request=pod_list_request,
        page_is_pod=page_is_pod,
        calls=calls,
    )

    asyncio.run(_collect(dependencies))

    assert calls["collect"] == [
        (
            "Bearer token",
            {
                "include_pod_list": include_list,
                "list_namespace": "team-a" if include_list else "",
            },
        )
    ]
    assert len(calls["namespaces"]) == namespace_calls
    assert len(calls["pages"]) == page_calls


def test_tool_call_is_emitted_before_pod_collection_wait() -> None:
    async def run() -> None:
        calls = {name: [] for name in ("collect", "refs", "messages", "pages", "namespaces")}
        started = asyncio.Event()
        release = asyncio.Event()
        dependencies = _dependencies(
            calls=calls,
            collect_started=started,
            collect_release=release,
        )
        flow = stream_pod_status_evidence(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            request=SimpleNamespace(message="pod status"),
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )

        assert json.loads((await anext(flow)).payload)["type"] == "tool_call"
        assert not started.is_set()
        pending = asyncio.create_task(anext(flow))
        await started.wait()
        assert not pending.done()
        release.set()
        assert json.loads((await pending).payload)["name"] == "pod_status_evidence"
        await flow.aclose()

    asyncio.run(run())


def test_main_factory_uses_current_pod_evidence_callbacks(monkeypatch) -> None:
    async def collect(*_args: Any, **_kwargs: Any) -> str:
        return "evidence"

    monkeypatch.setattr(gateway_main, "collect_pod_status_evidence", collect)
    dependencies = gateway_main.pod_evidence_flow_dependencies()
    assert dependencies.collect_pod_status_evidence is collect


def test_pod_evidence_flow_module_does_not_import_main() -> None:
    module_path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_pod_evidence_flow.py"
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module is not None
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )
    assert not any(module == "main" or module.endswith(".main") for module in imported_modules)
