import asyncio
import hashlib
import re
from collections.abc import Awaitable, Callable, Mapping, MutableMapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx


SYSTEM_NAMESPACE_RE = re.compile(
    r"^(default|kube-|openshift-|redhat-|olm|local)$", re.IGNORECASE
)


@dataclass(frozen=True)
class NamespaceCleanupInventoryConfig:
    api_url: str
    api_ca_file: str | bool


@dataclass(frozen=True)
class NamespaceCleanupInventoryDependencies:
    fetch_ocp_json: Callable[
        [httpx.AsyncClient, str, str], Awaitable[Mapping[str, Any] | None]
    ]


@dataclass(frozen=True)
class NamespaceCleanupCandidateConfig:
    forbidden_verbs: Sequence[str]


@dataclass(frozen=True)
class NamespaceCleanupRenderDependencies:
    action_capable_mode: Callable[[str], bool]
    execution_mode_sentence: Callable[[str, str], str]


@dataclass(frozen=True)
class NamespaceCleanupCandidateStoreDependencies:
    candidate_cache: MutableMapping[str, dict[str, Any]]
    build_candidate: Callable[[Mapping[str, Any], str, str], dict[str, Any]]
    candidates_from_inventory: Callable[[Mapping[str, Any]], list[Mapping[str, Any]]]


