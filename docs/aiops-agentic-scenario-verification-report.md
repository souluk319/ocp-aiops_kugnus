# AIOps Agentic Multi-turn Scenario Verification Report

검증일: 2026-06-23 KST

## 목적

자연어 멀티턴 요청이 OpenShift AIOps 동작으로 이어지는지 검증했다. 특히 다음 조건을 확인했다.

- 직전 턴 맥락과 `진행해` 후속 명령을 결합해 실행한다.
- 장애 Pod 처리, Deployment scale/restart, rollback, HPA bounds, host diagnostics 흐름을 typed action 또는 안전한 증거 수집 경로로 분리한다.
- 실행 가능한 요청은 Gateway ActionProposal/SealedActionPlan/Approval/Action Executor 경로를 사용한다.
- 대상이 불명확한 변경 요청은 OLS 일반 분석으로 넘기지 않고 Gateway에서 중단한다.

## 구현 변경

- 자연어 action intent 확장
  - `rollback_deployment_to_revision`
  - `evict_one_unhealthy_controller_owned_pod`
  - `set_hpa_bounds`
- ActionPlan 생성 경로 일반화
  - 기존 Deployment 고정 조회에서 `apiVersion/kind` 기반 target lookup으로 변경
  - Deployment, Pod, HorizontalPodAutoscaler target 지원
- 한국어 mutation 분류 보강
  - `퇴거`, `교체`, `재생성` 계열 요청을 action proposal 경로로 분류
- 멀티턴 회귀 테스트 보강
  - 최근 사용자 요청 + `진행해` 후속 실행
  - 실행 가능한 action과 안전 중단/읽기 전용 증거 수집 10개 시나리오 매트릭스

## 샘플 상황 10개

| ID | 상황 | 요청 예 | 기대 동작 | 검증 근거 |
| :--- | :--- | :--- | :--- | :--- |
| S01 | 명시적 Deployment scale | `team-a 네임스페이스의 web-api 파드 4개로 올려줘` | `set_replicas_within_bounds` intent 생성 | `test_agentic_action_scenario_matrix_parses_typed_actions` |
| S02 | 멀티턴 후속 scale | 직전 요청 후 `진행해` | 최근 user 요청 복원 후 scale action 실행 | unit test + live `/tmp/aiops-s01-contextual-scale.sse` |
| S03 | Deployment 화면 기준 restart | Deployment 상세 화면에서 `재시작해줘` | pageContext의 Deployment를 `rollout_restart_deployment`로 실행 | unit test + live `/tmp/aiops-s02-rollout-restart.sse` |
| S04 | bad rollout rollback | `deployment/web-api revision 2로 롤백해줘` | `rollback_deployment_to_revision` intent 생성 | `test_parse_natural_action_intent_accepts_agentic_action_variants` |
| S05 | 장애 Pod 교체 | `pod/web-api-abc 교체해줘` | controller-owned unhealthy Pod eviction action 생성 | unit test + live `/tmp/aiops-s03-pod-eviction.sse` |
| S06 | HPA bounds 변경 | `hpa/web-hpa 최소 2 최대 8로 변경해줘` | `set_hpa_bounds` intent 및 HPA API target plan 생성 | `test_create_natural_action_plan_uses_intent_target_kind` |
| S07 | 대상 불명확한 변경 요청 | `파드 하나 재시작해줘` | 실행하지 않고 대상 리소스 부족으로 Gateway 중단 | `test_agentic_safety_and_evidence_scenario_matrix_covers_non_mutating_paths` |
| S08 | Pod 리스트 조회 | `team-a 네임스페이스 파드 리스트 조회해줘` | mutation 아님, read-only pod list 경로 | `is_pod_list_request` matrix assertion |
| S09 | CrashLoopBackOff 원인 분석 | `CrashLoopBackOff 파드 원인 분석해줘` | mutation 아님, Pod status evidence 수집 경로 | `should_collect_pod_status_evidence` matrix assertion |
| S10 | 노드 host OS read-only 진단 | node `worker-a` 진단 요청 | DiagnosticRequestCandidate digest 생성, host collector allow-list 사용 | diagnostic candidate matrix assertion |

