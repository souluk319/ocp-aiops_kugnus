# v0.2.4 JK Reference Absorption Plan

## 기준과 목적

- 현재 기준: `dev@5c178dd`
- 참고 기준: `cywell-rnd-team/ocp-aiops feature/aiops-jk@d9921bd`
- 상위 계약: `docs/Ver.0.2.2/aiops-answer-experience-contract.md`, `docs/Ver.0.2.3/aiops-action-plan-contract.md`, `DESIGN.md`
- 공식 제품 기준: `docs/Komsco_ai_agent_final.pdf`

이 문서는 JK 브랜치를 보고 배울 점을 제품 구현으로 흡수하기 위한 계획서이다. 목표는 JK 코드를 통째로 가져오는 것이 아니라, 우리 제품의 약한 지점인 챗봇 답변 경험, Action Plan 표현, 시스템 경계 설명, typed action 검증 루프를 더 단단하게 만드는 것이다.

v0.2.4의 제품 문장은 아래로 고정한다.

```text
KOMSCO AIOps는 OpenShift 콘솔 안에서 운영자가 현재 문제를 파악하고,
근거를 확인하고, 승인 가능한 Action Plan을 통제하는 Agentic Operator UI이다.
```

## 현재 판단

JK 브랜치가 우리보다 우위인 부분은 아래이다.

| 항목 | JK 브랜치의 장점 | 우리 현재 gap | v0.2.4 흡수 방식 |
| --- | --- | --- | --- |
| 첫인상 | 챗봇이 아니라 operations copilot처럼 보인다. | 답변/조치 카드가 때때로 말풍선, 기록, 내부 상태처럼 흩어진다. | assistant 응답을 운영 런북 카드로 재구성한다. |
| 런북 카드 | severity, scope, impact, command, action이 한 카드에 묶인다. | Action Plan 카드와 근거/명령/검증이 분리되어 승인 판단이 약하다. | Action Plan 카드에 대상, 근거, 영향, 검증, 롤백, 승인 조건을 고정한다. |
| 확장 모드 | 넓은 화면에 context rail을 둔다. | expanded 화면이 독립페이지와 챗봇 기능 사이에서 집중도가 떨어질 수 있다. | expanded assistant는 오른쪽 context rail을 표준으로 한다. |
| 책임 경계 | OLS/Gateway/Action Executor 역할이 명확하다. | UI 라벨과 코드 설명이 `읽기 전용`, `실행 가능`, `실행 무제한`의 의미를 흔들 때가 있다. | 책임 경계와 실행 모드 설명을 한 언어로 통일한다. |
| 검증 | typed action scenario report가 있다. | 기능이 있어도 사용자에게 "실제로 되는 흐름"으로 보이는 증거가 약하다. | v0.2.4 acceptance criteria와 verifier/test 이름으로 고정한다. |

반대로 그대로 가져오면 안 되는 부분도 있다.

| 항목 | 이유 | 처리 |
| --- | --- | --- |
| JK HTML 데모 자체 | 정적 데모이며 현재 React 상태/서비스 계약과 직접 연결되지 않는다. | 시각 구조와 UX 원칙만 흡수한다. |
| 별도 Tool Broker/Rust 전환 | 현재 repo는 FastAPI Gateway 중심 구현이고 즉시 대체하면 위험하다. | 현재 Gateway/Action Executor 안에서 책임 경계만 먼저 반영한다. |
| 문서의 장기 target architecture 전체 | MVP 범위를 넘는 Credential Broker, Evidence Service, DB ledger가 많다. | v0.2.4에는 라벨, 정책, 검증, UI 표현에 필요한 부분만 반영한다. |
| 회사 서버 배포 관련 변경 | 최근 배포 사고와 별개로 이번 목표는 로컬 UX/계약 정리이다. | OLM/Helm/NetworkPolicy/Route는 이번 범위에서 제외한다. |

## 참고 파일별 흡수 항목

