# KOMSCO AIOps Design Rules

이 문서는 KOMSCO AIOps Console Plugin, 관제탑, 챗봇, Action Plan 화면을 만들기 전에 읽는 프로젝트 전용 디자인 기준이다.

목표는 예쁜 화면이 아니라 운영자가 압박 상황에서도 빠르게 판단하고 승인할 수 있는 OpenShift 운영 도구이다.

## Product Position

KOMSCO AIOps는 마케팅 사이트가 아니다.

```text
OpenShift/OCP 전용 Agentic Operator for AIOps
```

첫 화면과 주요 화면은 설명용 hero가 아니라 실제 운영 화면이어야 한다.

채팅창은 본체가 아니라 operator interface이다. 핵심 화면은 intent, evidence, RCA, runbook, Action Plan, 승인/거절, 실행 검증, 감사 기록이 연결되는 운영 루프를 보여줘야 한다.

- 관제탑
- 챗봇
- Evidence/RCA
- Action Plan
- 승인/거절
- 실행/검증/감사 기록

## Visual Tone

- 조용하고 밀도 있는 admin console이어야 한다.
- 정보의 우선순위가 색보다 먼저 보여야 한다.
- 장식용 gradient, 큰 hero, 마케팅식 카드 나열을 금지한다.
- 보라/파랑 gradient 떡칠, 의미 없는 배경 장식, 큰 둥근 카드 남발을 금지한다.
- 카드 안에 카드를 넣지 않는다.
- 같은 정보는 한 번만 보여준다. 본문, footer, badge, 상세 영역에 중복으로 뿌리지 않는다.

## Layout Rules

- 화면은 `상태 요약 -> 우선 확인 -> 근거 -> Action Plan -> 상세/감사` 순서로 읽혀야 한다.
- 관제탑은 복구 계획 더미 목록이 아니라 현재 이상 징후와 승인 가능한 조치 후보를 보여준다.
- 챗봇 오버레이를 닫으면 관련 좌측 패널도 함께 정리되어야 한다. 패널만 남는 상태는 실패이다.
- 좁은 패널에서 버튼, 배지, 언어 전환, 실행 모드가 겹치면 실패이다.
- 폰트는 운영자가 바로 읽을 수 있어야 한다. 12px 이하의 본문성 텍스트는 지양한다.
- 긴 technical id는 기본 본문을 밀어내지 않게 chip, monospace, 접힘 상세로 제한한다.

## Chat Answer Rules

챗봇 기본 답변은 보고서 원문이나 내부 로그가 아니다.

기본 순서는 아래로 고정한다.

```text
요약
영향 범위
확인한 근거
원인 후보
Action Plan
추가 확인
재발 방지
```

- raw Tool Plan JSON은 기본 답변에 노출하지 않는다.
- RAG 원문, source uri, score, 내부 event id는 기본 본문에 나열하지 않는다.
- 문서/RAG/Tool 근거는 `근거 상세보기`에 모은다.
- `RCA 문맥 연결: post_answer` 같은 내부 용어는 제품 화면에 노출하지 않는다.
- `OLS 스트림 중계중`처럼 사용자에게 불필요하게 어려운 상태 문구를 쓰지 않는다.
- OpenShift Lightspeed는 OLS의 풀네임이다. OLS와 Lightspeed를 서로 다른 단계처럼 표시하지 않는다.

## Evidence And Detail Rules

운영자가 기본 화면에서 봐야 하는 것은 raw source가 아니라 판단 가능한 근거이다.

기본 화면:

```text
근거 수집 4
추가 확인 1
Action Plan 가능/불가
```

상세 보기:

```text
조회 계획
수집한 evidence
누락 evidence
RAG 문서
source uri
score
Tool Plan JSON
RcaContext JSON
```

- 개발자/감사용 raw JSON은 유지하되 기본 화면에서 숨긴다.
- 근거 badge는 작아도 읽혀야 하며, 내부 id가 화면을 지배하면 실패이다.
- 문서 근거와 운영 증거는 섞지 않는다.

