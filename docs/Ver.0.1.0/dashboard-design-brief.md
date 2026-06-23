# Ver.0.1.0 Dashboard and Chat UI Design Brief

작성 기준일: 2026-06-24 KST

## 현재 판단

Cywell AI for KOMSCO는 OpenShift Console 안에서 동작하는 운영 보조 도구다. 따라서 외부 admin dashboard template, stock image, 별도 UI kit를 가져와 꾸미는 방식이 아니라 OpenShift Console과 같은 질감의 PatternFly 기반 UI로 고정한다.

검색 기준:

- PatternFly Dashboard: https://www.patternfly.org/patterns/dashboard/design-guidelines
- PatternFly Card: https://www.patternfly.org/components/card/design-guidelines
- PatternFly Drawer: https://www.patternfly.org/components/drawer/html-demos
- PatternFly AI Chatbot: https://www.patternfly.org/patternfly-ai/chatbot/about-chatbot
- PatternFly Chatbot Header: https://www.patternfly.org/patternfly-ai/chatbot/chatbot-header
- PatternFly Chatbot Conversation History: https://www.patternfly.org/patternfly-ai/chatbot/chatbot-conversation-history
- PatternFly Chatbot Footer / Message Bar: https://www.patternfly.org/patternfly-ai/chatbot/chatbot-footer
- PatternFly Chatbot Messages: https://www.patternfly.org/patternfly-ai/chatbot/chatbot-messages
- OpenShift Dynamic Plugins: https://docs.redhat.com/en/documentation/openshift_container_platform/4.14/html/web_console/dynamic-plugins
- OpenShift dynamic-plugin-sdk: https://github.com/openshift/console/blob/main/frontend/packages/console-dynamic-plugin-sdk/README.md
- Microsoft Teams streaming UX stop control reference: https://learn.microsoft.com/en-us/microsoftteams/platform/bots/streaming-ux
- MDN CSS resize reference: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/resize

판단:

- OpenShift 동적 플러그인은 PatternFly component와 CSS variable을 써야 콘솔과 맞는다.
- Dashboard는 KPI/상태/증적/정책을 카드와 그리드로 보여주는 구조가 맞다.
- Chat UI는 PatternFly AI Chatbot 계열의 기본 기능을 따른다: toggle, compact header, message stream, message bar, stop control, conversation history drawer.
- 외부 테마는 사용하지 않는다. 고객 로고와 K 아이콘만 제품 식별 자산으로 사용한다.

## 디자인 에셋 계약

| 목적 | 파일 | 사용 위치 |
| :--- | :--- | :--- |
| Catalog card icon | `docs/Ver.0.1.0/design-assets/K_icon.png` | OLM CSV icon, Software Catalog/OperatorHub 카드 |
| Assistant floating toggle | `komsco-ai-console-plugin/src/assets/k_icon.png` | 우측 하단 assistant FAB |
| Empty assistant mark | `komsco-ai-console-plugin/src/assets/k_icon.png` | 빈 대화 상태 |
| KOMSCO customer logo | `docs/Ver.0.1.0/design-assets/komsco_logo.svg` | 기준 원본 |
| Chat header logo | `komsco-ai-console-plugin/src/assets/komsco_logo.svg` | Cywell AI 헤더 |

원칙:

- `K_icon.png`는 카탈로그와 챗봇 토글 심볼이다.
- `komsco_logo.svg`는 고객/훈련 대상 로고다. 헤더 브랜드 영역에서만 쓴다.
- 외부 dashboard image, gradient background, stock illustration은 사용하지 않는다.
- 아이콘은 가능한 `@patternfly/react-icons`를 사용한다.

## Chat UI 계약

### Header

한 줄 배치로 고정한다.

```text
sidebar toggle | KOMSCO logo | Cywell AI | language | fullscreen | resize lock | close
```

Pass 기준:

- sidebar toggle은 헤더 맨 왼쪽이다.
- KOMSCO 로고는 toggle 오른쪽에 있고, 한글이 식별될 만큼 보인다.
- 제품명은 `Cywell AI`다.
- 헤더 아래에 별도 메뉴 row/context strip을 만들지 않는다.
- 상태 chip을 억지로 헤더에 밀어 넣어 세로 공간을 늘리지 않는다.

Fail 기준:

- sidebar toggle이 헤더 오른쪽이나 본문 안에 있다.
- KOMSCO 로고가 너무 작아 텍스트를 식별하기 어렵다.
- 헤더와 메뉴가 두 줄로 갈라져 채팅 공간을 잡아먹는다.
- 텍스트 badge를 과하게 나열해 운영 화면이 지저분해진다.

### Sidebar

ChatGPT형 히스토리 패턴으로 고정한다.

Pass 기준:

- sidebar는 surface의 sibling panel이다.
- sidebar를 열어도 chat workspace 내부 column을 쪼개지 않는다.
- embedded view에서는 sidebar가 열리면 우측 insight rail을 숨기고 chat 폭을 보존한다.
- fullscreen view에서는 sidebar, chat, insight rail이 서로 겹치지 않는다.
- sidebar open/close 때 width animation으로 흔들림을 만들지 않는다.

Fail 기준:

- sidebar가 workspace 내부 column이 되어 chat과 rail을 동시에 압축한다.
- fullscreen에서 좌측 sidebar와 우측 panel이 겹친다.
- sidebar open/close 때 레이아웃이 흔들려 버튼 위치가 튄다.

### Composer and Streaming

Pass 기준:

- 전송 버튼은 입력이 없으면 disabled다.
- 응답 생성 중에는 전송 버튼이 stop 버튼으로 바뀐다.
- 사용자가 scroll up하면 자동 하단 고정이 풀리고, 하단 복귀 버튼이 나타난다.
- 답변은 일반 챗봇처럼 paragraph/list/code/table 형태로 읽히게 포맷한다.
- 답변 복사 버튼은 assistant message에 제공한다.

Fail 기준:

- 응답 중단 수단이 없다.
- 스트리밍 중 사용자가 위를 읽는데 강제로 아래로 끌고 간다.
- 답변이 raw text dump처럼 보여 읽기 어렵다.

### Resize and Fullscreen

Pass 기준:

- 기본 상태는 resize locked다.
- lock 해제 버튼을 누르면 일반 floating assistant는 `resize: both`, embedded route는 `resize: vertical`이다.
- resize는 브라우저 native handle에만 기대지 않고 `.komsco-ai__resize-grip` mouse drag로 직접 제어한다.
- embedded route에서 resize 해도 문서 전체에 가로 스크롤이 생기지 않는다.
- fullscreen은 body portal로 올라가 OpenShift masthead나 parent overflow에 막히지 않는다.
- fullscreen에서도 exit/fullscreen/lock/language/sidebar 버튼이 클릭 가능해야 한다.

Fail 기준:

- embedded route에서 가로 resize가 되어 페이지 전체가 옆으로 밀린다.
- fullscreen이 부모 container 안에 갇혀 버튼 클릭이 막힌다.
- resize lock 상태가 UI와 실제 CSS 상태가 다르다.

## Dashboard 정보 구조

PatternFly dashboard 기준으로 카드 하나는 하나의 판단만 전달한다.

첫 화면 순서:

```text
Cywell AI title
-> Cluster health overview + API/version/safety/Lightspeed stream summary
-> Four primary metric cards
-> Embedded Cywell AI assistant
-> Evidence / Lightspeed / Tool Plan / Adapter / Safety / Operator panels
```

| 카드 | 목적 | 표시 데이터 |
| :--- | :--- | :--- |
| Cluster Health | 현재 OCP 상태 한눈에 확인 | health score, node ready, operator degraded |
| Lightspeed Link | 기존 Lightspeed 연동 상태 확인 | OLS base, stream status, fallback status |
| Agentic Plan | PDF의 Tool Plan JSON 개념 노출 | platform, execution policy, selected tools |
| Evidence Posture | 증적 충분성 표시 | event/log/metric/runbook/audit collected or missing |
| OS Adapter | Linux/Windows/OpenShift adapter 상태 표시 | adapter availability and scope |
| Safety Guard | read-only/mutation/unrestricted gate 표시 | allowed verbs, forbidden actions |
| Audit/Execution | 운영 책임성 확보 | recent audit/action/diagnostic records |

Pass 기준:

- 첫 화면은 설명서가 아니라 현재 상태를 보여준다.
- 카드 제목, 주요 수치, 상태 tone이 명확하다.
- Evidence가 없으면 success처럼 보이지 않고 missing으로 보인다.
- 위험 작업은 disabled 또는 별도 승인 흐름으로 보인다.
- `/aiops-kugnus` dashboard route에서는 embedded assistant가 있으므로 전역 floating FAB를 중복 표시하지 않는다.

Fail 기준:

- 마케팅 hero처럼 보인다.
- card 안에 설명 텍스트를 과하게 넣어 관제성이 떨어진다.
- 한 가지 색상 계열로만 화면을 채워 상태 구분이 약하다.
- embedded assistant와 전역 floating assistant toggle이 같은 화면에 동시에 떠 있다.

## 자동 검증

로컬 콘솔이 떠 있는 상태에서 실행한다.

```bash
task kugnus:ui:verify
```

기본 검증 URL:

```text
http://localhost:9000/aiops-kugnus
```

환경변수로 변경 가능:

```bash
KUGNUS_UI_URL=http://localhost:9000/aiops-kugnus task kugnus:ui:verify
KUGNUS_CHROME_DEBUG_PORT=9230 task kugnus:ui:verify
```

기본 실행은 Chrome CDP `9231` 포트를 사용한다. `9230`은 이전 수동 검증 세션이 남아 stale state가 생긴 적이 있어 기본값으로 쓰지 않는다. 다른 포트가 필요할 때만 `KUGNUS_CHROME_DEBUG_PORT`를 지정한다.

검증 항목:

- assistant surface load
- dashboard overview appears before assistant stage
- dashboard route does not show duplicate global assistant FAB
- dashboard health score is loaded from Gateway cluster summary
- dashboard overview side shows API, version, safety, and Lightspeed stream values
- dashboard exposes four primary metrics
- dashboard metric labels are connected: Ready nodes, Operator issues, Audit records, Action records
- dashboard has Evidence, Lightspeed, Tool Plan, OS Adapter, Safety panels
- header title `Cywell AI`
- sidebar toggle is left of KOMSCO logo
- KOMSCO logo visible size
- language toggle changes KO/EN label
- sidebar opens as surface sibling
- sidebar does not split chat workspace
- embedded sidebar hides right rail
- fullscreen portal parent is `BODY`
- fullscreen layout does not overlap left/sidebar/right rail
- resize default locked
- embedded resize unlock is vertical-only
- resize drag changes height
- embedded resize does not create horizontal overflow
- resize lock disables manual resize again
- composer send starts disabled without prompt
- composer send enables when prompt is entered
- composer send button turns into stop during response
- composer stop returns control to normal send button
- chat interaction creates visible conversation messages
- manual scroll-up unlocks bottom stickiness and shows the jump-to-latest button
- jump-to-latest returns the conversation to the newest message

WSL 주의:

- WSL에서 실행해도 `scripts/verify-kugnus-ui.mjs`는 Windows Chrome CDP에 붙기 위해 Windows Node로 자동 위임한다.
- 이유: Windows Chrome remote debugging port가 Windows loopback에만 열릴 수 있어 WSL Node가 직접 접근하지 못하는 경우가 있다.
- 사용자는 그대로 `task kugnus:ui:verify`만 실행하면 된다.

스크린샷 산출물:

```text
.tmp-aiops-kugnus-ui-verify-fullscreen.png
.tmp-aiops-kugnus-ui-verify-resize.png
```

현재 검증 결과:

```text
task kugnus:ui:verify
42 checks pass
```

## Ver.0.1.0 완료 기준

| 항목 | Pass |
| :--- | :--- |
| Catalog card | `K_icon.png`가 OLM CSV icon으로 들어간다 |
| Product title | 챗봇 헤더 제품명이 `Cywell AI`다 |
| Header | sidebar toggle, KOMSCO logo, title, action buttons가 한 줄이다 |
| Sidebar | history sidebar가 workspace를 쪼개지 않는다 |
| Fullscreen | body portal에서 겹침 없이 동작한다 |
| Resize | lock/unlock과 실제 CSS resize 상태가 일치한다 |
| Dashboard | PatternFly card/grid 기반의 운영 상태 화면이다 |
| Safety | read-only/mutation/unrestricted 상태가 과장 없이 표시된다 |
| Automation | `task kugnus:ui:verify`가 로컬 UI 계약을 PASS/FAIL로 판정한다 |
