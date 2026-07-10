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
from komsco_ai_gateway.chat_natural_action_proposal_flow import (
    NaturalActionProposalFlowDependencies,
    stream_chat_natural_action_proposal,
)


AUTHORIZATION = "Bearer operator-token"
SUBJECT = {"username": "operator", "uid": "uid-operator"}
INTENT = {"toolName": "set_replicas_within_bounds", "targetName": "web-api"}
PLAN = {"status": "planned", "planId": "plan-1", "token": "raw-secret"}
RCA_CONTEXT = {"phase": "post_answer", "marker": "proposal"}


def _sse(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _redact(value: Any) -> Any:
    if not isinstance(value, dict):
        return value
    return {
        key: "[REDACTED]" if key == "token" else item
        for key, item in value.items()
    }


def _dependencies(
    *,
    intent: dict[str, Any] | None,
    allows_actions: bool,
    immediate: bool,
    plan: dict[str, Any] | None,
    execution: dict[str, Any],
    calls: dict[str, list[Any]],
    execute_started: asyncio.Event | None = None,
    execute_release: asyncio.Event | None = None,
) -> NaturalActionProposalFlowDependencies:
    def parse(request: Any) -> dict[str, Any] | None:
        calls["parse"].append(request)
        return intent

    async def create(request: Any, authorization: str, subject: Any, **kwargs: Any):
        calls["create"].append((request, authorization, subject, kwargs))
        return plan

    async def execute(value: Any, authorization: str, subject: Any):
        calls["execute"].append((value, authorization, subject))
        if execute_started is not None:
            execute_started.set()
        if execute_release is not None:
            await execute_release.wait()
        return execution

    def current_rca(phase: str) -> dict[str, Any]:
        calls["rca"].append(phase)
        return {"type": "rca_context", "context": RCA_CONTEXT}

    return NaturalActionProposalFlowDependencies(
        parse_intent=parse,
        execution_mode=lambda _request: "unrestricted" if immediate else "execute",
        allows_actions=lambda _request: allows_actions,
        allows_immediate_actions=lambda _request: immediate,
        create_plan=create,
        execute_plan=execute,
        unresolved_response=lambda _request: "unresolved response",
        evidence_check_response=lambda value: f"evidence:{value['targetName']}",
        plan_response=lambda value: f"plan:{value['status']}",
        execution_response=lambda value: f"execution:{value['status']}",
        redact_sensitive=_redact,
        current_rca_context_event=current_rca,
        sse=_sse,
    )


async def _collect(dependencies: NaturalActionProposalFlowDependencies):
    request = SimpleNamespace(message="scale web-api")
    stream_events = [
        event
        async for event in stream_chat_natural_action_proposal(
            authorization=AUTHORIZATION,
            dependencies=dependencies,
            incident_id="inc-1",
            request=request,
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )
    ]
    return request, stream_events, [json.loads(event.payload) for event in stream_events]


@pytest.mark.parametrize(
    ("case", "intent", "allows_actions", "immediate", "plan", "execution", "event_types"),
    [
        (
            "unresolved",
            None,
            True,
            False,
            None,
            {"status": "unused"},
            ["tool_result", "text", "rca_context", "run_status", "[DONE]"],
        ),
        (
            "read_only",
            INTENT,
            False,
            False,
            None,
            {"status": "unused"},
            ["tool_result", "text", "rca_context", "run_status", "[DONE]"],
        ),
        (
            "plan_missing",
            INTENT,
            True,
            False,
            None,
            {"status": "unused"},
            [],
        ),
        (
            "plan_failed",
            INTENT,
            True,
            False,
            {"status": "target_not_found", "token": "raw-secret"},
            {"status": "unused"},
            ["tool_result", "text", "run_status", "rca_context", "[DONE]"],
        ),
        (
            "plan_ready",
            INTENT,
            True,
            False,
            PLAN,
            {"status": "unused"},
            ["tool_result", "text", "run_status", "rca_context", "[DONE]"],
        ),
        (
            "execute_success",
            INTENT,
            True,
            True,
            PLAN,
            {"status": "executed", "token": "raw-secret"},
            [
                "tool_result",
                "tool_call",
                "tool_result",
                "text",
                "run_status",
                "rca_context",
                "[DONE]",
            ],
        ),
        (
            "execute_failed",
            INTENT,
            True,
            True,
            PLAN,
            {"status": "failed", "token": "raw-secret"},
            [
                "tool_result",
                "tool_call",
                "tool_result",
                "text",
                "run_status",
                "rca_context",
                "[DONE]",
            ],
        ),
    ],
)
def test_proposal_flow_preserves_golden_branches(
    case: str,
    intent: dict[str, Any] | None,
    allows_actions: bool,
    immediate: bool,
    plan: dict[str, Any] | None,
    execution: dict[str, Any],
    event_types: list[str],
) -> None:
    calls = {name: [] for name in ("parse", "create", "execute", "rca")}
    dependencies = _dependencies(
        intent=intent,
        allows_actions=allows_actions,
        immediate=immediate,
        plan=plan,
        execution=execution,
        calls=calls,
    )

    request, stream_events, events = asyncio.run(_collect(dependencies))
    actual_types = [
        event if isinstance(event, str) else event["type"]
        for event in events
    ]
    assert actual_types == event_types
    assert calls["parse"] == [request]

    if intent and allows_actions:
        assert calls["create"] == [
            (
                request,
                AUTHORIZATION,
                SUBJECT,
                {"incident_id": "inc-1", "run_id": "run-1"},
            )
        ]
    else:
        assert calls["create"] == []

    should_execute = bool(plan and plan.get("status") == "planned" and immediate)
    assert calls["execute"] == (
        [(plan, AUTHORIZATION, SUBJECT)] if should_execute else []
    )
    expected_rca_count = 0 if case == "plan_missing" else 1
    assert calls["rca"] == ["post_answer"] * expected_rca_count
    marked = [event for event in stream_events if event.latest_rca_context is not None]
    assert len(marked) == expected_rca_count

    result_events = [
        event
        for event in events
        if isinstance(event, dict) and event.get("type") == "tool_result"
    ]
    assert all("raw-secret" not in event["detail"] for event in result_events)

    if case == "unresolved":
        assert result_events[0]["name"] == "natural_action_unresolved"
        assert events[1]["content"] == "unresolved response"
    if case == "read_only":
        assert result_events[0]["status"] == "skipped"
        assert events[1]["content"] == "evidence:web-api"
    if case == "plan_ready":
        assert events[1]["answerContract"] == "natural-action-plan-v0.2.1"
    if case == "plan_failed":
        assert "answerContract" not in events[1]
    if case.startswith("execute_"):
        assert result_events[0]["name"] == "natural_action_plan"
        assert result_events[1]["name"] == "natural_action_execute"


def test_execute_tool_call_is_yielded_before_blocking_execute() -> None:
    async def run() -> None:
        calls = {name: [] for name in ("parse", "create", "execute", "rca")}
        execute_started = asyncio.Event()
        execute_release = asyncio.Event()
        dependencies = _dependencies(
            intent=INTENT,
            allows_actions=True,
            immediate=True,
            plan=PLAN,
            execution={"status": "executed"},
            calls=calls,
            execute_started=execute_started,
            execute_release=execute_release,
        )
        flow = stream_chat_natural_action_proposal(
            authorization=AUTHORIZATION,
            dependencies=dependencies,
            incident_id="inc-1",
            request=SimpleNamespace(message="scale web-api"),
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )

        assert json.loads((await anext(flow)).payload)["name"] == "natural_action_plan"
        assert json.loads((await anext(flow)).payload)["type"] == "tool_call"
        assert not execute_started.is_set()
        pending_result = asyncio.create_task(anext(flow))
        await execute_started.wait()
        assert not pending_result.done()
        execute_release.set()
        assert json.loads((await pending_result).payload)["name"] == "natural_action_execute"
        await flow.aclose()

    asyncio.run(run())


def test_plan_creation_does_not_emit_placeholder_before_await() -> None:
    async def run() -> None:
        calls = {name: [] for name in ("parse", "create", "execute", "rca")}
        started = asyncio.Event()
        release = asyncio.Event()
        dependencies = _dependencies(
            intent=INTENT,
            allows_actions=True,
            immediate=False,
            plan=PLAN,
            execution={"status": "unused"},
            calls=calls,
        )

        async def blocking_create(*args: Any, **kwargs: Any):
            calls["create"].append((*args, kwargs))
            started.set()
            await release.wait()
            return PLAN

        dependencies = replace(dependencies, create_plan=blocking_create)
        flow = stream_chat_natural_action_proposal(
            authorization=AUTHORIZATION,
            dependencies=dependencies,
            incident_id="inc-1",
            request=SimpleNamespace(message="scale web-api"),
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )
        first_event = asyncio.create_task(anext(flow))
        await started.wait()
        assert not first_event.done()
        release.set()
        assert json.loads((await first_event).payload)["name"] == "natural_action_plan"
        await flow.aclose()

    asyncio.run(run())


def test_main_factory_uses_current_callbacks(monkeypatch) -> None:
    async def create(*_args: Any, **_kwargs: Any):
        return PLAN

    async def execute(*_args: Any, **_kwargs: Any):
        return {"status": "executed"}

    monkeypatch.setattr(gateway_main, "create_natural_action_plan", create)
    monkeypatch.setattr(gateway_main, "execute_natural_action_plan_result", execute)
    callback = lambda phase: {"type": "rca_context", "context": {"phase": phase}}
    dependencies = gateway_main.natural_action_proposal_flow_dependencies(callback)
    assert dependencies.create_plan is create
    assert dependencies.execute_plan is execute
    assert dependencies.current_rca_context_event is callback


def test_main_falls_through_to_ols_when_plan_creation_returns_none(monkeypatch) -> None:
    async def subject_review(_authorization: str) -> dict[str, Any]:
        return {"status": "authenticated", "subject": SUBJECT}

    async def product_access(_authorization: str) -> dict[str, Any]:
        return {"allowed": True, "enabled": True, "required": True}

    async def create_none(*_args: Any, **_kwargs: Any) -> None:
        return None

    async def ols_stream(*_args: Any, **_kwargs: Any):
        yield {"type": "text", "content": "OLS fallthrough reached"}
        yield {"type": "end"}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", product_access)
    monkeypatch.setattr(gateway_main, "create_natural_action_plan", create_none)
    monkeypatch.setattr(gateway_main, "call_ols_stream", ols_stream)

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/v1/chat/stream",
                headers={"Authorization": AUTHORIZATION},
                json={
                    "message": "team-a 네임스페이스의 web-api 파드 4개로 올려줘",
                    "pageContext": {"aiopsExecutionMode": "execute"},
                },
            )
        assert response.status_code == 200
        assert "OLS fallthrough reached" in response.text
        assert "natural-action-plan" not in response.text

    asyncio.run(run())


def test_proposal_flow_module_does_not_import_main() -> None:
    module_path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_natural_action_proposal_flow.py"
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
