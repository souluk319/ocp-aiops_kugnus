# v0.2.3 Frontend Refactor Plan

## 기준

- 기준 브랜치: `v0.2.2-aiops-answer-experience`
- 스캔 기준 HEAD: `64c0cd494783ddde08c5da0f2f8dfbbd841fd1b5`
- 스캔 시점 상태: Claude 작업 이후 dirty worktree
- 대상 루트: `komsco-ai-console-plugin/src`

이 문서는 리팩토링을 바로 실행하기 위한 작업 계획이 아니라, Claude 작업이 고정된 뒤 안전하게 나눠 실행하기 위한 기준 문서이다.

## 목표

KOMSCO AIOps Console Plugin의 대형 TSX/CSS 파일을 작은 단위로 분리하되, 사용자 화면 동작과 제품 계약은 바꾸지 않는다.

리팩토링의 목적은 아래로 고정한다.

```text
동작 유지
충돌 최소화
검증 가능한 작은 변경
다음 기능 개발 속도 회복
```

## 하지 않을 것

- 기능 동작 변경
- Action Plan 제품 계약 변경
- UI/UX 재설계
- 상태관리 방식 교체
- API 계약 변경
- 대량 네이밍 변경
- 보호된 Claude/user 산출물 수정
- 전체 components 폴더 일괄 리팩토링

## 현재 구조 요약

주요 프론트엔드 노출 지점은 `komsco-ai-console-plugin/package.json`의 `consolePlugin.exposedModules`이다.

```text
AiopsAuditPage              -> ./pages/AiopsAuditPage
AiopsDashboardPage          -> ./pages/AiopsDashboardPage
AiopsDocsPage               -> ./pages/AiopsDocsPage
AiopsExecutionRecordsPage   -> ./pages/AiopsExecutionRecordsPage
AiopsPolicyPage             -> ./pages/AiopsPolicyPage
NullContextProvider         -> ./components/NullContextProvider
useAssistantOverlay         -> ./hooks/useAssistantOverlay
```

실제 구현은 아래 두 파일에 집중되어 있다.

```text
src/components/AssistantLauncher.tsx
src/pages/AiopsPages.tsx
```

페이지 엔트리 파일들은 현재 대부분 `AiopsPages.tsx`에서 named export를 다시 default export하는 얇은 파일이다.

## 파일 크기 인벤토리

읽기 전용 스캔 결과:

| 파일 | 줄 수 | 판단 |
| --- | ---: | --- |
| `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx` | 7000 | 1순위 리팩토링 대상 |
| `komsco-ai-console-plugin/src/components/assistant.css` | 5468 | TSX 분리 후 CSS 분리 필요 |
| `komsco-ai-console-plugin/src/pages/AiopsPages.tsx` | 2550 | 2순위 리팩토링 대상 |
| `komsco-ai-console-plugin/src/pages/aiops-pages.css` | 1679 | 페이지 분리 후 CSS 분리 필요 |
| `komsco-ai-console-plugin/src/services/aiGateway.ts` | 1059 | 추후 types/API 분리 후보 |
| `komsco-ai-console-plugin/src/components/coolicons.tsx` | 295 | 유지 가능 |
| `komsco-ai-console-plugin/src/utils/evidenceDisplay.ts` | 64 | 유지 가능 |
| `komsco-ai-console-plugin/src/hooks/useAssistantOverlay.tsx` | 62 | 유지 가능 |

## 의존 관계 요약

### AssistantLauncher

`AssistantLauncher.tsx`는 다음을 직접 import한다.

```text
React
PatternFly Button/Card/CardBody/Switch/TextArea
ReactDOM
coolicons
aiGateway types/functions
evidenceDisplay helpers
k_icon.png
komsco_logo.svg
assistant.css
```

외부 사용 위치:

```text
src/hooks/useAssistantOverlay.tsx
src/pages/AiopsPages.tsx
```

따라서 `AssistantLauncher`의 default export와 props 계약은 1차 리팩토링에서 유지해야 한다.

### AiopsPages

`AiopsPages.tsx`는 다음 책임을 함께 가진다.

```text
공통 페이지 shell
dashboard board components
docs upload/RAG preview flow
audit page
execution records page
policy page
AssistantLauncher draft prompt 연결
aiGateway data fetch
```

각 exposed page 파일은 이 파일의 named export에 의존하므로, 1차 리팩토링에서 export 이름은 유지해야 한다.

