import asyncio
import json
import time
import uuid
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx
from fastapi import HTTPException


Record = dict[str, Any]
RecordStore = dict[str, Record]
RecordStoreDefinition = tuple[RecordStore, int, str]


class ChatRequestLike(Protocol):
    attachments: list[Any]
    conversationId: str | None
    message: str


@dataclass(frozen=True)
class PersistenceRuntimeConfig:
    record_store_enabled: bool
    record_store_configmap: str
    record_store_token_file: str
    record_store_namespace: str
    serviceaccount_namespace_file: str
    openshift_api_url: str
    openshift_api_ca_file: str | bool
    rate_limit_per_minute: int
    workflow_max_records: int
    chat_transcript_max_message_chars: int
    chat_transcript_max_answer_chars: int
    chat_transcript_jsonl_path: str


@dataclass(frozen=True)
class PersistenceRuntimeStores:
    record_stores: Mapping[str, RecordStoreDefinition]
    workflow_records: RecordStore
    rate_limit_buckets: dict[str, list[float]]
    action_proposals: RecordStore
    sealed_action_plans: RecordStore
    approval_decisions: RecordStore
    execution_records: RecordStore


@dataclass(frozen=True)
class PersistenceRuntimeCallbacks:
    bounded_put: Callable[[RecordStore, str, Record, int], None]
    canonical_digest: Callable[[Any], str]
    increment_metric: Callable[[str], None]
    now_rfc3339: Callable[[], str]
    redact_sensitive: Callable[[Any], Any]
    safe_subject: Callable[[Mapping[str, Any] | None], dict[str, Any]]


def current_namespace(config: PersistenceRuntimeConfig) -> str:
    if config.record_store_namespace:
        return config.record_store_namespace
    try:
        return Path(config.serviceaccount_namespace_file).read_text(encoding="utf-8").strip() or "default"
    except OSError:
        return "default"


def record_store_auth_header(config: PersistenceRuntimeConfig) -> str:
    try:
        token = Path(config.record_store_token_file).read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="record store token is unavailable") from exc
    return f"Bearer {token}"


def record_store_path(config: PersistenceRuntimeConfig, namespace: str) -> str:
    return f"/api/v1/namespaces/{namespace}/configmaps/{config.record_store_configmap}"


