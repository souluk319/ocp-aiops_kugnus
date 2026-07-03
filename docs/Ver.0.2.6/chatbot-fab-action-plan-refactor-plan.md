# v0.2.6 Chatbot / FAB / Action Plan Refactor Plan

## Summary

v0.2.6 fixes the remaining high-impact product surface after the v0.2.5 dashboard/portal work: the assistant overlay, FAB, and Action Plan lifecycle.

The goal is not to add another visual skin. The goal is to make the chatbot behave like an OpenShift operations copilot:

```text
question
  -> evidence
  -> RCA
  -> runbook card
  -> Action Plan
  -> approval / execution
  -> verification / audit
```

The v0.2.4 JK reference absorption plan remains the design and logic source for this lane. The v0.2.5 `AIOps for OCP` portal work remains the product naming and data-contract baseline.

## Current Judgment

The dashboard/portal side is close to a local verification state. The chatbot side is not yet at the same quality level.

Known gaps from current observations and existing source inspection:

- The dashboard now has a stronger product theme than the assistant; chatbot typography, badges, cards, and controls must catch up.
- Some controls are obviously related across surfaces, but not yet treated as one product loop.
- Completed answers can leave a spinner/loading animation that still looks active.
- Action Plan cards can repeat for the same target or same approval/execution path.
- `실행 가능` and `실행 무제한` exist, but the UI language does not yet make every server gate and failure reason obvious.
- Raw internal wording such as `Conflict`, sealed-plan style states, or record-like phrases can leak into the operator view.
- Dark mode can hide header/action icons.
- Answers still lean toward message blocks instead of structured runbook cards.
- Action lifecycle tests exist in pieces, but acceptance should verify natural request -> typed action -> approval/execution -> verification.

## Design Contract

Project `DESIGN.md` wins for UI behavior.

The assistant must read in this order:

```text
요약
영향 범위
확인한 근거
원인 후보
Action Plan
추가 확인
재발 방지
```

Action Plan cards must show:

- 대상
- 문제
- 근거
- 조치
- 예상 영향
- 검증 방법
- 롤백 또는 실패 시 대응
- 승인 조건
- 승인/거절 또는 실행 버튼

Raw JSON, source URI, RAG score, internal event id, sealed-plan terminology, and tool-plan internals stay behind detail toggles.

## Theme Alignment Contract

The v0.2.5 dashboard is now the visual baseline. The assistant must look like it belongs to the same product, not like an older plugin bolted onto the side.

The assistant should reuse the dashboard's product feel:

- Dense but calm admin-console spacing
- Clear section headers with small blue square markers where appropriate
- Crisp chips and badges with balanced vertical alignment
- Light workspace surface with dark product/sidebar accents
- Same severity language: `위험`, `주의`, `정상`
- Same product name: `AIOps for OCP`
- Same icon family and visual weight
- Same button feel for primary, secondary, danger, disabled, and icon-only controls
- No nested card stacks unless they represent repeated items or details
- No tiny body text that falls below the dashboard readability baseline

The assistant should not copy the dashboard layout literally. It should share the visual system while staying optimized for a docked/expanded chatbot.

Theme-specific acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-T01 | Assistant typography does not look smaller or older than the dashboard. | visual comparison | screenshots |
| V026-T02 | Badges/chips align vertically like dashboard badges. | visual check | screenshot |
| V026-T03 | Primary/danger/disabled buttons match dashboard control weight. | visual check | screenshot |
| V026-T04 | Docked panel remains dense and readable without horizontal scroll. | responsive check | screenshot |
| V026-T05 | Expanded assistant uses the dashboard design language but keeps chat/context layout. | browser check | screenshot |

## Integration Control Contract

The assistant is not a separate toy chat window. It controls and explains the same operational state shown by the dashboard and OKD console.

These links must be treated as product contracts:

| Control / state | Required behavior |
| --- | --- |
| FAB open/close | Opens/closes the assistant without leaving orphan side panels or stale overlays. |
| Current OKD page/resource | When launched from a resource page, the assistant receives namespace/kind/name/path context. |
| Dashboard Action Candidate | Clicking a dashboard action should draft or open the matching assistant prompt/action context. |
| RCA Center | RCA result should be reusable as assistant evidence, not duplicated as unrelated text. |
| Alerts & Events | Alert/event context should seed the assistant with reason, target, namespace, severity, and evidence links. |
| Cluster Resources | Selected resource should become the assistant target for RCA or Action Plan generation. |
| Execution mode | `읽기 전용`, `실행 가능`, `실행 무제한` must be shared between header controls, action cards, and server status. |
| Gateway capability | UI must show when execution/unrestricted is visible but server policy rejects it. |
| Conversation plan panel | Left plan panel and answer body must show the same lifecycle stage for the same plan. |
| History | Selecting history should restore the relevant answer/action state without replaying stale loading. |
| Upload/RAG evidence | Uploaded docs and RAG evidence should appear as evidence details, not random chat prose. |
| Theme | OCP light/dark theme must keep FAB, header buttons, chips, and action buttons visible. |
| Locale | KR/EN controls should either work consistently or be removed/disabled with clear state. |

