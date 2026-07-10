import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

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


@dataclass(frozen=True, slots=True)
class SpecialActionRecordConfig:
    cluster_id: str
    runbook_registry_entries: Mapping[str, dict[str, Any]]
    runbook_registry_digest: str
    preapproved_patch_field_schemas: Mapping[str, dict[str, Any]]
    preapproved_patch_field_digest: str
    break_glass_profiles: Mapping[str, dict[str, Any]]
    break_glass_profile_digest: str


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


def get_runbook_entry(runbook_id: str, config: SpecialActionRecordConfig) -> dict[str, Any]:
    entry = config.runbook_registry_entries.get(runbook_id)
    if not entry:
        raise HTTPException(status_code=400, detail="Runbook is not in the configured registry")
    return entry


def platform_namespace_requires_explicit_policy(namespace: str) -> bool:
    return namespace.startswith(("kube-", "openshift-"))


def evaluate_runbook_policy(
    runbook: Mapping[str, Any],
    target: Any,
    policy: Mapping[str, Any],
    namespace_requires_explicit_policy: Callable[[str], bool] = platform_namespace_requires_explicit_policy,
) -> dict[str, Any]:
    checks = runbook.get("policyChecks") if isinstance(runbook.get("policyChecks"), Mapping) else {}
    failures: list[str] = []
    warnings: list[str] = []
    if checks.get("namespaceRequired") and not target.namespace:
        failures.append("namespace is required")
    if checks.get("targetUidRequired") and not target.uid:
        failures.append("target uid is required")
    if target.kind != runbook.get("targetKind"):
        failures.append(f"target kind must be {runbook.get('targetKind')}")
    if checks.get("platformNamespaceRequiresExplicitPolicy") and namespace_requires_explicit_policy(
        target.namespace
    ):
        if policy.get("allowPlatformNamespace") is not True:
            failures.append("platform namespace requires explicit policy allowPlatformNamespace=true")
    if checks.get("ownerReviewRequired"):
        warnings.append("owner, GitOps, Operator, and external controller review required before execution")
    if checks.get("hpaReviewRequired"):
        warnings.append("HPA ownership review required before bounded scale execution")
    if checks.get("hpaPolicyReviewRequired"):
        warnings.append("HPA min/max bounds and targetRef review required before execution")
    if checks.get("rollbackRevisionReviewRequired"):
        warnings.append("ReplicaSet revision, image digest, and template diff review required before rollback")
    if checks.get("controllerOwnerRequired"):
        warnings.append("controller owner reference must be verified before eviction execution")
    if checks.get("pdbReviewRequired"):
        warnings.append("PDB allowance must be verified before eviction execution")
    return {
        "decision": "denied" if failures else "requires_approval",
        "failures": failures,
        "warnings": warnings,
    }


