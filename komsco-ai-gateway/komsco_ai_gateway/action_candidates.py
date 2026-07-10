from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from .security import now_rfc3339


ACTION_CANDIDATE_FORBIDDEN_VERBS = [
    "apply",
    "attach",
    "create",
    "delete",
    "evict",
    "exec",
    "patch",
    "replace",
    "restart",
    "rollout",
    "scale",
    "update",
]


def action_candidate_target_label(resource: Mapping[str, Any]) -> str:
    kind = str(resource.get("kind") or "Resource")
    name = str(resource.get("name") or "unknown")
    namespace = str(resource.get("namespace") or "")
    return f"{namespace}/{kind}/{name}" if namespace else f"cluster/{kind}/{name}"


def evidence_check_check_command(resource: Mapping[str, Any], fallback: str = "관련 리소스 상태를 조회합니다.") -> str:
    kind = str(resource.get("kind") or "")
    name = str(resource.get("name") or "")
    namespace = str(resource.get("namespace") or "")
    if kind.lower() == "pod" and name and namespace:
        return f"oc describe pod {name} -n {namespace}"
    if kind.lower() == "clusteroperator" and name:
        return f"oc get clusteroperator {name} -o yaml"
    if kind.lower() == "clusterversion":
        return "oc get clusterversion version -o yaml"
    if kind and name and namespace:
        return f"oc describe {kind} {name} -n {namespace}"
    return fallback


