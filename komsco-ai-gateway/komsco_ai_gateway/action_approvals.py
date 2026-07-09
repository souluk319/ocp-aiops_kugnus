import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from .action_parameters import ActionRecordContext
from .action_records import default_policy_binding, expires_at_rfc3339
from .gateway_state import APPROVAL_DECISIONS, EXECUTION_RECORDS, increment_metric
from .security import canonical_digest, now_rfc3339, redact_sensitive


@dataclass(frozen=True, slots=True)
class ApprovalDecisionRecordInput:
    plan_record: Mapping[str, Any]
    request: Any
    approver: Mapping[str, Any]
    action_access_review: Mapping[str, Any]
    context: ActionRecordContext
    allow_self_approval: bool = False
    auto_policy: bool = False


@dataclass(frozen=True, slots=True)
class ExecutionGrantInput:
    approval: Mapping[str, Any]
    plan: Mapping[str, Any]
    approver: Mapping[str, Any]
    context: ActionRecordContext


def same_observed_subject(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return (
        left.get("username") == right.get("username")
        and left.get("uid") == right.get("uid")
        and left.get("groupsDigest") == right.get("groupsDigest")
    )


def parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_approval_decision_record(record_input: ApprovalDecisionRecordInput) -> dict[str, Any]:
    plan = record_input.plan_record["spec"]["sealedActionPlan"]
    plan_digest = plan["digest"]["planDigest"]
    if record_input.request.expectedPlanDigest != plan_digest:
        raise HTTPException(status_code=409, detail="expectedPlanDigest does not match the sealed plan")
    requester = plan["metadata"]["requester"]
    if plan["safety"]["risk"] in {"medium", "high"} and same_observed_subject(requester, record_input.approver) and not record_input.allow_self_approval:
        raise HTTPException(status_code=409, detail="separation of duties requires requester and approver to differ")

    approval_id = f"approval-{uuid.uuid4()}"
    approved_at = now_rfc3339()
    expires_at = expires_at_rfc3339(timedelta(minutes=5))
    action = plan["action"]
    authorization = action.get("authorization") if isinstance(action.get("authorization"), Mapping) else {}
    attestation_claims = {
        "schemaVersion": "v1",
        "issuer": "aiops-tool-broker",
        "audience": "aiops-approval-api",
        "attestationId": f"authz-{uuid.uuid4()}",
        "issuedAt": approved_at,
        "notBefore": approved_at,
        "expiresAt": expires_at_rfc3339(timedelta(seconds=30)),
        "clusterId": record_input.context.cluster_id,
        "approver": redact_sensitive(dict(record_input.approver)),
        "planDigest": plan_digest,
        "action": {"toolName": action.get("toolName"), "toolVersion": action.get("toolVersion"), "actionRegistry": action.get("actionRegistry")},
        "target": plan["target"],
        "kubernetesAuthorization": {
            "apiGroup": authorization.get("apiGroup", ""),
            "resource": authorization.get("resource", ""),
            "subresource": authorization.get("subresource", ""),
            "verb": authorization.get("verb", ""),
        },
    }
    decision = {
        "approvalId": approval_id,
        "planDigest": plan_digest,
        "status": "approved",
        "approver": redact_sensitive(dict(record_input.approver)),
        "approvedAt": approved_at,
        "expiresAt": expires_at,
        "approvalScope": record_input.request.approvalScope,
        "target": plan["target"],
        "authorizationAttestationRef": {
            "attestationId": attestation_claims["attestationId"],
            "attestationDigest": canonical_digest(attestation_claims),
            "bearerAttestationStored": False,
            "issuer": attestation_claims["issuer"],
            "audience": attestation_claims["audience"],
        },
        "kubernetesAuthorization": {
            "apiGroup": authorization.get("apiGroup", ""),
            "resource": authorization.get("resource", ""),
            "subresource": authorization.get("subresource", ""),
            "verb": authorization.get("verb", ""),
            "ssarDecision": "allowed" if record_input.action_access_review.get("allowed") is True else "denied",
            "evaluatedAt": approved_at,
            "review": redact_sensitive(dict(record_input.action_access_review)),
        },
        "action": {"toolName": action.get("toolName"), "toolVersion": action.get("toolVersion"), "actionRegistry": action.get("actionRegistry")},
    }
    if record_input.auto_policy:
        decision["decidedBy"] = "auto-policy"
        decision["decisionPolicy"] = {"toolName": action.get("toolName"), "triggeredBy": "sealed-plan-creation"}
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "ApprovalDecisionRecord",
        "metadata": {"name": approval_id, "createdAt": approved_at},
        "spec": {"approvalDecision": decision},
        "subject": redact_sensitive(dict(record_input.approver)),
    }


