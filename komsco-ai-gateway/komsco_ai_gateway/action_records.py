import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from .action_parameters import ActionRecordContext, normalize_action_parameters
from .action_registry import (
    ACTION_REGISTRY_DIGEST,
    ACTION_REGISTRY_VERSION,
    get_action_registry_entry,
    validate_action_target,
)
from .security import canonical_digest, now_rfc3339, redact_sensitive, safe_subject


CANDIDATE_ACTION_DIGEST_FIELDS = (
    "schemaVersion",
    "clusterId",
    "requester",
    "target",
    "action",
    "policy",
)
SEALED_ACTION_PLAN_DIGEST_FIELDS = (
    "schemaVersion",
    "clusterId",
    "metadata",
    "target",
    "action",
    "safety",
    "approvalPresentation",
)


def default_policy_binding(policy: Mapping[str, Any]) -> dict[str, Any]:
    policy_projection = redact_sensitive(dict(policy))
    policy_digest = canonical_digest(policy_projection)
    return {
        "policyDecisionId": policy_projection.get("policyDecisionId") or "pd-local-foundation",
        "policyBundleHash": policy_projection.get("policyBundleHash") or "sha256:local-foundation",
        "policyInputDigest": policy_projection.get("policyInputDigest") or policy_digest,
        "policyDecisionDigest": policy_projection.get("policyDecisionDigest") or policy_digest,
    }


def subject_digest(subject: Mapping[str, Any]) -> str:
    return canonical_digest(
        {
            "groupsDigest": subject.get("groupsDigest"),
            "uid": subject.get("uid"),
            "username": subject.get("username"),
        }
    )


def normalized_parameters_digest(candidate: Mapping[str, Any]) -> str:
    action = candidate.get("action") if isinstance(candidate.get("action"), Mapping) else {}
    return canonical_digest(action.get("normalizedParameters") or {})


def policy_binding_digest(policy: Mapping[str, Any]) -> str:
    return canonical_digest(default_policy_binding(policy))


def candidate_action_request_digest(candidate: Mapping[str, Any]) -> str:
    projection = {field: candidate.get(field) for field in CANDIDATE_ACTION_DIGEST_FIELDS}
    return canonical_digest(redact_sensitive(projection))


def sealed_action_plan_digest(plan: Mapping[str, Any]) -> str:
    projection = {field: plan.get(field) for field in SEALED_ACTION_PLAN_DIGEST_FIELDS}
    return canonical_digest(redact_sensitive(projection))


def expires_at_rfc3339(delta: timedelta) -> str:
    return (datetime.now(UTC) + delta).isoformat()


def build_candidate_action_request(
    request: Any,
    subject: Mapping[str, Any],
    context: ActionRecordContext,
) -> dict[str, Any]:
    registry_entry = get_action_registry_entry(request.toolName, request.toolVersion)
    validate_action_target(registry_entry, request.target)
    return {
        "schemaVersion": "v1",
        "clusterId": context.cluster_id,
        "requester": redact_sensitive(dict(subject)),
        "target": request.target.model_dump(),
        "action": {
            "toolName": request.toolName,
            "toolVersion": request.toolVersion,
            "actionRegistry": {"version": ACTION_REGISTRY_VERSION, "digest": ACTION_REGISTRY_DIGEST},
            "authorization": registry_entry["authorization"],
            "request": registry_entry["request"],
            "normalizedParameters": normalize_action_parameters(registry_entry, request.parameters, context),
        },
        "policy": default_policy_binding(request.policy),
    }


def build_action_proposal_record(
    request: Any,
    subject: Mapping[str, Any],
    context: ActionRecordContext,
) -> dict[str, Any]:
    candidate = build_candidate_action_request(request, subject, context)
    candidate_digest = candidate_action_request_digest(candidate)
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionProposalRecord",
        "metadata": {"name": f"proposal-{candidate_digest.removeprefix('sha256:')[:16]}", "createdAt": now_rfc3339()},
        "spec": {
            "candidateActionRequest": candidate,
            "candidateRequestDigest": candidate_digest,
            "digestSchema": {
                "name": "candidate-action-request-digest-v1",
                "canonicalization": "stable-json-sort-keys",
                "includedFields": list(CANDIDATE_ACTION_DIGEST_FIELDS),
            },
            "evidenceRefs": redact_sensitive(request.evidenceRefs),
            "incidentId": request.incidentId,
            "operatorPresentation": {
                "expectedImpact": request.expectedImpact,
                "prerequisiteChecks": request.prerequisiteChecks,
                "problemSummary": request.problemSummary,
                "recommendationSteps": request.recommendationSteps,
                "verificationChecks": request.verificationChecks,
            },
            "runId": request.runId,
            "runbookRefs": redact_sensitive(request.runbookRefs),
            "sourceType": request.policy.get("sourceType"),
            "status": {"phase": "proposed"},
        },
        "subject": redact_sensitive(dict(subject)),
    }


