#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const WebSocket = require('ws');

const root = path.resolve(__dirname, '..');
const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9364');
const consoleUrl =
  process.env.AIOPS_CONSOLE_URL || 'http://localhost:9000/dashboards/aiops?codex_v=0281-local';
const portalUrl =
  process.env.AIOPS_PORTAL_URL || 'http://localhost:5174/dashboards/aiops?codex_v=0281-local';
const screenshotDirDefault = path.join(
  root,
  'docs',
  'Ver.0.2.8.1',
  'local-aiops-screenshots',
);
const reportDefault = path.join(
  root,
  'docs',
  'Ver.0.2.8.1',
  'local-aiops-scenario-test-report.json',
);
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-v0281-local-'));

const parseArgs = () => {
  const args = process.argv.slice(2);
  const parsed = {
    report: reportDefault,
    runs: 10,
    screenshotDir: screenshotDirDefault,
  };
  for (let index = 0; index < args.length; index += 1) {
    const item = args[index];
    if (item === '--runs') {
      parsed.runs = Number(args[index + 1] || '10');
      index += 1;
    } else if (item === '--report') {
      parsed.report = path.resolve(root, args[index + 1] || reportDefault);
      index += 1;
    } else if (item === '--screenshot-dir') {
      parsed.screenshotDir = path.resolve(root, args[index + 1] || screenshotDirDefault);
      index += 1;
    }
  }
  return parsed;
};

const cli = parseArgs();
fs.mkdirSync(path.dirname(cli.report), { recursive: true });
fs.mkdirSync(cli.screenshotDir, { recursive: true });

let chromeProcess;
let chromeWebSocket;
let nextId = 1;
const pending = new Map();
const runtimeErrors = [];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const readFile = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

const assert = (condition, message, evidence = undefined) => {
  if (!condition) {
    const detail = evidence === undefined ? '' : `\n${JSON.stringify(evidence, null, 2)}`;
    throw new Error(`${message}${detail}`);
  }
};

const deepClone = (value) => JSON.parse(JSON.stringify(value));

const iso = (offsetMs = 0) => new Date(Date.now() + offsetMs).toISOString();

const target = (namespace, name, kind = 'Pod', apiVersion = kind === 'Deployment' ? 'apps/v1' : 'v1') => ({
  apiVersion,
  kind,
  name,
  namespace,
  uid: `local-${namespace}-${name}`,
});

const targetKey = (recordTarget) =>
  recordTarget?.namespace ? `${recordTarget.namespace}/${recordTarget.name}` : recordTarget?.name || '';

const digestFor = (id) => `sha256:local-${id}`;

const emptyRecords = () => ({
  actionProposals: [],
  approvalDecisions: [],
  auditRecords: [],
  chatTranscripts: [],
  diagnosticRequests: [],
  executionRecords: [],
  sealedActionPlans: [],
});

const proposalRecord = (id, recordTarget, toolName, summary) => ({
  apiVersion: 'aiops.komsco/v1alpha1',
  kind: 'ActionProposalRecord',
  metadata: {
    createdAt: iso(-90_000),
    name: `proposal-${id}`,
  },
  spec: {
    candidateActionRequest: {
      action: {
        summary,
        toolName,
      },
      confidence: 0.78,
      evidenceRefs: [`ev-${id}-alert`, `ev-${id}-pod`],
      target: recordTarget,
    },
    status: {
      phase: 'proposal',
    },
  },
});

const planRecord = (id, recordTarget, toolName, options = {}) => ({
  apiVersion: 'aiops.komsco/v1alpha1',
  kind: 'SealedActionPlanRecord',
  metadata: {
    createdAt: iso(-80_000),
    name: `plan-${id}`,
  },
  spec: {
    sealedActionPlan: {
      action: {
        summary: options.summary || '승인 후 로컬 simulator에서만 실행합니다.',
        toolName,
      },
      digest: {
        planDigest: digestFor(id),
      },
      expectedImpact: options.expectedImpact || '대상 리소스 상태만 simulator 안에서 변경됩니다.',
      safety: {
        risk: options.risk || 'medium',
        rollbackDescription: options.rollbackDescription || 'simulator state를 이전 snapshot으로 복원합니다.',
        rollbackPossible: options.rollbackPossible ?? true,
      },
      target: recordTarget,
      verification: {
        expected: options.verification || 'Ready 상태와 ExecutionRecord 성공을 확인합니다.',
      },
    },
    status: {
      phase: 'sealed',
    },
  },
});

const approvalRecord = (id, recordTarget, toolName, status = 'approved') => ({
  apiVersion: 'aiops.komsco/v1alpha1',
  kind: 'ApprovalDecisionRecord',
  metadata: {
    createdAt: iso(),
    name: `approval-${id}-${status}`,
  },
  spec: {
    approvalDecision: {
      action: {
        toolName,
      },
      approvalId: `approval-${id}-${status}`,
      decidedBy: 'local-simulator',
      planDigest: digestFor(id),
      planId: `plan-${id}`,
      reason: status === 'rejected' ? '로컬 테스트에서 거절 경로를 검증했습니다.' : '로컬 테스트 승인',
      status,
      target: recordTarget,
    },
    status: {
      phase: status,
    },
  },
});

const executionRecord = (id, recordTarget, toolName) => ({
  apiVersion: 'aiops.komsco/v1alpha1',
  kind: 'ExecutionRecord',
  metadata: {
    createdAt: iso(),
    name: `execution-${id}`,
  },
  spec: {
    action: {
      toolName,
    },
    approvalId: `approval-${id}-approved`,
    mutationOutcome: {
      reason: 'local simulator mutation only',
      status: 'mutation_simulated',
    },
    planDigest: digestFor(id),
    remediationOutcome: {
      reason: 'verification passed in local simulator',
      status: 'verification_passed',
    },
    status: {
      phase: 'executed',
    },
    target: recordTarget,
  },
});

const actionRef = (id, record, stage, label) => {
  const spec = record.spec || {};
  const sealed = spec.sealedActionPlan || {};
  const approval = spec.approvalDecision || {};
  const proposal = spec.candidateActionRequest || {};
  const recordTarget = sealed.target || approval.target || proposal.target || spec.target || {};
  const toolName =
    sealed.action?.toolName || approval.action?.toolName || proposal.action?.toolName || 'local_action';
  const planDigest = sealed.digest?.planDigest || approval.planDigest || undefined;

  return {
    id: `${id}|${stage}|${record.metadata.name}`,
    label,
    messageAnchor: 'assistant-message-1',
    planDigest,
    recordKind: record.kind,
    recordName: record.metadata.name,
    stage,
    targetKey: targetKey(recordTarget),
    toolName,
    updatedAt: Date.now(),
  };
};

const answer = ({ actionPlan, causes, details, evidence, impact, summary, verify }) =>
  [
    '현재 판단',
    ...summary.map((item) => `- ${item}`),
    '',
    '영향 범위',
    ...impact.map((item) => `- ${item}`),
    '',
    '확인한 근거',
    ...evidence.map((item) => `- ${item}`),
    '',
    '원인 후보',
    ...causes.map((item) => `- ${item}`),
    '',
    'Action Plan',
    ...actionPlan.map((item) => `- ${item}`),
    '',
    '검증/롤백',
    ...verify.map((item) => `- ${item}`),
    '',
    '근거 상세보기',
    ...details.map((item) => `- ${item}`),
  ].join('\n');

const actionScenario = (base) => {
  const records = emptyRecords();
  if (base.proposal) {
    records.actionProposals.push(base.proposal);
  }
  if (base.plan) {
    records.sealedActionPlans.push(base.plan);
  }
  if (base.approval) {
    records.approvalDecisions.push(base.approval);
  }
  if (base.execution) {
    records.executionRecords.push(base.execution);
  }
  return {
    ...base,
    records,
  };
};

const crashTarget = target('komsco-ai-local', 'aiops-scenario-crashloop');
const imageTarget = target('openshift-marketplace', 'appscan360-catalog');
const podCreateTarget = target('komsco-ai-local', 'local-test-pods');
const scaleTarget = target('komsco-ai-local', 'aiops-local-worker', 'Deployment', 'apps/v1');
const rejectTarget = target('komsco-ai-local', 'risky-cache-rollout', 'Deployment', 'apps/v1');
const executeTarget = target('komsco-ai-local', 'safe-rollout-worker', 'Deployment', 'apps/v1');

