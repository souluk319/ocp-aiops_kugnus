# KOMSCO AIOps Safe Refactoring Harness Plan

목표는 줄 수를 억지로 줄이는 것이 아니라, 기능 동작을 유지한 채 파일별 책임 경계를 분리하는 것이다. `main.py` 18,723줄은 최우선 대상이지만, 한 번에 대수술하지 않는다. 모든 작업은 작은 단위로 나누고, 각 단계마다 테스트와 diff를 확인한다.

## 0. 절대 원칙

1. 기능 변경 금지
2. API path 변경 금지
3. response schema 변경 금지
4. env var 이름 변경 금지
5. RBAC/Auth 동작 변경 금지
6. Action review/execution 정책 변경 금지
7. redaction/masking 정책 변경 금지
8. 테스트 기대값 임의 수정 금지
9. 새 기능 추가 금지
10. 기존 로직을 새로 재작성하지 말고, 가능한 그대로 이동
11. import 연결을 위해 wrapper/glue code를 과도하게 만들지 말 것
12. 한 단계가 실패하면 그 단계만 되돌릴 것

## 1. 작업 전 기준점 고정

아래 명령을 실행하고 결과를 기록한다.

```bash
pwd
git status --short
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py
pytest komsco-ai-gateway/tests/test_health.py -q
```

가능하면 현재 정상 동작 기준 커밋을 만든다.

```bash
git add -A
git commit -m "baseline before safe refactoring"
```

커밋이 어렵다면 최소한 patch를 저장한다.

```bash
git diff > /tmp/before-refactoring.patch
```

## 2. 매 단계 공통 하네스

각 리팩토링 단계는 반드시 아래 순서로만 진행한다.

```bash
# 1. 변경 전 상태 확인
git status --short

# 2. 아주 작은 범위만 수정
# 예: constants만 이동, schema만 이동, formatter 함수 1묶음만 이동

# 3. 문법 확인
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py
find komsco-ai-gateway/komsco_ai_gateway -type f -name "*.py" -exec python -m py_compile {} \;

# 4. 핵심 테스트
pytest komsco-ai-gateway/tests/test_health.py -q

# 5. 변경량 확인
git diff --stat
git diff --name-status

# 6. main.py 줄 수 확인
wc -l komsco-ai-gateway/komsco_ai_gateway/main.py
```

실패하면 코드 추가로 땜질하지 말고, 원인 보고 후 해당 단계만 되돌린다.

```bash
git checkout -- <failed_file>
git clean -fd <new_files_if_needed>
```

## 3. Stop 조건

아래 중 하나라도 발생하면 즉시 중지하고 보고만 한다.

- import error가 3개 이상 발생
- 테스트 기대값을 바꾸고 싶어짐
- 기존 함수 이동보다 새 함수 작성이 많아짐
- main.py는 줄었지만 전체 Python 라인 수가 증가
- Action/RBAC/Auth 쪽 동작을 이해하지 못한 채 수정 필요
- response key 변경 필요성이 생김
- env var 이름 변경 필요성이 생김
- circular import 해결을 위해 임시 wrapper가 늘어남
- 1단계 변경에서 500줄 이상 diff 발생

중지 보고 형식:

```text
STOP REPORT
- 실패 단계:
- 변경 파일:
- 깨진 테스트/에러:
- 새로 만든 파일:
- 되돌려야 할 파일:
- 안전하게 재시도 가능한 더 작은 범위:
```

## 4. 우선순위 파일 목록

현재 라인 수 기준 상위 파일이다. 줄 수는 의심 지표일 뿐이며, 실제 판단은 책임 혼합도와 변경 위험도로 한다.

| 우선 | 파일 | 줄 수 | 판단 | 처리 방향 |
|---:|---|---:|---|---|
| 1 | `komsco-ai-gateway/komsco_ai_gateway/main.py` | 18723 | 최우선. Gateway 핵심이 과밀 | 안전 분리 |
| 2 | `komsco-ai-gateway/tests/test_health.py` | 9054 | 테스트 시나리오 과밀 | main.py 이후 분리 |
| 3 | `komsco-ai-console-plugin/src/components/assistant.css` | 8892 | 전역 CSS 과밀 | 기능 안정 후 분리 |
| 4 | `komsco-ai-console-plugin/src/portal/PortalApp.tsx` | 8056 | 포털 메인 과밀 | 화면/상태 분리 |
| 5 | `komsco-ai-console-plugin/src/portal/styles.css` | 7611 | CSS 과밀 | 후순위 |
| 6 | `komsco-ai-portal/src/styles.css` | 7502 | CSS 과밀 | 후순위 |
| 7 | `komsco-ai-portal/src/App.tsx` | 7335 | 앱 메인 과밀 | 라우팅/뷰 분리 |
| 8 | `komsco-ai-portal/src/v2/v2.css` | 6237 | v2 스타일 과밀 | 후순위 |
| 9 | `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx` | 4510 | 챗봇 UI 핵심 과밀 | main.py 이후 |
| 10 | `scripts/verify-v0281-chatbot-answer-ux.cjs` | 4344 | 검증 스크립트 | 후순위 |
| 11 | `komsco-ai-portal/src/v2/lib/model.ts` | 3361 | 모델/타입 과밀 가능 | 검토 |
| 12 | `scripts/serve-v0281-local-aiops-gateway.cjs` | 3203 | 로컬 서버 스크립트 | 후순위 |

