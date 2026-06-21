from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

SENSITIVE_KEYS = {
    "access_token",
    "api_key",
    "authorization",
    "bearer",
    "client_secret",
    "clientsecret",
    "data",
    "id_token",
    "kubeconfig",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "token",
}
PRIVATE_KEY_BLOCK_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----.*?-----END [A-Z0-9 ]*PRIVATE KEY-----",
    re.DOTALL,
)
AUTHORIZATION_HEADER_RE = re.compile(
    r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9._~+/=-]+"
)
BEARER_TOKEN_RE = re.compile(r"(?i)\b(bearer)\s+[A-Za-z0-9._~+/=-]{16,}")
KEY_VALUE_SECRET_RE = re.compile(
    r"(?i)([\"']?(?:access[_-]?token|api[_-]?key|authorization|client[_-]?secret|id[_-]?token|password|private[_-]?key|refresh[_-]?token|secret|token)[\"']?\s*[:=]\s*[\"']?)([^\"'\s,;}]+)([\"']?)"
)
KUBECONFIG_TOKEN_RE = re.compile(r"(?im)^(\s*token:\s*)[A-Za-z0-9._~+/=-]+$")
DIRECT_MUTATION_RE = re.compile(
    r"(?i)(^|\b)(apply|cordon|delete|drain|evict|exec|patch|restart|rollback|rollout\s+(restart|undo)|scale|uncordon)\b"
)
KOREAN_MUTATION_RE = re.compile(
    r"(삭제|재시작|리스타트|롤백|스케일\s*(아웃|인)?|배포|패치|적용|변경|수정|중지|시작|격리|드레인|언코든|코든)"
)
KOREAN_DIRECT_RE = re.compile(r"(해줘|해주세요|수행|실행|적용해|변경해|삭제해|재시작해|늘려|줄여|처리해)")
KOREAN_ACTION_PROPOSAL_RE = re.compile(r"(계획|제안|승인\s*요청|승인\s*절차|초안|수립)")
KOREAN_EXPLICIT_MUTATION_EXECUTION_RE = re.compile(
    r"(재시작\s*(해|해주세요|시켜|시켜줘|수행|실행)|"
    r"삭제\s*(해|해주세요|수행|실행)|"
    r"스케일\s*(아웃|인)?\s*(해|해주세요|수행|실행|늘려|줄여)|"
    r"롤백\s*(해|해주세요|수행|실행)|"
    r"패치\s*(해|해주세요|수행|실행)|"
    r"적용\s*(해|해주세요|수행|실행)|"
    r"변경\s*(해|해주세요|수행|실행)|"
    r"드레인\s*(해|해주세요|수행|실행)|"
    r"코든\s*(해|해주세요|수행|실행)|"
    r"언코든\s*(해|해주세요|수행|실행))"
)
READ_ONLY_OPERATIONAL_ANALYSIS_RE = re.compile(
    r"(?i)(분석|확인|조회|알려|정리|상태|현황|이력|횟수|많은|높은|원인|왜|최근|"
    r"restart\s+(count|history|status|analysis|summary)|"
    r"(many|high|top)\s+restarts|status)"
)


def now_rfc3339() -> str:
    return datetime.now(UTC).isoformat()


def canonical_digest(value: Any) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def groups_digest(groups: list[Any] | None) -> str:
    safe_groups = sorted({str(group) for group in groups or []})
    return canonical_digest(safe_groups)


def redact_text(text: str) -> str:
    redacted = PRIVATE_KEY_BLOCK_RE.sub("[REDACTED_PRIVATE_KEY]", text)
    redacted = AUTHORIZATION_HEADER_RE.sub(r"\1[REDACTED]", redacted)
    redacted = BEARER_TOKEN_RE.sub(r"\1 [REDACTED]", redacted)
    redacted = KEY_VALUE_SECRET_RE.sub(r"\1[REDACTED]\3", redacted)
    redacted = KUBECONFIG_TOKEN_RE.sub(r"\1[REDACTED]", redacted)
    return redacted


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            normalized_key = key_text.lower().replace("-", "_")
            if normalized_key in SENSITIVE_KEYS or normalized_key.endswith("_token"):
                redacted[key_text] = "[REDACTED]"
            else:
                redacted[key_text] = redact_sensitive(item)
        return redacted

    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]

    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)

    return value


def safe_subject(user_info: Mapping[str, Any] | None) -> dict[str, Any]:
    if not user_info:
        return {
            "authenticatedByCluster": "unknown",
            "groupsDigest": groups_digest([]),
            "uid": "unknown",
            "username": "unknown",
        }

    groups = user_info.get("groups")
    return {
        "authenticatedByCluster": "api-server",
        "groupsDigest": groups_digest(groups if isinstance(groups, list) else []),
        "uid": str(user_info.get("uid") or "unknown"),
        "username": str(user_info.get("username") or "unknown"),
    }


