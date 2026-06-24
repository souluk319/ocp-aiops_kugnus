# Ver.0.1.2 Stage 4 Review - Read-only 조치 후보

## Ref stamp

- Branch: `feat/v.0.1.2`
- Base flow: Ver.0.1.2 Stage 1-3 완료 후 Stage 4 진행
- Scope: read-only 조치 후보 생성과 대시보드 표시
- OCP mutation/install/deploy: 실행하지 않음

## 목표

Stage 4의 목표는 실제 조치 실행이 아니라, 이상 징후를 근거로 운영자가 검토할 read-only 조치 후보를 만드는 것이다.

완료 기준은 다음으로 잠근다.

- 후보에는 위험도, 선행 확인, 예상 영향, 승인 필요 여부, 검증 항목이 있어야 한다.
- UI에는 `제안만 함 / 실행 안 함`이 보여야 한다.
- 후보 생성은 `ActionProposal`, `SealedActionPlan`, `Approval`, `Execution` 저장소를 증가시키면 안 된다.
- `oc apply`, `oc delete`, `oc patch`, `oc scale`, `oc exec`는 실행 지시가 아니라 금지 동작으로만 표시한다.

## 구현 내용

### Backend

- `build_aiops_action_candidates()`를 추가했다.
- `/v1/aiops/overview` 응답에 `spec.actionCandidates`를 추가했다.
- `/v1/aiops/action-candidates` GET 엔드포인트를 추가했다.
- 후보 payload에 다음 안전 필드를 고정했다.
  - `executable: false`
  - `mutationSubmitted: false`
  - `approvalRequired: true`
  - `statusLabel: "제안만 함 / 실행 안 함"`
  - `blockedReasons`
  - `blockedActions`
  - `evidenceRefs`
  - `executionPolicy.mode: read-only`
  - `executionPolicy.executionEnabled: false`
- read-only 자연어 조치 응답 문구를 `실행 모드 전환 안내` 중심에서 `조치 후보만 정리 / 실행 안 함` 중심으로 수정했다.

### Frontend

- `AiopsActionCandidate` / `AiopsActionCandidateSummary` 타입을 추가했다.
- 대시보드에 `Cywell AI 조치 후보` 보드를 추가했다.
- 배치 순서는 `이상 징후 -> 조치 후보 -> 데이터 소스 -> 챗봇`으로 고정했다.
- 후보 카드는 최대 3개만 보여주고, 각 카드에 다음 항목을 표시한다.
  - 대상
  - 상태
  - 선행 확인
  - 예상 영향
  - 승인
  - 검증
- 정책 라인에 `mutation disabled`와 금지 동작을 표시한다.

### Verifier

- `scripts/verify-kugnus-ui.mjs`에 Stage 4 DOM 검증을 추가했다.
- 검증 항목:
  - 조치 후보 보드 존재
  - `data-action-candidate-execution="not-executed"`
  - `data-action-candidate-mode="read-only"`
  - `제안만 함 / 실행 안 함` 표시
  - mutation disabled 및 금지 동작 표시
  - 후보 카드가 위험도/선행 확인/예상 영향/승인/검증을 표시
  - 대시보드 순서가 `metrics -> anomaly -> action candidates -> source -> assistant`
- OpenShift console 초기 watch 지연을 고려해 최초 root 대기 시간을 60초로 늘렸다.

## Reviewer 결과

### Reviewer A - 제품/요구사항

초안 판단은 fail이었다.

- 기존 read-only 조치 요청은 후보 생성이 아니라 skipped였다.
- 위험도/선행 확인/예상 영향/승인 필요 여부가 별도 후보 산출물로 없었다.
- UI에 `제안만 함 / 실행 안 함`이 명확하지 않았다.

반영:

- `AIOpsActionCandidateSummary`를 별도 산출물로 추가했다.
- 후보 카드와 read-only 응답에 `제안만 함 / 실행 안 함`을 표시했다.

### Reviewer B - 백엔드/안전성

초안 판단은 fail 가능성이었다.

