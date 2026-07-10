from __future__ import annotations

import os
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import HTTPException

from .aiops_core import (
    AiopsCoreError,
    action_from_plan,
    build_mutation_request,
    deployment_scale_path,
    parameters_from_plan,
    path_segment,
    target_path,
    target_from_plan,
)
from .gateway_state import increment_metric
from .security import canonical_digest, redact_sensitive
from .settings import parse_ols_verify
from .test_pod_create import (
    TestPodCreateSettings,
    pod_manifest as build_crashloop_test_pod_manifest,
    pod_name as build_crashloop_test_pod_name,
    review_execution_result as build_test_pod_create_review_execution_result,
)


FetchOcpJson = Callable[..., Awaitable[dict[str, Any] | None]]
SubmitOcpRequest = Callable[..., Awaitable[httpx.Response]]


@dataclass(frozen=True, slots=True)
class ActionExecutionConfig:
    openshift_api_url: str
    openshift_api_ca_file: bool | str
    action_executor_token_file: str
    action_executor_field_manager: str
    action_executor_url: str
    action_executor_shared_token: str
    test_pod_create_enabled: bool
    test_pod_create_default_image: str
    test_pod_create_name_prefix: str
    test_pod_create_app_label: str
    test_pod_create_allowed_namespaces: frozenset[str]
    test_pod_create_failure_command: tuple[str, ...]


def default_action_execution_config() -> ActionExecutionConfig:
    openshift_api_url = os.getenv("OPENSHIFT_API_URL", "").rstrip("/")
    if not openshift_api_url and os.getenv("KUBERNETES_SERVICE_HOST"):
        kubernetes_host = os.getenv("KUBERNETES_SERVICE_HOST")
        kubernetes_port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
        openshift_api_url = f"https://{kubernetes_host}:{kubernetes_port}"
    return ActionExecutionConfig(
        openshift_api_url=openshift_api_url,
        openshift_api_ca_file=parse_ols_verify(
            os.getenv(
                "OPENSHIFT_API_CA_FILE",
                "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
                if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
                else "",
            )
        ),
        action_executor_token_file=os.getenv(
            "KOMSCO_AI_ACTION_EXECUTOR_TOKEN_FILE",
            "/var/run/secrets/kubernetes.io/serviceaccount/token",
        ),
        action_executor_field_manager=os.getenv(
            "KOMSCO_AI_ACTION_EXECUTOR_FIELD_MANAGER",
            "komsco-ai-action-executor",
        ),
        action_executor_url=os.getenv("KOMSCO_AI_ACTION_EXECUTOR_URL", "").rstrip("/"),
        action_executor_shared_token=os.getenv("KOMSCO_AI_ACTION_EXECUTOR_SHARED_TOKEN", ""),
        test_pod_create_enabled=os.getenv("KOMSCO_AI_TEST_POD_CREATE_ENABLED", "").strip().lower()
        in {"1", "true", "yes", "on"},
        test_pod_create_default_image="registry.access.redhat.com/ubi9/ubi-minimal:latest",
        test_pod_create_name_prefix="aiops-test-pod",
        test_pod_create_app_label="aiops-test-pods",
        test_pod_create_allowed_namespaces=frozenset(
            item.strip()
            for item in os.getenv("KOMSCO_AI_TEST_POD_CREATE_ALLOWED_NAMESPACES", "").split(",")
            if item.strip()
        ),
        test_pod_create_failure_command=(
            "/bin/sh",
            "-c",
            "echo aiops intentional crashloop test pod; exit 1",
        ),
    )


def test_pod_create_settings(config: ActionExecutionConfig) -> TestPodCreateSettings:
    return TestPodCreateSettings(
        enabled=config.test_pod_create_enabled,
        default_image=config.test_pod_create_default_image,
        name_prefix=config.test_pod_create_name_prefix,
        app_label=config.test_pod_create_app_label,
        allowed_namespaces=config.test_pod_create_allowed_namespaces,
        failure_command=config.test_pod_create_failure_command,
    )


