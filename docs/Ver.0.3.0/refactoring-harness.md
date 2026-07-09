# OCP AIOps Refactoring Harness

## 문서 목적

이 문서는 OCP AIOps 프로젝트를 안전하게 리팩토링하기 위한 실행 하네스다.

이 문서의 목표는 다음 둘이다.

- 리팩토링 중에도 전체 시스템이 계속 동작하도록 보호한다.
- 줄 수 감량 자체가 아니라, 무리 없이 운영 가능한 건강한 구조를 만든다.

## 성공 기준

다음 조건을 모두 만족하면 이번 리팩토링은 성공으로 본다.

- 핵심 사용자 플로우가 리팩토링 전후 동일하게 동작한다.
- 플러그인, 포털, 게이트웨이, OLM 관련 배포 흐름이 모두 살아 있다.
- 기존 거대 파일은 책임 기준으로 분리되며, 새 경계가 문서화되어 있다.
- 새로 추가되는 코드는 기존보다 더 작은 단위, 더 좁은 책임, 더 쉬운 테스트 구조를 가진다.
- 리팩토링 도중 문제가 생기면 즉시 되돌릴 수 있다.

## 비목표

이번 작업에서 아래 항목은 목표가 아니다.

- 줄 수만을 위한 무리한 분해
- UI 재디자인
- API 계약 변경
- 여러 축의 아키텍처 개편을 한 번에 수행
- 테스트 자산 삭제를 통한 겉보기 안정화

## 적용 방식과 종료 조건

이 하네스의 핵심은 리팩토링 전에 먼저 시스템을 측정 가능한 상태로 만드는 것이다.

실제 적용 순서는 아래처럼 고정한다.

1. `tests/test_health.py`, `scripts/verify-*`, `scripts/evaluate-*`를 정리 대상이 아니라 게이트로 승격한다.
2. 현재 실패와 통과를 베이스라인 리포트로 분리한다.
3. `main.py`에서 부트스트랩과 도메인 로직을 분리한다.
4. 프런트에서는 `PortalApp.tsx`, `App.tsx`, `AssistantLauncher.tsx`에서 상태 소유권과 렌더링을 분리한다.
5. CSS는 Playwright/Cypress/스크린샷 기준 이미지가 잡힌 뒤에만 들어간다.
6. Operator/OLM 관련 변경은 매번 bundle/package 검증, scorecard 또는 그 대체 증거, cluster smoke를 붙인다.

건강한 상태의 정의는 줄 수가 아름답게 떨어지는 순간이 아니다.

- 동작이 보존된다.
- 경계가 분명해진다.
- 다음 변경이 덜 무섭다.
- 실패했을 때 어느 층이 깨졌는지 바로 보인다.

줄 수 감량은 보너스다. 이번 작업의 본체는 안전한 구조 전환과 작업자 멘탈 보존이다.

## Acceptance Criteria

| ID | 기준 | Pass/Fail | 측정 방법 | Evidence | 현재 gap |
| --- | --- | --- | --- | --- | --- |
| AC-01 | 리팩터링 전 기준 상태가 남는다 | Pass는 branch, HEAD, test 결과, 스크린샷/로그 위치가 기록된 상태 | `git status --short --branch`, `git rev-parse HEAD`, 베이스라인 명령 실행 | `.tmp-kugnus-refactor/` 또는 `docs/Ver.0.3.0/` 리포트 | 첫 리팩터링 PR 전에 baseline report 파일이 필요 |
| AC-02 | 보호 자산이 삭제/무력화되지 않는다 | 보호 자산 삭제, 무근거 skip, silent delete가 있으면 Fail | `git diff --name-status`, 보호 자산 diff review | PR diff와 검증 로그 | `test_health.py`는 현재 거대하지만 보호 게이트로 유지해야 함 |
| AC-03 | 게이트웨이 계약이 보존된다 | API envelope, auth/RBAC, action proposal/approval/execute 의미 변경 시 Fail | `pytest`, gateway response evaluator, contract verifier | pytest output, evaluator JSON | 현재 `test_health.py` 일부 실패는 별도 baseline으로 분류 필요 |
| AC-04 | 프런트 상태와 렌더링 경계가 분리된다 | 상태 hook/service와 presentational component가 구분되면 Pass | TS build/typecheck, UI verifier, screenshot | build log, screenshot path | CSS 기준 이미지가 먼저 필요 |
| AC-05 | OLM/Operator 변경은 배포 경로가 살아 있다 | package/status/smoke 중 하나라도 깨지면 Fail | `task aiops:package`, `task olm:status`, 필요 시 cluster smoke | Task output, cluster status | scorecard task는 현재 Taskfile에 직접 노출되어 있지 않음 |
| AC-06 | 변경 단위가 되돌릴 수 있다 | 한 PR에 주 경계가 2개 이상이면 Fail | PR plan과 changed files 비교 | 작업 기록 템플릿 | 대형 파일을 한 번에 반으로 나누는 작업 금지 |
| AC-07 | 작업자가 다음 행동을 판단할 수 있다 | 실패 원인, 다음 명령, 롤백 기준이 없으면 Fail | 최종 보고 체크 | final report, handoff note | “통과/실패/미실행”을 매번 명시해야 함 |

