import json
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any

import httpx

from .aiops_core import path_segment
from .cluster_common import metadata_name, metadata_namespace, resource_items
from .cluster_evidence import safe_error_text
from .security import redact_sensitive


FetchOcpJson = Callable[..., Awaitable[Mapping[str, Any] | None]]
AsyncCallback = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class ClusterEvidenceRuntimeConfig:
    openshift_api_url: str
    openshift_api_ca_file: str | bool
    demo_namespace_allowlist: frozenset[str]


@dataclass(frozen=True)
class ClusterEvidenceRuntimeCallbacks:
    fetch_ocp_json: FetchOcpJson
    fetch_ocp_text_status: AsyncCallback
    fetch_resource_access_review: AsyncCallback
    fetch_crashloop_demo_access_reviews: AsyncCallback
    fetch_ocp_log_pattern_probe: AsyncCallback
    collect_cluster_wide_restart_fallback_events: AsyncCallback


def _evidence_summary(label: str, status: str) -> str:
    if status == "success":
        return f"{label} 수집 완료"
    if status == "partial":
        return f"{label} 부분 수집"
    return f"{label} 수집 불가"


def container_status_rows(pod_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    status = pod_payload.get("status") if isinstance(pod_payload.get("status"), Mapping) else {}
    statuses = status.get("containerStatuses")
    rows: list[dict[str, Any]] = []
    for item in statuses if isinstance(statuses, list) else []:
        if not isinstance(item, Mapping):
            continue
        state = item.get("state") if isinstance(item.get("state"), Mapping) else {}
        waiting = state.get("waiting") if isinstance(state.get("waiting"), Mapping) else {}
        terminated = state.get("terminated") if isinstance(state.get("terminated"), Mapping) else {}
        last_state = item.get("lastState") if isinstance(item.get("lastState"), Mapping) else {}
        last_terminated = (
            last_state.get("terminated")
            if isinstance(last_state.get("terminated"), Mapping)
            else {}
        )
        rows.append(
            {
                "container": str(item.get("name") or "unknown"),
                "lastReason": str(last_terminated.get("reason") or ""),
                "ready": bool(item.get("ready")),
                "restartCount": int(item.get("restartCount") or 0),
                "stateReason": str(waiting.get("reason") or terminated.get("reason") or ""),
            }
        )
    return rows


def crashloop_container_name(pod_payload: Mapping[str, Any]) -> str:
    rows = container_status_rows(pod_payload)
    waiting_crashloop = [
        row
        for row in rows
        if "crashloop" in str(row.get("stateReason") or "").lower()
    ]
    if waiting_crashloop:
        return str(waiting_crashloop[0].get("container") or "")
    if rows:
        return str(sorted(rows, key=lambda row: int(row.get("restartCount") or 0), reverse=True)[0].get("container") or "")
    return ""


def summarize_pod_event_availability(events_payload: Mapping[str, Any] | None) -> tuple[str, int]:
    items = events_payload.get("items") if isinstance(events_payload, Mapping) else []
    warning_reasons: dict[str, int] = {}
    total = 0
    for event in items if isinstance(items, list) else []:
        if not isinstance(event, Mapping):
            continue
        total += 1
        if str(event.get("type") or "") != "Warning":
            continue
        reason = str(event.get("reason") or "Warning")
        warning_reasons[reason] = warning_reasons.get(reason, 0) + 1

    reason_summary = ", ".join(
        f"{reason}={count}"
        for reason, count in sorted(warning_reasons.items(), key=lambda item: (-item[1], item[0]))[:5]
    )
    if reason_summary:
        return f"events={total}; warningReasons={reason_summary}; raw event messages omitted", total
    return f"events={total}; warningReasons=none; raw event messages omitted", total


async def fetch_ocp_text_status(
    config: ClusterEvidenceRuntimeConfig,
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
) -> dict[str, Any]:
    response = await client.get(
        f"{config.openshift_api_url}{path}",
        headers={
            "Accept": "text/plain",
            "Authorization": authorization,
        },
    )
    if response.status_code >= 400:
        return {
            "byteCount": 0,
            "httpStatus": response.status_code,
            "lineCount": 0,
            "reason": f"HTTP {response.status_code}",
            "status": "skipped",
        }
    return {
        "byteCount": len(response.content or b""),
        "httpStatus": response.status_code,
        "lineCount": len(response.text.splitlines()),
        "reason": "",
        "status": "success",
    }


def build_resource_access_review_request(resource_attributes: Mapping[str, Any]) -> dict[str, Any]:
    clean_attributes = {
        key: value
        for key, value in dict(resource_attributes).items()
        if value is not None and value != ""
    }
    return {
        "apiVersion": "authorization.k8s.io/v1",
        "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": clean_attributes},
    }


