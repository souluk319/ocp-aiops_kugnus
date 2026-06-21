import asyncio
import base64
import binascii
import json
import os
import re
import time
import uuid
from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .security import (
    build_evidence_reference,
    build_gateway_guardrail,
    build_trace_record,
    classify_request_policy,
    redact_sensitive,
    safe_subject,
)

app = FastAPI(title="KOMSCO AI Gateway", version="0.1.0")


def parse_bool(value: str | None, *, default: bool = False) -> bool:
    if value is None or value.strip() == "":
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def parse_ols_verify(value: str | None) -> bool | str:
    if value is None or value.strip() == "":
        return True

    normalized = value.strip().lower()
    if normalized in {"0", "false", "no", "off"}:
        return False
    if normalized in {"1", "true", "yes", "on"}:
        return True

    return value


OLS_BASE_URL = os.getenv("OLS_BASE_URL", "").rstrip("/")
OLS_CA_FILE = parse_ols_verify(os.getenv("OLS_CA_FILE"))
DEV_ECHO = parse_bool(os.getenv("KOMSCO_AI_DEV_ECHO"))
OPENSHIFT_API_URL = os.getenv("OPENSHIFT_API_URL", "").rstrip("/")
if not OPENSHIFT_API_URL and os.getenv("KUBERNETES_SERVICE_HOST"):
    kubernetes_host = os.getenv("KUBERNETES_SERVICE_HOST")
    kubernetes_port = os.getenv("KUBERNETES_SERVICE_PORT", "443")
    OPENSHIFT_API_URL = f"https://{kubernetes_host}:{kubernetes_port}"
OPENSHIFT_API_CA_FILE = parse_ols_verify(
    os.getenv(
        "OPENSHIFT_API_CA_FILE",
        "/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
        if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt")
        else "",
    )
)
TOOL_LINE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Tool call:", "tool_call"),
    ("Tool result:", "tool_result"),
)
MAX_TOOL_DETAIL_CHARS = 4000
RUN_HEARTBEAT_SECONDS = 5.0
MAX_IMAGE_ATTACHMENTS = 4
MAX_IMAGE_ATTACHMENT_BYTES = 2 * 1024 * 1024
MAX_IMAGE_ATTACHMENT_TOTAL_BYTES = 6 * 1024 * 1024
ALLOWED_IMAGE_MIME_TYPES = {"image/gif", "image/jpeg", "image/png", "image/webp"}
DISALLOWED_GATEWAY_API_REFERENCE_RE = re.compile(
    r"^\s*(Gateway|GatewayClass)\s+\[gateway\.networking\.k8s\.io/v1\]:\s+https?://",
    re.IGNORECASE,
)
EXPLICIT_KUBERNETES_GATEWAY_API_RE = re.compile(
    r"(?i)(gatewayclass|gateway\.networking\.k8s\.io|kubernetes gateway api|openshift gateway api|gateway api)"
)
LOW_SIGNAL_REFERENCE_RE = re.compile(
    r"^\s*("
    r"Extension APIs|"
    r"Admission plugins|"
    r"TokenReview\s+\[authentication\.k8s\.io/v1\]|"
    r"ClusterRole\s+\[authorization\.openshift\.io/v1\]"
    r"):\s+https?://",
    re.IGNORECASE,
)
EXPLICIT_OPENSHIFT_DOC_REFERENCE_RE = re.compile(
    r"(?i)(문서|docs?|reference|참고 링크|api\s*문서|extension api|admission plugin|tokenreview|clusterrole)"
)
POD_STATUS_ANALYSIS_RE = re.compile(
    r"(?i)((pod|pods|파드).*(상태|현황|이력|횟수|많은|높은|분석|확인|조회|"
    r"crashloop|imagepull|backoff|failed|error|pending|restart\s+(count|history|status|analysis|summary)|"
    r"(many|high|top)\s+restarts)|"
    r"(상태|현황|이력|횟수|많은|높은|분석|확인|조회|crashloop|imagepull|backoff|failed|"
    r"error|pending|restart\s+count|"
    r"restart\s+(history|status|analysis|summary)|(many|high|top)\s+restarts).*(pod|pods|파드))"
)
CRONJOB_ACTIVITY_ANALYSIS_RE = re.compile(
    r"(?i)(cron\s*job|cronjob|크론잡|scheduled\s+job|schedule|스케줄|"
    r"\d+\s*(분|minute|min)|\*/\d+|0/\d+|"
    r"반복\s*(실행|활동)|주기|activity|활동|이벤트)"
)
CRONJOB_POLICY_ENV_RE = re.compile(
    r"(?i)(workspace|notebook|sandbox|hibernate|suspend|sleep|idle|delete|ttl|"
    r"expire|expiration|cleanup|retention|prune|archive|max[_-]?age|timeout|gc)"
)
SECRET_ENV_RE = re.compile(r"(?i)(secret|token|password|passwd|private|credential|key)")
POD_RESTART_LANGUAGE_REPLACEMENTS: tuple[tuple[str, str], ...] = (
    ("재시작 빈도", "누적 재시작 횟수"),
    ("높은 빈도", "높은 누적 재시작 횟수"),
    ("빈번한 재시작", "누적 재시작 이력"),
    ("재시작이 빈번하게 발생", "재시작 이력이 누적"),
    ("재시작이 빈번", "누적 재시작 횟수가 높음"),
)
VISION_SYSTEM_PROMPT = (
    "You are an image analysis component for an OpenShift AIOps assistant. "
    "Extract visible text, UI state, error messages, resource names, namespace names, "
    "and operational signals from the attached image. Be concise and do not invent "
    "details that are not visible."
)


class ImageAttachment(BaseModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=180)
    mimeType: str = Field(min_length=1, max_length=80)
    size: int = Field(ge=1, le=MAX_IMAGE_ATTACHMENT_BYTES)
    data: str = Field(min_length=1)


class ChatRequest(BaseModel):
    message: str = Field(default="", max_length=4000)
    pageContext: dict[str, Any] | None = None
    conversationId: str | None = None
    runId: str | None = None
    attachments: list[ImageAttachment] = Field(default_factory=list, max_length=MAX_IMAGE_ATTACHMENTS)


def sse(data: Mapping[str, Any] | str) -> str:
    if isinstance(data, str):
        return f"data: {data}\n\n"

    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


async def verify_user_access(user_auth_header: str, req: ChatRequest) -> None:
    # TODO: add TokenReview/SelfSubjectAccessReview checks for product policy.
    if not user_auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    if not req.message.strip() and not req.attachments:
        raise HTTPException(status_code=400, detail="Message or image attachment is required")


def verify_bearer_header(user_auth_header: str | None) -> str:
    if not user_auth_header or not user_auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    return user_auth_header


def validate_image_attachments(attachments: list[ImageAttachment]) -> None:
    total_size = 0
    seen_ids: set[str] = set()

    for attachment in attachments:
        if attachment.id in seen_ids:
            raise HTTPException(status_code=400, detail="Duplicate attachment id")
        seen_ids.add(attachment.id)

        if attachment.mimeType not in ALLOWED_IMAGE_MIME_TYPES:
            raise HTTPException(status_code=400, detail=f"Unsupported image type: {attachment.mimeType}")

        try:
            decoded = base64.b64decode(attachment.data, validate=True)
        except binascii.Error as exc:
            raise HTTPException(status_code=400, detail="Invalid image attachment data") from exc

        decoded_size = len(decoded)
        if decoded_size != attachment.size:
            raise HTTPException(status_code=400, detail="Image attachment size mismatch")
        if decoded_size > MAX_IMAGE_ATTACHMENT_BYTES:
            raise HTTPException(status_code=400, detail="Image attachment is too large")

        total_size += decoded_size

    if total_size > MAX_IMAGE_ATTACHMENT_TOTAL_BYTES:
        raise HTTPException(status_code=400, detail="Image attachments are too large")


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def find_condition(resource: Mapping[str, Any], condition_type: str) -> Mapping[str, Any] | None:
    conditions = resource.get("status", {}).get("conditions", [])
    if not isinstance(conditions, list):
        return None

    for condition in conditions:
        if isinstance(condition, Mapping) and condition.get("type") == condition_type:
            return condition

    return None


def condition_status(resource: Mapping[str, Any], condition_type: str) -> str | None:
    condition = find_condition(resource, condition_type)
    if not condition:
        return None

    status = condition.get("status")
    return str(status) if status is not None else None


def node_roles(node: Mapping[str, Any]) -> list[str]:
    labels = node.get("metadata", {}).get("labels", {})
    if not isinstance(labels, Mapping):
        return []

    roles = []
    for key in labels:
        prefix = "node-role.kubernetes.io/"
        if key.startswith(prefix):
            role = key[len(prefix) :] or "worker"
            roles.append(role)

    return sorted(roles) or ["worker"]


def node_metric_map(node_metrics_payload: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not node_metrics_payload:
        return {}

    items = node_metrics_payload.get("items")
    if not isinstance(items, list):
        return {}

    metrics = {}
    for item in items:
        if not isinstance(item, Mapping):
            continue

        name = item.get("metadata", {}).get("name")
        if isinstance(name, str):
            metrics[name] = item

    return metrics


def summarize_node(node: Mapping[str, Any], metrics: Mapping[str, Any] | None) -> dict[str, Any]:
    metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), Mapping) else {}
    status = node.get("status", {}) if isinstance(node.get("status"), Mapping) else {}
    node_info = status.get("nodeInfo", {}) if isinstance(status.get("nodeInfo"), Mapping) else {}
    name = str(metadata.get("name") or "unknown-node")
    ready = condition_status(node, "Ready") == "True"
    pressures = {
        "disk": condition_status(node, "DiskPressure") == "True",
        "memory": condition_status(node, "MemoryPressure") == "True",
        "pid": condition_status(node, "PIDPressure") == "True",
    }
    usage = metrics.get("usage", {}) if isinstance(metrics, Mapping) else {}

    return {
        "name": name,
        "roles": node_roles(node),
        "ready": ready,
        "pressures": pressures,
        "kubeletVersion": node_info.get("kubeletVersion"),
        "osImage": node_info.get("osImage"),
        "usage": {
            "cpu": usage.get("cpu") if isinstance(usage, Mapping) else None,
            "memory": usage.get("memory") if isinstance(usage, Mapping) else None,
        },
    }


def summarize_operator(operator: Mapping[str, Any]) -> dict[str, Any]:
    metadata = operator.get("metadata", {}) if isinstance(operator.get("metadata"), Mapping) else {}
    name = str(metadata.get("name") or "unknown-operator")
    available = condition_status(operator, "Available") == "True"
    degraded = condition_status(operator, "Degraded") == "True"
    progressing = condition_status(operator, "Progressing") == "True"
    upgradeable = condition_status(operator, "Upgradeable")
    issue_condition = (
        find_condition(operator, "Degraded")
        if degraded
        else find_condition(operator, "Available")
        if not available
        else find_condition(operator, "Progressing")
        if progressing
        else find_condition(operator, "Upgradeable")
        if upgradeable == "False"
        else None
    )

    return {
        "name": name,
        "available": available,
        "degraded": degraded,
        "progressing": progressing,
        "upgradeable": upgradeable,
        "reason": issue_condition.get("reason") if issue_condition else None,
        "message": issue_condition.get("message") if issue_condition else None,
    }


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
    if version_summary.get("upgradeable") is False:
        score -= 8

    return max(0, min(100, score))