## 현재 최우선 대상

### 보호 자산

아래 파일들은 당장 정리 대상이 아니라 보호 자산으로 취급한다.

- `komsco-ai-gateway/tests/test_health.py`
- `scripts/verify-*.cjs`
- `scripts/verify-*.py`
- `scripts/evaluate-*.py`
- `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py`
- `komsco-ai-console-plugin/src/services/aiGateway.ts`

원칙:
- 보호 자산은 먼저 실행 가능 상태를 고정한다.
- 리팩토링 초기에는 삭제, 통합, 대규모 rename 금지.
- 필요 시 fixture 정리나 공통 helper 추출만 허용.

### 1차 리팩토링 타깃

- `komsco-ai-gateway/komsco_ai_gateway/main.py`
- `komsco-ai-console-plugin/src/portal/PortalApp.tsx`
- `komsco-ai-portal/src/App.tsx`
- `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx`

### 2차 리팩토링 타깃

- `komsco-ai-gateway/komsco_ai_gateway/olm_operator.py`
- `komsco-ai-portal/src/v2/lib/model.ts`
- `komsco-ai-console-plugin/src/pages/AiopsPages.tsx`
- `komsco-ai-console-plugin/src/pages/AiopsDashboardSections.tsx`

### 시각 회귀 민감 타깃

아래 파일은 로직 경계 안정화 후에 다룬다.

- `komsco-ai-console-plugin/src/components/assistant.css`
- `komsco-ai-console-plugin/src/portal/styles.css`
- `komsco-ai-portal/src/styles.css`
- `komsco-ai-portal/src/v2/v2.css`
- `komsco-ai-console-plugin/src/pages/aiops-pages.css`

### 초기 위험도 측정값

아래 값은 목표 숫자가 아니라 위험도 지도다. 줄 수를 줄이기 위해 기능을 바꾸면 실패다.

| 파일 | 현재 줄 수 | 리팩터링 의미 |
| --- | ---: | --- |
| `komsco-ai-gateway/komsco_ai_gateway/main.py` | 18,520 | 부트스트랩, route, domain, adapter, response mapping이 한 파일에 섞인 최우선 분리 대상 |
| `komsco-ai-gateway/tests/test_health.py` | 9,054 | 정리 대상이 아니라 회귀 감지 게이트 |
| `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx` | 4,510 | launcher/session/action/rendering state 분리 대상 |
| `komsco-ai-console-plugin/src/portal/PortalApp.tsx` | 8,056 | portal shell, route composition, data/state ownership 분리 대상 |
| `komsco-ai-portal/src/App.tsx` | 7,335 | standalone portal shell과 page composition 분리 대상 |
| `komsco-ai-portal/src/v2/lib/model.ts` | 3,361 | v2 mock/runtime model boundary 정리 대상 |
| `komsco-ai-console-plugin/src/components/assistant.css` | 8,892 | 기준 이미지 확보 전 대형 수정 금지 |
| `komsco-ai-portal/src/v2/v2.css` | 6,237 | 기준 이미지 확보 전 대형 수정 금지 |

## 하드 룰

- 한 PR에서는 한 개의 주 경계만 건드린다.
- 같은 PR에서 플러그인 API 계약과 게이트웨이 응답 형태를 동시에 바꾸지 않는다.
- 기존 동작을 대체하기 전, 새 seam 또는 adapter를 먼저 추가한다.
- 리팩토링 중 새 버그를 “리팩토링 범위 밖”으로 넘기지 않는다.
- 테스트를 고치기 전에 왜 깨졌는지 분류한다.
- 깨진 이유가 실제 회귀면 코드 수정, 테스트 오탐이면 테스트 수정, 외부 불안정이면 quarantine 규칙 적용.

