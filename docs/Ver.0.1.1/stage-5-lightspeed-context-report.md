# Ver.0.1.1 Stage 5 Lightspeed Context Injection Report

## 목표

Stage 5는 Gateway가 OpenShift Lightspeed로 넘기는 요청에 Tool Plan, RCA Context, evidence summary, safety contract를 구조화된 `gateway_context`로 붙이고, 실패 시 Gateway fallback임을 사용자가 화면에서 구분할 수 있게 만드는 단계다.
공식 회사 OCP에 등록, 설치, 배포하지 않는다.

## 구현 범위

- `komsco-ai-gateway/komsco_ai_gateway/main.py`
  - `build_ols_gateway_context` 추가
  - `build_ols_payload`에 `gateway_context` schema 전달
  - OLS stream 상태를 `OLS_STREAM_STATUS`로 기록
  - stream 시작/성공/실패/not configured/dev echo 상태와 `lastContextDigest` 기록
  - chat stream `run_status`, `lightspeed_stream` error, fallback text event에 `gatewayContextDigest` 연결
- `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py`
  - runtime safety contract의 `lightspeedStatus`를 실제 stream 상태 기반으로 확장
  - stale placeholder `not_probed_by_status_endpoint`를 기본 `not_started`로 교체
- `komsco-ai-gateway/tests/test_health.py`
  - OLS payload에 schema 기반 `GatewayContext`가 들어가는지 검증
  - token/Authorization 문자열이 payload에 남지 않는지 검증
  - OLS failure 시 stream/status/fallback event에 동일한 context digest가 남는지 검증
- `komsco-ai-console-plugin/src/services/aiGateway.ts`
  - `lightspeedStatus`, stream event 타입 확장
- `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx`
  - stream event의 Lightspeed status를 header 상태에 반영
  - fallback answer에 `Gateway fallback` badge 표시
- `komsco-ai-console-plugin/src/components/assistant.css`
  - fallback badge 스타일 추가
- `komsco-ai-console-plugin/src/pages/AiopsPages.tsx`
  - Lightspeed panel에 stream status, fallback active, gateway context digest, last error 표시
- `scripts/verify-kugnus-ui.mjs`
  - stale not-probed placeholder 금지 검증
  - OLS fallback 질문을 별도로 실행해 fallback badge/header 상태 검증

## 하지 않은 것

- `oc apply` 실행 없음
- `helm install/upgrade` 실행 없음
- `task kugnus:publish`, `task kugnus:install`, `task catalog:register` 실행 없음
- `CatalogSource`, `PackageManifest`, `Subscription`, `AIOpsInstallation` 생성 없음
- 공식 회사 OCP namespace, ConsolePlugin, Lightspeed, 기존 KOMSCO 챗봇 변경 없음
- LLM endpoint, token, kubeconfig, `.env` 값 문서화 또는 커밋 없음

## Acceptance Criteria

| 기준 | evidence | 상태 |
| --- | --- | --- |
| OLS payload에 구조화된 `gateway_context` 포함 | request builder pytest | PASS |
| context가 prompt 문자열에만 섞이지 않고 schema로 추적됨 | `GatewayContext.kind`, digest pytest | PASS |
| Tool Plan, RCA Context, evidence summary, missing evidence, safety contract 포함 | payload pytest | PASS |
| OLS 실패 시 동일 context digest가 stream/status/fallback event에 남음 | chat stream pytest | PASS |
| token/secret이 OLS payload에 남지 않음 | redaction pytest | PASS |
| `streamProbe`가 `not_probed_by_status_endpoint`로 고정되지 않음 | status/UI verifier | PASS |
| OLS 실패 fallback임을 UI에서 구분 가능 | assistant badge/header verifier | PASS |
| 공식 회사 서버 쓰기 없음 | 실행 명령 목록 | PASS |

## 검증 명령