| 참고 파일 | 확인한 내용 | 흡수할 것 |
| --- | --- | --- |
| `demo/DESIGN.md` | 466px docked panel, expanded 1240px, 316px context rail, runbook card, compact composer | assistant layout과 CSS acceptance criteria |
| `demo/ocp_chatbot_redesign.html` | 우선 확인 3개, command block, copy control, context rail, quick prompt, read-only indicator | 카드 정보 구조와 expanded/docked 화면 흐름 |
| `docs/architecture/ols-gateway-tool-boundary.md` | OLS는 read-only observation, Gateway는 BFF/policy/SSE, mutation은 별도 승인 흐름 | Gateway prompt와 UI 라벨 책임 경계 |
| `docs/architecture/aiops-agent-architecture-proposal.md` | ActionProposal, SealedActionPlan, ApprovalDecision, ExecutionGrant, Action Executor 경계 | Action Plan lifecycle UI와 실행 모드 설명 |
| `komsco-ai-gateway/komsco_ai_gateway/main.py` | 자연어 intent, followup 복원, target resolution, action plan 생성/실행 branch | UI보다 먼저 로직 계약 inventory로 흡수 |
| `komsco-ai-gateway/komsco_ai_gateway/aiops_core.py` | typed mutation request builder, HPA/rollback/eviction precondition | 실행 전 deterministic validation 기준 |
| `komsco-ai-gateway/komsco_ai_gateway/action_executor.py` | ExecutionGrant audience/digest/target/policy 검증 | 승인 후 실행 경계와 실패 문구 기준 |
| `komsco-ai-gateway/komsco_ai_gateway/security.py` | mutation request classification과 gateway guardrail | OLS 일반 답변으로 빠지면 안 되는 변경 요청 차단 기준 |
| `docs/reports/aiops-agentic-scenario-verification-report.md` | 3/4/5턴 `진행해`, restart/scale/evict/rollback/HPA, ambiguous block | Gateway/action regression gate |
| `scripts/evaluate-aiops-actions-e2e.py` | live action e2e의 setup, approve, execute, verify 흐름 | 이후 별도 검증 스크립트 또는 task 설계 참고 |

## 구현 범위

v0.2.4 구현은 5개 lane으로 나눈다. 한 브랜치에서 모두 섞지 않는다.

```text
lane 1: JK backend/action logic absorption
lane 2: assistant runbook card UI
lane 3: expanded assistant context rail
lane 4: Action Plan lifecycle/dedupe/error wording
lane 5: typed action verification gate
```

배포 lane은 없다. 회사 서버 배포는 v0.2.4 구현/검증이 끝난 뒤 별도 배포 계약에서 다룬다.

## Lane 1: JK Backend/Action Logic Absorption

### 목표

UI를 바꾸기 전에 JK 브랜치에서 배울 agentic action 로직을 현재 repo의 구현과 비교해, 이미 있는 것과 보강할 것을 나눈다.

이 lane은 사용자가 말한 "단순 UI 참고로 끝내면 안 되는 지점"을 고정하는 단계이다.

### 로직 학습 대상

| 영역 | JK에서 볼 것 | 우리 구현에서 확인할 것 |
| --- | --- | --- |
| Natural action intent | scale/restart/rollback/evict/HPA 자연어 분류 | `parse_natural_action_intent`가 한국어 운영 표현을 충분히 받는지 |
| Followup execution | 3/4/5턴 뒤 `진행해`가 최근 action request를 복원 | `recent_natural_action_request`가 assistant/system 문장에 끌려가지 않는지 |
| Target resolution | namespace/kind/name, pageContext, cluster-wide ambiguity 처리 | 대상 불명확 시 OLS로 넘기지 않고 Gateway에서 중단하는지 |
| Action registry | toolName, targetKind, parameter schema, risk, pathTemplate | registry version/digest가 plan/approval/execution에 일관되게 묶이는지 |
| Runbook registry | runbook step과 typed action 연결 | UI의 "런북 카드"가 실제 action/runbook id와 연결되는지 |
| Mutation builder | restart/scale/evict/rollback/HPA별 deterministic request 생성 | HPA review, controller owner, rollback revision, min/max validation |
| Approval/Execution | SealedActionPlan, ApprovalDecision, ExecutionGrant 검증 | self-approval, expiry, digest mismatch, policy hash mismatch 처리 |
| Error surface | Conflict, policy disabled, reauth, target mismatch | 사용자 화면 문구가 원인 단위로 번역되는지 |

### 구현 산출물

- 새 코드 대량 이식 전에 `docs/Ver.0.2.4/aiops-jk-logic-inventory.md`를 작성한다.
- inventory는 `already covered`, `partial`, `missing`, `do not copy` 네 구역으로 나눈다.
- `partial`과 `missing`만 후속 구현 대상으로 올린다.
- UI lane은 이 inventory를 기준으로 카드의 상태/버튼/에러 문구를 결정한다.

