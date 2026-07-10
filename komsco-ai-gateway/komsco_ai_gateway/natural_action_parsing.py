from collections.abc import Callable, Mapping
import re
from typing import Any


def execution_mode_allows_actions(req: Any, *, execution_mode: Callable[[Any], str]) -> bool:
    return execution_mode(req) in {"execute", "unrestricted"}


def execution_mode_allows_immediate_actions(
    req: Any,
    *,
    execution_mode: Callable[[Any], str],
    unrestricted_commands_enabled: bool,
) -> bool:
    return execution_mode(req) == "unrestricted" and unrestricted_commands_enabled


def rollback_revision_from_message(message: str, *, pattern: re.Pattern[str]) -> int | None:
    match = pattern.search(message)
    if not match:
        return None
    revision = match.group("revision") or match.group("korean_revision")
    return int(revision) if revision else None


def hpa_bounds_from_message(
    message: str,
    *,
    min_pattern: re.Pattern[str],
    max_pattern: re.Pattern[str],
) -> tuple[int, int] | None:
    min_match = min_pattern.search(message)
    max_match = max_pattern.search(message)
    if not min_match or not max_match:
        return None
    min_replicas = int(min_match.group("value"))
    max_replicas = int(max_match.group("value"))
    if min_replicas < 1 or max_replicas < min_replicas:
        return None
    return min_replicas, max_replicas


def is_followup_execution_request(message: str, *, pattern: re.Pattern[str]) -> bool:
    return bool(pattern.search(message))


def recent_natural_action_request(
    req: Any,
    *,
    request_factory: Callable[..., Any],
    is_followup: Callable[[str], bool],
    parse_intent: Callable[[Any], Mapping[str, Any] | None],
) -> Any | None:
    for message in reversed(req.recentMessages):
        role = message.role.strip().lower()
        content = message.content.strip()
        if role != "user" or not content or is_followup(content):
            continue
        candidate = request_factory(
            message=content,
            pageContext=req.pageContext,
            conversationId=req.conversationId,
            runId=req.runId,
        )
        if parse_intent(candidate):
            return candidate
    return None


def parse_natural_action_intent(
    req: Any,
    *,
    namespace_from_request: Callable[[Any], str],
    target_name_from_request: Callable[[Any, re.Match[str] | None], str],
    hpa_target_name_from_request: Callable[[Any, re.Match[str] | None], str],
    pod_target_name_from_request: Callable[[Any, re.Match[str] | None], str],
    hpa_bounds: Callable[[str], tuple[int, int] | None],
    rollback_revision: Callable[[str], int | None],
    page_context_resource_name: Callable[[Any, str], str],
    now_rfc3339: Callable[[], str],
    hpa_request_pattern: re.Pattern[str],
    scale_intent_pattern: re.Pattern[str],
    scale_replicas_pattern: re.Pattern[str],
    pod_eviction_pattern: re.Pattern[str],
    pod_resource_pattern: re.Pattern[str],
    rollback_request_pattern: re.Pattern[str],
    restart_intent_pattern: re.Pattern[str],
    restart_request_pattern: re.Pattern[str],
) -> dict[str, Any] | None:
    namespace = namespace_from_request(req)

    if hpa_request_pattern.search(req.message):
        bounds = hpa_bounds(req.message)
        target_name = hpa_target_name_from_request(req, None)
        if bounds and namespace and target_name:
            min_replicas, max_replicas = bounds
            return {
                "apiVersion": "autoscaling/v2",
                "kind": "HorizontalPodAutoscaler",
                "toolName": "set_hpa_bounds",
                "targetName": target_name,
                "namespace": namespace,
                "parameters": {
                    "allowMaxIncrease": False,
                    "maxReplicas": max_replicas,
                    "minReplicas": min_replicas,
                },
                "summary": (
                    f"HPA `{namespace}/{target_name}` minReplicas를 `{min_replicas}`, "
                    f"maxReplicas를 `{max_replicas}`로 변경"
                ),
            }

    scale_match = scale_intent_pattern.search(req.message)
    replicas_match = scale_match or scale_replicas_pattern.search(req.message)
    if replicas_match:
        target_name = target_name_from_request(req, scale_match)
        replicas = int(replicas_match.group("replicas"))
        if not target_name:
            return None
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "toolName": "set_replicas_within_bounds",
            "targetName": target_name,
            "namespace": namespace,
            "parameters": {
                "hpaReviewed": False,
                "maxReplicas": max(20, replicas),
                "minReplicas": 0,
                "replicas": replicas,
            },
            "summary": f"Deployment `{namespace}/{target_name}` replicas를 `{replicas}`로 변경",
        }

    if pod_eviction_pattern.search(req.message) and (
        pod_resource_pattern.search(req.message)
        or page_context_resource_name(req, "Pod")
        or re.search(r"(?:pod|pods|파드)", req.message, re.IGNORECASE)
    ):
        target_name = pod_target_name_from_request(req, None)
        if not namespace or not target_name:
            return None
        return {
            "apiVersion": "v1",
            "kind": "Pod",
            "toolName": "evict_one_unhealthy_controller_owned_pod",
            "targetName": target_name,
            "namespace": namespace,
            "parameters": {"reason": "natural_language_unhealthy_pod_eviction"},
            "summary": f"Unhealthy controller-owned Pod `{namespace}/{target_name}` eviction",
        }

    if rollback_request_pattern.search(req.message):
        target_name = target_name_from_request(req, None)
        if not target_name:
            return None
        revision = rollback_revision(req.message)
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "toolName": "rollback_deployment_to_revision",
            "targetName": target_name,
            "namespace": namespace,
            "parameters": {"revision": revision},
            "summary": (
                f"Deployment `{namespace}/{target_name}` rollback"
                + (f" to revision `{revision}`" if revision else " to previous revision")
            ),
        }

    restart_match = restart_intent_pattern.search(req.message)
    if restart_match or restart_request_pattern.search(req.message):
        target_name = target_name_from_request(req, restart_match)
        if not target_name:
            return None
        return {
            "apiVersion": "apps/v1",
            "kind": "Deployment",
            "toolName": "rollout_restart_deployment",
            "targetName": target_name,
            "namespace": namespace,
            "parameters": {"restartedAt": now_rfc3339()},
            "summary": f"Deployment `{namespace}/{target_name}` rollout restart",
        }

    return None