def build_cluster_summary(
    nodes_payload: Mapping[str, Any],
    node_metrics_payload: Mapping[str, Any] | None,
    cluster_version_payload: Mapping[str, Any] | None,
    cluster_operators_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    node_items = nodes_payload.get("items", [])
    if not isinstance(node_items, list):
        node_items = []

    metrics_by_name = node_metric_map(node_metrics_payload)
    nodes = []
    for node in node_items:
        if not isinstance(node, Mapping):
            continue

        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), Mapping) else {}
        nodes.append(summarize_node(node, metrics_by_name.get(str(metadata.get("name")))))
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

    operator_items = (
        cluster_operators_payload.get("items", [])
        if isinstance(cluster_operators_payload, Mapping)
        else []
    )
    if not isinstance(operator_items, list):
        operator_items = []

    operators = [
        summarize_operator(operator) for operator in operator_items if isinstance(operator, Mapping)
    ]
    operator_issues = [
        operator
        for operator in operators
        if not operator["available"]
        or operator["degraded"]
        or operator["progressing"]
        or operator.get("upgradeable") == "False"
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
    upgradeable_condition = (
        find_condition(cluster_version_payload or {}, "Upgradeable")
        if isinstance(cluster_version_payload, Mapping)
        else None
    )
    version_summary = {
        "version": desired.get("version"),
        "channel": cluster_version_status.get("channel"),
        "updateAvailable": isinstance(available_updates, list) and len(available_updates) > 0,
        "upgradeable": upgradeable_condition.get("status") != "False"
        if upgradeable_condition
        else None,
        "upgradeableReason": upgradeable_condition.get("reason") if upgradeable_condition else None,
        "upgradeableMessage": upgradeable_condition.get("message") if upgradeable_condition else None,
    }

    return {
        "updatedAt": datetime.now(UTC).isoformat(),
        "apiUrl": OPENSHIFT_API_URL,
        "healthScore": compute_health_score(nodes_summary, operators_summary, version_summary),
        "nodes": nodes_summary,
        "operators": operators_summary,
        "version": version_summary,
    }


def build_attachment_context(
    attachments: list[ImageAttachment],
    image_analysis: str | None = None,
    *,
    forwarded_to_ols: bool = False,
) -> str:
    if not attachments:
        return "첨부 이미지 없음"

    lines = [
        "첨부 이미지는 Gateway에서 수신 및 검증했습니다.",
    ]
    if image_analysis:
        lines.append("Gateway 비전 분석 결과:")
        lines.append(image_analysis)
    elif forwarded_to_ols:
        lines.append("이미지 원본은 Lightspeed attachments로 전달했습니다.")
    else:
        lines.append(
            "현재 Gateway 비전 분석과 OLS image attachment 전달이 비활성화되어 있습니다. "
            "답변에는 첨부 파일 메타데이터, 사용자 설명, 도구 조회 결과만 근거로 사용하세요."
        )

    lines.append("첨부 파일 메타데이터:")

    for index, attachment in enumerate(attachments, start=1):
        lines.append(
            f"{index}. {attachment.name} ({attachment.mimeType}, {format_bytes(attachment.size)})"
        )

    return "\n".join(lines)


def build_ols_attachments(attachments: list[ImageAttachment]) -> list[dict[str, str]]:
    return [
        {
            "attachment_type": "image",
            "content_type": attachment.mimeType,
            "content": attachment.data,
        }
        for attachment in attachments
    ]


def build_ols_payload(
    query: str,
    conversation_id: str | None,
    attachments: list[ImageAttachment],
    *,
    forward_image_attachments: bool = False,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": query}
    if conversation_id:
        payload["conversation_id"] = conversation_id

    ols_attachments = build_ols_attachments(attachments) if forward_image_attachments else []
    if ols_attachments:
        payload["attachments"] = ols_attachments

    return payload


def read_secret_value(value: str | None, file_path: str | None) -> str | None:
    if value:
        return value
    if not file_path:
        return None

    try:
        with open(file_path, encoding="utf-8") as secret_file:
            return secret_file.read().strip()
    except OSError:
        return None


def should_forward_image_attachments_to_ols() -> bool:
    return parse_bool(os.getenv("KOMSCO_AI_FORWARD_IMAGE_ATTACHMENTS_TO_OLS"), default=False)


def get_vision_config() -> dict[str, str] | None:
    base_url = os.getenv("KOMSCO_AI_VISION_BASE_URL", "").rstrip("/")
    model = os.getenv("KOMSCO_AI_VISION_MODEL", "").strip()
    api_key = read_secret_value(
        os.getenv("KOMSCO_AI_VISION_API_KEY"),
        os.getenv("KOMSCO_AI_VISION_API_KEY_FILE"),
    )

    if not base_url or not model:
        return None

    config = {"base_url": base_url, "model": model}
    if api_key:
        config["api_key"] = api_key

    return config


def truncate_detail(value: str, limit: int = MAX_TOOL_DETAIL_CHARS) -> str:
    if len(value) <= limit:
        return value

    return f"{value[:limit]}\n... truncated ..."


def dump_tool_detail(value: Any) -> str:
    if isinstance(value, str):
        return truncate_detail(value)

    try:
        return truncate_detail(json.dumps(value, ensure_ascii=False, indent=2))
    except TypeError:
        return truncate_detail(str(value))


def summarize_resource_args(args: Any) -> str | None:
    if not isinstance(args, Mapping):
        return None

    kind = args.get("kind")
    name = args.get("name")
    namespace = args.get("namespace")
    if not kind or not name:
        return None

    resource_name = f"{namespace}/{name}" if namespace else str(name)
    return f"{kind} {resource_name}"


def summarize_resource_content(content: str) -> str | None:
    kind_match = re.search(r"(?m)^kind:\s*([A-Za-z0-9_.-]+)\s*$", content)
    name_match = re.search(r"(?m)^\s{2}name:\s*([A-Za-z0-9_.-]+)\s*$", content)
    namespace_match = re.search(r"(?m)^\s{2}namespace:\s*([A-Za-z0-9_.-]+)\s*$", content)
    if not kind_match or not name_match:
        return None

    resource_name = (
        f"{namespace_match.group(1)}/{name_match.group(1)}"
        if namespace_match
        else name_match.group(1)
    )
    return f"{kind_match.group(1)} {resource_name}"


def summarize_tool_payload(event_type: str, payload: Mapping[str, Any]) -> str:
    tool_name = payload.get("name") or payload.get("tool_name")
    if event_type == "tool_call":
        if tool_name == "resources_get":
            resource_ref = summarize_resource_args(payload.get("args"))
            if resource_ref:
                return f"{resource_ref} 상세 조회"

        server_name = payload.get("server_name") or payload.get("serverName")
        if server_name:
            return f"{server_name} 도구 호출"

        return "도구 호출"

    status = payload.get("status")
    content = payload.get("content")
    if status and str(status).lower() in {"error", "failed", "failure"}:
        if isinstance(content, str) and content.strip():
            first_line = content.strip().splitlines()[0]
            return f"조회 실패: {truncate_detail(first_line, 80)}"

        return f"상태: {status}"

    if isinstance(content, str):
        if tool_name == "resources_get":
            resource_ref = summarize_resource_content(content)
            if resource_ref:
                return f"{resource_ref} 조회 완료"

        try:
            parsed_content = json.loads(content)
        except json.JSONDecodeError:
            parsed_content = None

        if isinstance(parsed_content, Mapping):
            alerts = parsed_content.get("alerts")
            if isinstance(alerts, list):
                return f"경고 {len(alerts)}건 조회"

    if status:
        return f"상태: {status}"

    return "도구 실행 완료"


def summarize_alerts_detail(alerts: list[Any]) -> str:
    lines = [f"조회 경고: {len(alerts)}건"]
    for alert in alerts[:10]:
        if not isinstance(alert, Mapping):
            continue

        labels = alert.get("labels") if isinstance(alert.get("labels"), Mapping) else {}
        annotations = (
            alert.get("annotations") if isinstance(alert.get("annotations"), Mapping) else {}
        )
        parts = [
            str(labels.get("severity") or "unknown"),
            str(labels.get("alertname") or "unknown-alert"),
        ]
        namespace = labels.get("namespace")
        pod = labels.get("pod")
        if namespace:
            parts.append(f"namespace={namespace}")
        if pod:
            parts.append(f"pod={pod}")

        lines.append(f"- {' / '.join(parts)}")
        summary = annotations.get("summary")
        if summary:
            lines.append(f"  {summary}")

    if len(alerts) > 10:
        lines.append(f"... {len(alerts) - 10}건 더 있음")

    return "\n".join(lines)


def build_tool_detail(event_type: str, payload: Mapping[str, Any]) -> str:
    if event_type == "tool_call":
        lines = []
        server_name = payload.get("server_name") or payload.get("serverName")
        args = payload.get("args")
        if server_name:
            lines.append(f"도구 서버: {server_name}")
        if args is not None:
            lines.append(f"요청 인자:\n{dump_tool_detail(args)}")

        return "\n".join(lines) or dump_tool_detail(payload)

    lines = []
    status = payload.get("status")
    if status:
        lines.append(f"상태: {status}")

    content = payload.get("content")
    if isinstance(content, str):
        try:
            parsed_content = json.loads(content)
        except json.JSONDecodeError:
            parsed_content = None

        if isinstance(parsed_content, Mapping):
            alerts = parsed_content.get("alerts")
            if isinstance(alerts, list):
                lines.append(summarize_alerts_detail(alerts))
                return truncate_detail("\n".join(lines))

            lines.append(dump_tool_detail(parsed_content))
            return truncate_detail("\n".join(lines))

        lines.append(truncate_detail(content))
        return truncate_detail("\n".join(lines))

    result = payload.get("result")
    if result is not None:
        lines.append(dump_tool_detail(result))
        return truncate_detail("\n".join(lines))

    return dump_tool_detail(payload)


def normalize_tool_event(event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {
        "type": event_type,
        "name": payload.get("name") or payload.get("tool_name") or "unknown_tool",
        "summary": summarize_tool_payload(event_type, payload),
        "detail": build_tool_detail(event_type, payload),
    }

    for source_key, target_key in (
        ("id", "id"),
        ("args", "args"),
        ("status", "status"),
        ("server_name", "serverName"),
        ("serverName", "serverName"),
        ("round", "round"),
    ):
        value = payload.get(source_key)
        if value is not None:
            normalized[target_key] = value

    return normalized


def parse_tool_text_line(line: str) -> dict[str, Any] | None:
    stripped = line.strip()
    for prefix, event_type in TOOL_LINE_PREFIXES:
        if not stripped.startswith(prefix):
            continue

        raw_payload = stripped[len(prefix) :].strip()
        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return {
                "type": event_type,
                "name": "unknown_tool",
                "summary": "도구 이벤트 수신",
                "detail": truncate_detail(raw_payload),
            }

        if isinstance(payload, Mapping):
            return normalize_tool_event(event_type, payload)

        return {
            "type": event_type,
            "name": "unknown_tool",
            "summary": "도구 이벤트 수신",
            "detail": dump_tool_detail(payload),
        }

    return None


async def split_plain_text_events(chunks: AsyncIterator[str]) -> AsyncIterator[dict[str, Any]]:
    pending = ""

    async for chunk in chunks:
        if not chunk:
            continue

        pending += chunk
        while pending:
            if any(prefix.startswith(pending) for prefix, _ in TOOL_LINE_PREFIXES):
                break

            matched_prefix = next(
                (prefix for prefix, _ in TOOL_LINE_PREFIXES if pending.startswith(prefix)),
                None,
            )
            if matched_prefix:
                line_end = pending.find("\n")
                if line_end == -1:
                    break

                line = pending[:line_end]
                pending = pending[line_end + 1 :]
                tool_event = parse_tool_text_line(line)
                if tool_event:
                    yield tool_event
                continue

            line_end = pending.find("\n")
            if line_end == -1:
                yield {"type": "text", "content": pending}
                pending = ""
                continue

            yield {"type": "text", "content": pending[: line_end + 1]}
            pending = pending[line_end + 1 :]

    if pending:
        tool_event = parse_tool_text_line(pending)
        if tool_event:
            yield tool_event
        else:
            yield {"type": "text", "content": pending}


def should_collect_pod_status_evidence(message: str) -> bool:
    return bool(POD_STATUS_ANALYSIS_RE.search(message))


def should_collect_cronjob_activity_evidence(
    message: str,
    image_analysis: str | None = None,
) -> bool:
    combined = f"{message}\n{image_analysis or ''}".strip()
    return bool(combined and CRONJOB_ACTIVITY_ANALYSIS_RE.search(combined))


def append_gateway_evidence(current: str | None, new_evidence: str) -> str:
    if not current:
        return new_evidence

    return f"{current}\n\n{new_evidence}"


def normalize_pod_restart_language(text: str) -> str:
    normalized = text
    for source, replacement in POD_RESTART_LANGUAGE_REPLACEMENTS:
        normalized = normalized.replace(source, replacement)
    return normalized


def parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def state_summary(container_status: Mapping[str, Any]) -> str:
    state = container_status.get("state")
    if not isinstance(state, Mapping):
        return "unknown"

    if isinstance(state.get("waiting"), Mapping):
        waiting = state["waiting"]
        reason = waiting.get("reason") or "Waiting"
        return f"waiting:{reason}"

    if isinstance(state.get("running"), Mapping):
        running = state["running"]
        started_at = running.get("startedAt")
        return f"running since {started_at}" if started_at else "running"

    if isinstance(state.get("terminated"), Mapping):
        terminated = state["terminated"]
        reason = terminated.get("reason") or "Terminated"
        exit_code = terminated.get("exitCode")
        return f"terminated:{reason}/{exit_code}"

    return "unknown"


def last_termination_summary(container_status: Mapping[str, Any]) -> tuple[str, str]:
    last_state = container_status.get("lastState")
    if not isinstance(last_state, Mapping):
        return "-", ""

    terminated = last_state.get("terminated")
    if not isinstance(terminated, Mapping):
        return "-", ""

    reason = terminated.get("reason") or "Terminated"
    exit_code = terminated.get("exitCode")
    finished_at = str(terminated.get("finishedAt") or "")
    return f"{reason}/{exit_code}", finished_at


def pod_ready_summary(pod: Mapping[str, Any]) -> str:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if not isinstance(statuses, list):
        return "0/0"

    total = len(statuses)
    ready = sum(1 for item in statuses if isinstance(item, Mapping) and item.get("ready"))
    return f"{ready}/{total}"


def pod_display_state(pod: Mapping[str, Any]) -> str:
    status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
    phase = str(status.get("phase") or "Unknown")
    statuses = status.get("containerStatuses", [])
    if not isinstance(statuses, list):
        return phase

    waiting_reasons = []
    for item in statuses:
        if not isinstance(item, Mapping):
            continue
        state = item.get("state")
        waiting = state.get("waiting") if isinstance(state, Mapping) else None
        if isinstance(waiting, Mapping):
            waiting_reasons.append(str(waiting.get("reason") or "Waiting"))

    if waiting_reasons:
        return f"{phase} ({', '.join(sorted(set(waiting_reasons)))})"

    return phase


def pod_owner_summary(pod: Mapping[str, Any]) -> str:
    owners = pod.get("metadata", {}).get("ownerReferences", [])
    if not isinstance(owners, list) or not owners:
        return "-"

    owner = owners[0]
    if not isinstance(owner, Mapping):
        return "-"

    kind = owner.get("kind") or "Owner"
    name = owner.get("name") or "unknown"
    return f"{kind}/{name}"


def build_pod_status_evidence(pods_payload: Mapping[str, Any]) -> str:
    items = pods_payload.get("items")
    if not isinstance(items, list):
        return "Pod status evidence unavailable: API response did not include an items list."

    rows: list[dict[str, Any]] = []
    unhealthy_rows: list[dict[str, Any]] = []
    for pod in items:
        if not isinstance(pod, Mapping):
            continue

        metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        namespace = str(metadata.get("namespace") or "unknown")
        pod_name = str(metadata.get("name") or "unknown")
        phase = str(status.get("phase") or "Unknown")
        pod_start_time = str(status.get("startTime") or "-")
        ready = pod_ready_summary(pod)
        pod_state = pod_display_state(pod)
        owner = pod_owner_summary(pod)
        statuses = status.get("containerStatuses", [])
        regular_statuses = statuses if isinstance(statuses, list) else []
        expected_ready = f"{len(regular_statuses)}/{len(regular_statuses)}"
        is_unhealthy = phase not in {"Running", "Succeeded"} or ready != expected_ready

        for container in regular_statuses:
            if not isinstance(container, Mapping):
                continue

            last_state, last_finished_at = last_termination_summary(container)
            row = {
                "namespace": namespace,
                "pod": pod_name,
                "container": str(container.get("name") or "unknown"),
                "phase": pod_state,
                "podStartTime": pod_start_time,
                "ready": ready,
                "state": state_summary(container),
                "restartCount": int(container.get("restartCount") or 0),
                "lastState": last_state,
                "lastFinishedAt": last_finished_at or "-",
                "lastFinishedSort": parse_rfc3339(last_finished_at)
                or datetime.min.replace(tzinfo=UTC),
                "owner": owner,
            }
            rows.append(row)
            if is_unhealthy or row["state"].startswith("waiting:"):
                unhealthy_rows.append(row)

    top_restart_rows = sorted(
        rows,
        key=lambda item: (item["restartCount"], item["lastFinishedSort"]),
        reverse=True,
    )[:15]
    top_unhealthy_rows = sorted(
        unhealthy_rows,
        key=lambda item: (item["restartCount"], item["lastFinishedSort"]),
        reverse=True,
    )[:10]

    lines = [
        "Gateway-collected Pod status evidence from Kubernetes API `/api/v1/pods`.",
        "Use this as primary evidence for cluster-wide Pod restart/status analysis.",
        "Restart counts below are cumulative container-level counts, not Pod-level rates.",
        "Pod phase/startTime indicate the current Pod object state; old Failed pods can be historical artifacts.",
        "Do not infer current control-plane or service impact from Failed pods alone; correlate with owner/controller/operator status.",
        "",
        "Top container restart counts:",
        "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Last Finished | Owner |",
        "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- | :--- |",
    ]
    if top_restart_rows:
        for row in top_restart_rows:
            lines.append(
                "| {namespace} | `{pod}` | `{container}` | {phase} / {state} | {podStartTime} | {ready} | {restartCount} | {lastState} | {lastFinishedAt} | {owner} |".format(
                    **row
                )
            )
    else:
        lines.append("| - | - | - | - | - | - | 0 | - | - | - |")

    lines.extend(
        [
            "",
            "Currently non-healthy or waiting container evidence:",
            "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
            "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
        ]
    )
    if top_unhealthy_rows:
        for row in top_unhealthy_rows:
            lines.append(
                "| {namespace} | `{pod}` | `{container}` | {phase} / {state} | {podStartTime} | {ready} | {restartCount} | {lastState} | {owner} |".format(
                    **row
                )
            )
    else:
        lines.append(
            "| - | - | - | 현재 non-healthy/waiting container가 evidence 상위권에 없음 | - | - | 0 | - | - |"
        )

    return "\n".join(lines)


def cluster_operator_condition(
    operator: Mapping[str, Any],
    condition_type: str,
) -> tuple[str, str, str]:
    conditions = operator.get("status", {}).get("conditions", [])
    if not isinstance(conditions, list):
        return "-", "-", "-"

    for condition in conditions:
        if not isinstance(condition, Mapping) or condition.get("type") != condition_type:
            continue
        return (
            str(condition.get("status") or "-"),
            str(condition.get("reason") or "-"),
            str(condition.get("message") or "-"),
        )

    return "-", "-", "-"


def build_cluster_operator_status_evidence(cluster_operators_payload: Mapping[str, Any]) -> str:
    items = cluster_operators_payload.get("items")
    if not isinstance(items, list):
        return "ClusterOperator evidence unavailable: API response did not include an items list."

    rows: list[dict[str, str]] = []
    for operator in items:
        if not isinstance(operator, Mapping):
            continue

        metadata = operator.get("metadata", {}) if isinstance(operator.get("metadata"), Mapping) else {}
        status = operator.get("status", {}) if isinstance(operator.get("status"), Mapping) else {}
        available, available_reason, available_message = cluster_operator_condition(
            operator,
            "Available",
        )
        degraded, degraded_reason, degraded_message = cluster_operator_condition(
            operator,
            "Degraded",
        )
        progressing, progressing_reason, progressing_message = cluster_operator_condition(
            operator,
            "Progressing",
        )
        rows.append(
            {
                "name": str(metadata.get("name") or "unknown"),
                "version": str(status.get("versions", [{}])[0].get("version") or "-")
                if isinstance(status.get("versions"), list) and status.get("versions")
                else "-",
                "available": available,
                "degraded": degraded,
                "progressing": progressing,
                "reason": next(
                    (
                        value
                        for value in [
                            degraded_reason if degraded == "True" else "",
                            progressing_reason if progressing == "True" else "",
                            available_reason if available != "True" else "",
                        ]
                        if value and value != "-"
                    ),
                    "-",
                ),
                "message": truncate_detail(
                    next(
                        (
                            value
                            for value in [
                                degraded_message if degraded == "True" else "",
                                progressing_message if progressing == "True" else "",
                                available_message if available != "True" else "",
                            ]
                            if value and value != "-"
                        ),
                        "-",
                    ),
                    300,
                ),
            }
        )

    issue_rows = [
        row
        for row in rows
        if row["available"] != "True" or row["degraded"] == "True" or row["progressing"] == "True"
    ]
    selected_rows = issue_rows or rows[:10]
    lines = [
        "Gateway-collected ClusterOperator status evidence from Kubernetes API `/apis/config.openshift.io/v1/clusteroperators`.",
        "Use this to avoid treating historical Failed control-plane/operator installer pods as current outages when operators are healthy.",
        "| ClusterOperator | Version | Available | Degraded | Progressing | Reason | Message |",
        "| :--- | :--- | :---: | :---: | :---: | :--- | :--- |",
    ]
    for row in selected_rows[:15]:
        lines.append(
            "| {name} | {version} | {available} | {degraded} | {progressing} | {reason} | {message} |".format(
                **row
            )
        )
    if not selected_rows:
        lines.append("| - | - | - | - | - | - | - |")

    return "\n".join(lines)


def cron_minute_interval(schedule: str) -> int | None:
    fields = schedule.split()
    if len(fields) < 5:
        return None

    minute_field = fields[0]
    match = re.fullmatch(r"(?:\*|0)/(\d+)", minute_field)
    if not match:
        return None

    interval = int(match.group(1))
    return interval if interval > 0 else None


def requested_minute_interval(context_text: str) -> int | None:
    cron_match = re.search(r"(?:\*|0)/(\d+)", context_text)
    if cron_match:
        interval = int(cron_match.group(1))
        return interval if interval > 0 else None

    minute_match = re.search(r"(?i)(\d+)\s*(분|minute|min)", context_text)
    if minute_match:
        interval = int(minute_match.group(1))
        return interval if interval > 0 else None

    return None


def schedule_interval_summary(schedule: str) -> str:
    interval = cron_minute_interval(schedule)
    if interval is None:
        return "-"

    return f"{interval}분마다"


def format_seconds_duration(value: str) -> str:
    try:
        seconds = int(value)
    except ValueError:
        return value

    if seconds <= 0:
        return f"{seconds}초"
    if seconds % 86400 == 0:
        days = seconds // 86400
        return f"{seconds}초 ({days}일)"
    if seconds % 3600 == 0:
        hours = seconds // 3600
        return f"{seconds}초 ({hours}시간)"
    if seconds % 60 == 0:
        minutes = seconds // 60
        return f"{seconds}초 ({minutes}분)"

    return f"{seconds}초"


def safe_env_value(env_item: Mapping[str, Any]) -> str:
    name = str(env_item.get("name") or "")
    if SECRET_ENV_RE.search(name):
        return "[REDACTED]"

    value = env_item.get("value")
    if value is not None:
        return str(value)

    value_from = env_item.get("valueFrom")
    if isinstance(value_from, Mapping):
        if "secretKeyRef" in value_from:
            return "[REDACTED:valueFrom.secretKeyRef]"
        return f"valueFrom.{next(iter(value_from.keys()), 'unknown')}"

    return "-"


def cronjob_container_summary(cronjob: Mapping[str, Any]) -> tuple[str, list[Mapping[str, Any]]]:
    containers = (
        cronjob.get("spec", {})
        .get("jobTemplate", {})
        .get("spec", {})
        .get("template", {})
        .get("spec", {})
        .get("containers", [])
    )
    if not isinstance(containers, list):
        return "-", []

    images = []
    env_items: list[Mapping[str, Any]] = []
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        image = container.get("image")
        if image:
            images.append(str(image))
        env = container.get("env", [])
        if isinstance(env, list):
            env_items.extend(item for item in env if isinstance(item, Mapping))

    return ", ".join(images) if images else "-", env_items


def cronjob_matches_context(cronjob: Mapping[str, Any], context_text: str) -> bool:
    metadata = cronjob.get("metadata", {}) if isinstance(cronjob.get("metadata"), Mapping) else {}
    spec = cronjob.get("spec", {}) if isinstance(cronjob.get("spec"), Mapping) else {}
    name = str(metadata.get("name") or "")
    namespace = str(metadata.get("namespace") or "")
    schedule = str(spec.get("schedule") or "")
    context = context_text.lower()
    requested_interval = requested_minute_interval(context_text)

    if name and name.lower() in context:
        return True
    if namespace and namespace.lower() in context and ("cron" in context or "크론" in context):
        return True
    if requested_interval is not None and cron_minute_interval(schedule) == requested_interval:
        return True
    if cron_minute_interval(schedule) is not None and re.search(
        r"(?i)(주기|반복|활동|이벤트|activity|schedule|스케줄)",
        context_text,
    ):
        return True

    return False


def build_cronjob_activity_evidence(
    cronjobs_payload: Mapping[str, Any],
    jobs_payload: Mapping[str, Any] | None = None,
    *,
    context_text: str = "",
) -> str:
    cronjobs = cronjobs_payload.get("items")
    if not isinstance(cronjobs, list):
        return "CronJob activity evidence unavailable: API response did not include an items list."

    matched: list[Mapping[str, Any]] = [
        item for item in cronjobs if isinstance(item, Mapping) and cronjob_matches_context(item, context_text)
    ]
    if not matched:
        requested_interval = requested_minute_interval(context_text)
        matched = [
            item
            for item in cronjobs
            if isinstance(item, Mapping)
            and requested_interval is not None
            and cron_minute_interval(str(item.get("spec", {}).get("schedule") or ""))
            == requested_interval
        ]
    if not matched:
        matched = [item for item in cronjobs if isinstance(item, Mapping)][:10]

    matched = sorted(
        matched,
        key=lambda item: (
            str(item.get("metadata", {}).get("namespace") or ""),
            str(item.get("metadata", {}).get("name") or ""),
        ),
    )[:10]
    matched_keys = {
        (
            str(item.get("metadata", {}).get("namespace") or ""),
            str(item.get("metadata", {}).get("name") or ""),
        )
        for item in matched
    }

    lines = [
        "Gateway-collected CronJob activity evidence from Kubernetes API `/apis/batch/v1/cronjobs`.",
        "Use this as primary evidence for scheduled Activity/CronJob questions.",
        "If a matched CronJob uses an interval schedule, answer first whether the observed interval is expected by configuration.",
        "Do not overstate intent from the name alone; use env/settings as policy hints and say when behavior needs log confirmation.",
        "Env seconds are threshold values only; do not infer created-time or idle-time basis unless logs or source confirm it.",
        "",
        "Matched CronJobs:",
        "| Namespace | CronJob | Schedule | Derived interval | Concurrency | Suspend | Successful history | Failed history | Image |",
        "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | ---: | :--- |",
    ]

    policy_env_rows: list[str] = []
    for cronjob in matched:
        metadata = cronjob.get("metadata", {}) if isinstance(cronjob.get("metadata"), Mapping) else {}
        spec = cronjob.get("spec", {}) if isinstance(cronjob.get("spec"), Mapping) else {}
        namespace = str(metadata.get("namespace") or "unknown")
        name = str(metadata.get("name") or "unknown")
        schedule = str(spec.get("schedule") or "-")
        concurrency_policy = str(spec.get("concurrencyPolicy") or "-")
        suspend = str(spec.get("suspend", False))
        success_history = str(spec.get("successfulJobsHistoryLimit", "-"))
        failed_history = str(spec.get("failedJobsHistoryLimit", "-"))
        image_summary, env_items = cronjob_container_summary(cronjob)
        interval_summary = schedule_interval_summary(schedule)
        lines.append(
            f"| {namespace} | `{name}` | `{schedule}` | {interval_summary} | "
            f"{concurrency_policy} | {suspend} | {success_history} | {failed_history} | "
            f"`{image_summary}` |"
        )

        for env_item in env_items:
            env_name = str(env_item.get("name") or "")
            if not CRONJOB_POLICY_ENV_RE.search(env_name):
                continue
            raw_value = safe_env_value(env_item)
            interpreted = format_seconds_duration(raw_value) if raw_value.isdigit() else raw_value
            policy_env_rows.append(f"| {namespace} | `{name}` | `{env_name}` | `{raw_value}` | {interpreted} |")

    lines.extend(
        [
            "",
            "Policy-related environment hints:",
            "| Namespace | CronJob | Env | Raw value | Interpreted value |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    lines.extend(policy_env_rows or ["| - | - | - | - | 관련 env 힌트 없음 |"])

    jobs = jobs_payload.get("items") if isinstance(jobs_payload, Mapping) else None
    recent_job_rows: list[dict[str, Any]] = []
    if isinstance(jobs, list):
        for job in jobs:
            if not isinstance(job, Mapping):
                continue
            metadata = job.get("metadata", {}) if isinstance(job.get("metadata"), Mapping) else {}
            status = job.get("status", {}) if isinstance(job.get("status"), Mapping) else {}
            namespace = str(metadata.get("namespace") or "")
            owner_name = "-"
            owners = metadata.get("ownerReferences", [])
            if isinstance(owners, list):
                for owner in owners:
                    if isinstance(owner, Mapping) and owner.get("kind") == "CronJob":
                        owner_name = str(owner.get("name") or "-")
                        break
            if (namespace, owner_name) not in matched_keys:
                continue

            created_at = str(metadata.get("creationTimestamp") or "")
            recent_job_rows.append(
                {
                    "namespace": namespace,
                    "name": str(metadata.get("name") or "unknown"),
                    "owner": owner_name,
                    "createdAt": created_at,
                    "startTime": str(status.get("startTime") or "-"),
                    "completionTime": str(status.get("completionTime") or "-"),
                    "succeeded": int(status.get("succeeded") or 0),
                    "failed": int(status.get("failed") or 0),
                    "active": int(status.get("active") or 0),
                    "createdSort": parse_rfc3339(created_at) or datetime.min.replace(tzinfo=UTC),
                }
            )

    lines.extend(
        [
            "",
            "Recent Jobs owned by matched CronJobs:",
            "| Namespace | Job | Owner CronJob | Created | Started | Completed | Succeeded | Failed | Active |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | ---: | ---: | ---: |",
        ]
    )
    for row in sorted(recent_job_rows, key=lambda item: item["createdSort"], reverse=True)[:10]:
        lines.append(
            "| {namespace} | `{name}` | `{owner}` | {createdAt} | {startTime} | {completionTime} | "
            "{succeeded} | {failed} | {active} |".format(**row)
        )
    if not recent_job_rows:
        lines.append("| - | - | - | - | - | - | 0 | 0 | 0 |")

    return "\n".join(lines)


def build_ols_query(
    req: ChatRequest,
    image_analysis: str | None = None,
    *,
    policy: Mapping[str, Any] | None = None,
    subject: Mapping[str, Any] | None = None,
    gateway_evidence: str | None = None,
) -> str:
    page_context = {
        key: value
        for key, value in (req.pageContext or {}).items()
        if key in {"href", "pathname", "namespace", "resourceKind", "resourceName"}
    }
    forwarded_to_ols = should_forward_image_attachments_to_ols()
    effective_policy = policy or classify_request_policy(req.message)
    subject_metadata = subject or safe_subject(None)
    query = f"""
[Gateway 보안 경계]
{build_gateway_guardrail(effective_policy)}

[Gateway 정책 결정]
{json.dumps(redact_sensitive(effective_policy), ensure_ascii=False)}

[API 서버 관찰 주체]
{json.dumps(redact_sensitive(subject_metadata), ensure_ascii=False)}

[사용자 질문]
{redact_sensitive(req.message)}

[현재 콘솔 컨텍스트]
{json.dumps(redact_sensitive(page_context), ensure_ascii=False)}

[첨부 이미지]
{build_attachment_context(req.attachments, redact_sensitive(image_analysis) if image_analysis else None, forwarded_to_ols=forwarded_to_ols)}

[Gateway 선조회 증거]
{redact_sensitive(gateway_evidence) if gateway_evidence else "Gateway 선조회 증거 없음"}

이미지/화면 컨텍스트 처리:
- [첨부 이미지]가 `첨부 이미지 없음`이면 현재 콘솔 페이지의 스크린샷이나 이미지가 전달된 것이 아닙니다. 이 경우 답변에 "이미지를 직접 판독할 수 없다", "스크린샷을 볼 수 없다" 같은 문장을 쓰지 말고 [현재 콘솔 컨텍스트]의 `pathname`/`href`와 필요한 OpenShift 도구 조회 결과만 근거로 답하세요.
- [현재 콘솔 컨텍스트]는 URL, namespace, resource metadata입니다. 화면의 시각적 내용 자체라고 단정하지 말고, `/catalog/ns/<namespace>` 같은 경로가 있으면 "경로 기준으로는 Catalog 페이지로 보입니다"처럼 근거 범위를 분리하세요.
- [첨부 이미지]에 Gateway 비전 분석 결과가 없으면 이미지 내부 텍스트, 색상, 표 항목을 보았다고 말하지 마세요. 필요한 경우 이미지 첨부 또는 비전 분석 설정이 필요하다는 점을 별도 전제로만 짧게 표시하세요.

AIOps 리소스 원인분석 라우팅:
- 이 프롬프트에서 "Gateway"는 KOMSCO AI Gateway/BFF 보안 경계를 뜻합니다. 사용자가 Kubernetes Gateway API를 명시적으로 묻지 않았다면 `gateway.networking.k8s.io`, `Gateway`, `GatewayClass` 문서 링크를 추가하지 마세요.
- 사용자가 namespace와 리소스/워크로드 이름을 언급하고 "왜", "원인", "안 떠", "Pending", "CrashLoop", "ImagePull", "Ready", "Secret", "ConfigMap", "PVC", "HPA", "스케일", "지난주 이슈", "최근 운영 이슈"처럼 장애 원인 분석을 묻는 경우 active alert 조회를 우선하지 말고 해당 namespace의 Kubernetes 리소스 조회를 먼저 수행하세요.
- alert 조회는 사용자가 "경고", "alert", "알람"을 명시했거나, 리소스 상태 조회 후 관련 경고를 보강할 때 사용하세요. "활성 alert에 없음"은 HPA, Pod, PVC, Job 장애가 없다는 뜻이 아닙니다.
- HPA/스케일아웃 질문은 `HorizontalPodAutoscaler` 목록 또는 상세를 먼저 조회하고, `TARGETS`, `currentMetrics`, `desiredReplicas`, `currentReplicas`, `minReplicas`, `maxReplicas`, 관련 Deployment/Pod 상태를 근거로 설명하세요.
- Pod/Deployment/워크로드 이름이 주어졌지만 정확한 Pod 이름이 아니면 namespace의 Pod 목록을 먼저 조회하고, `metadata.name`, `labels.app`, ownerReferences가 질문 대상과 맞는 Pod를 선택해 상세 조회하세요.
- 사용자가 Pod 재시작, rollout restart, delete pod, scale 같은 변경 요청을 했지만 대상 namespace 또는 리소스 이름이 없으면 임의로 Gateway API나 다른 동음이의어 리소스로 해석하지 마세요. "대상 미지정"으로 표시하고 `namespace`, `Pod 또는 관리 객체 이름`, 장애 증상만 요청하세요.
- `CreateContainerConfigError`는 Pod의 `status.containerStatuses[*].state.waiting.message`, `envFrom.configMapRef`, `envFrom.secretRef`, volume secret/configMap 참조를 근거로 원인을 설명하세요. Secret 값은 조회하거나 출력하지 마세요.
- PVC/Pending 질문은 PVC 상세와 관련 Pod의 `volumes[*].persistentVolumeClaim`, `status.conditions`, 이벤트 메시지를 근거로 설명하고, 존재하지 않는 StorageClass/Provisioner/BindingMode를 구분하세요.
- namespace 전체의 "최근/지난주/운영 이슈" 요약 질문은 먼저 Pod 목록, HPA 목록, PVC 목록, Job 목록을 확인하고, 비정상 리소스의 대표 상세만 조회해 우선순위를 작성하세요. 최종 답변은 반드시 분석 요약과 조치 항목을 먼저 쓰고, 참고 링크만 단독으로 출력하지 마세요.

CronJob/Activity 분석 프로토콜:
- 사용자가 콘솔 Activity, 반복 실행, CronJob, Job, schedule, 특정 분 단위 주기를 묻는 경우에는 CronJob `spec.schedule`, `spec.concurrencyPolicy`, `successfulJobsHistoryLimit`, `failedJobsHistoryLimit`, container image, lifecycle/retention 관련 env, 최근 Job 실행 이력을 근거로 답하세요.
- `spec.schedule`에서 분 단위 interval이 확인되면 첫 문장에 "네, 설정상 의도된 <N>분 주기입니다"처럼 정상 여부를 먼저 명확히 답하세요.
- 이름만 보고 작업 목적을 단정하지 말고, env 이름에 hibernate/suspend/sleep/idle/delete/ttl/expire/cleanup/retention/prune/archive/max_age/timeout 같은 lifecycle/retention 신호가 확인된 경우에만 해당 정책으로 보인다고 쓰세요.
- 초 단위 env는 사람이 읽는 값으로 같이 풀어 쓰되 "기준값"으로만 표현하세요. 예: `1800`은 30분, `1209600`은 14일입니다. 로그나 소스 근거 없이 생성 후/마지막 사용 후/유휴 시간 기준인지 단정하지 마세요.
- `concurrencyPolicy: Forbid`는 이전 실행이 끝나지 않았을 때 중복 실행을 막는 설정으로 설명하고, `successfulJobsHistoryLimit`는 콘솔에 남는 성공 Job 이력 수를 설명할 때만 사용하세요.
- 실제로 어떤 리소스를 처리했는지는 CronJob 설정만으로 단정하지 말고 최근 Job 로그 확인이 필요하다고 분리하세요.
- 로그 확인 명령은 가능하면 `oc -n <namespace> logs job/<job-name>` 형태로 제시하고, 최근 Job 이름 확인 명령은 `oc -n <namespace> get jobs --sort-by=.metadata.creationTimestamp | grep <cronjob-name>` 형태를 우선 제시하세요.

Pod 상태/재시작 분석 프로토콜:
- Pod 상태 또는 재시작 이력 질문은 현재 상태와 과거 재시작 이력을 먼저 분리하세요. 현재 상태는 `status.phase`, `Ready` condition, `status.containerStatuses[*].ready`, `status.containerStatuses[*].state`를 기준으로 표현하세요.
- `restartCount`만 보고 현재 `CrashLoopBackOff`, "현재 진행 중", "지속 오류"라고 단정하지 마세요. 현재 `state.waiting.reason` 또는 `oc get pods` STATUS가 `CrashLoopBackOff`인 경우에만 현재 CrashLoopBackOff라고 쓰세요.
- `restartCount`는 Pod 단위가 아니라 container 단위입니다. 멀티컨테이너 Pod는 반드시 container 이름별로 `restartCount`, `lastState.terminated.reason`, `exitCode`, `finishedAt`, 현재 `state`를 구분해 쓰세요.
- `restartCount`는 누적 카운터입니다. 특정 시간 구간의 증가량이나 여러 종료 시각이 확인되지 않았다면 "빈번", "빈도", "계속 발생"이라고 표현하지 말고 "재시작 이력/누적 재시작 횟수"라고 쓰세요.
- `oc get pods -A --sort-by=.status.containerStatuses[0].restartCount`는 첫 번째 컨테이너 기준이라 멀티컨테이너 Pod의 재시작을 놓칠 수 있습니다. 가능하면 JSON 결과의 모든 `containerStatuses[*]`를 기준으로 상위 항목을 판단하세요.
- `Running` 및 `Ready=True`이면서 restartCount가 높은 Pod는 "현재 CrashLoop"가 아니라 "과거 또는 최근 재시작 이력/최근 복구됨"으로 표현하고, 마지막 종료 시각과 현재 startedAt을 같이 제시하세요.
- `status.phase=Failed`이고 현재 `state.terminated`인 Pod는 현재 재시작 중인 Pod가 아니라 종료된 Pod 객체일 수 있습니다. `startTime`, `finishedAt`, owner/controller/operator 상태를 함께 보고 "과거 실패 이력"과 "현재 장애"를 분리하세요.
- OpenShift 관리 namespace의 installer/revisioner/pruner 같은 단발성 작업 Pod가 Failed로 남아 있더라도 관련 ClusterOperator가 `Available=True`, `Degraded=False`, `Progressing=False`이면 현재 제어면 장애라고 단정하지 마세요. "과거 실패 Pod 이력, 현재 Operator 상태는 정상"처럼 표현하세요.
- `Last State`가 `Error`와 exit code만 제공되면 일반적인 원인을 나열하기 전에 `--previous` 로그 또는 이벤트 근거를 확인하세요. `exitCode=137`은 OOMKilled일 수 있지만 `reason`이 `OOMKilled`가 아니면 단정하지 말고 "강제 종료 가능성, 추가 확인 필요"로 표현하세요.
- 이전 종료 원인을 볼 때는 `oc logs <pod> -n <namespace> -c <container> --previous --tail=120`처럼 컨테이너명을 포함하세요. 단일 컨테이너 Pod도 컨테이너명을 명시하면 근거가 더 명확합니다.
- 우선순위는 1) 현재 `Pending`, `NotReady`, `CrashLoopBackOff`, `ImagePullBackOff` 등 비정상 상태, 2) 현재 Running/Ready지만 최근에 재시작된 컨테이너, 3) 오래된 재시작 이력 순으로 정리하세요.
- `ImagePullBackOff` 또는 `ErrImagePull`은 `status.containerStatuses[*].state.waiting.message`와 Events를 최우선 근거로 삼고, catalog/marketplace 성격의 Pod라면 관련 `CatalogSource` 상태와 image registry 접근성도 확인 항목에 포함하세요.
- 최종 답변 표에는 가능한 경우 `Namespace`, `Pod`, `Container`, `현재 상태`, `Ready`, `Restart Count`, `Last State/Exit`, `마지막 종료 시각`, `근거`를 포함하세요.

OpenShift 경고 분석 프로토콜:
- 사용자가 "최근 경고", "alert", "우선 확인 항목"을 묻는 경우 먼저 active alert 목록을 조회하세요.
- 주요 alert별 상세 조사는 아래 순서를 따르세요. 해당 상세 조회가 실패하면 실패 사실과 이유를 답변에 포함하고, 확인하지 못한 원인은 추정으로만 표현하세요.
- 상태 표현은 엄격히 구분하세요.
  - "상세 확인됨": 관련 리소스 상세 조회를 수행했고, 답변에 쓰는 field path가 그 결과에 존재하는 경우에만 사용하세요.
  - "Alert 근거 확인": active alert의 labels/annotations만 근거로 삼은 경우에 사용하세요.
  - "추가 확인 필요": 상세 조회를 하지 않았거나 도구가 실패한 경우에 사용하세요.
- 상세 조회를 실제로 호출하지 않은 리소스의 `status.conditions`, `containerStatuses`, `events`, Secret/ConfigMap 존재 여부를 확인했다고 쓰지 마세요.
- KubePodNotReady:
  1. alert label의 namespace/pod 값으로 `resources_get`을 사용해 `apiVersion: v1`, `kind: Pod`, `namespace`, `name`을 조회하세요.
  2. Pod의 `status.conditions`, `status.containerStatuses[*].state.waiting.reason/message`, `spec.containers[*].image`, ownerReferences를 근거로 원인을 작성하세요.
  3. 이벤트 조회 도구가 있으면 해당 namespace/pod의 events도 조회하세요. 이벤트 도구가 없거나 실패하면 events는 추가 확인 명령으로만 제시하세요.
  4. container가 시작하지 못한 상태(ImagePullBackOff, ErrImagePull 등)이면 `oc logs`를 원인 확인의 첫 명령으로 제시하지 마세요.
- ClusterNotUpgradeable:
  1. `resources_get`으로 `apiVersion: config.openshift.io/v1`, `kind: ClusterVersion`, `name: version`을 조회하세요.
  2. `status.conditions[type=Upgradeable]`의 status/reason/message를 최우선 근거로 사용하세요.
  3. `ClusterOperator` 문제라고 쓰려면 ClusterOperator 상세나 요약에서 실제 Degraded/Unavailable/Progressing이 확인된 경우에만 그렇게 표현하세요.
- AlertmanagerReceiversNotConfigured:
  1. alert 결과만으로 ConfigMap 또는 Secret 이름을 만들어 조회하지 마세요.
  2. Secret 내용은 권한 또는 보안 정책상 직접 조회가 제한될 수 있으므로, 조회 시도 대신 "설정 리소스 확인은 권한상 제한될 수 있음"으로 표현하고 사용자가 확인할 안전한 명령을 제시하세요.
- etcdDatabaseHighFragmentationRatio:
  1. alert annotation의 비율/instance/pod를 근거로 설명하세요.
  2. defrag는 즉시 실행 지시가 아니라 상태 확인, 영향도 판단, 공식 절차 검토, 승인 후 수행으로 표현하세요.
- Watchdog:
  1. Alertmanager 경로 확인용 상시 경고로 분류하고 우선 조치 대상에서 제외하세요.

답변 지침:
- 실시간 클러스터 상태(경고, 이벤트, Pod, Node, 리소스, 메트릭, 로그)가 필요한 질문이면 OpenShift MCP 도구를 먼저 사용하세요.
- 도구 결과에 없는 alert, pod, node, namespace, resource 이름이나 상태를 만들지 마세요.
- 도구를 사용할 수 없거나 결과가 부족하면 확인하지 못했다고 말하고 사용자가 확인할 명령을 제시하세요.
- 참고 링크는 사용자가 문서를 요청했거나 답변의 대상 리소스와 직접 관련된 경우에만 제시하세요. KOMSCO AI Gateway 보안 경계를 설명하면서 Kubernetes Gateway API 또는 GatewayClass 문서를 붙이지 마세요.
- 참고 링크가 필요한 경우에도 답변의 근거가 된 리소스/경고와 직접 관련된 문서만 1-2개로 제한하세요. Pod 상태 분석 답변 끝에 `Extension APIs`, `Admission plugins`, `TokenReview`, `ClusterRole`처럼 분석 대상과 무관한 API 색인 링크를 붙이지 마세요.
- alert 이름이나 summary만으로 원인을 단정하지 마세요. 원인, 영향, 조치 우선순위는 관련 리소스 상세 조회 결과가 있을 때만 "확인됨"으로 표현하세요.
- 도구 결과로 확인한 사실과 추가 확인이 필요한 추정을 분리해서 작성하세요. 최종 답변에는 각 주요 항목마다 "근거"를 짧게 포함하세요.
- 도구 실패나 권한 제한이 있으면 숨기지 말고 "조회 실패/권한 제한" 항목으로 짧게 표시하세요.
- 사용자가 실행 가능한 조치와 근거를 함께 제시하세요.
- Secret, token, password, private key는 절대 출력하지 마세요.
- etcd defrag, 리소스 삭제, 재시작, 설정 변경 같은 위험 작업은 "즉시 수행"으로 단정하지 말고 상태 확인, 영향 판단, 공식 절차 검토, 승인 후 수행 순서로 표현하세요.
- 대상이 특정되지 않은 재시작 요청에는 `oc get pods -A`를 기본 제안하지 마세요. 현재 콘솔 컨텍스트 namespace가 있으면 `oc get pods -n <namespace>`를 제시하고, namespace도 없으면 namespace와 Pod/Deployment/StatefulSet/DaemonSet 이름을 먼저 요청하세요.
- `oc delete pod`는 기본 재시작 방법으로 제시하지 마세요. ownerReferences, replica 수, PDB, 현재 rollout 상태를 확인했고 승인 단계가 있다는 조건을 명시한 경우에만 보조 선택지로 언급하세요. Deployment가 확인되면 승인 후 계획의 기본 후보는 `oc rollout restart deployment/<name> -n <namespace>`입니다.
- KubePodNotReady는 대상 Pod의 status.containerStatuses와 events를 확인하기 전까지 원인을 단정하지 마세요. container가 시작하지 못한 상태면 oc logs를 우선 명령으로 제시하지 말고 oc describe pod/events를 먼저 제시하세요.
- KubePodNotReady가 openshift-marketplace의 catalog Pod라면 이미지 풀, registry, CatalogSource/PackageManifest 영향 범위를 먼저 확인하고 일반 업무 서비스 장애로 단정하지 마세요.
- ClusterNotUpgradeable는 ClusterOperator 장애로 단정하지 마세요. ClusterVersion conditions 또는 oc adm upgrade 상당 결과의 reason/message를 확인하고, ClusterOperator가 실제 Degraded/Unavailable/Progressing일 때만 Operator 문제라고 표현하세요.
- AlertmanagerReceiversNotConfigured는 alert 결과만으로 특정 ConfigMap/Secret 이름을 만들지 말고, 권한상 직접 확인이 제한될 수 있음을 표시하세요.
- Watchdog alert는 Alertmanager 경로 확인용 상시 경고임을 설명하고 우선 조치 대상에서 제외하세요.
- Markdown은 GitHub Flavored Markdown으로 작성하고, 코드블록은 반드시 삼중 백틱으로 열고 삼중 백틱으로 닫으세요.
- 코드블록 안에는 실행 가능한 명령만 넣고, "Pod 로그 확인" 같은 설명 문장은 코드블록 밖에 작성하세요.
- OpenShift 관점에서 설명하세요.
"""
    return redact_sensitive(query)


async def analyze_image_attachments(
    attachments: list[ImageAttachment],
    user_message: str,
) -> str | None:
    if not attachments:
        return None

    config = get_vision_config()
    if not config:
        return None

    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                f"{VISION_SYSTEM_PROMPT}\n\n"
                f"User request: {user_message.strip() or 'Analyze the attached OpenShift image.'}"
            ),
        }
    ]
    for attachment in attachments:
        content.append(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{attachment.mimeType};base64,{attachment.data}",
                },
            }
        )

    headers = {"Content-Type": "application/json"}
    api_key = config.get("api_key")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": config["model"],
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
        "max_tokens": 800,
    }

    async with httpx.AsyncClient(timeout=httpx.Timeout(90.0, connect=10.0)) as client:
        response = await client.post(
            f"{config['base_url']}/chat/completions",
            headers=headers,
            json=payload,
        )
        if response.status_code >= 400:
            body = response.text[:500]
            return f"비전 분석 실패: provider returned HTTP {response.status_code}: {body}"

        result = response.json()

    choices = result.get("choices") if isinstance(result, Mapping) else None
    if not isinstance(choices, list) or not choices:
        return "비전 분석 실패: provider response did not include choices"

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        return "비전 분석 실패: provider response choice format is invalid"

    message = first_choice.get("message")
    if not isinstance(message, Mapping):
        return "비전 분석 실패: provider response message format is invalid"

    content_text = message.get("content")
    if isinstance(content_text, str) and content_text.strip():
        return content_text.strip()

    return "비전 분석 실패: provider response content is empty"


