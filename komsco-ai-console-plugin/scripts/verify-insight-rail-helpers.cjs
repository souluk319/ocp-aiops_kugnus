const assert = require('node:assert/strict');
const fs = require('node:fs');
const Module = require('node:module');
const path = require('node:path');

require('ts-node').register({
  compilerOptions: {
    jsx: 'react-jsx',
    module: 'commonjs',
  },
  project: path.join(__dirname, '../tsconfig.json'),
  transpileOnly: true,
});

require.extensions['.tsx'] = require.extensions['.ts'];
const resolveFilename = Module._resolveFilename;
Module._resolveFilename = function resolveTsxFilename(request, parent, isMain, options) {
  if (parent && (request.startsWith('./') || request.startsWith('../'))) {
    const candidate = path.resolve(path.dirname(parent.filename), request);
    if (!path.extname(candidate) && fs.existsSync(`${candidate}.tsx`)) {
      return `${candidate}.tsx`;
    }
  }

  return resolveFilename.call(this, request, parent, isMain, options);
};

const {
  formatNodeUsage,
  formatSummaryTime,
  getClusterFaultCount,
  getClusterHost,
  getClusterUsageSummary,
  getHealthTone,
  getNodeCompactStatus,
  getOperatorCompactStatus,
  getOperatorTone,
  renderActionLifecycle,
  renderExecutionCapabilityBadges,
  renderHeaderOpsStatus,
  renderRailSummaryBadges,
  renderRecordRows,
  renderStatusTag,
} = require('../src/components/assistant.insightRailHelpers.tsx');

const textOf = (value) => {
  if (value === null || value === undefined || typeof value === 'boolean') {
    return '';
  }
  if (typeof value === 'string' || typeof value === 'number') {
    return String(value);
  }
  if (Array.isArray(value)) {
    return value.map(textOf).join('');
  }
  if (typeof value === 'object' && value.props) {
    return textOf(value.props.children);
  }

  return '';
};

const makeNode = (overrides = {}) => ({
  kubeletVersion: 'v1.33.11',
  name: 'worker-1',
  pressures: { disk: false, memory: false, pid: false },
  ready: true,
  roles: ['worker'],
  usage: { cpu: '1500m', memory: '2Gi' },
  ...overrides,
});

const makeSummary = (overrides = {}) => ({
  apiUrl: 'https://api.ocp.cywell.server:6443',
  healthScore: 92,
  nodes: {
    items: [makeNode()],
    metricsAvailable: true,
    notReady: 0,
    ready: 1,
    total: 1,
  },
  operators: {
    available: 3,
    degraded: 0,
    issues: [],
    progressing: 0,
    total: 3,
    unavailable: 0,
  },
  updatedAt: '2026-07-04T01:20:00Z',
  version: {
    channel: 'stable-4.20',
    updateAvailable: true,
    upgradeable: false,
    upgradeableMessage: 'Admin acknowledgement required',
    version: '4.20.23',
  },
  ...overrides,
});

const records = (overrides = {}) => ({
  actionProposals: [],
  approvalDecisions: [],
  diagnosticRequests: [],
  executionRecords: [],
  sealedActionPlans: [],
  ...overrides,
});

const status = ({ capabilities = {}, recordOverrides = {} } = {}) => ({
  spec: {
    capabilities: {
      actionExecutorConfigured: true,
      diagnosticsControllerConfigured: true,
      diagnosticsEnabled: true,
      mutationsEnabled: true,
      recordStoreEnabled: true,
      unrestrictedCommandsEnabled: true,
      ...capabilities,
    },
    records: records(recordOverrides),
    safetyContract: {
      allowedReadOnlyVerbs: [],
      capabilityGates: {},
      evidenceStatus: [],
      forbiddenActions: [],
      mode: 'controlled_execution',
      product: { name: 'AIOps for OCP' },
    },
  },
});

const summary = makeSummary();

assert.equal(formatSummaryTime(), '수집 대기');
assert.equal(formatSummaryTime('not-a-date'), '수집됨');
assert.equal(getClusterHost(summary.apiUrl), 'api.ocp.cywell.server:6443');
assert.equal(getClusterHost('not a url'), 'not a url');

assert.equal(getClusterUsageSummary(summary), 'CPU 1.5 cores · 메모리 2.00 GiB');
assert.equal(
  getClusterUsageSummary(
    makeSummary({
      nodes: { ...summary.nodes, metricsAvailable: false },
    }),
  ),
  'Metrics API unavailable',
);
assert.equal(formatNodeUsage(makeNode({ usage: { cpu: '500m', memory: '1024Mi' } })), 'CPU 500 m · 메모리 1.00 GiB');
assert.equal(
  formatNodeUsage(
    makeNode({
      pressures: { disk: false, memory: true, pid: true },
      usage: {},
    }),
  ),
  'Memory/PID Pressure',
);

