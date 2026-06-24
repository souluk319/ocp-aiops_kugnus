# Ver.0.1.2 Stage 3-2 Review - RCA Signal Preflight 연결

## 현재 판단

Stage 3-2는 Stage 3-1에서 `planned/missing`으로 남겨둔 Node, Active Alert, Restart Metric RCA 근거를 실제 read-only preflight 수집 경로에 연결하는 단계다.

이번 작업은 회사 OCP에 설치/배포/변경을 하지 않는다. Gateway가 사용자 토큰으로 조회 가능한 범위에서 다음 데이터를 읽고, 성공/부분수집/실패를 `RcaContext`와 evidence footer에서 구분하도록 고정했다.

- Node: `/api/v1/nodes`, `/apis/metrics.k8s.io/v1beta1/nodes`
- Alert: Thanos query `ALERTS{alertstate="firing"}`
- Metric: Thanos query `increase(kube_pod_container_status_restarts_total[1h]) > 0`

## 구현 범위

- OpenShift adapter 계약 갱신
  - `openshift_node_status_lookup`
  - `openshift_alert_lookup`
  - `openshift_metric_query`
  - 위 세 capability를 `available`로 전환했다.

- RCA evidence 상태 계약 강화
  - `collectedRefs`, `partialRefs`, `failedRefs`, `missing`을 분리했다.
  - `partialCount`를 summary에 추가했다.
  - step status에 `partial`을 추가했다.
  - 실제 수집/부분수집된 evidence type은 stale `missing_evidence`에서 제거한다.

- evidence type 추론 강화
  - `evidenceType` / `evidence_type`을 우선 사용한다.
  - `node_status_evidence`, `active_alerts_evidence`, `restart_metric_evidence`가 각각 `node`, `alert`, `metric`으로 매칭된다.

- read-only preflight collector 추가
  - `collect_node_status_rca_evidence`
  - `collect_active_alerts_rca_evidence`
  - `collect_restart_metric_rca_evidence`
  - 각 collector는 실패해도 stream을 죽이지 않고 `status`, `missingReason`, `sourcePath`를 남긴다.

- evidence reference 보존 강화
  - `build_evidence_reference_events`가 `eventStatus`, `evidenceType`, `sourcePath`, `missingReason`을 보존한다.
  - `RcaContext.analysisPlan.evidenceCollectionSteps`가 실제 evidence ref와 정확히 맞물린다.

- 기존 preflight 문구 보정
  - Pod/CronJob 수집 실패 또는 skip 상태가 "수집 완료"처럼 보이지 않도록 상태별 summary를 사용한다.
  - preflight 예외는 `safe_exception_text`로 redaction한다.

- UI verifier 갱신
  - evidence footer count를 Stage 3-1의 고정값 `1/1`로 보지 않는다.
  - Stage 3-2부터는 수집 refs가 늘어날 수 있으므로 `수집 >= 1`, `추가 확인 >= 0`, overflow 없음 기준으로 본다.

## 병렬 검수 결과

### Reviewer A - 제품/운영성

결과: PASS 조건 고정.

빠꾸 기준:
- Alert/Node/Metrics가 계획에만 있으면 fail.
- 운영자가 원인 후보와 다음 확인 행동을 판단할 수 없으면 fail.
- 관련 active alert가 없으면 "없음"으로 표시해야지, 정상으로 단정하면 fail.

반영:
- 세 signal 모두 실제 preflight collector를 붙였다.
- 관련 Alert가 없으면 non-Watchdog active alert 없음으로 표시한다.
- Metric/Thanos 실패는 `확인 불가`로 남도록 event status를 유지한다.

### Reviewer B - 백엔드/안전성

결과: 1차 FAIL 후 보강.

빠꾸 기준:
- `partial`이 collected/failed 어느 쪽에도 제대로 표현되지 않으면 fail.
- `node`/`alert` evidence가 `openshift`로 뭉개지면 fail.
- 실제 수집됐는데 정적 missing reason이 계속 남으면 fail.
- preflight 예외에 token/Bearer가 섞이면 fail.

반영:
- `partialRefs`, `partialCount`, step status `partial`을 추가했다.
- `evidenceType` 우선 매칭을 추가했다.
- covered type은 stale missing에서 제거했다.
- Pod/CronJob/Node/Alert/Metric preflight 예외를 redaction 경로로 통일했다.

### Reviewer C - UI/Trace

결과: PASS 조건 갱신.

