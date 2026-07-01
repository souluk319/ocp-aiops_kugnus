# Ver.0.2.1 Answer Quality Contract

Branch: `v0.2.1-aiops-answer-contract`
Base head: `28aa229`

## Goal

KOMSCO AI AGENT must answer OpenShift operational questions from observed runtime evidence first, and must not mix analysis-only answers with action approval or execution UI.

## Why This Version Exists

Ver.0.2.0 output looked AIOps-like, but the product boundary was not strict enough:

- An alert summary answer exposed action lifecycle UI (`Proposal`, `Sealed plan`, `Approval decision`).
- Runtime alert evidence and RAG/reference documents appeared at the same evidence level.
- Answer text said one evidence count while the UI footer showed another count.
- Old action records could appear under a new analysis answer.

Because these failures make the demo look plausible but untrustworthy, Ver.0.2.1 must lock the answer contract before adding more features.

## Reporting Rule

Do not stop at problem naming.
Do not end with passive agreement, sympathy, or a status-only sentence.
Every diagnostic response must end with a corrective route or a concrete recommendation.

Use this shape:

```text
This fails because <specific product boundary or evidence contract is broken>.
Therefore we should <specific corrective route>.
I recommend <small reversible implementation and verifier>.
```

Bad report:

```text
The worktree is dirty. It may not work.
```

Good report:

```text
The worktree is dirty, so changing Ver.0.2.0 in place will hide which change caused the answer regression.
Therefore we should branch to Ver.0.2.1 and put an answer-quality contract in front of the code fix.
I recommend fixing only the answer/action boundary first, then running the smallest gateway and UI verifier.
```

Forbidden endings:

- "맞습니다."
- "확인했습니다."
- "어렵습니다."
- "작업트리가 더럽습니다."
- "현재는 검증이 필요합니다."

Allowed only when followed by:

- the exact boundary that failed
- the route that avoids repeating it
- the next file, test, or verifier to run

## Acceptance Criteria

### AC-01 Runtime Evidence Alert Summary

Pass:

- User asks for recent OpenShift alerts, priorities, evidence, or next checks.
- Answer shows collected runtime evidence separately from additional checks.
- Answer says no mutation was performed.
- No inline `바로 해결`, `Proposal`, `Sealed plan`, or `Approval decision` card is shown.

Fail:

- An analysis-only alert summary exposes approval or execution controls.
- Past action records from another scenario appear below the new answer.

### AC-02 Evidence Layer Separation

Pass:

- Runtime evidence includes source type such as alert, node, pod, event, metric, or API response.
- RAG documents are labeled as reference/runbook evidence, not as live alert proof.
- Each high-priority alert has enough raw fields to verify: alert name, namespace or target, severity when available, status, and source.

Fail:

- PDF/runbook citations are presented as the direct proof that an alert is firing.
- Specific resource names are asserted without a runtime evidence ref.

### AC-03 Count Consistency

Pass:

- Text summary and evidence footer agree on collected, failed, and missing counts.
- If a source is optional, it is labeled optional and not counted as a missing required check.

Fail:

- Answer says `추가 확인 0건` while footer shows `추가 확인 1`.
- Table contains multiple "확인 필요" items while the summary says there are none without explaining the difference.

### AC-04 Action Boundary

Pass:

- `ActionProposal -> SealedActionPlan -> ApprovalDecision -> ExecutionRecord` appears only when the user asks for a change, action plan, approval, or execution.
- For analysis-only prompts, action lifecycle details may remain in the side rail audit area, but not under the answer as a recommended next click.

Fail:

- A pure analysis prompt gets an inline action lifecycle section.
- The UI title says `바로 해결` before cause confidence, scope, and rollback are clear.

### AC-05 Minimum Verifiers

Pass requires all applicable checks:

- Python syntax check for touched gateway code.
- TypeScript or targeted frontend check for touched console plugin code.
- A gateway test proving analysis-only alert answers do not emit the action contract text.
- A UI/unit verifier or focused test proving answer action cards are not shown unless the current answer explicitly carries an action contract.

### AC-06 Chat Transcript Storage

Pass:

- Every completed chat response stores a `ChatTranscriptRecord`.
- The record includes `conversationId`, `runId`, redacted `userMessage`, redacted `assistantAnswer`, `observedState`, `evidenceRefs`, `answerContract`, and linked action record refs.
- The Gateway record store persists transcripts under `chatTranscripts.json` when `KOMSCO_AI_RECORD_STORE_ENABLED=true`.
- The Gateway also appends each completed transcript as JSONL to `var/aiops/chat-transcripts.jsonl` by default, or to `KOMSCO_AI_CHAT_TRANSCRIPT_JSONL_PATH` when that env var is set.
- `/v1/aiops/status` exposes readable `records.chatTranscripts` so operators can inspect recent answer quality.
- The console Audit page exposes recent chat transcript records, not only audit/action lifecycle records.

Fail:

- Chat history exists only in React component state.
- Audit records store only message length and cannot reconstruct the actual answer.
- A user complaint cannot be tied back to the exact observed state and answer text.

## Not In Scope

- Do not edit protected Claude/user-authored scenario JSON files.
- Do not rewrite Ver.0.2.0 documents to hide the failure.
- Do not run cluster mutation commands.
- Do not mark completion without a verifier result.
