from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_attachment_cronjob_flow import (
    AttachmentCronjobFlowDependencies,
    stream_attachment_and_cronjob_preflight,
)


SUBJECT = {"username": "operator", "uid": "uid-operator"}


def _sse(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _dependencies(
    *,
    image_analysis: str | None,
    collect_cronjob: bool,
    cronjob_detail: str = "cronjob evidence",
    cronjob_error: Exception | None = None,
    calls: dict[str, list[Any]],
    vision_started: asyncio.Event | None = None,
    vision_release: asyncio.Event | None = None,
) -> AttachmentCronjobFlowDependencies:
    async def analyze(attachments: Any, message: str) -> str | None:
        calls["vision"].append((attachments, message))
        if vision_started is not None:
            vision_started.set()
        if vision_release is not None:
            await vision_release.wait()
        return image_analysis

    def should_collect(message: str, analysis: str | None) -> bool:
        calls["should"].append((message, analysis))
        return collect_cronjob

    async def collect(authorization: str, context: str) -> str:
        calls["cronjob"].append((authorization, context))
        if cronjob_error is not None:
            raise cronjob_error
        return cronjob_detail

    def build_refs(**kwargs: Any) -> list[dict[str, Any]]:
        calls["refs"].append(kwargs)
        return [{"type": "evidence_ref", "evidenceType": "cronjob"}]

    return AttachmentCronjobFlowDependencies(
        analyze_image_attachments=analyze,
        should_collect_cronjob_activity_evidence=should_collect,
        collect_cronjob_activity_evidence=collect,
        append_gateway_evidence=lambda current, new: f"{current}|{new}",
        safe_exception_text=lambda exc: f"safe:{exc}",
        evidence_summary=lambda label, status: f"{label}:{status}",
        build_evidence_reference_events=build_refs,
        sse=_sse,
    )


async def _collect(
    dependencies: AttachmentCronjobFlowDependencies,
    *,
    attachments: list[Any],
    message: str = "CronJob 상태 확인",
):
    request = SimpleNamespace(message=message, attachments=attachments)
    stream_events = [
        event
        async for event in stream_attachment_and_cronjob_preflight(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            request=request,
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )
    ]
    return stream_events, [json.loads(event.payload) for event in stream_events]


def test_flow_is_empty_without_attachments_or_cronjob_intent() -> None:
    calls = {name: [] for name in ("vision", "should", "cronjob", "refs")}
    dependencies = _dependencies(
        image_analysis=None,
        collect_cronjob=False,
        calls=calls,
    )

    stream_events, events = asyncio.run(_collect(dependencies, attachments=[]))

    assert stream_events == []
    assert events == []
    assert calls["vision"] == []
    assert calls["should"] == [("CronJob 상태 확인", None)]
    assert calls["cronjob"] == []


@pytest.mark.parametrize(
    ("analysis", "vision_result"),
    [("screen analysis", "ok"), (None, "not_configured")],
)
def test_attachment_events_preserve_order_and_analysis_marker(
    analysis: str | None,
    vision_result: str,
) -> None:
    calls = {name: [] for name in ("vision", "should", "cronjob", "refs")}
    attachment = SimpleNamespace(size=123)
    dependencies = _dependencies(
        image_analysis=analysis,
        collect_cronjob=False,
        calls=calls,
    )

    stream_events, events = asyncio.run(
        _collect(dependencies, attachments=[attachment])
    )

    assert [(event["type"], event["name"]) for event in events] == [
        ("tool_call", "attachment_check"),
        ("tool_result", "attachment_check"),
        ("tool_call", "vision_analysis"),
        ("tool_result", "vision_analysis"),
    ]
    assert events[1]["result"] == {
        "images": 1,
        "totalBytes": 123,
        "forwardedToLightspeed": False,
    }
    assert events[3]["result"] == vision_result
    marked = [event for event in stream_events if event.image_analysis_updated]
    assert len(marked) == 1
    assert marked[0].image_analysis == analysis
    assert calls["should"] == [("CronJob 상태 확인", analysis)]


@pytest.mark.parametrize(
    ("detail", "error", "status", "missing_reason"),
    [
        ("cronjob evidence", None, "success", ""),
        (
            "CronJob activity evidence unavailable: disabled",
            None,
            "skipped",
            "CronJob activity evidence unavailable: disabled",
        ),
        ("unused", RuntimeError("cluster down"), "error", "safe:cluster down"),
    ],
)
def test_cronjob_evidence_status_and_reference_contract(
    detail: str,
    error: Exception | None,
    status: str,
    missing_reason: str,
) -> None:
    calls = {name: [] for name in ("vision", "should", "cronjob", "refs")}
    dependencies = _dependencies(
        image_analysis="screen analysis",
        collect_cronjob=True,
        cronjob_detail=detail,
        cronjob_error=error,
        calls=calls,
    )

    stream_events, events = asyncio.run(
        _collect(dependencies, attachments=[SimpleNamespace(size=10)])
    )

    assert [(event["type"], event.get("name")) for event in events[-3:]] == [
        ("tool_call", "cronjob_activity_evidence"),
        ("tool_result", "cronjob_activity_evidence"),
        ("evidence_ref", None),
    ]
    result = events[-2]
    assert result["status"] == status
    assert result["missingReason"] == missing_reason
    assert result["evidenceType"] == "cronjob"
    assert calls["cronjob"] == [
        ("Bearer token", "CronJob 상태 확인\nscreen analysis")
    ]
    assert calls["refs"][0]["event"] == result
    assert calls["refs"][0]["subject"] == SUBJECT
    assert calls["refs"][0]["source_type"] == "gateway-preflight-evidence"
    updated = [event.gateway_evidence for event in stream_events if event.gateway_evidence]
    expected_detail = (
        "CronJob activity evidence unavailable: safe:cluster down"
        if error
        else detail
    )
    assert updated == [f"base|{expected_detail}"]


def test_attachment_tool_events_are_emitted_before_vision_wait() -> None:
    async def run() -> None:
        calls = {name: [] for name in ("vision", "should", "cronjob", "refs")}
        started = asyncio.Event()
        release = asyncio.Event()
        dependencies = _dependencies(
            image_analysis="screen analysis",
            collect_cronjob=False,
            calls=calls,
            vision_started=started,
            vision_release=release,
        )
        flow = stream_attachment_and_cronjob_preflight(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            request=SimpleNamespace(
                message="화면 확인",
                attachments=[SimpleNamespace(size=10)],
            ),
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )

        assert json.loads((await anext(flow)).payload)["name"] == "attachment_check"
        assert json.loads((await anext(flow)).payload)["name"] == "attachment_check"
        assert json.loads((await anext(flow)).payload)["name"] == "vision_analysis"
        assert not started.is_set()
        pending = asyncio.create_task(anext(flow))
        await started.wait()
        assert not pending.done()
        release.set()
        assert json.loads((await pending).payload)["name"] == "vision_analysis"
        await flow.aclose()

    asyncio.run(run())


def test_reference_failure_reenters_original_error_event_path() -> None:
    calls = {name: [] for name in ("vision", "should", "cronjob", "refs")}
    dependencies = _dependencies(
        image_analysis=None,
        collect_cronjob=True,
        cronjob_detail="cronjob evidence",
        calls=calls,
    )
    reference_calls = 0

    def flaky_references(**_kwargs: Any) -> list[dict[str, Any]]:
        nonlocal reference_calls
        reference_calls += 1
        if reference_calls == 1:
            raise RuntimeError("reference write failed")
        return [{"type": "evidence_ref", "evidenceType": "cronjob"}]

    dependencies = replace(
        dependencies,
        build_evidence_reference_events=flaky_references,
    )
    stream_events, events = asyncio.run(_collect(dependencies, attachments=[]))

    results = [event for event in events if event.get("type") == "tool_result"]
    assert [event["status"] for event in results] == ["success", "error"]
    assert results[1]["missingReason"] == "safe:reference write failed"
    assert events[-1]["type"] == "evidence_ref"
    updated = [event.gateway_evidence for event in stream_events if event.gateway_evidence]
    assert updated == [
        "base|cronjob evidence",
        "base|cronjob evidence|CronJob activity evidence unavailable: safe:reference write failed",
    ]


def test_main_factory_uses_current_callbacks(monkeypatch) -> None:
    async def analyze(*_args: Any, **_kwargs: Any) -> str:
        return "analysis"

    monkeypatch.setattr(gateway_main, "analyze_image_attachments", analyze)
    dependencies = gateway_main.attachment_cronjob_flow_dependencies()
    assert dependencies.analyze_image_attachments is analyze


def test_attachment_cronjob_flow_module_does_not_import_main() -> None:
    module_path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_attachment_cronjob_flow.py"
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