const scenarioDefinitions = [
  {
    id: '01-alert-triage',
    title: '최근 OpenShift 경고 정리',
    question: '최근 OpenShift 경고와 우선 확인할 항목을 실제 근거와 추가 확인 필요 항목으로 구분해서 정리해줘.',
    content: answer({
      actionPlan: ['현재 질문은 경고 정리이므로 승인 가능한 Action Plan은 만들지 않습니다.'],
      causes: ['etcd 파편화는 장기 성능 저하 후보입니다.', 'appscan360 Pod NotReady는 서비스 영향 가능성이 직접적입니다.', 'control-plane memory pressure는 API 응답 지연과 연결될 수 있습니다.'],
      details: ['운영 증거: Active Alert, Node 상태, Metric snapshot', '문서 근거: local runbook fixture'],
      evidence: ['Alert: etcdDatabaseHighFragmentationRatio', 'Alert: KubePodNotReady / openshift-marketplace/appscan360-catalog', 'Metric: control-plane memory pressure'],
      impact: ['marketplace catalog 기능 영향 가능성', 'control-plane 응답 지연 가능성'],
      summary: ['우선 확인 3건입니다.', '지금은 조회/판단 답변이라 실행 계획을 만들지 않습니다.'],
      verify: ['다음 단계는 Events, logs, metric current value 확인입니다.', '변경 조치는 요청되지 않았습니다.'],
    }),
    expectedNoAction: true,
    records: emptyRecords(),
  },
  actionScenario({
    id: '02-crashloop-action-plan',
    title: 'CrashLoopBackOff 조치 후보',
    question: 'CrashLoopBackOff 상태인 Pod를 안전하게 복구할 Action Plan을 만들어줘.',
    content: answer({
      actionPlan: ['Action Plan: rollout restart 전에 Events, logs, owner Deployment를 확인합니다.', '승인 후 simulator에서 Deployment rollout restart를 기록합니다.'],
      causes: ['최근 restart 증가와 liveness probe 실패 후보가 있습니다.', '이미지 문제는 확인되지 않았습니다.'],
      details: ['운영 증거: Pod status, restart metric, recent events'],
      evidence: ['Pod: komsco-ai-local/aiops-scenario-crashloop', 'Status: CrashLoopBackOff', 'Metric: restart increase observed'],
      impact: ['해당 워크로드 요청 처리 실패 가능성이 있습니다.'],
      summary: ['CrashLoopBackOff 복구 후보 1건입니다.', '대상과 검증 방법이 명확하므로 승인 가능한 Action Plan을 제시합니다.'],
      verify: ['실행 후 Ready 상태와 restart 증가 중단을 확인합니다.', '실패하면 이전 ReplicaSet 상태를 확인합니다.'],
    }),
    executionMode: 'execute',
    plan: planRecord('crashloop', crashTarget, 'rollout_restart_deployment', {
      summary: 'owner Deployment rollout restart를 simulator에서 실행합니다.',
      verification: 'Pod Ready 1/1과 restart 증가 중단',
    }),
  }),
  actionScenario({
    id: '03-imagepullbackoff-no-eviction',
    title: 'ImagePullBackOff',
    question: 'ImagePullBackOff 경고를 확인하고 조치 후보를 알려줘.',
    content: answer({
      actionPlan: ['Pod eviction은 생성하지 않습니다.', '근거 더 수집: image tag, registry secret, pull event를 확인합니다.'],
      causes: ['image tag 오타, registry 접근 실패, imagePullSecret 누락 후보입니다.'],
      details: ['운영 증거: Pod Events, container waiting reason'],
      evidence: ['Pod: openshift-marketplace/appscan360-catalog', 'Reason: ImagePullBackOff'],
      impact: ['catalog source 갱신이 지연될 수 있습니다.'],
      summary: ['ImagePullBackOff는 삭제/eviction보다 pull 원인 확인이 먼저입니다.'],
      verify: ['Events와 registry secret 확인 후 image reference를 검증합니다.'],
    }),
    expectedNoEviction: true,
    records: emptyRecords(),
  }),
  actionScenario({
    id: '04-create-three-pods',
    title: 'Pod 3개 생성 요청',
    question: 'komsco-ai-local namespace에 테스트 Pod 3개 만들어줘.',
    content: answer({
      actionPlan: ['대상 namespace: komsco-ai-local', '생성 수량: 3', '승인 후 local simulator state만 desired=3, current=3, ready=3/3으로 변경합니다.'],
      causes: ['사용자가 명시적으로 생성 작업을 요청했습니다.'],
      details: ['운영 증거: local fixture namespace exists', '실제 cluster mutation 없음'],
      evidence: ['Namespace: komsco-ai-local', 'Current: desired=0, current=0, ready=0/0'],
      impact: ['로컬 simulator 상태만 바뀌며 회사 OKD에는 영향이 없습니다.'],
      summary: ['로컬 한정 테스트 Pod 생성 Action Plan입니다.'],
      verify: ['승인 전 상태 변경 없음', '실행 후 simulator state ready=3/3 확인'],
    }),
    executionMode: 'execute',
    plan: planRecord('create-three-pods', podCreateTarget, 'create_test_pods', {
      expectedImpact: 'local simulator pod state only',
      verification: 'desired=3 current=3 ready=3/3',
    }),
    runtime: {
      createdPods: {
        current: 0,
        desired: 0,
        ready: '0/0',
      },
    },
  }),
  actionScenario({
    id: '05-deployment-scale-gap',
    title: 'Deployment scale 요청',
    question: 'aiops-local-worker Deployment를 3개로 늘려줘.',
    content: answer({
      actionPlan: ['현재 1개, 목표 3개라 gap 2개가 있습니다.', '승인 후 local simulator에서 replicas=3으로 반영합니다.', '이미 3개인 상태라면 조치 없음으로 판정해야 합니다.'],
      causes: ['현재 replicas가 목표보다 부족합니다.'],
      details: ['운영 증거: Deployment status fixture'],
      evidence: ['Deployment: komsco-ai-local/aiops-local-worker', 'Current replicas: 1', 'Desired replicas: 3'],
      impact: ['로컬 simulator의 replica count만 바뀝니다.'],
      summary: ['gap이 있는 scale 요청이므로 Action Plan을 생성합니다.'],
      verify: ['실행 후 current=3, ready=3/3을 확인합니다.'],
    }),
    executionMode: 'execute',
    plan: planRecord('scale-gap', scaleTarget, 'scale_deployment_replicas', {
      expectedImpact: 'local simulator replica state only',
      verification: 'current replicas 3',
    }),
    runtime: {
      scale: {
        current: 1,
        desired: 3,
        ready: '1/3',
      },
    },
  }),
  actionScenario({
    id: '06-readonly-action-request',
    title: '읽기 전용 모드에서 조치 요청',
    question: '이 문제를 바로 복구해줘.',
    content: answer({
      actionPlan: ['읽기 전용 모드에서는 조치 버튼을 표시하지 않습니다.', 'Action Plan 생성/실행은 실행 가능 모드가 필요합니다.'],
      causes: ['복구 의도는 있지만 현재 실행 모드가 읽기 전용입니다.'],
      details: ['운영 증거: local sealed plan fixture'],
      evidence: ['Pod: komsco-ai-local/aiops-scenario-crashloop', 'Status: CrashLoopBackOff'],
      impact: ['현재 화면에서는 실행 영향이 없습니다.'],
      summary: ['실행 모드가 읽기 전용이므로 계획 상태만 보여줍니다.'],
      verify: ['실행 가능 모드로 변경하면 승인 버튼을 표시할 수 있습니다.'],
    }),
    executionMode: 'read-only',
    plan: planRecord('readonly-blocked', crashTarget, 'rollout_restart_deployment'),
  }),
  actionScenario({
    id: '07-approval-rejection',
    title: '승인 거절 경로',
    question: '이 Action Plan은 거절해줘.',
    content: answer({
      actionPlan: ['승인 가능한 Action Plan입니다.', '거절 시 rejected 기록만 남기고 실행은 차단합니다.'],
      causes: ['위험도가 있어 운영자 판단이 필요합니다.'],
      details: ['운영 증거: local sealed plan fixture'],
      evidence: ['Deployment: komsco-ai-local/risky-cache-rollout', 'Risk: medium'],
      impact: ['거절하면 mutation은 발생하지 않습니다.'],
      summary: ['거절 경로 검증용 Action Plan입니다.'],
      verify: ['거절 후 ExecutionRecord가 없어야 합니다.'],
    }),
    executionMode: 'execute',
    plan: planRecord('reject-plan', rejectTarget, 'rollout_restart_deployment', {
      risk: 'high',
    }),
  }),
  actionScenario({
    id: '08-approval-execution',
    title: '승인 실행 경로',
    question: '승인하고 실행까지 진행해줘.',
    content: answer({
      actionPlan: ['승인 후 실행 가능한 Action Plan입니다.', '실행 결과는 simulator ExecutionRecord로만 기록합니다.'],
      causes: ['대상과 검증 방법이 명확합니다.'],
      details: ['운영 증거: local sealed plan fixture'],
      evidence: ['Deployment: komsco-ai-local/safe-rollout-worker', 'Status: degraded'],
      impact: ['local simulator state와 audit record만 바뀝니다.'],
      summary: ['승인 실행 경로 검증용 Action Plan입니다.'],
      verify: ['실행 후 mutation simulated, verification passed를 확인합니다.'],
    }),
    executionMode: 'execute',
    plan: planRecord('execute-plan', executeTarget, 'rollout_restart_deployment'),
  }),
  {
    id: '09-history-action-list',
    title: '좌패널 대화/조치 목록',
    question: '좌패널 대화와 조치 목록을 확인해줘.',
    content: answer({
      actionPlan: ['좌패널에서 대화별 하위 조치 목록을 확인합니다.'],
      causes: ['대화와 조치가 분리되어 보이면 운영자가 흐름을 잃습니다.'],
      details: ['UI fixture: 3 conversations, 4 action refs'],
      evidence: ['History: conversations with nested action refs'],
      impact: ['클릭 후에도 dated conversation order가 안정적이어야 합니다.'],
      summary: ['좌패널은 목록형으로 대화 아래 조치가 붙어야 합니다.'],
      verify: ['조치 클릭 전/후 대화 title order를 비교합니다.'],
    }),
    historyScenario: true,
    records: (() => {
      const records = emptyRecords();
      records.sealedActionPlans.push(planRecord('history-plan', crashTarget, 'rollout_restart_deployment'));
      records.approvalDecisions.push(approvalRecord('history-approval', crashTarget, 'rollout_restart_deployment'));
      records.executionRecords.push(executionRecord('history-execution', executeTarget, 'rollout_restart_deployment'));
      return records;
    })(),
  },
  {
    id: '10-responding-trust-ui',
    title: '응답 중 상태와 신뢰 UI',
    question: '현재 화면 기준으로 안전하게 확인해줘.',
    content: answer({
      actionPlan: ['응답 중에는 헤더 하단 light rail로 상태를 표시합니다.', '답변 완료 후 안정 상태로 돌아옵니다.'],
      causes: ['로딩 상태가 불분명하면 운영자는 실행 중인지 멈춘 것인지 판단하기 어렵습니다.'],
      details: ['UI fixture: responding class, avatar style, font metrics'],
      evidence: ['Header rail CSS, assistant message font, icon frame style'],
      impact: ['신뢰 UI와 가독성을 확인합니다.'],
      summary: ['응답 중 상태와 가독성 검증 시나리오입니다.'],
      verify: ['light rail animation, font >= 14px, icon frame 제거를 확인합니다.'],
    }),
    trustUiScenario: true,
    records: emptyRecords(),
  },
];

