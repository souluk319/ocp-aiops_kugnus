# v0.2.7 Chatbot / Tool Plan / UI Review Report

## 기준

- Branch: `feature/v0.2.7-chatbot-jk-ui`
- Current inspected HEAD: `b78a107`
- Fixed PDF source: `docs/AIOps-For-OCP.pdf`
- PDF SHA-256: `193cf62eea36bea9cf7d370203ac413fab6a9ef044a89d8e121f93e1df6a7cb5`
- Scope: local OKD console `http://localhost:9000`, local gateway `http://127.0.0.1:18080`, local portal source/build.
- Out of scope: company server deploy, OLM publish/install, catalog mutation.

## PDF 기준 계약

`docs/AIOps-For-OCP.pdf`에서 이번 챗봇/Action/UI 검수에 직접 연결되는 계약은 다음이다.

- page 3: Lightspeed는 실시간 클러스터 관측과 AI 응답 기반을 제공하고, AI Gateway는 UserToken 경계, RBAC 검증, 민감정보 제거, 감사로그, RAG/Tool 연동을 담당한다.
- page 4: 목표 흐름은 `Detect -> Ask -> Collect Evidence -> RCA -> Approve & Execute -> Audit & Report`이다.
- page 6-7: AIOps Agentic Model이 질문의 OS Context를 판단하고 Tool Plan JSON을 생성하며, Tool Adapter와 OpenShift Lightspeed/MCP 조회 결과를 RCA JSON과 최종 답변으로 통합한다.
- page 11: 기본 관측은 읽기 전용이며, 위험 작업은 자연어 명령을 바로 실행하지 않고 Action Proposal로 변환한다. Action Executor는 별도 ServiceAccount와 Typed Action만 사용한다.
- page 14-15: v1.0은 read-only observability/RCA이고, controlled action은 Action Proposal, Sealed Action Plan, Approval Decision, Action Executor, 감사 원장으로 확장된다.

## 변경 요약

- Assistant 제품 표면 라벨을 `AIOps`로 정리했다.
- 답변 본문/미리보기/진행 상태에서 `OpenShift Lightspeed`, `KOMSCO AI AGENT`가 노출되지 않도록 display-only 정규화 helper를 분리했다.
- `assistant.display.ts`를 추가해 제품명 표시/미리보기 로직을 `AssistantLauncher.tsx`에서 분리했다.
- 기본 실행 모드를 PDF의 read-only first 계약에 맞춰 `read-only`로 변경했다.
- 알림/이벤트와 보고서의 한글 배지 정렬을 `inline-flex`, `align-items: center`, 균형 padding 기준으로 수정했다.
- OKD 내장 포털과 독립 포털 소스의 배지 CSS를 같이 맞췄다.
- 실행 capability tooltip/비활성 사유에서 `mutation gate disabled`, `Action Executor URL not configured` 같은 raw 내부 문구가 나오지 않도록 운영자용 한국어 문구로 바꿨다.
- 기존 통합 UI verifier가 `Sealed plan`, `Action Executor URL not configured` 같은 낡은 영어 문구를 기대하던 부분을 현재 한국어 UI 계약으로 갱신했다.
- `봉인 계획`, `승인 봉인`, `unrestricted command gate`처럼 운영자 기본 화면에 어색하게 보일 수 있는 표현을 `승인 필요 계획`, `승인 검증`, `실행 무제한 capability` 기준으로 정리했다.
- `scripts/verify-v027-ui-balance.cjs`를 추가해 9000 대시보드/알림/보고서와 Assistant docked/fullscreen의 badge/chip 정렬, clipping, raw 내부 문구, horizontal overflow를 자동 검사한다.
- `AssistantLauncher.tsx`에서 실행 mode/capability/lifecycle summary 계산 helper를 `assistant.actionState.ts`로 분리했다. JSX 구조는 그대로 두고 순수 계산 로직만 이동해 리팩터링 위험을 낮췄다.
- `AssistantLauncher.tsx`에서 Action record, sealed plan, approval, execution outcome, dedupe helper를 `assistant.actionRecords.ts`로 분리했다. Action Plan 렌더 JSX와 사용자 interaction은 그대로 두고 데이터 계산 로직만 이동했다.
- `AssistantLauncher.tsx`에서 localStorage 기반 대화 복원, active conversation 저장, UI 언어 저장, history time/title helper를 `assistant.storage.ts`로 분리했다. 저장/복원 계약은 유지하고 렌더링과 네트워크 흐름은 건드리지 않았다.
- `AssistantLauncher.tsx`에서 raw Tool Plan을 화면용 footer로 변환하는 parser와 실행 정책/플래너 라벨 helper를 `assistant.toolPlan.ts`로 분리했다. Tool Plan footer 렌더와 stream attach 흐름은 유지했다.
- `AssistantLauncher.tsx`에서 Evidence footer parser, evidence label/status label, RCA rail evidence count helper를 `assistant.evidence.ts`로 분리했다. 근거 footer 렌더와 우측 context rail 표시 흐름은 유지했다.
- `AssistantEvidenceFooter.tsx`를 추가해 답변 하단 근거 footer JSX를 `AssistantLauncher.tsx` 밖으로 분리했다. 메시지 본문 렌더 흐름은 `<AssistantEvidenceFooter />`로 연결하고 UI 클래스/문구/data attribute 계약은 유지했다.
- `AssistantToolPlanFooter.tsx`를 추가해 답변 하단 Tool Plan footer JSX를 `AssistantLauncher.tsx` 밖으로 분리했다. `조회 계획`, 실행 정책 badge, planner 설명, 감사용 JSON, 복사 버튼 UI 계약은 유지했다.
- `AssistantActionRecords.tsx`를 추가해 Action Plan stage dots, plan summary, 답변 하단 직접 조치 카드/버튼 JSX를 `AssistantLauncher.tsx` 밖으로 분리했다. rail action row와 answer action card가 같은 stage/summary 표시 컴포넌트를 재사용한다.
- `verify-v027-expanded-assistant-rail.cjs`의 초기 DOM 접근을 null-safe하게 보강했다. CDP가 `documentElement` 생성 전 poll을 실행해도 실패하지 않고 ready=false로 계속 기다린다.
- `verify-v027-expanded-assistant-rail.cjs`를 API-DOM 대조 방식으로 보강했다. 브라우저 세션 안에서 `/v1/cluster/summary`, `/v1/aiops/status`를 다시 호출하고, health score, Node/Operator 집계, OCP version, 첫 노드명, 최근 진단 수, 승인·실행 기록 수가 오른쪽 context rail에 같은 값으로 표시되는지 확인한다.
- `verify-v027-toolplan-chat-ui.cjs`에 Tool Plan 전용 답변이 무관한 Action Plan 카드를 표시하지 않는 계약을 추가했다. 같은 message stack 안의 `.komsco-ai__answer-actions`가 보이면 실패하도록 해, 조회 전용 Tool Plan과 기존 Action record가 섞이는 회귀를 막는다.
- `evaluate-aiops-actions-e2e.py`에 `--plan-only` 안전 모드를 추가했다. 실제 live E2E가 생성/변경/삭제할 임시 RBAC, Deployment, HPA, pod eviction, host diagnostic job, action lifecycle을 oc/API 호출 없이 먼저 리포트로 확인할 수 있다.
- `evaluate-aiops-actions-e2e.py`에 `--confirm-live-mutations` 확인 플래그를 추가했다. `--plan-only`가 아닌 live mode는 이 플래그가 없으면 oc/gateway 호출 전 `live-blocked` 리포트를 남기고 종료한다.
- 확장 모드 헤더 하단에서 실행 모드 토글이 발광선에 걸쳐 보이던 부분을 fullscreen 전용 CSS로 보정했다. 기능/상태 흐름은 그대로 두고 헤더 상태줄 위치와 토글 높이만 미세 조정했다.
- Tool Plan/Action focused pytest에서 발견된 OLM 상태 계약 회귀를 수정했다. `mode=evidence-check`인데 `capabilities.mutations=true`인 잘못된 CR 설정은 이제 `SafetyModeReady=False`, `ReadOnlyCapabilityMismatch`, phase `Progressing`으로 표시된다.

## 5회 이상 검수 결과

