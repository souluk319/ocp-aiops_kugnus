# v0.2.3 AIOps Reference Map

## 목적

이 문서는 KOMSCO AIOps를 강한 추론으로 새로 발명하지 않기 위한 레퍼런스 지도이다.

v0.2.3 이후 제품 판단은 아래 순서를 따른다.

```text
레퍼런스 확인
↓
KOMSCO OpenShift 맥락에 맞게 축소
↓
코드/화면/검증기로 고정
```

## 핵심 결론

KOMSCO AIOps의 기준 조합은 아래와 같다.

```text
OpenShift Lightspeed = 콘솔 안의 입
Dynatrace Assist/Davis CoPilot = 관측 데이터와 근거를 보는 눈
PagerDuty AIOps/Copilot = 인시던트 대응과 조치 흐름의 손발
RCA Agent / RCACopilot 연구 = Tool Plan, Evidence, RCA 흐름의 정당성
```

제품 문장으로 바꾸면 아래와 같다.

> KOMSCO AI Agent는 OpenShift 콘솔 안에서 질문을 받고, 관측 근거를 수집하고, 인시던트 우선순위를 정리한 뒤, 승인 가능한 Action Plan을 제시하는 운영자용 AIOps Assistant이다.

더 정확한 제품 포지션은 아래이다.

```text
OpenShift/OCP 전용 Agentic Operator for AIOps
```

즉 채팅창은 인터페이스이고, 본질은 아래 운영 루프이다.

```text
Intent 감지
→ 운영 skill 선택
→ 클러스터/로그/메트릭/이벤트 조회
→ 상태 해석
→ 원인 후보 축소
→ runbook 선택
→ 조치 제안 또는 실행
→ 결과 검증
→ 리포트/기억 저장
```

이 관점에서 경쟁력은 범용 모델의 말솜씨가 아니라 OCP 운영 맥락, runbook, tool 호출, 검증 루프, 감사 기록에 있다.

## Reference Matrix

| 레퍼런스 | 공식 설명에서 확인한 축 | 우리 제품에 가져올 것 | 구현 판단 |
| --- | --- | --- | --- |
| Red Hat OpenShift Lightspeed | OpenShift 웹 콘솔 내부에서 자연어 질문을 받고 단계별 가이드를 제공하는 생성형 AI assistant | 콘솔 내 오버레이/패널형 챗봇, OpenShift 문서 기반 답변, 초보자와 숙련자 모두를 위한 단계형 안내 | 우리 챗봇의 기본 골격. 단, 내부 Tool Plan JSON은 기본 답변에 노출하지 않는다. |
| Dynatrace Davis CoPilot | 자연어 프롬프트를 DQL로 변환하고 Notebooks/Dashboards에서 분석 결과로 연결 | 질문을 쿼리/도구 호출로 변환, 결과를 요약/표/근거로 표시 | Tool Plan은 내부 쿼리 계획이며, 답변 하단에는 `확인한 항목`과 `근거 상세보기`를 둔다. |
| Dynatrace Assist | 환경 데이터에 질문하고, 답변마다 sources를 제공하며, agentic mode에서 도구/권한 기반 데이터 분석 | 대화 저장, sources 제공, 현재 앱 context 활용, agentic permissions 구분 | Chat transcript 저장과 Evidence/RAG footer 구조를 유지한다. |
| Datadog Bits AI / Bits Chat | 관측 데이터에 대해 자연어로 탐색하고, alert investigation, security triage, operational workflow를 agentic task로 위임 | 챗봇이 단순 설명이 아니라 현재 리소스/경고를 조사하고 다음 작업을 제안하는 형태 | KOMSCO 챗봇은 `답변 박스`가 아니라 tool-equipped investigation panel이어야 한다. |
| PagerDuty AIOps | alert noise 감소, incident visibility, triage, 반복 작업 제거, 중앙 operations console | alert를 incident/action 관점으로 묶고, 우선순위/영향/다음 조치를 먼저 보여줌 | 관제탑은 복구 계획 더미가 아니라 이상 징후, 영향, 상위 Action Plan 후보 중심으로 보여준다. |
| PagerDuty Copilot | Slack 기반 생성형 AI assistant가 incident lifecycle 전체에서 인사이트 제공, “what happened / what changed / customer impact” 질문 지원 | 인시던트 맥락, 변경 이벤트, 영향 범위, remediation path | 챗봇 답변 첫 화면은 “무슨 일/무엇이 바뀜/영향/다음 조치” 순서를 우선한다. |
| Microsoft RCA Agent 연구 | ReAct agent + retrieval tools로 production incident RCA를 평가하고, 외부 진단 서비스 접근 도구를 붙임 | RCA는 말 잘하는 문제가 아니라 필요한 증거를 수집하는 문제 | Tool Plan -> Evidence -> RCA Context 흐름을 유지한다. |
| RCACopilot | 런타임 진단 정보 수집, root cause 예측, 설명 가능한 narrative, targeted action steps 제공 | 원인 후보, 판단 경로, 조치 단계, 운영자가 납득 가능한 설명 | RCA 답변은 narrative와 action steps를 같이 제공해야 한다. |