Integration-specific acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-I01 | Launching assistant from a Pod/Deployment page includes resource context in prompt/action state. | browser/manual check | screenshot/log |
| V026-I02 | Dashboard action candidate opens assistant with matching target/action draft. | browser/manual check | screenshot |
| V026-I03 | Alerts & Events item can start RCA with severity/reason/target preserved. | browser/manual check | screenshot |
| V026-I04 | Execution mode displayed in header and Action Plan cards is the same state. | DOM/browser check | screenshot |
| V026-I05 | Closing assistant clears dependent context panels and does not leave stale UI. | browser check | screenshot |
| V026-I06 | History restore does not show active spinner for completed answers. | browser check | screenshot |

## JK Reference Items To Absorb

| Reference idea from v0.2.4 | v0.2.6 product decision |
| --- | --- |
| Operations runbook UI | Default assistant answer becomes one primary runbook card plus collapsed supporting sections. |
| OLS/Gateway/Action Executor boundary | UI labels separate observation, policy coordination, and approved mutation. |
| Typed action validation | Every action card is tied to tool/action id, target, digest, approval state, and execution result. |
| Follow-up action recovery | "진행해", "승인해", "실행해" should resolve to the latest valid plan, not random assistant text. |
| Registry/runbook alignment | UI card labels should map to action/runbook registry names where possible. |
| Error surface | Raw failures are translated into target changed, policy rejected, permission denied, capability disabled, expired plan, or execution failed. |

## Implementation Lanes

### Lane 0: Theme And Integration Inventory

Goal: before touching components, identify the exact controls and visual tokens that must be aligned.

Work:

- Compare v0.2.5 dashboard styles in `komsco-ai-portal/src/styles.css` and embedded portal styles with `assistant.css`.
- List reusable visual decisions: typography scale, badge geometry, control height, border color, severity colors, icon button weight.
- Map assistant entry points from dashboard, OKD routes, FAB, history, action records, and alert/resource rows.
- Write a short implementation checklist before patching UI.

Acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-00 | Theme/control inventory exists before UI patching. | doc/checklist | changed file |
| V026-00A | Integration entry points are listed with source and target state. | source grep + notes | evidence |

### Lane 1: Loading And Stream Completion

Goal: a finished answer must look finished.

Work:

- Inspect `AssistantLauncher.tsx` loading state, SSE end handling, abort handling, and queued assistant text flush.
- Make the loading indicator depend on an active request, not merely on the latest assistant message.
- Ensure `[DONE]`, stream `end`, request error, and manual stop all clear visual loading.

Acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-01 | Completed answer has no moving spinner. | Browser check or DOM state check | screenshot or test note |
| V026-02 | Stop button clears request state and does not leave stale animation. | UI check | screenshot or event log |
| V026-03 | Stream error shows a readable failure state instead of an eternal loading state. | mocked/error path | test output |

### Lane 2: Runbook Card Answer Renderer

Goal: answers should be scannable runbooks, not long undifferentiated chat blobs.

Work:

- Add a structured assistant answer renderer that can display:
  - 요약
  - 영향 범위
  - 확인한 근거
  - 원인 후보
  - Action Plan
  - 검증/롤백
  - 근거 상세보기
- Keep markdown fallback for answers that cannot be parsed safely.
- Keep raw evidence and JSON details behind explicit toggles.

Acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-04 | First visible answer section is an operator summary/runbook card. | Browser check | docked and expanded screenshots |
| V026-05 | Raw JSON/source ids do not dominate the default answer view. | DOM/text check | screenshot |
| V026-06 | Long pod/deployment ids wrap or collapse without horizontal scroll. | responsive check | screenshot |

### Lane 3: Action Plan Dedupe And Lifecycle

Goal: one operational issue should not produce two or three visually competing cards.

Canonical lifecycle:

```text
candidate -> plan -> approval -> execution -> verification
```

Dedupe key:

