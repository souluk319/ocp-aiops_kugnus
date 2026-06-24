# Ver.0.1.1 Stage 7 OLM/Operator Readiness Report

## 목표

Stage 7는 0.1.1 기능 계약이 OLM package, CSV, CRD, AIOpsInstallation, operator status 경로에서도 재현되게 만드는 단계다.
현재 단계는 로컬 패키지/계약 검증 단계이며 공식 회사 OCP에 CatalogSource, PackageManifest, Subscription, AIOpsInstallation, ConsolePlugin, Service, Route를 생성하거나 변경하지 않는다.

## 현재 기준

- branch: `feat/v.0.1.1`
- base head before Stage 7: `7ced363`
- hard boundary: 공식 회사 서버 write/register/deploy/install 금지
- local-only default: `task kugnus:status`는 기본적으로 로컬 생성물만 검증한다.
- cluster read mode: 실제 cluster 조회는 `KOMSCO_AIOPS_STATUS_MODE=cluster`를 명시할 때만 허용한다.

## 구현 범위

- `scripts/olm-package.py`
  - CRD status schema에 `conditions`, `components`, `versionScope` 추가
  - CSV annotation에 `aiops.komsco.io/version-scope=Ver.0.1.1` 추가
  - CSV annotation/env에 0.1.1 readiness condition 목록 추가
  - operator env에 `KOMSCO_AI_OPERATOR_VERSION_SCOPE`, `KOMSCO_AI_OPERATOR_READINESS_CONDITIONS` 추가
- `komsco-ai-gateway/komsco_ai_gateway/olm_operator.py`
  - `AIOpsInstallation.status.conditions` 생성 로직 추가
  - readiness condition:
    - `TargetNamespaceReady`
    - `GatewayServiceReady`
    - `GatewayReady`
    - `ConsolePluginDeploymentReady`
    - `ConsolePluginConfigured`
    - `ServiceCABundleReady`
    - `RBACReady`
    - `ActionExecutorReady`
    - `HostDiagnosticsReady`
    - `SafetyModeReady`
  - `status.components`에 gateway, consolePlugin, serviceCA, rbac, actionExecutor, hostDiagnostics, safetyMode 상태 요약 추가
  - readiness가 모두 True면 `Ready`, 미충족 조건이 있으면 `Progressing`, reconcile 실패면 `Failed` 유지
  - read-only 기본값에서 Action Executor는 `DisabledByReadOnly`로 표시
  - Host Diagnostics는 기본 `diagnostics=true` 기준으로 readiness 대상이며, 비활성 spec에서는 `DisabledByPolicy`로 표시
  - `mode`와 capability가 모순되면 `SafetyModeReady=False`로 표시
- `scripts/kugnus-olm.sh`
  - `KOMSCO_AIOPS_STATUS_MODE=local` 기본값 추가
  - `status` 기본 동작을 local package readiness 검증으로 변경
  - cluster 조회는 `KOMSCO_AIOPS_STATUS_MODE=cluster`일 때만 실행
  - `images`는 `KOMSCO_AIOPS_APPROVE_IMAGES=komsco-ai-kugnus` 없으면 거부
  - `publish`는 `KOMSCO_AIOPS_APPROVE_PUBLISH=komsco-ai-kugnus` 없으면 거부
  - 기존 `install` 승인 guard 유지
  - package verifier가 Kugnus 이름, read-only 기본값, PNG icon SHA256, 0.1.1 readiness 계약을 검증
- `scripts/olm-deploy.sh`
  - `python3`만 요구하지 않고 `python3` 또는 `python`을 사용할 수 있게 수정
  - 기본 이름을 Kugnus 전용으로 변경
  - `catalog`, `install`, `deploy`는 `KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE=komsco-ai-kugnus` 없으면 거부
  - `status`는 local-only 기본값으로 변경
  - `wait_operands`는 mutations/diagnostics capability 기준으로 실제 생성되는 operand만 기다림
- `komsco-ai-gateway/tests/test_health.py`
  - operator status payload가 0.1.1 readiness conditions/components를 노출하는지 테스트 추가
  - Gateway rollout 미충족 시 `Progressing`과 `GatewayReady=False`로 보고하는지 테스트 추가
  - `mode=execute + mutations=false`, `mode=read-only + mutations=true` 모순 상태가 `Ready`로 보이지 않도록 테스트 추가

## 하지 않은 것

- `oc apply` 실행 없음
- `task kugnus:publish` 실행 없음
- `task kugnus:install` 실행 없음
- `task catalog:register`, `task catalog:deploy`, `task olm:deploy`, `task olm:install` 실행 없음
- 공식 회사 OCP에 CatalogSource, PackageManifest, Subscription, AIOpsInstallation 생성 없음
- 기존 `komsco-ai-console-plugin`, `lightspeed-console-plugin`, `komsco-ai`, `komsco-ai-dev` 리소스 변경 없음
- `.env`, token, kubeconfig, password 읽기/문서화/커밋 없음

## Acceptance Criteria