const hydrateScenario = (scenario) => {
  const records = deepClone(scenario.records || emptyRecords());
  const actionRefs = [];
  for (const record of records.actionProposals || []) {
    actionRefs.push(actionRef(scenario.id, record, 'proposal', '1단계 · 후보 접수'));
  }
  for (const record of records.sealedActionPlans || []) {
    actionRefs.push(actionRef(scenario.id, record, 'plan', '2단계 · 승인 필요'));
  }
  for (const record of records.approvalDecisions || []) {
    actionRefs.push(actionRef(scenario.id, record, 'approval', '3단계 · 실행 대기'));
  }
  for (const record of records.executionRecords || []) {
    actionRefs.push(actionRef(scenario.id, record, 'execution', '4단계 · 실행 완료'));
  }

  return {
    ...scenario,
    actionRefs,
    records,
  };
};

const scenarios = scenarioDefinitions.map(hydrateScenario);

const simulator = {
  clusterMutationCommands: [],
  companyMutationExecuted: false,
  interceptedRequests: [],
  records: emptyRecords(),
  runtime: {},
  scenarioId: '',
};

const resetSimulator = (scenario) => {
  simulator.clusterMutationCommands = [];
  simulator.companyMutationExecuted = false;
  simulator.interceptedRequests = [];
  simulator.records = deepClone(scenario.records || emptyRecords());
  simulator.runtime = deepClone(scenario.runtime || {});
  simulator.scenarioId = scenario.id;
};

const findPlan = (planId, digest) =>
  simulator.records.sealedActionPlans.find((record) => {
    const sealed = record.spec?.sealedActionPlan || {};
    return record.metadata?.name === planId || sealed.digest?.planDigest === digest;
  });

const fulfill = async (requestId, statusCode, contentType, body) => {
  const rawBody = typeof body === 'string' ? body : JSON.stringify(body);
  await send('Fetch.fulfillRequest', {
    body: Buffer.from(rawBody, 'utf8').toString('base64'),
    responseCode: statusCode,
    responseHeaders: [
      { name: 'Content-Type', value: contentType },
      { name: 'Access-Control-Allow-Origin', value: '*' },
    ],
    requestId,
  });
};

const fulfillJson = (requestId, body, statusCode = 200) =>
  fulfill(requestId, statusCode, 'application/json; charset=utf-8', body);

const continueRequest = async (requestId) => {
  await send('Fetch.continueRequest', { requestId });
};

const subject = () => ({
  apiUrl: 'https://api.local-aiops.invalid:6443',
  groups: ['system:authenticated', 'local-aiops-testers'],
  source: 'local-simulator',
  username: 'admin',
});

const clusterSummary = () => ({
  aiopsWorkloads: {
    daemonsets: [],
    deployments: [
      {
        available: simulator.runtime.scale?.current ?? 1,
        createdAt: iso(-3_600_000),
        desired: simulator.runtime.scale?.desired ?? 1,
        detail: `ready ${simulator.runtime.scale?.ready ?? '1/1'} · local simulator`,
        kind: 'Deployment',
        name: 'aiops-local-worker',
        namespace: 'komsco-ai-local',
        ready: simulator.runtime.scale?.current ?? 1,
        severity: simulator.runtime.scale?.current === simulator.runtime.scale?.desired ? 'ok' : 'warn',
        updated: simulator.runtime.scale?.current ?? 1,
      },
    ],
    issues: 2,
    namespaces: ['komsco-ai-local', 'openshift-marketplace'],
    total: 1,
  },
  apiUrl: 'https://api.local-aiops.invalid:6443',
  available: true,
  consoleUrl: consoleUrl.replace('/dashboards/aiops?codex_v=0281-local', ''),
  healthScore: 92,
  nodes: {
    items: [
      {
        kubeletVersion: 'v1.30-local',
        name: 'local-control-plane-0',
        osImage: 'Red Hat Enterprise Linux CoreOS local',
        pressures: {
          disk: false,
          memory: false,
          pid: false,
        },
        ready: true,
        roles: ['master', 'worker'],
        usage: {
          cpu: '42%',
          memory: '61%',
        },
      },
    ],
    metricsAvailable: true,
    notReady: 0,
    pressureCount: 0,
    ready: 1,
    total: 1,
  },
  operatorHealthy: true,
  operators: {
    available: 8,
    degraded: 0,
    issues: [],
    progressing: 0,
    total: 8,
    unavailable: 0,
  },
  resources: {
    issues: 2,
    items: [
      {
        detail: 'CrashLoopBackOff 1 · ImagePullBackOff 1',
        id: 'pods',
        issues: 2,
        kind: 'Pod',
        name: 'pods',
        ready: 21,
        score: '21/23',
        severity: 'risk',
        total: 23,
      },
      {
        detail: `ready ${simulator.runtime.scale?.ready ?? '1/1'} · local simulator`,
        id: 'deployments',
        issues: simulator.runtime.scale?.current === simulator.runtime.scale?.desired ? 0 : 1,
        kind: 'Deployment',
        name: 'deployments',
        ready: simulator.runtime.scale?.current ?? 1,
        score: `${simulator.runtime.scale?.current ?? 1}/${simulator.runtime.scale?.desired ?? 1}`,
        severity: simulator.runtime.scale?.current === simulator.runtime.scale?.desired ? 'ok' : 'warn',
        total: simulator.runtime.scale?.desired ?? 1,
      },
    ],
    total: 2,
  },
  timestamp: iso(),
  updatedAt: iso(),
  version: {
    channel: 'stable-local',
    updateAvailable: false,
    upgradeable: true,
    version: '4.20-local',
  },
});