## 라이브 검증 결과

대상 클러스터 namespace: `komsco-ai-dev`

### L01. 멀티턴 scale 실행

요청:

```json
{
  "message": "진행해",
  "pageContext": {"aiopsExecutionMode": "unrestricted"},
  "recentMessages": [
    {"role": "user", "content": "komsco-ai-dev 네임스페이스의 aiops-two-pod-exec 파드 3개로 올려줘"}
  ]
}
```

결과:

- SSE event: `natural_action_followup`
- Action: `set_replicas_within_bounds`
- Mutation: `mutation_succeeded`
- Verification: `verified / scale_spec_matches`
- observedReplicas: `3`

### L02. Deployment rollout restart 실행

요청:

```text
komsco-ai-dev:aiops-two-pod-exec 재시작해줘
```

결과:

- SSE event: `natural_action_execute`
- Action: `rollout_restart_deployment`
- Mutation: `mutation_succeeded`
- Verification: `verified / restart_annotation_observed`
- `oc rollout status deployment/aiops-two-pod-exec -n komsco-ai-dev --timeout=90s` 성공
- 새 Pod hash `9f57c7f74` 3개 생성 확인
- 이전 Pod hash `686fdb7784` 3개는 `deletionTimestamp` 확인

### L03. CrashLoopBackOff Pod eviction 실행

요청:

```text
komsco-ai-dev 네임스페이스의 pod/aiops-scenario-1-crashloop-7448bf8897-s2tg8 교체해줘
```

결과:

- SSE event: `natural_action_execute`
- Action: `evict_one_unhealthy_controller_owned_pod`
- Mutation: `mutation_succeeded`
- HTTP status: `201`
- Verification: `verified / target_pod_deleting`
- replacement Pod: `aiops-scenario-1-crashloop-7448bf8897-57pjz`
- replacement 상태: `CrashLoopBackOff`, restart count `1`

참고: replacement Pod도 CrashLoopBackOff인 것은 의도된 테스트 deployment template이 계속 crash하도록 구성되어 있기 때문이다. AIOps 조치는 단일 장애 Pod 교체를 수행했으며, 영구 해결은 Deployment template 수정 또는 rollback 대상으로 분리된다.

## 자동 테스트

실행한 타겟 테스트:

```bash
python3 -m pytest -q komsco-ai-gateway/tests/test_health.py -k "agentic_action_scenario_matrix or agentic_safety_and_evidence or agentic_action_variants or create_natural_action_plan_uses_intent_target_kind"
```

결과:

```text
12 passed, 104 deselected
```

전체 회귀 테스트:

```bash
python3 -m pytest -q komsco-ai-gateway/tests/test_health.py
```

결과:

```text
116 passed, 2 warnings
```

프론트 빌드:

```bash
yarn build-dev
```

결과:

```text
webpack 5.105.4 compiled successfully
```

## 판정

완료로 판정한 범위:

- 멀티턴 `진행해`가 직전 사용자 변경 요청을 복원해 실행한다.
- Deployment scale/restart는 라이브 클러스터에서 Action Executor까지 실행됐다.
- 장애 Pod eviction은 라이브 클러스터에서 Action Executor까지 실행됐다.
- rollback/HPA bounds는 자연어 intent 및 target kind별 ActionPlan 생성 경로가 자동 테스트로 검증됐다.
- 대상 불명확한 변경 요청은 OLS 분석으로 빠지지 않고 Gateway에서 안전 중단한다.
- Pod 목록, CrashLoopBackOff RCA, host diagnostics는 mutation이 아니라 read-only evidence/diagnostic 경로로 분리된다.

남은 운영 확장 후보:

- rollback/HPA bounds도 전용 라이브 샘플 리소스를 만들어 실행까지 검증
- HPA가 붙은 Deployment scale 요청에서 `hpa_review_required`를 UI에 더 명확히 표시
- Pod eviction 후 replacement가 동일 CrashLoopBackOff면 자동으로 Deployment rollback/runbook 제안을 이어가는 chained remediation
