# OCP AIOps Workspace

Local source workspace for the KOMSCO OpenShift AI assistant.

## Layout

```text
komsco-ai-console-plugin/
  OpenShift Console Dynamic Plugin based on console-plugin-template release-4.20.

komsco-ai-gateway/
  FastAPI gateway/BFF for UserToken forwarding and OpenShift Lightspeed
  streaming.

openshift/
  Kustomize manifests for dev/prod namespaces and Helm values for the console
  plugin chart.

scripts/
  Local helper scripts for dev and cluster integration.
```

## Local Development

After VPN/hosts setup and `oc login`, run the local development loop with
Task:

```bash
task be:dev
```

`task be:dev` asks which mode to run and defaults to `실험 무제한` for the
internal development network:

- `읽기 전용`: analysis/planning only.
- `실행 가능`: submit approved typed actions through the cluster Action
  Executor.
- `실험 무제한`: local lab mode that immediately executes supported natural
  language AIOps actions and also enables explicit `/exec <command>` requests to
  run with the Gateway process privileges.

In another terminal:

```bash
task fe:dev
```

`task be:dev` port-forwards
`openshift-lightspeed/lightspeed-app-server:8443` to `127.0.0.1:18443` and
runs the FastAPI gateway on `http://127.0.0.1:18080` with `OLS_BASE_URL` pointing
at that local Lightspeed endpoint. In `실행 가능` and `실험 무제한` modes, the
same task also port-forwards the cluster `komsco-ai-action-executor:8080`
service to the local gateway and sets `KOMSCO_AI_ENABLE_MUTATIONS=true`.
`실험 무제한` additionally sets `KOMSCO_AI_ENABLE_UNRESTRICTED_COMMANDS=true`.
In that mode, requests such as `web-api 파드 3개로 올려줘` are converted to a
typed AIOps action, auto-approved for the local lab, executed through the Action
Executor path, and verified in the same chat response. It is intended only for
disposable local labs where direct host command execution is acceptable.

`task fe:dev` starts the plugin webpack dev server on `http://127.0.0.1:9001`
and then starts the local OpenShift Console bridge on `http://localhost:9000`.
The bridge proxy forwards the assistant API path to `http://localhost:18080`.

The local console bridge captures the current `oc` bearer token when it starts.
If that token expires, `task fe:dev` validates the token with the API server and
stops/restarts the bridge instead of keeping a broken `401 Unauthorized` console
session alive. A static `.env.local` `OPENSHIFT_TOKEN` is not refreshable by
itself; replace it when it expires, or configure local-only
`OPENSHIFT_USERNAME`/`OPENSHIFT_PASSWORD` credentials. For custom SSO flows,
configure `OPENSHIFT_RELOGIN_COMMAND` to run `oc login` and produce a fresh valid
session. When either relogin source is configured, the dev loop uses it after
token/health failures, verifies `oc whoami`, and restarts the bridge with the
new token.

The assistant supports image attachments in the local chat UI. The gateway
validates image type and size, optionally runs a gateway-side vision
preprocessor, and includes the resulting image summary plus file metadata in
the Lightspeed query. This keeps OLS responsible for OpenShift tools/RAG while
avoiding image attachment rejection in current OLS deployments.

OLS owns live read-only OpenShift observation through its MCP tools. The gateway
owns validation, redaction, streaming normalization, attachments, and future
internal integrations. See [docs/ols-gateway-tool-boundary.md](docs/ols-gateway-tool-boundary.md).

The current implementation follows the approved security envelope from
[docs/aiops-agent-architecture-proposal.md](docs/aiops-agent-architecture-proposal.md):

- Gateway keeps the console `UserToken` at the boundary and forwards it only to
  OpenShift/Lightspeed APIs that need it.
- Gateway emits structured `security_boundary`, `subject_review`,
  `policy_check`, `audit_record`, and `evidence_ref` stream events.
- Request text, page context, audit payloads, and evidence references are
  redacted before they are used as model or UI-facing metadata.
