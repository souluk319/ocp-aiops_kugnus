# Ver.0.1.2 Stage 5 Review - 운영자 대시보드 UX

## Ref stamp

- Branch: `feat/v.0.1.2`
- Base HEAD before Stage 5: `a8a613e`
- Scope: 운영자용 dashboard UX, Stage 5 verifier hardening
- OCP mutation/install/deploy: 실행하지 않음

## 목표

Stage 5의 목표는 OpenShift 기본 대시보드와 Cywell AI 관제탑의 역할을 분리하고, 운영자가 한 화면에서 현재 상태와 다음 행동 흐름을 읽을 수 있게 만드는 것이다.

완료 기준은 다음으로 잠근다.

- `관제탑 -> 이상 징후 -> RCA 근거 -> 조치 후보 -> 감사/대화 -> 안전 정책` 흐름이 한 줄 요약으로 보여야 한다.
- 아직 수집하지 못한 값은 `0건`, `disabled`처럼 확정값으로 보이면 안 된다.
- 좌측 navigation은 페이지 성격에 맞게 `챗봇`이 아니라 `관제탑`으로 표시한다.
- 중요한 운영 문구는 ellipsis로 잘리지 않아야 한다.
- verifier는 stale tab이나 Chrome target hang을 성공으로 숨기면 안 된다.

## 구현 내용

### Frontend

- 대시보드 상단에 `운영 흐름` 보드를 추가했다.
- 보드 항목:
  - 클러스터 상태
  - 이상 징후
  - RCA 근거
  - 조치 후보
  - 감사·대화
  - 안전 정책
- `overview pending`, `waiting_for_question`, `status pending` 같은 내부 문자열을 운영자용 한국어 상태로 바꿨다.
- 로딩 중에도 대시보드 children과 embedded assistant shell을 계속 렌더한다.
  - 기존 문제: Gateway 응답이 지연되면 `PageShell`이 children 전체를 숨겨 챗봇이 사라진 것처럼 보였다.
  - 변경 후: 초기 수집 배너는 표시하지만 관제탑/챗봇 shell은 유지한다.
- `console-extensions.json`의 `/aiops-kugnus` navigation 이름을 `챗봇`에서 `관제탑`으로 바꿨다.
- 운영 흐름, 이상 징후, 조치 후보 제목의 ellipsis를 제거하고 줄바꿈 가능하게 수정했다.

### Verifier

- `KUGNUS_UI_VERIFY_MODE`를 추가했다.
  - `/aiops-kugnus`는 dashboard mode로 판단한다.
  - dashboard mode에서는 `.komsco-ai-page`를 초기 root로 검증한다.
- fresh dashboard target이 실패했을 때 stale tab으로 성공 처리하지 않도록 막았다.
- CDP console/runtime/network diagnostics를 수집한다.
- CDP command timeout을 추가해 Chrome target hang이 무한 대기로 남지 않게 했다.
- Stage 5 검증을 추가했다.
  - 운영 흐름 보드가 overview와 metrics 사이에 있는지 확인
  - 6개 항목 label 확인
  - 내부 pending 문자열 노출 금지
  - 핵심 운영 문구 clipping 금지
- 챗봇 응답 검증 기준을 질문 유형에 맞게 수정했다.
  - RCA 질문은 RCA 보고서 구조를 요구한다.
  - `파드 몇 개?` 같은 상태 질의는 표 기반 직접 답변과 read-only 고지를 pass로 본다.

## Reviewer 결과

### Reviewer A - Visual/Product polish

초안 판단은 fail이었다.

- null/loading 상태가 `총 0건`, `감사 0건`, `mutation disabled`처럼 확정값으로 보였다.
- `overview pending`, `waiting_for_question`, `status pending`이 그대로 노출됐다.
- 첫 navigation item이 `챗봇`이라 실제 dashboard route와 맞지 않았다.
- 중요한 운영 텍스트가 ellipsis로 잘릴 수 있었다.

반영:

- 미수집 상태는 `수집 중`, `상태 확인 중`, `정책 확인 중`으로 분리했다.
- navigation label을 `관제탑`으로 변경했다.
- 운영 흐름/이상 징후/조치 후보 제목은 줄바꿈 가능하게 수정했다.

### Reviewer B - Verification hardening

초안 판단은 fail이었다.

- fresh target이 실패해도 기존 탭으로 recover하면 dashboard 검증이 성공처럼 보일 수 있었다.
- `/dashboards` overlay 검증과 `/aiops-kugnus` dashboard 검증이 섞일 수 있었다.
- Chrome/CDP hang이 원인 없이 `fetch failed` 또는 무출력으로 남을 수 있었다.

반영:

- dashboard mode에서는 fresh `/aiops-kugnus` target을 반드시 검증한다.
- CDP diagnostics와 command timeout을 추가했다.
- root 조건을 route 성격에 맞게 분리했다.

### Reviewer C - OpenShift product fit

최종 기준:

- OpenShift 기본 대시보드와 Cywell AI 관제탑이 헷갈리면 fail.
- console navigation이 페이지 의미와 다르면 fail.
- read-only 관측 화면에서 실행 가능한 것처럼 보이면 fail.

현재 판정:

- 관제탑 route와 navigation 의미 정리: pass
- read-only 조치 후보와 안전 정책 표기: pass
- OpenShift 콘솔 톤 유지: pass

### Reviewer K - 김성욱봇

최종 빠꾸 기준:

- 가짜 0건으로 운영자를 속이면 fail.
- backend hang 때문에 챗봇이 사라지면 fail.
- verifier가 실패 원인을 숨기면 fail.
- 질문에 맞지 않는 답변 형식을 강요하면 fail.

현재 판정:

- 로딩 중 shell 유지: pass
- verifier 105 checks: pass
- 상태 질의 답변 검증 기준 보정: pass

## 검증 결과

- `node --check scripts/verify-kugnus-ui.mjs`: pass
- `git diff --check`: pass
- `cd komsco-ai-console-plugin && corepack yarn build`: pass
- `task kugnus:ui:verify`: pass
  - checked: `105`
  - failed: `0`
  - URL: `http://localhost:9000/aiops-kugnus`

## 실행 중 발견한 운영 이슈

- 기존 backend dev server가 hang 상태였다.
  - 증상: `curl http://127.0.0.1:18080/healthz` timeout
  - UI 증상: `.komsco-ai-page`는 있으나 children이 hidden이라 assistant가 없는 것처럼 보임
  - 조치: 기존 local `task be:dev` 프로세스를 종료하고 read-only mode로 재기동
- 직접 curl은 token 없이 호출하면 `401 Missing OpenShift bearer token`이 정상이다.
  - console proxy를 통한 요청은 UserToken이 붙어 정상 동작한다.
- Lightspeed stream은 상황에 따라 `failed`가 될 수 있으며, 이 경우 Gateway fallback이 명시된다.

## 완료 판단

Stage 5는 pass로 본다.

남은 Ver.0.1.2 큰 흐름은 Stage 6 운영 시나리오/기능 연결 리포트 작성과 최종 통합 검수다.