## 5. main.py 안전 분리 순서

### Phase 1. 순수 선언만 이동

대상:

- constants
- enum-like values
- regex patterns
- default prompt/template strings
- simple TypedDict/Pydantic schema/dataclass

금지:

- 함수 로직 수정
- route 함수 이동
- auth/action/RBAC 로직 수정

예상 산출:

```text
komsco_ai_gateway/config.py
komsco_ai_gateway/schemas.py
komsco_ai_gateway/constants.py
```

성공 기준:

- py_compile 통과
- test_health.py 통과
- response schema 변화 없음

### Phase 2. 유틸 함수 이동

대상:

- string helper
- timestamp helper
- redaction helper 중 순수 함수
- dict/list normalization helper

주의:

redaction/masking은 보안 정책이므로 본문 변경 금지. 파일만 이동한다.

예상 산출:

```text
komsco_ai_gateway/utils/text.py
komsco_ai_gateway/utils/time.py
komsco_ai_gateway/security/redaction.py
```

### Phase 3. Response formatter 분리

대상:

- chatbot final answer formatting
- evidence summary formatting
- action/result message formatting
- markdown/table rendering helpers

금지:

- 문구 대규모 변경
- key 이름 변경
- thought/tool plan 노출 정책 변경

예상 산출:

```text
komsco_ai_gateway/agent/response_formatter.py
komsco_ai_gateway/agent/evidence_formatter.py
```

### Phase 4. OpenShift read-only 조회 함수 분리

대상:

- Pod 조회
- Event 조회
- Log 조회
- Node 조회
- Snapshot 조회

금지:

- write/mutation action 이동
- 권한 체크 우회
- token 처리 변경

예상 산출:

```text
komsco_ai_gateway/ocp/client.py
komsco_ai_gateway/ocp/pods.py
komsco_ai_gateway/ocp/events.py
komsco_ai_gateway/ocp/logs.py
komsco_ai_gateway/ocp/nodes.py
```

### Phase 5. Auth/RBAC 분리

대상:

- UserToken extraction
- authorization check
- access review request builder
- RBAC deny response builder

주의:

이 단계는 위험도가 높다. 함수 본문 수정 없이 이동만 한다.

예상 산출:

```text
komsco_ai_gateway/auth/tokens.py
komsco_ai_gateway/auth/rbac.py
komsco_ai_gateway/auth/access_review.py
```

### Phase 6. Action review/executor 분리

대상:

- action registry
- action proposal/review
- sealed action plan
- executor authorization
- audit record generation

주의:

가장 위험한 구간이다. Phase 1~5가 안정화된 뒤에만 진행한다.

예상 산출:

```text
komsco_ai_gateway/actions/registry.py
komsco_ai_gateway/actions/review.py
komsco_ai_gateway/actions/executor.py
komsco_ai_gateway/actions/audit.py
```

### Phase 7. Routes 분리

대상:

- health routes
- chat routes
- action routes
- audit/history routes

최종 목표:

```text
main.py는 app 생성, middleware, router 등록, startup/shutdown wiring만 담당한다.
```

예상 산출:

```text
komsco_ai_gateway/routes/health.py
komsco_ai_gateway/routes/chat.py
komsco_ai_gateway/routes/actions.py
komsco_ai_gateway/routes/audit.py
komsco_ai_gateway/app_factory.py
```

## 6. main.py 목표 구조

현실적 1차 목표:

```text
main.py 18723줄 -> 12000줄 이하
```

2차 목표:

```text
main.py 12000줄 -> 8000줄 이하
```

3차 목표:

```text
main.py 8000줄 -> 5000줄 이하
```

최종 목표:

```text
main.py 5000줄 -> 3000줄 이하
```

최종 형태 예시:

```python
from komsco_ai_gateway.app_factory import create_app

app = create_app()
```

