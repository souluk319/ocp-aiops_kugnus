# Ver.0.1.2 Stage 1 Review

## 범위

- Stage: 1. 현재 클러스터 상태 요약
- Branch: `feat/v.0.1.2`
- Base: `af895a5`
- Plan commit: `8d7ea9e`
- 실행 원칙: 회사 OCP는 read-only 관측 대상으로만 사용한다.
- 금지 유지: `oc apply/delete/patch/scale/exec`, `task catalog:deploy`, `task olm:install`, `task kugnus:install` 실행하지 않음.

## 구현 결과

- 신규 API: `GET /v1/aiops/overview`
- 기존 API 유지: `GET /v1/cluster/summary`
- 수집 항목:
  - Node inventory: `/api/v1/nodes`
  - Node metrics: `/apis/metrics.k8s.io/v1beta1/nodes`
  - ClusterVersion: `/apis/config.openshift.io/v1/clusterversions/version`
  - ClusterOperator: `/apis/config.openshift.io/v1/clusteroperators`
  - Monitoring URL config: `openshift-config-managed/monitoring-shared-config`
  - Thanos probe: `thanosPublicURL + /api/v1/query?query=up`
- UI:
  - 대시보드 상단을 `Cywell AI 관제탑` 관점으로 명확히 분리.
  - `OpenShift 기본 대시보드`와 혼동하지 않도록 overview side에 분리 문구 표시.
  - 데이터 소스별 available/error/unavailable 상태와 실패 사유를 카드로 노출.
  - Gateway fallback, stream 상태, read-only safety mode를 숨기지 않음.

## 자동 검증 1차

| 항목 | 결과 | 근거 |
| --- | --- | --- |
| Backend syntax | PASS | `python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py` |
| Targeted backend tests | PASS | `3 passed, 155 deselected` |
| Full backend tests | PASS | `160 passed, 2 warnings` |
| Frontend build | FAIL then PASS | 초기 `flushSync` named import 타입 오류 수정 후 `webpack compiled successfully` |
| UI verifier | FAIL then PASS | stop button, stale history state, screenshot hang, click simulation 보강 후 `89 checked / 0 failed` |

## 빠꾸와 수정

| 빠꾸 항목 | 원인 | 수정 |
| --- | --- | --- |
| 정지 버튼이 스트리밍 중 상태로 안 잡힘 | React state batching 또는 매우 빠른 fallback 응답으로 loading DOM이 보이지 않음 | 전송 직후 sync/fallback 렌더 보장, 최소 stop 상태 표시 시간 추가 |
| 정지 버튼 클릭 후 전송 버튼 복귀 지연 | abort 완료까지 loading 해제가 묶임 | cancel 즉시 `setLoading(false)` 수행 |
| history sidebar 기본 닫힘 검증 오염 | HMR/브라우저 타깃 재사용으로 이전 열린 상태가 남음 | verifier 시작 cleanup에서 열린 history sidebar 닫음 |
| screenshot 단계 hang | CDP `Page.captureScreenshot`에 timeout/retry 없음 | screenshot timeout 및 1회 retry 추가 |
| quick menu click 불안정 | verifier의 `el.click()`가 실제 사용자 입력과 다름 | pointer/mouse event sequence로 click helper 개선 |
| click helper가 가로 스크롤 생성 | `scrollIntoView({ inline: "center" })`로 page X offset 변동 | `inline: "nearest"`와 scrollX 복구 적용 |

## Reviewer 판정

### Reviewer A: Visual polish

- PASS.
- Cywell AI 관제탑 카드가 기존 OpenShift 대시보드와 구분된다.
- 데이터 소스 상태 카드가 지나치게 장식적이지 않고 운영 도구 톤을 유지한다.
- 검증 근거: dashboard overview, metrics, source board, horizontal overflow, screenshots pass.

### Reviewer B: Interaction UX

- PASS.
- 채팅 전송 버튼은 전송 중 stop 상태로 바뀌고, 사용자가 중지하면 정상 전송 버튼으로 돌아온다.
- history drawer, fullscreen, resize lock/unlock, quick menu, Ask/Troubleshooting 선택 동작 검증 통과.
- 검증 근거: `task kugnus:ui:verify` 89 checks pass.

### Reviewer C: OpenShift product fit

- PASS.
- API는 OpenShift UserToken 기반 read-only 관측으로 유지된다.
- 실패한 데이터 소스와 fallback 상태를 숨기지 않고 UI에 노출한다.
- 기존 `komsco-ai-console-plugin`, `lightspeed-console-plugin`, 회사 OCP 설치 리소스는 변경하지 않았다.

### 김성욱봇: 깐깐한 제품 심사

- PASS with watch item.
- "가짜 데이터 없이 실제 클러스터 관측값과 실패 원인을 내는 점은 통과."
- "다만 다음 단계부터는 단순 상태 표시가 아니라 이상 징후 우선순위와 조치 후보까지 연결되어야 제품성이 생김."

## 완료 기준 판정

| 완료 기준 | 판정 | evidence |
| --- | --- | --- |
| `/v1/aiops/overview` 제공 | PASS | backend route/test 추가 |
| `/v1/cluster/summary` 유지 | PASS | 기존 route 유지, 기존 테스트 통과 |
| 노드/메트릭/Operator/Monitoring 상태 포함 | PASS | overview spec + tests |
| 데이터 소스별 성공/실패 원인 표시 | PASS | `dataSources[]`와 UI source board |
| OpenShift 기본 대시보드와 Cywell AI 관제탑 구분 | PASS | UI overview side 문구와 source board |
| 가짜 데이터 숨김 없음 | PASS | unavailable/error reason 노출 |
| 회사 OCP 변경 없음 | PASS | 설치/배포/patch 계열 명령 미실행 |

## 남은 리스크

- 로컬 dev console은 HMR/Chrome target 재사용 상태에 영향을 받을 수 있다. verifier에 cleanup과 timeout을 보강했지만, 재부팅 후에는 `task fe:dev`를 새로 띄운 깨끗한 상태가 가장 안정적이다.
- 현재 Lightspeed stream은 로컬 검증 중 fallback 상태가 관측되었다. Stage 1 범위에서는 실패 노출이 목적이므로 pass이나, Stage 2 이후에는 이상 징후 정리와 함께 원인 표시를 더 정교화해야 한다.
- Thanos probe는 `monitoring-shared-config`의 public URL과 사용자 토큰 접근성에 의존한다. 접근 실패 시 `dataSources`에 reason이 표시되어야 한다.

## 다음 단계

- Stage 2: 이상 징후 자동 정리.
- Alert, Degraded Operator, CrashLoopBackOff, ImagePullBackOff, Pending Pod, restart spike, upgrade block 신호를 수집한다.
- 출력은 `정상`, `주의`, `확인 필요`, `위험`으로 정렬하고, 사용자가 바로 누를 수 있는 read-only 근거 조회로 연결한다.