async def stream_with_heartbeats(
    events: AsyncIterator[dict[str, Any]],
    run_id: str,
) -> AsyncIterator[dict[str, Any]]:
    queue: asyncio.Queue[dict[str, Any] | BaseException | None] = asyncio.Queue()
    started_at = time.monotonic()

    async def produce() -> None:
        try:
            async for event in events:
                await queue.put(event)
        except BaseException as exc:
            await queue.put(exc)
        finally:
            await queue.put(None)

    producer = asyncio.create_task(produce())

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=RUN_HEARTBEAT_SECONDS)
            except TimeoutError:
                yield {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "waiting",
                    "message": "Lightspeed 응답 스트림 대기 중",
                    "elapsedMs": int((time.monotonic() - started_at) * 1000),
                }
                continue

            if item is None:
                break

            if isinstance(item, BaseException):
                raise item

            yield item
    finally:
        if not producer.done():
            producer.cancel()


async def call_ols_stream(
    user_auth_header: str,
    query: str,
    conversation_id: str | None,
    attachments: list[ImageAttachment],
) -> AsyncIterator[dict[str, Any]]:
    if DEV_ECHO or not OLS_BASE_URL:
        yield {
            "type": "text",
            "content": "DEV_ECHO: Gateway is running. Configure OLS_BASE_URL for Lightspeed streaming.\n\n",
        }
        yield {"type": "text", "content": query[:1200]}
        yield {"type": "end", "conversationId": conversation_id}
        return

    payload = build_ols_payload(
        query,
        conversation_id,
        attachments,
        forward_image_attachments=should_forward_image_attachments_to_ols(),
    )

    async with httpx.AsyncClient(
        verify=OLS_CA_FILE,
        timeout=httpx.Timeout(300.0, connect=10.0),
    ) as client:
        async with client.stream(
            "POST",
            f"{OLS_BASE_URL}/v1/streaming_query",
            headers={
                "Accept": "text/event-stream",
                "Authorization": user_auth_header,
                "Content-Type": "application/json",
            },
            json=payload,
        ) as response:
            if response.status_code >= 400:
                body = await response.aread()
                raise HTTPException(
                    status_code=response.status_code,
                    detail=body.decode("utf-8", errors="replace"),
                )

            content_type = response.headers.get("content-type", "")
            if "text/event-stream" not in content_type:
                async for event in split_plain_text_events(response.aiter_text()):
                    yield event
                return

            buffer = ""
            async for chunk in response.aiter_text():
                if not chunk:
                    continue

                buffer += chunk
                frames = buffer.split("\n\n")
                buffer = frames.pop() or ""

                for frame in frames:
                    data_lines = [
                        line[len("data:") :].strip()
                        for line in frame.splitlines()
                        if line.startswith("data:")
                    ]
                    if not data_lines:
                        continue

                    raw = "\n".join(data_lines)
                    if not raw or raw == "[DONE]":
                        continue

                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError:
                        tool_event = parse_tool_text_line(raw)
                        if tool_event:
                            yield tool_event
                        else:
                            yield {"type": "text", "content": raw}
                        continue

                    yield event

            if buffer.strip() and not buffer.lstrip().startswith("data:"):
                async def iter_buffer() -> AsyncIterator[str]:
                    yield buffer

                async for event in split_plain_text_events(iter_buffer()):
                    yield event


