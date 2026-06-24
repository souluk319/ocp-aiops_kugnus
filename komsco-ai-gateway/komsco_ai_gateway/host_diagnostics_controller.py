from __future__ import annotations

import os
import json
import re
from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from .aiops_core import HOST_DIAGNOSTIC_COLLECTORS, AiopsCoreError, get_host_diagnostic_collector
from .security import canonical_digest, now_rfc3339, redact_sensitive

app = FastAPI(title="KOMSCO AIOps Host Diagnostics Controller", version="0.1.3")

SERVICEACCOUNT_DIR = "/var/run/secrets/kubernetes.io/serviceaccount"
HOST_DIAGNOSTIC_COLLECTOR_VERSION = "v1"
HOST_DIAGNOSTIC_COLLECTOR_BUNDLE = {
    "schemaVersion": "v1",
    "version": HOST_DIAGNOSTIC_COLLECTOR_VERSION,
    "collectors": HOST_DIAGNOSTIC_COLLECTORS,
}
HOST_DIAGNOSTIC_COLLECTOR_DIGEST = canonical_digest(HOST_DIAGNOSTIC_COLLECTOR_BUNDLE)


def parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


CONTROLLER_ENABLED = parse_bool(
    os.getenv("KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_ENABLED"),
    default=False,
)
CONTROLLER_SHARED_TOKEN = os.getenv("KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_SHARED_TOKEN", "")
RUNNER_IMAGE = os.getenv("KOMSCO_AI_HOST_DIAGNOSTICS_RUNNER_IMAGE", "komsco-ai-gateway:dev")
RUNNER_SERVICE_ACCOUNT = os.getenv(
    "KOMSCO_AI_HOST_DIAGNOSTICS_RUNNER_SERVICE_ACCOUNT",
    "komsco-ai-host-diagnostics-runner",
)
OPENSHIFT_API_URL = os.getenv("OPENSHIFT_API_URL", "").rstrip("/")
if not OPENSHIFT_API_URL and os.getenv("KUBERNETES_SERVICE_HOST"):
    kubernetes_host = os.getenv("KUBERNETES_SERVICE_HOST")
    kubernetes_port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
    OPENSHIFT_API_URL = f"https://{kubernetes_host}:{kubernetes_port}"
OPENSHIFT_API_CA_FILE = os.getenv(
    "OPENSHIFT_API_CA_FILE",
    f"{SERVICEACCOUNT_DIR}/ca.crt" if os.path.exists(f"{SERVICEACCOUNT_DIR}/ca.crt") else "",
)
JOB_RECORDS: dict[str, dict[str, Any]] = {}
K8S_NAME_RE = re.compile(r"[^a-z0-9-]+")


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ControllerDiagnosticRequest(StrictBaseModel):
    diagnosticRequest: dict[str, Any] = Field(min_length=1)


def current_namespace() -> str:
    configured = os.getenv("KOMSCO_AI_HOST_DIAGNOSTICS_NAMESPACE", "").strip()
    if configured:
        return configured
    namespace_file = f"{SERVICEACCOUNT_DIR}/namespace"
    try:
        return open(namespace_file, encoding="utf-8").read().strip() or "default"
    except OSError:
        return "default"


def serviceaccount_token() -> str:
    token_file = os.getenv(
        "KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_TOKEN_FILE",
        f"{SERVICEACCOUNT_DIR}/token",
    )
    try:
        return open(token_file, encoding="utf-8").read().strip()
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Host diagnostics controller token unavailable") from exc


def verify_controller_ingress(authorization: str | None) -> None:
    if not CONTROLLER_ENABLED:
        raise HTTPException(status_code=403, detail="Host Diagnostics Controller is disabled")
    if not CONTROLLER_SHARED_TOKEN:
        return
    if authorization != f"Bearer {CONTROLLER_SHARED_TOKEN}":
        raise HTTPException(status_code=401, detail="Invalid Host Diagnostics Controller caller token")


def safe_k8s_name(value: str, *, prefix: str = "aiops-diag") -> str:
    normalized = K8S_NAME_RE.sub("-", value.lower()).strip("-")
    if not normalized:
        normalized = "request"
    if normalized.startswith(prefix):
        candidate = normalized
    else:
        candidate = f"{prefix}-{normalized}"
    return candidate[:63].strip("-")