```bash
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py

# Windows 임시 venv 사용. WSL 서비스가 Wsl/Service/0x8007274c로 실패했기 때문에 로컬 검증만 Windows venv로 수행.
python -m venv %TEMP%/ocp-aiops-pytest-venv
%TEMP%/ocp-aiops-pytest-venv/Scripts/python.exe -m pip install -r komsco-ai-gateway/requirements-dev.txt
%TEMP%/ocp-aiops-pytest-venv/Scripts/python.exe -m pytest tests/test_health.py -k "runtime_safety_contract_defaults_to_read_only or build_ols_payload_includes_schema_gateway_context_without_secrets or chat_stream_marks_lightspeed_context_digest_on_gateway_fallback"

cd komsco-ai-console-plugin
corepack yarn build

KUGNUS_UI_URL=http://localhost:9000/aiops-kugnus node scripts/verify-kugnus-ui.mjs
```

## 검증 결과

| 명령 | 결과 | 비고 |
| --- | --- | --- |
| `python -m py_compile ...` | PASS | Python 문법 확인 |
| targeted `pytest` 5건 | PASS | 5 passed, 146 deselected |
| full `pytest tests/test_health.py` on Windows temp venv | PARTIAL | 146 passed, 3 failed. 실패는 Windows에서 Linux 전용 `/bin/bash`, `os.statvfs` 경로를 실행한 환경 차이이며 Stage 5 변경 실패가 아님 |
| `corepack yarn build` | PASS | vendor chunk size warning only |
| `node scripts/verify-kugnus-ui.mjs` with `/aiops-kugnus` | PASS | 85 checked, 0 failed |
| `git diff --check` | PASS | whitespace error 없음 |

## Runtime Note

첫 UI verifier 실패 원인은 코드가 아니라 로컬 Gateway `127.0.0.1:18080`이 이전 프로세스를 계속 물고 있던 stale runtime이었다.
PID `29636`의 로컬 uvicorn만 종료하고, Windows 임시 venv의 uvicorn으로 `18080`을 재기동했다.
이 작업은 로컬 개발 서버 교체이며 공식 회사 OCP에는 어떤 리소스도 쓰지 않았다.

## Reviewer FAIL 대응 기록

| Reviewer | 지적 | 수정 | 검증 |
| --- | --- | --- | --- |
| B Backend/Safety | OLS upstream error body가 token/Authorization 값을 포함할 경우 SSE/detail/status로 노출될 수 있었다. | SSE 직렬화에 `redact_sensitive`를 적용하고, OLS error/detail/status reason을 `safe_error_text`/`safe_exception_text`로 제한/마스킹했다. | targeted pytest 5 passed |
| B Backend/Safety | OLS stream이 성공 종료됐지만 답변 텍스트가 없으면 fallback text는 나가는데 status는 succeeded로 남을 수 있었다. | `not emitted_answer_text` fallback 직전에 `OLS_STREAM_STATUS`를 `failed + fallbackActive`로 갱신했다. | `test_chat_stream_marks_empty_ols_success_as_fallback_status` PASS |
| C Frontend/UX | verifier가 Gateway 직접 답변 경로가 fallback으로 오표시되지 않는지 확인하지 않았다. | direct pod-count 답변에는 fallback badge/header가 없음을 검증하고, OLS를 타지 않은 direct completion은 header fallback state를 해제한다. | UI verifier 85 checked 0 failed |
| C Frontend/UX | fallback positive verifier가 OLS failure 환경에 의존했다. | `DEV_ECHO`/`OLS_BASE_URL` 미설정도 Gateway fallback event metadata를 붙이도록 보강하고, fallback 검증을 dashboard RCA 검증 이후로 분리했다. | UI verifier 85 checked 0 failed |

## Reviewer Gate

| Reviewer | 관점 | 결과 | 근거 |
| --- | --- | --- | --- |
| A | Product/Requirements | PASS | Stage 5 local-only boundary, structured context, fallback UI 구분 확인 |
| B | Backend/Safety | PASS | secret-bearing OLS error redaction, empty OLS success fallback status 재검수 PASS |
| C | Frontend/UX | PASS | direct answer negative check, fallback badge/header, verifier order 재검수 PASS |