## 변경 단위 규칙

각 변경은 아래 단위를 넘기지 않는다.

- 라우트 추출 1개
- 서비스 객체 추출 1개
- 상태 훅 추출 1개
- 프리젠테이셔널 컴포넌트 추출 1개
- CSS 섹션 분리 1개
- 계약 스키마 정리 1개

큰 파일 하나를 한 번에 반으로 쪼개지 않는다.
항상 “추출 → 연결 → 비교 → 스위치” 순서로 진행한다.

## 베이스라인 캡처

리팩토링 시작 전 아래를 반드시 남긴다.

권장 출력 위치:

- `.tmp-kugnus-refactor/baseline/`
- `.tmp-kugnus-refactor/screenshots/`
- `.tmp-kugnus-refactor/logs/`
- `docs/Ver.0.3.0/refactoring-baseline-summary.md`

최소 ref stamp:

```bash
git status --short --branch
git rev-parse HEAD
git rev-parse --abbrev-ref --symbolic-full-name '@{u}' || true
python3 --version
node --version
task --version
```

WSL/PowerShell 주의:

- 이 repo의 기준 실행 환경은 WSL bash로 둔다.
- PowerShell에서 직접 실행할 때는 `|`, `>`, `2>/dev/null`, `@{u}`, 백틱이 먼저 해석될 수 있다.
- Codex 세션 셸이 PowerShell이면 아래처럼 WSL bash 안으로 명령을 넣어 실행한다.

```powershell
wsl -d Ubuntu --cd /home/kugnus/cywell/ocp-aiops_kugnus -- bash -lc 'git status --short --branch'
```

### 실행 베이스라인

- 현재 브랜치 SHA
- 실행 환경
- 사용 클러스터 정보
- 사용 모델/게이트웨이 설정
- 로그인/인증 조건
- 필수 환경 변수 목록

### 기능 베이스라인

- 플러그인 로드 성공 여부
- 포털 초기 진입 성공 여부
- 핵심 대시보드 렌더링 여부
- 어시스턴트 실행/응답 여부
- 액션 이력 표시 여부
- 리포트 화면 진입 여부
- 실행 이력 화면 진입 여부
- crashloop/live demo 관련 주요 흐름 여부

### 로그 베이스라인

- server log
- browser console error
- network error
- gateway error envelope
- operator / bundle 관련 이벤트

### 화면 베이스라인

다음 화면의 스크린샷을 기준 이미지로 저장한다.

- 포털 홈
- 대시보드
- Assistant launcher 닫힘 상태
- Assistant launcher 열림 상태
- action history
- markdown 답변 렌더링
- report view
- execution view
- aiops pages 주요 1면

화면 베이스라인은 무거운 브라우저 검증이므로 모든 작은 PR에서 강제하지 않는다. CSS, layout, dashboard, assistant rendering, portal shell 변경이 있을 때 필수로 올린다.

## 필수 검증 스위트

### 빠른 스모크

다음은 모든 PR에서 기본 실행한다.

- health 관련 테스트
- 게이트웨이 응답 스모크
- 로컬 aiops 시나리오
- 어시스턴트 기본 답변 UX
- 액션 lifecycle 스모크

권장 명령:

```bash
python3 -m py_compile \
  komsco-ai-gateway/komsco_ai_gateway/main.py \
  komsco-ai-gateway/tests/test_health.py

komsco-ai-gateway/.venv/bin/python -m pytest komsco-ai-gateway/tests/test_health.py

python3 scripts/verify-aiops-answer-boundary.py
python3 scripts/verify-aiops-answer-experience.py
node scripts/verify-v029-chatbot-markdown-ux.cjs
node scripts/verify-v029-chatbot-action-history-flow.cjs
task kugnus:scenario:verify
```

`komsco-ai-gateway/.venv/bin/python`이 없으면 `python3 -m pytest ...`로 대체한다. 단, 어떤 Python으로 실행했는지 evidence에 남긴다.

### 경계 검증

다음은 계약 변경 또는 경계 파일 변경 시 필수다.

