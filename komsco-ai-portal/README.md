# AIOps for OCP Portal

Standalone React SPA for the AIOps for OCP portal experience.

The OpenShift Console plugin remains in `komsco-ai-console-plugin/`. This package
is a separate frontend that talks to a separately deployed Gateway/BFF. It does
not embed backend code.

## Local development

```bash
cd komsco-ai-portal
npm install
npm run dev
```

By default, the Vite dev server proxies `/v1/*` to `http://127.0.0.1:18080`.
Override the target when the Gateway runs elsewhere:

```bash
AIOPS_GATEWAY_ORIGIN=http://127.0.0.1:8080 npm run dev
```

When using the local Gateway directly, start through the repository task so the
current `oc` token is injected into the dev proxy at runtime:

```bash
task portal:dev
```

For production builds, set `VITE_AIOPS_API_BASE_URL` to the Gateway/BFF origin or
serve the SPA from the same origin as the Gateway and leave it empty.

```bash
VITE_AIOPS_API_BASE_URL=https://aiops-gateway.example.com npm run build
```

The UI falls back to local demo data when the Gateway is unavailable so the
portal can be reviewed independently from backend deployment.
