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
3. `/v1/rag/search`가 source metadata를 반환함
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

## 11. 구현 결과 및 검수 메모

작성 기준: `feat/v.0.1.4`

### 11.1 이번에 닫은 범위

- `POST /v1/rag/uploads` 추가
  - JSON 기반 사용자 문서 업로드 계약을 만든다.
  - `content` 또는 base64 `data` 중 하나만 받는다.
  - Ver.0.1.4 최소 범위는 UTF-8 텍스트/마크다운 계열 문서다.
  - raw content는 응답으로 반환하지 않는다.

- `GET /v1/rag/uploads` 추가
  - pgvector에 저장된 `sourceType=user-upload` 문서 목록을 반환한다.
  - 좌측 확장 패널의 업로드 문서 탭이 이 endpoint를 조회한다.

- pgvector schema 확장
  - 기존 `aiops_rag_chunks`에 더해 `aiops_rag_documents`를 생성한다.
  - 업로드 문서는 `aiops_rag_documents`에 문서 metadata를 저장하고, chunk는 기존 `aiops_rag_chunks`에 저장한다.
  - 기존 `/v1/rag/search`는 `sourceTypes: ["user-upload"]` filter로 업로드 문서를 검색할 수 있다.
  - 업로드 ACL은 클라이언트 입력을 그대로 신뢰하지 않고, 현재 OpenShift subject의 group/user principal과 교집합이 있는 값만 저장한다.
  - `/v1/rag/uploads`와 `/v1/rag/search`는 subject principal과 ACL이 교차하는 문서만 반환한다.
  - `system:authenticated` 같은 광역 시스템 그룹은 기본 ACL에서 제외한다.
  - pgvector 조회 시 DB query 단계부터 ACL array overlap을 적용해 전역 top-k 이후 필터링으로 인한 false-empty를 줄인다.
  - kubeconfig의 `client-key-data`, `client-certificate-data`, `certificate-authority-data`도 chunk 저장 전에 redact한다.
  - 업로드 chunk label에 `safetyClass`와 `freshness`를 보존하고, 위험 명령 패턴이 있는 문서는 `dangerous`로 승격한다.
  - `dangerous` 또는 `stale` 문서는 기본 RAG context/citation에서 제외하고, 명시 필터가 있을 때만 검색 계약상 포함할 수 있다.
  - OLM runtime은 `spec.rag.backendUrlSecret/backendUrlKey`를 통해 `KOMSCO_AI_RAG_BACKEND_URL`을 Gateway에 Secret env로 주입할 수 있다.

- 프론트 연결
  - 좌측 패널 상단의 큰 `+ 새 채팅` 버튼을 아이콘 toolbar로 바꿨다.
  - 대화 기록 아이콘과 업로드 문서 아이콘을 분리해 패널 view를 전환한다.
  - 업로드 문서 패널 토글 아이콘을 추가했다.
  - 첨부 버튼은 기존 이미지 첨부를 유지하면서 TXT/MD/JSON/YAML/log 문서를 RAG upload endpoint로 보낸다.
  - 업로드 성공 시 좌측 패널을 `업로드 문서` view로 전환하고, 업로드 문서 목록을 보여준다.
  - RAG backend가 `not_configured`/`unavailable`이면 빈 목록처럼 숨기지 않고 오류 상태로 표시한다.

- smoke task 추가
  - `task kugnus:rag:upload:smoke`
  - 실제 Gateway에 문서를 업로드하고, pgvector persist, 목록 조회, RAG search retrieval까지 확인한다.
  - `task kugnus:rag:chat:smoke`
  - 채팅 SSE에서 `rag_context_evidence`와 답변의 `[ RAG 근거 ]` citation이 보이는지 확인한다.

### 11.2 병렬 검수 반영

- 문서 검수: 0.1.4 문서는 방향은 맞지만, 업로드 ingestion이 없으면 완료로 볼 수 없다고 판단했다.
- 백엔드 검수: 기존 상태는 demo runbook search contract 수준이었고, user upload endpoint와 backend write가 없었다.
- 프론트 검수: 업로드 문서 패널은 placeholder였고, 접근성 `aria-pressed`, 실제 list fetch, document icon이 부족했다.

위 지적에 따라 upload endpoint, pgvector document table, upload smoke, data-backed uploaded document panel, document icon, `aria-pressed`, subject 기반 ACL enforcement, 답변 citation smoke를 반영했다.

### 11.3 검증 결과

- `python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py`: pass
- `cd komsco-ai-gateway && . .venv/bin/activate && python -m pytest`: `179 passed, 2 warnings`
- `cd komsco-ai-console-plugin && corepack yarn build`: pass
- `task kugnus:scenario:verify`: `10 passed, 0 failed`
- `task kugnus:runtime:smoke`: pass
  - `health=92`, `nodes=1/1`, `operators=34/34`
  - `rag=collected`, `backend=pgvector`, `results=1`
- `task kugnus:rag:upload:smoke`: pass
  - upload HTTP 200
  - list HTTP 200
  - search HTTP 200
  - `upload-persisted`
  - `list-includes-upload`
  - `search-finds-upload`
- `task kugnus:rag:chat:smoke`: pass
  - chat stream HTTP 200
  - `rag_context_evidence` SSE event emitted
  - answer stream includes `[ RAG 근거 ]`
  - uploaded document id/title appears in RAG stream evidence

### 11.4 아직 0.1.5 이후로 넘기는 범위

- PDF/Office 문서 parser
- multipart upload endpoint
- upload stream progress event
- delete/re-ingest endpoint
- 문서 freshness의 시간 기반 자동 만료 판정
- 위험 문서 `dangerous` safety class의 정책 엔진화
- Chrome CDP 기반 `task kugnus:ui:verify` 안정화

### 11.5 주의: UI verifier 상태

`task kugnus:ui:verify`는 이번 실행에서 `Chrome CDP endpoint missing`으로 실패했다. 이는 UI 코드 빌드 실패가 아니라 Windows Chrome remote debugging endpoint `localhost:9231`에 연결하지 못한 상태다. 따라서 UI verifier는 pass로 보고하지 않는다. 대신 frontend build와 backend/API smoke, upload smoke, chat citation smoke를 이번 0.1.4 검증 증거로 사용한다.
