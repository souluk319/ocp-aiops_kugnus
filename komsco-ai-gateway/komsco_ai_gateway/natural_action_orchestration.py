from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
import uuid

import httpx


@dataclass(frozen=True)
class NaturalActionOrchestrationDependencies:
    openshift_api_url: str
    openshift_api_ca_file: Any
    mutations_enabled: bool
    sealed_action_plans: Mapping[str, dict[str, Any]]
    execution_records: Mapping[str, dict[str, Any]]
    action_target_type: Any
    action_proposal_create_type: Any
    approval_decision_create_type: Any
    approval_decision_record_input_type: Any
    execution_grant_input_type: Any
    parse_natural_action_intent: Callable[[Any], dict[str, Any] | None]
    resolve_natural_action_target: Callable[..., Awaitable[Mapping[str, Any]]]
    build_action_proposal_record: Callable[[Any, Mapping[str, Any]], dict[str, Any]]
    build_sealed_action_plan_record: Callable[[Mapping[str, Any]], dict[str, Any]]
    bounded_put_record: Callable[[str, str, dict[str, Any]], Awaitable[None]]
    increment_metric: Callable[[str], None]
    can_subject_read_record: Callable[[Mapping[str, Any], Mapping[str, Any]], bool]
    fetch_action_access_review: Callable[..., Awaitable[Mapping[str, Any]]]
    enforce_action_access_review: Callable[[Mapping[str, Any]], None]
    build_approval_decision_record: Callable[[Any], dict[str, Any]]
    validate_approval_is_active: Callable[[Mapping[str, Any]], None]
    validate_execution_evidence_freshness: Callable[[Mapping[str, Any]], None]
    build_execution_grant_reference: Callable[[Any], dict[str, Any]]
    action_record_context: Callable[[], Any]
    execute_action_with_executor: Callable[..., Awaitable[dict[str, Any]]]
    natural_action_executor_fallback_authorization: Callable[[], str]
    now_rfc3339: Callable[[], str]
    redact_sensitive: Callable[[Any], Any]


