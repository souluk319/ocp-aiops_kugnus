import ast
import asyncio
from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest
from fastapi import HTTPException

from komsco_ai_gateway import action_candidate_plans
from komsco_ai_gateway import main as gateway_main
from komsco_ai_gateway.gateway_state import ACTION_PROPOSALS, SEALED_ACTION_PLANS
from komsco_ai_gateway.schemas import ActionCandidatePlanCreate, ActionCandidateTargetCreate
from komsco_ai_gateway.security import safe_subject


def candidate_request(
    *,
    kind: str = "Deployment",
    namespace: str | None = "team-a",
    name: str = "web",
    source_type: str | None = None,
    parameters: dict | None = None,
) -> ActionCandidatePlanCreate:
    return ActionCandidatePlanCreate(
        candidateId="action-candidate-test",
        title="Action candidate test",
        sourceType=source_type,
        target=ActionCandidateTargetCreate(
            apiVersion="v1" if kind in {"Pod", "Namespace"} else "apps/v1",
            kind=kind,
            namespace=namespace,
            name=name,
        ),
        parameters=parameters or {},
    )


def test_test_pod_create_candidate_maps_to_executable_crashloop_action(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ENABLED", True)
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ALLOWED_NAMESPACES", {"gpu-test-kugnus"})
    intent = gateway_main.action_candidate_plan_intent(
        ActionCandidatePlanCreate(
            candidateId="chat-test-pod-create-gpu-test-kugnus",
            title="CrashLoop test Pod 3 create",
            sourceFindingId="test-pod-create-gpu-test-kugnus",
            sourceType="test_pod_create_review",
            target=ActionCandidateTargetCreate(
                apiVersion="v1",
                kind="Namespace",
                name="gpu-test-kugnus",
                namespace="gpu-test-kugnus",
            ),
            parameters={
                "count": 3,
                "failureMode": "crashloop",
                "image": "registry.access.redhat.com/ubi9/ubi-minimal:latest",
                "namePrefix": "aiops-test-pod",
            },
        )
    )

    assert intent["toolName"] == "create_crashloop_test_pods"
    assert intent["parameters"]["count"] == 3
    assert intent["parameters"]["failureMode"] == "crashloop"


def test_test_pod_create_candidate_plan_preserves_pods_create_action(monkeypatch) -> None:
    ACTION_PROPOSALS.clear()
    SEALED_ACTION_PLANS.clear()

    async def fake_fetch_ocp_json(_client, path: str, _authorization: str, *_, **__) -> dict:
        assert path == "/api/v1/namespaces/gpu-test-kugnus"
        return {
            "apiVersion": "v1",
            "kind": "Namespace",
            "metadata": {"name": "gpu-test-kugnus", "uid": "namespace-uid-gpu-test"},
        }

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ENABLED", True)
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ALLOWED_NAMESPACES", {"gpu-test-kugnus"})
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch_ocp_json)

    request = ActionCandidatePlanCreate(
        candidateId="chat-test-pod-create-gpu-test-kugnus",
        title="CrashLoop test Pod 3 create",
        sourceFindingId="test-pod-create-gpu-test-kugnus",
        sourceType="create_crashloop_test_pods",
        target=ActionCandidateTargetCreate(
            apiVersion="v1",
            kind="Namespace",
            name="gpu-test-kugnus",
            namespace="gpu-test-kugnus",
        ),
        parameters={
            "count": 3,
            "failureMode": "crashloop",
            "image": "registry.access.redhat.com/ubi9/ubi-minimal:latest",
            "namePrefix": "aiops-test-pod",
        },
    )
    subject = safe_subject({"username": "dev-user", "uid": "uid-dev", "groups": ["system:authenticated"]})

    result = asyncio.run(
        gateway_main.create_plan_from_action_candidate(request, "Bearer user-token", subject)
    )

    sealed_plan = result["spec"]["plan"]["spec"]["sealedActionPlan"]
    assert sealed_plan["action"]["toolName"] == "create_crashloop_test_pods"
    assert sealed_plan["action"]["authorization"]["resource"] == "pods"
    assert sealed_plan["action"]["authorization"]["verb"] == "create"
    assert sealed_plan["action"]["normalizedParameters"]["count"] == 3
    assert sealed_plan["action"]["normalizedParameters"]["failureMode"] == "crashloop"
    assert sealed_plan["safety"]["risk"] == "low"
    assert len(ACTION_PROPOSALS) == 1
    assert len(SEALED_ACTION_PLANS) == 1


