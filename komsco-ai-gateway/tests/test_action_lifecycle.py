from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import HTTPException

import komsco_ai_gateway.action_executor as action_executor
import komsco_ai_gateway.main as gateway_main
from komsco_ai_gateway.main import (
    ACTION_PROPOSALS,
    ACTION_REGISTRY_DIGEST,
    ACTION_REGISTRY_ENTRIES,
    APPROVAL_DECISIONS,
    BREAK_GLASS_PROFILE_DIGEST,
    BREAK_GLASS_PROFILES,
    BREAK_GLASS_REQUESTS,
    EXECUTION_RECORDS,
    PREAPPROVED_PATCH_REQUESTS,
    RUNBOOK_PLANS,
    RUNBOOK_REGISTRY_DIGEST,
    RUNBOOK_REGISTRY_ENTRIES,
    SEALED_ACTION_PLANS,
    ActionProposalCreate,
    ActionTarget,
    BreakGlassRequestCreate,
    BreakGlassTargetNode,
    PatchPreapprovedFieldCreate,
    RunbookPlanCreate,
    app,
    build_action_access_review_request,
    build_action_proposal_record,
    build_break_glass_request_record,
    build_preapproved_patch_record,
    build_runbook_plan_record,
    build_sealed_action_plan_record,
    candidate_action_request_digest,
    sealed_action_plan_digest,
    validate_execution_evidence_freshness,
)
from komsco_ai_gateway.security import safe_subject

def test_action_proposal_digest_uses_runtime_target_not_hardcoded_target() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = ActionProposalCreate(
        toolName="rollout_restart_deployment",
        target=ActionTarget(
            apiVersion="apps/v1",
            kind="Deployment",
            namespace="team-a",
            name="web-a",
            uid="deployment-uid-a",
        ),
        parameters={"restartedAt": "2026-06-21T00:00:00Z"},
    )
    changed_target_request = request.model_copy(
        update={
            "target": ActionTarget(
                apiVersion="apps/v1",
                kind="Deployment",
                namespace="team-b",
                name="web-b",
                uid="deployment-uid-b",
            )
        }
    )
    record = build_action_proposal_record(request, subject)
    changed_record = build_action_proposal_record(changed_target_request, subject)
    candidate = record["spec"]["candidateActionRequest"]
    changed_candidate = changed_record["spec"]["candidateActionRequest"]

    assert candidate["target"]["namespace"] == "team-a"
    assert candidate["target"]["name"] == "web-a"
    assert candidate_action_request_digest(candidate) != candidate_action_request_digest(changed_candidate)












def test_pod_diagnostic_review_action_proposal_is_review_only() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    proposal = build_action_proposal_record(
        ActionProposalCreate(
            toolName="pod_diagnostic_review",
            target=ActionTarget(
                apiVersion="v1",
                kind="Pod",
                namespace="team-a",
                name="web-abc",
                uid="pod-uid-a",
            ),
            parameters={"includePreviousLogs": True, "includeEvents": True},
            policy={"sourceType": "pod_diagnostic_review"},
        ),
        subject,
    )
    plan = build_sealed_action_plan_record(proposal)["spec"]["sealedActionPlan"]

    assert plan["action"]["toolName"] == "pod_diagnostic_review"
    assert plan["action"]["request"]["method"] == "GET"
    assert plan["action"]["authorization"]["verb"] == "get"
    assert plan["action"]["normalizedParameters"] == {
        "includeDescribe": True,
        "includeEvents": True,
        "includePreviousLogs": True,
        "reviewOnly": True,
    }
    assert plan["safety"]["risk"] == "low"
    assert proposal["spec"]["sourceType"] == "pod_diagnostic_review"