def normalize_ols_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = event.get("event") or event.get("type")

    if event_type == "text":
        return {
            "type": "text",
            "content": event.get("data") or event.get("content") or "",
        }

    if event_type == "end":
        return {"type": "end", "conversationId": event.get("conversation_id")}

    if event_type in {"tool_call", "tool_result"}:
        if event.get("detail") is not None and event.get("summary") is not None:
            return event

        return normalize_tool_event(event_type, event)

    return event


def should_filter_gateway_api_references(message: str) -> bool:
    return not bool(EXPLICIT_KUBERNETES_GATEWAY_API_RE.search(message))


def should_filter_low_signal_references(message: str) -> bool:
    return not bool(EXPLICIT_OPENSHIFT_DOC_REFERENCE_RE.search(message))


def is_disallowed_gateway_api_reference(line: str) -> bool:
    return bool(DISALLOWED_GATEWAY_API_REFERENCE_RE.search(line))


def is_low_signal_reference(line: str) -> bool:
    return bool(LOW_SIGNAL_REFERENCE_RE.search(line))


class TextReferenceFilter:
    def __init__(
        self,
        *,
        filter_gateway_api_references: bool,
        filter_low_signal_references: bool = False,
        normalize_restart_language: bool = False,
    ) -> None:
        self.filter_gateway_api_references = filter_gateway_api_references
        self.filter_low_signal_references = filter_low_signal_references
        self.normalize_restart_language = normalize_restart_language
        self.pending = ""
        self.held_lines: list[str] = []

    def filter(self, content: str, *, final: bool = False) -> str:
        if (
            not self.filter_gateway_api_references
            and not self.filter_low_signal_references
            and not self.normalize_restart_language
        ):
            return content

        text = f"{self.pending}{content}"
        if final:
            complete = text
            self.pending = ""
        else:
            last_newline = text.rfind("\n")
            if last_newline == -1:
                self.pending = text
                return ""

            complete = text[: last_newline + 1]
            self.pending = text[last_newline + 1 :]

        if self.normalize_restart_language:
            complete = normalize_pod_restart_language(complete)

        lines = complete.splitlines(keepends=True)
        filtered_lines: list[str] = []
        for line in lines:
            if self.is_disallowed_reference(line):
                self.held_lines = []
                continue

            if self.held_lines:
                if not line.strip():
                    self.held_lines.append(line)
                    continue

                filtered_lines.extend(self.held_lines)
                self.held_lines = []

            if line.strip() == "---":
                self.held_lines = [line]
                continue

            filtered_lines.append(line)

        return "".join(filtered_lines)

    def is_disallowed_reference(self, line: str) -> bool:
        return (
            self.filter_gateway_api_references
            and is_disallowed_gateway_api_reference(line)
        ) or (
            self.filter_low_signal_references
            and is_low_signal_reference(line)
        )

    def flush(self) -> str:
        filtered = self.filter("", final=True)
        if self.held_lines:
            filtered = f"{filtered}{''.join(self.held_lines)}"
            self.held_lines = []
        return filtered


