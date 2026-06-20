# Agent Notes

This is an instantiated KOMSCO plugin, not the upstream template.

- Keep extension code references in `console-extensions.json` aligned with
  `package.json` `consolePlugin.exposedModules`.
- Prefix plugin CSS with `komsco-ai__`.
- Do not add direct browser calls to Lightspeed or Kubernetes APIs. Use
  `consoleFetch` through the `ai-gateway` proxy.
- Preserve `ConsolePlugin.spec.proxy.authorization: UserToken` so the gateway can
  enforce user-specific RBAC and audit behavior.
