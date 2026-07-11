import mimetypes
import os
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, UploadFile

from .rag_pgvector import RagDocumentUploadCreate, build_rag_upload_document
from .schemas import (
    BreakGlassRequestCreate,
    PatchPreapprovedFieldCreate,
    RagSearchCreate,
    RunbookPlanCreate,
)


@dataclass(frozen=True)
class KnowledgeConfig:
    runbook_registry_version: str
    runbook_registry_digest: str
    runbook_registry_entries: Mapping[str, dict[str, Any]]
    preapproved_patch_field_digest: str
    preapproved_patch_field_schemas: Mapping[str, dict[str, Any]]
    break_glass_profile_version: str
    break_glass_profile_digest: str
    break_glass_profiles: Mapping[str, dict[str, Any]]
    break_glass_enabled: bool
    latest_runtime_tool_plan: dict[str, Any] | None
    latest_rca_context: dict[str, Any] | None


@dataclass(frozen=True)
class KnowledgeStores:
    runbook_plans: Mapping[str, dict[str, Any]]
    preapproved_patch_requests: Mapping[str, dict[str, Any]]
    break_glass_requests: Mapping[str, dict[str, Any]]


@dataclass(frozen=True)
class KnowledgeDependencies:
    config: KnowledgeConfig
    stores: KnowledgeStores
    verify_bearer_header: Callable[..., str]
    fetch_self_subject_review: Callable[..., Any]
    can_subject_read_record: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]
    now_rfc3339: Callable[[], str]
    list_rag_upload_documents: Callable[..., tuple[str, str, list[dict[str, Any]]]]
    build_rag_backend_status: Callable[[], dict[str, Any]]
    persist_rag_upload_document: Callable[..., Any]
    extract_rag_upload_file_content: Callable[..., tuple[str, dict[str, Any]]]
    parse_rag_upload_form_labels: Callable[[str], dict[str, str]]
    search_rag_runbooks: Callable[..., Any]
    increment_metric: Callable[[str], None]
    build_runbook_plan_record: Callable[..., dict[str, Any]]
    build_preapproved_patch_record: Callable[..., dict[str, Any]]
    build_break_glass_request_record: Callable[..., dict[str, Any]]
    bounded_put_record: Callable[..., Any]
    log_break_glass_audit_record: Callable[[Mapping[str, Any]], None]
    build_trace_record: Callable[..., dict[str, Any]]


def get_runbook_registry(
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    deps.verify_bearer_header(authorization)
    config = deps.config
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookRegistry",
        "metadata": {"name": "restricted-runbook-registry", "version": config.runbook_registry_version},
        "spec": {
            "digest": config.runbook_registry_digest,
            "entries": list(config.runbook_registry_entries.values()),
            "preapprovedPatchFieldDigest": config.preapproved_patch_field_digest,
            "preapprovedPatchFieldSchemas": list(config.preapproved_patch_field_schemas.values()),
        },
    }


async def list_rag_uploads(
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    status, reason, documents = deps.list_rag_upload_documents(subject)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagUploadedDocumentList",
        "metadata": {"name": "uploaded-rag-documents", "generatedAt": deps.now_rfc3339()},
        "spec": {
            "status": status,
            "reason": reason,
            "backend": deps.build_rag_backend_status(),
            "documents": documents,
            "totals": {"documents": len(documents)},
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "rawContentReturned": False,
            },
        },
    }