| Review | 담당/방식 | Pass/Fail | Evidence | Current gap |
| --- | --- | --- | --- | --- |
| R1 | Contract Reviewer subagent | Partial Pass -> Fixed UI label | Tool Plan, Action Proposal, Sealed Plan, Approval, Execution Record 계약 확인. deterministic gateway planner와 action registry가 동작함. Tool Plan footer에 `Gateway 안전 플래너` 출처와 설명을 표시하도록 수정. | 실제 model-generated Tool Plan까지 구현한 것은 아니며, 현재 실행 가능한 Tool Plan은 deterministic gateway planner 기반이다. |
| R2 | UI Reviewer subagent | Fail -> Fixed | event/report badge가 `padding-top` 기반으로 위쪽 쏠림 가능하다고 지적. 이후 `status-badge`, report severity, runbook/evidence em badge를 flex center로 수정. | 더 넓은 모바일 visual regression은 별도 Cypress/Playwright spec 필요. |
| R3 | Refactor/Test Reviewer subagent | Partial Pass | `AssistantLauncher.tsx`, `assistant.css`, `PortalApp.tsx`, standalone `App.tsx` oversized 확인. smoke/typecheck/action lifecycle 검증 후보 확인. | 큰 파일은 아직 큼. 이번 변경은 `assistant.display.ts` 분리까지만 수행. |
| R4 | Automated Gateway/Action test | Pass | `py_compile` pass, wide action pytest `37 passed`, selected default-mode action pytest `21 passed`, RCA parser `20 passed`. | 실제 mutation 실행은 intentionally 하지 않음. |
| R5 | Live Action lifecycle | Pass | `/tmp/aiops-live-action-lifecycle-v027-final.json`: `11 passed`, `0 failed`, `mutationExecuted=false`, gateway `http://127.0.0.1:18080`. | live verifier가 Action records를 생성하므로 반복 실행 시 화면 record count는 증가함. |
| R6 | Browser UI evidence | Pass | 9000 Alerts/Reports badge computed style: `display:flex/inline-flex`, `alignItems:center`, no horizontal overflow. Assistant expanded rail: `92 / 100`, `Node 1/1`, `Operator 34/34`, action lifecycle DOM present, old product labels absent. | 추가 모바일 폭 visual regression spec은 별도 필요. |
| R7 | Standalone direct route evidence | Pass | 5174 `/dashboards/aiops/alerts` direct URL opens `알림 & 이벤트`; `/dashboards/aiops/reports` direct URL opens `보고서`; both keep centered badges and avoid dashboard fallback. | 실제 배포 도메인 `https://aiops.cywell.co.kr` route 확인은 배포 lane에서 수행. |
| R8 | Expanded Assistant rail CDP verifier | Pass | `scripts/verify-v027-expanded-assistant-rail.cjs`: surface `1408px`, panel/workspace `1406px`, rail `316px`; `api.ocp.cywell.server`, `92 / 100`, `Node 1/1`, `Operator 34/34`, action records 확인; document/body/surface/workspace/rail overflow 모두 정상; `Conflict`, `Action Executor URL not configured`, `mutation gate disabled` 같은 raw 문구 미노출. Screenshot: `/tmp/v027-expanded-assistant-rail.png`. | Cypress Electron은 WSL 런타임에 `libnspr4.so`가 없어 실행하지 못함. |
| R9 | Whole UI badge/chip balance verifier | Fail -> Fixed -> Pass | `scripts/verify-v027-ui-balance.cjs` 최초 실행에서 dashboard `hero-pill`, `status-badge`, fullscreen Action Plan summary chip이 `display:block`으로 잡힘. CSS 수정 후 verifier를 desktop/mobile x light/dark matrix로 확장했고, 9000 dashboard/alerts/reports + Assistant docked/fullscreen 36 contexts 모두 `issueCount=0`, `iconIssueCount=0`, `rawInternalTerms=[]`, overflow OK. | 실제 사용자 Chrome/OCP theme 저장값 기반 visual review는 별도 수동 확인이 필요할 수 있다. |
| R10 | Safe refactor pass | Pass | `assistant.actionState.ts` 추가. `AssistantLauncher.tsx`는 `6771`줄에서 `6652`줄로 감소. Refactor 후 `typecheck`, `build-dev`, expanded rail verifier, UI balance matrix verifier가 모두 통과. | `AssistantLauncher.tsx`, `assistant.css`, `PortalApp.tsx`, standalone `App.tsx`는 여전히 oversized라 후속 분리가 필요하다. |
| R11 | Safe refactor pass | Pass | `assistant.actionRecords.ts` 추가. Action record/plan/approval/execution outcome/dedupe helper를 분리했고 `AssistantLauncher.tsx`는 `6652`줄에서 `6281`줄로 감소. Refactor 후 `git diff --check`, `typecheck`, `build-dev`, expanded rail verifier, UI balance matrix verifier가 모두 통과. | `AssistantLauncher.tsx`는 아직 6천 줄대라 render helper/history/action UI 추가 분리가 필요하다. |
| R12 | Safe refactor pass | Pass | `assistant.storage.ts` 추가. localStorage 저장/복원, conversation title, history time, UI language persistence를 분리했고 `AssistantLauncher.tsx`는 `6281`줄에서 `6037`줄로 감소. Refactor 후 `git diff --check`, `typecheck`, `build-dev`, expanded rail verifier, UI balance matrix verifier가 모두 통과. | `AssistantLauncher.tsx`는 아직 6천 줄대라 render helper와 message/action UI 추가 분리가 필요하다. |
| R13 | Safe refactor pass | Pass | `assistant.toolPlan.ts` 추가. raw Tool Plan parser, execution policy label, planner label/summary helper를 분리했고 `AssistantLauncher.tsx`는 `6037`줄에서 `5939`줄로 감소. Refactor 후 `git diff --check`, `typecheck`, `build-dev`, expanded rail verifier, UI balance matrix verifier가 모두 통과. | Tool Plan footer JSX는 아직 Launcher 내부에 남아 있어 추후 작은 presentational component로 분리 가능하다. |
| R14 | Expanded rail/context evidence review | Pass | `assistant.evidence.ts` 추가. Evidence footer parser/label/status label/RCA rail evidence count helper를 분리했고 `AssistantLauncher.tsx`는 `5939`줄에서 `5756`줄로 감소. Expanded Assistant verifier에서 `api.ocp.cywell.server`, `92 / 100`, `Node 1/1`, `Operator 34/34`, 승인·실행 기록과 rail overflow OK를 확인했다. `git diff --check`, `typecheck`, `build-dev`, UI balance 36 contexts도 통과. | Evidence footer JSX는 아직 Launcher 내부에 남아 있어 추후 작은 presentational component로 분리 가능하다. |
| R15 | Safe refactor pass | Pass | `AssistantEvidenceFooter.tsx` 추가. 답변 하단 Evidence footer JSX를 분리했고 `AssistantLauncher.tsx`는 `5756`줄에서 `5643`줄로 감소. Refactor 후 `git diff --check`, `typecheck`, `build-dev`, expanded rail verifier, UI balance 36 contexts가 모두 통과했다. | Tool Plan footer JSX와 Action Plan answer action JSX는 아직 Launcher 내부에 남아 있어 후속 분리 후보다. |
| R16 | Safe Tool Plan UI refactor pass | Pass | `AssistantToolPlanFooter.tsx` 추가. 답변 하단 Tool Plan footer JSX를 분리했고 `AssistantLauncher.tsx`는 `5643`줄에서 `5538`줄로 감소. Refactor 후 `git diff --check`, `typecheck`, `build-dev`, expanded rail verifier, UI balance 36 contexts가 모두 통과했다. 첫 expanded rail verifier는 CDP 초기 DOM 타이밍으로 `documentElement` null 측정 실패가 있었고, 새 debug port `9334`에서 재검증 통과했다. | Action Plan answer action JSX와 history/action panel UI는 아직 Launcher 내부에 남아 있어 후속 분리 후보다. |
| R17 | Safe Action Plan answer UI refactor pass | Pass | `AssistantActionRecords.tsx` 추가. Action Plan stage dots, plan summary, 답변 하단 직접 조치 카드/버튼 JSX를 분리했고 `AssistantLauncher.tsx`는 `5537`줄에서 `5375`줄로 감소. Refactor 후 `typecheck`, `build-dev`, expanded rail verifier(debug port `9335`), UI balance 36 contexts가 모두 통과했다. | history/action panel UI와 rail action row wrapper는 아직 Launcher 내부에 남아 있어 후속 분리 후보다. |
| R18 | Verifier robustness review | Pass | `verify-v027-expanded-assistant-rail.cjs` 초기 poll과 metrics 수집의 `document.body`/`document.documentElement` 접근을 null-safe하게 보강했다. `node --check`, `git diff --check`, expanded rail verifier 기본 port, expanded rail verifier debug port `9336` 모두 통과했다. | UI balance verifier는 이번 변경 대상이 아니므로 재실행하지 않았다. |
| R19 | Expanded Assistant live rail/UI review | Pass | 확장 모드 우측 context rail이 실제 콘솔 프록시/Gateway 데이터를 반영하는지 재확인했다. `AIOPS_VIEWPORT_SIZE=1440,900`과 `1920,1080` 모두 `api.ocp.cywell.server`, `92 / 100`, `Node 1/1`, `Operator 34/34`, action records 확인. document/body/surface/workspace/rail overflow 모두 OK. Header 실행 모드 토글이 하단 발광선에 붙어 보이는 문제를 fullscreen CSS로 보정했다. | shell에서 `oc whoami -t` 토큰은 없어서 direct `18080` curl 비교는 수행하지 못했다. 브라우저 콘솔 프록시 경로의 실제 렌더 데이터로 검증했다. |
| R20 | Tool Plan/Action lifecycle contract review | Fail -> Fixed -> Pass | Focused pytest 최초 실행에서 `test_olm_operator_status_rejects_evidence_check_mode_with_mutations`가 실패했다. 원인은 `safety_mode_condition`이 `evidence-check + mutations=true` 설정을 Ready로 통과시킨 것. `komsco_ai_gateway/olm_operator.py`에 `ReadOnlyCapabilityMismatch` 조건을 추가했고, 단일 회귀 테스트 `1 passed`, focused action pytest `66 passed, 155 deselected`, RCA parser `20 passed`, live lifecycle verifier `11 passed, 0 failed`, `mutationExecuted=false`를 확인했다. | 실제 deployment/HPA/eviction mutation E2E(`scripts/evaluate-aiops-actions-e2e.py`)는 클러스터 변경 범위라 이번 자동 실행에서는 제외했다. 별도 승인 후 실행 대상이다. |
| R21 | Expanded Assistant API-DOM rail contract | Pass | `scripts/verify-v027-expanded-assistant-rail.cjs`를 API-DOM 대조 방식으로 보강했다. 1440x900, 1920x1080 모두 브라우저 콘솔 프록시가 받은 API snapshot(`apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=6`)과 오른쪽 context rail 텍스트가 일치했다. document/body/surface/workspace/rail horizontal overflow 모두 OK. Screenshots: `/tmp/v027-expanded-assistant-rail-livecheck-1440.png`, `/tmp/v027-expanded-assistant-rail-livecheck-1920.png`. | 실제 사용자 Chrome 수동 드래그/스크롤 감각까지는 자동 검증하지 않았다. 이번 검증은 headless Chrome DOM/스크린샷 기준이다. |
| R22 | Tool Plan chat UI isolation contract | Pass | `scripts/verify-v027-toolplan-chat-ui.cjs`를 강화해 Tool Plan 전용 질문(`clusteroperator 상태 확인해줘...`)의 같은 message stack 안에 `.komsco-ai__answer-actions`가 보이면 실패하도록 했다. 9000 콘솔에서 실행 결과 `answerActionVisible=false`, `answerActionText=""`, default/opened 상태 모두 overflow 0, raw internal terms 미노출, JSON detail closed를 확인했다. Screenshot: `/tmp/v027-toolplan-chat-ui-r22.png`. | 실제 mutation Action Plan 생성/승인/실행 UI는 별도 scenario에서 검증해야 한다. 이번 검증은 조회 전용 Tool Plan UI 격리 계약이다. |
| R23 | Action E2E safety/preflight contract | Pass | `scripts/evaluate-aiops-actions-e2e.py --plan-only` 추가 후 실행. `/tmp/komsco-ai-actions-e2e-plan-v027-r23.json`에서 `clusterCallsExecuted=false`, `wouldMutateClusterInLiveMode=true`, planned tools `rollout_restart_deployment`, `set_replicas_within_bounds`, `rollback_deployment_to_revision`, `set_hpa_bounds`, `evict_one_unhealthy_controller_owned_pod`, `node_os_readonly_triage` 확인. 이어서 비파괴 live lifecycle verifier `/tmp/aiops-live-action-lifecycle-v027-r23.json`은 `11 passed, 0 failed`, `mutationExecuted=false`, `executeEndpointOnlyRejectedRequests=true`. | live mutation E2E는 실제 임시 RBAC/Deployment/HPA 생성, patch/scale/rollback/evict, cleanup을 수행하므로 별도 명시 승인 후 실행해야 한다. |
| R24 | Action E2E live confirmation guard | Pass | `scripts/evaluate-aiops-actions-e2e.py` live mode에 `--confirm-live-mutations`를 필수화했다. 플래그 없이 실행하면 return code `2`, report `/tmp/komsco-ai-actions-e2e-blocked-v027-r24b.json`, `mode=live-blocked`, `clusterCallsExecuted=false`, `mutationExecuted=false`, error `live action e2e requires --confirm-live-mutations`. `--plan-only` report `/tmp/komsco-ai-actions-e2e-plan-v027-r24.json`는 recommended live command에 `--confirm-live-mutations`를 포함한다. 비파괴 lifecycle verifier `/tmp/aiops-live-action-lifecycle-v027-r24.json`는 `11 passed, 0 failed`. | 실제 live mutation E2E 자체는 아직 승인 없이 실행하지 않았다. 이제 실행하려면 plan-only 검토 후 명시 플래그가 필요하다. |
| R25 | Expanded Assistant current rail reality/UI check | Pass | 1440x900, 1920x1080에서 확장 챗봇 우측 rail을 재검증했다. 브라우저 프록시 API snapshot과 rail DOM이 모두 일치했다: `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`. document/body/surface/workspace/rail horizontal overflow 모두 OK. Screenshots: `/tmp/v027-expanded-assistant-rail-current-1440.png`, `/tmp/v027-expanded-assistant-rail-current-1920.png`. | 우측 rail에 action record가 18건까지 쌓여 있어 하단 `승인·실행` 카드 목록은 세로 스크롤이 길다. 데이터 반영/가로 UI 문제는 아니지만, 후속 UX에서는 최신/대표 plan만 기본 노출하고 나머지는 접는 방식이 더 낫다. |
| R26 | Action E2E non-mutating preflight | Pass | `scripts/evaluate-aiops-actions-e2e.py --preflight-only`를 추가하고 실행했다. gateway probe 제외 preflight는 `/tmp/komsco-ai-actions-e2e-preflight-skip-gateway-v027-r25.json`에서 `14 passed, 0 failed`, `clusterCallsExecuted=false`, `mutationExecuted=false`. gateway probe 포함 preflight는 `/tmp/komsco-ai-actions-e2e-preflight-v027-r25.json`에서 `14 passed, 0 failed`, `gatewayProbeOk=true`, `healthz=ok`, capabilities `mutationsEnabled=true`, `recordStoreEnabled=true`, `actionExecutorConfigured=true`, `diagnosticsEnabled=true`. | 실제 live mutation E2E는 아직 실행하지 않았다. 환경/권한/gateway capability는 준비됐지만, 임시 RBAC/Deployment/HPA 생성과 patch/scale/rollback/evict가 포함되므로 `--confirm-live-mutations` 명시 승인 후에만 실행한다. |
| R27 | Safe conversation rail refactor | Pass | `AssistantConversationRail.tsx`를 추가해 확장 챗봇 우측 rail의 `대화 요약`, `질문·답변 타임라인`, `저장된 리포트` UI를 `AssistantLauncher.tsx` 밖으로 분리했다. `AssistantLauncher.tsx`는 `5414`줄에서 `5311`줄로 감소. `git diff --check`, console plugin `typecheck`, `build-dev`, expanded rail verifier, UI balance 36 contexts 모두 통과했다. Expanded rail screenshot: `/tmp/v027-expanded-assistant-rail-r27-refactor.png`. | 큰 파일은 아직 남아 있다. 다음 안전 분리 후보는 우측 rail의 cluster status/operator/action record section 또는 input toolbar이며, 상태 변경 로직과 분리 가능한 UI 조각부터 진행해야 한다. |
| R28 | Rail Action record density fix | Pass | 확장 챗봇 우측 rail의 `승인·실행` 기록은 전체 count와 records를 유지하되, 기본 화면에서는 최신 3건만 보여주고 나머지는 접힌 `나머지 N건 펼쳐보기`로 표시하도록 바꿨다. 현재 18건 record 환경에서 verifier가 `나머지 15건 펼쳐보기`를 확인했고, API-DOM snapshot은 `actionRecordCount=18` 그대로 유지됐다. `git diff --check`, console plugin `typecheck`, `build-dev`, expanded rail verifier, UI balance 36 contexts 모두 통과. Screenshot: `/tmp/v027-expanded-assistant-rail-r28-collapse.png`. | 접힌 상세를 열었을 때의 키보드/스크린리더 경험은 기본 HTML `<details>`에 의존한다. 추후 접근성 강화가 필요하면 별도 버튼+aria-expanded 제어로 확장할 수 있다. |
| R29 | Safe Action record rail component refactor | Pass | `AssistantActionRecords.tsx`에 `AssistantRailActionRecords`를 추가해 우측 rail과 좌측 조치 목록의 Action record row UI를 `AssistantLauncher.tsx` 밖으로 분리했다. `AssistantLauncher.tsx`는 `5311`줄에서 `5232`줄로 감소했고, R28의 `나머지 15건 펼쳐보기` 동작과 `actionRecordCount=18` API-DOM 계약은 유지됐다. `git diff --check`, console plugin `typecheck`, `build-dev`, expanded rail verifier, UI balance 36 contexts 모두 통과. Screenshot: `/tmp/v027-expanded-assistant-rail-r29-action-record-refactor.png`. | Action record row 표시 로직은 분리됐지만 action resolve 정책(`getAiopsRecordAction`)은 아직 Launcher에 남아 있다. 이 정책은 상태/권한과 가까워서 후속 분리 시 별도 unit test를 먼저 붙이는 편이 안전하다. |
| R30 | Safe Action resolver policy refactor | Pass | `getAiopsRecordAction`을 `AssistantLauncher.tsx`에서 `assistant.actionState.ts`로 이동했다. 실행 모드/read-only gate, proposal->plan, plan->approval/auto-execute, approval->execution 정책은 그대로 유지했고, `AssistantLauncher.tsx`는 `5232`줄에서 `5159`줄로 감소했다. `git diff --check`, console plugin `typecheck`, `build-dev`, expanded rail verifier, Tool Plan chat UI verifier, UI balance 36 contexts 모두 통과. Screenshots: `/tmp/v027-expanded-assistant-rail-r30-action-resolver.png`, `/tmp/v027-toolplan-chat-ui-r30-action-resolver.png`. | resolver는 순수 helper로 이동했지만 dedicated unit test 파일은 아직 없다. 현재 evidence는 typecheck/build + 브라우저 DOM verifier + gateway/action lifecycle tests 조합이다. 다음 단계에서 helper 단위 fixture 테스트를 추가하면 더 강해진다. |
| R31 | Expanded Assistant user-request rail check | Pass | 사용자 요청 기준으로 확장 챗봇 우측 rail을 1440x900, 1920x1080에서 재점검했다. 브라우저 프록시 API snapshot과 rail DOM이 일치했다: `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`. document/body/surface/workspace/rail horizontal overflow 모두 OK. Screenshots: `/tmp/v027-expanded-assistant-rail-user-request-1440.png`, `/tmp/v027-expanded-assistant-rail-user-request-1920.png`. | 우측 rail은 정보량 때문에 내부 세로 스크롤이 있다. 현재는 가로 확장/겹침/현실 데이터 불일치 문제는 없고, 후속 UX 후보는 세로 스크롤 밀도 조정이다. |
| R32 | Action resolver fixture verifier | Pass | `komsco-ai-console-plugin/scripts/verify-action-resolver.cjs`를 추가했다. `getAiopsRecordAction`을 fixture로 직접 호출해 proposal create-plan, read-only disabled reason, Gateway disabled reason, sealed plan approval, unrestricted auto approve/execute, existing approval dedupe, missing digest, approved decision execution, rejected approval hide, already executed hide, missing plan reason까지 12개 케이스를 확인했다. `node --check`, `node komsco-ai-console-plugin/scripts/verify-action-resolver.cjs`, `git diff --check`, console plugin `typecheck` 모두 통과했다. | 이 verifier는 UI/DOM이 아니라 action resolver 정책 단위 검증이다. 실제 live mutation E2E는 클러스터 변경을 수행하므로 별도 승인 후 `--confirm-live-mutations`로만 실행한다. |
| R33 | Safe insight rail component refactor | Pass | 확장 챗봇 우측 rail 표시를 `AssistantInsightRail.tsx`로 분리했다. `AssistantLauncher.tsx`는 `5162`줄에서 `4876`줄로 감소했고, cluster summary/API status/action records 표시 계약은 유지했다. `git diff --check`, console plugin `typecheck`, `build-dev`, expanded rail API-DOM verifier, UI balance 36 contexts, action resolver 12 fixtures 모두 통과했다. Screenshot: `/tmp/v027-expanded-assistant-rail-r33-insight-refactor.png`. | helper 함수는 아직 일부 `AssistantLauncher.tsx`에 남아 props로 전달된다. 다음 안전 리팩터링은 cluster/status display helper를 별도 helper 파일로 옮기는 단계가 될 수 있다. |
| R34 | Safe insight rail helper refactor | Pass | cluster/status 표시 helper를 `assistant.insightRailHelpers.tsx`로 분리하고 `AssistantInsightRail.tsx`가 직접 import하도록 정리했다. `AssistantLauncher.tsx`는 `4874`줄에서 `4281`줄로 감소했고, 헤더 Node/Operator chip, rail summary badge, health/node/operator/action lifecycle/record row 표시 계약은 유지했다. `git diff --check`, console plugin `typecheck`, `build-dev`, expanded rail API-DOM verifier, UI balance 36 contexts, action resolver 12 fixtures 모두 통과했다. Screenshot: `/tmp/v027-expanded-assistant-rail-r34-helper-refactor.png`. | 이번 단계는 표시 helper 분리이며 사용자 흐름 변경은 없다. `AssistantLauncher.tsx`는 여전히 큰 파일이므로 다음 후보는 input toolbar/send flow 또는 message rendering helper의 추가 분리다. |
| R35 | Insight rail helper fixture verifier | Pass | `komsco-ai-console-plugin/scripts/verify-insight-rail-helpers.cjs`를 추가했다. `formatSummaryTime`, `getClusterHost`, CPU/memory 사용량 포맷, node/operator compact status, health tone, status tag, header/rail badge text, execution capability badges, action lifecycle data attributes, record row fallback까지 33개 fixture를 검증한다. `node --check`, `verify-insight-rail-helpers`, action resolver 12 fixtures, `git diff --check`, console plugin `typecheck`, `build-dev`, expanded rail API-DOM verifier 모두 통과했다. Screenshot: `/tmp/v027-expanded-assistant-rail-r35-helper-verifier.png`. | 이 verifier는 helper 계약 단위 테스트다. 전체 36-context UI balance는 R34에서 통과했고, 이번 R35에서는 expanded rail API-DOM verifier로 화면 경로를 확인했다. |
| R36 | Fixed PDF contract verifier | Pass | `scripts/verify-v027-fixed-pdf.py`를 추가했다. `docs/AIOps-For-OCP.pdf`와 `docs/Ver.0.2.5/AIOps-For-OCP.pdf`가 동일 SHA-256 `193cf62eea36bea9cf7d370203ac413fab6a9ef044a89d8e121f93e1df6a7cb5`인지 확인하고, fixed PDF 16페이지, 공식 기준 PDF `docs/Komsco_ai_agent_final.pdf` 14페이지, `AIOps for OCP`, `OpenShift Lightspeed`, `AI Gateway`, `UserToken`, `RBAC`, `Action Executor`, `Tool Plan JSON`, `RCA JSON` 등 핵심 문구 추출 가능 여부를 검증한다. `python3 -m py_compile scripts/verify-v027-fixed-pdf.py`, `python3 scripts/verify-v027-fixed-pdf.py`, `git diff --check` 통과. | 이 verifier는 fixed PDF 기준 파일의 동일성/텍스트 계약 확인이다. PDF 레이아웃 시각 검수는 문서 자체를 수정할 때 별도 렌더링 검수로 수행한다. |

