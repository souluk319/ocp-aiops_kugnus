from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass(frozen=True)
class EvidenceStores:
    evidence: Mapping[str, dict[str, Any]]
    workflows: Mapping[str, dict[str, Any]]


@dataclass(frozen=True)
class EvidenceDependencies:
    stores: EvidenceStores
    verify_bearer_header: Callable[..., str]
    fetch_self_subject_review: Callable[..., Any]
    can_subject_read_record: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]


async def auth_subject(
    authorization: str | None,
    deps: EvidenceDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    return await deps.fetch_self_subject_review(user_auth_header)


async def list_evidence(
    authorization: str | None,
    incident_id: str | None,
    run_id: str | None,
    deps: EvidenceDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    items = []
    for record in deps.stores.evidence.values():
        if incident_id and record.get("incidentId") != incident_id:
            continue
        if run_id and record.get("runId") != run_id:
            continue
        if not deps.can_subject_read_record(record, subject):
            continue
        items.append({key: value for key, value in record.items() if key != "detail"})

    return {
        "apiVersion": "aiops.komsco/v1",
        "items": items,
        "kind": "EvidenceReferenceList",
    }


async def get_evidence(
    evidence_id: str,
    authorization: str | None,
    deps: EvidenceDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.stores.evidence.get(evidence_id)
    if not record or not deps.can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Evidence not found")

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "Evidence",
        "metadata": {"name": evidence_id},
        "spec": record,
    }


async def get_workflow(
    run_id: str,
    authorization: str | None,
    deps: EvidenceDependencies,
) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.stores.workflows.get(run_id)
    if not record or not deps.can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Workflow not found")

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "Workflow",
        "metadata": {"name": run_id},
        "spec": record,
    }
