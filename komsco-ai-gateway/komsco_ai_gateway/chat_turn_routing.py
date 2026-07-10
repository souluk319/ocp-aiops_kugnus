from collections.abc import Mapping
import re
from typing import Literal


ChatTurnIntent = Literal["operational", "product_feedback", "ui_explanation"]

_PRODUCT_FEEDBACK_TERMS = (
    "답변 개선",
    "개선 후보",
    "답변 피드백",
    "답변 품질",
    "챗봇 피드백",
    "런북에 반영",
    "runbook에 반영",
    "runbook 반영",
)

_SCREEN_TERMS = (
    "현재 화면",
    "보는 화면",
    "이 화면",
    "대시보드",
    "시각화",
    "그래프",
    "차트",
)

_EXPLANATION_TERMS = (
    "설명",
    "알려",
    "무슨 화면",
    "무엇을 보여",
    "어떤 화면",
    "뭐야",
)

_OPERATIONAL_TERMS = (
    "원인",
    "분석",
    "조회",
    "확인해",
    "조치",
    "실행",
    "삭제",
    "재시작",
    "장애",
    "에러",
    "오류",
    "action plan",
    "actionplan",
)

_OPERATIONAL_TARGET_TERMS = (
    "pod",
    "파드",
    "namespace",
    "네임스페이스",
    "deployment",
    "디플로이먼트",
    "cluster",
    "클러스터",
    "clusteroperator",
    "cluster operator",
    "operator",
    "오퍼레이터",
    "node",
    "노드",
    "pvc",
    "route",
    "service",
    "재시작",
    "삭제",
    "조치",
)


def _normalized_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _context_route(page_context: Mapping[str, object] | None) -> str:
    if not isinstance(page_context, Mapping):
        return ""

    candidates: list[str] = []
    for key in ("route", "pathname", "path", "href"):
        value = page_context.get(key)
        if isinstance(value, str) and value.strip():
            candidates.append(value.strip().lower())

    view_context = page_context.get("aiopsViewContext")
    if isinstance(view_context, Mapping):
        for key in ("route", "pathname", "path", "href"):
            value = view_context.get(key)
            if isinstance(value, str) and value.strip():
                candidates.append(value.strip().lower())

    return next(
        (candidate for candidate in candidates if "/dashboards/aiops" in candidate),
        candidates[0] if candidates else "",
    )


def classify_chat_turn_intent(
    message: str,
    *,
    page_context: Mapping[str, object] | None = None,
) -> ChatTurnIntent:
    """Classify non-operational turns before Kubernetes tool planning."""

    normalized = _normalized_text(message)
    has_product_feedback = any(term in normalized for term in _PRODUCT_FEEDBACK_TERMS)
    has_operational_target = any(term in normalized for term in _OPERATIONAL_TARGET_TERMS)
    if has_product_feedback and not has_operational_target:
        return "product_feedback"

    route = _context_route(page_context)
    is_aiops_screen = "/dashboards/aiops" in route
    asks_screen_explanation = (
        any(term in normalized for term in _SCREEN_TERMS)
        and any(term in normalized for term in _EXPLANATION_TERMS)
    )
    asks_operational_work = any(term in normalized for term in _OPERATIONAL_TERMS)

    if is_aiops_screen and asks_screen_explanation and not asks_operational_work:
        return "ui_explanation"

    return "operational"