def build_runbook_plan_record(
    request: Any,
    subject: Mapping[str, Any],
    config: SpecialActionRecordConfig,
    *,
    runbook_lookup: Callable[[str], dict[str, Any]],
    policy_evaluator: Callable[[Mapping[str, Any], Any, Mapping[str, Any]], dict[str, Any]],
    action_proposal_factory: Callable[..., Any],
    candidate_builder: Callable[[Any, Mapping[str, Any]], dict[str, Any]],
) -> dict[str, Any]:
    runbook = runbook_lookup(request.runbookId)
    policy = default_policy_binding(request.policy)
    policy_result = policy_evaluator(runbook, request.target, request.policy)
    step_plans: list[dict[str, Any]] = []
    for step in runbook["allowedSteps"]:
        action_request = action_proposal_factory(
            incidentId=request.incidentId,
            runId=request.runId,
            toolName=step["toolName"],
            toolVersion=step["toolVersion"],
            target=request.target,
            parameters=request.parameters,
            evidenceRefs=request.evidenceRefs,
            runbookRefs=[
                {
                    "id": runbook["runbookId"],
                    "version": runbook["runbookVersion"],
                    "contentDigest": config.runbook_registry_digest,
                }
            ],
            policy=policy,
        )
        candidate = candidate_builder(action_request, subject)
        step_plans.append(
            {
                "stepId": step["stepId"],
                "toolName": step["toolName"],
                "toolVersion": step["toolVersion"],
                "candidateActionRequest": candidate,
                "candidateRequestDigest": candidate_action_request_digest(candidate),
            }
        )

    plan_digest = canonical_digest(
        {
            "runbook": {
                "runbookId": runbook["runbookId"],
                "runbookVersion": runbook["runbookVersion"],
                "registryDigest": config.runbook_registry_digest,
            },
            "stepPlans": step_plans,
            "target": request.target.model_dump(),
            "policy": policy,
        }
    )
    plan_id = f"runbook-plan-{plan_digest.removeprefix('sha256:')[:16]}"
    created_at = now_rfc3339()
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "RunbookPlanRecord",
        "metadata": {"name": plan_id, "createdAt": created_at},
        "spec": {
            "runbook": {
                "runbookId": runbook["runbookId"],
                "runbookVersion": runbook["runbookVersion"],
                "incidentClass": runbook["incidentClass"],
                "registryDigest": config.runbook_registry_digest,
            },
            "target": request.target.model_dump(),
            "stepPlans": step_plans,
            "policy": policy,
            "policyResult": policy_result,
            "evidenceRefs": redact_sensitive(request.evidenceRefs),
            "incidentId": request.incidentId,
            "runId": request.runId,
            "digest": {
                "runbookPlanDigest": plan_digest,
                "canonicalization": "stable-json-sort-keys",
            },
            "status": {"phase": "denied" if policy_result["failures"] else "waiting_for_approval"},
        },
        "subject": redact_sensitive(dict(subject)),
    }


def get_preapproved_patch_schema(field_schema_id: str, config: SpecialActionRecordConfig) -> dict[str, Any]:
    schema = config.preapproved_patch_field_schemas.get(field_schema_id)
    if not schema:
        raise HTTPException(status_code=400, detail="Field schema is not preapproved")
    return schema


def validate_preapproved_patch_value(schema: Mapping[str, Any], target: Any, value: Any) -> None:
    if target.kind != schema.get("targetKind"):
        raise HTTPException(status_code=400, detail=f"Patch target kind must be {schema.get('targetKind')}")
    if target.apiVersion != schema.get("apiVersion"):
        raise HTTPException(status_code=400, detail=f"Patch target apiVersion must be {schema.get('apiVersion')}")
    if schema.get("valueType") == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise HTTPException(status_code=400, detail="Preapproved patch value must be an integer")
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if isinstance(minimum, int) and value < minimum:
            raise HTTPException(status_code=400, detail="Preapproved patch value is below the documented minimum")
        if isinstance(maximum, int) and value > maximum:
            raise HTTPException(status_code=400, detail="Preapproved patch value exceeds the documented maximum")


def build_preapproved_patch_record(
    request: Any,
    subject: Mapping[str, Any],
    config: SpecialActionRecordConfig,
    *,
    schema_lookup: Callable[[str], dict[str, Any]],
    value_validator: Callable[[Mapping[str, Any], Any, Any], None],
) -> dict[str, Any]:
    schema = schema_lookup(request.fieldSchemaId)
    value_validator(schema, request.target, request.value)
    policy = default_policy_binding(request.policy)
    request_projection = {
        "schemaVersion": "v1",
        "clusterId": config.cluster_id,
        "requester": redact_sensitive(dict(subject)),
        "target": request.target.model_dump(),
        "fieldSchema": schema,
        "value": redact_sensitive(request.value),
        "policy": policy,
        "evidenceRefs": redact_sensitive(request.evidenceRefs),
    }
    request_digest = canonical_digest(request_projection)
    request_id = f"prepatch-{request_digest.removeprefix('sha256:')[:16]}"
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "PatchPreapprovedFieldRequestRecord",
        "metadata": {"name": request_id, "createdAt": now_rfc3339()},
        "spec": {
            "fieldSchema": schema,
            "target": request.target.model_dump(),
            "value": redact_sensitive(request.value),
            "patch": {
                "op": "replace",
                "path": schema["jsonPointer"],
                "value": redact_sensitive(request.value),
            },
            "policy": policy,
            "evidenceRefs": redact_sensitive(request.evidenceRefs),
            "incidentId": request.incidentId,
            "runId": request.runId,
            "digest": {
                "patchRequestDigest": request_digest,
                "schemaBundleDigest": config.preapproved_patch_field_digest,
                "canonicalization": "stable-json-sort-keys",
            },
            "status": {
                "phase": "waiting_for_approval",
                "mutationSubmitted": False,
                "reason": "patch_preapproved_field is a documented request only until Action Executor integration.",
            },
        },
        "subject": redact_sensitive(dict(subject)),
    }


