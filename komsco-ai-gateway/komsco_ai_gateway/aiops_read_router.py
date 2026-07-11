from collections.abc import Callable

from fastapi import APIRouter, Depends, Header, Query

from . import aiops_read_service
from .aiops_read_service import AiopsReadDependencies


def create_aiops_read_router(
    dependency_provider: Callable[[], AiopsReadDependencies],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/cluster/summary")
    async def cluster_summary(
        authorization: str | None = Header(default=None),
        deps: AiopsReadDependencies = Depends(dependency_provider),
    ) -> dict:
        return await aiops_read_service.cluster_summary(authorization, deps)

    @router.get("/v1/aiops/overview")
    async def aiops_overview(
        authorization: str | None = Header(default=None),
        deps: AiopsReadDependencies = Depends(dependency_provider),
    ) -> dict:
        return await aiops_read_service.aiops_overview(authorization, deps)

    @router.get("/v1/aiops/anomalies")
    async def aiops_anomalies(
        authorization: str | None = Header(default=None),
        namespace: str | None = Query(default=None),
        since_minutes: int = Query(default=60, alias="sinceMinutes", ge=1, le=1440),
        limit: int = Query(default=50, ge=1, le=200),
        deps: AiopsReadDependencies = Depends(dependency_provider),
    ) -> dict:
        return await aiops_read_service.aiops_anomalies(
            authorization, namespace, since_minutes, limit, deps,
        )

    @router.get("/v1/aiops/action-candidates")
    async def aiops_action_candidates(
        authorization: str | None = Header(default=None),
        deps: AiopsReadDependencies = Depends(dependency_provider),
    ) -> dict:
        return await aiops_read_service.aiops_action_candidates(authorization, deps)

    @router.get("/v1/aiops/events")
    async def get_aiops_events(
        authorization: str | None = Header(default=None),
        limit: int = Query(default=50, ge=1, le=200),
        deps: AiopsReadDependencies = Depends(dependency_provider),
    ) -> dict:
        return await aiops_read_service.get_aiops_events(authorization, limit, deps)

    @router.get("/v1/aiops/status")
    async def get_aiops_status(
        authorization: str | None = Header(default=None),
        deps: AiopsReadDependencies = Depends(dependency_provider),
    ) -> dict:
        return await aiops_read_service.get_aiops_status(authorization, deps)

    return router
