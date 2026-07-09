# Refactoring Gate Baseline

Baseline captured for Todo 2 of `.omo/plans/kugnus-refactoring-harness-replan.md`.

Evidence root: `.omo/evidence/kugnus-refactoring-harness-replan/task-2/`

## Worktree boundary

- Before status artifact: `.omo/evidence/kugnus-refactoring-harness-replan/task-2/git-status-before.txt`
- After status artifact: `.omo/evidence/kugnus-refactoring-harness-replan/task-2/git-status-after-restore.txt`
- Product code, tests, verifier scripts, protected artifacts, scenario JSON, contracts, and `docs/Ver.0.3.0/refactoring-harness.md` were not edited for this Todo.
- Only this report and task-2 evidence artifacts were written.
- Cleanup: `task kugnus:scenario:verify` regenerated `docs/Ver.0.1.3/aiops-scenario-evaluation-report.json`; that generated report was restored because it is outside the Todo 2 allowed write set. Receipt: `.omo/evidence/kugnus-refactoring-harness-replan/task-2/restored-generated-report.txt`.

## Gate results

| Gate | Command | Exit code | Classification | Evidence |
| --- | --- | ---: | --- | --- |
| `py_compile` | `python3 -m py_compile komsco-ai-gateway/komsco_ai_gateway/main.py komsco-ai-gateway/tests/test_health.py` | 0 | pass | `py_compile.command`, `py_compile.stdout`, `py_compile.stderr` |
| `pytest` | `komsco-ai-gateway/.venv/bin/python -m pytest komsco-ai-gateway/tests/test_health.py -q` | 1 | actual regression | `pytest.command`, `pytest.stdout`, `pytest.stderr`, `pytest.interpreter` |
| `answer_boundary` | `python3 scripts/verify-aiops-answer-boundary.py` | 1 | stale expectation | `answer_boundary.command`, `answer_boundary.stdout`, `answer_boundary.stderr` |
| `answer_experience` | `python3 scripts/verify-aiops-answer-experience.py` | 0 | pass | `answer_experience.command`, `answer_experience.stdout`, `answer_experience.stderr` |
| `markdown_ux` | `node scripts/verify-v029-chatbot-markdown-ux.cjs` | 1 | actual regression | `markdown_ux.command`, `markdown_ux.stdout`, `markdown_ux.stderr` |
| `action_history` | `node scripts/verify-v029-chatbot-action-history-flow.cjs` | 143 | environment/live dependency | `action_history.command`, `action_history.stdout`, `action_history.stderr`, `action_history.timeout` |
| `scenario_verify` | `task kugnus:scenario:verify` | 0 | pass | `scenario_verify.command`, `scenario_verify.stdout`, `scenario_verify.stderr` |

Raw exit-code ledger: `.omo/evidence/kugnus-refactoring-harness-replan/task-2/exit-codes.txt`

Durations: `.omo/evidence/kugnus-refactoring-harness-replan/task-2/durations.txt`

## Nonzero classifications

### `pytest`: actual regression

Observable: exit code 1, `12 failed, 226 passed in 3.31s`.

Evidence: `.omo/evidence/kugnus-refactoring-harness-replan/task-2/pytest.stdout`

Failed checks:

- `test_olm_operator_status_payload_exposes_v011_readiness_conditions`: expected `payload["phase"] == "Ready"`, observed `Progressing`.
- `test_chat_stream_unrestricted_executes_natural_scale_action`: authorization fallback assertion failed around `Bearer token` vs `Bearer test-token`.
- `test_rag_upload_safety_and_freshness_metadata_are_classified`: expected `safetyClass == "evidence-check"`, observed `approved-exec`.
- `test_build_ols_query_defaults_to_minimal_safe_prompt`: minimal safe prompt assertion failed.
- `test_chat_stream_handles_openshift_user_auth_401_without_raw_status`: expected subject result error handling, observed missing/empty result path.
- `test_pod_list_request_fallback_returns_list_instead_of_single_pod_analysis`: expected `문제 의심 Pod/Container` in fallback answer.
- `test_medium_risk_action_requires_separation_of_duties`: expected approval HTTP 409, observed 403.
- `test_approved_different_subject_can_execute_with_product_access`: expected execution HTTP 403, observed 503.
- `test_runbook_registry_allows_only_runbook_defined_action_steps`: runbook registry entries differ from expected set.
- `test_break_glass_profile_is_disabled_by_default_and_fixed_entrypoint_only`: missing `node_readonly_triage_v1` profile.
- `test_break_glass_request_records_disabled_status_without_job_submission`: `get_break_glass_profile` raised HTTP 400.
- `test_break_glass_api_rejects_arbitrary_command_input_and_records_request`: expected request HTTP 200, observed 400.

Reasoning: these are local unit/contract failures with deterministic assertions, not missing tooling or a live cluster dependency.

### `answer_boundary`: stale expectation

