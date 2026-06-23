# Agent Notes

This is an instantiated KOMSCO plugin, not the upstream template.

- Keep extension code references in `console-extensions.json` aligned with
  `package.json` `consolePlugin.exposedModules`.
- Prefix plugin CSS with `komsco-ai__`.
- Do not add direct browser calls to Lightspeed or Kubernetes APIs. Use
  `consoleFetch` through the `ai-gateway` proxy.
- Preserve `ConsolePlugin.spec.proxy.authorization: UserToken` so the gateway can
  enforce user-specific RBAC and audit behavior.
- UI work must be implemented as a final-quality product surface in one pass.
  Do not intentionally ship rough placeholders, temporary header designs, or
  "first draft" visual states for the user to discover. Decide the product
  role of each asset before editing, then build and verify against the running
  screen.
- Branding roles are fixed: `K_icon.png` is the Kugnus/catalog identity and the
  assistant launch/toggle mark; `komsco_logo.svg` is the customer logo for the
  assistant header. Do not swap these roles without an explicit product reason.
- For manual user guidance, give the preferred command/action first and only
  one step at a time unless the user asks for a full batch.