## 실행한 검증 명령

```bash
git diff --check
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
cd komsco-ai-portal && npm run build
komsco-ai-gateway/.venv/bin/python -m py_compile \
  komsco-ai-gateway/komsco_ai_gateway/main.py \
  komsco-ai-gateway/komsco_ai_gateway/aiops_core.py \
  komsco-ai-gateway/komsco_ai_gateway/action_executor.py \
  komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py \
  -k "aiops_contract or runtime_tool_plan or rca_context or actions_api or action_executor or page_context_aiops_execution_mode or unrestricted or followup or sealed_action_plan"
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py \
  -k "page_context_aiops_execution_mode or unrestricted or action_executor or actions_api or sealed_action_plan"
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_rca_result_parser.py
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py::test_olm_operator_status_rejects_evidence_check_mode_with_mutations
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py \
  -k "aiops_contract or runtime_tool_plan or action_executor or actions_api or sealed_action_plan or unrestricted or followup or approval or execution or mutation or rollback or hpa or eviction or natural_action"
python3 scripts/verify-live-action-lifecycle.py \
  --report /tmp/aiops-live-action-lifecycle-v027-final.json
python3 scripts/verify-live-action-lifecycle.py \
  --report /tmp/aiops-live-action-lifecycle-v027-r20.json
python3 scripts/verify-live-action-lifecycle.py \
  --report /tmp/aiops-live-action-lifecycle-v027-r23.json
python3 scripts/evaluate-aiops-actions-e2e.py \
  --plan-only \
  --namespace komsco-ai-dev \
  --report /tmp/komsco-ai-actions-e2e-plan-v027-r23.json
python3 scripts/evaluate-aiops-actions-e2e.py \
  --plan-only \
  --namespace komsco-ai-dev \
  --report /tmp/komsco-ai-actions-e2e-plan-v027-r24.json
python3 scripts/evaluate-aiops-actions-e2e.py \
  --namespace komsco-ai-dev \
  --report /tmp/komsco-ai-actions-e2e-blocked-v027-r24b.json
python3 scripts/evaluate-aiops-actions-e2e.py \
  --preflight-only \
  --skip-gateway-probe \
  --namespace komsco-ai-dev \
  --report /tmp/komsco-ai-actions-e2e-preflight-skip-gateway-v027-r25.json
komsco-ai-gateway/.venv/bin/python scripts/evaluate-aiops-actions-e2e.py \
  --preflight-only \
  --namespace komsco-ai-dev \
  --report /tmp/komsco-ai-actions-e2e-preflight-v027-r25.json
python3 scripts/verify-live-action-lifecycle.py \
  --report /tmp/aiops-live-action-lifecycle-v027-r24.json
python3 -m py_compile \
  scripts/evaluate-aiops-actions-e2e.py \
  scripts/verify-live-action-lifecycle.py
KOMSCO_AIOPS_SKIP_ENV_FILES=true GATEWAY_ENDPOINT=http://host.docker.internal:18080 task fe:dev
curl -s -i http://localhost:9000/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/healthz
NODE_PATH=/home/kugnus/cywell/ocp-aiops_kugnus/komsco-ai-console-plugin/node_modules \
  node scripts/verify-v027-expanded-assistant-rail.cjs
NODE_PATH=/home/kugnus/cywell/ocp-aiops_kugnus/komsco-ai-console-plugin/node_modules \
  node scripts/verify-v027-ui-balance.cjs
AIOPS_CHROME_DEBUG_PORT=9342 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-usercheck-fixed-1440.png \
  AIOPS_VIEWPORT_SIZE=1440,900 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9343 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-usercheck-fixed-1920.png \
  AIOPS_VIEWPORT_SIZE=1920,1080 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9342 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-livecheck-1440.png \
  AIOPS_VIEWPORT_SIZE=1440,900 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9343 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-livecheck-1920.png \
  AIOPS_VIEWPORT_SIZE=1920,1080 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9344 node scripts/verify-v027-ui-balance.cjs
AIOPS_CHROME_DEBUG_PORT=9346 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-toolplan-chat-ui-r22.png \
  node scripts/verify-v027-toolplan-chat-ui.cjs
AIOPS_CHROME_DEBUG_PORT=9350 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-current-1440.png \
  AIOPS_VIEWPORT_SIZE=1440,900 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9351 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-current-1920.png \
  AIOPS_VIEWPORT_SIZE=1920,1080 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
AIOPS_CHROME_DEBUG_PORT=9352 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-r27-refactor.png \
  AIOPS_VIEWPORT_SIZE=1440,900 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9353 node scripts/verify-v027-ui-balance.cjs
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
AIOPS_CHROME_DEBUG_PORT=9354 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-r28-collapse.png \
  AIOPS_VIEWPORT_SIZE=1440,900 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9355 node scripts/verify-v027-ui-balance.cjs
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
AIOPS_CHROME_DEBUG_PORT=9356 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-r29-action-record-refactor.png \
  AIOPS_VIEWPORT_SIZE=1440,900 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9357 node scripts/verify-v027-ui-balance.cjs
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
AIOPS_CHROME_DEBUG_PORT=9358 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-r30-action-resolver.png \
  AIOPS_VIEWPORT_SIZE=1440,900 \
  node scripts/verify-v027-expanded-assistant-rail.cjs
AIOPS_CHROME_DEBUG_PORT=9359 \
  AIOPS_SCREENSHOT_PATH=/tmp/v027-toolplan-chat-ui-r30-action-resolver.png \
  node scripts/verify-v027-toolplan-chat-ui.cjs
AIOPS_CHROME_DEBUG_PORT=9360 node scripts/verify-v027-ui-balance.cjs
```

