import asyncio
import uuid
from collections.abc import Awaitable, Callable, Mapping, MutableMapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from .schemas import ActionExecutionCreate, ApprovalDecisionCreate


AsyncCallable = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ActionApiConfig:
    mutations_enabled: bool
    unrestricted_commands_enabled: bool
    approval_access_review_required: bool
    registry_version: str
    registry_digest: str
    registry_entries: Mapping[str, Mapping[str, Any]]
    auto_execute_tool_names: frozenset[str]
    auto_execute_evict_eligible_source_types: frozenset[str]


@dataclass(frozen=True)
class ActionApiStores:
    action_proposals: MutableMapping[str, dict[str, Any]]
    sealed_action_plans: MutableMapping[str, dict[str, Any]]
    approval_decisions: MutableMapping[str, dict[str, Any]]
    execution_records: MutableMapping[str, dict[str, Any]]
    auto_execute_target_locks: MutableMapping[str, asyncio.Lock]


@dataclass(frozen=True)
class ActionApiDependencies:
    config: ActionApiConfig
    stores: ActionApiStores
    verify_bearer_header: Callable[[str | None], str]
    fetch_self_subject_review: AsyncCallable
    fetch_product_access_review: AsyncCallable
    fetch_action_access_review: AsyncCallable
    enforce_product_access_review: Callable[..., None]
    enforce_action_access_review: Callable[..., None]
    can_subject_read_record: Callable[..., bool]
    build_action_proposal_record: Callable[..., dict[str, Any]]
    build_sealed_action_plan_record: Callable[..., dict[str, Any]]
    build_approval_decision_record: Callable[..., dict[str, Any]]
    build_action_rejection_record: Callable[..., dict[str, Any]]
    build_execution_grant_reference: Callable[..., dict[str, Any]]
    create_plan_from_action_candidate: AsyncCallable
    bounded_put_record: AsyncCallable
    increment_metric: Callable[[str], None]
    maybe_auto_approve_and_execute: AsyncCallable
    plan_has_approval_status: Callable[..., bool]
    find_approval_by_plan_status: Callable[..., Mapping[str, Any] | None]
    record_created_at: Callable[..., datetime]
    validate_approval_is_active: Callable[..., None]
    approval_already_executed: Callable[[str], bool]
    validate_execution_evidence_freshness: Callable[..., None]
    execute_action_with_executor: AsyncCallable
    sealed_plan_is_review_only: Callable[[Mapping[str, Any]], bool]
    now_rfc3339: Callable[[], str]
    redact_sensitive: Callable[..., Any]
    aiops_action_candidates: AsyncCallable


def get_action_registry(authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    deps.verify_bearer_header(authorization)
    config = deps.config
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionRegistry",
        "metadata": {"name": "mutation-action-registry", "version": config.registry_version},
        "spec": {
            "digest": config.registry_digest,
            "mutationsEnabled": config.mutations_enabled,
            "entries": list(config.registry_entries.values()),
        },
    }