def parse_duration_seconds(value: Any, *, default: int) -> int:
    text = str(value or "").strip().lower()
    if not text:
        return default
    try:
        if text.endswith("ms"):
            return max(1, int(text[:-2]) // 1000)
        if text.endswith("s"):
            return max(1, int(text[:-1]))
        if text.endswith("m"):
            return max(1, int(text[:-1]) * 60)
        return max(1, int(text))
    except ValueError:
        return default


def bounded_limits(candidate: Mapping[str, Any], collector_profile: Mapping[str, Any]) -> dict[str, int]:
    request_limits = candidate.get("limits") if isinstance(candidate.get("limits"), Mapping) else {}
    collector_limits = (
        collector_profile.get("limits") if isinstance(collector_profile.get("limits"), Mapping) else {}
    )
    request_deadline = parse_duration_seconds(request_limits.get("deadline"), default=30)
    collector_deadline = parse_duration_seconds(collector_limits.get("deadline"), default=30)
    return {
        "maxBytes": min(
            int(request_limits.get("maxBytes") or collector_limits.get("maxBytes") or 10 * 1024 * 1024),
            int(collector_limits.get("maxBytes") or 10 * 1024 * 1024),
        ),
        "maxLines": min(
            int(request_limits.get("maxLines") or collector_limits.get("maxLines") or 50000),
            int(collector_limits.get("maxLines") or 50000),
        ),
        "deadlineSeconds": min(request_deadline, collector_deadline),
    }


def host_path_volume(path: str) -> dict[str, Any]:
    path_name = path.strip("/").replace("/", "-").replace(".", "-") or "root"
    host_path_type = "Directory"
    if path.endswith(".sock"):
        host_path_type = "Socket"
    return {
        "name": f"host-{path_name}"[:63].strip("-"),
        "hostPath": {
            "path": path,
            "type": host_path_type,
        },
    }


def volume_mount_for_host_path(volume: Mapping[str, Any]) -> dict[str, Any]:
    host_path = str(volume["hostPath"]["path"])
    return {
        "name": str(volume["name"]),
        "mountPath": f"/host{host_path}",
        "readOnly": True,
    }


def validate_diagnostic_record(record: Mapping[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
    spec = record.get("spec") if isinstance(record.get("spec"), Mapping) else {}
    candidate = spec.get("candidate") if isinstance(spec.get("candidate"), Mapping) else {}
    request_id = str(metadata.get("name") or "")
    if not request_id.startswith("diag-"):
        raise HTTPException(status_code=400, detail="Diagnostic request metadata.name is invalid")

    collector = str(candidate.get("collector") or "")
    try:
        collector_profile = get_host_diagnostic_collector(collector)
    except AiopsCoreError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if collector_profile.get("arbitraryCommandInputAllowed") is not False:
        raise HTTPException(status_code=400, detail="Collector allows arbitrary command input")
    if candidate.get("collectorVersion") != collector_profile["collectorVersion"]:
        raise HTTPException(status_code=400, detail="Collector version mismatch")
    if candidate.get("collectorProfile") != collector_profile["collectorProfile"]:
        raise HTTPException(status_code=400, detail="Collector profile mismatch")
    registry = candidate.get("collectorRegistry") if isinstance(candidate.get("collectorRegistry"), Mapping) else {}
    if registry.get("digest") != HOST_DIAGNOSTIC_COLLECTOR_DIGEST:
        raise HTTPException(status_code=400, detail="Collector registry digest mismatch")
    target_node = candidate.get("targetNode") if isinstance(candidate.get("targetNode"), Mapping) else {}
    if not target_node.get("name") or not target_node.get("uid"):
        raise HTTPException(status_code=400, detail="Target node name and uid are required")

    return request_id, dict(candidate), collector_profile


def build_diagnostic_job_manifest(
    record: Mapping[str, Any],
    *,
    namespace: str,
    runner_image: str,
    runner_service_account: str,
) -> dict[str, Any]:
    request_id, candidate, collector_profile = validate_diagnostic_record(record)
    target_node = candidate["targetNode"]
    collector = candidate["collector"]
    limits = bounded_limits(candidate, collector_profile)
    job_name = safe_k8s_name(request_id)
    host_paths = collector_profile.get("hostAccess", {}).get("hostPaths", [])
    volumes = [host_path_volume(str(item["path"])) for item in host_paths if isinstance(item, Mapping)]
    volumes.append({"name": "tmp", "emptyDir": {}})
    volume_mounts = [volume_mount_for_host_path(volume) for volume in volumes if "hostPath" in volume]
    volume_mounts.append({"name": "tmp", "mountPath": "/tmp"})

    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {
            "name": job_name,
            "namespace": namespace,
            "labels": {
                "app": "komsco-ai-host-diagnostics",
                "aiops.komsco/request-id": request_id,
                "aiops.komsco/collector": str(collector),
            },
            "annotations": {
                "aiops.komsco/target-node": str(target_node["name"]),
                "aiops.komsco/request-digest": str(record.get("spec", {}).get("diagnosticRequestDigest", "")),
            },
        },
        "spec": {
            "backoffLimit": 0,
            "ttlSecondsAfterFinished": 600,
            "activeDeadlineSeconds": limits["deadlineSeconds"],
            "template": {
                "metadata": {
                    "labels": {
                        "app": "komsco-ai-host-diagnostics",
                        "aiops.komsco/request-id": request_id,
                    }
                },
                "spec": {
                    "serviceAccountName": runner_service_account,
                    "restartPolicy": "Never",
                    "nodeName": str(target_node["name"]),
                    "hostPID": bool(collector_profile.get("hostAccess", {}).get("hostPID")),
                    "hostNetwork": bool(collector_profile.get("hostAccess", {}).get("hostNetwork")),
                    "containers": [
                        {
                            "name": "collector",
                            "image": runner_image,
                            "imagePullPolicy": "Always",
                            "command": ["python", "-m", "komsco_ai_gateway.host_diagnostics_collector"],
                            "env": [
                                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"},
                                {"name": "PYTHONPYCACHEPREFIX", "value": "/tmp/pycache"},
                                {"name": "AIOPS_DIAGNOSTIC_REQUEST_ID", "value": request_id},
                                {"name": "AIOPS_COLLECTOR", "value": str(collector)},
                                {"name": "AIOPS_TARGET_NODE_NAME", "value": str(target_node["name"])},
                                {"name": "AIOPS_TARGET_NODE_UID", "value": str(target_node["uid"])},
                                {"name": "AIOPS_MAX_BYTES", "value": str(limits["maxBytes"])},
                                {"name": "AIOPS_MAX_LINES", "value": str(limits["maxLines"])},
                            ],
                            "resources": {
                                "requests": {"cpu": "25m", "memory": "64Mi"},
                                "limits": {"cpu": "250m", "memory": "256Mi"},
                            },
                            "securityContext": {
                                "allowPrivilegeEscalation": False,
                                "capabilities": {"drop": ["ALL"]},
                                "readOnlyRootFilesystem": True,
                                "runAsUser": 0,
                            },
                            "volumeMounts": volume_mounts,
                        }
                    ],
                    "volumes": volumes,
                },
            },
        },
    }


async def kubernetes_request(
    method: str,
    path: str,
    *,
    json_body: Mapping[str, Any] | None = None,
    expect_json: bool = True,
) -> dict[str, Any]:
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")
    headers = {"Authorization": f"Bearer {serviceaccount_token()}"}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
    verify: str | bool = OPENSHIFT_API_CA_FILE or True
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=5.0), verify=verify) as client:
        response = await client.request(
            method,
            f"{OPENSHIFT_API_URL}{path}",
            headers=headers,
            json=json_body,
        )
    if response.status_code >= 400:
        detail = response.text[:1000]
        raise HTTPException(status_code=response.status_code, detail=f"Kubernetes API request failed: {detail}")
    if not expect_json:
        return {"raw": response.text}
    return response.json() if response.content else {}