def build_sealed_action_plan_record(proposal: Mapping[str, Any], context: ActionRecordContext) -> dict[str, Any]:
    spec = proposal.get("spec") if isinstance(proposal.get("spec"), Mapping) else {}
    candidate = spec.get("candidateActionRequest") if isinstance(spec.get("candidateActionRequest"), Mapping) else {}
    action = candidate.get("action") if isinstance(candidate.get("action"), Mapping) else {}
    target = candidate.get("target") if isinstance(candidate.get("target"), Mapping) else {}
    requester = candidate.get("requester") if isinstance(candidate.get("requester"), Mapping) else safe_subject(None)
    policy = candidate.get("policy") if isinstance(candidate.get("policy"), Mapping) else {}
    presentation = spec.get("operatorPresentation") if isinstance(spec.get("operatorPresentation"), Mapping) else {}
    registry = action.get("actionRegistry") if isinstance(action.get("actionRegistry"), Mapping) else {}
    registry_digest = registry.get("digest") or ""
    plan_id = f"plan-{uuid.uuid4()}"
    incident_id = spec.get("incidentId") or f"inc-{uuid.uuid4()}"
    created_at = now_rfc3339()
    expires_at = expires_at_rfc3339(timedelta(minutes=5))
    dry_run_projection = {
        "candidateRequestDigest": spec.get("candidateRequestDigest"),
        "decision": "not_executed_foundation",
        "mutationsEnabled": context.mutations_enabled,
    }
    validation_claims = {
        "schemaVersion": "v1",
        "issuer": "aiops-approval-api",
        "audience": "aiops-action-executor",
        "grantId": f"validation-{uuid.uuid4()}",
        "issuedAt": created_at,
        "notBefore": created_at,
        "expiresAt": expires_at_rfc3339(timedelta(seconds=30)),
        "maxUses": 1,
        "clusterId": context.cluster_id,
        "candidateRequestDigest": spec.get("candidateRequestDigest"),
        "normalizedParametersDigest": normalized_parameters_digest(candidate),
        "actionRegistryDigest": registry_digest,
        "requesterSubjectDigest": subject_digest(requester),
        "policyDecisionDigest": policy.get("policyDecisionDigest"),
        "policyBindingDigest": policy_binding_digest(policy),
        "action": {"toolName": action.get("toolName"), "toolVersion": action.get("toolVersion")},
        "target": target,
        "allowedOperation": "server_side_dry_run_only",
    }
    plan_validation_grant_ref = {
        "grantId": validation_claims["grantId"],
        "grantDigest": canonical_digest(validation_claims),
        "bearerGrantStored": False,
        "claimsDigest": canonical_digest(
            {
                "candidateRequestDigest": validation_claims["candidateRequestDigest"],
                "normalizedParametersDigest": validation_claims["normalizedParametersDigest"],
                "actionRegistryDigest": validation_claims["actionRegistryDigest"],
                "requesterSubjectDigest": validation_claims["requesterSubjectDigest"],
                "policyDecisionDigest": validation_claims["policyDecisionDigest"],
                "policyBindingDigest": validation_claims["policyBindingDigest"],
            }
        ),
    }
    plan = {
        "schemaVersion": "v1",
        "clusterId": context.cluster_id,
        "metadata": {
            "planId": plan_id,
            "incidentId": incident_id,
            "requester": requester,
            "idempotencyKey": f"idem-{uuid.uuid4()}",
            "createdAt": created_at,
            "apiCallTimeout": "30s",
            "verificationDeadline": "10m",
            "maxMutationAttempts": 1,
            "maxVerificationAttempts": 3,
        },
        "target": target,
        "action": action,
        "safety": {
            "risk": get_action_registry_entry(str(action.get("toolName")), str(action.get("toolVersion")))["risk"],
            "policy": default_policy_binding(policy),
            "planValidationGrantRef": plan_validation_grant_ref,
            "dryRun": {
                "requestDigest": canonical_digest(dry_run_projection),
                "normalizedDiffDigest": canonical_digest(dry_run_projection),
                "decision": "not_executed_foundation",
            },
            "preconditions": [
                {"type": "UIDEquals", "value": target.get("uid")},
                {"type": "ActionRegistryDigestEquals", "value": registry_digest},
                {"type": "RequiresFreshDryRun", "value": True},
            ],
            "hardPostconditions": [{"type": "ExecutionRecordTerminalState", "value": True}],
            "observationalPostconditions": [],
            "rollbackDescription": "No automatic rollback is generated by this foundation API.",
            "typedRollbackAction": None,
            "rollbackRequiresApproval": False,
            "rollbackPossible": False,
            "expiresAt": expires_at,
        },
        "approvalPresentation": {
            "impact": {
                "affectedWorkloads": 1,
                "affectedPods": None,
                "availabilityRisk": "unknown",
                "summaryDigest": canonical_digest({"action": action.get("toolName"), "target": target}),
            },
            "dryRun": {
                "normalizedDiffDigest": canonical_digest(dry_run_projection),
                "decision": "not_executed_foundation",
            },
            "evidenceRefs": spec.get("evidenceRefs") or [],
            "expectedImpact": presentation.get("expectedImpact"),
            "prerequisiteChecks": presentation.get("prerequisiteChecks") or [],
            "problemSummary": presentation.get("problemSummary"),
            "recommendationSteps": presentation.get("recommendationSteps") or [],
            "runbookRefs": spec.get("runbookRefs") or [],
            "verificationChecks": presentation.get("verificationChecks") or [],
        },
    }
    plan_digest = sealed_action_plan_digest(plan)
    plan["digest"] = {
        "planDigest": plan_digest,
        "canonicalization": "stable-json-sort-keys",
        "digestSchema": "sealed-action-plan-digest-v1",
        "includedFields": list(SEALED_ACTION_PLAN_DIGEST_FIELDS),
        "excludedFields": ["/digest"],
    }
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "SealedActionPlanRecord",
        "metadata": {"name": plan_id, "createdAt": created_at},
        "spec": {"sealedActionPlan": plan, "status": {"phase": "sealed"}},
        "subject": redact_sensitive(dict(requester)),
    }