def test_action_candidate_plan_intent_maps_deployment_to_restart_action() -> None:
    intent = gateway_main.action_candidate_plan_intent(
        ActionCandidatePlanCreate(
            candidateId="action-candidate-deploy",
            title="Deployment restart candidate",
            target=ActionCandidateTargetCreate(
                apiVersion="apps/v1",
                kind="Deployment",
                namespace="team-a",
                name="web",
            ),
        )
    )

    assert intent["apiVersion"] == "apps/v1"
    assert intent["kind"] == "Deployment"
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "web"
    assert intent["toolName"] == "rollout_restart_deployment"
    assert "restartedAt" in intent["parameters"]


def test_action_candidate_plan_intent_maps_deployment_command_fix_to_patch_action() -> None:
    intent = gateway_main.action_candidate_plan_intent(
        ActionCandidatePlanCreate(
            candidateId="action-candidate-deployment-command-fix",
            sourceType="deployment_container_command_fix",
            title="Deployment command update",
            target=ActionCandidateTargetCreate(
                apiVersion="apps/v1",
                kind="Deployment",
                namespace="team-a",
                name="sample-crashy",
            ),
            parameters={
                "command": ["python", "-c", "import time; time.sleep(86400)"],
                "containerName": "app",
                "reason": "CrashLoopBackOff command fix",
            },
        )
    )

    assert intent["apiVersion"] == "apps/v1"
    assert intent["kind"] == "Deployment"
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "sample-crashy"
    assert intent["toolName"] == "set_deployment_container_command"
    assert intent["parameters"]["containerName"] == "app"
    assert intent["parameters"]["command"] == ["python", "-c", "import time; time.sleep(86400)"]


def test_action_candidate_plan_intent_maps_pod_to_eviction_action() -> None:
    intent = gateway_main.action_candidate_plan_intent(
        candidate_request(kind="Pod", name="web-abc")
    )

    assert intent["apiVersion"] == "v1"
    assert intent["kind"] == "Pod"
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "web-abc"
    assert intent["toolName"] == "evict_one_unhealthy_controller_owned_pod"
    assert intent["parameters"] == {"reason": "action_candidate_unhealthy_pod_eviction"}


def test_action_candidate_plan_intent_maps_pod_diagnostic_to_review_action() -> None:
    request = candidate_request(kind="Pod", name="web-abc", source_type="pod_diagnostic_review")
    request = request.model_copy(update={"sourceFindingId": "pod-crashloop-diagnostic", "title": "diagnostic plan"})
    intent = gateway_main.action_candidate_plan_intent(request)

    assert intent["apiVersion"] == "v1"
    assert intent["kind"] == "Pod"
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "web-abc"
    assert intent["toolName"] == "pod_diagnostic_review"
    assert intent["parameters"] == {"includePreviousLogs": True, "includeEvents": True}


def test_action_candidate_plan_intent_keeps_pod_fix_review_separate_from_diagnostic() -> None:
    request = candidate_request(kind="Pod", name="web-abc", source_type="pod_fix_or_rollback_review")
    request = request.model_copy(update={"sourceFindingId": "pod-crashloop-fix-review", "title": "fix review plan"})
    intent = gateway_main.action_candidate_plan_intent(request)

    assert intent["apiVersion"] == "v1"
    assert intent["kind"] == "Pod"
    assert intent["namespace"] == "team-a"
    assert intent["targetName"] == "web-abc"
    assert intent["toolName"] == "pod_fix_or_rollback_review"
    assert intent["parameters"] == {
        "includeOwnerChain": True,
        "includeRolloutHistory": True,
        "includeTemplateReview": True,
    }


