from collections.abc import Mapping
from typing import Any


def resource_items(payload: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    items = payload.get("items") if payload else None
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, Mapping)]


def metadata_name(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return ""
    return str(metadata.get("name") or "")


def metadata_namespace(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return "default"
    return str(metadata.get("namespace") or "default")


def pod_container_statuses(pod: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    status = pod.get("status", {})
    if not isinstance(status, Mapping):
        return []
    statuses = status.get("containerStatuses", [])
    if not isinstance(statuses, list):
        return []
    return [item for item in statuses if isinstance(item, Mapping)]


def pod_ready_summary(pod: Mapping[str, Any]) -> str:
    status = pod.get("status", {})
    statuses = status.get("containerStatuses", []) if isinstance(status, Mapping) else []
    if not isinstance(statuses, list):
        return "0/0"
    ready = sum(1 for item in statuses if isinstance(item, Mapping) and item.get("ready"))
    return f"{ready}/{len(statuses)}"


def pod_owner_summary(pod: Mapping[str, Any]) -> str:
    metadata = pod.get("metadata", {})
    owners = metadata.get("ownerReferences", []) if isinstance(metadata, Mapping) else []
    if not isinstance(owners, list) or not owners or not isinstance(owners[0], Mapping):
        return "-"
    return f"{owners[0].get('kind') or 'Owner'}/{owners[0].get('name') or 'unknown'}"


def pod_is_fully_ready(pod: Mapping[str, Any]) -> bool:
    status = pod.get("status", {})
    statuses = status.get("containerStatuses", []) if isinstance(status, Mapping) else []
    if not isinstance(statuses, list):
        return False
    ready = sum(1 for item in statuses if isinstance(item, Mapping) and item.get("ready"))
    return len(statuses) > 0 and ready == len(statuses)


def pod_restart_total(pod: Mapping[str, Any]) -> int:
    return sum(int(item.get("restartCount") or 0) for item in pod_container_statuses(pod))


def pod_is_terminating(pod: Mapping[str, Any]) -> bool:
    metadata = pod.get("metadata", {})
    if not isinstance(metadata, Mapping):
        return False
    return bool(metadata.get("deletionTimestamp"))


def find_condition(resource: Mapping[str, Any], condition_type: str) -> Mapping[str, Any] | None:
    status = resource.get("status", {})
    conditions = status.get("conditions", []) if isinstance(status, Mapping) else []
    if not isinstance(conditions, list):
        return None
    return next(
        (
            condition
            for condition in conditions
            if isinstance(condition, Mapping) and condition.get("type") == condition_type
        ),
        None,
    )


def condition_status(resource: Mapping[str, Any], condition_type: str) -> str | None:
    condition = find_condition(resource, condition_type)
    if condition and condition.get("status") is not None:
        return str(condition.get("status"))
    return None
