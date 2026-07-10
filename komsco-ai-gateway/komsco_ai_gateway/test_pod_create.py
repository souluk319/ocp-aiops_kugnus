from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx


@dataclass(frozen=True, slots=True)
class TestPodCreateSettings:
    enabled: bool
    default_image: str
    name_prefix: str
    app_label: str
    allowed_namespaces: frozenset[str]
    failure_command: tuple[str, ...]


def count_from_message(message: str) -> int | None:
    text = message.lower()
    digit = re.search(r"\b([1-5])\s*(?:개|pods?|파드)?\b", text)
    if digit:
        return int(digit.group(1))
    korean_numbers = (
        (1, r"한\s*개|하나|일\s*개"),
        (2, r"두\s*개|둘|두\s*대|이\s*개"),
        (3, r"세\s*개|셋|삼\s*개"),
        (4, r"네\s*개|넷|사\s*개"),
        (5, r"다섯\s*개|다섯|오\s*개"),
    )
    for count, pattern in korean_numbers:
        if re.search(pattern, text, re.IGNORECASE):
            return count
    english_numbers = (
        (1, r"\bone\b"),
        (2, r"\btwo\b"),
        (3, r"\bthree\b"),
        (4, r"\bfour\b"),
        (5, r"\bfive\b"),
    )
    for count, pattern in english_numbers:
        if re.search(pattern, text, re.IGNORECASE):
            return count
    return None


def request_from_message(
    message: str,
    settings: TestPodCreateSettings,
    namespace_names_from_message: Callable[[str], list[str]],
) -> dict[str, Any]:
    names = namespace_names_from_message(message)
    namespace = names[0] if names else ""
    return {
        "count": count_from_message(message),
        "failureMode": "crashloop",
        "image": settings.default_image,
        "namespace": namespace,
        "targetName": settings.app_label,
    }


def is_ready(request: Mapping[str, Any], settings: TestPodCreateSettings) -> bool:
    count = request.get("count")
    namespace = str(request.get("namespace") or "").strip()
    return bool(
        settings.enabled
        and namespace
        and isinstance(count, int)
        and not isinstance(count, bool)
        and 1 <= count <= 5
        and namespace in settings.allowed_namespaces
    )


async def collect_preflight(
    request: Mapping[str, Any],
    *,
    api_ca_file: str | bool,
    api_url: str,
    fetch_ocp_json: Callable[[httpx.AsyncClient, str, str], Any],
    path_segment: Callable[[str], str],
    settings: TestPodCreateSettings,
    user_auth_header: str,
) -> dict[str, Any]:
    namespace = str(request.get("namespace") or "").strip()
    count = request.get("count")
    if not settings.enabled:
        return {
            "error": "CrashLoop test Pod creation is disabled in product mode",
            "namespace": namespace,
            "ok": False,
            "server": api_url,
            "status": "test_pod_create_disabled",
        }
    if not namespace:
        return {
            "error": "namespace is required for test Pod creation",
            "namespace": "",
            "ok": False,
            "server": api_url,
            "status": "missing_namespace_for_test_pod_create",
        }
    if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 5:
        return {
            "error": "test Pod count must be explicitly set between 1 and 5",
            "namespace": namespace,
            "ok": False,
            "server": api_url,
            "status": "missing_or_invalid_count_for_test_pod_create",
        }
    if namespace not in settings.allowed_namespaces:
        return {
            "error": f"namespace `{namespace}` is outside the test Pod creation allowlist",
            "namespace": namespace,
            "ok": False,
            "server": api_url,
            "status": "unsupported_namespace_for_test_pod_create",
        }
    if not api_url:
        return {
            "error": "OPENSHIFT_API_URL is not configured",
            "namespace": namespace,
            "ok": False,
            "server": "",
            "status": "missing_api_url",
        }

    async with httpx.AsyncClient(
        verify=api_ca_file,
        timeout=httpx.Timeout(15.0, connect=5.0),
    ) as client:
        namespace_payload = await fetch_ocp_json(
            client,
            f"/api/v1/namespaces/{path_segment(namespace)}",
            user_auth_header,
        )

    metadata = (
        namespace_payload.get("metadata", {})
        if isinstance(namespace_payload, Mapping) and isinstance(namespace_payload.get("metadata"), Mapping)
        else {}
    )
    exists = bool(metadata.get("name"))
    return {
        "namespace": namespace,
        "ok": exists,
        "server": api_url,
        "status": "namespace_ready" if exists else "namespace_missing",
        "uid": str(metadata.get("uid") or ""),
    }