## AssistantLauncher 책임 분해 후보

현재 파일 안의 큰 책임은 아래로 보인다.

| 구역 | 현재 위치 | 분리 후보 |
| --- | --- | --- |
| quick prompt/task mode/copy 상수 | 상단 | `assistant.constants.ts`, `assistant.copy.tsx` |
| message/progress/evidence/tool plan 타입 | 상단 | `assistant.types.ts` |
| localStorage 대화 기록 helper | 중상단 | `assistantStorage.ts` |
| markdown/code/evidence render helper | 중단 | `assistantMessageRenderers.tsx` |
| cluster summary/usage formatting | 중후반 | `assistantClusterFormatters.ts` |
| action record/action plan helper | 중후반 | `assistantActionHelpers.tsx` |
| history sidebar/uploaded docs rows | 후반 JSX | `AssistantHistoryPanel.tsx` |
| insight/context rail | 후반 JSX | `AssistantInsightRail.tsx` |
| composer/attachments/quick menu | 후반 JSX | `AssistantComposer.tsx` |
| progress timeline | 중단 | `AssistantProgressTimeline.tsx` |

## AiopsPages 책임 분해 후보

| 구역 | 현재 위치 | 분리 후보 |
| --- | --- | --- |
| 공통 타입/formatter | 상단 | `aiopsPages.types.ts`, `aiopsPages.formatters.ts` |
| useAiopsPageData | 약 384라인 | `useAiopsPageData.ts` |
| PageShell/MetricTile/EmptyState | 약 431라인 | `PageShell.tsx`, `common` 컴포넌트 |
| OperatorFlowBoard | 약 481라인 | `dashboard/OperatorFlowBoard.tsx` |
| AnomalySummaryBoard | 약 877라인 | `dashboard/AnomalySummaryBoard.tsx` |
| ActionCandidateBoard | 약 1011라인 | `dashboard/ActionCandidateBoard.tsx` |
| DataSourceBoard | 약 1209라인 | `dashboard/DataSourceBoard.tsx` |
| CustomerTopologyPanel | 약 1265라인 | `dashboard/CustomerTopologyPanel.tsx` |
| Evidence/Capability/ToolPlan/RCA panels | 약 1373~1702라인 | `dashboard/*Panel.tsx` |
| AiopsDocsPage upload/RAG flow | 약 2014라인 | `docs/AiopsDocsPage.tsx` |
| Audit/Records/Policy pages | 약 2366라인 이후 | 각 page 파일로 이동 |

## 권장 브랜치 전략

Claude 작업이 커밋된 뒤 `dev`를 만들고, 실제 리팩토링은 `dev`에서 직접 하지 않는다.

```text
현재 최신 작업 브랜치
  -> dev
    -> refactor/frontend-inventory
    -> refactor/assistant-types-constants
    -> refactor/assistant-render-helpers
    -> refactor/assistant-history-panel
    -> refactor/assistant-progress-panel
    -> refactor/aiops-pages-dashboard-sections
    -> refactor/aiops-pages-docs-page
```

`dev`는 통합 브랜치이고, `refactor/*`는 되돌릴 수 있는 짧은 작업 브랜치이다.

## 실행 순서

### 0단계: 기준 고정

```bash
git status --short
git branch --show-current
git rev-parse HEAD
```

기능 검증이 끝난 최신 브랜치를 먼저 커밋/푸시한다. 이후 그 브랜치에서 `dev`를 만든다.

### 1단계: 타입/상수/문구 분리

가장 먼저 `AssistantLauncher.tsx`의 타입, 상수, UI copy를 분리한다.

```text
AssistantLauncher.tsx
assistant.types.ts
assistant.constants.tsx
assistant.copy.tsx
```

이 단계에서는 JSX 구조, 상태 흐름, API 호출을 바꾸지 않는다.

### 2단계: 순수 helper 분리

렌더링과 무관하거나 입력/출력이 명확한 helper만 분리한다.

```text
assistantStorage.ts
assistantFormatters.ts
assistantEvidence.ts
assistantActions.ts
```

이 단계에서는 hook, state, effect를 이동하지 않는다.

### 3단계: 작은 UI 컴포넌트 분리

상태를 거의 가지지 않는 UI부터 분리한다.

