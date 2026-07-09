from collections.abc import Mapping
from typing import Any

from .cluster_anomaly_templates import anomaly_finding, anomaly_resource
from .cluster_common import metadata_name, metadata_namespace, resource_items


def event_anomaly_findings(events_payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for event in resource_items(events_payload):
        event_type = str(event.get("type") or "")
        if event_type != "Warning":
            continue
        namespace = metadata_namespace(event)
        reason = str(event.get("reason") or "Warning")
        message = str(event.get("message") or "")
        involved = event.get("involvedObject", {}) if isinstance(event.get("involvedObject"), Mapping) else {}
        resource = anomaly_resource(
            kind=str(involved.get("kind") or "Event"),
            namespace=str(involved.get("namespace") or namespace),
            name=str(involved.get("name") or metadata_name(event)),
        )
        priority = 12 if reason in {"FailedScheduling", "FailedMount", "FailedAttachVolume"} else 28
        findings.append(warning_event_finding(namespace, reason, message, resource, priority))
    return findings[:12]


def warning_event_finding(
    namespace: str,
    reason: str,
    message: str,
    resource: Mapping[str, Any],
    priority: int,
) -> dict[str, Any]:
    resource_namespace = str(resource.get("namespace") or namespace)
    return anomaly_finding(
        candidate_cause="Kubernetes Warning Event가 발생했습니다. 해당 리소스 describe와 같은 namespace의 후속 이벤트 확인이 필요합니다.",
        evidence=f"event.reason={reason}, message={message[:220]}",
        finding_type="warning_event",
        namespace=resource_namespace,
        next_check=f"oc describe {resource.get('kind')} {resource.get('name')} -n {resource_namespace}",
        priority=priority,
        reason=reason,
        resource=resource,
        severity="확인 필요" if priority <= 20 else "주의",
        source="events",
        title=f"Warning Event: {reason}",
    )


def operator_anomaly_findings(cluster_summary_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    operators = cluster_summary_payload.get("operators", {})
    operators = operators if isinstance(operators, Mapping) else {}
    issues = operators.get("issues") if isinstance(operators.get("issues"), list) else []
    findings: list[dict[str, Any]] = []
    for issue in issues:
        if isinstance(issue, Mapping):
            findings.append(operator_condition_finding(issue))
    return findings


def operator_condition_finding(issue: Mapping[str, Any]) -> dict[str, Any]:
    name = str(issue.get("name") or "unknown-operator")
    unavailable = not bool(issue.get("available"))
    degraded = bool(issue.get("degraded"))
    progressing = bool(issue.get("progressing"))
    upgradeable = str(issue.get("upgradeable") or "")
    reason = str(issue.get("reason") or "")
    message = str(issue.get("message") or "")
    if unavailable:
        priority = 3
    elif degraded:
        priority = 6
    else:
        priority = 22
    if upgradeable == "False":
        priority = min(priority, 14)
    return anomaly_finding(
        candidate_cause="ClusterOperator condition이 정상 조건을 벗어났습니다. reason/message를 기준으로 관련 operand와 namespace를 확인해야 합니다.",
        evidence=(
            f"available={issue.get('available')}, degraded={degraded}, progressing={progressing}, "
            f"upgradeable={upgradeable or '-'}, reason={reason}, message={message[:180]}"
        ),
        finding_type="clusteroperator_condition",
        next_check=f"oc get clusteroperator {name} -o yaml",
        priority=priority,
        reason=reason or "ClusterOperatorCondition",
        resource=anomaly_resource(kind="ClusterOperator", name=name),
        severity="위험" if unavailable or degraded else "확인 필요",
        source="clusteroperators",
        title=f"ClusterOperator 확인 필요: {name}",
    )


def version_anomaly_findings(cluster_summary_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    version = cluster_summary_payload.get("version", {})
    version = version if isinstance(version, Mapping) else {}
    if version.get("upgradeable") is not False:
        return []
    return [upgrade_blocked_finding(version)]


def upgrade_blocked_finding(version: Mapping[str, Any]) -> dict[str, Any]:
    return anomaly_finding(
        candidate_cause="ClusterVersion Upgradeable=False 상태입니다. 업그레이드 전 차단 조건을 해소해야 합니다.",
        evidence=(
            f"version={version.get('version')}, channel={version.get('channel')}, "
            f"reason={version.get('upgradeableReason')}, "
            f"message={str(version.get('upgradeableMessage') or '')[:220]}"
        ),
        finding_type="upgrade_blocked",
        next_check="oc get clusterversion version -o yaml",
        priority=20,
        reason=str(version.get("upgradeableReason") or "UpgradeableFalse"),
        resource=anomaly_resource(kind="ClusterVersion", name="version"),
        severity="확인 필요",
        source="clusterversion",
        title="Cluster upgrade blocked",
    )
