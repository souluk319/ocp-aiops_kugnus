from collections.abc import Mapping
from typing import Any

from .cluster_anomaly_templates import DEFAULT_CLUSTER_SAFETY, ClusterSafety
from .cluster_metric_anomalies import alert_anomaly_findings, restart_metric_findings
from .cluster_platform_anomalies import (
    event_anomaly_findings,
    operator_anomaly_findings,
    version_anomaly_findings,
)
from .cluster_pod_anomalies import pod_anomaly_findings
from .security import now_rfc3339


def build_aiops_anomaly_summary(
    cluster_summary_payload: Mapping[str, Any],
    pods_payload: Mapping[str, Any] | None,
    events_payload: Mapping[str, Any] | None,
    alerts_probe: Mapping[str, Any] | None,
    restart_probe: Mapping[str, Any] | None,
    data_sources: list[Mapping[str, Any]],
    *,
    safety: ClusterSafety = DEFAULT_CLUSTER_SAFETY,
) -> dict[str, Any]:
    operator_findings = operator_anomaly_findings(cluster_summary_payload)
    pod_findings = pod_anomaly_findings(pods_payload)
    event_findings = event_anomaly_findings(events_payload)
    alert_findings, excluded_alerts = alert_anomaly_findings(alerts_probe)
    findings = (
        operator_findings
        + version_anomaly_findings(cluster_summary_payload)
        + pod_findings
        + event_findings
        + alert_findings
        + restart_metric_findings(restart_probe)
    )
    ordered = ordered_unique_findings(findings)
    danger = sum(1 for item in ordered if item.get("severity") == "위험")
    attention = sum(1 for item in ordered if item.get("severity") == "확인 필요")
    warning = sum(1 for item in ordered if item.get("severity") == "주의")
    unavailable_sources = [item for item in data_sources if item.get("status") != "available"]
    source_errors = [item for item in data_sources if item.get("status") == "error" and item.get("required")]
    status, label = anomaly_status_label(source_errors, danger, attention, warning, unavailable_sources)
    source_status_by_name = {str(item.get("name") or ""): str(item.get("status") or "") for item in data_sources}
    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsAnomalySummary",
        "metadata": {"generatedAt": now_rfc3339(), "name": "kugnus-anomaly-summary"},
        "spec": {
            "dataSources": list(data_sources),
            "excludedAlerts": excluded_alerts,
            "findings": ordered[:24],
            "normalSignals": normal_signals(
                source_status_by_name,
                operator_findings,
                pod_findings,
                event_findings,
            ),
            "status": status,
            "statusLabel": label,
            "safety": {
                "methodsUsed": ["GET"],
                "mode": "execute",
                "mutationsEnabled": safety.mutations_enabled,
                "unrestrictedCommandsEnabled": safety.unrestricted_commands_enabled,
            },
            "totals": {
                "attention": attention,
                "danger": danger,
                "total": len(ordered),
                "warning": warning,
            },
        },
    }


def ordered_unique_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: dict[str, dict[str, Any]] = {}
    for finding in findings:
        unique[str(finding.get("id"))] = finding
    return sorted(
        unique.values(),
        key=lambda item: (
            int(item.get("priority") or 999),
            str(item.get("source") or ""),
            str(item.get("namespace") or ""),
            str(item.get("title") or ""),
        ),
    )


def anomaly_status_label(
    source_errors: list[Mapping[str, Any]],
    danger: int,
    attention: int,
    warning: int,
    unavailable_sources: list[Mapping[str, Any]],
) -> tuple[str, str]:
    if source_errors:
        return "error", "필수 이상 징후 데이터 소스 확인 실패"
    if danger:
        return "risk", f"위험 이상 징후 {danger}건"
    if attention:
        return "attention", f"확인 필요 이상 징후 {attention}건"
    if warning:
        return "warning", f"주의 이상 징후 {warning}건"
    if unavailable_sources:
        return "unknown", "일부 이상 징후 데이터 소스 미확인"
    return "normal", "현재 수집 범위에서 주요 이상 징후 없음"


def normal_signals(
    source_status_by_name: Mapping[str, str],
    operator_findings: list[dict[str, Any]],
    pod_findings: list[dict[str, Any]],
    event_findings: list[dict[str, Any]],
) -> list[str]:
    signals = [
        "ClusterOperator issues 없음"
        if source_status_by_name.get("clusteroperators") == "available" and not operator_findings
        else "",
        "Pod 비정상 상태 없음"
        if source_status_by_name.get("pods") == "available" and not pod_findings
        else "",
        "Warning Event 없음"
        if source_status_by_name.get("events") == "available" and not event_findings
        else "",
    ]
    return [signal for signal in signals if signal]
