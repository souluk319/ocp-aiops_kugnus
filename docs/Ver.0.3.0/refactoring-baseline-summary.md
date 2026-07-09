# Ver.0.3.0 Refactoring Baseline Summary

작성 목적: Todo 1 리팩토링 시작 전 기준선 고정. 제품 코드, 보호 시나리오, 계약 문서, `docs/Ver.0.3.0/refactoring-harness.md`는 수정하지 않았다.

## Raw Evidence

- `.tmp-kugnus-refactor/baseline/git-status-short-branch.txt`
- `.tmp-kugnus-refactor/baseline/head.txt`
- `.tmp-kugnus-refactor/baseline/tool-versions.txt`
- `.tmp-kugnus-refactor/baseline/line-count-top60.txt`
- `.tmp-kugnus-refactor/baseline/line-count-top60-files.txt`
- `.tmp-kugnus-refactor/baseline/protected-artifact-status.txt`
- `.omo/evidence/kugnus-refactoring-harness-replan/task-1/baseline.txt`

## Baseline Commands

```bash
git status --short --branch
git rev-parse HEAD
python3 --version
node --version
task --version
rg --files -g "!**/node_modules/**" -g "!**/dist/**" -g "!**/.tmp*/**" -g "*.py" -g "*.ts" -g "*.tsx" -g "*.js" -g "*.cjs" -g "*.mjs" -g "*.css" | xargs wc -l | sort -nr | head -60
```

## Branch And HEAD

```text
branch: refactor/ver0.3.0
HEAD: 9795da9632aba3630b14f3f44c909ff3929dcb85
```

## Dirty Status

```text
## refactor/ver0.3.0...origin/refactor/ver0.3.0
 D docs/Ver.0.3.0/SAFE_REFACTORING_HARNESS_PLAN.md
?? .omo/
?? docs/Ver.0.3.0/refactoring-harness.md
```

기존 워크트리 상태는 보존했다. `SAFE_REFACTORING_HARNESS_PLAN.md` 삭제와 `refactoring-harness.md` 추가는 되돌리지 않았다.

## Tool Versions

```text
Python 3.12.3
v24.14.0
3.51.1
```

## Large-File Inventory

제외 규칙: `node_modules`, `dist`, `.tmp*`, `.git` 제외. 아래 목록은 `wc -l`의 `total` 행을 제외한 파일 기준 상위 60개다.

```text
  18520 komsco-ai-gateway/komsco_ai_gateway/main.py
   9054 komsco-ai-gateway/tests/test_health.py
   8892 komsco-ai-console-plugin/src/components/assistant.css
   8056 komsco-ai-console-plugin/src/portal/PortalApp.tsx
   7611 komsco-ai-console-plugin/src/portal/styles.css
   7502 komsco-ai-portal/src/styles.css
   7335 komsco-ai-portal/src/App.tsx
   6237 komsco-ai-portal/src/v2/v2.css
   4510 komsco-ai-console-plugin/src/components/AssistantLauncher.tsx
   4344 scripts/verify-v0281-chatbot-answer-ux.cjs
   3361 komsco-ai-portal/src/v2/lib/model.ts
   3206 scripts/verify-kugnus-ui.mjs
   3203 scripts/serve-v0281-local-aiops-gateway.cjs
   1879 scripts/verify-v0281-local-aiops-scenarios.cjs
   1685 komsco-ai-gateway/komsco_ai_gateway/olm_operator.py
   1679 komsco-ai-console-plugin/src/pages/aiops-pages.css
   1649 komsco-ai-console-plugin/src/pages/AiopsPages.tsx
   1486 komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py
   1399 komsco-ai-portal/src/v2/views/V2Reports.tsx
   1213 komsco-ai-console-plugin/src/services/aiGateway.ts
   1158 komsco-ai-console-plugin/src/components/AssistantActionRecords.tsx
   1007 scripts/evaluate-aiops-actions-e2e.py
    950 scripts/evaluate-gateway-responses.py
    944 komsco-ai-console-plugin/src/pages/AiopsDashboardSections.tsx
    909 scripts/kugnus-demo-preflight.py
    808 komsco-ai-console-plugin/src/components/AssistantMessageContent.tsx
    740 komsco-ai-console-plugin/src/components/AssistantInsightRail.tsx
    708 komsco-ai-console-plugin/src/components/assistant.insightRailHelpers.tsx
    705 scripts/verify-v029-chatbot-action-history-flow.cjs
    694 scripts/verify-crashloop-live-demo-cycle.py
    686 scripts/verify-live-lightspeed-final-response.py
    685 scripts/verify-v0281-connected-aiops-scenarios.cjs
    684 scripts/olm-package.py
    633 komsco-ai-console-plugin/src/components/assistant.actionRecords.ts
    624 scripts/kugnus-ocp-connectivity-ladder.py
    601 komsco-ai-portal/src/v2/components/primitives.tsx
    597 scripts/verify-v029-aiops-completion-audit.cjs
    577 scripts/evaluate-aiops-scenarios.py
    554 komsco-ai-console-plugin/src/components/AssistantHistoryPanel.tsx
    550 komsco-ai-gateway/komsco_ai_gateway/aiops_core.py
    536 komsco-ai-portal/src/v2/views/V2Dashboard.tsx
    521 scripts/export-aiops-learning-dataset.cjs
    504 scripts/verify-v027-ui-balance.cjs
    493 scripts/verify-v029-chatbot-markdown-ux.cjs
    477 komsco-ai-portal/src/v2/views/V2Executions.tsx
    476 komsco-ai-console-plugin/src/components/AssistantProgressTimeline.tsx
    474 scripts/verify-aiops-review-gate.py
    464 scripts/verify-v027-expanded-assistant-rail.cjs
    440 komsco-ai-gateway/komsco_ai_gateway/host_diagnostics_controller.py
    435 scripts/verify-live-action-lifecycle.py
    406 scripts/verify-v027-toolplan-chat-ui.cjs
    396 scripts/verify-evidence-rca-scene.py
    385 komsco-ai-portal/src/v2/views/V2Wiki.tsx
    382 komsco-ai-gateway/komsco_ai_gateway/answer_planning.py
    380 komsco-ai-portal/src/v2/views/V2Alerts.tsx
    372 komsco-ai-console-plugin/src/components/AssistantCreateActionPlanButtons.tsx
    367 komsco-ai-portal/src/v2/views/V2Rca.tsx
    354 komsco-ai-portal/src/v2/components/V2Topology.tsx
    352 komsco-ai-console-plugin/src/components/AssistantComposer.tsx
    341 komsco-ai-console-plugin/src/pages/AiopsDocsSections.tsx
```