def job_phase(job: Mapping[str, Any]) -> str:
    status = job.get("status") if isinstance(job.get("status"), Mapping) else {}
    if status.get("succeeded"):
        return "completed"
    if status.get("failed"):
        return "failed"
    if status.get("active"):
        return "running"
    return "submitted"


async def diagnostic_pod_log(namespace: str, request_id: str) -> dict[str, Any]:
    label_selector = quote(f"aiops.komsco/request-id={request_id}", safe="")
    pods = await kubernetes_request(
        "GET",
        f"/api/v1/namespaces/{namespace}/pods?labelSelector={label_selector}",
    )
    items = pods.get("items") if isinstance(pods.get("items"), list) else []
    if not items:
        return {"podFound": False}
    pod = items[0]
    pod_name = str(pod.get("metadata", {}).get("name") or "")
    phase = str(pod.get("status", {}).get("phase") or "")
    result: dict[str, Any] = {
        "podFound": True,
        "podName": pod_name,
        "podPhase": phase,
    }
    if not pod_name or phase not in {"Succeeded", "Failed"}:
        return result
    log_payload = await kubernetes_request(
        "GET",
        f"/api/v1/namespaces/{namespace}/pods/{quote(pod_name, safe='')}/log?container=collector&tailLines=300",
        expect_json=False,
    )
    raw_log = str(log_payload.get("raw") or "")
    result["logPreview"] = raw_log[:20000]
    try:
        evidence = json.loads(raw_log)
    except json.JSONDecodeError:
        return result
    sections = evidence.get("spec", {}).get("sections", []) if isinstance(evidence, Mapping) else []
    result["evidenceSummary"] = {
        "kind": evidence.get("kind") if isinstance(evidence, Mapping) else "",
        "requestId": evidence.get("spec", {}).get("requestId") if isinstance(evidence, Mapping) else "",
        "collector": evidence.get("spec", {}).get("collector", {}).get("name")
        if isinstance(evidence, Mapping)
        else "",
        "sections": [
            section.get("name")
            for section in sections
            if isinstance(section, Mapping) and section.get("name")
        ],
    }
    return result


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/controller/diagnostics/requests")
async def submit_diagnostic_request(
    req: ControllerDiagnosticRequest,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    verify_controller_ingress(authorization)
    namespace = current_namespace()
    manifest = build_diagnostic_job_manifest(
        req.diagnosticRequest,
        namespace=namespace,
        runner_image=RUNNER_IMAGE,
        runner_service_account=RUNNER_SERVICE_ACCOUNT,
    )
    job = await kubernetes_request(
        "POST",
        f"/apis/batch/v1/namespaces/{namespace}/jobs",
        json_body=manifest,
    )
    request_id = str(manifest["metadata"]["labels"]["aiops.komsco/request-id"])
    record = {
        "requestId": request_id,
        "jobName": job.get("metadata", {}).get("name", manifest["metadata"]["name"]),
        "namespace": namespace,
        "submittedAt": now_rfc3339(),
        "phase": job_phase(job),
    }
    JOB_RECORDS[request_id] = record
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "HostDiagnosticSubmission",
        "metadata": {
            "name": request_id,
        },
        "spec": redact_sensitive(record),
    }


@app.get("/v1/controller/diagnostics/requests/{request_id}")
async def get_diagnostic_job(
    request_id: str,
    authorization: str | None = Header(default=None),
) -> dict[str, Any]:
    verify_controller_ingress(authorization)
    record = JOB_RECORDS.get(request_id, {"requestId": request_id, "namespace": current_namespace()})
    namespace = str(record.get("namespace") or current_namespace())
    label_selector = quote(f"aiops.komsco/request-id={request_id}", safe="")
    jobs = await kubernetes_request(
        "GET",
        f"/apis/batch/v1/namespaces/{namespace}/jobs?labelSelector={label_selector}",
    )
    items = jobs.get("items") if isinstance(jobs.get("items"), list) else []
    if items:
        job = items[0]
        record = {
            **record,
            "jobName": job.get("metadata", {}).get("name", record.get("jobName")),
            "phase": job_phase(job),
            "status": job.get("status", {}),
        }
    record["collectorPod"] = await diagnostic_pod_log(namespace, request_id)
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "HostDiagnosticSubmission",
        "metadata": {
            "name": request_id,
        },
        "spec": redact_sensitive(record),
    }
