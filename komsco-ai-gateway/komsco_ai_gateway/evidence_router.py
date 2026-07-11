from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, Query

from . import evidence_service
from .evidence_service import EvidenceDependencies


def create_evidence_router(
    dependency_provider: Callable[[], EvidenceDependencies],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/auth/subject")
    async def auth_subject(
        authorization: str | None = Header(default=None),
        deps: EvidenceDependencies = Depends(dependency_provider),
    ) -> dict:
        return await evidence_service.auth_subject(authorization, deps)

    @router.get("/v1/evidence")
    async def list_evidence(
        authorization: str | None = Header(default=None),
        incident_id: str | None = Query(default=None, alias="incidentId"),
        run_id: str | None = Query(default=None, alias="runId"),
        deps: EvidenceDependencies = Depends(dependency_provider),
    ) -> dict:
        return await evidence_service.list_evidence(
            authorization, incident_id, run_id, deps,
        )

    @router.get("/v1/evidence/{evidence_id}")
    async def get_evidence(
        evidence_id: str,
        authorization: str | None = Header(default=None),
        deps: EvidenceDependencies = Depends(dependency_provider),
    ) -> dict:
        return await evidence_service.get_evidence(evidence_id, authorization, deps)

    @router.get("/v1/workflows/{run_id}")
    async def get_workflow(
        run_id: str,
        authorization: str | None = Header(default=None),
        deps: EvidenceDependencies = Depends(dependency_provider),
    ) -> dict:
        return await evidence_service.get_workflow(run_id, authorization, deps)

    return router