def read_secret_value(value: str | None, file_path: str | None) -> str | None:
    if value:
        return value
    if file_path:
        try:
            with open(file_path, encoding="utf-8") as handle:
                return handle.read().strip()
        except OSError:
            return None
    return None


def append_query(path: str, query: Mapping[str, str]) -> str:
    separator = "&" if "?" in path else "?"
    encoded = "&".join(f"{key}={value}" for key, value in query.items())
    return f"{path}{separator}{encoded}"


def executor_auth_header(config: ActionExecutionConfig | None = None) -> str:
    runtime = config or default_action_execution_config()
    token = read_secret_value(
        os.getenv("KOMSCO_AI_ACTION_EXECUTOR_BEARER_TOKEN"),
        runtime.action_executor_token_file,
    )
    if not token:
        raise HTTPException(status_code=503, detail="Action Executor service account token is not configured")
    return f"Bearer {token}"


async def fetch_ocp_json(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    required: bool = False,
    config: ActionExecutionConfig | None = None,
) -> dict[str, Any] | None:
    runtime = config or default_action_execution_config()
    if not runtime.openshift_api_url:
        if required:
            raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")
        return None
    response = await client.get(
        f"{runtime.openshift_api_url}{path}",
        headers={"Accept": "application/json", "Authorization": authorization},
    )
    if response.status_code == 404 and not required:
        return None
    if response.status_code >= 400:
        if required:
            raise HTTPException(status_code=response.status_code, detail=response.text[:1000])
        return None
    payload = response.json()
    return payload if isinstance(payload, dict) else None


async def submit_ocp_request(
    client: httpx.AsyncClient,
    authorization: str,
    *,
    method: str,
    path: str,
    content_type: str,
    body: Mapping[str, Any],
    config: ActionExecutionConfig | None = None,
) -> httpx.Response:
    runtime = config or default_action_execution_config()
    if not runtime.openshift_api_url:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")
    return await client.request(
        method,
        f"{runtime.openshift_api_url}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": authorization,
            "Content-Type": content_type,
        },
        json=body,
    )


