from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DiagnosticTargetNode(StrictBaseModel):
    name: str = Field(min_length=1, max_length=253)
    uid: str = Field(min_length=1, max_length=128)


class DiagnosticTimeRange(StrictBaseModel):
    since: str = Field(min_length=1, max_length=80)
    until: str = Field(min_length=1, max_length=80)


class DiagnosticLimits(StrictBaseModel):
    deadline: str = Field(default="30s", min_length=1, max_length=32)
    maxBytes: int = Field(default=10 * 1024 * 1024, ge=1, le=100 * 1024 * 1024)
    maxLines: int = Field(default=50000, ge=1, le=500000)


class DiagnosticEvidencePolicy(StrictBaseModel):
    classification: str = Field(default="restricted", min_length=1, max_length=64)
    rawStorageAllowed: bool = False
    redactionPolicyDigest: str = Field(default="sha256:unspecified", min_length=1, max_length=128)


class DiagnosticRequestCreate(StrictBaseModel):
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    targetNode: DiagnosticTargetNode
    collector: str = Field(min_length=1, max_length=120)
    collectorVersion: str = Field(default="v1", min_length=1, max_length=64)
    collectorProfile: str = Field(default="passive-readonly", min_length=1, max_length=80)
    timeRange: DiagnosticTimeRange
    limits: DiagnosticLimits = Field(default_factory=DiagnosticLimits)
    evidencePolicy: DiagnosticEvidencePolicy = Field(default_factory=DiagnosticEvidencePolicy)
    policy: dict[str, Any] = Field(default_factory=dict)


class ActionTarget(StrictBaseModel):
    apiVersion: str = Field(min_length=1, max_length=80)
    kind: str = Field(min_length=1, max_length=80)
    namespace: str = Field(min_length=1, max_length=253)
    name: str = Field(min_length=1, max_length=253)
    uid: str = Field(min_length=1, max_length=128)


class ActionProposalCreate(StrictBaseModel):
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    toolName: str = Field(min_length=1, max_length=120)
    toolVersion: str = Field(default="v1", min_length=1, max_length=64)
    target: ActionTarget
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    expectedImpact: str | None = Field(default=None, max_length=1000)
    prerequisiteChecks: list[str] = Field(default_factory=list, max_length=12)
    problemSummary: str | None = Field(default=None, max_length=1000)
    recommendationSteps: list[str] = Field(default_factory=list, max_length=12)
    runbookRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    verificationChecks: list[str] = Field(default_factory=list, max_length=12)
    policy: dict[str, Any] = Field(default_factory=dict)


class ActionCandidateTargetCreate(StrictBaseModel):
    apiVersion: str | None = Field(default=None, max_length=80)
    kind: str = Field(min_length=1, max_length=80)
    namespace: str | None = Field(default=None, max_length=253)
    name: str = Field(min_length=1, max_length=253)


class ActionCandidatePlanCreate(StrictBaseModel):
    candidateId: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=240)
    sourceFindingId: str | None = Field(default=None, max_length=160)
    sourceType: str | None = Field(default=None, max_length=120)
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    target: ActionCandidateTargetCreate
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    expectedImpact: str | None = Field(default=None, max_length=1000)
    parameters: dict[str, Any] = Field(default_factory=dict)
    policy: dict[str, Any] = Field(default_factory=dict)
    prerequisiteChecks: list[str] = Field(default_factory=list, max_length=12)
    problemSummary: str | None = Field(default=None, max_length=1000)
    recommendationSteps: list[str] = Field(default_factory=list, max_length=12)
    verificationChecks: list[str] = Field(default_factory=list, max_length=12)


class SealedActionPlanCreate(StrictBaseModel):
    proposalId: str = Field(min_length=1, max_length=120)


class ApprovalDecisionCreate(StrictBaseModel):
    planId: str = Field(min_length=1, max_length=120)
    expectedPlanDigest: str = Field(min_length=1, max_length=128)
    approvalScope: str = Field(default="single-target", min_length=1, max_length=80)


class ActionRejectionCreate(StrictBaseModel):
    planId: str = Field(min_length=1, max_length=120)
    expectedPlanDigest: str = Field(min_length=1, max_length=128)
    reason: str = Field(default="operator rejected the proposed action", min_length=1, max_length=500)


class ActionExecutionCreate(StrictBaseModel):
    approvalId: str = Field(min_length=1, max_length=120)
    planId: str = Field(min_length=1, max_length=120)
    expectedPlanDigest: str = Field(min_length=1, max_length=128)


class UnrestrictedCommandExecuteCreate(StrictBaseModel):
    command: str = Field(min_length=1, max_length=8000)
    cwd: str | None = Field(default=None, max_length=1000)
    timeoutSeconds: int | None = Field(default=None, ge=1, le=3600)


class RunbookPlanCreate(StrictBaseModel):
    runbookId: str = Field(min_length=1, max_length=160)
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    target: ActionTarget
    parameters: dict[str, Any] = Field(default_factory=dict)
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    policy: dict[str, Any] = Field(default_factory=dict)


class RagSearchFilters(StrictBaseModel):
    sourceTypes: list[str] = Field(default_factory=list, max_length=20)
    namespaces: list[str] = Field(default_factory=list, max_length=20)
    customers: list[str] = Field(default_factory=list, max_length=20)
    aclGroups: list[str] = Field(default_factory=list, max_length=40)
    runbookIds: list[str] = Field(default_factory=list, max_length=40)
    versions: list[str] = Field(default_factory=list, max_length=20)
    labels: dict[str, str] = Field(default_factory=dict)


class RagSearchCreate(StrictBaseModel):
    query: str = Field(min_length=1, max_length=1000)
    topK: int = Field(default=5, ge=1, le=20)
    filters: RagSearchFilters = Field(default_factory=RagSearchFilters)
    includeContent: bool = False
    runId: str | None = Field(default=None, max_length=120)


class PatchPreapprovedFieldCreate(StrictBaseModel):
    fieldSchemaId: str = Field(min_length=1, max_length=160)
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    target: ActionTarget
    value: Any
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    policy: dict[str, Any] = Field(default_factory=dict)


class BreakGlassTargetNode(StrictBaseModel):
    name: str = Field(min_length=1, max_length=253)
    uid: str = Field(min_length=1, max_length=128)


class BreakGlassRequestCreate(StrictBaseModel):
    profileId: str = Field(min_length=1, max_length=160)
    incidentId: str | None = Field(default=None, max_length=120)
    runId: str | None = Field(default=None, max_length=120)
    targetNode: BreakGlassTargetNode
    justification: str = Field(min_length=12, max_length=1000)
    evidenceRefs: list[dict[str, Any]] = Field(default_factory=list, max_length=20)
    policy: dict[str, Any] = Field(default_factory=dict)
