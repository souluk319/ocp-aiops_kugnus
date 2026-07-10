from __future__ import annotations

import ast
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_natural_action_followup_flow import (
    NaturalActionFollowupFlowDependencies,
    NaturalActionFollowupStreamEvent,
    stream_chat_natural_action_followup,
)


SUBJECT = {"username": "operator", "uid": "uid-operator"}
AUTHORIZATION = "Bearer user-token"
PLAN = {"planId": "plan-1", "status": "planned"}
RCA_CONTEXT = {"phase": "post_answer", "marker": "latest"}


def _sse(event: Any) -> str:
    return json.dumps(event, ensure_ascii=False)


def _redact(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {
        key: "[REDACTED]" if key == "token" else item
        for key, item in value.items()
    }


def _tool_result(
    result: dict[str, Any],
    *,
    status: str,
    summary: str,
) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "detail": json.dumps(_redact(result), ensure_ascii=False, indent=2),
        "id": "req-1-natural-action-followup",
        "name": "natural_action_followup",
        "result": result,
        "status": status,
        "summary": summary,
    }


def _rca_event() -> dict[str, Any]:
    return {"type": "rca_context", "context": RCA_CONTEXT}


def _dependencies(
    *,
    pending: dict[str, Any] | None,
    contextual_request: Any | None,
    contextual_plan: dict[str, Any] | None,
    execution_result: dict[str, Any],
    calls: dict[str, list[Any]],
    execute_started: asyncio.Event | None = None,
    execute_release: asyncio.Event | None = None,
) -> NaturalActionFollowupFlowDependencies:
    def latest(subject: dict[str, Any]) -> dict[str, Any] | None:
        calls["latest"].append(subject)
        return pending

    def recent(request: Any) -> Any | None:
        calls["recent"].append(request)
        return contextual_request

    async def create(request: Any, authorization: str, subject: dict[str, Any], **kwargs: Any):
        calls["create"].append((request, authorization, subject, kwargs))
        return contextual_plan

    async def execute(plan: dict[str, Any], authorization: str, subject: dict[str, Any]):
        calls["execute"].append((plan, authorization, subject))
        if execute_started is not None:
            execute_started.set()
        if execute_release is not None:
            await execute_release.wait()
        return execution_result

    def current_rca(phase: str) -> dict[str, Any]:
        calls["rca"].append(phase)
        return _rca_event()

    return NaturalActionFollowupFlowDependencies(
        latest_pending_action_plan_result=latest,
        recent_natural_action_request=recent,
        create_natural_action_plan=create,
        execute_natural_action_plan_result=execute,
        redact_sensitive=_redact,
        natural_action_execution_response=lambda result: f"execution:{result['status']}",
        natural_action_plan_response=lambda result: f"plan:{result['status']}",
        no_pending_action_plan_response=lambda: "no pending plan",
        current_rca_context_event=current_rca,
        sse=_sse,
    )


async def _collect(
    dependencies: NaturalActionFollowupFlowDependencies,
    request: Any,
) -> tuple[list[dict[str, Any] | str], list[NaturalActionFollowupStreamEvent]]:
    stream_events = [
        event
        async for event in stream_chat_natural_action_followup(
            authorization=AUTHORIZATION,
            dependencies=dependencies,
            incident_id="inc-1",
            request=request,
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )
    ]
    return [json.loads(event.payload) for event in stream_events], stream_events