- plugin ↔ gateway contract 검증
- connected aiops 시나리오
- local aiops 시나리오
- final response 검증
- action history flow 검증
- markdown UX 검증
- completion audit 검증

권장 명령:

```bash
python3 scripts/verify-aiops-answer-boundary.py
python3 scripts/verify-aiops-answer-experience.py
node scripts/verify-v0281-local-aiops-scenarios.cjs
node scripts/verify-v0281-connected-aiops-scenarios.cjs
node scripts/verify-v029-aiops-completion-audit.cjs
```

connected 시나리오는 local console, gateway, OCP access가 준비된 경우에만 실행한다. 미실행이면 `not run: missing local console/gateway/OCP access`처럼 이유를 적는다.

### 실환경/데모 검증

다음은 release 후보 또는 live demo 관련 변경 시 필수다.

- crashloop live demo cycle
- live lightspeed final response
- live action lifecycle
- review gate
- demo preflight
- OCP connectivity ladder

권장 명령:

```bash
task kugnus:demo:preflight
task kugnus:aiops:verify
task kugnus:runtime:smoke
task kugnus:actions:live-verify
task kugnus:lightspeed:live-verify
task kugnus:ocp:ladder:verify
python3 scripts/evaluate-gateway-responses.py
python3 scripts/evaluate-aiops-actions-e2e.py
python3 scripts/verify-crashloop-live-demo-cycle.py
python3 scripts/verify-live-action-lifecycle.py
python3 scripts/verify-live-lightspeed-final-response.py
```

실환경 검증은 인증, VPN, 회사 서버 접근, 로컬 gateway 상태의 영향을 받는다. 실패 시 `auth`, `network`, `cluster`, `gateway`, `model/RAG`, `UI rendering`, `stale state` 중 하나로 원인을 분류한다.

### OLM/Operator 검증

아래 파일이 바뀐 경우 필수다.

- `olm_operator.py`
- `olm-package.py`
- bundle/catalog 관련 파일

항목:
- bundle 생성
- bundle validate
- scorecard
- cluster install smoke
- upgrade smoke
- ConsolePlugin enable 확인

현재 repo에서 바로 확인한 Taskfile 경로:

```bash
task aiops:package
task aiops:status
task olm:package
task olm:status
```

회사 서버 대상 작업은 아래 순서만 허용한다.

```bash
task kugnus:company:check
task kugnus:company:status
```

`publish`, `install`, `redeploy`는 별도 사용자 승인 전에는 실행하지 않는다.

scorecard gap:

- 현재 Taskfile에는 `scorecard` 전용 task가 직접 노출되어 있지 않다.
- Operator/OLM 변경 PR에서는 `operator-sdk scorecard`를 직접 실행한 로그를 붙이거나, `task olm:scorecard` 같은 명시 task를 먼저 추가해야 한다.

## Quarantine 규칙

외부 환경 또는 라이브 의존으로 인해 흔들리는 테스트는 삭제하지 않는다.

허용:
- 명시적 이유가 있는 `xfail`
- 명시적 이유가 있는 `skip`
- flaky 라벨 부여
- 재실행 정책 적용
- 별도 nightly 또는 pre-release 단계 이동

금지:
- 이유 없는 skip
- 실패 테스트 silent delete
- “나중에 고침” 주석만 남기기

## 리팩터링 Lane 순서

### Lane 0: 게이트 승격

목표:
- 기존 테스트와 verify/evaluate 스크립트를 삭제 대상이 아니라 안전장치로 고정한다.

해야 할 일:
- 현재 `test_health.py` 실패 목록을 baseline으로 저장한다.
- 실패를 `actual regression`, `stale expectation`, `environment/live dependency`, `known gap`으로 분류한다.
- 각 분류마다 다음 행동을 정한다.

완료 조건:
- “무엇이 깨졌는지 모른다” 상태가 사라진다.
- 첫 리팩터링 PR에서 어떤 검증을 반드시 돌릴지 결정된다.

### Lane 1: Gateway 부트스트랩 분리

목표:
- `main.py`를 먼저 작게 만드는 것이 아니라, FastAPI 앱 생성과 route wiring 경계를 만든다.

허용 변경:
- settings/config 모듈 추가
- router registration helper 추가
- 기존 route handler를 유지한 채 import 경로만 안정화

금지:
- response envelope 의미 변경
- auth/RBAC 판단 변경
- action proposal/approval/execute 정책 변경

