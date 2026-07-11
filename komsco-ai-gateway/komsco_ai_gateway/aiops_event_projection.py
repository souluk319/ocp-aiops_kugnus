from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

from .cluster_common import resource_items
from .cluster_evidence import last_termination_summary, state_summary
from .pod_counting import (
    pod_is_fully_ready,
    pod_is_terminating,
    pod_ready_numbers,
    pod_ready_summary,
    pod_restart_total,
)
from .security import now_rfc3339


def compact_event_detail(value: Any, *, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}..."


def parse_kubernetes_timestamp(value: str) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def aiops_event_timestamp(event: Mapping[str, Any]) -> str:
    for key in ("eventTime", "lastTimestamp", "firstTimestamp"):
        value = event.get(key)
        if isinstance(value, str) and value:
            return value

    metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), Mapping) else {}
    value = metadata.get("creationTimestamp")
    return str(value or now_rfc3339())


def aiops_event_involved_target(event: Mapping[str, Any]) -> tuple[str, str, str, str]:
    metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), Mapping) else {}
    involved = event.get("involvedObject", {})
    involved = involved if isinstance(involved, Mapping) else {}
    namespace = str(involved.get("namespace") or metadata.get("namespace") or "")
    kind = str(involved.get("kind") or "Resource")
    name = str(involved.get("name") or metadata.get("name") or "unknown")
    target = f"{kind}/{name}" if not namespace else f"{namespace}/{kind}/{name}"
    return namespace, kind, name, target


def aiops_event_severity(reason: str, event_type: str, message: str = "") -> str:
    text = f"{reason} {event_type} {message}".lower()
    risk_tokens = (
        "crashloopbackoff",
        "errimagepull",
        "failed",
        "failedmount",
        "failedscheduling",
        "imagepullbackoff",
        "oomkilled",
        "unhealthy",
    )
    warn_tokens = ("backoff", "notready", "unavailable", "warning")
    if any(token in text for token in risk_tokens):
        return "risk"
    if str(event_type).lower() == "warning" or any(token in text for token in warn_tokens):
        return "warn"
    return "ok"