def resource_items(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not payload:
        return []
    items = payload.get("items")
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def metadata_name(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    return str(metadata.get("name") or "")


def metadata_namespace(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    return str(metadata.get("namespace") or "")


def resource_labels(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    labels = metadata.get("labels")
    return labels if isinstance(labels, Mapping) else {}


def parse_k8s_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def age_days(value: Any) -> int | None:
    timestamp = parse_k8s_timestamp(value)
    if not timestamp:
        return None
    return max(0, int((datetime.now(UTC) - timestamp).total_seconds() // 86400))


def namespace_resource_counts(
    namespace: str,
    payloads: Mapping[str, Mapping[str, Any] | None],
) -> dict[str, int]:
    def count_for(payload_name: str) -> int:
        return len(
            [
                item
                for item in resource_items(payloads.get(payload_name))
                if metadata_namespace(item) == namespace
            ]
        )

    return {
        "deployments": count_for("deployments"),
        "events": count_for("events"),
        "pods": count_for("pods"),
        "pvcs": count_for("pvcs"),
        "routes": count_for("routes"),
        "services": count_for("services"),
    }


def namespace_last_event_age_days(
    namespace: str,
    events_payload: Mapping[str, Any] | None,
) -> int | None:
    latest: datetime | None = None
    for event in resource_items(events_payload):
        if metadata_namespace(event) != namespace:
            continue
        metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), Mapping) else {}
        event_time = (
            event.get("lastTimestamp")
            or event.get("eventTime")
            or event.get("firstTimestamp")
            or metadata.get("creationTimestamp")
        )
        parsed = parse_k8s_timestamp(event_time)
        if parsed and (latest is None or parsed > latest):
            latest = parsed
    if not latest:
        return None
    return max(0, int((datetime.now(UTC) - latest).total_seconds() // 86400))


def namespace_cleanup_decision(
    namespace: str,
    namespace_resource: Mapping[str, Any] | None,
    counts: Mapping[str, int],
    last_event_age: int | None,
) -> dict[str, str]:
    if namespace_resource is None:
        return {"label": "확인 불가", "reason": "namespace가 조회 결과에 없습니다", "next": "이름을 다시 확인"}
    if SYSTEM_NAMESPACE_RE.search(namespace):
        return {"label": "보호", "reason": "시스템 또는 기본 namespace", "next": "삭제 계획 제외"}

    workload_count = int(counts.get("pods") or 0) + int(counts.get("deployments") or 0)
    exposure_count = int(counts.get("services") or 0) + int(counts.get("routes") or 0) + int(counts.get("pvcs") or 0)
    if workload_count > 0 or exposure_count > 0:
        return {
            "label": "사용 중",
            "reason": f"workload {workload_count}개, service/route/pvc {exposure_count}개 확인",
            "next": "소유자와 실제 서비스 영향 확인",
        }
    if last_event_age is not None and last_event_age <= 7:
        return {"label": "삭제 보류", "reason": f"최근 이벤트가 {last_event_age}일 전 확인", "next": "최근 작업 목적 확인"}
    return {
        "label": "정리 검토 가능",
        "reason": "workload, service, route, pvc가 없고 최근 활동 신호가 약함",
        "next": "소유자/백업/PVC 재확인 후 승인 검토",
    }


def namespace_cleanup_candidate_from_item(
    item: Mapping[str, Any],
    run_id: str,
    incident_id: str,
    config: NamespaceCleanupCandidateConfig,
) -> dict[str, Any]:
    namespace = str(item.get("namespace") or "")
    uid = str(item.get("uid") or f"namespace-{namespace}")
    candidate_id = f"action-candidate-namespace-cleanup-{hashlib.sha256(namespace.encode()).hexdigest()[:12]}"
    return {
        "approvalRequired": True,
        "blockedActions": list(config.forbidden_verbs),
        "blockedReasons": ["approval-required", "review-only-plan"],
        "confidence": "medium",
        "evidence": str(item.get("reason") or "namespace read-only inventory"),
        "evidenceRefs": [{"evidenceType": "namespace_inventory", "findingId": f"namespace-cleanup-{namespace}", "sourceType": "namespace_cleanup_review", "status": "collected"}],
        "executable": False,
        "executionPolicy": {"executionEnabled": False, "mode": "review-only", "mutationVerbsDisabled": True, "proposalOnly": True},
        "expectedImpact": "정리 후보를 승인 검토 계획으로 고정합니다. 이 후보 자체는 namespace 삭제를 실행하지 않습니다.",
        "id": candidate_id,
        "mutationSubmitted": False,
        "priority": 40,
        "prerequisiteChecks": ["소유자 확인", "PVC/Route 잔존 여부 재확인", "백업 필요 여부 확인"],
        "recommendationSteps": ["namespace 사용 신호 재확인", "정리 검토 Action Plan 생성", "별도 삭제 승인 정책 확인"],
        "riskLevel": "medium",
        "riskLabel": "중간",
        "severity": "확인 필요",
        "sourceFindingId": f"namespace-cleanup-{namespace}",
        "sourceType": "namespace_cleanup_review",
        "statusLabel": "승인 필요",
        "target": {"apiVersion": "v1", "kind": "Namespace", "name": namespace, "namespace": namespace, "uid": uid},
        "title": "Namespace 정리 검토",
        "verificationChecks": ["Action Plan 생성 후에도 namespace가 존재하는지 확인", "삭제 실행 기록이 없는지 확인"],
        "chatRunId": run_id,
        "incidentId": incident_id,
        "expiresAt": (datetime.now(UTC) + timedelta(minutes=15)).isoformat(),
    }


async def collect_namespace_cleanup_inventory(
    user_auth_header: str,
    requested_names: Sequence[str],
    config: NamespaceCleanupInventoryConfig,
    deps: NamespaceCleanupInventoryDependencies,
) -> dict[str, Any]:
    if not config.api_url:
        return {
            "error": "OPENSHIFT_API_URL is not configured",
            "inspected": [],
            "ok": False,
            "requestedNames": list(requested_names),
            "server": "",
            "status": "missing_api_url",
            "totalNamespaces": 0,
        }

    async with httpx.AsyncClient(verify=config.api_ca_file, timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        payloads_result = await asyncio.gather(
            deps.fetch_ocp_json(client, "/api/v1/namespaces?limit=500", user_auth_header),
            deps.fetch_ocp_json(client, "/api/v1/pods?limit=500", user_auth_header),
            deps.fetch_ocp_json(client, "/apis/apps/v1/deployments?limit=500", user_auth_header),
            deps.fetch_ocp_json(client, "/api/v1/services?limit=500", user_auth_header),
            deps.fetch_ocp_json(client, "/apis/route.openshift.io/v1/routes?limit=500", user_auth_header),
            deps.fetch_ocp_json(client, "/api/v1/persistentvolumeclaims?limit=500", user_auth_header),
            deps.fetch_ocp_json(client, "/api/v1/events?limit=500", user_auth_header),
        )
    namespaces_payload, pods_payload, deployments_payload, services_payload, routes_payload, pvcs_payload, events_payload = payloads_result
    namespace_items = resource_items(namespaces_payload)
    namespace_by_name = {metadata_name(item): item for item in namespace_items}
    names = [name for name in requested_names if name]
    if not names:
        names = [name for name in sorted(namespace_by_name) if not SYSTEM_NAMESPACE_RE.search(name)][:12]

    payloads = {
        "deployments": deployments_payload,
        "events": events_payload,
        "pods": pods_payload,
        "pvcs": pvcs_payload,
        "routes": routes_payload,
        "services": services_payload,
    }
    inspected: list[dict[str, Any]] = []
    for namespace in names[:12]:
        namespace_resource = namespace_by_name.get(namespace)
        metadata = namespace_resource.get("metadata", {}) if isinstance(namespace_resource, Mapping) and isinstance(namespace_resource.get("metadata"), Mapping) else {}
        counts = namespace_resource_counts(namespace, payloads)
        last_event_age = namespace_last_event_age_days(namespace, events_payload)
        decision = namespace_cleanup_decision(namespace, namespace_resource, counts, last_event_age)
        inspected.append({
            "counts": counts,
            "createdAgeDays": age_days(metadata.get("creationTimestamp")),
            "decision": decision,
            "eventCount": counts["events"],
            "lastEventAgeDays": last_event_age,
            "namespace": namespace,
            "ok": namespace_resource is not None,
            "reason": decision["reason"],
            "uid": str(metadata.get("uid") or ""),
        })
    return {
        "inspected": inspected,
        "ok": bool(namespace_items),
        "requestedNames": names[:12],
        "server": config.api_url,
        "status": "success" if namespace_items else "empty_namespace_inventory",
        "totalNamespaces": len(namespace_items),
    }


def namespace_cleanup_candidates_from_inventory(inventory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in inventory.get("inspected", [])
        if isinstance(item, Mapping)
        and isinstance(item.get("decision"), Mapping)
        and item["decision"].get("label") == "정리 검토 가능"
    ]


def namespace_cleanup_command_block(inventory: Mapping[str, Any]) -> str:
    names = [str(item.get("namespace") or "") for item in inventory.get("inspected", []) if isinstance(item, Mapping) and item.get("namespace")]
    lines = ["```bash", "oc whoami --show-server", "oc get namespaces"]
    for namespace in names[:12]:
        lines.append(f"oc get all,pvc,route,event -n {namespace} --ignore-not-found")
        lines.append(f"oc get namespace {namespace} -o yaml")
    lines.append("```")
    return "\n".join(lines)


def _english_decision_text(value: Any) -> str:
    text = str(value or "-")
    replacements = {
        "namespace가 조회 결과에 없습니다": "namespace was not found in the query result",
        "시스템 또는 기본 namespace": "system or default namespace",
        "소유자와 실제 서비스 영향 확인": "confirm owner and service impact",
        "최근 작업 목적 확인": "confirm the purpose of recent activity",
        "삭제 계획 제외": "exclude from deletion plans",
        "이름을 다시 확인": "recheck the namespace name",
        "소유자/백업/PVC 재확인 후 승인 검토": "confirm owner, backup, and PVC state before approval review",
        "workload, service, route, pvc가 없고 최근 활동 신호가 약함": "no workload, service, route, or PVC was found and recent activity evidence is weak",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"workload\s+(\d+)개,\s+service/route/pvc\s+(\d+)개\s+확인", r"workload \1, service/route/pvc \2 found", text)
    return re.sub(r"최근 이벤트가\s+(\d+)일 전 확인", r"latest event was \1 days ago", text)


def namespace_cleanup_answer(
    inventory: Mapping[str, Any],
    execution_mode: str,
    language: str,
    deps: NamespaceCleanupRenderDependencies,
) -> str:
    is_en = language == "en"
    if not inventory.get("ok"):
        if is_en:
            return "\n".join(["## Current Status", "AIOps for OCP could not run the OpenShift read-only namespace query.", "", "## Failure Point", f"- {inventory.get('status')}: {inventory.get('error') or 'namespace inventory unavailable'}", "", "## Next Step", "- First verify `oc whoami --show-server` and `oc get namespaces` from the terminal.", "- No cleanup candidate is decided until read-only evidence is collected."])
        return "\n".join(["## 현재 상태", "AIOps for OCP가 OpenShift namespace read-only 조회를 실행하지 못했습니다.", "", "## 실패 지점", f"- {inventory.get('status')}: {inventory.get('error') or 'namespace inventory unavailable'}", "", "## 다음 조치", "- 터미널에서 `oc whoami --show-server`와 `oc get namespaces`가 되는지 먼저 확인해야 합니다.", "- 조회 결과가 정리되기 전에는 정리 후보를 판정하지 않습니다."])

    cleanup_candidates = namespace_cleanup_candidates_from_inventory(inventory)
    action_mode = deps.action_capable_mode(execution_mode)
    mode_line = deps.execution_mode_sentence(execution_mode, language)
    if is_en:
        suffix = "Cleanup review candidates exist, so an approval-gated Action Plan candidate can be created." if action_mode and cleanup_candidates else "No safe cleanup review candidate was found." if action_mode else ""
        lines = ["## Current Assessment", f"{mode_line} {suffix}".strip(), "", "## Query Evidence", f"- API server: {inventory.get('server') or '-'}", f"- Accessible namespaces: {inventory.get('totalNamespaces')}", f"- Query scope: {', '.join(inventory.get('requestedNames') or [])}", "", "## Namespace Decisions", "| Namespace | Decision | Evidence | Next Step |", "|---|---|---|---|"]
        label_map = {"확인 불가": "Unknown", "보호": "Protected", "사용 중": "In use", "삭제 보류": "Hold", "정리 검토 가능": "Cleanup review candidate"}
        for item in inventory.get("inspected", []):
            if isinstance(item, Mapping):
                decision = item.get("decision") if isinstance(item.get("decision"), Mapping) else {}
                lines.append(f"| {item.get('namespace')} | {label_map.get(str(decision.get('label') or ''), str(decision.get('label') or '-'))} | {_english_decision_text(decision.get('reason'))} | {_english_decision_text(decision.get('next'))} |")
        action_status = f"- Approval-required candidates: {', '.join(f'`{item.get('namespace')}`' for item in cleanup_candidates)}" if action_mode and cleanup_candidates else "- Status: execution mode is enabled, but no safe cleanup candidate was found." if action_mode else "- Status: read-only mode shows cleanup review candidates only; switch to execution-enabled mode to create an Action Plan."
        lines.extend(["", "## Action Plan", action_status, "- This review plan does not delete a namespace by itself.", "- Deletion requires a separate owner/backup/PVC/Route confirmation policy.", "- Read-only terminal checks include `oc get namespaces` and `oc get all,pvc,route,event` for each reviewed namespace.", "", "## Terminal Check Commands", namespace_cleanup_command_block(inventory)])
        return "\n".join(lines)

    suffix = "정리 검토 후보가 있어 Action Plan 후보를 만들 수 있습니다." if action_mode and cleanup_candidates else "안전한 정리 검토 후보가 없습니다." if action_mode else ""
    lines = ["## 현재 판단", f"{mode_line} {suffix}".strip(), "", "## 조회 결과", f"- API 서버: {inventory.get('server') or '-'}", f"- 접근 가능한 namespace: {inventory.get('totalNamespaces')}개", f"- 조회 범위: {', '.join(inventory.get('requestedNames') or [])}", "", "## 네임스페이스별 판단", "| Namespace | 판단 | 확인 결과 | 다음 조치 |", "|---|---|---|---|"]
    for item in inventory.get("inspected", []):
        if isinstance(item, Mapping):
            decision = item.get("decision") if isinstance(item.get("decision"), Mapping) else {}
            lines.append(f"| {item.get('namespace')} | {decision.get('label')} | {decision.get('reason')} | {decision.get('next')} |")
    action_status = f"- 승인 필요 후보: {', '.join(f'`{item.get('namespace')}`' for item in cleanup_candidates)}" if action_mode and cleanup_candidates else "- 상태: 실행 가능 모드이지만 안전한 정리 후보가 없어 Action Plan 버튼을 만들지 않습니다." if action_mode else "- 상태: 읽기 전용 모드에서는 정리 검토 후보만 표시하고, Action Plan 생성은 실행 가능 모드에서 진행합니다."
    lines.extend(["", "## Action Plan", action_status, "- 이 검토 계획은 namespace 삭제를 직접 실행하지 않습니다.", "- 실제 삭제는 소유자 확인, PVC/Route 잔존 여부, 백업 필요 여부를 별도로 승인해야 합니다.", "", "## 터미널 확인 명령", namespace_cleanup_command_block(inventory)])
    return "\n".join(lines)


def remember_namespace_cleanup_candidates(
    inventory: Mapping[str, Any],
    run_id: str,
    incident_id: str,
    deps: NamespaceCleanupCandidateStoreDependencies,
) -> None:
    candidates = [deps.build_candidate(item, run_id, incident_id) for item in deps.candidates_from_inventory(inventory)]
    now = datetime.now(UTC)
    for key, candidate in list(deps.candidate_cache.items()):
        expires_at = parse_k8s_timestamp(candidate.get("expiresAt"))
        if expires_at and expires_at < now:
            deps.candidate_cache.pop(key, None)
    for candidate in candidates:
        deps.candidate_cache[str(candidate["id"])] = candidate


def merge_recent_namespace_cleanup_candidates(
    action_candidates: Mapping[str, Any],
    candidate_cache: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    merged = dict(action_candidates)
    spec = dict(merged.get("spec", {})) if isinstance(merged.get("spec"), Mapping) else {}
    candidates = list(spec.get("candidates") or []) if isinstance(spec.get("candidates"), list) else []
    now = datetime.now(UTC)
    recent = []
    for candidate in candidate_cache.values():
        expires_at = parse_k8s_timestamp(candidate.get("expiresAt"))
        if expires_at and expires_at >= now:
            recent.append({key: value for key, value in candidate.items() if key != "expiresAt"})
    existing_ids = {str(candidate.get("id") or "") for candidate in candidates if isinstance(candidate, Mapping)}
    candidates.extend(candidate for candidate in recent if str(candidate.get("id") or "") not in existing_ids)
    candidates = sorted([candidate for candidate in candidates if isinstance(candidate, Mapping)], key=lambda item: (0 if item.get("chatRunId") else 1, int(item.get("priority") or 999), str(item.get("id") or "")))
    spec["candidates"] = candidates[:8]
    totals = dict(spec.get("totals", {})) if isinstance(spec.get("totals"), Mapping) else {}
    totals.update({"approvalRequired": len(candidates), "shown": min(len(candidates), 8), "total": len(candidates)})
    spec["totals"] = totals
    if recent and spec.get("status") in {None, "", "idle"}:
        spec["status"] = "candidates"
        spec["statusLabel"] = f"승인 기반 조치 후보 {len(candidates)}건"
    merged["spec"] = spec
    return merged
