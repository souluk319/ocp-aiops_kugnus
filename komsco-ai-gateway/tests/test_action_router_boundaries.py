from __future__ import annotations

import ast
import asyncio
from pathlib import Path

import httpx

from komsco_ai_gateway import action_api_service, action_router
from komsco_ai_gateway import main as gateway_main


ACTION_PATHS = {
    "/v1/actions/registry",
    "/v1/actions/proposals",
    "/v1/actions/proposals/{proposal_id}",
    "/v1/actions/candidate-plans",
    "/v1/actions/plans",
    "/v1/actions/plans/{plan_id}",
    "/v1/actions/approvals",
    "/v1/actions/rejections",
    "/v1/actions/execute",
}


def test_action_router_owns_only_action_lifecycle_paths() -> None:
    router = action_router.create_action_router(gateway_main.action_api_dependencies)

    paths = {route.path for route in router.routes}

    assert paths == ACTION_PATHS
    assert not any("/dev/" in path or "/runbooks/" in path for path in paths)
    for name in (
        "get_action_registry",
        "create_action_proposal",
        "create_action_candidate_plan",
        "get_action_proposal",
        "create_action_plan",
        "get_action_plan",
        "create_approval_decision",
        "reject_action_plan",
        "execute_action",
    ):
        assert callable(getattr(gateway_main, name))


def test_action_modules_do_not_import_main() -> None:
    for module in (action_api_service, action_router):
        path = Path(module.__file__)
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        imported_modules = {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module
        }
        assert "main" not in imported_modules
        assert "komsco_ai_gateway.main" not in imported_modules


def test_action_dependencies_preserve_gateway_state_identity() -> None:
    stores = gateway_main.action_api_dependencies().stores

    assert stores.action_proposals is gateway_main.ACTION_PROPOSALS
    assert stores.sealed_action_plans is gateway_main.SEALED_ACTION_PLANS
    assert stores.approval_decisions is gateway_main.APPROVAL_DECISIONS
    assert stores.execution_records is gateway_main.EXECUTION_RECORDS
    assert stores.auto_execute_target_locks is gateway_main._AUTO_EXECUTE_TARGET_LOCKS


def test_action_router_resolves_current_main_bindings_per_request(monkeypatch) -> None:
    seen: list[str | None] = []

    def patched_verify_bearer_header(value: str | None) -> str:
        seen.append(value)
        return "Bearer patched"

    monkeypatch.setattr(gateway_main, "verify_bearer_header", patched_verify_bearer_header)
    monkeypatch.setattr(gateway_main, "MUTATIONS_ENABLED", True)

    async def request_registry() -> httpx.Response:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            return await client.get(
                "/v1/actions/registry",
                headers={"Authorization": "Bearer original"},
            )

    response = asyncio.run(request_registry())

    assert response.status_code == 200
    assert response.json()["spec"]["mutationsEnabled"] is True
    assert seen == ["Bearer original"]
