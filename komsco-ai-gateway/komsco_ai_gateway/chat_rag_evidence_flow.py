from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class RagEvidenceFlowDependencies:
    make_request: Callable[..., Any]
    search_runbooks: Callable[..., Awaitable[tuple[str, str, list[dict[str, Any]]]]]
    build_context_detail: Callable[[list[dict[str, Any]], str], str]
    build_citation_text: Callable[[list[dict[str, Any]]], str]
    append_gateway_evidence: Callable[[str | None, str], str]
    safe_exception_text: Callable[[Exception], str]
    build_evidence_reference_events: Callable[..., list[dict[str, Any]]]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class RagEvidenceStreamEvent:
    payload: str
    gateway_evidence: str | None = None
    citation_text: str | None = None
    citation_text_updated: bool = False


def _event(dependencies, value, **state):
    return RagEvidenceStreamEvent(payload=dependencies.sse(value), **state)


async def stream_rag_evidence(
    *,
    dependencies: RagEvidenceFlowDependencies,
    gateway_evidence: str | None,
    incident_id: str,
    message: str,
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any],
) -> AsyncIterator[RagEvidenceStreamEvent]:
    yield _event(
        dependencies,
        {
            "type": "tool_call",
            "id": f"{request_id}-rag-context-evidence",
            "name": "rag_context_evidence",
            "summary": "RAG 참고 문서 검색",
        },
    )
    citation_text = ""
    try:
        request = dependencies.make_request(
            query=message,
            topK=3,
            includeContent=False,
            runId=run_id,
        )
        status, reason, results = await dependencies.search_runbooks(
            request,
            subject=subject,
        )
        detail = dependencies.build_context_detail(results, reason)
        gateway_evidence = dependencies.append_gateway_evidence(gateway_evidence, detail)
        citation_text = dependencies.build_citation_text(results)
        rag_event = {
            "type": "tool_result",
            "detail": detail,
            "evidenceType": "runbook",
            "id": f"{request_id}-rag-context-evidence",
            "missingReason": "" if results else reason,
            "name": "rag_context_evidence",
            "result": {
                "query": message,
                "resultCount": len(results),
                "results": [
                    {
                        "documentId": result.get("documentId"),
                        "score": result.get("score"),
                        "sourceType": result.get("sourceType"),
                        "sourceUri": result.get("sourceUri"),
                        "title": result.get("title"),
                    }
                    for result in results
                ],
                "status": status,
            },
            "sourcePath": "/v1/rag/search",
            "status": "success" if results else "skipped",
            "summary": (
                f"RAG 참고 문서 {len(results)}건 검색"
                if results
                else "RAG 참고 문서 검색 결과 없음"
            ),
        }
    except Exception as exc:
        safe_detail = dependencies.safe_exception_text(exc)
        detail = f"RAG evidence unavailable: {safe_detail}"
        gateway_evidence = dependencies.append_gateway_evidence(gateway_evidence, detail)
        rag_event = {
            "type": "tool_result",
            "detail": detail,
            "evidenceType": "runbook",
            "id": f"{request_id}-rag-context-evidence",
            "missingReason": safe_detail,
            "name": "rag_context_evidence",
            "sourcePath": "/v1/rag/search",
            "status": "error",
            "summary": "RAG 참고 문서 검색 실패",
        }

    yield _event(
        dependencies,
        rag_event,
        gateway_evidence=gateway_evidence,
        citation_text=citation_text,
        citation_text_updated=True,
    )
    for reference in dependencies.build_evidence_reference_events(
        event=rag_event,
        incident_id=incident_id,
        run_id=run_id,
        source_type="gateway-rag-evidence",
        subject=subject,
    ):
        yield _event(dependencies, reference)
