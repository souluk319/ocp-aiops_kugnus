# Komsco AI Agent Final PDF 주안점

작성 기준일: 2026-06-24 KST  
기준 문서: `docs/Komsco_ai_agent_final.pdf`

## 한 줄 결론

최종 PDF의 핵심은 OpenShift Lightspeed를 단순히 감싸는 챗봇이 아니라, **AI Gateway가 Agentic Tool Plan, Evidence/RAG, OS-aware Adapter, Safety Guard를 수행하고 Lightspeed의 최종 RCA 답변을 강화하는 OCP 네이티브 AIOps 제품**을 만드는 것이다.

## 페이지별 핵심

| Page | 주안점 | 0.1.1 해석 |
| :--- | :--- | :--- |
| 1 | 기존 OpenShift 보존, Lightspeed REST 유지, 신규 Plugin/Gateway 구축 | 기존 환경을 깨지 않고 Kugnus 전용 UI/Gateway/OLM 경로로 확장 |
| 2 | UserToken RBAC, KOMSCO AIOps Model, OS-aware Tool Adapter, 안전한 Lightspeed 연동 | Gateway 진입 통제와 Tool Plan 기반 증거 수집이 중심 |
| 3 | Tool Plan, Linux/Windows Adapter, Evidence API, Runbook/RAG, OpenShift resource/event/metric 조회 | 질문마다 필요한 증거원을 자동 선택해야 함 |
| 4 | OS Context Classifier, Tool Router, Evidence Planner, RCA Reasoner, JSON Formatter, Safety Guard | Agentic 기능을 명시적 모듈/계약으로 분리해야 함 |
| 5 | Qwen/Gemma 등 AIOps Agentic Model 선정 근거 | 0.1.1은 모델 교체보다 모델 인터페이스와 평가 기준을 먼저 잡아야 함 |
| 6 | Linux/Windows/OpenShift별 Tool Adapter 변환 | OpenShift Adapter만으로는 부족하며 OS별 adapter contract 필요 |
| 7 | 장애 티켓, Event/Log, Runbook, Tool 결과, 보안 정책을 학습 데이터로 축적 | 감사/증거/피드백을 학습 가능한 구조로 저장해야 함 |
| 8 | Tool Plan JSON과 RCA Context JSON 표준화 | UI와 Gateway에서 최신 plan/context를 볼 수 있어야 함 |
| 9 | Evidence 기반 RCA 시나리오 | "어제 새벽 Pod 재시작" 같은 시간 기반 질문에 과거 증거가 필요 |
| 10 | Namespace/RBAC/Image/OLM/CR/Console 전환 로드맵 | Operator 설치 후 CR 기반 자동 배포와 상태 condition 필요 |
| 11 | GB10 2노드 모델 구성 3안 | 모델 PoC는 한국어 품질, RCA 품질, 동시성, 운영성 기준으로 평가 |
| 12 | 모델 구성안 상세 비교 | 단일 대형모델보다 운영 가능한 라우팅/HA 구조가 중요 |
| 13 | 1안 혼합형 권장, 2안 HA 대안, 3안 제한 적용 | 심층 RCA와 빠른 질의를 분리하는 routing policy 필요 |
| 14 | PostgreSQL + pgvector 기본 RAG 저장소 권장 | 소규모 RAG는 Gateway 전용 계정, ACL metadata, 백업 정책이 핵심 |

## 핵심 아키텍처 계약

```text
OpenShift Console Chat UI
  -> ConsolePlugin proxy with UserToken
  -> AI Gateway
  -> OS Context Classifier
  -> Tool Router / Evidence Planner
  -> OpenShift / Linux / Windows Adapter
  -> Evidence API / RAG / Runbook
  -> RCA Context JSON
  -> OpenShift Lightspeed streaming_query
  -> Chat UI answer with evidence
```

## 필수 JSON 계약

### Tool Plan JSON

```json
{
  "task_type": "pod_restart_rca",
  "target": {
    "platform": "openshift"
  },
  "execution_policy": {
    "mode": "read_only"
  },
  "tool_plan": [
    {
      "step": 1,
      "tool": "event_tool"
    },
    {
      "step": 2,
      "tool": "grep_tool"
    },
    {
      "step": 3,
      "tool": "metric_tool"
    }
  ]
}
```

### RCA Context JSON

```json
{
  "cause_candidates": [
    {
      "cause": "Deployment memory limit decrease caused Pod OOM",
      "confidence": 0.86
    }
  ],
  "evidence": [
    {
      "type": "event",
      "summary": "OOMKilled event near restart time"
    }
  ],
  "action_candidates": [
    "Restore memory limit",
    "Review recent Deployment change"
  ]
}
```

## 모델/LLM 관련 판단

PDF는 Qwen 계열을 깊은 Tool Reasoning과 RCA JSON 생성에 유리한 후보로 보고, Gemma 계열을 빠른 triage/요약/분류에 유리한 후보로 본다.

0.1.1에서 바로 모델을 확정하기보다 먼저 다음 인터페이스를 만든다.

- model endpoint config contract
- tool plan JSON schema
- RCA context JSON schema
- model routing policy: quick triage vs deep RCA
- evaluation set: 한국어 운영 질의, tool call 정확도, JSON schema 유효율, TTFT/p95

## RAG 저장소 판단

PDF의 권장 기본안은 `PostgreSQL + pgvector`다.

0.1.1에서는 최소한 다음을 설계 기준으로 둔다.

- Gateway만 DB에 접근
- 문서 chunk, metadata, ACL metadata를 함께 저장
- read-only 질문에는 사용자의 권한으로 접근 가능한 문서만 retrieve
- PoC는 Exact search부터 시작하고, p95가 나빠지면 HNSW 검토
- 원본 문서와 백업은 NAS 또는 별도 저장소, 온라인 검색 DB는 로컬 NVMe 기준

## 제품 관점 주안점

1. 답변 품질은 "LLM이 똑똑함"이 아니라 "증거가 맞음"으로 평가한다.
2. AIOps UI는 상태를 예쁘게 보여주는 것이 아니라 누락된 증거와 다음 행동을 보여줘야 한다.
3. 위험 작업은 처음부터 실행하지 않고 계획, 승인, 실행, 감사로 분리한다.
4. Operator/OLM은 배포 수단이 아니라 설치/업그레이드/롤백/상태 condition까지 포함하는 제품 계약이다.