async def fetch_ocp_json(
    client: httpx.AsyncClient,
    path: str,
    authorization: str,
    *,
    required: bool = False,
) -> Mapping[str, Any] | None:
    response = await client.get(
        f"{OPENSHIFT_API_URL}{path}",
        headers={
            "Accept": "application/json",
            "Authorization": authorization,
        },
    )
    if response.status_code >= 400:
        if required:
            body = response.text[:500]
            raise HTTPException(
                status_code=response.status_code,
                detail=f"OpenShift API request failed for {path}: {body}",
            )

        return None

    payload = response.json()
    if isinstance(payload, Mapping):
        return payload

    return None


async def collect_pod_status_evidence(user_auth_header: str) -> str:
    if not OPENSHIFT_API_URL:
        return "Pod status evidence unavailable: OPENSHIFT_API_URL is not configured."

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        pods_payload = await fetch_ocp_json(client, "/api/v1/pods", user_auth_header)
        cluster_operators_payload = await fetch_ocp_json(
            client,
            "/apis/config.openshift.io/v1/clusteroperators",
            user_auth_header,
        )

    if not pods_payload:
        return (
            "Pod status evidence unavailable: Kubernetes API pod list was not returned. "
            "This may be a permission or API availability issue."
        )

    evidence = build_pod_status_evidence(pods_payload)
    if cluster_operators_payload:
        evidence = append_gateway_evidence(
            evidence,
            build_cluster_operator_status_evidence(cluster_operators_payload),
        )

    return evidence


