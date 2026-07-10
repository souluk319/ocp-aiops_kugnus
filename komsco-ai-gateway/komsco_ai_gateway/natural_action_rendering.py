from collections.abc import Callable, Mapping, Sequence
import json
import re
from typing import Any


def natural_action_plan_response(
    result: Mapping[str, Any], *, redact_sensitive: Callable[[Any], Any]
) -> str:
    if result.get("status") == "unavailable":
        return "\n".join([
            "자연어 조치 요청을 해석했지만 Gateway가 OpenShift API에 연결되어 있지 않아 실행 계획을 만들지 못했습니다.",
            "", "실제 조치를 수행하지 않았습니다.", "",
            f"- 요청 해석: {result.get('summary')}",
            "- 확인할 항목: `OPENSHIFT_API_URL` 또는 Gateway의 OpenShift API 연결 설정",
        ])
    if result.get("status") == "ambiguous":
        intent = result.get("intent") if isinstance(result.get("intent"), Mapping) else {}
        candidates = result.get("candidates") if isinstance(result.get("candidates"), list) else []
        candidate_lines = [
            f"- `{candidate.get('namespace')}/{candidate.get('name')}` ({candidate.get('kind') or intent.get('kind') or 'resource'})"
            for candidate in candidates if isinstance(candidate, Mapping)
        ]
        return "\n".join([
            "자연어 조치 요청을 해석했지만 대상 후보가 여러 개라 실행하지 않았습니다.",
            "", "### 대상 후보", *(candidate_lines or ["- 후보를 표시할 수 없습니다."]), "",
            "namespace와 대상 이름을 함께 지정해 다시 요청하세요.",
        ])
    if result.get("status") == "missing_namespace":
        return "\n".join([
            "자연어 조치 요청을 해석했지만 namespace가 없어 실행하지 않았습니다.", "",
            f"- 요청 해석: {result.get('summary')}",
            "- 예: `cis 네임스페이스의 cis 파드 3개로 올려줘`",
        ])
    if result.get("status") == "not_found":
        intent = result.get("intent") if isinstance(result.get("intent"), Mapping) else {}
        kind = str(intent.get("kind") or "resource")
        return "\n".join([
            f"자연어 조치 요청을 해석했지만 대상 {kind} 리소스를 찾지 못했습니다.", "",
            f"- 요청 해석: {result.get('summary')}",
            "- namespace와 대상 이름을 확인한 뒤 다시 요청하세요.",
        ])

    target = result.get("target") if isinstance(result.get("target"), Mapping) else {}
    parameters = result.get("parameters") if isinstance(result.get("parameters"), Mapping) else {}
    intent = result.get("intent") if isinstance(result.get("intent"), Mapping) else {}
    risk = str(result.get("risk") or "unknown")
    next_step = "오른쪽 `AIOps 실행 상태 > 승인·실행`에서 `승인` 후 `실행`을 누르면 실제 변경됩니다."
    if risk in {"medium", "high"}:
        next_step = (
            "이 조치는 medium/high risk로 분류될 수 있어 승인 정책상 별도 승인자가 필요할 수 있습니다. "
            "오른쪽 `AIOps 실행 상태 > 승인·실행`에서 승인 가능 여부를 확인하세요."
        )
    return "\n".join([
        "자연어 조치 요청을 승인 가능한 Action Plan으로 정리했습니다.", "", "### Action Plan",
        f"- 대상: `{target.get('namespace')}/{target.get('name')}` ({target.get('kind')})",
        f"- 조치: `{intent.get('toolName')}`",
        f"- 입력값: `{json.dumps(redact_sensitive(parameters), ensure_ascii=False)}`",
        f"- 위험도: `{risk}`", "- 상태: 승인 전에는 변경 작업을 실행하지 않습니다.", "",
        "### 다음 단계", f"- {next_step}",
    ])


def no_pending_action_plan_response() -> str:
    return "\n".join([
        "실행할 Gateway AIOps Action Plan이 없습니다.", "",
        "`승인`/`실행` 같은 후속 명령은 Gateway가 생성한 미실행 Action Plan이 있을 때만 처리합니다.",
        "대상과 namespace를 포함해서 다시 요청하세요.", "",
        "예: `komsco-ai-dev 네임스페이스의 aiops-two-pod-exec 파드 3개로 올려줘`",
        "예: `6:cis 파드 3개로 올려줘`",
    ])


