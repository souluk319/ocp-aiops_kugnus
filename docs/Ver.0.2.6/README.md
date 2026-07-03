# v0.2.6 Chatbot / FAB / Action Plan

## Purpose

v0.2.6은 `AIOps for OCP`의 챗봇, FAB, Action Plan 경험을 운영자용 Incident Copilot 수준으로 정리하는 버전이다.

v0.2.5에서 독립 포털과 OKD 내부 탭의 대시보드 경험을 맞췄다면, v0.2.6은 사용자가 실제로 문제를 묻고, 근거를 보고, Action Plan을 승인하거나 실행하는 흐름을 고친다.

## Baseline

- Working branch: `feature/v0.2.5-aiops-for-ocp-port`
- Baseline HEAD when this document was created: `b5fd01f`
- Current working tree already contains v0.2.5 dashboard/portal/gateway changes.
- v0.2.6 implementation should start after the v0.2.5 dashboard state is committed or otherwise intentionally preserved.

## Scope

v0.2.6 targets only these surfaces:

- `komsco-ai-console-plugin/src/components/AssistantLauncher.tsx`
- `komsco-ai-console-plugin/src/components/assistant.css`
- assistant helper components/types under `komsco-ai-console-plugin/src/components/`
- Gateway action lifecycle code only when UI contract requires a typed status or error mapping
- focused tests for chat/action lifecycle behavior

## Goals

| Area | Goal |
| --- | --- |
| Chat answer | Move from long message/raw state display to operator runbook cards. |
| FAB | Keep the polished FAB, but verify dark theme and state indicator visibility. |
| Theme alignment | Make chatbot typography, spacing, badges, cards, and controls feel like the v0.2.5 dashboard. |
| Control sync | Connect chatbot state with dashboard context, selected resource, action candidates, mode, and panel state. |
| Action Plan | Normalize candidate -> plan -> approval -> execution -> verification. |
| Loading state | Remove lingering answer-preparing animation after completion. |
| Dedupe | Do not show duplicate Action Plan cards for the same target/tool/request. |
| Execution modes | Make read-only, executable, and unrestricted modes visible and truthful. |
| Error wording | Translate raw errors such as `Conflict` into actionable Korean explanations. |
| Verification | Add actual lifecycle checks, not only UI screenshots. |

## Out Of Scope

- Company server deployment
- OLM publish/install
- Catalog rebuild
- Helm release changes
- Dashboard portal redesign
- Changing the dashboard theme source without a separate v0.2.5/v0.2.6 agreement
- Protected scenario JSON edits
- Rewriting protected beginner/strategy HTML documents

## Primary Plan

See [chatbot-fab-action-plan-refactor-plan.md](./chatbot-fab-action-plan-refactor-plan.md).
