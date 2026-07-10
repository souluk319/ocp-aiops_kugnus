# KOMSCO AI Gateway

FastAPI BFF for the KOMSCO OpenShift Console AI assistant.

The console plugin forwards the current OpenShift user token through
`ConsolePlugin.spec.proxy` with `authorization: UserToken`. This gateway keeps
request validation, redaction, and OpenShift Lightspeed calls outside the
browser.

## Local Development

From the repository root, the preferred Lightspeed-connected local flow is:

```bash
task be:dev
```

This uses `oc port-forward` from
`openshift-lightspeed/lightspeed-app-server:8443` to `127.0.0.1:18443`, then
runs the gateway on `http://127.0.0.1:18080` with:

```bash
OLS_BASE_URL=https://127.0.0.1:18443
OLS_CA_FILE=false
KOMSCO_AI_DEV_ECHO=false
```

Image attachments are accepted by `/v1/chat/stream` as base64 image payloads.
The gateway validates MIME type, per-file size, total size, and duplicate ids,
then optionally calls an OpenAI-compatible vision endpoint before forwarding the
vision summary and file metadata to Lightspeed as text context. Current OLS
deployments can reject `image/*` attachments, so raw image forwarding to OLS is
disabled by default.

Vision preprocessing is enabled with:

```bash
export KOMSCO_AI_VISION_BASE_URL=http://example-llm/v1
export KOMSCO_AI_VISION_MODEL=vision-capable-model
export KOMSCO_AI_VISION_API_KEY_FILE=/path/to/api-key
```

Raw image attachments are not sent to OLS 1.1.x because its request contract
rejects `attachment_type=image`.

Echo-only mode:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
KOMSCO_AI_DEV_ECHO=true uvicorn komsco_ai_gateway.main:app --reload --port 8080
```

When `KOMSCO_AI_DEV_ECHO=true`, `/v1/chat/stream` returns a local SSE echo
response without requiring an in-cluster Lightspeed service.

For cluster integration, set:

```bash
export OLS_BASE_URL=https://lightspeed-app-server.openshift-lightspeed.svc:8443
export OLS_CA_FILE=/var/run/configmaps/service-ca/service-ca.crt
```

## Runtime APIs

The gateway exposes the current implementation foundation as JSON APIs:

- `GET /v1/evidence` and `GET /v1/evidence/{evidence_id}` return redacted
  evidence references and details with read-time subject checks.
- `GET /v1/workflows/{run_id}` returns observable workflow state.
- `POST /v1/diagnostics/requests` creates a host diagnostic request candidate,
  digest, and grant reference. When `KOMSCO_AI_DIAGNOSTICS_ENABLED=true` and
  `KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_URL` is configured, the gateway submits
  the request to the Host Diagnostics Controller. The controller creates a fixed,
  evidence-check collector Job for the selected allow-listed node OS/runtime profile.
- `GET /v1/diagnostics/collectors` returns the host diagnostics collector
  registry used to validate node OS/runtime triage requests.
- `GET /v1/actions/registry` returns the typed action allow-list.
- `POST /v1/actions/proposals`, `/v1/actions/plans`,
  `/v1/actions/approvals`, and `/v1/actions/execute` model the
  approval-gated action lifecycle. Kubernetes mutation remains blocked while
  `KOMSCO_AI_ENABLE_MUTATIONS=false`; when enabled, the executor only performs
  typed allow-list requests and rejects generic `patch_resource`, `apply_manifest`,
  `run_command`, `exec`, and arbitrary host command flows.
- `GET /metrics` exposes core counters and in-memory record gauges.

Run the gateway checks with:

```bash
ruff check . ../scripts/evaluate-gateway-responses.py
pytest
```
