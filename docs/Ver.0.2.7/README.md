# v0.2.7 Chatbot JK UI Absorption

## Scope

- Base branch: `feature/v0.2.7-chatbot-jk-ui`
- Base commit: `9117234`
- Reference: `/home/kugnus/cywell/AIOps-Ref/aiops-ocp`
- Product name: `AIOps for OCP`

v0.2.7 is a local UI/design absorption lane for the OKD console Assistant/FAB. It does not deploy to the company server and does not publish or install OLM/catalog resources.

## Goal

The v0.2.6 chatbot is functionally connected, but its UI still feels like accumulated patches. v0.2.7 aligns it with the JK reference chatbot:

- dark command-center header
- softer left history rail without a hard divider
- assistant answers as operational runbook cards instead of a bulky chat bubble
- compact but readable typography
- cleaner composer and action controls
- expanded mode that reads as `chat column + context rail`

## Protected Files

This lane must not edit:

- `docs/version-progress-book.html`
- `docs/aiops-beginner-guide.html`
- `docs/Ver.0.1.8/aiops-llm-strategy-brief.html`
- `evals/aiops-scenarios/*`

## Verification

- `git diff --check`
- `python3 -m py_compile scripts/verify-v027-fixed-pdf.py && python3 scripts/verify-v027-fixed-pdf.py`
- `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck`
- `cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev`
- `NODE_PATH=/home/kugnus/cywell/ocp-aiops_kugnus/komsco-ai-console-plugin/node_modules node scripts/verify-v027-expanded-assistant-rail.cjs`
- `NODE_PATH=/home/kugnus/cywell/ocp-aiops_kugnus/komsco-ai-console-plugin/node_modules node scripts/verify-v027-ui-balance.cjs`

`verify-v027-ui-balance.cjs` checks local 9000 dashboard, alerts, reports, Assistant docked, and Assistant fullscreen across desktop/mobile and light/dark theme emulation.

Browser checks should stay local, mainly `http://localhost:9000`.

## Reports

- `chatbot-jk-ui-absorption-plan.md`: JK reference absorption plan.
- `chatbot-action-ui-test-review-report.md`: v0.2.7 chatbot, Tool Plan, Action lifecycle, badge alignment, and five-review evidence report.
