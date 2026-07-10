import hashlib
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from .action_candidates import ACTION_CANDIDATE_FORBIDDEN_VERBS
from .pod_evidence_parsing import (
    is_pod_namespace_pattern_lookup_request,
    parse_gateway_current_pod_list_rows,
    parse_gateway_pod_evidence_rows,
    parse_restart_count,
    pod_inventory_selected_rows,
    pod_row_priority,
)

ChatRequest = Any
_dependency_provider: Callable[[], Any] | None = None


def _configure_dependency_provider(provider: Callable[[], Any]) -> None:
    global _dependency_provider
    _dependency_provider = provider


def _require_dependencies() -> Any:
    if _dependency_provider is None:
        raise RuntimeError("pod action candidate dependencies are not configured")
    return _dependency_provider()


def pod_row_target(row: Mapping[str, str]) -> str:
    namespace = row.get("namespace") or "-"
    pod = row.get("pod") or "-"
    container = row.get("container") or "-"
    return f"{namespace}/{pod}/{container}"


def pod_inventory_action_candidate_from_row(
    row: Mapping[str, str],
    *,
    incident_id: str,
    run_id: str,
) -> dict[str, Any]:
    namespace = str(row.get("namespace") or "")
    pod = str(row.get("pod") or "")
    container = str(row.get("container") or "")
    priority_rank, priority_label, priority_reason = pod_row_priority(row)
    target_digest = hashlib.sha256(f"{namespace}/{pod}/{container}".encode()).hexdigest()[:12]
    current_state = str(row.get("currentState") or "-")
    last_state = str(row.get("lastState") or "-")
    restarts = str(row.get("restarts") or "0")
    evidence = (
        f"{namespace}/{pod}"
        f"{f' container {container}' if container and container != '-' else ''}: "
        f"{priority_reason}. 현재 상태 {current_state}, restart {restarts}, 마지막 종료 {last_state}."
    )
    return {
        "approvalRequired": True,
        "blockedActions": list(ACTION_CANDIDATE_FORBIDDEN_VERBS),
        "blockedReasons": ["diagnostic-review", "review-only-plan"],
        "confidence": "medium",
        "evidence": evidence,
        "evidenceRefs": [
            {
                "evidenceType": "pod_status",
                "findingId": f"pod-inventory-{target_digest}",
                "sourceType": "pod_inventory",
                "status": "collected",
            }
        ],
        "executable": False,
        "executionPolicy": {
            "executionEnabled": False,
            "mode": "review-only",
            "mutationVerbsDisabled": True,
            "proposalOnly": True,
        },
        "expectedImpact": (
            "Pod 로그, 이전 로그, describe, Event 확인 결과를 검토 기록으로 남깁니다. "
            "Pod 삭제, 재시작, patch, scale은 실행하지 않습니다."
        ),
        "id": f"action-candidate-pod-inventory-diagnostic-{target_digest}",
        "mutationSubmitted": False,
        "parameters": {
            "containerName": container if container and container != "-" else "",
            "includeEvents": True,
            "includePreviousLogs": True,
            "includePodDescribe": True,
        },
        "priority": 20 + priority_rank,
        "prerequisiteChecks": [
            "대상 Pod와 namespace 확인",
            "이전 로그와 Event 조회 결과 확인",
            "현재 상태와 마지막 종료 상태를 분리",
        ],
        "recommendationSteps": [
            "Pod 로그/previous log/describe/Event 확인 계획 생성",
            "OOMKilled, probe, API 연결, image pull, command/env/config 문제 분리",
            "원인 확인 뒤 수정/롤백/재생성 여부를 별도 Action Plan으로 판단",
        ],
        "riskLevel": "low",
        "riskLabel": "낮음",
        "severity": priority_label,
        "sourceFindingId": f"pod-inventory-{target_digest}",
        "sourceType": "pod_diagnostic_review",
        "statusLabel": "원인 확인 플랜",
        "target": {
            "apiVersion": "v1",
            "kind": "Pod",
            "name": pod,
            "namespace": namespace,
        },
        "title": "Pod 원인 확인 플랜",
        "verificationChecks": [
            "로그/describe/Event 확인 결과가 기록되었는지 확인",
            "승인 전후 모두 클러스터 변경 작업이 없는지 확인",
        ],
        "chatRunId": run_id,
        "incidentId": incident_id,
        "expiresAt": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
    }


def pod_inventory_action_candidates_from_evidence(
    req: ChatRequest,
    gateway_evidence: str | None,
    *,
    incident_id: str,
    run_id: str,
    limit: int = 2,
) -> list[dict[str, Any]]:
    dependencies = _require_dependencies()
    if dependencies.is_ambiguous_cleanup_review_request(req):
        return []
    if is_pod_namespace_pattern_lookup_request(req.message):
        return []
    if not dependencies.is_pod_list_request(req.message):
        return []

    rows, namespace_filter, _rows_shown = parse_gateway_current_pod_list_rows(gateway_evidence)
    if not rows:
        rows = parse_gateway_pod_evidence_rows(gateway_evidence)

    namespace = dependencies.pod_list_namespace(req) or namespace_filter or ""
    if namespace and namespace != "all-accessible-namespaces":
        rows = [row for row in rows if row.get("namespace") == namespace]

    selected_rows = [
        row
        for row in pod_inventory_selected_rows(req.message, rows)
        if row.get("namespace") and row.get("pod")
    ]
    return [
        pod_inventory_action_candidate_from_row(row, incident_id=incident_id, run_id=run_id)
        for row in selected_rows[:limit]
    ]


def pod_inventory_check_commands(rows: list[Mapping[str, str]], namespace: str) -> list[str]:
    commands: list[str] = []
    sorted_rows = sorted(
        rows,
        key=lambda row: (pod_row_priority(row)[0], -parse_restart_count(row.get("restarts") or "")),
    )
    for row in sorted_rows[:2]:
        ns = row.get("namespace") or namespace
        pod = row.get("pod") or ""
        container = row.get("container") or ""
        if not ns or not pod or pod == "-":
            continue
        current = str(row.get("currentState") or "")
        last_state = str(row.get("lastState") or "")
        if (
            container
            and container != "-"
            and (
                re.search(r"(?i)(crashloopbackoff)", current)
                or re.search(r"(?i)(error|oomkilled)", last_state)
            )
        ):
            commands.append(f"oc logs {pod} -n {ns} -c {container} --previous --tail=120")
            commands.append(f"oc describe pod {pod} -n {ns}")
        elif re.search(r"(?i)(imagepullbackoff|errimagepull|pending|waiting:)", current):
            commands.append(f"oc describe pod {pod} -n {ns}")
        else:
            commands.append(f"oc describe pod {pod} -n {ns}")
    if not commands:
        commands.append(f"oc get pods -n {namespace}" if namespace != "all-accessible-namespaces" else "oc get pods -A")
    deduped: list[str] = []
    for command in commands:
        if command not in deduped:
            deduped.append(command)
    return deduped[:4]
