import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from .security import now_rfc3339


@dataclass(frozen=True, slots=True)
class ActionRecordContext:
    cluster_id: str
    mutations_enabled: bool
    test_pod_create_default_image: str
    test_pod_create_name_prefix: str
    test_pod_create_app_label: str
    test_pod_create_failure_command: tuple[str, ...]


def normalize_action_parameters(
    action: Mapping[str, Any],
    parameters: Mapping[str, Any],
    context: ActionRecordContext,
) -> dict[str, Any]:
    tool_name = action.get("toolName")
    if tool_name == "rollout_restart_deployment":
        restarted_at = parameters.get("restartedAt")
        return {"restartedAt": restarted_at if isinstance(restarted_at, str) else now_rfc3339()}

    if tool_name == "set_replicas_within_bounds":
        replicas = parameters.get("replicas")
        min_replicas = parameters.get("minReplicas", 0)
        max_replicas = parameters.get("maxReplicas", 20)
        hpa_reviewed = parameters.get("hpaReviewed", False)
        if (
            isinstance(replicas, bool)
            or isinstance(min_replicas, bool)
            or isinstance(max_replicas, bool)
            or not isinstance(hpa_reviewed, bool)
            or not isinstance(replicas, int)
            or not isinstance(min_replicas, int)
            or not isinstance(max_replicas, int)
        ):
            raise HTTPException(status_code=400, detail="replicas bounds must be integer values")
        if min_replicas < 0 or max_replicas < min_replicas or not (min_replicas <= replicas <= max_replicas):
            raise HTTPException(status_code=400, detail="replicas must be within minReplicas/maxReplicas")
        return {
            "maxReplicas": max_replicas,
            "minReplicas": min_replicas,
            "replicas": replicas,
            "hpaReviewed": hpa_reviewed,
        }

    if tool_name == "evict_one_unhealthy_controller_owned_pod":
        reason = parameters.get("reason")
        return {"reason": reason if isinstance(reason, str) else "approved_unhealthy_pod_eviction"}

    if tool_name == "rollback_deployment_to_revision":
        revision = parameters.get("revision")
        if revision is None:
            return {"revision": None}
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 1:
            raise HTTPException(status_code=400, detail="rollback revision must be a positive integer")
        return {"revision": revision}

    if tool_name == "set_hpa_bounds":
        min_replicas = parameters.get("minReplicas")
        max_replicas = parameters.get("maxReplicas")
        allow_max_increase = parameters.get("allowMaxIncrease", False)
        if (
            isinstance(min_replicas, bool)
            or isinstance(max_replicas, bool)
            or not isinstance(min_replicas, int)
            or not isinstance(max_replicas, int)
            or not isinstance(allow_max_increase, bool)
        ):
            raise HTTPException(status_code=400, detail="HPA replica bounds must be integer values")
        if min_replicas < 1 or max_replicas < min_replicas:
            raise HTTPException(status_code=400, detail="HPA maxReplicas must be >= minReplicas")
        return {"allowMaxIncrease": allow_max_increase, "maxReplicas": max_replicas, "minReplicas": min_replicas}

    if tool_name == "set_deployment_container_command":
        container_name = parameters.get("containerName")
        command = parameters.get("command")
        expected_previous_digest = parameters.get("expectedPreviousCommandDigest")
        reason = parameters.get("reason")
        if not isinstance(container_name, str) or not container_name.strip():
            raise HTTPException(status_code=400, detail="containerName must be a non-empty string")
        if not isinstance(command, list) or not command or len(command) > 8:
            raise HTTPException(status_code=400, detail="command must be a list of 1 to 8 strings")
        normalized_command = []
        for item in command:
            if not isinstance(item, str) or not item.strip() or len(item.strip()) > 256:
                raise HTTPException(status_code=400, detail="command entries must be non-empty strings up to 256 chars")
            normalized_command.append(item.strip())
        if expected_previous_digest is not None and not isinstance(expected_previous_digest, str):
            raise HTTPException(status_code=400, detail="expectedPreviousCommandDigest must be a string")
        if reason is not None and not isinstance(reason, str):
            raise HTTPException(status_code=400, detail="reason must be a string")
        return {
            "command": normalized_command,
            "containerName": container_name.strip(),
            "expectedPreviousCommandDigest": str(expected_previous_digest or ""),
            "reason": str(reason or "approved deployment container command fix")[:240],
        }

    if tool_name == "namespace_cleanup_review":
        owner_confirmed = parameters.get("ownerConfirmed", False)
        pvc_route_reviewed = parameters.get("pvcRouteReviewed", False)
        backup_reviewed = parameters.get("backupReviewed", False)
        if not all(isinstance(value, bool) for value in (owner_confirmed, pvc_route_reviewed, backup_reviewed)):
            raise HTTPException(status_code=400, detail="namespace cleanup review flags must be boolean values")
        return {
            "backupReviewed": backup_reviewed,
            "ownerConfirmed": owner_confirmed,
            "pvcRouteReviewed": pvc_route_reviewed,
            "reviewOnly": True,
        }

    if tool_name == "test_pod_create_review":
        count = parameters.get("count")
        image = str(parameters.get("image") or context.test_pod_create_default_image)
        if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 5:
            raise HTTPException(status_code=400, detail="test pod count must be an integer between 1 and 5")
        return {
            "count": count,
            "image": image[:240],
            "namePrefix": str(parameters.get("namePrefix") or context.test_pod_create_name_prefix)[:63],
            "reviewOnly": True,
        }

    if tool_name == "create_crashloop_test_pods":
        count = parameters.get("count")
        image = str(parameters.get("image") or context.test_pod_create_default_image)
        name_prefix = str(parameters.get("namePrefix") or context.test_pod_create_name_prefix).strip()
        if isinstance(count, bool) or not isinstance(count, int) or count < 1 or count > 5:
            raise HTTPException(status_code=400, detail="test pod count must be an integer between 1 and 5")
        if image != context.test_pod_create_default_image:
            raise HTTPException(status_code=400, detail="test pod image is fixed by policy")
        if not re.fullmatch(r"[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?", name_prefix):
            raise HTTPException(status_code=400, detail="test pod namePrefix must be a Kubernetes-safe name")
        return {
            "appLabel": context.test_pod_create_app_label,
            "count": count,
            "failureMode": "crashloop",
            "fixedCommand": list(context.test_pod_create_failure_command),
            "image": image,
            "namePrefix": name_prefix[:48],
        }

    if tool_name == "pod_diagnostic_review":
        include_describe = parameters.get("includeDescribe", True)
        include_events = parameters.get("includeEvents", True)
        include_previous_logs = parameters.get("includePreviousLogs", True)
        if not all(isinstance(value, bool) for value in (include_describe, include_events, include_previous_logs)):
            raise HTTPException(status_code=400, detail="pod diagnostic review flags must be boolean values")
        return {
            "includeDescribe": include_describe,
            "includeEvents": include_events,
            "includePreviousLogs": include_previous_logs,
            "reviewOnly": True,
        }

    if tool_name == "pod_fix_or_rollback_review":
        include_owner_chain = parameters.get("includeOwnerChain", True)
        include_rollout_history = parameters.get("includeRolloutHistory", True)
        include_template_review = parameters.get("includeTemplateReview", True)
        if not all(isinstance(value, bool) for value in (include_owner_chain, include_rollout_history, include_template_review)):
            raise HTTPException(status_code=400, detail="pod fix review flags must be boolean values")
        return {
            "includeOwnerChain": include_owner_chain,
            "includeRolloutHistory": include_rollout_history,
            "includeTemplateReview": include_template_review,
            "reviewOnly": True,
        }

    raise HTTPException(status_code=400, detail="Unsupported action")
