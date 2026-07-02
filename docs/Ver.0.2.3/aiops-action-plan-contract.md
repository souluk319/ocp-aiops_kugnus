# v0.2.3 AIOps Action Plan Contract

## 기준

- 기준 브랜치: `v0.2.2-aiops-answer-experience`
- 기준 HEAD: `d4ce654`
- 단일 구현 기준: AIOps의 중심 경험은 챗봇이 운영자에게 승인 가능한 `Action Plan`을 제시하고, 운영자가 승인/거절 버튼으로 실행을 통제하는 것이다.

## 제품 이상향

KOMSCO AIOps는 없는 개념을 새로 발명하는 프로젝트가 아니다.

OpenShift/Kubernetes 운영, Observability, AIOps, ITSM, Runbook 자동화, 운영 위키, 토폴로지 기반 관제 UI는 이미 레퍼런스와 정답지가 많이 쌓인 영역이다. 따라서 v0.2.3부터는 강한 추론으로 새로운 제품 형태를 창조하려고 하기보다, 이미 검증된 구조를 기준으로 수렴한다.

기본 우선순위는 아래와 같다.

```text
1. 레퍼런스가 있는 운영 구조를 먼저 확인한다.
2. 그 구조를 KOMSCO/OpenShift 맥락에 맞게 좁혀 구현한다.
3. 추론은 빈칸을 메우는 데만 쓴다.
4. 추론 결과는 반드시 코드, 화면, 검증기로 고정한다.
```

KOMSCO AI Agent의 목표는 단순히 장애 원인을 설명하는 RCA 챗봇이 아니다.

제품 포지션은 아래로 고정한다.

```text
OpenShift/OCP 전용 Agentic Operator for AIOps
```

채팅창은 인터페이스일 뿐이고, 핵심 자산은 운영 skill, runbook, tool 호출, evidence 수집, 검증 루프, 실행/감사 기록이다.

| 구분 | 의미 |
| --- | --- |
| AIOps 챗봇 | 사용자가 물어보면 로그/메트릭/문서 기반 설명을 제공한다. |
| Agentic Operator | 문제가 생기면 의도를 파악하고, 필요한 도구를 선택하고, 클러스터 상태를 확인하고, 원인 후보를 좁히고, runbook을 선택하고, 조치를 제안/실행하고, 결과를 검증/기록한다. |

따라서 UI와 답변은 “대화가 잘 되는 챗봇”보다 “운영자가 승인 가능한 판단과 조치 계획을 받는 operator console”을 우선한다.

운영자가 원하는 상태는 아래에 가깝다.

```text
문제가 있다
근거가 있다
원인 후보가 있다
실행 가능한 조치 계획이 있다
예상 영향과 검증 방법이 있다
승인 버튼으로 실행 여부를 통제할 수 있다
실행 결과와 감사 기록이 남는다
```

따라서 v0.2.3의 이상향은 아래 문장으로 고정한다.

> AIOps의 꽃은 챗봇이 승인 버튼이 달린 Action Plan을 제시하는 것이다.

## 레퍼런스 우선 원칙

v0.2.3 이후 제품 결정은 아래 레퍼런스 축을 먼저 본다.

상세 레퍼런스 맵은 [aiops-reference-map.md](./aiops-reference-map.md)를 단일 기준으로 둔다.

| 축 | 참고할 정답지 | 우리 제품에 반영할 것 |
| --- | --- | --- |
| OpenShift/Kubernetes 운영 | Alert, Event, Pod 상태, Logs, Metrics, Operator 상태, `oc describe`, `oc logs`, `oc adm top` | 현재 화면 리소스 기준 증거 수집, 운영자가 아는 명령/상태명 사용 |
| Observability/AIOps | Red Hat Insights/Lightspeed, Dynatrace Davis, Datadog Watchdog/Bits AI, New Relic AI, Splunk ITSI, Elastic AI Assistant | 영향도, 근거, 원인 후보, 우선순위, 다음 조치 분리 |
| ITSM/Runbook 자동화 | ServiceNow, PagerDuty, Rundeck, StackStorm, Ansible Automation Platform | 승인 가능한 조치 계획, 실행 전 영향/검증/롤백, 실행 감사 |
| 운영 위키/문서 | Confluence, Backstage, internal runbook/wiki | 문서 근거와 운영 증거 분리, RAG 원문은 상세 보기/문서 영역으로 이동 |
| 토폴로지 관제 | Palantir식 entity graph, service map, dependency map, CMDB | 리소스/서비스/노드/경고 간 관계를 한 화면에서 추적 |
| 운영 UI | Cloud/Observability 콘솔의 dense dashboard, incident console, alert detail page | 카드 남발보다 스캔 가능한 요약, 상태 배지, 우선순위 리스트, 접힌 상세 |