```text
conversationId + target.namespace + target.kind + target.name + toolName + actionType + parameterDigest
```

Work:

- Normalize session action record grouping around the canonical lifecycle.
- Merge proposal/plan/approval/execution records into one visible card when they share the dedupe key.
- Prefer the highest lifecycle stage for the card status.
- Keep audit/detail records available in details, not as repeated top-level cards.

Acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-07 | Same target/tool does not show duplicate Action Plan cards in one answer. | unit/static or browser check | test output |
| V026-08 | Approval and execution update the same card instead of creating confusing duplicates. | action lifecycle check | screenshot/test |
| V026-09 | The left conversation plan panel and answer body agree on the same lifecycle status. | browser check | screenshot |

### Lane 4: Execution Mode Truthfulness

Goal: `읽기 전용`, `실행 가능`, and `실행 무제한` are visible, truthful, and policy-aware.

Work:

- Keep all three modes visible.
- In `읽기 전용`, show RCA/evidence and do not offer mutation execution.
- In `실행 가능`, require approval before execution.
- In `실행 무제한`, allow automatic approval/execution only when Gateway capability is enabled.
- If capability is disabled, keep the mode visible and show the reason.

Acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-10 | All three modes are visible and selectable when UI policy allows. | browser check | screenshot |
| V026-11 | Unrestricted mode auto approval/execution path works only when capability is enabled. | pytest/UI flow | test output |
| V026-12 | Disabled capability shows a Korean reason instead of silently hiding buttons. | browser check | screenshot |

### Lane 5: Human Error Wording

Goal: users should not see raw infrastructure words without explanation.

Mapping:

| Raw/internal signal | Operator wording |
| --- | --- |
| `Conflict` | 대상 상태가 계획 생성 이후 바뀌었습니다. 최신 상태를 다시 확인한 뒤 재생성해야 합니다. |
| `Forbidden` / RBAC denial | 현재 계정에는 이 조치를 실행할 권한이 없습니다. |
| capability disabled | 서버에서 해당 실행 기능이 꺼져 있습니다. 관리자 설정 확인이 필요합니다. |
| expired plan | 승인 가능한 시간이 지나 Action Plan을 다시 만들어야 합니다. |
| digest mismatch | 승인한 계획과 실행 요청의 내용이 달라 실행을 중단했습니다. |
| target not found | 대상 리소스가 더 이상 존재하지 않습니다. |
| execution failed | 조치 실행이 실패했습니다. 대상 상태와 이벤트를 다시 확인해야 합니다. |

Acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-13 | `Conflict` raw text is not the primary user-facing error. | text grep/UI check | evidence |
| V026-14 | Policy/capability/permission failures each have distinct Korean wording. | unit check | test output |
| V026-15 | Raw error is still available in developer/audit detail. | detail toggle check | screenshot |

### Lane 6: FAB And Dark Theme Visibility

Goal: the assistant entry point and header controls remain visible in OCP dark theme and match the dashboard control language.

Work:

- Audit FAB icon, status indicator, header icon buttons, KR/EN toggle, fullscreen, lock, close.
- Use theme-safe colors/tokens instead of relying on dark-on-dark icons.
- Keep the current FAB shape that was accepted as polished.
- Align icon button sizing, focus state, disabled state, and tooltip behavior with the dashboard controls.
- Confirm FAB status indicator means the same thing as gateway/assistant state.

Acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-16 | FAB icon and status dot are visible in light and dark themes. | browser screenshot | screenshot |
| V026-17 | Header icon buttons are visible in dark theme. | browser screenshot | screenshot |
| V026-18 | No dark-theme icon is only discoverable by hover. | visual check | screenshot |
| V026-19 | FAB and assistant header controls visually match dashboard controls. | visual comparison | screenshot |

### Lane 6.5: Cross-Surface Control Sync

Goal: the assistant should react to dashboard and OKD context in predictable ways.

Work:

- Define a single assistant launch context shape:

```ts
type AssistantLaunchContext = {
  source: 'fab' | 'dashboard' | 'alerts' | 'resource' | 'rca' | 'history';
  promptDraft?: string;
  namespace?: string;
  kind?: string;
  name?: string;
  severity?: 'risk' | 'warn' | 'ok';
  reason?: string;
  actionType?: string;
  evidenceRefs?: string[];
};
```

- Route dashboard/resource/alert clicks through that context instead of ad hoc text only.
- Keep draft prompt, target chips, and Action Plan target in sync.
- Clear launch context when conversation changes or assistant closes.