def build_kubernetes_event_items(
    events_payload: Mapping[str, Any] | None,
    *,
    limit: int = 40,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    ok_budget = max(2, limit // 10)
    ok_count = 0
    for event in resource_items(events_payload):
        metadata = event.get("metadata", {}) if isinstance(event.get("metadata"), Mapping) else {}
        reason = str(event.get("reason") or "Event")
        event_type = str(event.get("type") or "Normal")
        message = compact_event_detail(event.get("message"))
        namespace, kind, name, target = aiops_event_involved_target(event)
        severity = aiops_event_severity(reason, event_type, message)
        if severity == "ok":
            if ok_count >= ok_budget:
                continue
            ok_count += 1

        event_id = str(
            metadata.get("uid")
            or f"{namespace}-{kind}-{name}-{reason}-{aiops_event_timestamp(event)}"
        )
        items.append(
            {
                "category": "event",
                "detail": message or f"{event_type} event observed.",
                "id": f"k8s-event-{event_id}",
                "namespace": namespace,
                "severity": severity,
                "source": "Kubernetes Event",
                "target": target,
                "time": aiops_event_timestamp(event),
                "title": f"{reason} · {kind}/{name}",
            }
        )

    items.sort(key=lambda item: str(item.get("time") or ""), reverse=True)
    return items[:limit]


def pod_container_signal_summary(pod: Mapping[str, Any]) -> str:
    status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
    statuses = status.get("containerStatuses")
    if not isinstance(statuses, list):
        return "-"

    signals: list[str] = []
    for container_status in statuses:
        if not isinstance(container_status, Mapping):
            continue
        name = str(container_status.get("name") or "container")
        state = state_summary(container_status)
        last_state, _finished_at = last_termination_summary(container_status)
        restarts = int(container_status.get("restartCount") or 0)
        if state == "running" and restarts < 3 and last_state == "-":
            continue
        suffix = f"{name} {state} restart={restarts}"
        if last_state != "-":
            suffix = f"{suffix} last={last_state}"
        signals.append(suffix)

    return "; ".join(signals[:4]) if signals else "-"


def pod_has_recent_restart(pod: Mapping[str, Any], *, hours: int = 6) -> bool:
    status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
    statuses = status.get("containerStatuses")
    if not isinstance(statuses, list):
        return False

    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    for container_status in statuses:
        if not isinstance(container_status, Mapping):
            continue
        if int(container_status.get("restartCount") or 0) <= 0:
            continue
        _last_state, finished_at = last_termination_summary(container_status)
        finished_at_dt = parse_kubernetes_timestamp(finished_at)
        if finished_at_dt is not None and finished_at_dt >= cutoff:
            return True
    return False


def is_openshift_build_pod(pod: Mapping[str, Any]) -> bool:
    metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
    labels = metadata.get("labels", {}) if isinstance(metadata.get("labels"), Mapping) else {}
    owner_refs = metadata.get("ownerReferences", [])
    if labels.get("openshift.io/build.name") or labels.get("openshift.io/build-config.name"):
        return True
    if labels.get("buildconfig") and str(metadata.get("name") or "").endswith("-build"):
        return True
    if isinstance(owner_refs, list):
        return any(
            isinstance(ref, Mapping) and str(ref.get("kind") or "").lower() == "build"
            for ref in owner_refs
        )
    return False


def build_problem_pod_event_items(
    pods_payload: Mapping[str, Any] | None,
    *,
    limit: int = 30,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    observed_at = now_rfc3339()
    for pod in resource_items(pods_payload):
        metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        name = str(metadata.get("name") or "")
        namespace = str(metadata.get("namespace") or "")
        if is_openshift_build_pod(pod):
            continue
        phase = str(status.get("phase") or "Unknown")
        restarts = pod_restart_total(pod)
        ready = pod_ready_summary(pod)
        terminating = pod_is_terminating(pod)
        recent_restart = pod_has_recent_restart(pod)
        problem = (
            terminating
            or phase not in {"Running", "Succeeded"}
            or (phase == "Running" and not pod_is_fully_ready(pod))
            or (phase != "Succeeded" and restarts >= 3 and recent_restart)
        )
        if not problem:
            continue

        created_at = str(metadata.get("creationTimestamp") or now_rfc3339())
        created_at_dt = parse_kubernetes_timestamp(created_at)
        if (
            phase in {"Failed", "Succeeded"}
            and created_at_dt is not None
            and datetime.now(UTC) - created_at_dt > timedelta(hours=24)
        ):
            continue

        container_signal = pod_container_signal_summary(pod)
        ready_count, ready_total = pod_ready_numbers(pod)
        signal_text = container_signal.lower()
        severity = (
            "risk"
            if (
                phase in {"Failed", "Unknown"}
                or (phase == "Running" and ready_total > 0 and ready_count == 0 and restarts > 0)
                or any(
                    token in signal_text
                    for token in ("crashloopbackoff", "errimagepull", "imagepullbackoff", "oomkilled")
                )
            )
            else "warn"
        )
        if (phase == "Pending" or terminating) and severity != "risk":
            severity = "warn"
        target = f"{namespace}/Pod/{name}" if namespace else f"Pod/{name}"
        detail_parts = [
            f"phase={phase}",
            f"ready={ready}",
            f"restart={restarts}",
            f"created={created_at}",
            "terminating=true" if terminating else "",
            container_signal,
        ]
        items.append(
            {
                "category": "pod",
                "detail": compact_event_detail(
                    " · ".join(part for part in detail_parts if part and part != "-")
                ),
                "id": f"pod-signal-{namespace}-{name}",
                "namespace": namespace,
                "severity": severity,
                "source": "Pod status",
                "target": target,
                "time": observed_at,
                "title": f"Pod 상태 이상 · {name}",
            }
        )

    severity_order = {"risk": 2, "warn": 1, "ok": 0}
    items.sort(
        key=lambda item: (
            severity_order.get(str(item.get("severity") or "ok"), 0),
            str(item.get("time") or ""),
        ),
        reverse=True,
    )
    return items[:limit]
