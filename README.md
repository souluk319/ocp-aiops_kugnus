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

In another terminal:

```bash
task fe:dev
```

`task be:dev` port-forwards
`openshift-lightspeed/lightspeed-app-server:8443` to `127.0.0.1:18443` and
runs the FastAPI gateway on `http://127.0.0.1:18080` with `OLS_BASE_URL` pointing
at that local Lightspeed endpoint.

`task fe:dev` starts the plugin webpack dev server on `http://127.0.0.1:9001`
and then starts the local OpenShift Console bridge on `http://localhost:9000`.
The bridge proxy forwards the assistant API path to `http://localhost:18080`.

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
- Direct mutation requests are downgraded to action proposals. Actual Kubernetes
  remediation remains disabled by default with `KOMSCO_AI_ENABLE_MUTATIONS=false`.

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