const buildStatus = () => ({
  apiVersion: 'aiops.komsco/v1alpha1',
  kind: 'AiopsRuntimeStatus',
  metadata: {
    name: 'local-simulator',
    namespace: 'local-only',
    timestamp: iso(),
  },
  spec: {
    capabilities: {
      actionExecutorConfigured: true,
      diagnosticsControllerConfigured: true,
      diagnosticsEnabled: true,
      mutationsEnabled: true,
      rag: {
        endpointConfigured: true,
        status: 'local-simulator',
      },
      recordStoreEnabled: true,
      unrestrictedCommandsEnabled: true,
    },
    records: deepClone(simulator.records),
    safetyContract: {
      allowedReadOnlyVerbs: ['get', 'list', 'watch'],
      capabilityGates: {
        companyOkdMutation: false,
        localSimulatorOnly: true,
      },
      evidenceStatus: [
        {
          label: 'local fixture',
          phase: 'collected',
        },
      ],
      forbiddenActions: ['company-cluster-mutation'],
      lightspeedStatus: {
        lastStatus: 'local-simulator',
        status: 'ok',
      },
      mode: 'local-simulator',
      product: {
        name: 'KOMSCO Local AIOps Simulator',
      },
    },
    subject: subject(),
  },
});

const dataSources = () => [
  {
    label: 'Local Alert fixture',
    name: 'alert-fixture',
    path: '/local/alerts',
    required: true,
    status: 'available',
  },
  {
    label: 'Local Pod fixture',
    name: 'pod-fixture',
    path: '/local/pods',
    required: true,
    status: 'available',
  },
  {
    label: 'Local Runbook fixture',
    name: 'runbook-fixture',
    path: '/local/runbooks',
    required: false,
    status: 'available',
  },
];

const anomalySummary = () => ({
  apiVersion: 'aiops.komsco/v1alpha1',
  kind: 'AIOpsAnomalySummary',
  metadata: {
    generatedAt: iso(),
    name: 'local-anomalies',
  },
  spec: {
    dataSources: dataSources(),
    findings: [
      {
        candidateCause: '최근 restart 증가와 probe 실패 후보',
        category: '워크로드',
        evidence: 'Pod status + restart metric',
        id: 'local-crashloop',
        impact: '워크로드 요청 실패 가능성',
        lastObservedAt: iso(-60_000),
        namespace: 'komsco-ai-local',
        nextCheck: 'Events, logs, owner Deployment 확인',
        priority: 1,
        reason: 'CrashLoopBackOff',
        resource: {
          kind: 'Pod',
          name: 'aiops-scenario-crashloop',
          namespace: 'komsco-ai-local',
        },
        severity: '위험',
        source: 'local-simulator',
        status: 'risk',
        statusLabel: '조치 후보 필요',
        title: 'CrashLoopBackOff 조치 후보',
        type: 'pod',
      },
      {
        candidateCause: 'image tag 또는 pull secret 확인 필요',
        category: '이미지',
        evidence: 'Pod event reason=ImagePullBackOff',
        id: 'local-imagepull',
        impact: 'catalog source 갱신 지연',
        lastObservedAt: iso(-90_000),
        namespace: 'openshift-marketplace',
        nextCheck: 'image, registry secret, event 확인',
        priority: 2,
        reason: 'ImagePullBackOff',
        resource: {
          kind: 'Pod',
          name: 'appscan360-catalog',
          namespace: 'openshift-marketplace',
        },
        severity: '확인 필요',
        source: 'local-simulator',
        status: 'warning',
        statusLabel: '근거 더 수집',
        title: 'ImagePullBackOff 원인 확인',
        type: 'pod',
      },
    ],
    normalSignals: ['Node Ready 1/1', 'Operator 정상'],
    query: {
      limit: 10,
      namespace: 'local-only',
      sinceMinutes: 60,
    },
    safety: {
      methodsUsed: ['local-fixture'],
      mode: 'local-simulator',
      mutationsEnabled: false,
      unrestrictedCommandsEnabled: true,
    },
    status: 'attention',
    statusLabel: '로컬 이상 징후 2건',
    totals: {
      attention: 1,
      danger: 1,
      total: 2,
      warning: 1,
    },
  },
});

const actionCandidateSummary = () => {
  const candidates = simulator.records.sealedActionPlans.map((record, index) => {
    const sealed = record.spec?.sealedActionPlan || {};
    const planTarget = sealed.target || {};
    const toolName = sealed.action?.toolName || 'local_action';
    return {
      approvalRequired: true,
      confidence: '높음',
      evidence: `${targetKey(planTarget)} 근거 ${index + 1}`,
      evidenceRefs: [{ id: `ev-${simulator.scenarioId}-${index}`, type: 'local' }],
      executable: true,
      executionPolicy: {
        executionEnabled: true,
        mode: 'local-simulator',
        mutationVerbsDisabled: true,
        proposalOnly: false,
      },
      expectedImpact: sealed.expectedImpact || 'local simulator state only',
      id: `candidate-${record.metadata?.name || index}`,
      priority: index + 1,
      prerequisiteChecks: ['대상 리소스 확인', 'local simulator mode 확인'],
      recommendationSteps: [sealed.action?.summary || 'Action Plan 승인 후 simulator 실행'],
      riskLabel: sealed.safety?.risk || 'medium',
      riskLevel: sealed.safety?.risk || 'medium',
      severity: index === 0 ? '위험' : '주의',
      sourceFindingId: `finding-${simulator.scenarioId}-${index}`,
      sourceType: 'local-simulator',
      statusLabel: '승인 필요',
      target: planTarget,
      title: `${planTarget.name || 'local-target'} 조치 후보`,
      verificationChecks: [sealed.verification?.expected || 'ExecutionRecord 확인'],
    };
  });

  return {
    apiVersion: 'aiops.komsco/v1alpha1',
    kind: 'AIOpsActionCandidateSummary',
    metadata: {
      generatedAt: iso(),
      name: 'local-action-candidates',
    },
    spec: {
      candidates,
      dataSources: dataSources(),
      safety: {
        forbiddenMutationVerbs: ['company-okd-apply', 'company-okd-create', 'company-okd-delete'],
        methodsUsed: ['local-fixture', 'cdp-fetch-intercept'],
        mode: 'local-simulator',
        mutationsEnabled: false,
        proposalOnly: false,
        unrestrictedCommandsEnabled: true,
      },
      source: {
        anomalySummaryName: 'local-anomalies',
        requiredDataSourceGaps: [],
      },
      status: candidates.length > 0 ? 'candidates' : 'normal',
      statusLabel: candidates.length > 0 ? `조치 후보 ${candidates.length}건` : '조치 후보 없음',
      totals: {
        approvalRequired: candidates.length,
        blockedByRequiredSourceGap: 0,
        highRisk: candidates.filter((candidate) => candidate.riskLevel === 'high').length,
        shown: candidates.length,
        total: candidates.length,
      },
    },
  };
};

const eventFeed = () => ({
  metadata: {
    generatedAt: iso(),
    name: 'local-aiops-events',
  },
  spec: {
    items: [
      {
        category: '워크로드',
        detail: 'CrashLoopBackOff detected in local fixture',
        id: 'event-local-crashloop',
        message: 'aiops-scenario-crashloop restart increased',
        namespace: 'komsco-ai-local',
        reason: 'CrashLoopBackOff',
        severity: 'risk',
        source: 'local-simulator',
        target: 'komsco-ai-local/aiops-scenario-crashloop',
        time: iso(-60_000),
        title: 'CrashLoopBackOff',
        type: 'Pod',
      },
      {
        category: '이미지',
        detail: 'Image pull check required',
        id: 'event-local-imagepull',
        message: 'appscan360-catalog image pull backoff',
        namespace: 'openshift-marketplace',
        reason: 'ImagePullBackOff',
        severity: 'warn',
        source: 'local-simulator',
        target: 'openshift-marketplace/appscan360-catalog',
        time: iso(-90_000),
        title: 'ImagePullBackOff',
        type: 'Pod',
      },
    ],
    pollIntervalSeconds: 30,
    sources: ['local-simulator'],
  },
});

const overview = () => ({
  apiVersion: 'aiops.komsco/v1alpha1',
  kind: 'AIOpsOverview',
  metadata: {
    generatedAt: iso(),
    name: 'local-aiops-overview',
  },
  spec: {
    actionCandidates: actionCandidateSummary(),
    anomalies: anomalySummary(),
    clusterSummary: clusterSummary(),
    controlTower: {
      attentionCount: 2,
      healthScore: 92,
      mode: 'local-simulator',
      name: 'Local AIOps Control Tower',
      status: 'attention',
      statusLabel: '로컬 시나리오 검증 중',
      target: simulator.scenarioId,
    },
    dataSources: dataSources(),
    monitoring: {
      probe: {
        httpStatus: 200,
        query: 'local-simulator',
        reason: 'CDP fixture active',
        resultCount: 2,
        status: 'available',
      },
      urls: {
        alertmanagerConfigured: true,
        prometheusConfigured: true,
        thanosConfigured: true,
      },
    },
    safety: {
      executionDefault: true,
      mutationsEnabled: false,
      unrestrictedCommandsEnabled: true,
    },
  },
});

