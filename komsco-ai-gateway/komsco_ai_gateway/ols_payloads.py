from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .security import canonical_digest, now_rfc3339, redact_sensitive


class ImageAttachmentPayload(Protocol):
    name: str
    mimeType: str
    size: int
    data: str


@dataclass(frozen=True, slots=True)
class OlsGatewayContextInput:
    tool_plan: Mapping[str, Any]
    rca_context: Mapping[str, Any]
    safety_contract: Mapping[str, Any]
    policy: Mapping[str, Any]
    gateway_evidence: str | None = None


@dataclass(frozen=True, slots=True)
class OlsPayloadInput:
    query: str
    conversation_id: str | None
    attachments: list[ImageAttachmentPayload]
    forward_image_attachments: bool = True
    forward_conversation_id: bool = False
    gateway_context: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OlsContextHandoffInput:
    gateway_context: Mapping[str, Any] | None = None
    gateway_evidence: str | None = None
    max_chars: int = 0
    max_lines: int = 0


def format_bytes(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"

    return f"{size / (1024 * 1024):.1f} MB"


def build_attachment_context(
    attachments: list[ImageAttachmentPayload],
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
            "답변에는 첨부 파일 메타데이터, 사용자 설명, 도구 조회 결과만 기준으로 사용하세요."
        )

    lines.append("첨부 파일 메타데이터:")

    for index, attachment in enumerate(attachments, start=1):
        lines.append(
            f"{index}. {attachment.name} ({attachment.mimeType}, {format_bytes(attachment.size)})"
        )

    return "\n".join(lines)


def build_ols_attachments(attachments: list[ImageAttachmentPayload]) -> list[dict[str, str]]:
    return [
        {
            "attachment_type": "image",
            "content_type": attachment.mimeType,
            "content": attachment.data,
        }
        for attachment in attachments
    ]


def build_ols_gateway_context(context_input: OlsGatewayContextInput) -> dict[str, Any]:
    tool_plan = context_input.tool_plan
    rca_context = context_input.rca_context
    safety_contract = context_input.safety_contract
    policy = context_input.policy
    gateway_evidence = context_input.gateway_evidence
    rca_evidence = rca_context.get("evidence", {}) if isinstance(rca_context.get("evidence"), Mapping) else {}
    missing_evidence = rca_evidence.get("missing", []) if isinstance(rca_evidence, Mapping) else []
    context = {
        "apiVersion": "aiops.komsco/v1alpha1",
        "kind": "GatewayContext",
        "metadata": {
            "generatedAt": now_rfc3339(),
            "source": "komsco-ai-gateway",
            "version": "0.1.3",
            "rcaContextDigest": rca_context.get("metadata", {}).get("digest")
            if isinstance(rca_context.get("metadata"), Mapping)
            else "",
        },
        "toolPlan": redact_sensitive(dict(tool_plan)),
        "evidenceSummary": redact_sensitive(rca_evidence.get("summary", {}) if isinstance(rca_evidence, Mapping) else {}),
        "missingEvidence": redact_sensitive(missing_evidence if isinstance(missing_evidence, list) else []),
        "rcaContext": redact_sensitive(dict(rca_context)),
        "safetyContract": redact_sensitive(dict(safety_contract)),
        "policy": redact_sensitive(dict(policy)),
        "gatewayEvidenceDigest": canonical_digest(redact_sensitive(gateway_evidence or "")) if gateway_evidence else "",
    }
    context["metadata"]["digest"] = canonical_digest(redact_sensitive(context))
    return context


def build_ols_payload(payload_input: OlsPayloadInput) -> dict[str, Any]:
    payload: dict[str, Any] = {"query": payload_input.query}
    if payload_input.forward_conversation_id and payload_input.conversation_id:
        payload["conversation_id"] = payload_input.conversation_id

    # OLS 1.1.x rejects unknown request-body fields with 422 extra_forbidden.
    # Keep gateway_context in local Gateway status/events and put the evidence
    # handoff inside query text instead of adding a non-OLS field.
    _ = payload_input.gateway_context

    ols_attachments = (
        build_ols_attachments(payload_input.attachments)
        if payload_input.forward_image_attachments
        else []
    )
    if ols_attachments:
        payload["attachments"] = ols_attachments

    return payload


def build_ols_context_handoff(handoff_input: OlsContextHandoffInput) -> str:
    if handoff_input.max_chars <= 0:
        return ""

    lines: list[str] = []
    gateway_context = handoff_input.gateway_context
    gateway_evidence = handoff_input.gateway_evidence
    if isinstance(gateway_context, Mapping):
        tool_plan = gateway_context.get("toolPlan")
        rca_context = gateway_context.get("rcaContext")
        if isinstance(tool_plan, Mapping):
            task_type = str(tool_plan.get("task_type") or "generic_openshift_question")
            policy = tool_plan.get("execution_policy")
            execution_mode = (
                str(policy.get("mode"))
                if isinstance(policy, Mapping) and policy.get("mode")
                else "evidence_check"
            )
            lines.append(f"- Tool plan: {task_type}; execution policy: {execution_mode}")

        if isinstance(rca_context, Mapping):
            evidence = rca_context.get("evidence")
            if isinstance(evidence, Mapping):
                summary = evidence.get("summary")
                if isinstance(summary, Mapping):
                    lines.append(
                        "- Evidence refs: "
                        f"collected={summary.get('collectedCount', 0)}, "
                        f"partial={summary.get('partialCount', 0)}, "
                        f"failed={summary.get('failedCount', 0)}, "
                        f"missing={summary.get('missingCount', 0)}"
                    )
                missing = evidence.get("missing")
                if isinstance(missing, list) and missing:
                    missing_types = [
                        str(item.get("type") or "unknown")
                        for item in missing
                        if isinstance(item, Mapping)
                    ]
                    if missing_types:
                        lines.append(f"- Missing evidence types: {', '.join(missing_types[:6])}")

    if gateway_evidence:
        lines.append("- Verified facts collected before final answer:")
        for raw_line in str(redact_sensitive(gateway_evidence)).splitlines():
            line = " ".join(raw_line.strip().split())
            if not line:
                continue
            if not line.startswith(("-", "*")):
                line = f"- {line}"
            lines.append(line)
            if len(lines) >= handoff_input.max_lines:
                break

    handoff = "\n".join(lines).strip()
    if len(handoff) > handoff_input.max_chars:
        handoff = (
            handoff[:handoff_input.max_chars].rstrip()
            + "\n- ... truncated; full RCA context is available in the local event stream."
        )
    return handoff
