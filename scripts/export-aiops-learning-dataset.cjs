#!/usr/bin/env node

const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

const DEFAULT_STATUS_URL =
  process.env.AIOPS_LEARNING_STATUS_URL ||
  `${(process.env.AIOPS_GATEWAY_URL || 'http://127.0.0.1:5174').replace(/\/+$/, '')}/v1/aiops/status`;
const DEFAULT_TRANSCRIPTS_PATH = 'komsco-ai-gateway/var/aiops/chat-transcripts.jsonl';
const DEFAULT_SCENARIO_REPORT = 'docs/Ver.0.1.3/aiops-scenario-evaluation-report.json';

const usage = () => `Usage:
  node scripts/export-aiops-learning-dataset.cjs [--url URL] [--status-file FILE] [--transcripts FILE] [--scenario-report FILE] [--format json|jsonl] [--output FILE] [--limit N]

Purpose:
  Export a sanitized AIOpsLearningDataset from chat transcripts, feedback, action/audit records, and scenario evaluation results.

Environment:
  AIOPS_LEARNING_STATUS_URL  Full /v1/aiops/status URL
  AIOPS_GATEWAY_URL          Gateway base URL, default http://127.0.0.1:5174
  AIOPS_BEARER_TOKEN         Optional bearer token for deployed Gateway access

Examples:
  node scripts/export-aiops-learning-dataset.cjs --output .tmp-kugnus-demo/aiops-learning-dataset.json
  AIOPS_BEARER_TOKEN="$(oc whoami -t)" node scripts/export-aiops-learning-dataset.cjs --url http://127.0.0.1:18080/v1/aiops/status --limit 50
`;

const parseArgs = (argv) => {
  const options = {
    format: 'json',
    help: false,
    limit: 100,
    maxTextChars: 12000,
    offline: false,
    output: '',
    scenarioReport: DEFAULT_SCENARIO_REPORT,
    statusFile: '',
    strict: false,
    transcripts: DEFAULT_TRANSCRIPTS_PATH,
    url: DEFAULT_STATUS_URL,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    const nextValue = () => argv[++i] || '';
    if (arg === '--help' || arg === '-h') options.help = true;
    else if (arg === '--format') options.format = nextValue();
    else if (arg.startsWith('--format=')) options.format = arg.slice('--format='.length);
    else if (arg === '--limit') options.limit = Number(nextValue());
    else if (arg.startsWith('--limit=')) options.limit = Number(arg.slice('--limit='.length));
    else if (arg === '--max-text-chars') options.maxTextChars = Number(nextValue());
    else if (arg.startsWith('--max-text-chars=')) options.maxTextChars = Number(arg.slice('--max-text-chars='.length));
    else if (arg === '--offline') options.offline = true;
    else if (arg === '--output') options.output = nextValue();
    else if (arg.startsWith('--output=')) options.output = arg.slice('--output='.length);
    else if (arg === '--scenario-report') options.scenarioReport = nextValue();
    else if (arg.startsWith('--scenario-report=')) options.scenarioReport = arg.slice('--scenario-report='.length);
    else if (arg === '--status-file') options.statusFile = nextValue();
    else if (arg.startsWith('--status-file=')) options.statusFile = arg.slice('--status-file='.length);
    else if (arg === '--strict') options.strict = true;
    else if (arg === '--transcripts') options.transcripts = nextValue();
    else if (arg.startsWith('--transcripts=')) options.transcripts = arg.slice('--transcripts='.length);
    else if (arg === '--url') options.url = nextValue();
    else if (arg.startsWith('--url=')) options.url = arg.slice('--url='.length);
    else throw new Error(`Unknown argument: ${arg}`);
  }

  if (!['json', 'jsonl'].includes(options.format)) {
    throw new Error(`Unsupported format: ${options.format}`);
  }
  if (!Number.isFinite(options.limit) || options.limit < 1) {
    throw new Error('--limit must be a positive number');
  }
  if (!Number.isFinite(options.maxTextChars) || options.maxTextChars < 200) {
    throw new Error('--max-text-chars must be at least 200');
  }
  return options;
};

const asObject = (value) =>
  value && typeof value === 'object' && !Array.isArray(value) ? value : {};
