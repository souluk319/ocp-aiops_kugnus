# Ver.0.1.2 Functional Connection Report

## Ref stamp

- Branch: `feat/v.0.1.2`
- Verification base head: `82ea0359603497bd919d3fe12d9e9d78943793fb`
- Base ref: `feat/v.0.1.1` / `af895a5d2934aea8ef721d54e1d97b916afc32d6`
- Verification time: `2026-06-25T08:00:29+09:00`
- Target console route: `http://localhost:9000/aiops-kugnus`
- Company API server observed read-only: `https://api.ocp.cywell.server:6443`

## Current judgment

Ver.0.1.2 now has one connected local control-tower path:

1. WSL Gateway runs read-only on `0.0.0.0:18080`.
2. Docker local OpenShift console bridge reaches Gateway through the WSL IP endpoint.
3. `Cywell AI 관제탑` dashboard loads actual company OCP state through console proxy/UserToken.
4. Dashboard shows cluster state, anomaly summary, RCA/evidence posture, action candidates, safety contract, and operator flow.
5. Chat answers remain read-only, expose collected/missing evidence, and label Gateway fallback when Lightspeed stream fails.

This is still a local development console. It is not a company OCP install, catalog publish, subscription, or runtime deployment.

## Runtime wiring

Use these 0.1.2 tasks after reboot:

```bash
task kugnus:dev:be
```

This starts the Gateway with:

- `GATEWAY_HOST=0.0.0.0`
- `AIOPS_GATEWAY_MODE=read-only`
- `OLS_BASE_URL=https://127.0.0.1:18443`

Then:

```bash
task kugnus:dev:fe
```

This starts the local console bridge with:

- `GATEWAY_ENDPOINT=http://<current-wsl-ip>:18080`
- console URL `http://localhost:9000`

Reason: Docker console cannot reach a Gateway bound only to WSL `127.0.0.1`. The earlier failure showed `health score = -` and console proxy errors against the wrong host path. Binding Gateway to `0.0.0.0` and passing the WSL IP to the bridge restored dashboard data loading.

## Stage connection matrix

| Stage | Product path | API/contract | UI evidence | Verification evidence | Result |
| --- | --- | --- | --- | --- | --- |
| 1 Cluster overview | 관제탑 health/state cards | `/v1/aiops/overview`, `/v1/cluster/summary` | Health score `92`, API `https://api.ocp.cywell.server:6443`, version `4.20.23`, `read_only` | UI verifier: `dashboard health score is loaded from gateway data` | PASS |
| 2 Anomalies | 위험/확인 필요/주의 summary | `/v1/aiops/anomalies`, `spec.anomalies` | 위험 2, 확인 필요 16, 주의 43, total 61 | UI verifier checks top 3 anomaly cards with priority/target/cause/evidence/next check | PASS |
| 3 RCA/evidence | Chat answer + RCA Context JSON | `ToolPlan`, `RcaContext`, evidence footer | `RCA Context JSON` includes digest/contextId/collected/missing/failed refs | UI verifier checks evidence footer, trace fields, fallback labeling | PASS |
| 4 Action candidates | Read-only action candidate board | `/v1/aiops/action-candidates`, `mutationSubmitted=false` | `제안만 함 / 실행 안 함`, approval required, forbidden actions | UI verifier checks risk/precheck/impact/approval/verification | PASS |
| 5 Operator dashboard UX | Operator flow and polished assistant shell | Dashboard route + assistant overlay | Six-step operator flow before metrics; no duplicate FAB; sidebar closed by default | UI verifier 105 checks, screenshots saved | PASS |
| 6 Verification automation | Local verification task | `task kugnus:stage6:verify` | Local route and UI verified by CDP | pytest/build/evaluator/API smoke/OCP read-only/UI verifier | PASS |

## Verification results

| Command | Result | Evidence |
| --- | --- | --- |
| `task kugnus:stage6:verify` | PASS | Completed end-to-end after environment fixes |
| `node --check ./scripts/verify-kugnus-ui.mjs` | PASS | Stage 6 task static checks |
| `python -m pytest komsco-ai-gateway -q` | PASS | `169 passed, 2 warnings in 2.80s` |
| `cd komsco-ai-console-plugin && corepack yarn build` | PASS | `webpack 5.105.4 compiled successfully in 64606 ms` |
| `python scripts/evaluate-aiops-scenarios.py --scenarios evals/aiops-scenarios --report docs/Ver.0.1.2/aiops-scenario-evaluation-report.json` | PASS | `scenarioCount=5`, `passed=5`, `failed=0`, `negativeControlsPassed=true` |
| `curl http://127.0.0.1:18080/healthz` | PASS | `{"status":"ok"}` |
| `curl -i http://127.0.0.1:18080/v1/aiops/overview` without token | PASS expected auth guard | `401 Missing OpenShift bearer token` |
| `oc whoami && oc whoami --show-server` | PASS read-only context | `admin`, `https://api.ocp.cywell.server:6443` |
| `oc get consoleplugin komsco-ai-console-plugin lightspeed-console-plugin --no-headers` | PASS read-only snapshot | `komsco-ai-console-plugin`, `lightspeed-console-plugin` still present |
| `task kugnus:ui:verify` | PASS | `ok=true`, `checked=105`, `failed=[]` |

## Scenario evaluator contract

The first evaluator run failed: `passed=2`, `failed=3`.

Root cause: the Pod RCA scenario JSON expected `metric` as a missing evidence type, while the current Stage 3/3-2 ToolPlan/RCA contract records missing `event`, `pod_log`, `clusteroperator`, and `runbook` for Pod RCA when only pod status evidence is supplied.

Fix: update the three Pod RCA scenario files so they no longer claim Event evidence was collected and now require the actual missing evidence types.

Final report path:

```text
docs/Ver.0.1.2/aiops-scenario-evaluation-report.json
```

## OCP immutability

No install/deploy/mutation task was executed for Stage 6.

Not executed:

- `oc apply`
- `oc delete`
- `oc patch`
- `oc scale`
- `oc exec`
- `task catalog:deploy`
- `task olm:install`
- `task kugnus:install`

Read-only OCP commands used:

- `oc whoami`
- `oc whoami --show-server`
- `oc get consoleplugin ...`

## Known gaps

- Direct Gateway API calls without console UserToken correctly return `401`; authenticated API path is verified through local console proxy and UI verifier.
- Lightspeed stream currently reports `failed`, and the UI correctly labels `Gateway fallback active`. This is not hidden as success.
- WSL Git sees existing Ver.0.1.1 generated JSON reports as modified due line-ending noise; Windows Git does not. Stage 6 verification scopes `git diff --check` to 0.1.2 target files to avoid mixing old generated-report hygiene into this stage.
- Windows `netsh portproxy` for `18080` requires Administrator. The working 0.1.2 path avoids it by using the WSL IP endpoint in `task kugnus:dev:fe`.
