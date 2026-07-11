import asyncio
import inspect

import httpx
from fastapi.routing import APIRoute

from komsco_ai_gateway import (
    diagnostics_router,
    diagnostics_service,
    evidence_router,
    evidence_service,
)
from komsco_ai_gateway import main as gateway_main


EXTRACTED_ROUTES = {
    ("/v1/auth/subject", "GET"): "komsco_ai_gateway.evidence_router",
    ("/v1/evidence", "GET"): "komsco_ai_gateway.evidence_router",
    ("/v1/evidence/{evidence_id}", "GET"): "komsco_ai_gateway.evidence_router",
    ("/v1/workflows/{run_id}", "GET"): "komsco_ai_gateway.evidence_router",
    ("/v1/diagnostics/collectors", "GET"): "komsco_ai_gateway.diagnostics_router",
    ("/v1/diagnostics/requests", "POST"): "komsco_ai_gateway.diagnostics_router",
    ("/v1/diagnostics/requests/{request_id}", "GET"): "komsco_ai_gateway.diagnostics_router",
}


def test_evidence_and_diagnostics_routers_own_extracted_paths() -> None:
    routers = (
        evidence_router.create_evidence_router(gateway_main.evidence_dependencies),
        diagnostics_router.create_diagnostics_router(gateway_main.diagnostics_dependencies),
    )
    owners = {
        (route.path, method): route.endpoint.__module__
        for router in routers
        for route in router.routes
        if isinstance(route, APIRoute)
        for method in route.methods
        if (route.path, method) in EXTRACTED_ROUTES
    }

    assert owners == EXTRACTED_ROUTES


def test_evidence_and_diagnostics_modules_do_not_import_main() -> None:
    for module in (
        evidence_router,
        evidence_service,
        diagnostics_router,
        diagnostics_service,
    ):
        source = inspect.getsource(module)
        assert "from . import main" not in source
        assert "import komsco_ai_gateway.main" not in source


def test_extracted_routes_resolve_dependencies_at_request_time(monkeypatch) -> None:
    calls: list[str] = []

    async def current_subject_review(user_auth_header: str) -> dict:
        calls.append(user_auth_header)
        return {
            "username": "request-time-user",
            "uid": "request-time-uid",
            "groups": [],
            "groupsDigest": "sha256:request-time",
            "authenticatedByCluster": "test",
        }

    monkeypatch.setattr(gateway_main, "fetch_self_subject_review", current_subject_review)

    async def run() -> None:
        transport = httpx.ASGITransport(app=gateway_main.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/v1/auth/subject",
                headers={"Authorization": "Bearer current-token"},
            )

        assert response.status_code == 200
        assert response.json()["username"] == "request-time-user"

    asyncio.run(run())
    assert calls == ["Bearer current-token"]


def test_extracted_openapi_paths_keep_public_methods_and_parameter_aliases() -> None:
    paths = gateway_main.app.openapi()["paths"]

    assert {
        (path, method.upper())
        for path, _expected_method in EXTRACTED_ROUTES
        for method in paths[path]
        if method in {"get", "post"}
        and path in {item[0] for item in EXTRACTED_ROUTES}
    } == set(EXTRACTED_ROUTES)
    evidence_parameters = paths["/v1/evidence"]["get"]["parameters"]
    assert [(item["name"], item["in"]) for item in evidence_parameters] == [
        ("incidentId", "query"),
        ("runId", "query"),
        ("authorization", "header"),
    ]
