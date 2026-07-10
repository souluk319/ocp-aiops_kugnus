from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from .schemas import ActionCandidatePlanCreate


@dataclass(frozen=True)
class ActionCandidatePlanConfig:
    openshift_api_url: str
    openshift_api_ca_file: str | bool
    test_pod_create_enabled: bool
    test_pod_create_allowed_namespaces: frozenset[str]
    test_pod_create_default_image: str
    test_pod_create_name_prefix: str


@dataclass(frozen=True)
class ActionCandidatePlanDependencies:
    action_candidate_plan_intent: Callable[[ActionCandidatePlanCreate], dict[str, Any]]
    action_target_type: Callable[..., Any]
    action_proposal_create_type: Callable[..., Any]
    async_client_factory: Callable[..., Any]
    timeout_factory: Callable[..., Any]
    now_rfc3339: Callable[[], str]
    path_segment: Callable[[str], str]
    fetch_ocp_json: Callable[..., Awaitable[Any]]
    resolve_natural_action_target: Callable[..., Awaitable[Mapping[str, Any]]]
    build_action_proposal_record: Callable[[Any, Mapping[str, Any]], dict[str, Any]]
    build_sealed_action_plan_record: Callable[[Mapping[str, Any]], dict[str, Any]]
    bounded_put_record: Callable[[str, str, dict[str, Any]], Awaitable[None]]
    increment_metric: Callable[[str], None]
    maybe_auto_approve_and_execute: Callable[..., Awaitable[dict[str, Any] | None]]


def action_candidate_plan_intent(
    req: ActionCandidatePlanCreate,
    *,
    config: ActionCandidatePlanConfig,
    now_rfc3339: Callable[[], str],
) -> dict[str, Any]:
    target = req.target
    kind = target.kind
    namespace = target.namespace or ""
    parameters = dict(req.parameters)
    source_hint = " ".join(
        [
            str(req.candidateId or ""),
            str(req.sourceType or ""),
            str(req.title or ""),
            str(req.sourceFindingId or ""),
        ]
    ).lower()

    if kind == "Deployment":
        if any(token in source_hint for token in ("container_command", "command_fix", "set_deployment_container_command")):
            return {
                "apiVersion": target.apiVersion or "apps/v1",
                "kind": "Deployment",
                "namespace": namespace,
                "targetName": target.name,
                "toolName": "set_deployment_container_command",
                "parameters": parameters,
                "summary": f"Deployment `{namespace}/{target.name}` container command update",
            }
        return {
            "apiVersion": target.apiVersion or "apps/v1",
            "kind": "Deployment",
            "namespace": namespace,
            "targetName": target.name,
            "toolName": "rollout_restart_deployment",
            "parameters": parameters or {"restartedAt": now_rfc3339()},
            "summary": f"Deployment `{namespace}/{target.name}` rollout restart",
        }

    if kind == "Pod":
        if any(token in source_hint for token in ("fix-review", "fix_or_rollback", "rollback_review")):
            return {
                "apiVersion": target.apiVersion or "v1",
                "kind": "Pod",
                "namespace": namespace,
                "targetName": target.name,
                "toolName": "pod_fix_or_rollback_review",
                "parameters": parameters
                or {
                    "includeOwnerChain": True,
                    "includeRolloutHistory": True,
                    "includeTemplateReview": True,
                },
                "summary": f"Pod `{namespace}/{target.name}` fix or rollback review",
            }
        if any(
            token in source_hint
            for token in (
                "diagnostic",
                "diagnosis",
                "rca",
                "evidence",
                "log-review",
                "pod_crashloop",
            )
        ):
            return {
                "apiVersion": target.apiVersion or "v1",
                "kind": "Pod",
                "namespace": namespace,
                "targetName": target.name,
                "toolName": "pod_diagnostic_review",
                "parameters": parameters or {"includePreviousLogs": True, "includeEvents": True},
                "summary": f"Pod `{namespace}/{target.name}` diagnostic review",
            }
        return {
            "apiVersion": target.apiVersion or "v1",
            "kind": "Pod",
            "namespace": namespace,
            "targetName": target.name,
            "toolName": "evict_one_unhealthy_controller_owned_pod",
            "parameters": parameters or {"reason": "action_candidate_unhealthy_pod_eviction"},
            "summary": f"Unhealthy controller-owned Pod `{namespace}/{target.name}` eviction",
        }

    if kind == "Namespace":
        if any(token in source_hint for token in ("test-pod", "test_pod", "create-test", "pod-create")):
            count = parameters.get("count")
            target_namespace = namespace or target.name
            if not config.test_pod_create_enabled:
                raise HTTPException(status_code=403, detail="CrashLoop test Pod creation is disabled in product mode")
            if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 5:
                raise HTTPException(status_code=400, detail="test pod count must be explicitly set between 1 and 5")
            if target_namespace not in config.test_pod_create_allowed_namespaces:
                raise HTTPException(status_code=403, detail="namespace is outside the test Pod creation allowlist")
            return {
                "apiVersion": target.apiVersion or "v1",
                "kind": "Namespace",
                "namespace": target_namespace,
                "targetName": target.name,
                "toolName": "create_crashloop_test_pods",
                "parameters": parameters
                or {
                    "failureMode": "crashloop",
                    "count": count,
                    "image": config.test_pod_create_default_image,
                    "namePrefix": config.test_pod_create_name_prefix,
                },
                "summary": f"Create CrashLoop test Pods in namespace `{target.name}`",
            }
        return {
            "apiVersion": target.apiVersion or "v1",
            "kind": "Namespace",
            "namespace": namespace or target.name,
            "targetName": target.name,
            "toolName": "namespace_cleanup_review",
            "parameters": parameters
            or {
                "backupReviewed": False,
                "ownerConfirmed": False,
                "pvcRouteReviewed": False,
            },
            "summary": f"Namespace `{target.name}` cleanup review",
        }

    raise HTTPException(
        status_code=400,
        detail=f"Action candidate target kind {kind} is not connected to an executable action yet",
    )