const asArray = (value) => (Array.isArray(value) ? value : []);
const asText = (value) => (value == null ? '' : String(value));

const SENSITIVE_KEY_RE = /(authorization|bearer|token|password|passwd|secret|clientSecret|apiKey|session|cookie)/i;
const BEARER_RE = /Bearer\s+[A-Za-z0-9._~+/=-]+/g;
const SECRET_ASSIGNMENT_RE =
  /\b(token|password|passwd|secret|api[_-]?key|client[_-]?secret)\s*[:=]\s*["']?[^"'\s,;]+/gi;
const PUBLIC_URL_RE = /\bhttps?:\/\/[^\s)>"']+/gi;

const redactString = (value) =>
  asText(value)
    .replace(BEARER_RE, 'Bearer [redacted]')
    .replace(SECRET_ASSIGNMENT_RE, (match) => `${match.split(/[:=]/)[0]}=[redacted]`)
    .replace(PUBLIC_URL_RE, '[url-redacted]');

const truncate = (value, maxTextChars) => {
  const text = redactString(value);
  if (text.length <= maxTextChars) return text;
  return `${text.slice(0, maxTextChars)}…[truncated ${text.length - maxTextChars} chars]`;
};

const sanitize = (value, maxTextChars, keyHint = '') => {
  if (value == null || typeof value === 'number' || typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    return SENSITIVE_KEY_RE.test(keyHint) ? '[redacted]' : truncate(value, maxTextChars);
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitize(item, maxTextChars, keyHint));
  }
  if (typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value).map(([key, item]) => [
        key,
        SENSITIVE_KEY_RE.test(key) ? '[redacted]' : sanitize(item, maxTextChars, key),
      ]),
    );
  }
  return String(value);
};

const sha256 = (value) =>
  `sha256:${crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex')}`;

