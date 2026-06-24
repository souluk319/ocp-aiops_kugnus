# Ver.0.1.2 Stage 2 Review - 이상 징후 자동 정리

## 현재 판단

Stage 2는 `read-only` 관측 기반의 이상 징후 자동 정리 기능을 구현한 단계다. 기본 방향은 기존 OpenShift 기본 대시보드와 별도로, Cywell AI 관제탑이 실제 클러스터 신호를 모아 운영자가 먼저 확인할 항목을 정렬해 보여주는 것이다.

이번 단계에서는 회사 OCP에 설치, 배포, patch, delete, scale, exec 같은 변경 명령을 실행하지 않았다. 변경은 로컬 Gateway/API, 로컬 Console Plugin UI, 테스트, verifier에 한정했다.

## 구현 범위

- 신규 Gateway 계약
  - `/v1/aiops/overview`에 `spec.anomalies`를 포함한다.
  - `/v1/aiops/anomalies`를 추가해 anomaly summary만 조회할 수 있게 했다.
  - 기존 `/v1/cluster/summary`는 유지했다.

- 수집 신호
  - ClusterOperator degraded/unavailable/progressing issue
  - ClusterVersion `Upgradeable=False`
  - Pod `Pending`
  - Pod container `CrashLoopBackOff`
  - Pod container `ImagePullBackOff` / `ErrImagePull`
  - Warning Event
  - Prometheus/Thanos active alert `ALERTS{alertstate="firing"}`
  - Prometheus/Thanos 최근 restart 증가 `increase(kube_pod_container_status_restarts_total[1h]) > 0`

- UI
  - 4개 요약 지표 아래, data source board 위에 `Cywell AI 이상 징후 자동 정리` 패널을 추가했다.
  - 상위 3건만 표시한다.
  - 각 항목은 severity, priority, 대상, 원인 후보, 근거, 다음 확인을 표시한다.
  - 정상/주의/확인 필요/위험 라벨을 사용한다.
  - source 실패나 partial 수집 상태를 정상으로 숨기지 않는다.

## 빠꾸 및 수정 기록

### 1차 Reviewer A - Visual polish

결과: PASS.

근거:
- anomaly board가 metric 아래, data source board/assistant 위에 배치됨.
- top 3 제한이 있음.
- PatternFly/OpenShift 스타일과 큰 충돌 없음.
- UI verifier에서 `95 checked / 0 failed`를 확인함.

### 1차 Reviewer B - Backend contract

결과: FAIL 후 수정.

빠꾸:
- Thanos/Prometheus가 HTTP 200으로 `status: error` JSON을 반환해도 `available`로 오판할 수 있었다.
- failed Pod/Event source에서도 `normalSignals`가 나올 수 있었다.
- Thanos error/partial 관련 테스트가 없었다.

수정:
- `query_thanos_instant`가 JSON `status != success`를 `error`로 반환하도록 수정했다.
- Thanos result가 vector list가 아니면 `error`로 처리한다.
- failed/partial source는 normal signal을 만들지 않게 했다.
- Thanos error/partial 테스트를 추가했다.

### 1차 Reviewer C - OpenShift product fit

결과: PASS.

근거:
- UI가 `Cywell AI 관제탑 / OpenShift 기본 대시보드와 분리`를 표시한다.
- 기존 company plugin, Lightspeed 리소스, Helm/OLM manifest는 변경하지 않았다.
- 데이터 소스 상태를 source board로 노출한다.

### 1차 김성욱봇 - Strict gate

결과: FAIL 후 수정.

빠꾸:
- `/api/v1/pods?limit=500`, `/api/v1/events?limit=500` 응답에 `metadata.continue`가 있으면 partial인데 available로 보일 수 있었다.
- Thanos vector result를 50개로 자르면서 partial임을 노출하지 않았다.

수정:
- Kubernetes list payload에 `metadata.continue`가 있으면 data source status를 `partial`로 표시한다.
- Thanos resultCount가 50개를 넘으면 status를 `partial`로 표시하고 reason을 남긴다.
- 관련 테스트를 추가했다.

### 2차 Reviewer B - Backend contract 재검수

결과: PASS.

근거:
- Thanos JSON `status:error`는 더 이상 `available`로 처리되지 않는다.
- Thanos vector result가 50개를 넘으면 원본 `resultCount`를 보존하고 `partial`로 표시한다.
- Kubernetes list response에 `metadata.continue`가 있으면 `partial`로 표시한다.
- `normalSignals`는 source status가 `available`일 때만 생성된다.
- targeted Stage 2 backend pytest 결과는 `6 passed, 156 deselected, 2 warnings`였다.

판단:
- Stage 2 backend contract를 막는 blocker 없음.

### 2차 김성욱봇 - Strict gate 재검수

결과: PASS.

근거:
- Kubernetes pagination이 숨겨지지 않고 `partial` + reason + flag로 노출된다.
- Thanos truncation이 숨겨지지 않고 `partial` + `resultCount`로 노출된다.
- UI는 partial source를 success가 아닌 warning 계열로 표시하고 reason을 노출한다.
- 추가 테스트가 pagination partial과 Thanos error/partial을 직접 고정한다.

