# v0.2.5 AIOps for OCP Reference Inventory

## Ref Stamp

| Item | Value |
| --- | --- |
| Current repo branch | `feature/v0.2.5-aiops-for-ocp-port` |
| Current repo baseline | `b5fd01f` |
| Reference repo | `/home/kugnus/cywell/AIOps-Ref/aiops-ocp` |
| Reference branch | `dev` |
| Reference HEAD | `a7bd16b` |
| Product name | `AIOps for OCP` |

## Classification

| Area | Reference path | Current repo status | Decision | Notes |
| --- | --- | --- | --- | --- |
| Standalone portal package | `komsco-ai-portal/` | Missing | `copy` | Add as a separate package. Do not delete console plugin standalone code in this change. |
| Portal Vite proxy | `komsco-ai-portal/vite.config.ts` | Missing | `copy` | Keep `/v1` proxy to `AIOPS_GATEWAY_ORIGIN`, default `http://127.0.0.1:18080`. |
| Portal API client/types | `komsco-ai-portal/src/api.ts`, `src/types.ts` | Missing | `copy` | This locks required Gateway endpoints: summary/status/events. |
| Portal UI | `komsco-ai-portal/src/App.tsx`, `src/styles.css` | Missing | `copy` | Use as the v0.2.5 standalone page baseline. |
| Local portal tasks | `Taskfile.yml` | Missing in current repo | `merge` | Add only `portal:dev` and `portal:build`. Do not touch deployment tasks. |
| Cluster summary API | `komsco-ai-gateway/komsco_ai_gateway/main.py` | Present but narrower | `merge` | Extend current endpoint shape instead of replacing current Gateway. |
| AIOps status API | `komsco-ai-gateway/komsco_ai_gateway/main.py` | Present and richer | `merge` | Preserve current safety/access review/RAG fields while keeping portal-compatible `capabilities` and `records`. |
| AIOps events API | `komsco-ai-gateway/komsco_ai_gateway/main.py` | Missing route in current repo | `merge` | Add `/v1/aiops/events` and tests. |
| Action registry/lifecycle | `main.py`, `aiops_core.py`, `action_executor.py` | Mostly present, current repo has newer additions | `merge` | Diff and port only missing behavior. Keep current execution policy safeguards. |
| Gateway tests | `komsco-ai-gateway/tests/test_health.py` | Present, richer in current repo | `merge` | Add missing portal contract/event tests only. |
| Console left navigation | `komsco-ai-console-plugin/console-extensions.json` | Present under `/dashboards/aiops` | `keep` | Console internal AIOps pages remain available. |
| ApplicationMenu ConsoleLink | chart/base/OLM config | Present but hrefs are not fully aligned | `defer` | Review source only in this lane. Do not deploy. Final href target is `https://aiops.cywell.co.kr`. |
| OLM/Helm/catalog deploy scripts | `scripts/*`, `openshift/*` | Present and production-sensitive | `defer` | Do not run `aiops:company:*`, `olm:*`, or `catalog:*` in v0.2.5 local implementation. |
| Reference node_modules | `komsco-ai-portal/node_modules/` | Not tracked target | `do not port` | Use `npm install` in target package. |

## Gateway Contract Delta

| Endpoint | Reference | Current repo before v0.2.5 | v0.2.5 action |
| --- | --- | --- | --- |
| `GET /healthz` | Present | Present | Keep. |
| `GET /v1/cluster/summary` | Includes nodes, operators, version, workloads/resources | Present but narrower | Extend shape for portal. |
| `GET /v1/aiops/status` | Runtime capabilities and records | Present with extra safety/access review fields | Keep extras, maintain portal-required shape. |
| `GET /v1/aiops/events` | Present | Missing route | Add route and tests. |
| `GET /v1/actions/registry` | Present | Present | Keep current registry unless diff shows missing safe action. |
| `POST /v1/actions/*` | Present | Present plus candidate plan/rejection routes | Keep current routes; only port missing behavior. |
| `GET /v1/runbooks/registry` | Present | Present | Keep current route. |
| `GET /v1/evidence`, `GET /v1/workflows/{run_id}` | Present | Present | Keep current route. |
| `POST /v1/chat/stream` | Present | Present | Keep current stream flow; verify portal work does not change it. |

## Safe Execution Boundary

Allowed in this lane:

```text
git diff --check
rg / sed / find
npm install
npm run build
task portal:build
python3 -m py_compile ...
komsco-ai-gateway/.venv/bin/python -m pytest ...
local curl against 127.0.0.1 only
```

Forbidden in this lane:

```text
task aiops:company:*
task olm:*
task catalog:*
oc apply
oc delete
helm upgrade
scripts/kugnus-olm.sh publish/install/uninstall
scripts/olm-deploy.sh deploy/install/catalog
```

## Reviewer Assignments

| Reviewer | Mode | Focus | Evidence |
| --- | --- | --- | --- |
| Portal Contract | read-only | Portal package structure, Vite proxy, API client, brand text, build output | `pass/fail/evidence/current gap/recommended adjustment` |
| Gateway/Action Contract | read-only | Summary/status/events API shape, action lifecycle tests, unrestricted local behavior | `pass/fail/evidence/current gap/recommended adjustment` |
| Console/Deploy Safety | read-only | Launcher href source consistency, no deployment task execution, protected files untouched | `pass/fail/evidence/current gap/recommended adjustment` |

## Completion Gate

v0.2.5 is not complete until these are all true:

- `komsco-ai-portal` builds locally.
- Gateway tests cover `cluster_summary`, `aiops_status`, and `aiops_events`.
- No company server deploy/install command was run.
- `git diff --name-only` does not include protected artifacts or `evals/aiops-scenarios/*`.
- Any ConsoleLink/ApplicationMenu source change is documented as source-only and not applied to the cluster.
