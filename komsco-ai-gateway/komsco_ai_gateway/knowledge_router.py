from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Header, UploadFile

from . import knowledge_service
from .knowledge_service import KnowledgeDependencies
from .rag_pgvector import RagDocumentUploadCreate
from .schemas import (
    BreakGlassRequestCreate,
    PatchPreapprovedFieldCreate,
    RagSearchCreate,
    RunbookPlanCreate,
)


def create_knowledge_router(
    dependency_provider: Callable[[], KnowledgeDependencies],
) -> APIRouter:
    router = APIRouter()

    @router.get("/v1/runbooks/registry")
    async def get_runbook_registry(
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return knowledge_service.get_runbook_registry(authorization, deps)

    @router.get("/v1/rag/uploads")
    async def list_rag_uploads(
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.list_rag_uploads(authorization, deps)

    @router.post("/v1/rag/uploads")
    async def create_rag_upload(
        req: RagDocumentUploadCreate,
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.create_rag_upload(req, authorization, deps)

    @router.post("/v1/rag/uploads/file")
    async def create_rag_upload_file(
        file: UploadFile = File(...),
        authorization: str | None = Header(default=None),
        labels: str = Form(default="{}"),
        customer: str = Form(default="komsco"),
        namespace: str = Form(default="komsco-ai-kugnus"),
        run_id: str | None = Form(default=None),
        source_type: str = Form(default="user-upload"),
        source_uri: str | None = Form(default=None),
        version: str = Form(default="v0.1.5"),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.create_rag_upload_file(
            file,
            authorization,
            labels,
            customer,
            namespace,
            run_id,
            source_type,
            source_uri,
            version,
            deps,
        )

    @router.post("/v1/rag/search")
    async def search_rag_runbooks(
        req: RagSearchCreate,
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.search_rag_runbooks(req, authorization, deps)

    @router.post("/v1/runbooks/plans")
    async def create_runbook_plan(
        req: RunbookPlanCreate,
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.create_runbook_plan(req, authorization, deps)

    @router.get("/v1/runbooks/plans/{plan_id}")
    async def get_runbook_plan(
        plan_id: str,
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.get_runbook_plan(plan_id, authorization, deps)

    @router.post("/v1/runbooks/patch-preapproved-field")
    async def create_preapproved_patch_request(
        req: PatchPreapprovedFieldCreate,
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.create_preapproved_patch_request(req, authorization, deps)

    @router.get("/v1/runbooks/patch-preapproved-field/{request_id}")
    async def get_preapproved_patch_request(
        request_id: str,
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.get_preapproved_patch_request(request_id, authorization, deps)

    @router.get("/v1/breakglass/profiles")
    async def get_break_glass_profiles(
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return knowledge_service.get_break_glass_profiles(authorization, deps)

    @router.post("/v1/breakglass/requests")
    async def create_break_glass_request(
        req: BreakGlassRequestCreate,
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.create_break_glass_request(req, authorization, deps)

    @router.get("/v1/breakglass/requests/{request_id}")
    async def get_break_glass_request(
        request_id: str,
        authorization: str | None = Header(default=None),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        return await knowledge_service.get_break_glass_request(request_id, authorization, deps)

    @router.get("/v1/rca/last")
    async def get_last_rca_context(
        authorization: str = Header(default=""),
        deps: KnowledgeDependencies = Depends(dependency_provider),
    ) -> dict[str, Any]:
        """최근 채팅 실행의 Tool Plan + Evidence 상태 + RCA 결과를 반환.

        인증 토큰이 없거나 만료된 경우 401을 반환합니다.
        아직 채팅 기록이 없으면 404를 반환합니다.
        """
        return knowledge_service.get_last_rca_context(authorization, deps)

    return router