따라서 구현 의사결정 문장은 아래처럼 쓴다.

```text
이 UI/흐름은 새로 상상한 것이 아니라,
기존 AIOps/Observability/ITSM 레퍼런스에서 검증된 패턴을
KOMSCO OpenShift 운영 맥락에 맞게 축소 구현한 것이다.
```

## 추론 사용 원칙

강한 추론은 제품 형태를 새로 창조하는 데 쓰지 않는다. 아래 경우에만 쓴다.

- 여러 레퍼런스가 충돌할 때 KOMSCO 맥락에 맞는 우선순위를 정한다.
- 현재 코드/데이터/화면이 레퍼런스 패턴과 어디서 어긋나는지 찾는다.
- 검증 기준을 `pass/fail`로 바꾼다.
- 레퍼런스에는 없지만 이 프로젝트의 제약 때문에 필요한 접착 구조를 설계한다.

강한 추론을 쓰지 말아야 할 경우도 고정한다.

- 이미 업계 표준 UI/운영 흐름이 있는 경우
- 버튼/라벨/폰트/배치처럼 레퍼런스와 사용성 기준으로 판단 가능한 경우
- 사용자가 작은 수정 또는 명확한 복구를 요청한 경우
- 근거 없이 “그럴듯한 AIOps”를 새로 만드는 경우

## 용어 고정

| 용어 | 의미 | 사용자 기본 화면 노출 |
| --- | --- | --- |
| `Tool Plan` | Gateway/Agent가 내부적으로 만드는 도구 호출 계획. Alert, Event, Metric, Log, Runbook을 어떤 순서로 조회할지 정한다. | 기본 노출하지 않음 |
| `RcaContext` | Tool Plan 실행 결과로 만들어진 근거 묶음. 수집 근거, 누락 근거, 원인 후보, 조회 계획을 포함한다. | 요약만 노출 |
| `Action Proposal` | 근거 기반 조치 후보. 아직 승인 가능한 실행 계획은 아니다. | 조치 후보로 노출 가능 |
| `Action Plan` | 운영자가 승인/거절할 수 있는 실행 계획. 대상, 명령/변경 범위, 예상 영향, 검증, 롤백, 감사 기록 조건을 포함한다. | 핵심 노출 대상 |
| `Approval` | 운영자의 승인/거절 판단. 버튼 클릭으로 남는다. | 버튼으로 노출 |
| `Execution Record` | 승인 후 실제 실행/검증/감사 결과. | 실행 결과로 노출 |

## 목표 흐름

```text
사용자 질문 또는 화면 이상 징후
↓
Intent 감지
↓
운영 skill / runbook / tool 선택
↓
클러스터 / 로그 / 메트릭 / 이벤트 조회
↓
상태 해석
↓
원인 후보 축소
↓
RcaContext 생성
↓
사람용 RCA 요약
↓
Action Proposal 생성
↓
승인 가능한 Action Plan 생성
↓
운영자 승인/거절
↓
실행
↓
검증
↓
Execution Record / Audit / memory 기록
```

## 기본 챗봇 답변 구조

기본 답변은 보고서처럼 길게 풀지 않는다. 먼저 운영 판단판을 보여준다.

```text
현재 우선 확인
- 가장 급한 항목 1~3개
- 서비스 영향 또는 컨트롤플레인 영향

확인한 근거
- Alert/Event/Metric/Pod/Runbook 근거
- 현재값, 임계값, 발생 시간은 있으면 표시
- 없으면 "추가 확인 필요"로 표시

원인 후보
- 근거로 말할 수 있는 후보만 표시
- 추정과 확정은 분리

Action Plan
- 승인 가능한 조치가 있으면 계획 카드로 제시
- 변경 대상, 영향, 검증, 롤백, 승인 조건을 표시
- 승인/거절 버튼 제공

추가 확인
- Action Plan을 만들기 전에 더 필요한 근거
```

## Action Plan 카드 기준

Action Plan은 아래 항목을 반드시 가진다.

| 항목 | 설명 |
| --- | --- |
| 대상 | namespace/kind/name, 또는 node/operator/alert 이름 |
| 문제 | 어떤 증상 또는 경고를 해결하려는지 |
| 근거 | Action Plan 생성에 사용된 evidence refs 요약 |
| 조치 | 실제 변경 또는 실행할 작업 |
| 예상 영향 | 서비스 영향, 재시작, 일시 중단, 권한 영향 |
| 검증 | 실행 후 어떤 상태를 확인할지 |
| 롤백 | 실패 시 되돌리는 방법 또는 수동 복구 방법 |
| 승인 조건 | 누가 무엇을 승인해야 하는지 |
| 버튼 | `승인`, `거절`, 필요 시 `근거 더 수집` |

## 실행 모드와 Action Plan

