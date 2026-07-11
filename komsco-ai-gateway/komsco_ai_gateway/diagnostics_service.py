from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import httpx
from fastapi import HTTPException

from .aiops_core import AiopsCoreError
from .schemas import DiagnosticRequestCreate


@dataclass(frozen=True)
class DiagnosticsConfig:
    cluster_id: str
    diagnostics_enabled: bool
    controller_url: str
    controller_shared_token: str
    collector_registry_version: str
    collector_registry_digest: str
    request_digest_fields: Sequence[str]


@dataclass(frozen=True)
class DiagnosticsDependencies:
    config: DiagnosticsConfig
    diagnostic_requests: Mapping[str, dict[str, Any]]
    collectors: Mapping[str, dict[str, Any]]
    verify_bearer_header: Callable[..., str]
    fetch_self_subject_review: Callable[..., Any]
    can_subject_read_record: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]
    get_host_diagnostic_collector: Callable[[str], dict[str, Any]]
    canonical_digest: Callable[[Any], str]
    redact_sensitive: Callable[[Any], Any]
    now_rfc3339: Callable[[], str]
    bounded_put_record: Callable[..., Any]
    increment_metric: Callable[[str], None]


def diagnostic_request_digest(
    candidate: Mapping[str, Any],
    deps: DiagnosticsDependencies,
) -> str:
    projection = {
        field: candidate.get(field) for field in deps.config.request_digest_fields
    }
    return deps.canonical_digest(deps.redact_sensitive(projection))


def build_diagnostic_request_candidate(
    request: DiagnosticRequestCreate,
    subject: Mapping[str, Any],
    deps: DiagnosticsDependencies,
) -> dict[str, Any]:
    try:
        collector_profile = deps.get_host_diagnostic_collector(request.collector)
    except AiopsCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if request.collectorVersion != collector_profile["collectorVersion"]:
        raise HTTPException(status_code=400, detail="collectorVersion does not match the registry")
    if request.collectorProfile != collector_profile["collectorProfile"]:
        raise HTTPException(status_code=400, detail="collectorProfile does not match the registry")
    return {
        "schemaVersion": "v1",
        "clusterId": deps.config.cluster_id,
        "requester": deps.redact_sensitive(dict(subject)),
        "targetNode": request.targetNode.model_dump(),
        "collector": request.collector,
        "collectorVersion": request.collectorVersion,
        "collectorProfile": request.collectorProfile,
        "collectorRegistry": {
            "version": deps.config.collector_registry_version,
            "digest": deps.config.collector_registry_digest,
        },
        "collectorConstraints": collector_profile,
        "timeRange": request.timeRange.model_dump(),
        "limits": request.limits.model_dump(),
        "evidencePolicy": request.evidencePolicy.model_dump(),
        "policy": deps.redact_sensitive(dict(request.policy)),
    }


def build_diagnostic_request_record(
    request: DiagnosticRequestCreate,
    subject: Mapping[str, Any],
    deps: DiagnosticsDependencies,
) -> dict[str, Any]:
    candidate = build_diagnostic_request_candidate(request, subject, deps)
    request_digest = diagnostic_request_digest(candidate, deps)
    request_id = f"diag-{request_digest.removeprefix('sha256:')[:16]}"
    grant_reference_digest = deps.canonical_digest(
        {
            "audience": "aiops-host-diagnostics-controller",
            "requestDigest": request_digest,
            "requestId": request_id,
        }
    )
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequestRecord",
        "metadata": {"name": request_id, "createdAt": deps.now_rfc3339()},
        "spec": {
            "candidate": candidate,
            "diagnosticRequestDigest": request_digest,
            "digestSchema": {
                "name": "diagnostic-request-digest-v1",
                "canonicalization": "stable-json-sort-keys",
                "includedFields": list(deps.config.request_digest_fields),
            },
            "grantRef": {
                "grantId": f"diag-grant-{request_digest.removeprefix('sha256:')[:16]}",
                "grantDigest": grant_reference_digest,
                "bearerGrantStored": False,
            },
            "incidentId": request.incidentId,
            "runId": request.runId,
            "status": {
                "phase": "pending_controller_submission"
                if deps.config.diagnostics_enabled
                else "disabled",
                "reason": (
                    "Host diagnostics controller submission is enabled."
                    if deps.config.diagnostics_enabled
                    else "Host diagnostics controller submission is disabled by configuration."
                ),
                "submittedToController": False,
            },
        },
        "subject": deps.redact_sensitive(dict(subject)),
    }