async def create_natural_action_plan(
    req: Any,
    authorization: str,
    subject: Mapping[str, Any],
    *,
    incident_id: str,
    run_id: str,
    dependencies: NaturalActionOrchestrationDependencies,
) -> dict[str, Any] | None:
    intent = dependencies.parse_natural_action_intent(req)
    if not intent:
        return None
    if not dependencies.openshift_api_url:
        return {
            "intent": intent,
            "status": "unavailable",
            "summary": "OpenShift API URL이 없어 Action Plan 대상을 확인하지 못했습니다.",
        }

    namespace = str(intent["namespace"])
    target_name = str(intent["targetName"])
    api_version = str(intent.get("apiVersion") or "apps/v1")
    kind = str(intent.get("kind") or "Deployment")
    async with httpx.AsyncClient(
        verify=dependencies.openshift_api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        resolved_target = await dependencies.resolve_natural_action_target(client, intent, authorization)

    if resolved_target.get("status") == "ambiguous":
        return {
            "candidates": resolved_target.get("candidates", []),
            "intent": intent,
            "status": "ambiguous",
            "summary": f"{kind} `{target_name}` 후보가 여러 namespace에서 발견되었습니다.",
        }
    if resolved_target.get("status") == "missing_namespace":
        return {
            "intent": intent,
            "status": "missing_namespace",
            "summary": f"{kind} `{target_name}` 조치에는 namespace가 필요합니다.",
        }
    live_target = resolved_target.get("target") if isinstance(resolved_target.get("target"), Mapping) else None
    if not live_target:
        return {
            "intent": intent,
            "status": "not_found",
            "summary": f"{kind} `{namespace}/{target_name}`를 찾지 못했습니다.",
        }

    metadata = live_target.get("metadata", {}) if isinstance(live_target.get("metadata"), Mapping) else {}
    namespace = str(metadata.get("namespace") or namespace)
    target_name = str(metadata.get("name") or target_name)
    intent = {
        **intent,
        "namespace": namespace,
        "targetName": target_name,
        "summary": f"{kind} `{namespace}/{target_name}` 조치",
    }
    target = dependencies.action_target_type(
        apiVersion=api_version,
        kind=kind,
        namespace=namespace,
        name=target_name,
        uid=str(metadata.get("uid") or ""),
    )
    proposal_request = dependencies.action_proposal_create_type(
        incidentId=incident_id,
        runId=run_id,
        toolName=str(intent["toolName"]),
        target=target,
        parameters=dict(intent["parameters"]),
        policy={"source": "natural-language-chat"},
    )
    proposal_record = dependencies.build_action_proposal_record(proposal_request, subject)
    proposal_id = str(proposal_record["metadata"]["name"])
    await dependencies.bounded_put_record("actionProposals", proposal_id, proposal_record)
    dependencies.increment_metric("aiops_action_proposals_total")

    plan_record = dependencies.build_sealed_action_plan_record(proposal_record)
    plan_id = str(plan_record["metadata"]["name"])
    await dependencies.bounded_put_record("sealedActionPlans", plan_id, plan_record)
    dependencies.increment_metric("aiops_action_plans_total")
    plan = plan_record["spec"]["sealedActionPlan"]
    return {
        "intent": intent,
        "parameters": intent["parameters"],
        "planDigest": plan["digest"]["planDigest"],
        "planId": plan_id,
        "proposalId": proposal_id,
        "risk": plan["safety"]["risk"],
        "status": "planned",
        "target": target.model_dump(),
    }


def action_plan_result_from_record(record: Mapping[str, Any]) -> dict[str, Any]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    sealed_plan = record.get("spec", {}).get("sealedActionPlan")
    if not isinstance(sealed_plan, Mapping):
        return {"status": "not_found"}
    action = sealed_plan.get("action") if isinstance(sealed_plan.get("action"), Mapping) else {}
    target = sealed_plan.get("target") if isinstance(sealed_plan.get("target"), Mapping) else {}
    parameters = action.get("normalizedParameters")
    parameters = parameters if isinstance(parameters, Mapping) else {}
    digest = sealed_plan.get("digest") if isinstance(sealed_plan.get("digest"), Mapping) else {}
    return {
        "intent": {
            "toolName": action.get("toolName"), "targetName": target.get("name"),
            "namespace": target.get("namespace"), "parameters": dict(parameters),
            "summary": f"{action.get('toolName')} {target.get('namespace')}/{target.get('name')}",
        },
        "parameters": dict(parameters), "planDigest": digest.get("planDigest"),
        "planId": metadata.get("name"), "proposalId": "",
        "risk": sealed_plan.get("safety", {}).get("risk") if isinstance(sealed_plan.get("safety"), Mapping) else "",
        "status": "planned", "target": dict(target),
    }


def plan_has_execution(plan_id: str, *, execution_records: Mapping[str, Mapping[str, Any]]) -> bool:
    return any(
        record.get("spec", {}).get("planId") == plan_id
        for record in execution_records.values()
        if isinstance(record.get("spec"), Mapping)
    )


def latest_pending_action_plan_result(
    subject: Mapping[str, Any],
    *,
    sealed_action_plans: Mapping[str, Mapping[str, Any]],
    plan_has_execution: Callable[[str], bool],
    can_subject_read_record: Callable[[Mapping[str, Any], Mapping[str, Any]], bool],
    action_plan_result_from_record: Callable[[Mapping[str, Any]], dict[str, Any]],
) -> dict[str, Any] | None:
    candidates = sorted(
        sealed_action_plans.values(),
        key=lambda record: str(record.get("metadata", {}).get("createdAt") or ""),
        reverse=True,
    )
    for record in candidates:
        plan_id = str(record.get("metadata", {}).get("name") or "")
        if not plan_id or plan_has_execution(plan_id):
            continue
        if not can_subject_read_record(record, subject):
            continue
        result = action_plan_result_from_record(record)
        if result.get("status") == "planned":
            return result
    return None


async def execute_natural_action_plan_result(
    plan_result: Mapping[str, Any],
    authorization: str,
    subject: Mapping[str, Any],
    *,
    dependencies: NaturalActionOrchestrationDependencies,
) -> dict[str, Any]:
    if plan_result.get("status") != "planned":
        return {"plan": dict(plan_result), "status": "not_executed", "reason": "natural action plan was not created"}
    plan_id = str(plan_result.get("planId") or "")
    plan_record = dependencies.sealed_action_plans.get(plan_id)
    if not plan_record:
        return {"plan": dict(plan_result), "status": "not_executed", "reason": "sealed action plan was not found"}

    sealed_plan = plan_record["spec"]["sealedActionPlan"]
    plan_digest = sealed_plan["digest"]["planDigest"]
    action_access_review = await dependencies.fetch_action_access_review(authorization, sealed_plan)
    dependencies.enforce_action_access_review(action_access_review)
    approval_request = dependencies.approval_decision_create_type(
        approvalScope="lab-auto-unrestricted", expectedPlanDigest=plan_digest, planId=plan_id,
    )
    approval_record = dependencies.build_approval_decision_record(
        dependencies.approval_decision_record_input_type(
            plan_record=plan_record, request=approval_request, approver=subject,
            action_access_review=action_access_review, context=dependencies.action_record_context(),
            allow_self_approval=True,
        )
    )
    approval_id = str(approval_record["metadata"]["name"])
    await dependencies.bounded_put_record("approvalDecisions", approval_id, approval_record)
    dependencies.increment_metric("aiops_approval_decisions_total")
    approval_decision = approval_record["spec"]["approvalDecision"]
    dependencies.validate_approval_is_active(approval_decision)
    dependencies.validate_execution_evidence_freshness(sealed_plan)
    grant_reference = dependencies.build_execution_grant_reference(
        dependencies.execution_grant_input_type(
            approval=approval_record, plan=plan_record, approver=subject,
            context=dependencies.action_record_context(),
        )
    )
    execution_id = f"execution-{uuid.uuid4()}"
    if dependencies.mutations_enabled:
        executor_result = await dependencies.execute_action_with_executor(
            sealed_plan, grant_reference,
            fallback_authorization=dependencies.natural_action_executor_fallback_authorization(),
        )
    else:
        executor_result = {
            "mutationOutcome": {"status": "mutation_disabled", "reason": "KOMSCO_AI_ENABLE_MUTATIONS is false."},
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False},
        }
    execution_record = {
        "schemaVersion": "v1", "apiVersion": "aiops.komsco/v1", "kind": "ExecutionRecord",
        "metadata": {"name": execution_id, "createdAt": dependencies.now_rfc3339()},
        "spec": {
            "executionId": execution_id, "approvalId": approval_id, "planId": plan_id,
            "planDigest": plan_digest,
            "executionGrantRef": {key: value for key, value in grant_reference.items() if key != "claims"},
            "mutationOutcome": executor_result["mutationOutcome"],
            "remediationOutcome": executor_result["remediationOutcome"],
            "executorTrace": dependencies.redact_sensitive(executor_result.get("executorTrace") or {}),
            "executionAuthorization": dependencies.redact_sensitive(action_access_review),
        },
        "subject": dependencies.redact_sensitive(dict(subject)),
    }
    await dependencies.bounded_put_record("executionRecords", execution_id, execution_record)
    approval_decision["status"] = "executed"
    approval_decision["executedAt"] = execution_record["metadata"]["createdAt"]
    await dependencies.bounded_put_record("approvalDecisions", approval_id, approval_record)
    dependencies.increment_metric("aiops_execution_requests_total")
    mutation_status = str(executor_result.get("mutationOutcome", {}).get("status") or "")
    if mutation_status == "mutation_succeeded":
        status = "executed"
    elif mutation_status == "review_recorded":
        status = "review_recorded"
    elif mutation_status == "mutation_disabled":
        status = "execution_disabled"
    else:
        status = "execution_failed"
    return {
        "approvalId": approval_id, "approval": approval_record, "executionId": execution_id,
        "execution": execution_record, "mutationOutcome": executor_result.get("mutationOutcome"),
        "plan": dict(plan_result), "remediationOutcome": executor_result.get("remediationOutcome"),
        "status": status,
    }
