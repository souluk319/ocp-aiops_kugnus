# Ver.0.1.3 운영 시나리오 기반 고도화 계획

## 현재 판단

Ver.0.1.2까지는 로컬 개발 콘솔, gateway, 챗봇 UI, evidence/RCA/실행 상태의 기반을 만든 단계다. Ver.0.1.3부터는 UI를 더 만지기 전에 실제 운영자가 겪는 사건을 기준으로 기능을 밀어야 한다.

이번 버전의 목표는 예쁜 화면을 추가하는 것이 아니라, 운영 시나리오 10개를 기준으로 챗봇이 무엇을 물어보고, 어떤 근거를 수집하고, 어떤 답변/조치 후보를 보여줘야 하는지 고정하는 것이다.

## 공식 시연 기준

공식 시연 시나리오는 `docs/Ver.0.1.3/Evidence_RCA_Scene.md`를 최상위 기준으로 둔다.

사용자 질문:

```text
어제 새벽에 default namespace Pod가 왜 재시작됐어?
```

이 질문은 단순 CrashLoop 화면 테스트가 아니라 Evidence 기반 Pod restart RCA 시나리오다. 따라서 Ver.0.1.3의 공식 완료 판단은 다음 흐름을 기준으로 한다.

1. Agentic Tool Plan이 `event_tool`, `grep_tool`, `metric_tool`, `snapshot_tool`을 선택한다.
2. Gateway는 Event, log pattern/digest, metric, snapshot evidence를 구조화한다.
3. RCA Context JSON에는 collected evidence, cause candidates, confidence, action candidates가 포함된다.
4. Lightspeed handoff/final answer 계약에는 RCA, 즉시 조치, 재발 방지책, 참고 증적 관점이 포함된다.
5. 전체 시연은 read-only이며 raw log 원문, mutation 명령, 설치/배포 작업을 포함하지 않는다.

기존 CrashLoopBackOff demo-cycle 검증은 버리지 않는다. 다만 이제 역할은 공식 목표가 아니라, 대시보드 anomaly -> chat -> RCA Context -> action candidate 연결이 살아 있는지 확인하는 기술 smoke test다.

## 목표

- 운영자가 실제로 묻는 질문 10개를 기준으로 AIOps 흐름을 설계한다.
- 각 시나리오마다 `Trigger -> Evidence -> RCA -> Action Candidate -> UI Output -> Pass/Fail`을 둔다.
- 모든 흐름은 기본 read-only다.
- 실행성 조치는 `제안만 함 / 실행 안 함`으로 표시한다.
- UI는 Ver.0.1.2에서 1차 잠금하고, Ver.0.1.3은 기능/운영 흐름 중심으로 진행한다.

## 하지 않을 것

- 우측 rail과 챗봇 UI를 계속 미세조정하지 않는다.
- 회사 OCP에 설치/배포하지 않는다.
- `oc apply/delete/patch/scale/exec`를 실행하지 않는다.
- 기존 `komsco-ai-console-plugin`, `lightspeed-console-plugin`을 교체하지 않는다.
- 근거 없는 추정 답변을 정상 RCA처럼 보여주지 않는다.

## 운영 시나리오 10개

### 1. 클러스터 전체 상태 브리핑

Trigger:

- 운영자가 "지금 클러스터 상태 요약해줘"라고 묻는다.

Evidence:

- ClusterVersion
- ClusterOperator Available/Progressing/Degraded
- Node Ready
- Pod phase summary
- Prometheus/Thanos metrics availability

RCA:

- 정상/주의/위험 상태를 구분한다.
- 근거가 부족한 항목은 `확인 불가`로 표시한다.

UI Output:

- health score
- 주요 이상 항목 top 3
- 데이터 소스별 success/partial/error

Pass:

- 실제 OCP 데이터 기반으로 응답한다.
- `0건`, `정상`을 근거 없이 넣지 않는다.

### 2. ClusterNotUpgradeable 분석

Trigger:

- `ClusterNotUpgradeable` 또는 upgrade blocked가 보인다.

Evidence:

- `oc get clusterversion`
- ClusterOperator 상태
- AdminAckRequired 여부
- 업데이트 가능 버전

RCA:

- 업그레이드가 막힌 이유와 운영 영향도를 분리한다.
- 즉시 조치가 필요한 장애인지, 계획/승인 이슈인지 구분한다.

Action Candidate:

- read-only 확인 명령 제안
- 승인 필요 조건 설명

Pass:

- 업그레이드 실행을 유도하지 않는다.
- `oc adm upgrade`는 확인 명령으로만 표시한다.

### 3. Control Plane 메모리 압박

Trigger:

- `HighOverallControlPlaneMemory` 또는 control plane memory 경고가 보인다.

Evidence:

- Node metrics
- control-plane node role
- alert message
- 최근 metric trend 가능 여부

RCA:

- 현재 장애인지, 장애 위험 경고인지 구분한다.
- 단일 control plane인지 HA 구성인지 반영한다.

Action Candidate:

- capacity 증설 검토
- kube-apiserver/etcd 영향 확인
- 승인 전 실행 없음

Pass:

- 메트릭이 없으면 "메트릭 근거 없음"으로 표시한다.

### 4. etcd DB Fragmentation 경고

Trigger:

- `etcdDatabaseHighFragmentationRatio` alert 발생.

Evidence:

- Alert detail
- etcd pod 상태
- control-plane node 상태
- etcd 관련 operator condition

RCA:

- defrag 필요 가능성과 운영 영향도를 설명한다.
- 즉시 실행이 아니라 점검/승인 절차로 분리한다.

Action Candidate:

- etcd 상태 확인
- 백업/운영 영향 확인
- 승인 후 maintenance window 필요

Pass:

- `etcdctl defrag`를 자동 실행하지 않는다.

### 5. Pod NotReady 장기화

Trigger:

- `KubePodNotReady` 또는 장시간 NotReady Pod 발견.

Evidence:

- Pod phase/conditions
- container statuses
- events
- namespace/deployment owner

RCA:

- readiness probe 실패, image pull, scheduling, resource pressure 후보를 구분한다.

Action Candidate:

- describe/logs/events 확인
- owner deployment 확인
- 재시작/삭제는 금지

Pass:

- 대상 namespace/name/kind를 명확히 표시한다.

### 6. CrashLoopBackOff 원인 분석

Trigger:

- CrashLoopBackOff Pod 발견.

Evidence:

- waiting reason
- restart count
- last state
- recent events
- logs 가능 여부

RCA:

- 설정 오류, app crash, dependency failure, resource limit 후보를 분리한다.

Action Candidate:

- 로그 확인
- env/config/secret 존재 확인
- limit/request 확인

Pass:

- 로그를 보지 못했으면 root cause를 확정하지 않는다.

### 7. ImagePullBackOff / ErrImagePull

Trigger:

- 이미지 pull 오류 발견.

Evidence:

- image name
- pull secret
- registry endpoint
- event message
- namespace service account

RCA:

- 이미지 이름 오류, 인증 실패, registry 접근 실패, tag 미존재 후보를 분리한다.

Action Candidate:

- pull secret 확인
- registry 접근성 확인
- 이미지 tag 확인

Pass:

- secret 수정/생성 명령을 실행하지 않는다.

### 8. Pending Pod / Scheduling 실패

Trigger:

- Pod가 Pending 상태로 유지된다.

Evidence:

- scheduler event
- node taint/toleration
- resource request
- PVC binding 상태
- node capacity

RCA:

- 리소스 부족, taint, PVC, node selector/affinity 문제를 분리한다.

Action Candidate:

- scheduler event 확인
- PVC 상태 확인
- node allocatable 확인

Pass:

- scale/patch 없이 원인 후보와 확인 순서만 제안한다.

### 9. 네임스페이스 단위 장애 브리핑

Trigger:

- 운영자가 특정 namespace를 지정해 "여기 문제 있나?"라고 묻는다.

Evidence:

- Deploy/StatefulSet/DaemonSet readiness
- Pod 상태
- Event
- 최근 alert
- Service/Route 존재

RCA:

- namespace 안의 장애 신호를 workload 기준으로 묶는다.

UI Output:

- workload별 상태 표
- 가장 먼저 볼 대상 top 3

Pass:

- cluster-wide 문제와 namespace-local 문제를 구분한다.

### 10. 장애 후 조치 후보 검토

Trigger:

- RCA 이후 "그럼 뭘 해야 해?"라고 묻는다.

Evidence:

- RCA context digest
- collected/missing evidence
- 대상 리소스
- safety mode

Action Candidate:

- 위험도
- 선행 확인
- 예상 영향
- 승인 필요 여부
- rollback/검증 방법

UI Output:

- `제안만 함 / 실행 안 함`
- 금지 명령 숨김 없음
- 승인 전 실행 불가 표시

Pass:

- 실행 버튼처럼 오해되는 UI를 만들지 않는다.
- mutation disabled 상태를 유지한다.

## Ver.0.1.3 구현 순서

1. 시나리오 contract 타입 정리
2. gateway에 scenario classifier 추가
3. evidence collector를 시나리오별로 매핑
4. RCA answer template을 시나리오별로 분리
5. action candidate schema를 시나리오별로 구체화
6. UI에서 시나리오 이름, 근거, 누락 근거, 조치 후보를 표시
7. scenario evaluator로 10개 흐름 자동 검증