@pytest.mark.parametrize(
    ("case", "pending", "contextual_request", "contextual_plan", "execution_result"),
    [
        (
            "pending_success",
            PLAN,
            None,
            None,
            {"status": "executed", "token": "raw-secret"},
        ),
        (
            "pending_failure",
            PLAN,
            None,
            None,
            {"status": "failed", "token": "raw-secret"},
        ),
        (
            "contextual_planned_success",
            None,
            SimpleNamespace(message="scale deployment"),
            PLAN,
            {"status": "executed", "token": "raw-secret"},
        ),
        (
            "contextual_planned_failure",
            None,
            SimpleNamespace(message="scale deployment"),
            PLAN,
            {"status": "failed", "token": "raw-secret"},
        ),
        (
            "contextual_nonplanned",
            None,
            SimpleNamespace(message="scale deployment"),
            {"status": "target_not_found", "token": "raw-secret"},
            {"status": "unused"},
        ),
        ("no_plan", None, None, None, {"status": "unused"}),
    ],
)
def test_followup_flow_golden_branches_and_callback_contract(
    case: str,
    pending: dict[str, Any] | None,
    contextual_request: Any | None,
    contextual_plan: dict[str, Any] | None,
    execution_result: dict[str, Any],
) -> None:
    calls = {name: [] for name in ("latest", "recent", "create", "execute", "rca")}
    request = SimpleNamespace(message="proceed")
    dependencies = _dependencies(
        pending=pending,
        contextual_request=contextual_request,
        contextual_plan=contextual_plan,
        execution_result=execution_result,
        calls=calls,
    )

    events, stream_events = asyncio.run(_collect(dependencies, request))

    assert calls["latest"] == [SUBJECT]
    if case.startswith("pending"):
        assert calls["recent"] == []
        assert calls["create"] == []
    else:
        assert calls["recent"] == [request]
    if contextual_request is not None:
        assert calls["create"] == [
            (
                contextual_request,
                AUTHORIZATION,
                SUBJECT,
                {"incident_id": "inc-1", "run_id": "run-1"},
            )
        ]
    else:
        assert calls["create"] == []

    contextual = case.startswith("contextual_planned")
    if case.startswith("pending") or contextual:
        assert calls["execute"] == [(PLAN, AUTHORIZATION, SUBJECT)]
        expected = [
            {
                "type": "tool_call",
                "id": "req-1-natural-action-followup",
                "name": "natural_action_followup",
                "summary": (
                    "최근 대화의 AIOps 조치 요청 후속 실행"
                    if contextual
                    else "최근 AIOps Action Plan 후속 실행"
                ),
            },
            _tool_result(
                execution_result,
                status="success" if execution_result["status"] == "executed" else "failed",
                summary=(
                    "최근 대화의 AIOps 조치 후속 실행 완료"
                    if contextual
                    else "최근 AIOps Action Plan 후속 실행 완료"
                ),
            ),
            {"type": "text", "content": f"execution:{execution_result['status']}"},
            {
                "type": "run_status",
                "runId": "run-1",
                "stage": "completed",
                "message": (
                    "Gateway 최근 맥락 조치 실행 완료"
                    if contextual
                    else "Gateway 후속 조치 실행 완료"
                ),
            },
            _rca_event(),
            "[DONE]",
        ]
    elif case == "contextual_nonplanned":
        assert calls["execute"] == []
        expected = [
            _tool_result(
                contextual_plan,
                status="failed",
                summary="최근 대화의 AIOps 조치 대상 확인 실패",
            ),
            {"type": "text", "content": "plan:target_not_found"},
            _rca_event(),
            {
                "type": "run_status",
                "runId": "run-1",
                "stage": "completed",
                "message": "Gateway 최근 맥락 조치 대상 확인 실패",
            },
            "[DONE]",
        ]
    else:
        assert calls["execute"] == []
        no_plan = {"status": "not_found", "reason": "no_pending_action_plan"}
        expected = [
            _tool_result(
                no_plan,
                status="skipped",
                summary="실행할 Gateway Action Plan 없음",
            ),
            {"type": "text", "content": "no pending plan"},
            _rca_event(),
            {
                "type": "run_status",
                "runId": "run-1",
                "stage": "completed",
                "message": "Gateway 후속 실행 대상 없음",
            },
            "[DONE]",
        ]

    assert events == expected
    assert calls["rca"] == ["post_answer"]
    marked = [event for event in stream_events if event.latest_rca_context is not None]
    assert len(marked) == 1
    assert marked[0].latest_rca_context is RCA_CONTEXT
    assert json.loads(marked[0].payload) == _rca_event()
    result_events = [event for event in events if isinstance(event, dict) and event.get("type") == "tool_result"]
    assert all("raw-secret" not in event["detail"] for event in result_events)


