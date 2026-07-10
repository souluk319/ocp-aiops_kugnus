import hashlib
import re
from collections.abc import Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .pod_evidence_parsing import (
    parse_gateway_current_pod_list_rows,
    parse_gateway_pod_evidence_rows,
)


AMBIGUOUS_CLEANUP_REQUEST_RE = re.compile(
    r"(?i)(정리(?:를|을)?\s*(?:좀|할까|해도|해야|하면|해볼|할지)|"
    r"없애도|지워도|삭제해도|별\s*의미\s*없|테스트용(?:이면|이라면)|"
    r"cleanup\s*(?:maybe|review)?|should\s+.*cleanup)"
)
CLEANUP_SCOPE_CONFIRMATION_RE = re.compile(
    r"(?i)^\s*(응|그래|좋아|ㅇㅋ|오케이|그\s*범위|그걸로|그대로|yes|ok|proceed)\b|"
    r"(그\s*범위로|그걸로).*(정리|검토|진행|확인)|"
    r"정리\s*검토\s*(해|해줘|진행)"
)
CLEANUP_DELETE_REVIEW_RE = re.compile(
    r"(?i)((최근|최신|나중|마지막|만들어진|생성|created|latest|newest).{0,80}"
    r"(삭제|지워|없애|정리|delete|remove|cleanup)|"
    r"(삭제|지워|없애|정리|delete|remove|cleanup).{0,80}"
    r"(최근|최신|나중|마지막|만들어진|생성|created|latest|newest))"
)
POD_PATTERN_CONTEXT_RE = re.compile(
    r"`(?P<quoted>[a-z0-9][a-z0-9.*-]*(?:pod|pods)[a-z0-9.*-]*)`|"
    r"\b(?P<plain>[a-z0-9][a-z0-9.*-]*(?:pod|pods)[a-z0-9.*-]*)\b",
    re.IGNORECASE,
)
NAMESPACE_CLEANUP_REQUEST_RE = re.compile(
    r"(namespace|namespaces|네임스페이스).*(사용\s*중|사용\s*여부|안\s*쓰|오래된|정리|삭제|cleanup|unused|stale)"
    r"|((사용\s*중|안\s*쓰|오래된|정리|삭제|cleanup|unused|stale).*(namespace|namespaces|네임스페이스))",
    re.IGNORECASE,
)
NAMESPACE_TOKEN_RE = re.compile(r"\b[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\b")
NAMESPACE_TOKEN_HINT_RE = re.compile(r"(aiops|komsco|cywell|gpu|test|demo|dev|lab)", re.IGNORECASE)
SYSTEM_NAMESPACE_RE = re.compile(r"^(default|kube-|openshift-|redhat-|olm|local)$", re.IGNORECASE)


@dataclass(frozen=True)
class ConversationCleanupDependencies:
    page_context_namespace: Callable[[Any], str]
    is_resource_summary_rca_request: Callable[[Any], bool]
    parse_gateway_current_pod_list_rows: Callable[
        [str | None], tuple[list[dict[str, str]], str, str]
    ]
    parse_gateway_pod_evidence_rows: Callable[[str | None], list[dict[str, str]]]
    candidate_cache: MutableMapping[str, dict[str, Any]]
    forbidden_verbs: Sequence[str]


def parse_k8s_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_namespace_cleanup_request(req: Any, deps: ConversationCleanupDependencies) -> bool:
    text = re.sub(r"\s+", " ", req.message or "").strip()
    if deps.is_resource_summary_rca_request(req):
        return False
    return bool(text and NAMESPACE_CLEANUP_REQUEST_RE.search(text))


def namespace_names_from_message(message: str) -> list[str]:
    seen: set[str] = set()
    names: list[str] = []
    for token in NAMESPACE_TOKEN_RE.findall(message.lower()):
        if token in seen:
            continue
        if token in {
            "namespace", "namespaces", "read", "only", "read-only", "readonly", "oc",
            "action", "plan", "test", "pod", "pods", "create", "creation", "generated",
            "candidate", "candidates",
        }:
            continue
        if "-" not in token and not NAMESPACE_TOKEN_HINT_RE.search(token):
            continue
        seen.add(token)
        names.append(token)
    return names[:12]