def _proposal_request(
    req: ActionCandidatePlanCreate,
    intent: Mapping[str, Any],
    target: Any,
    *,
    review_only_candidate: bool,
    dependencies: ActionCandidatePlanDependencies,
) -> Any:
    return dependencies.action_proposal_create_type(
        incidentId=req.incidentId,
        runId=req.runId,
        toolName=str(intent["toolName"]),
        target=target,
        parameters=dict(intent["parameters"]),
        evidenceRefs=req.evidenceRefs,
        expectedImpact=req.expectedImpact,
        prerequisiteChecks=req.prerequisiteChecks,
        problemSummary=req.problemSummary or req.title,
        recommendationSteps=req.recommendationSteps,
        policy={
            "candidateId": req.candidateId,
            "source": "aiops-action-candidate-board",
            "sourceFindingId": req.sourceFindingId,
            "sourceType": req.sourceType,
            **dict(req.policy),
            **({"reviewOnly": True} if review_only_candidate else {}),
        },
        verificationChecks=req.verificationChecks,
    )


async def _store_proposal_and_plan(
    proposal_request: Any,
    subject: Mapping[str, Any],
    *,
    dependencies: ActionCandidatePlanDependencies,
) -> tuple[dict[str, Any], str, dict[str, Any], str]:
    proposal_record = dependencies.build_action_proposal_record(proposal_request, subject)
    proposal_id = str(proposal_record["metadata"]["name"])
    await dependencies.bounded_put_record("actionProposals", proposal_id, proposal_record)
    dependencies.increment_metric("aiops_action_proposals_total")

    plan_record = dependencies.build_sealed_action_plan_record(proposal_record)
    plan_id = str(plan_record["metadata"]["name"])
    await dependencies.bounded_put_record("sealedActionPlans", plan_id, plan_record)
    dependencies.increment_metric("aiops_action_plans_total")
    return proposal_record, proposal_id, plan_record, plan_id


def _response(
    req: ActionCandidatePlanCreate,
    intent: Mapping[str, Any],
    target: Any,
    proposal_record: dict[str, Any],
    proposal_id: str,
    plan_record: dict[str, Any],
    plan_id: str,
    auto_result: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    plan = plan_record["spec"]["sealedActionPlan"]
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ActionCandidatePlan",
        "metadata": {"name": plan_id, "createdAt": plan_record["metadata"]["createdAt"]},
        "spec": {
            "candidateId": req.candidateId,
            "intent": dict(intent),
            "plan": plan_record,
            "planDigest": plan["digest"]["planDigest"],
            "planId": plan_id,
            "proposal": proposal_record,
            "proposalId": proposal_id,
            "status": "planned",
            "target": target.model_dump(),
            "title": req.title,
            **(dict(auto_result) if auto_result else {}),
        },
    }


