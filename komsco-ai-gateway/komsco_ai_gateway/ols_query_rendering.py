from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .security import redact_sensitive


@dataclass(frozen=True, slots=True)
class OlsQueryRenderInput:
    profile: str
    message: str
    page_context: Mapping[str, Any]
    policy: Mapping[str, Any]
    subject_metadata: Mapping[str, Any]
    language_contract: str
    section_contract: str
    operating_answer_contract: str
    resource_summary_contract: str
    attachment_context: str
    recent_context: str
    context_handoff: str
    gateway_guardrail: str
    crashloop_contract: str
    past_pod_restart_contract: str


def render_ols_query(payload: OlsQueryRenderInput) -> str:
    recent_context_block = (
        f"\nRecent conversation context:\n{payload.recent_context}\n"
        "Use this only to resolve follow-up references such as 그 namespace, 그 파드, 안에 있는 파드, 정리. "
        "Cluster facts still require verified Gateway/OpenShift evidence.\n"
        if payload.recent_context
        else ""
    )
    context_handoff_block = (
        f"\nVerified operational context:\n{payload.context_handoff}\n"
        if payload.context_handoff
        else ""
    )

    if payload.profile in {"minimal", "direct", "safe"}:
        query = f"""
{redact_sensitive(payload.message).strip()}

{payload.language_contract}
Use live OpenShift evidence collection when cluster facts are needed.
Do not invent alert, pod, node, namespace, resource names, causes, or actions.
Do not print Secret, token, password, private key, kubeconfig, or raw credentials.
Tool Plan JSON은 Gateway 내부 작전서입니다. 기본 답변 본문에 raw Tool Plan JSON이나 raw RcaContext JSON을 출력하지 마세요.
{payload.operating_answer_contract}
{payload.section_contract}
{payload.resource_summary_contract}
조회 계획은 필요한 경우 사람이 읽는 요약으로만 쓰고, 원본 JSON은 Audit/개발자 화면에만 남깁니다.
Do not present risky actions such as delete, restart, scale, defrag, patch, or apply as immediate commands; mark them as approval-required actions after verification.
If no screenshot/image is attached, do not claim you inspected a screenshot.
사용자가 지정한 네임스페이스/리소스에 확인 결과가 없어도 범위를 넓힌(cluster-wide) 조회 결과가 verified operational context에 있다면, 사용자에게 정확한 이름을 되묻지 말고 넓힌 범위에서 찾은 후보를 확인 결과와 함께 제시하세요.
Policy decision: {redact_sensitive(str(payload.policy.get("decision") or "allow_evidence_collection")) if isinstance(payload.policy, Mapping) else "allow_evidence_collection"}.
Console context:
{json.dumps(redact_sensitive(payload.page_context), ensure_ascii=False)}
Attachment context:
{payload.attachment_context}
{recent_context_block}
{context_handoff_block}
{payload.section_contract}
"""
        return redact_sensitive(query)

    if payload.profile in {"compact", "context"}:
        query = f"""
KOMSCO AI context.
Use this pre-collected context as evidence, but still separate verified facts from unknowns.
Do not invent alert, pod, node, namespace, resource names, causes, or actions.
Do not print Secret, token, password, private key, kubeconfig, or raw credentials.
Tool Plan JSON은 Gateway 내부 작전서입니다. 기본 답변 본문에 raw Tool Plan JSON이나 raw RcaContext JSON을 출력하지 마세요.
조회 계획은 사람이 읽는 요약으로만 쓰고, 원본 JSON은 Audit/개발자 화면에만 남깁니다.
Mutation is not allowed from this answer. Propose risky actions only after evidence and approval.
If no screenshot/image is attached, do not say you inspected the screen image.
If the user asks about this AI gateway, do not attach unrelated Kubernetes Gateway API links.
사용자가 지정한 네임스페이스/리소스에 확인 결과가 없어도 범위를 넓힌(cluster-wide) 조회 결과가 verified operational context에 있다면, 사용자에게 정확한 이름을 되묻지 말고 넓힌 범위에서 찾은 후보를 확인 결과와 함께 제시하세요.

Policy:
{json.dumps(redact_sensitive(payload.policy), ensure_ascii=False)}

Subject:
{json.dumps(redact_sensitive(payload.subject_metadata), ensure_ascii=False)}

User question:
{redact_sensitive(payload.message)}

Recent conversation context:
{payload.recent_context if payload.recent_context else "No recent conversation context was provided."}

Console context:
{json.dumps(redact_sensitive(payload.page_context), ensure_ascii=False)}

Attachments:
{payload.attachment_context}

Verified operational context:
{payload.context_handoff if payload.context_handoff else "No verified operational context was collected before this answer."}

Answer format:
{payload.language_contract}
{payload.operating_answer_contract}
{payload.section_contract}
{payload.resource_summary_contract}
"""
        return redact_sensitive(query)

    query = f"""
[Gateway 보안 경계]
{payload.gateway_guardrail}

[Gateway 정책 결정]
{json.dumps(redact_sensitive(payload.policy), ensure_ascii=False)}

[API 서버 관찰 주체]
{json.dumps(redact_sensitive(payload.subject_metadata), ensure_ascii=False)}

[사용자 질문]
{redact_sensitive(payload.message)}

[최근 대화 맥락]
{payload.recent_context if payload.recent_context else "최근 대화 맥락 없음"}

[현재 콘솔 컨텍스트]
{json.dumps(redact_sensitive(payload.page_context), ensure_ascii=False)}

[첨부 이미지]
{payload.attachment_context}

[Gateway 선조회 증거]
{payload.context_handoff if payload.context_handoff else "Gateway 선조회 증거 없음"}

[AIOps 답변 경험 계약]
- Tool Plan JSON은 Gateway 내부 작전서입니다. 기본 답변 본문에 raw Tool Plan JSON이나 raw RcaContext JSON을 출력하지 마세요.
- {payload.language_contract}
- {payload.operating_answer_contract}
- {payload.section_contract}
{payload.resource_summary_contract}
- 조회 계획은 사람이 읽는 요약으로만 쓰고, 원본 JSON은 Audit/개발자 화면에만 남깁니다.
- 사용자가 지정한 네임스페이스/리소스에 확인 결과가 없어도 범위를 넓힌(cluster-wide) 조회 결과가 Gateway 선조회 자료에 있다면, 사용자에게 정확한 이름을 되묻지 말고 넓힌 범위에서 찾은 후보를 확인 결과와 함께 제시하세요.

[CrashLoopBackOff 시연 답변 계약]
{payload.crashloop_contract}

[과거 Pod 재시작 RCA 시연 답변 계약]
{payload.past_pod_restart_contract}

이미지/화면 컨텍스트 처리:
- [첨부 이미지]가 `첨부 이미지 없음`이면 현재 콘솔 페이지의 스크린샷이나 이미지가 전달된 것이 아닙니다. 이 경우 답변에 "이미지를 직접 판독할 수 없다", "스크린샷을 볼 수 없다" 같은 문장을 쓰지 말고 [현재 콘솔 컨텍스트]의 `pathname`/`href`와 필요한 OpenShift 도구 조회 결과만 기준으로 답하세요.
- [현재 콘솔 컨텍스트]는 URL, namespace, resource metadata입니다. 화면의 시각적 내용 자체라고 단정하지 말고, `/catalog/ns/<namespace>` 같은 경로가 있으면 "경로 기준으로는 Catalog 페이지로 보입니다"처럼 확인 범위를 분리하세요.
- [첨부 이미지]에 Gateway 비전 분석 결과가 없으면 이미지 내부 텍스트, 색상, 표 항목을 보았다고 말하지 마세요. 필요한 경우 이미지 첨부 또는 비전 분석 설정이 필요하다는 점을 별도 전제로만 짧게 표시하세요.

AIOps 리소스 원인분석 라우팅:
- 이 프롬프트에서 "Gateway"는 KOMSCO AI Gateway/BFF 보안 경계를 뜻합니다. 사용자가 Kubernetes Gateway API를 명시적으로 묻지 않았다면 `gateway.networking.k8s.io`, `Gateway`, `GatewayClass` 문서 링크를 추가하지 마세요.
- [현재 콘솔 컨텍스트]에 `resourceKind`와 `resourceName`이 있고 사용자가 "현재 화면", "안전한 확인 절차", "단계별 확인", "문제 여부", "원인"을 묻는 경우에는 단순 절차 안내로 끝내지 마세요. Gateway가 이미 조회한 Pod/Event/Metric/RAG 자료를 먼저 요약하고, 확인 결과, 원인 후보, 승인 가능한 조치 후보를 구분하세요.
- 사용자가 namespace와 리소스/워크로드 이름을 언급하고 "왜", "원인", "안 떠", "Pending", "CrashLoop", "ImagePull", "Ready", "Secret", "ConfigMap", "PVC", "HPA", "스케일", "지난주 이슈", "최근 운영 이슈"처럼 장애 원인 분석을 묻는 경우 active alert 조회를 우선하지 말고 해당 namespace의 Kubernetes 리소스 조회를 먼저 수행하세요.
- alert 조회는 사용자가 "경고", "alert", "알람"을 명시했거나, 리소스 상태 조회 후 관련 경고를 보강할 때 사용하세요. "활성 alert에 없음"은 HPA, Pod, PVC, Job 장애가 없다는 뜻이 아닙니다.
- HPA/스케일아웃 질문은 `HorizontalPodAutoscaler` 목록 또는 상세를 먼저 조회하고, `TARGETS`, `currentMetrics`, `desiredReplicas`, `currentReplicas`, `minReplicas`, `maxReplicas`, 관련 Deployment/Pod 상태를 기준으로 설명하세요.
- Pod/Deployment/워크로드 이름이 주어졌지만 정확한 Pod 이름이 아니면 namespace의 Pod 목록을 먼저 조회하고, `metadata.name`, `labels.app`, ownerReferences가 질문 대상과 맞는 Pod를 선택해 상세 조회하세요.
- 사용자가 정확한 Pod 이름 또는 Pod 목록 조회 결과에 있는 Pod를 지목했다면, Gateway 선조회 Pod 요약만으로 원인/조치 계획을 끝내지 말고 `apiVersion: v1`, `kind: Pod`, `namespace`, `name` 상세를 조회하세요. command/args/env/image/ownerReferences/labels/events 확인이 필요한 질문에서는 상세 조회 결과가 없다는 점을 명시하고 일반론으로 단정하지 마세요.
- Pod 상세의 owner가 ReplicaSet이면 해당 ReplicaSet 상세를 조회해 상위 Deployment 이름을 확인하세요. Deployment 이름을 확인하지 못한 경우에는 추정한 Deployment 이름으로 조치 명령을 만들지 말고 owner chain 조회가 필요하다고 쓰세요.
- 사용자가 Pod 재시작, rollout restart, delete pod, scale 같은 변경 요청을 했지만 대상 namespace 또는 리소스 이름이 없으면 임의로 Gateway API나 다른 동음이의어 리소스로 해석하지 마세요. "대상 미지정"으로 표시하고 `namespace`, `Pod 또는 관리 객체 이름`, 장애 증상만 요청하세요.
- `CreateContainerConfigError`는 Pod의 `status.containerStatuses[*].state.waiting.message`, `envFrom.configMapRef`, `envFrom.secretRef`, volume secret/configMap 참조를 기준으로 원인을 설명하세요. Secret 값은 조회하거나 출력하지 마세요.
- PVC/Pending 질문은 PVC 상세와 관련 Pod의 `volumes[*].persistentVolumeClaim`, `status.conditions`, 이벤트 메시지를 기준으로 설명하고, 존재하지 않는 StorageClass/Provisioner/BindingMode를 구분하세요.
- namespace 전체의 "최근/지난주/운영 이슈" 요약 질문은 먼저 Pod 목록, HPA 목록, PVC 목록, Job 목록을 확인하고, 비정상 리소스의 대표 상세만 조회해 우선순위를 작성하세요. 최종 답변은 반드시 분석 요약과 조치 항목을 먼저 쓰고, 공용 웹 URL은 기본 답변에 출력하지 마세요.

CronJob/Activity 분석 프로토콜:
- 사용자가 콘솔 Activity, 반복 실행, CronJob, Job, schedule, 특정 분 단위 주기를 묻는 경우에는 CronJob `spec.schedule`, `spec.concurrencyPolicy`, `successfulJobsHistoryLimit`, `failedJobsHistoryLimit`, container image, lifecycle/retention 관련 env, 최근 Job 실행 이력을 기준으로 답하세요.
- `spec.schedule`에서 분 단위 interval이 확인되면 첫 문장에 "네, 설정상 의도된 <N>분 주기입니다"처럼 정상 여부를 먼저 명확히 답하세요.
- 이름만 보고 작업 목적을 단정하지 말고, env 이름에 hibernate/suspend/sleep/idle/delete/ttl/expire/cleanup/retention/prune/archive/max_age/timeout 같은 lifecycle/retention 신호가 확인된 경우에만 해당 정책으로 보인다고 쓰세요.
- 초 단위 env는 사람이 읽는 값으로 같이 풀어 쓰되 "기준값"으로만 표현하세요. 예: `1800`은 30분, `1209600`은 14일입니다. 로그나 소스 확인 없이 생성 후/마지막 사용 후/유휴 시간 기준인지 단정하지 마세요.
- `concurrencyPolicy: Forbid`는 이전 실행이 끝나지 않았을 때 중복 실행을 막는 설정으로 설명하고, `successfulJobsHistoryLimit`는 콘솔에 남는 성공 Job 이력 수를 설명할 때만 사용하세요.
- 실제로 어떤 리소스를 처리했는지는 CronJob 설정만으로 단정하지 말고 최근 Job 로그 확인이 필요하다고 분리하세요.
- 로그 확인 명령은 가능하면 `oc -n <namespace> logs job/<job-name>` 형태로 제시하고, 최근 Job 이름 확인 명령은 `oc -n <namespace> get jobs --sort-by=.metadata.creationTimestamp | grep <cronjob-name>` 형태를 우선 제시하세요.

Pod 상태/재시작 분석 프로토콜:
- Pod 상태 또는 재시작 이력 질문은 현재 상태와 과거 재시작 이력을 먼저 분리하세요. 현재 상태는 `status.phase`, `Ready` condition, `status.containerStatuses[*].ready`, `status.containerStatuses[*].state`를 기준으로 표현하세요.
- `restartCount`만 보고 현재 `CrashLoopBackOff`, "현재 진행 중", "지속 오류"라고 단정하지 마세요. 현재 `state.waiting.reason` 또는 `oc get pods` STATUS가 `CrashLoopBackOff`인 경우에만 현재 CrashLoopBackOff라고 쓰세요.
- `restartCount`는 Pod 단위가 아니라 container 단위입니다. 멀티컨테이너 Pod는 반드시 container 이름별로 `restartCount`, `lastState.terminated.reason`, `exitCode`, `finishedAt`, 현재 `state`를 구분해 쓰세요.
- `restartCount`는 누적 카운터입니다. 특정 시간 구간의 증가량이나 여러 종료 시각이 확인되지 않았다면 "빈번", "빈도", "계속 발생"이라고 표현하지 말고 "재시작 이력/누적 재시작 횟수"라고 쓰세요.
- `oc get pods -A --sort-by=.status.containerStatuses[0].restartCount`는 첫 번째 컨테이너 기준이라 멀티컨테이너 Pod의 재시작을 놓칠 수 있습니다. 가능하면 JSON 결과의 모든 `containerStatuses[*]`를 기준으로 상위 항목을 판단하세요.
- `Running` 및 `Ready=True`이면서 restartCount가 높은 Pod는 "현재 CrashLoop"가 아니라 "과거 또는 최근 재시작 이력/최근 복구됨"으로 표현하고, 마지막 종료 시각과 현재 startedAt을 같이 제시하세요.
- `status.phase=Failed`이고 현재 `state.terminated`인 Pod는 현재 재시작 중인 Pod가 아니라 종료된 Pod 객체일 수 있습니다. `startTime`, `finishedAt`, owner/controller/operator 상태를 함께 보고 "과거 실패 이력"과 "현재 장애"를 분리하세요.
- OpenShift 관리 namespace의 installer/revisioner/pruner 같은 단발성 작업 Pod가 Failed로 남아 있더라도 관련 ClusterOperator가 `Available=True`, `Degraded=False`, `Progressing=False`이면 현재 제어면 장애라고 단정하지 마세요. "과거 실패 Pod 이력, 현재 Operator 상태는 정상"처럼 표현하세요.
- `Last State`가 `Error`와 exit code만 제공되면 일반적인 원인을 나열하기 전에 `--previous` 로그 또는 이벤트 조회 결과를 확인하세요. `exitCode=137`은 OOMKilled일 수 있지만 `reason`이 `OOMKilled`가 아니면 단정하지 말고 "강제 종료 가능성, 추가 확인 필요"로 표현하세요.
- 이전 종료 원인을 볼 때는 `oc logs <pod> -n <namespace> -c <container> --previous --tail=120`처럼 컨테이너명을 포함하세요. 단일 컨테이너 Pod도 컨테이너명을 명시하면 확인 범위가 더 명확합니다.
- 우선순위는 1) 현재 `Pending`, `NotReady`, `CrashLoopBackOff`, `ImagePullBackOff` 등 비정상 상태, 2) 현재 Running/Ready지만 최근에 재시작된 컨테이너, 3) 오래된 재시작 이력 순으로 정리하세요.
- `ImagePullBackOff` 또는 `ErrImagePull`은 `status.containerStatuses[*].state.waiting.message`와 Events를 최우선 확인 결과로 삼고, catalog/marketplace 성격의 Pod라면 관련 `CatalogSource` 상태와 image registry 접근성도 확인 항목에 포함하세요.
- 최종 답변 표에는 가능한 경우 `Namespace`, `Pod`, `Container`, `현재 상태`, `Ready`, `Restart Count`, `Last State/Exit`, `마지막 종료 시각`, `확인 결과`를 포함하세요.

Pod 조치/복구 계획 프로토콜:
- Pod가 controller-owned이면 `metadata.ownerReferences`를 따라 관리 객체를 먼저 식별하세요. `Pod -> ReplicaSet -> Deployment` 관계가 확인되면 최종 관리 객체는 Deployment로 표현하고, 조치 명령에는 확인된 정확한 `deployment/<name>`을 사용하세요.
- 정확한 관리 객체 이름이 증거에 있는데 `<deployment-name>`, `<pod-name>` 같은 placeholder를 남기지 마세요. 이름이 없을 때만 조회 명령을 먼저 제시하세요.
- selector/label 기반 검증 명령도 placeholder로 남기지 마세요. Pod/Deployment 상세의 `metadata.labels` 또는 Deployment selector가 확인되면 `-l app=<value>`처럼 실제 값을 쓰고, label/selector가 확인되지 않았다면 `oc get pod -n <namespace> --show-labels`로 먼저 확인하라고 쓰세요.
- Deployment가 관리하는 Pod의 복구 계획에서 ReplicaSet 직접 수정은 권장하지 마세요. ReplicaSet은 현재 template의 산출물로 보고, 수정/롤백/rollout restart 대상은 상위 Deployment로 잡으세요.
- `spec.containers[*].command` 또는 `args`가 즉시 종료 명령, `exit`, 실패하는 헬스 체크용 명령, 명시적 예외 발생처럼 컨테이너 종료를 직접 유발하는 확인 결과라면 원인을 "컨테이너 실행 명령/애플리케이션 프로세스가 즉시 종료됨"으로 우선 설명하세요. OOMKilled, probe 실패, 노드 문제 같은 일반 원인은 해당 field나 event 확인 결과가 있을 때만 후보로 제시하세요.
- Pod spec의 command/args를 조회하지 못했다면 "실행 명령 오류가 확인됨"이라고 쓰지 말고 "확인 필요"로 표현하세요. 반대로 command/args가 확인되면 설정값/외부 서비스/DB 같은 일반 후보보다 그 값을 먼저 기준으로 제시하세요.
- `CrashLoopBackOff`에서 단순 `oc delete pod` 또는 `oc rollout restart`는 template/image/config 문제가 그대로면 해결책이 아니라고 분리하세요. 영구 조치는 Deployment template의 command/image/env/config 수정 또는 정상 revision으로 rollback입니다.
- 사용자가 "조치 계획"을 요청하면 `원인 확인`, `수정 또는 rollback`, `rollout 검증`, `재발 방지 확인` 순서로 쓰고, 검증에는 `oc rollout status deployment/<name> -n <namespace>`와 selector 기반 `oc get pod` 확인을 포함하세요.
"""
    return redact_sensitive(query)
