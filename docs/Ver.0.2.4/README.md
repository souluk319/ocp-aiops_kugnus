# v0.2.4 JK Reference Absorption

## 기준

- 기준 브랜치: `dev`
- 기준 HEAD: `5c178dd`
- 참고 브랜치: `cywell-rnd-team/ocp-aiops` `feature/aiops-jk`
- 참고 HEAD: `d9921bd`
- 작성 목적: JK 브랜치의 UI/시스템 설계 강점을 KOMSCO AIOps v0.2.3 Action Plan 계약 위에 흡수하기 위한 구현 계획을 고정한다.

## 핵심 판단

JK 브랜치는 전체 제품을 통째로 대체할 대상이 아니라, 아래 세 영역에서 우리 제품보다 더 명확한 기준을 제공한다.

| 영역 | JK 브랜치에서 배울 점 | v0.2.4 반영 방향 |
| --- | --- | --- |
| 챗봇 UI | 일반 말풍선보다 운영 런북 카드가 먼저 보인다. | 답변 첫 화면을 `우선 확인 -> 근거 -> 명령/절차 -> Action Plan` 구조로 재배치한다. |
| 확장 레이아웃 | 넓은 화면에서 빈 공간 대신 context rail을 사용한다. | expanded assistant를 `chat column + context rail` 구조로 고정한다. |
| 시스템 경계 | OLS, Gateway, Action Executor 역할이 문서로 분리되어 있다. | 현재 FastAPI 구현 안에서 책임 경계와 라벨을 일관되게 맞춘다. |
| Agentic action logic | 자연어 요청을 typed action으로 바꾸고 대상 확인, 승인, 실행, 검증까지 연결한다. | intent parser, target resolver, registry, execution grant, followup 복원 로직을 별도 흡수 대상으로 둔다. |
| 검증 루프 | typed action과 멀티턴 후속 실행을 시나리오로 검증한다. | restart/scale/evict/rollback/HPA/ambiguous/read-only 시나리오를 v0.2.4 게이트로 둔다. |

## 참고 산출물

현재 repo 또는 임시 비교 clone에서 확인한 참고 파일은 아래이다.

```text
demo/DESIGN.md
demo/ocp_chatbot_redesign.html
demo/ocp_chatbot_redesign_docked.png
demo/ocp_chatbot_redesign_expanded.png
docs/architecture/ols-gateway-tool-boundary.md
docs/architecture/aiops-agent-architecture-proposal.md
docs/reports/aiops-agentic-scenario-verification-report.md
scripts/evaluate-aiops-actions-e2e.py
```

## 이번 버전의 산출물

- [aiops-jk-reference-absorption-plan.md](./aiops-jk-reference-absorption-plan.md)

## 하지 않을 것

- 회사 OCP/OKD 서버 배포
- OLM 패키징 변경
- Helm chart, NetworkPolicy, Route, Subscription 변경
- 보호된 Claude/user 산출물 수정
- `evals/aiops-scenarios/*` 수정
- JK 코드를 통째로 복사

## 권장 실행 순서

```text
1. v0.2.4 문서 계약 고정
2. JK backend/action logic inventory를 먼저 작성
3. 챗봇 런북 카드 UI를 작은 브랜치에서 구현
4. expanded context rail 구현
5. Action Plan lifecycle/dedupe 정리
6. Gateway/action 검증 시나리오 보강
7. 브라우저와 type/build 검증 후 다음 배포 계약으로 넘김
```
