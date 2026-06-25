# Ver.0.1.3 pgvector RAG Demo Implementation Report

## 목적

최종 PDF가 요구하는 `사내 Runbook / SOP 연동 (RAG)`을 내일 시연에서 최소 한 사이클로 보여줄 수 있게 로컬 전용 pgvector 검색 루프를 추가했다.

## 현재 판단

- 500은 Gateway 코드 장애가 아니라 잘못된 토큰 전달 검증의 false-positive였다.
- 현재 18080 Gateway는 OCP summary/overview/runbook/RAG contract 모두 200으로 응답한다.
- RAG는 더 이상 `not_configured`가 아니다.
- 현재 로컬 Gateway는 `PostgreSQL + pgvector` backend를 사용해 seed runbook 3개 이상을 반환한다.

## 구현 내용

| 영역 | 변경 |
| --- | --- |
| Gateway dependency | `psycopg[binary]>=3.2,<4` 추가 |
| RAG search | `/v1/rag/search`가 `KOMSCO_AI_RAG_BACKEND_URL` 설정 시 pgvector backend를 조회 |
| Embedding | 내일 시연용 deterministic hashing 64-dim vector 사용 |
| Seed runbook | Pod restart/OOMKilled, ImagePullBackOff, etcd fragmentation, ClusterOperator degraded, approved bounded action |
| DB schema | `aiops_rag_chunks` table + `vector(64)` column |
| Dev backend | `scripts/kugnus-rag-pgvector-dev.sh` 추가 |
| Task | `task kugnus:rag:dev:up`, `task kugnus:dev:be:execute:rag`, `task kugnus:runtime:smoke` 추가 |
| Report | `docs/Ver.0.1.3/runtime-smoke-report.json` 생성 |

## 보안/운영 경계

- 로컬 pgvector는 `127.0.0.1:15432`에만 bind된다.
- repo에 DB password를 저장하지 않는다.
- 로컬 dev container는 `POSTGRES_HOST_AUTH_METHOD=trust`를 사용한다.
- Gateway만 DB에 접근한다.
- Frontend/LLM/ConsolePlugin에는 DB credential을 주지 않는다.
- 회사 OCP에는 `oc apply/delete/patch/scale/exec`를 실행하지 않았다.

## 현재 실행 상태

| 항목 | 상태 |
| --- | --- |
| Gateway | `0.0.0.0:18080` running |
| Local console | `http://localhost:9000/dashboards` 200 |
| Plugin webpack | `9001` running |
| pgvector | `kugnus-rag-pgvector`, `127.0.0.1:15432` running |
| RAG backend URL | `postgresql://komsco_aiops@127.0.0.1:15432/komsco_aiops` |
| Embedding model label | `hashing-bow-v1` |
| Vector dimensions | `64` |

## 검증 결과

명령:

```bash
task kugnus:runtime:smoke
```

결과:

```text
Runtime smoke: PASS
[PASS] healthz HTTP 200
[PASS] auth-subject HTTP 200
[PASS] cluster-summary HTTP 200
       health=92 nodes=1/1 operators=34/34
[PASS] aiops-overview HTTP 200
[PASS] runbooks-registry HTTP 200
[PASS] rag-search-contract HTTP 200
       rag=collected backend=pgvector configured=True results=3
```

추가 검증:

```text
4 passed, 166 deselected
```

대상 테스트:

- `test_rag_ingestion_cli_redacts_sensitive_preview`
- `test_rag_ingestion_cli_redacts_pem_before_chunking`
- `test_rag_search_returns_not_configured_contract_without_backend`
- `test_aiops_status_api_exposes_runtime_capabilities_and_recent_records`

## 내일 시연에서 말해도 되는 것

- 최종 PDF의 RAG 저장소 기본안인 PostgreSQL + pgvector를 로컬 시연 backend로 연결했다.
- 현재 Gateway는 runbook seed를 pgvector에 적재하고 `/v1/rag/search`로 검색한다.
- 공식 Evidence RCA 질문에서 Pod restart/OOMKilled 관련 runbook evidence를 검색 결과로 붙일 수 있다.
- 이 구현은 production embedding 모델이 아니라 내일 시연용 deterministic embedding이다.

## 내일 시연에서 말하면 안 되는 것

- 사내 전체 Runbook/SOP가 이미 embedding 완료됐다고 말하면 안 된다.
- production-grade semantic embedding/reranker가 붙었다고 말하면 안 된다.
- 회사 OCP에 pgvector DB를 설치했다고 말하면 안 된다.
- unrestricted mode가 공식 운영 기본이라고 말하면 안 된다.

## 다음 작업

1. 공식 Evidence RCA chat 답변에 RAG result를 자연스럽게 포함시킨다.
2. UI right rail의 RAG 상태가 `RAG configured/collected`로 보이는지 브라우저에서 확인한다.
3. 시연 질문 하나를 고정하고, 답변에 `Runbook evidence`가 들어가는지 캡처한다.
4. production 단계에서는 hashing embedding을 실제 사내 embedding/reranker로 교체한다.