## 적용할 검색 키워드

`AIOps chatbot`보다 아래 키워드를 우선한다.

```text
OpenShift Lightspeed demo UI
OpenShift Lightspeed chat window
Ask an OpenShift Admin OpenShift Lightspeed
Dynatrace Davis CoPilot demo
Dynatrace Assist chat with data
Datadog Bits AI chat
Datadog Bits Investigation UI
PagerDuty Copilot incident response
PagerDuty AIOps demo
PagerDuty Operations Console
PagerDuty Visibility Console
incident copilot UI
root cause analysis copilot UI
observability AI assistant UI
Kubernetes AI assistant RCA
```

## 챗봇 답변 Reference Shape

기본 답변은 ChatGPT식 장문 설명이 아니라 incident copilot 형태를 따른다.

```text
요약
- 지금 무슨 일이 일어났는지 한 문장

영향 범위
- namespace / deployment / pod / node / service
- 서비스 영향 또는 컨트롤플레인 영향

원인 후보
- 가능성 높은 순서
- 확정/추정/추가 확인 필요 분리

확인 근거
- event / log / metric / alert / config diff / runbook
- 현재값, 임계값, 발생 시간이 있으면 표시

추천 확인
- read-only 확인 조치 먼저
- 어떤 명령/도구로 확인하는지 표시

Action Plan
- 승인 가능한 변경 조치만 표시
- restart / scale / patch / rollback 등
- 영향, 검증, 롤백, 승인 조건 포함

관련 문서
- Runbook / SOP / OpenShift Docs / 사내 문서
```

## UI Reference Shape

운영자 화면은 “예쁜 카드 모음”이 아니라 사고 조사관 화면이어야 한다.

```text
[경고 요약]
Severity: Warning/Critical
Target: namespace/kind/name
Status: 현재 상태
Confidence: 근거 충분도

[원인 후보]
1. 가장 가능성 높은 원인
2. 다음 가능성
3. 추가 확인 필요

[확인 근거]
✓ Event 확인됨
✓ Pod restartCount 증가
✓ Metric threshold 근접
△ 배포 변경 이력 추가 확인 필요

[추천 확인]
1. 최근 ReplicaSet 변경 이력 확인
2. memory limit 값 비교
3. 종료 직전 로그 확인

[Action Plan]
승인 필요: Deployment restart
승인 필요: Resource limit patch
거절/승인 버튼
```

## Dashboard And Tool-Equipped Chat UI References

KOMSCO AIOps UI는 대시보드와 챗봇을 따로 만든 뒤 붙이는 구조가 아니다.

기준은 아래 두 화면이 같이 움직이는 구조이다.

```text
관제탑 dashboard = 지금 어디가 위험한지 보여주는 운영 판단판
툴 장착 챗봇 = 선택된 리소스를 조사하고 Action Plan으로 넘기는 investigation panel
```

### 1. 기본 대시보드 패턴

PagerDuty Operations Console / Visibility Console 계열을 기준으로 삼는다.

가져올 것:

- incident/service 중심의 필터와 검색
- `Open`, `Acknowledged`, `Triggered`, `Assigned to me` 같은 빠른 상태 필터
- severity, priority, service, team, status 중심의 dense table
- 실시간 운영 상태를 한 곳에서 보는 중앙 console
- 자동 새로고침되는 incidents/services/activity module
- alert noise를 그대로 보여주지 않고 대응 가능한 incident 단위로 정리

