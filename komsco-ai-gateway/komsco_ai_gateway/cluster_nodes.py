from collections.abc import Mapping
from typing import Any

from .cluster_common import condition_status, resource_items


def node_roles(node: Mapping[str, Any]) -> list[str]:
    metadata = node.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return []
    labels = metadata.get("labels", {})
    if not isinstance(labels, Mapping):
        return []
    prefix = "node-role.kubernetes.io/"
    roles = [(key[len(prefix) :] or "worker") for key in labels if str(key).startswith(prefix)]
    return sorted(roles) or ["worker"]


def node_metric_map(node_metrics_payload: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    return {
        name: item
        for item in resource_items(node_metrics_payload)
        if isinstance((name := item.get("metadata", {}).get("name")), str)
    }


def summarize_node(node: Mapping[str, Any], metrics: Mapping[str, Any] | None) -> dict[str, Any]:
    metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), Mapping) else {}
    status = node.get("status", {}) if isinstance(node.get("status"), Mapping) else {}
    node_info = status.get("nodeInfo", {}) if isinstance(status.get("nodeInfo"), Mapping) else {}
    usage = metrics.get("usage", {}) if isinstance(metrics, Mapping) else {}
    return {
        "name": str(metadata.get("name") or "unknown-node"),
        "roles": node_roles(node),
        "ready": condition_status(node, "Ready") == "True",
        "pressures": {
            "disk": condition_status(node, "DiskPressure") == "True",
            "memory": condition_status(node, "MemoryPressure") == "True",
            "pid": condition_status(node, "PIDPressure") == "True",
        },
        "kubeletVersion": node_info.get("kubeletVersion"),
        "osImage": node_info.get("osImage"),
        "usage": {
            "cpu": usage.get("cpu") if isinstance(usage, Mapping) else None,
            "memory": usage.get("memory") if isinstance(usage, Mapping) else None,
        },
    }
