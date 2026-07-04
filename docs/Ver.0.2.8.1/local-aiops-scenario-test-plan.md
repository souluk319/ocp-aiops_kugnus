# v0.2.8.1 Local AIOps Scenario Test Plan

이 문서는 회사 OKD를 변경하지 않고 로컬 서버에서만 AIOps 기능을 검증하기 위한 테스트코스이다.

목표는 챗봇이 운영 상황을 설명하는 수준을 넘어서, 로컬 simulator 안에서 Evidence, RCA, Action Plan, Approval, ExecutionRecord 흐름을 제품처럼 보여주는지 확인하는 것이다.

## Scope

이번 범위는 로컬 한정이다.

- Console Plugin: `http://localhost:9000/dashboards/aiops`
- Standalone Portal: `http://localhost:5174/dashboards/aiops`
- Gateway API는 브라우저 verifier가 CDP network intercept로 local fixture 응답을 제공한다.
- 실제 `oc apply`, `oc create`, `oc delete`, `oc patch`, `oc scale`은 실행하지 않는다.
- 회사 OKD 격리 namespace 테스트는 다음 단계에서 별도 계획으로 진행한다.

## Completion Criteria

| 항목 | Pass |
| --- | --- |
| 로컬 simulator | Alert, Pod, Deployment, Metric, Runbook, ActionProposal, SealedActionPlan, ApprovalDecision, ExecutionRecord를 상태ful하게 제공한다. |
| 회사 OKD mutation | 자동 report에 `companyMutationExecuted=false`와 mutation command count `0`이 남는다. |
| 10개 시나리오 | 브라우저 자동 조작으로 10개 모두 pass한다. |
| Action Plan | 조치 요청 시 승인 가능한 Action Plan이 보이고, 승인/거절/실행 상태가 DOM과 simulator record에 반영된다. |
| 좌패널 | 대화별 하위 조치 목록이 보이고, 클릭/펼침 후에도 날짜별 대화 순서가 바뀌지 않는다. |
| 신뢰 UI | 응답 중 헤더 하단 light rail, 14px 이상 본문, 외곽 프레임 없는 챗봇 아이콘을 확인한다. |
| 수동 테스트 | 같은 10개 질문과 정상 화면 기준을 문서로 제공한다. |

## Simulator Contract

Verifier는 Chrome DevTools Protocol `Fetch` interception으로 local Gateway 응답을 만든다.

```text
브라우저 UI
-> /api/proxy/plugin/.../ai-gateway/v1/*
-> scripts/verify-v0281-local-aiops-scenarios.cjs local simulator
-> fixture records 반환
```

상태 전이는 simulator 안에서만 일어난다.

```text
ActionProposal
-> SealedActionPlan
-> ApprovalDecision approved/rejected
-> ExecutionRecord simulated
```

`Pod 3개 생성`도 실제 cluster 생성이 아니라 simulator 상태만 아래처럼 바뀐다.

```text
before approval: desired=0, current=0, ready=0/0
after approval + execution: desired=3, current=3, ready=3/3
```

## 10 Local Scenarios

### 1. 최근 OpenShift 경고 정리

- 질문: `최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.`
- 더미 상황: etcd fragmentation, appscan360 Pod NotReady, control-plane memory pressure.
- 기대 답변: 현재 판단, 영향 범위, 확인한 근거, 원인 후보, 추가 확인 분리.
- 기대 Action Plan: 없음.
- Pass: raw `Tool Plan`, `source:`, `score=`, `post_answer` 노출 없음.
- Fail: 조회 질문인데 승인/실행 버튼이 표시된다.

### 2. CrashLoopBackOff 조치 후보

- 질문: `CrashLoopBackOff 상태인 Pod를 안전하게 복구할 Action Plan을 만들어줘.`
- 더미 상황: `komsco-ai-local/aiops-scenario-crashloop` Pod restart 증가.
- 기대 답변: Pod 상태 근거, 원인 후보, 승인 가능한 Action Plan 1개.
- 기대 UI: `승인 요청` 또는 `승인 후 실행` 버튼.
- Fail: 중복 계획 버튼, 중복 승인 버튼, 실행 버튼이 동시에 난립한다.

### 3. ImagePullBackOff