def build_action_rejection_record(plan_record: Mapping[str, Any], request: Any, rejecter: Mapping[str, Any]) -> dict[str, Any]:
    plan = plan_record["spec"]["sealedActionPlan"]
    plan_digest = plan["digest"]["planDigest"]
    if request.expectedPlanDigest != plan_digest:
        raise HTTPException(status_code=409, detail="expectedPlanDigest does not match the sealed plan")
    rejected_at = now_rfc3339()
    rejection_id = f"rejection-{uuid.uuid4()}"
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "ApprovalDecisionRecord",
        "metadata": {"name": rejection_id, "createdAt": rejected_at},
        "spec": {
            "approvalDecision": {
                "approvalId": rejection_id,
                "planDigest": plan_digest,
                "status": "rejected",
                "approver": redact_sensitive(dict(rejecter)),
                "approvedAt": None,
                "rejectedAt": rejected_at,
                "reason": request.reason,
                "approvalScope": "single-target",
                "target": plan["target"],
                "action": {"toolName": plan["action"].get("toolName"), "toolVersion": plan["action"].get("toolVersion"), "actionRegistry": plan["action"].get("actionRegistry")},
            }
        },
        "subject": redact_sensitive(dict(rejecter)),
    }


def validate_execution_evidence_freshness(plan: Mapping[str, Any]) -> None:
    presentation = plan.get("approvalPresentation")
    if not isinstance(presentation, Mapping):
        return
    evidence_refs = presentation.get("evidenceRefs")
    if not isinstance(evidence_refs, list):
        return
    now = datetime.now(UTC)
    for evidence_ref in evidence_refs:
        if not isinstance(evidence_ref, Mapping):
            continue
        required_until = parse_rfc3339(evidence_ref.get("requiredFreshUntil"))
        if required_until and required_until < now:
            increment_metric("aiops_evidence_freshness_failures_total")
            raise HTTPException(status_code=409, detail="Sealed action plan evidence is no longer fresh; create a new plan and approval")


def validate_approval_is_active(approval_decision: Mapping[str, Any]) -> None:
    expires_at = parse_rfc3339(approval_decision.get("expiresAt"))
    if expires_at and expires_at < datetime.now(UTC):
        raise HTTPException(status_code=409, detail="Approval decision is expired")


def approval_already_executed(approval_id: str) -> bool:
    return any(
        record.get("spec", {}).get("approvalId") == approval_id
        for record in EXECUTION_RECORDS.values()
        if isinstance(record.get("spec"), Mapping)
    )


def record_created_at(record: Mapping[str, Any]) -> datetime | None:
    metadata = record.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    return parse_rfc3339(metadata.get("createdAt"))


def plan_has_approval_status(plan_digest: str, statuses: set[str], *, not_before: datetime | None = None) -> bool:
    return find_approval_by_plan_status(plan_digest, statuses, not_before=not_before) is not None


def find_approval_by_plan_status(
    plan_digest: str,
    statuses: set[str],
    *,
    not_before: datetime | None = None,
) -> dict[str, Any] | None:
    for record in APPROVAL_DECISIONS.values():
        if not_before is not None:
            created_at = record_created_at(record)
            if created_at is not None and created_at < not_before:
                continue
        spec = record.get("spec")
        decision = spec.get("approvalDecision") if isinstance(spec, Mapping) else None
        if isinstance(decision, Mapping) and decision.get("planDigest") == plan_digest and decision.get("status") in statuses:
            return record
    return None


def build_execution_grant_reference(grant_input: ExecutionGrantInput) -> dict[str, Any]:
    decision = grant_input.approval["spec"]["approvalDecision"]
    sealed_plan = grant_input.plan["spec"]["sealedActionPlan"]
    grant_id = f"exec-grant-{uuid.uuid4()}"
    issued_at = now_rfc3339()
    grant_claims = {
        "schemaVersion": "v1",
        "issuer": "aiops-approval-api",
        "audience": "aiops-action-executor",
        "grantId": grant_id,
        "issuedAt": issued_at,
        "notBefore": issued_at,
        "expiresAt": expires_at_rfc3339(timedelta(seconds=30)),
        "clusterId": grant_input.context.cluster_id,
        "planDigest": decision["planDigest"],
        "approvalId": decision["approvalId"],
        "approver": redact_sensitive(dict(grant_input.approver)),
        "action": decision["action"],
        "target": decision["target"],
        "kubernetesAuthorization": decision["kubernetesAuthorization"],
        "policyBundleHash": sealed_plan["safety"]["policy"]["policyBundleHash"],
    }
    return {"grantId": grant_id, "grantDigest": canonical_digest(grant_claims), "bearerGrantStored": False, "claims": grant_claims}
