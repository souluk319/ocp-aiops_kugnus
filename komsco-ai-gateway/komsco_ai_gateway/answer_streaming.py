from __future__ import annotations

import json
import re
from collections.abc import AsyncIterator, Mapping
from typing import Any

from .security import redact_sensitive

TOOL_LINE_PREFIXES: tuple[tuple[str, str], ...] = (
    ("Tool call:", "tool_call"),
    ("Tool result:", "tool_result"),
)
MAX_TOOL_DETAIL_CHARS = 4000


def sse(data: Mapping[str, Any] | str) -> str:
    if isinstance(data, str):
        return f"data: {data}\n\n"

    return f"data: {json.dumps(redact_sensitive(data), ensure_ascii=False)}\n\n"


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
        annotations = alert.get("annotations") if isinstance(alert.get("annotations"), Mapping) else {}
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


def normalize_ols_event(event: dict[str, Any]) -> dict[str, Any]:
    event_type = event.get("event") or event.get("type")

    if event_type == "text":
        normalized = {
            "type": "text",
            "content": event.get("data") or event.get("content") or "",
        }
        for key in ("fallbackAnswer", "gatewayContextDigest", "source", "streamProbe"):
            if key in event:
                normalized[key] = event[key]
        return normalized

    if event_type == "end":
        return {"type": "end", "conversationId": event.get("conversation_id")}

    if event_type in {"tool_call", "tool_result"}:
        if event.get("detail") is not None and event.get("summary") is not None:
            return event

        return normalize_tool_event(event_type, event)

    return event
