from __future__ import annotations

import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .action_approvals import parse_rfc3339
from .action_execution import execute_typed_action_plan
from .action_records import sealed_action_plan_digest
from .security import canonical_digest, redact_sensitive
from .settings import parse_bool

app = FastAPI(title="KOMSCO AIOps Action Executor", version="0.1.3")

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
        raise HTTPException(status_code=503, detail="Action Executor shared token is not configured")
    if authorization != f"Bearer {EXECUTOR_SHARED_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid Action Executor caller token")


def verify_execution_grant(sealed_plan: Mapping[str, Any], grant: Mapping[str, Any]) -> None:
    claims = grant.get("claims")
    if not isinstance(claims, Mapping):
        raise HTTPException(status_code=403, detail="ExecutionGrant claims are required")
    if claims.get("audience") != "aiops-action-executor":
        raise HTTPException(status_code=403, detail="ExecutionGrant audience mismatch")
    if grant.get("grantDigest") != canonical_digest(claims):
        raise HTTPException(status_code=403, detail="ExecutionGrant digest mismatch")
    not_before = parse_rfc3339(claims.get("notBefore"))
    expires_at = parse_rfc3339(claims.get("expiresAt"))
    now = datetime.now(UTC)
    if not_before is None or expires_at is None or now < not_before or now > expires_at:
        raise HTTPException(status_code=403, detail="ExecutionGrant time window is not active")

    digest = sealed_plan.get("digest") if isinstance(sealed_plan.get("digest"), Mapping) else {}
    plan_digest = digest.get("planDigest")
    if not plan_digest or claims.get("planDigest") != plan_digest:
        raise HTTPException(status_code=403, detail="ExecutionGrant plan digest mismatch")
    if sealed_action_plan_digest(sealed_plan) != plan_digest:
        raise HTTPException(status_code=403, detail="Sealed action plan digest mismatch")

    safety = sealed_plan.get("safety") if isinstance(sealed_plan.get("safety"), Mapping) else {}
    policy = safety.get("policy") if isinstance(safety.get("policy"), Mapping) else {}
    if claims.get("action") != sealed_plan.get("action"):
        raise HTTPException(status_code=403, detail="ExecutionGrant action mismatch")
    if claims.get("target") != sealed_plan.get("target"):
        raise HTTPException(status_code=403, detail="ExecutionGrant target mismatch")
    if claims.get("policyBundleHash") != policy.get("policyBundleHash"):
        raise HTTPException(status_code=403, detail="ExecutionGrant policy hash mismatch")


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/executor/actions/execute")
async def execute_action(
    req: ExecutorActionExecuteRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    verify_executor_ingress(authorization)
    verify_execution_grant(req.sealedActionPlan, req.executionGrantRef)

    result = await execute_typed_action_plan(req.sealedActionPlan)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "ExecutorActionResult",
        "spec": redact_sensitive(result),
    }