async def fetch_executor_live_state(
    client: httpx.AsyncClient,
    authorization: str,
    plan: Mapping[str, Any],
    *,
    config: ActionExecutionConfig | None = None,
    fetch_ocp_json_func: FetchOcpJson = fetch_ocp_json,
) -> dict[str, Any]:
    target = target_from_plan(plan)
    action = action_from_plan(plan)
    live_target = await fetch_ocp_json_func(
        client,
        target_path(target),
        authorization,
        required=True,
        config=config,
    )
    live_state: dict[str, Any] = {"target": live_target or {}}
    namespace = str(target.get("namespace") or "")
    tool_name = str(action.get("toolName") or "")
    if tool_name == "set_replicas_within_bounds":
        hpas = await fetch_ocp_json_func(
            client,
            f"/apis/autoscaling/v2/namespaces/{namespace}/horizontalpodautoscalers",
            authorization,
            config=config,
        )
        items = hpas.get("items") if isinstance(hpas, Mapping) else []
        live_state["hpas"] = [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
    if tool_name == "rollback_deployment_to_revision":
        replica_sets = await fetch_ocp_json_func(
            client,
            f"/apis/apps/v1/namespaces/{namespace}/replicasets",
            authorization,
            config=config,
        )
        items = replica_sets.get("items") if isinstance(replica_sets, Mapping) else []
        live_state["replicaSets"] = (
            [item for item in items if isinstance(item, Mapping)] if isinstance(items, list) else []
        )
    return live_state


async def verify_typed_action_postcondition(
    client: httpx.AsyncClient,
    authorization: str,
    sealed_plan: Mapping[str, Any],
    *,
    config: ActionExecutionConfig | None = None,
    fetch_ocp_json_func: FetchOcpJson = fetch_ocp_json,
) -> dict[str, Any]:
    action = action_from_plan(sealed_plan)
    target = target_from_plan(sealed_plan)
    parameters = parameters_from_plan(sealed_plan)
    tool_name = str(action.get("toolName") or "")
    target_resource = await fetch_ocp_json_func(client, target_path(target), authorization, config=config)

    if tool_name == "evict_one_unhealthy_controller_owned_pod":
        if target_resource is None:
            return {"status": "verified", "reason": "target_pod_removed"}
        deletion_timestamp = target_resource.get("metadata", {}).get("deletionTimestamp")
        if deletion_timestamp:
            return {
                "status": "verified",
                "reason": "target_pod_deleting",
                "deletionTimestamp": deletion_timestamp,
            }
        observed_uid = str(target_resource.get("metadata", {}).get("uid") or "")
        if observed_uid != str(target.get("uid") or ""):
            return {"status": "verified", "reason": "target_pod_replaced"}
        return {"status": "verification_failed", "reason": "target_pod_still_present"}

    if target_resource is None:
        return {"status": "verification_failed", "reason": "target_resource_unavailable"}

    if tool_name == "rollout_restart_deployment":
        annotations = (
            target_resource.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("annotations", {})
        )
        restarted_at = str(parameters.get("restartedAt") or "")
        if isinstance(annotations, Mapping) and annotations.get("kubectl.kubernetes.io/restartedAt") == restarted_at:
            return {"status": "verified", "reason": "restart_annotation_observed"}
        return {"status": "verification_failed", "reason": "restart_annotation_not_observed"}

    if tool_name == "set_replicas_within_bounds":
        scale = await fetch_ocp_json_func(client, deployment_scale_path(target), authorization, config=config)
        replicas = parameters.get("replicas")
        observed = scale.get("spec", {}).get("replicas") if isinstance(scale, Mapping) else None
        if observed == replicas:
            return {"status": "verified", "reason": "scale_spec_matches", "observedReplicas": observed}
        return {
            "status": "verification_failed",
            "reason": "scale_spec_mismatch",
            "observedReplicas": observed,
        }

    if tool_name == "rollback_deployment_to_revision":
        annotations = (
            target_resource.get("spec", {})
            .get("template", {})
            .get("metadata", {})
            .get("annotations", {})
        )
        if isinstance(annotations, Mapping) and annotations.get("aiops.komsco/rollback-revision"):
            return {
                "status": "verified",
                "reason": "rollback_template_annotation_observed",
                "rollbackRevision": annotations.get("aiops.komsco/rollback-revision"),
            }
        return {"status": "verification_failed", "reason": "rollback_annotation_not_observed"}

    if tool_name == "set_hpa_bounds":
        spec = target_resource.get("spec", {}) if isinstance(target_resource.get("spec"), Mapping) else {}
        if spec.get("minReplicas") == parameters.get("minReplicas") and spec.get("maxReplicas") == parameters.get("maxReplicas"):
            return {"status": "verified", "reason": "hpa_bounds_match"}
        return {
            "status": "verification_failed",
            "reason": "hpa_bounds_mismatch",
            "observed": {
                "minReplicas": spec.get("minReplicas"),
                "maxReplicas": spec.get("maxReplicas"),
            },
        }

    if tool_name == "set_deployment_container_command":
        container_name = str(parameters.get("containerName") or "")
        command = parameters.get("command") if isinstance(parameters.get("command"), list) else []
        containers = (
            target_resource.get("spec", {})
            .get("template", {})
            .get("spec", {})
            .get("containers", [])
        )
        observed_command = None
        if isinstance(containers, list):
            for container in containers:
                if isinstance(container, Mapping) and container.get("name") == container_name:
                    observed_command = container.get("command")
                    break
        if observed_command == command:
            return {
                "status": "verified",
                "reason": "deployment_container_command_matches",
                "containerName": container_name,
            }
        return {
            "status": "verification_failed",
            "reason": "deployment_container_command_mismatch",
            "containerName": container_name,
            "observedCommand": observed_command,
        }

    return {"status": "inconclusive", "reason": "no_postcondition_for_tool"}


def namespace_cleanup_review_execution_result(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    target = target_from_plan(sealed_plan)
    target_name = str(target.get("name") or target.get("namespace") or "namespace")
    return {
        "mutationOutcome": {
            "status": "review_recorded",
            "reason": f"namespace cleanup review recorded for {target_name}; no namespace deletion executed",
            "httpStatus": 200,
        },
        "remediationOutcome": {
            "status": "verified",
            "reason": f"{target_name} namespace cleanup review recorded without mutation",
        },
        "executorTrace": {
            "mutationSubmitted": False,
            "reviewOnly": True,
            "toolName": "namespace_cleanup_review",
            "target": target,
        },
    }


def test_pod_create_review_execution_result(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    target = target_from_plan(sealed_plan)
    action = action_from_plan(sealed_plan)
    parameters = action.get("parameters") if isinstance(action.get("parameters"), Mapping) else {}
    return build_test_pod_create_review_execution_result(target, parameters)


async def create_crashloop_test_pods_execution_result(
    sealed_plan: Mapping[str, Any],
    client: httpx.AsyncClient,
    authorization: str,
    *,
    config: ActionExecutionConfig | None = None,
    submit_ocp_request_func: SubmitOcpRequest = submit_ocp_request,
    fetch_ocp_json_func: FetchOcpJson = fetch_ocp_json,
) -> dict[str, Any]:
    runtime = config or default_action_execution_config()
    target = target_from_plan(sealed_plan)
    parameters = parameters_from_plan(sealed_plan)
    namespace = str(target.get("namespace") or target.get("name") or "")
    count = int(parameters.get("count") or 0)
    image = str(parameters.get("image") or runtime.test_pod_create_default_image)
    name_prefix = str(parameters.get("namePrefix") or runtime.test_pod_create_name_prefix)

    if not runtime.test_pod_create_enabled:
        return {
            "mutationOutcome": {
                "status": "mutation_rejected",
                "reason": "CrashLoop test Pod creation is disabled in product mode",
                "httpStatus": 403,
            },
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False, "toolName": "create_crashloop_test_pods", "target": target},
        }
    if count < 1 or count > 5:
        return {
            "mutationOutcome": {
                "status": "mutation_rejected",
                "reason": "test Pod count must be explicitly set between 1 and 5",
                "httpStatus": 400,
            },
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False, "toolName": "create_crashloop_test_pods", "target": target},
        }
    if namespace not in runtime.test_pod_create_allowed_namespaces:
        return {
            "mutationOutcome": {
                "status": "mutation_rejected",
                "reason": f"namespace `{namespace}` is outside the test Pod creation allowlist",
                "httpStatus": 403,
            },
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False, "toolName": "create_crashloop_test_pods", "target": target},
        }
    if image != runtime.test_pod_create_default_image:
        return {
            "mutationOutcome": {
                "status": "mutation_rejected",
                "reason": "test Pod image is fixed by policy",
                "httpStatus": 400,
            },
            "remediationOutcome": {"status": "not_remediated"},
            "executorTrace": {"mutationSubmitted": False, "toolName": "create_crashloop_test_pods", "target": target},
        }

    plan_digest = ""
    if isinstance(sealed_plan.get("digest"), Mapping):
        plan_digest = str(sealed_plan["digest"].get("planDigest") or "")
    metadata = sealed_plan.get("metadata") if isinstance(sealed_plan.get("metadata"), Mapping) else {}
    request_id = canonical_digest(
        {
            "idempotencyKey": metadata.get("idempotencyKey") or "",
            "planDigest": plan_digest,
        }
    ).removeprefix("sha256:")[:10]
    manifests = [
        build_crashloop_test_pod_manifest(
            image=image,
            index=index,
            namespace=namespace,
            pod_name=build_crashloop_test_pod_name(name_prefix, request_id, index),
            request_id=request_id,
            settings=test_pod_create_settings(runtime),
        )
        for index in range(1, count + 1)
    ]
    pods_path = f"/api/v1/namespaces/{path_segment(namespace)}/pods"
    dry_run_path = append_query(
        pods_path,
        {"dryRun": "All", "fieldManager": runtime.action_executor_field_manager},
    )
    mutation_path = append_query(
        pods_path,
        {"fieldManager": runtime.action_executor_field_manager},
    )

    dry_run_errors: list[str] = []
    for manifest in manifests:
        response = await submit_ocp_request_func(
            client,
            authorization,
            method="POST",
            path=dry_run_path,
            content_type="application/json",
            body=manifest,
        )
        if response.status_code not in {200, 201}:
            dry_run_errors.append(f"{manifest['metadata']['name']}: HTTP {response.status_code} {response.text[:300]}")
    increment_metric("aiops_execution_dry_run_total")
    if dry_run_errors:
        return {
            "mutationOutcome": {
                "status": "mutation_failed",
                "reason": "server_side_dry_run_failed",
                "httpStatus": 400,
                "body": "; ".join(dry_run_errors)[:1000],
            },
            "remediationOutcome": {"status": "mutation_failed"},
            "executorTrace": {
                "dryRunPath": dry_run_path,
                "mutationSubmitted": False,
                "toolName": "create_crashloop_test_pods",
                "target": target,
            },
        }

    created: list[str] = []
    mutation_errors: list[str] = []
    for manifest in manifests:
        response = await submit_ocp_request_func(
            client,
            authorization,
            method="POST",
            path=mutation_path,
            content_type="application/json",
            body=manifest,
        )
        if response.status_code in {200, 201}:
            created.append(str(manifest["metadata"]["name"]))
        else:
            mutation_errors.append(f"{manifest['metadata']['name']}: HTTP {response.status_code} {response.text[:300]}")

    label_selector = quote(f"app={runtime.test_pod_create_app_label},aiops.komsco/request-id={request_id}", safe="")
    observed_payload = await fetch_ocp_json_func(
        client,
        f"/api/v1/namespaces/{path_segment(namespace)}/pods?labelSelector={label_selector}",
        authorization,
    )
    items = observed_payload.get("items") if isinstance(observed_payload, Mapping) else []
    observed = len(items) if isinstance(items, list) else 0
    ok = not mutation_errors and observed == count
    if ok:
        increment_metric("aiops_execution_mutation_succeeded_total")
    else:
        increment_metric("aiops_execution_mutation_failed_total")
    return {
        "mutationOutcome": {
            "status": "mutation_succeeded" if ok else "mutation_partial" if created else "mutation_failed",
            "reason": (
                f"created {observed}/{count} intentional CrashLoopBackOff test Pods"
                if ok
                else f"created {len(created)}/{count}; {'; '.join(mutation_errors)[:700]}"
            ),
            "httpStatus": 201 if ok else 207 if created else 500,
        },
        "remediationOutcome": {
            "status": "verified" if ok else "verification_failed",
            "reason": f"observed {observed}/{count} Pods with app={runtime.test_pod_create_app_label} and request-id={request_id}",
        },
        "executorTrace": {
            "createdPods": created,
            "dryRunPath": dry_run_path,
            "mutationPath": mutation_path,
            "mutationSubmitted": bool(created),
            "requestId": request_id,
            "target": target,
            "toolName": "create_crashloop_test_pods",
            "verificationSelector": f"app={runtime.test_pod_create_app_label},aiops.komsco/request-id={request_id}",
        },
    }


