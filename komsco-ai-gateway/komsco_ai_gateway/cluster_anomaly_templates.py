import hashlib
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .security import now_rfc3339
from .settings import parse_bool


@dataclass(frozen=True, slots=True)
class ClusterSafety:
    mutations_enabled: bool
    unrestricted_commands_enabled: bool


DEFAULT_CLUSTER_SAFETY = ClusterSafety(
    mutations_enabled=parse_bool(os.getenv("KOMSCO_AI_ENABLE_MUTATIONS"), default=True),
    unrestricted_commands_enabled=parse_bool(
        os.getenv("KOMSCO_AI_UNRESTRICTED_COMMANDS_ENABLED"),
        default=False,
    ),
)


def anomaly_resource(*, kind: str, name: str, namespace: str = "") -> dict[str, str]:
    resource = {"kind": kind, "name": name}
    if namespace:
        resource["namespace"] = namespace
    return resource


def anomaly_finding(
    *,
    candidate_cause: str,
    evidence: str,
    finding_type: str,
    priority: int,
    resource: Mapping[str, Any],
    severity: str,
    source: str,
    title: str,
    next_check: str = "",
    namespace: str = "",
    reason: str = "",
) -> dict[str, Any]:
    identity = json.dumps(
        {
            "namespace": namespace or resource.get("namespace"),
            "priority": priority,
            "resource": dict(resource),
            "source": source,
            "title": title,
            "type": finding_type,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    finding = {
        "candidateCause": candidate_cause,
        "category": finding_type.split("_", 1)[0],
        "evidence": evidence,
        "id": hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
        "impact": finding_impact(severity),
        "lastObservedAt": now_rfc3339(),
        "message": evidence,
        "priority": priority,
        "resource": dict(resource),
        "severity": severity,
        "source": source,
        "statusLabel": severity,
        "status": severity_status(severity),
        "title": title,
        "type": finding_type,
    }
    if namespace or resource.get("namespace"):
        finding["namespace"] = namespace or str(resource.get("namespace") or "")
    if next_check:
        finding["nextCheck"] = next_check
    if reason:
        finding["reason"] = reason
    return finding


def finding_impact(severity: str) -> str:
    if severity == "위험":
        return "서비스 영향 또는 운영 안정성 저하 가능성이 높습니다."
    if severity == "확인 필요":
        return "운영자가 원인 확인과 후속 관찰을 해야 합니다."
    return "즉시 장애로 단정하지 않고 추세를 확인해야 합니다."


def severity_status(severity: str) -> str:
    severity_rank = {"위험": "danger", "확인 필요": "attention", "주의": "warning"}
    return severity_rank.get(severity, "info")
