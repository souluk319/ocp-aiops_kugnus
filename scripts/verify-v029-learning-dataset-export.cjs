#!/usr/bin/env node

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const readFile = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');
const assert = (condition, message, evidence = undefined) => {
  if (!condition) {
    const detail = evidence === undefined ? '' : `\n${JSON.stringify(evidence, null, 2)}`;
    throw new Error(`${message}${detail}`);
  }
};

const exporter = readFile('scripts/export-aiops-learning-dataset.cjs');
const taskfile = readFile('Taskfile.yml');

assert(exporter.includes("kind: 'AIOpsLearningDataset'"), 'exporter must emit AIOpsLearningDataset');
assert(exporter.includes('chatTranscripts'), 'exporter must include chat transcripts');
assert(exporter.includes('chatFeedback'), 'exporter must include chat feedback');
assert(exporter.includes('actionProposals'), 'exporter must include action proposals');
assert(exporter.includes('sealedActionPlans'), 'exporter must include sealed action plans');
assert(exporter.includes('approvalDecisions'), 'exporter must include approval decisions');
assert(exporter.includes('executionRecords'), 'exporter must include execution records');
assert(exporter.includes('scenarioEvaluation'), 'exporter must include scenario evaluation results');
assert(exporter.includes('bearerTokensRemoved: true'), 'exporter must declare bearer token redaction');
assert(exporter.includes('publicUrlsRedacted: true'), 'exporter must redact public URLs for closed-network datasets');
assert(exporter.includes('AIOPS_BEARER_TOKEN'), 'exporter must support deployed Gateway bearer access');
assert(exporter.includes('--status-file'), 'exporter must support offline status-file verification');
assert(taskfile.includes('kugnus:aiops:learning-dataset'), 'Taskfile must expose a learning dataset export target');

const tmpDir = path.join(root, '.tmp-kugnus-demo');
fs.mkdirSync(tmpDir, { recursive: true });

const transcriptPath = path.join(tmpDir, 'learning-sample-transcripts.jsonl');
const statusPath = path.join(tmpDir, 'learning-sample-status.json');
const outputPath = path.join(tmpDir, 'aiops-learning-dataset.verify.json');
const outputJsonlPath = path.join(tmpDir, 'aiops-learning-dataset.verify.jsonl');

const transcriptRecord = {
  apiVersion: 'aiops.komsco/v1',
  kind: 'ChatTranscriptRecord',
  metadata: {
    createdAt: '2026-07-08T00:00:00Z',
    name: 'chat-transcript-verify',
  },
  spec: {
    assistantAnswer:
      '확인 결과입니다. token=should-not-leak Bearer abc.def.ghi https://docs.example.invalid/runbook',
    conversationId: 'inc-learning-verify',
    evidenceRefs: {
      collected: [{ evidenceType: 'event' }, { evidenceType: 'log' }],
      failed: [],
      missing: [{ type: 'metric' }],
    },
    observedState: {
      evidenceSummary: { collectedCount: 2, failedCount: 0, missingCount: 1 },
      rcaContextDigest: 'sha256:rca',
      rcaResult: { cause_candidates: ['CrashLoopBackOff'], confidence: 0.72 },
      taskType: 'openshift_operational_question',
      toolPlanDigest: 'sha256:tool',
    },
    policy: {
      decision: 'allow_evidence_collection',
      mutationAllowed: false,
      risk: 'low',
    },
    requestId: 'req-learning-verify',
    runId: 'run-learning-verify',
    status: 'completed',
    userMessage: 'CrashLoopBackOff 원인을 확인해줘',
    workflow: {
      incidentId: 'inc-learning-verify',
    },
  },
};

