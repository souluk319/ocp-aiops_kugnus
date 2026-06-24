# Ver.0.1.1 PDF 요구사항 완료 플랜

작성 기준일: 2026-06-24 KST  
작업 브랜치: `feat/v.0.1.1`  
기준 요구사항: `docs/Ver.0.1.1/final-pdf-key-points.md`

## 목표

Ver.0.1.1의 목표는 최종 PDF에서 요구한 AIOps Agent 제품 요구사항을 **동작 가능한 PoC 수준으로 모두 닫는 것**이다.

여기서 "닫는다"의 의미는 다음과 같다.

- UI에 상태만 흉내내는 것이 아니라 실제 Gateway/API/상태 데이터와 연결한다.
- 모델, RAG, OS Adapter처럼 외부 인프라가 필요한 항목은 runtime contract, 설정, mock 또는 minimal implementation, 검증 명령까지 만든다.
- 회사 OCP 공용 Lightspeed와 기존 ConsolePlugin은 건드리지 않는다.
- 모든 항목은 pass/fail 가능한 evidence를 남긴다.

## 0.1.1 완료 정의

0.1.1은 아래 10개 Epic이 모두 pass이면 완료다.

| Epic | 완료 판정 |
| :--- | :--- |
| E1. Header status UX | 사용자가 연결/모드/안전/실행 가능성을 tooltip 또는 popover로 이해할 수 있음 |
| E2. Runtime Tool Plan | 질문마다 Tool Plan JSON이 생성되고 chat stream/dashboard/API에서 확인됨 |
| E3. Evidence/RCA Context | 답변마다 수집 evidence, missing evidence, RCA Context JSON이 연결됨 |
| E4. RAG/Runbook foundation | pgvector 기반 RAG 저장소 계약, ingestion skeleton, search API가 있음 |
| E5. OS-aware Adapter | OpenShift/Linux/Windows Adapter contract와 status endpoint가 있음 |
| E6. Lightspeed context injection | Tool Plan/RCA Context가 Lightspeed 요청에 주입되고 hash/status가 확인됨 |
| E7. AIOps action lifecycle | proposal -> sealed plan -> approval -> execution 흐름이 UI에서 이해 가능 |
| E8. Operator/OLM readiness | 0.1.1 package/install/status가 CR status condition과 함께 검증됨 |
| E9. Model endpoint/routing | 회사 LLM endpoint 연동 계약과 quick/deep routing skeleton이 있음 |
| E10. Evaluation | 한국어 AIOps scenario 5개 이상이 자동 pass/fail로 평가됨 |

## 요구사항 매핑

| PDF 요구 | 0.1.1에서 끝낼 것 | 구현 대상 | Evidence |
| :--- | :--- | :--- | :--- |
| 기존 OpenShift 보존 + 신규 Plugin/Gateway | Kugnus 전용 리소스만 사용, 기존 공용 plugin 불변 검증 | `scripts/kugnus-olm.sh`, status docs | `oc get consoleplugin` before/after |
| UserToken RBAC 진입 통제 | Gateway 진입 시 subject/access review 결과 UI 표시 | Gateway status, header popover | `/v1/auth/subject`, `/v1/aiops/status` |
| KOMSCO AIOps Model | 모델 endpoint contract와 deterministic planner fallback | Gateway planner module | config + tests |
| Tool Plan JSON | 질문별 plan 생성/저장/stream event | Gateway chat stream, Dashboard | `tool_plan` event, UI panel |
| Evidence Planner | event/log/metric/runbook/audit 수집 계획과 누락 이유 | Evidence schema/API | `/v1/evidence`, chat evidence refs |
| OS-aware Adapter | OpenShift/Linux/Windows adapter contract | Adapter registry/status | `/v1/adapters` or status payload |
| RAG/Runbook | pgvector contract, ingestion skeleton, search API | RAG module, docs | `/v1/rag/search` mock/minimal |
| RCA Context JSON | cause/evidence/action/confidence context 생성 | Gateway RCA context builder | `rca_context` event |
| Lightspeed streaming | Gateway context를 OLS payload에 주입 | OLS request builder | context digest/status |
| Safety Guard | read-only 기본, mutation/exec gate 명확화 | Header UX, Gateway policy | UI verifier + tests |
| OLM 표준 배포 | 0.1.1 package/install/status 검증 | package scripts, runbook | `task kugnus:package/status` |
| 모델 구성/PoC 기준 | Qwen/Gemma 라우팅 평가 기준 문서화 | model-routing doc/eval | eval report |
| RAG 저장소 권장 | PostgreSQL + pgvector schema와 ACL metadata | `rag-storage-contract.md` | schema doc + skeleton |