async def create_plan_from_action_candidate(
    req: ActionCandidatePlanCreate,
    authorization: str,
    subject: Mapping[str, Any],
    *,
    config: ActionCandidatePlanConfig,
    dependencies: ActionCandidatePlanDependencies,
) -> dict[str, Any]:
    if not config.openshift_api_url:
        raise HTTPException(
            status_code=503,
            detail="OpenShift API URL이 없어 조치 대상 리소스를 확인하지 못했습니다.",
        )

    intent = dependencies.action_candidate_plan_intent(req)
    review_only_candidate = str(intent.get("toolName") or "") in {
        "namespace_cleanup_review",
        "test_pod_create_review",
        "pod_diagnostic_review",
        "pod_fix_or_rollback_review",
    }
    timeout = dependencies.timeout_factory(20.0, connect=5.0)

    if str(intent.get("kind") or "") == "Namespace":
        target_name = str(intent["targetName"])
        async with dependencies.async_client_factory(
            verify=config.openshift_api_ca_file,
            timeout=timeout,
        ) as client:
            live_target = await dependencies.fetch_ocp_json(
                client,
                f"/api/v1/namespaces/{dependencies.path_segment(target_name)}",
                authorization,
                required=True,
            )
        if not isinstance(live_target, Mapping):
            raise HTTPException(status_code=404, detail=f"Namespace `{target_name}`를 찾지 못했습니다.")
        metadata = live_target.get("metadata", {}) if isinstance(live_target.get("metadata"), Mapping) else {}
        uid = str(metadata.get("uid") or "")
        if not uid:
            raise HTTPException(status_code=409, detail="Namespace UID를 확인하지 못했습니다.")
        target = dependencies.action_target_type(
            apiVersion="v1",
            kind="Namespace",
            namespace=target_name,
            name=target_name,
            uid=uid,
        )
        proposal_request = _proposal_request(
            req,
            intent,
            target,
            review_only_candidate=review_only_candidate,
            dependencies=dependencies,
        )
        stored = await _store_proposal_and_plan(proposal_request, subject, dependencies=dependencies)
        return _response(req, intent, target, *stored)

    async with dependencies.async_client_factory(
        verify=config.openshift_api_ca_file,
        timeout=timeout,
    ) as client:
        resolved_target = await dependencies.resolve_natural_action_target(client, intent, authorization)

    status = str(resolved_target.get("status") or "unknown")
    if status == "ambiguous":
        raise HTTPException(
            status_code=409,
            detail={
                "candidates": resolved_target.get("candidates", []),
                "message": f"{intent['kind']} `{intent['targetName']}` 후보가 여러 namespace에서 발견되었습니다.",
                "status": status,
            },
        )
    if status == "missing_namespace":
        raise HTTPException(
            status_code=400,
            detail=f"{intent['kind']} `{intent['targetName']}` 조치에는 namespace가 필요합니다.",
        )
    if status != "found":
        raise HTTPException(
            status_code=404,
            detail=f"{intent['kind']} `{intent['namespace']}/{intent['targetName']}`를 찾지 못했습니다.",
        )

    live_target = resolved_target.get("target") if isinstance(resolved_target.get("target"), Mapping) else None
    if not live_target:
        raise HTTPException(status_code=404, detail="조치 대상 리소스를 찾지 못했습니다.")

    metadata = live_target.get("metadata", {}) if isinstance(live_target.get("metadata"), Mapping) else {}
    namespace = str(metadata.get("namespace") or intent["namespace"])
    target_name = str(metadata.get("name") or intent["targetName"])
    uid = str(metadata.get("uid") or "")
    if not uid:
        raise HTTPException(status_code=409, detail="조치 대상 UID를 확인하지 못했습니다.")

    target = dependencies.action_target_type(
        apiVersion=str(intent.get("apiVersion") or req.target.apiVersion or "apps/v1"),
        kind=str(intent["kind"]),
        namespace=namespace,
        name=target_name,
        uid=uid,
    )
    proposal_request = _proposal_request(
        req,
        intent,
        target,
        review_only_candidate=review_only_candidate,
        dependencies=dependencies,
    )
    stored = await _store_proposal_and_plan(proposal_request, subject, dependencies=dependencies)
    auto_result = await dependencies.maybe_auto_approve_and_execute(stored[2], authorization)
    return _response(req, intent, target, *stored, auto_result=auto_result)