const chatStream = () =>
  [
    'event: text',
    'data: {"content":"현재 판단\\n- 로컬 simulator 응답입니다.\\n\\nAction Plan\\n- fixture 기반으로 검증합니다.","answerContract":"local-simulator"}',
    '',
    'event: done',
    'data: {}',
    '',
  ].join('\n');

const parseBody = (postData) => {
  if (!postData) {
    return {};
  }
  try {
    return JSON.parse(postData);
  } catch (_error) {
    return {};
  }
};

const routeAction = async (requestId, pathName, method, postData) => {
  const body = parseBody(postData);

  if (pathName.endsWith('/actions/plans') && method === 'POST') {
    const proposalId = body.proposalId || body.id || '';
    const proposal = simulator.records.actionProposals.find(
      (record) => record.metadata?.name === proposalId,
    );
    if (!proposal) {
      return fulfillJson(requestId, { detail: `proposal ${proposalId} not found` }, 404);
    }
    const proposalTarget = proposal.spec?.candidateActionRequest?.target || crashTarget;
    const toolName =
      proposal.spec?.candidateActionRequest?.action?.toolName || 'rollout_restart_deployment';
    const suffix = proposalId.replace(/^proposal-/, '');
    let plan = findPlan(`plan-${suffix}`);
    if (!plan) {
      plan = planRecord(suffix, proposalTarget, toolName);
      simulator.records.sealedActionPlans.push(plan);
    }
    return fulfillJson(requestId, plan);
  }

  if (pathName.endsWith('/actions/approvals') && method === 'POST') {
    const planId = body.planId || '';
    const expectedPlanDigest = body.expectedPlanDigest || body.planDigest || '';
    const plan = findPlan(planId, expectedPlanDigest);
    if (!plan) {
      return fulfillJson(requestId, { detail: `plan ${planId} not found` }, 404);
    }
    const sealed = plan.spec?.sealedActionPlan || {};
    const digest = sealed.digest?.planDigest || '';
    if (expectedPlanDigest && expectedPlanDigest !== digest) {
      return fulfillJson(requestId, { detail: 'expectedPlanDigest mismatch' }, 409);
    }
    const id = plan.metadata.name.replace(/^plan-/, '');
    const toolName = sealed.action?.toolName || 'local_action';
    const record = approvalRecord(id, sealed.target || crashTarget, toolName, 'approved');
    simulator.records.approvalDecisions = simulator.records.approvalDecisions.filter(
      (item) => item.metadata?.name !== record.metadata.name,
    );
    simulator.records.approvalDecisions.push(record);
    return fulfillJson(requestId, record);
  }

  if (pathName.endsWith('/actions/rejections') && method === 'POST') {
    const planId = body.planId || '';
    const expectedPlanDigest = body.expectedPlanDigest || body.planDigest || '';
    const plan = findPlan(planId, expectedPlanDigest);
    if (!plan) {
      return fulfillJson(requestId, { detail: `plan ${planId} not found` }, 404);
    }
    const sealed = plan.spec?.sealedActionPlan || {};
    const id = plan.metadata.name.replace(/^plan-/, '');
    const toolName = sealed.action?.toolName || 'local_action';
    const record = approvalRecord(id, sealed.target || crashTarget, toolName, 'rejected');
    simulator.records.approvalDecisions.push(record);
    return fulfillJson(requestId, record);
  }

  if (pathName.endsWith('/actions/execute') && method === 'POST') {
    const approvalId = body.approvalId || '';
    const approval = simulator.records.approvalDecisions.find(
      (record) =>
        record.metadata?.name === approvalId ||
        record.spec?.approvalDecision?.approvalId === approvalId,
    );
    if (!approval || approval.spec?.approvalDecision?.status === 'rejected') {
      return fulfillJson(requestId, { detail: `approval ${approvalId} is not executable` }, 409);
    }
    const id = approval.spec.approvalDecision.planId.replace(/^plan-/, '');
    const recordTarget = approval.spec.approvalDecision.target || crashTarget;
    const toolName = approval.spec.approvalDecision.action?.toolName || 'local_action';
    const record = executionRecord(id, recordTarget, toolName);
    simulator.records.executionRecords.push(record);
    if (id === 'create-three-pods') {
      simulator.runtime.createdPods = {
        current: 3,
        desired: 3,
        ready: '3/3',
      };
    }
    if (id === 'scale-gap') {
      simulator.runtime.scale = {
        current: 3,
        desired: 3,
        ready: '3/3',
      };
    }
    return fulfillJson(requestId, record);
  }

  return fulfillJson(requestId, { detail: 'unsupported local action route' }, 404);
};

const handleFetchPaused = async (params) => {
  const { request, requestId } = params;
  let parsed;
  try {
    parsed = new URL(request.url);
  } catch (_error) {
    await continueRequest(requestId);
    return;
  }
  const pathName = parsed.pathname;
  const method = request.method || 'GET';

  if (
    !pathName.includes('/ai-gateway/v1/') &&
    !pathName.includes('/api/kubernetes/apis/user.openshift.io/v1/users/~') &&
    !(parsed.host === 'localhost:5174' && pathName.startsWith('/v1/'))
  ) {
    await continueRequest(requestId);
    return;
  }

  simulator.interceptedRequests.push({
    method,
    path: pathName,
    scenarioId: simulator.scenarioId,
    url: request.url,
  });

  try {
    if (pathName.includes('/api/kubernetes/apis/user.openshift.io/v1/users/~')) {
      return fulfillJson(requestId, {
        fullName: 'Local Simulator Admin',
        identities: ['local:admin'],
        kind: 'User',
        metadata: {
          name: 'admin',
        },
      });
    }
    if (pathName.endsWith('/v1/auth/subject')) {
      return fulfillJson(requestId, subject());
    }
    if (pathName.endsWith('/v1/cluster/summary')) {
      return fulfillJson(requestId, clusterSummary());
    }
    if (pathName.endsWith('/v1/aiops/status')) {
      return fulfillJson(requestId, buildStatus());
    }
    if (pathName.endsWith('/v1/aiops/overview')) {
      return fulfillJson(requestId, overview());
    }
    if (pathName.endsWith('/v1/aiops/events')) {
      return fulfillJson(requestId, eventFeed());
    }
    if (pathName.endsWith('/v1/aiops/action-candidates')) {
      return fulfillJson(requestId, actionCandidateSummary());
    }
    if (pathName.endsWith('/v1/rag/uploads')) {
      return fulfillJson(requestId, {
        apiVersion: 'aiops.komsco/v1alpha1',
        kind: 'RagUploadedDocumentList',
        metadata: {
          generatedAt: iso(),
          name: 'local-rag-uploads',
        },
        spec: {
          backend: {
            endpointConfigured: true,
            status: 'local-simulator',
          },
          documents: [],
          status: 'empty',
          totals: {
            documents: 0,
          },
        },
      });
    }
    if (pathName.endsWith('/v1/rag/search')) {
      return fulfillJson(requestId, {
        documents: [
          {
            id: 'local-runbook',
            title: 'Local AIOps Runbook',
            type: 'runbook',
          },
        ],
      });
    }
    if (pathName.endsWith('/v1/chat/stream')) {
      return fulfill(requestId, 200, 'text/event-stream; charset=utf-8', chatStream());
    }
    if (pathName.includes('/v1/actions/')) {
      return routeAction(requestId, pathName, method, request.postData);
    }
    return fulfillJson(requestId, { ok: true, scenarioId: simulator.scenarioId });
  } catch (error) {
    return fulfillJson(
      requestId,
      {
        detail: error instanceof Error ? error.message : String(error),
      },
      500,
    );
  }
};

const sourceReview = () => {
  const plan = readFile('docs/Ver.0.2.8.1/local-aiops-scenario-test-plan.md');
  const guide = readFile('docs/Ver.0.2.8.1/local-aiops-manual-test-guide.md');
  const design = readFile('DESIGN.md');
  const script = readFile('scripts/verify-v0281-local-aiops-scenarios.cjs');

  assert(plan.includes('회사 OKD mutation 금지') || plan.includes('회사 OKD를 변경하지 않고'), 'local plan must explicitly forbid company OKD mutation');
  assert(guide.includes('10개 수동 테스트 질문'), 'manual guide must list manual scenarios');
  assert(design.includes('OpenShift/OCP 전용 Agentic Operator for AIOps'), 'DESIGN.md product position missing');
  assert(script.includes('Fetch.fulfillRequest'), 'verifier must use local CDP fixture responses');
  assert(script.includes('companyMutationExecuted: false'), 'verifier must record no company mutation');
  const ocPrefix = 'o' + 'c ';
  const blockedMutationCommands = ['apply', 'create', 'delete', 'patch', 'scale'].map(
    (verb) => `${ocPrefix}${verb}`,
  );
  assert(
    blockedMutationCommands.every((command) => !script.includes(command)),
    'verifier must not run oc mutation commands',
  );
};

