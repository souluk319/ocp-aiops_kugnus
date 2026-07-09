# KOMSCO AIOps Docs Map

이 폴더는 공식 원문, 계약 사본, 학습 문서, 테스트북, 설계/검증 산출물이 섞이지 않도록 카테고리별로 정리한다.

## 먼저 봐야 하는 공식 기준

- `Komsco_ai_agent_final.pdf`: 최상위 공식 기준 문서
- `AIOps-For-OCP.pdf`: AIOps for OCP 최종 기준 자료
- `contracts/`: 공식 PDF를 검색하기 쉽게 변환한 Markdown 계약 사본

## 보호 benchmark 문서

아래 파일은 기존 경로를 유지한다. 다른 문서나 구현을 평가할 때 기준으로 읽되, 명시 요청 없이 이동/수정하지 않는다.

- `aiops-beginner-guide.html`: 초보자 학습 문서 품질 기준
- `version-progress-book.html`: 버전 진행 기록장
- `Ver.0.1.8/aiops-llm-strategy-brief.html`: 상세 전략 브리프 품질 기준

## 현재 카테고리

| 폴더 | 용도 | 대표 문서 |
| --- | --- | --- |
| `architecture/` | 구조, 경계, 실행 아키텍처 | `aiops-agent-architecture-proposal.md`, `ols-gateway-tool-boundary.md` |
| `design/` | UI, 색상, 아이콘 정책 | `assistant-color-map.html`, `coolicons-functional-icon-policy.md` |
| `reports/` | 검증/감사/시나리오 결과 | `aiops-agentic-scenario-verification-report.md` |
| `study/` | 개념 학습, E-Book, 운영 흐름 설명 | `aiops-action-plan-e-book.html` |
| `testbooks/` | 직접 따라 하는 테스트북 | `TestBook_26.07.08.html` |
| `contracts/` | 공식 PDF 검색용 계약 사본 | `Komsco_ai_agent_final.contract.md`, `AIOps-For-OCP.contract.md` |
| `color/` | 디자인 참고 색상 이미지 | `black.png`, `white.png`, `back ground white.png` |
| `Ver.*` | 버전별 스냅샷 산출물 | 각 버전의 README, 계획서, 보고서, HTML |

## HTML 문서 빠른 분류

### 테스트북

- `testbooks/TestBook_26.07.08.html`
- `Ver.0.1.3/test-readiness-book.html`
- `Ver.0.1.9/aiops-replica-recovery-testbook.html`
- `Ver.0.2.8.1/connected-aiops-scenario-test-book.html`
- `Ver.0.2.8.1/local-aiops-scenario-test-runner.html`

### 스터디/가이드

- `study/aiops-action-plan-e-book.html`
- `aiops-beginner-guide.html`
- `Ver.0.1.0/kugnus-aiops-catalog-practice-guide.html`
- `Ver.0.1.8/demo-guide-past-pod-restart.html`
- `Ver.0.1.8/local-okd-workbench-reboot-recovery-guide.html`
- `Ver.0.2.8.1/local-okd-aiops-run-tutorial.html`
- `Ver.0.2.8.1/reboot-aiops-start-study-guide.html`

### 전략/아키텍처

- `Ver.0.1.8/aiops-llm-strategy-brief.html`
- `Ver.0.1.8.2/aiops-execution-logic-deep-plan.html`
- `Ver.0.2.8/aiops-llm-wiki-strategy-brief.html`
- `Ver.0.1.9/komsco-aiops-agent-brief.html`
- `Ver.0.2.0/komsco-aiops-agent-brief.html`

### 검증/리포트

- `reports/aiops-agentic-scenario-verification-report.md`
- `Ver.0.1.3/code-and-risk-audit.html`
- `Ver.0.1.4/completion-review.html`
- `Ver.0.1.5/demo-readiness-report.html`
- `Ver.0.1.6/preflight-report.html`
- `Ver.0.2.8.1/local-5174-connection-incident-report.html`

### 디자인/UI

- `design/assistant-color-map.html`
- `design/coolicons-functional-icon-policy.md`
- `Ver.0.2.9/aiops-for-ocp-demo-deck.html`

## 정리 원칙

- 공식 PDF와 보호 benchmark 문서는 루트 경로를 유지한다.
- 새 학습 HTML은 `study/` 또는 `testbooks/`에 둔다.
- 새 UI/색상/아이콘 문서는 `design/`에 둔다.
- 새 구조/경계 문서는 `architecture/`에 둔다.
- 검증 결과는 `reports/` 또는 해당 `Ver.*` 폴더에 둔다.
- 이미 버전 폴더 안에 있는 산출물은 과거 스냅샷이므로 무리하게 이동하지 않는다.