def test_main_builds_fresh_frozen_config_and_dependencies(monkeypatch) -> None:
    first_config = gateway_main._action_candidate_plan_config()
    first_dependencies = gateway_main._action_candidate_plan_dependencies()

    def replacement_fetch(*_args, **_kwargs):
        return None

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.changed:6443")
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ALLOWED_NAMESPACES", {"changed"})
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", replacement_fetch)
    second_config = gateway_main._action_candidate_plan_config()
    second_dependencies = gateway_main._action_candidate_plan_dependencies()

    assert first_config is not second_config
    assert first_dependencies is not second_dependencies
    assert second_config.openshift_api_url == "https://api.changed:6443"
    assert second_config.test_pod_create_allowed_namespaces == frozenset({"changed"})
    assert second_dependencies.fetch_ocp_json is replacement_fetch
    with pytest.raises(FrozenInstanceError):
        second_config.openshift_api_url = "changed"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        second_dependencies.fetch_ocp_json = first_dependencies.fetch_ocp_json  # type: ignore[misc]


def test_url_check_precedes_current_main_intent_callback(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "")
    monkeypatch.setattr(
        gateway_main,
        "action_candidate_plan_intent",
        lambda _req: pytest.fail("intent must not run before the OpenShift URL check"),
    )

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gateway_main.create_plan_from_action_candidate(
                candidate_request(), "Bearer token", {"username": "operator"}
            )
        )

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == "OpenShift API URL이 없어 조치 대상 리소스를 확인하지 못했습니다."


@pytest.mark.parametrize(
    ("candidate", "status_code", "detail"),
    [
        (
            candidate_request(kind="StatefulSet"),
            400,
            "Action candidate target kind StatefulSet is not connected to an executable action yet",
        ),
        (
            candidate_request(
                kind="Namespace",
                namespace="test-a",
                name="test-a",
                source_type="test_pod_create_review",
                parameters={"count": 1},
            ),
            403,
            "CrashLoop test Pod creation is disabled in product mode",
        ),
    ],
)
def test_intent_error_contracts(monkeypatch, candidate, status_code, detail) -> None:
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ENABLED", False)
    with pytest.raises(HTTPException) as exc_info:
        gateway_main.action_candidate_plan_intent(candidate)
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == detail


@pytest.mark.parametrize(
    ("count", "allowed_namespaces", "status_code", "detail"),
    [
        (True, {"test-a"}, 400, "test pod count must be explicitly set between 1 and 5"),
        (6, {"test-a"}, 400, "test pod count must be explicitly set between 1 and 5"),
        (1, {"other"}, 403, "namespace is outside the test Pod creation allowlist"),
    ],
)
def test_test_pod_intent_validation_contracts(
    monkeypatch, count, allowed_namespaces, status_code, detail
) -> None:
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ENABLED", True)
    monkeypatch.setattr(gateway_main, "TEST_POD_CREATE_ALLOWED_NAMESPACES", allowed_namespaces)
    request = candidate_request(
        kind="Namespace",
        namespace="test-a",
        name="test-a",
        source_type="test_pod_create_review",
        parameters={"count": count},
    )

    with pytest.raises(HTTPException) as exc_info:
        gateway_main.action_candidate_plan_intent(request)
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == detail


class FakeAsyncClient:
    calls: list[dict] = []

    def __init__(self, **kwargs) -> None:
        self.calls.append(kwargs)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None


@pytest.mark.parametrize(
    ("resolved", "status_code", "detail"),
    [
        (
            {"status": "ambiguous", "candidates": [{"namespace": "team-a"}, {"namespace": "team-b"}]},
            409,
            {
                "candidates": [{"namespace": "team-a"}, {"namespace": "team-b"}],
                "message": "Deployment `web` 후보가 여러 namespace에서 발견되었습니다.",
                "status": "ambiguous",
            },
        ),
        (
            {"status": "missing_namespace"},
            400,
            "Deployment `web` 조치에는 namespace가 필요합니다.",
        ),
        (
            {"status": "not_found"},
            404,
            "Deployment `team-a/web`를 찾지 못했습니다.",
        ),
        (
            {"status": "found", "target": None},
            404,
            "조치 대상 리소스를 찾지 못했습니다.",
        ),
        (
            {"status": "found", "target": {"metadata": {"namespace": "team-a", "name": "web"}}},
            409,
            "조치 대상 UID를 확인하지 못했습니다.",
        ),
    ],
)
def test_resolved_target_error_contracts(monkeypatch, resolved, status_code, detail) -> None:
    async def fake_resolve(*_args, **_kwargs):
        return resolved

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(gateway_main, "resolve_natural_action_target", fake_resolve)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gateway_main.create_plan_from_action_candidate(
                candidate_request(), "Bearer token", {"username": "operator"}
            )
        )
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == detail