async def fetch_resource_access_review(
    config: ClusterEvidenceRuntimeConfig,
    client: httpx.AsyncClient,
    user_auth_header: str,
    resource_attributes: Mapping[str, Any],
) -> dict[str, Any]:
    review_request = build_resource_access_review_request(resource_attributes)
    response = await client.post(
        f"{config.openshift_api_url}/apis/authorization.k8s.io/v1/selfsubjectaccessreviews",
        headers={
            "Accept": "application/json",
            "Authorization": user_auth_header,
            "Content-Type": "application/json",
        },
        json=review_request,
    )
    if response.status_code >= 400:
        return {
            "allowed": False,
            "evaluationError": safe_error_text(response.text, limit=300),
            "reason": f"SelfSubjectAccessReview failed with HTTP {response.status_code}",
            "resourceAttributes": review_request["spec"]["resourceAttributes"],
        }

    payload = response.json()
    status_payload = payload.get("status", {}) if isinstance(payload, Mapping) else {}
    status_map = status_payload if isinstance(status_payload, Mapping) else {}
    return {
        "allowed": bool(status_map.get("allowed")),
        "denied": bool(status_map.get("denied")),
        "evaluationError": status_map.get("evaluationError") or "",
        "reason": status_map.get("reason") or "",
        "resourceAttributes": review_request["spec"]["resourceAttributes"],
    }


async def fetch_crashloop_demo_access_reviews(
    config: ClusterEvidenceRuntimeConfig,
    client: httpx.AsyncClient,
    user_auth_header: str,
    target: Mapping[str, str],
) -> dict[str, dict[str, Any]]:
    namespace = str(target.get("namespace") or "")
    pod_name = str(target.get("name") or "")
    return {
        "eventsList": await fetch_resource_access_review(
                config,
            client,
            user_auth_header,
            {
                "namespace": namespace,
                "resource": "events",
                "verb": "list",
            },
        ),
        "podGet": await fetch_resource_access_review(
                config,
            client,
            user_auth_header,
            {
                "namespace": namespace,
                "name": pod_name,
                "resource": "pods",
                "verb": "get",
            },
        ),
        "podLogGet": await fetch_resource_access_review(
                config,
            client,
            user_auth_header,
            {
                "namespace": namespace,
                "name": pod_name,
                "resource": "pods",
                "subresource": "log",
                "verb": "get",
            },
        ),
    }


def crashloop_demo_skipped_evidence_events(
    *,
    request_id: str,
    target: Mapping[str, str],
    reason: str,
    detail: str = "",
) -> list[dict[str, Any]]:
    safe_detail = safe_error_text(detail or reason, limit=700)
    return [
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "event",
            "id": f"{request_id}-crashloop-event-evidence",
            "missingReason": reason,
            "name": "crashloop_event_evidence",
            "sourcePath": "",
            "status": "skipped",
            "summary": "CrashLoop Event 조회 결과 수집 생략",
            "target": dict(target),
        },
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "pod_log",
            "id": f"{request_id}-crashloop-log-availability",
            "missingReason": reason,
            "name": "crashloop_log_availability",
            "sourcePath": "",
            "status": "skipped",
            "summary": "CrashLoop 이전 로그 가용성 확인 생략",
            "target": dict(target),
        },
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "snapshot",
            "id": f"{request_id}-crashloop-pod-snapshot",
            "missingReason": reason,
            "name": "crashloop_pod_snapshot",
            "sourcePath": "",
            "status": "skipped",
            "summary": "CrashLoop Pod snapshot 조회 결과 수집 생략",
            "target": dict(target),
        },
    ]