## Protected Artifact Status

명령:

```bash
git status --short --branch -- docs/Ver.0.3.0/SAFE_REFACTORING_HARNESS_PLAN.md docs/Ver.0.3.0/refactoring-harness.md docs/version-progress-book.html docs/aiops-beginner-guide.html docs/Ver.0.1.8/aiops-llm-strategy-brief.html evals/aiops-scenarios .claude docs/contracts
```

출력:

```text
## refactor/ver0.3.0...origin/refactor/ver0.3.0
 D docs/Ver.0.3.0/SAFE_REFACTORING_HARNESS_PLAN.md
?? docs/Ver.0.3.0/refactoring-harness.md
```

- `docs/Ver.0.3.0/refactoring-harness.md`: 보호 대상으로 보고 읽기만 했다.
- `evals/aiops-scenarios/`: 변경 없음.
- `docs/contracts/`: 변경 없음.
- `docs/version-progress-book.html`: 변경 없음.
- `docs/aiops-beginner-guide.html`: 변경 없음.
- `docs/Ver.0.1.8/aiops-llm-strategy-brief.html`: 변경 없음.
- `.claude/`: 변경 없음.

## Refactor Scope Guard

Todo 3부터 refactor PR은 `scripts/verify-refactor-scope.py`로 범위를 확인한다. 이 guard는 보호 문서 삭제/수정, 계약 문서 변경, 시나리오 JSON 변경, `.claude/` handoff 변경, mock customer/demo 자료 변경, 회사 서버 publish/install/redeploy 계열 작업 문자열 추가를 실패 처리한다.

허용된 baseline 문서만 고칠 때의 기준 명령:

```bash
python3 scripts/verify-refactor-scope.py --base HEAD --allow docs/Ver.0.3.0/refactoring-baseline-summary.md docs/Ver.0.3.0/refactoring-gate-baseline.md
```

## QA Commands To Preserve This Baseline

Happy QA:

```bash
bash -lc 'dir=.omo/evidence/kugnus-refactoring-harness-replan/task-1; mkdir -p "$dir"; { git status --short --branch; git rev-parse HEAD; python3 --version; node --version; task --version; rg --files -g "!**/node_modules/**" -g "!**/dist/**" -g "!**/.tmp*/**" -g "*.py" -g "*.ts" -g "*.tsx" -g "*.js" -g "*.cjs" -g "*.mjs" -g "*.css" | xargs wc -l | sort -nr | head -60; } > "$dir/baseline.txt"'
```

Acceptance:

```bash
test -f docs/Ver.0.3.0/refactoring-baseline-summary.md && rg "git status --short --branch|git rev-parse HEAD|main.py|test_health.py|assistant.css" docs/Ver.0.3.0/refactoring-baseline-summary.md
```

Failure guard:

```bash
bash -lc 'git diff --name-status | rg "^D\\s+(komsco-ai-gateway/tests/test_health.py|evals/aiops-scenarios/|docs/contracts/)"'
```

기대 결과: failure guard는 삭제 대상이 없어서 exit 1이어야 한다.
