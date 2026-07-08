from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException

from .security import canonical_digest


ACTION_REGISTRY_VERSION = "v1"
ACTION_REGISTRY_ENTRIES: dict[str, dict[str, Any]] = {
    "rollout_restart_deployment": {
        "toolName": "rollout_restart_deployment",
        "toolVersion": "v1",
        "targetKind": "Deployment",
        "risk": "low",
        "authorization": {
            "apiGroup": "apps",
            "resource": "deployments",
            "subresource": "",
            "verb": "patch",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
        },
    },
    "set_replicas_within_bounds": {
        "toolName": "set_replicas_within_bounds",
        "toolVersion": "v1",
        "targetKind": "Deployment",
        "risk": "medium",
        "authorization": {
            "apiGroup": "apps",
            "resource": "deployments",
            "subresource": "scale",
            "verb": "update",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/apps/v1/namespaces/{namespace}/deployments/{name}/scale",
        },
    },
    "evict_one_unhealthy_controller_owned_pod": {
        "toolName": "evict_one_unhealthy_controller_owned_pod",
        "toolVersion": "v1",
        "targetKind": "Pod",
        "risk": "medium",
        "authorization": {
            "apiGroup": "",
            "resource": "pods",
            "subresource": "eviction",
            "verb": "create",
        },
        "request": {
            "method": "POST",
            "pathTemplate": "/api/v1/namespaces/{namespace}/pods/{name}/eviction",
        },
    },
    "rollback_deployment_to_revision": {
        "toolName": "rollback_deployment_to_revision",
        "toolVersion": "v1",
        "targetKind": "Deployment",
        "risk": "medium",
        "authorization": {
            "apiGroup": "apps",
            "resource": "deployments",
            "subresource": "",
            "verb": "patch",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
        },
    },
    "set_hpa_bounds": {
        "toolName": "set_hpa_bounds",
        "toolVersion": "v1",
        "targetKind": "HorizontalPodAutoscaler",
        "risk": "medium",
        "authorization": {
            "apiGroup": "autoscaling",
            "resource": "horizontalpodautoscalers",
            "subresource": "",
            "verb": "patch",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/autoscaling/v2/namespaces/{namespace}/horizontalpodautoscalers/{name}",
        },
    },
    "set_deployment_container_command": {
        "toolName": "set_deployment_container_command",
        "toolVersion": "v1",
        "targetKind": "Deployment",
        "risk": "medium",
        "authorization": {
            "apiGroup": "apps",
            "resource": "deployments",
            "subresource": "",
            "verb": "patch",
        },
        "request": {
            "method": "PATCH",
            "pathTemplate": "/apis/apps/v1/namespaces/{namespace}/deployments/{name}",
        },
    },
    "namespace_cleanup_review": {
        "toolName": "namespace_cleanup_review",
        "toolVersion": "v1",
        "targetKind": "Namespace",
        "risk": "medium",
        "authorization": {
            "apiGroup": "",
            "resource": "namespaces",
            "subresource": "",
            "verb": "get",
        },
        "request": {
            "method": "GET",
            "pathTemplate": "/api/v1/namespaces/{name}",
        },
    },
    "test_pod_create_review": {
        "toolName": "test_pod_create_review",
        "toolVersion": "v1",
        "targetKind": "Namespace",
        "risk": "low",
        "authorization": {
            "apiGroup": "",
            "resource": "namespaces",
            "subresource": "",
            "verb": "get",
        },
        "request": {
            "method": "GET",
            "pathTemplate": "/api/v1/namespaces/{name}",
        },
    },
    "create_crashloop_test_pods": {
        "toolName": "create_crashloop_test_pods",
        "toolVersion": "v1",
        "targetKind": "Namespace",
        "risk": "low",
        "authorization": {
            "apiGroup": "",
            "resource": "pods",
            "subresource": "",
            "verb": "create",
        },
        "request": {
            "method": "POST",
            "pathTemplate": "/api/v1/namespaces/{namespace}/pods",
        },
    },
    "pod_diagnostic_review": {
        "toolName": "pod_diagnostic_review",
        "toolVersion": "v1",
        "targetKind": "Pod",
        "risk": "low",
        "authorization": {
            "apiGroup": "",
            "resource": "pods",
            "subresource": "",
            "verb": "get",
        },
        "request": {
            "method": "GET",
            "pathTemplate": "/api/v1/namespaces/{namespace}/pods/{name}",
        },
    },
    "pod_fix_or_rollback_review": {
        "toolName": "pod_fix_or_rollback_review",
        "toolVersion": "v1",
        "targetKind": "Pod",
        "risk": "low",
        "authorization": {
            "apiGroup": "",
            "resource": "pods",
            "subresource": "",
            "verb": "get",
        },
        "request": {
            "method": "GET",
            "pathTemplate": "/api/v1/namespaces/{namespace}/pods/{name}",
        },
    },
}
ACTION_REGISTRY_BUNDLE = {
    "schemaVersion": "v1",
    "version": ACTION_REGISTRY_VERSION,
    "entries": ACTION_REGISTRY_ENTRIES,
}
ACTION_REGISTRY_DIGEST = canonical_digest(ACTION_REGISTRY_BUNDLE)


def get_action_registry_entry(tool_name: str, tool_version: str) -> dict[str, Any]:
    entry = ACTION_REGISTRY_ENTRIES.get(tool_name)
    if not entry or entry.get("toolVersion") != tool_version:
        raise HTTPException(status_code=400, detail="Action is not in the configured allow-list")
    return entry


def validate_action_target(action: Mapping[str, Any], target: Any) -> None:
    expected_kind = action.get("targetKind")
    if expected_kind and target.kind != expected_kind:
        raise HTTPException(
            status_code=400,
            detail=f"Action target kind must be {expected_kind}",
        )