def action_candidate_template(
    finding: Mapping[str, Any],
) -> tuple[list[str], list[str], list[str], str, str]:
    finding_type = str(finding.get("type") or "")
    resource = finding.get("resource") if isinstance(finding.get("resource"), Mapping) else {}
    target_label = action_candidate_target_label(resource)
    evidence_check_check = evidence_check_check_command(resource)

    if finding_type == "pod_crashloop":
        return (
            [
                evidence_check_check,
                "이전 컨테이너 로그와 Warning Event를 확인해 현재 진행 중인 CrashLoop인지 확정합니다.",
                "소유 리소스와 최근 배포 변경 이력을 확인합니다.",
            ],
            [
                "원인이 image, command, env, config, dependency 중 어디인지 분리합니다.",
                "승인 전에는 template 수정, rollback, 재시작을 실행 계획으로 만들지 않습니다.",
                "승인 후에는 단일 원인에 맞춘 변경 계획과 rollback 경로를 별도로 작성합니다.",
            ],
            [
                "대상 workload의 rollout 상태와 Ready Pod 수를 확인합니다.",
                "최근 1시간 restart 증가량이 멈췄는지 Thanos 지표로 재확인합니다.",
            ],
            f"{target_label} 회복 가능성이 있지만 잘못된 변경은 재시작 또는 서비스 영향으로 이어질 수 있습니다.",
            "high",
        )
    if finding_type == "pod_image_pull":
        return (
            [
                evidence_check_check,
                "이미지 이름, tag, registry 접근성, imagePullSecret 참조를 확인합니다.",
                "동일 namespace의 Secret과 ServiceAccount 연결 상태를 확인합니다.",
            ],
            [
                "이미지/tag 오타, registry 권한, pull secret 누락 중 하나로 원인을 좁힙니다.",
                "승인 전에는 image 또는 secret 변경을 실행하지 않습니다.",
                "승인 후에는 변경 범위와 영향받는 workload를 명시한 계획을 작성합니다.",
            ],
            [
                "Pod Events에서 pull 실패 메시지가 사라졌는지 확인합니다.",
                "새 Pod가 ImagePullBackOff 없이 Running/Ready로 진입했는지 확인합니다.",
            ],
            f"{target_label} 기동 차단을 해소할 수 있으나 image/secret 변경은 배포 범위 전체에 영향이 날 수 있습니다.",
            "high",
        )
    if finding_type in {"pod_pending", "warning_event"}:
        return (
            [
                evidence_check_check,
                "동일 namespace의 최근 Event를 시간순으로 확인합니다.",
                "PVC, quota, node resource, scheduling constraint 중 차단 지점을 분리합니다.",
            ],
            [
                "스케줄링 실패 사유가 quota/PVC/node/affinity 중 무엇인지 확정합니다.",
                "승인 전에는 resource request, PVC, node selector, affinity를 변경하지 않습니다.",
                "승인 후에는 최소 변경 단위와 되돌림 방법을 포함한 계획을 작성합니다.",
            ],
            [
                "Pending Pod가 Running/Ready로 바뀌었는지 확인합니다.",
                "동일 reason의 Warning Event가 계속 증가하지 않는지 확인합니다.",
            ],
            f"{target_label} 배치 지연을 해소할 수 있으나 quota나 scheduling 변경은 다른 workload에 영향을 줄 수 있습니다.",
            "medium",
        )
    if finding_type == "clusteroperator_condition":
        return (
            [
                evidence_check_check,
                "Operator condition의 reason/message와 관련 operand namespace를 확인합니다.",
                "ClusterVersion과 다른 ClusterOperator의 연쇄 영향을 확인합니다.",
            ],
            [
                "Operator 자체 문제인지 operand 문제인지 분리합니다.",
                "승인 전에는 ClusterOperator, Subscription, operand 리소스를 변경하지 않습니다.",
                "승인 후에는 벤더/운영 절차에 맞는 복구 계획을 별도로 작성합니다.",
            ],
            [
                "해당 ClusterOperator의 Available/Degraded/Progressing 조건을 재확인합니다.",
                "콘솔과 경고 상태가 동시에 회복되었는지 확인합니다.",
            ],
            f"{target_label} 정상화는 클러스터 기능 전체에 영향이 있으므로 변경 전 승인과 영향 범위 확인이 필요합니다.",
            "high",
        )
    if finding_type == "upgrade_blocked":
        return (
            [
                evidence_check_check,
                "Upgradeable=False reason과 AdminAck 또는 차단 조건을 확인합니다.",
                "관련 ClusterOperator 조건과 업데이트 채널 상태를 함께 확인합니다.",
            ],
            [
                "업그레이드 차단 조건을 문서화하고 필요한 승인 절차를 정리합니다.",
                "승인 전에는 upgrade ack, 채널 변경, 업데이트 진행을 수행하지 않습니다.",
                "승인 후에는 maintenance window와 rollback 판단 기준을 포함합니다.",
            ],
            [
                "Upgradeable 조건이 True로 회복되었는지 확인합니다.",
                "업그레이드 전 필수 ClusterOperator가 안정 상태인지 확인합니다.",
            ],
            "업그레이드 차단 해소는 클러스터 전체 운영 계획과 연결되므로 사전 승인 없이는 실행하지 않습니다.",
            "high",
        )
    if finding_type in {"active_alert", "pod_restart_spike", "pod_restart_history"}:
        return (
            [
                evidence_check_check,
                "Alert label, Pod 상태, 최근 restart 지표가 같은 대상을 가리키는지 확인합니다.",
                "현재 장애인지 복구된 이력인지 lastState와 시간 범위로 분리합니다.",
            ],
            [
                "경고와 지표의 공통 원인을 RCA 후보로 고정합니다.",
                "승인 전에는 재시작, scale, patch 같은 증상 제거 작업을 실행하지 않습니다.",
                "승인 후에는 원인별 수정과 검증 순서를 나눈 계획을 작성합니다.",
            ],
            [
                "Alert firing 상태가 해소되었는지 확인합니다.",
                "restart 증가량과 Ready 상태가 안정화되었는지 확인합니다.",
            ],
            f"{target_label}의 경고/재시작 신호를 줄일 수 있으나 원인 확정 전 실행은 재발 가능성이 높습니다.",
            "medium",
        )
    return (
        [
            evidence_check_check,
            "관련 리소스의 현재 상태, Event, owner 관계를 먼저 확인합니다.",
            "데이터 소스 실패가 있으면 후보 신뢰도를 낮춰 판단합니다.",
        ],
        [
            "확인 결과가 충분할 때만 수정 후보를 하나로 좁힙니다.",
            "승인 전에는 변경성 작업을 실행하지 않습니다.",
            "승인 후에는 영향 범위와 되돌림 기준을 포함한 계획을 작성합니다.",
        ],
        [
            "같은 이상 징후가 더 이상 증가하지 않는지 확인합니다.",
            "대상 리소스와 상위 workload의 정상 상태를 함께 확인합니다.",
        ],
        f"{target_label}의 운영 리스크를 낮출 수 있으나 원인 확정 전 실행은 금지됩니다.",
        "medium",
    )