def disabled_answer(request: Mapping[str, Any], language: str) -> str:
    is_en = language == "en"
    namespace = str(request.get("namespace") or "").strip()
    count = request.get("count")
    if is_en:
        lines = [
            "## Current Assessment",
            "CrashLoop test Pod creation is a validation-only path and cannot create an Action Plan in the current product conditions.",
            "",
            "## What I Checked",
            f"- namespace in request: `{namespace or 'not specified'}`",
            f"- requested count: `{count if count is not None else 'not specified'}`",
            "",
            "## Next Step",
            "Use read-only RCA/evidence checks in this mode. Test Pod creation requires a controlled validation flag, an explicit namespace, an explicit count, and an allowlisted namespace.",
        ]
        return "\n".join(lines)

    lines = [
        "## 현재 판단",
        "CrashLoop 테스트 Pod 생성은 검증 전용 경로라서 현재 제품 조건에서는 Action Plan 후보를 만들지 않습니다.",
        "",
        "## 확인한 요청",
        f"- namespace: `{namespace or '지정되지 않음'}`",
        f"- 생성 수량: `{count if count is not None else '지정되지 않음'}`",
        "",
        "## 다음 행동",
        "현재 모드에서는 읽기 전용 RCA와 Evidence 확인만 수행합니다. 테스트 Pod 생성은 별도 검증 환경에서 기능 flag, 명시 namespace, 명시 수량, allowlist가 모두 맞을 때만 사용할 수 있습니다.",
    ]
    return "\n".join(lines)


def candidate_from_preflight(
    request: Mapping[str, Any],
    preflight: Mapping[str, Any],
    run_id: str,
    incident_id: str,
    settings: TestPodCreateSettings,
) -> dict[str, Any]:
    namespace = str(request.get("namespace") or "")
    count = int(request.get("count") or 0)
    candidate_id = f"action-candidate-test-pod-create-{hashlib.sha256(namespace.encode()).hexdigest()[:12]}"
    return {
        "approvalRequired": True,
        "blockedActions": [],
        "blockedReasons": ["approval-required"],
        "confidence": "high" if preflight.get("ok") else "medium",
        "evidence": f"{namespace} namespace 존재 확인 후 의도적으로 CrashLoopBackOff가 나는 테스트 Pod {count}개를 생성할 수 있습니다.",
        "evidenceRefs": [
            {
                "evidenceType": "namespace_preflight",
                "findingId": f"test-pod-create-{namespace}",
                "sourceType": "create_crashloop_test_pods",
                "status": "collected" if preflight.get("ok") else "missing",
            }
        ],
        "executable": True,
        "executionPolicy": {
            "executionEnabled": True,
            "mode": "execute",
            "mutationVerbsDisabled": False,
            "proposalOnly": False,
        },
        "expectedImpact": f"{namespace} namespace에 의도적으로 CrashLoopBackOff가 나는 테스트 Pod {count}개를 생성합니다. 승인 전에는 생성하지 않습니다.",
        "id": candidate_id,
        "priority": 35,
        "parameters": {
            "count": count,
            "failureMode": "crashloop",
            "image": str(request.get("image") or settings.default_image),
            "namePrefix": settings.name_prefix,
        },
        "prerequisiteChecks": ["대상 namespace 존재 확인", "테스트 목적 확인", "정리 방법 확인"],
        "recommendationSteps": ["CrashLoop 테스트 Pod 생성 계획 작성", "승인 게이트 통과", "생성 후 CrashLoopBackOff 상태 조회로 검증"],
        "riskLevel": "low",
        "riskLabel": "낮음",
        "severity": "실행 가능",
        "sourceFindingId": f"test-pod-create-{namespace}",
        "sourceType": "create_crashloop_test_pods",
        "statusLabel": "승인 후 실행 가능",
        "target": {
            "apiVersion": "v1",
            "kind": "Namespace",
            "name": namespace,
            "namespace": namespace,
            "uid": str(preflight.get("uid") or f"namespace-{namespace}"),
        },
        "title": f"CrashLoop 테스트 Pod {count}개 생성",
        "verificationChecks": ["생성 전 namespace 재확인", f"label app={settings.app_label} 기준 Pod {count}개 조회"],
        "chatRunId": run_id,
        "incidentId": incident_id,
        "expiresAt": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
    }


