# Ver.0.1.2 Stage 3 Review - RCA 보고서 계약 고정

## 현재 판단

Stage 3 전체 목표는 챗봇 RCA 고도화다. 이번 커밋 범위는 Stage 3-1로 고정한다.

완료한 것은 `질문 -> read-only Tool Plan -> RCA Context -> 운영 분석 보고서 형식 답변 -> evidence footer/UI trace` 계약을 강화한 것이다. 아직 Alert, Node, Metrics를 실제 runtime preflight로 모두 수집하는 단계까지는 아니다. 해당 항목은 계획과 missing reason으로 노출되며, 다음 Stage 3-2에서 실제 수집 경로를 붙인다.

이번 작업에서도 회사 OCP에 `oc apply/delete/patch/scale/exec` 또는 설치성 task를 실행하지 않았다.

## 구현 범위

- `RcaContext.analysisPlan` 추가
  - `mode: evidence_first`
  - `evidenceCollectionSteps`
  - `answerContract`
  - `stopConditions`

- evidence step 상태 계약 추가
  - 각 planned evidence step은 `collected`, `failed`, `missing`, `not_attempted` 중 하나로 표현한다.
  - 가능한 경우 `evidenceId`, `contentDigest`, `sourcePath`, `missingReason`을 포함한다.

- Pod restart RCA ToolPlan 확장
  - Pod/Event/Pod log/ClusterOperator/Node/Alert/Metric/Runbook을 RCA 증거 범위로 명시한다.
  - 실제로 아직 runtime preflight가 없는 Node/Alert/Metric은 `planned` adapter 또는 `missing` evidence로 드러낸다.
  - 계획을 수집 완료처럼 보이지 않게 한다.

- RCA 답변 형식 강화
  - OLS 프롬프트에 `## RCA 보고서` 형식과 필수 섹션을 명시했다.
  - OLS 실패/빈 응답 fallback도 동일한 운영 분석 보고서 구조를 사용한다.
  - 기본 섹션: `우선 판단`, `수집 근거`, `원인 후보`, `확인 불가`, `다음 확인 명령`, `우선순위`.

- UI 진행 상태 강화
  - stream 중 `tool_plan` 이벤트를 `증거 수집 계획` 진행 단계로 표시한다.
  - `rca_context` 이벤트를 `RCA 근거 문맥` 진행 단계로 표시한다.
  - evidence footer는 기존처럼 수집/추가 확인 count와 trace id를 표시한다.

- verifier 강화
  - assistant RCA 답변에 보고서 섹션이 있는지 검사한다.
  - 본문이 heading/list/code/table 등 구조화된 렌더링을 사용하는지 검사한다.
  - read-only RCA 답변에 `oc apply/delete/patch/scale/exec` 실행 지시가 섞이면 fail 처리한다.

- 안전성 보강
  - generic exception 경로에서도 `safe_exception_text`를 사용하도록 수정했다.
  - `Authorization: Bearer ...`, `token=...` 형태의 민감 문자열이 SSE/audit/workflow에 원문으로 남지 않도록 테스트했다.

## 병렬 검수 결과

### Reviewer A - 요구사항/제품성

결과: PASS 조건 정의.

핵심 빠꾸 기준:
- ToolPlan이 답변보다 먼저 나와야 한다.
- RCA Context와 evidence footer가 화면에서 추적 가능해야 한다.
- OLS 실패를 숨기면 fail.
- `docs/Ver.0.1.2/stage-3-review.md`에 증거가 남아야 한다.

### Reviewer B - 백엔드/안전성

결과: 1차 FAIL 후 보강.

지적:
- 계획과 실제 수집 상태가 불일치할 수 있었다.
- Alert/Node/Metrics가 RCA 증거 범위에 명확히 들어오지 않았다.
- OLS 성공 경로의 보고서 형식은 prompt 계약으로 더 강하게 고정해야 했다.
- generic exception 경로의 redaction이 부족했다.

