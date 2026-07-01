from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

from .security import canonical_digest


class AiopsCoreError(ValueError):
    def __init__(self, message: str, *, reason: str = "validation_failed") -> None:
        super().__init__(message)
        self.reason = reason


@dataclass(frozen=True)
class MutationRequest:
    method: str
    path: str
    content_type: str
    body: dict[str, Any]
    expected_statuses: tuple[int, ...] = (200, 201, 202)


def path_segment(value: str) -> str:
    if not value:
        raise AiopsCoreError("resource path segment is required", reason="invalid_target")
    return quote(value, safe="")


def action_from_plan(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    action = plan.get("action")
    if not isinstance(action, Mapping):
        raise AiopsCoreError("sealed plan does not contain an action", reason="invalid_plan")
    return action


def target_from_plan(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    target = plan.get("target")
    if not isinstance(target, Mapping):
        raise AiopsCoreError("sealed plan does not contain a target", reason="invalid_plan")
    return target


def parameters_from_plan(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    action = action_from_plan(plan)
    parameters = action.get("normalizedParameters")
    if not isinstance(parameters, Mapping):
        raise AiopsCoreError("sealed plan does not contain normalized parameters", reason="invalid_plan")
    return parameters


def policy_from_plan(plan: Mapping[str, Any]) -> Mapping[str, Any]:
    safety = plan.get("safety")
    if not isinstance(safety, Mapping):
        return {}
    policy = safety.get("policy")
    return policy if isinstance(policy, Mapping) else {}


def target_path(target: Mapping[str, Any]) -> str:
    api_version = str(target.get("apiVersion") or "")
    kind = str(target.get("kind") or "")
    namespace = str(target.get("namespace") or "")
    name = str(target.get("name") or "")

    if api_version == "apps/v1" and kind == "Deployment":
        return f"/apis/apps/v1/namespaces/{path_segment(namespace)}/deployments/{path_segment(name)}"
    if api_version == "v1" and kind == "Pod":
        return f"/api/v1/namespaces/{path_segment(namespace)}/pods/{path_segment(name)}"
    if api_version in {"autoscaling/v2", "autoscaling/v2beta2"} and kind == "HorizontalPodAutoscaler":
        return (
            f"/apis/{api_version}/namespaces/{path_segment(namespace)}"
            f"/horizontalpodautoscalers/{path_segment(name)}"
        )

    raise AiopsCoreError(
        f"unsupported target apiVersion/kind: {api_version}/{kind}",
        reason="unsupported_target",
    )


def deployment_scale_path(target: Mapping[str, Any]) -> str:
    if target.get("apiVersion") != "apps/v1" or target.get("kind") != "Deployment":
        raise AiopsCoreError("scale target must be apps/v1 Deployment", reason="unsupported_target")
    return f"{target_path(target)}/scale"


def target_uid_matches(target: Mapping[str, Any], live_resource: Mapping[str, Any]) -> bool:
    expected_uid = str(target.get("uid") or "")
    observed_uid = str(live_resource.get("metadata", {}).get("uid") or "")
    return bool(expected_uid and observed_uid and expected_uid == observed_uid)


def validate_live_target(target: Mapping[str, Any], live_resource: Mapping[str, Any]) -> None:
    if not target_uid_matches(target, live_resource):
        raise AiopsCoreError("live target UID does not match sealed plan target", reason="target_uid_mismatch")


def int_parameter(parameters: Mapping[str, Any], key: str) -> int:
    value = parameters.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise AiopsCoreError(f"{key} must be an integer", reason="invalid_parameters")
    return value


def bool_parameter(parameters: Mapping[str, Any], key: str, *, default: bool = False) -> bool:
    value = parameters.get(key, default)
    if isinstance(value, bool):
        return value
    raise AiopsCoreError(f"{key} must be a boolean", reason="invalid_parameters")


def owned_by_uid(resource: Mapping[str, Any], owner_uid: str) -> bool:
    owners = resource.get("metadata", {}).get("ownerReferences", [])
    if not isinstance(owners, Sequence) or isinstance(owners, (str, bytes)):
        return False
    for owner in owners:
        if isinstance(owner, Mapping) and str(owner.get("uid") or "") == owner_uid:
            return True
    return False


def hpa_targets_deployment(hpa: Mapping[str, Any], target: Mapping[str, Any]) -> bool:
    scale_target = hpa.get("spec", {}).get("scaleTargetRef")
    if not isinstance(scale_target, Mapping):
        return False
    return (
        scale_target.get("apiVersion") == "apps/v1"
        and scale_target.get("kind") == "Deployment"
        and scale_target.get("name") == target.get("name")
        and hpa.get("metadata", {}).get("namespace") == target.get("namespace")
    )


def matching_hpas_for_deployment(
    hpas: Sequence[Mapping[str, Any]],
    target: Mapping[str, Any],
) -> list[Mapping[str, Any]]:
    return [hpa for hpa in hpas if hpa_targets_deployment(hpa, target)]


def container_waiting_reasons(pod: Mapping[str, Any]) -> list[str]:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if not isinstance(statuses, Sequence) or isinstance(statuses, (str, bytes)):
        return []
    reasons: list[str] = []
    for status in statuses:
        if not isinstance(status, Mapping):
            continue
        state = status.get("state")
        waiting = state.get("waiting") if isinstance(state, Mapping) else None
        if isinstance(waiting, Mapping):
            reasons.append(str(waiting.get("reason") or "Waiting"))
    return reasons


def pod_is_ready(pod: Mapping[str, Any]) -> bool:
    conditions = pod.get("status", {}).get("conditions", [])
    if not isinstance(conditions, Sequence) or isinstance(conditions, (str, bytes)):
        return False
    return any(
        condition.get("type") == "Ready" and condition.get("status") == "True"
        for condition in conditions
        if isinstance(condition, Mapping)
    )


def pod_is_unhealthy(pod: Mapping[str, Any]) -> bool:
    phase = str(pod.get("status", {}).get("phase") or "")
    return phase not in {"Running", "Succeeded"} or not pod_is_ready(pod) or bool(container_waiting_reasons(pod))


def pod_has_controller_owner(pod: Mapping[str, Any]) -> bool:
    owners = pod.get("metadata", {}).get("ownerReferences", [])
    if not isinstance(owners, Sequence) or isinstance(owners, (str, bytes)):
        return False
    return any(
        owner.get("controller") is True and str(owner.get("uid") or "")
        for owner in owners
        if isinstance(owner, Mapping)
    )


def replica_set_revision(replica_set: Mapping[str, Any]) -> int | None:
    annotations = replica_set.get("metadata", {}).get("annotations", {})
    if not isinstance(annotations, Mapping):
        return None
    revision = annotations.get("deployment.kubernetes.io/revision")
    try:
        return int(str(revision))
    except (TypeError, ValueError):
        return None


def deployment_revision(deployment: Mapping[str, Any]) -> int | None:
    annotations = deployment.get("metadata", {}).get("annotations", {})
    if not isinstance(annotations, Mapping):
        return None
    revision = annotations.get("deployment.kubernetes.io/revision")
    try:
        return int(str(revision))
    except (TypeError, ValueError):
        return None


def select_rollback_replica_set(
    deployment: Mapping[str, Any],
    replica_sets: Sequence[Mapping[str, Any]],
    requested_revision: int | None,
) -> Mapping[str, Any]:
    deployment_uid = str(deployment.get("metadata", {}).get("uid") or "")
    current_revision = deployment_revision(deployment)
    candidates: list[tuple[int, Mapping[str, Any]]] = []
    for replica_set in replica_sets:
        if not isinstance(replica_set, Mapping) or not owned_by_uid(replica_set, deployment_uid):
            continue
        revision = replica_set_revision(replica_set)
        if revision is not None:
            candidates.append((revision, replica_set))

    if not candidates:
        raise AiopsCoreError("no owned ReplicaSet revision found for rollback", reason="rollback_target_missing")

    if requested_revision is not None:
        for revision, replica_set in candidates:
            if revision == requested_revision:
                return replica_set
        raise AiopsCoreError("requested rollback revision was not found", reason="rollback_revision_missing")

    previous = [
        (revision, replica_set)
        for revision, replica_set in candidates
        if current_revision is None or revision < current_revision
    ]
    if not previous:
        raise AiopsCoreError("no previous ReplicaSet revision found for rollback", reason="rollback_revision_missing")
    return sorted(previous, key=lambda item: item[0], reverse=True)[0][1]


def rollback_template_from_replica_set(replica_set: Mapping[str, Any]) -> dict[str, Any]:
    template = deepcopy(replica_set.get("spec", {}).get("template"))
    if not isinstance(template, dict):
        raise AiopsCoreError("rollback ReplicaSet does not contain a pod template", reason="invalid_rollback_template")

    metadata = template.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        raise AiopsCoreError("rollback pod template metadata is invalid", reason="invalid_rollback_template")

    labels = metadata.get("labels")
    if isinstance(labels, dict):
        labels.pop("pod-template-hash", None)

    annotations = metadata.get("annotations")
    if isinstance(annotations, dict):
        annotations.pop("deployment.kubernetes.io/revision", None)

    return template


def build_rollout_restart_request(plan: Mapping[str, Any], live: Mapping[str, Any]) -> MutationRequest:
    target = target_from_plan(plan)
    validate_live_target(target, live)
    parameters = parameters_from_plan(plan)
    restarted_at = str(parameters.get("restartedAt") or "")
    if not restarted_at:
        raise AiopsCoreError("restartedAt is required", reason="invalid_parameters")
    return MutationRequest(
        method="PATCH",
        path=target_path(target),
        content_type="application/strategic-merge-patch+json",
        body={
            "spec": {
                "template": {
                    "metadata": {
                        "annotations": {
                            "kubectl.kubernetes.io/restartedAt": restarted_at,
                        }
                    }
                }
            }
        },
    )


def build_set_replicas_request(
    plan: Mapping[str, Any],
    live: Mapping[str, Any],
    hpas: Sequence[Mapping[str, Any]],
) -> MutationRequest:
    target = target_from_plan(plan)
    validate_live_target(target, live)
    parameters = parameters_from_plan(plan)
    replicas = int_parameter(parameters, "replicas")
    min_replicas = int_parameter(parameters, "minReplicas")
    max_replicas = int_parameter(parameters, "maxReplicas")
    if min_replicas < 0 or max_replicas < min_replicas or not (min_replicas <= replicas <= max_replicas):
        raise AiopsCoreError("replicas must be within approved bounds", reason="invalid_parameters")
    matching_hpas = matching_hpas_for_deployment(hpas, target)
    if matching_hpas and not bool_parameter(parameters, "hpaReviewed", default=False):
        raise AiopsCoreError(
            "target Deployment is controlled by HPA; hpaReviewed=true is required",
            reason="hpa_review_required",
        )
    return MutationRequest(
        method="PATCH",
        path=deployment_scale_path(target),
        content_type="application/merge-patch+json",
        body={"spec": {"replicas": replicas}},
    )


def build_pod_eviction_request(plan: Mapping[str, Any], live: Mapping[str, Any]) -> MutationRequest:
    target = target_from_plan(plan)
    validate_live_target(target, live)
    if not pod_has_controller_owner(live):
        raise AiopsCoreError("Pod eviction requires a controller owner", reason="controller_owner_required")
    if not pod_is_unhealthy(live):
        raise AiopsCoreError("Pod is not currently unhealthy", reason="pod_not_unhealthy")
    return MutationRequest(
        method="POST",
        path=f"{target_path(target)}/eviction",
        content_type="application/json",
        body={
            "apiVersion": "policy/v1",
            "kind": "Eviction",
            "metadata": {
                "name": target.get("name"),
                "namespace": target.get("namespace"),
            },
            "deleteOptions": {
                "preconditions": {
                    "uid": target.get("uid"),
                }
            },
        },
        expected_statuses=(200, 201, 202, 404),
    )


def build_rollback_request(
    plan: Mapping[str, Any],
    live: Mapping[str, Any],
    replica_sets: Sequence[Mapping[str, Any]],
) -> MutationRequest:
    target = target_from_plan(plan)
    validate_live_target(target, live)
    parameters = parameters_from_plan(plan)
    requested_revision = parameters.get("revision")
    if requested_revision is not None:
        requested_revision = int_parameter(parameters, "revision")
    selected = select_rollback_replica_set(live, replica_sets, requested_revision)
    selected_revision = replica_set_revision(selected)
    template = rollback_template_from_replica_set(selected)
    template.setdefault("metadata", {}).setdefault("annotations", {})
    template["metadata"]["annotations"]["aiops.komsco/rollback-revision"] = str(selected_revision)
    template["metadata"]["annotations"]["aiops.komsco/rollback-template-digest"] = canonical_digest(template)
    return MutationRequest(
        method="PATCH",
        path=target_path(target),
        content_type="application/strategic-merge-patch+json",
        body={"spec": {"template": template}},
    )


def build_hpa_bounds_request(plan: Mapping[str, Any], live: Mapping[str, Any]) -> MutationRequest:
    target = target_from_plan(plan)
    validate_live_target(target, live)
    parameters = parameters_from_plan(plan)
    min_replicas = int_parameter(parameters, "minReplicas")
    max_replicas = int_parameter(parameters, "maxReplicas")
    if min_replicas < 1 or max_replicas < min_replicas:
        raise AiopsCoreError("HPA minReplicas/maxReplicas bounds are invalid", reason="invalid_parameters")
    current_max = live.get("spec", {}).get("maxReplicas")
    if isinstance(current_max, int) and max_replicas > current_max:
        if not bool_parameter(parameters, "allowMaxIncrease", default=False):
            raise AiopsCoreError(
                "HPA maxReplicas increase requires allowMaxIncrease=true",
                reason="hpa_max_increase_requires_policy",
            )
    return MutationRequest(
        method="PATCH",
        path=target_path(target),
        content_type="application/merge-patch+json",
        body={"spec": {"minReplicas": min_replicas, "maxReplicas": max_replicas}},
    )


def build_mutation_request(
    plan: Mapping[str, Any],
    *,
    live_target: Mapping[str, Any],
    hpas: Sequence[Mapping[str, Any]] = (),
    replica_sets: Sequence[Mapping[str, Any]] = (),
) -> MutationRequest:
    tool_name = str(action_from_plan(plan).get("toolName") or "")
    if tool_name == "rollout_restart_deployment":
        return build_rollout_restart_request(plan, live_target)
    if tool_name == "set_replicas_within_bounds":
        return build_set_replicas_request(plan, live_target, hpas)
    if tool_name == "evict_one_unhealthy_controller_owned_pod":
        return build_pod_eviction_request(plan, live_target)
    if tool_name == "rollback_deployment_to_revision":
        return build_rollback_request(plan, live_target, replica_sets)
    if tool_name == "set_hpa_bounds":
        return build_hpa_bounds_request(plan, live_target)
    raise AiopsCoreError(f"unsupported action tool: {tool_name}", reason="unsupported_action")


HOST_DIAGNOSTIC_COLLECTORS: dict[str, dict[str, Any]] = {
    "node_os_readonly_triage": {
        "collector": "node_os_readonly_triage",
        "collectorVersion": "v1",
        "collectorProfile": "passive-readonly",
        "risk": "evidence-check",
        "hostAccess": {
            "hostPID": False,
            "hostNetwork": False,
            "runtimeSocket": False,
            "hostPaths": [
                {"path": "/proc", "readOnly": True, "reason": "kernel and pressure summary"},
                {"path": "/sys", "readOnly": True, "reason": "block and kernel device summary"},
                {"path": "/var/log", "readOnly": True, "reason": "bounded kubelet and crio log tail"},
            ],
        },
        "allowedCommands": [
            "collect_node_conditions",
            "collect_kubelet_log_tail",
            "collect_crio_log_tail",
            "collect_disk_pressure_summary",
            "collect_kernel_summary",
        ],
        "arbitraryCommandInputAllowed": False,
        "limits": {"maxBytes": 10 * 1024 * 1024, "maxLines": 50000, "deadline": "30s"},
    },
    "node_runtime_readonly_triage": {
        "collector": "node_runtime_readonly_triage",
        "collectorVersion": "v1",
        "collectorProfile": "elevated-readonly",
        "risk": "medium",
        "hostAccess": {
            "hostPID": False,
            "hostNetwork": False,
            "runtimeSocket": True,
            "hostPaths": [
                {"path": "/run/crio/crio.sock", "readOnly": True, "reason": "evidence-check runtime inspection adapter"},
                {"path": "/var/lib/kubelet", "readOnly": True, "reason": "pod volume and kubelet state summary"},
            ],
        },
        "allowedCommands": [
            "collect_runtime_container_summary",
            "collect_kubelet_pod_state",
        ],
        "arbitraryCommandInputAllowed": False,
        "limits": {"maxBytes": 20 * 1024 * 1024, "maxLines": 80000, "deadline": "45s"},
    },
}


def get_host_diagnostic_collector(collector: str) -> dict[str, Any]:
    profile = HOST_DIAGNOSTIC_COLLECTORS.get(collector)
    if not profile:
        raise AiopsCoreError("host diagnostic collector is not in the registry", reason="unsupported_collector")
    return profile
