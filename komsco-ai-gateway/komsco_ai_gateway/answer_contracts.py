from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Protocol


class ChatAnswerRequest(Protocol):
    message: str
    language: str | None
    pageContext: Mapping[str, Any] | None


def page_context_aiops_ui_language(req: ChatAnswerRequest) -> str:
    value = str(getattr(req, "language", None) or "").strip().lower()
    if value.startswith("en"):
        return "en"
    if value.startswith(("ko", "kr")):
        return "ko"
    return ""


def message_looks_english(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.search(r"[가-힣]", stripped):
        return False
    return bool(re.search(r"[A-Za-z]", stripped))


def answer_language(req: ChatAnswerRequest) -> str:
    ui_language = page_context_aiops_ui_language(req)
    if ui_language == "en":
        return "en"
    if message_looks_english(req.message):
        return "en"
    return "ko"


def answer_language_contract(req: ChatAnswerRequest) -> str:
    if answer_language(req) == "en":
        return (
            "Answer language: English.\n"
            "The console UI or user message is English, so every user-facing sentence, section heading, "
            "status explanation, example, and action note in the final answer must be English.\n"
            "Do not output Korean in the final answer unless you are quoting a Korean resource name or the user explicitly asks for Korean."
        )
    return (
        "답변 언어: 한국어.\n"
        "최종 답변의 사용자-facing 문장, 섹션 제목, 상태 설명, 예시, 조치 안내는 한국어로 작성하세요.\n"
        "사용자가 영어 답변을 명시적으로 요청했거나 영어로만 질문한 경우에는 영어로 답하세요."
    )


def answer_section_contract(req: ChatAnswerRequest) -> str:
    if answer_language(req) == "en":
        return (
            "Use this structure when RCA or operations status is requested: "
            "Current Assessment, Root Cause Candidates, Verified Evidence, Action Method, Additional Checks."
        )
    return (
        "RCA 또는 운영 상태 질문에는 가능한 경우 아래 순서를 사용하세요: "
        "현재 판단, 원인 후보, 확인 결과, 조치 방법, 추가 확인."
    )


def assistant_operating_answer_style_contract(req: ChatAnswerRequest) -> str:
    if answer_language(req) == "en":
        return (
            "Default assistant answer style: answer the exact question first, in the smallest useful size. "
            "Use current console context such as page path, namespace, resource kind, selected filters, and verified evidence when available. "
            "When next steps are useful, end with the exact heading '### What would you like to check next?' "
            "and a numbered list of no more than 3 context-fit choices. Each choice must be one self-contained question on one line "
            "and must name the target or check clearly, for example a top-N table, status split, detailed check command, or Action Proposal draft. "
            "Do not reflexively create or display an Action Plan unless the user asks for a change/action or the target, risk, approval condition, and verification are concrete."
        )
    return (
        "기본 운영 답변 양식: 사용자의 질문에 먼저 짧고 정확하게 답하세요. "
        "현재 콘솔 경로, namespace, resource kind, 선택 필터, 검증된 조회 결과가 있으면 화면 기준으로 반영하세요. "
        "다음 단계가 유용한 경우 답변 끝에 정확히 '### 다음으로 무엇을 확인할까요?' 제목을 쓰고, "
        "상황에 맞는 선택지를 최대 3개까지 번호 목록으로 제안하세요. 각 선택지는 대상과 확인 행동이 분명한 독립 질문 한 줄이어야 합니다. "
        "예: 상위 N개 표 정리, 상태별 분기표, 상세 확인 명령, Action Proposal 초안. "
        "Action Plan은 반사적으로 만들거나 노출하지 말고, 사용자가 조치/변경을 원하거나 대상·위험·승인 조건·검증 방법이 구체적일 때만 제안하세요."
    )


def casual_identity_answer(req: ChatAnswerRequest) -> str:
    if answer_language(req) == "en":
        return "\n\n".join(
            [
                "I'm AIOps for OCP.",
                (
                    "I am an AIOps model specialized for OCP/OpenShift operations. "
                    "I help operators check cluster state with evidence, separate verified facts "
                    "from follow-up checks, prepare Action Plans, pass approval gates, and verify execution."
                ),
                "Send a namespace, pod, deployment, node, operator, or alert when you want me to inspect something.",
            ]
        )
    return "\n\n".join(
        [
            "저는 AIOps for OCP입니다.",
            (
                "OCP(OpenShift Container Platform)를 위한 전문 AIOps 모델로, 운영 상태를 조회 결과 기반으로 확인하고 "
                "원인 후보 정리, Action Plan 작성, 승인 후 실행 검증까지 도와드립니다."
            ),
            "네임스페이스, 파드, 디플로이먼트, 노드, 오퍼레이터, 경고 메시지 중 확인할 대상을 알려주시면 바로 이어서 보겠습니다.",
        ]
    )


def general_concept_answer(req: ChatAnswerRequest) -> str:
    if answer_language(req) == "en":
        return "\n\n".join(
            [
                "OpenShift is Red Hat's Kubernetes-based container platform.",
                (
                    "It helps teams deploy applications, connect networking and storage, apply security policy, "
                    "and operate clusters from a single console and API."
                ),
                (
                    "In AIOps for OCP, I use OpenShift signals such as namespaces, pods, deployments, nodes, "
                    "operators, and alerts to check evidence, prepare Action Plans, and verify approved changes."
                ),
            ]
        )
    return "\n\n".join(
        [
            "OpenShift는 Red Hat의 Kubernetes 기반 컨테이너 플랫폼입니다.",
            "애플리케이션 배포, 네트워크/스토리지 연결, 보안 정책, 운영 자동화를 콘솔과 API에서 관리할 수 있게 해줍니다.",
            (
                "AIOps for OCP에서는 OpenShift의 네임스페이스, 파드, 디플로이먼트, 노드, 오퍼레이터, "
                "경고 상태를 조회 결과 기반으로 확인하고 Action Plan과 승인 후 검증까지 연결합니다."
            ),
        ]
    )


def build_aiops_answer_contract_text(
    *,
    policy: Mapping[str, Any],
    rca_context: Mapping[str, Any],
    runtime_tool_plan: Mapping[str, Any],
) -> str:
    steps = runtime_tool_plan.get("tool_plan")
    if not isinstance(steps, list) or not steps:
        return ""

    evidence = rca_context.get("evidence")
    evidence_summary = evidence.get("summary") if isinstance(evidence, Mapping) else {}
    collected = evidence_summary.get("collectedCount", 0) if isinstance(evidence_summary, Mapping) else 0
    missing = evidence_summary.get("missingCount", 0) if isinstance(evidence_summary, Mapping) else 0
    task_type = str(runtime_tool_plan.get("task_type") or "unknown")
    decision = str(policy.get("decision") or "unknown")
    if task_type == "resource_summary_rca":
        return "\n".join(
            [
                "",
                "## 조치 판단 조건",
                "- 현재 신호는 클러스터 전체 Pod 집계라서 바로 실행할 단일 조치 대상이 아닙니다.",
                f"- 확인 결과: 수집 {collected}건, 추가 확인 필요 {missing}건을 분리했습니다.",
                "- 실패/대기 Pod, restart count 상위 Pod, owner, 영향 namespace를 먼저 좁혀야 합니다.",
                "- namespace, kind, name, 조치 종류, 검증 방법이 확정되면 그때 Action Plan 후보를 생성합니다.",
            ]
        )

    if decision != "action_proposal_only" and task_type not in {"pod_restart_rca"}:
        return ""

    return "\n".join(
        [
            "",
            "## 승인 대기 조치",
            f"- 조회 계획: `{task_type}` 유형으로 필요한 확인 결과를 정리했습니다.",
            f"- 확인 결과: 수집 {collected}건, 추가 확인 필요 {missing}건을 분리했습니다.",
            "- 조치 흐름: Action Plan을 만든 뒤 운영자 승인/거절을 거쳐 실행 결과와 감사 기록을 남깁니다.",
            "- 승인 전에는 변경 작업을 실행하지 않습니다.",
            "- 거절하면 실행은 차단되고 거절 기록만 남습니다.",
        ]
    )
