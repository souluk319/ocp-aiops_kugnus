# v0.2.2 AIOps Answer Experience Contract

## 기준

- 기준 브랜치: `v0.2.2-aiops-answer-experience`
- 기준 체크포인트: `v0.2.1-aiops-answer-contract` commit `d1d6108`
- 단일 구현 기준: Tool Plan JSON은 내부 작전서이고, 기본 챗봇 답변은 사람용 RCA이다.

## 목표

KOMSCO AI Agent는 매 질문마다 내부 `ToolPlan`을 만들고 Gateway가 Tool Adapter를 실행해 `RcaContext`를 만든다. 사용자가 기본 챗봇 답변에서 보는 것은 JSON 실행계획이 아니라 운영자가 바로 판단할 수 있는 RCA 답변이어야 한다.

기본 답변 형식은 아래 다섯 섹션을 따른다.

```text
원인 후보
확인한 증적
권장 조치
추가 확인
재발 방지
```

## 노출 정책

| 영역 | 보여줄 내용 | 보여주지 않을 내용 |
| --- | --- | --- |
| 기본 챗봇 답변 | 사람용 RCA, 근거 요약, 권장 조치 | raw Tool Plan JSON, raw RcaContext JSON |
| 답변 Evidence footer | 수집/추가 확인 count, evidence ref, 상세 보기의 사람용 조회 계획 | 내부 JSON 원문 |
| 상세 보기 | `조회 계획` 목록: 어떤 근거를 어떤 이유로 조회했는지 | raw Tool Plan JSON |
| Audit/개발자 화면 | 원본 `ToolPlan JSON`, 원본 `RcaContext JSON` | 없음 |
| Chat transcript | `assistantAnswer`, `toolPlanDigest`, `rcaContextDigest`, `evidenceRefs`, `answerMode` | Secret/token/raw credential |
| 콘솔 대화 목록 | 같은 브라우저 새로고침 후 복원되는 현재 대화와 최근 대화 | 첨부 이미지 원본 데이터 |
| 현재 화면 Pod RCA | Gateway가 수집한 Pod evidence 기반 답변, 조치 레코드 생성 여부 | 일반론 템플릿, 확인되지 않은 로그/설정/DB 원인 단정 |
| Cywell AI 관제탑 | 운영 대시보드와 닫힌 FAB 챗봇 런처 | 본문을 꽉 채우는 embedded/lockOpen 챗봇 |

## 실행 모드

세 모드는 모두 유지한다.

- `읽기 전용`: 증거 수집과 RCA만 수행한다. 조치 요청도 계획/승인/실행 레코드를 만들지 않는다.
- `실행 가능`: 조치 요청 시 `ActionProposal -> SealedActionPlan`까지 만든다. 실행은 승인 이후에만 가능하다.
- `실행 무제한`: 실험/개발용 확장 모드이다. UI 선택은 항상 가능해야 하며, Gateway capability가 꺼져 있으면 실행 시점에 서버가 거절 사유를 반환한다. UI가 선택 직후 임의로 `실행 가능`으로 되돌리면 안 된다.

## Acceptance Criteria

| ID | Pass/Fail 기준 | 측정 방법 | Evidence |
| --- | --- | --- | --- |
| AX-01 | 모든 질문에서 내부 ToolPlan과 RcaContext가 만들어진다. | Gateway stream/test에서 `runtime_tool_plan`, `rca_context` 이벤트 확인 | pytest, scenario verify |
| AX-02 | 기본 답변 본문에 raw Tool Plan JSON이 없다. | static verifier가 Gateway prompt와 UI 기본 카드 문자열 검사 | `scripts/verify-aiops-answer-experience.py` |
| AX-03 | 기본 답변은 사람용 RCA 섹션을 기준으로 한다. | prompt/contract/verifier가 다섯 섹션 문자열 확인 | contract + Gateway prompt |
| AX-04 | Evidence footer의 상세 보기에는 사람용 `조회 계획`이 있다. | Console component에서 `queryPlan`, `상세 보기`, `조회 계획` 확인 | typecheck/build-dev |
| AX-05 | Audit/개발자 화면에서는 원본 Tool Plan JSON과 RcaContext JSON을 유지한다. | Console page 문자열과 JSON 렌더링 확인 | static verifier |
| AX-06 | Chat transcript에 `assistantAnswer`, `toolPlanDigest`, `rcaContextDigest`, `evidenceRefs`, `answerMode`가 남는다. | Gateway transcript builder 검사 | static verifier |
| AX-07 | 읽기 전용/실행 가능/실행 무제한 모드가 모두 유지된다. | Console mode toggle 및 Gateway mode mapping 검사 | typecheck + static verifier |
| AX-08 | Pod/워크로드 화면에서 "현재 화면 기준", "안전한 확인 절차"를 물으면 수동 절차 안내가 아니라 화면 대상 RCA ToolPlan으로 승격한다. | pageContext `resourceKind=Pod` 요청이 `pod_screen_rca`와 Pod evidence 수집으로 라우팅되는지 검사 | pytest + static verifier |
| AX-09 | 같은 브라우저에서 새로고침해도 현재 대화와 최근 대화 목록이 복원된다. | Console component가 active conversation/history를 browser storage에 저장·복원하는지 검사 | static verifier + typecheck |
| AX-10 | `pod_screen_rca` 답변은 OLS 일반 문장 생성에 맡기지 않고 Gateway evidence renderer가 대상/상태/재시작/exit/owner/조치 레코드 상태를 명시한다. | Gateway helper와 stream branch가 `evidence-grounded-pod-rca-v0.2.2` 답변을 생성하는지 검사 | pytest + static verifier |
| AX-11 | `/aiops-kugnus` 관제탑 화면은 챗봇을 본문 embedded/lockOpen 형태로 렌더링하지 않는다. | Dashboard page에서 `AssistantLauncher`가 닫힌 FAB 런처로만 배치되는지 검사 | static verifier + typecheck |

## 하지 않을 것

- 보호된 Claude/user scenario JSON 또는 benchmark HTML을 수정하지 않는다.
- 런타임 JSONL transcript를 git에 커밋하지 않는다.
- 원인이 확정되지 않은 변경 작업을 즉시 실행 명령처럼 표시하지 않는다.
