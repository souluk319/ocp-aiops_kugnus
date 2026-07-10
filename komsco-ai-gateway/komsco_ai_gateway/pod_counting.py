from collections.abc import Mapping
from typing import Any

from .cluster_common import metadata_name, resource_items
from .cluster_evidence import markdown_table_cell, pod_ready_summary


def _metadata_namespace(resource: Mapping[str, Any]) -> str:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    return str(metadata.get("namespace") or "")


def _resource_labels(resource: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = resource.get("metadata", {}) if isinstance(resource.get("metadata"), Mapping) else {}
    labels = metadata.get("labels")
    return labels if isinstance(labels, Mapping) else {}


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


def selector_matches_labels(selector: Mapping[str, Any], labels: Mapping[str, Any]) -> bool:
    matched_any_selector = False
    match_labels = selector.get("matchLabels")
    if isinstance(match_labels, Mapping):
        for key, value in match_labels.items():
            matched_any_selector = True
            if str(labels.get(str(key)) or "") != str(value):
                return False

    expressions = selector.get("matchExpressions")
    if isinstance(expressions, list):
        for expression in expressions:
            if not isinstance(expression, Mapping):
                return False
            key = str(expression.get("key") or "")
            operator = str(expression.get("operator") or "")
            values = expression.get("values")
            value_set = {str(value) for value in values} if isinstance(values, list) else set()
            label_exists = key in labels
            label_value = str(labels.get(key) or "")
            matched_any_selector = True
            if operator == "In" and label_value not in value_set:
                return False
            if operator == "NotIn" and label_exists and label_value in value_set:
                return False
            if operator == "Exists" and not label_exists:
                return False
            if operator == "DoesNotExist" and label_exists:
                return False
            if operator not in {"In", "NotIn", "Exists", "DoesNotExist"}:
                return False

    return matched_any_selector


def pod_matches_deployment_selector(pod: Mapping[str, Any], deployment: Mapping[str, Any]) -> bool:
    if _metadata_namespace(pod) != _metadata_namespace(deployment):
        return False
    spec = deployment.get("spec", {}) if isinstance(deployment.get("spec"), Mapping) else {}
    selector = spec.get("selector")
    if not isinstance(selector, Mapping):
        return False
    return selector_matches_labels(selector, _resource_labels(pod))


def pod_ready_numbers(pod: Mapping[str, Any]) -> tuple[int, int]:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if not isinstance(statuses, list):
        return 0, 0
    total = len(statuses)
    ready = sum(1 for item in statuses if isinstance(item, Mapping) and item.get("ready"))
    return ready, total


def pod_is_fully_ready(pod: Mapping[str, Any]) -> bool:
    ready, total = pod_ready_numbers(pod)
    return total > 0 and ready == total


def pod_restart_total(pod: Mapping[str, Any]) -> int:
    statuses = pod.get("status", {}).get("containerStatuses", [])
    if not isinstance(statuses, list):
        return 0
    return sum(int(item.get("restartCount") or 0) for item in statuses if isinstance(item, Mapping))


def pod_is_terminating(pod: Mapping[str, Any]) -> bool:
    metadata = pod.get("metadata", {}) if isinstance(pod.get("metadata"), Mapping) else {}
    return bool(metadata.get("deletionTimestamp"))


def pod_matches_target_fallback(pod: Mapping[str, Any], target_name: str, namespace: str = "") -> bool:
    if namespace and _metadata_namespace(pod) != namespace:
        return False

    pod_name = metadata_name(pod)
    if pod_name == target_name or pod_name.startswith(f"{target_name}-"):
        return True

    labels = _resource_labels(pod)
    standard_identity_labels = (
        "app",
        "app.kubernetes.io/name",
        "app.kubernetes.io/instance",
        "deployment",
        "deploymentconfig",
        "name",
    )
    return any(str(labels.get(key) or "") == target_name for key in standard_identity_labels)


def deployment_matches_identity(deployment: Mapping[str, Any], target_name: str) -> bool:
    if metadata_name(deployment) == target_name:
        return True

    standard_identity_labels = (
        "app",
        "app.kubernetes.io/name",
        "app.kubernetes.io/instance",
        "deployment",
        "deploymentconfig",
        "name",
    )
    metadata_labels = _resource_labels(deployment)
    if any(str(metadata_labels.get(key) or "") == target_name for key in standard_identity_labels):
        return True

    spec = deployment.get("spec", {}) if isinstance(deployment.get("spec"), Mapping) else {}
    template = spec.get("template") if isinstance(spec.get("template"), Mapping) else {}
    template_metadata = template.get("metadata") if isinstance(template.get("metadata"), Mapping) else {}
    template_labels = template_metadata.get("labels") if isinstance(template_metadata.get("labels"), Mapping) else {}
    return any(str(template_labels.get(key) or "") == target_name for key in standard_identity_labels)


def summarize_counted_pods(pods: list[Mapping[str, Any]]) -> dict[str, Any]:
    phase_counts: dict[str, int] = {}
    for pod in pods:
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        phase = str(status.get("phase") or "Unknown")
        phase_counts[phase] = phase_counts.get(phase, 0) + 1

    pod_details = [
        {
            "name": metadata_name(pod),
            "phase": pod_display_state(pod),
            "ready": pod_ready_summary(pod),
            "restarts": pod_restart_total(pod),
            "terminating": pod_is_terminating(pod),
        }
        for pod in sorted(pods, key=lambda item: metadata_name(item))
    ]
    running = sum(
        1
        for pod in pods
        if (pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}).get("phase") == "Running"
    )
    ready = sum(1 for pod in pods if pod_is_fully_ready(pod))
    terminating = sum(1 for pod in pods if pod_is_terminating(pod))
    return {
        "phaseCounts": phase_counts,
        "podDetails": pod_details,
        "readyPods": ready,
        "runningPods": running,
        "terminatingPods": terminating,
        "totalPods": len(pods),
        "unhealthyPods": sum(
            1
            for pod in pods
            if not pod_is_fully_ready(pod)
            or (pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}).get("phase") != "Running"
        ),
    }


