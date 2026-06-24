# Ver.0.1.1 RAG/Runbook Storage Contract

## 현재 판단

Stage 3의 목표는 공식 회사 OCP에 무언가를 등록하거나 설치하는 것이 아니다.
이번 단계는 로컬 Gateway와 로컬 콘솔에서 RAG/Runbook 검색 계약을 먼저 고정하는 단계다.

- 실행 기준: `http://localhost:9000/dashboards` 로컬 콘솔
- API 기준: local `komsco-ai-gateway`
- 배포 기준: 없음
- 금지 기준: `oc apply`, `helm install`, `task kugnus:publish`, `task kugnus:install`, `task catalog:register`

즉, 이 문서는 내일 카탈로그 등록 전에 필요한 저장소/검색/ACL 계약을 검증 가능한 형태로 잠그는 산출물이다.

## 목표

최종 PDF의 Evidence/RAG 요구사항을 Ver.0.1.1에서 다음 수준까지 구현한다.

- Runbook/RAG 저장소의 논리 schema를 정의한다.
- ingestion 시 반드시 붙어야 하는 checksum, version, ACL metadata를 정의한다.
- Gateway 외 직접 DB 접근 금지 원칙을 명시한다.
- `/v1/rag/search` API skeleton을 제공한다.
- backend 미설정 시 API와 UI가 `not_configured`를 명확히 표시한다.
- mock 결과를 실제 검색 완료처럼 보이게 하지 않는다.

## Storage Contract

권장 backend는 PostgreSQL + pgvector다. 단, Ver.0.1.1 Stage 3에서는 실제 DB를 설치하지 않는다.
Gateway가 유일한 접근 경로이며, UI/ConsolePlugin/LLM은 DB credential을 알면 안 된다.

### aiops_rag_documents

| Field | Type | Required | 설명 |
| --- | --- | --- | --- |
| `document_id` | text | yes | stable document id |
| `source_uri` | text | yes | 원본 위치. 사내 문서 경로, Git path, PDF extract path 등 |
| `source_type` | text | yes | `runbook`, `sop`, `rca`, `pdf_extract`, `note` |
| `customer` | text | yes | 기본값 `komsco` |
| `namespace` | text | yes | 문서가 대응하는 OCP namespace 또는 제품 namespace |
| `title` | text | no | 사람이 보는 제목 |
| `checksum` | text | yes | 원문 기준 SHA256 |
| `version` | text | yes | 문서 version 또는 제품 version |
| `acl_groups` | text[] | yes | 접근 허용 그룹. 비어 있으면 검색 불가 |
| `labels` | jsonb | no | severity, domain, owner 등 |
| `lifecycle` | text | yes | `draft`, `active`, `deprecated` |
| `created_at` | timestamptz | yes | 생성 시각 |
| `updated_at` | timestamptz | yes | 갱신 시각 |

### aiops_rag_chunks

| Field | Type | Required | 설명 |
| --- | --- | --- | --- |
| `chunk_id` | text | yes | stable chunk id |
| `document_id` | text | yes | document foreign key |
| `chunk_index` | int | yes | 문서 내 순서 |
| `content_redacted` | text | yes | secret redaction 이후 저장되는 본문 |
| `text_hash` | text | yes | chunk content SHA256 |
| `token_count` | int | no | embedding 전 토큰 수 |
| `metadata` | jsonb | no | section heading, page number 등 |
| `checksum` | text | yes | chunk projection SHA256 |
| `version` | text | yes | source document version |

### aiops_rag_embeddings

| Field | Type | Required | 설명 |
| --- | --- | --- | --- |
| `chunk_id` | text | yes | chunk foreign key |
| `embedding_model` | text | yes | embedding model id |
| `dimensions` | int | yes | vector dimension |
| `vector` | vector | yes | pgvector embedding |
| `vector_checksum` | text | yes | vector payload checksum |
| `created_at` | timestamptz | yes | 생성 시각 |

### aiops_rag_ingestion_runs

