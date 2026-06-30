# Ver.0.1.7

## 목표

Ver.0.1.6 RAG/LLM 시스템 점검에서 "데모 한계"로 미룬 세 항목을 완성한다.

| 항목 | 내용 |
|---|---|
| Semantic Embedding | `KOMSCO_AI_RAG_EMBEDDING_SERVICE_URL` 설정 시 외부 HTTP 임베딩 서비스 호출, 미설정 시 hashing-bow-v1 유지 |
| Auto-Ingest | `KOMSCO_AI_RAG_SYNC_DIR` 설정 시 Gateway 시작 때 디렉토리 내 문서 일괄 적재 |
| Schema Migration | `aiops_rag_schema_version` 테이블로 스키마 변경 이력 관리 |

## 완료 조건

1. **Semantic Embedding**
   - `KOMSCO_AI_RAG_EMBEDDING_SERVICE_URL` 미설정 → hashing-bow-v1 기존 동작 완전 유지
   - 설정 시 TEI(`/embed`) 또는 Ollama(`/api/embeddings`) 형식 호환
   - 서비스 timeout/오류 시 자동 fallback + 1회 경고 로그
   - `/v1/aiops/status` 응답에 `embeddingServiceConfigured` 필드 노출

2. **Auto-Ingest**
   - `KOMSCO_AI_RAG_SYNC_DIR` 미설정 시 아무것도 안 함
   - 설정 시 Gateway 시작 때 .md/.txt/.pdf 파일 자동 적재
   - 같은 checksum 파일 재시작 시 skip (중복 적재 없음)
   - `task kugnus:rag:sync` CLI로도 동일 동작 가능

3. **Schema Migration**
   - `aiops_rag_schema_version` 테이블 자동 생성
   - Migration 1~3 적용 (content_chars, embedding_model 컬럼 추가)
   - 재시작 시 이미 적용된 migration skip
   - 기존 DB에서 오류 없이 실행

## 검증 방법

```bash
task kugnus:dev:doctor
task kugnus:runtime:smoke
task kugnus:rag:file-upload:smoke
task kugnus:rag:sync
.venv/bin/python -m pytest komsco-ai-gateway/tests/ -q
```

## 하지 않을 것 (Out of Scope)

- Alembic 도입 (운영 단계에서 고려)
- APScheduler/Celery 스케줄러 (재시작 1회 sync로 대체)
- 회사 OCP 서버에 신규 배포 (별도 승인 필요)
- vector 차원 실제 변경 (migration 4번 skeleton만 — 재계산 로직은 0.1.8)
- 외부 wiki (Confluence, GitHub Pages) 자동 크롤링

## 브랜치

`feat/v.0.1.7` ← `feat/v.0.1.6`
