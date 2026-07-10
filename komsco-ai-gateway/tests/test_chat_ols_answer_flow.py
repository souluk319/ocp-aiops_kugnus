from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_ols_answer_flow import (
    OlsAnswerFlowDependencies,
    OlsAnswerState,
    stream_ols_answer_attempts,
)


SUBJECT = {"username": "operator", "uid": "uid-operator"}
CONTEXT = {"metadata": {"digest": "sha256:context"}}


class TextFilter:
    def __init__(self, *, suffix: str = "") -> None:
        self.suffix = suffix

    def filter(self, content: str) -> str:
        return content

    def flush(self) -> str:
        suffix, self.suffix = self.suffix, ""
        return suffix


def _dependencies(*, attempts, retries=1, require=True, calls):
    attempt_index = 0

    def call_ols(*args):
        nonlocal attempt_index
        calls["queries"].append(args)
        current = attempts[attempt_index]
        attempt_index += 1

        async def events():
            if isinstance(current, Exception):
                raise current
            for event in current:
                yield event

        return events()

    async def heartbeats(stream, run_id):
        calls["heartbeats"].append(run_id)
        async for event in stream:
            yield event

    def refs(**kwargs: Any):
        calls["refs"].append(kwargs)
        return [{"type": "evidence_ref", "evidenceType": "event"}]

    return OlsAnswerFlowDependencies(
        empty_answer_retries=retries,
        require_final_answer=require,
        call_ols_stream=call_ols,
        stream_with_heartbeats=heartbeats,
        normalize_ols_event=lambda event: event,
        redact_sensitive=lambda value: value,
        answer_language_contract=lambda _request: "Answer in Korean.",
        safe_exception_text=lambda exc: f"safe:{exc}",
        update_ols_stream_status=lambda *args, **kwargs: calls["status"].append((args, kwargs)),
        active_llm_stage=lambda: "lightspeed",
        active_llm_label=lambda: "Lightspeed",
        build_evidence_reference_events=refs,
        sse=lambda value: json.dumps(value, ensure_ascii=False),
    )


async def _collect(dependencies, *, text_filter=None):
    state = OlsAnswerState()
    request = SimpleNamespace(
        message="pod 상태 알려줘",
        conversationId="conv-1",
        attachments=[],
    )
    payloads = [
        payload
        async for payload in stream_ols_answer_attempts(
            authorization="Bearer token",
            dependencies=dependencies,
            gateway_context=CONTEXT,
            incident_id="inc-1",
            ols_query="full query",
            request=request,
            request_id="req-1",
            run_id="run-1",
            state=state,
            subject=SUBJECT,
            text_reference_filter=text_filter or TextFilter(),
        )
    ]
    return state, [json.loads(payload) for payload in payloads]


def _calls():
    return {"queries": [], "heartbeats": [], "refs": [], "status": []}


def test_text_stream_preserves_metadata_and_flush_state() -> None:
    calls = _calls()
    dependencies = _dependencies(
        attempts=[
            [
                {
                    "type": "text",
                    "content": "answer",
                    "source": "ols",
                    "streamProbe": "ok",
                },
                {"type": "end"},
            ]
        ],
        calls=calls,
    )
    state, events = asyncio.run(
        _collect(dependencies, text_filter=TextFilter(suffix=" tail"))
    )

    assert events == [
        {"type": "text", "content": "answer", "source": "ols", "streamProbe": "ok"},
        {"type": "text", "content": " tail"},
        {"type": "end"},
    ]
    assert state.emitted_answer_text is True
    assert state.answer_chunks == ["answer", " tail"]
    assert state.attempt_count == 1


def test_tool_result_adds_reference_and_state() -> None:
    calls = _calls()
    tool_result = {"type": "tool_result", "name": "pods", "evidenceType": "event"}
    state, events = asyncio.run(
        _collect(_dependencies(attempts=[[tool_result, {"type": "end"}]], retries=0, calls=calls))
    )
    assert events[:2] == [tool_result, {"type": "evidence_ref", "evidenceType": "event"}]
    assert state.tool_results == [tool_result]
    assert calls["refs"][0]["source_type"] == "ols-tool-result"
    assert calls["refs"][0]["subject"] == SUBJECT


def test_empty_answer_retries_with_rewritten_query() -> None:
    calls = _calls()
    state, events = asyncio.run(
        _collect(
            _dependencies(
                attempts=[
                    [{"type": "end"}],
                    [{"type": "text", "content": "retry answer"}, {"type": "end"}],
                ],
                calls=calls,
            )
        )
    )
    retry_status = next(event for event in events if event.get("stage") == "lightspeed_retry")
    assert retry_status["attempt"] == 2
    assert "Do not call tools again" in calls["queries"][1][1]
    assert "Answer in Korean." in calls["queries"][1][1]
    assert state.answer_chunks == ["retry answer"]
    assert state.attempt_count == 2


def test_exception_retries_then_emits_final_error() -> None:
    calls = _calls()
    state, events = asyncio.run(
        _collect(
            _dependencies(
                attempts=[RuntimeError("first"), RuntimeError("second")],
                calls=calls,
            )
        )
    )
    assert events[0]["stage"] == "lightspeed_retry"
    assert events[-1]["name"] == "lightspeed_stream"
    assert events[-1]["detail"] == "safe:second"
    assert len(state.tool_results) == 2
    assert len(calls["status"]) == 2
    assert calls["status"][-1][1]["fallback_active"] is False


def test_main_factory_uses_current_stream_callback(monkeypatch) -> None:
    def stream(*_args, **_kwargs):
        return None

    monkeypatch.setattr(gateway_main, "call_ols_stream", stream)
    assert gateway_main.ols_answer_flow_dependencies().call_ols_stream is stream


def test_ols_answer_flow_module_does_not_import_main() -> None:
    path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_ols_answer_flow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(module == "main" or module.endswith(".main") for module in imported)