수정:
- `analysisPlan.evidenceCollectionSteps[*].status`를 추가했다.
- Node/Alert/Metric adapter capability를 `planned`로 드러냈다.
- Pod restart RCA missing evidence에 Event/Pod log/ClusterOperator/Node/Alert/Metric/Runbook을 명시했다.
- OLS prompt와 fallback에 RCA 보고서 섹션 계약을 추가했다.
- generic exception 경로를 `safe_exception_text`로 통일했다.

### Reviewer C - UI/UX

결과: PASS 조건 정의.

핵심 빠꾸 기준:
- 답변이 `확인해보세요` 식 문장 나열이면 fail.
- evidence footer만 있고 본문에 근거/미확인이 분리되지 않으면 fail.
- read-only RCA 답변에서 mutation 명령이 실행 지시처럼 보이면 fail.
- raw JSON은 trace panel에만 두고, chat 본문은 사람용 보고서여야 한다.

수정:
- UI 진행 단계에 `증거 수집 계획`, `RCA 근거 문맥`을 추가했다.
- verifier에 RCA 보고서 섹션과 read-only 명령 검사를 추가했다.

## 검증 결과

### Backend targeted

PASS.

```text
7 passed, 155 deselected, 2 warnings
```

포함 검증:
- read-only pod restart RCA ToolPlan
- RcaContext analysisPlan/step status
- OLS prompt RCA report contract
- fallback RCA report contract
- generic exception redaction

### Backend full

PASS.

```text
164 passed, 2 warnings
```

### Frontend build

PASS.

```text
corepack yarn build
webpack 5.105.4 compiled with 1 warning
```

warning은 기존 vendor chunk size 경고다.

### UI verifier

Verifier script는 Stage 3 RCA section/read-only command 검사를 포함하도록 갱신했다.

최종 live verifier는 현재 로컬 dev server/Gateway 상태에 의존하므로 이번 산출물에서는 실행 완료 증거로 쓰지 않는다. Stage 3-2 시작 전에 `task fe:dev`와 Gateway를 깨끗하게 재시작한 뒤 `task kugnus:ui:verify`를 다시 수행해야 한다.

### 실행하지 않은 것

- 회사 OCP 변경 명령
- 설치/배포/카탈로그 등록 명령
- `task catalog:deploy`
- `task olm:install`
- `task kugnus:install`

## Pass / Fail 기준

| 기준 | 결과 | 근거 |
| --- | --- | --- |
| ToolPlan이 read-only RCA 계획을 만든다 | PASS | backend tests |
| RcaContext가 analysisPlan과 evidence step status를 가진다 | PASS | backend tests |
| OLS prompt/fallback이 RCA 보고서 섹션을 요구한다 | PASS | backend tests |
| 근거 부족이 missing/not_attempted로 드러난다 | PASS | analysisPlan + missing evidence |
| Generic exception이 민감값을 원문 노출하지 않는다 | PASS | backend tests |
| UI가 RCA 계획/문맥 진행 단계를 표시한다 | PASS | frontend build |
| UI verifier가 RCA 보고서 섹션을 검사한다 | PASS | verifier source update |
| Alert/Node/Metrics 실제 runtime preflight 수집 | NEXT | Stage 3-2 범위 |
| Live UI verifier 최종 실행 | NEXT | 로컬 dev server 재시작 후 수행 |

## 남은 리스크

- Stage 3-1은 RCA 계약 강화 단계다. Alert/Node/Metrics 실제 수집은 아직 missing/planned로 표시된다.
- OLS가 prompt를 무시하고 비구조화 답변을 반환하는 경우 Gateway가 본문을 강제 재작성하지는 않는다. 현재는 prompt 계약과 UI verifier로 잡는다.
- live verifier는 로컬 Gateway/console dev server가 건강해야 의미가 있다.

## 다음 행동

1. Stage 3-2에서 Alert/Node/Metrics runtime preflight 수집을 붙인다.
2. OLS 정상 응답이 보고서 형식을 어길 때 Gateway가 fallback 또는 section guard를 적용할지 결정한다.
3. dev server 재시작 후 `task kugnus:ui:verify`를 실행한다.
4. Stage 4 조치 후보 생성으로 넘어가기 전에 RCA report와 evidence trace가 실제 화면에서 pass하는지 확인한다.