def pod_diagnostic_review_execution_result(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    target = target_from_plan(sealed_plan)
    target_label = "/".join(
        part for part in [str(target.get("namespace") or ""), str(target.get("name") or "")] if part
    ) or "pod"
    return {
        "mutationOutcome": {
            "status": "review_recorded",
            "reason": f"pod diagnostic review recorded for {target_label}; no Pod eviction or restart was executed",
            "httpStatus": 200,
        },
        "remediationOutcome": {
            "status": "verified",
            "reason": f"{target_label} diagnostic/fix review recorded without mutation",
        },
        "executorTrace": {
            "mutationSubmitted": False,
            "reviewOnly": True,
            "target": target,
            "toolName": "pod_diagnostic_review",
        },
    }


def pod_fix_or_rollback_review_execution_result(sealed_plan: Mapping[str, Any]) -> dict[str, Any]:
    target = target_from_plan(sealed_plan)
    target_label = "/".join(
        part for part in [str(target.get("namespace") or ""), str(target.get("name") or "")] if part
    ) or "pod"
    return {
        "mutationOutcome": {
            "status": "review_recorded",
            "reason": f"pod fix/rollback review recorded for {target_label}; no Pod restart, eviction, patch, or rollback was executed",
            "httpStatus": 200,
        },
        "remediationOutcome": {
            "status": "verified",
            "reason": f"{target_label} fix/rollback review recorded without mutation",
        },
        "executorTrace": {
            "mutationSubmitted": False,
            "reviewOnly": True,
            "target": target,
            "toolName": "pod_fix_or_rollback_review",
        },
    }


async def execute_typed_action_plan(
    sealed_plan: Mapping[str, Any],
    *,
    config: ActionExecutionConfig | None = None,
    fetch_ocp_json_func: FetchOcpJson = fetch_ocp_json,
    submit_ocp_request_func: SubmitOcpRequest = submit_ocp_request,
) -> dict[str, Any]:
    runtime = config or default_action_execution_config()
    if not runtime.openshift_api_url:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    action = action_from_plan(sealed_plan)
    tool_name = str(action.get("toolName") or "")
    if tool_name == "namespace_cleanup_review":
        return namespace_cleanup_review_execution_result(sealed_plan)
    if tool_name == "test_pod_create_review":
        return test_pod_create_review_execution_result(sealed_plan)
    if tool_name == "pod_diagnostic_review":
        return pod_diagnostic_review_execution_result(sealed_plan)
    if tool_name == "pod_fix_or_rollback_review":
        return pod_fix_or_rollback_review_execution_result(sealed_plan)

    executor_auth = executor_auth_header(runtime)
    async with httpx.AsyncClient(
        verify=runtime.openshift_api_ca_file,
        timeout=httpx.Timeout(30.0, connect=5.0),
    ) as client:
        if tool_name == "create_crashloop_test_pods":
            return await create_crashloop_test_pods_execution_result(
                sealed_plan,
                client,
                executor_auth,
                config=runtime,
                submit_ocp_request_func=submit_ocp_request_func,
                fetch_ocp_json_func=fetch_ocp_json_func,
            )

        live_state = await fetch_executor_live_state(
            client,
            executor_auth,
            sealed_plan,
            config=runtime,
            fetch_ocp_json_func=fetch_ocp_json_func,
        )
        try:
            mutation = build_mutation_request(
                sealed_plan,
                live_target=live_state["target"],
                hpas=live_state.get("hpas") or (),
                replica_sets=live_state.get("replicaSets") or (),
            )
        except AiopsCoreError as exc:
            raise HTTPException(status_code=409, detail={"reason": exc.reason, "message": str(exc)}) from exc

        dry_run_path = append_query(
            mutation.path,
            {
                "dryRun": "All",
                "fieldManager": runtime.action_executor_field_manager,
            },
        )
        dry_run_response = await submit_ocp_request_func(
            client,
            executor_auth,
            method=mutation.method,
            path=dry_run_path,
            content_type=mutation.content_type,
            body=mutation.body,
        )
        increment_metric("aiops_execution_dry_run_total")
        if dry_run_response.status_code not in mutation.expected_statuses:
            return {
                "mutationOutcome": {
                    "status": "mutation_failed",
                    "reason": "server_side_dry_run_failed",
                    "httpStatus": dry_run_response.status_code,
                    "body": dry_run_response.text[:1000],
                },
                "remediationOutcome": {"status": "mutation_failed"},
                "executorTrace": {"dryRunPath": dry_run_path, "mutationSubmitted": False},
            }

        mutate_path = append_query(
            mutation.path,
            {
                "fieldManager": runtime.action_executor_field_manager,
            },
        )
        mutation_response = await submit_ocp_request_func(
            client,
            executor_auth,
            method=mutation.method,
            path=mutate_path,
            content_type=mutation.content_type,
            body=mutation.body,
        )
        if mutation_response.status_code not in mutation.expected_statuses:
            increment_metric("aiops_execution_mutation_failed_total")
            return {
                "mutationOutcome": {
                    "status": "mutation_failed",
                    "reason": "kubernetes_api_request_failed",
                    "httpStatus": mutation_response.status_code,
                    "body": mutation_response.text[:1000],
                },
                "remediationOutcome": {"status": "mutation_failed"},
                "executorTrace": {
                    "dryRunPath": dry_run_path,
                    "mutationPath": mutate_path,
                    "mutationSubmitted": True,
                },
            }

        postcondition = await verify_typed_action_postcondition(
            client,
            executor_auth,
            sealed_plan,
            config=runtime,
            fetch_ocp_json_func=fetch_ocp_json_func,
        )
        increment_metric("aiops_execution_mutation_succeeded_total")
        return {
            "mutationOutcome": {
                "status": "mutation_succeeded",
                "reason": "typed_action_executed",
                "httpStatus": mutation_response.status_code,
            },
            "remediationOutcome": postcondition,
            "executorTrace": {
                "dryRunPath": dry_run_path,
                "mutationPath": mutate_path,
                "mutationSubmitted": True,
                "toolName": action_from_plan(sealed_plan).get("toolName"),
                "target": target_from_plan(sealed_plan),
            },
        }


async def execute_action_with_executor(
    sealed_plan: Mapping[str, Any],
    grant_reference: Mapping[str, Any],
    *,
    config: ActionExecutionConfig | None = None,
    fallback_authorization: str | None = None,
    fetch_ocp_json_func: FetchOcpJson = fetch_ocp_json,
    submit_ocp_request_func: SubmitOcpRequest = submit_ocp_request,
) -> dict[str, Any]:
    runtime = config or default_action_execution_config()
    action = action_from_plan(sealed_plan)
    tool_name = str(action.get("toolName") or "")
    if tool_name == "namespace_cleanup_review":
        return namespace_cleanup_review_execution_result(sealed_plan)
    if tool_name == "test_pod_create_review":
        return test_pod_create_review_execution_result(sealed_plan)
    if tool_name == "pod_diagnostic_review":
        return pod_diagnostic_review_execution_result(sealed_plan)
    if tool_name == "pod_fix_or_rollback_review":
        return pod_fix_or_rollback_review_execution_result(sealed_plan)

    if tool_name == "create_crashloop_test_pods":
        action_auth = fallback_authorization or executor_auth_header(runtime)
        async with httpx.AsyncClient(
            verify=runtime.openshift_api_ca_file,
            timeout=httpx.Timeout(30.0, connect=5.0),
        ) as client:
            return await create_crashloop_test_pods_execution_result(
                sealed_plan,
                client,
                action_auth,
                config=runtime,
                submit_ocp_request_func=submit_ocp_request_func,
                fetch_ocp_json_func=fetch_ocp_json_func,
            )

    if not runtime.action_executor_url:
        return await execute_typed_action_plan(
            sealed_plan,
            config=runtime,
            fetch_ocp_json_func=fetch_ocp_json_func,
            submit_ocp_request_func=submit_ocp_request_func,
        )

    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if runtime.action_executor_shared_token:
        headers["Authorization"] = f"Bearer {runtime.action_executor_shared_token}"

    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0, connect=5.0)) as client:
        response = await client.post(
            f"{runtime.action_executor_url}/v1/executor/actions/execute",
            headers=headers,
            json={
                "sealedActionPlan": redact_sensitive(dict(sealed_plan)),
                "executionGrantRef": redact_sensitive(dict(grant_reference)),
            },
        )

    if response.status_code >= 400:
        return {
            "mutationOutcome": {
                "status": "mutation_failed",
                "reason": "action_executor_request_failed",
                "httpStatus": response.status_code,
                "body": response.text[:1000],
            },
            "remediationOutcome": {"status": "mutation_failed"},
            "executorTrace": {
                "executorUrlConfigured": True,
                "mutationSubmitted": False,
            },
        }

    payload = response.json()
    spec = payload.get("spec") if isinstance(payload, Mapping) else {}
    if isinstance(spec, Mapping):
        return dict(spec)

    return {
        "mutationOutcome": {
            "status": "indeterminate",
            "reason": "action_executor_response_invalid",
        },
        "remediationOutcome": {"status": "inconclusive"},
        "executorTrace": {
            "executorUrlConfigured": True,
            "mutationSubmitted": True,
        },
    }