def pod_patterns_from_text(text: str) -> list[str]:
    seen: set[str] = set()
    patterns: list[str] = []
    for match in POD_PATTERN_CONTEXT_RE.finditer(text.lower()):
        value = (match.group("quoted") or match.group("plain") or "").strip("`.,;:()[]{}")
        if not value or value in {"pod", "pods"} or value in seen:
            continue
        seen.add(value)
        patterns.append(value)
    return patterns[:8]


def normalized_pod_pattern_from_texts(texts: Sequence[str]) -> str:
    seen: set[str] = set()
    patterns: list[str] = []
    for text in texts:
        for pattern in pod_patterns_from_text(text):
            if pattern in seen:
                continue
            seen.add(pattern)
            patterns.append(pattern)
    if not patterns:
        return ""
    for pattern in patterns:
        if "*" in pattern:
            return pattern
    test_pod_patterns = [pattern for pattern in patterns if pattern.startswith("aiops-test-pod-")]
    if test_pod_patterns:
        return "aiops-test-pod-*"
    return patterns[0]


def focus_namespace_from_text(text: str) -> str:
    for name in namespace_names_from_message(text):
        if "pod" not in name:
            return name
    return ""


def recent_context_texts(req: Any) -> list[str]:
    return [
        str(message.content or "")
        for message in reversed(req.recentMessages[-6:])
        if str(message.role or "").strip().lower() in {"user", "assistant"}
        and str(message.content or "").strip()
    ]


def conversation_focus_from_request(req: Any, deps: ConversationCleanupDependencies) -> dict[str, str]:
    current = req.message or ""
    texts = [current, *recent_context_texts(req)]
    namespace = focus_namespace_from_text(current) or deps.page_context_namespace(req)
    pod_pattern = normalized_pod_pattern_from_texts(texts)
    for text in texts:
        if not namespace:
            namespace = focus_namespace_from_text(text)
        if namespace and pod_pattern:
            break
    combined = " ".join(texts).lower()
    intent = ""
    if CLEANUP_DELETE_REVIEW_RE.search(current):
        intent = "cleanup_delete_review"
    elif AMBIGUOUS_CLEANUP_REQUEST_RE.search(current) or (
        CLEANUP_SCOPE_CONFIRMATION_RE.search(current)
        and re.search(r"정리|cleanup|테스트\s*pod|테스트\s*파드|test\s*pod", combined, re.IGNORECASE)
    ):
        intent = "cleanup_review"
    focus = {
        "intent": intent,
        "namespace": namespace,
        "podPattern": pod_pattern,
        "resourceKind": "Pod" if re.search(r"(?i)(pod|pods|파드)", combined) else "",
    }
    return {key: value for key, value in focus.items() if value}


def is_ambiguous_cleanup_review_request(req: Any, deps: ConversationCleanupDependencies) -> bool:
    text = re.sub(r"\s+", " ", req.message or "").strip()
    if not text or is_namespace_cleanup_request(req, deps):
        return False
    return bool(AMBIGUOUS_CLEANUP_REQUEST_RE.search(text))


def should_clarify_cleanup_scope(
    req: Any,
    deps: ConversationCleanupDependencies,
    focus: Mapping[str, str] | None = None,
) -> bool:
    if not is_ambiguous_cleanup_review_request(req, deps):
        return False
    active_focus = dict(focus or conversation_focus_from_request(req, deps))
    if active_focus.get("namespace") or active_focus.get("podPattern"):
        return True
    return bool(re.search(r"(?i)(안에|그\s*파드|그\s*namespace|그\s*네임스페이스|테스트|test)", req.message))


def should_create_cleanup_review_candidate(
    req: Any,
    deps: ConversationCleanupDependencies,
    focus: Mapping[str, str] | None = None,
) -> bool:
    active_focus = dict(focus or conversation_focus_from_request(req, deps))
    if active_focus.get("intent") != "cleanup_review":
        return False
    if not active_focus.get("namespace") or not active_focus.get("podPattern"):
        return False
    if is_ambiguous_cleanup_review_request(req, deps):
        return False
    return bool(CLEANUP_SCOPE_CONFIRMATION_RE.search(req.message or ""))


def cleanup_delete_count_from_message(message: str) -> int:
    text = message.lower()
    digit = re.search(r"([1-9])\s*(?:개|pods?|파드)(?:만)?", text)
    if digit:
        return int(digit.group(1))
    korean_numbers = (
        (1, r"한\s*개|하나|일\s*개"), (2, r"두\s*개|둘|두\s*대|이\s*개"),
        (3, r"세\s*개|셋|삼\s*개"), (4, r"네\s*개|넷|사\s*개"),
        (5, r"다섯\s*개|다섯|오\s*개"),
    )
    for count, pattern in korean_numbers:
        if re.search(pattern, text, re.IGNORECASE):
            return count
    return 0