async def collect_crashloop_demo_evidence_events(
    config: ClusterEvidenceRuntimeConfig,
    callbacks: ClusterEvidenceRuntimeCallbacks,
    user_auth_header: str,
    target: Mapping[str, str],
    request_id: str,
) -> list[dict[str, Any]]:
    if not config.openshift_api_url:
        return [
            {
                "type": "tool_result",
                "detail": "CrashLoop event evidence unavailable: OPENSHIFT_API_URL is not configured.",
                "evidenceType": "event",
                "id": f"{request_id}-crashloop-event-evidence",
                "missingReason": "OPENSHIFT_API_URL is not configured",
                "name": "crashloop_event_evidence",
                "sourcePath": "",
                "status": "skipped",
                "summary": "CrashLoop Event 조회 결과 수집 생략",
            },
            {
                "type": "tool_result",
                "detail": "CrashLoop previous log availability unavailable: OPENSHIFT_API_URL is not configured.",
                "evidenceType": "pod_log",
                "id": f"{request_id}-crashloop-log-availability",
                "missingReason": "OPENSHIFT_API_URL is not configured",
                "name": "crashloop_log_availability",
                "sourcePath": "",
                "status": "skipped",
                "summary": "CrashLoop 이전 로그 가용성 확인 생략",
            },
            {
                "type": "tool_result",
                "detail": "CrashLoop Pod snapshot unavailable: OPENSHIFT_API_URL is not configured.",
                "evidenceType": "snapshot",
                "id": f"{request_id}-crashloop-pod-snapshot",
                "missingReason": "OPENSHIFT_API_URL is not configured",
                "name": "crashloop_pod_snapshot",
                "sourcePath": "",
                "status": "skipped",
                "summary": "CrashLoop Pod snapshot 조회 결과 수집 생략",
            },
        ]

    namespace = str(target.get("namespace") or "")
    pod_name = str(target.get("name") or "")
    if not namespace or not pod_name:
        return crashloop_demo_skipped_evidence_events(
            request_id=request_id,
            target=target,
            reason="CrashLoop demo target is incomplete.",
        )

    if namespace not in config.demo_namespace_allowlist:
        return crashloop_demo_skipped_evidence_events(
            request_id=request_id,
            target=target,
            reason=f"Namespace {namespace} is not allowlisted for CrashLoop demo evidence collection.",
            detail=json.dumps(
                {
                    "allowlist": sorted(config.demo_namespace_allowlist),
                    "namespace": namespace,
                    "target": dict(target),
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    pod_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods/{path_segment(pod_name)}"
    events_path = (
        f"/api/v1/namespaces/{path_segment(namespace)}/events"
        f"?fieldSelector=involvedObject.name={path_segment(pod_name)}&limit=50"
    )

    async with httpx.AsyncClient(
        verify=config.openshift_api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        access_reviews = await callbacks.fetch_crashloop_demo_access_reviews(
            client, user_auth_header, target
        )
        denied_reviews = {
            key: value
            for key, value in access_reviews.items()
            if value.get("allowed") is not True
        }
        if denied_reviews:
            return crashloop_demo_skipped_evidence_events(
                request_id=request_id,
                target=target,
                reason="Exact SelfSubjectAccessReview denied CrashLoop demo evidence collection.",
                detail=json.dumps(
                    {
                        "deniedReviews": redact_sensitive(denied_reviews),
                        "target": dict(target),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )

        pod_payload = await callbacks.fetch_ocp_json(client, pod_path, user_auth_header)
        events_payload = await callbacks.fetch_ocp_json(client, events_path, user_auth_header)
        container_name = crashloop_container_name(pod_payload or {})
        log_path = (
            f"/api/v1/namespaces/{path_segment(namespace)}/pods/{path_segment(pod_name)}/log"
            f"?previous=true&tailLines=1&limitBytes=1"
        )
        if container_name:
            log_path = f"{log_path}&container={path_segment(container_name)}"
        log_status = await callbacks.fetch_ocp_text_status(client, log_path, user_auth_header)

    container_rows = container_status_rows(pod_payload or {})
    event_summary, event_count = summarize_pod_event_availability(events_payload)
    event_status = "success" if events_payload is not None else "skipped"
    event_missing = "" if event_status == "success" else "Pod-specific events were not returned by Kubernetes API."
    log_probe_status = str(log_status.get("status") or "skipped")
    log_evidence_status = "partial"
    log_missing = (
        "availability checked only; raw logs intentionally withheld"
        if log_probe_status == "success"
        else (
            "previous log endpoint probe did not return log content; "
            f"raw logs intentionally withheld; probeStatus={log_status.get('reason') or 'unknown'}"
        )
    )
    pod_summary = {
        "containers": container_rows,
        "phase": str((pod_payload or {}).get("status", {}).get("phase") or "Unknown")
        if isinstance((pod_payload or {}).get("status"), Mapping)
        else "Unknown",
        "target": dict(target),
    }
    return [
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "eventAvailability": event_summary,
                        "eventCount": event_count,
                        "pod": pod_summary,
                        "rawEventMessages": "omitted",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1200,
            ),
            "evidenceType": "event",
            "id": f"{request_id}-crashloop-event-evidence",
            "missingReason": event_missing,
            "name": "crashloop_event_evidence",
            "sourcePath": events_path,
            "status": event_status,
            "summary": _evidence_summary("CrashLoop Pod Event 증거", event_status),
        },
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "byteCount": log_status.get("byteCount"),
                        "container": container_name,
                        "httpStatus": log_status.get("httpStatus"),
                        "lineCount": log_status.get("lineCount"),
                        "probeLimitBytes": 1,
                        "rawLogDisclosure": False,
                        "target": dict(target),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1200,
            ),
            "evidenceType": "pod_log",
            "id": f"{request_id}-crashloop-log-availability",
            "missingReason": log_missing,
            "name": "crashloop_log_availability",
            "sourcePath": log_path,
            "status": log_evidence_status,
            "summary": _evidence_summary("CrashLoop 이전 로그 가용성", log_evidence_status),
        },
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "pod": pod_summary,
                        "snapshotSource": "pod.status.containerStatuses",
                        "target": dict(target),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1200,
            ),
            "evidenceType": "snapshot",
            "id": f"{request_id}-crashloop-pod-snapshot",
            "missingReason": "" if pod_payload is not None else "Pod payload was not returned by Kubernetes API.",
            "name": "crashloop_pod_snapshot",
            "sourcePath": pod_path,
            "status": "success" if pod_payload is not None else "skipped",
            "summary": _evidence_summary(
                "CrashLoop Pod snapshot 증거",
                "success" if pod_payload is not None else "skipped",
            ),
        },
    ]