const readJsonFile = (filePath, warnings, label) => {
  if (!filePath || !fs.existsSync(filePath)) {
    if (filePath) warnings.push(`${label} not found: ${filePath}`);
    return null;
  }
  try {
    return JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (error) {
    warnings.push(`${label} parse failed: ${filePath}: ${error.message}`);
    return null;
  }
};

const readJsonlFile = (filePath, warnings, label, limit) => {
  if (!filePath || !fs.existsSync(filePath)) {
    if (filePath) warnings.push(`${label} not found: ${filePath}`);
    return [];
  }
  const rows = [];
  const lines = fs.readFileSync(filePath, 'utf8').split(/\r?\n/).filter(Boolean);
  for (const line of lines.slice(-limit * 3)) {
    try {
      rows.push(JSON.parse(line));
    } catch (error) {
      warnings.push(`${label} JSONL line skipped: ${error.message}`);
    }
  }
  return rows.slice(-limit);
};

const fetchStatus = async (url) => {
  const headers = { Accept: 'application/json' };
  if (process.env.AIOPS_BEARER_TOKEN) {
    headers.Authorization = `Bearer ${process.env.AIOPS_BEARER_TOKEN}`;
  }
  const response = await fetch(url, { headers });
  if (!response.ok) {
    const body = await response.text();
    throw new Error(`${url} -> ${response.status} ${response.statusText}: ${body.slice(0, 300)}`);
  }
  return response.json();
};

const metadataName = (record) => asText(asObject(record.metadata).name).trim();
const createdAt = (record) => asText(asObject(record.metadata).createdAt).trim();
const specOf = (record) => asObject(record.spec);

const mergeRecords = (...lists) => {
  const map = new Map();
  for (const list of lists) {
    for (const record of asArray(list)) {
      const key = metadataName(record) || sha256(record);
      map.set(key, record);
    }
  }
  return Array.from(map.values()).sort((left, right) => createdAt(left).localeCompare(createdAt(right)));
};

const evidenceSummary = (spec) => {
  const observed = asObject(spec.observedState);
  const summary = asObject(observed.evidenceSummary);
  const refs = asObject(spec.evidenceRefs);
  const collected = asArray(refs.collected);
  const failed = asArray(refs.failed);
  const missing = asArray(refs.missing);
  return {
    collectedCount: Number(summary.collectedCount ?? collected.length) || 0,
    failedCount: Number(summary.failedCount ?? failed.length) || 0,
    missingCount: Number(summary.missingCount ?? missing.length) || 0,
    evidenceTypes: collected
      .map((item) => asText(asObject(item).evidenceType || asObject(item).type).trim())
      .filter(Boolean)
      .slice(0, 12),
  };
};

const feedbackMatchesTranscript = (feedback, transcriptSpec) => {
  const feedbackSpec = specOf(feedback);
  const conversationId = asText(transcriptSpec.conversationId);
  return conversationId && asText(feedbackSpec.conversationId) === conversationId;
};

const actionRecordRunId = (record) => {
  const spec = specOf(record);
  const candidate = asObject(spec.candidateActionRequest);
  const plan = asObject(spec.sealedActionPlan);
  const approval = asObject(spec.approvalDecision);
  return (
    asText(spec.runId) ||
    asText(candidate.runId) ||
    asText(plan.runId) ||
    asText(approval.runId)
  );
};

const actionRecordIncidentId = (record) => {
  const spec = specOf(record);
  const candidate = asObject(spec.candidateActionRequest);
  const plan = asObject(spec.sealedActionPlan);
  const approval = asObject(spec.approvalDecision);
  return (
    asText(spec.incidentId) ||
    asText(candidate.incidentId) ||
    asText(plan.incidentId) ||
    asText(approval.incidentId)
  );
};

const actionRecordToolName = (record) => {
  const spec = specOf(record);
  const candidate = asObject(spec.candidateActionRequest);
  const candidateAction = asObject(candidate.action);
  const plan = asObject(spec.sealedActionPlan);
  const planAction = asObject(plan.action);
  const approval = asObject(spec.approvalDecision);
  const approvalAction = asObject(approval.action);
  const trace = asObject(spec.executorTrace);
  return asText(candidateAction.toolName || planAction.toolName || approvalAction.toolName || trace.toolName || record.kind);
};

const actionRecordPhase = (record) => {
  const spec = specOf(record);
  const status = asObject(spec.status);
  const approval = asObject(spec.approvalDecision);
  const mutation = asObject(spec.mutationOutcome);
  return asText(status.phase || approval.status || mutation.status || 'recorded');
};

const actionRecordsForTranscript = (actionRecords, transcriptSpec) => {
  const runId = asText(transcriptSpec.runId);
  const incidentId = asText(asObject(transcriptSpec.workflow).incidentId || transcriptSpec.conversationId);
  return actionRecords.filter((record) => {
    const recordRunId = actionRecordRunId(record);
    const recordIncidentId = actionRecordIncidentId(record);
    return (runId && recordRunId === runId) || (incidentId && recordIncidentId === incidentId);
  });
};

const summarizeActions = (records) => ({
  count: records.length,
  stages: records.map((record) => record.kind || 'Record').slice(0, 12),
  tools: records.map(actionRecordToolName).filter(Boolean).slice(0, 12),
  phases: records.map(actionRecordPhase).filter(Boolean).slice(0, 12),
  recordNames: records.map(metadataName).filter(Boolean).slice(0, 12),
});

const transcriptToLearningRecord = (record, context, options) => {
  const spec = specOf(record);
  const observed = asObject(spec.observedState);
  const feedback = context.feedback.filter((item) => feedbackMatchesTranscript(item, spec));
  const linkedActions = actionRecordsForTranscript(context.actionRecords, spec);
  const cleanRecord = sanitize(
    {
      id: metadataName(record) || asText(spec.requestId) || sha256(record),
      source: 'chat_transcript',
      createdAt: createdAt(record),
      taskType: asText(observed.taskType || spec.taskType || 'unknown'),
      prompt: asText(spec.userMessage),
      assistantAnswer: asText(spec.assistantAnswer),
      answerContract: spec.answerContract || spec.answerMode || '',
      toolPlanDigest: asText(spec.toolPlanDigest || observed.toolPlanDigest),
      rcaContextDigest: asText(spec.rcaContextDigest || observed.rcaContextDigest),
      rcaResult: asObject(observed.rcaResult),
      evidenceSummary: evidenceSummary(spec),
      feedback: feedback.map((item) => ({
        feedbackId: metadataName(item),
        rating: asText(specOf(item).rating),
        optionalComment: asText(specOf(item).optionalComment),
        submittedAt: asText(specOf(item).submittedAt || createdAt(item)),
      })),
      actionSummary: summarizeActions(linkedActions),
      safety: {
        decision: asText(asObject(spec.policy).decision),
        mutationAllowed: asObject(spec.policy).mutationAllowed === true,
        risk: asText(asObject(spec.policy).risk),
      },
      labels: {
        answerMode: asText(spec.answerMode),
        conversationId: asText(spec.conversationId),
        requestId: asText(spec.requestId),
        runId: asText(spec.runId),
        status: asText(spec.status),
      },
    },
    options.maxTextChars,
  );
  return { ...cleanRecord, digest: sha256(cleanRecord) };
};

const feedbackOnlyRecords = (feedback, options) =>
  feedback.map((record) => {
    const spec = specOf(record);
    const cleanRecord = sanitize(
      {
        id: metadataName(record) || sha256(record),
        source: 'chat_feedback',
        createdAt: createdAt(record),
        taskType: 'feedback_only',
        prompt: '',
        assistantAnswer: '',
        answerContract: asText(spec.answerContract),
        evidenceSummary: { collectedCount: 0, failedCount: 0, missingCount: 0, evidenceTypes: [] },
        feedback: [
          {
            feedbackId: metadataName(record),
            optionalComment: asText(spec.optionalComment),
            rating: asText(spec.rating),
            submittedAt: asText(spec.submittedAt || createdAt(record)),
          },
        ],
        actionSummary: summarizeActions([]),
        safety: { decision: '', mutationAllowed: false, risk: '' },
        labels: {
          conversationId: asText(spec.conversationId),
          messageId: asText(spec.messageId),
          mode: asText(spec.mode),
          route: asText(spec.route),
        },
      },
      options.maxTextChars,
    );
    return { ...cleanRecord, digest: sha256(cleanRecord) };
  });

const scenarioEvaluation = (scenarioReport, scenarioReportPath, maxTextChars) => {
  if (!scenarioReport) {
    return {
      reportPath: scenarioReportPath,
      status: 'missing',
      scenarioCount: 0,
      passed: 0,
      failed: 0,
      negativeControlsPassed: 0,
      requiredChecksPresent: false,
      results: [],
    };
  }
  const results = asArray(scenarioReport.results).map((result) => {
    const clean = sanitize(
      {
        id: asText(result.id || result.scenarioId || result.name),
        passed: result.passed === true,
        failedChecks: asArray(result.failedChecks).map(asText),
        taskType: asText(result.taskType),
      },
      maxTextChars,
    );
    return clean;
  });
  return {
    reportPath: scenarioReportPath,
    status: 'loaded',
    scenarioCount: Number(scenarioReport.scenarioCount ?? results.length) || results.length,
    expectedScenarioCount: Number(scenarioReport.expectedScenarioCount ?? 0) || undefined,
    passed: Number(scenarioReport.passed ?? results.filter((item) => item.passed).length) || 0,
    failed: Number(scenarioReport.failed ?? results.filter((item) => !item.passed).length) || 0,
    negativeControlsPassed: Number(scenarioReport.negativeControlsPassed ?? 0) || 0,
    requiredChecksPresent: scenarioReport.requiredChecksPresent === true,
    results: results.slice(0, 40),
  };
};

const auditSummary = (records) => {
  const groups = {
    actionProposals: records.actionProposals.length,
    sealedActionPlans: records.sealedActionPlans.length,
    approvalDecisions: records.approvalDecisions.length,
    executionRecords: records.executionRecords.length,
    auditRecords: records.auditRecords.length,
  };
  const mutationStatuses = {};
  for (const record of records.executionRecords) {
    const status = actionRecordPhase(record) || 'unknown';
    mutationStatuses[status] = (mutationStatuses[status] || 0) + 1;
  }
  return { counts: groups, mutationStatuses };
};

const buildDataset = async (options) => {
  const warnings = [];
  let status = null;

  if (options.statusFile) {
    status = readJsonFile(options.statusFile, warnings, 'status file');
  } else if (!options.offline) {
    try {
      status = await fetchStatus(options.url);
    } catch (error) {
      warnings.push(`status fetch failed: ${error.message}`);
      if (options.strict) throw error;
    }
  }

  const statusRecords = asObject(asObject(status?.spec).records);
  const transcripts = mergeRecords(
    asArray(statusRecords.chatTranscripts),
    readJsonlFile(options.transcripts, warnings, 'chat transcripts', options.limit),
  ).slice(-options.limit);
  const feedback = mergeRecords(asArray(statusRecords.chatFeedback)).slice(-options.limit);
  const actionRecords = mergeRecords(
    asArray(statusRecords.actionProposals),
    asArray(statusRecords.sealedActionPlans),
    asArray(statusRecords.approvalDecisions),
    asArray(statusRecords.executionRecords),
  ).slice(-options.limit * 4);
  const recordsByKind = {
    actionProposals: asArray(statusRecords.actionProposals),
    sealedActionPlans: asArray(statusRecords.sealedActionPlans),
    approvalDecisions: asArray(statusRecords.approvalDecisions),
    executionRecords: asArray(statusRecords.executionRecords),
    auditRecords: asArray(statusRecords.auditRecords),
  };
  const scenarioReport = readJsonFile(options.scenarioReport, warnings, 'scenario report');
  const context = { actionRecords, feedback };
  const learningRecords = transcripts.map((record) =>
    transcriptToLearningRecord(record, context, options),
  );
  if (learningRecords.length === 0 && feedback.length > 0) {
    learningRecords.push(...feedbackOnlyRecords(feedback, options));
  }

  const generatedAt = new Date().toISOString();
  const sanitizedWarnings = sanitize(warnings, options.maxTextChars);
  return {
    apiVersion: 'aiops.komsco/v1',
    kind: 'AIOpsLearningDataset',
    metadata: {
      generatedAt,
      name: 'aiops-learning-dataset',
      source: {
        statusFile: options.statusFile || undefined,
        statusUrl: options.offline || options.statusFile ? undefined : options.url,
        transcriptJsonlPath: options.transcripts,
        scenarioReportPath: options.scenarioReport,
      },
      counts: {
        records: learningRecords.length,
        chatTranscripts: transcripts.length,
        chatFeedback: feedback.length,
        ...auditSummary(recordsByKind).counts,
      },
      warnings: sanitizedWarnings,
    },
    spec: {
      records: learningRecords.slice(-options.limit),
      scenarioEvaluation: scenarioEvaluation(scenarioReport, options.scenarioReport, options.maxTextChars),
      auditSummary: auditSummary(recordsByKind),
      privacy: {
        bearerTokensRemoved: true,
        rawSecretsExcluded: true,
        publicUrlsRedacted: true,
        subjectClaimsExcluded: true,
        redactionApplied: true,
      },
      intendedUse: [
        'SFT: question, OS/OCP context, Tool Plan digest, RCA result shape',
        'Preference tuning: feedback-rated answer candidates',
        'Safety tuning: policy decision, mutationAllowed, approval/execution outcomes',
        'Continuous learning: audit logs, user feedback, RCA verification results',
      ],
    },
  };
};

const serialize = (dataset, options) => {
  if (options.format === 'jsonl') {
    return `${dataset.spec.records.map((record) => JSON.stringify(record)).join('\n')}${
      dataset.spec.records.length ? '\n' : ''
    }`;
  }
  return `${JSON.stringify(dataset, null, 2)}\n`;
};

const main = async () => {
  const options = parseArgs(process.argv.slice(2));
  if (options.help) {
    process.stdout.write(usage());
    return;
  }
  const dataset = await buildDataset(options);
  const output = serialize(dataset, options);
  if (options.output) {
    fs.mkdirSync(path.dirname(options.output), { recursive: true });
    fs.writeFileSync(options.output, output, 'utf8');
    process.stderr.write(
      `Exported ${dataset.spec.records.length} learning records to ${options.output}\n`,
    );
  } else {
    process.stdout.write(output);
  }
};

main().catch((error) => {
  process.stderr.write(`${error.stack || error.message}\n`);
  process.exit(1);
});
