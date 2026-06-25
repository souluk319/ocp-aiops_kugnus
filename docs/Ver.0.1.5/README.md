# Ver.0.1.5 사용자 업로드 RAG 파서 도입

## 현재 판단

Ver.0.1.4의 파일 첨부 RAG는 브라우저가 `TXT/MD/JSON/YAML/log` 파일을 텍스트로 읽어 Gateway에 JSON으로 보내는 구조였다. 따라서 PDF는 파일 선택 목록에도 뜨지 않았고, Gateway에도 PDF parser가 없었다.

PBS 로컬 프로젝트 `OCPOps-PBS-Dev-v2`를 확인한 결과, 업로드 RAG의 핵심 흐름은 다음이었다.

1. 파일을 안전한 이름으로 저장한다.
2. 문서 포맷을 감지한다.
3. PDF/DOCX/PPTX/XLSX 등을 Markdown/text로 변환한다.
4. block/chunk를 만든다.
5. PostgreSQL/pgvector 저장소에 넣고 검색 대상으로 만든다.
6. 실패하면 failure report를 남긴다.

우리 프로젝트는 이미 Gateway 내부에 RAG document/chunk 저장 계약과 pgvector 경로가 있으므로, PBS 전체 파이프라인을 복사하지 않고 문서 parser 경계만 최소 이식한다.

## 구현 범위

- 신규 Gateway endpoint:
  - `POST /v1/rag/uploads/file`
  - `multipart/form-data`로 브라우저 파일을 그대로 받는다.

- 신규 parser 지원:
  - `PDF`: `pypdf` 기반 텍스트 추출
  - `DOCX`: Office Open XML에서 문단 텍스트 추출
  - `PPTX`: slide XML에서 텍스트 추출
  - `XLSX`: shared strings와 worksheet cell value 추출
  - `TXT/MD/JSON/YAML/log`: UTF-8 text 경로 유지

- 프론트 파일 첨부 확장:
  - 파일 선택 accept에 `PDF/DOCX/PPTX/XLSX` 추가
  - PDF/Office 계열은 `FormData` multipart 업로드 사용
  - 기존 이미지 첨부와 텍스트 문서 첨부는 유지

- 업로드 제한:
  - 문서당 기본 최대 `5 MiB`
  - 추출 텍스트는 기존 RAG 계약에 맞춰 최대 `120000 chars`
  - 초과 시 잘라 넣고 `truncated=true` parser report를 남긴다.

## 증거와 추적성

업로드 성공 응답에는 다음 정보가 남는다.

- `spec.document.mimeType`
- `spec.document.labels.parser`
- `spec.document.labels.documentFormat`
- `spec.document.labels.originalFileName`
- `spec.document.labels.originalBytes`
- `spec.document.labels.extractedChars`
- `spec.ingestionReport`
- `spec.chunks`

즉 발표 때 “PDF가 RAG에 들어갔는지”는 화면의 업로드 문서 목록만 보지 말고, Gateway 응답의 parser/chunk/report를 기준으로 확인한다.

## 하지 않을 것

- PBS parser 전체 복붙 금지
- Docling/markitdown/PyMuPDF/pdfplumber 전체 체인 즉시 도입 금지
- OCR 기반 스캔 PDF 지원을 완료됐다고 보고 금지
- image-only PDF를 성공으로 위장 금지
- raw 문서 본문을 API 응답으로 반환 금지
- 회사 OCP 리소스 apply/delete/patch/scale/exec 금지

## 현재 한계

- 스캔본 PDF는 텍스트가 없으면 실패한다.
- PDF 표 구조 복원은 아직 최소 수준이다.
- DOCX/PPTX/XLSX는 Office XML 텍스트 추출이며, 레이아웃 품질 보장은 PBS 고급 parser보다 낮다.
- embedding 품질 평가는 Ver.0.1.5의 완료 범위가 아니다.

## 검증 결과

- `komsco-ai-gateway/.venv/bin/python -m pytest komsco-ai-gateway/tests/test_health.py -q -k "rag_pdf_upload_parser or rag_upload_file_endpoint"`
  - result: `2 passed`

- `cd komsco-ai-console-plugin && corepack yarn build`
  - result: webpack compiled successfully

- `komsco-ai-gateway/.venv/bin/python -m pytest komsco-ai-gateway -q`
  - result: `181 passed, 2 warnings`

## 다음 작업

1. 실제 PDF를 첨부해 `spec.ingestionReport.parser=pypdf`와 업로드 문서 목록 반영을 확인한다.
2. 스캔 PDF가 필요한 경우 OCR/parser chain을 별도 stage로 추가한다.
3. RAG 검색 결과에서 사용자 업로드 문서가 질문 답변 근거로 쓰이는지 화면 시나리오로 검증한다.