def test_pod_diagnostic_review_lifecycle_allows_same_user_review_record(monkeypatch) -> None:
    previous_stores = (
        dict(ACTION_PROPOSALS),
        dict(SEALED_ACTION_PLANS),
        dict(APPROVAL_DECISIONS),
        dict(EXECUTION_RECORDS),
    )
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()

    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})

    async def fake_subject_review(_user_auth_header: str) -> dict:
        return subject

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {"allowed": True}

    async def fake_action_access_review(_user_auth_header: str, plan: Mapping[str, object]) -> dict:
        action = plan.get("action") if isinstance(plan.get("action"), Mapping) else {}
        return {
            "allowed": True,
            "enabled": True,
            "resourceAttributes": {
                "group": "",
                "resource": "pods",
                "verb": "get",
                "name": plan.get("target", {}).get("name") if isinstance(plan.get("target"), Mapping) else "",
                "namespace": plan.get("target", {}).get("namespace") if isinstance(plan.get("target"), Mapping) else "",
            },
            "toolName": action.get("toolName") if isinstance(action, Mapping) else "",
        }

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_action_access_review", fake_action_access_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            proposal_response = await client.post(
                "/v1/actions/proposals",
                headers=headers,
                json={
                    "toolName": "pod_diagnostic_review",
                    "target": {
                        "apiVersion": "v1",
                        "kind": "Pod",
                        "namespace": "team-a",
                        "name": "web-abc",
                        "uid": "pod-uid-a",
                    },
                    "parameters": {"includePreviousLogs": True, "includeEvents": True},
                    "policy": {"sourceType": "pod_diagnostic_review"},
                },
            )
            assert proposal_response.status_code == 200, proposal_response.text
            proposal_id = proposal_response.json()["metadata"]["name"]

            plan_response = await client.post(
                "/v1/actions/plans",
                headers=headers,
                json={"proposalId": proposal_id},
            )
            assert plan_response.status_code == 200, plan_response.text
            plan_payload = plan_response.json()
            sealed_plan = plan_payload["spec"]["sealedActionPlan"]
            plan_id = plan_payload["metadata"]["name"]
            plan_digest = sealed_plan["digest"]["planDigest"]
            assert sealed_plan["action"]["toolName"] == "pod_diagnostic_review"
            assert sealed_plan["action"]["normalizedParameters"]["reviewOnly"] is True
            assert sealed_plan["safety"]["risk"] == "low"

            approval_response = await client.post(
                "/v1/actions/approvals",
                headers=headers,
                json={
                    "approvalScope": "single-target",
                    "expectedPlanDigest": plan_digest,
                    "planId": plan_id,
                },
            )
            assert approval_response.status_code == 200, approval_response.text
            approval_id = approval_response.json()["metadata"]["name"]

            execution_response = await client.post(
                "/v1/actions/execute",
                headers=headers,
                json={
                    "approvalId": approval_id,
                    "expectedPlanDigest": plan_digest,
                    "planId": plan_id,
                },
            )
            assert execution_response.status_code == 200, execution_response.text
            execution = execution_response.json()

        spec = execution["spec"]
        assert spec["mutationOutcome"]["status"] == "review_recorded"
        assert spec["executorTrace"]["reviewOnly"] is True
        assert spec["executorTrace"]["mutationSubmitted"] is False
        assert spec["executorTrace"]["toolName"] == "pod_diagnostic_review"
        assert APPROVAL_DECISIONS[approval_id]["spec"]["approvalDecision"]["status"] == "executed"
        assert list(EXECUTION_RECORDS.values())[0]["spec"]["mutationOutcome"]["status"] == "review_recorded"

    try:
        asyncio.run(run())
    finally:
        ACTION_PROPOSALS.clear()
        SEALED_ACTION_PLANS.clear()
        APPROVAL_DECISIONS.clear()
        EXECUTION_RECORDS.clear()
        ACTION_PROPOSALS.update(previous_stores[0])
        SEALED_ACTION_PLANS.update(previous_stores[1])
        APPROVAL_DECISIONS.update(previous_stores[2])
        EXECUTION_RECORDS.update(previous_stores[3])


def test_review_only_execution_results_do_not_claim_mutation_success() -> None:
    sealed_plan = {
        "target": {
            "apiVersion": "v1",
            "kind": "Namespace",
            "name": "team-a",
            "namespace": "team-a",
            "uid": "namespace-uid",
        },
        "action": {
            "toolName": "namespace_cleanup_review",
            "normalizedParameters": {},
        },
    }

    result = gateway_main.namespace_cleanup_review_execution_result(sealed_plan)

    assert result["mutationOutcome"]["status"] == "review_recorded"
    assert "no namespace deletion executed" in result["mutationOutcome"]["reason"]
    assert result["executorTrace"]["reviewOnly"] is True
    assert result["executorTrace"]["mutationSubmitted"] is False


