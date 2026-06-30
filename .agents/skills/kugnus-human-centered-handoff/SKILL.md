---
name: kugnus-human-centered-handoff
description: Use for this Kugnus repo when continuing Claude handoffs, writing beginner-facing guides, writing detailed strategy briefs, responding to repeated user frustration, or deciding whether to edit protected artifacts. Triggers include 초보자, 웹북, beginner guide, strategy brief, Claude handoff, AGENTS.md, 제자리걸음, 어렵다, 이해 안 된다, 회사 서버 배포, OLM install, and KOMSCO AIOps documentation.
---

# Kugnus Human-Centered Handoff

Use this skill to avoid repeating the repo's known failure mode: technically dense output that does not help the user act or decide.

## First Move

- Read repo `AGENTS.md`.
- Treat `docs/Komsco_ai_agent_final.pdf` as the KOMSCO AIOps official source document before judging architecture, product scope, Lightspeed/provider structure, agent role, customer-facing behavior, or roadmap claims.
- Check `git status --short`.
- Treat Claude/user-authored artifacts as protected.
- Identify the deliverable type before editing.
- If the user is upset or says the output is hard to understand, stop producing more of the same and switch to benchmark comparison.

## Source Of Truth

Evidence order for KOMSCO AIOps:

- `docs/Komsco_ai_agent_final.pdf` wins over all derived notes and HTML briefs.
- Current repo code, Taskfile, scripts, tests, generated reports, and explicit cluster command output come next.
- Claude/user-authored HTML briefs and beginner guides are protected benchmark artifacts, but they are not the official product source when they conflict with the PDF.
- Vendor docs and model cards are used to verify external products and current facts.

When a brief says "replace Lightspeed with on-prem LLM" but the official PDF says "Lightspeed provider uses an on-prem LLM", call the brief imprecise and preserve the PDF's meaning.

## Protected Benchmark Artifacts

Read, do not rewrite, unless the user explicitly asks:

- `docs/aiops-beginner-guide.html` — benchmark for beginner teaching.
- `docs/Ver.0.1.8/aiops-llm-strategy-brief.html` — benchmark for detailed technical strategy briefs.
- `docs/version-progress-book.html` — progress ledger, not the benchmark for beginner quality.
- Claude-created scenario JSON files under `evals/aiops-scenarios/`.

## Beginner Guide Workflow

Before writing beginner docs, read the relevant section of `docs/aiops-beginner-guide.html`.

The output must let the user safely do one thing:

- what this project is
- what phase we are in
- what one safe command to run first
- what the command does
- what output lines to look for
- what must not be run yet
- what server effect each command has
- what to inspect if it fails

Use plain Korean first, then technical term. Separate "my computer test" from "company server install" every time.

## Strategy Brief Workflow

Before writing strategy/architecture/model roadmap docs, read the relevant section of `docs/Ver.0.1.8/aiops-llm-strategy-brief.html`.

The output must connect:

- current implementation status
- remaining gaps
- current end-to-end flow
- target end-to-end architecture
- named roles and responsibilities
- candidate options
- why each option exists
- tradeoffs
- data/training/evaluation plan
- version roadmap
- measurable metrics

Do not shrink the brief into generic AI strategy. The user wants dense but navigable detail.

## Failure Recovery

When stuck:

- Reproduce the failure with the smallest command.
- Read the exact error.
- Search with `rg`.
- Check whether the evaluator, glue code, task wiring, or report is stale before editing protected artifacts.
- Make one reversible change.
- Run the smallest relevant verifier.
- Report exact pass/fail.

If the user compares the work to Claude, do not argue. Use Claude artifacts as the benchmark and move the fix to integration code unless explicitly permitted.
