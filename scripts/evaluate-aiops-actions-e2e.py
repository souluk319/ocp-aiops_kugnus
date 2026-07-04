#!/usr/bin/env python3
"""Run live AIOps action and host-diagnostic e2e checks through the gateway API."""

from __future__ import annotations

import argparse
import json
import socket
import subprocess
import time
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - CLI dependency diagnostic path
    httpx = None


DEFAULT_NAMESPACE = "komsco-ai-dev"
DEFAULT_REPORT_PATH = Path("/tmp/komsco-ai-actions-e2e.json")


class HostDiagnosticError(RuntimeError):
    def __init__(self, message: str, request_id: str) -> None:
        super().__init__(message)
        self.request_id = request_id


def run_oc(
    args: list[str],
    *,
    input_text: str | None = None,
    check: bool = True,
    timeout: int = 60,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["oc", *args],
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=timeout,
    )
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"oc {' '.join(args)} failed with {completed.returncode}: {completed.stderr.strip()}"
        )
    return completed


def oc_json(args: list[str], *, timeout: int = 60) -> Mapping[str, Any]:
    completed = run_oc([*args, "-o", "json"], timeout=timeout)
    payload = json.loads(completed.stdout)
    if not isinstance(payload, Mapping):
        raise RuntimeError(f"oc {' '.join(args)} did not return a JSON object")
    return payload


def oc_check(name: str, args: list[str], *, timeout: int = 60) -> dict[str, Any]:
    completed = run_oc(args, check=False, timeout=timeout)
    return {
        "name": name,
        "command": "oc " + " ".join(args),
        "ok": completed.returncode == 0,
        "returnCode": completed.returncode,
        "stdout": completed.stdout.strip()[:1000],
        "stderr": completed.stderr.strip()[:1000],
    }


def oc_apply(items: list[Mapping[str, Any]]) -> None:
    payload = {"apiVersion": "v1", "kind": "List", "items": items}
    run_oc(["apply", "-f", "-"], input_text=json.dumps(payload), timeout=120)


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def selector(prefix: str) -> str:
    return f"aiops.komsco/e2e-run={prefix}"


def labels(prefix: str, app_name: str) -> dict[str, str]:
    return {"app": app_name, "aiops.komsco/e2e-run": prefix}


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def require_httpx():
    if httpx is None:
        raise RuntimeError(
            "Python dependency 'httpx' is required for live action e2e. "
            "Use komsco-ai-gateway/.venv/bin/python or install the gateway test dependencies."
        )
    return httpx


def auth_can_i_check(
    verb: str,
    resource: str,
    *,
    namespace: str | None = None,
    timeout: int = 30,
) -> dict[str, Any]:
    args = ["auth", "can-i", verb, resource]
    if namespace:
        args.extend(["-n", namespace])
    completed = run_oc(args, check=False, timeout=timeout)
    allowed = completed.stdout.strip().lower() == "yes"
    return {
        "name": f"can {verb} {resource}" + (f" in {namespace}" if namespace else ""),
        "command": "oc " + " ".join(args),
        "ok": completed.returncode == 0 and allowed,
        "returnCode": completed.returncode,
        "allowed": allowed,
        "stdout": completed.stdout.strip()[:300],
        "stderr": completed.stderr.strip()[:500],
    }