async def collect_cronjob_activity_evidence(user_auth_header: str, context_text: str) -> str:
    if not OPENSHIFT_API_URL:
        return "CronJob activity evidence unavailable: OPENSHIFT_API_URL is not configured."

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        cronjobs_payload = await fetch_ocp_json(client, "/apis/batch/v1/cronjobs", user_auth_header)
        jobs_payload = await fetch_ocp_json(client, "/apis/batch/v1/jobs?limit=500", user_auth_header)

    if not cronjobs_payload:
        return (
            "CronJob activity evidence unavailable: Kubernetes API CronJob list was not returned. "
            "This may be a permission or API availability issue."
        )

    return build_cronjob_activity_evidence(
        cronjobs_payload,
        jobs_payload,
        context_text=context_text,
    )


def log_audit_record(record: Mapping[str, Any]) -> None:
    print(
        json.dumps({"aiopsAudit": redact_sensitive(dict(record))}, ensure_ascii=False),
        flush=True,
    )


async def fetch_self_subject_review(user_auth_header: str) -> dict[str, Any]:
    if not OPENSHIFT_API_URL:
        return safe_subject(None)

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(10.0, connect=5.0),
    ) as client:
        response = await client.post(
            f"{OPENSHIFT_API_URL}/apis/authentication.k8s.io/v1/selfsubjectreviews",
            headers={
                "Accept": "application/json",
                "Authorization": user_auth_header,
                "Content-Type": "application/json",
            },
            json={
                "apiVersion": "authentication.k8s.io/v1",
                "kind": "SelfSubjectReview",
            },
        )

    if response.status_code >= 400:
        body = response.text[:500]
        raise HTTPException(
            status_code=response.status_code,
            detail=f"OpenShift subject review failed: {body}",
        )

    payload = response.json()
    user_info = payload.get("status", {}).get("userInfo", {}) if isinstance(payload, Mapping) else {}
    return safe_subject(user_info if isinstance(user_info, Mapping) else None)