| Field | Type | Required | 설명 |
| --- | --- | --- | --- |
| `run_id` | text | yes | ingestion run id |
| `source` | text | yes | 입력 source |
| `status` | text | yes | `planned`, `validated`, `failed`, `committed` |
| `document_count` | int | yes | 처리 문서 수 |
| `chunk_count` | int | yes | 처리 chunk 수 |
| `error_summary` | text | no | 실패 요약 |
| `created_at` | timestamptz | yes | 실행 시작 시각 |

### aiops_rag_access_audit

| Field | Type | Required | 설명 |
| --- | --- | --- | --- |
| `request_id` | text | yes | Gateway request id |
| `subject_hash` | text | yes | 사용자 식별값은 raw 저장 금지 |
| `decision` | text | yes | `allow`, `deny`, `not_configured` |
| `filters` | jsonb | yes | namespace/customer/acl filter |
| `result_count` | int | yes | 반환 result 수 |
| `created_at` | timestamptz | yes | 검색 시각 |

## ACL Rule

검색은 default deny다.

- document `acl_groups`가 비어 있으면 검색 결과에 포함하지 않는다.
- 사용자 group과 document `acl_groups`가 교차해야 한다.
- namespace/customer filter가 있으면 둘 다 만족해야 한다.
- UI에서 임의로 ACL을 우회하는 parameter를 보내도 Gateway가 최종 판단한다.
- 검색 결과에는 secret, kubeconfig, bearer token, password, private key를 반환하지 않는다.

## Gateway API Contract

### `GET /v1/aiops/status`

`spec.capabilities.rag`에 RAG 상태를 포함한다.

```json
{
  "status": "not_configured",
  "backendType": "pgvector",
  "collection": "komsco-aiops-runbooks",
  "endpointConfigured": false,
  "embeddingModel": "not_configured",
  "vectorDimensions": 0,
  "accessPath": "gateway-only",
  "directDatabaseAccess": false,
  "aclRequired": true
}
```

### `POST /v1/rag/search`

Request:

```json
{
  "query": "최근 OpenShift 경고 조치 절차",
  "topK": 5,
  "filters": {
    "sourceTypes": ["runbook"],
    "namespaces": ["openshift-monitoring"],
    "customers": ["komsco"],
    "aclGroups": ["aiops-admins"]
  },
  "includeContent": false
}
```

Backend 미설정 response:

```json
{
  "kind": "RagSearchResult",
  "spec": {
    "status": "not_configured",
    "results": [],
    "evidence": {
      "type": "runbook",
      "status": "missing"
    },
    "safety": {
      "gatewayOnly": true,
      "directDatabaseAccessAllowed": false,
      "aclRequired": true,
      "mockResultsAreProductionEvidence": false
    }
  }
}
```

## Ingestion CLI Skeleton

로컬 검증 도구:

```bash
python komsco-ai-gateway/scripts/ingest-rag-documents.py \
  --source docs/Ver.0.1.1/rag-storage-contract.md \
  --source-type runbook \
  --customer komsco \
  --namespace komsco-ai-kugnus \
  --acl-group aiops-admins \
  --dry-run
```

이 도구는 DB에 쓰지 않는다. 문서 checksum, chunk checksum, ACL metadata가 붙은 ingestion plan JSON만 만든다.

## 하지 않을 것

- 공식 회사 OCP에 CatalogSource, Subscription, AIOpsInstallation 생성 금지
- pgvector/PostgreSQL 설치 금지
- DB credential, kubeconfig, token commit 금지
- UI에서 mock result를 실제 RAG 검색 성공처럼 표시 금지
- Gateway를 우회해 frontend가 DB에 직접 접근 금지

## Pass/Fail 기준

| 기준 | 측정 방법 | Pass |
| --- | --- | --- |
| RAG 저장소 schema가 문서화됨 | 이 문서의 schema 표 | pass |
| ACL/checksum/version metadata가 필수로 명시됨 | schema 및 ACL Rule 확인 | pass |
| API가 backend 미설정 시 `not_configured` 반환 | pytest `/v1/rag/search` | pass |
| UI/API에 RAG 미구성이 드러남 | `/v1/aiops/status`, dashboard capability | pass |
| mock result가 실제 검색처럼 보이지 않음 | response `mockResultsAreProductionEvidence=false` | pass |
| 회사 OCP에 쓰기 작업 없음 | git diff와 실행 명령 확인 | pass |