```text
AssistantProgressTimeline.tsx
AssistantCodeBlock.tsx
AssistantEvidenceFooter.tsx
AssistantUploadedDocumentRows.tsx
```

props 계약은 명시적으로 두고, 부모 상태 구조는 유지한다.

### 4단계: 큰 UI 구역 분리

후반 JSX를 화면 구역 기준으로 분리한다.

```text
AssistantHistoryPanel.tsx
AssistantInsightRail.tsx
AssistantComposer.tsx
AssistantMessageList.tsx
```

이 단계부터 props가 많아질 수 있으므로, 먼저 임시 props 전달을 허용하고 hook 재설계는 뒤로 미룬다.

### 5단계: hook 분리

UI 분리 후에만 상태 로직을 hook으로 뺀다.

```text
useAssistantStorage.ts
useAssistantRuntimeStatus.ts
useAssistantChatStream.ts
useAssistantAttachments.ts
useAssistantPanelResize.ts
```

이 단계는 회귀 위험이 높으므로 한 브랜치에 하나의 hook만 분리한다.

### 6단계: AiopsPages 분리

`AiopsPages.tsx`는 Dashboard와 Docs를 먼저 분리한다.

```text
pages/AiopsDashboardPage.tsx
pages/AiopsDocsPage.tsx
pages/AiopsAuditPage.tsx
pages/AiopsExecutionRecordsPage.tsx
pages/AiopsPolicyPage.tsx
pages/shared/*
pages/dashboard/*
pages/docs/*
```

외부 exposed module 경로는 그대로 유지한다.

### 7단계: CSS 분리

TSX 분리가 안정된 뒤 CSS를 컴포넌트 구역별로 나눈다.

```text
assistant.css
assistant-history.css
assistant-composer.css
assistant-message.css
assistant-rail.css
aiops-pages.css
aiops-dashboard.css
aiops-docs.css
```

CSS 분리는 시각 회귀 위험이 있으므로 TSX 분리와 같은 커밋에 섞지 않는다.

## Acceptance Criteria

| ID | Pass/Fail 기준 | 측정 방법 | Evidence |
| --- | --- | --- | --- |
| RF-01 | 리팩토링 전후 exposed module 이름이 유지된다. | `package.json` + import check | `consolePlugin.exposedModules` |
| RF-02 | `AssistantLauncher` default export와 props 계약이 유지된다. | typecheck | `yarn typecheck` |
| RF-03 | 1차 리팩토링은 UI 동작 변경 없이 타입/상수/helper 이동만 한다. | diff review | PR diff |
| RF-04 | 각 refactor 브랜치는 한 가지 성격의 변경만 포함한다. | git diff stat | branch diff |
| RF-05 | `AssistantLauncher.tsx`는 단계적으로 7000줄에서 1500줄 이하로 줄인다. | line count | `Get-Content ... .Count` |
| RF-06 | `AiopsPages.tsx`는 단계적으로 2550줄에서 700줄 이하로 줄인다. | line count | `Get-Content ... .Count` |
| RF-07 | CSS 분리는 TSX 안정화 이후 별도 브랜치에서 한다. | branch history | git log |
| RF-08 | 보호된 Claude/user 산출물은 리팩토링 브랜치에서 수정하지 않는다. | git diff --name-only | protected file list |

## 검증 명령

리팩토링 전후 최소 검증:

```bash
cd komsco-ai-console-plugin
yarn typecheck
```

가능하면 추가 검증:

```bash
cd komsco-ai-console-plugin
yarn build-dev
```

주의:

```text
yarn lint
```

현재 package script는 `--fix`를 포함하므로 리팩토링 검증용으로 바로 실행하지 않는다. 필요한 경우 `eslint`를 fix 없이 별도 명령으로 실행한다.

## 리팩토링 시작 전 체크리스트

- [ ] Claude 작업 브랜치가 커밋/푸시되어 있다.
- [ ] 최신 작업 브랜치에서 `dev`를 만들었다.
- [ ] `dev`에서 짧은 `refactor/*` 브랜치를 만들었다.
- [ ] 첫 브랜치는 타입/상수/문구 분리만 한다.
- [ ] `AssistantLauncher` props/export 계약을 바꾸지 않는다.
- [ ] `AiopsPages` exposed page export 이름을 바꾸지 않는다.
- [ ] CSS 분리는 후속 브랜치로 미룬다.
- [ ] `yarn typecheck` 결과를 커밋/PR에 남긴다.
