from collections.abc import Mapping
from typing import Any

from .cluster_anomaly_templates import anomaly_finding, anomaly_resource
from .cluster_evidence import prometheus_vector_results


def alert_anomaly_findings(alerts_probe: Mapping[str, Any] | None) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    findings: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for item in prometheus_vector_results(alerts_probe):
        metric = item.get("metric", {}) if isinstance(item.get("metric"), Mapping) else {}
        alertname = str(metric.get("alertname") or "unknown-alert")
        if alertname == "Watchdog":
            excluded.append({"alertname": alertname, "reason": "Watchdog is an always-firing pipeline health alert."})
            continue
        findings.append(active_alert_finding(metric, alertname))
    return findings, excluded


def active_alert_finding(metric: Mapping[str, Any], alertname: str) -> dict[str, Any]:
    severity_label = str(metric.get("severity") or metric.get("alert_severity") or "").lower()
    namespace = str(metric.get("namespace") or "")
    pod_name = str(metric.get("pod") or metric.get("pod_name") or "")
    severity = alert_severity_label(severity_label)
    if severity == "위험":
        priority = 4
    elif severity == "확인 필요":
        priority = 13
    else:
        priority = 32
    return anomaly_finding(
        candidate_cause="Alert labels/annotations 기준의 활성 경고입니다. 관련 리소스 상세 조회로 원인을 확정해야 합니다.",
        evidence=(
            f"alertname={alertname}, severity={severity_label or '-'}, "
            f"namespace={namespace or '-'}, pod={pod_name or '-'}"
        ),
        finding_type="active_alert",
        namespace=namespace,
        next_check=alert_next_check(namespace, pod_name),
        priority=priority,
        reason=alertname,
        resource=anomaly_resource(
            kind="Alert",
            namespace=namespace,
            name=alertname if not pod_name else pod_name,
        ),
        severity=severity,
        source="alerts",
        title=f"Active alert: {alertname}",
    )


def alert_severity_label(severity_label: str) -> str:
    if severity_label in {"critical", "error"}:
        return "위험"
    if severity_label in {"warning", "warn"}:
        return "확인 필요"
    return "주의"


def alert_next_check(namespace: str, pod_name: str) -> str:
    if pod_name and namespace:
        return f"oc describe pod {pod_name} -n {namespace}"
    return "Alert labels에서 namespace/pod/resource를 확인한 뒤 관련 리소스를 describe"


def restart_metric_findings(restart_probe: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for item in prometheus_vector_results(restart_probe):
        restart_delta = restart_delta_value(item.get("value"))
        if restart_delta <= 0:
            continue
        metric = item.get("metric", {}) if isinstance(item.get("metric"), Mapping) else {}
        findings.append(restart_metric_finding(metric, restart_delta))
    return findings


def restart_delta_value(value: Any) -> float:
    if not isinstance(value, list) or len(value) < 2:
        return 0.0
    try:
        return float(value[1])
    except (TypeError, ValueError):
        return 0.0


def restart_metric_finding(metric: Mapping[str, Any], restart_delta: float) -> dict[str, Any]:
    namespace = str(metric.get("namespace") or "")
    pod_name = str(metric.get("pod") or "")
    container = str(metric.get("container") or "")
    return anomaly_finding(
        candidate_cause="최근 1시간 restart 증가가 관측되었습니다. 현재 CrashLoop인지 복구된 이력인지는 Pod 상태와 lastState로 확정해야 합니다.",
        evidence=(
            f"increase(kube_pod_container_status_restarts_total[1h])={restart_delta:g}, "
            f"container={container or '-'}"
        ),
        finding_type="pod_restart_spike",
        namespace=namespace,
        next_check=f"oc get pod {pod_name} -n {namespace} -o jsonpath='{{.status.containerStatuses}}'",
        priority=10,
        reason="RestartIncrease1h",
        resource=anomaly_resource(kind="Pod", namespace=namespace, name=pod_name or "unknown-pod"),
        severity="확인 필요",
        source="metrics",
        title=f"Recent restart increase: {namespace}/{pod_name or 'unknown-pod'}",
    )
