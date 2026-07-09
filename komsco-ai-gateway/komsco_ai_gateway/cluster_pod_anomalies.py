from collections.abc import Mapping
from typing import Any

from .cluster_anomaly_templates import anomaly_finding, anomaly_resource
from .cluster_common import (
    metadata_name,
    metadata_namespace,
    pod_owner_summary,
    pod_ready_summary,
    resource_items,
)


def pod_anomaly_findings(pods_payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for pod in resource_items(pods_payload):
        namespace = metadata_namespace(pod)
        pod_name = metadata_name(pod)
        status = pod.get("status", {}) if isinstance(pod.get("status"), Mapping) else {}
        phase = str(status.get("phase") or "Unknown")
        resource = anomaly_resource(kind="Pod", namespace=namespace, name=pod_name)
        if phase == "Pending":
            findings.append(pending_pod_finding(namespace, pod_name, pod, resource, phase))
        findings.extend(container_anomaly_findings(namespace, pod_name, status, resource))
    return findings


def pending_pod_finding(
    namespace: str,
    pod_name: str,
    pod: Mapping[str, Any],
    resource: Mapping[str, Any],
    phase: str,
) -> dict[str, Any]:
    return anomaly_finding(
        candidate_cause="스케줄링, PVC, 이미지 pull, node resource 중 하나가 막혔을 가능성이 있습니다. Events 확인이 우선입니다.",
        evidence=f"Pod phase=`Pending`, ready={pod_ready_summary(pod)}, owner={pod_owner_summary(pod)}",
        finding_type="pod_pending",
        namespace=namespace,
        next_check=f"oc get events -n {namespace} --field-selector involvedObject.name={pod_name}",
        priority=25,
        reason=phase,
        resource=resource,
        severity="확인 필요",
        source="pods",
        title=f"Pending Pod: {namespace}/{pod_name}",
    )


def container_anomaly_findings(
    namespace: str,
    pod_name: str,
    status: Mapping[str, Any],
    resource: Mapping[str, Any],
) -> list[dict[str, Any]]:
    statuses = status.get("containerStatuses", [])
    if not isinstance(statuses, list):
        return []
    findings: list[dict[str, Any]] = []
    for container in statuses:
        if isinstance(container, Mapping):
            findings.extend(container_state_findings(namespace, pod_name, container, resource))
    return findings


def container_state_findings(
    namespace: str,
    pod_name: str,
    container: Mapping[str, Any],
    resource: Mapping[str, Any],
) -> list[dict[str, Any]]:
    container_name = str(container.get("name") or "unknown-container")
    state = container.get("state", {}) if isinstance(container.get("state"), Mapping) else {}
    waiting = state.get("waiting") if isinstance(state.get("waiting"), Mapping) else {}
    waiting_reason = str(waiting.get("reason") or "")
    waiting_message = str(waiting.get("message") or "")
    restart_count = int(container.get("restartCount") or 0)
    last_state = container.get("lastState", {}) if isinstance(container.get("lastState"), Mapping) else {}
    last_terminated = last_state.get("terminated") if isinstance(last_state.get("terminated"), Mapping) else {}
    last_reason = str(last_terminated.get("reason") or "")

    findings: list[dict[str, Any]] = []
    if waiting_reason in {"CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"}:
        findings.append(
            pull_or_crash_finding(
                namespace,
                pod_name,
                container_name,
                waiting_reason,
                waiting_message,
                restart_count,
                resource,
            )
        )
    elif waiting_reason and waiting_reason not in {"ContainerCreating", "PodInitializing"}:
        findings.append(
            waiting_container_finding(
                namespace,
                pod_name,
                container_name,
                waiting_reason,
                waiting_message,
                resource,
            )
        )
    if restart_count >= 5:
        findings.append(
            restart_history_finding(
                namespace,
                pod_name,
                container_name,
                restart_count,
                last_reason,
                resource,
            )
        )
    return findings


def pull_or_crash_finding(
    namespace: str,
    pod_name: str,
    container_name: str,
    waiting_reason: str,
    waiting_message: str,
    restart_count: int,
    resource: Mapping[str, Any],
) -> dict[str, Any]:
    is_pull = waiting_reason in {"ImagePullBackOff", "ErrImagePull"}
    return anomaly_finding(
        candidate_cause=(
            "이미지 이름, registry 접근, pull secret, tag 존재 여부 확인이 우선입니다."
            if is_pull
            else "컨테이너 프로세스 종료, 설정/env/command 오류, 의존 서비스 연결 실패 가능성이 큽니다."
        ),
        evidence=(
            f"container={container_name}, waiting.reason={waiting_reason}, "
            f"restartCount={restart_count}, message={waiting_message[:180]}"
        ),
        finding_type="pod_image_pull" if is_pull else "pod_crashloop",
        namespace=namespace,
        next_check=(
            f"oc describe pod {pod_name} -n {namespace}"
            if is_pull
            else f"oc logs {pod_name} -n {namespace} -c {container_name} --previous"
        ),
        priority=5 if not is_pull else 8,
        reason=waiting_reason,
        resource=resource,
        severity="위험",
        source="pods",
        title=f"{waiting_reason}: {namespace}/{pod_name}",
    )


def waiting_container_finding(
    namespace: str,
    pod_name: str,
    container_name: str,
    waiting_reason: str,
    waiting_message: str,
    resource: Mapping[str, Any],
) -> dict[str, Any]:
    return anomaly_finding(
        candidate_cause="컨테이너가 정상 실행 상태로 진입하지 못했습니다. waiting reason과 Events를 같이 확인해야 합니다.",
        evidence=f"container={container_name}, waiting.reason={waiting_reason}, message={waiting_message[:180]}",
        finding_type="pod_waiting",
        namespace=namespace,
        next_check=f"oc describe pod {pod_name} -n {namespace}",
        priority=18,
        reason=waiting_reason,
        resource=resource,
        severity="확인 필요",
        source="pods",
        title=f"Waiting container: {namespace}/{pod_name}",
    )


def restart_history_finding(
    namespace: str,
    pod_name: str,
    container_name: str,
    restart_count: int,
    last_reason: str,
    resource: Mapping[str, Any],
) -> dict[str, Any]:
    return anomaly_finding(
        candidate_cause="누적 재시작 이력이 있습니다. 현재 장애인지 최근 복구 이력인지는 lastState와 metrics 증가량 확인이 필요합니다.",
        evidence=f"container={container_name}, restartCount={restart_count}, lastState.reason={last_reason or '-'}",
        finding_type="pod_restart_history",
        namespace=namespace,
        next_check=f"oc get pod {pod_name} -n {namespace} -o jsonpath='{{.status.containerStatuses}}'",
        priority=35 if restart_count < 20 else 16,
        reason=last_reason or "RestartCountHigh",
        resource=resource,
        severity="주의" if restart_count < 20 else "확인 필요",
        source="pods",
        title=f"Container restart history: {namespace}/{pod_name}",
    )