def should_create_latest_cleanup_delete_review_candidate(
    req: Any,
    deps: ConversationCleanupDependencies,
    focus: Mapping[str, str] | None = None,
) -> bool:
    active_focus = dict(focus or conversation_focus_from_request(req, deps))
    if active_focus.get("intent") != "cleanup_delete_review":
        return False
    if not active_focus.get("namespace") or not active_focus.get("podPattern"):
        return False
    if cleanup_delete_count_from_message(req.message or "") <= 0:
        return False
    return bool(CLEANUP_DELETE_REVIEW_RE.search(req.message or ""))


def cleanup_scope_clarification_response(
    req: Any,
    deps: ConversationCleanupDependencies,
    focus: Mapping[str, str] | None = None,
) -> str:
    active_focus = dict(focus or conversation_focus_from_request(req, deps))
    namespace = active_focus.get("namespace")
    pod_pattern = active_focus.get("podPattern")
    if namespace and pod_pattern:
        return "\n".join([
            "## 현재 판단", f"`{namespace}`의 `{pod_pattern}` 정리 가능 여부를 확인합니다.", "",
            "## 확인 필요", "- 정리 검토 전에는 현재 Pod 수, owner, label, 최근 사용 흔적을 먼저 확인해야 합니다.",
            "- 아직 Pod 삭제나 재시작 같은 서버 변경은 실행하지 않습니다.", "", "## 다음 선택",
            f"`{namespace}` / `{pod_pattern}` 범위로 정리 검토를 이어갈 수 있습니다.",
        ])
    if namespace:
        return "\n".join([
            "## 현재 판단", f"`{namespace}` 네임스페이스 안의 테스트성 Pod 정리 검토 요청입니다.", "",
            "## 확인 필요", "- 어떤 Pod 이름 패턴이나 label을 기준으로 볼지 먼저 정해야 합니다.",
            "- 범위가 정해지기 전에는 전체 클러스터 Pod를 정리 후보로 만들지 않습니다.", "", "## 다음 선택",
            f"`{namespace}`에서 확인할 Pod 이름 패턴이나 label을 알려주세요.",
        ])
    return "\n".join([
        "## 현재 판단", "테스트성 Pod 정리 검토 요청이지만 대상 범위가 아직 넓습니다.", "", "## 확인 필요",
        "- 정리 대상 namespace", "- Pod 이름 패턴 또는 label", "- 삭제가 아니라 검토만 할지 여부", "",
        "범위를 확인하면 그 대상만 기준으로 정리 검토를 진행하겠습니다.",
    ])


def pod_name_matches_pattern(pod_name: str, pattern: str) -> bool:
    if not pod_name or not pattern:
        return False
    return pod_name.startswith(pattern[:-1]) if pattern.endswith("*") else pod_name == pattern


def cleanup_candidate_pod_rows(
    focus: Mapping[str, str],
    gateway_evidence: str | None,
    deps: ConversationCleanupDependencies,
) -> list[dict[str, str]]:
    namespace = str(focus.get("namespace") or "")
    pod_pattern = str(focus.get("podPattern") or "")
    parsed_rows, _, _ = deps.parse_gateway_current_pod_list_rows(gateway_evidence)
    if not parsed_rows:
        parsed_rows = deps.parse_gateway_pod_evidence_rows(gateway_evidence)
    rows_by_pod: dict[tuple[str, str], dict[str, str]] = {}
    for row in parsed_rows:
        row_namespace = str(row.get("namespace") or "")
        pod_name = str(row.get("pod") or "")
        if namespace and row_namespace != namespace:
            continue
        if not pod_name_matches_pattern(pod_name, pod_pattern):
            continue
        key = (row_namespace, pod_name)
        previous = rows_by_pod.get(key)
        if previous is None:
            rows_by_pod[key] = dict(row)
            continue
        previous_ts = parse_k8s_timestamp(previous.get("podStart"))
        row_ts = parse_k8s_timestamp(row.get("podStart"))
        if row_ts and (previous_ts is None or row_ts > previous_ts):
            rows_by_pod[key] = dict(row)
    return list(rows_by_pod.values())