Observable: exit code 1.

Evidence:

- `.omo/evidence/kugnus-refactoring-harness-replan/task-2/answer_boundary.stderr`
- `scripts/verify-aiops-answer-boundary.py`
- `komsco-ai-gateway/komsco_ai_gateway/main.py`

Failure text: missing exact snippet `if decision != "action_proposal_only":\n        return ""`.

Current code has a nearby guard with an additional `pod_restart_rca` exception:

```text
if decision != "action_proposal_only" and task_type not in {"pod_restart_rca"}:
    return ""
```

Reasoning: the verifier is an exact string check for the older shape. Todo 2 does not decide whether the `pod_restart_rca` exception is correct; it records that this failure is currently a stale static expectation, not a syntax failure or missing dependency.

### `markdown_ux`: actual regression

Observable: exit code 1.

Evidence:

- `.omo/evidence/kugnus-refactoring-harness-replan/task-2/markdown_ux.stderr`
- `scripts/verify-v029-chatbot-markdown-ux.cjs`
- `komsco-ai-console-plugin/src/components/AssistantMessageContent.tsx`

Failure text: `Runbook follow-up section must use a controlled line renderer instead of raw markdown table layout`.

Reasoning: `AssistantMessageContent.tsx` has follow-up section IDs and CSS exists, but `renderRunbookLines` returns `AssistantMarkdown` immediately for nonempty section markdown. The controlled follow-up renderer expected by the verifier is not active.

### `action_history`: environment/live dependency

Observable: original gate exit code 143 after the exact process was terminated for exceeding the local lightweight-gate wait window; classification rerun with `timeout 20s` exited 124 with empty stdout/stderr.

Evidence:

- `.omo/evidence/kugnus-refactoring-harness-replan/task-2/action_history.timeout`
- `.omo/evidence/kugnus-refactoring-harness-replan/task-2/action_history_rerun.command`
- `.omo/evidence/kugnus-refactoring-harness-replan/task-2/action_history_rerun.stdout`
- `.omo/evidence/kugnus-refactoring-harness-replan/task-2/action_history_rerun.stderr`
- `.omo/evidence/kugnus-refactoring-harness-replan/task-2/action_history_console_url.stdout`
- `.omo/evidence/kugnus-refactoring-harness-replan/task-2/chrome_binary.stdout`

Reasoning: this script drives a real headless Chrome session against `http://localhost:9000/dashboards/aiops?codex_v=029-action-history` and can wait up to several minutes for assistant answer/action-history UI state. Chrome exists and the console URL returned HTTP 200, but the verifier did not complete within the local baseline window and produced no assertion text. This is classified as a live browser/UI dependency, not a product-code regression from this Todo.

Diagnostic rerun:

| Diagnostic | Command | Exit code | Classification | Evidence |
| --- | --- | ---: | --- | --- |
| `action_history_rerun` | `timeout 20s node scripts/verify-v029-chatbot-action-history-flow.cjs` | 124 | environment/live dependency | `action_history_rerun.command`, `action_history_rerun.stdout`, `action_history_rerun.stderr` |
| `action_history_console_url` | `curl -I --max-time 5 http://localhost:9000/dashboards/aiops?codex_v=029-action-history` | 0 | pass | `action_history_console_url.stdout`, `action_history_console_url.stderr` |
| `chrome_binary` | `/home/kugnus/.local/bin/google-chrome --version` | 0 | pass | `chrome_binary.stdout`, `chrome_binary.stderr` |

## Passing gates

- `py_compile`: exit code 0, no stdout/stderr.
- `answer_experience`: exit code 0, static contract checks passed.
- `scenario_verify`: exit code 0, report `docs/Ver.0.1.3/aiops-scenario-evaluation-report.json`, `scenarioCount: 13`, `passed: 13`, `failed: 0`, `negativeControlsPassed: true`.

## Adversarial notes

- `dirty_worktree`: probed by `git status --short` before the suite; existing dirty state preserved.
- `stale_state`: ruled out by running all listed commands live in this Todo and writing fresh stdout/stderr/exit-code artifacts.
- `hung_or_long_commands`: probed by `action_history`; timeout behavior recorded without killing unrelated processes.
- `misleading_success_output`: classification uses exit code and artifact files, not optimistic stdout.
- `flaky_tests`: `action_history` was rerun once only for classification; the original nonzero result remains recorded.
- `malformed_input`: ruled out because this Todo does not introduce or parse new external input.
- `prompt_injection`: ruled out because no untrusted prompt/document text is consumed for code or verifier changes.
- `cancel_resume`: ruled out because no resumable user workflow was modified.
- `repeated_interruptions`: ruled out because the suite completed after one controlled timeout intervention.

## Known gap classification

No nonzero command was classified as `known gap` in this baseline. The current nonzero results are classified as `actual regression`, `stale expectation`, or `environment/live dependency`.