| 기준 | evidence | 상태 |
| --- | --- | --- |
| CSV/env/config에 Ver.0.1.1 readiness 계약 포함 | generated CSV static verification | PASS |
| CRD status에 conditions/components/versionScope 포함 | generated CRD static verification | PASS |
| Kugnus package/catalog/plugin 이름이 공용 이름과 충돌하지 않음 | generated manifest static verification | PASS |
| 기본 install spec은 read-only, mutations=false, unrestricted=false | generated install static verification | PASS |
| 기본 install spec은 diagnostics=true이며 install wait 대상과 일치 | generated install/wait static verification | PASS |
| publish/images/install은 명시 승인 없이는 실행 불가 | script guard audit | PASS |
| status 기본값은 공식 cluster 조회가 아닌 local-only | script guard audit | PASS |
| operator status가 Ready/Progressing을 readiness condition으로 판단 | local operator smoke | PASS |
| mode/capability 모순 시 Ready가 되지 않음 | local operator smoke | PASS |
| 공식 회사 서버 write 없음 | 실행 명령 목록 | PASS |

## 검증 명령

```powershell
# Python syntax
python -m py_compile scripts/olm-package.py komsco-ai-gateway/komsco_ai_gateway/olm_operator.py

# Kugnus OLM manifest generation, local only
python scripts/olm-package.py

# Generated manifest static verification
python -  # inline verifier: package/catalog/CSV/CRD/install/icon/readiness checks

# Operator readiness payload smoke
$env:PYTHONPATH='komsco-ai-gateway'
python -  # inline smoke: Ready payload and GatewayReady=False -> Progressing payload

# Guard audit
rg -n "KOMSCO_AIOPS_APPROVE_CLUSTER_WRITE|require_cluster_write_approval|require_uninstall_approval|STATUS_MODE|bool_enabled|wait_operands|komsco-ai-action-executor|kugnus:status|KOMSCO_AIOPS_STATUS_MODE" scripts/olm-deploy.sh scripts/kugnus-olm.sh Taskfile.yml

# Whitespace
git diff --check
```

## 검증 결과

| 명령 | 결과 | 비고 |
| --- | --- | --- |
| `python -m py_compile ...` | PASS | Python 문법 확인 |
| Kugnus OLM manifest generation | PASS | `komsco-aiops-kugnus-operator.v0.1.3` 생성 |
| generated manifest static verification | PASS | CSV, CRD, CatalogSource, Package, install spec, icon SHA256, readiness env/annotation, install wait guard 확인 |
| operator readiness payload smoke | PASS | Ready payload, GatewayReady=False -> Progressing, mode/capability mismatch -> Progressing 확인 |
| guard audit `rg ... scripts/olm-deploy.sh scripts/kugnus-olm.sh Taskfile.yml` | PASS | lower-level cluster write guard, local status default, capability-based wait 확인 |
| `git diff --check` | PASS | whitespace error 없음 |

## 실행하지 못한 검증과 대체 검증

| 검증 | 결과 | 대체 |
| --- | --- | --- |
| `python -m pytest komsco-ai-gateway/tests/test_health.py -q -k "olm_operator"` | Windows Python에 `pytest` 미설치: `No module named pytest` | operator readiness payload inline smoke로 핵심 계약 확인 |
| `task kugnus:package`, `task kugnus:status` | 현재 세션의 Windows PATH에 `task` 없음 | `python scripts/olm-package.py`와 generated manifest static verification 수행 |
| WSL 기반 `task` 실행 | `wsl.exe -d Ubuntu ...`가 `Wsl/Service/0x8007274c`로 실패 | 공식 OCP write 없이 Windows Python 로컬 검증으로 대체 |

## Reviewer FAIL 대응 기록

| Reviewer | 지적 | 수정 | 검증 |
| --- | --- | --- | --- |
| A Product/OLM Safety | `scripts/olm-deploy.sh`를 직접 호출하면 wrapper guard를 우회해 cluster write가 가능했고, 공용 ConsolePlugin 기본값도 살아 있었다. | lower-level `olm-deploy.sh`도 Kugnus 기본값/이름 검증/cluster write approval/local status default를 갖도록 수정. `olm-package.py`, operator 기본값도 Kugnus 전용으로 변경하고 protected plugin은 별도 승인 없이는 항상 거부. | A re-review PASS |
| B Backend/Operator Status | `mode=execute + mutations=false` 같은 모순 spec에서도 모든 condition이 True가 되어 `Ready`가 될 수 있었다. | `ActionExecutorReady`와 `SafetyModeReady`에 capability mismatch reason 추가. 모순 spec은 `Progressing`으로 떨어지게 하고 테스트 추가. | B re-review PASS |
| C Verification/Regression | generated install manifest를 직접 검증하지 않았고, read-only 기본값에서 없는 Action Executor를 무조건 기다릴 수 있었다. `task kugnus:status` 설명도 stale이었다. | install manifest 직접 검증 추가, `wait_operands`를 mutations/diagnostics capability 기준으로 조건화, Taskfile 설명 수정. Host Diagnostics 기본값은 `diagnostics=true`로 문서 수정. | generated manifest static verification |

## Reviewer Gate

| Reviewer | 관점 | 결과 | 근거 |
| --- | --- | --- | --- |
| A | Product/OLM Safety | PASS | lower-level `olm-deploy.sh`까지 cluster write approval, Kugnus defaults, protected name refusal, local status default 확인 |
| B | Backend/Operator Status | PASS | mode/capability mismatch가 `Progressing`으로 떨어지고 false readiness condition을 남김 |
| C | Verification/Regression | PASS | install wait가 capability 기반이며 local verifier가 install manifest/wait guard/Taskfile 설명까지 확인 |
