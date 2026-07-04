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

const { getAiopsRecordAction } = require('../src/components/assistant.actionState.ts');

const target = {
  kind: 'Deployment',
  name: 'aiops-two-pod-exec',
  namespace: 'komsco-ai-dev',
};

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

const proposal = {
  kind: 'ActionProposalRecord',
  metadata: { name: 'proposal-1' },
  spec: {
    candidateActionRequest: {
      actionType: 'rollout_restart_deployment',
      target,
    },
  },
};

const plan = {
  kind: 'SealedActionPlanRecord',
  metadata: { name: 'plan-1' },
  spec: {
    sealedActionPlan: {
      action: { toolName: 'rollout_restart_deployment' },
      digest: { planDigest: 'digest-1' },
      safety: { risk: 'low', rollbackPossible: false },
      target,
    },
  },
};

const planWithoutDigest = {
  kind: 'SealedActionPlanRecord',
  metadata: { name: 'plan-no-digest' },
  spec: {
    sealedActionPlan: {
      action: { toolName: 'rollout_restart_deployment' },
      safety: { risk: 'low' },
      target,
    },
  },
};

const approval = {
  kind: 'ApprovalDecisionRecord',
  metadata: { name: 'approval-1' },
  spec: {
    approvalDecision: {
      approvalId: 'approval-1',
      planDigest: 'digest-1',
      status: 'approved',
      target,
    },
  },
};

const rejectedApproval = {
  kind: 'ApprovalDecisionRecord',
  metadata: { name: 'approval-rejected' },
  spec: {
    approvalDecision: {
      approvalId: 'approval-rejected',
      planDigest: 'digest-1',
      status: 'rejected',
      target,
    },
  },
};

const execution = {
  kind: 'ExecutionRecord',
  metadata: { name: 'execution-1' },
  spec: {
    approvalId: 'approval-1',
    mutationOutcome: { status: 'mutation_succeeded' },
    target,
  },
};

const cases = [
  {
    expected: { label: '계획', step: 'create-plan' },
    mode: 'execute',
    name: 'proposal can create plan in execute mode',
    record: proposal,
    status: status(),
  },
  {
    expected: {
      disabledReason: '읽기 전용 모드에서는 승인·실행 불가',
      label: '계획',
      step: 'create-plan',
    },
    mode: 'read-only',
    name: 'proposal shows read-only disabled reason',
    record: proposal,
    status: status(),
  },
  {
    expected: {
      disabledReason: 'Gateway 실행 기능 미구성',
      label: '계획',
      step: 'create-plan',
    },
    mode: 'execute',
    name: 'proposal shows gateway disabled reason',
    record: proposal,
    status: status({
      capabilities: {
        actionExecutorConfigured: false,
        mutationsEnabled: false,
      },
    }),
  },
  {
    expected: { label: '승인', step: 'approve-plan' },
    mode: 'execute',
    name: 'sealed plan needs approval in execute mode',
    record: plan,
    status: status({ recordOverrides: { sealedActionPlans: [plan] } }),
  },
  {
    expected: { label: '실행', step: 'approve-execute-plan' },
    mode: 'unrestricted',
    name: 'sealed plan can auto approve and execute in unrestricted mode',
    record: plan,
    status: status({ recordOverrides: { sealedActionPlans: [plan] } }),
  },
  {
    expected: null,
    mode: 'execute',
    name: 'sealed plan hides action after approval exists',
    record: plan,
    status: status({
      recordOverrides: {
        approvalDecisions: [approval],
        sealedActionPlans: [plan],
      },
    }),
  },
  {
    expected: {
      disabledReason: 'plan digest 없음',
      label: '승인',
      step: 'approve-plan',
    },
    mode: 'execute',
    name: 'sealed plan without digest cannot approve cleanly',
    record: planWithoutDigest,
    status: status({ recordOverrides: { sealedActionPlans: [planWithoutDigest] } }),
  },
  {
    expected: {
      disabledReason: 'plan digest 없음',
      label: '실행',
      step: 'approve-execute-plan',
    },
    mode: 'unrestricted',
    name: 'sealed plan without digest keeps unrestricted label but blocks',
    record: planWithoutDigest,
    status: status({ recordOverrides: { sealedActionPlans: [planWithoutDigest] } }),
  },
  {
    expected: { label: '실행', step: 'execute-approval' },
    mode: 'execute',
    name: 'approved decision can execute when matching plan exists',
    record: approval,
    status: status({
      recordOverrides: {
        approvalDecisions: [approval],
        sealedActionPlans: [plan],
      },
    }),
  },
  {
    expected: null,
    mode: 'execute',
    name: 'rejected approval has no action',
    record: rejectedApproval,
    status: status({
      recordOverrides: {
        approvalDecisions: [rejectedApproval],
        sealedActionPlans: [plan],
      },
    }),
  },
  {
    expected: null,
    mode: 'execute',
    name: 'approved decision hides action after execution exists',
    record: approval,
    status: status({
      recordOverrides: {
        approvalDecisions: [approval],
        executionRecords: [execution],
        sealedActionPlans: [plan],
      },
    }),
  },
  {
    expected: {
      disabledReason: '연결된 plan 없음',
      label: '실행',
      step: 'execute-approval',
    },
    mode: 'execute',
    name: 'approved decision without plan shows missing plan reason',
    record: approval,
    status: status({ recordOverrides: { approvalDecisions: [approval] } }),
  },
];

for (const item of cases) {
  const actual = getAiopsRecordAction(item.record, item.status, item.mode);
  assert.deepEqual(actual, item.expected, item.name);
}

console.log(
  JSON.stringify(
    {
      checked: cases.length,
      ok: true,
      verifier: 'verify-action-resolver',
    },
    null,
    2,
  ),
);