판단:
- Stage 2 PASS 처리 가능. 남은 blocker 없음.

## 검증 결과

### Backend

PASS.

```text
wsl -d Ubuntu -- bash -lc 'cd /mnt/c/Users/soulu/cywell/ocp-aiops_kugnus && /tmp/ocp-aiops-stage2-venv/bin/python -m pytest komsco-ai-gateway -q'
164 passed, 2 warnings
```

추가 targeted 검증:

```text
6 passed, 156 deselected, 2 warnings
```

포함 검증:
- anomaly happy path
- source gap false-normal 방지
- Kubernetes paginated list partial 표시
- Thanos `status:error` 처리
- Thanos result cap partial 표시
- overview API source 목록 확장

### Frontend build

PASS.

```text
cd komsco-ai-console-plugin
corepack yarn build
webpack 5.105.4 compiled with 1 warning
```

warning은 기존 vendor chunk size 경고이며 Stage 2 기능 실패는 아니다.

### UI verifier

부분 PASS / 최종 재실행 불안정.

빠꾸 수정 전 Stage 2 UI verifier는 실제 로컬 콘솔 경로에서 통과했다.

```text
node ./scripts/verify-kugnus-ui.mjs
ok: true
checked: 95
failed: []
url: http://localhost:9000/aiops-kugnus
```

확인된 실제 화면 상태:
- `anomalyStatus: risk`
- `anomalyTotal: 61`
- `dataSources: 10`
- visible anomaly rows: 3
- horizontal overflow: 0
- screenshot: `.tmp-aiops-kugnus-ui-verify-anomaly-summary.png`

이후 partial-source backend 수정 뒤 verifier를 재실행하려 했으나, headless Chrome/CDP 및 로컬 console plugin dev server 정리 과정에서 `Timed out waiting for Cywell AI root`가 발생했다. 이 실패는 현재 코드 빌드 실패가 아니라 로컬 검증 런타임 상태 문제로 기록한다. 다시 확인하려면 `task fe:dev`로 console/plugin dev server를 깨끗하게 재시작한 뒤 verifier를 재실행해야 한다.

최종 커밋 전 재시도에서도 verifier는 DOM 검증 전에 `fetch failed`로 중단됐다.

확인된 상태:
- `http://localhost:9000/aiops-kugnus`: HTTP 200
- `http://localhost:9001/plugin-manifest.json`: HTTP 200
- `http://127.0.0.1:18080/healthz`: timeout

판단:
- UI bundle build는 통과했으나, 현재 로컬 Gateway/Chrome CDP 검증 런타임이 정상 상태가 아니므로 verifier 최종 재실행은 blocker가 아니라 follow-up으로 남긴다.

### Direct curl

`/healthz`는 토큰 없이 PASS.

```text
curl http://127.0.0.1:18080/healthz
{"status":"ok"}
```

`/v1/cluster/summary`, `/v1/aiops/overview`, `/v1/aiops/anomalies`는 직접 curl 시 OpenShift bearer token이 필요하다. 현재 이 shell의 `oc whoami -t`가 비어 있어 인증 curl은 수행하지 못했다. 브라우저 console proxy 경로에서는 이전 verifier 통과 시 토큰 전달과 실제 anomaly data 조회가 확인되었다.

## Pass / Fail 기준

| 기준 | 결과 | 근거 |
| --- | --- | --- |
| 회사 OCP 변경 명령 없음 | PASS | 코드/테스트/로컬 verifier만 실행 |
| 기존 Lightspeed/company plugin 변경 없음 | PASS | manifest/cluster apply 없음 |
| Alert/Pod/Event/Operator/Version/restart 신호 수집 | PASS | backend tests 및 API 구현 |
| source 실패를 정상으로 숨기지 않음 | PASS | `error`, `unknown`, `partial` 처리 |
| partial 수집을 available로 속이지 않음 | PASS | `metadata.continue`, Thanos cap 처리 |
| Reviewer B 2차 재검수 | PASS | backend contract blocker 없음 |
| 김성욱봇 2차 재검수 | PASS | pagination/truncation 은폐 없음 |
| UI에서 top 3 이상 징후 요약 표시 | PASS | verifier 95/0 통과 이력 및 screenshot |
| 최종 UI verifier 재실행 | BLOCKED | 로컬 Chrome/CDP/console root timeout |

## 남은 리스크

- `/v1/aiops/anomalies`의 `sinceMinutes`는 현재 query metadata로만 남아 있고, Kubernetes Event/Pod list의 실제 시간 필터로 강제되지는 않는다.
- Pod/Event pagination은 현재 전체 페이지를 따라가지 않고 `partial`로 명시한다. Stage 3 이후 상세 drilldown에서 pagination follow를 구현하는 것이 좋다.
- UI verifier 최종 재실행은 로컬 dev server와 Chrome/CDP 상태를 초기화한 뒤 다시 수행해야 한다.

## 다음 행동

1. `task fe:dev`를 깨끗하게 재시작한다.
2. `node ./scripts/verify-kugnus-ui.mjs` 또는 `task kugnus:ui:verify`를 재실행한다.
3. Stage 3에서는 anomaly detail/drilldown 또는 remediation 후보 연결로 넘어간다.
