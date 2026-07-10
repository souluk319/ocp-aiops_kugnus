from __future__ import annotations

import json
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class NamespaceCleanupInventoryDependencies:
    execution_mode: Callable[[Any], str]
    answer_language: Callable[[Any], str]
    namespace_names: Callable[[str], list[str]]
    collect_inventory: Callable[..., Awaitable[dict[str, Any]]]
    cleanup_candidates: Callable[[Mapping[str, Any]], list[dict[str, Any]]]
    action_capable_mode: Callable[[str], bool]
    remember_candidates: Callable[..., None]
    answer: Callable[..., str]
    redact_sensitive: Callable[[Any], Any]
    sse: Callable[[Any], str]


@dataclass(frozen=True, slots=True)
class NamespaceCleanupInventoryStreamEvent:
    payload: str
    answer_chunk: str | None = None


def _event(dependencies, value, *, answer_chunk=None):
    return NamespaceCleanupInventoryStreamEvent(
        dependencies.sse(value),
        answer_chunk=answer_chunk,
    )


async def stream_namespace_cleanup_inventory(
    *,
    authorization: str,
    dependencies: NamespaceCleanupInventoryDependencies,
    incident_id: str,
    request: Any,
    request_id: str,
    run_id: str,
) -> AsyncIterator[NamespaceCleanupInventoryStreamEvent]:
    execution_mode = dependencies.execution_mode(request)
    language = dependencies.answer_language(request)
    requested_names = dependencies.namespace_names(request.message)
    yield _event(
        dependencies,
        {
            "type": "run_status",
            "runId": run_id,
            "stage": "started",
            "message": "Namespace usage check started" if language == "en" else "네임스페이스 사용 여부 확인 시작",
        },
    )
    yield _event(
        dependencies,
        {
            "type": "tool_call",
            "id": f"{request_id}-namespace-cleanup-inventory",
            "name": "namespace_cleanup_inventory",
            "summary": "Namespace usage read-only inventory" if language == "en" else "namespace 사용 여부 read-only 조회",
        },
    )
    inventory = await dependencies.collect_inventory(authorization, requested_names)
    candidates = dependencies.cleanup_candidates(inventory)
    action_capable = dependencies.action_capable_mode(execution_mode)
    if action_capable and candidates:
        dependencies.remember_candidates(inventory, run_id, incident_id)
    answer_text = dependencies.answer(inventory, execution_mode, language)
    redacted_inventory = dependencies.redact_sensitive(inventory)
    yield _event(
        dependencies,
        {
            "type": "tool_result",
            "detail": json.dumps(redacted_inventory, ensure_ascii=False, indent=2),
            "id": f"{request_id}-namespace-cleanup-inventory",
            "name": "namespace_cleanup_inventory",
            "result": redacted_inventory,
            "status": "success" if inventory.get("ok") else "failed",
            "summary": (
                f"namespace {len(inventory.get('inspected') or [])} read-only checks"
                if language == "en"
                else f"namespace {len(inventory.get('inspected') or [])}개 read-only 조회"
            ),
        },
    )
    tool_steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "adapter": "oc",
            "tool": "oc_get_namespaces",
            "verb": "list",
            "purpose": "접근 가능한 namespace 목록 확인",
        },
        {
            "step": 2,
            "adapter": "oc",
            "tool": "oc_get_namespace_inventory",
            "verb": "get",
            "purpose": "workload, PVC, Route, Event 잔존 확인",
        },
    ]
    if action_capable and candidates:
        tool_steps.append(
            {
                "step": 3,
                "adapter": "aiops-gateway",
                "tool": "namespace_cleanup_review_plan",
                "verb": "propose",
                "purpose": "승인 필요 Namespace 정리 검토 Action Plan 후보 생성",
            }
        )
    yield _event(
        dependencies,
        {
            "type": "tool_plan",
            "plan": {
                "task_type": "namespace_cleanup_review",
                "execution_policy": {
                    "mode": execution_mode,
                    "mutations_enabled": False,
                    "proposal_only": True,
                    "review_only": True,
                },
                "tool_plan": tool_steps,
                "validation": {
                    "ok": bool(inventory.get("ok")),
                    "status": (
                        "action_candidate_ready"
                        if action_capable and candidates
                        else "read_only_inventory_collected"
                        if inventory.get("ok")
                        else inventory.get("status")
                    ),
                },
            },
            "runId": run_id,
            "status": "success" if inventory.get("ok") else "failed",
        },
    )
    yield _event(
        dependencies,
        {
            "type": "text",
            "content": answer_text,
            "source": "gateway_direct" if inventory.get("ok") else "gateway_fallback",
        },
        answer_chunk=answer_text,
    )
    yield _event(
        dependencies,
        {
            "type": "run_status",
            "runId": run_id,
            "stage": "completed" if inventory.get("ok") else "failed",
            "message": "Namespace usage check completed" if language == "en" else "네임스페이스 사용 여부 확인 완료",
        },
    )
    yield _event(dependencies, "[DONE]")
