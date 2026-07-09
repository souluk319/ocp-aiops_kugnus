import os
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from .cluster_common import condition_status, find_condition, resource_items
from .cluster_nodes import node_metric_map, summarize_node
from .cluster_aiops_workloads import build_aiops_workload_summary
from .cluster_resource_inventory import build_resource_summary


def summarize_operator(operator: Mapping[str, Any]) -> dict[str, Any]:
    metadata = operator.get("metadata", {}) if isinstance(operator.get("metadata"), Mapping) else {}
    available = condition_status(operator, "Available") == "True"
    degraded = condition_status(operator, "Degraded") == "True"
    progressing = condition_status(operator, "Progressing") == "True"
    upgradeable = condition_status(operator, "Upgradeable")
    issue_condition = operator_issue_condition(
        operator,
        degraded=degraded,
        available=available,
        progressing=progressing,
        upgradeable=upgradeable,
    )
    return {
        "name": str(metadata.get("name") or "unknown-operator"),
        "available": available,
        "degraded": degraded,
        "progressing": progressing,
        "upgradeable": upgradeable,
        "reason": issue_condition.get("reason") if issue_condition else None,
        "message": issue_condition.get("message") if issue_condition else None,
    }


def operator_issue_condition(
    operator: Mapping[str, Any],
    *,
    degraded: bool,
    available: bool,
    progressing: bool,
    upgradeable: str | None,
) -> Mapping[str, Any] | None:
    if degraded:
        return find_condition(operator, "Degraded")
    if not available:
        return find_condition(operator, "Available")
    if progressing:
        return find_condition(operator, "Progressing")
    if upgradeable == "False":
        return find_condition(operator, "Upgradeable")
    return None


def compute_health_score(
    nodes_summary: Mapping[str, Any],
    operators_summary: Mapping[str, Any],
    version_summary: Mapping[str, Any],
) -> int:
    score = 100
    score -= min(40, int(nodes_summary.get("notReady", 0)) * 25)
    score -= min(30, int(nodes_summary.get("pressureCount", 0)) * 10)
    score -= min(35, int(operators_summary.get("degraded", 0)) * 12)
    score -= min(35, int(operators_summary.get("unavailable", 0)) * 15)
    score -= min(15, int(operators_summary.get("progressing", 0)) * 5)
    score -= 8 if version_summary.get("upgradeable") is False else 0
    return max(0, min(100, score))


def build_cluster_summary(
    nodes_payload: Mapping[str, Any],
    node_metrics_payload: Mapping[str, Any] | None,
    cluster_version_payload: Mapping[str, Any] | None,
    cluster_operators_payload: Mapping[str, Any] | None,
    pods_payload: Mapping[str, Any] | None = None,
    deployments_payload: Mapping[str, Any] | None = None,
    replicasets_payload: Mapping[str, Any] | None = None,
    daemonsets_payload: Mapping[str, Any] | None = None,
    statefulsets_payload: Mapping[str, Any] | None = None,
    services_payload: Mapping[str, Any] | None = None,
    routes_payload: Mapping[str, Any] | None = None,
    pvcs_payload: Mapping[str, Any] | None = None,
    namespaces_payload: Mapping[str, Any] | None = None,
    *,
    api_url: str | None = None,
) -> dict[str, Any]:
    metrics_by_name = node_metric_map(node_metrics_payload)
    nodes = [
        summarize_node(
            node,
            metrics_by_name.get(
                str(
                    (
                        node.get("metadata", {})
                        if isinstance(node.get("metadata"), Mapping)
                        else {}
                    ).get("name")
                )
            ),
        )
        for node in resource_items(nodes_payload)
    ]
    ready_nodes = [node for node in nodes if node["ready"]]
    pressure_nodes = [
        node for node in nodes if any(bool(value) for value in node.get("pressures", {}).values())
    ]
    nodes_summary = {
        "total": len(nodes),
        "ready": len(ready_nodes),
        "notReady": len(nodes) - len(ready_nodes),
        "pressureCount": len(pressure_nodes),
        "items": nodes,
        "metricsAvailable": bool(metrics_by_name),
    }

    operators = [summarize_operator(operator) for operator in resource_items(cluster_operators_payload)]
    operator_issues = [
        operator
        for operator in operators
        if (
            not operator["available"]
            or operator["degraded"]
            or operator["progressing"]
            or operator.get("upgradeable") == "False"
        )
    ]
    operators_summary = {
        "total": len(operators),
        "available": len([operator for operator in operators if operator["available"]]),
        "degraded": len([operator for operator in operators if operator["degraded"]]),
        "progressing": len([operator for operator in operators if operator["progressing"]]),
        "unavailable": len([operator for operator in operators if not operator["available"]]),
        "issues": operator_issues[:8],
    }

    cluster_version_status = (
        cluster_version_payload.get("status", {})
        if isinstance(cluster_version_payload, Mapping)
        else {}
    )
    desired = (
        cluster_version_status.get("desired", {})
        if isinstance(cluster_version_status.get("desired"), Mapping)
        else {}
    )
    available_updates = cluster_version_status.get("availableUpdates")
    conditional_updates = cluster_version_status.get("conditionalUpdates")
    upgradeable_condition = (
        find_condition(cluster_version_payload or {}, "Upgradeable")
        if isinstance(cluster_version_payload, Mapping)
        else None
    )
    version_summary = {
        "version": desired.get("version"),
        "channel": cluster_version_status.get("channel"),
        "updateAvailable": isinstance(available_updates, list) and len(available_updates) > 0,
        "availableUpdates": available_update_versions(available_updates),
        "conditionalUpdates": conditional_update_versions(conditional_updates),
        "upgradeable": upgradeable_condition.get("status") != "False"
        if upgradeable_condition
        else None,
        "upgradeableReason": upgradeable_condition.get("reason") if upgradeable_condition else None,
        "upgradeableMessage": upgradeable_condition.get("message") if upgradeable_condition else None,
    }
    resources_summary = build_resource_summary(
        daemonsets_payload=daemonsets_payload,
        deployments_payload=deployments_payload,
        namespaces_payload=namespaces_payload,
        pods_payload=pods_payload,
        pvcs_payload=pvcs_payload,
        replicasets_payload=replicasets_payload,
        routes_payload=routes_payload,
        services_payload=services_payload,
        statefulsets_payload=statefulsets_payload,
    )
    aiops_workloads_summary = build_aiops_workload_summary(
        daemonsets_payload=daemonsets_payload,
        deployments_payload=deployments_payload,
    )
    return {
        "updatedAt": datetime.now(UTC).isoformat(),
        "apiUrl": api_url if api_url is not None else os.getenv("OPENSHIFT_API_URL", "").rstrip("/"),
        "healthScore": compute_health_score(nodes_summary, operators_summary, version_summary),
        "nodes": nodes_summary,
        "operators": operators_summary,
        "resources": resources_summary,
        "aiopsWorkloads": aiops_workloads_summary,
        "version": version_summary,
    }


def available_update_versions(updates: Any) -> list[str]:
    if not isinstance(updates, list):
        return []
    return [
        str(update.get("version"))
        for update in updates
        if isinstance(update, Mapping) and update.get("version")
    ][:5]


def conditional_update_versions(updates: Any) -> list[str]:
    if not isinstance(updates, list):
        return []
    return [
        str(update.get("release", {}).get("version"))
        for update in updates
        if (
            isinstance(update, Mapping)
            and isinstance(update.get("release"), Mapping)
            and update.get("release", {}).get("version")
        )
    ][:5]
