from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
from urllib.parse import unquote

from .security import redact_sensitive

K8S_RESOURCE_KIND_BY_ROUTE_SEGMENT = {
    "buildconfigs": "BuildConfig",
    "configmaps": "ConfigMap",
    "cronjobs": "CronJob",
    "daemonsets": "DaemonSet",
    "deployments": "Deployment",
    "deploymentconfigs": "DeploymentConfig",
    "events": "Event",
    "horizontalpodautoscalers": "HorizontalPodAutoscaler",
    "hpas": "HorizontalPodAutoscaler",
    "ingresses": "Ingress",
    "jobs": "Job",
    "namespaces": "Namespace",
    "nodes": "Node",
    "pods": "Pod",
    "projects": "Project",
    "replicasets": "ReplicaSet",
    "replicationcontrollers": "ReplicationController",
    "routes": "Route",
    "secrets": "Secret",
    "services": "Service",
    "statefulsets": "StatefulSet",
}
PAGE_CONTEXT_ALLOWED_KEYS = {
    "aiopsDemoCycle",
    "aiopsExecutionMode",
    "clusterScope",
    "href",
    "namespace",
    "pathname",
    "perspective",
    "resourceKind",
    "resourceList",
    "resourceName",
    "route",
}
AIOPS_DEMO_CYCLE_ALLOWED_KEYS = {
    "candidateId",
    "candidateStatusLabel",
    "findingId",
    "findingTitle",
    "scenarioId",
    "selectedAt",
    "source",
}
AIOPS_DEMO_CYCLE_TARGET_ALLOWED_KEYS = {
    "kind",
    "name",
    "namespace",
}


class PageContextRequest(Protocol):
    pageContext: Mapping[str, Any] | None


def decode_path_segment(segment: str | None) -> str | None:
    if not segment:
        return None

    try:
        return unquote(segment)
    except ValueError:
        return segment


def normalize_aiops_demo_cycle_context(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}

    normalized = {
        key: value.get(key)
        for key in AIOPS_DEMO_CYCLE_ALLOWED_KEYS
        if value.get(key) is not None and value.get(key) != ""
    }
    target = value.get("target")
    if isinstance(target, Mapping):
        normalized_target = {
            key: target.get(key)
            for key in AIOPS_DEMO_CYCLE_TARGET_ALLOWED_KEYS
            if target.get(key) is not None and target.get(key) != ""
        }
        if normalized_target:
            normalized["target"] = normalized_target

    return normalized


def normalize_console_page_context(page_context: Mapping[str, Any] | None) -> dict[str, Any]:
    raw_context = page_context or {}
    normalized: dict[str, Any] = {}
    for key, value in raw_context.items():
        if key == "aiopsDemoCycle":
            demo_cycle = normalize_aiops_demo_cycle_context(value)
            if demo_cycle:
                normalized[key] = demo_cycle
            continue
        if key in PAGE_CONTEXT_ALLOWED_KEYS and value is not None and value != "":
            normalized[key] = value
    pathname = str(normalized.get("pathname") or "")
    segments = [segment for segment in pathname.split("/") if segment]

    route = decode_path_segment(segments[0] if segments else None)
    if route and "route" not in normalized:
        normalized["route"] = route

    if "namespace" not in normalized and "ns" in segments:
        ns_index = segments.index("ns")
        namespace = decode_path_segment(segments[ns_index + 1] if len(segments) > ns_index + 1 else None)
        if namespace:
            normalized["namespace"] = namespace

    if segments[:2] == ["k8s", "cluster"]:
        normalized.setdefault("clusterScope", True)

    ns_index = segments.index("ns") if "ns" in segments else -1
    resource_segment_index = ns_index + 2 if ns_index >= 0 else -1
    if segments[:2] == ["k8s", "cluster"]:
        resource_segment_index = 2

    resource_list = decode_path_segment(
        segments[resource_segment_index] if len(segments) > resource_segment_index >= 0 else None
    )
    if resource_list:
        normalized.setdefault("resourceList", resource_list)
        resource_kind = K8S_RESOURCE_KIND_BY_ROUTE_SEGMENT.get(resource_list.lower())
        if resource_kind:
            normalized.setdefault("resourceKind", resource_kind)
            resource_name = decode_path_segment(
                segments[resource_segment_index + 1]
                if len(segments) > resource_segment_index + 1
                else None
            )
            if resource_name:
                normalized.setdefault("resourceName", resource_name)

    if route == "catalog":
        normalized.setdefault("perspective", "developer")
        normalized.setdefault("resourceKind", "Catalog")
    elif route == "topology":
        normalized.setdefault("perspective", "developer")
    elif route == "monitoring":
        normalized.setdefault("perspective", "administrator")

    return redact_sensitive(normalized)


def page_context_namespace(req: PageContextRequest) -> str:
    context = normalize_console_page_context(req.pageContext)
    namespace = context.get("namespace")
    return str(namespace) if namespace else ""


def page_context_resource_name(req: PageContextRequest, expected_kind: str = "Deployment") -> str:
    context = normalize_console_page_context(req.pageContext)
    kind = str(context.get("resourceKind") or "")
    name = context.get("resourceName")
    if kind == expected_kind and name:
        return str(name)
    return ""


def page_context_resource_kind(req: PageContextRequest) -> str:
    context = normalize_console_page_context(req.pageContext)
    return str(context.get("resourceKind") or "").strip()


def page_context_is_pod_workload(req: PageContextRequest) -> bool:
    return page_context_resource_kind(req).lower() in {
        "pod",
        "deployment",
        "replicaset",
        "statefulset",
        "daemonset",
        "deploymentconfig",
    }


def page_context_aiops_execution_mode(req: PageContextRequest) -> str:
    context = normalize_console_page_context(req.pageContext)
    mode = str(context.get("aiopsExecutionMode") or "read-only").strip().lower()
    if mode in {"read-only", "read_only", "readonly", "evidence-check", "evidence_check", "점검", "조회"}:
        return "evidence-check"
    if mode in {"unrestricted", "dev-unrestricted", "experimental", "실험", "무제한"}:
        return "unrestricted"
    if mode in {"execute", "execution", "execution-enabled", "enabled"}:
        return "execute"
    return "evidence-check"