def summarize_policy_detail(policy: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            f"decision: {policy.get('decision')}",
            f"risk: {policy.get('risk')}",
            f"mutationAllowed: {policy.get('mutationAllowed')}",
            f"reason: {policy.get('reason')}",
        ]
    )


def summarize_subject_detail(subject: Mapping[str, Any], *, live_review: bool) -> str:
    if not live_review:
        return "OPENSHIFT_API_URL 미설정: bearer 형식만 확인했고 live SelfSubjectReview는 건너뜀"

    return "\n".join(
        [
            f"username: {subject.get('username')}",
            f"uid: {subject.get('uid')}",
            f"groupsDigest: {subject.get('groupsDigest')}",
            f"authenticatedByCluster: {subject.get('authenticatedByCluster')}",
        ]
    )


def build_action_proposal_fallback(req: ChatRequest, policy: Mapping[str, Any]) -> str:
    return "\n".join(
        [
            "현재 요청은 변경/재시작/삭제/스케일/패치 계열 작업으로 분류되어 직접 실행할 수 없습니다.",
            "",
            "### 조치 제안",
            f"- 요청: {redact_sensitive(req.message.strip()) or '미지정'}",
            "- 현재 단계: Gateway Phase 0-1",
            f"- 정책 결정: `{policy.get('decision')}`",
            "- 실행 가능 범위: 읽기 전용 증거 수집, 영향도 설명, 승인 전 조치 계획 작성",
            "",
            "### 승인 필요 여부",
            "- 필요함. 실제 mutation 실행은 Approval API와 Action Executor 단계에서만 허용됩니다.",
            "",
            "### 추가로 필요한 대상 정보",
            "- namespace",
            "- Pod 또는 관리 객체(Deployment/StatefulSet/DaemonSet 등) 이름",
            "- 원하는 작업이 단순 재시작인지, 장애 원인 분석 후 조치인지",
        ]
    )


def build_empty_answer_fallback(
    req: ChatRequest,
    policy: Mapping[str, Any],
    tool_results: list[Mapping[str, Any]],
) -> str:
    if policy.get("decision") == "action_proposal_only":
        return build_action_proposal_fallback(req, policy)

    lines = [
        "Live 조회는 완료됐지만 모델의 최종 요약 텍스트가 비어 있어 Gateway가 안전한 요약을 생성했습니다.",
        "",
        f"- 질문: {redact_sensitive(req.message.strip()) or '미지정'}",
    ]
    if tool_results:
        lines.extend(["", "### 확인된 도구 결과"])
        for index, event in enumerate(tool_results[-3:], start=1):
            name = event.get("name") or "tool_result"
            status_text = event.get("status") or "-"
            summary = event.get("summary") or event.get("detail") or "-"
            lines.append(f"{index}. `{name}` status={status_text}: {truncate_detail(str(summary), 500)}")
    else:
        lines.extend(["", "- 도구 결과가 없어 현재 답변은 추가 조회가 필요합니다."])

    lines.extend(
        [
            "",
            "### 다음 확인",
            "- 위 도구 결과의 상세 진행 항목을 기준으로 상태/원인/조치 우선순위를 다시 요청하세요.",
        ]
    )
    return "\n".join(lines)


