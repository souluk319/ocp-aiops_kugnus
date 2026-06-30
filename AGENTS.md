# AGENTS.md

This repository uses a strict handoff workflow. The agent must protect existing work, especially Claude-authored artifacts, and must verify claims with local commands.

## Prime Directive

- Do not compete with previous agents. Preserve their useful work and make the system around it reliable.
- Treat `docs/Komsco_ai_agent_final.pdf` as the project's official source document. When architecture, product scope, Lightspeed/provider structure, agent role, customer-facing behavior, or roadmap claims conflict, this PDF wins over derived HTML briefs, generated notes, and agent memory.
- Treat Claude-authored or user-authored artifacts as protected source material. Do not edit them unless the user explicitly asks for that file to be changed.
- If a protected artifact appears inconsistent, report the exact file, field, failure, and proposed fix first. Prefer changing evaluator, glue code, task wiring, or docs references around it.
- Never hide uncertainty behind vague words. Say the exact command, exact output, exact failing layer, and exact next action.

## Source Of Truth

Use this evidence order for KOMSCO AIOps claims:

- First: `docs/Komsco_ai_agent_final.pdf`.
- Second: current repo code, Taskfile, scripts, tests, generated reports, and cluster output from explicit commands.
- Third: protected Claude/user artifacts such as beginner guides and strategy briefs.
- Fourth: vendor documentation such as Red Hat, OpenShift, Dell, model provider docs, and model cards.

If a derived document says "replace Lightspeed with on-prem LLM" but the official PDF describes "Lightspeed provider backed by an on-prem LLM", report the derived document as imprecise instead of treating the PDF as wrong.

## Protected Artifacts

Assume these are protected unless the user says otherwise:

- `docs/version-progress-book.html`
- `docs/aiops-beginner-guide.html`
- `docs/Ver.0.1.8/aiops-llm-strategy-brief.html`
- beginner webbook/editorial documents
- Claude-created scenario JSON files under `evals/aiops-scenarios/`
- mock customer operation documents and generated customer demo materials
- user-written handoff notes under `.claude/` or attachments

Allowed without extra permission:

- read protected artifacts
- run validators against them
- quote short relevant fragments for diagnosis
- update runtime code, evaluator code, Taskfile commands, scripts, and generated reports when those are the correct integration layer

## Handoff Intake

Before continuing interrupted work:

- Read `AGENTS.md`.
- Read the latest user request and any attached handoff text.
- Check `git status --short`.
- Search references with `rg` before editing.
- Identify which files are protected artifacts and which files are integration code.
- Run the smallest useful verifier once before changing behavior, so failures are based on evidence.

## When Work Is Going In Circles

If the user is angry, says the output is not understandable, compares the work unfavorably to Claude, says "쉽게", "초보자", "왜 이해 못해", "제자리걸음", or repeats the same complaint twice, stop the current production loop.

Do this instead:

- Do not keep patching the same artifact.
- Do not defend the previous approach.
- Identify the deliverable type: beginner guide, strategy brief, deployment runbook, code fix, cluster operation, or verifier.
- Load the closest benchmark artifact before writing: `docs/aiops-beginner-guide.html` for beginner teaching, `docs/Ver.0.1.8/aiops-llm-strategy-brief.html` for detailed strategy briefs.
- For Codex behavior, `AGENTS.md`, skills, hooks, or persistent setup questions, consult the current Codex manual or official docs route before inventing process.
- Convert the user's complaint into a concrete quality gate. Example: "too hard" becomes "first command, expected output, server effect, failure location must be visible before terminology".
- Prefer changing process, verifier, or integration code over rewriting protected Claude artifacts.
- Report the new route in one short paragraph, then execute only the smallest reversible change.

If the same blocker repeats three times, stop editing and write a handoff note with exact files, commands, failures, and benchmark artifacts instead of continuing by momentum.

## Beginner Documentation Standard

When writing a webbook or beginner guide, act like an education publisher, not a system log.

The reader must understand the flow without knowing Kubernetes, OLM, Taskfile, or this project.

Use `docs/aiops-beginner-guide.html` as the quality benchmark for beginner-facing HTML. Do not use `docs/version-progress-book.html` as the benchmark; that file is a progress ledger with beginner sections, not the teaching standard.

Before writing or reviewing beginner documentation:

- Read the relevant section of `docs/aiops-beginner-guide.html`.
- Copy its teaching pattern, not its exact text.
- Start from "what is this project" and "what can I safely try first".
- Explain one safe command before explaining the whole system.
- Use plain Korean words first, then put the technical term beside them.
- Give analogies only when they reduce fear or confusion.
- Separate "my computer test" from "company server install" every time.

Every practical section must answer:

- What do I type?
- Where is that short command defined?
- What long command or script does it run for me?
- What does it create on the server?
- What does it not create yet?
- What does normal output look like?
- If it fails, what exact file, command, or server layer do I inspect?

