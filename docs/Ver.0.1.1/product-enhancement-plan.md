# Ver.0.1.1 제품 기능 고도화 플랜

작성 기준일: 2026-06-24 KST  
작업 브랜치: `feat/v.0.1.1`  
기준 PDF: `docs/Komsco_ai_agent_final.pdf`

## 현재 기준

0.1.0/0.1.3 기준 구현은 다음을 이미 갖고 있다.

- Dynamic Console Plugin 기반 `Cywell AI` UI
- Kugnus 전용 `komsco-ai-console-plugin-kugnus` proxy 경로
- Gateway `/v1/chat/stream` -> Lightspeed `/v1/streaming_query` 중계
- `UserToken` 기반 Gateway 호출
- read-only 기본 모드와 mutation/unrestricted gate
- audit/evidence/action/approval record의 in-memory ledger
- Pod/CronJob/ClusterOperator 중심의 일부 evidence preflight
- OLM package/catalog/install 자동화
- UI 자동 검증 `task kugnus:ui:verify`

하지만 최종 PDF 기준으로는 아직 **AIOps 제품 기능이 충분히 닫히지 않은 상태**다.

## 현재 누락 또는 부실한 점

| 영역 | 현재 상태 | 부족한 점 | 우선도 |
| :--- | :--- | :--- | :--- |
| Header status UX | 연결/읽기/방패/터미널/info 표시가 있음 | indicator와 button의 구분이 모호하고 disabled 이유가 보이지 않음 | P0 |
| Tool Plan JSON | `safetyContract.toolPlanStatus.latestRuntimePlan`이 `not_persisted_in_ver_0_1_0` | 실제 질문별 Tool Plan 생성/저장/표시가 없음 | P0 |
| RCA Context JSON | Gateway evidence fallback은 있음 | Lightspeed에 넘긴 RCA Context를 사용자가 확인할 수 없음 | P0 |
| Evidence | 일부 Pod/CronJob/Operator evidence와 in-memory Evidence API 존재 | 시간 범위, 장기 증적, metric, runbook, RAG 근거가 체계화되지 않음 | P0 |
| RAG | Runbook registry API는 있으나 vector retrieval은 없음 | PostgreSQL + pgvector ingestion/search/ACL 설계가 없음 | P0 |
| OS-aware Adapter | OpenShift read-only 관측 중심, Linux diagnostics는 gated, Windows는 planned | Adapter contract와 OS별 tool mapping이 runtime 기능으로 부족 | P1 |
| Lightspeed 상태 | streaming 호출은 수행 | status endpoint에서 stream probe가 `not_probed_by_status_endpoint` | P1 |
| Action lifecycle | proposal/plan/approval/execute API 존재 | 지원 action 범위와 UI 설명, failure recovery, evidence freshness UX가 약함 | P1 |
| Model routing | PDF의 Qwen/Gemma 역할 구분 있음 | 회사 LLM endpoint, quick/deep routing, schema validation 평가가 없음 | P1 |
| Operator runtime | package/install 경로 존재 | CR status condition, metrics/alert, rollback evidence가 운영 수준으로 부족 | P2 |
| Evaluation | UI verifier는 강함 | AIOps RCA 품질, tool selection, evidence match 평가 세트가 없음 | P0 |

## 0.1.1 목표

0.1.1의 목표는 **실제 기능 연동을 시작하기 전에 제품의 판단 계약을 고정하는 것**이다.
최종 PDF 요구사항 전체를 0.1.1에서 닫기 위한 상세 Epic/Phase 계획은
`pdf-requirements-completion-plan.md`를 기준으로 한다.

완료 기준:

- 사용자가 header status를 보고 현재 연결/모드/실행 가능성을 이해할 수 있다.
- 질문 1건마다 Tool Plan JSON이 생성되고 UI/API에서 볼 수 있다.
- 답변에 사용된 Evidence와 누락 Evidence가 구분된다.
- 최소 OpenShift RCA 질문 5종에 대해 evidence-first 답변 검증이 가능하다.
- RAG/pgvector는 최소 설계와 ingestion skeleton이 있다.
- OS Adapter는 OpenShift/Linux/Windows 모두 contract와 status가 있다.

## 구현 Lane

### Lane 1. Header status contract 정리

현재 문제:

- 연결 상태, 실행 모드, safety indicator, executor indicator가 작은 칩으로 섞여 있다.
- `>_`, `i` 같은 아이콘은 사용자가 기능을 추측해야 한다.
- disabled 상태가 "왜 안 눌리는지" 설명하지 않는다.

작업:

- `Connection`, `Mode`, `Safety`, `Executor`를 명확히 나눈다.
- 클릭 가능한 항목은 button으로, 클릭 불가 항목은 status indicator로 표시한다.
- `Safety` 클릭 시 popover에 forbidden actions, allowed verbs, mutation gate, unrestricted gate를 표시한다.
- `Executor` 클릭 시 action executor configured 여부와 disabled reason을 표시한다.
- `i`는 의미가 겹치면 제거한다.

Pass:

- header chip 각각의 의미가 tooltip/popover로 설명된다.
- disabled button에는 disabled reason이 있다.
- UI 검증에 `header status controls expose labels and reasons` 항목이 추가된다.

### Lane 2. Runtime Tool Plan JSON

현재 문제:

- Dashboard는 Tool Plan JSON처럼 보이는 샘플을 보여주지만 실제 질문별 plan이 아니다.
- Gateway contract도 `contract_only` 상태다.

작업:

- `ToolPlan` schema를 정의한다.
- `POST /v1/aiops/tool-plan/preview` 또는 chat stream 내부 event로 질문별 plan을 생성한다.
- 초기는 LLM 없이 deterministic planner로 시작한다.
- target platform, task_type, selected tools, missing evidence, execution policy를 포함한다.
- chat stream에서 `tool_plan` event를 보내고 UI에 표시한다.

Pass:

- "어제 새벽 pod가 왜 재시작됐어?" 질문에 `pod_restart_rca` plan이 생성된다.
- plan은 `read_only` policy를 포함한다.
- forbidden action이 들어가면 `assert_read_only_tool_plan`이 fail한다.
- Dashboard `Tool Plan JSON`은 최신 runtime plan을 보여준다.

### Lane 3. Evidence/RCA Context 강화

현재 문제:

- Evidence는 일부 preflight 문자열과 in-memory record 중심이다.
- 사용자는 답변이 어떤 근거에서 나왔는지 확실히 추적하기 어렵다.

작업:

- `EvidenceRecord` schema를 명확히 한다.
- event/log/metric/runbook/audit evidence를 타입별로 구분한다.
- chat answer마다 `RCA Context JSON`을 생성하고 evidence refs를 연결한다.
- missing evidence를 UI에서 경고로 표시한다.
- time range 질문을 위한 `time_window` parsing을 추가한다.

Pass:

- Pod restart RCA 답변에 event/log/metric 중 수집된 것과 누락된 것이 표시된다.
- 답변 하단에 evidence reference가 1개 이상 연결된다.
- evidence가 없으면 "확인됨"이라고 답하지 않는다.

### Lane 4. RAG/Runbook foundation

현재 문제:

- Runbook registry는 있으나 PDF가 말하는 사내 Runbook/RAG 검색은 아직 없다.
- pgvector 저장소와 ACL metadata 설계가 없다.

작업:

- `docs/Ver.0.1.1/rag-storage-contract.md` 작성.
- PostgreSQL + pgvector schema 초안 작성.
- ingestion target: runbook markdown/pdf/html, SOP, RCA report.
- chunk metadata: source, namespace/customer, acl_group, checksum, version.
- Gateway retrieve API skeleton: `/v1/rag/search`.

Pass:

- RAG DB schema와 ACL 필터 기준이 문서화된다.
- retrieve 결과가 RCA Context JSON의 `evidence`에 들어갈 수 있는 형태다.
- 직접 DB 접속이 아니라 Gateway 전용 경로로만 접근한다.

### Lane 5. OS-aware Adapter contract

현재 문제:

- OpenShift Adapter는 실제 read-only 조회가 가능하지만 Linux/Windows는 상태상 planned에 가깝다.
- Tool Plan의 추상 tool이 OS별 명령으로 어떻게 바뀌는지 runtime contract가 없다.

작업:

- `AdapterRequest` / `AdapterResult` schema 정의.
- OpenShift: `oc get`, `oc describe`, event/log/metric query.
- Linux: `journalctl`, `systemctl`, `dmesg`, `df`, `free`는 diagnostics gate 뒤에 둔다.
- Windows: `Get-WinEvent`, `Get-Service`는 설계/Mock부터 시작한다.
- Adapter status endpoint에 supported tools와 disabled reason을 노출한다.

Pass:

- Dashboard에서 OpenShift/Linux/Windows adapter가 supported/disabled/planned 이유와 함께 보인다.
- Tool Plan의 `event_tool`이 OpenShift adapter로 resolve되는 예시가 있다.
- Linux/Windows는 실제 실행 전에도 "왜 아직 planned인지" 명확하다.

### Lane 6. Lightspeed context injection 검증

현재 문제:

- Gateway가 Lightspeed streaming endpoint로 요청을 넘기지만, Tool Plan/RCA Context가 실제로 어떻게 주입되는지 검증이 약하다.
- status endpoint는 stream probe를 하지 않는다.

작업:

- OLS request payload에 `gateway_context` 섹션을 명시한다.
- `tool_plan`, `evidence_summary`, `missing_evidence`, `safety_contract`를 포함한다.
- `/v1/aiops/status`에서 Lightspeed stream probe 또는 last success/fail timestamp를 제공한다.
- fallback 답변과 OLS 답변을 UI에서 구분한다.

Pass:

- chat stream 로그/이벤트에서 OLS에 전달된 context hash를 확인할 수 있다.
- OLS 실패 시 fallback이라고 명시한다.
- status panel의 streamProbe가 `not_probed_by_status_endpoint`가 아니다.

### Lane 7. AIOps 평가 세트

현재 문제:

- UI는 65개 검증이 있지만 RCA 품질 검증은 부족하다.

작업:

- `evals/aiops-scenarios/`에 최소 5개 한국어 운영 질문 세트 작성.
- 평가 항목: tool_plan schema valid, evidence match, forbidden hallucination, answer format, safety mode.
- Gateway response evaluator를 scenario 단위로 실행한다.

Pass:

- `task kugnus:evaluate` 또는 유사 task가 생긴다.
- 최소 5개 scenario가 pass/fail로 기록된다.
- "증거 없는데 단정" 케이스를 fail 처리한다.

## 0.1.1 작업 순서

1. Header status UX 정리
2. Tool Plan JSON schema 및 runtime event 추가
3. Evidence/RCA Context schema 추가
4. Dashboard가 최신 Tool Plan/Evidence를 표시하도록 연결
5. RAG storage contract 작성 및 skeleton API 추가
6. OS Adapter contract와 status 확장
7. Lightspeed context injection 검증
8. AIOps scenario 평가 자동화

## Acceptance Criteria

| 항목 | Pass | Evidence |
| :--- | :--- | :--- |
| Header UX | 모든 상태 칩의 의미와 disabled reason이 UI에서 확인됨 | Playwright/UI verifier |
| Tool Plan | 질문별 runtime Tool Plan JSON 생성 | `/v1/chat/stream` event 또는 status |
| Evidence | 수집/누락 evidence가 답변과 Dashboard에 표시 | Evidence API, UI panel |
| RAG | pgvector 기반 저장소 계약과 retrieve skeleton 존재 | docs + API route |
| Adapter | OpenShift/Linux/Windows adapter status가 이유와 함께 표시 | `/v1/aiops/status` |
| Lightspeed | OLS context injection hash 또는 last stream status 표시 | Gateway event/status |
| Evaluation | 5개 이상 AIOps scenario pass/fail 자동화 | evaluator output |
| Safety | read-only 기본값, mutation/unrestricted는 명시적으로 gated | tests + UI |

## 우선 구현 후보

가장 먼저 손댈 곳:

- `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx`
- `komsco-ai-console-plugin/src/pages/AiopsPages.tsx`
- `komsco-ai-console-plugin/src/services/aiGateway.ts`
- `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py`
- `komsco-ai-gateway/komsco_ai_gateway/main.py`
- `komsco-ai-gateway/tests/test_health.py`
- `scripts/verify-kugnus-ui.mjs`

첫 번째 실제 구현 단위는 **Header status UX + Tool Plan runtime event**가 적절하다. 이유는 사용자가 지금 바로 혼란을 느끼는 지점이고, 동시에 PDF의 핵심인 Tool Plan JSON으로 연결되는 입구이기 때문이다.