def build_aiops_action_candidates(
    anomaly_summary: Mapping[str, Any] | None,
    data_sources: list[Mapping[str, Any]],
    *,
    mutations_enabled: bool,
    action_executor_url: str,
    unrestricted_commands_enabled: bool,
) -> dict[str, Any]:
    anomaly_spec = (
        anomaly_summary.get("spec", {})
        if isinstance(anomaly_summary, Mapping) and isinstance(anomaly_summary.get("spec"), Mapping)
        else {}
    )
    findings = anomaly_spec.get("findings") if isinstance(anomaly_spec.get("findings"), list) else []
    required_gaps = [
        item
        for item in data_sources
        if item.get("required") and item.get("status") not in {"available", "partial"}
    ]
    action_execution_enabled = mutations_enabled and bool(action_executor_url) and not required_gaps
    action_candidate_mode = "execute"
    proposal_only = not action_execution_enabled
    blocked_actions = [] if action_execution_enabled else list(ACTION_CANDIDATE_FORBIDDEN_VERBS)
    candidates: list[dict[str, Any]] = []
    for finding in findings:
        if not isinstance(finding, Mapping):
            continue
        finding_type = str(finding.get("type") or "unknown")
        finding_resource = dict(finding.get("resource") if isinstance(finding.get("resource"), Mapping) else {})
        if finding_type in {"pod_crashloop", "pod_restart_spike", "pod_restart_history"} and str(
            finding_resource.get("kind") or ""
        ) == "Pod":
            source_id = str(
                finding.get("id")
                or hashlib.sha256(json.dumps(finding, sort_keys=True, default=str).encode()).hexdigest()[:16]
            )
            diagnostic_steps = [
                evidence_check_check_command(finding_resource),
                "이전 컨테이너 로그(`--previous`)와 Warning Event를 확인합니다.",
                "lastState.reason, exitCode, command/env/config 확인 결과를 분리합니다.",
            ]
            candidates.append(
                {
                    "approvalRequired": True,
                    "blockedActions": list(ACTION_CANDIDATE_FORBIDDEN_VERBS),
                    "blockedReasons": ["diagnostic-review", "review-only-plan"],
                    "confidence": "medium",
                    "evidence": str(finding.get("evidence") or "CrashLoopBackOff 진단 확인 필요"),
                    "evidenceRefs": [
                        {
                            "evidenceType": str(finding.get("source") or "pods"),
                            "findingId": f"{source_id}-diagnostic",
                            "sourceType": "pod_diagnostic_review",
                            "status": "collected",
                        }
                    ],
                    "executable": False,
                    "executionPolicy": {
                        "executionEnabled": False,
                        "mode": "review-only",
                        "mutationVerbsDisabled": True,
                        "proposalOnly": True,
                    },
                    "expectedImpact": "로그와 Pod 상세, Event 확인 결과를 검토하는 계획입니다. Pod 삭제나 재시작은 실행하지 않습니다.",
                    "id": f"action-candidate-{source_id}-diagnostic",
                    "mutationSubmitted": False,
                    "priority": max(1, int(finding.get("priority") or 10) - 1),
                    "prerequisiteChecks": diagnostic_steps,
                    "recommendationSteps": [
                        "이전 로그와 describe 결과를 먼저 확인",
                        "OOMKilled, command/env/config, probe, dependency 문제를 분리",
                        "원인이 확인된 뒤 수정/롤백/재생성 유도 중 하나를 선택",
                    ],
                    "riskLevel": "low",
                    "riskLabel": "낮음",
                    "severity": str(finding.get("severity") or "확인 필요"),
                    "sourceFindingId": f"{source_id}-diagnostic",
                    "sourceType": "pod_diagnostic_review",
                    "statusLabel": "원인 확인 플랜",
                    "target": finding_resource,
                    "title": "원인 확인 플랜",
                    "verificationChecks": ["로그/describe/Event 확인 결과가 정리되었는지 확인", "승인 전 mutation 없음 확인"],
                }
            )
            candidates.append(
                {
                    "approvalRequired": True,
                    "blockedActions": list(ACTION_CANDIDATE_FORBIDDEN_VERBS),
                    "blockedReasons": ["requires-root-cause", "review-only-plan"],
                    "confidence": "medium",
                    "evidence": str(finding.get("evidence") or "CrashLoopBackOff 원인별 수정 방향 검토 필요"),
                    "evidenceRefs": [
                        {
                            "evidenceType": str(finding.get("source") or "pods"),
                            "findingId": f"{source_id}-fix-review",
                            "sourceType": "pod_fix_or_rollback_review",
                            "status": "collected",
                        }
                    ],
                    "executable": False,
                    "executionPolicy": {
                        "executionEnabled": False,
                        "mode": "review-only",
                        "mutationVerbsDisabled": True,
                        "proposalOnly": True,
                    },
                    "expectedImpact": "원인 확인 후 Deployment template 수정, 이전 정상 revision rollback, config/env 수정 중 하나를 선택하는 계획입니다.",
                    "id": f"action-candidate-{source_id}-fix-review",
                    "mutationSubmitted": False,
                    "priority": int(finding.get("priority") or 10) + 1,
                    "prerequisiteChecks": [
                        "상위 ReplicaSet/Deployment owner chain 확인",
                        "최근 rollout/change cause 확인",
                        "ConfigMap/Secret/env/image/command 변경 이력 확인",
                    ],
                    "recommendationSteps": [
                        "원인이 command/env/config이면 Deployment template 수정 계획 작성",
                        "최근 배포가 원인이면 이전 정상 revision rollback 계획 작성",
                        "수정 전 영향 범위와 rollback 조건을 승인 게이트에 포함",
                    ],
                    "riskLevel": "medium",
                    "riskLabel": "보통",
                    "severity": str(finding.get("severity") or "확인 필요"),
                    "sourceFindingId": f"{source_id}-fix-review",
                    "sourceType": "pod_fix_or_rollback_review",
                    "statusLabel": "근본 조치 검토",
                    "target": finding_resource,
                    "title": "수정/롤백 검토 플랜",
                    "verificationChecks": ["rollout status 확인", "Ready Pod 수 확인", "restart 증가 중단 확인"],
                }
            )
        prerequisite_checks, recommendation_steps, verification_checks, expected_impact, risk_level = (
            action_candidate_template(finding)
        )
        source_id = str(
            finding.get("id")
            or hashlib.sha256(json.dumps(finding, sort_keys=True, default=str).encode()).hexdigest()[:16]
        )
        blocked_reasons = ["approval-required"]
        if not action_execution_enabled:
            blocked_reasons.append("execution-gate-disabled")
        if not mutations_enabled:
            blocked_reasons.append("mutation-disabled")
        if not action_executor_url:
            blocked_reasons.append("action-executor-not-configured")
        if required_gaps:
            blocked_reasons.append("required-data-source-gap")
        candidates.append(
            {
                "approvalRequired": True,
                "blockedActions": blocked_actions,
                "blockedReasons": blocked_reasons,
                "confidence": "limited" if required_gaps else "medium",
                "evidence": str(finding.get("evidence") or finding.get("message") or "확인 중"),
                "evidenceRefs": [
                    {
                        "evidenceType": str(finding.get("source") or "anomaly"),
                        "findingId": source_id,
                        "sourceType": str(finding.get("type") or "unknown"),
                        "status": "collected",
                    }
                ],
                "executable": action_execution_enabled,
                "executionPolicy": {
                    "executionEnabled": action_execution_enabled,
                    "mode": action_candidate_mode,
                    "mutationVerbsDisabled": not action_execution_enabled,
                    "proposalOnly": proposal_only,
                },
                "expectedImpact": expected_impact,
                "id": f"action-candidate-{source_id}",
                "mutationSubmitted": False,
                "priority": int(finding.get("priority") or 999),
                "prerequisiteChecks": prerequisite_checks,
                "recommendationSteps": recommendation_steps,
                "riskLevel": risk_level,
                "riskLabel": "높음" if risk_level == "high" else "중간",
                "severity": str(finding.get("severity") or "확인 필요"),
                "sourceFindingId": source_id,
                "sourceType": str(finding.get("type") or "unknown"),
                "statusLabel": "승인 후 실행 계획 생성 가능" if action_execution_enabled else "제안만 함 / 실행 안 함",
                "target": finding_resource,
                "title": (
                    "Pod 재생성 유도"
                    if finding_type in {"pod_crashloop", "pod_restart_spike", "pod_restart_history"}
                    else f"{finding.get('title') or '이상 징후'} 조치 후보"
                ),
                "verificationChecks": verification_checks,
            }
        )

    candidates = sorted(candidates, key=lambda item: (item["priority"], item["sourceType"], item["id"]))
    if required_gaps:
        status = "blocked"
        status_label = "필수 데이터 소스 실패로 조치 후보 신뢰 제한"
    elif candidates:
        status = "candidates"
        status_label = (
            f"승인 기반 조치 후보 {len(candidates)}건"
            if action_execution_enabled
            else f"승인 기반 조치 후보 {len(candidates)}건"
        )
    elif anomaly_spec.get("status") == "normal":
        status = "normal"
        status_label = "현재 수집 범위에서 제안할 조치 후보 없음"
    else:
        status = "unknown"
        status_label = "조치 후보 생성을 위한 이상 징후 데이터 확인 중"

    return {
        "apiVersion": "aiops.komsco/v1",
        "kind": "AIOpsActionCandidateSummary",
        "metadata": {"generatedAt": now_rfc3339(), "name": "kugnus-action-candidates"},
        "spec": {
            "candidates": candidates[:8],
            "dataSources": list(data_sources),
            "safety": {
                "forbiddenMutationVerbs": list(ACTION_CANDIDATE_FORBIDDEN_VERBS),
                "methodsUsed": ["GET", "POST"] if action_execution_enabled else ["GET"],
                "mode": action_candidate_mode,
                "mutationsEnabled": mutations_enabled,
                "proposalOnly": proposal_only,
                "unrestrictedCommandsEnabled": unrestricted_commands_enabled,
            },
            "source": {
                "anomalySummaryName": str(
                    (anomaly_summary or {}).get("metadata", {}).get("name")
                    if isinstance((anomaly_summary or {}).get("metadata"), Mapping)
                    else "kugnus-anomaly-summary"
                ),
                "requiredDataSourceGaps": required_gaps,
            },
            "status": status,
            "statusLabel": status_label,
            "totals": {
                "approvalRequired": len(candidates),
                "blockedByRequiredSourceGap": len(required_gaps),
                "highRisk": len([candidate for candidate in candidates if candidate.get("riskLevel") == "high"]),
                "shown": min(len(candidates), 8),
                "total": len(candidates),
            },
        },
    }