def answer(
    request: Mapping[str, Any],
    preflight: Mapping[str, Any],
    execution_mode_sentence_text: str,
    *,
    action_mode: bool,
    language: str,
    settings: TestPodCreateSettings,
) -> str:
    is_en = language == "en"
    namespace = str(request.get("namespace") or "")
    count = int(request.get("count") or 0)
    preflight_label = "namespace exists" if is_en else "namespace 존재 확인"
    if not preflight.get("ok"):
        preflight_label = "namespace must be rechecked before execution" if is_en else "실행 전 namespace 재확인 필요"

    if is_en:
        lines = [
            "## Current Assessment",
            (
                f"{execution_mode_sentence_text} "
                + (
                    "After Action Plan creation, approval, and execution, intentional CrashLoopBackOff test Pods can be created."
                    if action_mode and preflight.get("ok")
                    else "Plan candidates can be reviewed, but creation and execution are locked."
                    if not action_mode
                    else "The namespace must be rechecked before an Action Plan candidate is created."
                )
            ),
            "",
            "## Target",
            f"- namespace: `{namespace}`",
            f"- object group: `{settings.app_label}`",
            f"- requested count: `{count}`",
            "- failure mode: `CrashLoopBackOff`",
            "",
            "## Confirmed Evidence",
            f"- API server: {preflight.get('server') or '-'}",
            f"- namespace preflight: {preflight_label}",
            "",
            "## Action Plan",
            (
                f"- Approval-required candidate: create `{count}` CrashLoopBackOff test Pods in `{namespace}`"
                if action_mode and preflight.get("ok")
                else "- Status: read-only mode shows the plan candidate only; switch to execution-enabled mode to create it."
                if not action_mode
                else "- Status: namespace must be rechecked before a candidate is created."
            ),
            "- No Pod is created before approval.",
            f"- Execution: after approval, the Gateway creates {count} Pod objects with a fixed command that exits with code 1.",
            f"- Verification: after execution, confirm that `app={settings.app_label}` has {count} Pods and the containers enter CrashLoopBackOff/Error.",
            "",
            "## Terminal Check Commands",
            "```bash",
            "oc whoami --show-server",
            f"oc get namespace {namespace}",
            f"oc get pods -n {namespace} -l app={settings.app_label}",
            "```",
        ]
        return "\n".join(lines)

    lines = [
        "## 현재 판단",
        (
            f"{execution_mode_sentence_text} "
            + (
                "Action Plan 생성 후 승인·실행하면 의도적으로 CrashLoopBackOff가 나는 테스트 Pod를 만들 수 있습니다."
                if action_mode and preflight.get("ok")
                else "계획 후보는 확인할 수 있지만 생성과 실행은 잠겨 있습니다."
                if not action_mode
                else "Action Plan 후보 생성 전 namespace 재확인이 필요합니다."
            )
        ),
        "",
        "## 대상",
        f"- namespace: `{namespace}`",
        f"- 오브젝트 그룹: `{settings.app_label}`",
        f"- 생성 수량: `{count}`",
        "- 실패 방식: `CrashLoopBackOff`",
        "",
        "## 확인 결과",
        f"- API 서버: {preflight.get('server') or '-'}",
        f"- namespace 사전 확인: {preflight_label}",
        "",
        "## Action Plan",
        (
            f"- 승인 필요 후보: `{namespace}`에 CrashLoopBackOff 테스트 Pod {count}개 생성"
            if action_mode and preflight.get("ok")
            else "- 상태: 읽기 전용 모드에서는 계획 후보만 표시하고, 생성은 실행 가능 모드에서 진행합니다."
            if not action_mode
            else "- 상태: 실행 전 namespace 재확인 필요"
        ),
        "- 승인 전에는 Pod를 생성하지 않습니다.",
        "- 실행: 승인 후 Gateway가 종료 코드 1로 즉시 종료되는 Pod 오브젝트를 생성합니다.",
        f"- 검증: 실행 후 `app={settings.app_label}` label 기준으로 Pod {count}개와 CrashLoopBackOff/Error 상태를 확인합니다.",
        "",
        "## 터미널 확인 명령",
        "```bash",
        "oc whoami --show-server",
        f"oc get namespace {namespace}",
        f"oc get pods -n {namespace} -l app={settings.app_label}",
        "```",
    ]
    return "\n".join(lines)