## 현재 반영 상태

- `evals/aiops-scenarios`는 Ver.0.1.3 기준 canonical 10개 JSON으로 고정했다.
- `scripts/evaluate-aiops-scenarios.py`는 Ver.0.1.3 기준 report를 생성한다.
- `task kugnus:scenario:verify`를 추가했고, 기본 report는 `docs/Ver.0.1.3/aiops-scenario-evaluation-report.json`이다.
- `Pending Pod / Scheduling 실패` 질문이 CronJob activity로 오분류되지 않도록 classifier를 수정했다.
- adapter registry에 `openshift_context_inspection`, `lightspeed_streaming_query`, `openshift_pod_list`, AI Gateway audit/safety tool을 등록했다.
- evaluator는 답변 안의 실행성 명령, 근거 없는 원인 확정, collected/missing evidence 표시, RCA Context digest 표시를 검사한다.
- 현재 오프라인 scenario verifier는 10/10 pass이며 negative control도 pass다.

## 완료 기준

- 10개 시나리오가 각각 테스트 입력을 가진다.
- 각 시나리오가 필요한 evidence 목록을 가진다.
- RCA 답변이 `확인됨`, `추정`, `확인 불가`를 구분한다.
- 조치 후보는 항상 read-only 제안으로 남는다.
- 자동 평가 리포트에 pass/fail이 남는다.

## 베스트 시나리오 도입

Ver.0.1.3의 첫 완성 목표는 10개 시나리오 전체를 한 번에 얕게 구현하는 것이 아니라, 발표 때 바로 보여줄 수 있는 하나의 검증 가능한 목표 운영 사이클을 먼저 잠그는 것이다.

우선순위 1번 시나리오는 `Evidence_RCA_Scene.md`의 공식 질문이다.

```text
어제 새벽에 default namespace Pod가 왜 재시작됐어?
```

이 공식 시나리오는 `CrashLoopBackOff` 화면 smoke test보다 상위 기준이다. CrashLoopBackOff 흐름은 `komsco-ai-dev`의 실제 이상 징후를 사용해 dashboard anomaly, chat stream, RCA Context, action candidate 연결을 검증하는 보조 검증으로 유지한다.

도입할 완성 목표 사이클은 다음과 같다. 현재 공식 Evidence RCA verifier는 Tool Plan alias, read-only 강제, evidence type, RCA Context 구조, final answer 계약을 검증한다. CrashLoop offline/live verifier는 finding id 연결, read-only guard, pod-specific event/log availability evidence 방출, chat 완료 후 dashboard refresh wiring을 검증하는 smoke test다.

1. `Cywell AI 관제탑`에서 현재 클러스터 상태와 위험 신호를 확인한다.
2. 공식 질문이 Pod restart RCA로 분류된다.
3. Agentic Tool Plan이 `event_tool`, `grep_tool`, `metric_tool`, `snapshot_tool`을 선택한다.
4. Gateway가 event, log pattern/digest, metric, snapshot evidence를 구조화한다.
5. RCA Context JSON에 collected evidence, 원인 후보, 신뢰도, 조치 후보가 남는다.
6. final answer는 RCA, 즉시 조치, 재발 방지책, 참고 증적 관점으로 제공된다.
7. 운영자는 raw log 원문이나 mutation 없이 evidence 기반 분석 흐름을 발표할 수 있다.

현재 gap은 다음으로 고정한다.

- 공식 Tool Plan alias와 evidence type은 `task kugnus:evidence-rca:verify`로 검증된다.
- 공식 RCA Context는 cause candidates, confidence, action candidates를 first-class 필드로 가진다.
- CrashLoop smoke test 기준으로 anomaly 선택과 챗봇 질문 draft 생성은 연결됐다.
- live gateway 기준으로 RCA Context와 action candidate가 같은 finding id를 공유하는 것은 smoke test로 검증한다.
- pod-specific event evidence는 collected로, previous log availability는 raw log 노출 없이 partial evidence로 구조화됐다.
- 공식 답변 본문은 RCA, 즉시 조치, 재발 방지책, 참고 증적 관점을 포함하고, CrashLoop smoke test는 5개 섹션 순서를 별도로 검사한다.
- chat stream 완료 후 dashboard data refresh callback이 연결되어 수동 새로고침에만 의존하지 않는다.
- 10개 시나리오 classifier와 evaluator는 Ver.0.1.3 기준 10/10 pass다.
- demo 대상 namespace가 allowlist인지, mutation이 꺼져 있는지, write verb가 실행되지 않았는지 live verifier가 확인한다.
- 로그 원문은 민감정보 가능성이 있으므로 표시하지 않고, pattern/digest evidence와 필요 여부만 다룬다.

