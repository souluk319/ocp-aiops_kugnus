# Ver.0.1.2 Stage 6 Review - Verification Automation

## Ref stamp

- Branch: `feat/v.0.1.2`
- Base head before Stage 6 commit: `82ea0359603497bd919d3fe12d9e9d78943793fb`
- Base ref: `feat/v.0.1.1` / `af895a5d2934aea8ef721d54e1d97b916afc32d6`
- Verification time: `2026-06-25T08:00:29+09:00`
- Runtime mode: local development console, company OCP read-only observation

## Goal

Stage 6 locks Ver.0.1.2 as a verified local AIOps control tower instead of a collection of disconnected feature claims.

Completion requires:

- One reproducible verification task.
- Functional connection report.
- Operational scenarios.
- Pass/fail evidence.
- Read-only/OCP immutability statement.
- Known failures recorded by actual cause.

## Implemented changes

### Task automation

Added:

- `scripts/kugnus-stage6-verify.sh`
- `task kugnus:stage6:verify`
- `task kugnus:dev:be`
- `task kugnus:dev:fe`

`kugnus:stage6:verify` runs:

- ref stamp
- scoped `git diff --check`
- `node --check`
- gateway pytest
- frontend build
- offline scenario evaluator
- local API smoke
- OCP read-only snapshot
- UI verifier

`kugnus:dev:be` and `kugnus:dev:fe` lock the WSL/Docker local-console wiring that made the dashboard load real Gateway data.

### UI verifier hardening

- Chrome CDP fetch failures now include host/port/path in the error.
- Windows Chrome autostart now binds CDP to `127.0.0.1` instead of `0.0.0.0`.
- Top-level verifier crash output includes a short stack preview.

### Scenario evaluator contract

Updated Pod RCA scenario files:

- `evals/aiops-scenarios/01-pod-restart-rca.json`
- `evals/aiops-scenarios/02-crashloopbackoff.json`
- `evals/aiops-scenarios/03-imagepullbackoff.json`

Reason: the previous expected missing evidence list did not match the Stage 3/3-2 ToolPlan/RCA contract. The corrected scenarios now expect missing `event`, `pod_log`, `clusteroperator`, and `runbook` when only Pod status evidence is supplied.

## Review loop

### Reviewer A - Product/requirements

Result: PASS.

- The connection report maps Stage 1-5 into one operator flow.
- The dashboard is separated from the default OpenShift dashboard.
- The scenarios describe actual operational use, not only UI clicks.

### Reviewer B - Backend/safety

Result: PASS.

- Gateway pytest passed.
- Scenario evaluator passed with negative hallucination control.
- Direct unauthenticated Gateway API returned `401`, which is expected.
- Only read-only `oc` checks were used.

### Reviewer C - UI/UX

Result: PASS.

- UI verifier passed 105 checks.
- Dashboard data loaded from Gateway.
- Anomaly/action/RCA/evidence/fallback surfaces are visible.
- Header/sidebar/fullscreen/composer regressions remain covered.

### Reviewer K - 김성욱봇

Result: PASS after fixes.

Initial fails:

- Scenario evaluator was `2 passed / 3 failed`.
- Dashboard health score was `-` because Docker console could not reach Gateway.
- Chrome CDP failure was reported too vaguely as `fetch failed`.
- Stage verification was vulnerable to unrelated 0.1.1 generated JSON CRLF noise in WSL Git.

Fixes:

- Corrected scenario contracts.
- Restarted Gateway on `0.0.0.0:18080`.
- Restarted console bridge with `GATEWAY_ENDPOINT=http://<wsl-ip>:18080`.
- Hardened verifier CDP diagnostics.
- Scoped Stage 6 diff check to Stage 6 target paths.

## Verification evidence

| Check | Result | Evidence |
| --- | --- | --- |
| `task kugnus:stage6:verify` | PASS | Final task completed |
| Gateway tests | PASS | `169 passed, 2 warnings in 2.80s` |
| Frontend build | PASS | `webpack 5.105.4 compiled successfully in 64606 ms` |
| Offline scenarios | PASS | `scenarioCount=5`, `passed=5`, `failed=0`, `negativeControlsPassed=true` |
| Health smoke | PASS | `{"status":"ok"}` |
| Direct overview without token | PASS expected guard | `401 Missing OpenShift bearer token` |
| OCP identity | PASS | `admin`, `https://api.ocp.cywell.server:6443` |
| Existing ConsolePlugins read-only snapshot | PASS | `komsco-ai-console-plugin`, `lightspeed-console-plugin` listed |
| UI verifier | PASS | `ok=true`, `checked=105`, `failed=[]` |

## Safety statement

Stage 6 did not execute install, deploy, or mutation commands against company OCP.

Forbidden commands/tasks not run:

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

## Known gaps and follow-up

- Lightspeed stream currently fails and Gateway fallback answers from local evidence. This is visible in the UI and is acceptable for Stage 6 because it is not hidden.
- Authenticated direct `curl /v1/aiops/*` was not run with a raw token in the script. The authenticated path is verified through console proxy/UserToken via UI verifier.
- WSL Git sees two Ver.0.1.1 generated JSON reports as modified because of line-ending noise. They are not part of Stage 6 and must not be staged for this commit.
- Prometheus/Thanos is verified through overview/UI source status and metric-backed anomaly evidence. If a future stage requires direct query proof, add a token-safe smoke command that does not print credentials.

## Completion judgment

Stage 6 is complete.

The product now has:

- Local recovery tasks.
- Reproducible verification task.
- Functional connection report.
- Operational scenarios.
- Scenario evaluator report.
- UI verifier pass.
- Explicit read-only boundary.