def tool_plan(
    request: Mapping[str, Any],
    execution_mode: str,
    *,
    action_ready: bool,
) -> dict[str, Any]:
    namespace = str(request.get("namespace") or "")
    plan_steps: list[dict[str, Any]] = [
        {
            "step": 1,
            "adapter": "oc",
            "tool": "oc_get_namespace",
            "verb": "get",
            "purpose": "대상 namespace 존재 확인",
        }
    ]
    if action_ready:
        plan_steps.extend(
            [
                {
                    "step": 2,
                    "adapter": "aiops-gateway",
                    "tool": "create_test_pod_action_candidate",
                    "verb": "propose",
                    "purpose": "승인 필요 테스트 Pod 생성 Action Plan 후보 생성",
                },
                {
                    "step": 3,
                    "adapter": "oc",
                    "tool": "oc_get_created_pods",
                    "verb": "get",
                    "purpose": "승인 후 생성된 Pod 오브젝트 확인",
                },
            ]
        )
    if execution_mode == "unrestricted" and action_ready:
        policy_mode = "unrestricted_pending_approval"
    elif execution_mode == "execute" and action_ready:
        policy_mode = "controlled_execution"
    else:
        policy_mode = "read_only_review"
    return {
        "task_type": "test_pod_create",
        "target": {
            "apiVersion": "v1",
            "kind": "Namespace",
            "name": namespace,
            "namespace": namespace,
        },
        "execution_policy": {
            "mode": policy_mode,
            "mutations_enabled": action_ready,
            "proposal_only": not action_ready,
            "review_only": False,
        },
        "tool_plan": plan_steps,
        "validation": {
            "ok": True,
            "status": "action_candidate_ready" if action_ready else "preflight_required",
        },
    }


def review_execution_result(target: Mapping[str, Any], parameters: Mapping[str, Any]) -> dict[str, Any]:
    target_name = str(target.get("name") or target.get("namespace") or "")
    count = int(parameters.get("count") or 0)
    return {
        "mutationOutcome": {
            "status": "review_recorded",
            "reason": f"test Pod creation review recorded for {target_name}; no Pod was created",
            "httpStatus": 200,
        },
        "remediationOutcome": {
            "status": "verified",
            "reason": f"{target_name} test Pod creation plan review recorded for {count} Pods without mutation",
        },
        "executorTrace": {
            "mutationSubmitted": False,
            "reviewOnly": True,
            "toolName": "test_pod_create_review",
            "target": target,
        },
    }


def pod_name(prefix: str, request_id: str, index: int) -> str:
    suffix = f"{request_id}-{index}"
    trimmed_prefix = prefix[: max(1, 63 - len(suffix) - 1)].rstrip("-")
    return f"{trimmed_prefix}-{suffix}"


def pod_manifest(
    *,
    image: str,
    index: int,
    namespace: str,
    pod_name: str,
    request_id: str,
    settings: TestPodCreateSettings,
) -> dict[str, Any]:
    labels = {
        "app": settings.app_label,
        "aiops.komsco/scenario": "crashloop-test",
        "aiops.komsco/request-id": request_id,
    }
    return {
        "apiVersion": "v1",
        "kind": "Pod",
        "metadata": {
            "annotations": {
                "aiops.komsco/created-by": "aiops-action-plan",
                "aiops.komsco/purpose": "intentional-crashloop-test",
            },
            "labels": labels,
            "name": pod_name,
            "namespace": namespace,
        },
        "spec": {
            "containers": [
                {
                    "command": list(settings.failure_command),
                    "image": image,
                    "imagePullPolicy": "IfNotPresent",
                    "name": "crashloop",
                    "resources": {
                        "requests": {"cpu": "5m", "memory": "16Mi"},
                        "limits": {"cpu": "50m", "memory": "64Mi"},
                    },
                }
            ],
            "restartPolicy": "Always",
        },
    }
