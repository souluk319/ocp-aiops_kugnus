# Ver.0.1.4 PBS 사용자 업로드 RAG 파이프라인 조사

작성일: 2026-06-25  
참조 프로젝트: `/mnt/c/Users/soulu/cywell/OCPOps-PBS-Dev-v2`  
현재 프로젝트 브랜치: `feat/v.0.1.4`

## 1. 결론

PBS 프로젝트에는 사용자가 문서를 업로드하면 RAG에 들어갈 수 있도록 처리하는 파이프라인이 이미 있다. 우리 KOMSCO AIOps 챗봇의 파일 첨부 버튼은 이 기능을 붙일 명확한 후보 지점이다.

단, PBS 코드를 통째로 복붙하면 안 된다. 우리 프로젝트에는 OpenShift 콘솔 플러그인, Gateway, pgvector dev RAG, Evidence/RCA, Action Executor라는 별도 제품 맥락이 있으므로 **기능 단위로 선별 이식**해야 한다.

## 2. PBS에서 확인한 핵심 흐름

PBS 업로드 파이프라인은 다음 흐름을 갖는다.

1. 프론트에서 파일을 `FormData`로 전송
2. 서버가 안전한 파일명으로 object storage 하위에 저장
3. 문서 포맷 감지
4. 문서 파싱: md/txt/pdf/docx/pptx/xlsx/image 등
5. block 추출
6. chunk 생성
7. PostgreSQL에 document source / parsed document / blocks / assets / chunks 저장
8. pgvector embedding indexing
9. ingestion report 생성
10. quality gate와 ready_for_chat 상태 반환
11. stream API로 진행 상황을 프론트에 전달

## 3. 참고한 PBS 파일

| 파일 | 가져올 만한 기능 |
|---|---|
| `src/play_book_studio/http/upload_api.py` | 업로드 저장, 중복 처리, stage event, failure report, ingestion report, stream handler |
| `src/play_book_studio/ingestion/document_parsing.py` | 문서 포맷 감지, markdown 변환, block/asset/chunk 모델 |
| `src/play_book_studio/db/document_repository.py` | document source, parsed document, block, asset, chunk persist 구조 |
| `src/play_book_studio/db/embedding_indexer.py` | pending chunk를 pgvector embedding으로 index하는 구조 |
| `db/migrations/0001_ingestion_foundation.sql` | documents/versions/parse_jobs/blocks/assets/chunks 기본 schema |
| `db/migrations/0010_pgvector_chunk_embeddings.sql` | `chunk_embeddings` pgvector schema와 HNSW index |
| `apps/web/src/lib/runtimeApi.ts` | `uploadDocumentIngestion`, `uploadDocumentIngestionStream`, `loadUploadIngestReport`, `deleteUploadedDocument` API client |
| `src/play_book_studio/evals/user_upload_rag_eval.py` | 업로드 문서 기반 RAG 평가 구조 |

## 4. 우리 프로젝트에 바로 가져올 최소 기능 세트

### 4.1 Backend 최소 세트

- `/v1/aiops/uploads/ingest`
- `/v1/aiops/uploads/ingest/stream`
- `/v1/aiops/uploads/reports/{document_source_id}`
- `/v1/aiops/uploads/delete`
- local object storage: `.aiops-storage/uploads/**`
- upload source table
- parsed document table
- document chunk table
- chunk embedding table
- ingestion report JSON

### 4.2 Frontend 최소 세트

- 현재 챗봇 composer의 첨부 버튼에 파일 선택 연결
- 업로드 진행 상태 표시: store, parse, chunk, persist, index, ready
- 업로드된 문서를 현재 대화의 RAG scope에 연결
- 답변에서 “사용자 업로드 문서 근거”를 별도 badge로 표시
- 실패 시 실패 stage와 report link 표시

### 4.3 RAG 최소 세트

- upload document chunks를 기존 pgvector RAG 검색 대상에 포함
- 기본 검색은 official/internal runbook + user upload를 함께 검색
- 필요 시 `restrictUploadedSources` 옵션으로 업로드 문서만 검색
- citation/source에 `uploaded-document` 표시
- stale/missing/dangerous evidence 구분 유지

## 5. 우리 제품에 맞게 바꿔야 할 점

PBS는 PlayBookStudio용 구조이고, 우리는 OpenShift AIOps 콘솔 플러그인이다. 따라서 다음은 그대로 가져오지 않는다.

- PBS viewer route 전체
- PBS course/runtime/learning 기능
- PBS terminal/session 기능
- Neo4j/graph sidecar 전체
- Qdrant legacy 흔적
- customer pack 전체 기능
- PBS 전용 UI 레이아웃

가져올 것은 “업로드 문서가 RAG source가 되는 pipeline”뿐이다.

## 6. 안전 설계

| 위험 | 대응 |
|---|---|
| token/kubeconfig 업로드 | 파일 내용 redaction scan 또는 reject policy 필요 |
| 너무 큰 파일 | size limit, page/chunk limit, timeout |
| OCR/이미지 처리 비용 | 0.1.4에서는 optional로 두고 기본은 텍스트 중심 |
| 문서 중복 | SHA256 + owner/session scope로 중복 처리 |
| 근거 없는 답변 | 업로드 문서 검색 실패 시 missing evidence 표시 |
| 위험 조치 문서 | safety_class를 `dangerous`로 분류하고 자동 실행 금지 |
| 회사 OCP 오염 | 업로드/RAG는 로컬 개발 DB 기준. OCP 리소스 변경과 분리 |

## 7. 0.1.4 구현 순서 제안

1. PBS 업로드 파이프라인에서 필요한 모델/스키마만 축소 설계
2. 우리 Gateway에 upload ingestion endpoint 추가
3. local object storage 디렉터리 추가
4. pgvector schema에 `aiops_documents`, `aiops_document_chunks`, `aiops_chunk_embeddings` 추가
5. `md/txt/pdf/docx`부터 parser 지원
6. chunker 구현
7. hashing embedding으로 먼저 index
8. `/v1/aiops/rag/search`가 upload chunk source를 반환하게 변경
9. 챗봇 첨부 버튼을 upload stream API에 연결
10. 답변 citation에 uploaded document source 표시
11. user-upload RAG smoke/eval 추가

## 8. 완료 조건

0.1.4에서 이 기능은 다음이 되면 완료로 본다.

1. 챗봇에서 파일 첨부 가능
2. 업로드 진행 상태가 UI에 표시됨
3. 업로드 문서가 pgvector에 chunk/embedding으로 들어감
4. 공식 질문 또는 별도 질문에서 업로드 문서가 근거로 검색됨
5. 답변에 업로드 문서 citation/source가 표시됨
6. 실패 시 어느 stage에서 실패했는지 report로 확인 가능
7. `task kugnus:rag:upload:smoke` 같은 pass/fail 검증이 존재함

## 9. 현재 판단

사용자 말대로 채팅창 첨부 버튼은 단순 UI 장식으로 두면 안 된다. PBS에 이미 구현된 파이프라인이 있으므로, 0.1.4는 RAG 설계뿐 아니라 **사용자 업로드 문서 RAG ingestion**을 핵심 목표로 잡는 것이 맞다.
