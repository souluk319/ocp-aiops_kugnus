from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_namespace_cleanup_inventory_flow import (
    NamespaceCleanupInventoryDependencies,
    stream_namespace_cleanup_inventory,
)


def _dependencies(*, ok, candidates, action_mode, language="ko", calls):
    inventory = {
        "ok": ok,
        "status": "ready" if ok else "failed",
        "inspected": [{"name": "team-a"}],
        "token": "secret",
    }

    async def collect(authorization, names):
        calls["collect"].append((authorization, names))
        return inventory

    return NamespaceCleanupInventoryDependencies(
        execution_mode=lambda request: calls["mode"].append(request) or "execute",
        answer_language=lambda request: calls["language"].append(request) or language,
        namespace_names=lambda message: calls["names"].append(message) or ["team-a"],
        collect_inventory=collect,
        cleanup_candidates=lambda value: calls["candidates"].append(value) or candidates,
        action_capable_mode=lambda mode: calls["action"].append(mode) or action_mode,
        remember_candidates=lambda value, run_id, incident_id: calls["remember"].append((value, run_id, incident_id)),
        answer=lambda value, mode, lang: f"answer:{value['status']}:{mode}:{lang}",
        redact_sensitive=lambda value: {
            key: "[REDACTED]" if key == "token" else item
            for key, item in value.items()
        },
        sse=lambda value: json.dumps(value, ensure_ascii=False),
    )


async def _collect(dependencies):
    stream_events = [
        event
        async for event in stream_namespace_cleanup_inventory(
            authorization="Bearer token",
            dependencies=dependencies,
            incident_id="inc-1",
            request=SimpleNamespace(message="team-a 정리해도 돼?"),
            request_id="req-1",
            run_id="run-1",
        )
    ]
    return stream_events, [json.loads(event.payload) for event in stream_events]


def _calls():
    return {name: [] for name in ("collect", "mode", "language", "names", "candidates", "action", "remember")}


@pytest.mark.parametrize(
    ("ok", "action_mode", "candidates", "validation", "steps", "remembered"),
    [
        (True, True, [{"id": "candidate"}], "action_candidate_ready", 3, 1),
        (True, False, [{"id": "candidate"}], "read_only_inventory_collected", 2, 0),
        (False, True, [], "failed", 2, 0),
    ],
)
def test_namespace_cleanup_inventory_contract(
    ok, action_mode, candidates, validation, steps, remembered
) -> None:
    calls = _calls()
    stream_events, events = asyncio.run(
        _collect(
            _dependencies(
                ok=ok,
                candidates=candidates,
                action_mode=action_mode,
                calls=calls,
            )
        )
    )
    assert [event if isinstance(event, str) else event["type"] for event in events] == [
        "run_status", "tool_call", "tool_result", "tool_plan", "text", "run_status", "[DONE]"
    ]
    assert events[2]["result"]["token"] == "[REDACTED]"
    assert events[3]["plan"]["validation"]["status"] == validation
    assert len(events[3]["plan"]["tool_plan"]) == steps
    assert events[3]["plan"]["execution_policy"]["mutations_enabled"] is False
    assert len(calls["remember"]) == remembered
    assert calls["collect"] == [("Bearer token", ["team-a"])]
    assert [event.answer_chunk for event in stream_events if event.answer_chunk] == [
        f"answer:{'ready' if ok else 'failed'}:execute:ko"
    ]


def test_main_factory_uses_current_inventory_collector(monkeypatch) -> None:
    async def collect(*_args, **_kwargs):
        return {}

    monkeypatch.setattr(gateway_main, "collect_namespace_cleanup_inventory", collect)
    assert gateway_main.namespace_cleanup_inventory_dependencies().collect_inventory is collect


def test_namespace_cleanup_inventory_module_does_not_import_main() -> None:
    path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_namespace_cleanup_inventory_flow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(module == "main" or module.endswith(".main") for module in imported)