def build_top_pod_namespace_count_result(pods_payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not pods_payload:
        return {
            "reason": "Kubernetes API pod list was not returned",
            "rows": [],
            "status": "unavailable",
        }

    counts: dict[str, int] = {}
    for pod in resource_items(pods_payload):
        namespace = _metadata_namespace(pod)
        if not namespace:
            continue
        counts[namespace] = counts.get(namespace, 0) + 1

    rows = [
        {"namespace": namespace, "podCount": count}
        for namespace, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]
    if not rows:
        return {
            "reason": "No pod namespace metadata was found",
            "rows": [],
            "status": "not_found",
        }

    return {
        "rows": rows,
        "status": "found",
        "topNamespace": rows[0]["namespace"],
        "topPodCount": rows[0]["podCount"],
        "totalNamespaces": len(rows),
        "totalPods": sum(row["podCount"] for row in rows),
    }


def top_pod_namespace_count_response(result: Mapping[str, Any], *, display_limit: int = 5) -> str:
    status = str(result.get("status") or "unknown")
    if status == "unavailable":
        return "\n".join(
            [
                "namespace별 Pod 수를 직접 조회하지 못했습니다.",
                "",
                f"- 사유: {result.get('reason')}",
                "- 서버 변경은 실행하지 않았습니다.",
            ]
        )
    if status != "found":
        return "\n".join(
            [
                "현재 조회 범위에서 Pod namespace 정보를 확인하지 못했습니다.",
                "",
                "- 서버 변경은 실행하지 않았습니다.",
            ]
        )

    rows = result.get("rows")
    result_rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    top_namespace = str(result.get("topNamespace") or result_rows[0].get("namespace") or "")
    top_pod_count = int(result.get("topPodCount") or result_rows[0].get("podCount") or 0)
    visible_rows = result_rows[: max(display_limit, 1)]

    lines = [
        f"`{top_namespace}`입니다. 현재 조회 범위에서 Pod {top_pod_count}개로 가장 많습니다.",
        "",
        f"상위 {len(visible_rows)}개 namespace만 보면:",
        "",
        "| 순위 | Namespace | Pod 수 |",
        "| ---: | :--- | ---: |",
    ]
    for index, row in enumerate(visible_rows, start=1):
        lines.append(
            "| "
            + " | ".join(
                [
                    str(index),
                    markdown_table_cell(f"`{row.get('namespace')}`"),
                    markdown_table_cell(row.get("podCount")),
                ]
            )
            + " |"
        )
    if len(result_rows) > len(visible_rows):
        lines.extend(
            [
                "",
                f"전체 namespace는 {len(result_rows)}개입니다. 전체 목록이 필요하면 `전체 namespace별 Pod 수 보여줘`라고 이어서 물어보세요.",
            ]
        )
    lines.extend(["", "서버 변경은 실행하지 않았습니다."])
    return "\n".join(lines)


def build_pod_count_investigation(
    query: Mapping[str, str],
    deployments_payload: Mapping[str, Any] | None,
    pods_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    target_name = str(query.get("targetName") or "")
    namespace = str(query.get("namespace") or "")
    if not target_name:
        return {
            "namespace": namespace,
            "reason": "target_name_missing",
            "status": "missing_target",
        }

    deployments = resource_items(deployments_payload)
    pods = resource_items(pods_payload)
    matched_deployments = [
        deployment
        for deployment in deployments
        if metadata_name(deployment) == target_name
        and (not namespace or _metadata_namespace(deployment) == namespace)
    ]

    rows: list[dict[str, Any]] = []
    if matched_deployments:
        for deployment in sorted(
            matched_deployments,
            key=lambda item: (_metadata_namespace(item), metadata_name(item)),
        ):
            spec = deployment.get("spec", {}) if isinstance(deployment.get("spec"), Mapping) else {}
            status = deployment.get("status", {}) if isinstance(deployment.get("status"), Mapping) else {}
            matched_pods = [pod for pod in pods if pod_matches_deployment_selector(pod, deployment)]
            pod_summary = summarize_counted_pods(matched_pods)
            rows.append(
                {
                    **pod_summary,
                    "availableReplicas": int(status.get("availableReplicas") or 0),
                    "desiredReplicas": int(spec.get("replicas") or 0),
                    "kind": "Deployment",
                    "namespace": _metadata_namespace(deployment),
                    "observedGeneration": status.get("observedGeneration"),
                    "readyReplicas": int(status.get("readyReplicas") or 0),
                    "targetName": target_name,
                    "updatedReplicas": int(status.get("updatedReplicas") or 0),
                }
            )
        return {
            "matchStrategy": "deployment_selector",
            "namespace": namespace,
            "rows": rows,
            "status": "found",
            "targetName": target_name,
        }

    matched_pods = [pod for pod in pods if pod_matches_target_fallback(pod, target_name, namespace=namespace)]
    if matched_pods:
        grouped: dict[str, list[Mapping[str, Any]]] = {}
        for pod in matched_pods:
            grouped.setdefault(_metadata_namespace(pod), []).append(pod)
        for pod_namespace, namespace_pods in sorted(grouped.items()):
            pod_summary = summarize_counted_pods(namespace_pods)
            rows.append(
                {
                    **pod_summary,
                    "availableReplicas": "-",
                    "desiredReplicas": "-",
                    "kind": "PodSelector",
                    "namespace": pod_namespace,
                    "readyReplicas": "-",
                    "targetName": target_name,
                    "updatedReplicas": "-",
                }
            )
        return {
            "matchStrategy": "pod_name_or_standard_labels",
            "namespace": namespace,
            "rows": rows,
            "status": "found",
            "targetName": target_name,
        }

    return {
        "matchStrategy": "deployment_then_pod_fallback",
        "namespace": namespace,
        "rows": [],
        "status": "not_found",
        "targetName": target_name,
    }


def pod_count_investigation_response(result: Mapping[str, Any]) -> str:
    status = str(result.get("status") or "unknown")
    target_name = str(result.get("targetName") or "")
    namespace = str(result.get("namespace") or "")
    scope = f"namespace `{namespace}`" if namespace else "접근 가능한 전체 namespace"

    if status == "unavailable":
        return "\n".join(
            [
                "Pod 개수 직접 조회를 수행하지 못했습니다.",
                "",
                f"- 사유: {result.get('reason')}",
                f"- 조회 범위: {scope}",
            ]
        )

    if status == "missing_target":
        return "\n".join(
            [
                "Pod 개수를 직접 조회하려면 대상 Deployment 또는 Pod 이름이 필요합니다.",
                "",
                f"- 조회 범위: {scope}",
                "- 예: `komsco-ai-dev 네임스페이스의 web-api 파드 몇 개 떠있어?`",
            ]
        )

    if status == "not_found":
        return "\n".join(
            [
                f"`{target_name}` 기준으로 직접 Kubernetes API를 조회했지만 매칭되는 Deployment 또는 Pod를 찾지 못했습니다.",
                "",
                f"- 조회 범위: {scope}",
                f"- 매칭 방식: `{result.get('matchStrategy')}`",
                "- 대상 이름 또는 namespace를 확인하세요.",
            ]
        )

    rows = result.get("rows")
    result_rows = [row for row in rows if isinstance(row, Mapping)] if isinstance(rows, list) else []
    if not result_rows:
        return f"`{target_name}` 기준 조회 결과가 비어 있습니다. 조회 범위: {scope}"

    first_row = result_rows[0]
    if len(result_rows) == 1:
        lead = (
            f"`{first_row.get('namespace')}/{target_name}` 기준 현재 Pod는 총 "
            f"{first_row.get('totalPods')}개이며, Running {first_row.get('runningPods')}개, "
            f"Ready {first_row.get('readyPods')}/{first_row.get('totalPods')}개입니다."
        )
    else:
        total_pods = sum(int(row.get("totalPods") or 0) for row in result_rows)
        running_pods = sum(int(row.get("runningPods") or 0) for row in result_rows)
        ready_pods = sum(int(row.get("readyPods") or 0) for row in result_rows)
        lead = (
            f"`{target_name}` 이름이 여러 namespace에서 매칭되었습니다. 합계는 총 {total_pods}개, "
            f"Running {running_pods}개, Ready {ready_pods}/{total_pods}개입니다."
        )

    lines = [
        lead,
        "",
        "직접 Kubernetes API로 조회했으며 실행/변경 조치는 수행하지 않았습니다.",
        "",
        "| Namespace | Target | Desired | Current Pods | Running | Ready | Terminating | Pod details |",
        "| :--- | :--- | ---: | ---: | ---: | :---: | ---: | :--- |",
    ]
    for row in result_rows:
        pod_details = row.get("podDetails")
        detail_items = []
        if isinstance(pod_details, list):
            for pod in pod_details[:8]:
                if not isinstance(pod, Mapping):
                    continue
                terminating = ", terminating" if pod.get("terminating") else ""
                detail_items.append(
                    f"{pod.get('name')}({pod.get('phase')}, ready {pod.get('ready')}, restarts {pod.get('restarts')}{terminating})"
                )
            if len(pod_details) > len(detail_items):
                detail_items.append(f"+{len(pod_details) - len(detail_items)} more")

        lines.append(
            "| "
            + " | ".join(
                [
                    markdown_table_cell(row.get("namespace")),
                    markdown_table_cell(f"{row.get('kind')}/{row.get('targetName')}"),
                    markdown_table_cell(row.get("desiredReplicas")),
                    markdown_table_cell(row.get("totalPods")),
                    markdown_table_cell(row.get("runningPods")),
                    markdown_table_cell(f"{row.get('readyPods')}/{row.get('totalPods')}"),
                    markdown_table_cell(row.get("terminatingPods")),
                    markdown_table_cell(", ".join(detail_items) or "-", max_length=800),
                ]
            )
            + " |"
        )

    return "\n".join(lines)