- Evidence and workflow state are available through read-time authorized
  gateway APIs.
- Host diagnostics and approval-gated action lifecycle foundation APIs are
  present, including request/plan digests, grant references, approval decisions,
  and execution records.
- Natural-language mutation requests such as "A 파드 3개로 올려줘" are parsed into
  typed action proposals and sealed plans before approval/execution.
- A typed AIOps core action engine is present for unhealthy controller-owned Pod
  eviction, Deployment rollout restart, bounded Deployment scale, Deployment
  rollback to a ReplicaSet revision, and HPA min/max bound changes. When
  enabled, execution goes through dry-run, UID/precondition validation, and the
  `komsco-ai-action-executor` ServiceAccount.
- Host OS diagnostics are requested through a collector registry. Arbitrary host
  commands are not accepted; node OS/runtime triage requests must use registered
  read-only collector profiles.

Manual gateway echo mode:

```bash
cd komsco-ai-gateway
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
KOMSCO_AI_DEV_ECHO=true uvicorn komsco_ai_gateway.main:app --reload --port 8080
```

Manual console plugin:

```bash
cd komsco-ai-console-plugin
yarn install
yarn start
```

In another terminal, after `oc login`:

```bash
cd komsco-ai-console-plugin
yarn start-console
```

`start-console.sh` defaults `BRIDGE_PLUGIN_PROXY` to forward
`/api/proxy/plugin/komsco-ai-console-plugin/ai-gateway/` to the local gateway
on `http://localhost:8080`.

## OCP Dev Integration

```bash
oc login https://api.<cluster>:6443
scripts/apply-dev.sh
```

Build and push images to your registry, then update:

- `openshift/overlays/dev/kustomization.yaml`
- `openshift/helm-values/console-plugin-dev.yaml`

Console plugin chart example:

```bash
helm upgrade -i komsco-ai-console-plugin \
  komsco-ai-console-plugin/charts/openshift-console-plugin \
  -n komsco-ai-dev \
  --create-namespace \
  -f openshift/helm-values/console-plugin-dev.yaml
```

Enable the KOMSCO plugin and remove only the Lightspeed UI plugin from the
active console plugin list:

```bash
scripts/enable-console-plugin.sh
```

## Official OLM / OperatorHub Deployment

Use this path when the OpenShift console should provide install and update as
official Operator Lifecycle Manager features. The packaging flow is:

```text
CatalogSource -> PackageManifest -> Subscription -> CSV -> Operator Deployment
-> AIOpsInstallation CR -> ConsolePlugin/Gateway/Executor/Diagnostics operands
```

The operator is intentionally lightweight and runs from the gateway image with
`python -m komsco_ai_gateway.olm_operator`. OLM owns the operator lifecycle; the
`AIOpsInstallation` custom resource owns the KOMSCO AIOps runtime.

Prepare images that are reachable by the cluster:

```bash
export KOMSCO_AIOPS_OPERATOR_VERSION=0.1.0
export KOMSCO_AIOPS_OPERATOR_NAMESPACE=komsco-ai
export KOMSCO_AIOPS_NAMESPACE=komsco-ai
export KOMSCO_AIOPS_OPERATOR_IMAGE=image-registry.openshift-image-registry.svc:5000/komsco-ai/komsco-ai-gateway:0.1.0
export KOMSCO_AIOPS_PLUGIN_IMAGE=image-registry.openshift-image-registry.svc:5000/komsco-ai/komsco-ai-console-plugin:0.1.0
export KOMSCO_AIOPS_GATEWAY_IMAGE=image-registry.openshift-image-registry.svc:5000/komsco-ai/komsco-ai-gateway:0.1.0
```

Source-to-OLM one-shot release:

```bash
task olm:release
```

This builds and pushes the gateway/operator image plus the console plugin image,
then registers the OLM catalog and installs or updates the Subscription. By
default it pushes to `oc registry info` and writes operand image references with
`oc registry info --internal`. Override `KOMSCO_AIOPS_PUSH_REGISTRY` and
`KOMSCO_AIOPS_PULL_REGISTRY` when the workstation push endpoint and in-cluster
pull endpoint differ.