## 검증 결과 요약

- `git diff --check`: PASS
- Console plugin typecheck: PASS
- Console plugin `build-dev`: PASS
- Standalone portal build: PASS. Node 18.19.1에서 Vite Node 20.19+ 권장 경고가 출력됐지만 build는 완료됨.
- Gateway py_compile: PASS
- Wide Tool Plan/Action pytest: `37 passed, 184 deselected`
- Default/read-only/action focused pytest: `21 passed, 200 deselected`
- v0.2.7 R20 focused Tool Plan/Action pytest: first run found 1 OLM safety status contract failure; after fix `66 passed, 155 deselected`.
- OLM safety status regression test: `1 passed`.
- RCA parser: `20 passed`
- RCA parser R20 rerun: `20 passed`.
- Live action lifecycle: `11 passed, 0 failed`, mutation not executed.
- Live action lifecycle R20 rerun: `11 passed, 0 failed`, `mutationExecuted=false`, `executeEndpointOnlyRejectedRequests=true`, report `/tmp/aiops-live-action-lifecycle-v027-r20.json`.
- Live action lifecycle R23 rerun: `11 passed, 0 failed`, `mutationExecuted=false`, `executeEndpointOnlyRejectedRequests=true`, report `/tmp/aiops-live-action-lifecycle-v027-r23.json`.
- Action mutation E2E plan-only: PASS, report `/tmp/komsco-ai-actions-e2e-plan-v027-r23.json`, `clusterCallsExecuted=false`, `wouldMutateClusterInLiveMode=true`.
- Live action lifecycle R24 rerun: `11 passed, 0 failed`, `mutationExecuted=false`, `executeEndpointOnlyRejectedRequests=true`, report `/tmp/aiops-live-action-lifecycle-v027-r24.json`.
- Action mutation E2E plan-only R24: PASS, report `/tmp/komsco-ai-actions-e2e-plan-v027-r24.json`, `clusterCallsExecuted=false`, `wouldMutateClusterInLiveMode=true`, recommended live command includes `--confirm-live-mutations`.
- Action mutation E2E unconfirmed live guard: PASS, return code `2`, report `/tmp/komsco-ai-actions-e2e-blocked-v027-r24b.json`, `mode=live-blocked`, `clusterCallsExecuted=false`, `mutationExecuted=false`.
- Action mutation E2E preflight: PASS. Skip-gateway report `/tmp/komsco-ai-actions-e2e-preflight-skip-gateway-v027-r25.json` returned `14 passed, 0 failed`, `clusterCallsExecuted=false`, `mutationExecuted=false`. Full gateway preflight report `/tmp/komsco-ai-actions-e2e-preflight-v027-r25.json` returned `14 passed, 0 failed`, `gatewayProbeOk=true`, `healthz=ok`, capabilities `mutationsEnabled=true`, `recordStoreEnabled=true`, `actionExecutorConfigured=true`, `diagnosticsEnabled=true`.
- Expanded Assistant current rail reality/UI check: PASS. 1440x900 and 1920x1080 both matched API snapshot to rail DOM: `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`. No horizontal overflow in document/body/surface/workspace/rail.
- Safe conversation rail refactor: PASS. `AssistantConversationRail.tsx` split out conversation summary/timeline/saved reports from `AssistantLauncher.tsx`; `AssistantLauncher.tsx` reduced to `5311` lines. `typecheck`, `build-dev`, expanded rail verifier, and UI balance 36 contexts all passed after the split.
- Rail Action record density fix: PASS. Fullscreen rail keeps `actionRecordCount=18`, but defaults to latest 3 records and a collapsed `나머지 15건 펼쳐보기` control. `typecheck`, `build-dev`, expanded rail verifier, and UI balance 36 contexts all passed.
- Safe Action record rail component refactor: PASS. `AssistantRailActionRecords` split Action record row UI into `AssistantActionRecords.tsx`; `AssistantLauncher.tsx` reduced to `5232` lines. `typecheck`, `build-dev`, expanded rail verifier, and UI balance 36 contexts all passed after the split.
- Safe Action resolver policy refactor: PASS. `getAiopsRecordAction` moved to `assistant.actionState.ts`; `AssistantLauncher.tsx` reduced to `5159` lines. `typecheck`, `build-dev`, expanded rail verifier, Tool Plan chat UI verifier, and UI balance 36 contexts all passed after the split.
- 9000 console proxy health: `HTTP/1.1 200 OK`, body `{"status":"ok"}`.
- Expanded Assistant CDP verifier: PASS, screenshot `/tmp/v027-expanded-assistant-rail.png`.
- Expanded Assistant CDP verifier robustness: PASS. 기본 debug port와 `AIOPS_CHROME_DEBUG_PORT=9336` 반복 실행 모두 통과.
- Expanded Assistant live rail/UI review: PASS. 1440x900 screenshot `/tmp/v027-expanded-assistant-rail-usercheck-fixed-1440.png`, 1920x1080 screenshot `/tmp/v027-expanded-assistant-rail-usercheck-fixed-1920.png`. Both show live rail signals and no horizontal overflow.
- Expanded Assistant API-DOM rail contract: PASS. 1440x900 screenshot `/tmp/v027-expanded-assistant-rail-livecheck-1440.png`, 1920x1080 screenshot `/tmp/v027-expanded-assistant-rail-livecheck-1920.png`. Browser API snapshot matched rail DOM: `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `diagnosticRecordCount=0`, `actionRecordCount=6`.
- Whole UI badge/chip balance verifier: PASS, `failedCount=0`, 36 contexts, desktop/mobile x light/dark, all `issueCount=0`, `iconIssueCount=0`, raw internal terms absent, document/body overflow OK.
- Whole UI badge/chip balance R21 rerun: PASS, `failedCount=0`, 36 contexts, all `issueCount=0`, `iconIssueCount=0`, raw internal terms absent, document/body overflow OK.
- Tool Plan chat UI isolation: PASS. `answerActionVisible=false`, `answerActionText=""`, default/opened overflow 0, raw internal terms absent, JSON detail closed. Screenshot `/tmp/v027-toolplan-chat-ui-r22.png`.
- Fixed PDF hash check: PASS. `docs/AIOps-For-OCP.pdf` and `docs/Ver.0.2.5/AIOps-For-OCP.pdf` both SHA-256 `193cf62eea36bea9cf7d370203ac413fab6a9ef044a89d8e121f93e1df6a7cb5`.
- Safe refactor pass: PASS. `AssistantLauncher.tsx` execution state helpers moved to `assistant.actionState.ts`; Action record/plan/approval/execution outcome helpers moved to `assistant.actionRecords.ts`; localStorage/history/language persistence helpers moved to `assistant.storage.ts`; Tool Plan parser/label helpers moved to `assistant.toolPlan.ts`; Evidence footer/parser label helpers moved to `assistant.evidence.ts`; Evidence footer JSX moved to `AssistantEvidenceFooter.tsx`; Tool Plan footer JSX moved to `AssistantToolPlanFooter.tsx`; Action Plan answer action JSX moved to `AssistantActionRecords.tsx`; `typecheck`, `build-dev`, expanded rail verifier, and UI balance verifier passed after the splits.
- Expanded Assistant current rail recheck: PASS. Screenshot `/tmp/v027-expanded-assistant-rail-user-check.png`; browser API snapshot matched fullscreen rail DOM with `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`. Document/body/surface/workspace/rail horizontal overflow all OK.
- Whole UI badge/chip balance recheck: PASS. `failedCount=0` across 36 contexts: dashboard/alerts/reports x page/docked/fullscreen x desktop/mobile x light/dark. All `issueCount=0`, `iconIssueCount=0`, raw internal terms absent, document/body overflow OK.
- Safe composer refactor and menu layer check: PASS. `AssistantComposer.tsx` split input/attachment/quick prompt/task mode/send JSX from `AssistantLauncher.tsx`; attachment size/preview helpers moved to `assistant.attachments.ts`; `AssistantLauncher.tsx` reduced to `4061` lines. `+` quick menu clipping verifier initially failed because the menu bottom was too close to the composer (`visibleAboveComposer=false`, bottom `683`), then passed after raising the surface popover offset (`visibleAboveComposer=true`, bottom `639`, `overflow=0`). Screenshot `/tmp/v027-assistant-composer-r37-fixed.png`.
- Post-composer verification: PASS. `git diff --check`, `typecheck`, `build-dev`, `node --check scripts/verify-v027-assistant-composer.cjs`, Tool Plan chat UI verifier (`/tmp/v027-toolplan-chat-ui-r37-composer-refactor.png`), expanded rail verifier (`/tmp/v027-expanded-assistant-rail-r37-composer-refactor.png`), and whole UI balance 36-context verifier all passed after the split.
- Safe message renderer refactor: PASS. `AssistantMessageContent.tsx` split attachment grid, runbook answer renderer, markdown/table/code/reference rendering, and assistant display normalization out of `AssistantLauncher.tsx`. `AssistantLauncher.tsx` reduced from `4061` to `3508` lines while preserving message labels, copy action, Action Plan buttons, Tool Plan footer, Evidence footer, and state flow in the launcher.
- Post-message-renderer verification: PASS. `git diff --check`, console plugin `typecheck`, `build-dev`, verifier syntax checks, Tool Plan chat UI verifier (`/tmp/v027-toolplan-chat-ui-r38-message-renderer-refactor.png`), expanded rail verifier (`/tmp/v027-expanded-assistant-rail-r38-message-renderer-refactor.png`), composer menu verifier (`/tmp/v027-assistant-composer-r38-message-renderer-refactor.png`), and whole UI balance 36-context verifier all passed after the split.
- Safe execution mode toggle refactor: PASS. `AssistantExecutionModeToggle.tsx` split the header execution mode controls from `AssistantLauncher.tsx`; the three required modes remain visible as `읽기 전용`, `실행 가능`, `실행 무제한`. `AssistantLauncher.tsx` reduced from `3508` to `3453` lines while preserving mode state and disabled-reason tooltip data in the caller contract.
- Post-execution-toggle verification: PASS. `git diff --check`, console plugin `typecheck`, `build-dev`, expanded rail verifier (`/tmp/v027-expanded-assistant-rail-r39-execution-toggle-refactor.png`), composer menu verifier (`/tmp/v027-assistant-composer-r39-execution-toggle-refactor.png`), and whole UI balance 36-context verifier all passed after the split.
- R40 fixed PDF/action safety rerun: PASS. `python3 scripts/verify-v027-fixed-pdf.py` confirmed fixed PDF SHA `193cf62eea36bea9cf7d370203ac413fab6a9ef044a89d8e121f93e1df6a7cb5`, fixed PDF 16 pages, official source PDF 14 pages, and required contract terms. `node komsco-ai-console-plugin/scripts/verify-action-resolver.cjs` checked 12 action resolver cases. `scripts/evaluate-aiops-actions-e2e.py --plan-only` wrote `/tmp/komsco-ai-actions-e2e-plan-v027-r40.json` with `clusterCallsExecuted=false`, planned tools `rollout_restart_deployment`, `set_replicas_within_bounds`, `rollback_deployment_to_revision`, `set_hpa_bounds`, `evict_one_unhealthy_controller_owned_pod`, `node_os_readonly_triage`, and `wouldMutateClusterInLiveMode=true`.
- R40 action preflight/guard rerun: PASS. Unconfirmed live run exited with code `2` and report `/tmp/komsco-ai-actions-e2e-blocked-v027-r40.json`: `mode=live-blocked`, `clusterCallsExecuted=false`, `mutationExecuted=false`, error `live action e2e requires --confirm-live-mutations`. Skip-gateway preflight report `/tmp/komsco-ai-actions-e2e-preflight-skip-gateway-v027-r40.json` returned `14 passed`, `0 failed`, `oc whoami=admin`, server `https://api.ocp.cywell.server:6443`. Full preflight with plain `python3` failed only at gateway probe because `httpx` was missing; rerun with `komsco-ai-gateway/.venv/bin/python` passed in `/tmp/komsco-ai-actions-e2e-preflight-v027-r40-venv.json` with `healthz=ok`, `mutationsEnabled=true`, `recordStoreEnabled=true`, `actionExecutorConfigured=true`, `diagnosticsEnabled=true`, and `mutationExecuted=false`.
- R41 uploaded document render refactor: PASS. `AssistantLauncher.tsx` no longer owns uploaded document row JSX; `AssistantUploadedDocuments.tsx` renders the same `komsco-ai__uploaded-doc-*` DOM and `AssistantHistoryPanel.tsx` consumes it directly instead of a render prop. Current line counts: `AssistantLauncher.tsx=3426`, `AssistantHistoryPanel.tsx=381`, `AssistantUploadedDocuments.tsx=41`.
- R41 static/build gates: PASS. `git diff --check`, `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`, and `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev` all passed after the uploaded document refactor.
- R41 expanded Assistant rail: PASS. `AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-upload-doc-refactor.png node scripts/verify-v027-expanded-assistant-rail.cjs` passed. API-DOM rail contract matched `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`; document/body/surface/workspace/rail horizontal overflow were all OK.
- R41 whole UI balance: PASS. `node scripts/verify-v027-ui-balance.cjs` checked 36 contexts across dashboard/alerts/reports, page/docked/fullscreen, desktop/mobile, light/dark. `failedCount=0`, `iconIssueCount=0` in every context, raw internal terms absent, and document/body horizontal overflow OK.
- R42 image lightbox refactor: PASS. `AssistantLauncher.tsx` no longer owns image preview lightbox JSX; `AssistantImageLightbox.tsx` renders the same `komsco-ai__image-lightbox-*` DOM and owns preview URL formatting. Current line counts: `AssistantLauncher.tsx=3395`, `AssistantImageLightbox.tsx=52`, `AssistantUploadedDocuments.tsx=41`.
- R42 static/build gates: PASS. `git diff --check`, `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`, and `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev` all passed after the image lightbox refactor.
- R42 expanded Assistant rail: PASS. `AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-image-lightbox-refactor.png node scripts/verify-v027-expanded-assistant-rail.cjs` passed with the same live API-DOM rail contract: `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`; document/body/surface/workspace/rail horizontal overflow were all OK.
- R42 whole UI balance: PASS. `node scripts/verify-v027-ui-balance.cjs` checked 36 contexts across dashboard/alerts/reports, page/docked/fullscreen, desktop/mobile, light/dark. `failedCount=0`, `iconIssueCount=0`, raw internal terms absent, and document/body horizontal overflow OK.
- R43 resize handle refactor: PASS. `AssistantLauncher.tsx` no longer owns the eight resize handle buttons; `AssistantResizeHandles.tsx` renders the same `komsco-ai__resize-handle-*` DOM and receives the existing resize callback. Current line counts: `AssistantLauncher.tsx=3382`, `AssistantResizeHandles.tsx=30`, `AssistantImageLightbox.tsx=52`, `AssistantUploadedDocuments.tsx=41`.
- R43 static/build gates: PASS. `git diff --check`, `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`, and `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev` all passed after the resize handle refactor.
- R43 expanded Assistant rail: PASS. `AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-resize-handles-refactor.png node scripts/verify-v027-expanded-assistant-rail.cjs` passed. API-DOM rail contract matched `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`; document/body/surface/workspace/rail horizontal overflow were all OK.
- R43 whole UI balance: PASS. `node scripts/verify-v027-ui-balance.cjs` checked 36 contexts across dashboard/alerts/reports, page/docked/fullscreen, desktop/mobile, light/dark. `failedCount=0`, `iconIssueCount=0`, raw internal terms absent, and document/body horizontal overflow OK.
- R44 Assistant header refactor: PASS. `AssistantLauncher.tsx` no longer owns Assistant header chrome, sidebar toggle, language toggle, fullscreen toggle, resize lock toggle, close button, or header execution mode toggle JSX. `AssistantHeader.tsx` renders the same `komsco-ai__header-*` DOM and receives existing callbacks. Current line counts: `AssistantLauncher.tsx=3321`, `AssistantHeader.tsx=127`, `AssistantResizeHandles.tsx=30`.
- R44 static/build gates: PASS. `git diff --check`, `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`, and `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev` all passed after the Assistant header refactor.
- R44 expanded Assistant rail: PASS. `AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-header-refactor.png node scripts/verify-v027-expanded-assistant-rail.cjs` passed. API-DOM rail contract matched `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`; document/body/surface/workspace/rail horizontal overflow were all OK.
- R44 whole UI balance: PASS. `node scripts/verify-v027-ui-balance.cjs` checked 36 contexts across dashboard/alerts/reports, page/docked/fullscreen, desktop/mobile, light/dark. `failedCount=0`, `iconIssueCount=0`, raw internal terms absent, and document/body horizontal overflow OK.
- R45 create Action Plan button refactor: PASS. `AssistantLauncher.tsx` no longer owns the answer-level create Action Plan button list or candidate button label helper. `AssistantCreateActionPlanButtons.tsx` renders the same `komsco-ai__create-action-plan` and `komsco-ai__action-button` DOM, including busy/loading state. Current line counts: `AssistantLauncher.tsx=3287`, `AssistantCreateActionPlanButtons.tsx=49`, `AssistantHeader.tsx=127`.
- R45 static/build gates: PASS. `git diff --check`, `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`, and `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev` all passed after the create Action Plan button refactor.
- R45 expanded Assistant rail: PASS. `AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-create-action-buttons-refactor.png node scripts/verify-v027-expanded-assistant-rail.cjs` passed. API-DOM rail contract matched `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`; document/body/surface/workspace/rail horizontal overflow were all OK.
- R45 whole UI balance: PASS. `node scripts/verify-v027-ui-balance.cjs` checked 36 contexts across dashboard/alerts/reports, page/docked/fullscreen, desktop/mobile, light/dark. `failedCount=0`, `iconIssueCount=0`, raw internal terms absent, and document/body horizontal overflow OK.
- R46 Insight rail direct render cleanup: PASS. Removed the internal `renderInsightRail` pass-through wrapper from `AssistantLauncher.tsx`; the launcher now renders `AssistantInsightRail` directly with the same props. Current line counts: `AssistantLauncher.tsx=3255`, `AssistantInsightRail.tsx=378`.
- R46 static/build gates: PASS. `git diff --check`, `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`, and `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev` all passed after direct rail render cleanup.
- R46 action/toolplan gates: PASS. `node komsco-ai-console-plugin/scripts/verify-action-resolver.cjs` checked 12 action resolver cases. `node scripts/verify-v027-toolplan-chat-ui.cjs` confirmed the Tool Plan answer footer (`조회 계획`, `cluster_operator_status`, `조회 전용`), opened detail (`Gateway 안전 플래너`, 2 steps), hidden raw JSON/default internals, no answer action card for read-only Tool Plan, and zero horizontal overflow.
- R46 expanded Assistant rail: PASS. `AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-direct-insight-rail.png node scripts/verify-v027-expanded-assistant-rail.cjs` passed. API-DOM rail contract matched `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`; document/body/surface/workspace/rail horizontal overflow were all OK.
- R46 whole UI balance: PASS. `node scripts/verify-v027-ui-balance.cjs` checked 36 contexts across dashboard/alerts/reports, page/docked/fullscreen, desktop/mobile, light/dark. `failedCount=0`, `iconIssueCount=0`, raw internal terms absent, and document/body horizontal overflow OK.
- R47 Surface portal refactor: PASS. `AssistantLauncher.tsx` no longer owns `AssistantSurfacePortal` JSX/createPortal logic; `AssistantSurfacePortal.tsx` preserves the same `active && typeof document !== 'undefined'` portal behavior and fallback fragment rendering. Current line counts: `AssistantLauncher.tsx=3244`, `AssistantSurfacePortal.tsx=22`.
- R47 static/build gates: PASS. `git diff --check`, `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`, and `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev` all passed after the surface portal refactor.
- R47 action/toolplan gates: PASS. `node komsco-ai-console-plugin/scripts/verify-action-resolver.cjs` checked 12 action resolver cases. `node scripts/verify-v027-toolplan-chat-ui.cjs` confirmed the Tool Plan answer footer/detail/raw JSON hiding/overflow behavior after the portal refactor.
- R47 expanded Assistant rail: PASS. `AIOPS_SCREENSHOT_PATH=/tmp/v027-expanded-assistant-rail-surface-portal-refactor.png node scripts/verify-v027-expanded-assistant-rail.cjs` passed. API-DOM rail contract matched `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=18`; document/body/surface/workspace/rail horizontal overflow were all OK.
- R47 whole UI balance: PASS. `node scripts/verify-v027-ui-balance.cjs` checked 36 contexts across dashboard/alerts/reports, page/docked/fullscreen, desktop/mobile, light/dark. `failedCount=0`, `iconIssueCount=0`, raw internal terms absent, and document/body horizontal overflow OK.
- R48 fixed PDF/action safety rerun: PASS. `python3 scripts/verify-v027-fixed-pdf.py` confirmed fixed PDF `docs/AIOps-For-OCP.pdf` and `docs/Ver.0.2.5/AIOps-For-OCP.pdf`, SHA `193cf62eea36bea9cf7d370203ac413fab6a9ef044a89d8e121f93e1df6a7cb5`, fixed PDF 16 pages, official source PDF `docs/Komsco_ai_agent_final.pdf` 14 pages, SHA `078657e7c8e589d793e9a84639e1810aaed2f7d2917f9fd7eb555191919b7f2d`. `node komsco-ai-console-plugin/scripts/verify-action-resolver.cjs` checked 12 action resolver cases.
- R48 action E2E plan-only: PASS. `python3 scripts/evaluate-aiops-actions-e2e.py --namespace komsco-ai-dev --plan-only --report /tmp/komsco-ai-actions-e2e-plan-v027-r48.json` wrote a plan-only report with `clusterCallsExecuted=false`, `ok=true`, `wouldMutateClusterInLiveMode=true`, and planned tools `rollout_restart_deployment`, `set_replicas_within_bounds`, `rollback_deployment_to_revision`, `set_hpa_bounds`, `evict_one_unhealthy_controller_owned_pod`, `node_os_readonly_triage`.
- R48 live guard: PASS. Running without `--confirm-live-mutations` wrote `/tmp/komsco-ai-actions-e2e-blocked-v027-r48.json`, printed `EXIT_CODE=2`, and reported `mode=live-blocked`, `clusterCallsExecuted=false`, `mutationExecuted=false`, `error=live action e2e requires --confirm-live-mutations`.
- R48 gateway preflight: PASS. `komsco-ai-gateway/.venv/bin/python scripts/evaluate-aiops-actions-e2e.py --namespace komsco-ai-dev --preflight-only --report /tmp/komsco-ai-actions-e2e-preflight-v027-r48.json` returned `14 passed`, `0 failed`, `gatewayProbeOk=true`, `healthz=ok`, and capabilities `mutationsEnabled=true`, `recordStoreEnabled=true`, `actionExecutorConfigured=true`, `diagnosticsEnabled=true`. The current `oc` context was `admin` on `https://api.ocp.cywell.server:6443`; no mutation was executed.
- R48 Python compile gate: PASS. `komsco-ai-gateway/.venv/bin/python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/komsco_ai_gateway/aiops_core.py komsco-ai-gateway/komsco_ai_gateway/action_executor.py scripts/evaluate-aiops-actions-e2e.py` completed successfully.
- Cypress expanded rail spec: NOT RUN. Electron dependency check failed with `libnspr4.so: cannot open shared object file`.
- JS verifier syntax: `node --check scripts/verify-kugnus-ui.mjs` PASS, `node --check scripts/verify-v027-expanded-assistant-rail.cjs` PASS.