### Pass/Fail

| ID | Pass | Fail |
| --- | --- | --- |
| LOGIC-01 | JK action 로직과 현재 repo 로직의 차이가 파일/함수 단위로 정리된다. | "로직도 참고" 같은 추상 문장만 있다. |
| LOGIC-02 | 이미 구현된 기능과 부족한 기능이 분리된다. | 이미 있는 코드를 중복 구현한다. |
| LOGIC-03 | UI 카드가 실제 action lifecycle 상태와 연결된다. | 예쁜 카드만 생기고 실행/승인 상태와 무관하다. |
| LOGIC-04 | ambiguous/read-only/unrestricted/followup 로직이 각각 검증 항목으로 매핑된다. | 실행 모드와 후속 명령이 화면 문구 수준에 머문다. |

## Lane 2: Assistant Runbook Card UI

### 목표

챗봇 답변 첫 화면을 일반 말풍선이 아니라 운영자가 바로 판단할 수 있는 런북 카드로 보이게 한다.

### UI 구조

기본 assistant 응답은 아래 순서로 읽혀야 한다.

```text
요약
우선 확인
영향 범위
확인한 근거
원인 후보
조회 명령/절차
Action Plan
검증/롤백
추가 확인
```

카드는 아래 규칙을 따른다.

- 첫 번째 핵심 런북 카드만 열린다.
- 나머지 후보/확인 항목은 접힌 카드로 둔다.
- 명령은 dark monospace block과 copy button으로 표시한다.
- 긴 namespace/pod/action id는 chip 또는 접힘 상세로 제한한다.
- raw `ToolPlan`, `RcaContext`, source uri, internal event id는 기본 카드에 노출하지 않는다.
- 답변이 완료되면 running spinner 또는 "답변 준비 중" 상태가 남지 않아야 한다.

### 주요 구현 후보

- `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx`
- `komsco-ai-console-plugin/src/components/assistant.css`
- 이미 분리된 `AssistantProgressTimeline.tsx`, `AssistantHistoryPanel.tsx`, `assistant.types.ts`와 충돌하지 않게 최소 변경한다.

### Pass/Fail

| ID | Pass | Fail |
| --- | --- | --- |
| UI-01 | 첫 assistant 답변에 `우선 확인`, `확인한 근거`, `Action Plan`이 스캔 가능한 카드로 보인다. | 장문 말풍선 하나 또는 중복 카드 목록으로 보인다. |
| UI-02 | 명령/절차는 copy 가능한 monospace block에 있다. | 본문 텍스트에 명령이 섞여 밀린다. |
| UI-03 | 답변 완료 후 loading animation이 사라진다. | 완료된 답변 아래 spinner가 계속 움직인다. |
| UI-04 | dark theme에서 헤더 아이콘과 버튼이 보인다. | KR/EN, 전체화면, 잠금, 닫기 아이콘이 사라진다. |

## Lane 3: Expanded Assistant Context Rail

### 목표

expanded assistant는 넓은 화면을 빈 공간으로 쓰지 않고 운영 컨텍스트를 보여준다.

### 레이아웃

```text
expanded assistant
  header
  body
    chat column
    context rail
  composer
```

context rail은 아래 항목을 가진다.

- cluster health score와 갱신 시각
- 중요한 경고 3개
- 현재 분석 scope chip: cluster, namespace, workload, alert, document
- 최근 복사/조회 명령
- Action Plan 상태: 후보, 계획, 승인, 실행
- 현재 실행 모드와 capability 상태

### 반응형 기준

- 760px 미만: context rail 숨김, full-screen sheet.
- docked panel: rail 없음, 핵심 카드만 표시.
- expanded desktop: rail width 300~330px.
- 텍스트 overflow는 ellipsis 또는 wrap, 가로 스크롤 금지.

### Pass/Fail

| ID | Pass | Fail |
| --- | --- | --- |
| XR-01 | expanded에서 `chat column + context rail`이 보인다. | 넓은 화면에도 단일 컬럼만 있고 빈 공간이 크다. |
| XR-02 | context rail에 cluster health, 주요 경고, scope, Action Plan 상태가 있다. | 단순 장식 패널이거나 더미 데이터만 있다. |
| XR-03 | mobile/docked에서 UI가 겹치지 않는다. | 버튼, badge, mode toggle이 겹친다. |

## Lane 4: Action Plan Lifecycle 정규화

### 목표