KOMSCO 적용:

```text
상단: 클러스터/노드/Operator/실행 모드 상태
중앙: 현재 이상 징후 Top N
우측 또는 하단: 선택된 리소스 영향/근거/Action Plan 후보
상세: 감사 기록, 실행 기록, 원본 evidence
```

하지 않을 것:

- `복구 계획 24개`처럼 실제 실행 가능성과 무관한 계획 목록을 대량 노출하지 않는다.
- source id, plan digest, internal status를 첫 화면에 나열하지 않는다.
- 예쁜 카드 숫자판으로만 만들지 않는다.

### 2. 툴 장착 챗봇 패턴

OpenShift Lightspeed, Dynatrace Assist, Datadog Bits AI 계열을 기준으로 삼는다.

가져올 것:

- 콘솔 안에서 현재 context를 기준으로 질문을 받는다.
- 현재 resource, alert, metric, log, runbook을 도구로 조회한다.
- 답변마다 근거/sources를 접힌 상세로 제공한다.
- 대화 기록을 저장하고 이어서 질문할 수 있다.
- 사용자가 응답 생성을 취소하거나 질문을 수정해 다시 보낼 수 있다.
- 조사 결과가 충분하면 Action Plan으로 승격한다.

KOMSCO 적용:

```text
사용자 질문
↓
현재 화면 context 주입
↓
Tool Plan 생성
↓
Evidence 수집
↓
요약/영향/원인 후보
↓
Action Plan 후보
↓
승인/거절
```

하지 않을 것:

- 챗봇 본문에 RAG 원문, source uri, score를 길게 노출하지 않는다.
- Tool Plan JSON을 사용자 기본 답변으로 보여주지 않는다.
- `OLS 질의 전달중`, `Lightspeed 처리중`처럼 같은 제품을 남남인 단계로 쪼개 보이지 않는다.

### 3. 대시보드와 챗봇 연결 패턴

대시보드에서 리소스나 경고를 선택하면 챗봇은 그 context를 받아야 한다.

```text
사용자가 Pod/Alert/Node 선택
↓
챗봇 입력창에 context chip 표시
↓
안전 조회/원인 분석/Action Plan 생성 quick action 제공
↓
답변은 선택된 리소스 기준으로 생성
↓
근거 상세보기와 Action Plan 카드가 같은 thread에 남음
```

이 연결이 없으면 관제탑과 챗봇은 같은 화면에 있을 뿐, 하나의 AIOps 제품이 아니다.

### 4. KOMSCO UI Acceptance Criteria

| ID | 기준 | Pass/Fail |
| --- | --- | --- |
| UI-REF-01 | 관제탑 첫 화면에 현재 이상 징후 Top N, 영향, Action Plan 후보가 보인다. | 없으면 fail |
| UI-REF-02 | 챗봇은 현재 화면/선택 리소스 context를 chip 또는 header로 보여준다. | context가 없으면 fail |
| UI-REF-03 | 기본 답변은 요약/영향/근거/Action Plan 순서로 읽힌다. | 상세 분석부터 시작하면 fail |
| UI-REF-04 | RAG 원문과 source uri는 `근거 상세보기` 안에 있다. | 본문에 길게 나오면 fail |
| UI-REF-05 | 조사 결과가 조치 가능하면 승인/거절 가능한 Action Plan 카드가 생성된다. | 설명만 있고 버튼이 없으면 fail |
| UI-REF-06 | 대시보드에서 선택한 리소스와 챗봇 답변 대상이 일치한다. | 서로 다르면 fail |

## 제품별 적용 원칙

### 1. OpenShift Lightspeed에서 가져올 것

- OpenShift 콘솔 안에서 자연어 질문을 받는다.
- 답변은 OpenShift 사용자에게 익숙한 단어와 절차로 제공한다.
- 단계별 안내, 명령어, 문서 근거를 제공한다.
- 내부 JSON과 adapter debug는 기본 답변에서 숨긴다.

### 2. Dynatrace에서 가져올 것

- 질문을 내부 쿼리/도구 호출로 변환한다.
- 어떤 데이터를 봤는지 감추지 않는다.
- sources/evidence를 접힌 상세로 제공한다.
- 대화 기록을 저장한다.
- agentic 기능은 권한과 도구 접근 범위를 분리한다.