def test_action_access_review_request_is_derived_from_sealed_plan_target() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    proposal = build_action_proposal_record(
        ActionProposalCreate(
            toolName="set_hpa_bounds",
            target=ActionTarget(
                apiVersion="autoscaling/v2",
                kind="HorizontalPodAutoscaler",
                namespace="dynamic-team",
                name="web-hpa",
                uid="hpa-uid-a",
            ),
            parameters={"minReplicas": 2, "maxReplicas": 5},
        ),
        subject,
    )
    plan_record = build_sealed_action_plan_record(proposal)
    review_request = build_action_access_review_request(plan_record["spec"]["sealedActionPlan"])
    attributes = review_request["spec"]["resourceAttributes"]

    assert attributes == {
        "group": "autoscaling",
        "resource": "horizontalpodautoscalers",
        "verb": "patch",
        "namespace": "dynamic-team",
        "name": "web-hpa",
    }


def test_sealed_action_plan_digest_excludes_mutable_status_and_digest_fields() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    proposal = build_action_proposal_record(
        ActionProposalCreate(
            toolName="rollout_restart_deployment",
            target=ActionTarget(
                apiVersion="apps/v1",
                kind="Deployment",
                namespace="team-a",
                name="web-a",
                uid="deployment-uid-a",
            ),
            parameters={"restartedAt": "2026-06-21T00:00:00Z"},
        ),
        subject,
    )
    plan_record = build_sealed_action_plan_record(proposal)
    plan = plan_record["spec"]["sealedActionPlan"]
    plan_digest = plan["digest"]["planDigest"]
    mutable_copy = {
        **plan,
        "digest": {"planDigest": "sha256:tampered"},
        "executionStatus": {"phase": "mutation_succeeded"},
    }

    assert sealed_action_plan_digest(plan) == plan_digest
    assert sealed_action_plan_digest(mutable_copy) == plan_digest
    grant_ref = plan["safety"]["planValidationGrantRef"]
    assert grant_ref["grantId"].startswith("validation-")
    assert grant_ref["grantDigest"].startswith("sha256:")
    assert grant_ref["bearerGrantStored"] is False


def test_action_executor_rejects_missing_or_mismatched_execution_grant() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    proposal = build_action_proposal_record(
        ActionProposalCreate(
            toolName="rollout_restart_deployment",
            target=ActionTarget(
                apiVersion="apps/v1",
                kind="Deployment",
                namespace="team-a",
                name="web-a",
                uid="deployment-uid-a",
            ),
            parameters={"restartedAt": "2026-06-21T00:00:00Z"},
        ),
        subject,
    )
    plan_record = build_sealed_action_plan_record(proposal)
    plan = plan_record["spec"]["sealedActionPlan"]

    with pytest.raises(HTTPException) as missing_claims:
        action_executor.verify_execution_grant(plan, {"grantDigest": "sha256:missing"})
    assert missing_claims.value.status_code == 403

    claims = {
        "audience": "aiops-action-executor",
        "planDigest": "sha256:wrong",
    }
    with pytest.raises(HTTPException) as digest_mismatch:
        action_executor.verify_execution_grant(
            plan,
            {
                "claims": claims,
                "grantDigest": gateway_main.canonical_digest(claims),
            },
        )
    assert digest_mismatch.value.status_code == 403

    claims = {
        "audience": "aiops-action-executor",
        "notBefore": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
        "expiresAt": (datetime.now(UTC) + timedelta(minutes=1)).isoformat(),
        "planDigest": plan["digest"]["planDigest"],
        "action": plan["action"],
        "target": plan["target"],
        "policyBundleHash": plan["safety"]["policy"]["policyBundleHash"],
    }
    action_executor.verify_execution_grant(
        plan,
        {
            "claims": claims,
            "grantDigest": gateway_main.canonical_digest(claims),
        },
    )

    expired_claims = {
        **claims,
        "notBefore": (datetime.now(UTC) - timedelta(minutes=3)).isoformat(),
        "expiresAt": (datetime.now(UTC) - timedelta(minutes=1)).isoformat(),
    }
    with pytest.raises(HTTPException) as expired_grant:
        action_executor.verify_execution_grant(
            plan,
            {
                "claims": expired_claims,
                "grantDigest": gateway_main.canonical_digest(expired_claims),
            },
        )
    assert expired_grant.value.status_code == 403
    assert "time window" in str(expired_grant.value.detail)