def get_break_glass_profile(profile_id: str, config: SpecialActionRecordConfig) -> dict[str, Any]:
    profile = config.break_glass_profiles.get(profile_id)
    if not profile:
        raise HTTPException(status_code=400, detail="Break-glass profile is not configured")
    return profile


def build_break_glass_request_record(
    request: Any,
    subject: Mapping[str, Any],
    config: SpecialActionRecordConfig,
    *,
    profile_lookup: Callable[[str], dict[str, Any]],
) -> dict[str, Any]:
    profile = profile_lookup(request.profileId)
    policy = default_policy_binding(request.policy)
    request_projection = {
        "schemaVersion": "v1",
        "clusterId": config.cluster_id,
        "requester": redact_sensitive(dict(subject)),
        "profile": {
            "profileId": profile["profileId"],
            "profileVersion": profile["profileVersion"],
            "profileDigest": config.break_glass_profile_digest,
            "imageDigest": profile["imageDigest"],
            "fixedEntrypoint": profile["fixedEntrypoint"],
        },
        "targetNode": request.targetNode.model_dump(),
        "justificationDigest": canonical_digest(redact_sensitive(request.justification)),
        "policy": policy,
        "evidenceRefs": redact_sensitive(request.evidenceRefs),
    }
    request_digest = canonical_digest(request_projection)
    request_id = f"breakglass-{request_digest.removeprefix('sha256:')[:16]}"
    enabled = bool(profile.get("enabled"))
    phase = "pending_privileged_job_controller" if enabled else "disabled"
    reason = (
        "Break-glass profile is enabled and ready for a dedicated controller."
        if enabled
        else "Break-glass host operations are disabled by configuration or missing fixed image digest."
    )
    return {
        "schemaVersion": "v1",
        "apiVersion": "aiops.komsco/v1",
        "kind": "BreakGlassRequestRecord",
        "metadata": {"name": request_id, "createdAt": now_rfc3339()},
        "spec": {
            "profile": {
                "profileId": profile["profileId"],
                "profileVersion": profile["profileVersion"],
                "profileDigest": config.break_glass_profile_digest,
                "enabled": enabled,
                "imageDigest": profile["imageDigest"],
                "fixedEntrypoint": profile["fixedEntrypoint"],
                "arbitraryCommandInputAllowed": False,
            },
            "targetNode": request.targetNode.model_dump(),
            "justificationDigest": canonical_digest(redact_sensitive(request.justification)),
            "policy": policy,
            "evidenceRefs": redact_sensitive(request.evidenceRefs),
            "incidentId": request.incidentId,
            "runId": request.runId,
            "jobTemplateConstraints": {
                "privilegedJob": profile["privilegedJob"],
                "scheduling": {
                    **profile["scheduling"],
                    "targetNodeName": request.targetNode.name,
                    "targetNodeUid": request.targetNode.uid,
                },
                "network": profile["network"],
                "cleanup": profile["cleanup"],
            },
            "digest": {
                "breakGlassRequestDigest": request_digest,
                "profileBundleDigest": config.break_glass_profile_digest,
                "canonicalization": "stable-json-sort-keys",
            },
            "audit": profile["audit"],
            "status": {
                "phase": phase,
                "jobSubmitted": False,
                "arbitraryCommandRejected": True,
                "reason": reason,
            },
        },
        "subject": redact_sensitive(dict(subject)),
    }
