# Ver.0.1.4 Completion Review

## Ref stamp

- Branch: `feat/v.0.1.4`
- Base before this closure: `ff81067 polish history panel upload actions`
- Scope: PBS 사용자 문서 업로드 RAG의 최소 end-to-end 경로, 업로드 문서 패널, RAG citation smoke, subject 기반 ACL 보강

## Goal

Ver.0.1.4는 RAG를 demo search contract에서 사용자 문서 업로드 기반의 최소 운영 경로로 올리는 단계다.

완료 기준은 다음으로 본다.

1. 업로드 문서가 Gateway를 통해 안전하게 ingestion된다.
2. 업로드 문서 chunk가 pgvector에 저장된다.
3. `/v1/rag/search`가 업로드 문서 source metadata를 반환한다.
4. 채팅 스트림에서 RAG evidence와 답변 citation이 보인다.
5. 좌측 패널에서 업로드 문서 목록을 볼 수 있다.
6. ACL, missing, freshness, dangerous 상태가 최소 metadata 수준에서 구분된다.
7. smoke/evaluator가 pass/fail 산출물을 남긴다.

## Implemented

1. Backend upload ingestion contract
   - `POST /v1/rag/uploads`
   - `GET /v1/rag/uploads`
   - `RagDocumentUploadCreate`
   - UTF-8 text/markdown/json/yaml/log 계열 JSON upload
   - size limit, redaction-before-chunking, raw content response 금지

2. pgvector persistence/search
   - `aiops_rag_documents` table creation
   - uploaded document chunk persistence into `aiops_rag_chunks`
   - `/v1/rag/search` retrieval through `sourceTypes=["user-upload"]`
   - search result `evidenceRef`, `sourceUri`, `sourceType`, `safetyClass`, `freshness`

3. Subject-based ACL
   - `safe_subject` now preserves sanitized group names as well as `groupsDigest`.
   - upload ACL is derived from current OpenShift subject principals.
   - caller-provided `aclGroups` are accepted only when owned by the current subject.
   - list/search return only rows whose ACL intersects the current subject principals.

4. Frontend uploaded document panel
   - left history panel icon toolbar
   - new chat icon, history icon, uploaded-document icon
   - data-backed uploaded document list
   - `not_configured`/`unavailable` is shown as an error state, not hidden as an empty list
   - file attach keeps image upload and adds TXT/MD/JSON/YAML/log document upload
   - attach button is no longer disabled merely because image attachment slots are full

5. Chat citation path
   - chat loop runs RAG context search before Lightspeed handoff.
   - SSE emits `rag_context_evidence`.
   - answer stream appends `[ RAG 근거 ]` citation text when RAG results exist.

6. Verification automation
   - `task kugnus:rag:upload:smoke`
   - `task kugnus:rag:chat:smoke`
   - reports:
     - `docs/Ver.0.1.4/rag-upload-smoke-report.json`
     - `docs/Ver.0.1.4/rag-chat-citation-smoke-report.json`

## Parallel Review Closure

Two fresh read-only subagent reviews were run after the first 0.1.4 implementation pass.

Backend/RAG review findings:

- ACL/user isolation was metadata-only.
- caller-controlled `aclGroups` could not be trusted.
- local upload/list/search smoke existed; a stronger pytest was still needed for cross-subject ACL filtering.
- docs had route drift between `/v1/aiops/rag/search` and `/v1/rag/search`.

Frontend/UI review findings:

- UI browser verifier still does not prove the frontend flow because Chrome CDP is unavailable.
- uploaded-documents panel treated `not_configured` as empty.
- attach button blocked document uploads when image slots were full.
- uploaded-documents panel and icon toolbar are present and accessible at source level.

Actions taken after review:

- Added subject principal preservation and ACL enforcement.
- Removed default `cluster-admins` upload ACL.
- Added ACL/safety/freshness pytest coverage, including cross-subject search filter rejection.
- Excluded broad `system:authenticated` style groups from default upload ACL.
- Added kubeconfig data redaction for `client-key-data`, `client-certificate-data`, and `certificate-authority-data`.
- Moved pgvector ACL filtering into the SQL query path and kept source-level row filtering as a second guard.
- Excluded `dangerous` and `stale` documents from default RAG context/citation.
- Added OLM runtime RAG backend Secret wiring through `spec.rag.backendUrlSecret/backendUrlKey`.
- Added RAG pre-answer evidence search and answer citation text.
- Added chat citation smoke task/report.
- Fixed uploaded-documents `not_configured` UI handling.
- Fixed attach button disable logic.
- Fixed docs route drift to `/v1/rag/search`.

## Verification

| Check | Result |
|---|---|
| `python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/komsco_ai_gateway/security.py` | PASS |
| Gateway pytest | `179 passed, 2 warnings` |
| Console plugin build | PASS |
| `task kugnus:scenario:verify` | `10 passed, 0 failed` |
| `task kugnus:runtime:smoke` | PASS, `health=92`, `nodes=1/1`, `operators=34/34`, `rag=collected`, `results=1` |
| `task kugnus:rag:upload:smoke` | PASS |
| `task kugnus:rag:chat:smoke` | PASS |
| `task kugnus:ui:verify` | FAIL: Chrome CDP endpoint missing |

## Acceptance Status

| Requirement | Status | Evidence |
|---|---|---|
| RAG schema/source documented | PASS | `README.md`, `rag-architecture-design.html` |
| local pgvector receives real chunks | PASS | `rag-upload-smoke-report.json` |
| RAG search returns source metadata | PASS | `/v1/rag/search`, runtime smoke, upload smoke |
| uploaded document list panel exists | PASS | `AssistantLauncher.tsx`, `fetchUploadedRagDocuments` |
| chat answer includes RAG citation | PASS | `task kugnus:rag:chat:smoke`, `rag-chat-citation-smoke-report.json` |
| subject ACL enforced for upload/list/search | PASS | `main.py`, `security.py`, pytest ACL coverage, broad system groups excluded |
| stale/missing/dangerous distinguishable | PASS for 0.1.4 minimum | missing is represented in RAG search evidence; uploaded chunks expose `freshness`; dangerous/stale documents are excluded by default search policy |
| upload smoke/evaluator exists | PASS | `task kugnus:rag:upload:smoke` |
| UI browser verifier pass | NOT PROVEN | Chrome CDP endpoint unavailable |

## Residual Risk

- Browser-level UI verification remains blocked by Chrome CDP `localhost:9231` reachability. Do not report `task kugnus:ui:verify` as pass.
- PDF/Office parsing is not included in 0.1.4.
- multipart upload and streaming upload progress are not included in 0.1.4.
- Time-based stale expiration, namespace ownership checks, DB health reporting beyond env presence, and policy-engine-grade dangerous document handling should move to Ver.0.1.5.

## Next Version Candidates

- Ver.0.1.5: PDF/Office parser
- Ver.0.1.5: multipart upload and upload progress stream
- Ver.0.1.5: UI verifier Chrome CDP auto-start stabilization
- Ver.0.1.5: time-based freshness expiry and policy-engine dangerous document handling