운영자가 조치 카드의 상태를 보고 지금 무엇을 할 수 있는지 즉시 이해하게 한다.

### 상태 모델

UI 상태는 아래 순서를 따른다.

```text
candidate
  -> plan
  -> approval
  -> execution
  -> verification
```

각 상태의 운영자용 라벨은 아래로 고정한다.

| 내부 상태 | 운영자 라벨 | 설명 |
| --- | --- | --- |
| candidate | 조치 후보 | 근거가 수집되어 Action Plan 생성 가능 |
| plan | Action Plan 생성됨 | 대상/영향/검증/롤백 확인 필요 |
| approval | 승인 필요 또는 승인 완료 | 승인/거절 기록 가능 |
| execution | 실행 중 또는 실행 완료 | Action Executor 실행 상태 |
| verification | 검증 완료 또는 추가 확인 필요 | 실행 후 관측 결과 |

피해야 할 라벨:

- `봉인됨`
- `Sealed plan`
- `proposal waits for`
- `Conflict`
- `ExecutionRecord` 단독 노출
- `read-only`를 제품 철학처럼 보이게 하는 문구

### 실행 모드

| 모드 | v0.2.4 표현 | 동작 |
| --- | --- | --- |
| `읽기 전용` | 조회와 RCA만 수행 | Action Plan 생성/승인/실행 버튼을 만들지 않음 |
| `실행 가능` | 승인 후 실행 | Action Plan 생성 후 사용자가 승인하면 실행 |
| `실행 무제한` | 자동 승인 후 실행 가능 | capability가 켜진 경우 자동 승인/실행, 꺼진 경우 사람이 읽는 거절 사유 표시 |

### 중복 제거 기준

같은 답변 또는 같은 active conversation 안에서 아래 key가 같으면 하나의 Action Plan 카드로 합친다.

```text
namespace + targetKind + targetName + toolName + planDigest
```

`planDigest`가 아직 없으면 아래 fallback key를 쓴다.

```text
namespace + targetKind + targetName + toolName + normalizedParametersDigest
```

같은 대상/도구지만 파라미터가 다른 경우에는 별도 카드로 유지한다.

### 에러 문구

서버가 원문 에러를 반환해도 UI 기본 화면은 아래처럼 변환한다.

| 원문/상태 | 사용자 문구 |
| --- | --- |
| `Conflict` | 현재 대상 상태가 Action Plan 생성 시점과 달라 다시 확인이 필요합니다. |
| `hpa_review_required` | HPA가 연결된 대상입니다. 오토스케일러 영향 검토 후 승인해야 합니다. |
| `controller_owner_required` | 직접 재생성할 수 없는 Pod입니다. 상위 컨트롤러를 확인해야 합니다. |
| `reauth_required` | 인증 정보가 만료되었습니다. 콘솔을 새로고침하거나 다시 로그인해야 합니다. |
| policy disabled | 현재 설치 설정에서 실행 기능이 비활성화되어 있습니다. |

## Lane 5: Typed Action Verification Gate

### 목표

기능이 있다는 주장 대신, 자연어 요청이 typed action과 실행 검증으로 이어지는지를 테스트 이름과 결과로 남긴다.

### 우선 시나리오

| ID | 요청 유형 | 기대 |
| --- | --- | --- |
| VA-01 | Deployment restart | `rollout_restart_deployment` plan 생성, 승인 후 실행, annotation 또는 rollout 상태 검증 |
| VA-02 | Deployment scale | `set_replicas_within_bounds` plan 생성, HPA 있으면 review required |
| VA-03 | CrashLoopBackOff Pod 교체 | controller-owned unhealthy Pod만 `evict_one_unhealthy_controller_owned_pod` 가능 |
| VA-04 | rollback 요청 | `rollback_deployment_to_revision` intent와 target kind 검증 |
| VA-05 | HPA bounds 변경 | `set_hpa_bounds` intent와 min/max validation |
| VA-06 | 대상 불명확한 mutation | OLS 일반 답변으로 넘기지 않고 Gateway에서 중단 |
| VA-07 | read-only RCA | mutation record 없이 evidence/RCA만 생성 |
| VA-08 | 3/4/5턴 `진행해` | 최근 실행 가능한 사용자 요청만 복원 |

### 검증 명령

로컬 구현 후 우선 아래 범위로 검증한다.

```bash
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py -k "agentic_action or action_plan or unrestricted or followup"
python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/komsco_ai_gateway/action_executor.py
```