@app.get("/v1/cluster/summary")
async def cluster_summary(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_auth_header = verify_bearer_header(authorization)
    if not OPENSHIFT_API_URL:
        raise HTTPException(status_code=503, detail="OPENSHIFT_API_URL is not configured")

    async with httpx.AsyncClient(
        verify=OPENSHIFT_API_CA_FILE,
        timeout=httpx.Timeout(20.0, connect=5.0),
    ) as client:
        nodes_payload = await fetch_ocp_json(
            client,
            "/api/v1/nodes",
            user_auth_header,
            required=True,
        )
        node_metrics_payload = await fetch_ocp_json(
            client,
            "/apis/metrics.k8s.io/v1beta1/nodes",
            user_auth_header,
        )
        cluster_version_payload = await fetch_ocp_json(
            client,
            "/apis/config.openshift.io/v1/clusterversions/version",
            user_auth_header,
        )
        cluster_operators_payload = await fetch_ocp_json(
            client,
            "/apis/config.openshift.io/v1/clusteroperators",
            user_auth_header,
        )

    return build_cluster_summary(
        nodes_payload or {"items": []},
        node_metrics_payload,
        cluster_version_payload,
        cluster_operators_payload,
    )


@app.post("/v1/chat/stream")
async def chat_stream(
    req: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing OpenShift bearer token")

    async def generate() -> AsyncIterator[str]:
        run_id = req.runId or f"run-{uuid.uuid4()}"
        request_id = f"req-{uuid.uuid4()}"
        incident_id = req.conversationId or f"inc-{uuid.uuid4()}"
        policy = classify_request_policy(req.message)
        subject = safe_subject(None)
        gateway_evidence: str | None = None
        text_reference_filter = TextReferenceFilter(
            filter_gateway_api_references=should_filter_gateway_api_references(req.message),
            filter_low_signal_references=should_filter_low_signal_references(req.message),
            normalize_restart_language=should_collect_pod_status_evidence(req.message),
        )

        try:
            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "started",
                    "message": "Gateway 실행 루프 시작",
                    "elapsedMs": 0,
                }
            )
            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-security-boundary",
                    "name": "security_boundary",
                    "summary": "Phase 0-1 보안 경계 적용",
                }
            )
            yield sse(
                {
                    "type": "tool_result",
                    "detail": (
                        "UserToken은 Gateway 내부와 OLS forwarding에만 사용합니다.\n"
                        "Agent/Model prompt, audit payload, evidence event에는 redacted metadata만 전달합니다.\n"
                        "Mutation execution은 Phase 0-1에서 비활성화되어 있습니다."
                    ),
                    "id": f"{request_id}-security-boundary",
                    "name": "security_boundary",
                    "status": "success",
                    "summary": "Gateway credential boundary 확인",
                }
            )
            yield sse({"type": "tool_call", "name": "access_check"})
            await verify_user_access(authorization, req)
            validate_image_attachments(req.attachments)
            yield sse({"type": "tool_result", "name": "access_check", "result": "ok"})

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-subject-review",
                    "name": "subject_review",
                    "summary": "API 서버 관찰 주체 확인",
                }
            )
            subject = await fetch_self_subject_review(authorization)
            live_review = bool(OPENSHIFT_API_URL)
            yield sse(
                {
                    "type": "tool_result",
                    "detail": summarize_subject_detail(subject, live_review=live_review),
                    "id": f"{request_id}-subject-review",
                    "name": "subject_review",
                    "result": subject,
                    "status": "success" if live_review else "skipped",
                    "summary": "주체 확인 완료" if live_review else "주체 확인 생략",
                }
            )

            yield sse(
                {
                    "type": "tool_call",
                    "id": f"{request_id}-policy-check",
                    "name": "policy_check",
                    "summary": "읽기 전용 정책 확인",
                }
            )
            yield sse(
                {
                    "type": "tool_result",
                    "detail": summarize_policy_detail(policy),
                    "id": f"{request_id}-policy-check",
                    "name": "policy_check",
                    "result": policy,
                    "status": "success",
                    "summary": (
                        "Action proposal only"
                        if policy.get("decision") == "action_proposal_only"
                        else "Read-only evidence allowed"
                    ),
                }
            )
            accepted_audit_record = build_trace_record(
                action="chat_request_accepted",
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
                target={"attachments": len(req.attachments), "messageLength": len(req.message)},
            )
            log_audit_record(accepted_audit_record)
            yield sse(
                {
                    "type": "tool_result",
                    "detail": json.dumps(
                        redact_sensitive(accepted_audit_record),
                        ensure_ascii=False,
                        indent=2,
                    ),
                    "id": accepted_audit_record["auditId"],
                    "name": "audit_record",
                    "status": "success",
                    "summary": "감사 레코드 기록",
                }
            )

            if req.attachments:
                yield sse({"type": "tool_call", "name": "attachment_check"})
                yield sse(
                    {
                        "type": "tool_result",
                        "name": "attachment_check",
                        "result": {
                            "images": len(req.attachments),
                            "totalBytes": sum(item.size for item in req.attachments),
                        },
                    }
                )

            image_analysis = None
            if req.attachments:
                yield sse({"type": "tool_call", "name": "vision_analysis"})
                image_analysis = await analyze_image_attachments(req.attachments, req.message)
                yield sse(
                    {
                        "type": "tool_result",
                        "name": "vision_analysis",
                        "result": "ok" if image_analysis else "not_configured",
                    }
                )

            if should_collect_cronjob_activity_evidence(req.message, image_analysis):
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-cronjob-activity-evidence",
                        "name": "cronjob_activity_evidence",
                        "summary": "CronJob/Activity 주기 증거 수집",
                    }
                )
                try:
                    cronjob_context = "\n".join(
                        item for item in [req.message, image_analysis] if item
                    )
                    cronjob_evidence = await collect_cronjob_activity_evidence(
                        authorization,
                        cronjob_context,
                    )
                    evidence_status = (
                        "skipped"
                        if cronjob_evidence.startswith("CronJob activity evidence unavailable:")
                        else "success"
                    )
                    gateway_evidence = append_gateway_evidence(gateway_evidence, cronjob_evidence)
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": cronjob_evidence,
                            "id": f"{request_id}-cronjob-activity-evidence",
                            "name": "cronjob_activity_evidence",
                            "status": evidence_status,
                            "summary": "CronJob/Activity 주기 증거 수집 완료",
                        }
                    )
                except Exception as exc:
                    cronjob_evidence = (
                        f"CronJob activity evidence unavailable: {type(exc).__name__}: {exc}"
                    )
                    gateway_evidence = append_gateway_evidence(gateway_evidence, cronjob_evidence)
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": cronjob_evidence,
                            "id": f"{request_id}-cronjob-activity-evidence",
                            "name": "cronjob_activity_evidence",
                            "status": "error",
                            "summary": "CronJob/Activity 주기 증거 수집 실패",
                        }
                    )

            if should_collect_pod_status_evidence(req.message):
                yield sse(
                    {
                        "type": "tool_call",
                        "id": f"{request_id}-pod-status-evidence",
                        "name": "pod_status_evidence",
                        "summary": "Pod 상태/재시작 증거 수집",
                    }
                )
                try:
                    pod_evidence = await collect_pod_status_evidence(authorization)
                    evidence_status = (
                        "skipped"
                        if pod_evidence.startswith("Pod status evidence unavailable:")
                        else "success"
                    )
                    gateway_evidence = append_gateway_evidence(gateway_evidence, pod_evidence)
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": pod_evidence,
                            "id": f"{request_id}-pod-status-evidence",
                            "name": "pod_status_evidence",
                            "status": evidence_status,
                            "summary": "Pod 상태/재시작 증거 수집 완료",
                        }
                    )
                except Exception as exc:
                    pod_evidence = f"Pod status evidence unavailable: {type(exc).__name__}: {exc}"
                    gateway_evidence = append_gateway_evidence(gateway_evidence, pod_evidence)
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": pod_evidence,
                            "id": f"{request_id}-pod-status-evidence",
                            "name": "pod_status_evidence",
                            "status": "error",
                            "summary": "Pod 상태/재시작 증거 수집 실패",
                        }
                    )

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "lightspeed",
                    "message": "실제 OpenShift Lightspeed로 스트림 요청 전달",
                }
            )
            ols_query = build_ols_query(
                req,
                image_analysis,
                policy=policy,
                subject=subject,
                gateway_evidence=gateway_evidence,
            )
            emitted_answer_text = False
            ols_tool_results: list[Mapping[str, Any]] = []
            async for ols_event in stream_with_heartbeats(
                call_ols_stream(
                    authorization,
                    ols_query,
                    req.conversationId,
                    req.attachments,
                ),
                run_id,
            ):
                normalized_event = normalize_ols_event(ols_event)
                if normalized_event.get("type") == "text":
                    filtered_content = text_reference_filter.filter(
                        str(normalized_event.get("content") or "")
                    )
                    if filtered_content:
                        if filtered_content.strip():
                            emitted_answer_text = True
                        yield sse({"type": "text", "content": filtered_content})
                    continue

                if normalized_event.get("type") == "end":
                    final_text = text_reference_filter.flush()
                    if final_text:
                        if final_text.strip():
                            emitted_answer_text = True
                        yield sse({"type": "text", "content": final_text})

                yield sse(normalized_event)
                if normalized_event.get("type") == "tool_result":
                    ols_tool_results.append(dict(normalized_event))
                    evidence_ref = build_evidence_reference(
                        event=normalized_event,
                        incident_id=incident_id,
                        run_id=run_id,
                        subject=subject,
                    )
                    yield sse(
                        {
                            "type": "tool_call",
                            "id": evidence_ref["evidenceId"],
                            "name": "evidence_ref",
                            "summary": "증거 참조 생성",
                        }
                    )
                    yield sse(
                        {
                            "type": "tool_result",
                            "detail": json.dumps(
                                redact_sensitive(evidence_ref),
                                ensure_ascii=False,
                                indent=2,
                            ),
                            "id": evidence_ref["evidenceId"],
                            "name": "evidence_ref",
                            "result": evidence_ref,
                            "status": "success",
                            "summary": f"{evidence_ref['evidenceId']} 기록",
                        }
                    )

            if not emitted_answer_text:
                yield sse(
                    {
                        "type": "text",
                        "content": build_empty_answer_fallback(req, policy, ols_tool_results),
                    }
                )

            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "completed",
                    "message": "Gateway 실행 루프 완료",
                }
            )
            completed_audit_record = build_trace_record(
                action="chat_request_completed",
                incident_id=incident_id,
                policy=policy,
                request_id=request_id,
                run_id=run_id,
                subject=subject,
            )
            log_audit_record(completed_audit_record)
            yield sse("[DONE]")
        except HTTPException as exc:
            log_audit_record(
                build_trace_record(
                    action="chat_request_failed",
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                    target={"error": str(exc.detail) or exc.__class__.__name__},
                )
            )
            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "failed",
                    "message": str(exc.detail) or exc.__class__.__name__,
                }
            )
            yield sse({"type": "error", "message": str(exc.detail) or exc.__class__.__name__})
            yield sse("[DONE]")
        except Exception as exc:
            log_audit_record(
                build_trace_record(
                    action="chat_request_failed",
                    incident_id=incident_id,
                    policy=policy,
                    request_id=request_id,
                    run_id=run_id,
                    subject=subject,
                    target={"error": str(exc) or exc.__class__.__name__},
                )
            )
            yield sse(
                {
                    "type": "run_status",
                    "runId": run_id,
                    "stage": "failed",
                    "message": str(exc) or exc.__class__.__name__,
                }
            )
            yield sse({"type": "error", "message": str(exc) or exc.__class__.__name__})
            yield sse("[DONE]")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