def classify_request_policy(message: str) -> dict[str, Any]:
    normalized_message = message.strip()
    has_read_only_analysis_intent = bool(READ_ONLY_OPERATIONAL_ANALYSIS_RE.search(normalized_message))
    has_direct_english_mutation = bool(DIRECT_MUTATION_RE.search(normalized_message)) and not (
        has_read_only_analysis_intent and "restart" in normalized_message.lower()
    )
    has_korean_mutation = bool(KOREAN_MUTATION_RE.search(normalized_message))
    has_direct_korean_request = bool(KOREAN_DIRECT_RE.search(normalized_message))
    has_korean_action_proposal_intent = bool(KOREAN_ACTION_PROPOSAL_RE.search(normalized_message))
    has_explicit_korean_mutation_execution = bool(
        KOREAN_EXPLICIT_MUTATION_EXECUTION_RE.search(normalized_message)
    )
    looks_like_mutation_request = (
        has_direct_english_mutation
        or has_explicit_korean_mutation_execution
        or (has_korean_mutation and has_korean_action_proposal_intent)
        or (
            has_korean_mutation
            and has_direct_korean_request
            and not has_read_only_analysis_intent
        )
    )

    if looks_like_mutation_request:
        return {
            "schemaVersion": "v1",
            "phase": "phase0-1",
            "decision": "action_proposal_only",
            "identityMode": "user-token",
            "mutationAllowed": False,
            "risk": "approval_required",
            "reason": (
                "Phase 0-1 supports read-only evidence and action proposals only; "
                "mutation execution requires a later Approval API and Action Executor."
            ),
        }

    return {
        "schemaVersion": "v1",
        "phase": "phase0-1",
        "decision": "allow_read_only_evidence",
        "identityMode": "user-token",
        "mutationAllowed": False,
        "risk": "low",
        "reason": "Read-only evidence collection and OpenShift knowledge synthesis are allowed.",
    }


def build_gateway_guardrail(policy: Mapping[str, Any]) -> str:
    if policy.get("decision") == "action_proposal_only":
        return """
[Gateway Phase 0-1 Security Envelope]
- 사용자가 변경 실행 또는 재시작/삭제/스케일/패치 계열 요청을 했더라도 이 Gateway는 mutation을 실행하지 않습니다.
- 현재 허용 범위는 읽기 전용 증거 수집, 원인 분석, 영향도 설명, 승인 전 action proposal 작성입니다.
- 답변에서는 즉시 실행했다고 말하지 말고, 필요한 live evidence, 위험도, 사전조건, 승인 필요 여부, 안전한 확인 명령을 분리해 작성하세요.
- 사용자 토큰, Secret, kubeconfig, Authorization header, private key, raw credential은 출력하지 마세요.
"""

    return """
[Gateway Phase 0-1 Security Envelope]
- 현재 허용 범위는 읽기 전용 증거 수집과 OpenShift 지식/런북 설명입니다.
- live cluster state가 필요한 경우 UserToken 범위의 조회 도구 결과만 근거로 사용하세요.
- 사용자 토큰, Secret, kubeconfig, Authorization header, private key, raw credential은 출력하지 마세요.
- mutation은 승인 API와 Action Executor가 구현되기 전까지 실행할 수 없습니다.
"""


def build_trace_record(
    *,
    action: str,
    incident_id: str,
    policy: Mapping[str, Any],
    request_id: str,
    run_id: str,
    subject: Mapping[str, Any] | None,
    target: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "v1",
        "action": action,
        "auditId": f"audit-{hashlib.sha256(f'{request_id}:{action}'.encode()).hexdigest()[:16]}",
        "incidentId": incident_id,
        "policy": redact_sensitive(dict(policy)),
        "requestId": request_id,
        "runId": run_id,
        "subject": redact_sensitive(dict(subject or safe_subject(None))),
        "target": redact_sensitive(dict(target or {})),
        "timestamp": now_rfc3339(),
    }


def build_evidence_reference(
    *,
    event: Mapping[str, Any],
    incident_id: str,
    run_id: str,
    source_type: str = "ols-tool-result",
    subject: Mapping[str, Any] | None,
) -> dict[str, Any]:
    evidence_projection = {
        "detail": event.get("detail"),
        "name": event.get("name"),
        "status": event.get("status"),
        "summary": event.get("summary"),
        "type": event.get("type"),
    }
    digest = canonical_digest(redact_sensitive(evidence_projection))
    return {
        "schemaVersion": "v1",
        "accessScope": "user-token",
        "classification": "internal",
        "collectedAt": now_rfc3339(),
        "contentDigest": digest,
        "evidenceId": f"ev-{digest.removeprefix('sha256:')[:16]}",
        "freshnessTtl": "5m",
        "identityMode": "user-token",
        "incidentId": incident_id,
        "modelAccessAllowed": True,
        "originatingSubject": redact_sensitive(dict(subject or safe_subject(None))),
        "redactionProfile": "gateway-phase0-v1",
        "runId": run_id,
        "sourceType": source_type,
        "summary": event.get("summary") or event.get("name") or "tool result",
    }
