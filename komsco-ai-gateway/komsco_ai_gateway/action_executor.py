from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .main import execute_typed_action_plan, parse_bool, redact_sensitive

app = FastAPI(title="KOMSCO AIOps Action Executor", version="0.1.0")

EXECUTOR_ENABLED = parse_bool(os.getenv("KOMSCO_AI_ACTION_EXECUTOR_ENABLED"), default=False)
EXECUTOR_SHARED_TOKEN = os.getenv("KOMSCO_AI_ACTION_EXECUTOR_SHARED_TOKEN", "")


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExecutorActionExecuteRequest(StrictBaseModel):
    sealedActionPlan: dict[str, Any] = Field(min_length=1)
    executionGrantRef: dict[str, Any] = Field(min_length=1)


def verify_executor_ingress(authorization: str | None) -> None:
    if not EXECUTOR_ENABLED:
        raise HTTPException(status_code=403, detail="Action Executor is disabled")
    if not EXECUTOR_SHARED_TOKEN:
        return
    if authorization != f"Bearer {EXECUTOR_SHARED_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid Action Executor caller token")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/executor/actions/execute")
async def execute_action(
    req: ExecutorActionExecuteRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    verify_executor_ingress(authorization)
    grant = req.executionGrantRef
    claims = grant.get("claims") if isinstance(grant, Mapping) else {}
    if isinstance(claims, Mapping) and claims.get("audience") != "aiops-action-executor":
        raise HTTPException(status_code=403, detail="ExecutionGrant audience mismatch")

    result = await execute_typed_action_plan(req.sealedActionPlan)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutorActionResult",
        "spec": redact_sensitive(result),
    }