| 모드 | 동작 |
| --- | --- |
| `읽기 전용` | RCA와 근거 수집만 수행한다. Action Plan 버튼은 만들지 않는다. 대신 "Action Plan 생성을 위해 실행 가능 모드가 필요"라고 표시한다. |
| `실행 가능` | `Action Proposal -> Action Plan`까지 만든다. 실행은 승인 이후에만 가능하다. |
| `실행 무제한` | 실험/개발용 확장 모드이다. UI 선택은 가능해야 하며, 서버 정책이 거절하면 거절 사유를 사람이 읽는 말로 표시한다. |

## UX 원칙

- 사용자는 raw Tool Plan JSON을 읽고 승인하지 않는다.
- 사용자는 Action Plan의 영향, 검증, 롤백을 보고 승인한다.
- `바로 해결`이라는 표현은 원인과 조치가 충분히 확정된 경우에만 쓴다.
- 원인 후보만 있고 조치 근거가 부족하면 `근거 더 수집`을 먼저 보여준다.
- 위험 조치는 `권장 조치`가 아니라 `승인 후 가능한 조치`로 표현한다.
- Action Plan이 없는데 조치 버튼만 있는 상태는 실패로 본다.

## Acceptance Criteria

| ID | Pass/Fail 기준 | 측정 방법 | Evidence |
| --- | --- | --- | --- |
| AP-01 | `Tool Plan`은 내부 계획으로 유지되고 기본 답변에 raw JSON으로 노출되지 않는다. | static verifier / browser text check | `scripts/verify-aiops-answer-experience.py` |
| AP-02 | `Action Plan`은 운영자에게 보여주는 승인 가능한 계획으로 문서와 UI에서 일관되게 사용된다. | source grep / UI label check | v0.2.3 verifier 예정 |
| AP-03 | 실행 가능한 조치에는 대상, 문제, 근거, 조치, 예상 영향, 검증, 롤백, 승인 조건이 표시된다. | action card component test | v0.2.3 implementation |
| AP-04 | `읽기 전용` 모드에서는 Action Plan 승인/실행 버튼이 생기지 않는다. | Gateway/console test | pytest + static verifier |
| AP-05 | `실행 가능` 모드에서는 Action Proposal과 Action Plan을 만들 수 있지만 승인 전 실행하지 않는다. | Gateway test / browser action flow | pytest + browser |
| AP-06 | 운영자가 승인하면 Approval 기록과 Execution Record가 남는다. | Gateway records check | API test |
| AP-07 | 운영자가 거절하면 rejected 기록이 남고 실행은 차단된다. | Gateway records check | API test |
| AP-08 | Action Plan이 없는 경우 챗봇은 "무엇을 추가 확인해야 Action Plan을 만들 수 있는지"를 알려준다. | prompt/answer contract check | static verifier |
| AP-09 | 기본 답변은 먼저 운영 판단판을 보여주고, 상세 분석은 아래로 미룬다. | browser visual/text check | browser |
| AP-10 | Action Plan 카드의 버튼은 모바일/좁은 패널에서도 겹치거나 잘리지 않는다. | responsive browser check | screenshot / DOM check |

## v0.2.3 구현 범위

1. Action Plan 용어 정리
   - UI에서 `복구 계획`, `바로 해결`, `Sealed plan` 같은 표현을 운영자용 `Action Plan` 흐름으로 정리한다.
   - Audit/개발자 화면은 원본 용어를 유지할 수 있다.

2. Action Plan 카드 설계
   - 기존 조치 후보 카드와 승인 버튼을 Action Plan 기준으로 재구성한다.
   - 카드에는 영향/검증/롤백/승인 조건이 보여야 한다.

3. 챗봇 답변 계약 보강
   - 단순 상세 분석보다 `현재 우선 확인 -> 근거 -> 원인 후보 -> Action Plan -> 추가 확인` 순서를 우선한다.
   - Action Plan이 가능하면 답변 말미가 아니라 판단 흐름 안에서 보여준다.

4. 검증기 추가
   - `scripts/verify-aiops-action-plan-experience.py`를 추가한다.
   - Action Plan 용어, 버튼, 읽기 전용 차단, 승인 전 실행 차단을 검사한다.

5. 브라우저 확인
   - `/aiops-kugnus`에서 조치 후보와 챗봇 답변의 Action Plan 표시를 확인한다.
   - 버튼이 보이고, 누르기 전/후 상태가 분명해야 한다.

## 하지 않을 것

- Tool Plan JSON을 기본 챗봇 답변에 직접 보여주지 않는다.
- 근거가 부족한 조치를 `바로 해결`처럼 확정적으로 표시하지 않는다.
- 승인 전 실행을 하지 않는다.
- 보호된 Claude/user scenario JSON과 benchmark HTML은 수정하지 않는다.
- 런타임 JSONL 로그는 커밋하지 않는다.
