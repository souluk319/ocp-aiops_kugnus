# KUGNUS HOME Company Project Integration Guide

이 문서는 회사 PC의 AIOps/RAG 프로젝트에서 홈서버 SWEET12의 `Gemma 4 12B QAT` chat endpoint와 `EmbeddingGemma` embed endpoint를 쓰기 위한 적용 가이드다.

## 1. Target Architecture

권장 방향은 SWEET12를 모델 런처이자 홈서버 gateway로 두고, 회사 프로젝트는 Tailscale 주소 하나만 바라보는 구조다.

```text
Company AIOps/RAG project
  -> Tailscale HTTPS
  -> SWEET12 gateway on KUGNUS HOME
  -> chat: Gemma 4 12B QAT
  -> embed: EmbeddingGemma
```

SWEET12 내부 제어 API와 외부 프로젝트용 API는 역할이 다르다.

```text
SWEET12 control API
/api/home-server/start
/api/home-server/stop
/api/home-server/status

Current external API
/api/home-server/chat
/api/home-server/embed
/api/home-server/rag/query

Recommended future compatibility API
/v1/chat/completions
/v1/embeddings
/v1/models
```

현재 구현은 `Current external API`까지 완료되어 있다. 회사 프로젝트가 OpenAI SDK, LangChain OpenAI provider, LlamaIndex OpenAI provider만 받는 구조라면 SWEET12에 `/v1` adapter를 추가한 뒤 붙이는 것이 가장 깔끔하다.

## 2. Home Server Setup

홈서버에서 SWEET12를 API key와 함께 실행한다. 이미 dev server가 떠 있다면 종료 후 다시 시작해야 환경변수가 반영된다.

```powershell
cd F:\AI_Models\llmfit\local-llm-lab
$env:SWEET12_GATEWAY_API_KEY="replace-with-long-random-key"
npm run dev
```

SWEET12 대시보드에서 `RCA/RAG` 버튼을 눌러 home-server profile을 `ready` 상태로 만든다.

현재 홈서버 Tailscale 정보:

```text
Tailscale IP: 100.99.152.52
MagicDNS: souluk.tail14d38e.ts.net
Local SWEET12 API: http://127.0.0.1:8788
```

Tailscale Serve로 로컬 SWEET12 API를 tailnet에 노출한다.

```powershell
tailscale serve --bg 8788
tailscale serve status
```

회사 PC에서 접근할 base URL:

```text
https://souluk.tail14d38e.ts.net
```

## 3. Company Project `.env`

현재 SWEET12 전용 gateway API에 바로 붙는 설정이다.

```env
KUGNUS_HOME_BASE_URL=https://souluk.tail14d38e.ts.net

KUGNUS_HOME_CHAT_ENDPOINT=https://souluk.tail14d38e.ts.net/api/home-server/chat
KUGNUS_HOME_EMBED_ENDPOINT=https://souluk.tail14d38e.ts.net/api/home-server/embed
KUGNUS_HOME_RAG_ENDPOINT=https://souluk.tail14d38e.ts.net/api/home-server/rag/query

KUGNUS_HOME_CHAT_MODEL=gemma4:12b-it-qat
KUGNUS_HOME_EMBED_MODEL=embeddinggemma:latest
KUGNUS_HOME_EMBED_DIMENSIONS=768

KUGNUS_HOME_API_KEY=replace-with-long-random-key
KUGNUS_HOME_TIMEOUT_MS=120000
KUGNUS_HOME_EMBED_TIMEOUT_MS=120000
```

나중에 SWEET12에 OpenAI-compatible `/v1` adapter를 붙이면 아래 형태로 바꾸는 것이 권장된다.

```env
KUGNUS_HOME_OPENAI_BASE_URL=https://souluk.tail14d38e.ts.net/v1
KUGNUS_HOME_OPENAI_API_KEY=replace-with-long-random-key
KUGNUS_HOME_CHAT_MODEL=gemma4:12b-it-qat
KUGNUS_HOME_EMBED_MODEL=embeddinggemma:latest
KUGNUS_HOME_EMBED_DIMENSIONS=768
```

기존 프로젝트가 실제 OpenAI API도 같이 쓴다면 `OPENAI_BASE_URL`을 덮어쓰지 말고 `KUGNUS_HOME_*`로 분리한다.

## 4. Request Contract

### Chat

```http
POST /api/home-server/chat
Authorization: Bearer replace-with-long-random-key
Content-Type: application/json
```

```json
{
  "prompt": "OCP 503 장애의 RCA 초안을 작성해줘.",
  "systemPrompt": "너는 AIOps 운영 분석가다. 근거와 조치 순서를 분리해서 답한다.",
  "temperature": 0.2,
  "maxTokens": 800
}
```

응답은 Ollama chat 응답 형태를 그대로 반환한다.

```json
{
  "model": "gemma4:12b-it-qat",
  "message": {
    "role": "assistant",
    "content": "..."
  },
  "done": true
}
```

### Embedding

```http
POST /api/home-server/embed
Authorization: Bearer replace-with-long-random-key
Content-Type: application/json
```

```json
{
  "input": [
    "Secret 변경 이후 DB 인증 실패가 발생했다.",
    "rollout restart 직후 CrashLoopBackOff가 증가했다."
  ],
  "bulk": true
}
```

