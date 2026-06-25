# Ver.0.1.4 RAG 아키텍처 설계

작성일: 2026-06-25  
브랜치: `feat/v.0.1.4`  
기준: Ver.0.1.3 로컬 시연 PASS 상태 이후

## 1. 목표

Ver.0.1.4의 목표는 RAG를 단순 demo 연결에서 운영 가능한 설계로 끌어올리는 것이다.

현재 0.1.3의 RAG는 pgvector dev DB와 hashing embedding으로 검색 계약을 통과하는 상태다. 0.1.4에서는 다음을 결정해야 한다.

- 어떤 문서를 수집할 것인가
- 어떻게 chunking할 것인가
- 어떤 metadata를 붙일 것인가
- 어떤 embedding 모델을 쓸 것인가
- 검색 결과를 Evidence/RCA 답변에 어떻게 연결할 것인가
- stale/없는/부정확한 문서를 어떻게 표시할 것인가

## 2. 현재 출발점

| 항목 | 현재 상태 |
|---|---|
| Backend | local Docker pgvector dev DB |
| DSN | `postgresql://komsco_aiops@127.0.0.1:15432/komsco_aiops` |
| Gateway env | `KOMSCO_AI_RAG_BACKEND_URL`, `KOMSCO_AI_RAG_EMBEDDING_MODEL`, `KOMSCO_AI_RAG_VECTOR_DIMENSIONS` |
| Embedding | `hashing-bow-v1`, 64 dimensions |
| Smoke result | `rag=collected backend=pgvector configured=True results=3` |
| 운영 수준 | demo/search contract 수준, production RAG 아님 |

## 3. RAG 대상 문서

우선순위는 운영자가 사고 대응 중 바로 써먹는 문서다.

1. OpenShift 운영 runbook
2. KOMSCO/Cywell AIOps 자체 조치 절차
3. 장애 유형별 RCA template
4. 승인/실행 정책 문서
5. 과거 시연/실습 시나리오 문서
6. OpenShift 공식 문서 중 필요한 좁은 범위
7. 회사 환경 특화 namespace/service/ConsolePlugin/Operator 설명

수집 금지 또는 제한:

- token, kubeconfig, `.env`, password, private key
- 고객사 내부 비공개 운영정보 중 승인되지 않은 내용
- 너무 오래되어 현재 OCP 버전과 맞지 않는 runbook
- 출처가 없는 인터넷 복붙 문서

## 4. 데이터 모델 초안

### 4.1 documents

| column | type | 의미 |
|---|---|---|
| id | uuid/text | 문서 ID |
| source_type | text | pdf, md, html, url, manual, runbook |
| source_uri | text | 원본 경로 또는 URL |
| title | text | 문서 제목 |
| version | text | 문서 버전 |
| owner | text | 소유/작성 주체 |
| created_at | timestamptz | 수집 시간 |
| updated_at | timestamptz | 갱신 시간 |
| freshness | text | fresh, stale, unknown |
| trust_level | text | official, internal-approved, draft, external-reference |

### 4.2 chunks

| column | type | 의미 |
|---|---|---|
| id | uuid/text | chunk ID |
| document_id | uuid/text | 상위 문서 |
| chunk_index | int | 순서 |
| heading_path | text | 문서 내 위치 |
| content | text | chunk 본문 |
| summary | text | 짧은 요약 |
| tags | text[] | crashloop, imagepull, operator, etcd 등 |
| os_scope | text | rhel, coreos, ubuntu, windows, generic |
| ocp_version_min | text | 적용 최소 버전 |
| ocp_version_max | text | 적용 최대 버전 |
| safety_class | text | read-only, approved-exec, dangerous |
| embedding | vector | embedding vector |

### 4.3 retrieval_events

| column | type | 의미 |
|---|---|---|
| id | uuid/text | 검색 이벤트 ID |
| query | text | 사용자 질문 또는 Tool Plan query |
| scenario_id | text | 연결된 시나리오 |
| top_k | int | 검색 개수 |
| selected_chunk_ids | text[] | 선택 chunk |
| missing_reason | text | 없거나 부족한 경우 이유 |
| created_at | timestamptz | 시각 |