def select_latest_cleanup_pod_rows(
    focus: Mapping[str, str],
    gateway_evidence: str | None,
    count: int,
    deps: ConversationCleanupDependencies,
) -> list[dict[str, str]]:
    def sort_key(row: Mapping[str, str]) -> tuple[int, datetime, str]:
        timestamp = parse_k8s_timestamp(row.get("podStart"))
        return (1 if timestamp else 0, timestamp or datetime.min.replace(tzinfo=UTC), str(row.get("pod") or ""))
    return sorted(
        cleanup_candidate_pod_rows(focus, gateway_evidence, deps),
        key=sort_key,
        reverse=True,
    )[:max(0, count)]


def build_conversation_cleanup_review_candidate(
    focus: Mapping[str, str], deps: ConversationCleanupDependencies, *, incident_id: str, run_id: str,
    selected_rows: Sequence[Mapping[str, str]] | None = None, requested_count: int = 0,
) -> dict[str, Any]:
    namespace = str(focus.get("namespace") or "")
    pod_pattern = str(focus.get("podPattern") or "")
    selected_pods = [{
        "currentState": str(row.get("currentState") or ""), "name": str(row.get("pod") or ""),
        "namespace": str(row.get("namespace") or namespace), "owner": str(row.get("owner") or ""),
        "podStart": str(row.get("podStart") or ""), "ready": str(row.get("ready") or ""),
    } for row in (selected_rows or []) if str(row.get("pod") or "")]
    latest_delete_review = bool(selected_pods) or requested_count > 0
    effective_count = requested_count or len(selected_pods)
    selected_names = [pod["name"] for pod in selected_pods]
    target_digest_source = f"{namespace}/{pod_pattern}/{'/'.join(selected_names)}/{effective_count}"
    target_digest = hashlib.sha256(target_digest_source.encode()).hexdigest()[:12]
    title = f"최신 테스트 Pod {effective_count}개 삭제 검토" if latest_delete_review and effective_count else "테스트 Pod 정리 검토"
    source_type = "test_pod_latest_delete_review" if latest_delete_review else "test_pod_cleanup_review"
    evidence = (f"{namespace}/{pod_pattern} 범위의 최신 테스트 Pod {effective_count}개 삭제 검토 요청"
                if latest_delete_review and effective_count else f"{namespace}/{pod_pattern} 범위의 테스트성 Pod 정리 검토 요청")
    expected_impact = ("선택된 테스트 Pod 삭제 가능성을 검토합니다. 승인 전에는 서버 변경이 없습니다."
                       if latest_delete_review else "정리 대상 Pod 목록과 사용 흔적을 검토 기록으로 남깁니다. Pod 삭제는 실행하지 않습니다.")
    return {
        "approvalRequired": True, "blockedActions": list(deps.forbidden_verbs),
        "blockedReasons": ["cleanup-review", "approval-required", "review-only-plan"], "chatRunId": run_id,
        "confidence": "medium", "evidence": evidence,
        "evidenceRefs": [{"evidenceType": "pod_status", "findingId": f"test-pod-cleanup-{target_digest}", "sourceType": source_type, "status": "pending"}],
        "executable": False,
        "executionPolicy": {"executionEnabled": False, "mode": "review-only", "mutationVerbsDisabled": True, "proposalOnly": True},
        "expectedImpact": expected_impact, "expiresAt": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
        "id": f"action-candidate-test-pod-cleanup-{target_digest}", "incidentId": incident_id, "mutationSubmitted": False,
        "parameters": {"podNamePattern": pod_pattern, "requestedCount": effective_count, "reviewOnly": True,
                       "selectedPods": selected_pods, "sortBy": "podStart desc"}, "priority": 5,
        "prerequisiteChecks": ["대상 namespace 확인", "Pod 이름 패턴 또는 label 기준 확인", "ownerReferences, labels, 현재 상태 확인", "생성/시작 시간 확인"],
        "recommendationSteps": ["현재 대상 Pod 목록 조회", "최신순 삭제 검토 대상 산정", "테스트/시나리오 리소스 여부 확인", "승인 후에만 삭제 실행 가능"],
        "riskLevel": "low", "riskLabel": "낮음", "severity": "확인 필요",
        "sourceFindingId": f"test-pod-cleanup-{target_digest}", "sourceType": source_type,
        "statusLabel": "삭제 검토 후보" if latest_delete_review else "정리 검토 후보",
        "target": {"apiVersion": "v1", "kind": "Pod", "name": pod_pattern if not selected_names else ", ".join(selected_names[:2]), "namespace": namespace},
        "title": title,
        "verificationChecks": ["Action Plan 생성 후에도 Pod 삭제가 실행되지 않았는지 확인", "owner/label/현재 상태 확인 실패 시 실행 차단", "승인 후 대상 Pod만 삭제되는지 확인"],
    }


