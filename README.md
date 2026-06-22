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

`task be:dev` asks which mode to run: `읽기 전용` for analysis/planning only,
or `실행 가능` to submit approved typed actions through the cluster Action
Executor.

In another terminal:

```bash
task fe:dev
```

`task be:dev` port-forwards
`openshift-lightspeed/lightspeed-app-server:8443` to `127.0.0.1:18443` and
runs the FastAPI gateway on `http://127.0.0.1:18080` with `OLS_BASE_URL` pointing
at that local Lightspeed endpoint. In `실행 가능` mode, the same task also
port-forwards the cluster `komsco-ai-action-executor:8080` service to the local
gateway, sets `KOMSCO_AI_ENABLE_MUTATIONS=true`, and is intended for controlled
demos of the approval/execution path.

`task fe:dev` starts the plugin webpack dev server on `http://127.0.0.1:9001`
and then starts the local OpenShift Console bridge on `http://localhost:9000`.
The bridge proxy forwards the assistant API path to `http://localhost:18080`.

The local console bridge captures the current `oc` bearer token when it starts.
If that token expires, `task fe:dev` validates the token with the API server and
stops/restarts the bridge instead of keeping a broken `401 Unauthorized` console
session alive. A static `.env.local` `OPENSHIFT_TOKEN` is not refreshable by
itself; replace it when it expires, or configure a local-only
`OPENSHIFT_RELOGIN_COMMAND` that can run `oc login` and produce a fresh valid
session. When that command is configured, the dev loop runs it after token/health
failures, verifies `oc whoami`, and restarts the bridge with the new token.

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
