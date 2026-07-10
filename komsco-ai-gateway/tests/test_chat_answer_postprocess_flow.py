from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_answer_postprocess_flow import (
    AnswerPostprocessDependencies,
    AnswerPostprocessState,
    stream_answer_postprocess,
)


CONTEXT = {"metadata": {"digest": "sha256:context"}}


def _dependencies(*, require, crashloop="", aiops="", calls):
    return AnswerPostprocessDependencies(
        require_final_answer=require,
        active_llm_label=lambda: "Lightspeed",
        update_ols_stream_status=lambda *args, **kwargs: calls["status"].append((args, kwargs)),
        build_required_failure_answer=lambda *args, **kwargs: calls["required"].append((args, kwargs)) or "required notice",
        build_empty_answer_fallback=lambda *args, **kwargs: calls["fallback"].append((args, kwargs)) or "gateway fallback",
        should_forward_image_attachments_to_ols=lambda: False,
        build_crashloop_answer_contract_text=lambda request, run_id: calls["crashloop"].append((request, run_id)) or crashloop,
        build_aiops_answer_contract_text=lambda **kwargs: calls["aiops"].append(kwargs) or aiops,
        sse=lambda value: json.dumps(value, ensure_ascii=False),
    )


async def _collect(dependencies, *, emitted, attempts=1, citation=""):
    state = AnswerPostprocessState()
    request = SimpleNamespace(message="pod 상태")
    payloads = [
        payload
        async for payload in stream_answer_postprocess(
            attempt_count=attempts,
            dependencies=dependencies,
            emitted_answer_text=emitted,
            gateway_context=CONTEXT,
            gateway_evidence="evidence",
            image_analysis="analysis",
            ols_tool_results=[{"type": "tool_result"}],
            policy={"decision": "allow_evidence_collection"},
            pre_answer_rca_context={"phase": "pre_answer"},
            rag_citation_text=citation,
            request=request,
            run_id="run-1",
            runtime_tool_plan={"kind": "plan"},
            state=state,
        )
    ]
    return request, state, [json.loads(payload) for payload in payloads]


def _calls():
    return {name: [] for name in ("status", "required", "fallback", "crashloop", "aiops")}


def test_required_final_answer_notice_blocks_citation_and_contract() -> None:
    calls = _calls()
    _, state, events = asyncio.run(
        _collect(
            _dependencies(require=True, aiops="aiops contract", calls=calls),
            emitted=False,
            attempts=2,
            citation="citation",
        )
    )
    assert events == [
        {
            "type": "text",
            "content": "required notice",
            "source": "ols_required_notice",
            "gatewayContextDigest": "sha256:context",
            "streamProbe": "failed",
            "finalAnswerUnavailable": True,
        }
    ]
    assert state.transcript_chunks == ["required notice"]
    assert state.answer_contracts == []
    assert calls["status"][0][1]["fallback_active"] is False
    assert "after 2 attempts" in calls["status"][0][1]["reason"]
    assert calls["fallback"] == []


def test_gateway_fallback_allows_citation_and_aiops_contract() -> None:
    calls = _calls()
    _, state, events = asyncio.run(
        _collect(
            _dependencies(require=False, aiops="aiops contract", calls=calls),
            emitted=False,
            citation="citation",
        )
    )
    assert [event["source"] for event in events] == [
        "gateway_fallback",
        "gateway_rag_citation",
        "gateway_answer_contract",
    ]
    assert events[0]["fallbackAnswer"] is True
    assert events[2]["answerContract"] == "aiops-action-v0.1.9"
    assert state.transcript_chunks == ["gateway fallback", "citation", "aiops contract"]
    assert state.answer_contracts == ["aiops-action-v0.1.9"]
    assert calls["status"][0][1]["fallback_active"] is True


def test_emitted_answer_prefers_crashloop_contract() -> None:
    calls = _calls()
    request, state, events = asyncio.run(
        _collect(
            _dependencies(
                require=True,
                crashloop="crashloop contract",
                aiops="must not be used",
                calls=calls,
            ),
            emitted=True,
            citation="citation",
        )
    )
    assert [event["content"] for event in events] == ["citation", "crashloop contract"]
    assert events[1]["answerContract"] == "crashloop-v0.1.3"
    assert state.answer_contracts == ["crashloop-v0.1.3"]
    assert calls["crashloop"] == [(request, "run-1")]
    assert calls["aiops"] == []
    assert calls["status"] == []


def test_main_factory_uses_current_fallback_callback(monkeypatch) -> None:
    def fallback(*_args, **_kwargs):
        return "fallback"

    monkeypatch.setattr(gateway_main, "build_empty_answer_fallback", fallback)
    assert gateway_main.answer_postprocess_dependencies().build_empty_answer_fallback is fallback


def test_answer_postprocess_module_does_not_import_main() -> None:
    path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_answer_postprocess_flow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(module == "main" or module.endswith(".main") for module in imported)