빠꾸 기준:
- footer와 RCA Context JSON의 digest/runId가 엇갈리면 fail.
- raw JSON이 chat 본문으로 밀려 나오면 fail.
- evidence footer가 refs 증가로 본문을 밀거나 overflow 나면 fail.

반영:
- evidence ref에 type/status/sourcePath/missingReason이 남도록 했다.
- verifier의 footer count 고정값을 제거했다.
- live verifier는 로컬 콘솔 서버가 떠 있을 때만 유효하다고 문서화한다.

### Reviewer D - 김성욱봇

결과: 조건부 PASS.

깐깐한 지적:
- "수집할 수 있음"과 "수집했다"를 섞으면 바로 fail.
- Alert/Metric 실패를 정상인 척 숨기면 fail.
- 카운트만 보여주고 운영 판단에 쓸 수 없는 표면 정보면 fail.

반영:
- collector는 `success`, `partial`, `error`, `skipped`를 그대로 event status로 남긴다.
- Node evidence는 Ready/Pressure/CPU/Memory를 표로 제공한다.
- Alert evidence는 Watchdog 제외와 non-Watchdog active alert count를 분리한다.
- Metric evidence는 query/window/value를 표로 제공한다.

## 검증 결과

### Python compile

PASS.

```text
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py
```

### Backend targeted

PASS.

```text
6 passed, 160 deselected, 2 warnings
```

포함 검증:
- OpenShift adapter node/alert/metric resolved
- pod restart RCA ToolPlan missing evidence 갱신
- Node/Alert/Metric evidence builder
- partial/failed RCA Context step status
- `/v1/chat/stream` pre-answer evidence_ref 생성

### Backend full

PASS.

```text
168 passed, 2 warnings
```

### Frontend build

PASS.

```text
corepack yarn build
webpack 5.105.4 compiled successfully in 59949 ms
```

### UI verifier

FAIL - 환경 사유.

```text
task kugnus:ui:verify
FAIL kugnus ui verifier crashed {"message":"fetch failed"}
url: http://localhost:9000/aiops-kugnus
```

판단:
- verifier 코드 자체는 실행됐다.
- 실패 원인은 `http://localhost:9000/aiops-kugnus` 로컬 콘솔 dev server가 떠 있지 않은 상태다.
- 이 결과는 UI 기능 실패 판정이 아니라 live verification 환경 미준비다.

## Pass / Fail 기준

| 기준 | 결과 | 근거 |
| --- | --- | --- |
| Node/Alert/Metric adapter가 resolved다 | PASS | backend tests |
| 세 evidence type이 `node`, `alert`, `metric`으로 매칭된다 | PASS | backend tests |
| partial evidence가 별도 상태로 남는다 | PASS | backend tests |
| failed evidence가 collected로 섞이지 않는다 | PASS | backend tests |
| stale missing reason이 수집된 type에 남지 않는다 | PASS | backend tests |
| pre-answer RCA Context가 세 signal evidence를 반영한다 | PASS | chat stream test |
| token/Bearer 원문이 evidence에 남지 않는다 | PASS | backend tests |
| Frontend build | PASS | webpack build |
| Live UI verifier | FAIL 환경 | local console server not reachable |

## 실행하지 않은 것

- `oc apply`
- `oc delete`
- `oc patch`
- `oc scale`
- `oc exec`
- `task catalog:deploy`
- `task olm:install`
- `task kugnus:install`
- 회사 OCP 설치/배포/카탈로그 변경

## 남은 리스크

- Live UI verifier는 `task be:dev`, `task fe:dev`, Docker, oc login, portproxy가 정상인 상태에서 다시 수행해야 한다.
- Alert/Metric은 Thanos public URL이 없거나 권한이 부족하면 `skipped/error`가 정상 결과다. 이 경우 답변은 원인을 단정하면 안 된다.
- Node metrics.k8s.io가 없으면 Node 상태는 수집하되 CPU/Memory usage는 partial로 남는다.
- Pod log evidence는 아직 실제 preflight로 가져오지 않는다. Stage 3-3 또는 Stage 4 전에 별도 안전 기준이 필요하다.

## 다음 행동

1. 로컬 dev server를 띄운 뒤 `task kugnus:ui:verify`를 다시 수행한다.
2. Stage 3-3에서 Pod log/Event 별도 evidence ref를 실제 preflight로 분리할지 결정한다.
3. Stage 4에서 조치 후보 생성으로 넘어가기 전에 RCA 답변 본문이 실제 evidence status를 올바르게 말하는지 live UI에서 확인한다.