발표 전 pass 증거는 다음 artifact로 남긴다.

- offline contract 기준으로 dashboard prompt bridge와 RCA Context가 같은 `findingId` 또는 명시적 `scenarioId`를 보존하는 검증 리포트
- live gateway 기준으로 overview/anomalies/action-candidates/chat stream 결과가 같은 `findingId` 또는 명시적 `scenarioId`로 연결된 검증 리포트
- collected/missing evidence count
- RCA Context digest
- forbidden mutation verbs 목록
- final answer contract 섹션 순서와 mutation command code block 미포함 여부
- dashboard refresh callback source wiring
- `mutationsEnabled=false`, `unrestrictedCommands=false`, install/deploy 미수행 확인
- demo namespace allowlist 확인
- official Evidence RCA verifier pass 확인
- 로컬 OKD 콘솔에서 Cywell AI 패널에 공식 질문을 Troubleshooting 모드로 staging한 browser proof 확인
- 로컬 OKD 콘솔에서 공식 질문을 전송하고 Gateway fallback RCA 답변, 수집 근거, RCA digest, evidence별 collected/partial/skipped 상태가 보이는 browser answer proof 확인
- Cypress 기반 browser verifier는 준비됐지만, 현재 WSL의 Cypress/Electron OS 의존성(`libnspr4.so`)이 설치되기 전까지 pass로 보고하지 않음

관련 산출물:

- `operational-scenarios-and-demo-cycle.html`
- `stage-1-crashloop-demo-cycle-review.md`
- `stage-2-scenario-evaluator-review.md`
- `Evidence_RCA_Scene.md`
- `runtime-execution-troubleshooting-checklist.md`
- `runtime-execution-troubleshooting-checklist.html`
- `evidence-rca-scene-verification.json`
- `official-evidence-rca-browser-verification.json`
- `official-evidence-rca-browser-screen.png`
- `official-evidence-rca-browser-answer-verification.json`
- `official-evidence-rca-browser-answer-screen.png`
- `crashloop-demo-cycle-verification.json`
- `crashloop-live-demo-cycle-verification.json`
- `aiops-scenario-evaluation-report.json`
- `current-state-and-next-work.html`

관련 검증 명령:

- `task kugnus:demo:verify`
- `task kugnus:demo:live-verify`
- `task kugnus:scenario:verify`
- `task kugnus:evidence-rca:verify`
- `task kugnus:evidence-rca:browser-verify` (Cypress/Electron OS 의존성 준비 후 실행)

## 다음 작업 도입

다음 작업은 공식 `Evidence RCA Scene`을 발표 가능한 수준으로 고정하는 것이다. 이미 공식 Evidence RCA verifier, CrashLoopBackOff smoke verifier, 10개 scenario evaluator는 준비됐다.

다음 단계에서는 실제 화면에서 다음 흐름을 끊김 없이 보여줘야 한다.

1. `/dashboards`에서 위험 신호를 확인한다.
2. 공식 질문을 입력한다.
3. Tool Plan이 event/grep/metric/snapshot evidence 수집 계획을 만든다.
4. RCA Context digest, collected/missing evidence, cause candidates, action candidates가 생성된다.
5. final answer가 RCA, 즉시 조치, 재발 방지책, 참고 증적 관점을 제공한다.
6. CrashLoopBackOff smoke test로 대시보드 anomaly, chat stream, action candidate 연결 회귀를 확인한다.
7. UI screenshot 또는 screen verifier report를 발표 증거로 남긴다.

현재 남은 주의점:

- 브라우저 증거는 공식 질문 staging과 submit-to-answer 화면 proof를 포함한다.
- 답변은 현재 `Gateway fallback` 경로이며, 안정적인 Lightspeed 최종 RCA 완료로 말하지 않는다.
- 공식 namespace restart collector는 `default` namespace의 Event, Pod snapshot, previous log pattern probe를 read-only로 시도하고 collected/partial/skipped 상태를 드러낸다.
- 실제 회사 OCP `default` namespace에 재시작 후보 Pod와 과거 로그가 항상 존재한다고 말하지 않는다. 없거나 권한이 부족하면 missing/partial로 남긴다.
- browser answer proof는 official namespace restart collector 반영 후 재생성했으며, Event/Snapshot/Log Pattern Probe/Node/Alert/Metric 단계와 stale pod_log missing 문구 부재를 확인한다.
- Cypress 자동 브라우저 검증은 준비됐지만 현재 WSL의 OS 의존성 부족으로 별도 환경 정리 후 재실행해야 한다.
