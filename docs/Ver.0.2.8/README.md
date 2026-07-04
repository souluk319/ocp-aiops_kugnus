# Ver.0.2.8 - AIOps LLM Wiki Design

Ref stamp: `feature/v0.2.8-llm-wiki-design` from `4777496`

## Purpose

v0.2.8은 현재 `위키 문서 관리` 메뉴를 단순 RAG 문서 업로드 화면에서 한 단계 올려, AIOps for OCP의 운영 지식과 실시간 클러스터 객체, RCA, Action Plan, 감사 기록이 서로 연결되는 LLM Wiki 시스템으로 설계한다.

이번 버전은 설계 산출물 단계이다. 회사 서버 배포, OLM publish/install, 카탈로그 변경, 실행 정책 변경은 하지 않는다.

## Deliverables

- `aiops-llm-wiki-agent-plan.md`
  - 다음 작업 에이전트들이 구현에 들어가기 위한 상세 설계/수행 계획서.
- `aiops-llm-wiki-strategy-brief.html`
  - 사용자와 팀에게 공유하기 위한 HTML 전략 보고서.

## Core Idea

Palantir의 Ontology 원리는 운영 세계를 `object / link / action / permission`으로 모델링하는 것이다. Obsidian의 원리는 사람이 읽고 쓸 수 있는 Markdown 지식이 `link / backlink / graph / property`를 통해 네트워크가 되는 것이다.

우리의 v0.2.8 LLM Wiki는 이 둘을 합쳐야 한다.

```text
Markdown Runbook + Backlink Graph
  -> AIOps Ontology Object Graph
    -> RCA Evidence
      -> Action Plan
        -> Approval / Execution / Verification / Audit
          -> Wiki gap and learning loop
```

## Non-goals

- 회사 OCP/OKD 서버에 배포하지 않는다.
- 기존 `dev` 배포 지점을 직접 수정하지 않는다.
- 기존 Wiki UI를 이번 문서 작업에서 코드로 재작성하지 않는다.
- Wiki 문서를 근거 없이 자동 실행 명령으로 바꾸지 않는다.
- `evals/aiops-scenarios/*`와 보호 HTML/PDF 산출물을 수정하지 않는다.