## 구현 순서

### Phase 1. 상태 UX와 계약 정리

목표: 사용자가 지금 헤더에 떠 있는 칩의 의미를 바로 이해하게 만든다.

작업:

- Header status를 `Connection`, `Mode`, `Safety`, `Executor`로 재구성한다.
- `방패`는 Safety popover로 만든다.
- `>_`는 Executor 상태로 만들고 disabled reason을 표시한다.
- 의미 없는 `i`는 popover로 의미를 부여하거나 제거한다.
- UI verifier에 header status 의미 검증을 추가한다.

Pass:

- 각 상태 요소는 accessible label과 tooltip/popover를 가진다.
- disabled executor는 이유를 표시한다.
- `task kugnus:ui:verify`가 관련 항목을 검증한다.

### Phase 2. Tool Plan runtime화

목표: PDF의 Tool Plan JSON을 실제 runtime artefact로 만든다.

작업:

- `ToolPlan` Pydantic/TypeScript schema 작성.
- deterministic planner 구현:
  - Pod restart RCA
  - Pod status/list/count
  - ClusterOperator status
  - CronJob activity
  - generic OpenShift question
- chat stream에서 `tool_plan` event 송신.
- 최신 Tool Plan을 `/v1/aiops/status`에 노출.
- Dashboard `Tool Plan JSON`이 샘플이 아니라 최신 plan을 보여주게 변경.

Pass:

- 한국어 질문 "어제 새벽 default namespace Pod가 왜 재시작됐어?"에 `pod_restart_rca` plan 생성.
- `execution_policy.mode`는 기본 `read_only`.
- forbidden action이 있으면 validator가 fail.
- UI에서 latest runtime plan 확인 가능.

### Phase 3. Evidence/RCA Context 연결

목표: 답변이 어떤 증거로 만들어졌는지 추적 가능하게 만든다.

작업:

- `EvidenceRecord`와 `RcaContext` schema 작성.
- 수집 evidence와 missing evidence를 구분한다.
- Pod/CronJob/Operator preflight evidence를 schema에 맞게 변환한다.
- metric evidence는 사용 가능 여부와 unavailable reason을 명확히 기록한다.
- chat stream에서 `evidence_ref`, `rca_context` event 송신.
- assistant 답변 하단에 evidence summary 표시.

Pass:

- evidence가 없으면 "확인됨" 단정 답변 금지.
- answer마다 context digest 또는 evidence id가 남는다.
- Dashboard Evidence posture가 collected/missing을 실제 record 기반으로 표시한다.

### Phase 4. RAG/Runbook foundation

목표: PDF의 PostgreSQL + pgvector 권장안을 0.1.1에서 PoC 가능한 형태로 만든다.

작업:

- `docs/Ver.0.1.1/rag-storage-contract.md` 작성.
- pgvector schema 초안:
  - document
  - chunk
  - embedding
  - acl metadata
  - checksum/version
- ingestion CLI skeleton 작성.
- `/v1/rag/search` API skeleton 작성.
- 검색 결과를 RCA Context evidence에 넣을 수 있는 형태로 반환.

Pass:

- RAG가 없으면 UI에 `not configured`로 표시.
- mock/minimal search 결과가 `runbook` evidence type으로 들어간다.
- Gateway 외부 직접 DB 접근 금지 원칙이 문서화된다.

### Phase 5. OS-aware Adapter registry

목표: OpenShift/Linux/Windows Adapter가 설계 문서가 아니라 runtime status로 보이게 한다.

작업:

- `AdapterRegistry` 작성.
- OpenShift Adapter: event, resource, log, metric capabilities 표시.
- Linux Adapter: diagnostics gate 뒤에 journalctl/systemctl/dmesg 등 capability 표시.
- Windows Adapter: planned/mock status와 required credential/agent 조건 표시.
- Tool Plan step을 Adapter capability로 resolve하는 함수 작성.

Pass:

- `/v1/aiops/status`가 adapter별 supported tools와 disabled reason을 반환한다.
- Dashboard가 "planned"만 보여주는 대신 이유와 next action을 보여준다.
- OpenShift Adapter는 최소 3개 tool step을 resolve한다.

### Phase 6. Lightspeed context injection

목표: Gateway가 수집한 context가 Lightspeed 최종 답변에 들어가는 경로를 검증 가능하게 만든다.

작업:

- OLS request builder를 분리한다.
- OLS payload에 `gateway_context` 포함:
  - tool_plan
  - evidence_summary
  - missing_evidence
  - rca_context
  - safety_contract
- context digest를 audit record와 stream event에 남긴다.
- status endpoint에 last OLS stream success/fail timestamp를 추가한다.

Pass:

- OLS 요청마다 context digest가 남는다.
- OLS 실패 시 fallback answer임을 UI에 표시한다.
- status panel의 `streamProbe`가 `not_probed_by_status_endpoint`로 남지 않는다.

### Phase 7. Action lifecycle UX

목표: 실행 기능이 있는지 없는지, 왜 안 되는지, 승인 후 무엇이 실행되는지 사용자가 이해하게 한다.

작업:

- Action Executor configured 여부를 header popover와 right rail에 표시.
- proposal/plan/approval/execution record를 단계형 UI로 정리.
- read-only일 때는 action proposal을 만들지 않거나, 만든다면 disabled reason을 명확히 표시.
- evidence freshness 실패를 UI에 표시.

Pass:

- read-only 모드에서 mutation은 실행되지 않는다.
- execute 모드에서도 approval 없이 execution 불가.
- 실패 사유가 UI에 표시된다.

### Phase 8. OLM/Operator readiness

목표: 0.1.1 기능이 카탈로그/설치 경로에서도 재현 가능하게 한다.

작업:

- 기본 operator version을 `0.1.1` 또는 현재 릴리스 정책에 맞는 새 patch로 정리한다.
- `AIOpsInstallation.status.conditions`를 강화한다.
- Gateway, Plugin, ConsolePlugin, Service CA, RBAC condition을 표시한다.
- `task kugnus:package`, `task kugnus:install`, `task kugnus:status` 검증 항목 업데이트.

Pass:

- package 생성 시 CSV에 0.1.1 기능 env/config가 반영된다.
- install 후 CR status에서 Gateway/Plugin/ConsolePlugin readiness를 볼 수 있다.
- 기존 공용 plugin은 변경되지 않는다.

### Phase 9. Model endpoint/routing

목표: 회사 LLM endpoint를 안전하게 연결할 수 있는 계약을 만든다.

작업:

- `.env.example`에 model endpoint 변수 문서화.
- 실제 `.env`는 읽거나 commit하지 않는다.
- quick triage vs deep RCA routing skeleton 작성.
- model unavailable 시 deterministic planner fallback.
- JSON schema validation 실패 시 retry/fallback 정책 작성.

Pass:

- model endpoint가 없어도 로컬 PoC는 deterministic planner로 동작한다.
- model endpoint가 있으면 Tool Plan JSON schema validation을 통과해야 사용한다.
- 실패 시 fallback임을 audit/status에 남긴다.

### Phase 10. Evaluation 자동화

목표: "느낌상 좋아짐"이 아니라 AIOps 답변 품질을 자동 판정한다.

작업:

- `evals/aiops-scenarios/` 생성.
- 최소 5개 한국어 시나리오:
  - Pod restart RCA
  - CrashLoopBackOff
  - ImagePullBackOff
  - ClusterOperator degraded
  - CronJob 반복 실행/정책
- 평가 기준:
  - Tool Plan schema valid
  - evidence type match
  - missing evidence 표시
  - forbidden hallucination 없음
  - safety mode 준수
- `task kugnus:evaluate` 추가.

Pass:

- 5개 시나리오가 pass/fail report를 생성한다.
- 증거 없이 단정하면 fail.
- schema invalid면 fail.

## 최종 완료 체크리스트

| 체크 | Pass 기준 |
| :--- | :--- |
| UI | `task kugnus:ui:verify` 통과 |
| Gateway unit | Gateway pytest 통과 |
| Package | `task kugnus:package` 통과 |
| AIOps eval | `task kugnus:evaluate` 통과 |
| Tool Plan | latest runtime plan이 status/dashboard/chat event에 있음 |
| Evidence | collected/missing evidence가 답변과 status에 있음 |
| RAG | search skeleton과 storage contract가 있음 |
| Adapter | OpenShift/Linux/Windows status와 disabled reason 표시 |
| Lightspeed | context digest와 stream status가 남음 |
| Safety | read-only 기본값, mutation/unrestricted gate 유지 |
| OLM | 기존 공용 ConsolePlugin/Lightspeed 미변경 |

## 작업 순서 결론

0.1.1 첫 구현은 다음 순서가 가장 낫다.

1. Header status UX
2. Tool Plan schema/runtime event
3. Evidence/RCA Context schema
4. Dashboard/status 연결
5. Lightspeed context injection
6. AIOps scenario evaluator
7. RAG skeleton
8. OS Adapter registry
9. Action lifecycle UX
10. OLM/Operator condition 정리

이 순서는 사용자가 지금 바로 혼란을 느끼는 UI 문제를 먼저 해결하면서도, 바로 다음 단계에서 PDF의 핵심인 Tool Plan/Evidence/RCA Context로 이어진다.

