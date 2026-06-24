# Ver.0.1.1 3-Reviewer Gate Protocol

작성 기준일: 2026-06-24 KST  
브랜치: `feat/v.0.1.1`  
목적: 0.1.1 남은 기능 단계를 끝낼 때마다 3명 검수 기준으로 pass/fail을 판정하고, 하나라도 fail이면 해당 단계를 rework로 돌린다.

## 이 문서의 단계 기준

0.1.1 전체 완료 정의는 `pdf-requirements-completion-plan.md`의 10 Epic이다.
다만 현재 Goal에서 실행하는 `1부터 8단계`는 전체 10 Epic을 처음부터 다시 세는 목록이 아니다.
이미 완료되어 push된 기준선 이후에 남은 기능 stage 8개를 뜻한다.

완료된 기준선:

- UI polish lock: `9c3c53e`
- Header status disabled reason 1차: `9c3c53e`
- Runtime Tool Plan 1차: `c081832`
- 0.1.1 요구사항 산출물: `19268dc`

따라서 이 문서에서 Stage 1은 Header가 아니라 **Evidence/RCA Context 연결**이다.
Header와 Runtime Tool Plan은 필요 시 회귀 검증 대상이지만, 현재 8단계의 첫 작업 단위는 아니다.

## 기본 원칙

- 각 단계는 구현, 테스트, 문서 evidence, 검수 기록이 모두 있어야 완료로 본다.
- Reviewer A/B/C 중 한 명이라도 fail이면 다음 단계로 넘어가지 않는다.
- fail 사유는 감정이나 취향이 아니라 깨진 계약, 빠진 evidence, 회귀, 사용자가 헷갈릴 UI, 안전 위반, 테스트 공백으로 적는다.
- rework 후에는 같은 단계의 3명 검수를 다시 수행한다.
- `.env`, token, kubeconfig, password, 회사 인증정보는 어떤 단계에서도 commit하지 않는다.
- 회사 OCP 기존 공용 `komsco-ai-console-plugin`, `lightspeed-console-plugin`, 공용 namespace는 교체하거나 삭제하지 않는다.

## 검수자 역할

| Reviewer | 관점 | Fail 조건 |
| :--- | :--- | :--- |
| A. Product/Requirements | PDF 요구사항, 산출물 추적성, pass/fail evidence | 요구사항과 구현 연결이 불명확하거나, 문서와 코드가 다른 상태 |
| B. Backend/Safety | Gateway 계약, read-only safety, API schema, 테스트 | mutation gate 누락, 증거 없는 단정, schema/test 미흡 |
| C. Frontend/UX | UI 의미, OpenShift/PatternFly 적합성, verifier, screenshot | 사용자가 버튼/상태 의미를 모름, 레이아웃 회귀, verifier 미포함 |

## 단계별 게이트

### Stage 1. Evidence/RCA Context 연결

목표: 질문/답변 단위로 수집 evidence, missing evidence, RCA Context JSON을 연결한다.

필수 작업:

- `EvidenceRecord`와 `RcaContext` runtime schema 정의
- 모든 chat run에 trace 가능한 `rca_context` event 추가
- evidence가 있는 경우 `evidence_ref` event와 `rca_context.evidence_refs`를 연결
- Pod/CronJob/Operator preflight 결과를 schema 기반 evidence로 변환
- evidence가 없는 경우 `missing_evidence`와 uncertainty reason을 남김
- evidence가 없으면 "확인됨"으로 단정하지 않도록 fallback 문구 조정

Pass evidence:

- Gateway tests
- 최소 1개 chat stream에서 `rca_context.id`, `digest`, `evidence_refs` 또는 `missing_evidence` 확인
- Dashboard/assistant에서 수집/누락 evidence가 구분됨

Return 조건:

- 증거 없는 원인 단정
- evidence와 answer를 추적할 id/digest 부재
- `rca_context`가 sample/static fixture로만 존재함
- UI에 fake 또는 sample evidence가 실제처럼 표시됨

### Stage 2. 답변 하단 Evidence Reference 표시

목표: 사용자가 답변의 근거와 누락 근거를 채팅 화면에서 바로 확인한다.

필수 작업:

- assistant message 하단에 evidence summary/ref 표시
- missing evidence는 경고 또는 "추가 확인 필요"로 분리
- evidence id/digest와 answer 사이의 추적성을 유지
- token, subject, namespace 등 표시 전 redaction 기준 확인
- 복사/스크롤/스트리밍/정지 버튼 회귀 방지

Pass evidence:

- `task kugnus:ui:verify`
- screenshot inspection
- evidence 없는 답변과 evidence 있는 답변의 UI 차이 확인

Return 조건:

- 답변 본문을 밀어내거나 채팅 가독성을 해침
- evidence가 너무 많은 공간을 차지함
- missing evidence가 성공 evidence처럼 보임
- 민감정보가 evidence footer나 copy text에 노출됨

### Stage 3. RAG/Runbook Storage Contract + Search Skeleton

목표: PDF의 PostgreSQL + pgvector 권장안을 PoC 가능한 계약과 API skeleton으로 만든다.

필수 작업:

- `rag-storage-contract.md` 작성
- document/chunk/embedding/ACL/checksum/version schema 초안
- ingestion CLI skeleton
- `/v1/rag/search` mock/minimal API
- RAG backend 미설정 시 `not_configured` 상태 반환
- Gateway 외 직접 DB 접근 금지 원칙 명시