## Action Plan Rules

AIOps의 중심 경험은 승인 버튼이 달린 Action Plan이다.

Action Plan 카드에는 반드시 아래가 보여야 한다.

- 대상
- 문제
- 근거
- 조치
- 예상 영향
- 검증 방법
- 롤백 또는 실패 시 대응
- 승인 조건
- 승인/거절 버튼

`바로 해결`은 조건이 충분할 때만 쓴다. 원인 후보만 있는 상태에서는 `근거 더 수집` 또는 `Action Plan 생성`을 쓴다.

## Execution Mode Rules

실행 모드는 기능을 숨기지 않는다.

- `읽기 전용`
- `실행 가능`
- `실행 무제한`

세 모드는 모두 UI에서 선택 가능해야 한다.

서버 정책상 특정 실행이 거절되면 버튼을 없애지 말고, 사람이 이해할 수 있는 거절 사유를 보여준다.

`읽기 전용`은 제품 전체의 기본 사상이 아니다. 단지 실행 모드 중 하나이다.

## Label Rules

제품 화면의 용어는 운영자 언어를 우선한다.

권장:

- `확인 중`
- `답변 생성 중`
- `근거 수집 중`
- `Action Plan 생성`
- `승인 필요`
- `실행 가능`
- `실행 무제한`
- `근거 상세보기`
- `조회 계획`

피할 것:

- `RCA 문맥 연결`
- `post_answer`
- `Sealed plan`
- `proposal waits for`
- `ExecutionRecord` 단독 노출
- `OLS 스트림 중계중`
- `read-only mode`를 제품 철학처럼 보이게 하는 문구

개발자/감사 화면에서는 원본 용어를 표시할 수 있지만, 운영자 기본 화면에서는 사람용 용어로 바꾼다.

## Header And Chrome Rules

- KOMSCO 워드마크가 공간을 잡아먹으면 K 로고만 사용한다.
- 상태 배지와 실행 모드는 같은 행에서 읽히되, 좁으면 자연스럽게 다음 줄로 내려간다.
- 언어 전환 `KR/EN`은 실제로 작동해야 하며, 작동하지 않으면 표시하지 않는다.
- 아이콘 버튼은 tooltip 또는 접근 가능한 label을 가진다.
- 실행 모드 badge는 작아도 클릭 가능한 영역과 선택 상태가 분명해야 한다.

## Reference Shapes

화면 판단은 새로 상상하지 않고 아래 레퍼런스 패턴을 먼저 본다.

- OpenShift Lightspeed: 콘솔 내부 자연어 assistant
- Dynatrace Assist/Davis CoPilot: 관측 데이터, query/tool 변환, sources
- Datadog Bits AI: alert investigation, observability data chat, delegated operational workflow
- PagerDuty AIOps/Copilot: incident triage, impact, next action, remediation path
- PagerDuty Operations/Visibility Console: incident/service 중심 dense dashboard, filter, real-time operations view
- RCA Agent/RCACopilot: tool use, evidence, RCA narrative, targeted action steps

자세한 제품 기준은 `docs/Ver.0.2.3/aiops-reference-map.md`를 따른다.

## Final UI Checklist

UI 변경을 완료했다고 말하기 전에 아래를 확인한다.

- 첫 화면이 실제 도구인가?
- 운영자가 지금 가장 먼저 볼 항목이 위에 있는가?
- raw JSON, source uri, 내부 id가 기본 화면을 더럽히지 않는가?
- Action Plan 버튼은 근거/영향/검증/롤백과 함께 있는가?
- 실행 모드 3개가 모두 보존되는가?
- 챗봇을 닫았을 때 좌측 패널 같은 잔여 UI가 남지 않는가?
- 좁은 폭에서 버튼과 배지가 겹치지 않는가?
- 폰트가 너무 작아 읽기 어렵지 않은가?
- KR/EN 같은 표시된 기능이 실제 동작하는가?
- 보호된 문서나 시나리오를 불필요하게 수정하지 않았는가?
