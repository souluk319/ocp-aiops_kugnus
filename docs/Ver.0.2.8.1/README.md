# Ver.0.2.8.1

## Purpose

v0.2.8.1의 목표는 챗봇 답변 형식과 좌측 패널의 조치 목록 경험을 제품 수준으로 재정의하는 것이다.

이번 버전은 바로 UI를 대량 수정하는 단계가 아니다. 먼저 JK 레퍼런스와 현재 로컬 콘솔 화면을 기준으로 아래를 고정한다.

- 챗봇 답변은 긴 보고서가 아니라 운영자가 바로 판단할 수 있는 runbook/action card 구조여야 한다.
- 좌측 패널은 단순 대화 목록이 아니라 대화와 연결된 조치 흐름을 한눈에 보여줘야 한다.
- Action Plan은 AIOps의 핵심 경험이며, 버튼과 상태가 반복 노출되거나 신뢰를 해치면 실패이다.
- 로컬 서버에서만 재현 가능한 UI 테스트 시나리오를 만들고, 브라우저로 직접 확인한 뒤 구현으로 넘어간다.

## Documents

- [chatbot-answer-ux-plan.md](./chatbot-answer-ux-plan.md)
- [ui-redesign-plan.md](./ui-redesign-plan.md)
- [local-aiops-scenario-test-plan.md](./local-aiops-scenario-test-plan.md)
- [local-aiops-manual-test-guide.md](./local-aiops-manual-test-guide.md)
- [local-aiops-scenario-test-runner.html](./local-aiops-scenario-test-runner.html)
- [local-5174-connection-incident-report.html](./local-5174-connection-incident-report.html)
- [local-aiops-scenario-test-report.json](./local-aiops-scenario-test-report.json)

## Scope

포함:

- 챗봇 답변 형식 개선 계획
- 좌측 패널 대화/조치 목록 개선 계획
- JK 레퍼런스 흡수 항목
- 로컬 브라우저 테스트 시나리오
- pass/fail acceptance criteria

제외:

- 회사 서버 배포
- OLM publish/install
- protected artifact 수정
- 대량 리팩터링
- JK 코드 그대로 복사
