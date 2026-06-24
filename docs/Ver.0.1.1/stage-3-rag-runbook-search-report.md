# Ver.0.1.1 Stage 3 RAG/Runbook Search Report

## 목표

Stage 3는 RAG/Runbook Storage Contract + Search Skeleton을 로컬 개발환경에 고정하는 단계다.
공식 회사 OCP에 등록, 설치, 배포하지 않는다.

## 구현 범위

- `docs/Ver.0.1.1/rag-storage-contract.md`
  - pgvector 기준 논리 schema
  - document/chunk/embedding/ACL/checksum/version metadata
  - Gateway-only 접근 원칙
  - backend 미설정 시 `not_configured` 계약
- `komsco-ai-gateway/komsco_ai_gateway/main.py`
  - `spec.capabilities.rag` runtime status 추가
  - `POST /v1/rag/search` skeleton 추가
  - backend 미설정 시 빈 결과와 missing runbook evidence 반환
  - `aiops_rag_search_requests_total` metric 추가
- `komsco-ai-gateway/scripts/ingest-rag-documents.py`
  - 로컬 ingestion plan 생성 skeleton
  - DB write 없음
  - ACL group 필수
- `komsco-ai-console-plugin/src/services/aiGateway.ts`
  - RAG capability type 추가
- `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx`
  - AIOps 실행 상태 rail에 RAG 상태 표시
- `komsco-ai-console-plugin/src/pages/AiopsPages.tsx`
  - dashboard capability board에 Runbook RAG 상태 표시
- `komsco-ai-gateway/tests/test_health.py`
  - status API의 RAG capability 검증
  - `/v1/rag/search` `not_configured` 계약 검증

## 하지 않은 것

- `oc apply` 실행 없음
- `helm install/upgrade` 실행 없음
- `task kugnus:publish`, `task kugnus:install`, `task catalog:register` 실행 없음
- 회사 OCP CatalogSource/PackageManifest/Subscription 생성 없음
- pgvector/PostgreSQL 설치 없음
- DB credential 또는 secret 추가 없음

## Acceptance Criteria

| 기준 | evidence | 상태 |
| --- | --- | --- |
| RAG 저장소 계약 문서 존재 | `rag-storage-contract.md` | PASS |
| API가 backend 미설정 시 `not_configured` 반환 | pytest `/v1/rag/search` | PASS |
| UI/API에 RAG 미구성이 표시됨 | status API + dashboard capability | PASS |
| mock 결과가 실제 검색 완료처럼 보이지 않음 | response `results=[]`, `mockResultsAreProductionEvidence=false` | PASS |
| Gateway 외 직접 DB 접근 금지 | docs + API safety field | PASS |
| 공식 회사 서버에 쓰기 없음 | 실행 명령 목록 | PASS |

## 검증 명령

```bash
python -m pytest komsco-ai-gateway/tests/test_health.py -q
python komsco-ai-gateway/scripts/ingest-rag-documents.py --source docs/Ver.0.1.1/rag-storage-contract.md --source-type runbook --customer komsco --namespace komsco-ai-kugnus --acl-group aiops-admins --dry-run
cd komsco-ai-console-plugin && corepack yarn build
```

## 검증 결과

| 명령 | 결과 | 비고 |
| --- | --- | --- |
| `python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/scripts/ingest-rag-documents.py` | PASS | Python 문법 확인 |
| `py -3.13 -m pytest komsco-ai-gateway/tests/test_rag_ingestion_cli.py komsco-ai-gateway/tests/test_health.py -q -k "rag_ingestion_cli_redacts_sensitive_preview or rag_ingestion_cli_redacts_pem_before_chunking or aiops_status_api_exposes_runtime_capabilities_and_recent_records or rag_search_returns_not_configured_contract_without_backend or runbook_and_preapproved_patch_apis_expose_foundation_records"` | PASS | 5 passed, 143 deselected |
| `python komsco-ai-gateway/scripts/ingest-rag-documents.py --source docs/Ver.0.1.1/rag-storage-contract.md --source-type runbook --customer komsco --namespace komsco-ai-kugnus --acl-group aiops-admins --dry-run` | PASS | `RagIngestionPlan` JSON 생성 |
| `corepack yarn build` in `komsco-ai-console-plugin` | PASS | vendor chunk size warning only |
| `KUGNUS_UI_URL=http://localhost:9000/dashboards node ./scripts/verify-kugnus-ui.mjs` | PASS | 62 checked, 0 failed |
| `py -3.13 -m pytest komsco-ai-gateway/tests/test_health.py -q` | ENV FAIL | 143 passed, 3 failed. 실패 3건은 Windows 실행환경 차이(`/bin/bash` 없음 2건, `os.statvfs` 없음 1건)이며 Stage 3 RAG 변경 실패가 아님 |

## Reviewer FAIL 대응 기록

| Reviewer | 지적 | 수정 | 검증 |
| --- | --- | --- | --- |
| B Backend/Safety | ingestion CLI가 `contentPreview: chunk[:160]`로 source 문서 일부를 raw 출력할 수 있어 Bearer token, kubeconfig, private key가 dry-run JSON에 남을 위험이 있었다. | `contentPreviewRedacted`로 변경하고 전체 chunk redaction 후 preview를 자르도록 수정했다. Bearer/API key/kubeconfig PEM probe 테스트를 추가했다. | `test_rag_ingestion_cli_redacts_sensitive_preview` PASS |
| B Backend/Safety 2차 | PEM redaction이 chunk split 이후 수행되면 긴 private key가 chunk 경계를 넘어 preview에 남을 수 있었다. | preview용 document를 chunking 전에 먼저 redaction하고, raw chunk는 hash/checksum에만 사용하도록 수정했다. 긴 PEM이 `max_chunk_chars`를 넘는 probe 테스트를 추가했다. | `test_rag_ingestion_cli_redacts_pem_before_chunking` PASS |

## Reviewer Gate

| Reviewer | 관점 | 결과 | 근거 |
| --- | --- | --- | --- |
| A | Product/Requirements | PASS | 로컬 전용 경계, `not_configured` 정직성, acceptance traceability 확인 |
| B | Backend/Safety | PASS | ingestion preview redaction 2회 fail 대응 후 long PEM boundary probe 포함 PASS |
| C | Frontend/UX | PASS | rail/dashboard RAG 상태 표시, build, mock result 오인 방지 확인 |

## 다음 단계

1. 로컬 테스트를 통과시킨다.
2. Reviewer A/B/C 검수에서 fail 항목이 나오면 즉시 수정한다.
3. 세 명 모두 PASS 후 커밋/푸시한다.