Acceptance:

| ID | Pass/Fail | Method | Evidence |
| --- | --- | --- | --- |
| V026-20 | Launch context has one typed shape. | source check | typecheck |
| V026-21 | Dashboard action candidate opens assistant with target chip and draft prompt. | browser check | screenshot |
| V026-22 | Alert/resource context clears when assistant closes. | browser check | screenshot |
| V026-23 | Context chips do not create horizontal scroll in docked mode. | responsive check | screenshot |

### Lane 7: Action Lifecycle Verification

Goal: the implementation must prove the action loop, not only render it.

Target scenarios:

- Read-only RCA
- Deployment restart proposal
- Deployment scale proposal
- Pod eviction
- Rollback intent
- HPA bounds
- Ambiguous mutation blocked
- Follow-up "진행해" or "승인해"
- Unrestricted local lab execution
- Conflict/target changed

Verification commands:

```bash
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs typecheck
cd komsco-ai-console-plugin && node .yarn/releases/yarn-4.13.0.cjs build-dev
python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/komsco_ai_gateway/aiops_core.py komsco-ai-gateway/komsco_ai_gateway/action_executor.py
komsco-ai-gateway/.venv/bin/python -m pytest -q komsco-ai-gateway/tests/test_health.py -k "agentic_action or action_plan or natural_action or followup or unrestricted or rollback or hpa or eviction or conflict"
```

Browser checks are required after UI implementation:

- OKD console plugin at `http://localhost:9000`
- Standalone portal at `http://localhost:5174` for dashboard-triggered context checks
- FAB open/close
- docked assistant
- expanded assistant
- dashboard action candidate -> assistant draft
- alerts/resources -> assistant context
- light/dark theme
- narrow panel width

## Execution Order

1. Finish and commit/preserve v0.2.5 dashboard state.
2. Create a v0.2.6 implementation branch from the preserved state.
3. Lane 0: theme and integration inventory.
4. Lane 1: loading completion fix.
5. Lane 3 + Lane 5: lifecycle grouping, dedupe, and error wording.
6. Lane 4: execution mode truthfulness.
7. Lane 6.5: cross-surface control sync.
8. Lane 2: runbook card renderer.
9. Lane 6: FAB/dark theme/theme alignment polish.
10. Lane 7: lifecycle verification and screenshots.

This order intentionally fixes state correctness before visual restructuring.

## Reviewer Lanes

If parallel reviewers are available, they should be read-only.

| Reviewer | Focus | Output |
| --- | --- | --- |
| UI Reviewer | runbook card, FAB, dark theme, responsive panel | pass/fail/evidence/current gap |
| Contract Reviewer | action lifecycle state, dedupe key, error mapping, execution mode | pass/fail/evidence/current gap |
| Gateway Reviewer | typed action, approval/execution, verification tests | pass/fail/evidence/current gap |
| Integration Reviewer | dashboard/alert/resource/history context sync | pass/fail/evidence/current gap |

## Do Not Do In v0.2.6

- Do not deploy to company OCP.
- Do not run OLM publish/install/catalog tasks.
- Do not modify protected scenario files.
- Do not remove execution modes to hide policy problems.
- Do not hide errors without preserving raw detail for audit/developer inspection.
- Do not redesign the dashboard/portal while fixing chatbot behavior.

## Final Acceptance Criteria

| ID | Pass/Fail Criteria | Method | Evidence |
| --- | --- | --- | --- |
| V026-F01 | Assistant answer completion clears loading UI. | browser/test | screenshot or test |
| V026-F02 | One operational issue produces one primary Action Plan card. | browser/test | screenshot/test |
| V026-F03 | Action card shows target, evidence, impact, approval condition, verification, rollback. | UI check | screenshot |
| V026-F04 | Execution modes are visible and match server capability. | UI + status payload | screenshot/API evidence |
| V026-F05 | Raw `Conflict` and similar errors are translated for operators. | unit/UI check | test/screenshot |
| V026-F06 | Dark theme icons are visible. | browser screenshot | screenshot |
| V026-F07 | Natural action lifecycle tests pass. | pytest | command output |
| V026-F08 | Console plugin typecheck and build pass. | yarn commands | command output |
| V026-F09 | Protected artifacts remain untouched. | `git diff --name-only` | diff evidence |
| V026-F10 | Assistant theme matches v0.2.5 dashboard visual language. | visual comparison | screenshot |
| V026-F11 | Dashboard/resource/alert controls can launch assistant with typed context. | browser/manual check | screenshot/log |