@contextmanager
def port_forward(namespace: str, resource: str, remote_port: int):
    local_port = free_port()
    proc = subprocess.Popen(
        ["oc", "-n", namespace, "port-forward", resource, f"{local_port}:{remote_port}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        yield f"https://127.0.0.1:{local_port}", proc
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def wait_for(
    name: str,
    callback: Callable[[], Any],
    *,
    timeout_seconds: int = 120,
    interval_seconds: float = 2.0,
) -> Any:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            value = callback()
            if value:
                return value
        except Exception as exc:  # noqa: BLE001 - report the last polling error.
            last_error = exc
        time.sleep(interval_seconds)
    suffix = f": {last_error}" if last_error else ""
    raise TimeoutError(f"timed out waiting for {name}{suffix}")


def wait_gateway_health(gateway_url: str, proc: subprocess.Popen[str]) -> None:
    httpx_module = require_httpx()

    def check() -> bool:
        if proc.poll() is not None:
            stderr = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"gateway port-forward exited early: {stderr.strip()}")
        try:
            response = httpx_module.get(f"{gateway_url}/healthz", verify=False, timeout=5.0)
        except httpx_module.HTTPError:
            return False
        return response.status_code == 200

    wait_for("gateway /healthz", check, timeout_seconds=60, interval_seconds=1.0)


def apply_e2e_rbac(namespace: str, prefix: str) -> str:
    role_name = f"{prefix}-approver"
    binding_name = f"{prefix}-approver"
    service_account_name = f"{prefix}-approver"
    oc_apply(
        [
            {
                "apiVersion": "v1",
                "kind": "ServiceAccount",
                "metadata": {"name": service_account_name, "namespace": namespace, "labels": labels(prefix, service_account_name)},
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRole",
                "metadata": {"name": role_name, "labels": labels(prefix, role_name)},
                "rules": [
                    {
                        "apiGroups": ["console.openshift.io"],
                        "resources": ["consoleplugins"],
                        "verbs": ["get"],
                    },
                    {
                        "apiGroups": ["apps"],
                        "resources": ["deployments"],
                        "verbs": ["get", "list", "watch", "patch", "update"],
                    },
                    {
                        "apiGroups": ["apps"],
                        "resources": ["deployments/scale"],
                        "verbs": ["get", "patch", "update"],
                    },
                    {
                        "apiGroups": ["apps"],
                        "resources": ["replicasets"],
                        "verbs": ["get", "list", "watch"],
                    },
                    {
                        "apiGroups": ["autoscaling"],
                        "resources": ["horizontalpodautoscalers"],
                        "verbs": ["get", "list", "watch", "patch", "update"],
                    },
                    {
                        "apiGroups": [""],
                        "resources": ["pods"],
                        "verbs": ["get", "list", "watch"],
                    },
                    {
                        "apiGroups": [""],
                        "resources": ["pods/eviction"],
                        "verbs": ["create"],
                    },
                    {
                        "apiGroups": ["policy"],
                        "resources": ["poddisruptionbudgets"],
                        "verbs": ["get", "list", "watch"],
                    },
                ],
            },
            {
                "apiVersion": "rbac.authorization.k8s.io/v1",
                "kind": "ClusterRoleBinding",
                "metadata": {"name": binding_name, "labels": labels(prefix, binding_name)},
                "roleRef": {
                    "apiGroup": "rbac.authorization.k8s.io",
                    "kind": "ClusterRole",
                    "name": role_name,
                },
                "subjects": [
                    {
                        "kind": "ServiceAccount",
                        "name": service_account_name,
                        "namespace": namespace,
                    }
                ],
            },
        ]
    )
    return service_account_name


def deployment_manifest(namespace: str, prefix: str, name: str, image: str, *, unready: bool = False) -> dict[str, Any]:
    container: dict[str, Any] = {
        "name": "sleeper",
        "image": image,
        "command": ["python", "-c", "import time; time.sleep(3600)"],
    }
    if unready:
        container["readinessProbe"] = {
            "exec": {"command": ["python", "-c", "raise SystemExit(1)"]},
            "initialDelaySeconds": 1,
            "periodSeconds": 2,
            "failureThreshold": 1,
        }
    return {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": name, "namespace": namespace, "labels": labels(prefix, name)},
        "spec": {
            "replicas": 1,
            "selector": {"matchLabels": {"app": name}},
            "template": {
                "metadata": {"labels": labels(prefix, name)},
                "spec": {"containers": [container]},
            },
        },
    }


def hpa_manifest(namespace: str, prefix: str, name: str, target_name: str) -> dict[str, Any]:
    return {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": name, "namespace": namespace, "labels": labels(prefix, name)},
        "spec": {
            "minReplicas": 1,
            "maxReplicas": 3,
            "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": target_name},
            "metrics": [
                {
                    "type": "Resource",
                    "resource": {
                        "name": "cpu",
                        "target": {"type": "Utilization", "averageUtilization": 50},
                    },
                }
            ],
        },
    }