Pass evidence:

- docs + schema
- API route test
- RAG not configured 상태가 UI/API에 명확히 표시

Return 조건:

- DB credential이나 실제 비밀값 commit
- ACL metadata 없이 검색 가능하다고 표시
- mock 결과를 실제 검색 완료처럼 표시

### Stage 4. OS-aware Adapter Registry/Status

목표: OpenShift/Linux/Windows adapter capability와 disabled/planned reason을 runtime status로 노출한다.

필수 작업:

- `AdapterRegistry` 또는 동일 역할 모듈 작성
- OpenShift capability 최소 3종 resolve
- Linux diagnostics gate와 disabled reason 표시
- Windows planned/mock status와 필요 조건 표시
- Tool Plan step을 adapter capability로 resolve하고 실패 reason을 남김

Pass evidence:

- `/v1/aiops/status`에 adapter별 supported tools, status, reason 포함
- Dashboard가 adapter 상태, disabled reason, next action을 표시
- tests + UI verifier

Return 조건:

- Linux/Windows가 실제 준비된 것처럼 보임
- disabled reason 없음
- Tool Plan step이 adapter capability로 resolve되지 않음

### Stage 5. Lightspeed Context Injection 검증

목표: Tool Plan/RCA Context/Evidence/Safety가 OLS 요청에 들어가는지 검증 가능하게 만든다.

필수 작업:

- OLS request builder 분리
- `gateway_context`에 tool plan, evidence summary, missing evidence, rca context, safety contract 포함
- context digest를 audit/status/stream event에 남김
- OLS last success/fail 또는 probe 상태를 status에서 구분
- OLS 실패 시 fallback answer임을 UI에 표시

Pass evidence:

- request builder unit test
- stream event 또는 status에서 context digest 확인
- `streamProbe`가 계속 `not_probed_by_status_endpoint`로만 남지 않음

Return 조건:

- context가 prompt 문자열에만 섞여 schema로 추적 불가
- OLS 실패와 fallback이 구분되지 않음
- token/secret이 OLS payload나 audit에 섞임

### Stage 6. Action Lifecycle UX 정리

목표: proposal -> sealed plan -> approval -> execution 흐름과 비활성 이유를 사용자가 이해한다.

필수 작업:

- Action Executor configured 여부와 disabled reason UI 표시
- proposal/plan/approval/execution record 단계형 표시
- read-only mode에서는 mutation 실행 불가를 명확히 표시
- evidence freshness failure 표시
- execute 시 sealed plan digest, active approval, freshness, SSAR, mutation flag를 모두 확인

Pass evidence:

- Gateway action tests
- UI verifier에서 disabled reason/action lifecycle 의미 검증
- read-only에서 mutation 실행 불가 evidence

Return 조건:

- approval 없이 execute 가능
- digest mismatch 또는 만료된 approval로 execute 가능
- read-only에서 mutation 가능하거나 가능해 보임
- 실패 reason이 UI에 없음

### Stage 7. OLM/Operator 0.1.1 Readiness

목표: 0.1.1 기능이 catalog/package/install/status 경로에서도 재현 가능하게 한다.

필수 작업:

- package/install/status task 검증
- CSV/env/config에 0.1.1 기능 계약 반영
- CR status condition 강화 여부 확인
- 기존 공용 plugin 변경 없음 검증
- `publish`는 catalog/package visibility까지만 수행하고 install은 별도 명령으로 유지

Pass evidence:

- `task kugnus:package`
- `task kugnus:status`
- 필요 시 별도 승인 후 install 검증
- 기존 `komsco-ai-console-plugin`, `lightspeed-console-plugin` 불변 확인

Return 조건:

- publish가 install까지 수행
- 공용 plugin/namespace 변경
- Kugnus 이름 충돌 방어 없음

### Stage 8. AIOps Evaluation 자동화

목표: 한국어 AIOps 시나리오 5개 이상을 자동 pass/fail로 평가한다.

필수 작업:

- `evals/aiops-scenarios/` 생성
- Pod restart RCA, CrashLoopBackOff, ImagePullBackOff, ClusterOperator degraded, CronJob scenario 작성
- evaluator가 Tool Plan schema, evidence match, missing evidence, hallucination, safety mode 평가
- `task kugnus:evaluate` 추가

Pass evidence:

- `task kugnus:evaluate`
- 5개 이상 scenario report
- 증거 없이 단정하면 fail
- schema invalid면 fail

Return 조건:

- 수동 눈대중 평가
- scenario가 UI만 보고 API/contract를 검증하지 않음
- 실패 케이스를 pass로 처리

## 단계 종료 절차

1. 구현자가 stage 완료 후보를 만든다.
2. 구현자는 관련 테스트와 verifier를 먼저 통과시킨다.
3. Reviewer A/B/C가 각각 pass/fail과 rework 항목을 남긴다.
4. 세 명 모두 pass면 stage를 완료 처리한다.
5. 하나라도 fail이면 fail 항목을 작업 queue에 넣고 같은 stage를 다시 수행한다.
6. stage 완료 commit message는 `complete ver.0.1.1 stage N ...` 형식으로 남긴다.

## 현재 기준선

- UI polish lock 완료: `9c3c53e`
- Runtime Tool Plan 1차 완료: `c081832`
- 0.1.1 요구사항 산출물 commit: `19268dc`
- 다음 구현 stage: Stage 1 Evidence/RCA Context 연결