def test_execution_evidence_freshness_rejects_expired_evidence_refs() -> None:
    expired = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    plan = {
        "approvalPresentation": {
            "evidenceRefs": [
                {
                    "evidenceId": "ev-expired",
                    "requiredFreshUntil": expired,
                }
            ]
        }
    }

    with pytest.raises(HTTPException) as exc_info:
        validate_execution_evidence_freshness(plan)
    assert exc_info.value.status_code == 409
    assert "evidence is no longer fresh" in str(exc_info.value.detail)
    assert "create a new plan and approval" in str(exc_info.value.detail)


def test_actions_api_rejects_stale_approval_and_blocks_disabled_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()
    subject = safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    async def fake_subject_review(_user_auth_header: str) -> dict[str, object]:
        return subject

    async def fake_product_access_review(_user_auth_header: str) -> dict[str, object]:
        return {"allowed": True, "enabled": True, "required": False}

    async def fake_action_access_review(_user_auth_header: str, _plan: dict[str, object]) -> dict[str, object]:
        return {
            "allowed": True,
            "enabled": True,
            "resourceAttributes": {"group": "apps", "resource": "deployments", "verb": "patch"},
        }

    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", False)
    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_action_access_review", fake_action_access_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            registry_response = await client.get("/v1/actions/registry", headers=headers)
            proposal_response = await client.post(
                "/v1/actions/proposals",
                headers=headers,
                json={
                    "incidentId": "inc-action",
                    "runId": "run-action",
                    "toolName": "rollout_restart_deployment",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "parameters": {"restartedAt": "2026-06-21T00:00:00Z"},
                },
            )
            proposal_id = proposal_response.json()["metadata"]["name"]
            plan_response = await client.post(
                "/v1/actions/plans",
                headers=headers,
                json={"proposalId": proposal_id},
            )
            plan_payload = plan_response.json()
            plan_id = plan_payload["metadata"]["name"]
            plan_digest = plan_payload["spec"]["sealedActionPlan"]["digest"]["planDigest"]
            stale_approval_response = await client.post(
                "/v1/actions/approvals",
                headers=headers,
                json={"planId": plan_id, "expectedPlanDigest": "sha256:stale"},
            )
            approval_response = await client.post(
                "/v1/actions/approvals",
                headers=headers,
                json={"planId": plan_id, "expectedPlanDigest": plan_digest},
            )
            approval_id = approval_response.json()["metadata"]["name"]
            execution_response = await client.post(
                "/v1/actions/execute",
                headers=headers,
                json={
                    "approvalId": approval_id,
                    "planId": plan_id,
                    "expectedPlanDigest": plan_digest,
                },
            )
            rejected_proposal_response = await client.post(
                "/v1/actions/proposals",
                headers=headers,
                json={
                    "incidentId": "inc-rejected-action",
                    "runId": "run-rejected-action",
                    "toolName": "rollout_restart_deployment",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-b",
                        "uid": "deployment-uid-b",
                    },
                    "parameters": {"restartedAt": "2026-06-21T00:00:00Z"},
                },
            )
            rejected_plan_response = await client.post(
                "/v1/actions/plans",
                headers=headers,
                json={"proposalId": rejected_proposal_response.json()["metadata"]["name"]},
            )
            rejected_plan_payload = rejected_plan_response.json()
            rejected_plan_id = rejected_plan_payload["metadata"]["name"]
            rejected_plan_digest = rejected_plan_payload["spec"]["sealedActionPlan"]["digest"]["planDigest"]
            rejection_response = await client.post(
                "/v1/actions/rejections",
                headers=headers,
                json={
                    "planId": rejected_plan_id,
                    "expectedPlanDigest": rejected_plan_digest,
                    "reason": "operator selected reject",
                },
            )
            approve_rejected_response = await client.post(
                "/v1/actions/approvals",
                headers=headers,
                json={"planId": rejected_plan_id, "expectedPlanDigest": rejected_plan_digest},
            )
            reject_approved_response = await client.post(
                "/v1/actions/rejections",
                headers=headers,
                json={"planId": plan_id, "expectedPlanDigest": plan_digest},
            )

        assert registry_response.status_code == 200
        assert registry_response.json()["spec"]["mutationsEnabled"] is False
        assert proposal_response.status_code == 200
        assert plan_response.status_code == 200
        assert stale_approval_response.status_code == 409
        assert approval_response.status_code == 200
        approval_decision = approval_response.json()["spec"]["approvalDecision"]
        assert approval_decision["authorizationAttestationRef"]["bearerAttestationStored"] is False
        assert approval_decision["authorizationAttestationRef"]["attestationDigest"].startswith("sha256:")
        assert approval_decision["kubernetesAuthorization"]["ssarDecision"] == "allowed"
        assert execution_response.status_code == 403
        assert execution_response.json()["detail"]["mutationOutcome"]["status"] == "mutation_disabled"
        assert rejection_response.status_code == 200
        rejection_decision = rejection_response.json()["spec"]["approvalDecision"]
        assert rejection_decision["status"] == "rejected"
        assert rejection_decision["reason"] == "operator selected reject"
        assert approve_rejected_response.status_code == 409
        assert "rejected" in approve_rejected_response.json()["detail"]
        assert reject_approved_response.status_code == 409
        assert len(EXECUTION_RECORDS) == 1
        execution_record = next(iter(EXECUTION_RECORDS.values()))
        assert execution_record["spec"]["executionGrantRef"]["bearerGrantStored"] is False
        assert "claims" not in execution_record["spec"]["executionGrantRef"]
        assert execution_record["spec"]["executionAuthorization"]["allowed"] is True

    asyncio.run(run())

