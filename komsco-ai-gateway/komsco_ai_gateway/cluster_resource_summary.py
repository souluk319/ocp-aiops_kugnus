from collections.abc import Mapping
from typing import Any

from .cluster_common import (
    pod_is_fully_ready,
    pod_is_terminating,
    pod_restart_total,
    resource_items,
)

def resource_summary_item(
    *,
    detail: str,
    id: str,
    issues: int,
    kind: str,
    name: str,
    ready: int | str,
    severity: str,
    total: int,
) -> dict[str, Any]:
    score = f"{ready}/{total}" if isinstance(ready, int) else str(ready)
    return {
        "id": id,
        "name": name,
        "kind": kind,
        "total": total,
        "ready": ready,
        "issues": issues,
        "score": score,
        "detail": detail,
        "severity": severity,
    }


def workload_severity(issues: int, total: int) -> str:
    if issues <= 0:
        return "ok"
    if total > 0 and issues == total:
        return "risk"
    return "warn"


def summarize_pod_resources(pods_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    pods = resource_items(pods_payload)
    phase_counts: dict[str, int] = {}
    running = ready = succeeded = failed = terminating = restarts = issues = 0
    for pod in pods:
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        phase = str(status.get("phase") or "Unknown")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1
        running += 1 if phase == "Running" else 0
        succeeded += 1 if phase == "Succeeded" else 0
        failed += 1 if phase == "Failed" else 0
        terminating += 1 if pod_is_terminating(pod) else 0
        restarts += pod_restart_total(pod)
        pod_ready = pod_is_fully_ready(pod)
        ready += 1 if pod_ready else 0
        issues += 1 if phase not in {"Running", "Succeeded"} or (phase == "Running" and not pod_ready) else 0

    issue_count = issues + terminating
    return resource_summary_item(
        id="pods",
        name="Pods",
        kind="Pod",
        total=len(pods),
        ready=ready,
        issues=issue_count,
        severity="risk" if failed else workload_severity(issue_count, len(pods)),
        detail=(
            f"Running {running} · Ready {ready} · Pending {phase_counts.get('Pending', 0)} "
            f"· Failed {failed} · Succeeded {succeeded} · Restarts {restarts}"
        ),
    )


def summarize_replicated_resources(
    payload: Mapping[str, Any] | None,
    *,
    id: str,
    kind: str,
    name: str,
) -> dict[str, Any]:
    resources = resource_items(payload)
    desired = ready = available = updated = healthy = issues = 0
    for resource in resources:
        spec = resource.get("spec", {}) if isinstance(resource.get("spec"), Mapping) else {}
        status = resource.get("status", {}) if isinstance(resource.get("status"), Mapping) else {}
        resource_desired = int(spec.get("replicas") or status.get("replicas") or 0)
        resource_ready = int(status.get("readyReplicas") or 0)
        desired += resource_desired
        ready += resource_ready
        available += int(status.get("availableReplicas") or 0)
        updated += int(status.get("updatedReplicas") or 0)
        generation = int(
            (
                resource.get("metadata", {})
                if isinstance(resource.get("metadata"), Mapping)
                else {}
            ).get("generation")
            or 0
        )
        observed_generation = int(status.get("observedGeneration") or generation or 0)
        unavailable = int(status.get("unavailableReplicas") or 0) > 0
        if unavailable or resource_ready < resource_desired or observed_generation < generation:
            issues += 1
        else:
            healthy += 1
    return resource_summary_item(
        id=id,
        name=name,
        kind=kind,
        total=len(resources),
        ready=healthy,
        issues=issues,
        severity=workload_severity(issues, len(resources)),
        detail=(
            f"Ready replicas {ready}/{desired} · Available {available} "
            f"· Updated {updated} · Issues {issues}"
        ),
    )


def summarize_daemonset_resources(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    daemonsets = resource_items(payload)
    desired = ready = available = healthy = issues = 0
    for daemonset in daemonsets:
        status = daemonset.get("status", {}) if isinstance(daemonset.get("status"), Mapping) else {}
        resource_desired = int(status.get("desiredNumberScheduled") or 0)
        resource_ready = int(status.get("numberReady") or 0)
        desired += resource_desired
        ready += resource_ready
        available += int(status.get("numberAvailable") or 0)
        if int(status.get("numberUnavailable") or 0) > 0 or resource_ready < resource_desired:
            issues += 1
        else:
            healthy += 1
    return resource_summary_item(
        id="daemonsets",
        name="DaemonSets",
        kind="DaemonSet",
        total=len(daemonsets),
        ready=healthy,
        issues=issues,
        severity=workload_severity(issues, len(daemonsets)),
        detail=f"Ready pods {ready}/{desired} · Available {available} · Issues {issues}",
    )
