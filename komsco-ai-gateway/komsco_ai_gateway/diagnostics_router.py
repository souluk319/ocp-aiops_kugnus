from collections.abc import Callable

from fastapi import APIRouter, Depends, Header

from . import diagnostics_service
from .diagnostics_service import DiagnosticsDependencies
from .schemas import DiagnosticRequestCreate


def create_diagnostics_router(
    dependency_provider: Callable[[], DiagnosticsDependencies],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/diagnostics/collectors")
    async def get_diagnostic_collectors(
        authorization: str | None = Header(default=None),
        deps: DiagnosticsDependencies = Depends(dependency_provider),
    ) -> dict:
        return diagnostics_service.get_diagnostic_collectors(authorization, deps)

    @router.post("/v1/diagnostics/requests")
    async def create_diagnostic_request(
        req: DiagnosticRequestCreate,
        authorization: str | None = Header(default=None),
        deps: DiagnosticsDependencies = Depends(dependency_provider),
    ) -> dict:
        return await diagnostics_service.create_diagnostic_request(req, authorization, deps)

    @router.get("/v1/diagnostics/requests/{request_id}")
    async def get_diagnostic_request(
        request_id: str,
        authorization: str | None = Header(default=None),
        deps: DiagnosticsDependencies = Depends(dependency_provider),
    ) -> dict:
        return await diagnostics_service.get_diagnostic_request(request_id, authorization, deps)

    return router