def e2e_resource_names(prefix: str) -> dict[str, str]:
    return {
        "restart": f"{prefix}-restart",
        "scale": f"{prefix}-scale",
        "rollback": f"{prefix}-rollback",
        "badpod": f"{prefix}-badpod",
        "hpaTarget": f"{prefix}-hpa-target",
        "hpa": f"{prefix}-hpa",
    }


def apply_workloads(namespace: str, prefix: str, image: str) -> dict[str, str]:
    names = e2e_resource_names(prefix)
    oc_apply(
        [
            deployment_manifest(namespace, prefix, names["restart"], image),
            deployment_manifest(namespace, prefix, names["scale"], image),
            deployment_manifest(namespace, prefix, names["rollback"], image),
            deployment_manifest(namespace, prefix, names["badpod"], image, unready=True),
            deployment_manifest(namespace, prefix, names["hpaTarget"], image),
            hpa_manifest(namespace, prefix, names["hpa"], names["hpaTarget"]),
        ]
    )
    for key in ("restart", "scale", "rollback", "hpaTarget"):
        run_oc(
            ["rollout", "status", f"deployment/{names[key]}", "-n", namespace, "--timeout=180s"],
            timeout=210,
        )
    run_oc(
        ["set", "env", f"deployment/{names['rollback']}", "-n", namespace, "AIOPS_E2E_REVISION=two"],
        timeout=60,
    )
    run_oc(
        ["rollout", "status", f"deployment/{names['rollback']}", "-n", namespace, "--timeout=180s"],
        timeout=210,
    )
    wait_for(
        "unready e2e pod",
        lambda: first_pod(namespace, f"app={names['badpod']}", ready=False),
        timeout_seconds=180,
    )
    oc_json(["get", "hpa", names["hpa"], "-n", namespace])
    return names


def pod_ready(pod: Mapping[str, Any]) -> bool:
    conditions = pod.get("status", {}).get("conditions", [])
    if not isinstance(conditions, list):
        return False
    return any(
        isinstance(condition, Mapping)
        and condition.get("type") == "Ready"
        and condition.get("status") == "True"
        for condition in conditions
    )


def first_pod(namespace: str, label_selector: str, *, ready: bool | None = None) -> Mapping[str, Any] | None:
    payload = oc_json(["get", "pods", "-n", namespace, "-l", label_selector])
    items = [item for item in payload.get("items", []) if isinstance(item, Mapping)]
    items.sort(key=lambda item: str(item.get("metadata", {}).get("creationTimestamp") or ""))
    for pod in items:
        if pod.get("status", {}).get("phase") not in {"Running", "Pending"}:
            continue
        if ready is None or pod_ready(pod) is ready:
            return pod
    return None


def target_from_resource(resource: Mapping[str, Any], api_version: str, kind: str) -> dict[str, str]:
    metadata = resource.get("metadata", {})
    return {
        "apiVersion": api_version,
        "kind": kind,
        "namespace": str(metadata.get("namespace") or ""),
        "name": str(metadata.get("name") or ""),
        "uid": str(metadata.get("uid") or ""),
    }


def api_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/json"}


def api_post(client: httpx.Client, path: str, token: str, payload: Mapping[str, Any]) -> Mapping[str, Any]:
    response = client.post(path, headers=api_headers(token), json=payload)
    if response.status_code >= 400:
        raise RuntimeError(f"POST {path} failed with {response.status_code}: {response.text[:1000]}")
    body = response.json()
    if not isinstance(body, Mapping):
        raise RuntimeError(f"POST {path} returned non-object JSON")
    return body


def api_get(client: httpx.Client, path: str, token: str) -> Mapping[str, Any]:
    response = client.get(path, headers=api_headers(token))
    if response.status_code >= 400:
        raise RuntimeError(f"GET {path} failed with {response.status_code}: {response.text[:1000]}")
    body = response.json()
    if not isinstance(body, Mapping):
        raise RuntimeError(f"GET {path} returned non-object JSON")
    return body


