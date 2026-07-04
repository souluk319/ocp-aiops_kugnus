# v0.2.8.1 Chatbot Answer UX And Action List Plan

## Ref Stamp

- Branch: `feature/v0.2.8.1-chatbot-answer-ux-plan`
- Base checkpoint: `ffc6cc7`
- Current purpose: plan only, not implementation
- Reference source: `/home/kugnus/cywell/AIOps-Ref/aiops-ocp`
- Primary local test surface: `http://localhost:9000/dashboards/aiops`

## Goal

챗봇을 단순 AIOps 질의응답창이 아니라 `OpenShift/OCP 전용 Agentic Operator for AIOps`의 operator interface로 보이게 만든다.

이번 버전의 핵심은 아래 두 가지다.

1. 챗봇 답변을 JK 레퍼런스처럼 운영자가 바로 읽는 runbook/action card 구조로 정리한다.
2. 좌측 패널에서 대화 목록과 조치 목록이 연결되어, 사용자가 “이 대화에서 어떤 조치 흐름이 생겼는지”를 즉시 파악하게 한다.

## Non-Goals

- JK 레퍼런스 HTML/CSS를 그대로 복사하지 않는다.
- 기존 `Tool Plan`, `RcaContext`, `ActionProposal`, `SealedActionPlan`, `ApprovalDecision`, `ExecutionRecord` 계약을 새로 만들지 않는다.
- 회사 서버 배포를 하지 않는다.
- protected artifact와 `evals/aiops-scenarios/*`를 수정하지 않는다.

## Reference Findings

### JK Demo

참고 파일:

- `/home/kugnus/cywell/AIOps-Ref/aiops-ocp/demo/DESIGN.md`
- `/home/kugnus/cywell/AIOps-Ref/aiops-ocp/demo/ocp_chatbot_redesign.html`
- `/home/kugnus/cywell/AIOps-Ref/aiops-ocp/demo/ocp_chatbot_redesign_docked.png`
- `/home/kugnus/cywell/AIOps-Ref/aiops-ocp/demo/ocp_chatbot_redesign_expanded.png`

흡수할 점:

- 기본 패널은 오른쪽 466px 내외의 운영 보조 패널로 유지한다.
- 확대 모드는 chat column + context rail 구조로 사용한다.
- Assistant 답변은 거대한 말풍선이 아니라 heading, summary, runbook card로 보여준다.
- Runbook card는 severity, scope, impact, command, action이 한 덩어리로 읽혀야 한다.
- 하나의 핵심 카드만 open 상태로 시작하고 나머지는 접힌다.
- command block은 dark monospace + copy control로 분리한다.
- quick prompt는 답변 아래가 아니라 composer 주변에 작게 둔다.
- 안전/실행 상태는 항상 보이되, 실행 버튼은 신뢰 가능한 Action Plan에만 붙인다.

흡수하지 않을 점:

- JK의 브랜드명, OCP 로고 스타일, mock-only 데이터는 그대로 가져오지 않는다.
- `모든 명령은 조회 전용` 같은 문구는 제품 전체 철학으로 가져오지 않는다. `읽기 전용`은 실행 모드 중 하나일 뿐이다.
- 단순 HTML demo의 정적 상태는 우리 Gateway/Action lifecycle과 반드시 연결해 재구성한다.

## Current Local Browser Evidence

테스트 일시 기준 로컬 콘솔:

- `http://localhost:9000/aiops-kugnus?codex_v=0281-plan`: 404
- 실제 동작 경로: `http://localhost:9000/dashboards/aiops?codex_v=0281-plan`

대시보드 기본 화면:

- `Tool Plan`, `RCA Context JSON`, `source:`, `score=`, `post_answer`, `[redacted-token]`, `execute` 기본 노출은 없음
- horizontal overflow 없음
- FAB는 우측 하단에 보임

챗봇 open 상태:

