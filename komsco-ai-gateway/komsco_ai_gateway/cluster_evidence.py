import json
from collections.abc import Mapping
from datetime import UTC, datetime
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


def _pod_display_state(pod: Mapping[str, Any]) -> str:
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


def json_list_summary(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return "-"
    return json.dumps(redact_sensitive(value), ensure_ascii=False)


def pod_label_summary(pod: Mapping[str, Any]) -> str:
    metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
    labels = metadata.get("labels")
    if not isinstance(labels, Mapping) or not labels:
        return "-"

    priority_keys = [
        "app",
        "app.kubernetes.io/name",
        "app.kubernetes.io/component",
        "aiops.komsco/scenario",
        "aiops.komsco/scenario-type",
        "pod-template-hash",
    ]
    ordered_keys = [key for key in priority_keys if key in labels]
    ordered_keys.extend(sorted(str(key) for key in labels if str(key) not in ordered_keys))
    parts = [f"{key}={labels.get(key)}" for key in ordered_keys[:8]]
    if len(labels) > len(parts):
        parts.append(f"+{len(labels) - len(parts)} more")
    return ", ".join(parts)


def container_spec_index(pod: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    spec = pod.get("spec", {}) if isinstance(pod.get("spec"), Mapping) else {}
    containers = spec.get("containers")
    if not isinstance(containers, list):
        return {}

    indexed: dict[str, Mapping[str, Any]] = {}
    for container in containers:
        if not isinstance(container, Mapping):
            continue
        name = str(container.get("name") or "")
        if name:
            indexed[name] = container
    return indexed


def replicaset_owner_index(replicasets_payload: Mapping[str, Any] | None) -> dict[tuple[str, str], str]:
    if not replicasets_payload:
        return {}
    items = replicasets_payload.get("items")
    if not isinstance(items, list):
        return {}

    indexed: dict[tuple[str, str], str] = {}
    for replicaset in items:
        if not isinstance(replicaset, Mapping):
            continue
        metadata = replicaset.get("metadata", {}) if isinstance(replicaset.get("metadata"), Mapping) else {}
        namespace = str(metadata.get("namespace") or "")
        name = str(metadata.get("name") or "")
        owner = pod_owner_summary(replicaset)
        if namespace and name and owner != "-":
            indexed[(namespace, name)] = owner
    return indexed


def pod_owner_chain_summary(
    pod: Mapping[str, Any],
    replicaset_owners: Mapping[tuple[str, str], str],
) -> str:
    metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
    namespace = str(metadata.get("namespace") or "")
    owner = pod_owner_summary(pod)
    if owner == "-" or not owner.startswith("ReplicaSet/"):
        return owner

    replicaset_name = owner.split("/", 1)[1]
    parent_owner = replicaset_owners.get((namespace, replicaset_name))
    if not parent_owner:
        return owner
    return f"{owner} -> {parent_owner}"


def _parse_rfc3339(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def build_pod_status_evidence(
    pods_payload: Mapping[str, Any],
    replicasets_payload: Mapping[str, Any] | None = None,
    *,
    include_pod_list: bool = False,
    list_namespace: str = "",
) -> str:
    items = pods_payload.get("items")
    if not isinstance(items, list):
        return "Pod status evidence unavailable: API response did not include an items list."

    replicaset_owners = replicaset_owner_index(replicasets_payload)
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
        pod_state = _pod_display_state(pod)
        owner = pod_owner_summary(pod)
        owner_chain = pod_owner_chain_summary(pod, replicaset_owners)
        label_summary = pod_label_summary(pod)
        specs_by_name = container_spec_index(pod)
        statuses = status.get("containerStatuses", [])
        regular_statuses = statuses if isinstance(statuses, list) else []
        expected_ready = f"{len(regular_statuses)}/{len(regular_statuses)}"
        is_unhealthy = phase not in {"Running", "Succeeded"} or ready != expected_ready

        for container in regular_statuses:
            if not isinstance(container, Mapping):
                continue

            last_state, last_finished_at = last_termination_summary(container)
            container_name = str(container.get("name") or "unknown")
            container_spec = specs_by_name.get(container_name, {})
            row = {
                "namespace": namespace,
                "pod": pod_name,
                "container": container_name,
                "phase": pod_state,
                "podStartTime": pod_start_time,
                "ready": ready,
                "state": state_summary(container),
                "restartCount": int(container.get("restartCount") or 0),
                "lastState": last_state,
                "lastFinishedAt": last_finished_at or "-",
                "lastFinishedSort": _parse_rfc3339(last_finished_at)
                or datetime.min.replace(tzinfo=UTC),
                "owner": owner,
                "ownerChain": owner_chain,
                "image": markdown_table_cell(container_spec.get("image") or "-"),
                "command": markdown_table_cell(json_list_summary(container_spec.get("command"))),
                "args": markdown_table_cell(json_list_summary(container_spec.get("args"))),
                "labels": markdown_table_cell(label_summary),
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
    list_rows = sorted(
        [
            row
            for row in rows
            if not list_namespace or str(row.get("namespace") or "") == list_namespace
        ],
        key=lambda item: (str(item["namespace"]), str(item["pod"]), str(item["container"])),
    )

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

    if include_pod_list:
        shown_list_rows = list_rows[:200]
        namespace_label = list_namespace or "all-accessible-namespaces"
        lines.extend(
            [
                "",
                "Current Pod list evidence:",
                f"Namespace filter: `{namespace_label}`",
                f"Rows shown: {len(shown_list_rows)} / {len(list_rows)}",
                "| Namespace | Pod | Container | Current State | Pod Start | Ready | Restarts | Last State/Exit | Owner |",
                "| :--- | :--- | :--- | :--- | :--- | :---: | ---: | :--- | :--- |",
            ]
        )
        if shown_list_rows:
            for row in shown_list_rows:
                lines.append(
                    "| {namespace} | `{pod}` | `{container}` | {phase} / {state} | {podStartTime} | {ready} | {restartCount} | {lastState} | {owner} |".format(
                        **row
                    )
                )
        else:
            lines.append("| - | - | - | 조회된 Pod 없음 | - | - | 0 | - | - |")

    lines.extend(
        [
            "",
            "Spec evidence for currently non-healthy or waiting containers:",
            "Use command/args/image/labels below as concrete evidence for root-cause and remediation planning; do not replace these values with generic guesses.",
            "| Namespace | Pod | Container | Image | Command | Args | Pod Labels | Owner Chain |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ]
    )
    if top_unhealthy_rows:
        for row in top_unhealthy_rows:
            lines.append(
                "| {namespace} | `{pod}` | `{container}` | {image} | {command} | {args} | {labels} | {ownerChain} |".format(
                    **row
                )
            )
    else:
        lines.append("| - | - | - | - | - | - | - | - |")

    return "\n".join(lines)


def build_deployment_rollout_evidence(
    deployments_payload: Mapping[str, Any] | None,
    replicasets_payload: Mapping[str, Any] | None,
    pods_payload: Mapping[str, Any],
) -> str:
    deployments = deployments_payload.get("items") if isinstance(deployments_payload, Mapping) else None
    if not isinstance(deployments, list):
        return "Deployment rollout evidence unavailable: deployments API response did not include an items list."

    replicasets = replicasets_payload.get("items") if isinstance(replicasets_payload, Mapping) else []
    pods = pods_payload.get("items") if isinstance(pods_payload.get("items"), list) else []
    rs_by_deployment_uid: dict[str, list[Mapping[str, Any]]] = {}
    if isinstance(replicasets, list):
        for replicaset in replicasets:
            if not isinstance(replicaset, Mapping):
                continue
            for owner in replicaset.get("metadata", {}).get("ownerReferences", []) or []:
                if isinstance(owner, Mapping) and owner.get("kind") == "Deployment":
                    rs_by_deployment_uid.setdefault(str(owner.get("uid") or ""), []).append(replicaset)

    pod_rows_by_selector: dict[tuple[str, str], list[str]] = {}
    if isinstance(pods, list):
        for pod in pods:
            if not isinstance(pod, Mapping):
                continue
            metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
            labels = metadata.get("labels") if isinstance(metadata.get("labels"), Mapping) else {}
            namespace = str(metadata.get("namespace") or "")
            app = str(labels.get("app") or "")
            if not namespace or not app:
                continue
            hash_value = str(labels.get("pod-template-hash") or "-")
            name = str(metadata.get("name") or "unknown")
            start_time = str(pod.get("status", {}).get("startTime") or "-")
            pod_rows_by_selector.setdefault((namespace, app), []).append(f"{name} hash={hash_value} start={start_time}")

    rows: list[dict[str, Any]] = []
    for deployment in deployments:
        if not isinstance(deployment, Mapping):
            continue
        metadata = deployment.get("metadata", {}) if isinstance(deployment.get("metadata"), Mapping) else {}
        spec = deployment.get("spec", {}) if isinstance(deployment.get("spec"), Mapping) else {}
        status = deployment.get("status", {}) if isinstance(deployment.get("status"), Mapping) else {}
        namespace = str(metadata.get("namespace") or "unknown")
        name = str(metadata.get("name") or "unknown")
        annotations = metadata.get("annotations") if isinstance(metadata.get("annotations"), Mapping) else {}
        template_metadata = (
            spec.get("template", {}).get("metadata", {})
            if isinstance(spec.get("template"), Mapping)
            else {}
        )
        template_annotations = (
            template_metadata.get("annotations")
            if isinstance(template_metadata.get("annotations"), Mapping)
            else {}
        )
        labels = template_metadata.get("labels") if isinstance(template_metadata.get("labels"), Mapping) else {}
        app_label = str(labels.get("app") or "")
        deployment_uid = str(metadata.get("uid") or "")
        owned_rs = sorted(
            rs_by_deployment_uid.get(deployment_uid, []),
            key=lambda item: str(item.get("metadata", {}).get("creationTimestamp") or ""),
        )
        rs_summary = []
        for replicaset in owned_rs[-4:]:
            rs_meta = replicaset.get("metadata", {}) if isinstance(replicaset.get("metadata"), Mapping) else {}
            rs_status = replicaset.get("status", {}) if isinstance(replicaset.get("status"), Mapping) else {}
            rs_spec = replicaset.get("spec", {}) if isinstance(replicaset.get("spec"), Mapping) else {}
            rs_annotations = rs_meta.get("annotations") if isinstance(rs_meta.get("annotations"), Mapping) else {}
            rs_summary.append(
                "{name}(rev={rev},desired={desired},ready={ready})".format(
                    name=str(rs_meta.get("name") or "unknown"),
                    rev=str(rs_annotations.get("deployment.kubernetes.io/revision") or "-"),
                    desired=str(rs_spec.get("replicas", 0)),
                    ready=str(rs_status.get("readyReplicas", 0)),
                )
            )
        pod_summary = pod_rows_by_selector.get((namespace, app_label), [])
        rows.append(
            {
                "namespace": namespace,
                "name": name,
                "revision": markdown_table_cell(annotations.get("deployment.kubernetes.io/revision") or "-"),
                "restartedAt": markdown_table_cell(
                    template_annotations.get("kubectl.kubernetes.io/restartedAt") or "-"
                ),
                "observedGeneration": markdown_table_cell(status.get("observedGeneration") or "-"),
                "ready": f"{status.get('readyReplicas', 0)}/{spec.get('replicas', 0)}",
                "updated": markdown_table_cell(status.get("updatedReplicas", 0)),
                "replicaSets": markdown_table_cell("; ".join(rs_summary) or "-"),
                "pods": markdown_table_cell("; ".join(sorted(pod_summary)) or "-"),
            }
        )

    lines = [
        "Deployment rollout/replacement evidence from Kubernetes APIs.",
        "Ready replicas only prove current availability. Do not say Pods were replaced unless restart annotation, Deployment revision/ReplicaSet transition, ExecutionRecord, or before/after Pod identity comparison proves it.",
        "| Namespace | Deployment | Revision | RestartedAt | ObservedGeneration | Ready | Updated | Recent ReplicaSets | Current Pods |",
        "| :--- | :--- | :--- | :--- | :--- | :---: | :---: | :--- | :--- |",
    ]
    for row in sorted(rows, key=lambda item: (str(item["namespace"]), str(item["name"])))[:40]:
        lines.append(
            "| {namespace} | `{name}` | {revision} | {restartedAt} | {observedGeneration} | {ready} | {updated} | {replicaSets} | {pods} |".format(
                **row
            )
        )
    if not rows:
        lines.append("| - | - | - | - | - | - | - | - | - |")
    return "\n".join(lines)


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