## Browser Evidence

9000 OKD console에서 확인:

- `알림 & 이벤트` 배지:
  - text: `위험`
  - display: `flex`
  - alignItems: `center`
  - justifyContent: `center`
  - height: `28`
  - paddingTop/paddingBottom: `0px/0px`
  - overflowX: `false`

- `보고서` 배지:
  - report type badge: `생성 가능`, `준비 중`
  - display: `flex`
  - alignItems: `center`
  - paddingTop/paddingBottom: `4px/4px`
  - overflowX: `false`
  - preview severity badge: `inline-flex`, `alignItems:center`, height `24`

- Assistant expanded mode:
  - title: `AIOps`
  - action lifecycle DOM count: `1`
  - visible stages: `approval`, `plan`, `proposal`
  - answer action buttons count: `1`
  - old labels absent: `OpenShift Lightspeed`, `KOMSCO AI AGENT`
  - raw `Conflict` absent
  - raw internal execution reasons absent: `Action Executor URL not configured`, `mutation gate disabled`, `unrestricted command gate`
  - rail actual signals: API URL present, `92 / 100`, `Node 1/1`, `Operator 34/34`
  - rail API-DOM contract: `apiUrl=https://api.ocp.cywell.server:6443`, `healthScore=92`, `node=1/1`, `operator=34/34`, `version=4.20.23`, `firstNode=52-54-00-a1-f8-7c`, `diagnosticRecordCount=0`, `actionRecordCount=6`
  - body/panel/rail/workspace horizontal overflow: `false`
  - expanded surface rect: `x=16`, `y=16`, `width=1408`, `height=725`
  - main panel rect: `width=1406`, `height=723`
  - workspace rect: `width=1406`, `height=647`
  - context rail rect: `width=316`, `height=647`
  - rail text includes:
    - `https://api.ocp.cywell.server:6443`
    - `Node 1/1 · Ready`
    - `Operator 34/34 정상`
    - `92 / 100`
    - `AIOps 실행 상태 연결됨`
    - `승인·실행 6건`
  - screenshot: `/tmp/v027-expanded-assistant-rail.png`