- surface size: 약 `520 x 690`
- 답변 본문 font: `13px`, line-height `20.15px`
- 현재 답변은 `상세 분석`부터 시작하고, 운영자 첫 판단 카드가 약하다.
- `읽기 전용` 모드에서도 답변 하단에 `계획`, `승인`, `거절`, `실행` 버튼이 여러 번 노출된다.
- 반복 버튼은 비활성 tooltip이 있어도 신뢰를 해친다.
- 좌측 패널 open 시 history width는 약 `236px`
- 최신 대화의 action refs는 `0건`으로 표시된다.
- 대화 옵션 메뉴는 항상 보이나, 조치 목록이 없는 대화에서는 패널이 단순 history sidebar에 그친다.

판정:

현재 화면은 내부 금지어 노출은 줄었지만, “신뢰할 수 있는 Agentic Operator”로 보이기에는 답변 구조와 조치 목록 경험이 부족하다.

## Problem Statement

현재 챗봇은 다음 이유로 신뢰를 주지 못한다.

- 답변이 상세 분석 보고서처럼 시작해 운영자가 먼저 봐야 할 판단이 늦게 나온다.
- `요약 -> 영향 -> 근거 -> Action Plan -> 검증/롤백` 구조가 화면에서 강하게 드러나지 않는다.
- Action 버튼이 중복 노출되고, 읽기 전용 모드에서도 조치 버튼이 반복되어 “누르면 되는 것인지 안 되는 것인지”가 불명확하다.
- 좌측 패널은 대화 목록 중심이고, 대화와 연결된 조치 lifecycle을 눈에 띄게 보여주지 못한다.
- Action Plan이 AIOps의 핵심 경험인데, 현재 UI에서는 부속 버튼처럼 흩어져 보인다.
- 폰트와 밀도가 아직 운영자용 runbook card라기보다 일반 markdown renderer에 가깝다.

## Target Experience

### Assistant Answer

기본 답변은 아래 구조로 렌더링한다.

```text
현재 판단
영향 범위
확인한 근거
원인 후보
Action Plan
추가 확인
검증/롤백
근거 상세보기
```

표시 원칙:

- 첫 화면에는 “우선 확인할 항목 N개”와 “왜 이 순서인지”가 먼저 보인다.
- 상세 분석은 첫 제목이 아니라 카드 내부의 세부 내용이 된다.
- 원인 후보와 Action Plan은 분리한다.
- Action Plan이 없으면 `조치 가능` 버튼을 반복 노출하지 않고 `근거 더 수집` 또는 `Action Plan 생성 조건 미충족`을 보여준다.
- Action Plan이 있으면 target, reason, impact, validation, rollback, approval 버튼이 한 카드에 들어간다.

### Action Plan Card

Action Plan 카드에는 반드시 아래를 포함한다.

- 아이콘: action type 또는 lifecycle stage를 즉시 구분
- 상태: 후보, 계획 생성, 승인 필요, 실행 가능, 실행 완료, 실패
- 대상: namespace/kind/name
- 근거: evidence count와 핵심 근거 1~2개
- 영향: 서비스 영향 또는 위험도
- 실행 전 검증: precheck
- 실패 시 대응: rollback 또는 verify-fail path
- 버튼: 상황에 맞는 하나의 primary action

금지:

- 같은 target/action의 `계획/승인/실행` 버튼이 한 답변 아래에 반복 노출
- 읽기 전용 모드에서 실행 가능한 것처럼 보이는 버튼
- `Conflict`, `Sealed plan`, `proposal waits for`, digest 원문 기본 노출

### Left Panel

좌측 패널은 아래처럼 구성한다.

```text
브랜드 / 새 대화 / 문서

지난 대화
  - 대화 제목
    시간
    조치 목록:
      [아이콘] 승인 필요 · restart deployment · target
      [아이콘] 실행 완료 · scale deployment · target

문서 탭

현재 사용자
```

조치 목록 규칙:

- 대화 제목 아래 action refs를 항상 보기 좋은 작은 row로 표시한다.
- 각 action ref는 stage icon, short label, target 요약을 가진다.
- 클릭하면 해당 대화와 해당 Action Plan 카드 위치로 이동한다.
- 조치가 없는 대화는 아무것도 없는 것이 아니라 `조치 없음`을 작게 표시하거나 공간 자체를 제거한다.
- menu button은 항상 보이되, 조치 row와 충돌하지 않는다.

## Local-Only Test Scenarios

실제 회사 서버나 live cluster 변경 없이 로컬 콘솔에서만 돌리는 fixture 기반 테스트를 만든다.

### Scenario 1: Alert Triage Answer

목적:

- 긴 경고 보고서가 runbook card로 보이는지 확인한다.

Fixture:

- user question: `최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해줘.`
- assistant answer: alert triage with summary, impact, evidence, cause, action, verification, details
- no executable Action Plan

Pass:

- 첫 open card는 `현재 판단` 또는 `우선 확인`
- Action buttons count: `0`
- `근거 상세보기`는 접힘
- body font >= `14px`

### Scenario 2: Pod CrashLoopBackOff Action Plan

목적:

- 조치 가능한 상황에서 승인 가능한 Action Plan 카드가 하나로 보이는지 확인한다.

Fixture:

- target: `komsco-ai-dev/Pod/aiops-scenario-1-crashloop-*`
- evidence: status `CrashLoopBackOff`, restart count, last exit code
- action: `rollout_restart_deployment` 또는 `rollback` 중 하나
- mode: `execute`

Pass:

- Action Plan 카드 1개
- primary button: `승인 요청` 또는 `승인 후 실행`
- impact, validation, rollback visible
- duplicate `계획/승인/실행` buttons 없음

### Scenario 3: Read-Only Mode Action Request

목적:

- 읽기 전용 모드에서 실행 버튼이 반복 노출되지 않는지 확인한다.

Fixture:

- same target as Scenario 2
- mode: `read-only`

Pass:

- execution button 없음
- `읽기 전용 모드에서는 Action Plan 생성/실행이 차단됨`을 사람용으로 1회만 표시
- disabled buttons repeated count: `0`

### Scenario 4: History Sidebar Action Refs

목적:

- 좌측 패널이 대화와 조치 lifecycle을 연결하는지 확인한다.

Fixture:

- one conversation with 3 action refs:
  - proposal
  - approval
  - execution

Pass:

- history item 아래 조치 row 3개 또는 compact grouped row 표시
- 각 row에 stage icon 있음
- target text가 panel width를 넘지 않음
- click action ref moves to corresponding action card

### Scenario 5: Expanded Mode

목적:

- 확대 모드에서 JK처럼 chat column + context rail이 안정적으로 보이는지 확인한다.

Pass:

- main panel does not jitter
- history panel, chat column, context rail overlap 없음
- context rail contains cluster status, key alerts, recent commands, action plan state

## Browser Verification Plan

새 verifier 후보:

```text
scripts/verify-v0281-chatbot-answer-ux.cjs
```

검증 방식:

- localhost `9000`만 사용
- fixture injection은 localStorage 또는 dev-only mock hook 사용
- live Gateway/cluster mutation 금지
- screenshot 저장:
  - `/tmp/v0281-chatbot-docked.png`
  - `/tmp/v0281-chatbot-history.png`
  - `/tmp/v0281-chatbot-expanded.png`

검증 항목:

- route: `/dashboards/aiops`가 정상 진입점
- `/aiops-kugnus` 404는 별도 route gap으로 기록
- answer body font >= 14px
- runbook cards present
- action card primary button count <= 1 per target/action
- read-only mode has no repeated disabled execution buttons
- history sidebar action refs count matches fixture
- action refs have icons and do not overflow
- no raw internal terms in default answer
- close/open/sidebar behavior leaves no orphan panel

## Implementation Lanes

### Lane 0: Plan And Fixture Harness

- `docs/Ver.0.2.8.1` 문서 작성
- local-only fixture schema 정의
- browser verifier skeleton 작성
- no product UI changes yet

### Lane 1: Answer Renderer