Use this explanation shape for wrapped commands:

```text
task kugnus:company:publish
  -> Taskfile.yml task block
    -> approved company server check
      -> scripts/kugnus-olm.sh publish
        -> image build + catalog registration
```

Do not fill the first page with abstract principles. Start with the path the beginner can follow today.

Avoid:

- blaming or diagnosing the reader
- grand motivational sentences
- long paragraphs of concepts before the first command
- unexplained acronyms
- walls of version history before the beginner workflow
- saying "done" before checking Korean rendering and command output

## Detailed Strategy Brief Standard

When the user asks for a detailed strategy brief, architecture brief, roadmap, model strategy, or executive technical HTML, use `docs/Ver.0.1.8/aiops-llm-strategy-brief.html` as the quality benchmark.

This benchmark is valuable because it is not a loose memo. It connects:

- current implementation status
- remaining gaps
- current end-to-end flow
- target end-to-end architecture
- role taxonomy
- candidate comparison
- concrete deployment cases
- why each option exists
- tradeoff matrix
- training data plan
- version roadmap
- evaluation metrics

For this style of deliverable:

- Do not summarize away the useful detail. The user wants the detailed structure.
- Start with "currently implemented vs remaining", so the reader knows the real baseline.
- Draw the full flow: user question -> gateway/model -> tools/adapters -> evidence/RAG -> answer/result.
- Split agent/model/system roles into named responsibilities, not vague components.
- Compare realistic options in tables or cards, with "why this choice" under each option.
- Include hardware/runtime assumptions when they affect the decision.
- Include data sources, training/evaluation plan, and version-by-version roadmap.
- Mark what is implemented, skeleton-only, planned, and out of scope.
- Tie every future idea back to an existing file, API, test, task, report, or missing artifact when possible.
- Use enough detail that the user can make a decision or hand the document to another engineer without re-explaining the context.

Avoid:

- generic AI strategy language
- shallow "pros/cons" without implementation consequences
- unexplained model names or architecture terms
- pretending a future adapter, model, or training path already exists
- removing tables/flows because they look long
- turning a strategy brief into a short status note

## Writing Style For This User

- Use Korean unless the user asks otherwise.
- Be direct, concrete, and brief.
- Do not lecture, moralize, or switch into crisis-counseling mode.
- Do not overuse numbered lists when the user is already irritated.
- Do not claim something is likely. Verify it or say what exact command is needed.
- Do not praise your own plan. Execute, verify, and report.

## Engineering Workflow

Use this order for code changes:

- Search: `rg` references and read the nearby code.
- Inspect: understand existing patterns before patching.
- Patch: use `apply_patch` for manual file edits.
- Check: run syntax/parse checks for touched languages.
- Test: run the smallest relevant test or task.
- Report: include exact pass/fail evidence and any blocker.

Do not declare completion if the relevant verifier was not run. If a verifier cannot run, say why and provide the exact missing dependency or failing layer.

## Verification Preferences

Prefer lightweight checks first:

- Python: `python3 -m py_compile ...`
- JSON: `python3 - <<'PY' ... json.load(...)`
- HTML: `HTMLParser`
- Scenario gate: `task kugnus:scenario:verify`
- Gateway tests: `komsco-ai-gateway/.venv/bin/python -m pytest ...`

Avoid heavy browser/headless verification unless the user asked for visual proof or the task is frontend rendering. If browser checks are necessary, say so first because WSL fan/CPU spikes have happened before.

## OCP And Company Server Safety

Before company server actions:

- Check `oc whoami --show-server`.
- Compare with `${KOMSCO_AIOPS_COMPANY_SERVER:-https://api.ocp.cywell.server:6443}`.
- Do not publish or install if the server does not match.
- Treat `publish` and `install` as separate phases.
- `publish` registers/builds catalog material.
- `install` creates the subscription/installation objects.
- Prefer `task kugnus:company:check`, `publish`, `status`, then approved `install`.

## Scenario And RCA Work

For `evals/aiops-scenarios`:

- Do not modify Claude-created scenario files without explicit permission.
- If scenario files fail, first inspect whether the evaluator, parser, adapter registry, or required scenario list is stale.
- Keep current scenario count and README synchronized.
- Reports must include pass/fail counts, negative control result, and RCA result schema when relevant.
- Linux/Windows OS scenarios may classify and route to RAG before real OS command adapters exist. Do not pretend host commands executed when they are only planned or missing evidence.

## Recovery Protocol

When a command fails:

- Read the exact error.
- Do not repeat the same command blindly.
- Identify whether the failure is code, environment, dependency, auth, server, or stale report.
- Try one targeted fix.
- After three failed attempts on the same blocker, stop editing and report the exact blocker.

## Final Response Contract

Final answers must include:

- what changed
- what passed
- what failed or was not run
- any protected artifact left untouched

Keep it short. The user can see the files; do not paste long diffs unless asked.