완료 조건:
- `main.py`가 아직 커도 “앱 생성, dependency wiring, router mount” 영역이 식별된다.

### Lane 2: Gateway domain/service 추출

목표:
- RCA, evidence, action records, action registry, gateway state처럼 이미 분리 조짐이 있는 책임을 service 단위로 이동한다.

허용 변경:
- 순수 함수 또는 service 객체 추출
- handler는 thin wrapper로 남기는 방향의 이동
- 기존 pytest 케이스를 새 service 단위 테스트로 보강

금지:
- route URL 변경
- event stream event name 변경
- audit schema 변경

완료 조건:
- 새 service 파일은 독립 py_compile과 단위 테스트가 가능하다.

### Lane 3: Frontend state ownership 분리

목표:
- `PortalApp.tsx`, `App.tsx`, `AssistantLauncher.tsx`에서 상태 소유권과 렌더링을 분리한다.

허용 변경:
- hook 추출
- service/client call 추출
- presentational component 추출
- 기존 CSS class 유지

금지:
- CSS 대형 변경
- 사용자가 보는 layout 재디자인
- plugin/gateway contract 동시 변경

완료 조건:
- shell, state hook, data fetching, message/action rendering이 파일명만 봐도 구분된다.

### Lane 4: CSS 구조 분리

목표:
- 시각 결과를 보존한 채 CSS 영향 범위를 줄인다.

진입 조건:
- Lane 3이 통과했다.
- 화면 baseline screenshot이 있다.
- 변경 대상 화면과 검증 스크립트가 정해져 있다.

완료 조건:
- screenshot 차이가 없거나, 차이가 의도된 이유와 화면 단위 evidence가 있다.

### Lane 5: Operator/OLM 안정화

목표:
- OLM bundle/catalog/install 흐름을 리팩터링해도 OperatorHub 노출과 ConsolePlugin enable이 깨지지 않게 한다.

진입 조건:
- `task aiops:package`가 통과한다.
- 회사 서버 작업이면 `task kugnus:company:check`가 먼저 통과한다.

완료 조건:
- package, status, cluster smoke, scorecard 또는 scorecard 대체 증거가 있다.

## 파일별 리팩토링 전략

### gateway main.py

목표:
- 진입점 파일에서는 부트스트랩만 담당한다.

추출 순서:
- config / settings
- router registration
- request handlers
- domain services
- client adapters
- serialization / response mapping
- error mapping
- telemetry / logging hooks

완료 조건:
- main.py는 앱 초기화와 wiring 중심으로 남는다.
- 도메인 로직이 main.py 밖으로 이동한다.
- handler 단위 테스트가 추가된다.

### PortalApp.tsx / App.tsx

목표:
- shell, state ownership, page composition을 분리한다.

추출 순서:
- route shell
- layout shell
- shared state hooks
- data fetching hooks
- feature sections
- presentational components

완료 조건:
- 페이지 조립과 데이터/상태 로직이 분리된다.
- prop drilling 또는 hidden singleton 의존이 줄어든다.
- 주요 화면의 시각 회귀가 없다.

### AssistantLauncher.tsx

목표:
- launcher open/close state, conversation state, action state, rendering state를 분리한다.

추출 순서:
- launcher shell
- session state hook
- action dispatch service
- message rendering layer
- insight rail layer
- history panel layer
- progress timeline layer

완료 조건:
- 한 파일에서 상태/네트워크/렌더링/스타일 결정을 동시에 하지 않는다.
- message, action records, insight rail, history panel 간 경계가 명확하다.

### CSS 거대 파일

목표:
- 시각 결과를 유지한 채 구조를 분리한다.

추출 순서:
- tokens
- reset/base
- layout
- feature sections
- component-level files
- temporary compatibility layer

완료 조건:
- selector 충돌 범위가 줄어든다.
- 변경 영향 범위를 feature 단위로 예측할 수 있다.
- 기준 이미지 대비 의도치 않은 차이가 없다.

## 변경 전 체크리스트

- [ ] 이번 변경의 주 경계가 하나로 정의되었다.
- [ ] 영향을 받는 보호 자산이 식별되었다.
- [ ] 베이스라인 로그와 스크린샷을 확보했다.
- [ ] 롤백 방법을 적었다.
- [ ] 계약 변경 여부를 명시했다.

## 변경 중 체크리스트

