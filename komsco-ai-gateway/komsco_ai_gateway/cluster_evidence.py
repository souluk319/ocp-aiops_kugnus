import json
from collections.abc import Mapping
from typing import Any

from .cluster_common import resource_items
from .cluster_nodes import node_metric_map, summarize_node
from .security import redact_sensitive


def safe_error_text(value: Any, *, limit: int = 500) -> str:
    redacted = redact_sensitive(value)
    if isinstance(redacted, str):
        text = redacted
    else:
        text = json.dumps(redacted, ensure_ascii=False, sort_keys=True)
    text = text.replace("\x00", "").strip()
    if len(text) > limit:
        return f"{text[:limit]}..."
    return text


def markdown_table_cell(value: Any, *, max_length: int = 180) -> str:
    text = str(redact_sensitive(value)).replace("\n", " ").replace("\r", " ").strip()
    text = text.replace("|", "\\|")
    if not text:
        return "-"
    if len(text) > max_length:
        return f"{text[: max_length - 1]}..."
    return text


def prometheus_vector_results(probe: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if not isinstance(probe, Mapping):
        return []
    result = probe.get("result")
    if not isinstance(result, list):
        return []
    return [item for item in result if isinstance(item, Mapping)]


def _prometheus_probe_reason(probe: Mapping[str, Any] | None) -> str:
    if not isinstance(probe, Mapping):
        return "probe payload was empty or invalid"
    return safe_error_text(probe.get("reason") or probe.get("error") or "", limit=240)


def rca_probe_event_status(probe: Mapping[str, Any] | None) -> str:
    status = str((probe or {}).get("status") or "unavailable").lower()
    if status == "available":
        return "success"
    if status == "partial":
        return "partial"
    if status == "error":
        return "error"
    return "skipped"


def build_node_status_rca_evidence(
    nodes_payload: Mapping[str, Any] | None,
    node_metrics_payload: Mapping[str, Any] | None,
    *,
    metrics_status: Mapping[str, Any] | None = None,
) -> str:
    node_items = resource_items(nodes_payload)
    if not node_items:
        return "Node status evidence unavailable: Kubernetes API `/api/v1/nodes` returned no node items."

    metrics_by_name = node_metric_map(node_metrics_payload)
    rows = []
    for node in node_items:
        metadata = node.get("metadata", {}) if isinstance(node.get("metadata"), Mapping) else {}
        summary = summarize_node(node, metrics_by_name.get(str(metadata.get("name"))))
        pressure_labels = [
            label
            for label, active in summary.get("pressures", {}).items()
            if active
        ]
        rows.append(
            {
                "cpu": summary.get("usage", {}).get("cpu") or "-",
                "memory": summary.get("usage", {}).get("memory") or "-",
                "name": summary.get("name") or "unknown-node",
                "pressures": ", ".join(pressure_labels) if pressure_labels else "-",
                "ready": "Ready" if summary.get("ready") else "NotReady",
                "roles": ",".join(summary.get("roles") or ["worker"]),
            }
        )

    ready_count = len([row for row in rows if row["ready"] == "Ready"])
    pressure_count = len([row for row in rows if row["pressures"] != "-"])
    metrics_state = str((metrics_status or {}).get("status") or "")
    metrics_reason = safe_error_text((metrics_status or {}).get("reason") or "", limit=240)
    lines = [
        "Gateway-collected Node status evidence from Kubernetes API `/api/v1/nodes` and metrics.k8s.io.",
        "EvidenceType: node",
        (
            f"Summary: total={len(rows)}, ready={ready_count}, "
            f"notReady={len(rows) - ready_count}, pressureNodes={pressure_count}, "
            f"metricsAvailable={bool(metrics_by_name)}"
        ),
    ]
    if metrics_state and metrics_state != "available":
        lines.append(
            f"Node metrics are partial/unavailable: status=`{metrics_state}`, reason={metrics_reason or '-'}"
        )
    lines.extend(
        [
            "",
            "| Node | Roles | Ready | Pressures | CPU | Memory |",
            "| :--- | :--- | :---: | :--- | :--- | :--- |",
        ]
    )
    for row in rows[:20]:
        lines.append(
            "| `{name}` | {roles} | {ready} | {pressures} | {cpu} | {memory} |".format(
                **{
                    key: markdown_table_cell(value)
                    for key, value in row.items()
                }
            )
        )
    if len(rows) > 20:
        lines.append("| ... | ... | ... | ... | ... | ... |")
        lines.append(f"Rows capped at 20 of {len(rows)} nodes for RCA prompt compactness.")
    return "\n".join(lines)


def build_active_alerts_rca_evidence(alerts_probe: Mapping[str, Any] | None) -> str:
    status = str((alerts_probe or {}).get("status") or "unavailable").lower()
    if status not in {"available", "partial"}:
        return (
            "Active alert evidence unavailable: "
            f"status={status}, reason={_prometheus_probe_reason(alerts_probe) or '-'}"
        )

    results = prometheus_vector_results(alerts_probe)
    active_rows: list[dict[str, str]] = []
    excluded_watchdog = 0
    for item in results:
        metric = item.get("metric", {}) if isinstance(item.get("metric"), Mapping) else {}
        alertname = str(metric.get("alertname") or "unknown-alert")
        if alertname == "Watchdog":
            excluded_watchdog += 1
            continue
        active_rows.append(
            {
                "alert": alertname,
                "severity": str(metric.get("severity") or metric.get("alert_severity") or "-"),
                "namespace": str(metric.get("namespace") or "-"),
                "pod": str(metric.get("pod") or metric.get("pod_name") or "-"),
                "instance": str(metric.get("instance") or "-"),
            }
        )

    reason = _prometheus_probe_reason(alerts_probe)
    lines = [
        'Gateway-collected Active alert evidence from Thanos query `ALERTS{alertstate="firing"}`.',
        "EvidenceType: alert",
        (
            f"Query status: `{status}`. resultCount={alerts_probe.get('resultCount', len(results))}, "
            f"nonWatchdogActiveAlerts={len(active_rows)}, excludedWatchdog={excluded_watchdog}"
        ),
    ]
    if status == "partial" or reason:
        lines.append(f"Probe note: {reason or 'partial vector result'}")
    lines.extend(
        [
            "",
            "| Alert | Severity | Namespace | Pod | Instance |",
            "| :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    if active_rows:
        for row in active_rows[:20]:
            lines.append(
                "| `{alert}` | {severity} | {namespace} | {pod} | {instance} |".format(
                    **{key: markdown_table_cell(value) for key, value in row.items()}
                )
            )
    else:
        lines.append("| - | - | - | - | 관련 active alert 없음. Watchdog은 pipeline health alert로 제외. |")
    if len(active_rows) > 20:
        lines.append(f"Rows capped at 20 of {len(active_rows)} non-Watchdog active alerts.")
    return "\n".join(lines)


def build_restart_metric_rca_evidence(restart_probe: Mapping[str, Any] | None) -> str:
    status = str((restart_probe or {}).get("status") or "unavailable").lower()
    query = "increase(kube_pod_container_status_restarts_total[1h]) > 0"
    if status not in {"available", "partial"}:
        return (
            "Metric RCA evidence unavailable: "
            f"status={status}, query=`{query}`, reason={_prometheus_probe_reason(restart_probe) or '-'}"
        )

    results = prometheus_vector_results(restart_probe)
    rows = []
    for item in results:
        metric = item.get("metric", {}) if isinstance(item.get("metric"), Mapping) else {}
        value = item.get("value")
        restart_delta = "-"
        if isinstance(value, list) and len(value) >= 2:
            restart_delta = str(value[1])
        rows.append(
            {
                "container": str(metric.get("container") or "-"),
                "namespace": str(metric.get("namespace") or "-"),
                "pod": str(metric.get("pod") or "-"),
                "restartDelta": restart_delta,
            }
        )

    reason = _prometheus_probe_reason(restart_probe)
    lines = [
        f"Gateway-collected Metric RCA evidence from Thanos query `{query}`.",
        "EvidenceType: metric",
        f"Query status: `{status}`. resultCount={restart_probe.get('resultCount', len(results))}, window=1h",
    ]
    if status == "partial" or reason:
        lines.append(f"Probe note: {reason or 'partial vector result'}")
    lines.extend(
        [
            "",
            "| Namespace | Pod | Container | Restart increase 1h |",
            "| :--- | :--- | :--- | ---: |",
        ]
    )
    if rows:
        for row in rows[:20]:
            lines.append(
                "| {namespace} | `{pod}` | `{container}` | {restartDelta} |".format(
                    **{key: markdown_table_cell(value) for key, value in row.items()}
                )
            )
    else:
        lines.append("| - | - | - | 0 |")
    if len(rows) > 20:
        lines.append(f"Rows capped at 20 of {len(rows)} restart metric series.")
    return "\n".join(lines)