def unresolved_natural_action_response(
    req: Any,
    *,
    normalize_console_page_context: Callable[[Any], Mapping[str, Any]],
    namespace_from_natural_action: Callable[[Any], str],
    page_context_resource_name: Callable[..., str],
    resource_patterns: Sequence[re.Pattern[str]],
) -> str:
    context = normalize_console_page_context(req.pageContext)
    namespace = namespace_from_natural_action(req)
    resource_name = page_context_resource_name(req)
    lines = [
        "변경 요청으로 판단했지만 실행 가능한 Gateway AIOps Action으로 확정하지 못했습니다.",
        "", "실제 조치를 수행하지 않았습니다.", "", "### 부족한 정보",
    ]
    if not namespace:
        lines.append("- Namespace가 명확하지 않습니다.")
    if not resource_name:
        resource_name = next((
            page_context_resource_name(req, kind)
            for kind in ("Pod", "HorizontalPodAutoscaler")
            if page_context_resource_name(req, kind)
        ), "")
    if not resource_name and not any(parser.search(req.message) for parser in resource_patterns):
        lines.append("- 대상 리소스 이름이 명확하지 않습니다.")
    if len(lines) == 5:
        lines.append(
            "- 지원되는 조치 형태가 아닙니다. 현재 자연어 즉시 실행은 Deployment scale/restart/rollback, "
            "controller-owned unhealthy Pod eviction, HPA bounds 변경을 우선 지원합니다."
        )
    lines.extend([
        "", "### 다시 입력 예시", "- `6:cis 파드 3개로 올려줘`",
        "- `6 네임스페이스의 cis 파드 3개로 올려줘`",
        "- `komsco-ai-dev:aiops-two-pod-exec 재시작해줘`",
        "- `komsco-ai-dev 네임스페이스의 pod/worker-abc 교체해줘`",
        "- `komsco-ai-dev 네임스페이스의 hpa/web-hpa 최소 2 최대 8로 변경해줘`",
    ])
    if context:
        lines.extend(["", f"- 현재 콘솔 경로: `{context.get('pathname') or context.get('href') or '-'}`"])
    return "\n".join(lines)


def natural_action_execution_response(
    result: Mapping[str, Any],
    *,
    sealed_action_plans: Mapping[str, Mapping[str, Any]],
    redact_sensitive: Callable[[Any], Any],
) -> str:
    plan_result = result.get("plan") if isinstance(result.get("plan"), Mapping) else {}
    target = plan_result.get("target") if isinstance(plan_result.get("target"), Mapping) else {}
    intent = plan_result.get("intent") if isinstance(plan_result.get("intent"), Mapping) else {}
    parameters = plan_result.get("parameters") if isinstance(plan_result.get("parameters"), Mapping) else {}
    if not parameters and isinstance(intent.get("parameters"), Mapping):
        parameters = intent["parameters"]
    if not parameters:
        plan_id = str(plan_result.get("planId") or "")
        plan_record = sealed_action_plans.get(plan_id) if plan_id else None
        sealed_plan = plan_record.get("spec", {}).get("sealedActionPlan", {}) if isinstance(plan_record, Mapping) else {}
        action = sealed_plan.get("action") if isinstance(sealed_plan.get("action"), Mapping) else {}
        parameters = action.get("normalizedParameters") if isinstance(action.get("normalizedParameters"), Mapping) else {}
    mutation = result.get("mutationOutcome") if isinstance(result.get("mutationOutcome"), Mapping) else {}
    remediation = result.get("remediationOutcome") if isinstance(result.get("remediationOutcome"), Mapping) else {}
    status = str(result.get("status") or "unknown")
    if status == "not_executed":
        return "\n".join([
            "자연어 조치 요청을 해석했지만 실행하지 못했습니다.", "",
            f"- Reason: `{result.get('reason') or 'unknown'}`",
            "- namespace와 대상 이름을 확인한 뒤 다시 요청하세요.",
        ])
    heading = "자연어 조치 요청을 해석해 실행까지 완료했습니다."
    if status == "review_recorded":
        heading = "자연어 조치 요청을 해석해 검토 기록을 남겼습니다."
    if status == "execution_disabled":
        heading = "자연어 조치 요청을 해석했지만 mutation 실행은 비활성화되어 있습니다."
    elif status == "execution_failed":
        heading = "자연어 조치 요청을 해석해 실행했지만 Kubernetes 변경이 실패했습니다."
    return "\n".join([
        heading, "", "### 실행 요약",
        f"- 대상: `{target.get('namespace')}/{target.get('name')}` ({target.get('kind')})",
        f"- Action: `{intent.get('toolName')}`",
        f"- Parameters: `{json.dumps(redact_sensitive(parameters), ensure_ascii=False)}`",
        f"- Plan: `{plan_result.get('planId')}`", f"- Approval: `{result.get('approvalId')}`",
        f"- Execution: `{result.get('executionId')}`",
        f"- Mutation: `{mutation.get('status')}` / `{mutation.get('reason')}`",
        f"- Verification: `{remediation.get('status')}` / `{remediation.get('reason')}`",
    ])


def natural_action_evidence_check_response(
    intent: Mapping[str, Any], *, redact_sensitive: Callable[[Any], Any]
) -> str:
    return "\n".join([
        "현재 AIOps 모드가 `읽기 전용`이라 실행 계획, 승인, 실행은 만들지 않고 조치 후보만 정리합니다.",
        "", "상태: **제안만 함 / 실행 안 함**", "", "### 요청 해석",
        f"- 대상: `{intent.get('namespace')}/{intent.get('targetName')}`",
        f"- Action: `{intent.get('toolName')}`",
        f"- Parameters: `{json.dumps(redact_sensitive(intent.get('parameters') or {}), ensure_ascii=False)}`",
        "", "### 선행 확인", "- 대상 리소스, namespace, owner, 최근 Event, 관련 Alert를 먼저 확인합니다.",
        "- 원인이 특정되지 않으면 재시작, scale, patch 같은 변경성 작업을 후보에서 제외합니다.",
        "", "### 안전선", "- 금지 동작: `oc apply`, `oc delete`, `oc patch`, `oc scale`, `oc exec`",
        "- 실제 변경은 별도 승인된 실행 모드와 Action Executor 경로에서만 가능합니다.",
    ])
