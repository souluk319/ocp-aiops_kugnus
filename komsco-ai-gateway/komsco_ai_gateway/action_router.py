from collections.abc import Callable

from fastapi import APIRouter, Depends, Header

from . import action_api_service
from .action_api_service import ActionApiDependencies
from .schemas import (
    ActionCandidatePlanCreate,
    ActionExecutionCreate,
    ActionProposalCreate,
    ActionRejectionCreate,
    ApprovalDecisionCreate,
    SealedActionPlanCreate,
)


def create_action_router(dependency_provider: Callable[[], ActionApiDependencies]) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/actions/registry")
    async def get_action_registry(
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return action_api_service.get_action_registry(authorization, deps)

    @router.post("/v1/actions/proposals")
    async def create_action_proposal(
        req: ActionProposalCreate,
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return await action_api_service.create_action_proposal(req, authorization, deps)

    @router.post("/v1/actions/candidate-plans")
    async def create_action_candidate_plan(
        req: ActionCandidatePlanCreate,
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return await action_api_service.create_action_candidate_plan(req, authorization, deps)

    @router.get("/v1/actions/proposals/{proposal_id}")
    async def get_action_proposal(
        proposal_id: str,
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return await action_api_service.get_action_proposal(proposal_id, authorization, deps)

    @router.post("/v1/actions/plans")
    async def create_action_plan(
        req: SealedActionPlanCreate,
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return await action_api_service.create_action_plan(req, authorization, deps)

    @router.get("/v1/actions/plans/{plan_id}")
    async def get_action_plan(
        plan_id: str,
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return await action_api_service.get_action_plan(plan_id, authorization, deps)

    @router.post("/v1/actions/approvals")
    async def create_approval_decision(
        req: ApprovalDecisionCreate,
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return await action_api_service.create_approval_decision(req, authorization, deps)

    @router.post("/v1/actions/rejections")
    async def reject_action_plan(
        req: ActionRejectionCreate,
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return await action_api_service.reject_action_plan(req, authorization, deps)

    @router.post("/v1/actions/execute")
    async def execute_action(
        req: ActionExecutionCreate,
        authorization: str | None = Header(default=None),
        deps: ActionApiDependencies = Depends(dependency_provider),
    ) -> dict:
        return await action_api_service.execute_action(req, authorization, deps)

    return router