@pytest.mark.parametrize(
    ("live_target", "status_code", "detail"),
    [
        (None, 404, "Namespace `team-a`를 찾지 못했습니다."),
        ({"metadata": {"name": "team-a"}}, 409, "Namespace UID를 확인하지 못했습니다."),
    ],
)
def test_namespace_target_error_contracts(monkeypatch, live_target, status_code, detail) -> None:
    async def fake_fetch(*_args, **_kwargs):
        return live_target

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            gateway_main.create_plan_from_action_candidate(
                candidate_request(kind="Namespace", name="team-a"),
                "Bearer token",
                {"username": "operator"},
            )
        )
    assert exc_info.value.status_code == status_code
    assert exc_info.value.detail == detail


@pytest.mark.parametrize(("kind", "expects_auto"), [("Deployment", True), ("Namespace", False)])
def test_store_metric_order_auto_execute_boundary_and_httpx_factory_compatibility(
    monkeypatch, kind, expects_auto
) -> None:
    events: list[str] = []
    FakeAsyncClient.calls.clear()

    async def fake_fetch(*_args, **_kwargs):
        return {"metadata": {"name": "web", "uid": "uid-1"}}

    async def fake_resolve(*_args, **_kwargs):
        return {
            "status": "found",
            "target": {"metadata": {"namespace": "team-a", "name": "web", "uid": "uid-1"}},
        }

    def fake_build_proposal(*_args, **_kwargs):
        events.append("build:proposal")
        return {"metadata": {"name": "proposal-1"}, "spec": {}}

    def fake_build_plan(*_args, **_kwargs):
        events.append("build:plan")
        return {
            "metadata": {"name": "plan-1", "createdAt": "2026-07-11T00:00:00Z"},
            "spec": {"sealedActionPlan": {"digest": {"planDigest": "digest-1"}}},
        }

    async def fake_put(store_name, _record_id, _record):
        events.append(f"store:{store_name}")

    def fake_metric(name):
        events.append(f"metric:{name}")

    async def fake_auto(*_args, **_kwargs):
        events.append("auto")
        return {"autoExecuted": True}

    monkeypatch.setattr(gateway_main, "OPENSHIFT_API_URL", "https://api.test:6443")
    monkeypatch.setattr(gateway_main.httpx, "AsyncClient", FakeAsyncClient)
    monkeypatch.setattr(gateway_main, "fetch_ocp_json", fake_fetch)
    monkeypatch.setattr(gateway_main, "resolve_natural_action_target", fake_resolve)
    monkeypatch.setattr(gateway_main, "build_action_proposal_record", fake_build_proposal)
    monkeypatch.setattr(gateway_main, "build_sealed_action_plan_record", fake_build_plan)
    monkeypatch.setattr(gateway_main, "bounded_put_record", fake_put)
    monkeypatch.setattr(gateway_main, "increment_metric", fake_metric)
    monkeypatch.setattr(gateway_main, "maybe_auto_approve_and_execute", fake_auto)

    result = asyncio.run(
        gateway_main.create_plan_from_action_candidate(
            candidate_request(kind=kind), "Bearer token", {"username": "operator"}
        )
    )

    expected = [
        "build:proposal",
        "store:actionProposals",
        "metric:aiops_action_proposals_total",
        "build:plan",
        "store:sealedActionPlans",
        "metric:aiops_action_plans_total",
    ]
    if expects_auto:
        expected.append("auto")
    assert events == expected
    assert ("autoExecuted" in result["spec"]) is expects_auto
    assert len(FakeAsyncClient.calls) == 1
    assert FakeAsyncClient.calls[0]["verify"] == gateway_main.OPENSHIFT_API_CA_FILE
    assert FakeAsyncClient.calls[0]["timeout"].connect == 5.0
    assert FakeAsyncClient.calls[0]["timeout"].read == 20.0


def test_public_symbols_and_new_module_has_no_main_import() -> None:
    assert callable(gateway_main.action_candidate_plan_intent)
    assert callable(gateway_main.create_plan_from_action_candidate)
    assert callable(action_candidate_plans.action_candidate_plan_intent)
    assert callable(action_candidate_plans.create_plan_from_action_candidate)

    module_path = Path(action_candidate_plans.__file__)
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_from = {
        node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert "komsco_ai_gateway.main" not in imported_modules
    assert "main" not in imported_from
