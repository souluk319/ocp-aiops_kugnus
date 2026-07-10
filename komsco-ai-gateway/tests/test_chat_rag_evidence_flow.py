from __future__ import annotations

import ast
import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.chat_rag_evidence_flow import (
    RagEvidenceFlowDependencies,
    stream_rag_evidence,
)


SUBJECT = {"username": "operator", "uid": "uid-operator"}
RESULT = {
    "documentId": "doc-1",
    "score": 0.9,
    "sourceType": "runbook",
    "sourceUri": "runbook://one",
    "title": "Runbook One",
    "content": "excluded",
}


def _dependencies(*, results, reason="", error=None, calls, started=None, release=None):
    async def search(request, *, subject):
        calls["search"].append((request, subject))
        if started:
            started.set()
        if release:
            await release.wait()
        if error:
            raise error
        return "ready", reason, results

    def refs(**kwargs: Any):
        calls["refs"].append(kwargs)
        return [{"type": "evidence_ref", "evidenceType": "runbook"}]

    return RagEvidenceFlowDependencies(
        make_request=lambda **kwargs: calls["request"].append(kwargs) or kwargs,
        search_runbooks=search,
        build_context_detail=lambda items, why: f"detail:{len(items)}:{why}",
        build_citation_text=lambda items: f"citations:{len(items)}",
        append_gateway_evidence=lambda current, detail: f"{current}|{detail}",
        safe_exception_text=lambda exc: f"safe:{exc}",
        build_evidence_reference_events=refs,
        sse=lambda value: json.dumps(value, ensure_ascii=False),
    )


async def _collect(dependencies):
    stream_events = [
        event
        async for event in stream_rag_evidence(
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            message="pod restart",
            request_id="req-1",
            run_id="run-1",
            subject=SUBJECT,
        )
    ]
    return stream_events, [json.loads(event.payload) for event in stream_events]


@pytest.mark.parametrize(
    ("results", "reason", "status", "summary", "citation"),
    [
        ([RESULT], "", "success", "RAG 참고 문서 1건 검색", "citations:1"),
        ([], "no match", "skipped", "RAG 참고 문서 검색 결과 없음", "citations:0"),
    ],
)
def test_rag_evidence_success_and_empty_contract(results, reason, status, summary, citation):
    calls = {"request": [], "search": [], "refs": []}
    stream_events, events = asyncio.run(
        _collect(_dependencies(results=results, reason=reason, calls=calls))
    )

    assert [event["type"] for event in events] == ["tool_call", "tool_result", "evidence_ref"]
    result = events[1]
    assert result["status"] == status
    assert result["summary"] == summary
    assert result["result"]["resultCount"] == len(results)
    assert "content" not in (result["result"]["results"][0] if results else {})
    assert result["missingReason"] == ("" if results else reason)
    marked = [event for event in stream_events if event.citation_text_updated]
    assert len(marked) == 1
    assert marked[0].citation_text == citation
    assert marked[0].gateway_evidence == f"base|detail:{len(results)}:{reason}"
    assert calls["request"] == [
        {"query": "pod restart", "topK": 3, "includeContent": False, "runId": "run-1"}
    ]
    assert calls["refs"][0]["source_type"] == "gateway-rag-evidence"


def test_rag_evidence_failure_clears_citation_and_emits_error() -> None:
    calls = {"request": [], "search": [], "refs": []}
    stream_events, events = asyncio.run(
        _collect(
            _dependencies(
                results=[],
                error=RuntimeError("dimension mismatch"),
                calls=calls,
            )
        )
    )
    result = events[1]
    assert result["status"] == "error"
    assert result["missingReason"] == "safe:dimension mismatch"
    assert result["detail"] == "RAG evidence unavailable: safe:dimension mismatch"
    assert stream_events[1].citation_text == ""


def test_tool_call_is_emitted_before_search_wait() -> None:
    async def run() -> None:
        calls = {"request": [], "search": [], "refs": []}
        started = asyncio.Event()
        release = asyncio.Event()
        dependencies = _dependencies(
            results=[RESULT], calls=calls, started=started, release=release
        )
        flow = stream_rag_evidence(
            dependencies=dependencies,
            gateway_evidence="base",
            incident_id="inc-1",
            message="pod restart",
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


def test_main_factory_uses_current_search_callback(monkeypatch) -> None:
    async def search(*_args, **_kwargs):
        return "ready", "", []

    monkeypatch.setattr(gateway_main, "search_pgvector_runbooks", search)
    assert gateway_main.rag_evidence_flow_dependencies().search_runbooks is search


def test_rag_evidence_module_does_not_import_main() -> None:
    path = Path(__file__).parents[1] / "komsco_ai_gateway" / "chat_rag_evidence_flow.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(module == "main" or module.endswith(".main") for module in imported)