응답은 embedding vector 배열을 반환한다.

```json
{
  "model": "embeddinggemma:latest",
  "embeddings": [
    [0.0123, -0.0421, 0.0088]
  ]
}
```

실제 vector는 3개가 아니라 `768`개 float로 구성된다.

### RAG Query

현재 `/api/home-server/rag/query`는 vector DB까지 내장한 endpoint가 아니라, 회사 프로젝트가 검색한 context를 넘겨 최종 답변만 받는 형태다.

```json
{
  "query": "DB 인증 실패의 원인을 RCA 형식으로 정리해줘.",
  "contexts": [
    "2026-06-30 10:12 Secret db-password changed by deploy bot",
    "2026-06-30 10:16 app rollout restarted",
    "2026-06-30 10:18 DB auth failed logs increased"
  ],
  "maxTokens": 1200
}
```

즉, 현재 권장 분리는 다음과 같다.

```text
회사 프로젝트:
  문서 chunking
  embedding 호출
  vector DB 저장/search
  context 조립

SWEET12 홈서버:
  EmbeddingGemma vector 생성
  Gemma 4 12B QAT 최종 답변 생성
```

## 5. Embedding Numbers Explained

embedder가 반환하는 숫자는 자연어 문장을 모델이 이해한 의미 좌표다. 보통 `embedding vector`라고 부른다.

예를 들어 `EmbeddingGemma`는 현재 `768`차원 vector를 반환한다.

```text
"DB 인증 실패" -> [0.031, -0.124, 0.008, ... 768개]
```

각 숫자 하나하나를 사람이 직접 해석하는 방식은 아니다. vector DB가 이 숫자 배열끼리의 거리를 계산해서 의미가 가까운 문서를 찾는다.

대표적으로 쓰는 계산은 다음과 같다.

```text
cosine similarity
dot product
L2 distance
```

RAG에서는 보통 아래 순서로 동작한다.

```text
1. 문서를 chunk로 자른다.
2. 각 chunk를 EmbeddingGemma로 숫자 vector로 바꾼다.
3. vector DB에 저장한다.
4. 사용자의 질문도 같은 embedder로 vector로 바꾼다.
5. 질문 vector와 가까운 chunk vector를 검색한다.
6. 검색된 chunk를 Gemma 4 12B QAT에 context로 넣고 답변을 생성한다.
```

주의점:

- 같은 vector DB index 안에서는 같은 embedding model을 써야 한다.
- embedding model을 바꾸면 기존 index는 다시 생성하는 것이 원칙이다.
- dimension이 다르면 같은 index에 섞을 수 없다.
- `768`은 현재 EmbeddingGemma의 vector 길이다.
- 숫자가 많다고 무조건 좋은 것은 아니며, 모델 품질과 도메인 적합도가 더 중요하다.
- bulk indexing 중에는 chat 요청을 큐에서 기다리게 해서 VRAM/응답 안정성을 우선한다.

## 6. Smoke Tests From Company PC

Chat:

```powershell
Invoke-RestMethod "https://souluk.tail14d38e.ts.net/api/home-server/chat" `
  -Method POST `
  -Headers @{ Authorization = "Bearer replace-with-long-random-key" } `
  -ContentType "application/json" `
  -Body '{"prompt":"RCA 백엔드 연결 테스트를 한 문장으로 답해","maxTokens":80}'
```

Embedding:

```powershell
Invoke-RestMethod "https://souluk.tail14d38e.ts.net/api/home-server/embed" `
  -Method POST `
  -Headers @{ Authorization = "Bearer replace-with-long-random-key" } `
  -ContentType "application/json" `
  -Body '{"input":"AIOps RAG embedding test","bulk":false}'
```

Expected checks:

```text
chat: message.content exists
embed: embeddings[0].length == 768
```

## 7. Implementation Notes For The Company Project

HTTP client wrapper를 하나 두고, 나머지 AIOps/RAG 로직은 provider에 의존하지 않게 만든다.

```ts
const baseUrl = process.env.KUGNUS_HOME_BASE_URL;
const apiKey = process.env.KUGNUS_HOME_API_KEY;

const chatEndpoint = process.env.KUGNUS_HOME_CHAT_ENDPOINT ?? `${baseUrl}/api/home-server/chat`;
const embedEndpoint = process.env.KUGNUS_HOME_EMBED_ENDPOINT ?? `${baseUrl}/api/home-server/embed`;

const headers = {
  "Content-Type": "application/json",
  Authorization: `Bearer ${apiKey}`
};
```

권장 timeout:

```text
chat: 120s
embed single: 120s
embed bulk: queue/job 방식 권장
```

운영 주의:

- 회사 프로젝트에서 직접 `11434`, `11435`로 붙지 않는다.
- 외부에서는 `https://souluk.tail14d38e.ts.net`만 사용한다.
- RAG indexing은 작은 batch부터 시작한다.
- 응답 실패 시 SWEET12 대시보드의 `Home Server RCA/RAG` 상태와 runtime log를 먼저 확인한다.
- 게임이나 GPU 작업 전에는 SWEET12의 `Stop RCA/RAG` 또는 `Game mode`로 내린다.
