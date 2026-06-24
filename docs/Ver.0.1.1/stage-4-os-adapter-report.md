# Ver.0.1.1 Stage 4 OS-aware Adapter Report

## 목표

Stage 4는 OpenShift/Linux/Windows adapter capability와 disabled/planned reason을 runtime status와 dashboard에 노출하는 단계다.
공식 회사 OCP에 등록, 설치, 배포하지 않는다.

## 구현 범위

- `komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py`
  - `build_adapter_registry` 추가
  - `resolve_tool_plan_adapters` 추가
  - OpenShift adapter supported tools 정의
  - Linux diagnostics gate disabled reason/next action 정의
  - Windows planned status/requirements 정의
  - Tool Plan에 `adapter_resolution` 연결
  - runtime safety contract에 `adapterStatus`와 `toolPlanStatus.adapterResolution` 연결
- `komsco-ai-gateway/komsco_ai_gateway/main.py`
  - diagnostics controller configured 여부를 safety contract에 전달
- `komsco-ai-console-plugin/src/services/aiGateway.ts`
  - adapter status/tool resolution 타입 확장
- `komsco-ai-console-plugin/src/pages/AiopsPages.tsx`
  - OS-aware adapters panel에 supported tools, disabled reason, next action 표시
- `komsco-ai-console-plugin/src/pages/aiops-pages.css`
  - adapter panel 정보 표시 레이아웃 보강
- `scripts/verify-kugnus-ui.mjs`
  - dashboard adapter panel 검증 추가
- `komsco-ai-gateway/tests/test_health.py`
  - adapter registry/status/tool resolution 테스트 추가

## 하지 않은 것

- `oc apply` 실행 없음
- `helm install/upgrade` 실행 없음
- `task kugnus:publish`, `task kugnus:install`, `task catalog:register` 실행 없음
- Linux diagnostics job 실행 없음
- Windows collector 또는 credential bridge 구현 없음
- 회사 OCP 공용 plugin/namespace 변경 없음

## Acceptance Criteria

| 기준 | evidence | 상태 |
| --- | --- | --- |
| `/v1/aiops/status`에 adapter별 supported tools, status, reason 포함 | status API pytest | PASS |
| OpenShift capability 최소 3종 resolve | Tool Plan pytest | PASS |
| Linux diagnostics gate와 disabled reason 표시 | status API + dashboard verifier | PASS |
| Windows planned/mock status와 필요 조건 표시 | status API + dashboard verifier | PASS |
| Tool Plan step이 adapter capability로 resolve되고 실패/비대상 reason이 남음 | `adapter_resolution` pytest | PASS |
| Dashboard가 adapter 상태, disabled reason, next action 표시 | UI verifier | PASS |
| 공식 회사 서버에 쓰기 없음 | 실행 명령 목록 | PASS |

## 검증 명령

```bash
python -m py_compile komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py komsco-ai-gateway/komsco_ai_gateway/main.py
py -3.13 -m pytest komsco-ai-gateway/tests/test_health.py -q -k "adapter_registry_resolves_openshift_tool_plan_steps_and_marks_disabled_adapters or runtime_safety_contract_defaults_to_read_only or runtime_tool_plan_generates_read_only_pod_restart_rca or runtime_safety_contract_exposes_latest_tool_plan or aiops_status_api_exposes_runtime_capabilities_and_recent_records"
cd komsco-ai-console-plugin && corepack yarn build
KUGNUS_UI_URL=http://localhost:9000/dashboards node ./scripts/verify-kugnus-ui.mjs
```

## 검증 결과

| 명령 | 결과 | 비고 |
| --- | --- | --- |
| `python -m py_compile komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py komsco-ai-gateway/komsco_ai_gateway/main.py` | PASS | Python 문법 확인 |
| `py -3.13 -m pytest komsco-ai-gateway/tests/test_health.py -q -k "adapter_registry_resolves_openshift_tool_plan_steps_and_marks_disabled_adapters or runtime_safety_contract_defaults_to_read_only or runtime_tool_plan_generates_read_only_pod_restart_rca or runtime_safety_contract_exposes_latest_tool_plan or aiops_status_api_exposes_runtime_capabilities_and_recent_records"` | PASS | 5 passed, 142 deselected |
| `corepack yarn build` in `komsco-ai-console-plugin` | PASS | vendor chunk size warning only |
| `KUGNUS_UI_URL=http://localhost:9000/dashboards node ./scripts/verify-kugnus-ui.mjs` | PASS | 62 checked, 0 failed. Overlay route regression 확인 |
| `KUGNUS_UI_URL=http://localhost:9000/aiops-kugnus node ./scripts/verify-kugnus-ui.mjs` | PASS | 82 checked, 0 failed. Dashboard adapter panel 확인 |

## Runtime Note

UI verifier가 처음 `/aiops-kugnus`에서 실패했을 때 원인은 코드가 아니라 local Gateway 18080이 reload 없이 old process를 물고 있던 stale runtime이었다.
로컬 Windows uvicorn 프로세스만 재시작했고, 공식 회사 OCP에는 쓰기 작업을 하지 않았다.

## Reviewer FAIL 대응 기록

| Reviewer | 지적 | 수정 | 검증 |
| --- | --- | --- | --- |
| C Frontend/UX | Windows planned requirements가 backend/type에는 있지만 dashboard에 표시되지 않았고, verifier도 Linux next action/Windows requirements를 확인하지 않았다. | AdapterBoard에 `requirements` 목록을 표시하고, verifier가 `Enable diagnostics`, `Windows node agent`, `read-only event log credential`, `network path from Gateway`까지 확인하도록 강화했다. | `corepack yarn build` PASS, `/aiops-kugnus` UI verifier 82 checked 0 failed |

## Reviewer Gate

| Reviewer | 관점 | 결과 | 근거 |
| --- | --- | --- | --- |
| A | Product/Requirements | PASS | Stage 4 local-only boundary, adapter status/Tool Plan resolution/dashboard traceability 확인 |
| B | Backend/Safety | PASS | read-only boundary, disabled/planned semantics, status API/tests 확인 |
| C | Frontend/UX | PASS | requirements 표시 누락 fail 대응 후 dashboard/verifier PASS |