- Assistant Tool Plan chat answer:
  - question: `clusteroperator 상태 확인해줘. 조회 계획과 근거를 같이 보여줘.`
  - default footer: `조회 계획`, `cluster_operator_status`, `조회 전용`, `조회 계획 상세보기`
  - opened detail: `Gateway 안전 플래너`, `clusteroperator`, `clusterversion`, step count `2`
  - answer action card: not visible, `answerActionVisible=false`
  - raw JSON/default internal terms: hidden
  - default/opened horizontal overflow: `0`
  - screenshot: `/tmp/v027-toolplan-chat-ui-r22.png`

- Action E2E safety preflight:
  - plan report: `/tmp/komsco-ai-actions-e2e-plan-v027-r23.json`
  - plan report with explicit live flag contract: `/tmp/komsco-ai-actions-e2e-plan-v027-r24.json`
  - unconfirmed live blocked report: `/tmp/komsco-ai-actions-e2e-blocked-v027-r24b.json`
  - live lifecycle report: `/tmp/aiops-live-action-lifecycle-v027-r23.json`
  - live lifecycle report after guard: `/tmp/aiops-live-action-lifecycle-v027-r24.json`
  - plan-only cluster calls: `false`
  - unconfirmed live cluster calls: `false`
  - unconfirmed live mutation executed: `false`
  - required live flag: `--confirm-live-mutations`
  - live-mode warning: actual E2E would create temporary RBAC, deployments, HPA, pod eviction, host diagnostic job, and cleanup them
  - non-mutating lifecycle result: `11 passed`, `0 failed`, mutation not executed