def run_action(
    client: httpx.Client,
    *,
    requester_token: str,
    approver_token: str,
    namespace: str,
    prefix: str,
    tool_name: str,
    target: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> dict[str, Any]:
    incident_id = f"inc-{prefix}-{tool_name}"
    proposal = api_post(
        client,
        "/v1/actions/proposals",
        requester_token,
        {
            "incidentId": incident_id,
            "runId": f"run-{prefix}",
            "toolName": tool_name,
            "target": target,
            "parameters": parameters,
        },
    )
    plan = api_post(
        client,
        "/v1/actions/plans",
        requester_token,
        {"proposalId": proposal["metadata"]["name"]},
    )
    sealed_plan = plan["spec"]["sealedActionPlan"]
    plan_digest = sealed_plan["digest"]["planDigest"]
    approval = api_post(
        client,
        "/v1/actions/approvals",
        approver_token,
        {"planId": plan["metadata"]["name"], "expectedPlanDigest": plan_digest},
    )
    execution = api_post(
        client,
        "/v1/actions/execute",
        approver_token,
        {
            "approvalId": approval["metadata"]["name"],
            "planId": plan["metadata"]["name"],
            "expectedPlanDigest": plan_digest,
        },
    )
    spec = execution["spec"]
    mutation_status = spec.get("mutationOutcome", {}).get("status")
    remediation_status = spec.get("remediationOutcome", {}).get("status")
    if mutation_status != "mutation_succeeded" or remediation_status != "verified":
        raise RuntimeError(
            f"{tool_name} did not verify: mutation={mutation_status} remediation={remediation_status}"
        )
    return {
        "toolName": tool_name,
        "namespace": namespace,
        "target": target,
        "proposalId": proposal["metadata"]["name"],
        "planId": plan["metadata"]["name"],
        "approvalId": approval["metadata"]["name"],
        "executionId": execution["metadata"]["name"],
        "mutationOutcome": spec.get("mutationOutcome"),
        "remediationOutcome": spec.get("remediationOutcome"),
    }


def run_host_diagnostic(
    client: httpx.Client,
    *,
    token: str,
    prefix: str,
) -> dict[str, Any]:
    nodes = oc_json(["get", "nodes"])
    node = next((item for item in nodes.get("items", []) if isinstance(item, Mapping)), None)
    if not node:
        raise RuntimeError("no node available for host diagnostic e2e")
    metadata = node.get("metadata", {})
    until = datetime.now(UTC)
    since = until - timedelta(minutes=5)
    request = api_post(
        client,
        "/v1/diagnostics/requests",
        token,
        {
            "incidentId": f"inc-{prefix}-hostdiag",
            "runId": f"run-{prefix}",
            "targetNode": {
                "name": str(metadata.get("name") or ""),
                "uid": str(metadata.get("uid") or ""),
            },
            "collector": "node_os_readonly_triage",
            "timeRange": {
                "since": since.isoformat().replace("+00:00", "Z"),
                "until": until.isoformat().replace("+00:00", "Z"),
            },
            "limits": {"deadline": "30s", "maxBytes": 1048576, "maxLines": 5000},
        },
    )
    request_id = request["metadata"]["name"]

    def fetch_terminal() -> Mapping[str, Any] | None:
        current = api_get(client, f"/v1/diagnostics/requests/{request_id}", token)
        status = current.get("spec", {}).get("status", {})
        phase = str(status.get("phase") or "")
        if phase in {"collector_succeeded", "collector_completed", "collector_failed"}:
            return current
        controller = status.get("controllerSubmission")
        if isinstance(controller, Mapping):
            controller_phase = str(controller.get("spec", {}).get("phase") or "")
            if controller_phase in {"completed", "succeeded", "failed"}:
                return current
        return None

    try:
        terminal = wait_for("host diagnostic completion", fetch_terminal, timeout_seconds=180)
    except TimeoutError as exc:
        raise HostDiagnosticError(str(exc), request_id) from exc
    phase = str(terminal.get("spec", {}).get("status", {}).get("phase") or "")
    if phase not in {"collector_succeeded", "collector_completed"}:
        raise RuntimeError(f"host diagnostic did not succeed: {phase}")
    return {
        "requestId": request_id,
        "targetNode": request["spec"]["candidate"]["targetNode"],
        "phase": "collector_succeeded" if phase == "collector_completed" else phase,
    }


def cleanup(namespace: str, prefix: str, diagnostic_request_id: str | None) -> None:
    run_oc(
        ["delete", "deployment,hpa", "-n", namespace, "-l", selector(prefix), "--ignore-not-found"],
        check=False,
        timeout=120,
    )
    run_oc(
        ["delete", "serviceaccount", f"{prefix}-approver", "-n", namespace, "--ignore-not-found"],
        check=False,
        timeout=60,
    )
    run_oc(["delete", "clusterrolebinding", f"{prefix}-approver", "--ignore-not-found"], check=False, timeout=60)
    run_oc(["delete", "clusterrole", f"{prefix}-approver", "--ignore-not-found"], check=False, timeout=60)
    if diagnostic_request_id:
        run_oc(
            [
                "delete",
                "job",
                "-n",
                namespace,
                "-l",
                f"aiops.komsco/request-id={diagnostic_request_id}",
                "--ignore-not-found",
            ],
            check=False,
            timeout=120,
        )


def plan_only_report(namespace: str, prefix: str, image: str) -> dict[str, Any]:
    names = e2e_resource_names(prefix)
    return {
        "ok": True,
        "mode": "plan-only",
        "clusterCallsExecuted": False,
        "wouldMutateClusterInLiveMode": True,
        "namespace": namespace,
        "prefix": prefix,
        "image": image,
        "generatedAt": now_rfc3339(),
        "plannedResources": [
            {
                "kind": "ServiceAccount",
                "namespace": namespace,
                "name": f"{prefix}-approver",
                "purpose": "separate approver identity for approval/execution checks",
            },
            {
                "kind": "ClusterRole",
                "name": f"{prefix}-approver",
                "purpose": "temporary e2e permissions for deployments, HPA, pods/eviction",
            },
            {
                "kind": "ClusterRoleBinding",
                "name": f"{prefix}-approver",
                "purpose": "bind temporary approver ServiceAccount",
            },
            {
                "kind": "Deployment",
                "namespace": namespace,
                "name": names["restart"],
                "purpose": "rollout_restart_deployment target",
            },
            {
                "kind": "Deployment",
                "namespace": namespace,
                "name": names["scale"],
                "purpose": "set_replicas_within_bounds target",
            },
            {
                "kind": "Deployment",
                "namespace": namespace,
                "name": names["rollback"],
                "purpose": "rollback_deployment_to_revision target",
            },
            {
                "kind": "Deployment",
                "namespace": namespace,
                "name": names["badpod"],
                "purpose": "evict_one_unhealthy_controller_owned_pod target with failing readiness probe",
            },
            {
                "kind": "Deployment",
                "namespace": namespace,
                "name": names["hpaTarget"],
                "purpose": "set_hpa_bounds scale target",
            },
            {
                "kind": "HorizontalPodAutoscaler",
                "namespace": namespace,
                "name": names["hpa"],
                "purpose": "set_hpa_bounds target",
            },
        ],
        "plannedActionLifecycle": [
            {
                "toolName": "rollout_restart_deployment",
                "target": f"Deployment/{namespace}/{names['restart']}",
                "liveEffect": "patch deployment pod template restart annotation",
            },
            {
                "toolName": "set_replicas_within_bounds",
                "target": f"Deployment/{namespace}/{names['scale']}",
                "liveEffect": "patch deployment scale subresource to 2 replicas",
            },
            {
                "toolName": "rollback_deployment_to_revision",
                "target": f"Deployment/{namespace}/{names['rollback']}",
                "liveEffect": "patch deployment pod template to selected ReplicaSet revision",
            },
            {
                "toolName": "set_hpa_bounds",
                "target": f"HorizontalPodAutoscaler/{namespace}/{names['hpa']}",
                "liveEffect": "patch HPA min/max replica bounds",
            },
            {
                "toolName": "evict_one_unhealthy_controller_owned_pod",
                "target": f"Pod selected by app={names['badpod']}",
                "liveEffect": "create pods/eviction request for one unready controller-owned pod",
            },
            {
                "toolName": "node_os_readonly_triage",
                "target": "first available Node",
                "liveEffect": "create diagnostics request/job for read-only node collector",
            },
        ],
        "plannedOcOperations": [
            "oc apply temporary RBAC ServiceAccount/ClusterRole/ClusterRoleBinding",
            "oc apply temporary Deployments and HPA labelled aiops.komsco/e2e-run=<prefix>",
            "oc rollout status temporary Deployments",
            "oc set env rollback target deployment to create a second revision",
            "oc create token temporary approver ServiceAccount",
            "oc port-forward svc/komsco-ai-gateway 8443",
            "Gateway /v1/actions proposal -> plan -> approval -> execute for five mutation tools",
            "Gateway /v1/diagnostics/requests for host diagnostic",
            "cleanup deletes temporary deployments, HPA, ServiceAccount, ClusterRoleBinding, ClusterRole, diagnostic job",
        ],
        "liveModeRequiredGates": [
            "current oc login must point to the intended test cluster",
            "namespace must be disposable enough for temporary e2e resources",
            "gateway capabilities.mutationsEnabled must be true",
            "gateway capabilities.recordStoreEnabled must be true",
            "image must be pullable by the namespace",
            "operator approval separation uses a temporary ServiceAccount token",
            "operator must pass --confirm-live-mutations after reviewing this plan",
        ],
        "recommendedLiveCommand": (
            "komsco-ai-gateway/.venv/bin/python scripts/evaluate-aiops-actions-e2e.py "
            f"--namespace {namespace} --report /tmp/komsco-ai-actions-e2e.json --confirm-live-mutations"
        ),
    }


def preflight_only_report(
    namespace: str,
    prefix: str,
    image: str,
    *,
    probe_gateway: bool,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    checks.append(oc_check("current oc identity", ["whoami"], timeout=30))
    checks.append(oc_check("current oc server", ["whoami", "--show-server"], timeout=30))
    checks.append(oc_check("namespace exists", ["get", "namespace", namespace], timeout=30))
    checks.append(
        oc_check(
            "gateway service exists",
            ["get", "svc", "komsco-ai-gateway", "-n", namespace],
            timeout=30,
        )
    )
    checks.append(
        oc_check(
            "gateway dev imagestream tag exists",
            ["get", "imagestreamtag", "komsco-ai-gateway:dev", "-n", namespace],
            timeout=30,
        )
    )

    checks.extend(
        [
            auth_can_i_check("create", "serviceaccounts", namespace=namespace),
            auth_can_i_check("create", "deployments.apps", namespace=namespace),
            auth_can_i_check("patch", "deployments.apps", namespace=namespace),
            auth_can_i_check("update", "deployments.apps/scale", namespace=namespace),
            auth_can_i_check("create", "horizontalpodautoscalers.autoscaling", namespace=namespace),
            auth_can_i_check("patch", "horizontalpodautoscalers.autoscaling", namespace=namespace),
            auth_can_i_check("create", "pods/eviction", namespace=namespace),
            auth_can_i_check("create", "clusterroles.rbac.authorization.k8s.io"),
            auth_can_i_check("create", "clusterrolebindings.rbac.authorization.k8s.io"),
        ]
    )

    gateway_probe: dict[str, Any] = {
        "enabled": probe_gateway,
        "ok": None,
        "healthz": None,
        "capabilities": None,
        "error": None,
    }
    if probe_gateway:
        try:
            httpx_module = require_httpx()
            token_result = run_oc(["whoami", "--show-token"], check=False, timeout=30)
            if token_result.returncode != 0 or not token_result.stdout.strip():
                raise RuntimeError(
                    "oc token unavailable: " + (token_result.stderr.strip() or token_result.stdout.strip())
                )
            with port_forward(namespace, "svc/komsco-ai-gateway", 8443) as (gateway_url, proc):
                wait_gateway_health(gateway_url, proc)
                with httpx_module.Client(base_url=gateway_url, verify=False, timeout=15.0) as client:
                    runtime = api_get(client, "/v1/aiops/status", token_result.stdout.strip())
            capabilities = runtime.get("spec", {}).get("capabilities", {})
            gateway_probe.update(
                {
                    "ok": True,
                    "healthz": "ok",
                    "capabilities": {
                        "mutationsEnabled": capabilities.get("mutationsEnabled"),
                        "recordStoreEnabled": capabilities.get("recordStoreEnabled"),
                        "actionExecutorConfigured": capabilities.get("actionExecutorConfigured"),
                        "diagnosticsEnabled": capabilities.get("diagnosticsEnabled"),
                    },
                }
            )
        except Exception as exc:  # noqa: BLE001 - preflight reports the exact readiness gap.
            gateway_probe.update({"ok": False, "error": str(exc)[:1000]})

    required_checks_ok = all(check["ok"] for check in checks)
    gateway_ok = gateway_probe["ok"] is not False
    return {
        "ok": required_checks_ok and gateway_ok,
        "mode": "preflight-only",
        "clusterCallsExecuted": False,
        "mutationExecuted": False,
        "wouldMutateClusterInLiveMode": True,
        "namespace": namespace,
        "prefix": prefix,
        "image": image,
        "generatedAt": now_rfc3339(),
        "checks": checks,
        "gatewayProbe": gateway_probe,
        "summary": {
            "passed": sum(1 for check in checks if check["ok"]),
            "failed": sum(1 for check in checks if not check["ok"]),
            "gatewayProbeOk": gateway_probe["ok"],
        },
        "nextStep": (
            "If preflight passes and temporary mutations are approved, run --plan-only once more, "
            "then run live mode with --confirm-live-mutations."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--image", default="")
    parser.add_argument("--keep-resources", action="store_true")
    parser.add_argument(
        "--plan-only",
        action="store_true",
        help="write the intended live e2e resources/actions without calling oc or the gateway",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="run non-mutating oc/gateway readiness checks for live mutation e2e",
    )
    parser.add_argument(
        "--skip-gateway-probe",
        action="store_true",
        help="with --preflight-only, skip gateway port-forward and /v1/aiops/status probe",
    )
    parser.add_argument(
        "--confirm-live-mutations",
        action="store_true",
        help="required for live mode; creates temporary resources and runs mutation action e2e",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    namespace = args.namespace
    prefix = f"aiops-e2e-{int(time.time())}"
    image = args.image or f"image-registry.openshift-image-registry.svc:5000/{namespace}/komsco-ai-gateway:dev"
    if args.plan_only:
        report = plan_only_report(namespace, prefix, image)
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.preflight_only:
        report = preflight_only_report(
            namespace,
            prefix,
            image,
            probe_gateway=not args.skip_gateway_probe,
        )
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if report["ok"] else 1

    if not args.confirm_live_mutations:
        report = {
            "ok": False,
            "mode": "live-blocked",
            "clusterCallsExecuted": False,
            "mutationExecuted": False,
            "wouldMutateClusterInLiveMode": True,
            "namespace": namespace,
            "prefix": prefix,
            "image": image,
            "generatedAt": now_rfc3339(),
            "error": "live action e2e requires --confirm-live-mutations",
            "nextStep": (
                "Run with --plan-only first, review the planned resources/actions, then rerun with "
                "--confirm-live-mutations only when temporary cluster mutations are approved."
            ),
        }
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2

    httpx_module = require_httpx()
    report: dict[str, Any] = {
        "ok": False,
        "namespace": namespace,
        "prefix": prefix,
        "startedAt": now_rfc3339(),
        "actions": [],
    }
    diagnostic_request_id: str | None = None
    try:
        requester_token = run_oc(["whoami", "--show-token"]).stdout.strip()
        approver_sa = apply_e2e_rbac(namespace, prefix)
        approver_token = run_oc(
            ["create", "token", approver_sa, "-n", namespace, "--duration=1h"],
            timeout=60,
        ).stdout.strip()
        names = apply_workloads(namespace, prefix, image)
        report["workloads"] = names

        with port_forward(namespace, "svc/komsco-ai-gateway", 8443) as (gateway_url, proc):
            wait_gateway_health(gateway_url, proc)
            report["gatewayUrl"] = gateway_url
            with httpx_module.Client(base_url=gateway_url, verify=False, timeout=30.0) as client:
                runtime_before = api_get(client, "/v1/aiops/status", requester_token)
                capabilities = runtime_before.get("spec", {}).get("capabilities", {})
                if capabilities.get("mutationsEnabled") is not True:
                    raise RuntimeError(f"gateway mutations are not enabled: {capabilities}")
                if capabilities.get("recordStoreEnabled") is not True:
                    raise RuntimeError(f"gateway record store is not enabled: {capabilities}")

                restart_deployment = oc_json(["get", "deployment", names["restart"], "-n", namespace])
                scale_deployment = oc_json(["get", "deployment", names["scale"], "-n", namespace])
                rollback_deployment = oc_json(["get", "deployment", names["rollback"], "-n", namespace])
                hpa = oc_json(["get", "hpa", names["hpa"], "-n", namespace])
                bad_pod = wait_for(
                    "badpod target pod",
                    lambda: first_pod(namespace, f"app={names['badpod']}", ready=False),
                    timeout_seconds=120,
                )

                report["actions"].append(
                    run_action(
                        client,
                        requester_token=requester_token,
                        approver_token=approver_token,
                        namespace=namespace,
                        prefix=prefix,
                        tool_name="rollout_restart_deployment",
                        target=target_from_resource(restart_deployment, "apps/v1", "Deployment"),
                        parameters={"restartedAt": now_rfc3339()},
                    )
                )
                report["actions"].append(
                    run_action(
                        client,
                        requester_token=requester_token,
                        approver_token=approver_token,
                        namespace=namespace,
                        prefix=prefix,
                        tool_name="set_replicas_within_bounds",
                        target=target_from_resource(scale_deployment, "apps/v1", "Deployment"),
                        parameters={"replicas": 2, "minReplicas": 1, "maxReplicas": 2, "hpaReviewed": True},
                    )
                )
                report["actions"].append(
                    run_action(
                        client,
                        requester_token=requester_token,
                        approver_token=approver_token,
                        namespace=namespace,
                        prefix=prefix,
                        tool_name="rollback_deployment_to_revision",
                        target=target_from_resource(rollback_deployment, "apps/v1", "Deployment"),
                        parameters={"revision": 1},
                    )
                )
                report["actions"].append(
                    run_action(
                        client,
                        requester_token=requester_token,
                        approver_token=approver_token,
                        namespace=namespace,
                        prefix=prefix,
                        tool_name="set_hpa_bounds",
                        target=target_from_resource(hpa, "autoscaling/v2", "HorizontalPodAutoscaler"),
                        parameters={"minReplicas": 1, "maxReplicas": 2, "allowMaxIncrease": False},
                    )
                )
                report["actions"].append(
                    run_action(
                        client,
                        requester_token=requester_token,
                        approver_token=approver_token,
                        namespace=namespace,
                        prefix=prefix,
                        tool_name="evict_one_unhealthy_controller_owned_pod",
                        target=target_from_resource(bad_pod, "v1", "Pod"),
                        parameters={"reason": "aiops_e2e_unready_pod_eviction"},
                    )
                )
                diagnostic = run_host_diagnostic(client, token=requester_token, prefix=prefix)
                diagnostic_request_id = diagnostic["requestId"]
                report["hostDiagnostic"] = diagnostic

                runtime_after = api_get(client, "/v1/aiops/status", requester_token)
                records = runtime_after.get("spec", {}).get("records", {})
                if len(records.get("executionRecords", [])) < 5:
                    raise RuntimeError("runtime status did not expose expected execution records")
                if not records.get("diagnosticRequests"):
                    raise RuntimeError("runtime status did not expose diagnostic records")
                report["runtimeStatus"] = {
                    "executionRecords": len(records.get("executionRecords", [])),
                    "diagnosticRequests": len(records.get("diagnosticRequests", [])),
                }

        report["ok"] = True
        return 0
    except Exception as exc:  # noqa: BLE001 - report any e2e failure.
        if isinstance(exc, HostDiagnosticError):
            diagnostic_request_id = exc.request_id
            report["hostDiagnostic"] = {"requestId": exc.request_id, "error": str(exc)}
        report["error"] = str(exc)
        return 1
    finally:
        report["finishedAt"] = now_rfc3339()
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        if not args.keep_resources:
            cleanup(namespace, prefix, diagnostic_request_id)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