async def submit_diagnostic_request_to_controller(
    record: dict[str, Any],
    deps: DiagnosticsDependencies,
) -> dict[str, Any]:
    status = record["spec"]["status"]
    config = deps.config
    if not config.diagnostics_enabled:
        return record
    if not config.controller_url:
        status.update(
            {
                "phase": "controller_unconfigured",
                "reason": "Host diagnostics controller URL is not configured.",
                "submittedToController": False,
            }
        )
        return record

    headers: dict[str, str] = {}
    if config.controller_shared_token:
        headers["Authorization"] = f"Bearer {config.controller_shared_token}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0)) as client:
            response = await client.post(
                f"{config.controller_url}/v1/controller/diagnostics/requests",
                headers=headers,
                json={"diagnosticRequest": record},
            )
    except httpx.HTTPError as exc:
        status.update(
            {
                "phase": "controller_submission_failed",
                "reason": f"Host diagnostics controller request failed: {exc.__class__.__name__}",
                "submittedToController": False,
            }
        )
        return record

    if response.status_code >= 400:
        status.update(
            {
                "phase": "controller_submission_failed",
                "reason": f"Host diagnostics controller returned HTTP {response.status_code}",
                "submittedToController": False,
                "controllerError": deps.redact_sensitive(response.text[:1000]),
            }
        )
        return record
    try:
        controller_result = response.json()
    except ValueError:
        controller_result = {"raw": response.text[:1000]}
    status.update(
        {
            "phase": "controller_submitted",
            "reason": "Host diagnostics controller accepted the request.",
            "submittedToController": True,
            "controllerSubmission": deps.redact_sensitive(controller_result),
        }
    )
    return record


def compact_controller_submission(
    controller_result: Mapping[str, Any],
    deps: DiagnosticsDependencies,
) -> dict[str, Any]:
    compacted = deps.redact_sensitive(dict(controller_result))
    spec = compacted.get("spec") if isinstance(compacted.get("spec"), Mapping) else {}
    collector_pod = spec.get("collectorPod") if isinstance(spec.get("collectorPod"), Mapping) else {}
    log_preview = collector_pod.get("logPreview")
    if isinstance(log_preview, str):
        collector_pod["logPreviewDigest"] = deps.canonical_digest(log_preview)
        collector_pod["logPreviewBytes"] = len(log_preview.encode("utf-8"))
        collector_pod.pop("logPreview", None)
    return compacted


def normalize_controller_phase(phase: str) -> str:
    return "succeeded" if phase == "completed" else phase


async def refresh_diagnostic_request_from_controller(
    record: dict[str, Any],
    deps: DiagnosticsDependencies,
) -> dict[str, Any]:
    status = record["spec"]["status"]
    config = deps.config
    if not config.diagnostics_enabled or not config.controller_url:
        return record
    if status.get("submittedToController") is not True:
        return record
    request_id = str(record["metadata"]["name"])
    headers: dict[str, str] = {}
    if config.controller_shared_token:
        headers["Authorization"] = f"Bearer {config.controller_shared_token}"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(20.0, connect=5.0)) as client:
            response = await client.get(
                f"{config.controller_url}/v1/controller/diagnostics/requests/{request_id}",
                headers=headers,
            )
    except httpx.HTTPError:
        return record
    if response.status_code >= 400:
        return record
    try:
        controller_result = response.json()
    except ValueError:
        return record
    controller_spec = controller_result.get("spec") if isinstance(controller_result, Mapping) else {}
    phase = controller_spec.get("phase") if isinstance(controller_spec, Mapping) else None
    if isinstance(phase, str) and phase:
        status["phase"] = f"collector_{normalize_controller_phase(phase)}"
    status["controllerSubmission"] = compact_controller_submission(controller_result, deps)
    return record


def get_diagnostic_collectors(
    authorization: str | None,
    deps: DiagnosticsDependencies,
) -> dict[str, Any]:
    deps.verify_bearer_header(authorization)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "HostDiagnosticCollectorRegistry",
        "metadata": {
            "name": "host-diagnostic-collector-registry",
            "version": deps.config.collector_registry_version,
        },
        "spec": {
            "digest": deps.config.collector_registry_digest,
            "diagnosticsEnabled": deps.config.diagnostics_enabled,
            "controllerConfigured": bool(deps.config.controller_url),
            "collectors": list(deps.collectors.values()),
        },
    }


async def create_diagnostic_request(
    req: DiagnosticRequestCreate,
    authorization: str | None,
    deps: DiagnosticsDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = build_diagnostic_request_record(req, subject, deps)
    record = await submit_diagnostic_request_to_controller(record, deps)
    request_id = str(record["metadata"]["name"])
    await deps.bounded_put_record("diagnosticRequests", request_id, record)
    deps.increment_metric("aiops_diagnostic_requests_total")
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }


async def get_diagnostic_request(
    request_id: str,
    authorization: str | None,
    deps: DiagnosticsDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.diagnostic_requests.get(request_id)
    if not record or not deps.can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Diagnostic request not found")
    record = await refresh_diagnostic_request_from_controller(record, deps)
    await deps.bounded_put_record("diagnosticRequests", request_id, record)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "DiagnosticRequest",
        "metadata": record["metadata"],
        "spec": record["spec"],
    }