const launchChrome = (url) =>
  spawn(
    chrome,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--window-size=1440,960',
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      url,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

const fetchJson = async (url) => {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`${url} -> ${res.status}`);
  }
  return res.json();
};

const waitForJson = async (url, timeoutMs = 30000) => {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      return await fetchJson(url);
    } catch (_error) {
      await sleep(250);
    }
  }
  throw new Error(`Timed out waiting for ${url}`);
};

const send = (method, params = {}) => {
  const id = nextId++;
  chromeWebSocket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
};

const evaluate = async (expression, timeout = 20000) => {
  const result = await send('Runtime.evaluate', {
    awaitPromise: true,
    expression,
    returnByValue: true,
    timeout,
  });
  if (result.exceptionDetails) {
    throw new Error(
      result.exceptionDetails.exception?.description ||
        result.exceptionDetails.text ||
        JSON.stringify(result.exceptionDetails),
    );
  }
  return result.result?.value;
};

const poll = async (expression, predicate, label, timeoutMs = 60000) => {
  const started = Date.now();
  let last;
  while (Date.now() - started < timeoutMs) {
    last = await evaluate(expression);
    if (predicate(last)) {
      return last;
    }
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${label}. Last=${JSON.stringify(last)}`);
};

const setupBrowser = async () => {
  chromeProcess = launchChrome(consoleUrl);
  let stderr = '';
  chromeProcess.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });

  const version = await waitForJson(`http://127.0.0.1:${port}/json/version`);
  const targets = await waitForJson(`http://127.0.0.1:${port}/json/list`);
  const targetPage = targets.find((item) => item.type === 'page') || targets[0];
  if (!targetPage?.webSocketDebuggerUrl) {
    throw new Error(`No page websocket target. Chrome stderr: ${stderr.slice(0, 1000)}`);
  }

  chromeWebSocket = new WebSocket(targetPage.webSocketDebuggerUrl);
  chromeWebSocket.on('message', (raw) => {
    const msg = JSON.parse(String(raw));
    if (msg.method === 'Runtime.exceptionThrown') {
      runtimeErrors.push(msg.params?.exceptionDetails || msg.params);
      return;
    }
    if (msg.method === 'Log.entryAdded') {
      runtimeErrors.push(msg.params?.entry || msg.params);
      return;
    }
    if (msg.method === 'Fetch.requestPaused') {
      handleFetchPaused(msg.params).catch((error) => {
        console.error(`Fetch intercept failed: ${error.stack || error}`);
      });
      return;
    }
    if (!msg.id || !pending.has(msg.id)) {
      return;
    }
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) {
      reject(new Error(JSON.stringify(msg.error)));
    } else {
      resolve(msg.result);
    }
  });

  await new Promise((resolve, reject) => {
    chromeWebSocket.once('open', resolve);
    chromeWebSocket.once('error', reject);
  });

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Log.enable');
  await send('Fetch.enable', {
    patterns: [
      { requestStage: 'Request', urlPattern: '*ai-gateway/v1/*' },
      { requestStage: 'Request', urlPattern: '*api/kubernetes/apis/user.openshift.io/v1/users/~*' },
      { requestStage: 'Request', urlPattern: 'http://localhost:5174/v1/*' },
    ],
  });
  return version;
};

const navigate = async (url) => {
  await send('Page.navigate', { url });
  await poll(
    `document.readyState === 'complete' && Boolean(document.body?.innerText?.trim())`,
    Boolean,
    `page ready ${url}`,
    90000,
  );
};

const installConversationFixture = async (scenario) => {
  const activeKey = 'komsco-ai.assistant.active-conversation.v1';
  const historyKey = 'komsco-ai.assistant.conversation-history.v1';
  const languageKey = 'komsco-ai.assistant.ui-language.v1';
  const now = Date.now();
  const messages = [
    {
      content: scenario.question,
      role: 'user',
      timestamp: now - 8000,
    },
    {
      answerContract: scenario.actionRefs.length ? 'local-action-plan' : undefined,
      content: scenario.content,
      role: 'assistant',
      timestamp: now - 7000,
    },
  ];
  const snapshot = {
    activeSessionId: `local-${scenario.id}`,
    actionRefs: scenario.actionRefs,
    actionTargetKeys: scenario.actionRefs.map((ref) => ref.targetKey),
    conversationId: `conversation-${scenario.id}`,
    messages,
  };

  const history = scenario.historyScenario
    ? [
        {
          ...snapshot,
          id: `local-${scenario.id}`,
          title: '현재 화면의 대상 리소스에 대해 가능한 조치',
          updatedAt: now,
        },
        {
          id: 'local-history-alerts',
          title: '최근 OpenShift 경고와 우선 확인할 항목',
          updatedAt: now - 120_000,
          conversationId: 'conversation-history-alerts',
          messages: [
            { content: '최근 OpenShift 경고를 정리해줘.', role: 'user', timestamp: now - 130_000 },
            { content: scenarioDefinitions[0].content, role: 'assistant', timestamp: now - 129_000 },
          ],
          actionRefs: [
            actionRef(
              'history',
              planRecord('history-plan', crashTarget, 'rollout_restart_deployment'),
              'plan',
              '2단계 · 승인 필요',
            ),
          ],
          actionTargetKeys: [targetKey(crashTarget)],
        },
        {
          id: 'local-history-executed',
          title: '승인 필요 · 비정상 Pod 격리 조치',
          updatedAt: now - 240_000,
          conversationId: 'conversation-history-executed',
          messages: [
            { content: 'CrashLoopBackOff 복구해줘.', role: 'user', timestamp: now - 250_000 },
            { content: scenarioDefinitions[1].content, role: 'assistant', timestamp: now - 249_000 },
          ],
          actionRefs: [
            actionRef(
              'history',
              executionRecord('history-execution', executeTarget, 'rollout_restart_deployment'),
              'execution',
              '4단계 · 실행 완료',
            ),
          ],
          actionTargetKeys: [targetKey(executeTarget)],
        },
      ]
    : [
        {
          ...snapshot,
          id: `local-${scenario.id}`,
          title: scenario.title,
          updatedAt: now,
        },
      ];

  const payload = JSON.stringify({ activeKey, historyKey, history, languageKey, snapshot });
  await evaluate(`(() => {
    const payload = ${payload};
    localStorage.setItem(payload.activeKey, JSON.stringify(payload.snapshot));
    localStorage.setItem(payload.historyKey, JSON.stringify(payload.history));
    localStorage.setItem(payload.languageKey, JSON.stringify('ko'));
    return true;
  })()`);
};

