# AIOps Recovery Roadmap

Date: 2026-07-10
Status: Active specification
Baseline: `refactor/ver0.3.1` at `3b7108a`

## Goal

Restore a traceable V1 read-only AIOps flow before expanding execution features:

`question -> intent -> page context -> Tool Plan -> Evidence -> Lightspeed/RCA -> Action Plan candidate -> audit record`

The product must explain what it actually knows, distinguish product/UI questions from OpenShift incidents, and never turn missing evidence into a plausible-looking operational answer.

## Completion Rules

- Every phase has a pass/fail regression test.
- Existing public API paths and SSE event names remain compatible.
- New behavior is added in cohesive modules instead of growing `main.py`, `AssistantLauncher.tsx`, or oversized test files.
- Protected PDFs, `docs/Ver.0.2.9/`, and protected editorial artifacts are not modified.
- A phase is complete only when the closest tests and an independent review lane pass.

## Phase 1 - Question Intent And RCA Screen Context

Current execution scope.

### 1A. Product feedback routing

- Questions about answer quality, feedback candidates, or Runbook promotion are classified as `product_feedback`.
- They must not be presented as OpenShift incidents or cluster-resource investigations.
- The deterministic Tool Plan contains no Kubernetes tool step.

### 1B. UI explanation routing

- Questions asking to explain the current AIOps dashboard are classified as `ui_explanation` when an AIOps route is present.
- Operational questions such as cause analysis, resource lookup, or remediation remain operational.
- The deterministic Tool Plan contains no Kubernetes tool step for a pure screen explanation.

### 1C. RCA Center page context

- `/dashboards/aiops/audit` publishes the page title, selected RCA case, issue type, summary, metrics, findings, evidence package, Runbook gates, and timeline to the Assistant request context.
- Context is based on the same data rendered by the RCA Center, not DOM scraping or screenshot guessing.
- Leaving a page clears stale page-specific context before the next view publishes its own context.

### 1D. Regression evidence

- Gateway intent tests cover product feedback, UI explanation, and an operational negative control.
- Frontend context tests prove the RCA payload contains the visible case and evidence fields.
- TypeScript typecheck and `git diff --check` pass.

## Phase 2 - Evidence Boundary And False Success

- Remove false PASS states when required Evidence is missing.
- Separate collection failure, provider failure, and answer rendering failure.
- Block dangerous execution when approval, digest, target, or Evidence identity does not match.
- Acceptance: no successful operational claim without a matching Evidence reference.

## Phase 3 - RAG Consistency

- Resolve the 768/1024 embedding dimension mismatch at configuration and storage boundaries.
- Make RAG availability and omission visible without leaking internal prompt text.
- Fail closed when a Runbook is required but unavailable.

## Phase 4 - Lightspeed And Conversation Contract

- Stabilize provider connectivity and expose the exact waiting layer.
- Preserve multi-turn focus across deterministic and model paths.
- Define one terminal stream outcome: success, partial with named missing evidence, or failure.
- Store test conversations so regressions can be reviewed without manual copy and paste.

## Phase 5 - Action And Audit Identity

- Keep `candidateId`, `proposalId`, `planId`, `planDigest`, approval, execution, and audit records connected.
- Distinguish review-only records from server mutation records.
- Persist records through the configured record store and make retention explicit.

## Phase 6 - Operator UI Reliability

- Restore chat/table scroll positions without rerender snap-back.
- Show measured progress by cluster, Gateway, model, rendering, action, and audit layers.
- Mark sample data and live data unambiguously.
- Keep Action Plan cards compact, recoverable from conversation history, and readable in read-only mode.

## Phase 7 - V1 Read-Only Demonstration Lock

Lock three end-to-end scenarios:

1. Cluster error Pod inventory and evidence-based RCA.
2. AIOps alert or RCA Center screen explanation using live page context.
3. Read-only Action Plan candidate with review record and no server mutation.

Each scenario must preserve `Tool Plan -> Evidence -> RCA -> Action Plan candidate -> review/audit record` and include failure evidence when a dependency is unavailable.

## Out Of Scope For Phase 1

- New mutation executors.
- Automatic Runbook promotion from feedback.
- Full context support for every dashboard tab.
- Broad visual redesign.
- Refactoring unrelated oversized modules.
