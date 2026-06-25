# Ver.0.1.3 Pre-demo Runtime/RAG Scope And 500 Report

## 목적

내일 시연 전에 현재 로컬 개발 서버, 회사 OCP 조회 경로, RAG/Runbook 범위를 혼동하지 않도록 문제 상태와 테스트 범위를 고정한다.

## 현재 판단

- 현재 작업 서버는 WSL 로컬 개발 서버다.
- 로컬 Gateway/Frontend 코드는 자유롭게 수정해도 된다.
- 다만 로컬 Gateway가 바라보는 대상은 회사 OCP API(`https://api.ocp.cywell.server:6443`)이므로, 회사 OCP에 영향을 주는 변경성 명령은 여전히 승인 전 금지다.
- 즉, 로컬 코드 수정과 회사 OCP mutation은 다른 문제다.

## 500 판정

초기 확인에서 `/v1/cluster/summary`, `/v1/aiops/overview`, `/v1/rag/search`가 500처럼 보였으나, WSL 내부에서 `oc whoami -t` 토큰을 정확히 전달해 재검증한 결과 현재 18080 Gateway는 정상 응답한다.

확인 결과:

| Endpoint | 결과 | 판단 |
| --- | --- | --- |
| `/healthz` | 200 | Gateway process alive |
| `/v1/auth/subject` | 200 | OpenShift bearer token accepted |
| `/v1/cluster/summary` | 200 | OCP node/operator/metrics summary 조회 가능 |
| `/v1/aiops/overview` | 200 | AIOps overview 조회 가능 |
| `/v1/rag/search` | 200 | API contract 응답 가능, 단 backend는 미설정 |

초기 500은 Gateway 코드 장애로 확정된 것이 아니라, 검증 명령을 WSL 밖에서 실행하면서 WSL bash 변수(`TOKEN`) 전달이 깨진 false-positive로 판단한다.

## 현재 RAG 상태

최종 PDF 기준으로 RAG는 필수 구조다.

문서 요구:

- AI Gateway가 RAG, Agent Tool, 보안/감사를 전담한다.
- 사내 Runbook/SOP 연동(RAG)이 Evidence RCA 흐름에 포함된다.
- 소규모 RAG 저장소는 PostgreSQL + pgvector를 기본안으로 적용한다.

현재 구현 상태:

| 항목 | 현재 상태 |
| --- | --- |
| Runbook registry | 있음 |
| `/v1/runbooks/registry` | 200 응답 |
| 내장 runbook | 5개 |
| `/v1/rag/search` | API contract 있음 |
| RAG backend type 기본값 | `pgvector` |
| RAG backend URL | 미설정 |
| 실제 pgvector 검색 | 아직 없음 |
| RCA에 runbook evidence 자동 연결 | 아직 제한적/미완성 |

현재 `/v1/rag/search` 응답 핵심:

```text
status: not_configured
backendType: pgvector
collection: komsco-aiops-runbooks
reason: KOMSCO_AI_RAG_BACKEND_URL is not configured; search returns no retrieved runbook evidence.
```

## 내일 시연에서 말해도 되는 것

- 로컬 OpenShift Console 개발환경이 회사 OCP를 read/execute contract로 관측한다.
- Gateway는 OCP node/operator/metrics/event/alert 데이터를 조회해 AIOps overview를 구성한다.
- Evidence RCA 시나리오의 Tool Plan, Evidence, Safety Contract 구조가 코드에 들어가 있다.
- Runbook registry와 RAG 검색 API contract는 있다.
- 최종 아키텍처상 RAG 저장소는 PostgreSQL + pgvector로 가는 것이 문서 기준 기본안이다.

## 내일 시연에서 말하면 안 되는 것

- pgvector RAG 검색이 이미 실제 운영 수준으로 붙었다고 말하면 안 된다.
- 실제 Runbook/SOP 문서가 embedding되어 검색된다고 말하면 안 된다.
- `default namespace`에 과거 재시작 Pod 로그가 항상 존재한다고 단정하면 안 된다.
- Cypress 브라우저 E2E가 WSL 의존성 문제 없이 pass됐다고 말하면 안 된다.
- 회사 OCP에 unrestricted command를 기본 운영 모드로 쓰겠다고 말하면 안 된다.

## 내일 전 우선 작업

1. RAG 최소 시연 루프 추가
   - PostgreSQL + pgvector 또는 로컬 skeleton backend 중 하나를 붙인다.
   - Runbook/SOP sample chunk를 3-5개 seed한다.
   - `/v1/rag/search`가 최소 1개 이상의 runbook evidence를 돌려주게 한다.
   - RCA Context에 `runbook` evidence ref가 붙는지 확인한다.

2. 공식 Evidence RCA 시나리오 재검증
   - 기준 문서: `docs/Ver.0.1.3/Evidence_RCA_Scene.md`
   - 질문: "어제 새벽에 default namespace Pod가 왜 재시작됐어?"
   - 결과는 RCA, 즉시 조치, 재발 방지책, 참고 증적 섹션을 포함해야 한다.

3. Gateway/OCP 연결 smoke test 고정
   - `/healthz`
   - `/v1/auth/subject`
   - `/v1/cluster/summary`
   - `/v1/aiops/overview`
   - `/v1/runbooks/registry`
   - `/v1/rag/search`

## Pass/Fail 기준

| 기준 | Pass | Fail |
| --- | --- | --- |
| Gateway alive | `/healthz` 200 | 500/connection refused |
| OCP auth | `/v1/auth/subject` 200 | Unauthorized/500 |
| OCP summary | node/operator/metrics 값 표시 | 데이터 없음/500 |
| Overview | dataSources와 anomalies 표시 | 필수 데이터 소스 실패 |
| RAG contract | `/v1/rag/search` 200 | endpoint 없음/500 |
| RAG 실검색 | result 1개 이상과 evidence ref 존재 | `not_configured` 유지 |
| 안전성 | mutation은 승인/Action Executor 경로 | 자연어에서 직접 delete/patch/scale 실행 |

## 현재 결론

500은 현재 재현되지 않는다. 로컬 Gateway와 OCP 조회 경로는 정상이다.

진짜 남은 문제는 RAG가 문서상 필수인데 아직 `not_configured`라는 점이다. 내일 시연 완성도를 올리려면 다음 작업은 500 수정이 아니라 PostgreSQL + pgvector 기반 최소 RAG 검색 루프를 붙이는 것이다.

## 2026-06-25 19:41 KST 업데이트

500 false-positive를 정리한 뒤 로컬 전용 pgvector RAG backend를 추가했다. 현재 18080 Gateway 기준 `task kugnus:runtime:smoke` 결과는 PASS이며, RAG contract는 다음 상태다.

```text
rag=collected backend=pgvector configured=True results=3
```

따라서 이 문서의 초기 `RAG not_configured` 항목은 문제 발견 당시의 상태 기록으로 유지하되, 현재 시연 기준은 `docs/Ver.0.1.3/pgvector-rag-demo-implementation-report.md`를 따른다.