def remember_conversation_cleanup_review_candidate(
    focus: Mapping[str, str], deps: ConversationCleanupDependencies, *, incident_id: str, run_id: str,
    selected_rows: Sequence[Mapping[str, str]] | None = None, requested_count: int = 0,
) -> dict[str, Any]:
    candidate = build_conversation_cleanup_review_candidate(
        focus, deps, incident_id=incident_id, run_id=run_id, selected_rows=selected_rows, requested_count=requested_count,
    )
    now = datetime.now(UTC)
    for key, cached in list(deps.candidate_cache.items()):
        expires_at = parse_k8s_timestamp(cached.get("expiresAt"))
        if expires_at and expires_at < now:
            deps.candidate_cache.pop(key, None)
    deps.candidate_cache[str(candidate["id"])] = candidate
    return candidate


def cleanup_latest_delete_review_response(candidate: Mapping[str, Any]) -> str:
    target = candidate.get("target") if isinstance(candidate.get("target"), Mapping) else {}
    parameters = candidate.get("parameters") if isinstance(candidate.get("parameters"), Mapping) else {}
    namespace = str(target.get("namespace") or "-")
    pod_pattern = str(parameters.get("podNamePattern") or target.get("name") or "-")
    requested_count = int(parameters.get("requestedCount") or 0)
    selected_pods = parameters.get("selectedPods")
    pod_items = selected_pods if isinstance(selected_pods, list) else []
    lines = ["## 현재 판단", f"`{namespace}`의 `{pod_pattern}` 중 최신 {requested_count}개를 삭제 검토 대상으로 확인합니다.", "",
             "## 확인 결과", "| 순서 | Namespace | Pod 이름 | 생성/시작 시간 | 현재 상태 | 삭제 판단 |",
             "| :---: | :--- | :--- | :--- | :--- | :--- |"]
    if pod_items:
        for index, pod in enumerate(pod_items, start=1):
            if not isinstance(pod, Mapping):
                continue
            pod_name = str(pod.get("name") or "-")
            pod_namespace = str(pod.get("namespace") or namespace)
            pod_start = str(pod.get("podStart") or "생성 시간 확인 필요")
            state = str(pod.get("currentState") or "현재 상태 확인 필요")
            decision = "삭제 검토 가능" if pod_start != "생성 시간 확인 필요" else "추가 조회 후 판단"
            lines.append(f"| {index} | `{pod_namespace}` | `{pod_name}` | `{pod_start}` | {state} | {decision} |")
    else:
        lines.append(f"| - | `{namespace}` | `{pod_pattern}` | 생성 시간 확인 필요 | 현재 상태 확인 필요 | 추가 조회 후 판단 |")
    lines.extend(["", "## Action Plan", f"- 후보: `{candidate.get('title') or '최신 테스트 Pod 삭제 검토'}`",
                  "- 승인 전에는 Pod 삭제, 재시작, patch, scale을 실행하지 않습니다.", "- owner, label, 현재 상태 확인이 실패하면 실행을 차단합니다."])
    return "\n".join(lines)


def cleanup_review_candidate_response(candidate: Mapping[str, Any]) -> str:
    if candidate.get("sourceType") == "test_pod_latest_delete_review":
        return cleanup_latest_delete_review_response(candidate)
    target = candidate.get("target") if isinstance(candidate.get("target"), Mapping) else {}
    namespace = str(target.get("namespace") or "-")
    pod_pattern = str(target.get("name") or "-")
    return "\n".join([
        "## 현재 판단", f"`{namespace}` 네임스페이스의 `{pod_pattern}` 범위로 정리 검토 후보를 준비했습니다.", "",
        "## Action Plan", "- 후보: `테스트 Pod 정리 검토`", "- 승인 전에는 Pod 삭제, 재시작, patch, scale을 실행하지 않습니다.",
        "- 먼저 현재 Pod 수, owner, label, 최근 사용 흔적을 확인하는 검토 계획만 만듭니다.", "", "## 다음 행동",
        "Action Plan 생성 버튼으로 검토 계획을 만든 뒤 결과를 확인하세요.",
    ])