const statusPayload = {
  apiVersion: 'aiops.komsco/v1',
  kind: 'AIOpsRuntimeStatus',
  metadata: { generatedAt: '2026-07-08T00:00:01Z', name: 'runtime-status' },
  spec: {
    capabilities: {
      actionExecutorConfigured: true,
      mutationsEnabled: true,
      recordStoreEnabled: true,
    },
    records: {
      auditRecords: [{ kind: 'AuditRecord', metadata: { name: 'audit-verify' }, spec: {} }],
      chatFeedback: [
	        {
	          kind: 'ChatFeedback',
	          metadata: { createdAt: '2026-07-08T00:00:02Z', name: 'feedback-verify' },
          spec: {
            assistantAnswer:
              'CrashLoopBackOff 원인은 이전 로그와 Event를 확인한 뒤 승인 가능한 Action Plan으로 분리해야 합니다.',
            conversationId: 'inc-learning-verify',
            messageId: 'assistant-message-1',
            optionalComment: '조치 전 검증 설명은 좋음',
            rating: 'up',
            route: 'gateway',
            submittedAt: '2026-07-08T00:00:02Z',
            userMessage: 'CrashLoopBackOff 원인을 확인해줘',
          },
        },
      ],
      chatTranscripts: [],
      actionProposals: [
        {
          kind: 'ActionProposalRecord',
          metadata: { createdAt: '2026-07-08T00:00:03Z', name: 'proposal-verify' },
          spec: {
            candidateActionRequest: {
              incidentId: 'inc-learning-verify',
              runId: 'run-learning-verify',
              action: { toolName: 'pod_diagnostic_review' },
            },
          },
        },
      ],
      sealedActionPlans: [
        {
          kind: 'SealedActionPlanRecord',
          metadata: { createdAt: '2026-07-08T00:00:04Z', name: 'plan-verify' },
          spec: {
            sealedActionPlan: {
              action: { toolName: 'pod_diagnostic_review' },
              incidentId: 'inc-learning-verify',
              runId: 'run-learning-verify',
            },
          },
        },
      ],
      approvalDecisions: [
        {
          kind: 'ApprovalDecisionRecord',
          metadata: { createdAt: '2026-07-08T00:00:05Z', name: 'approval-verify' },
          spec: {
            approvalDecision: {
              action: { toolName: 'pod_diagnostic_review' },
              incidentId: 'inc-learning-verify',
              runId: 'run-learning-verify',
              status: 'approved',
            },
          },
        },
      ],
      executionRecords: [
        {
          kind: 'ExecutionRecord',
          metadata: { createdAt: '2026-07-08T00:00:06Z', name: 'execution-verify' },
          spec: {
            approvalId: 'approval-verify',
            executorTrace: { reviewOnly: true, toolName: 'pod_diagnostic_review' },
            mutationOutcome: { status: 'review_recorded' },
            runId: 'run-learning-verify',
          },
        },
      ],
    },
  },
};

fs.writeFileSync(transcriptPath, `${JSON.stringify(transcriptRecord)}\n`, 'utf8');
fs.writeFileSync(statusPath, `${JSON.stringify(statusPayload, null, 2)}\n`, 'utf8');

execFileSync(
  'node',
  [
    'scripts/export-aiops-learning-dataset.cjs',
    '--status-file',
    statusPath,
    '--transcripts',
    transcriptPath,
    '--scenario-report',
    'docs/Ver.0.1.3/aiops-scenario-evaluation-report.json',
    '--output',
    outputPath,
    '--limit',
    '5',
  ],
  { cwd: root, stdio: 'pipe' },
);

const dataset = JSON.parse(fs.readFileSync(outputPath, 'utf8'));
assert(dataset.kind === 'AIOpsLearningDataset', 'dataset kind must be AIOpsLearningDataset', dataset);
assert(dataset.metadata.counts.records === 1, 'dataset must include one learning record', dataset.metadata.counts);
assert(dataset.metadata.counts.chatFeedback === 1, 'dataset must count chat feedback', dataset.metadata.counts);
assert(dataset.metadata.counts.executionRecords === 1, 'dataset must count execution records', dataset.metadata.counts);
assert(dataset.spec.records[0].feedback.length === 1, 'learning record must link feedback', dataset.spec.records[0]);
assert(dataset.spec.records[0].actionSummary.count === 4, 'learning record must link full action lifecycle', dataset.spec.records[0].actionSummary);
assert(dataset.spec.records[0].evidenceSummary.collectedCount === 2, 'learning record must preserve evidence summary', dataset.spec.records[0].evidenceSummary);
assert(dataset.spec.scenarioEvaluation.status === 'loaded', 'dataset must load scenario evaluation report', dataset.spec.scenarioEvaluation);
assert(dataset.spec.scenarioEvaluation.scenarioCount >= 1, 'scenario evaluation must include scenario count', dataset.spec.scenarioEvaluation);
assert(dataset.spec.privacy.redactionApplied === true, 'dataset must declare redaction', dataset.spec.privacy);

const rendered = JSON.stringify(dataset);
assert(!rendered.includes('should-not-leak'), 'dataset must redact secret-looking assignment');
assert(!rendered.includes('Bearer abc.def.ghi'), 'dataset must redact bearer token');
assert(!rendered.includes('https://docs.example.invalid'), 'dataset must redact public URL');

execFileSync(
  'node',
  [
    'scripts/export-aiops-learning-dataset.cjs',
    '--status-file',
    statusPath,
    '--transcripts',
    transcriptPath,
    '--format',
    'jsonl',
    '--output',
    outputJsonlPath,
    '--limit',
    '5',
  ],
  { cwd: root, stdio: 'pipe' },
);
const jsonlLines = fs.readFileSync(outputJsonlPath, 'utf8').trim().split('\n');
assert(jsonlLines.length === 1, 'jsonl export must write one learning record line', jsonlLines);
assert(JSON.parse(jsonlLines[0]).source === 'chat_transcript', 'jsonl line must be a learning record');

console.log('v0.2.9 learning dataset export verifier PASS');