const openAssistant = async () => {
  const alreadyOpen = await evaluate(`Boolean(document.querySelector('.komsco-ai__surface'))`);
  if (alreadyOpen) {
    return;
  }
  await poll(
    `Boolean(document.querySelector('.komsco-ai__fab'))`,
    Boolean,
    'assistant FAB visible',
    60000,
  );
  await sleep(750);
  for (let attempt = 0; attempt < 5; attempt += 1) {
    const opened = await evaluate(`(() => {
      if (document.querySelector('.komsco-ai__surface')) return true;
      const fab = document.querySelector('.komsco-ai__fab');
      if (!fab) return false;
      fab.scrollIntoView({ block: 'center', inline: 'center' });
      const eventInit = { bubbles: true, cancelable: true, view: window };
      for (const type of ['pointerdown', 'mousedown', 'mouseup', 'click']) {
        const EventCtor = type === 'pointerdown' && typeof PointerEvent === 'function' ? PointerEvent : MouseEvent;
        fab.dispatchEvent(new EventCtor(type, eventInit));
      }
      if (typeof fab.click === 'function') fab.click();
      return Boolean(document.querySelector('.komsco-ai__surface'));
    })()`);
    if (opened) {
      break;
    }
    await sleep(800);
    const nowOpen = await evaluate(`Boolean(document.querySelector('.komsco-ai__surface'))`);
    if (nowOpen) {
      break;
    }
  }
  if (!(await evaluate(`Boolean(document.querySelector('.komsco-ai__surface'))`))) {
    const rect = await evaluate(`(() => {
      const fab = document.querySelector('.komsco-ai__fab');
      const box = fab?.getBoundingClientRect();
      return box ? { x: box.left + box.width / 2, y: box.top + box.height / 2 } : null;
    })()`);
    if (rect) {
      await send('Input.dispatchMouseEvent', {
        button: 'left',
        buttons: 1,
        clickCount: 1,
        type: 'mousePressed',
        x: rect.x,
        y: rect.y,
      });
      await send('Input.dispatchMouseEvent', {
        button: 'left',
        buttons: 0,
        clickCount: 1,
        type: 'mouseReleased',
        x: rect.x,
        y: rect.y,
      });
      await sleep(800);
    }
  }
  try {
    await poll(
      `Boolean(document.querySelector('.komsco-ai__surface'))`,
      Boolean,
      'assistant surface open',
      15000,
    );
  } catch (error) {
    await evaluate(`(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const detailsButton = buttons.find((button) => (button.textContent || '').includes('Show details'));
      detailsButton?.click();
      return true;
    })()`).catch(() => false);
    await sleep(250);
    const evidence = await evaluate(`(() => {
      const fab = document.querySelector('.komsco-ai__fab');
      const rect = fab?.getBoundingClientRect();
      return {
        bodySample: (document.body?.innerText || '').slice(0, 600),
        detailsSample: (document.body?.innerText || '').slice(0, 2400),
        fabDisabled: Boolean(fab?.disabled),
        fabHtml: fab?.outerHTML?.slice(0, 800) || '',
        fabRect: rect ? { left: rect.left, top: rect.top, width: rect.width, height: rect.height } : null,
        surfaceCount: document.querySelectorAll('.komsco-ai__surface').length
      };
    })()`);
    throw new Error(`${error.message}\n${JSON.stringify({ ...evidence, runtimeErrors: runtimeErrors.slice(-5) }, null, 2)}`);
  }
};

const setExecutionMode = async (mode) => {
  const label = mode === 'execute' ? '실행 가능' : mode === 'unrestricted' ? '실행 무제한' : '읽기 전용';
  const clicked = await evaluate(`(() => {
    const buttons = Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button'));
    const button = buttons.find((item) => (item.textContent || '').includes('${label}'));
    if (!button) return false;
    button.click();
    return true;
  })()`);
  assert(clicked, `execution mode button not found: ${label}`);
  await sleep(300);
};

const openHistory = async () => {
  const isOpen = await evaluate(`(() => {
    const sidebar = document.querySelector('.komsco-ai__history-sidebar');
    const rect = sidebar?.getBoundingClientRect();
    return Boolean(rect && rect.width > 160);
  })()`);
  if (!isOpen) {
    await evaluate(`document.querySelector('.komsco-ai__sidebar-toggle')?.click(); true;`);
  }
  await poll(
    `(() => {
      const sidebar = document.querySelector('.komsco-ai__history-sidebar');
      const rect = sidebar?.getBoundingClientRect();
      return Boolean(rect && rect.width > 160);
    })()`,
    Boolean,
    'history sidebar open',
    60000,
  );
};

const screenshot = async (scenarioId) => {
  const result = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  const file = path.join(cli.screenshotDir, `${scenarioId}.png`);
  fs.writeFileSync(file, Buffer.from(result.data, 'base64'));
  return file;
};

const readUi = async () =>
  evaluate(`(() => {
    const text = document.body?.innerText || '';
    const answerContent = document.querySelector('.komsco-ai__message--assistant .komsco-ai__message-content');
    const answerStyle = answerContent ? getComputedStyle(answerContent) : null;
    const header = document.querySelector('.komsco-ai__header');
    const surface = document.querySelector('.komsco-ai__surface');
    const avatar = document.querySelector('.komsco-ai__message--assistant .komsco-ai__message-avatar');
    const emptyMark = document.querySelector('.komsco-ai__empty-mark');
    const avatarStyle = avatar ? getComputedStyle(avatar) : null;
    const emptyStyle = emptyMark ? getComputedStyle(emptyMark) : null;
    const actionCards = Array.from(document.querySelectorAll('.komsco-ai__answer-action-card'));
    const buttons = Array.from(document.querySelectorAll('.komsco-ai__answer-action-controls .komsco-ai__action-button'));
    const sections = Array.from(document.querySelectorAll('.komsco-ai__runbook-section-title')).map((el) => el.textContent.trim());
    return {
      actionButtonLabels: buttons.map((el) => el.textContent.trim()),
      actionButtonSteps: buttons.map((el) => el.getAttribute('data-answer-action-step')),
      actionCards: actionCards.length,
      disabledButtons: buttons.filter((el) => el.disabled).length,
      fontSize: answerStyle ? parseFloat(answerStyle.fontSize) : 0,
      lineHeight: answerStyle ? parseFloat(answerStyle.lineHeight) : 0,
      rawTerms: ['Tool Plan', 'source:', 'score=', 'post_answer', 'RCA 문맥 연결', 'evict_one_unhealthy_controller_owned_pod']
        .filter((term) => text.includes(term)),
      sections,
      text,
      avatarBackground: avatarStyle?.backgroundColor || '',
      avatarBorder: avatarStyle?.borderTopWidth || '',
      emptyBackground: emptyStyle?.backgroundColor || '',
      emptyBorder: emptyStyle?.borderTopWidth || '',
      surfaceResponding: Boolean(surface?.classList.contains('komsco-ai__surface--responding')),
      headerRail: header ? (() => {
        const original = surface;
        if (original) original.classList.add('komsco-ai__surface--responding');
        const rail = getComputedStyle(header, '::after');
        return {
          animationName: rail.animationName,
          display: rail.display,
          height: rail.height,
        };
      })() : null
    };
  })()`);

const expandRunbookSections = async () => {
  await evaluate(`(() => {
    for (const section of document.querySelectorAll('.komsco-ai__runbook-section')) {
      section.open = true;
    }
    return true;
  })()`);
  await sleep(150);
};

const clickActionStep = async (step) => {
  const clicked = await evaluate(`(() => {
    const buttons = Array.from(document.querySelectorAll('.komsco-ai__answer-action-controls .komsco-ai__action-button'));
    const button = buttons.find((item) => item.getAttribute('data-answer-action-step') === '${step}');
    if (!button) return false;
    button.click();
    return true;
  })()`);
  assert(clicked, `Action button not found: ${step}`);
  await sleep(800);
};

const simulatorEvidence = () => ({
  companyMutationExecuted: simulator.companyMutationExecuted,
  executionRecords: simulator.records.executionRecords.length,
  interceptedRequests: simulator.interceptedRequests.length,
  mutationCommands: simulator.clusterMutationCommands,
  records: {
    approvals: simulator.records.approvalDecisions.length,
    executions: simulator.records.executionRecords.length,
    plans: simulator.records.sealedActionPlans.length,
    proposals: simulator.records.actionProposals.length,
  },
  runtime: deepClone(simulator.runtime),
});

