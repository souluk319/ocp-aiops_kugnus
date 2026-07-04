# v0.2.8.1 Local AIOps Manual Test Guide

이 가이드는 자동 verifier가 사용하는 10개 로컬 시나리오를 사용자가 브라우저에서 직접 재현하기 위한 문서이다.

이번 테스트는 회사 OKD를 변경하지 않는다. 실행 성공은 실제 cluster mutation이 아니라 local simulator의 ExecutionRecord 성공을 의미한다.

## 준비

5174 standalone portal은 로컬 테스트에서 정적 포털 화면과 fixture `/v1/*` API를 같은 서버에서 제공한다.
회사 OKD를 건드리지 않고 로컬 테스트를 하려면 아래 단일 서버를 띄운다.

```bash
AIOPS_LOCAL_FIXTURE_HOST=0.0.0.0 \
AIOPS_LOCAL_FIXTURE_PORT=5174 \
AIOPS_LOCAL_SERVE_PORTAL=1 \
node scripts/serve-v0281-local-aiops-gateway.cjs
```

다른 터미널에서 Console Plugin을 빌드한다.

```bash
cd komsco-ai-console-plugin
node .yarn/releases/yarn-4.13.0.cjs build-dev
```

자동 fixture와 report를 만들려면 아래를 실행한다.

```bash
node scripts/verify-v0281-local-aiops-scenarios.cjs \
  --runs 10 \
  --report docs/Ver.0.2.8.1/local-aiops-scenario-test-report.json
```

정상 실행 후 확인 위치:

```text
Console Plugin: http://localhost:9000/dashboards/aiops
Standalone Portal: http://localhost:5174/dashboards/aiops
Fixture Gateway: http://localhost:5174/healthz
Report: docs/Ver.0.2.8.1/local-aiops-scenario-test-report.json
Screenshots: docs/Ver.0.2.8.1/local-aiops-screenshots/
```

## 공통 확인 기준

- 회사 OKD에 실제 생성/삭제/scale이 없어야 한다.
- 챗봇 기본 답변에 `Tool Plan`, `source:`, `score=`, `post_answer`가 보이면 실패이다.
- Action Plan은 조치 요청일 때만 보인다.
- 승인 전에는 실행 결과가 생기면 안 된다.
- 승인/실행 후에는 local simulator ExecutionRecord만 생긴다.
- 좌패널 대화 목록은 클릭해도 순서가 바뀌면 안 된다.

## 10개 수동 테스트 질문

### 1. 최근 OpenShift 경고 정리

입력:

```text
최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.
```

정상 화면:

- 현재 판단, 영향 범위, 확인한 근거, 원인 후보, 추가 확인이 보인다.
- 승인/실행 버튼은 없다.
- raw 내부 용어는 보이지 않는다.

### 2. CrashLoopBackOff 조치 후보

입력:

```text
CrashLoopBackOff 상태인 Pod를 안전하게 복구할 Action Plan을 만들어줘.
```

정상 화면:

- Pod 상태 근거와 원인 후보가 보인다.
- Action Plan 카드가 1개 보인다.
- `승인 요청` 또는 `승인 후 실행` 버튼이 보인다.

### 3. ImagePullBackOff

입력:

```text
ImagePullBackOff 경고를 확인하고 조치 후보를 알려줘.
```

정상 화면:

- Events, image tag, image pull secret 확인이 먼저 보인다.
- Pod eviction 조치가 보이면 실패이다.

### 4. Pod 3개 생성 요청

입력:

```text
komsco-ai-local namespace에 테스트 Pod 3개 만들어줘.
```

정상 화면:

- 생성 대상 namespace와 수량 3개가 보인다.
- 예상 영향과 검증 방법이 보인다.
- 승인 전에는 생성 완료로 표시되지 않는다.
- 승인/실행 후 report에서 simulator state가 `ready=3/3`로 바뀐다.

### 5. Deployment scale 요청

입력:

```text
aiops-local-worker Deployment를 3개로 늘려줘.
```

정상 화면:

- 현재 1개, 목표 3개, gap 2개가 보인다.
- gap이 있을 때만 Action Plan이 보인다.
- 이미 3개인 경우 조치 없음으로 판정한다.

### 6. 읽기 전용 모드에서 조치 요청

실행 모드를 `읽기 전용`으로 둔 뒤 입력:

```text
이 문제를 바로 복구해줘.
```

정상 화면:

- 실행 버튼이 없다.
- 읽기 전용 모드라 Action Plan 생성/실행은 실행 가능 모드가 필요하다는 안내가 1회만 보인다.

### 7. 승인 거절 경로

실행 모드를 `실행 가능`으로 바꾸고 입력:

```text
이 Action Plan은 거절해줘.
```

정상 화면:

- 거절 버튼을 누르면 rejected 기록이 보인다.
- ExecutionRecord가 생기면 실패이다.

### 8. 승인 실행 경로

실행 모드를 `실행 가능`으로 바꾸고 입력:

```text
승인하고 실행까지 진행해줘.
```

정상 화면:

- 승인 버튼을 누르면 실행 대기 상태가 된다.
- 실행 버튼을 누르면 simulated ExecutionRecord가 생긴다.
- 결과는 `mutation simulated`, `verification passed`로 표시된다.

### 9. 좌패널 대화/조치 목록

좌패널에서 지난 대화를 연다.

정상 화면:

```text
대화 제목
  조치 후보
  승인 가능한 계획
대화 제목
  실행 완료
```

- 조치 클릭 시 해당 대화로 이동한다.
- 클릭 후에도 대화 순서는 바뀌지 않는다.

### 10. 응답 중 상태와 신뢰 UI

입력:

```text
현재 화면 기준으로 안전하게 확인해줘.
```

정상 화면:

- 응답 중 헤더 하단에 빛이 좌우로 움직인다.
- 답변 완료 후 상태가 안정된다.
- 중앙/메시지 아이콘 외곽 프레임이 없다.
- 본문 폰트는 14px 이상으로 읽힌다.

## 실패 시 확인 위치

자동 report:

```bash
cat docs/Ver.0.2.8.1/local-aiops-scenario-test-report.json
```

스크린샷:

```bash
ls docs/Ver.0.2.8.1/local-aiops-screenshots/
```

브라우저 verifier 자체 문법:

```bash
node --check scripts/verify-v0281-local-aiops-scenarios.cjs
node --check scripts/serve-v0281-local-aiops-gateway.cjs
```

Console Plugin 타입:

```bash
cd komsco-ai-console-plugin
./node_modules/.bin/tsc --noEmit
```

## 수동 테스트 리셋

자동 verifier는 각 시나리오마다 active conversation과 simulator state를 다시 주입한다.

수동으로 상태가 꼬이면 아래 순서로 복구한다.

```bash
node scripts/verify-v0281-local-aiops-scenarios.cjs \
  --runs 10 \
  --report docs/Ver.0.2.8.1/local-aiops-scenario-test-report.json
```

그 다음 브라우저를 새로고침하고 `http://localhost:9000/dashboards/aiops`를 다시 연다.