- [ ] 먼저 seam 또는 adapter를 추가했다.
- [ ] 기존 호출 경로를 유지한 상태에서 새 구현을 연결했다.
- [ ] 테스트를 추가하거나 기존 테스트를 보강했다.
- [ ] 새로 분리한 파일의 책임을 한 줄로 설명할 수 있다.
- [ ] 기존 파일은 이전보다 더 얇아졌다.
- [ ] 예상 밖 부수효과가 생기면 즉시 범위를 줄였다.

## 변경 후 체크리스트

- [ ] 빠른 스모크 통과
- [ ] 경계 검증 통과
- [ ] 브라우저 콘솔 에러 확인
- [ ] 네트워크 에러 확인
- [ ] 스크린샷 비교 확인
- [ ] 운영 로그 비교 확인
- [ ] 문서 업데이트 완료

## 롤백 규칙

아래 중 하나라도 발생하면 즉시 롤백하거나 PR 범위를 축소한다.

- 기능 회귀 원인이 30분 내 특정되지 않음
- 플러그인 로드 실패
- 게이트웨이 응답 계약 깨짐
- 라이브 데모 핵심 플로우 실패
- OLM bundle/install smoke 실패
- 시각 회귀가 의도인지 설명 불가
- 테스트를 통과시키기 위해 의미를 바꾸는 수정이 필요함

## 장시간 리팩터링 운용 규칙

12시간 이상 이어지는 하네스에서는 “계속 움직임”보다 “안전한 상태 반복 확인”이 중요하다.

운용 단위:
- 한 cycle은 `탐색 -> 작은 변경 -> 가까운 검증 -> 기록`으로 끝난다.
- 한 cycle에서 주 경계는 하나만 둔다.
- 실패가 나오면 같은 명령을 반복하지 않고 실패 층을 먼저 분류한다.

30분마다 남길 최소 기록:
- 현재 branch / HEAD
- 마지막 변경 파일
- 마지막 통과 검증
- 마지막 실패 검증
- 다음 한 가지 행동

중단 조건:
- 같은 blocker가 세 번 반복된다.
- 실패 원인이 기능 회귀인지 테스트 기대값 문제인지 구분되지 않는다.
- 보호 자산을 수정해야만 앞으로 갈 수 있다.
- 회사 서버 publish/install/redeploy 같은 외부 영향 작업이 필요하다.

이 중단 조건은 작업 실패가 아니라 안전장치다. 멈춘 뒤에는 handoff note를 남기고 다음 cycle에서 다시 시작한다.

## 현재 gap

문서 작성 시점에 확인된 gap은 아래와 같다.

- `docs/Ver.0.3.0/SAFE_REFACTORING_HARNESS_PLAN.md`는 삭제 상태이고, 새 기준 문서는 `docs/Ver.0.3.0/refactoring-harness.md`다.
- `test_health.py`는 보호 게이트지만 현재 전체 green 상태가 아니다. 첫 리팩터링 cycle 전에 실패 목록을 baseline report로 남겨야 한다.
- CSS/화면 기준 이미지는 아직 baseline으로 고정되지 않았다.
- OLM scorecard는 Taskfile에 직접 노출된 task가 없다. Operator/OLM 변경 전 scorecard 실행 경로나 대체 evidence를 추가해야 한다.
- `evaluate-gateway-responses.py`, `evaluate-aiops-actions-e2e.py`는 live `oc`/gateway 의존 검증이다. 오프라인 quick smoke로 취급하면 안 된다.

## 기록 템플릿

### 작업 제목

### 변경 목적

### 주 경계

### 건드린 파일

### 새로 만든 seam / adapter

### 추가한 테스트

### 실행한 검증

### 발견한 회귀

### 최종 결정
- 유지
- 축소
- 롤백

### 다음 작업 후보

## 완료 정의

이번 리팩토링 웨이브는 아래가 만족되면 종료한다.

- 가장 위험한 shell 파일의 책임 분리가 끝났다.
- 보호 자산이 실제로 회귀를 잡아내는 상태다.
- 새 코드의 기본 예산과 규칙이 도입되었다.
- 이후 작업자가 “어디를 건드려야 하는지” 문서만 보고 찾을 수 있다.

종료 보고에는 반드시 아래를 포함한다.

- 현재 판단
- 핵심 근거
- 바뀐 파일
- 검증 결과
- 실패 또는 미실행 항목
- 다음 행동