## 5. Retrieval Pipeline

1. 질문 분석
2. Tool Plan 생성
3. query rewrite
4. vector search
5. metadata filter
6. rerank
7. evidence selection
8. answer grounding
9. missing evidence 표시
10. audit trail 기록

중요 원칙:

- 검색 결과가 없으면 없는 대로 말한다.
- 오래된 문서는 stale로 표시한다.
- 위험 조치 문서는 답변에 바로 실행 명령으로 내보내지 않는다.
- source URI와 heading path를 UI에 보여준다.

## 6. 평가 기준

| 평가 | pass 기준 |
|---|---|
| 검색 연결 | RAG backend configured, top-k 결과 반환 |
| 근거성 | 답변이 최소 1개 이상 chunk source를 참조 |
| 누락 처리 | 결과 부족 시 missing evidence로 표시 |
| 안전성 | dangerous chunk는 실행 명령으로 직접 승격되지 않음 |
| 최신성 | stale 문서가 stale로 표시됨 |
| 재현성 | 같은 질문에 같은 top document 계열이 반복적으로 검색됨 |

## 7. Ver.0.1.4 작업 순서

1. RAG schema migration 초안 작성
2. local pgvector table 생성 자동화
3. docs/Ver.0.1.3, final PDF 변환본, runbook seed를 ingestion source로 연결
4. chunker 구현
5. metadata/tagger 구현
6. embedding provider interface 분리
7. current hashing embedding 유지 + 교체 가능 구조 설계
8. retrieval endpoint 고도화
9. UI Evidence panel에 RAG source 표시 강화
10. RAG evaluation scenario 추가

## 8. 하지 않을 것

- 운영 DB를 바로 회사 OCP에 설치하지 않는다.
- 외부 embedding API key를 repo에 넣지 않는다.
- 출처 없는 문서를 official처럼 표시하지 않는다.
- 검색 결과가 없는데 RAG가 근거를 찾은 것처럼 답하지 않는다.
- 승인되지 않은 실행 명령을 RAG 문서에서 바로 자동 실행으로 넘기지 않는다.

## 9. 완료 조건

Ver.0.1.4는 다음이 되면 완료로 본다.

1. RAG schema와 ingestion source가 문서화됨
2. local pgvector에 실제 chunk가 들어감
3. `/v1/aiops/rag/search`가 source metadata를 반환함
4. 공식 질문에서 RAG evidence가 UI/응답에 보임
5. RAG 관련 smoke/evaluator가 pass/fail로 존재함
6. stale/missing/dangerous evidence가 구분됨

## 10. PBS 사용자 업로드 RAG 파이프라인 반영

참조 프로젝트 `/mnt/c/Users/soulu/cywell/OCPOps-PBS-Dev-v2`에서 사용자 문서 업로드 후 RAG에 연결하는 파이프라인을 확인했다.

핵심 흐름:

1. 프론트가 `FormData`로 파일 업로드
2. 서버가 안전한 storage path에 저장
3. 문서 포맷 감지
4. markdown/block/asset 추출
5. chunk 생성
6. PostgreSQL에 source/document/block/asset/chunk persist
7. pgvector embedding index
8. ingestion report와 quality gate 생성
9. stream API로 진행률 반환
10. 업로드 문서를 RAG search/citation에 포함

우리 프로젝트에 선별 이식할 최소 대상:

- upload ingestion endpoint
- upload stream progress event
- local object storage
- document/chunk/embedding schema
- ingestion report
- file attachment UI 연결
- uploaded document citation 표시
- upload RAG smoke/eval

가져오지 않을 대상:

- PBS viewer 전체
- PBS course/learning/runtime 기능
- terminal/session 기능
- graph sidecar 전체
- customer pack 전체

0.1.4 목표는 이제 단순 RAG schema 설계가 아니라 **챗봇 파일 첨부 -> 사용자 문서 ingestion -> pgvector 검색 -> Evidence/RCA 답변 citation**까지의 최소 end-to-end 경로를 설계하는 것이다.

근거 문서: `docs/Ver.0.1.4/pbs-user-upload-rag-import-analysis.md`