- Standalone portal direct path:
  - `http://localhost:5174/dashboards/aiops/alerts`: active nav `알림 & 이벤트`, dashboard fallback `false`
  - `http://localhost:5174/dashboards/aiops/reports`: active nav `보고서`, dashboard fallback `false`
  - alert/report badges remain `display:flex`, `alignItems:center`, overflow `false`

- Whole UI badge/chip balance:
  - URLs: `http://localhost:9000/dashboards/aiops`, `/alerts`, `/reports`
  - contexts: page, Assistant docked, Assistant fullscreen
  - viewports: `desktop:1440x900`, `mobile:390x844`
  - color schemes: `light`, `dark`
  - total contexts checked: 36
  - failed contexts: 0
  - icon issue contexts: 0
  - raw internal terms absent: `Conflict`, `Action Executor URL not configured`, `mutation gate disabled`, `unrestricted command gate`, `봉인됨`, `봉인 계획`, `승인 봉인`
  - document/body horizontal overflow: all OK

### R49 로컬 9000 확장 레일 재점검

User request: 챗봇 창 확대 시 우측 정보 레일이 실제 상황을 반영하는지와 UI 문제가 없는지 확인.

- Result: **Blocked by local OCP connectivity, not passed.**
- `http://localhost:9000/dashboards/aiops` verifier:
  - `scripts/verify-v027-expanded-assistant-rail.cjs` failed before UI inspection because 9000 console bridge was not listening.
  - `scripts/verify-v027-ui-balance.cjs` failed for the same reason.
- Local ports at the time:
  - Gateway `18080`: listening.
  - Standalone portal `5174`: listening.
  - Plugin dev server `9001`: listening, manifest OK.
  - Console bridge `9000`: not listening.
- Gateway direct API probe:
  - `/healthz`: `{"status":"ok"}`.
  - `/v1/aiops/status`: HTTP 200.
  - `/v1/cluster/summary` without token: HTTP 401 `Missing OpenShift bearer token`.
  - `/v1/cluster/summary` with local `.env` token: HTTP 504 `openshift_api_unavailable`.
- Root cause evidence:
  - `task kugnus:dev:console:repair` previously failed while shell-sourcing `.env` because a later duplicate placeholder value existed: `OPENSHIFT_API_SERVER=https://api.<cluster-domain>:6443`.
  - Fixed scripts now load `.env` with a safe parser, skip placeholder values, and wrap `oc` calls with timeout.
  - After the script fix, `task kugnus:dev:console:repair` no longer dies on the placeholder line, but fails at the real connectivity/login layer: `oc web login did not print a login URL`.
  - `scripts/kugnus-okd-console-morning.sh` now reports the actionable state:
    - `api.ocp.cywell.server -> 10.0.1.230`
    - `api.ocp.cywell.server:6443 TCP 연결 실패`
    - `이 상태에서는 9000을 재시작해도 OKD 데이터가 뜨지 않습니다.`
- Code verification after script hardening:
  - `bash -n scripts/lib/safe-env.sh scripts/open-okd-console.sh scripts/dev-console-plugin.sh scripts/kugnus-okd-console-morning.sh`: Pass.
  - `git diff --check`: Pass.
  - `node komsco-ai-console-plugin/scripts/verify-insight-rail-helpers.cjs`: Pass, 33 checked.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`: Pass.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev`: Pass.

### R50 safe-env 보강 + Empty State 분리

- Scope:
  - local console scripts hardening
  - small Assistant refactor without changing JSX behavior
  - fixed PDF/action plan-only/compile checks
- Changes:
  - Added `scripts/lib/safe-env.sh`.
  - `open-okd-console.sh`, `dev-console-plugin.sh`, `kugnus-okd-console-morning.sh` now use a safe `.env` loader instead of shell-sourcing raw `.env`.
  - Placeholder values such as `https://api.<cluster-domain>:6443` are skipped/unset.
  - `oc` calls in local console scripts are wrapped with timeout helpers so broken VPN/API sessions fail with an actionable message instead of hanging.
  - Extracted `AssistantEmptyState.tsx` from `AssistantLauncher.tsx`.
- Evidence:
  - Forced placeholder test:
    - `OPENSHIFT_API_SERVER=https://api.<cluster-domain>:6443 ... scripts/kugnus-okd-console-morning.sh`
    - Result: still uses expected `https://api.ocp.cywell.server:6443`, then reports real TCP failure.
  - `bash -n scripts/lib/safe-env.sh scripts/open-okd-console.sh scripts/dev-console-plugin.sh scripts/kugnus-okd-console-morning.sh`: Pass.
  - `git diff --check`: Pass.
  - `node komsco-ai-console-plugin/scripts/verify-insight-rail-helpers.cjs`: Pass, 33 checked.
  - `node komsco-ai-console-plugin/scripts/verify-action-resolver.cjs`: Pass, 12 checked.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`: Pass.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev`: Pass.
  - `python3 scripts/verify-v027-fixed-pdf.py`: Pass, fixed PDF `docs/AIOps-For-OCP.pdf`, 16 pages, SHA `193cf62eea36bea9cf7d370203ac413fab6a9ef044a89d8e121f93e1df6a7cb5`.
  - `komsco-ai-gateway/.venv/bin/python scripts/evaluate-aiops-actions-e2e.py --namespace komsco-ai-dev --plan-only --report /tmp/komsco-ai-actions-e2e-plan-v027-r50.json`: Pass, `clusterCallsExecuted=false`, planned tools `rollout_restart_deployment`, `set_replicas_within_bounds`, `rollback_deployment_to_revision`, `set_hpa_bounds`, `evict_one_unhealthy_controller_owned_pod`, `node_os_readonly_triage`.
- Browser UI check:
  - `node scripts/verify-v027-toolplan-chat-ui.cjs`: blocked, `localhost refused to connect`.
  - Cause remains local console bridge down because `api.ocp.cywell.server:6443` TCP connection is unavailable in the current workstation network state.
- Refactor size:
  - `AssistantLauncher.tsx`: 3243 lines.
  - `AssistantEmptyState.tsx`: 19 lines.

### R51 Standalone UI balance + Message Header 분리

- Scope:
  - standalone portal UI balance recheck while local 9000 bridge is blocked
  - safe Assistant message header refactor
- Changes:
  - Added `AssistantMessageHeader.tsx`.
  - Moved message label/icon/source badge/copy button JSX out of `AssistantLauncher.tsx`.
  - `AssistantLauncher.tsx` reduced to 3173 lines.
- Standalone portal UI balance:
  - Command:
    - `AIOPS_UI_BALANCE_URLS=http://localhost:5174/dashboards/aiops,http://localhost:5174/dashboards/aiops/alerts,http://localhost:5174/dashboards/aiops/reports,http://localhost:5174/dashboards/aiops/endpoints node scripts/verify-v027-ui-balance.cjs`
  - Result: Pass.
  - Contexts: 4 URLs x desktop/mobile x light/dark = 16 contexts.
  - `failedCount=0`.
  - `iconIssueCount=0`.
  - `issueCount=0`.
  - `rawInternalTerms=[]`.
  - document/body horizontal overflow all OK.
- Static/build evidence after refactor:
  - `git diff --check`: Pass.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`: Pass.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev`: Pass.
  - `node komsco-ai-console-plugin/scripts/verify-insight-rail-helpers.cjs`: Pass, 33 checked.
  - `node komsco-ai-console-plugin/scripts/verify-action-resolver.cjs`: Pass, 12 checked.
  - `python3 scripts/verify-v027-fixed-pdf.py`: Pass.

### R52 Standalone Portal Route Contract

- Scope:
  - strengthen standalone portal evidence while local 9000 bridge is blocked.
  - verify route/content contract, not only badge/overflow styling.
- Added verifier:
  - `scripts/verify-v027-portal-routes.cjs`
- Command:
  - `node --check scripts/verify-v027-portal-routes.cjs`
  - `node scripts/verify-v027-portal-routes.cjs`
- Result: Pass.
- Routes checked:
  - `/dashboards/aiops` -> active nav `대시보드`, text includes `시스템 건강도`.
  - `/dashboards/aiops/audit` -> active nav `RCA 센터`, text includes `RCA-`, `원본 증거`.
  - `/dashboards/aiops/service-map` -> active nav `서비스 맵`, text includes `클러스터 토폴로지`.
  - `/dashboards/aiops/endpoints` -> active nav `클러스터 리소스`, text includes `리소스 그룹 분포`.
  - `/dashboards/aiops/alerts` -> active nav `알림 & 이벤트`, text includes `이벤트 인박스`.
  - `/dashboards/aiops/docs` -> active nav `위키 문서 관리`, text includes `Runbook`.
  - `/dashboards/aiops/reports` -> active nav `보고서`, text includes `보고서 유형`.