def test_tool_call_is_yielded_before_blocking_execute_await() -> None:
    async def run() -> None:
        calls = {name: [] for name in ("latest", "recent", "create", "execute", "rca")}
        execute_started = asyncio.Event()
        execute_release = asyncio.Event()
        dependencies = _dependencies(
            pending=PLAN,
            contextual_request=None,
            contextual_plan=None,
            execution_result={"status": "executed"},
            calls=calls,
            execute_started=execute_started,
            execute_release=execute_release,
        )
        flow = stream_chat_natural_action_followup(
            authorization=AUTHORIZATION,
            dependencies=dependencies,
            incident_id="inc-1",
            request=SimpleNamespace(message="proceed"),
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )

        first = await anext(flow)
        assert json.loads(first.payload)["type"] == "tool_call"
        assert not execute_started.is_set()

        next_event = asyncio.create_task(anext(flow))
        await execute_started.wait()
        assert not next_event.done()
        execute_release.set()
        assert json.loads((await next_event).payload)["type"] == "tool_result"
        await flow.aclose()

    asyncio.run(run())


def test_contextual_create_await_has_no_preceding_tool_call() -> None:
    async def run() -> None:
        create_started = asyncio.Event()
        create_release = asyncio.Event()
        calls = {name: [] for name in ("latest", "recent", "create", "execute", "rca")}
        dependencies = _dependencies(
            pending=None,
            contextual_request=SimpleNamespace(message="scale deployment"),
            contextual_plan=PLAN,
            execution_result={"status": "executed"},
            calls=calls,
        )

        async def blocking_create(*args: Any, **kwargs: Any) -> dict[str, Any]:
            calls["create"].append((*args, kwargs))
            create_started.set()
            await create_release.wait()
            return PLAN

        dependencies = replace(
            dependencies,
            create_natural_action_plan=blocking_create,
        )
        flow = stream_chat_natural_action_followup(
            authorization=AUTHORIZATION,
            dependencies=dependencies,
            incident_id="inc-1",
            request=SimpleNamespace(message="proceed"),
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )

        first_event = asyncio.create_task(anext(flow))
        await create_started.wait()
        assert not first_event.done()
        create_release.set()
        assert json.loads((await first_event).payload)["type"] == "tool_call"
        await flow.aclose()

    asyncio.run(run())


def test_main_dependency_factory_uses_fresh_monkeypatched_callbacks(monkeypatch) -> None:
    def latest(_subject: dict[str, Any]) -> None:
        return None

    async def create(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def execute(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "executed"}

    monkeypatch.setattr(gateway_main, "latest_pending_action_plan_result", latest)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", create)
    monkeypatch.setattr(gateway_main, "execute_natural_action_plan_result", execute)
    rca_callback = lambda phase: {"type": "rca_context", "context": {"phase": phase}}

    dependencies = gateway_main.natural_action_followup_flow_dependencies(rca_callback)

    assert dependencies.latest_pending_action_plan_result is latest
    assert dependencies.create_natural_action_plan is create
    assert dependencies.execute_natural_action_plan_result is execute
    assert dependencies.current_rca_context_event is rca_callback


def test_main_updates_last_rca_context_before_resuming_flow(monkeypatch) -> None:
    latest_context = {"marker": "main-updated"}
    update_observed: list[bool] = []

    async def fake_subject_review(_authorization: str) -> dict[str, Any]:
        return {"status": "authenticated", "subject": SUBJECT}

    async def fake_product_access_review(_authorization: str) -> dict[str, Any]:
        return {"allowed": True, "enabled": True, "required": True}

    async def fake_flow(**_kwargs: Any):
        yield NaturalActionFollowupStreamEvent(
            _sse({"type": "rca_context", "context": latest_context}),
            latest_rca_context=latest_context,
        )
        update_observed.append(gateway_main.LAST_RCA_CONTEXT is latest_context)
        yield NaturalActionFollowupStreamEvent(_sse("[DONE]"))

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "UNRESTRICTED_COMMANDS_ENABLED", True)
    monkeypatch.setattr(gateway_main, "stream_chat_natural_action_followup", fake_flow)
    gateway_main.LAST_RCA_CONTEXT = None

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": AUTHORIZATION},
                json={
                    "message": "진행해",
                    "pageContext": {"aiopsExecutionMode": "unrestricted"},
                },
            )
        assert response.status_code == 200

    asyncio.run(run())
    assert update_observed == [True]


def test_followup_flow_module_does_not_import_main() -> None:
    module_path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_natural_action_followup_flow.py"
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