프론트 구현 후 아래를 실행한다.

```bash
cd komsco-ai-console-plugin
node .yarn/releases/yarn-4.13.0.cjs typecheck
node .yarn/releases/yarn-4.13.0.cjs build-dev
```

브라우저 검증은 UI 변경이 들어간 뒤 실행한다. WSL CPU/팬 부하 가능성이 있으므로 실행 전 사용자에게 알린다.

## 구현 순서

### Step 0: 기준 고정

```bash
git status --short
git branch --show-current
git rev-parse --short HEAD
```

완료 조건:

- 기준 branch/head가 구현 보고에 남는다.
- 기존 dirty worktree 파일을 무리하게 정리하지 않는다.
- 보호 산출물 목록을 확인한다.

### Step 1: 문서 계약 추가

대상:

```text
docs/Ver.0.2.4/README.md
docs/Ver.0.2.4/aiops-jk-reference-absorption-plan.md
```

완료 조건:

- JK 참고 산출물과 흡수 범위가 문서에 있다.
- 회사 서버 배포 제외가 명시되어 있다.
- Acceptance Criteria가 pass/fail로 있다.

### Step 2: JK backend/action logic inventory

권장 브랜치:

```text
feature/v0.2.4-action-logic-inventory
```

변경 대상:

```text
docs/Ver.0.2.4/aiops-jk-logic-inventory.md
```

확인 대상:

```text
komsco-ai-gateway/komsco_ai_gateway/main.py
komsco-ai-gateway/komsco_ai_gateway/aiops_core.py
komsco-ai-gateway/komsco_ai_gateway/action_executor.py
komsco-ai-gateway/komsco_ai_gateway/security.py
komsco-ai-gateway/tests/test_health.py
scripts/evaluate-aiops-actions-e2e.py
```

구현 내용:

- JK 브랜치와 현재 repo의 자연어 action, registry, target resolution, approval/execution, test coverage를 비교한다.
- `already covered`, `partial`, `missing`, `do not copy`로 나눈다.
- UI lane에서 필요한 상태/문구/dedupe 기준을 logic inventory에서 가져오게 한다.

검증:

```bash
git diff --check
rg -n "already covered|partial|missing|do not copy" docs/Ver.0.2.4/aiops-jk-logic-inventory.md
```

### Step 3: assistant runbook card UI

권장 브랜치:

```text
feature/v0.2.4-assistant-runbook-cards
```

변경 대상 후보:

```text
komsco-ai-console-plugin/src/components/AssistantLauncher.tsx
komsco-ai-console-plugin/src/components/assistant.css
```

구현 내용:

- 기존 답변 renderer를 유지하되, 구조화 가능한 답변은 런북 카드로 감싼다.
- 카드 heading, severity/scope chip, command block, action buttons, evidence detail toggle을 추가한다.
- 기존 markdown fallback은 유지한다.
- spinner 종료 조건을 점검해 completed answer에는 running indicator가 남지 않게 한다.
- dark theme icon/button 색상 token을 보강한다.

검증:

```bash
git diff --check
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
```

### Step 4: expanded context rail

권장 브랜치:

```text
feature/v0.2.4-assistant-context-rail
```

구현 내용:

- expanded mode에서만 오른쪽 context rail을 렌더링한다.
- rail data는 기존 cluster summary, runtime status, records, copied commands, current page context에서 가져온다.
- rail이 없어도 docked panel 동작은 바꾸지 않는다.
- 760px 미만에서는 rail을 숨긴다.

검증:

- expanded desktop에서 rail 표시.
- docked/mobile에서 rail 미표시.
- 가로 스크롤 없음.

### Step 5: Action Plan lifecycle/dedupe/error wording

권장 브랜치:

```text
feature/v0.2.4-action-lifecycle-polish
```

구현 내용:

- Action Plan 카드 상태를 `candidate -> plan -> approval -> execution -> verification`로 정리한다.
- `봉인됨`, `Conflict`, raw internal 상태를 사용자 문구로 변환한다.
- 동일 target/tool/parameter action 중복 표시를 접거나 병합한다.
- 실행 무제한 모드에서 capability가 켜진 경우 자동 승인/실행 경로를 명확히 표시한다.

검증:

- 같은 문제 하나를 물었을 때 같은 대상의 카드가 2~3개 중복 표시되지 않는다.
- Conflict 원문 대신 재확인 필요 문구가 보인다.
- 승인/거절/실행 버튼이 좁은 패널에서 겹치지 않는다.