assert.equal(getClusterFaultCount(summary), 0);
assert.equal(getClusterFaultCount(makeSummary({ operators: { ...summary.operators, degraded: 1 } })), 1);
assert.equal(getHealthTone(null), 'neutral');
assert.equal(getHealthTone(summary), 'ok');
assert.equal(getHealthTone(makeSummary({ healthScore: 80 })), 'warn');
assert.equal(
  getHealthTone(makeSummary({ nodes: { ...summary.nodes, notReady: 1, ready: 0 } })),
  'danger',
);

assert.deepEqual(getNodeCompactStatus(summary, false, ''), {
  label: 'Node 1/1 · Ready',
  title: 'All reported nodes are Ready.',
  tone: 'ok',
});
assert.equal(
  getNodeCompactStatus(makeSummary({ nodes: { ...summary.nodes, notReady: 1, ready: 0 } }), false, '').tone,
  'danger',
);
assert.equal(getNodeCompactStatus(null, true, '').label, 'Node 수집 중');
assert.equal(getNodeCompactStatus(null, false, 'boom').tone, 'danger');

assert.deepEqual(getOperatorCompactStatus(summary, false, ''), {
  label: 'Operator 3/3 정상',
  title: 'All 3 ClusterOperators are available.',
  tone: 'ok',
});
assert.equal(
  getOperatorCompactStatus(
    makeSummary({ operators: { ...summary.operators, progressing: 1 } }),
    false,
    '',
  ).tone,
  'warn',
);
assert.equal(
  getOperatorCompactStatus(
    makeSummary({ operators: { ...summary.operators, degraded: 1 } }),
    false,
    '',
  ).tone,
  'danger',
);
assert.equal(getOperatorCompactStatus(null, false, 'operator error').label, 'Operator 확인 필요');
assert.equal(getOperatorTone({ available: false, degraded: false }), 'danger');
assert.equal(getOperatorTone({ available: true, degraded: false }), 'warn');

const statusTag = renderStatusTag('승인 실행', 'review', 'title');
assert.match(statusTag.props.className, /komsco-ai__scope-tag--review/);
assert.equal(textOf(statusTag), '승인 실행');

assert.match(textOf(renderHeaderOpsStatus(summary, false, '')), /Node 1\/1/);
assert.match(textOf(renderHeaderOpsStatus(summary, false, '')), /Operator 정상/);
assert.match(textOf(renderRailSummaryBadges(summary, false, '')), /Node 1\/1 · Ready/);
assert.match(textOf(renderRailSummaryBadges(summary, false, '')), /Operator 3\/3 정상/);

const capabilityBadges = renderExecutionCapabilityBadges(status(), 'execute');
assert.match(textOf(capabilityBadges), /읽기 전용/);
assert.match(textOf(capabilityBadges), /승인 실행/);
assert.match(textOf(capabilityBadges), /실행 무제한/);

const lifecycle = renderActionLifecycle(
  status({
    recordOverrides: {
      actionProposals: [{ kind: 'ActionProposalRecord', metadata: { name: 'proposal-1' }, spec: {} }],
    },
  }),
  'read-only',
);
assert.equal(lifecycle.props['data-ui-execution-mode'], 'read-only');
assert.equal(lifecycle.props['data-action-executor-state'], 'configured');
assert.equal(lifecycle.props['data-mutation-flag-state'], 'enabled');
assert.match(textOf(lifecycle), /제안/);
assert.match(textOf(lifecycle), /제한 사유/);

const emptyRecordRows = renderRecordRows([], '최근 진단 요청이 없습니다.');
assert.equal(emptyRecordRows.props.className, 'komsco-ai__rail-empty');
assert.equal(textOf(emptyRecordRows), '최근 진단 요청이 없습니다.');

const approvalRecord = {
  kind: 'ApprovalDecisionRecord',
  metadata: { name: 'approval-1' },
  spec: {
    approvalDecision: {
      approvalId: 'approval-1',
      planDigest: 'digest-1',
      status: 'approved',
      target: {
        kind: 'Deployment',
        name: 'aiops-two-pod-exec',
        namespace: 'komsco-ai-dev',
      },
    },
  },
};
const recordRows = renderRecordRows([approvalRecord], 'empty');
assert.equal(Array.isArray(recordRows), true);
assert.equal(recordRows.length, 1);
assert.match(textOf(recordRows), /approval-1/);
assert.match(textOf(recordRows), /komsco-ai-dev\/aiops-two-pod-exec/);

console.log(
  JSON.stringify(
    {
      checked: 33,
      ok: true,
      verifier: 'verify-insight-rail-helpers',
    },
    null,
    2,
  ),
);
