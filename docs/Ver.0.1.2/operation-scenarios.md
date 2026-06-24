# Ver.0.1.2 Operation Scenarios

## Purpose

These scenarios describe how an operator should use the local Cywell AI control tower and what evidence must appear before calling a flow complete. All scenarios are read-only unless a later version explicitly adds an approved execution path.

## Scenario 1: Reboot recovery

Goal: restore local development after Windows/WSL/Docker restart.

Steps:

1. Confirm `oc whoami` and `oc whoami --show-server`.
2. Confirm Docker is reachable from WSL.
3. Run `task kugnus:dev:be`.
4. Run `task kugnus:dev:fe`.
5. Open `http://localhost:9000/aiops-kugnus`.

Pass:

- Gateway health returns `{"status":"ok"}`.
- Console bridge log shows `Gateway proxy endpoint: http://<wsl-ip>:18080`.
- Dashboard health score is numeric, not `-`.

Fail:

- Gateway only listens on `127.0.0.1:18080`.
- Console bridge points to `host.docker.internal:18080` and dashboard cards stay empty.

## Scenario 2: First screen cluster status

Goal: prove the control tower is not just OpenShift default dashboard chrome.

Expected evidence:

- Health score loaded from Gateway data.
- API server shown as `https://api.ocp.cywell.server:6443`.
- OpenShift version shown.
- Safety mode shown as `read_only`.
- Lightspeed status shown as either `not_started`, `failed`, or `Gateway fallback active`.

Pass:

- UI verifier check `dashboard health score is loaded from gateway data` passes.
- Data source failures are shown as `error`, `partial`, `unavailable`, or missing reason, not hidden as normal.

## Scenario 3: CrashLoopBackOff triage

Trigger: anomaly card shows `CrashLoopBackOff`.

Operator flow:

1. Read severity and priority.
2. Check namespace/kind/name.
3. Read cause candidate.
4. Read evidence line.
5. Use the next check command as a manual read-only follow-up.

Expected current example:

- `komsco-ai-dev/Pod/aiops-scenario-1-crashloop-...`
- Evidence includes waiting reason, restart count, and event message.
- Next check suggests logs/describe, but no command is executed by the product.

Pass:

- RCA does not claim root cause is final without pod log/event/metric confirmation.
- Action candidate remains `제안만 함 / 실행 안 함`.

## Scenario 4: ImagePullBackOff triage

Trigger: anomaly card shows `ImagePullBackOff`.

Operator flow:

1. Confirm image/pull secret/registry candidate cause.
2. Confirm namespace and pod.
3. Read next check command.
4. If remediation is needed, treat it as a future approval path, not current execution.

Pass:

- UI exposes registry/pull-secret angle.
- No `oc patch secret`, pod recreation, or delete action is submitted.

## Scenario 5: Recent restart increase

Trigger: anomaly card shows restart increase.

Expected evidence:

- Metric increase value.
- Container name.
- Statement that current CrashLoop vs recovered history must be confirmed from Pod status and lastState.

Pass:

- The system does not treat historical restart increase as a guaranteed current outage.
- Next check remains read-only.

## Scenario 6: RCA chat with insufficient evidence

Trigger: ask a broad status or RCA question.

Expected evidence:

- ToolPlan is generated before answer.
- RCA Context has `digest`, `contextId`, collected refs, missing refs.
- Evidence footer separates collected and missing evidence.
- If Lightspeed stream fails, answer is labelled `Gateway fallback`.

Pass:

- Answer includes what is known and what is not confirmed.
- Token-like values are redacted in footer/copy text.

## Scenario 7: Direct Pod inventory answer

Trigger: ask a concrete pod count/status question for a visible deployment.

Expected evidence:

- Answer can use direct Kubernetes API data.
- Response is table-like and compact.
- It states no execution/change was performed.

Pass:

- UI verifier confirms direct Gateway answer is not labelled as Lightspeed fallback.
- Evidence footer includes collected `pod_status`.

## Scenario 8: Read-only action candidate review

Trigger: inspect action candidate board after anomalies load.

Expected evidence:

- Top three candidates only.
- Risk, target, precheck, expected impact, approval, verification.
- `mutation disabled`.
- Forbidden actions: `apply`, `delete`, `patch`, `scale`, `exec`.

Pass:

- Candidate card cannot be mistaken for execution.
- No action executor URL configured is shown as a blocker.

## Scenario 9: Monitoring partial/error handling

Trigger: Prometheus/Thanos or metric source is unavailable, partial, or capped.

Expected behavior:

- Dashboard source board shows status and reason.
- RCA answer must not say metrics prove a cause when metric evidence is missing.
- Action candidate must keep verification step explicit.

Pass:

- Missing/partial is visible in UI/API evidence.
- No fake `0` or `정상` is substituted for unavailable data.

## Scenario 10: Existing company resources untouched

Trigger: before/after stage validation.

Read-only checks:

```bash
oc get consoleplugin komsco-ai-console-plugin lightspeed-console-plugin --no-headers
```

Pass:

- Existing company plugin names remain.
- No install/deploy/mutation commands were run.

Fail:

- Any Stage 6 workflow runs `oc apply/delete/patch/scale/exec` or install/deploy tasks.

## Scenario 11: UI control regression

Trigger: run `task kugnus:ui:verify`.

Expected coverage:

- Dashboard route root.
- No duplicate floating assistant FAB.
- Header alignment and KOMSCO logo.
- Sidebar default closed and external drawer behavior.
- Fullscreen and resize lock/unlock.
- Composer plus menu, attachment, Ask/Troubleshooting mode, stop button.
- Evidence footer, scroll lock, fallback label.

Pass:

- `checked=105`, `failed=[]`.

## Scenario 12: Stage 6 full verification

Trigger:

```bash
task kugnus:stage6:verify
```

Pass:

- Gateway tests pass.
- Frontend build passes.
- Offline AIOps scenarios pass.
- API smoke shows health OK and auth guard OK.
- UI verifier passes.

Blocked:

- Local console not running.
- Gateway bound only to localhost.
- Docker cannot reach WSL Gateway.
- Chrome CDP not running and verifier cannot autostart Chrome.