async def create_rag_upload(
    req: RagDocumentUploadCreate,
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = build_rag_upload_document(req, subject)
    status, reason, document = await deps.persist_rag_upload_document(record)
    return _rag_upload_result(record, status, reason, document, deps)


async def create_rag_upload_file(
    file: UploadFile,
    authorization: str | None,
    labels: str,
    customer: str,
    namespace: str,
    run_id: str | None,
    source_type: str,
    source_uri: str | None,
    version: str,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    filename = os.path.basename(file.filename or "upload").strip() or "upload"
    mime_type = file.content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    raw = await file.read()
    content, parser_report = deps.extract_rag_upload_file_content(filename, mime_type, raw)
    requested_labels = deps.parse_rag_upload_form_labels(labels)
    parser_labels = {
        key: str(value).lower() if isinstance(value, bool) else str(value)
        for key, value in parser_report.items()
        if value is not None
    }
    req = RagDocumentUploadCreate(
        name=filename,
        mimeType=mime_type,
        content=content,
        sourceUri=source_uri,
        sourceType=source_type,
        customer=customer,
        namespace=namespace,
        version=version,
        labels={
            **requested_labels,
            **parser_labels,
            "source": requested_labels.get("source", "chat-attachment"),
        },
        runId=run_id,
    )
    record = build_rag_upload_document(req, subject)
    status, reason, document = await deps.persist_rag_upload_document(record)
    return _rag_upload_result(
        record,
        status,
        reason,
        document,
        deps,
        ingestion_report=parser_report,
    )


def _rag_upload_result(
    record: dict[str, Any],
    status: str,
    reason: str,
    document: dict[str, Any] | None,
    deps: KnowledgeDependencies,
    *,
    ingestion_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    spec = {
        "status": status,
        "reason": reason,
        "backend": deps.build_rag_backend_status(),
        "document": document or record["document"],
        "chunks": [
            {
                "chunkId": chunk["chunkId"],
                "chunkIndex": chunk["chunkIndex"],
                "textHash": chunk["textHash"],
                "checksum": chunk["checksum"],
                "charLength": len(chunk["content"]),
                "sourceUri": chunk["sourceUri"],
            }
            for chunk in record["chunks"]
        ],
        "safety": {
            "gatewayOnly": True,
            "directDatabaseAccessAllowed": False,
            "rawContentReturned": False,
            "redactionAppliedBeforeChunking": True,
        },
    }
    if ingestion_report is not None:
        spec["ingestionReport"] = ingestion_report
        spec["safety"]["parserBoundary"] = "gateway-multipart-upload"
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagUploadIngestionResult",
        "metadata": {"name": record["document"]["documentId"], "generatedAt": deps.now_rfc3339()},
        "spec": spec,
    }


async def search_rag_runbooks(
    req: RagSearchCreate,
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    backend = deps.build_rag_backend_status()
    request_id = f"rag-search-{uuid.uuid4()}"
    deps.increment_metric("aiops_rag_search_requests_total")
    search_status, reason, results = await deps.search_rag_runbooks(req, subject=subject)
    evidence_status = "collected" if results else ("missing" if search_status == "not_configured" else search_status)
    collected_refs = [
        result.get("evidenceRef", {})
        for result in results
        if isinstance(result.get("evidenceRef"), Mapping)
    ]
    missing = [] if collected_refs else [{"type": "runbook", "reason": reason}]
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "RagSearchResult",
        "metadata": {"name": request_id, "generatedAt": deps.now_rfc3339()},
        "spec": {
            "query": req.query,
            "topK": req.topK,
            "filters": req.filters.model_dump(),
            "includeContent": req.includeContent,
            "runId": req.runId or request_id,
            "status": search_status,
            "reason": reason,
            "backend": backend,
            "results": results,
            "evidence": {
                "type": "runbook",
                "status": evidence_status,
                "reason": reason,
                "collectedRefs": collected_refs,
                "missing": missing,
            },
            "safety": {
                "gatewayOnly": True,
                "directDatabaseAccessAllowed": False,
                "aclRequired": True,
                "mockResultsAreProductionEvidence": False,
            },
        },
    }


async def create_runbook_plan(
    req: RunbookPlanCreate,
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.build_runbook_plan_record(req, subject)
    plan_id = str(record["metadata"]["name"])
    await deps.bounded_put_record("runbookPlans", plan_id, record)
    deps.increment_metric("aiops_runbook_plans_total")
    return _record_response("RunbookPlan", record)


async def get_runbook_plan(
    plan_id: str,
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    record = await _read_owned_record(
        deps.stores.runbook_plans,
        plan_id,
        authorization,
        deps,
        "Runbook plan not found",
    )
    return _record_response("RunbookPlan", record)


async def create_preapproved_patch_request(
    req: PatchPreapprovedFieldCreate,
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.build_preapproved_patch_record(req, subject)
    request_id = str(record["metadata"]["name"])
    await deps.bounded_put_record("preapprovedPatchRequests", request_id, record)
    deps.increment_metric("aiops_preapproved_patch_requests_total")
    return _record_response("PatchPreapprovedFieldRequest", record)


async def get_preapproved_patch_request(
    request_id: str,
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    record = await _read_owned_record(
        deps.stores.preapproved_patch_requests,
        request_id,
        authorization,
        deps,
        "Preapproved patch request not found",
    )
    return _record_response("PatchPreapprovedFieldRequest", record)


def get_break_glass_profiles(
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    deps.verify_bearer_header(authorization)
    config = deps.config
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassProfileRegistry",
        "metadata": {"name": "break-glass-profile-registry", "version": config.break_glass_profile_version},
        "spec": {
            "enabled": config.break_glass_enabled,
            "digest": config.break_glass_profile_digest,
            "profiles": list(config.break_glass_profiles.values()),
        },
    }


async def create_break_glass_request(
    req: BreakGlassRequestCreate,
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.build_break_glass_request_record(req, subject)
    request_id = str(record["metadata"]["name"])
    await deps.bounded_put_record("breakGlassRequests", request_id, record)
    deps.increment_metric("aiops_break_glass_requests_total")
    deps.log_break_glass_audit_record(
        deps.build_trace_record(
            action="break_glass_request_recorded",
            incident_id=req.incidentId or request_id,
            policy=record["spec"]["policy"],
            request_id=request_id,
            run_id=req.runId or request_id,
            subject=subject,
            target={
                "profileId": req.profileId,
                "targetNode": req.targetNode.model_dump(),
                "phase": record["spec"]["status"]["phase"],
                "jobSubmitted": False,
            },
        )
    )
    return _record_response("BreakGlassRequest", record)


async def get_break_glass_request(
    request_id: str,
    authorization: str | None,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    record = await _read_owned_record(
        deps.stores.break_glass_requests,
        request_id,
        authorization,
        deps,
        "Break-glass request not found",
    )
    return _record_response("BreakGlassRequest", record)


def get_last_rca_context(
    authorization: str,
    deps: KnowledgeDependencies,
) -> dict[str, Any]:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Authorization header with Bearer token is required")
    if deps.config.latest_rca_context is None:
        raise HTTPException(status_code=404, detail="No RCA context available yet — send a chat message first")
    return {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "RcaContextSummary",
        "toolPlan": deps.config.latest_runtime_tool_plan,
        "rcaContext": deps.config.latest_rca_context,
    }


async def _read_owned_record(
    store: Mapping[str, dict[str, Any]],
    record_id: str,
    authorization: str | None,
    deps: KnowledgeDependencies,
    not_found_detail: str,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = store.get(record_id)
    if not record or not deps.can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail=not_found_detail)
    return record


def _record_response(kind: str, record: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": kind,
        "metadata": record["metadata"],
        "spec": record["spec"],
    }