To build and push only:

```bash
task olm:images
```

Generate the OLM bundle/catalog/install manifests:

```bash
task olm:package
```

OLM-only one-shot install or update when images already exist:

```bash
task olm:deploy
```

This registers a ConfigMap-backed `CatalogSource` in `openshift-marketplace`,
creates the operator namespace, `OperatorGroup`, `Subscription`, and then
creates `AIOpsInstallation`. The same command can be used for updates after
bumping `KOMSCO_AIOPS_OPERATOR_VERSION` and image references. OLM will resolve
the new CSV and update the operator; the operator then reconciles the operands.

Useful checks:

```bash
task olm:status
oc get packagemanifest komsco-aiops -n openshift-marketplace
oc get subscription,csv,aiopsinstallation -n komsco-ai
```

To remove the OLM install path:

```bash
task olm:uninstall
```

The generated files live under `olm/generated/` and are not committed as build
outputs. Source of truth is:

- `komsco-ai-gateway/komsco_ai_gateway/olm_operator.py`
- `scripts/olm-package.py`
- `scripts/olm-deploy.sh`

## Helm Software Catalog Deployment

The local development loop stays source-first and hot-reload friendly:

```bash
task be:dev
task fe:dev
```

For shared dev/stage/prod systems, publish the KOMSCO AIOps Helm chart as an
OpenShift Software Catalog source. The current catalog chart installs the
console plugin and `ConsolePlugin` proxy wiring. The gateway, Action Executor,
and host diagnostics runtime are still applied from the OpenShift overlay before
or alongside the catalog install:

```bash
export KOMSCO_AIOPS_ENV=prod
task catalog:runtime:apply
```

Package a chart version and create the Helm repository index:

```bash
export KOMSCO_AIOPS_CATALOG_URL=https://charts.example.internal/komsco-aiops
export KOMSCO_AIOPS_CHART_VERSION=0.1.0
export KOMSCO_AIOPS_PACKAGE_VALUES=openshift/helm-values/console-plugin-prod.yaml
task catalog:package
```

`task catalog:package` writes `dist/software-catalog/index.yaml` and the chart
archive. The packaged chart defaults are taken from
`KOMSCO_AIOPS_PACKAGE_VALUES` so Software Catalog installs can work without
manually re-entering the plugin image and gateway values. Publish the contents of
`dist/software-catalog/` to the URL above, then register the repository in
OpenShift. After this, the chart appears in **Ecosystem > Software Catalog**.

```bash
task catalog:register
task catalog:status
```

For CLI parity with the catalog install/upgrade flow:

```bash
export KOMSCO_AIOPS_NAMESPACE=komsco-ai
export KOMSCO_AIOPS_VALUES=openshift/helm-values/console-plugin-prod.yaml
task catalog:deploy
```

For an end-to-end CLI release using the same chart package:

```bash
export KOMSCO_AIOPS_CATALOG_URL=https://charts.example.internal/komsco-aiops
task catalog:release
```

To ship an update, build and push new runtime images, update the values file or
image tags, publish a new chart version, and refresh the catalog repo:

```bash
export KOMSCO_AIOPS_CHART_VERSION=0.1.1
task catalog:package
# upload dist/software-catalog/* to KOMSCO_AIOPS_CATALOG_URL
task catalog:register
```

Users can then upgrade the installed Helm release from the OpenShift console.
For production install/update UX, prefer the OLM path above.

## Namespace Policy

```text
Local PC
  - source, tests, yarn start, FastAPI dev server
  - oc login for OCP access

OCP cluster
  - komsco-ai-dev for integration testing
  - komsco-ai for production
  - ConsolePlugin, Service, Secret, RBAC, Route/Service CA resources

OCP install server
  - operational helper only
  - no primary Node/Python/IDE/git workspace
```