- 기존 `ActionProposal` lifecycle에 태우면 실행 경로의 입구가 된다.
- Stage 4는 `ReadOnlyActionCandidateSet`이어야 한다.
- 후보 생성 중 proposal/plan/approval/execution record가 증가하면 fail이다.

반영:

- 기존 ActionProposal 저장소를 쓰지 않는 별도 builder로 구현했다.
- 테스트에서 `ACTION_PROPOSALS`, `SEALED_ACTION_PLANS`, `APPROVAL_DECISIONS`, `EXECUTION_RECORDS` count가 증가하지 않음을 확인했다.

### Reviewer C - UI/검증

초안 판단은 fail이었다.

- Dashboard에 조치 후보 전용 보드가 없었다.
- verifier가 quick menu label만 보고 Stage 4를 직접 검증하지 않았다.

반영:

- Dashboard 전용 조치 후보 보드를 추가했다.
- verifier에 Stage 4 보드와 필수 필드 검증을 추가했다.

### Reviewer K - 김성욱봇

최종 빠꾸 기준:

- 실행 기록 카운트로 조치 후보를 대체하면 fail.
- 후보가 실행 가능한 것처럼 보이면 fail.
- `나중에 고도화`로 위험도/선행 확인/승인 표시를 미루면 fail.
- 금지 동작이 실행 명령처럼 보이면 fail.

현재 판정:

- Backend 계약: pass
- Frontend build: pass
- UI verifier live run: environment fail, 원인 분리 필요

## 검증 결과

### Pass

```bash
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py
```

결과: pass

```bash
node --check scripts/verify-kugnus-ui.mjs
```

결과: pass

```bash
git diff --check
```

결과: pass

```bash
python -m pytest komsco-ai-gateway/tests/test_health.py -k "aiops_action_candidates or aiops_anomaly_summary or aiops_overview" -q
```

결과: `5 passed, 162 deselected, 2 warnings`

```bash
python -m pytest komsco-ai-gateway -q
```

결과: `169 passed, 2 warnings`

```bash
cd komsco-ai-console-plugin && corepack yarn build
```

결과: webpack compile success

### UI verifier

```bash
KUGNUS_CHROME_DEBUG_PORT=9232 task kugnus:ui:verify
```

결과: fail

증상:

- `http://localhost:9000/dashboards`: HTTP 200
- `http://localhost:9000/aiops-kugnus`: HTTP 200
- `http://localhost:9001/plugin-manifest.json`: HTTP 200
- plugin manifest에는 `komsco-ai-console-plugin-kugnus`, `AiopsDashboardPage`, `/aiops-kugnus` route가 존재한다.
- plugin script도 HTTP 200이다.
- 하지만 verifier의 headless Chrome 세션에서 `.komsco-ai` root를 제한 시간 안에 찾지 못했다.

현재 판단:

- 코드 컴파일 실패나 manifest 404는 아니다.
- 로컬 OpenShift console boot/watch 또는 headless verifier 세션에서 plugin route mount가 완료되지 않는 문제로 분리한다.
- 이 실패는 Stage 4 UI 검증 조건 추가 자체의 실패가 아니라 live browser 검증 환경 failure로 기록한다.

## 안전 확인

- 회사 OCP에 `oc apply/delete/patch/scale/exec`를 실행하지 않았다.
- `task catalog:deploy`, `task olm:install`, `task kugnus:install`를 실행하지 않았다.
- 기존 `komsco-ai-console-plugin`, `lightspeed-console-plugin` 변경 없음.
- `.env`, token, kubeconfig, password를 읽거나 커밋하지 않았다.

## 남은 gap

- live UI verifier가 `.komsco-ai` root를 못 찾는 원인을 추가로 분리해야 한다.
- 필요 시 프론트 dev server와 local console bridge를 재기동한 뒤 `task kugnus:ui:verify`를 다시 실행한다.
- Stage 5로 넘어가기 전, 실제 브라우저에서 `Cywell AI 조치 후보` 보드가 보이는지 스크린샷 evidence를 남긴다.

## 다음 단계

1. local console bridge/plugin dev server 상태를 재확인한다.
2. `task kugnus:ui:verify`를 다시 통과시킨다.
3. Stage 5 운영자 대시보드 UX로 넘어간다.
