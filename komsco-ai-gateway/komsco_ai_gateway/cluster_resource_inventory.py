from collections.abc import Mapping
from typing import Any

from .cluster_common import resource_items
from .cluster_resource_summary import (
    resource_summary_item,
    summarize_daemonset_resources,
    summarize_pod_resources,
    summarize_replicated_resources,
    workload_severity,
)


def summarize_route_resources(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    routes = resource_items(payload)
    admitted = issues = 0
    for route in routes:
        ingresses = (
            route.get("status", {}) if isinstance(route.get("status"), Mapping) else {}
        ).get("ingress")
        route_admitted = route_has_admitted_ingress(ingresses)
        admitted += 1 if route_admitted else 0
        issues += 0 if route_admitted else 1
    return resource_summary_item(
        id="routes",
        name="Routes",
        kind="Route",
        total=len(routes),
        ready=admitted,
        issues=issues,
        severity=workload_severity(issues, len(routes)),
        detail=f"Admitted {admitted}/{len(routes)} · Issues {issues}",
    )


def route_has_admitted_ingress(ingresses: Any) -> bool:
    if not isinstance(ingresses, list):
        return False
    return any(
        isinstance(ingress, Mapping)
        and isinstance(ingress.get("conditions"), list)
        and any(
            isinstance(condition, Mapping)
            and condition.get("type") == "Admitted"
            and condition.get("status") == "True"
            for condition in ingress.get("conditions", [])
        )
        for ingress in ingresses
    )


def summarize_phase_count(
    payload: Mapping[str, Any] | None,
    *,
    id: str,
    kind: str,
    name: str,
    ok_phase: str,
    label: str,
) -> dict[str, Any]:
    resources = resource_items(payload)
    ready = sum(1 for item in resources if resource_phase(item) == ok_phase)
    terminating = sum(1 for item in resources if resource_phase(item) == "Terminating")
    suffix = f" · Terminating {terminating}" if id == "namespaces" else ""
    issues = len(resources) - ready
    detail = (
        f"{label} {ready}/{len(resources)}{suffix}"
        if id == "namespaces"
        else f"{label} {ready}/{len(resources)}{suffix} · Issues {issues}"
    )
    return resource_summary_item(
        id=id,
        name=name,
        kind=kind,
        total=len(resources),
        ready=ready,
        issues=issues,
        severity=workload_severity(issues, len(resources)),
        detail=detail,
    )


def resource_phase(resource: Mapping[str, Any]) -> str:
    status = resource.get("status", {}) if isinstance(resource.get("status"), Mapping) else {}
    return str(status.get("phase") or "Unknown")


def summarize_simple_resource_count(
    payload: Mapping[str, Any] | None,
    *,
    id: str,
    kind: str,
    name: str,
) -> dict[str, Any]:
    total = len(resource_items(payload))
    return resource_summary_item(
        id=id,
        name=name,
        kind=kind,
        total=total,
        ready=total,
        issues=0,
        severity="ok",
        detail=f"Total {total}",
    )


def build_resource_summary(**payloads: Mapping[str, Any] | None) -> dict[str, Any]:
    items = [
        summarize_pod_resources(payloads.get("pods_payload")),
        summarize_replicated_resources(
            payloads.get("deployments_payload"),
            id="deployments",
            kind="Deployment",
            name="Deployments",
        ),
        summarize_replicated_resources(
            payloads.get("replicasets_payload"),
            id="replicasets",
            kind="ReplicaSet",
            name="ReplicaSets",
        ),
        summarize_daemonset_resources(payloads.get("daemonsets_payload")),
        summarize_replicated_resources(
            payloads.get("statefulsets_payload"),
            id="statefulsets",
            kind="StatefulSet",
            name="StatefulSets",
        ),
        summarize_simple_resource_count(
            payloads.get("services_payload"),
            id="services",
            kind="Service",
            name="Services",
        ),
        summarize_route_resources(payloads.get("routes_payload")),
        summarize_phase_count(
            payloads.get("pvcs_payload"),
            id="persistentvolumeclaims",
            kind="PersistentVolumeClaim",
            name="PVCs",
            ok_phase="Bound",
            label="Bound",
        ),
        summarize_phase_count(
            payloads.get("namespaces_payload"),
            id="namespaces",
            kind="Namespace",
            name="Namespaces",
            ok_phase="Active",
            label="Active",
        ),
    ]
    return {
        "total": sum(int(item.get("total") or 0) for item in items),
        "issues": sum(int(item.get("issues") or 0) for item in items),
        "items": items,
    }