async def record_store_request(
    config: PersistenceRuntimeConfig,
    method: str,
    path: str,
    *,
    body: Mapping[str, Any] | None = None,
    content_type: str = "application/json",
    auth_header: Callable[[], str] | None = None,
) -> httpx.Response:
    if not config.openshift_api_url:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")
    headers = {
        "Accept": "application/json",
        "Authorization": (auth_header or (lambda: record_store_auth_header(config)))(),
    }
    if body is not None:
        headers["Content-Type"] = content_type
    async with httpx.AsyncClient(
        verify=config.openshift_api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        return await client.request(
            method,
            f"{config.openshift_api_url}{path}",
            headers=headers,
            json=body,
        )


async def load_record_store(
    config: PersistenceRuntimeConfig,
    stores: PersistenceRuntimeStores,
    callbacks: PersistenceRuntimeCallbacks,
    request: Callable[..., Awaitable[httpx.Response]],
    namespace_provider: Callable[[], str] | None = None,
    path_provider: Callable[[str], str] | None = None,
) -> None:
    if not config.record_store_enabled:
        return
    namespace = (namespace_provider or (lambda: current_namespace(config)))()
    try:
        path = (path_provider or (lambda value: record_store_path(config, value)))(namespace)
        response = await request("GET", path)
        if response.status_code == 404:
            callbacks.increment_metric("aiops_record_store_loads_total")
            return
        if response.status_code >= 400:
            callbacks.increment_metric("aiops_record_store_failures_total")
            return
        payload = response.json()
        data = payload.get("data") if isinstance(payload, Mapping) else {}
        if not isinstance(data, Mapping):
            return
        for store, limit, key in stores.record_stores.values():
            raw = data.get(key)
            if not isinstance(raw, str) or not raw.strip():
                continue
            loaded = json.loads(raw)
            if not isinstance(loaded, Mapping):
                continue
            store.clear()
            for record_key, record in list(loaded.items())[-limit:]:
                if isinstance(record_key, str) and isinstance(record, Mapping):
                    store[record_key] = dict(record)
        callbacks.increment_metric("aiops_record_store_loads_total")
    except Exception:
        callbacks.increment_metric("aiops_record_store_failures_total")


async def persist_record_store(
    config: PersistenceRuntimeConfig,
    stores: PersistenceRuntimeStores,
    callbacks: PersistenceRuntimeCallbacks,
    store_name: str,
    request: Callable[..., Awaitable[httpx.Response]],
    namespace_provider: Callable[[], str] | None = None,
    path_provider: Callable[[str], str] | None = None,
) -> None:
    if not config.record_store_enabled:
        return
    definition = stores.record_stores.get(store_name)
    if not definition:
        return
    store, _limit, key = definition
    namespace = (namespace_provider or (lambda: current_namespace(config)))()
    data_value = json.dumps(
        callbacks.redact_sensitive(store),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    patch_body = {"data": {key: data_value}}
    try:
        response = await request(
            "PATCH",
            (path_provider or (lambda value: record_store_path(config, value)))(namespace),
            body=patch_body,
            content_type="application/merge-patch+json",
        )
        if response.status_code == 404:
            create_body = {
                "apiVersion": "v1",
                "kind": "ConfigMap",
                "metadata": {
                    "name": config.record_store_configmap,
                    "namespace": namespace,
                    "labels": {"app": "komsco-ai-gateway", "aiops.komsco/store": "ledger"},
                },
                "data": {key: data_value},
            }
            response = await request(
                "POST",
                f"/api/v1/namespaces/{namespace}/configmaps",
                body=create_body,
            )
        if response.status_code >= 400:
            callbacks.increment_metric("aiops_record_store_failures_total")
            return
        callbacks.increment_metric("aiops_record_store_writes_total")
    except Exception:
        callbacks.increment_metric("aiops_record_store_failures_total")


async def bounded_put_record(
    stores: PersistenceRuntimeStores,
    callbacks: PersistenceRuntimeCallbacks,
    store_name: str,
    key: str,
    value: Record,
    persist: Callable[[str], Awaitable[None]],
) -> None:
    store, limit, _data_key = stores.record_stores[store_name]
    callbacks.bounded_put(store, key, value, limit)
    await persist(store_name)


def enforce_rate_limit(
    config: PersistenceRuntimeConfig,
    stores: PersistenceRuntimeStores,
    callbacks: PersistenceRuntimeCallbacks,
    user_auth_header: str,
) -> None:
    if config.rate_limit_per_minute <= 0:
        return
    now = time.monotonic()
    bucket_key = callbacks.canonical_digest(user_auth_header)
    bucket = [item for item in stores.rate_limit_buckets.get(bucket_key, []) if now - item < 60.0]
    if len(bucket) >= config.rate_limit_per_minute:
        callbacks.increment_metric("aiops_rate_limited_total")
        raise HTTPException(status_code=429, detail="KOMSCO AI request rate limit exceeded")
    bucket.append(now)
    stores.rate_limit_buckets[bucket_key] = bucket


def record_workflow(
    config: PersistenceRuntimeConfig,
    stores: PersistenceRuntimeStores,
    callbacks: PersistenceRuntimeCallbacks,
    *,
    run_id: str,
    incident_id: str,
    policy: Mapping[str, Any],
    request_id: str,
    stage: str,
    status: str,
    subject: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None = None,
) -> None:
    existing = stores.workflow_records.get(run_id, {})
    record = {
        "schemaVersion": "v1",
        "createdAt": existing.get("createdAt") or callbacks.now_rfc3339(),
        "incidentId": incident_id,
        "lastUpdatedAt": callbacks.now_rfc3339(),
        "policy": callbacks.redact_sensitive(dict(policy)),
        "requestId": request_id,
        "runId": run_id,
        "stage": stage,
        "status": status,
        "subject": callbacks.redact_sensitive(dict(subject or callbacks.safe_subject(None))),
        "target": callbacks.redact_sensitive(dict(target or existing.get("target") or {})),
    }
    callbacks.bounded_put(stores.workflow_records, run_id, record, config.workflow_max_records)


def truncate_chat_text(callbacks: PersistenceRuntimeCallbacks, value: Any, limit: int) -> str:
    text = callbacks.redact_sensitive(str(value or ""))
    if len(text) <= limit:
        return text
    return f"{text[:limit].rstrip()}\n[TRUNCATED {len(text) - limit} chars]"


def chat_action_record_refs(
    stores: PersistenceRuntimeStores,
    incident_id: str,
    run_id: str,
) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for store_name, store in (
        ("actionProposals", stores.action_proposals),
        ("sealedActionPlans", stores.sealed_action_plans),
        ("approvalDecisions", stores.approval_decisions),
        ("executionRecords", stores.execution_records),
    ):
        for record in store.values():
            spec = record.get("spec") if isinstance(record.get("spec"), Mapping) else {}
            if not isinstance(spec, Mapping):
                continue
            if str(spec.get("runId") or "") != run_id and str(spec.get("incidentId") or "") != incident_id:
                continue
            metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
            status = spec.get("status") if isinstance(spec.get("status"), Mapping) else {}
            refs.append(
                {
                    "kind": record.get("kind"),
                    "name": metadata.get("name") or "",
                    "store": store_name,
                    "createdAt": metadata.get("createdAt") or "",
                    "phase": status.get("phase") or "",
                }
            )
    refs.sort(key=lambda item: str(item.get("createdAt") or ""))
    return refs


def build_chat_transcript_record(
    config: PersistenceRuntimeConfig,
    stores: PersistenceRuntimeStores,
    callbacks: PersistenceRuntimeCallbacks,
    *,
    req: ChatRequestLike,
    answer_text: str,
    answer_contracts: list[str],
    incident_id: str,
    policy: Mapping[str, Any],
    request_id: str,
    rca_context: Mapping[str, Any] | None,
    run_id: str,
    runtime_tool_plan: Mapping[str, Any] | None,
    status: str,
    subject: Mapping[str, Any],
    truncate_text: Callable[[Any, int], str] | None = None,
    action_record_refs: Callable[[str, str], list[dict[str, Any]]] | None = None,
) -> Record:
    created_at = callbacks.now_rfc3339()
    context = rca_context if isinstance(rca_context, Mapping) else {}
    context_metadata = context.get("metadata") if isinstance(context.get("metadata"), Mapping) else {}
    evidence = context.get("evidence") if isinstance(context.get("evidence"), Mapping) else {}
    rca_result = context.get("rcaResult") if isinstance(context.get("rcaResult"), Mapping) else {}
    tool_plan_digest = (
        str(context_metadata.get("toolPlanDigest") or "")
        if context_metadata.get("toolPlanDigest")
        else callbacks.canonical_digest(runtime_tool_plan)
        if isinstance(runtime_tool_plan, Mapping)
        else ""
    )
    rca_context_digest = str(context_metadata.get("digest") or "")
    answer_mode = (
        "action_plan"
        if "aiops-action-v0.1.9" in answer_contracts
        or "natural-action-plan-v0.2.1" in answer_contracts
        or str(policy.get("decision") or "") == "action_proposal_only"
        else "human_rca"
    )
    transcript_projection = {
        "answer": answer_text,
        "conversationId": req.conversationId,
        "requestId": request_id,
        "runId": run_id,
        "userMessage": req.message,
    }
    digest = callbacks.canonical_digest(callbacks.redact_sensitive(transcript_projection))
    transcript_id = f"chat-transcript-{digest.removeprefix('sha256:')[:16]}"
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ChatTranscriptRecord",
        "metadata": {"createdAt": created_at, "name": transcript_id},
        "spec": {
            "answerContract": list(dict.fromkeys(answer_contracts)),
            "answerMode": answer_mode,
            "assistantAnswer": (truncate_text or (lambda value, limit: truncate_chat_text(callbacks, value, limit)))(
                answer_text,
                config.chat_transcript_max_answer_chars,
            ),
            "attachments": len(req.attachments),
            "conversationId": req.conversationId or incident_id,
            "evidenceRefs": {
                "collected": callbacks.redact_sensitive(evidence.get("collectedRefs", [])),
                "failed": callbacks.redact_sensitive(evidence.get("failedRefs", [])),
                "missing": callbacks.redact_sensitive(evidence.get("missing", [])),
            },
            "rcaContextDigest": rca_context_digest,
            "observedState": {
                "evidenceSummary": callbacks.redact_sensitive(evidence.get("summary", {})),
                "rcaContextDigest": rca_context_digest,
                "rcaResult": callbacks.redact_sensitive(rca_result),
                "taskType": runtime_tool_plan.get("task_type") if isinstance(runtime_tool_plan, Mapping) else "",
                "toolPlanDigest": tool_plan_digest,
            },
            "policy": callbacks.redact_sensitive(dict(policy)),
            "requestId": request_id,
            "runId": run_id,
            "status": status,
            "toolPlanDigest": tool_plan_digest,
            "userMessage": (truncate_text or (lambda value, limit: truncate_chat_text(callbacks, value, limit)))(
                req.message,
                config.chat_transcript_max_message_chars,
            ),
            "workflow": {
                "actionRecords": (
                    action_record_refs or (lambda incident, run: chat_action_record_refs(stores, incident, run))
                )(incident_id, run_id),
                "incidentId": incident_id,
            },
        },
        "subject": callbacks.redact_sensitive(dict(subject)),
    }


async def persist_chat_transcript_record(
    callbacks: PersistenceRuntimeCallbacks,
    record: Record,
    put_record: Callable[[str, str, Record], Awaitable[None]],
    append_jsonl: Callable[[Mapping[str, Any]], Awaitable[None]],
) -> None:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    transcript_id = str(metadata.get("name") or f"chat-transcript-{uuid.uuid4().hex[:16]}")
    await put_record("chatTranscripts", transcript_id, record)
    await append_jsonl(record)
    callbacks.increment_metric("aiops_chat_transcripts_total")


def write_chat_transcript_jsonl(
    config: PersistenceRuntimeConfig,
    callbacks: PersistenceRuntimeCallbacks,
    record: Mapping[str, Any],
) -> None:
    if not config.chat_transcript_jsonl_path:
        return
    path = Path(config.chat_transcript_jsonl_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps(
                callbacks.redact_sensitive(dict(record)),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        handle.write("\n")


async def append_chat_transcript_jsonl(
    callbacks: PersistenceRuntimeCallbacks,
    record: Mapping[str, Any],
    write_jsonl: Callable[[Mapping[str, Any]], None],
) -> None:
    try:
        await asyncio.to_thread(write_jsonl, record)
    except Exception:
        callbacks.increment_metric("aiops_chat_transcript_jsonl_write_failures_total")


def can_subject_read_record(record: Mapping[str, Any], subject: Mapping[str, Any]) -> bool:
    record_subject = record.get("originatingSubject") or record.get("subject") or {}
    if not isinstance(record_subject, Mapping):
        return False
    return (
        record_subject.get("username") == subject.get("username")
        and record_subject.get("uid") == subject.get("uid")
        and record_subject.get("groupsDigest") == subject.get("groupsDigest")
    )