- 질문: `ImagePullBackOff 경고를 확인하고 조치 후보를 알려줘.`
- 더미 상황: image pull secret 또는 image tag 확인 필요.
- 기대 답변: Events, image, registry secret 확인 우선.
- 기대 Action Plan: `근거 더 수집` 또는 image/secret 확인 계획만 허용.
- Fail: Pod eviction Action Plan이 생성된다.

### 4. Pod 3개 생성 요청

- 질문: `komsco-ai-local namespace에 테스트 Pod 3개 만들어줘.`
- 더미 상황: 로컬 simulator에서 테스트 Pod가 아직 없음.
- 기대 답변: namespace, 생성 수량 3, 예상 영향, 검증 방법 포함.
- 기대 Action Plan: 승인 가능한 create plan.
- Fail: 승인 전에 simulator state가 `current=3`으로 바뀐다.
- Pass: 승인 후 ExecutionRecord가 생기고 simulator state가 `desired=3`, `current=3`, `ready=3/3`이 된다.

### 5. Deployment scale 요청

- 질문: `aiops-local-worker Deployment를 3개로 늘려줘.`
- 더미 상황: 현재 1개, 목표 3개.
- 기대 Action Plan: gap이 있을 때만 scale plan 생성.
- Fail: 이미 3개인 상태에서 scale plan이 생성된다.

### 6. 읽기 전용 모드에서 조치 요청

- 질문: `이 문제를 바로 복구해줘.`
- 더미 상황: 조치 가능한 plan은 있지만 실행 모드는 읽기 전용.
- 기대 UI: 실행 버튼 없음.
- 기대 문구: `읽기 전용 모드라 조치 버튼은 숨기고 계획 상태만 보여줍니다.`
- Fail: 비활성 실행 버튼이 반복 노출된다.

### 7. 승인 거절 경로

- 질문: `이 Action Plan은 거절해줘.`
- 더미 상황: 승인 가능한 sealed plan 존재.
- 기대 UI: 거절 클릭 후 rejected 기록 표시.
- Fail: ExecutionRecord가 생성된다.

### 8. 승인 실행 경로

- 질문: `승인하고 실행까지 진행해줘.`
- 더미 상황: sealed plan 존재.
- 기대 UI: 승인 클릭 후 실행 버튼, 실행 클릭 후 simulated ExecutionRecord.
- 기대 record: `mutation simulated`, `verification passed`.

### 9. 좌패널 대화/조치 목록

- 질문: 기존 대화 목록 fixture 사용.
- 기대 UI:

```text
# 대화내용
  - 조치내용
  - 조치내용
# 대화내용
  - 조치내용
```

- Pass: 조치 클릭 시 해당 대화/Action Plan으로 이동한다.
- Fail: 클릭하거나 펼쳤을 때 날짜별 대화 순서가 바뀐다.

### 10. 응답 중 상태와 신뢰 UI

- 질문: `현재 화면 기준으로 안전하게 확인해줘.`
- 기대 UI: 응답 중 헤더 하단 light rail 애니메이션.
- 기대 스타일:
  - 중앙/메시지 챗봇 아이콘 외곽 프레임 없음.
  - 본문 폰트 14px 이상.
  - 주요 답변 카드가 한눈에 읽힌다.

## Automatic Test Command

```bash
node --check scripts/verify-v0281-local-aiops-scenarios.cjs
cd komsco-ai-console-plugin && ./node_modules/.bin/tsc --noEmit
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
node scripts/verify-v0281-local-aiops-scenarios.cjs \
  --runs 10 \
  --report docs/Ver.0.2.8.1/local-aiops-scenario-test-report.json
```

## Generated Evidence

Verifier 실행 후 아래 파일이 생성된다.

```text
docs/Ver.0.2.8.1/local-aiops-scenario-test-report.json
docs/Ver.0.2.8.1/local-aiops-screenshots/*.png
```

Report에는 아래 항목이 포함되어야 한다.

- scenario id
- question
- pass/fail
- DOM evidence
- simulator record counts
- screenshot path
- portal 5174 connection check
- `companyMutationExecuted=false`
- `mutationCommands=[]`

## Out Of Scope

- 회사 OKD namespace 생성/삭제.
- 실제 Pod 생성/scale/patch.
- Claude-authored scenario JSON 수정.
- 운영 DB schema 변경.
- production Gateway route 변경.