- Contract checks:
  - `failedCount=0`.
  - no non-dashboard route fell back to dashboard.
  - `pathname` matched expected route for all 7 URLs.
  - document/body horizontal overflow `0` for all routes.

### R53 Review Matrix Verifier

- Scope:
  - verify that the review report itself contains the minimum review/evidence contract required by the user goal.
- Added verifier:
  - `scripts/verify-v027-review-matrix.cjs`
- Command:
  - `node --check scripts/verify-v027-review-matrix.cjs`
  - `node scripts/verify-v027-review-matrix.cjs`
- Result: Pass.
- Evidence:
  - `reviewRowCount=36`, so the report exceeds the minimum 5 function/UI review requirement.
  - `latestRound=52`, proving the continuation rounds are represented.
  - required evidence categories present:
    - fixed PDF verifier
    - Tool Plan UI verifier
    - Action E2E plan-only and live confirmation guard
    - UI balance verifier
    - standalone portal route verifier
    - refactor progress
    - named 9000/OCP API connectivity blocker
    - protected artifact section
  - `protectedStatus=[]`, confirming protected artifacts are not modified.
  - `git diff --check`: Pass.

### R54 Expanded Assistant Rail Reality/UI Recheck

- User request:
  - 챗봇 창 확대 시 가로로 커지며 우측에 뜨는 정보 레일이 실제 상황을 반영하는지와 UI 문제가 없는지 재점검.
- Current code contract:
  - `AssistantLauncher` renders `AssistantInsightRail` in fullscreen mode.
  - `AssistantInsightRail` receives `clusterSummary` and `aiopsStatus` from `fetchClusterSummary()` and `fetchAiopsStatus()`.
  - The rail shows live cluster/API context, health score, Node/Operator summary, operator issues, AIOps execution capability, evidence counts, diagnostic records, and approval/execution records.
- Fix made during this check:
  - `komsco-ai-console-plugin/integration-tests/tests/v027-expanded-assistant-rail.cy.js` no longer asserts stale fixed values such as `Node 1/1` and `Operator 34/34`.
  - The Cypress spec now calls the same console proxy endpoints and compares the rail text against the current API response:
    - `/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/cluster/summary`
    - `/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status`
- Static/build evidence:
  - `node --check komsco-ai-console-plugin/integration-tests/tests/v027-expanded-assistant-rail.cy.js`: Pass.
  - `git diff --check -- komsco-ai-console-plugin/integration-tests/tests/v027-expanded-assistant-rail.cy.js ...`: Pass.
  - `node komsco-ai-console-plugin/scripts/verify-insight-rail-helpers.cjs`: Pass, `checked=33`.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`: Pass.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev`: Pass.
  - CSS static checks:
    - fullscreen workspace two-column rail layout: Pass.
    - rail hidden outside fullscreen and shown in fullscreen: Pass.
    - rail horizontal overflow guard: Pass.
    - portal fullscreen viewport sizing: Pass.
- Browser/live UI evidence:
  - `scripts/verify-v027-expanded-assistant-rail.cjs`: Blocked before UI inspection.
  - Failure: `localhost:9000 refused to connect`, so dashboard/FAB could not be loaded.
  - `KUGNUS_OKD_CONSOLE_REPAIR=false scripts/kugnus-okd-console-morning.sh`: Fail at company API TCP layer.
  - Exact blocker:
    - `api.ocp.cywell.server -> 10.0.1.230`
    - `api.ocp.cywell.server:6443 TCP 연결 실패`
    - `이 상태에서는 9000을 재시작해도 OKD 데이터가 뜨지 않습니다.`
- Current judgment:
  - The expanded right rail is wired to real Gateway/OCP data, not mock constants.
  - The automated UI contract now verifies dynamic API-to-DOM matching instead of stale sample numbers.
  - Actual browser confirmation is pending until local workstation network/VPN can reach `api.ocp.cywell.server:6443` and the 9000 console bridge is available again.

### R55 Portal Navigation Contract Refactor

- Scope:
  - reduce oversized standalone/embedded portal files without changing menu labels, tab routes, or visual layout.
  - keep OKD embedded AIOps tabs and standalone portal routes on the same navigation contract.
- Changes:
  - `komsco-ai-portal/src/portalNavigation.tsx` now owns standalone portal `navItems`, `navGroupLabel`, route map, and `viewFromLocation`.
  - `komsco-ai-console-plugin/src/portal/portalNavigation.tsx` now owns the same contract for the embedded console portal.
  - Removed duplicate `NavItem`, `navItems`, `navGroupLabel`, `isNavView`, `viewFromPathname`, `viewFromLocation` definitions from both large App files.
  - Removed the extra embedded-only `consoleRouteByView`; embedded navigation now uses the same `standaloneRouteByView` contract.
- Refactor evidence:
  - `komsco-ai-portal/src/App.tsx`: `7329 -> 7268` lines.
  - `komsco-ai-console-plugin/src/portal/PortalApp.tsx`: `7713 -> 7640` lines.
  - `komsco-ai-portal/src/portalNavigation.tsx`: `77` lines.
  - `komsco-ai-console-plugin/src/portal/portalNavigation.tsx`: `77` lines.
  - Source grep confirmed the duplicate navigation definitions are gone from both large App files.
- Verification:
  - `git diff --check -- komsco-ai-portal/src/App.tsx komsco-ai-console-plugin/src/portal/PortalApp.tsx ...`: Pass.
  - `cd komsco-ai-portal && npm run build`: Pass.
    - Note: Vite warns that local Node `18.19.1` is below recommended `20.19+`, but build completed successfully.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`: Pass.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev`: Pass.
  - `node scripts/verify-v027-portal-routes.cjs`: Pass.
    - `failedCount=0`.
    - all 7 routes kept the expected active nav and did not fall back to dashboard.
    - document/body horizontal overflow remained `0`.

### R56 Whole Portal Badge Balance Expansion

- Scope:
  - strengthen the UI balance verifier from a partial route check into a full standalone portal tab sweep.
  - catch compact badge/label alignment regressions that manual "move it a little down" fixes can miss.
- Verifier changes:
  - `scripts/verify-v027-ui-balance.cjs` default URL list now covers all 7 AIOps tabs:
    - dashboard, RCA center, service map, cluster resources, alerts/events, wiki docs, reports.
  - Added compact selector coverage for:
    - `portal-mode`, `portal-sidebar__status`, `impact-edge-label`.
    - assistant context/evidence/header/action/runbook badge classes.
- Failure found:
  - First expanded 5174 run failed in the wiki docs tab.
  - `doc-list` cards used a broad `.doc-list span { display: block; ... }` rule that overrode `.status-badge`.
  - Affected labels: `검증됨`, `검증 필요`.
- Fix:
  - Added explicit wiki badge overrides in both standalone and embedded portal CSS:
    - `.doc-list .status-badge`
    - `.wiki-index-compact .status-badge`
    - `.wiki-search-results .status-badge`
  - The fix restores `inline-flex`, `align-items: center`, and `justify-content: center` for those badges without changing normal doc description spans.
- Verification:
  - `node --check scripts/verify-v027-ui-balance.cjs`: Pass.
  - `git diff --check -- scripts/verify-v027-ui-balance.cjs komsco-ai-portal/src/styles.css komsco-ai-console-plugin/src/portal/styles.css`: Pass.
  - `AIOPS_UI_BALANCE_URLS=http://localhost:5174/dashboards/aiops,...,/reports node scripts/verify-v027-ui-balance.cjs`: Pass.
    - 7 routes x desktop/mobile x light/dark = 28 contexts.
    - `failedCount=0`.
    - `issueCount=0`, `iconIssueCount=0`, `rawInternalTerms=[]` in all contexts.
    - document/body horizontal overflow OK in all contexts.
  - `cd komsco-ai-portal && npm run build`: Pass.
    - Node `18.19.1` warning remains from Vite requirement, but build completed.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`: Pass.
  - `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev`: Pass.

## 남은 Gap

- `AssistantLauncher.tsx`, `assistant.css`, `PortalApp.tsx`, standalone `App.tsx`는 여전히 oversized다. 이번에는 display helper, execution state helper, action record helper, storage/history helper, Tool Plan parser helper, Evidence footer/parser helper, Evidence footer JSX, Tool Plan footer JSX, Action Plan answer action JSX, uploaded document rows, image lightbox, resize handles, Assistant header chrome, answer-level create Action Plan buttons, Insight rail pass-through wrapper 제거, Surface portal 분리까지만 수행했다.
- Tool Plan은 현재 deterministic gateway planner 기반이다. UI에서는 `Gateway 안전 플래너`로 출처를 구분했지만, PDF의 model-generated Tool Plan 아키텍처까지 완성한 것은 아니다.
- 2026-07-04 R49 기준, 우측 확장 레일의 실제 OCP 반영은 현재 재검증 실패 상태다. 원인은 UI 코드가 아니라 로컬 작업대에서 `api.ocp.cywell.server:6443` TCP 연결이 되지 않아 9000 console bridge와 `/v1/cluster/summary`가 실제 클러스터 증거를 받지 못하는 것이다.
- Cypress Electron 기반 visual spec은 WSL에 `libnspr4.so`가 없어 실행하지 못했다. 대신 Chrome DevTools Protocol verifier로 동일 화면의 live signal/overflow/screenshot을 검증했다.
- UI balance verifier는 desktop/mobile x light/dark synthetic theme matrix를 통과했다. 다만 실제 사용자 Chrome의 저장된 OCP theme 설정, 브라우저 확장, 확대 배율까지 포함한 수동 visual review는 별도 확인이 필요할 수 있다.
- 실제 deployment/HPA/eviction mutation E2E는 안전상 이번 자동 검증에서 제외했다. 이제 `--plan-only`로 정확히 무엇을 만들고 바꾸는지 먼저 확인할 수 있고, live 실행에는 `--confirm-live-mutations`가 필수다. 검증된 것은 proposal -> sealed plan -> approval/rejection -> stale/rejected execution block, 그리고 mutation dispatch 전에 차단되는 safety gate이다.

## 보호 산출물

다음 보호 산출물은 수정하지 않았다.

- `docs/version-progress-book.html`
- `docs/aiops-beginner-guide.html`
- `docs/Ver.0.1.8/aiops-llm-strategy-brief.html`
- `evals/aiops-scenarios/*`