def official_namespace_restart_namespace(runtime_tool_plan: Mapping[str, Any] | None) -> str:
    if not isinstance(runtime_tool_plan, Mapping):
        return ""
    if str(runtime_tool_plan.get("task_type") or "") != "pod_restart_rca":
        return ""
    target = runtime_tool_plan.get("target")
    if not isinstance(target, Mapping):
        return ""
    namespace = str(target.get("namespace") or "").strip()
    if not namespace or namespace == "all-accessible-namespaces":
        return ""
    return namespace


def namespace_restart_candidate_rows(
    pods_payload: Mapping[str, Any] | None,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pod in resource_items(pods_payload):
        container_rows = container_status_rows(pod)
        restart_count = sum(int(row.get("restartCount") or 0) for row in container_rows)
        reasons = sorted(
            {
                str(row.get("stateReason") or row.get("lastReason") or "")
                for row in container_rows
                if row.get("stateReason") or row.get("lastReason")
            }
        )
        status = pod.get("status") if isinstance(pod.get("status"), Mapping) else {}
        phase = str(status.get("phase") or "Unknown")
        if restart_count <= 0 and not reasons and phase in {"Running", "Succeeded"}:
            continue
        rows.append(
            {
                "containers": container_rows[:4],
                "name": metadata_name(pod),
                "namespace": metadata_namespace(pod),
                "phase": phase,
                "restartCount": restart_count,
                "stateReasons": reasons,
            }
        )

    return sorted(
        rows,
        key=lambda row: (-int(row.get("restartCount") or 0), str(row.get("name") or "")),
    )[:limit]


def summarize_namespace_restart_events(
    events_payload: Mapping[str, Any] | None,
    *,
    candidate_names: set[str],
) -> dict[str, Any]:
    items = resource_items(events_payload)
    warning_reasons: dict[str, int] = {}
    candidate_hits: dict[str, int] = {}
    involved_kinds: dict[str, int] = {}
    restart_reason_hints = {"BackOff", "Killing", "OOMKilled", "Evicted", "Unhealthy", "Failed"}

    for event in items:
        involved = event.get("involvedObject") if isinstance(event.get("involvedObject"), Mapping) else {}
        involved_name = str(involved.get("name") or "")
        involved_kind = str(involved.get("kind") or "unknown")
        if involved_kind:
            involved_kinds[involved_kind] = involved_kinds.get(involved_kind, 0) + 1
        if candidate_names and involved_name in candidate_names:
            candidate_hits[involved_name] = candidate_hits.get(involved_name, 0) + 1
        if str(event.get("type") or "") != "Warning":
            continue
        reason = str(event.get("reason") or "Warning")
        warning_reasons[reason] = warning_reasons.get(reason, 0) + 1

    restart_hints = {
        reason: count
        for reason, count in warning_reasons.items()
        if reason in restart_reason_hints or "back" in reason.lower() or "kill" in reason.lower()
    }
    return {
        "candidateEventHits": dict(sorted(candidate_hits.items())[:8]),
        "eventCount": len(items),
        "involvedKinds": dict(sorted(involved_kinds.items())[:8]),
        "rawEventMessages": "omitted",
        "restartReasonHints": dict(sorted(restart_hints.items(), key=lambda item: (-item[1], item[0]))[:8]),
        "warningReasons": dict(sorted(warning_reasons.items(), key=lambda item: (-item[1], item[0]))[:8]),
    }


async def fetch_ocp_log_pattern_probe(
    config: ClusterEvidenceRuntimeConfig,
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
) -> dict[str, Any]:
    response = await client.get(
        f"{config.openshift_api_url}{path}",
        headers={
            "Accept": "text/plain",
            "Authorization": authorization,
        },
    )
    if response.status_code >= 400:
        return {
            "byteCount": 0,
            "httpStatus": response.status_code,
            "lineCount": 0,
            "matchedPatternIds": [],
            "patternCounts": {},
            "rawLogDisclosure": False,
            "reason": f"HTTP {response.status_code}",
            "status": "skipped",
        }

    text = response.text or ""
    patterns = {
        "Back-off": r"back[- ]off|crashloopbackoff",
        "Exception": r"exception|traceback|panic|error|failed",
        "OOMKilled": r"oomkilled|out of memory|killed process",
    }
    counts = {
        name: len(re.findall(pattern, text, flags=re.IGNORECASE))
        for name, pattern in patterns.items()
    }
    return {
        "byteCount": len(response.content or b""),
        "httpStatus": response.status_code,
        "lineCount": len(text.splitlines()),
        "matchedPatternIds": [name for name, count in counts.items() if count > 0],
        "patternCounts": counts,
        "rawLogDisclosure": False,
        "reason": "",
        "status": "success",
    }


def official_namespace_restart_skipped_evidence_events(
    *,
    namespace: str,
    request_id: str,
    reason: str,
    detail: str = "",
) -> list[dict[str, Any]]:
    safe_detail = safe_error_text(detail or reason, limit=900)
    target = {"kind": "Namespace", "namespace": namespace}
    return [
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "event",
            "id": f"{request_id}-official-namespace-restart-events",
            "missingReason": reason,
            "name": "official_namespace_restart_event_evidence",
            "sourcePath": "",
            "status": "skipped",
            "summary": "공식 Pod 재시작 namespace Event 조회 결과 수집 생략",
            "target": target,
        },
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "snapshot",
            "id": f"{request_id}-official-namespace-restart-snapshot",
            "missingReason": reason,
            "name": "official_namespace_restart_snapshot",
            "sourcePath": "",
            "status": "skipped",
            "summary": "공식 Pod 재시작 namespace snapshot 조회 결과 수집 생략",
            "target": target,
        },
        {
            "type": "tool_result",
            "detail": safe_detail,
            "evidenceType": "pod_log",
            "id": f"{request_id}-official-namespace-restart-log-patterns",
            "missingReason": reason,
            "name": "official_namespace_restart_log_pattern_probe",
            "sourcePath": "",
            "status": "skipped",
            "summary": "공식 Pod 재시작 log pattern 조회 결과 수집 생략",
            "target": target,
        },
    ]