### 3. PagerDuty에서 가져올 것

- alert를 그대로 나열하지 않고 운영자가 대응할 incident/action 단위로 묶는다.
- noise reduction, triage, visibility, next action을 우선한다.
- 중앙 관제탑은 고압 상황에서 바로 판단할 수 있어야 한다.
- 조치 후보는 Action Plan으로 승격 가능한 것만 버튼을 준다.

### 4. RCA Agent/RCACopilot에서 가져올 것

- RCA는 LLM 문장력이 아니라 증거 수집 능력으로 평가한다.
- Tool Plan, Evidence, RcaContext 흐름은 유지한다.
- 원인 후보와 조치 단계는 설명 가능한 narrative로 연결한다.
- Action Plan은 근거 없는 조언이 아니라 수집 근거에서 파생되어야 한다.

## KOMSCO AIOps Target Pattern

최종 target pattern은 아래로 고정한다.

```text
사용자 질문 또는 관제탑 이상 징후
↓
Intent 감지
↓
운영 skill / runbook / tool 선택
↓
OpenShift context 파악
↓
Tool Plan 생성
↓
Alert/Event/Metric/Log/Runbook/문서 근거 수집
↓
RCA Context 생성
↓
운영 판단판 답변
↓
Action Proposal 후보 생성
↓
승인 가능한 Action Plan 카드 표시
↓
운영자 승인/거절
↓
실행/검증/감사 기록
```

## v0.2.3에 바로 반영할 결정

1. 제품 포지션은 `OpenShift/OCP 전용 Agentic Operator for AIOps`로 본다.
2. `AIOps 챗봇`이라는 추상 명칭보다 `Incident Copilot`, `Observability AI Assistant`, `RCA Copilot`, `Kubernetes Assistant`, `Operator Agent` 패턴을 기준으로 본다.
3. 채팅창은 핵심 제품이 아니라 Agentic Operator의 인터페이스로 본다.
4. 챗봇 답변은 `상세 분석` 먼저가 아니라 `요약 -> 영향 -> 근거 -> Action Plan` 순서로 둔다.
5. 관제탑은 `복구 계획 24개` 같은 화면이 아니라 `상위 이상 징후`, `영향`, `Action Plan 후보`, `감사 기록`으로 정리한다.
6. `바로 해결` 버튼은 Action Plan 조건을 충족한 경우에만 표시한다.
7. 문서/RAG 근거는 기본 본문에 길게 나열하지 않고 `근거 상세보기`로 이동한다.
8. 기본 대시보드는 PagerDuty Operations/Visibility Console처럼 incident/action 중심으로 구성한다.
9. 툴 장착 챗봇은 OpenShift Lightspeed, Dynatrace Assist, Datadog Bits AI처럼 현재 context와 도구 실행 결과를 결합한다.
10. 대시보드와 챗봇은 선택 리소스 context로 연결되어야 한다.

## Sources

- Red Hat OpenShift Lightspeed: https://www.redhat.com/en/technologies/cloud-computing/openshift/lightspeed
- Dynatrace Davis CoPilot: https://www.dynatrace.com/news/blog/announcing-general-availability-of-davis-copilot-your-new-ai-assistant/
- Dynatrace Assist: https://docs.dynatrace.com/docs/dynatrace-intelligence/agentic-and-generative-ai/chat-with-dynatrace-assist
- Datadog Bits AI: https://docs.datadoghq.com/bits_ai/
- Datadog Bits Chat: https://docs.datadoghq.com/bits_ai/bits_chat/
- Datadog Bits Investigation: https://www.datadoghq.com/product/ai/bits-investigation/
- PagerDuty AIOps: https://www.pagerduty.com/platform/aiops/
- PagerDuty Operations Console: https://support.pagerduty.com/main/docs/operations-console
- PagerDuty Visibility Console: https://support.pagerduty.com/main/docs/visibility-console
- PagerDuty Copilot: https://www.pagerduty.com/newsroom/pagerduty-copilot/
- Microsoft RCA Agent paper: https://arxiv.org/abs/2403.04123
- RCACopilot paper: https://arxiv.org/abs/2507.03224