- `AssistantMessageContent.tsx`의 runbook renderer를 JK style card 구조로 강화
- 첫 카드: 현재 판단
- action card는 renderer가 아니라 action lifecycle data와 연결
- markdown fallback은 유지하되 기본 AIOps 답변은 card renderer 우선

### Lane 2: Answer Action List

- `assistant.actionRecords.ts`에서 target/action dedupe key 강화
- 답변 하단의 action list를 icon card로 재구성
- read-only mode에서는 execution controls를 반복 노출하지 않음
- Action Plan 없는 경우 `조치 없음` 또는 `Action Plan 조건 미충족`으로 명확히 표시

### Lane 3: History Sidebar Action Refs

- `AssistantHistoryPanel.tsx`의 `komsco-ai__history-action-refs`를 JK style small action timeline으로 재디자인
- stage icon 추가
- action refs가 없는 대화와 있는 대화의 시각 차이를 명확히 함
- click-to-message-anchor 검증

### Lane 4: Expanded Context Rail

- expanded mode에서 context rail이 실제 cluster/action state를 보여주는지 검증
- blank rail 또는 중복 rail 제거
- history/sidebar/open/close jitter 방지

### Lane 5: Visual Polish

- font, line-height, card rhythm 재조정
- icons는 lucide 또는 기존 coolicons/AIOps icon 중 일관된 체계로 사용
- dark header + thin blue accent 유지
- no nested cards, no decorative gradient

## Acceptance Criteria

| ID | Pass/Fail 기준 | 측정 방법 | Evidence |
| --- | --- | --- | --- |
| V0281-01 | 챗봇 답변 첫 화면이 보고서가 아니라 runbook/action card로 보인다. | Browser screenshot + DOM | docked screenshot |
| V0281-02 | 본문 폰트가 14px 이상이고 줄 간격이 1.6 이상이다. | computed style | verifier output |
| V0281-03 | 읽기 전용 모드에서 `계획/승인/실행` disabled 버튼이 반복 노출되지 않는다. | DOM count | verifier output |
| V0281-04 | Action Plan 카드에는 icon, target, evidence, impact, validation, rollback, primary action이 있다. | DOM + fixture | screenshot |
| V0281-05 | 좌측 패널의 대화 아래 조치 목록에 stage icon이 보인다. | DOM + screenshot | history screenshot |
| V0281-06 | 조치 목록 클릭 시 해당 대화/Action Plan으로 이동한다. | browser interaction | verifier output |
| V0281-07 | `/dashboards/aiops` 기준 로컬 테스트가 가능하다. | browser navigation | route evidence |
| V0281-08 | `/aiops-kugnus` route 혼동은 문서화되거나 수정 대상에 포함된다. | browser navigation | 404 evidence |
| V0281-09 | 기본 화면에 raw Tool Plan/RCA/RAG/internal id가 노출되지 않는다. | text scan | verifier output |
| V0281-10 | 회사 서버 배포나 live mutation 없이 검증된다. | command log | no deploy commands |

## Risks

- 현재 브랜치의 챗봇 UI는 v0.2.2에서 만든 일부 개선보다 뒤처져 있을 수 있다. 구현 전에 `dev`/최신 기준 브랜치와 병합 기준을 다시 확인해야 한다.
- localStorage fixture가 실제 Gateway record shape와 어긋나면 테스트가 거짓 안정감을 줄 수 있다. fixture는 실제 `ConversationActionRef`, `AiopsRecordView`, `Message` 타입에서 생성해야 한다.
- 답변 renderer만 예쁘게 만들고 Action lifecycle data와 연결하지 않으면 또 “그럴듯하지만 실행 신뢰가 없는 UI”가 된다.

## Next Command Set

구현 단계에서 우선 실행할 검증:

```bash
git diff --check
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
node scripts/verify-v0281-chatbot-answer-ux.cjs
```

브라우저 검증은 반드시 로컬 `http://localhost:9000/dashboards/aiops` 기준으로 한다.