### Step 6: typed action verification gate

권장 브랜치:

```text
feature/v0.2.4-action-verification-gate
```

구현 내용:

- 기존 `tests/test_health.py`에서 이미 있는 agentic/action/followup 테스트를 v0.2.4 acceptance criteria와 연결한다.
- live e2e는 회사 서버가 아니라 로컬/OKD 개발 namespace 기준으로만 별도 실행한다.
- JK `evaluate-aiops-actions-e2e.py`는 직접 복사하지 않고, 시나리오 구성과 결과 리포트 형식을 참고한다.

검증:

```bash
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py -k "agentic_action or action_plan or unrestricted or followup"
```

## Acceptance Criteria

| ID | Pass/Fail 기준 | 측정 방법 | Evidence |
| --- | --- | --- | --- |
| V024-01 | 챗봇 답변 첫 화면이 운영 런북 카드 구조로 보인다. | 브라우저/DOM 확인 | docked/expanded screenshot |
| V024-02 | Action Plan 카드에 대상, 근거, 영향, 승인 조건, 검증, 롤백이 보인다. | UI text check | typecheck + browser |
| V024-03 | 중복 plan/action 카드가 같은 target/tool에 반복 표시되지 않는다. | unit/static check | pytest 또는 verifier |
| V024-04 | 실행 무제한 모드는 capability가 켜진 경우 자동 승인/실행 경로를 타고, 꺼진 경우 이유를 표시한다. | Gateway/UI flow check | pytest + UI check |
| V024-05 | OLS/Gateway/Action Executor 책임 경계가 문서와 코드 라벨에서 충돌하지 않는다. | source grep | contract check |
| V024-06 | 다크 테마에서 모든 헤더 아이콘과 상태 버튼이 보인다. | browser visual check | screenshot |
| V024-07 | 배포 관련 Helm/OLM/회사 서버 리소스는 이번 작업에서 변경하지 않는다. | `git diff --name-only` | diff evidence |
| V024-08 | read-only RCA 요청은 mutation record 없이 evidence/RCA만 만든다. | Gateway test | pytest |
| V024-09 | ambiguous mutation 요청은 OLS 일반 답변으로 빠지지 않고 대상 부족으로 중단된다. | Gateway test | pytest |
| V024-10 | 3/4/5턴 `진행해`는 가장 최근 실행 가능한 사용자 요청만 복원한다. | Gateway stream test | pytest/SSE event |
| V024-11 | JK backend/action logic inventory가 작성되고, already covered/partial/missing/do not copy가 분리된다. | doc grep/source comparison | inventory doc |
| V024-12 | UI Action Plan 카드의 상태/버튼/에러 문구가 실제 lifecycle 로직에 매핑된다. | source grep + UI check | typecheck/browser |

## 완료 보고 형식

구현자가 각 lane을 끝낼 때 아래 형식으로 보고한다.

```text
현재 판단:
  무엇이 구현됐고 무엇이 아직 남았는지

핵심 근거:
  branch, head sha, diff 대상, 검증 명령

바뀐 파일:
  파일 목록

검증 결과:
  pass/fail, 실패 시 정확한 에러

다음 행동:
  다음 lane 또는 blocker
```

## 보호 범위

이번 v0.2.4 문서/구현 계획에서 아래는 수정하지 않는다.

```text
docs/version-progress-book.html
docs/aiops-beginner-guide.html
docs/Ver.0.1.8/aiops-llm-strategy-brief.html
evals/aiops-scenarios/*
company server deployment resources
OLM publish/install scripts unless a later deployment task explicitly asks
```

## 최종 판정

JK 브랜치에서 배울 핵심은 "예쁜 화면"보다 아래 다섯 가지이다.

```text
1. 자연어 운영 요청을 typed action lifecycle로 연결한다.
2. 챗봇 답변을 운영 런북 카드로 보이게 한다.
3. expanded 화면은 context rail로 운영 상황을 고정한다.
4. OLS/Gateway/Action Executor 책임 경계를 제품 언어로 일관되게 말한다.
5. typed action은 시나리오와 verifier로 증명한다.
```

이 네 가지를 흡수하면 현재 우리 제품의 기능량은 유지하면서, 선임이나 동료가 봤을 때 허접해 보이는 지점인 UI 첫인상, Action Plan 중복/혼선, 실행 경계 설명 부족을 줄일 수 있다.
