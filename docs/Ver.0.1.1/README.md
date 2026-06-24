# Ver.0.1.1 AIOps 기능 고도화 기준

작성 기준일: 2026-06-24 KST  
작업 브랜치: `feat/v.0.1.1`  
기준 PDF: `docs/Komsco_ai_agent_final.pdf`

## 현재 판단

Ver.0.1.0은 Kugnus 전용 카탈로그, 기본 UI, Gateway, 안전한 read-only 우선 실행 흐름을 잡은 단계다.
Ver.0.1.1은 이제 "예쁜 챗봇" 단계가 아니라 **AIOps 기능의 실제 판단력과 증거력을 올리는 단계**로 본다.

PDF의 핵심은 다음 네 가지다.

- KOMSCO AIOps Model이 질문을 이해해 `Tool Plan JSON`을 만든다.
- AI Gateway가 Tool Plan에 따라 OpenShift, Linux, Windows, Evidence/RAG를 안전하게 조회한다.
- 수집한 증거를 `RCA Context JSON`으로 구조화해 Lightspeed 최종 답변을 강화한다.
- Operator/OLM 방식으로 설치, 업그레이드, 감사, 롤백까지 운영 가능한 제품으로 만든다.

## 지금 UI의 상태 칩 의미

현재 헤더의 작은 칩들은 기능 버튼이라기보다 상태 표시와 모드 선택이 섞여 있다.

| 표시 | 현재 의미 | 현재 문제 | Ver.0.1.1 조치 |
| :--- | :--- | :--- | :--- |
| 연결됨 | Gateway/Lightspeed 연결 상태 | 무엇이 연결됐는지 설명 부족 | tooltip 또는 popover로 Gateway, OCP API, Lightspeed 상태 분리 |
| 읽기 | 현재 실행 모드 요약 | `읽기`와 `읽기 전용`이 중복되어 보임 | 하나의 Mode selector로 통합 |
| 방패 | Safety Guard 상태 | 눌리는 버튼인지 indicator인지 모호 | Security/Safety popover로 변경 |
| `>_` | 실행/Action Executor 가능 여부 | disabled 이유가 UI에 드러나지 않음 | disabled reason, executor URL, mutation gate 표시 |
| `i` | 부가 정보/상태 | 현재 사용자가 의미를 알 수 없음 | 정보 popover 또는 제거 |

결론: **안 눌리는 애들이 떠 있는 것은 "현재 기능 상태를 표시하려는 의도"지만, UX 계약이 불명확하다.** 0.1.1에서 header status는 "상태 표시", "모드 변경", "정보 확인"을 명확히 나누어야 한다.

## 0.1.1 목표

1. Agentic Tool Plan을 실제 runtime artefact로 만든다.
2. Evidence/RAG를 "있어 보이는 카드"가 아니라 실제 조회/저장/참조 가능한 체계로 만든다.
3. OS-aware Adapter를 OpenShift-only 수준에서 Linux/Windows 설계와 최소 동작까지 확장한다.
4. Lightspeed streaming 답변에 RCA Context JSON이 실제로 들어갔는지 검증 가능하게 만든다.
5. UI는 사용자가 현재 상태, 누락 증거, 실행 가능성, 다음 행동을 바로 이해하게 만든다.

## 산출물

| 파일 | 목적 |
| :--- | :--- |
| `final-pdf-key-points.md` | 최종 PDF 14페이지 주안점 정리 |
| `product-enhancement-plan.md` | 현재 gap, 0.1.1 구현 순서, acceptance criteria |
| `pdf-requirements-completion-plan.md` | 최종 PDF 요구사항을 0.1.1에서 끝내기 위한 Epic/Phase/Pass 기준 |

## 하지 않을 것

- 기존 공용 `komsco-ai-console-plugin` 교체
- 기존 `lightspeed-console-plugin` 삭제 또는 임의 비활성화
- 회사 OCP에서 unrestricted mode를 기본값으로 사용
- `.env`, token, kubeconfig, password commit
- RAG나 모델이 실제로 없는데 "연동 완료"라고 표시