현실적으로는 app 생성과 router 등록 코드가 남아도 된다.

## 7. 프론트엔드 비만 파일 처리 원칙

main.py 안정화 전에는 프론트 리팩토링을 동시에 하지 않는다. 단, 리뷰는 가능하다.

### AssistantLauncher.tsx

분리 후보:

```text
AssistantLauncher.tsx
assistant.state.ts
assistant.actions.ts
assistant.streaming.ts
assistant.quickPrompts.ts
AssistantChatPanel.tsx
AssistantInputBox.tsx
AssistantMessageList.tsx
```

### aiGateway.ts

분리 후보:

```text
services/aiGateway/client.ts
services/aiGateway/chat.ts
services/aiGateway/actions.ts
services/aiGateway/streaming.ts
services/aiGateway/types.ts
services/aiGateway/errors.ts
```

### PortalApp.tsx / App.tsx

분리 후보:

```text
routes.tsx
layouts/*.tsx
views/*.tsx
state/*.ts
```

### CSS

CSS는 기능 리팩토링 이후 처리한다. CSS 분리는 스냅샷/UI 확인 없이 진행하지 않는다.

분리 후보:

```text
assistant.layout.css
assistant.messages.css
assistant.input.css
assistant.timeline.css
pages.dashboard.css
pages.rca.css
portal.layout.css
portal.theme.css
```

## 8. 테스트 파일 분리 원칙

`test_health.py` 9054줄은 main.py 이후 분리한다.

분리 방향:

```text
tests/test_health.py
tests/test_chat_responses.py
tests/test_actions_review.py
tests/test_actions_executor.py
tests/test_rbac.py
tests/test_ocp_context.py
tests/test_redaction.py
tests/test_audit.py
```

금지:

- 리팩토링 실패를 해결하려고 expected 값을 바꾸지 말 것
- 테스트 삭제 금지
- skip 추가 금지

## 9. Codex 작업 프롬프트

아래 프롬프트를 Codex에게 반복 사용한다.

```text
You are performing safe refactoring only.

Goal:
Reduce file obesity by separating responsibilities without behavior changes.

Hard rules:
- Do not change API paths.
- Do not change response schemas.
- Do not rename env vars.
- Do not change RBAC/Auth behavior.
- Do not change Action review/execution policy.
- Do not change redaction/masking policy.
- Do not add new features.
- Do not rewrite logic unless absolutely required.
- Prefer moving existing code unchanged.
- Do not modify test expectations.
- If tests fail, report first. Do not patch around the failure.

Current phase:
<PHASE_NAME>

Allowed scope:
<EXACT_FILES_OR_FUNCTION_GROUPS>

Required report after work:
1. Files changed
2. Functions/classes moved
3. New imports added
4. Tests run and results
5. main.py line count before/after
6. Risks or unresolved issues

Stop immediately if:
- import errors multiply
- circular imports require new wrappers
- action/RBAC behavior becomes unclear
- response schema would need changes
- tests require expectation updates
```

## 10. 매 시간 점검 명령

밤새 하네스 돌릴 때 1시간마다 아래를 기록한다.

```bash
date
git status --short
git diff --stat
wc -l komsco-ai-gateway/komsco_ai_gateway/main.py
find komsco-ai-gateway/komsco_ai_gateway -type f -name "*.py" -exec wc -l {} + | sort -nr | head -30
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py
pytest komsco-ai-gateway/tests/test_health.py -q
```

## 11. 성공 판정

좋은 리팩토링:

```text
main.py 줄 수 감소
새 모듈은 책임별로 작게 증가
테스트 기대값 변경 없음
API/response/env/RBAC/action 정책 변화 없음
import 경로 명확
Codex가 특정 파일만 보고 수정 가능
```

나쁜 리팩토링:

```text
main.py 줄었지만 전체 코드가 증가
glue/wrapper가 늘어남
테스트 expected 수정
skip 추가
기존 로직 재작성
RBAC/action 경계 흐림
순환 import 땜질
```

## 12. 당장 실행 추천 순서

오늘 밤 실행 순서:

1. baseline commit 또는 patch 저장
2. Phase 1만 수행: constants/schemas 순수 선언 이동
3. 테스트 통과 확인
4. Phase 2 수행: 순수 utility만 이동
5. 테스트 통과 확인
6. Phase 3 일부 수행: response formatter 중 독립 함수만 이동
7. 여기까지만 진행하고 보고

오늘 밤 금지:

- Action executor 대수술
- RBAC 대수술
- route 전체 분리
- CSS 리팩토링 동시 진행
- 프론트 대형 컴포넌트 동시 진행