def test_medium_risk_action_requires_separation_of_duties() -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            proposal_response = await client.post(
                "/v1/actions/proposals",
                headers=headers,
                json={
                    "toolName": "set_replicas_within_bounds",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "parameters": {"replicas": 2, "minReplicas": 1, "maxReplicas": 3},
                },
            )
            proposal_id = proposal_response.json()["metadata"]["name"]
            plan_response = await client.post(
                "/v1/actions/plans",
                headers=headers,
                json={"proposalId": proposal_id},
            )
            plan_payload = plan_response.json()
            approval_response = await client.post(
                "/v1/actions/approvals",
                headers=headers,
                json={
                    "planId": plan_payload["metadata"]["name"],
                    "expectedPlanDigest": plan_payload["spec"]["sealedActionPlan"]["digest"]["planDigest"],
                },
            )

        assert proposal_response.status_code == 200
        assert plan_response.status_code == 200
        assert approval_response.status_code == 409
        assert "separation of duties" in approval_response.json()["detail"]

    asyncio.run(run())


def test_approved_different_subject_can_execute_with_product_access(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()
    APPROVAL_DECISIONS.clear()
    EXECUTION_RECORDS.clear()
    requester = safe_subject({"username": "requester@example.com", "uid": "uid-requester", "groups": ["ops"]})
    approver = safe_subject({"username": "approver@example.com", "uid": "uid-approver", "groups": ["ops"]})

    async def fake_subject_review(user_auth_header: str) -> dict:
        if user_auth_header == "Bearer requester-token":
            return requester
        return approver

    async def fake_product_access_review(_user_auth_header: str) -> dict:
        return {"allowed": True, "enabled": True, "required": False}

    async def fake_action_access_review(_user_auth_header: str, _plan: dict) -> dict:
        return {"allowed": True, "enabled": True, "resourceAttributes": {"resource": "deployments"}}

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", fake_subject_review)
    monkeypatch.setattr(gateway_main, "fetch_product_access_review", fake_product_access_review)
    monkeypatch.setattr(gateway_main, "fetch_action_access_review", fake_action_access_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        requester_headers = {"Authorization": "Bearer requester-token"}
        approver_headers = {"Authorization": "Bearer approver-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            proposal_response = await client.post(
                "/v1/actions/proposals",
                headers=requester_headers,
                json={
                    "toolName": "set_replicas_within_bounds",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "parameters": {"replicas": 2, "minReplicas": 1, "maxReplicas": 3},
                },
            )
            proposal_id = proposal_response.json()["metadata"]["name"]
            plan_response = await client.post(
                "/v1/actions/plans",
                headers=requester_headers,
                json={"proposalId": proposal_id},
            )
            plan_payload = plan_response.json()
            plan_digest = plan_payload["spec"]["sealedActionPlan"]["digest"]["planDigest"]
            approval_response = await client.post(
                "/v1/actions/approvals",
                headers=approver_headers,
                json={"planId": plan_payload["metadata"]["name"], "expectedPlanDigest": plan_digest},
            )
            execution_response = await client.post(
                "/v1/actions/execute",
                headers=approver_headers,
                json={
                    "approvalId": approval_response.json()["metadata"]["name"],
                    "planId": plan_payload["metadata"]["name"],
                    "expectedPlanDigest": plan_digest,
                },
            )

        assert proposal_response.status_code == 200
        assert plan_response.status_code == 200
        assert approval_response.status_code == 200
        assert execution_response.status_code == 403
        assert execution_response.json()["detail"]["mutationOutcome"]["status"] == "mutation_disabled"

    asyncio.run(run())


def test_runbook_registry_allows_only_runbook_defined_action_steps() -> None:
    assert RUNBOOK_REGISTRY_DIGEST.startswith("sha256:")
    assert set(RUNBOOK_REGISTRY_ENTRIES) == {
        "deployment_rollout_restart_v1",
        "deployment_bounded_scale_v1",
        "controller_owned_unhealthy_pod_eviction_v1",
        "deployment_rollout_rollback_v1",
        "hpa_bounds_adjustment_v1",
    }
    for runbook in RUNBOOK_REGISTRY_ENTRIES.values():
        for step in runbook["allowedSteps"]:
            assert step["toolName"] in ACTION_REGISTRY_ENTRIES
    assert "delete_pod" not in str(RUNBOOK_REGISTRY_ENTRIES)
    assert "run_command" not in str(RUNBOOK_REGISTRY_ENTRIES)


def test_runbook_plan_uses_runtime_target_and_denies_platform_namespace_without_policy() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = RunbookPlanCreate(
        runbookId="deployment_rollout_restart_v1",
        target=ActionTarget(
            apiVersion="apps/v1",
            kind="Deployment",
            namespace="openshift-example",
            name="operator-managed-app",
            uid="deployment-uid-a",
        ),
        parameters={"restartedAt": "2026-06-21T00:00:00Z"},
    )

    record = build_runbook_plan_record(request, subject)

    assert record["metadata"]["name"].startswith("runbook-plan-")
    assert record["spec"]["target"]["namespace"] == "openshift-example"
    assert record["spec"]["policyResult"]["decision"] == "denied"
    assert "allowPlatformNamespace=true" in record["spec"]["policyResult"]["failures"][0]
    assert record["spec"]["stepPlans"][0]["candidateActionRequest"]["target"]["name"] == "operator-managed-app"


def test_preapproved_patch_schema_rejects_undocumented_or_out_of_bounds_fields() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    valid_request = PatchPreapprovedFieldCreate(
        fieldSchemaId="deployment_progress_deadline_seconds_v1",
        target=ActionTarget(
            apiVersion="apps/v1",
            kind="Deployment",
            namespace="team-a",
            name="web-a",
            uid="deployment-uid-a",
        ),
        value=120,
    )
    record = build_preapproved_patch_record(valid_request, subject)

    assert record["metadata"]["name"].startswith("prepatch-")
    assert record["spec"]["patch"] == {
        "op": "replace",
        "path": "/spec/progressDeadlineSeconds",
        "value": 120,
    }
    assert record["spec"]["status"]["mutationSubmitted"] is False

    with pytest.raises(HTTPException):
        build_preapproved_patch_record(
            valid_request.model_copy(update={"fieldSchemaId": "deployment_unreviewed_field_v1"}),
            subject,
        )
    with pytest.raises(HTTPException):
        build_preapproved_patch_record(valid_request.model_copy(update={"value": 999999}), subject)


def test_runbook_and_preapproved_patch_apis_expose_foundation_records() -> None:
    RUNBOOK_PLANS.clear()
    PREAPPROVED_PATCH_REQUESTS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            registry_response = await client.get("/v1/runbooks/registry", headers=headers)
            plan_response = await client.post(
                "/v1/runbooks/plans",
                headers=headers,
                json={
                    "runbookId": "deployment_rollout_restart_v1",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "parameters": {"restartedAt": "2026-06-21T00:00:00Z"},
                },
            )
            patch_response = await client.post(
                "/v1/runbooks/patch-preapproved-field",
                headers=headers,
                json={
                    "fieldSchemaId": "deployment_revision_history_limit_v1",
                    "target": {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "namespace": "team-a",
                        "name": "web-a",
                        "uid": "deployment-uid-a",
                    },
                    "value": 5,
                },
            )

        assert registry_response.status_code == 200
        assert registry_response.json()["spec"]["digest"] == RUNBOOK_REGISTRY_DIGEST
        assert plan_response.status_code == 200
        assert plan_response.json()["spec"]["status"]["phase"] == "waiting_for_approval"
        assert patch_response.status_code == 200
        assert patch_response.json()["spec"]["status"]["mutationSubmitted"] is False
        assert len(RUNBOOK_PLANS) == 1
        assert len(PREAPPROVED_PATCH_REQUESTS) == 1

    asyncio.run(run())


def test_break_glass_profile_is_disabled_by_default_and_fixed_entrypoint_only() -> None:
    profile = BREAK_GLASS_PROFILES["node_readonly_triage_v1"]

    assert BREAK_GLASS_PROFILE_DIGEST.startswith("sha256:")
    assert profile["enabled"] is False
    assert profile["imageDigest"] == "not-configured"
    assert profile["arbitraryCommandInputAllowed"] is False
    assert profile["fixedEntrypoint"] == [
        "/aiops/breakglass-runner",
        "--profile",
        "node-readonly-triage",
    ]
    assert profile["cleanup"]["activeDeadlineSeconds"] == 300
    assert profile["cleanup"]["ttlSecondsAfterFinished"] == 600
    assert profile["network"]["egressPolicy"] == "deny-except-controller"


def test_break_glass_request_records_disabled_status_without_job_submission() -> None:
    subject = safe_subject({"username": "user@example.com", "uid": "uid-1", "groups": ["ops"]})
    request = BreakGlassRequestCreate(
        profileId="node_readonly_triage_v1",
        targetNode=BreakGlassTargetNode(name="worker-a.example.com", uid="node-uid-a"),
        justification="Need emergency evidence-check node diagnostics for incident review.",
    )

    record = build_break_glass_request_record(request, subject)

    assert record["metadata"]["name"].startswith("breakglass-")
    assert record["spec"]["profile"]["enabled"] is False
    assert record["spec"]["profile"]["arbitraryCommandInputAllowed"] is False
    assert record["spec"]["status"]["phase"] == "disabled"
    assert record["spec"]["status"]["jobSubmitted"] is False
    assert record["spec"]["jobTemplateConstraints"]["scheduling"]["targetNodeName"] == "worker-a.example.com"
    assert record["spec"]["jobTemplateConstraints"]["scheduling"]["targetNodeUid"] == "node-uid-a"
    assert record["spec"]["audit"]["stream"] == "aiopsBreakGlassAudit"


def test_break_glass_api_rejects_arbitrary_command_input_and_records_request() -> None:
    BREAK_GLASS_REQUESTS.clear()

    async def run() -> None:
        transport = httpx.ASGITransport(app=app)
        headers = {"Authorization": "Bearer test-token"}
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            profiles_response = await client.get("/v1/breakglass/profiles", headers=headers)
            command_response = await client.post(
                "/v1/breakglass/requests",
                headers=headers,
                json={
                    "profileId": "node_readonly_triage_v1",
                    "targetNode": {"name": "worker-a.example.com", "uid": "node-uid-a"},
                    "justification": "Need emergency evidence-check node diagnostics for incident review.",
                    "command": "nsenter --mount=/proc/1/ns/mnt sh",
                },
            )
            request_response = await client.post(
                "/v1/breakglass/requests",
                headers=headers,
                json={
                    "profileId": "node_readonly_triage_v1",
                    "targetNode": {"name": "worker-a.example.com", "uid": "node-uid-a"},
                    "justification": "Need emergency evidence-check node diagnostics for incident review.",
                },
            )

        assert profiles_response.status_code == 200
        assert profiles_response.json()["spec"]["enabled"] is False
        assert command_response.status_code == 422
        assert request_response.status_code == 200
        assert request_response.json()["spec"]["status"]["phase"] == "disabled"
        assert request_response.json()["spec"]["status"]["jobSubmitted"] is False
        assert len(BREAK_GLASS_REQUESTS) == 1

    asyncio.run(run())
