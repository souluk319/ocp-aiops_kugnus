from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .answer_intents import (
    ANSWER_KIND_CASUAL,
    ANSWER_KIND_PLATFORM_CONCEPT,
    ANSWER_KIND_RUNTIME_HEALTH,
    classify_fallback_answer_kind,
)

ComponentStatus = Literal["ok", "failed", "unknown"]


@dataclass(frozen=True, slots=True)
class ComponentDefinition:
    id: str
    label: str
    failure_guidance: str = ""


@dataclass(frozen=True, slots=True)
class EvidenceSignal:
    component_id: str
    ok_any: tuple[re.Pattern[str], ...]
    failed_any: tuple[re.Pattern[str], ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceComponent:
    id: str
    label: str
    status: ComponentStatus
    detail: str = ""
    failure_guidance: str = ""


@dataclass(frozen=True, slots=True)
class GatewayEvidenceSnapshot:
    components: tuple[EvidenceComponent, ...]
    failed_tools: tuple[str, ...]
    gateway_evidence: str = ""


@dataclass(frozen=True, slots=True)
class AnswerPlan:
    kind: str
    title: str
    verdict: str
    confirmed: tuple[EvidenceComponent, ...] = ()
    failed: tuple[EvidenceComponent, ...] = ()
    cautions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class GatewayFallbackPlanInput:
    message: str
    policy: Mapping[str, Any]
    tool_results: Sequence[Mapping[str, Any]]
    gateway_evidence: str | None = None


def _compile(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


COMPONENT_DEFINITIONS: dict[str, ComponentDefinition] = {
    "gateway_fallback": ComponentDefinition("gateway_fallback", "Gateway fallback 응답 경로"),
    "lightspeed_stream": ComponentDefinition(
        "lightspeed_stream",
        "Lightspeed stream",
        "현재 답변은 Lightspeed 최종 응답이 아니라 Gateway fallback입니다.",
    ),
    "rag_search": ComponentDefinition("rag_search", "Gateway RAG 검색"),
    "openshift_nodes": ComponentDefinition("openshift_nodes", "OpenShift evidence-check 노드 조회"),
    "openshift_pods": ComponentDefinition("openshift_pods", "OpenShift evidence-check Pod 조회"),
}

EVIDENCE_SIGNALS: tuple[EvidenceSignal, ...] = (
    EvidenceSignal(
        "rag_search",
        (_compile(r"Gateway-collected RAG evidence|/v1/rag/search"),),
        (_compile(r"RAG evidence unavailable"),),
    ),
    EvidenceSignal(
        "openshift_nodes",
        (_compile(r"Gateway-collected Node status evidence|Node status evidence|nodeSummary"),),
        (_compile(r"Node status evidence unavailable"),),
    ),
    EvidenceSignal(
        "openshift_pods",
        (
            _compile(r"Gateway-collected Pod status evidence|Pod status evidence"),
            _compile(r"Current Pod list evidence"),
        ),
        (_compile(r"Pod status evidence unavailable"),),
    ),
)

FAILED_TOOL_STATUSES = {"error", "failed", "timeout"}
OK_TOOL_STATUSES = {"ok", "success", "succeeded"}


def truncate_text(value: str, limit: int) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}\n... truncated ..."


def build_component(component_id: str, status: ComponentStatus, detail: str = "") -> EvidenceComponent:
    definition = COMPONENT_DEFINITIONS.get(component_id, ComponentDefinition(component_id, component_id))
    return EvidenceComponent(
        id=definition.id,
        label=definition.label,
        status=status,
        detail=detail,
        failure_guidance=definition.failure_guidance,
    )


def build_tool_component(
    tool_name: str,
    tool_results: Sequence[Mapping[str, Any]],
) -> EvidenceComponent | None:
    matching = [item for item in tool_results if str(item.get("name") or "") == tool_name]
    if not matching:
        return None

    latest = matching[-1]
    status_text = str(latest.get("status") or "").lower()
    if status_text in FAILED_TOOL_STATUSES:
        status: ComponentStatus = "failed"
    elif status_text in OK_TOOL_STATUSES:
        status = "ok"
    else:
        status = "unknown"
    return build_component(tool_name, status, str(latest.get("summary") or latest.get("detail") or ""))


def signal_status(signal: EvidenceSignal, evidence_text: str) -> ComponentStatus:
    if any(pattern.search(evidence_text) for pattern in signal.failed_any):
        return "failed"
    if any(pattern.search(evidence_text) for pattern in signal.ok_any):
        return "ok"
    return "unknown"


def build_gateway_evidence_snapshot(
    tool_results: Sequence[Mapping[str, Any]],
    gateway_evidence: str | None,
    *,
    fallback_active: bool = True,
) -> GatewayEvidenceSnapshot:
    components: list[EvidenceComponent] = []
    if fallback_active:
        components.append(build_component("gateway_fallback", "ok"))

    lightspeed_component = build_tool_component("lightspeed_stream", tool_results)
    if lightspeed_component and lightspeed_component.status != "unknown":
        components.append(lightspeed_component)

    evidence_text = str(gateway_evidence or "")
    for signal in EVIDENCE_SIGNALS:
        status = signal_status(signal, evidence_text)
        if status != "unknown":
            components.append(build_component(signal.component_id, status))

    failed_tools = tuple(
        str(item.get("name") or "tool_result")
        for item in tool_results
        if str(item.get("status") or "").lower() in FAILED_TOOL_STATUSES
    )
    return GatewayEvidenceSnapshot(
        components=tuple(components),
        failed_tools=failed_tools,
        gateway_evidence=evidence_text,
    )


def build_runtime_health_plan(snapshot: GatewayEvidenceSnapshot) -> AnswerPlan:
    confirmed = tuple(component for component in snapshot.components if component.status == "ok")
    failed = tuple(component for component in snapshot.components if component.status == "failed")
    non_gateway_confirmed = tuple(component for component in confirmed if component.id != "gateway_fallback")

    if confirmed and failed:
        verdict = "부분적으로 작동합니다. 확인된 경로는 응답했지만 실패한 구성요소가 있습니다."
    elif failed:
        verdict = "현재 수집된 근거 기준으로 실패한 구성요소가 확인됩니다."
    elif non_gateway_confirmed:
        verdict = "현재 수집된 근거 기준으로는 핵심 evidence-check 응답 경로가 작동합니다."
    elif confirmed:
        verdict = "Gateway fallback 응답 경로는 작동했지만, 전체 서비스 상태를 단정할 추가 근거가 부족합니다."
    else:
        verdict = "작동 여부를 단정할 만큼의 상태 근거가 부족합니다."

    cautions = [
        "정확한 전체 판정은 `task kugnus:demo:preflight` 또는 화면의 Evidence/Status 패널 기준으로 확인해야 합니다."
    ]
    if any(component.id == "rag_search" for component in confirmed):
        cautions.insert(0, "RAG 검색 결과가 있다는 사실만으로 전체 서비스가 정상이라고 단정하지 않습니다.")

    return AnswerPlan(
        kind=ANSWER_KIND_RUNTIME_HEALTH,
        title="상태 확인",
        verdict=verdict,
        confirmed=confirmed,
        failed=failed,
        cautions=tuple(cautions),
    )


def build_casual_plan() -> AnswerPlan:
    return AnswerPlan(
        kind=ANSWER_KIND_CASUAL,
        title="안내",
        verdict=(
            "안녕하세요! OCP 운영 관련 질문을 해주시면 도와드리겠습니다.\n\n"
            "예시:\n"
            "- Pod가 자꾸 재시작돼요\n"
            "- CPU 사용량이 갑자기 높아요\n"
            "- 네임스페이스 상태 확인해줘"
        ),
    )


def build_platform_concept_plan() -> AnswerPlan:
    return AnswerPlan(
        kind=ANSWER_KIND_PLATFORM_CONCEPT,
        title="OpenShift 개념",
        verdict=(
            "OpenShift는 Kubernetes를 기업 운영 환경에서 쓰기 좋게 묶은 컨테이너 플랫폼입니다.\n\n"
            "쉽게 말하면:\n"
            "- 컨테이너로 만든 서비스를 Pod/Deployment로 올립니다.\n"
            "- Service/Route로 접속 경로를 만들고, 로그/Event/Metric으로 상태를 봅니다.\n"
            "- Operator와 콘솔을 통해 설치, 업그레이드, 권한, 배포를 표준 방식으로 관리합니다.\n\n"
            "이 KOMSCO AIOps에서는 OpenShift 상태를 읽고, RAG/운영 근거와 합쳐 "
            "장애 원인 후보와 다음 확인 명령을 만드는 대상입니다."
        ),
    )


def build_gateway_fallback_answer_plan(request: GatewayFallbackPlanInput) -> AnswerPlan | None:
    answer_kind = classify_fallback_answer_kind(request.message, request.policy)
    if answer_kind == ANSWER_KIND_PLATFORM_CONCEPT:
        return build_platform_concept_plan()
    if answer_kind == ANSWER_KIND_CASUAL:
        return build_casual_plan()
    if answer_kind != ANSWER_KIND_RUNTIME_HEALTH:
        return None

    snapshot = build_gateway_evidence_snapshot(request.tool_results, request.gateway_evidence)
    return build_runtime_health_plan(snapshot)


def render_runtime_health_plan(plan: AnswerPlan) -> str:
    lines = [
        f"### {plan.title}",
        "",
        plan.verdict,
        "",
        "#### 확인됨",
    ]
    if plan.confirmed:
        for component in plan.confirmed:
            lines.append(f"- {component.label}: 작동 확인")
    else:
        lines.append("- 확인된 정상 구성요소가 없습니다.")

    lines.extend(["", "#### 실패 또는 제한"])
    if plan.failed:
        for component in plan.failed:
            detail = f" {truncate_text(component.detail, 260)}" if component.detail else ""
            lines.append(f"- {component.label}: 실패.{detail}")
            if component.failure_guidance:
                lines.append(f"- {component.failure_guidance}")
    else:
        lines.append("- 이 fallback 경로에서는 별도 실패 도구가 확인되지 않았습니다.")

    if plan.cautions:
        lines.extend(["", "#### 주의"])
        lines.extend(f"- {caution}" for caution in plan.cautions)

    return "\n".join(lines)


def render_answer_plan(plan: AnswerPlan) -> str:
    if plan.kind == ANSWER_KIND_RUNTIME_HEALTH:
        return render_runtime_health_plan(plan)
    return plan.verdict or ""