const verifyScenarioSpecifics = async (scenario, ui) => {
  assert(ui.fontSize >= 14, 'assistant answer font must be at least 14px', ui);
  assert(ui.rawTerms.filter((term) => term !== 'evict_one_unhealthy_controller_owned_pod').length === 0, 'default UI exposes raw internal terms', ui.rawTerms);
  assert(simulator.clusterMutationCommands.length === 0, 'verifier must not record company mutation commands', simulatorEvidence());

  if (scenario.expectedNoAction) {
    assert(ui.actionCards === 0, 'read-only alert triage must not render Action Plan cards', ui);
  }

  if (scenario.id === '02-crashloop-action-plan') {
    assert(ui.actionCards === 1, 'CrashLoopBackOff must show one Action Plan card', ui);
    assert(
      ui.actionButtonSteps.includes('approve-plan') || ui.actionButtonSteps.includes('approve-execute-plan'),
      'CrashLoopBackOff must expose an approval action',
      ui,
    );
    assert(new Set(ui.actionButtonSteps).size === ui.actionButtonSteps.length, 'CrashLoopBackOff action buttons must not duplicate', ui);
  }

  if (scenario.expectedNoEviction) {
    assert(!ui.text.includes('evict_one_unhealthy_controller_owned_pod'), 'ImagePullBackOff must not suggest pod eviction', ui);
    assert(ui.text.includes('근거 더 수집') || ui.text.includes('image') || ui.text.includes('secret'), 'ImagePullBackOff must prioritize image/secret evidence', ui);
  }

  if (scenario.id === '04-create-three-pods') {
    assert(simulator.runtime.createdPods?.current === 0, 'Pod create state changed before approval', simulatorEvidence());
    assert(ui.text.includes('생성 수량') && ui.text.includes('3'), 'Pod create answer must show quantity 3', ui);
    await clickActionStep('approve-plan');
    await poll(
      `document.body?.innerText?.includes('Action plan을 승인했습니다.') || Boolean(document.querySelector('[data-answer-action-step="execute-approval"]'))`,
      Boolean,
      'pod create approval notice',
      30000,
    );
    await clickActionStep('execute-approval');
    assert(simulator.runtime.createdPods?.ready === '3/3', 'Pod create simulator state must become ready 3/3 after execution', simulatorEvidence());
  }

  if (scenario.id === '05-deployment-scale-gap') {
    assert(ui.text.includes('현재 1개') && ui.text.includes('목표 3개'), 'scale answer must show current/target gap', ui);
    assert(ui.actionCards === 1, 'scale with gap must show one Action Plan', ui);
  }

  if (scenario.id === '06-readonly-action-request') {
    assert(ui.actionCards >= 1, 'read-only mode must still show plan state', ui);
    assert(ui.actionButtonSteps.length === 0, 'read-only mode must hide action buttons', ui);
    assert(ui.text.includes('읽기 전용 모드라 조치 버튼은 숨기고'), 'read-only mode must show one clear explanation', ui);
  }

  if (scenario.id === '07-approval-rejection') {
    await clickActionStep('reject-plan');
    assert(
      simulator.records.approvalDecisions.some(
        (record) => record.spec?.approvalDecision?.status === 'rejected',
      ),
      'reject action must create rejected approval record',
      simulatorEvidence(),
    );
    assert(simulator.records.executionRecords.length === 0, 'reject action must not create execution record', simulatorEvidence());
  }

  if (scenario.id === '08-approval-execution') {
    await clickActionStep('approve-plan');
    await poll(
      `Boolean(document.querySelector('[data-answer-action-step="execute-approval"]'))`,
      Boolean,
      'execute button after approval',
      30000,
    );
    await clickActionStep('execute-approval');
    assert(simulator.records.executionRecords.length >= 1, 'approved action must create execution record', simulatorEvidence());
    assert(
      simulator.records.executionRecords.some(
        (record) => record.spec?.mutationOutcome?.status === 'mutation_simulated' &&
          record.spec?.remediationOutcome?.status === 'verification_passed',
      ),
      'execution record must show simulated mutation and verification passed',
      simulatorEvidence(),
    );
  }

  if (scenario.historyScenario) {
    await openHistory();
    const before = await evaluate(`(() => Array.from(document.querySelectorAll('.komsco-ai__history-item-row .komsco-ai__history-item span')).map((el) => el.textContent.trim()))()`);
    const metrics = await evaluate(`(() => ({
      actionRefs: document.querySelectorAll('.komsco-ai__history-action-ref').length,
      groupedRefs: Array.from(document.querySelectorAll('.komsco-ai__history-action-ref')).filter((el) => Boolean(el.closest('.komsco-ai__history-item-row'))).length,
      width: Math.round(document.querySelector('.komsco-ai__history-sidebar')?.getBoundingClientRect().width || 0)
    }))()`);
    assert(metrics.actionRefs >= 2, 'history sidebar must show nested action refs', metrics);
    assert(metrics.groupedRefs === metrics.actionRefs, 'history action refs must be grouped under conversations', metrics);
    assert(metrics.width >= 260, 'history sidebar must be wider than the narrow old panel', metrics);
    await evaluate(`document.querySelectorAll('.komsco-ai__history-action-ref')[1]?.click(); true;`);
    await sleep(600);
    await openHistory();
    const after = await evaluate(`(() => Array.from(document.querySelectorAll('.komsco-ai__history-item-row .komsco-ai__history-item span')).map((el) => el.textContent.trim()))()`);
    assert(JSON.stringify(before) === JSON.stringify(after), 'history action click must not reorder conversation list', { before, after });
  }

  if (scenario.trustUiScenario) {
    assert(ui.headerRail?.animationName === 'komsco-ai-header-bottom-scan', 'responding header must show light rail animation', ui.headerRail);
    assert(ui.avatarBackground === 'rgba(0, 0, 0, 0)' || ui.avatarBackground === 'transparent', 'assistant message avatar must not keep outer filled frame', ui);
    assert(ui.avatarBorder === '0px', 'assistant message avatar must not keep outer border', ui);
    assert(ui.emptyBackground === 'rgba(0, 0, 0, 0)' || ui.emptyBackground === 'transparent' || ui.emptyBackground === '', 'empty assistant icon frame must be removed', ui);
  }
};

const runScenario = async (scenario, index) => {
  resetSimulator(scenario);
  await navigate(`${consoleUrl}&scenario=${encodeURIComponent(scenario.id)}&run=${Date.now()}`);
  await installConversationFixture(scenario);
  await send('Page.reload', { ignoreCache: true });
  await poll(
    `document.readyState === 'complete' && Boolean(document.body?.innerText?.trim())`,
    Boolean,
    `${scenario.id} reloaded`,
    90000,
  );
  await openAssistant();
  await setExecutionMode(scenario.executionMode || 'read-only');
  await poll(
    `document.body?.innerText?.includes(${JSON.stringify(scenario.title)}) || document.body?.innerText?.includes(${JSON.stringify(scenario.question.slice(0, 16))})`,
    Boolean,
    `${scenario.id} conversation visible`,
    30000,
  );
  await expandRunbookSections();

  const uiBefore = await readUi();
  await verifyScenarioSpecifics(scenario, uiBefore);
  const shot = await screenshot(`${String(index + 1).padStart(2, '0')}-${scenario.id}`);
  const uiAfter = await readUi();

  return {
    id: scenario.id,
    pass: true,
    question: scenario.question,
    screenshot: path.relative(root, shot),
    simulator: simulatorEvidence(),
    title: scenario.title,
    ui: {
      actionButtonSteps: uiAfter.actionButtonSteps,
      actionCards: uiAfter.actionCards,
      fontSize: uiAfter.fontSize,
      rawTerms: uiAfter.rawTerms,
      sections: uiAfter.sections,
    },
  };
};

const verifyPortal = async () => {
  await navigate(`${portalUrl}&run=${Date.now()}`);
  const metrics = await poll(
    `(() => {
      const text = document.body?.innerText || '';
      return {
        ready: Boolean(text.trim()),
        hasLocalSimulator: text.includes('api.local-aiops.invalid') || text.includes('92%'),
        hasAuthNeeded: text.includes('OpenShift 인증 필요'),
        hasGatewayConnected: text.includes('게이트웨이 연결됨'),
        hasGatewayDisconnected: text.includes('게이트웨이 연결 끊김'),
        sample: text.slice(0, 600)
      };
    })()`,
    (value) => value?.ready && value.hasLocalSimulator && !value.hasGatewayDisconnected,
    'standalone portal local connection',
    90000,
  );
  assert(!metrics.hasGatewayDisconnected, '5174 portal must not show gateway disconnected in local simulator mode', metrics);
  assert(metrics.hasLocalSimulator, '5174 portal must show local simulator cluster data', metrics);
  return metrics;
};

const cleanup = () => {
  if (chromeWebSocket) {
    chromeWebSocket.close();
  }
  if (chromeProcess) {
    chromeProcess.kill('SIGTERM');
  }
};

const main = async () => {
  sourceReview();
  const selected = scenarios.slice(0, Math.max(0, Math.min(cli.runs, scenarios.length)));
  assert(selected.length === cli.runs, `requested ${cli.runs} scenarios but only ${selected.length} available`);

  const chromeVersion = await setupBrowser();
  const startedAt = iso();
  const scenarioResults = [];
  for (let index = 0; index < selected.length; index += 1) {
    const scenario = selected[index];
    scenarioResults.push(await runScenario(scenario, index));
  }
  const portal = await verifyPortal();
  const finishedAt = iso();
  const report = {
    chrome: chromeVersion,
    companyMutationExecuted: false,
    finishedAt,
    localOnly: true,
    mutationCommands: [],
    pass: scenarioResults.every((item) => item.pass),
    portal,
    scenarioCount: scenarioResults.length,
    scenarios: scenarioResults,
    startedAt,
  };
  fs.writeFileSync(cli.report, `${JSON.stringify(report, null, 2)}\n`);
  console.log(JSON.stringify(report, null, 2));
  cleanup();
};

main().catch((error) => {
  cleanup();
  const report = {
    companyMutationExecuted: simulator.companyMutationExecuted,
    error: error.stack || String(error),
    localOnly: true,
    mutationCommands: simulator.clusterMutationCommands,
    pass: false,
    scenarioId: simulator.scenarioId,
  };
  try {
    fs.writeFileSync(cli.report, `${JSON.stringify(report, null, 2)}\n`);
  } catch (_writeError) {
    // Ignore report write failures after a browser crash.
  }
  console.error(error.stack || String(error));
  process.exit(1);
});