async def create_action_proposal(req: Any, authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.build_action_proposal_record(req, subject)
    proposal_id = str(record["metadata"]["name"])
    await deps.bounded_put_record("actionProposals", proposal_id, record)
    deps.increment_metric("aiops_action_proposals_total")
    return _record_response("ActionProposal", record)


async def create_action_candidate_plan(req: Any, authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    return await deps.create_plan_from_action_candidate(req, user_auth_header, subject)


async def get_action_proposal(proposal_id: str, authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.stores.action_proposals.get(proposal_id)
    if not record or not deps.can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Action proposal not found")
    return _record_response("ActionProposal", record)


async def create_action_plan(req: Any, authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    proposal = deps.stores.action_proposals.get(req.proposalId)
    if not proposal or not deps.can_subject_read_record(proposal, subject):
        raise HTTPException(status_code=404, detail="Action proposal not found")
    record = deps.build_sealed_action_plan_record(proposal)
    plan_id = str(record["metadata"]["name"])
    await deps.bounded_put_record("sealedActionPlans", plan_id, record)
    deps.increment_metric("aiops_action_plans_total")
    auto_result = await deps.maybe_auto_approve_and_execute(record, user_auth_header)
    response = _record_response("SealedActionPlan", record)
    response["spec"] = {**record["spec"], **(auto_result or {})}
    return response


async def get_action_plan(plan_id: str, authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    record = deps.stores.sealed_action_plans.get(plan_id)
    if not record or not deps.can_subject_read_record(record, subject):
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    return _record_response("SealedActionPlan", record)


async def create_approval_decision_impl(req: Any, user_auth_header: str, deps: ActionApiDependencies, *, auto_policy: bool = False) -> dict[str, Any]:
    subject = await deps.fetch_self_subject_review(user_auth_header)
    product_access_review = await deps.fetch_product_access_review(user_auth_header)
    if deps.config.approval_access_review_required:
        deps.enforce_product_access_review({**product_access_review, "required": True})
    plan = deps.stores.sealed_action_plans.get(req.planId)
    if not plan:
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    if not deps.can_subject_read_record(plan, subject) and product_access_review.get("allowed") is not True:
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    plan_digest = plan["spec"]["sealedActionPlan"]["digest"]["planDigest"]
    if req.expectedPlanDigest != plan_digest:
        raise HTTPException(status_code=409, detail="expectedPlanDigest does not match the sealed plan")
    plan_created_at = deps.record_created_at(plan)
    if deps.plan_has_approval_status(plan_digest, {"rejected"}, not_before=plan_created_at):
        raise HTTPException(status_code=409, detail="Action plan has been rejected")
    existing = deps.find_approval_by_plan_status(plan_digest, {"approved", "executed"}, not_before=plan_created_at)
    if existing is not None:
        return _record_response("ApprovalDecision", existing)
    action_access_review = await deps.fetch_action_access_review(user_auth_header, plan["spec"]["sealedActionPlan"])
    deps.enforce_action_access_review(action_access_review)
    action = plan["spec"]["sealedActionPlan"].get("action", {})
    review_only_action = isinstance(action, Mapping) and str(action.get("toolName") or "") in {
        "namespace_cleanup_review", "test_pod_create_review", "pod_diagnostic_review", "pod_fix_or_rollback_review",
    }
    record = deps.build_approval_decision_record(
        plan, req, subject, action_access_review,
        allow_self_approval=auto_policy or review_only_action,
        auto_policy=auto_policy,
    )
    approval_id = str(record["metadata"]["name"])
    await deps.bounded_put_record("approvalDecisions", approval_id, record)
    deps.increment_metric("aiops_approval_decisions_total")
    return _record_response("ApprovalDecision", record)


async def create_approval_decision(req: Any, authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    unrestricted_auto_policy = req.approvalScope == "lab-auto-unrestricted"
    if unrestricted_auto_policy and not deps.config.unrestricted_commands_enabled:
        raise HTTPException(status_code=403, detail="lab-auto-unrestricted approval requires unrestricted command gate")
    return await create_approval_decision_impl(req, user_auth_header, deps, auto_policy=unrestricted_auto_policy)


async def reject_action_plan(req: Any, authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    user_auth_header = deps.verify_bearer_header(authorization)
    subject = await deps.fetch_self_subject_review(user_auth_header)
    product_access_review = await deps.fetch_product_access_review(user_auth_header)
    plan = deps.stores.sealed_action_plans.get(req.planId)
    if not plan or (not deps.can_subject_read_record(plan, subject) and not bool(product_access_review.get("allowed"))):
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    plan_digest = plan["spec"]["sealedActionPlan"]["digest"]["planDigest"]
    if deps.plan_has_approval_status(plan_digest, {"approved", "executed"}, not_before=deps.record_created_at(plan)):
        raise HTTPException(status_code=409, detail="Action plan already has an active approval")
    record = deps.build_action_rejection_record(plan, req, subject)
    rejection_id = str(record["metadata"]["name"])
    await deps.bounded_put_record("approvalDecisions", rejection_id, record)
    deps.increment_metric("aiops_approval_decisions_total")
    return _record_response("ApprovalDecision", record)


async def execute_action_impl(req: Any, user_auth_header: str, deps: ActionApiDependencies, *, auto_policy: bool = False) -> dict[str, Any]:
    subject = await deps.fetch_self_subject_review(user_auth_header)
    product_access_review = await deps.fetch_product_access_review(user_auth_header)
    product_access_allowed = bool(product_access_review.get("allowed"))
    plan = deps.stores.sealed_action_plans.get(req.planId)
    approval = deps.stores.approval_decisions.get(req.approvalId)
    if not plan or (not deps.can_subject_read_record(plan, subject) and not product_access_allowed):
        raise HTTPException(status_code=404, detail="Sealed action plan not found")
    if not approval or (not deps.can_subject_read_record(approval, subject) and not product_access_allowed):
        raise HTTPException(status_code=404, detail="Approval decision not found")
    sealed_plan = plan["spec"]["sealedActionPlan"]
    plan_digest = sealed_plan["digest"]["planDigest"]
    approval_decision = approval["spec"]["approvalDecision"]
    if req.expectedPlanDigest != plan_digest or approval_decision["planDigest"] != plan_digest:
        raise HTTPException(status_code=409, detail="Execution request is stale for this sealed plan")
    if approval_decision["status"] != "approved":
        raise HTTPException(status_code=409, detail="Approval decision is not approved")
    deps.validate_approval_is_active(approval_decision)
    if deps.approval_already_executed(req.approvalId):
        raise HTTPException(status_code=409, detail="Approval decision has already been used for execution")
    execution_access_review = await deps.fetch_action_access_review(user_auth_header, sealed_plan)
    deps.enforce_action_access_review(execution_access_review)
    deps.validate_execution_evidence_freshness(sealed_plan)
    grant_reference = deps.build_execution_grant_reference(approval, plan, subject)
    execution_id = f"execution-{uuid.uuid4()}"
    review_only_execution = deps.sealed_plan_is_review_only(sealed_plan)
    if deps.config.mutations_enabled or review_only_execution:
        executor_result = await deps.execute_action_with_executor(sealed_plan, grant_reference, fallback_authorization=user_auth_header)
    else:
        executor_result = {
            "mutationOutcome": {"status": "mutation_disabled", "reason": "KOMSCO_AI_ENABLE_MUTATIONS is false."},
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False},
        }
    record = {
        "schemaVersion": "v1", "apiVersion": "aiops.komsco/v1", "kind": "ExecutionRecord",
        "metadata": {"name": execution_id, "createdAt": deps.now_rfc3339()},
        "spec": {
            "executionId": execution_id, "approvalId": req.approvalId, "planId": req.planId,
            "planDigest": plan_digest,
            "executionGrantRef": {key: value for key, value in grant_reference.items() if key != "claims"},
            "mutationOutcome": executor_result["mutationOutcome"],
            "remediationOutcome": executor_result["remediationOutcome"],
            "executorTrace": deps.redact_sensitive(executor_result.get("executorTrace") or {}),
            "executionAuthorization": deps.redact_sensitive(execution_access_review),
            **({"decidedBy": "auto-policy", "decisionPolicy": {"toolName": sealed_plan["action"].get("toolName"), "triggeredBy": "sealed-plan-creation"}} if auto_policy else {}),
        },
        "subject": deps.redact_sensitive(dict(subject)),
    }
    await deps.bounded_put_record("executionRecords", execution_id, record)
    approval_decision["status"] = "executed"
    approval_decision["executedAt"] = record["metadata"]["createdAt"]
    await deps.bounded_put_record("approvalDecisions", req.approvalId, approval)
    deps.increment_metric("aiops_execution_requests_total")
    if not deps.config.mutations_enabled and not review_only_execution:
        raise HTTPException(status_code=403, detail=record["spec"])
    return _record_response("ExecutionRecord", record)


async def execute_action(req: Any, authorization: str | None, deps: ActionApiDependencies) -> dict[str, Any]:
    return await execute_action_impl(req, deps.verify_bearer_header(authorization), deps)


def has_recent_auto_action_for_target(target: Mapping[str, Any], tool_name: str, deps: ActionApiDependencies, *, window_seconds: int = 180) -> bool:
    now = datetime.now(UTC)
    for record in deps.stores.approval_decisions.values():
        decision = record.get("spec", {}).get("approvalDecision", {})
        decision_target = decision.get("target") or {}
        if decision.get("decidedBy") != "auto-policy" or any(decision_target.get(key) != target.get(key) for key in ("namespace", "name", "kind")):
            continue
        if decision.get("action", {}).get("toolName") != tool_name:
            continue
        try:
            approved_at = datetime.fromisoformat(str(decision.get("approvedAt", "")).replace("Z", "+00:00"))
        except ValueError:
            continue
        if (now - approved_at).total_seconds() <= window_seconds:
            return True
    return False


async def verify_source_type_for_target(user_auth_header: str, target: Mapping[str, Any], deps: ActionApiDependencies) -> str | None:
    try:
        candidates = await deps.aiops_action_candidates(user_auth_header)
    except Exception:  # noqa: BLE001
        return None
    for candidate in candidates.get("spec", {}).get("candidates", []) or []:
        candidate_target = candidate.get("target") or {}
        if candidate_target.get("namespace") == target.get("namespace") and candidate_target.get("name") == target.get("name"):
            return candidate.get("sourceType")
    return None


async def maybe_auto_approve_and_execute(plan_record: Mapping[str, Any], user_auth_header: str, deps: ActionApiDependencies) -> dict[str, Any] | None:
    if not deps.config.mutations_enabled:
        return None
    plan = plan_record["spec"]["sealedActionPlan"]
    tool_name = plan["action"].get("toolName")
    if not tool_name or tool_name not in deps.config.auto_execute_tool_names:
        return None
    if tool_name == "evict_one_unhealthy_controller_owned_pod":
        source_type = await verify_source_type_for_target(user_auth_header, plan["target"], deps)
        if source_type not in deps.config.auto_execute_evict_eligible_source_types:
            return None
    target = plan["target"]
    target_key = f"{target.get('namespace')}/{target.get('kind')}/{target.get('name')}"
    lock = deps.stores.auto_execute_target_locks.setdefault(target_key, asyncio.Lock())
    async with lock:
        if has_recent_auto_action_for_target(target, tool_name, deps):
            return {"autoExecuted": False, "autoExecuteFailed": True, "reason": "duplicate auto-execute for this target was already handled"}
        plan_id = str(plan_record["metadata"]["name"])
        plan_digest = plan["digest"]["planDigest"]
        try:
            approval = await create_approval_decision_impl(
                ApprovalDecisionCreate(planId=plan_id, expectedPlanDigest=plan_digest, approvalScope="auto-policy"),
                user_auth_header, deps, auto_policy=True,
            )
            execution = await execute_action_impl(
                ActionExecutionCreate(approvalId=str(approval["metadata"]["name"]), planId=plan_id, expectedPlanDigest=plan_digest),
                user_auth_header, deps, auto_policy=True,
            )
        except HTTPException as exc:
            return {"autoExecuted": False, "autoExecuteFailed": True, "reason": str(exc.detail)}
        except Exception as exc:  # noqa: BLE001
            return {"autoExecuted": False, "autoExecuteFailed": True, "reason": str(exc)}
        return {"autoExecuted": True, "approval": approval, "execution": execution}


def _record_response(kind: str, record: Mapping[str, Any]) -> dict[str, Any]:
    return {"apiVersion": "aiops.komsco/v1", "kind": kind, "metadata": record["metadata"], "spec": record["spec"]}
