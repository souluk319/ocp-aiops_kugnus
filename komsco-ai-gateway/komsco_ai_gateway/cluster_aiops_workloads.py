import re
from collections.abc import Mapping
from typing import Any

from .cluster_common import resource_items

AIOPS_WORKLOAD_RE = re.compile(
    r"(aiops|komsco[-_.]?ai|cywell[-_.]?aiops|openshift[-_.]?lightspeed|"
    r"lightspeed|trustyai|rhoai|open[-_.]?data[-_.]?hub|\bodh\b|model[-_.]?registry|"
    r"nvidia|gpu|dcgm|\bmig\b|device[-_.]?plugin)",
    re.IGNORECASE,
)


def build_aiops_workload_summary(
    *,
    daemonsets_payload: Mapping[str, Any] | None,
    deployments_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    deployments = [
        summarize_aiops_workload(item, kind="Deployment")
        for item in resource_items(deployments_payload)
        if matches_aiops_workload(item)
    ]
    daemonsets = [
        summarize_aiops_workload(item, kind="DaemonSet")
        for item in resource_items(daemonsets_payload)
        if matches_aiops_workload(item)
    ]
    workloads = deployments + daemonsets
    return {
        "daemonsets": daemonsets,
        "deployments": deployments,
        "issues": len([workload for workload in workloads if workload.get("severity") != "ok"]),
        "namespaces": sorted({str(workload.get("namespace")) for workload in workloads})[:12],
        "total": len(workloads),
    }


def summarize_aiops_workload(resource: Mapping[str, Any], *, kind: str) -> dict[str, Any]:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    spec = resource.get("spec", {}) if isinstance(resource.get("spec"), Mapping) else {}
    status = resource.get("status", {}) if isinstance(resource.get("status"), Mapping) else {}
    desired, ready, available, updated, unavailable = workload_counts(kind, spec, status)
    generation = int(metadata.get("generation") or 0)
    observed_generation = int(status.get("observedGeneration") or generation or 0)
    rollout_lagging = bool(generation and observed_generation < generation)
    has_issue = unavailable > 0 or ready < desired or rollout_lagging
    if desired > 0 and ready == 0:
        severity = "risk"
    elif has_issue:
        severity = "warn"
    else:
        severity = "ok"
    return {
        "available": available,
        "createdAt": metadata.get("creationTimestamp"),
        "desired": desired,
        "detail": f"Ready {ready}/{desired} · Available {available} · Updated {updated}"
        + (" · Rollout lagging" if rollout_lagging else ""),
        "kind": kind,
        "name": str(metadata.get("name") or f"unknown-{kind.lower()}"),
        "namespace": str(metadata.get("namespace") or "default"),
        "ready": ready,
        "severity": severity,
        "updated": updated,
    }


def workload_counts(
    kind: str,
    spec: Mapping[str, Any],
    status: Mapping[str, Any],
) -> tuple[int, int, int, int, int]:
    if kind == "DaemonSet":
        desired = int(status.get("desiredNumberScheduled") or 0)
        ready = int(status.get("numberReady") or 0)
        available = int(status.get("numberAvailable") or 0)
        updated = int(status.get("updatedNumberScheduled") or 0)
        unavailable = int(status.get("numberUnavailable") or max(desired - ready, 0))
        return desired, ready, available, updated, unavailable
    desired = int(spec.get("replicas") or status.get("replicas") or 0)
    ready = int(status.get("readyReplicas") or 0)
    available = int(status.get("availableReplicas") or 0)
    updated = int(status.get("updatedReplicas") or 0)
    unavailable = int(status.get("unavailableReplicas") or max(desired - ready, 0))
    return desired, ready, available, updated, unavailable


def matches_aiops_workload(resource: Mapping[str, Any]) -> bool:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    spec = resource.get("spec", {}) if isinstance(resource.get("spec"), Mapping) else {}
    template = spec.get("template", {}) if isinstance(spec.get("template"), Mapping) else {}
    template_metadata = template.get("metadata", {}) if isinstance(template.get("metadata"), Mapping) else {}
    labels = metadata.get("labels", {}) if isinstance(metadata.get("labels"), Mapping) else {}
    template_labels = (
        template_metadata.get("labels", {})
        if isinstance(template_metadata.get("labels"), Mapping)
        else {}
    )
    text = " ".join(
        [
            str(metadata.get("namespace") or ""),
            str(metadata.get("name") or ""),
            " ".join(f"{key}={value}" for key, value in labels.items()),
            " ".join(f"{key}={value}" for key, value in template_labels.items()),
        ]
    )
    return bool(AIOPS_WORKLOAD_RE.search(text))