async def collect_cluster_wide_restart_fallback_events(
    config: ClusterEvidenceRuntimeConfig,
    callbacks: ClusterEvidenceRuntimeCallbacks,
    user_auth_header: str,
    namespace: str,
    request_id: str,
) -> list[dict[str, Any]]:
    if not config.openshift_api_url:
        return []

    async with httpx.AsyncClient(
        verify=config.openshift_api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        pods_payload = await callbacks.fetch_ocp_json(
            client, "/api/v1/pods?limit=200", user_auth_header
        )

    if not pods_payload:
        return []

    candidates = namespace_restart_candidate_rows(pods_payload)
    if not candidates:
        return []

    return [
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "candidatePods": candidates,
                        "originalNamespace": namespace,
                        "reason": f"Namespace `{namespace}` had no restart candidates; broadened to cluster-wide Pod scan.",
                        "snapshotSource": "cluster-wide pods.status.containerStatuses",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1600,
            ),
            "evidenceType": "snapshot",
            "id": f"{request_id}-cluster-wide-restart-fallback",
            "missingReason": "",
            "name": "cluster_wide_restart_fallback",
            "sourcePath": "/api/v1/pods",
            "status": "success",
            "summary": f"`{namespace}`에 재시작 후보가 없어 클러스터 전체로 범위를 넓혀 재조회했습니다.",
        },
    ]


