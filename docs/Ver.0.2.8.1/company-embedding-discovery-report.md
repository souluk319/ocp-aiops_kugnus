# Company Embedding Discovery Report

Date: 2026-07-05
Branch: `feature/v0.2.8.1-chatbot-answer-ux-plan`
Scope: read-only company OKD inspection

## Goal

KOMSCO AIOps is developed locally, but the deployment target is the company OKD cluster.
Therefore the production embedding path must not depend on the user's home-server EmbeddingGemma.

This report records what is actually installed or configured on the company cluster.

## Safety Boundary

- Company cluster mutation was not performed.
- Commands used were read-only `oc get` and HTTP probes.
- Secrets were not decoded or printed.
- Existing protected scenario/user artifacts were not modified.

## Verified Cluster

```text
oc whoami --show-server
-> https://api.ocp.cywell.server:6443

oc whoami
-> admin

oc project -q
-> cywell-aiops
```

## Confirmed Company AI Components

### OpenShift Lightspeed

Observed namespace and operator:

```text
namespace/openshift-lightspeed
lightspeed-operator.v1.1.1
```

Observed app server:

```text
openshift-lightspeed/lightspeed-app-server
service: lightspeed-app-server.openshift-lightspeed.svc:8443
status: 3/3 Running
```

Lightspeed LLM provider from `openshift-lightspeed/olsconfig`:

```yaml
llm_providers:
  - name: rhoai-gemma
    type: openai
    url: http://cllm.cywell.co.kr/v1
    models:
      - name: gemma-4-26b-a4b-it-awq-8bit
```

HTTP probe:

```text
curl http://cllm.cywell.co.kr/v1/models
-> HTTP 200
-> gemma-4-26b-a4b-it-awq-8bit present
```

### Lightspeed Internal Embedding Assets

`openshift-lightspeed/olsconfig` includes local embedding/vector paths:

```yaml
reference_content:
  embeddings_model_path: /app-root/embeddings_model
  indexes:
    - product_docs_index_id: ocp-product-docs-4_20
      product_docs_index_path: /app-root/vector_db/ocp_product_docs/4.20
      product_docs_origin: Red Hat OpenShift 4.20 documentation
```

Interpretation:

- Lightspeed does have embedding assets for its own reference content.
- They are not exposed as a standalone cluster `Service` for the KOMSCO Gateway.
- They are tied to the Lightspeed app-server image/runtime path.

### Red Hat OpenShift AI

Observed:

```text
Red Hat OpenShift AI 2.25.8
namespaces:
- redhat-ods-applications
- redhat-ods-operator
- rhoai-model-registries
- rhods-notebooks
```

KServe CRDs exist:

```text
inferenceservices.serving.kserve.io
llminferenceservices.serving.kserve.io
servingruntimes.serving.kserve.io
trainedmodels.serving.kserve.io
```

Current model-serving objects:

```text
oc get inferenceservice -A
-> none

oc get llminferenceservice -A
-> none
```

ServingRuntime templates observed in `internal-llm-demo`:

```text
gemma-3-12b-it
qwen3-8b
```

Interpretation:

- RHOAI/KServe capability is installed.
- No active KServe `InferenceService` or `LLMInferenceService` embedding model was found.

## Company Embedding Candidate

Repo docs and `.env.example` already point to:

```text
KOMSCO_AI_EMBEDDING_BASE_URL=http://tei.cywell.co.kr/v1
KOMSCO_AI_EMBEDDING_MODEL=dragonkue/bge-m3-ko
KOMSCO_AI_EMBEDDING_DIMENSIONS=1024
```

HTTP probe:

```text
curl http://tei.cywell.co.kr/v1/embeddings
-> HTTP 502 Bad Gateway
```

Interpretation:

- `tei.cywell.co.kr` is the company embedding-service candidate.
- It is not currently healthy from this workstation.
- It should be restored or replaced before company deployment can claim production RAG embedding.

## Other Related Service

`pbs-ocpops` has:

```text
service/bge-reranker
ClusterIP: 172.30.234.68
port: 80 -> external EndpointSlice 192.168.119.27:8082
```

Interpretation:

- This is labeled as a reranker service, not an embedding service.
- It may be useful for later retrieval ranking, but it should not be treated as the primary embedding endpoint without API verification.

## Current KOMSCO Gateway Gap

The deployed company Gateway currently uses the home-server embedding path:

```text
namespace: cywell-aiops
deployment: komsco-ai-gateway

KOMSCO_AI_EMBEDDING_PROVIDER=ollama
KOMSCO_AI_EMBEDDING_API_STYLE=ollama
KOMSCO_AI_EMBEDDING_BASE_URL=http://100.99.152.52:11435
KOMSCO_AI_EMBEDDING_MODEL=embeddinggemma:latest
KOMSCO_AI_EMBEDDING_DIMENSIONS=768
```

The source is the live `AIOpsInstallation` custom resource:

```yaml
namespace: cywell-aiops
kind: AIOpsInstallation
name: cywell-aiops
spec:
  rag:
    embeddingProvider: ollama
    embeddingApiStyle: ollama
    embeddingBaseUrl: http://100.99.152.52:11435
    embeddingModel: embeddinggemma:latest
    embeddingTimeoutSeconds: 120
    vectorDimensions: 768
```

This conflicts with the deployment target.

## Decision

Do not use the home-server EmbeddingGemma as the company deployment embedding target.

Target path:

```text
company embedding candidate:
  http://tei.cywell.co.kr/v1
  model: dragonkue/bge-m3-ko
  dimensions: 1024

current status:
  HTTP 502, needs restoration or replacement
```

Fallback/lab path:

```text
home-server EmbeddingGemma:
  http://100.99.152.52:11435
  model: embeddinggemma:latest
  dimensions: 768

usage:
  local lab/fallback reference only, not company deployment target
```

## Required Follow-Up

1. Restore or identify the real company TEI/embedding endpoint.
2. Verify `/v1/embeddings` returns HTTP 200 and vector dimension 1024.
3. Update the company `AIOpsInstallation.spec.rag` so company Gateway no longer deploys with `100.99.152.52:11435`.
4. Keep SWEET12 EmbeddingGemma only as a local lab/fallback profile.
5. Add a deployment verifier that fails if a company namespace Gateway points to `100.99.152.52`.
