# KOMSCO AI Console Plugin

OpenShift Console Dynamic Plugin for the KOMSCO AI assistant.

This project is based on `openshift/console-plugin-template` `release-4.20`,
but replaces the example page with a global assistant overlay:

- `console.context-provider` injects the assistant at the Console root.
- `useOverlay` renders a fixed bottom-right launcher and chat panel.
- `consoleFetch` calls `/api/proxy/plugin/komsco-ai-console-plugin/ai-gateway/`.
- `ConsolePlugin.spec.proxy.authorization: UserToken` forwards the current
  OpenShift user token to `komsco-ai-gateway`.

## Local Development

From the repository root, the preferred local flow is:

```bash
task fe:dev
```

This starts `yarn start` on `http://127.0.0.1:9001`, then starts the local
OpenShift Console bridge on `http://localhost:9000`. It expects the gateway from
`task be:dev` to be available at `http://localhost:18080`.

The chat composer supports PNG, JPEG, WebP, and GIF attachments through file
selection, paste, or drag-and-drop. Attached images are shown as previews in the
conversation and sent to the local gateway with the chat request.

Manual mode, terminal 1:

```bash
yarn install
yarn start
```

Manual mode, terminal 2 after `oc login`:

```bash
yarn start-console
```

`start-console.sh` provides a default `BRIDGE_PLUGIN_PROXY` that forwards the
plugin proxy path to `http://localhost:8080`, matching the local FastAPI gateway
dev server.

## Build

```bash
yarn build
podman build -t registry.example.com/komsco/komsco-ai-console-plugin:dev .
podman push registry.example.com/komsco/komsco-ai-console-plugin:dev
```

## Deploy

```bash
helm upgrade -i komsco-ai-console-plugin \
  charts/openshift-console-plugin \
  -n komsco-ai-dev \
  --create-namespace \
  -f ../openshift/helm-values/console-plugin-dev.yaml
```

The chart emits the `ConsolePlugin` CR with an `ai-gateway` proxy entry. The
top-level `openshift/` directory also contains kustomize manifests for gateway
deployment and cluster integration.