async def collect_official_namespace_restart_evidence_events(
    config: ClusterEvidenceRuntimeConfig,
    callbacks: ClusterEvidenceRuntimeCallbacks,
    user_auth_header: str,
    namespace: str,
    request_id: str,
) -> list[dict[str, Any]]:
    namespace = namespace.strip()
    if not config.openshift_api_url:
        return official_namespace_restart_skipped_evidence_events(
            namespace=namespace,
            request_id=request_id,
            reason="OPENSHIFT_API_URL is not configured",
        )
    if not namespace:
        return official_namespace_restart_skipped_evidence_events(
            namespace=namespace,
            request_id=request_id,
            reason="namespace target is empty",
        )
    if namespace not in config.demo_namespace_allowlist:
        return official_namespace_restart_skipped_evidence_events(
            namespace=namespace,
            request_id=request_id,
            reason=f"Namespace {namespace} is not allowlisted for official Evidence RCA collection.",
            detail=json.dumps(
                {"allowlist": sorted(config.demo_namespace_allowlist), "namespace": namespace},
                ensure_ascii=False,
                sort_keys=True,
            ),
        )

    pods_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods?limit=200"
    events_path = f"/api/v1/namespaces/{path_segment(namespace)}/events?limit=200"
    async with httpx.AsyncClient(
        verify=config.openshift_api_ca_file,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        access_reviews = {
            "eventsList": await callbacks.fetch_resource_access_review(
                client,
                user_auth_header,
                {"namespace": namespace, "resource": "events", "verb": "list"},
            ),
            "podsList": await callbacks.fetch_resource_access_review(
                client,
                user_auth_header,
                {"namespace": namespace, "resource": "pods", "verb": "list"},
            ),
        }
        denied_reviews = {
            key: value
            for key, value in access_reviews.items()
            if value.get("allowed") is not True
        }
        if denied_reviews:
            return official_namespace_restart_skipped_evidence_events(
                namespace=namespace,
                request_id=request_id,
                reason="SelfSubjectAccessReview denied namespace Evidence RCA collection.",
                detail=json.dumps(
                    {"deniedReviews": redact_sensitive(denied_reviews), "namespace": namespace},
                    ensure_ascii=False,
                    sort_keys=True,
                ),
            )

        pods_payload = await callbacks.fetch_ocp_json(client, pods_path, user_auth_header)
        events_payload = await callbacks.fetch_ocp_json(client, events_path, user_auth_header)
        candidates = namespace_restart_candidate_rows(pods_payload)
        top_candidate = candidates[0] if candidates else {}
        container_name = ""
        log_probe: dict[str, Any] = {
            "byteCount": 0,
            "lineCount": 0,
            "matchedPatternIds": [],
            "patternCounts": {},
            "rawLogDisclosure": False,
            "reason": "No restart candidate pod found in namespace snapshot.",
            "status": "skipped",
        }
        log_path = ""
        if top_candidate.get("name"):
            pod_payload = next(
                (
                    pod
                    for pod in resource_items(pods_payload)
                    if metadata_name(pod) == top_candidate.get("name")
                ),
                {},
            )
            container_name = crashloop_container_name(pod_payload)
            log_path = (
                f"/api/v1/namespaces/{path_segment(namespace)}/pods/"
                f"{path_segment(str(top_candidate.get('name') or ''))}/log"
                "?previous=true&tailLines=80&limitBytes=20000"
            )
            if container_name:
                log_path = f"{log_path}&container={path_segment(container_name)}"
            log_probe = await callbacks.fetch_ocp_log_pattern_probe(
                client, log_path, user_auth_header
            )

    fallback_events: list[dict[str, Any]] = []
    if not candidates:
        fallback_events = await callbacks.collect_cluster_wide_restart_fallback_events(
            user_auth_header, namespace, request_id
        )

    candidate_names = {str(candidate.get("name") or "") for candidate in candidates if candidate.get("name")}
    event_summary = summarize_namespace_restart_events(events_payload, candidate_names=candidate_names)
    event_status = "success" if events_payload is not None else "skipped"
    snapshot_status = "success" if pods_payload is not None else "skipped"
    log_status = "partial" if log_probe.get("status") == "success" else "skipped"
    log_missing = (
        "raw logs withheld; pattern probe executed"
        if log_probe.get("status") == "success"
        else str(log_probe.get("reason") or "Pod previous log pattern probe did not run")
    )

    return [
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "namespace": namespace,
                        "summary": event_summary,
                        "targetCandidateNames": sorted(candidate_names),
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1600,
            ),
            "evidenceType": "event",
            "id": f"{request_id}-official-namespace-restart-events",
            "missingReason": "" if event_status == "success" else "Namespace events were not returned by Kubernetes API.",
            "name": "official_namespace_restart_event_evidence",
            "sourcePath": events_path,
            "status": event_status,
            "summary": _evidence_summary("공식 Pod 재시작 namespace Event 증거", event_status),
        },
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "candidatePods": candidates,
                        "namespace": namespace,
                        "snapshotSource": "namespace pods.status.containerStatuses",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1600,
            ),
            "evidenceType": "snapshot",
            "id": f"{request_id}-official-namespace-restart-snapshot",
            "missingReason": "" if snapshot_status == "success" else "Namespace pods were not returned by Kubernetes API.",
            "name": "official_namespace_restart_snapshot",
            "sourcePath": pods_path,
            "status": snapshot_status,
            "summary": _evidence_summary("공식 Pod 재시작 namespace snapshot 증거", snapshot_status),
        },
        {
            "type": "tool_result",
            "detail": safe_error_text(
                json.dumps(
                    {
                        "container": container_name,
                        "namespace": namespace,
                        "probe": log_probe,
                        "rawLogDisclosure": False,
                        "targetPod": top_candidate.get("name") or "",
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                limit=1600,
            ),
            "evidenceType": "pod_log",
            "id": f"{request_id}-official-namespace-restart-log-patterns",
            "lineCount": log_probe.get("lineCount"),
            "matchedPatternIds": log_probe.get("matchedPatternIds"),
            "missingReason": log_missing,
            "name": "official_namespace_restart_log_pattern_probe",
            "patternCounts": log_probe.get("patternCounts"),
            "rawLogDisclosure": False,
            "sourcePath": log_path,
            "status": log_status,
            "summary": _evidence_summary("공식 Pod 재시작 log pattern 증거", log_status),
        },
        *fallback_events,
    ]
