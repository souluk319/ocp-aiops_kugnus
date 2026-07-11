import asyncio
import inspect

import httpx
from fastapi.routing import APIRoute

from komsco_ai_gateway import knowledge_router, knowledge_service
from komsco_ai_gateway import main as gateway_main


EXTRACTED_ROUTES = {
    ("/v1/runbooks/registry", "GET"),
    ("/v1/rag/uploads", "GET"),
    ("/v1/rag/uploads", "POST"),
    ("/v1/rag/uploads/file", "POST"),
    ("/v1/rag/search", "POST"),
    ("/v1/runbooks/plans", "POST"),
    ("/v1/runbooks/plans/{plan_id}", "GET"),
    ("/v1/runbooks/patch-preapproved-field", "POST"),
    ("/v1/runbooks/patch-preapproved-field/{request_id}", "GET"),
    ("/v1/breakglass/profiles", "GET"),
    ("/v1/breakglass/requests", "POST"),
    ("/v1/breakglass/requests/{request_id}", "GET"),
    ("/v1/rca/last", "GET"),
}


def test_knowledge_router_owns_exact_extracted_paths() -> None:
    router = knowledge_router.create_knowledge_router(gateway_main.knowledge_dependencies)
    routes = {
        (route.path, method): route.endpoint.__module__
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
    }

    assert set(routes) == EXTRACTED_ROUTES
    assert set(routes.values()) == {"komsco_ai_gateway.knowledge_router"}


def test_knowledge_modules_do_not_import_main() -> None:
    for module in (knowledge_router, knowledge_service):
        source = inspect.getsource(module)
        assert "from . import main" not in source
        assert "import komsco_ai_gateway.main" not in source


def test_knowledge_dependencies_keep_existing_store_identity() -> None:
    stores = gateway_main.knowledge_dependencies().stores

    assert stores.runbook_plans is gateway_main.RUNBOOK_PLANS
    assert stores.preapproved_patch_requests is gateway_main.PREAPPROVED_PATCH_REQUESTS
    assert stores.break_glass_requests is gateway_main.BREAK_GLASS_REQUESTS


def test_knowledge_routes_resolve_dependencies_at_request_time(monkeypatch) -> None:
    seen: list[str | None] = []

    def current_verify_bearer_header(authorization: str | None) -> str:
        seen.append(authorization)
        return authorization or ""

    monkeypatch.setattr(gateway_main, "verify_bearer_header", current_verify_bearer_header)

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/v1/runbooks/registry",
                headers={"Authorization": "Bearer current-token"},
            )

        assert response.status_code == 200
        assert response.json()["kind"] == "RunbookRegistry"

    asyncio.run(run())
    assert seen == ["Bearer current-token"]


def test_last_rca_route_reads_latest_request_time_state(monkeypatch) -> None:
    monkeypatch.setattr(gateway_main, "LAST_RUNTIME_TOOL_PLAN", {"kind": "ToolPlan"})
    monkeypatch.setattr(gateway_main, "LAST_RCA_CONTEXT", {"kind": "RcaContext"})

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/v1/rca/last",
                headers={"Authorization": "Bearer current-token"},
            )

        assert response.status_code == 200
        assert response.json()["toolPlan"] == {"kind": "ToolPlan"}
        assert response.json()["rcaContext"] == {"kind": "RcaContext"}

    asyncio.run(run())


def test_main_keeps_public_knowledge_wrappers() -> None:
    wrapper_names = {
        "get_runbook_registry",
        "list_rag_uploads",
        "create_rag_upload",
        "create_rag_upload_file",
        "search_rag_runbooks",
        "create_runbook_plan",
        "get_runbook_plan",
        "create_preapproved_patch_request",
        "get_preapproved_patch_request",
        "get_break_glass_profiles",
        "create_break_glass_request",
        "get_break_glass_request",
        "get_last_rca_context",
    }

    assert all(inspect.iscoroutinefunction(getattr(gateway_main, name)) for name in wrapper_names)
