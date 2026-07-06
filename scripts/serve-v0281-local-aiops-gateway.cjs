#!/usr/bin/env node
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');
const { execFile } = require('child_process');

const host = process.env.AIOPS_LOCAL_FIXTURE_HOST || '127.0.0.1';
const port = Number(process.env.AIOPS_LOCAL_FIXTURE_PORT || 18080);
const servePortal = process.env.AIOPS_LOCAL_SERVE_PORTAL === '1';
const repoRoot = path.resolve(__dirname, '..');
const portalDist = path.join(repoRoot, 'komsco-ai-portal', 'dist');
const docsRoot = path.join(repoRoot, 'docs', 'Ver.0.2.8.1');

const nowIso = () => new Date().toISOString();

const LOCAL_SUBJECT = {
  username: 'local-admin',
  uid: 'local-admin-fixture',
  groups: ['system:authenticated', 'aiops-admins'],
};

const LOCAL_TARGET = {
  apiVersion: 'apps/v1',
  kind: 'Deployment',
  namespace: 'komsco-ai-local',
  name: 'aiops-scenario-crashloop',
  uid: 'local-deployment-aiops-scenario-crashloop',
};

const LOCAL_PLAN_DIGEST = 'sha256:local-crashloop-plan-v1';
const LOCAL_TEST_POD_TARGET = {
  apiVersion: 'v1',
  kind: 'Pod',
  namespace: process.env.AIOPS_LOCAL_TEST_POD_NAMESPACE || 'gpu-test-kugnus',
  name: 'aiops-test-pods',
  uid: 'local-pod-aiops-test-pods',
};
const LOCAL_TEST_POD_COUNT = Number(process.env.AIOPS_LOCAL_TEST_POD_COUNT || 3);
const LOCAL_TEST_POD_IMAGE =
  process.env.AIOPS_LOCAL_TEST_POD_IMAGE ||
  'registry.access.redhat.com/ubi9/ubi-minimal:latest';
const LOCAL_TEST_POD_NAME_PREFIX =
  process.env.AIOPS_LOCAL_TEST_POD_NAME_PREFIX || 'aiops-test-pod';
const LOCAL_TEST_POD_PLAN_DIGEST = 'sha256:local-create-test-pods-plan-v1';
const LOCAL_NAMESPACE_CLEANUP_TARGET = {
  apiVersion: 'v1',
  kind: 'Namespace',
  name: process.env.AIOPS_LOCAL_NAMESPACE_CLEANUP_TARGET || 'komsco-aiops-lab',
  uid: 'local-namespace-komsco-aiops-lab',
};
const LOCAL_NAMESPACE_CLEANUP_PLAN_DIGEST = 'sha256:local-namespace-cleanup-plan-v1';
const LOCAL_ACTION_REGISTRY_DIGEST = 'sha256:local-action-registry-v1';
const LOCAL_POLICY_DIGEST = 'sha256:local-policy-v1';
const LOCAL_ACTION_PROPOSALS = new Map();
const LOCAL_SEALED_PLANS = new Map();
const LOCAL_APPROVALS = new Map();
const LOCAL_EXECUTIONS = new Map([
  [
    'execution-local-simulated',
    {
      schemaVersion: 'v1',
      apiVersion: 'aiops.komsco/v1',
      kind: 'ExecutionRecord',
      metadata: { name: 'execution-local-simulated', createdAt: nowIso() },
      spec: {
        executionId: 'execution-local-simulated',
        approvalId: 'approval-local-previous',
        planId: 'plan-local-previous',
        planDigest: 'sha256:local-previous-plan',
        mutationOutcome: {
          status: 'mutation_succeeded',
          reason: 'local simulator only',
        },
        remediationOutcome: {
          status: 'verified',
          reason: 'restart_annotation_observed',
        },
        executorTrace: {
          mutationSubmitted: true,
          companyMutationExecuted: false,
          mode: 'local-only',
        },
      },
      subject: LOCAL_SUBJECT,
    },
  ],
]);
const LOCAL_CHAT_FEEDBACK = new Map();

const actionTypeFromCandidateId = (candidateId = '') => {
  const value = String(candidateId || '');
  if (value.includes('namespace-cleanup')) {
    return 'namespace-cleanup';
  }
  if (value.includes('create-test-pods')) {
    return 'test-pods';
  }
  if (value.includes('crashloop')) {
    return 'crashloop';
  }
  return '';
};

const actionTypeFromProposalId = (proposalId = '') => {
  const value = String(proposalId || '');
  if (value.includes('namespace-cleanup')) {
    return 'namespace-cleanup';
  }
  if (value.includes('test-pods')) {
    return 'test-pods';
  }
  if (value.includes('crashloop')) {
    return 'crashloop';
  }
  return '';
};

const actionTypeFromPlanId = (planId = '') => {
  const value = String(planId || '');
  if (value.includes('namespace-cleanup')) {
    return 'namespace-cleanup';
  }
  if (value.includes('test-pods')) {
    return 'test-pods';
  }
  if (value.includes('crashloop')) {
    return 'crashloop';
  }
  return '';
};

const actionTypeFromPlanDigest = (planDigest = '') => {
  if (planDigest === LOCAL_NAMESPACE_CLEANUP_PLAN_DIGEST) {
    return 'namespace-cleanup';
  }
  if (planDigest === LOCAL_TEST_POD_PLAN_DIGEST) {
    return 'test-pods';
  }
  if (planDigest === LOCAL_PLAN_DIGEST) {
    return 'crashloop';
  }
  return '';
};

const localPlanDigests = () => [
  LOCAL_PLAN_DIGEST,
  LOCAL_TEST_POD_PLAN_DIGEST,
  LOCAL_NAMESPACE_CLEANUP_PLAN_DIGEST,
];

const planDigestForAction = (actionType = 'crashloop') =>
  actionType === 'namespace-cleanup'
    ? LOCAL_NAMESPACE_CLEANUP_PLAN_DIGEST
    : actionType === 'test-pods'
      ? LOCAL_TEST_POD_PLAN_DIGEST
      : LOCAL_PLAN_DIGEST;

const targetForAction = (actionType = 'crashloop') =>
  actionType === 'namespace-cleanup'
    ? LOCAL_NAMESPACE_CLEANUP_TARGET
    : actionType === 'test-pods'
      ? LOCAL_TEST_POD_TARGET
      : LOCAL_TARGET;

const planIdForAction = (actionType = 'crashloop') =>
  actionType === 'namespace-cleanup'
    ? 'plan-local-namespace-cleanup'
    : actionType === 'test-pods'
      ? 'plan-local-test-pods'
      : 'plan-local-crashloop';

const proposalIdForAction = (actionType = 'crashloop') =>
  actionType === 'namespace-cleanup'
    ? 'proposal-local-namespace-cleanup'
    : actionType === 'test-pods'
      ? 'proposal-local-test-pods'
      : 'proposal-local-crashloop';

const actionTitleForAction = (actionType = 'crashloop') =>
  actionType === 'namespace-cleanup'
    ? '미사용 namespace 정리'
    : actionType === 'test-pods'
    ? '테스트 Pod 3개 생성'
    : 'CrashLoopBackOff 복구 조치 후보';

const localAction = (actionType = 'crashloop') => {
  if (actionType === 'namespace-cleanup') {
    return {
      toolName: 'delete_namespace_after_approval',
      toolVersion: 'v1',
      normalizedParameters: {
        name: LOCAL_NAMESPACE_CLEANUP_TARGET.name,
      },
      actionRegistry: {
        version: 'local-fixture',
        digest: LOCAL_ACTION_REGISTRY_DIGEST,
      },
      authorization: {
        apiGroup: '',
        resource: 'namespaces',
        subresource: '',
        verb: 'delete',
      },
    };
  }

  if (actionType === 'test-pods') {
    return {
      toolName: 'create_test_pods',
      toolVersion: 'v1',
      normalizedParameters: {
        namespace: LOCAL_TEST_POD_TARGET.namespace,
        count: LOCAL_TEST_POD_COUNT,
        image: LOCAL_TEST_POD_IMAGE,
        namePrefix: LOCAL_TEST_POD_NAME_PREFIX,
      },
      actionRegistry: {
        version: 'local-fixture',
        digest: LOCAL_ACTION_REGISTRY_DIGEST,
      },
      authorization: {
        apiGroup: '',
        resource: 'pods',
        subresource: '',
        verb: 'create',
      },
    };
  }

  return {
    toolName: 'rollout_restart_deployment',
    toolVersion: 'v1',
    normalizedParameters: {
      namespace: LOCAL_TARGET.namespace,
      name: LOCAL_TARGET.name,
    },
    actionRegistry: {
      version: 'local-fixture',
      digest: LOCAL_ACTION_REGISTRY_DIGEST,
    },
    authorization: {
      apiGroup: 'apps',
      resource: 'deployments',
      subresource: '',
      verb: 'patch',
    },
  };
};

const localProposalRecord = (actionType = 'crashloop') => {
  const isTestPods = actionType === 'test-pods';
  const isNamespaceCleanup = actionType === 'namespace-cleanup';
  const target = targetForAction(actionType);
  return {
  schemaVersion: 'v1',
  apiVersion: 'aiops.komsco/v1',
  kind: 'ActionProposalRecord',
  metadata: { name: proposalIdForAction(actionType), createdAt: nowIso() },
  spec: {
    candidateActionRequest: {
      schemaVersion: 'v1',
      title: actionTitleForAction(actionType),
      target,
      action: localAction(actionType),
      requester: LOCAL_SUBJECT,
      policy: {
        mode: 'local-only',
        sourceType: 'local-fixture',
        policyDecisionDigest: LOCAL_POLICY_DIGEST,
      },
    },
    candidateRequestDigest: isNamespaceCleanup
      ? 'sha256:local-namespace-cleanup-candidate-request-v1'
      : isTestPods
      ? 'sha256:local-test-pods-candidate-request-v1'
      : 'sha256:local-candidate-request-v1',
    digestSchema: {
      name: 'candidate-action-request-digest-v1',
      canonicalization: 'stable-json-sort-keys',
    },
    evidenceRefs: isNamespaceCleanup
      ? [
          {
            id: 'ev-local-namespace-cleanup-komsco-aiops-lab',
            kind: 'NamespaceInventory',
            source: 'oc',
          },
        ]
      : isTestPods
      ? [
          {
            id: 'ev-local-user-request-test-pods',
            kind: 'UserRequest',
            source: 'chat',
          },
        ]
      : [
          {
            id: 'ev-local-alert-notready',
            kind: 'Alert',
            source: 'local-fixture',
          },
        ],
    incidentId: isNamespaceCleanup
      ? 'inc-local-namespace-cleanup'
      : isTestPods
        ? 'inc-local-test-pods'
        : 'inc-local-crashloop',
    runId: 'run-local-fixture',
    runbookRefs: [
      {
        title: isNamespaceCleanup
          ? 'Namespace cleanup approval runbook'
          : isTestPods
            ? 'Test Pod creation runbook'
            : 'Deployment restart runbook',
        uri: isNamespaceCleanup
          ? 'local-fixture://runbooks/namespace-cleanup'
          : isTestPods
          ? 'local-fixture://runbooks/create-test-pods'
          : 'local-fixture://runbooks/deployment-restart',
      },
    ],
    sourceType: 'local-fixture',
    status: { phase: 'proposed' },
  },
  subject: LOCAL_SUBJECT,
  };
};

const localSealedPlanRecord = (actionType = 'crashloop') => {
  const createdAt = nowIso();
  const isTestPods = actionType === 'test-pods';
  const isNamespaceCleanup = actionType === 'namespace-cleanup';
  const target = targetForAction(actionType);
  const planDigest = planDigestForAction(actionType);
  const plan = {
    schemaVersion: 'v1',
    clusterId: 'local-aiops-fixture',
    metadata: {
      planId: planIdForAction(actionType),
      incidentId: isNamespaceCleanup
        ? 'inc-local-namespace-cleanup'
        : isTestPods
          ? 'inc-local-test-pods'
          : 'inc-local-crashloop',
      requester: LOCAL_SUBJECT,
      idempotencyKey: isNamespaceCleanup
        ? 'idem-local-namespace-cleanup'
        : isTestPods
          ? 'idem-local-test-pods'
          : 'idem-local-crashloop',
      createdAt,
      apiCallTimeout: '30s',
      verificationDeadline: '10m',
      maxMutationAttempts: 1,
      maxVerificationAttempts: 3,
    },
    target,
    action: localAction(actionType),
    safety: {
      risk: isNamespaceCleanup ? 'medium' : 'low',
      policy: {
        mode: 'local-only',
        policyBundleHash: LOCAL_POLICY_DIGEST,
      },
      dryRun: {
        decision: 'local_fixture_validated',
        normalizedDiffDigest: 'sha256:local-dry-run-v1',
        requestDigest: 'sha256:local-dry-run-v1',
      },
      preconditions: [
        {
          type: isNamespaceCleanup
            ? 'NamespaceInventoryEmpty'
            : isTestPods
              ? 'TargetNamespaceSpecified'
              : 'TargetExists',
          value: true,
        },
        {
          type: isNamespaceCleanup
            ? 'HumanApprovalRequired'
            : isTestPods
              ? 'CompanyServerMutationGuard'
              : 'LocalFixtureOnly',
          value: true,
        },
      ],
      hardPostconditions: [{ type: 'ExecutionRecordTerminalState', value: true }],
      observationalPostconditions: isNamespaceCleanup
        ? [{ type: 'NamespaceAbsentOrDeletionTimestampObserved', value: target.name }]
        : isTestPods
        ? [{ type: 'TestPodsCreated', value: `${LOCAL_TEST_POD_COUNT} pods` }]
        : [{ type: 'DeploymentRestartObserved', value: LOCAL_TARGET.name }],
      rollbackDescription: isNamespaceCleanup
        ? 'Namespace 삭제는 일반적으로 즉시 되돌릴 수 없으므로 승인 전 백업/소유자 확인이 필수입니다.'
        : isTestPods
        ? `테스트 후 label app=${LOCAL_TEST_POD_NAME_PREFIX} 기준으로 생성 Pod를 삭제합니다.`
        : '필요 시 직전 ReplicaSet으로 rollout undo를 수행합니다.',
      rollbackRequiresApproval: true,
      rollbackPossible: !isNamespaceCleanup,
      expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    },
    approvalPresentation: {
      impact: {
        affectedWorkloads: isNamespaceCleanup ? 0 : isTestPods ? 0 : 1,
        affectedPods: isNamespaceCleanup ? 0 : isTestPods ? LOCAL_TEST_POD_COUNT : 1,
        availabilityRisk: 'low',
        summaryDigest: isNamespaceCleanup
          ? 'sha256:local-namespace-cleanup-impact-v1'
          : isTestPods
            ? 'sha256:local-test-pods-impact-v1'
            : 'sha256:local-impact-v1',
      },
      dryRun: {
        decision: 'local_fixture_validated',
        normalizedDiffDigest: 'sha256:local-dry-run-v1',
      },
      evidenceRefs: [
        {
          id: isNamespaceCleanup
            ? 'ev-local-namespace-cleanup-komsco-aiops-lab'
            : isTestPods
              ? 'ev-local-user-request-test-pods'
              : 'ev-local-alert-notready',
          source: isNamespaceCleanup ? 'oc' : isTestPods ? 'chat' : 'local-fixture',
        },
      ],
      runbookRefs: [
        {
          title: isNamespaceCleanup
            ? 'Namespace cleanup approval runbook'
            : isTestPods
              ? 'Test Pod creation runbook'
              : 'Deployment restart runbook',
        },
      ],
    },
    digest: {
      planDigest,
      canonicalization: 'stable-json-sort-keys',
      digestSchema: 'sealed-action-plan-digest-v1',
    },
  };

  return {
    schemaVersion: 'v1',
    apiVersion: 'aiops.komsco/v1',
    kind: 'SealedActionPlanRecord',
    metadata: { name: planIdForAction(actionType), createdAt },
    spec: { sealedActionPlan: plan, status: { phase: 'sealed' } },
    subject: LOCAL_SUBJECT,
  };
};

const localAuditRecord = () => ({
  kind: 'AuditRecord',
  metadata: { name: 'audit-local-fixture', createdAt: nowIso() },
  spec: {
    actor: 'local-fixture-gateway',
    action: 'served local-only AIOps fixture',
    companyMutationExecuted: false,
  },
});

const readJsonBody = (req) =>
  new Promise((resolve, reject) => {
    let body = '';
    req.on('data', (chunk) => {
      body += chunk.toString();
      if (body.length > 1024 * 1024) {
        reject(new Error('request body too large'));
        req.destroy();
      }
    });
    req.on('end', () => {
      if (!body.trim()) {
        resolve({});
        return;
      }
      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(error);
      }
    });
    req.on('error', reject);
  });

const sse = (res, payload) => {
  if (payload === '[DONE]') {
    res.write('data: [DONE]\n\n');
    return;
  }

  res.write(`data: ${JSON.stringify(payload)}\n\n`);
};

const endChatStream = (res, conversationId = `local-fixture-${Date.now()}`) => {
  sse(res, { type: 'end', conversationId });
  sse(res, '[DONE]');
  res.end();
};

const latestUserMessageFromBody = (body) => {
  if (typeof body?.message === 'string') {
    return body.message;
  }
  if (Array.isArray(body?.recentMessages)) {
    const latest = [...body.recentMessages].reverse().find((item) => item?.role === 'user');
    return typeof latest?.content === 'string' ? latest.content : '';
  }
  return '';
};

const isNamespaceCleanupQuestion = (message) => {
  const text = String(message || '');
  const mentionsNamespace = /(namespace|namespaces|네임스페이스|ns\b)/i.test(text);
  const hasNamespaceLikeName = /\b[a-z0-9]+(?:-[a-z0-9]+)+\b/i.test(text);
  const asksCleanup = /(안쓰|안 쓰|안쓰고|안 쓰고|정리|삭제|오래된|unused|cleanup|clean up|사용 여부|쓰고있는|쓰고 있는)/i.test(
    text,
  );
  return asksCleanup && (mentionsNamespace || hasNamespaceLikeName);
};

const isCrashloopDemoQuestion = (message) => {
  if (!String(message || '').trim() || isNamespaceCleanupQuestion(message)) {
    return false;
  }
  return /(kubepodnotready|crashloop|crash loop|action plan|조치 후보|복구|rollout|재시작|승인|실행)/i.test(
    message,
  );
};

const isOpenShiftSignalQuestion = (message) => {
  const text = String(message || '');
  if (isNamespaceCleanupQuestion(text) || isCrashloopDemoQuestion(text)) {
    return false;
  }
  return /(openshift|오픈시프트|경고|alert|event|이벤트|operator|pod|파드|clusteroperator|co\b)/i.test(text);
};

const ocReadTimeoutMs = Number(process.env.AIOPS_LOCAL_OC_TIMEOUT_MS || 12000);
const namespaceNamePattern = /\b[a-z0-9](?:[-a-z0-9]*[a-z0-9])?\b/g;
const dnsLabelPattern = /^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$/;

const koreanCountWords = new Map([
  ['한', 1],
  ['하나', 1],
  ['두', 2],
  ['둘', 2],
  ['세', 3],
  ['셋', 3],
  ['네', 4],
  ['넷', 4],
  ['다섯', 5],
]);

const requestedPodCount = (message) => {
  const text = String(message || '');
  const digitMatch = text.match(/(\d+)\s*(?:개|대|pods?|파드)?/i);
  if (digitMatch) {
    return Math.max(1, Math.min(10, Number(digitMatch[1])));
  }
  for (const [word, count] of koreanCountWords) {
    if (new RegExp(`${word}\\s*(?:개|대|pods?|파드)`, 'i').test(text)) {
      return count;
    }
  }
  return LOCAL_TEST_POD_COUNT;
};

const requestedNamespace = (message) => {
  const text = String(message || '');
  const beforeNamespace = text.match(/\b([a-z0-9](?:[-a-z0-9]*[a-z0-9])?)\s*(?:namespace|네임스페이스|ns)\b/i);
  if (beforeNamespace && dnsLabelPattern.test(beforeNamespace[1])) {
    return beforeNamespace[1];
  }
  const names = text.match(namespaceNamePattern) || [];
  return names.find((name) => dnsLabelPattern.test(name) && name.includes('-')) || '';
};

const parseTestPodCreateRequest = (message) => {
  const text = String(message || '');
  const asksCreate = /(생성|만들|띄워|올려|create|run|start)/i.test(text);
  const mentionsPod = /(pod|파드)/i.test(text);
  if (!asksCreate || !mentionsPod) {
    return null;
  }

  const namespace = requestedNamespace(text) || LOCAL_TEST_POD_TARGET.namespace;
  return {
    count: requestedPodCount(text),
    namespace,
    supported: namespace === LOCAL_TEST_POD_TARGET.namespace,
  };
};

const normalizedChatText = (message) => String(message || '').replace(/\s+/g, ' ').trim();

const actionCapableExecutionMode = (executionMode) =>
  executionMode === 'execute' || executionMode === 'unrestricted';

const executionModeSentence = (executionMode) => {
  if (executionMode === 'unrestricted') {
    return '실행 무제한 모드: 조회와 계획 생성은 가능하지만, 위험 조치는 승인 게이트를 먼저 통과해야 합니다.';
  }
  if (executionMode === 'execute') {
    return '실행 가능 모드: 조회 후 승인 가능한 Action Plan 후보를 만들 수 있습니다. 승인 전 변경은 실행하지 않습니다.';
  }
  return '읽기 전용 모드: 조회와 근거 수집만 수행하고 변경 작업은 만들지 않습니다.';
};

const clarificationModeSentence = (executionMode) => {
  if (executionMode === 'unrestricted') {
    return '실행 무제한 모드: 요청이 명확해지기 전에는 위험 조치를 실행하지 않습니다.';
  }
  if (executionMode === 'execute') {
    return '실행 가능 모드: 요청이 명확해지기 전에는 승인이나 실행을 만들지 않습니다.';
  }
  return '읽기 전용 모드: 조회와 근거 수집만 수행하고 변경 작업은 만들지 않습니다.';
};

const actionPolicyModeForExecutionMode = (executionMode, canProposeAction) => {
  if (!canProposeAction) {
    return 'read_only_review';
  }
  return executionMode === 'unrestricted'
    ? 'unrestricted_pending_approval'
    : 'controlled_execution';
};

const classifyLocalChatIntent = (message) => {
  const text = normalizedChatText(message);
  if (!text) {
    return {
      confidence: 'low',
      intent: 'unclear_or_out_of_scope',
      reason: 'empty_message',
    };
  }

  const compact = text.replace(/[^\p{L}\p{N}]+/gu, '');
  const mentionsOpenShiftDomain =
    /(openshift|오픈시프트|ocp|kubernetes|쿠버네티스|cluster|클러스터|namespace|네임스페이스|node|노드|operator|pod|파드|deployment|deploy|배포|event|이벤트|alert|경고|action plan|조치|승인|실행|터미널|명령|oc\b)/i.test(
      text,
    );
  const asksOperationalQuestion =
    /(확인|점검|분석|정리|삭제|생성|만들|알려|조회|진단|원인|복구|검증|롤백|계획|실행|create|delete|cleanup|diagnos|troubleshoot|restart|rollback|get|list)/i.test(
      text,
    );

  if (parseTestPodCreateRequest(text)) {
    return {
      confidence: 'high',
      intent: 'execution_request',
      reason: 'test_pod_create_request',
    };
  }
  if (isNamespaceCleanupQuestion(text)) {
    return {
      confidence: 'high',
      intent: 'namespace_cleanup',
      reason: 'namespace_cleanup_review',
    };
  }
  if (isCrashloopDemoQuestion(text)) {
    return {
      confidence: 'high',
      intent: 'action_plan_request',
      reason: 'crashloop_action_plan_review',
    };
  }
  if (isOpenShiftSignalQuestion(text)) {
    return {
      confidence: 'medium',
      intent: 'openshift_diagnosis',
      reason: 'openshift_signal_review',
    };
  }
  if (mentionsOpenShiftDomain && asksOperationalQuestion) {
    return {
      confidence: 'medium',
      intent: 'openshift_diagnosis',
      reason: 'general_openshift_review',
    };
  }
  if (compact.length <= 8 || !mentionsOpenShiftDomain) {
    return {
      confidence: 'low',
      intent: 'unclear_or_out_of_scope',
      reason: 'insufficient_operational_context',
    };
  }
  return {
    confidence: 'low',
    intent: 'general_chat',
    reason: 'not_an_operational_request',
  };
};
const activeWorkloadKinds = new Set([
  'CronJob',
  'DaemonSet',
  'Deployment',
  'DeploymentConfig',
  'Job',
  'Pod',
  'StatefulSet',
]);
const passiveWorkloadKinds = new Set(['ReplicaSet', 'ReplicationController']);
const exposureKinds = new Set(['Route', 'Service']);

const runOc = (args) =>
  new Promise((resolve) => {
    execFile(
      'oc',
      args,
      { maxBuffer: 8 * 1024 * 1024, timeout: ocReadTimeoutMs },
      (error, stdout, stderr) => {
        if (error) {
          resolve({
            ok: false,
            args,
            error: error.message,
            stderr: String(stderr || '').trim(),
            stdout: String(stdout || '').trim(),
          });
          return;
        }
        resolve({ ok: true, args, stdout: String(stdout || '').trim(), stderr: String(stderr || '').trim() });
      },
    );
  });

const runOcJson = async (args) => {
  const result = await runOc(args);
  if (!result.ok) {
    return result;
  }
  try {
    return { ...result, json: JSON.parse(result.stdout || '{}') };
  } catch (error) {
    return { ...result, ok: false, error: `failed to parse oc JSON: ${error.message}` };
  }
};

const resourceItems = (payload) => (Array.isArray(payload?.items) ? payload.items : []);

const metadataName = (item) => String(item?.metadata?.name || '');

const metadataNamespace = (item) => String(item?.metadata?.namespace || '');

const parseTimeMs = (value) => {
  const ms = Date.parse(String(value || ''));
  return Number.isFinite(ms) ? ms : 0;
};

const daysSince = (timestampMs) => {
  if (!timestampMs) {
    return null;
  }
  return Math.max(0, Math.floor((Date.now() - timestampMs) / 86_400_000));
};

const eventTimestampMs = (item) =>
  parseTimeMs(
    item?.eventTime ||
      item?.lastTimestamp ||
      item?.series?.lastObservedTime ||
      item?.firstTimestamp ||
      item?.metadata?.creationTimestamp,
  );

const kindCounts = (items) =>
  items.reduce((acc, item) => {
    const kind = String(item?.kind || 'Unknown');
    acc[kind] = (acc[kind] || 0) + 1;
    return acc;
  }, {});

const extractRequestedNamespaceNames = (message, availableNames) => {
  const available = new Set(availableNames);
  const tokens = Array.from(String(message || '').toLowerCase().matchAll(namespaceNamePattern)).map(
    (match) => match[0],
  );
  return [...new Set(tokens.filter((token) => available.has(token)))];
};

const namespaceDecision = ({ activeWorkloads, ageDays, exposureCount, lastEventAgeDays, name, pvcCount }) => {
  if (/^(default|kube-|kubernetes|openshift(?:-|$))/.test(name)) {
    return {
      label: '보호',
      reason: '시스템 또는 기본 namespace라 정리 대상에서 제외',
      next: '삭제 금지',
    };
  }
  if (pvcCount > 0) {
    return {
      label: '삭제 보류',
      reason: `PVC ${pvcCount}개가 남아 있음`,
      next: '소유자와 데이터 보존 필요 여부 확인',
    };
  }
  if (activeWorkloads > 0 || exposureCount > 0) {
    return {
      label: '사용 중',
      reason: `workload ${activeWorkloads}개, service/route ${exposureCount}개 확인`,
      next: '배포 소유자 확인 후 유지 여부 결정',
    };
  }
  if (lastEventAgeDays !== null && lastEventAgeDays <= 14) {
    return {
      label: '확인 필요',
      reason: `최근 ${lastEventAgeDays}일 안에 event가 있음`,
      next: '최근 작업자와 변경 이력 확인',
    };
  }
  return {
    label: '정리 검토 가능',
    reason: `workload/PVC/route 없음${ageDays === null ? '' : `, namespace age ${ageDays}일`}`,
    next: '소유자 확인 후 삭제 계획 생성',
  };
};

const inspectNamespace = async (namespace) => {
  const inventory = await runOcJson([
    'get',
    'all,pvc,route,event',
    '-n',
    namespace,
    '-o',
    'json',
    '--ignore-not-found',
  ]);
  if (!inventory.ok) {
    return {
      namespace,
      ok: false,
      error: inventory.stderr || inventory.error || 'oc namespace inventory failed',
    };
  }
  const items = resourceItems(inventory.json).filter((item) => metadataNamespace(item) === namespace || !metadataNamespace(item));
  const counts = kindCounts(items);
  const activeWorkloads = Object.entries(counts).reduce(
    (total, [kind, count]) => total + (activeWorkloadKinds.has(kind) ? count : 0),
    0,
  );
  const passiveWorkloads = Object.entries(counts).reduce(
    (total, [kind, count]) => total + (passiveWorkloadKinds.has(kind) ? count : 0),
    0,
  );
  const exposureCount = Object.entries(counts).reduce(
    (total, [kind, count]) => total + (exposureKinds.has(kind) ? count : 0),
    0,
  );
  const pvcCount = counts.PersistentVolumeClaim || 0;
  const eventTimes = items.filter((item) => item?.kind === 'Event').map(eventTimestampMs).filter(Boolean);
  const lastEventMs = eventTimes.length ? Math.max(...eventTimes) : 0;
  return {
    namespace,
    ok: true,
    activeWorkloads,
    passiveWorkloads,
    exposureCount,
    pvcCount,
    eventCount: counts.Event || 0,
    kindCounts: counts,
    lastEventAgeDays: daysSince(lastEventMs),
    lastEventAt: lastEventMs ? new Date(lastEventMs).toISOString() : '',
  };
};

const buildNamespaceInventory = async (message) => {
  const server = await runOc(['whoami', '--show-server']);
  if (!server.ok) {
    return {
      ok: false,
      status: 'oc_unavailable',
      error: server.stderr || server.error || 'oc whoami failed',
    };
  }
  const namespaces = await runOcJson(['get', 'namespaces', '-o', 'json']);
  if (!namespaces.ok) {
    return {
      ok: false,
      status: 'namespace_list_failed',
      server: server.stdout,
      error: namespaces.stderr || namespaces.error || 'oc get namespaces failed',
    };
  }
  const namespaceItems = resourceItems(namespaces.json);
  const availableNames = namespaceItems.map(metadataName).filter(Boolean).sort();
  const requestedNames = extractRequestedNamespaceNames(message, availableNames);
  const selectedNames = requestedNames.length ? requestedNames : availableNames.slice(0, 12);
  const inspected = [];
  for (const namespace of selectedNames) {
    const namespaceMeta = namespaceItems.find((item) => metadataName(item) === namespace);
    const createdMs = parseTimeMs(namespaceMeta?.metadata?.creationTimestamp);
    const inventory = await inspectNamespace(namespace);
    inspected.push({
      ...inventory,
      ageDays: daysSince(createdMs),
      decision: inventory.ok
        ? namespaceDecision({
            activeWorkloads: inventory.activeWorkloads,
            ageDays: daysSince(createdMs),
            exposureCount: inventory.exposureCount,
            lastEventAgeDays: inventory.lastEventAgeDays,
            name: namespace,
            pvcCount: inventory.pvcCount,
          })
        : {
            label: '판단 불가',
            reason: inventory.error,
            next: 'oc 조회 오류 확인',
          },
    });
  }
  return {
    ok: true,
    status: requestedNames.length ? 'scoped_by_user_names' : 'default_first_page',
    server: server.stdout,
    totalNamespaces: availableNames.length,
    requestedNames,
    inspected,
  };
};

const tableCell = (value) => String(value ?? '').replace(/\|/g, '/');

const executionModeFromRequestBody = (body) => {
  const mode = String(body?.pageContext?.aiopsExecutionMode || '').trim().toLowerCase();
  if (['execute', 'execution', 'execution-enabled', 'enabled'].includes(mode)) {
    return 'execute';
  }
  if (['unrestricted', 'dev-unrestricted', 'experimental'].includes(mode)) {
    return 'unrestricted';
  }
  return 'read-only';
};

const namespaceCleanupCandidates = (inventory) =>
  inventory.ok
    ? inventory.inspected.filter((item) => item.ok && item.decision?.label === '정리 검토 가능')
    : [];

const namespaceReviewCommandBlock = (inventory) => {
  const namespaces = inventory.ok
    ? inventory.inspected.map((item) => item.namespace)
    : [LOCAL_NAMESPACE_CLEANUP_TARGET.name];
  const lines = [
    '```bash',
    'oc whoami --show-server',
    'oc get namespaces',
  ];
  for (const namespace of namespaces) {
    lines.push(`oc get all,pvc,route,event -n ${namespace} --ignore-not-found`);
    lines.push(`oc get namespace ${namespace} -o yaml`);
  }
  lines.push('```');
  return lines.join('\n');
};

const namespaceInventoryAnswer = (inventory, executionMode = 'read-only') => {
  if (!inventory.ok) {
    return [
      '## 현재 상태',
      '실제 OpenShift 조회를 실행하지 못했습니다.',
      '',
      '## 실패 지점',
      `- ${inventory.status}: ${inventory.error}`,
      '',
      '## 다음 조치',
      '- 로컬 터미널에서 `oc whoami --show-server`와 `oc get namespaces`가 되는지 먼저 확인해야 합니다.',
      '- 조회가 되기 전에는 네임스페이스 정리 후보를 판정하지 않습니다.',
    ].join('\n');
  }

  const cleanupCandidates = namespaceCleanupCandidates(inventory);
  const actionCapableMode = actionCapableExecutionMode(executionMode);
  const modeLine = actionCapableMode
    ? cleanupCandidates.length
      ? `${executionModeSentence(executionMode)} 정리 후보가 있어 Action Plan 후보를 만들 수 있습니다. 실제 삭제는 승인 전 실행하지 않습니다.`
      : `${executionModeSentence(executionMode)} 승인 가능한 정리 후보가 없어 Action Plan을 만들지 않습니다.`
    : executionModeSentence(executionMode);
  const lines = [
    '## 현재 판단',
    modeLine,
    '',
    '## 조회 근거',
    `- API 서버: ${inventory.server}`,
    `- 접근 가능한 namespace: ${inventory.totalNamespaces}개`,
    `- 조회 범위: ${inventory.requestedNames.length ? inventory.requestedNames.join(', ') : '첫 12개 namespace'}`,
    '',
    '## 네임스페이스별 판단',
    '| Namespace | 판단 | 근거 | 다음 조치 |',
    '|---|---|---|---|',
  ];

  for (const item of inventory.inspected) {
    const reason = item.ok
      ? `${item.decision.reason}; events ${item.eventCount}개${item.lastEventAgeDays === null ? '' : `, last ${item.lastEventAgeDays}일 전`}`
      : item.decision.reason;
    lines.push(
      `| ${tableCell(item.namespace)} | ${tableCell(item.decision.label)} | ${tableCell(reason)} | ${tableCell(item.decision.next)} |`,
    );
  }

  lines.push(
    '',
    '## Action Plan',
    actionCapableMode && cleanupCandidates.length
      ? `- 승인 필요 후보: ${cleanupCandidates.map((item) => `\`${item.namespace}\``).join(', ')}`
      : '- 읽기 전용 모드에서는 Action Plan 버튼을 만들지 않습니다.',
    '- `정리 검토 가능`만 삭제 계획 후보로 올립니다.',
    '- `사용 중`, `삭제 보류`, `보호`는 삭제 계획을 만들지 않습니다.',
    '- 삭제 전 승인 조건: 소유자 확인, PVC/Route 잔존 여부 확인, 백업 필요 여부 확인.',
    '- 실제 삭제 실행 명령은 승인 전에는 절대 생성하거나 실행하지 않습니다.',
    '',
    '## 터미널 확인 명령',
    namespaceReviewCommandBlock(inventory),
  );
  return lines.join('\n');
};

const compactText = (value, max = 140) => {
  const text = String(value || '').replace(/\s+/g, ' ').trim();
  return text.length > max ? `${text.slice(0, max - 1)}...` : text;
};

const ageText = (timestampMs) => {
  const days = daysSince(timestampMs);
  if (days === null) {
    return '-';
  }
  if (days === 0) {
    return '오늘';
  }
  return `${days}일 전`;
};

const warningEventRows = (payload, limit = 8) =>
  resourceItems(payload)
    .map((item) => {
      const involved = item?.involvedObject || item?.regarding || {};
      const timestampMs = eventTimestampMs(item);
      const namespace = String(involved.namespace || item?.metadata?.namespace || '');
      const targetKind = String(involved.kind || 'Resource');
      const targetName = String(involved.name || metadataName(item) || '');
      return {
        namespace,
        target: targetName ? `${targetKind}/${targetName}` : targetKind,
        reason: String(item?.reason || ''),
        message: compactText(item?.message || item?.note || ''),
        timestampMs,
      };
    })
    .sort((a, b) => b.timestampMs - a.timestampMs)
    .slice(0, limit);

const conditionValue = (resource, type) =>
  resource?.status?.conditions?.find((condition) => condition?.type === type)?.status || '';

const operatorIssueRows = (payload) =>
  resourceItems(payload)
    .map((item) => {
      const available = conditionValue(item, 'Available');
      const degraded = conditionValue(item, 'Degraded');
      const progressing = conditionValue(item, 'Progressing');
      const issue = degraded === 'True' || available === 'False' || progressing === 'True';
      return {
        name: metadataName(item),
        available,
        degraded,
        progressing,
        issue,
      };
    })
    .filter((item) => item.issue);

const podIssueRows = (payload, limit = 8) =>
  resourceItems(payload)
    .map((pod) => {
      const statuses = Array.isArray(pod?.status?.containerStatuses) ? pod.status.containerStatuses : [];
      const waiting = statuses
        .map((status) => status?.state?.waiting?.reason)
        .filter(Boolean)
        .join(', ');
      const restarts = statuses.reduce((total, status) => total + Number(status?.restartCount || 0), 0);
      const unready = statuses.some((status) => status && status.ready === false);
      const phase = String(pod?.status?.phase || '');
      const issue = !['Running', 'Succeeded'].includes(phase) || Boolean(waiting) || unready || restarts > 0;
      return {
        namespace: metadataNamespace(pod),
        name: metadataName(pod),
        phase,
        waiting,
        restarts,
        issue,
      };
    })
    .filter((item) => item.issue)
    .sort((a, b) => b.restarts - a.restarts)
    .slice(0, limit);

const buildOpenShiftSignalInventory = async () => {
  const server = await runOc(['whoami', '--show-server']);
  if (!server.ok) {
    return {
      ok: false,
      status: 'oc_unavailable',
      error: server.stderr || server.error || 'oc whoami failed',
    };
  }
  const [events, operators, pods] = await Promise.all([
    runOcJson(['get', 'events', '-A', '--field-selector', 'type=Warning', '-o', 'json']),
    runOcJson(['get', 'clusteroperators', '-o', 'json']),
    runOcJson(['get', 'pods', '-A', '-o', 'json']),
  ]);
  const commandResults = { events, operators, pods };
  const rows = {
    warnings: events.ok ? warningEventRows(events.json) : [],
    operators: operators.ok ? operatorIssueRows(operators.json) : [],
    pods: pods.ok ? podIssueRows(pods.json) : [],
  };
  return {
    ok: events.ok || operators.ok || pods.ok,
    status: events.ok && operators.ok && pods.ok ? 'read_only_signals_collected' : 'partial_read_only_signals',
    server: server.stdout,
    errors: Object.entries(commandResults)
      .filter(([, result]) => !result.ok)
      .map(([name, result]) => `${name}: ${result.stderr || result.error}`),
    totals: {
      warningEvents: events.ok ? resourceItems(events.json).length : 0,
      operatorIssues: rows.operators.length,
      podIssues: rows.pods.length,
    },
    rows,
  };
};

const openShiftSignalAnswer = (inventory) => {
  if (!inventory.ok) {
    return [
      '## 현재 상태',
      '실제 OpenShift 경고 조회를 실행하지 못했습니다.',
      '',
      '## 실패 지점',
      `- ${inventory.status}: ${inventory.error}`,
      '',
      '## 다음 조치',
      '- 로컬 터미널에서 `oc whoami --show-server`, `oc get events -A`가 되는지 먼저 확인해야 합니다.',
    ].join('\n');
  }

  const lines = [
    '## 현재 판단',
    '실제 `oc` 읽기 전용 조회로 최근 경고와 우선 확인 대상을 정리했습니다. 변경은 실행하지 않았습니다.',
    '',
    '## 조회 근거',
    `- API 서버: ${inventory.server}`,
    `- Warning event: ${inventory.totals.warningEvents}개`,
    `- Operator 이상: ${inventory.totals.operatorIssues}개`,
    `- Pod 확인 대상: ${inventory.totals.podIssues}개`,
  ];
  if (inventory.errors.length) {
    lines.push(`- 일부 조회 실패: ${inventory.errors.join('; ')}`);
  }

  lines.push('', '## 우선 확인');
  if (!inventory.rows.warnings.length && !inventory.rows.operators.length && !inventory.rows.pods.length) {
    lines.push('- 현재 접근 가능한 범위에서 우선 확인할 Warning event, Operator issue, Pod issue가 보이지 않습니다.');
  } else {
    lines.push('| 구분 | 대상 | 근거 | 다음 확인 |');
    lines.push('|---|---|---|---|');
    for (const item of inventory.rows.operators.slice(0, 4)) {
      lines.push(
        `| Operator | ${tableCell(item.name)} | Available=${item.available}, Degraded=${item.degraded}, Progressing=${item.progressing} | ClusterOperator condition message 확인 |`,
      );
    }
    for (const item of inventory.rows.warnings.slice(0, 6)) {
      lines.push(
        `| Warning | ${tableCell(item.namespace ? `${item.namespace}/${item.target}` : item.target)} | ${tableCell(item.reason)} · ${tableCell(ageText(item.timestampMs))} · ${tableCell(item.message)} | Event 전후 Pod/Deployment 상태 확인 |`,
      );
    }
    for (const item of inventory.rows.pods.slice(0, 6)) {
      lines.push(
        `| Pod | ${tableCell(`${item.namespace}/${item.name}`)} | phase=${tableCell(item.phase)}, waiting=${tableCell(item.waiting || '-')}, restarts=${item.restarts} | logs/events/owner Deployment 확인 |`,
      );
    }
  }

  lines.push(
    '',
    '## Action Plan',
    '- 이 질문은 경고 정리라서 즉시 변경 계획을 만들지 않습니다.',
    '- 특정 Pod/Deployment와 원하는 조치가 확정되면 그때 승인 가능한 Action Plan을 생성합니다.',
  );
  return lines.join('\n');
};

const buildTestPodCreatePreflight = async (request) => {
  const server = await runOc(['whoami', '--show-server']);
  if (!server.ok) {
    if (request.supported) {
      return {
        ok: true,
        status: 'namespace_check_deferred',
        error: server.stderr || server.error || 'oc whoami failed',
        namespace: request.namespace,
        ocAvailable: false,
        server: '콘솔 연결 전 사전검증',
      };
    }
    return {
      ok: false,
      status: 'oc_unavailable',
      error: server.stderr || server.error || 'oc whoami failed',
      namespace: request.namespace,
      server: '',
    };
  }
  const namespace = await runOc(['get', 'namespace', request.namespace, '-o', 'name']);
  return {
    ok: request.supported,
    status: request.supported
      ? namespace.ok
        ? 'namespace_ready'
        : 'namespace_check_deferred'
      : 'unsupported_namespace_for_local_mutation',
    error: request.supported ? namespace.stderr || namespace.error || '' : 'local fixture mutation namespace mismatch',
    namespace: request.namespace,
    ocAvailable: true,
    server: server.stdout,
  };
};

const testPodCreateAnswer = (request, preflight, executionMode = 'read-only') => {
  const targetLabel = `${LOCAL_TEST_POD_TARGET.namespace}/${LOCAL_TEST_POD_TARGET.name}`;
  const actionCapableMode = actionCapableExecutionMode(executionMode);
  const requestedCount = request.count || LOCAL_TEST_POD_COUNT;
  const preflightLabel =
    preflight.status === 'namespace_ready'
      ? 'namespace 존재 확인'
      : preflight.status === 'namespace_check_deferred'
        ? '실행 전 namespace 재확인 필요'
        : preflight.status;
  if (!request.supported) {
    return [
      '## 현재 판단',
      '테스트 Pod 생성 요청으로 해석했지만, 현재 안전 범위 밖의 네임스페이스입니다.',
      '',
      '## 요청한 대상',
      `- namespace: \`${request.namespace}\``,
      '',
      '## 다음 조치',
      '- 대상 namespace가 맞는지 확인한 뒤 다시 요청하세요.',
      '- 허용 범위를 넓히기 전에는 생성 계획이나 실행을 만들지 않습니다.',
    ].join('\n');
  }

  const lines = [
    '## 현재 판단',
    actionCapableMode
      ? `${executionModeSentence(executionMode)} 테스트 Pod 생성은 승인 가능한 Action Plan 후보로 올릴 수 있습니다.`
      : `${executionModeSentence(executionMode)} 테스트 Pod 생성 요청은 해석했지만 Action Plan 버튼은 만들지 않습니다.`,
    '',
    '## 대상',
    `- namespace: \`${LOCAL_TEST_POD_TARGET.namespace}\``,
    `- 생성 수량: \`${requestedCount}\``,
    `- 계획 대상: \`${targetLabel}\``,
    '',
    '## 확인한 근거',
    `- API 서버: ${preflight.server || '확인 실패'}`,
    `- namespace 사전 확인: ${preflightLabel}`,
  ];

  if (!preflight.ok) {
    lines.push(`- 실패 사유: ${preflight.error || 'unknown'}`);
  }

  lines.push(
    '',
    '## Action Plan',
    actionCapableMode
      ? '- 상태: 승인 필요 Action Plan 후보 생성 가능'
      : '- 상태: 읽기 전용 모드라 계획 생성/실행 버튼을 표시하지 않음',
    `- 조치 후보: \`${LOCAL_TEST_POD_NAME_PREFIX}-<id>-1..${requestedCount}\` 테스트 Pod 생성`,
    `- 이미지: \`${LOCAL_TEST_POD_IMAGE}\``,
    '- 실행 조건: 운영자 승인 후 대상 namespace를 다시 확인하고 Pod 오브젝트 생성',
    `- 검증: 생성된 Pod 오브젝트 ${requestedCount}개가 조회되는지 확인`,
    '- 정리: 테스트 완료 후 label 기준 삭제 계획을 별도로 승인',
    '',
    '## 터미널 확인 명령',
    '```bash',
    'oc whoami --show-server',
    `oc get namespace ${LOCAL_TEST_POD_TARGET.namespace}`,
    `oc get pods -n ${LOCAL_TEST_POD_TARGET.namespace} -l app=${LOCAL_TEST_POD_NAME_PREFIX}`,
    '```',
  );

  return lines.join('\n');
};

const expectedMutationServer = () =>
  process.env.KOMSCO_AIOPS_COMPANY_SERVER || 'https://api.ocp.cywell.server:6443';

const executeTestPodCreatePlan = async () => {
  const server = await runOc(['whoami', '--show-server']);
  if (!server.ok) {
    return {
      ok: false,
      status: 'mutation_failed',
      reason: `oc server check failed: ${server.stderr || server.error}`,
      companyMutationExecuted: false,
      server: '',
      createdPods: [],
    };
  }

  const actualServer = String(server.stdout || '').trim();
  const expectedServer = expectedMutationServer();
  if (process.env.AIOPS_LOCAL_ALLOW_MUTATION_ON_ANY_SERVER !== '1' && actualServer !== expectedServer) {
    return {
      ok: false,
      status: 'mutation_rejected',
      reason: `server mismatch: expected ${expectedServer}, got ${actualServer}`,
      companyMutationExecuted: false,
      server: actualServer,
      createdPods: [],
    };
  }

  const namespace = await runOc(['get', 'namespace', LOCAL_TEST_POD_TARGET.namespace, '-o', 'name']);
  if (!namespace.ok) {
    return {
      ok: false,
      status: 'mutation_failed',
      reason: `namespace check failed: ${namespace.stderr || namespace.error}`,
      companyMutationExecuted: false,
      server: actualServer,
      createdPods: [],
    };
  }

  const requestId = Date.now().toString(36);
  const createdPods = [];
  const errors = [];
  for (let index = 1; index <= LOCAL_TEST_POD_COUNT; index += 1) {
    const podName = `${LOCAL_TEST_POD_NAME_PREFIX}-${requestId}-${index}`;
    const labels = `app=aiops-test-pod,aiops.komsco.local/request-id=${requestId}`;
    const result = await runOc([
      'run',
      podName,
      '-n',
      LOCAL_TEST_POD_TARGET.namespace,
      '--image',
      LOCAL_TEST_POD_IMAGE,
      '--restart=Never',
      '--image-pull-policy=IfNotPresent',
      '--labels',
      labels,
      '--command',
      '--',
      'sleep',
      '3600',
    ]);
    if (result.ok) {
      createdPods.push(podName);
    } else {
      errors.push(`${podName}: ${result.stderr || result.error}`);
    }
  }

  const verification = await runOcJson([
    'get',
    'pods',
    '-n',
    LOCAL_TEST_POD_TARGET.namespace,
    '-l',
    `aiops.komsco.local/request-id=${requestId}`,
    '-o',
    'json',
  ]);
  const observed = verification.ok ? resourceItems(verification.json).length : 0;
  const ok = errors.length === 0 && observed === LOCAL_TEST_POD_COUNT;
  return {
    ok,
    status: ok ? 'mutation_succeeded' : createdPods.length ? 'mutation_partial' : 'mutation_failed',
    reason: ok
      ? `created ${observed}/${LOCAL_TEST_POD_COUNT} test pods`
      : `created ${createdPods.length}/${LOCAL_TEST_POD_COUNT}; ${errors.join('; ') || verification.stderr || verification.error}`,
    companyMutationExecuted: createdPods.length > 0,
    server: actualServer,
    createdPods,
    observedPods: observed,
    requestId,
  };
};

const unsupportedLocalQuestionAnswer = (intent, executionMode) => [
  '## 요청 확인',
  'OpenShift 운영 작업으로 바로 실행할 만큼 대상과 목적이 충분하지 않습니다.',
  '',
  '## 필요한 정보',
  '- 확인할 대상: namespace, pod, deployment, node, operator 중 하나',
  '- 원하는 작업: 상태 조회, 원인 분석, Action Plan 생성, 승인 후 실행 중 하나',
  '',
  '## 지금 가능한 요청 예시',
  '- 최근 OpenShift 경고를 실제 근거와 추가 확인 항목으로 나눠줘.',
  '- 다음 네임스페이스가 실제 사용 중인지 read-only 명령까지 정리해줘.',
  '- gpu-test-kugnus 네임스페이스에 테스트 Pod 3개 생성 계획을 만들어줘.',
  '',
  '## 현재 모드',
  `- ${clarificationModeSentence(executionMode)}`,
  '- 처리 상태: 추가 정보 필요',
  '- 실행 상태: 변경 작업 없음',
].join('\n');

const streamLocalChat = async (req, res) => {
  let requestBody = {};
  try {
    requestBody = await readJsonBody(req);
  } catch {
    requestBody = {};
  }

  res.writeHead(200, {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-store',
    Connection: 'keep-alive',
  });

  const runId = `run-local-${Date.now()}`;
  const userMessage = latestUserMessageFromBody(requestBody);
  const executionMode = executionModeFromRequestBody(requestBody);
  const intent = classifyLocalChatIntent(userMessage);
  const testPodCreateRequest =
    intent.intent === 'execution_request' ? parseTestPodCreateRequest(userMessage) : null;

  if (testPodCreateRequest) {
    const actionCapableMode = actionCapableExecutionMode(executionMode);
    sse(res, {
      type: 'run_status',
      runId,
      stage: 'started',
      message: actionCapableMode
        ? '테스트 Pod 생성 Action Plan 사전 확인을 시작했습니다.'
        : '테스트 Pod 생성 요청을 읽기 전용으로 확인합니다.',
    });
    sse(res, {
      type: 'tool_call',
      id: 'test-pod-create-preflight-local',
      name: 'oc_test_pod_create_preflight',
      summary: '대상 네임스페이스 및 서버 확인',
    });
    const preflight = await buildTestPodCreatePreflight(testPodCreateRequest);
    const answer = testPodCreateAnswer(testPodCreateRequest, preflight, executionMode);
    const canProposeTestPods = actionCapableMode && preflight.ok;
    sse(res, {
      type: 'tool_result',
      id: 'test-pod-create-preflight-local',
      name: 'oc_test_pod_create_preflight',
      status: preflight.ok ? 'success' : 'failed',
      summary: preflight.ok
        ? `${LOCAL_TEST_POD_TARGET.namespace} 네임스페이스 확인`
        : `테스트 Pod 생성 사전 확인 실패: ${preflight.status}`,
      result: preflight,
    });
    sse(res, {
      type: 'tool_plan',
      runId,
      plan: {
        task_type: 'test_pod_create',
        target: LOCAL_TEST_POD_TARGET,
        execution_policy: {
          mode: actionPolicyModeForExecutionMode(executionMode, canProposeTestPods),
          mutations_enabled: canProposeTestPods,
          local_fixture_only: false,
        },
        tool_plan: [
          {
            step: 1,
            adapter: 'oc',
            tool: 'oc_get_namespace',
            verb: 'get',
            purpose: '대상 namespace 존재 확인',
          },
          ...(canProposeTestPods
            ? [
                {
                  step: 2,
                  adapter: 'aiops-gateway',
                  tool: 'create_test_pod_action_candidate',
                  verb: 'propose',
                  purpose: '승인 필요 테스트 Pod 생성 Action Plan 후보 생성',
                },
                {
                  step: 3,
                  adapter: 'oc',
                  tool: 'oc_get_created_pods',
                  verb: 'get',
                  purpose: '승인 후 생성된 Pod 오브젝트 확인',
                },
              ]
            : []),
        ],
        validation: {
          ok: preflight.ok,
          status: canProposeTestPods
            ? 'action_candidate_ready'
            : preflight.ok
              ? 'read_only_preflight_collected'
              : preflight.status,
        },
      },
      status: preflight.ok ? 'success' : 'failed',
    });
    sse(res, {
      type: 'text',
      content: answer,
      source: preflight.ok ? 'oc_action_plan_preflight' : 'oc_action_plan_preflight_failed',
      streamProbe: preflight.ok ? 'ok' : 'failed',
    });
    sse(res, {
      type: 'run_status',
      runId,
      stage: preflight.ok ? 'completed' : 'failed',
      message: preflight.ok
        ? actionCapableMode
          ? '테스트 Pod 생성 Action Plan 사전 확인을 완료했습니다.'
          : '테스트 Pod 생성 요청을 읽기 전용으로 확인했습니다.'
        : '테스트 Pod 생성 사전 확인에 실패했습니다.',
    });
    endChatStream(res);
    return;
  }

  if (intent.intent === 'namespace_cleanup') {
    const actionCapableMode = actionCapableExecutionMode(executionMode);
    sse(res, {
      type: 'run_status',
      runId,
      stage: 'started',
      message: actionCapableMode
        ? '네임스페이스 실조회와 Action Plan 후보 평가를 시작했습니다.'
        : '네임스페이스 read-only 조회를 시작했습니다.',
    });
    sse(res, {
      type: 'tool_call',
      id: 'namespace-inventory-local',
      name: 'oc_namespace_inventory',
      summary: 'oc read-only namespace inventory',
    });
    const inventory = await buildNamespaceInventory(userMessage);
    const cleanupCandidates = namespaceCleanupCandidates(inventory);
    const canProposeCleanup = inventory.ok && actionCapableMode && cleanupCandidates.length > 0;
    const answer = namespaceInventoryAnswer(inventory, executionMode);
    sse(res, {
      type: 'tool_result',
      id: 'namespace-inventory-local',
      name: 'oc_namespace_inventory',
      status: inventory.ok ? 'success' : 'failed',
      summary: inventory.ok
        ? `namespace ${inventory.inspected.length}개 read-only 조회`
        : 'namespace read-only 조회 실패',
      result: inventory,
    });
    sse(res, {
      type: 'tool_plan',
      runId,
      plan: {
        task_type: 'namespace_cleanup_review',
        execution_policy: {
          mode: actionPolicyModeForExecutionMode(executionMode, canProposeCleanup),
          mutations_enabled: canProposeCleanup,
          local_fixture_only: false,
        },
        tool_plan: [
          {
            step: 1,
            adapter: 'oc',
            tool: 'oc_get_namespaces',
            verb: 'list',
            purpose: '접근 가능한 네임스페이스 목록 확인',
          },
          {
            step: 2,
            adapter: 'oc',
            tool: 'oc_get_namespace_inventory',
            verb: 'get',
            purpose: 'workload, PVC, Route, Event 잔존 확인',
          },
          ...(canProposeCleanup
            ? [
                {
                  step: 3,
                  adapter: 'aiops-gateway',
                  tool: 'create_namespace_cleanup_action_candidate',
                  verb: 'propose',
                  purpose: '승인 필요 Namespace 정리 Action Plan 후보 생성',
                },
              ]
            : []),
        ],
        validation: {
          ok: inventory.ok,
          status: canProposeCleanup
            ? 'action_candidate_ready'
            : inventory.ok
              ? 'read_only_inventory_collected'
              : inventory.status,
        },
      },
      status: inventory.ok ? 'success' : 'failed',
    });
    sse(res, {
      type: 'text',
      content: answer,
      source: inventory.ok ? 'gateway_direct' : 'oc_read_failed',
      streamProbe: inventory.ok ? 'ok' : 'failed',
    });
    sse(res, {
      type: 'run_status',
      runId,
      stage: inventory.ok ? 'completed' : 'failed',
      message: inventory.ok ? '네임스페이스 read-only 조회를 완료했습니다.' : '네임스페이스 조회에 실패했습니다.',
    });
    endChatStream(res);
    return;
  }

  if (intent.intent === 'openshift_diagnosis') {
    sse(res, {
      type: 'run_status',
      runId,
      stage: 'started',
      message: 'OpenShift read-only 신호 조회를 시작했습니다.',
    });
    sse(res, {
      type: 'tool_call',
      id: 'openshift-signal-inventory-local',
      name: 'oc_openshift_signal_inventory',
      summary: 'oc read-only warning/operator/pod inventory',
    });
    const inventory = await buildOpenShiftSignalInventory();
    const answer = openShiftSignalAnswer(inventory);
    sse(res, {
      type: 'tool_result',
      id: 'openshift-signal-inventory-local',
      name: 'oc_openshift_signal_inventory',
      status: inventory.ok ? 'success' : 'failed',
      summary: inventory.ok
        ? `warning ${inventory.totals.warningEvents}개, operator issue ${inventory.totals.operatorIssues}개, pod issue ${inventory.totals.podIssues}개 조회`
        : 'OpenShift read-only 신호 조회 실패',
      result: inventory,
    });
    sse(res, {
      type: 'text',
      content: answer,
      source: inventory.ok ? 'oc_read_only_inventory' : 'oc_read_failed',
      streamProbe: inventory.ok ? 'ok' : 'failed',
    });
    sse(res, {
      type: 'run_status',
      runId,
      stage: inventory.ok ? 'completed' : 'failed',
      message: inventory.ok ? 'OpenShift read-only 신호 조회를 완료했습니다.' : 'OpenShift 신호 조회에 실패했습니다.',
    });
    endChatStream(res);
    return;
  }

  if (intent.intent === 'unclear_or_out_of_scope' || intent.intent === 'general_chat') {
    sse(res, {
      type: 'run_status',
      runId,
      stage: 'started',
      message: '요청 의도를 확인했습니다.',
    });
    sse(res, {
      type: 'tool_call',
      id: 'request-intent-local',
      name: 'request_intent_classifier',
      summary: '질문 의도와 OpenShift 운영 대상 확인',
    });
    sse(res, {
      type: 'tool_result',
      id: 'request-intent-local',
      name: 'request_intent_classifier',
      status: 'success',
      summary: `intent ${intent.intent}, confidence ${intent.confidence}`,
      result: intent,
    });
    sse(res, {
      type: 'text',
      content: unsupportedLocalQuestionAnswer(intent, executionMode),
      source: 'copilot_clarification',
      streamProbe: 'not_used',
    });
    sse(res, {
      type: 'run_status',
      runId,
      stage: 'completed',
      message: '추가 확인이 필요한 요청으로 정리했습니다.',
    });
    endChatStream(res);
    return;
  }

  if (intent.intent !== 'action_plan_request') {
    sse(res, {
      type: 'text',
      content: unsupportedLocalQuestionAnswer(
        {
          confidence: 'low',
          intent: 'unclear_or_out_of_scope',
          reason: 'no_matching_operational_route',
        },
        executionMode,
      ),
      source: 'copilot_clarification',
      streamProbe: 'not_used',
    });
    endChatStream(res);
    return;
  }

  const contextDigest = 'sha256:local-rca-context-v1';
  const crashloopActionCapableMode = actionCapableExecutionMode(executionMode);
  const toolPlan = {
    task_type: 'pod_restart_rca',
    target: LOCAL_TARGET,
    execution_policy: {
      mode: actionPolicyModeForExecutionMode(executionMode, crashloopActionCapableMode),
      mutations_enabled: crashloopActionCapableMode,
      local_fixture_only: true,
    },
    tool_plan: [
      {
        step: 1,
        adapter: 'OpenShift',
        tool: 'openshift_get_alerts',
        verb: 'list',
        purpose: '최근 경고 확인',
      },
      {
        step: 2,
        adapter: 'OpenShift',
        tool: 'openshift_get_deployment',
        verb: 'get',
        purpose: '대상 Deployment 상태 확인',
      },
      ...(crashloopActionCapableMode
        ? [
            {
              step: 3,
              adapter: 'AI Gateway',
              tool: 'gateway_pending_action_plan_lookup',
              verb: 'get',
              purpose: '승인 가능한 Action Plan 확인',
            },
          ]
        : []),
    ],
    validation: { ok: true, status: 'local_fixture_validated' },
  };
  const rcaContext = {
    apiVersion: 'aiops.komsco/v1alpha1',
    kind: 'RcaContext',
    metadata: { digest: contextDigest, generatedAt: nowIso(), source: 'local-fixture' },
    target: LOCAL_TARGET,
    evidence: {
      confirmed: [
        'KubePodNotReady alert is firing for openshift-marketplace/appscan360-catalog.',
        'Local simulator target Deployment is 0/1 ready.',
      ],
      missing: ['실제 OpenShift API 변경은 수행하지 않는 local-only fixture입니다.'],
    },
    rcaResult: {
      causes: ['CrashLoopBackOff fixture가 의도적으로 주입되어 있습니다.'],
      actions: ['Deployment rollout restart Action Plan 승인 후 실행'],
    },
  };
  const evidenceStatus = [
    { label: '수집 근거', status: 'ok', value: '2' },
    { label: '추가 확인', status: 'warn', value: '1' },
    {
      label: 'Action Plan',
      status: crashloopActionCapableMode ? 'ok' : 'warn',
      value: crashloopActionCapableMode ? '가능' : '읽기 전용',
    },
  ];
  const answer = [
    '## 현재 판단',
    crashloopActionCapableMode
      ? `${executionModeSentence(executionMode)} CrashLoopBackOff 복구 조치는 승인 가능한 Action Plan 후보로 정리할 수 있습니다.`
      : `${executionModeSentence(executionMode)} CrashLoopBackOff 복구 조치는 조회와 근거 정리까지만 표시합니다.`,
    '',
    '## 영향 범위',
    '- 대상: Deployment 1개',
    '- 현재 상태: ready replica 0/1',
    '- 사용자 영향: 해당 Deployment가 제공하는 기능 일부 중단 가능',
    '',
    '## 확인한 근거',
    '- `KubePodNotReady` 경고가 firing 상태입니다.',
    '- 대상 Deployment 1개가 `0/1 ready` 상태입니다.',
    '',
    '## 추가 확인',
    '- 실제 운영 판단에서는 Pod 로그와 이벤트가 필요합니다.',
    '- 최근 배포 변경 이력을 확인해야 원인을 확정할 수 있습니다.',
    '- 실행 전 대상 Deployment와 namespace가 최신인지 다시 확인해야 합니다.',
    '',
    '## Action Plan',
    crashloopActionCapableMode
      ? '- 상태: 승인 필요 Action Plan 후보 생성 가능'
      : '- 상태: 읽기 전용 모드라 계획 생성/실행 버튼을 표시하지 않음',
    '- 조치: Deployment rollout restart',
    '- 검증: 재시작 후 ready replica가 `1/1`로 회복되는지 확인',
    '- 롤백: 필요 시 직전 ReplicaSet으로 rollout undo',
  ].join('\n');

  sse(res, {
    type: 'run_status',
    runId,
    stage: 'started',
    message: crashloopActionCapableMode
      ? 'CrashLoopBackOff 근거와 Action Plan 후보 확인을 시작했습니다.'
      : 'CrashLoopBackOff 근거를 읽기 전용으로 확인합니다.',
  });
  sse(res, {
    type: 'tool_call',
    id: 'access-check-local',
    name: 'access_check',
    summary: '사용자 권한 확인',
    detail: 'local-admin fixture subject',
  });
  sse(res, {
    type: 'tool_result',
    id: 'access-check-local',
    name: 'access_check',
    status: 'success',
    summary: 'local-admin 권한 확인 완료',
  });
  sse(res, { type: 'tool_plan', runId, plan: toolPlan, status: 'success' });
  sse(res, {
    type: 'rca_context',
    runId,
    phase: 'plan_ready',
    status: 'success',
    context: rcaContext,
    evidenceStatus,
  });
  if (crashloopActionCapableMode) {
    sse(res, {
      type: 'tool_call',
      id: 'pending-action-local',
      name: 'gateway_pending_action_plan_lookup',
      summary: '승인 대기 Action Plan 확인',
    });
    sse(res, {
      type: 'tool_result',
      id: 'pending-action-local',
      name: 'gateway_pending_action_plan_lookup',
      status: 'success',
      summary: 'plan-local-crashloop 승인 대기',
      result: { planId: 'plan-local-crashloop', planDigest: LOCAL_PLAN_DIGEST },
    });
  }
  sse(res, {
    type: 'text',
    content: answer,
    gatewayContextDigest: contextDigest,
    source: 'local_fixture',
    streamProbe: 'ok',
  });
  sse(res, {
    type: 'rca_context',
    runId,
    phase: 'post_answer',
    status: 'success',
    context: rcaContext,
    evidenceStatus,
  });
  sse(res, {
    type: 'run_status',
    runId,
    stage: 'completed',
    message: 'CrashLoopBackOff 근거 연결과 조치 가능성 확인을 완료했습니다.',
  });
  endChatStream(res);
};

const json = (res, statusCode, payload) => {
  const body = JSON.stringify(payload, null, 2);
  res.writeHead(statusCode, {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Authorization, Content-Type',
    'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store',
  });
  res.end(body);
};

const contentTypeFor = (filePath) => {
  if (filePath.endsWith('.html')) return 'text/html; charset=utf-8';
  if (filePath.endsWith('.js')) return 'text/javascript; charset=utf-8';
  if (filePath.endsWith('.css')) return 'text/css; charset=utf-8';
  if (filePath.endsWith('.json')) return 'application/json; charset=utf-8';
  if (filePath.endsWith('.md')) return 'text/markdown; charset=utf-8';
  if (filePath.endsWith('.svg')) return 'image/svg+xml';
  if (filePath.endsWith('.woff2')) return 'font/woff2';
  if (filePath.endsWith('.png')) return 'image/png';
  return 'application/octet-stream';
};

const serveDocsArtifact = (url, res) => {
  if (!servePortal) {
    return false;
  }

  const allowedPrefixes = [
    '/local-',
    '/local-aiops-screenshots/',
  ];
  if (!allowedPrefixes.some((prefix) => url.pathname.startsWith(prefix))) {
    return false;
  }

  const requestPath = decodeURIComponent(url.pathname);
  const candidate = path.normalize(path.join(docsRoot, requestPath));
  const safeRoot = docsRoot + path.sep;
  if (!candidate.startsWith(safeRoot) || !fs.existsSync(candidate) || !fs.statSync(candidate).isFile()) {
    return false;
  }

  fs.readFile(candidate, (error, data) => {
    if (error) {
      json(res, 500, {
        error: 'docs artifact unavailable',
        detail: error.message,
        expected: docsRoot,
      });
      return;
    }
    res.writeHead(200, {
      'Content-Type': contentTypeFor(candidate),
      'Cache-Control': 'no-store',
    });
    res.end(data);
  });
  return true;
};

const serveStaticPortal = (url, res) => {
  if (!servePortal) {
    return false;
  }

  let requestPath = decodeURIComponent(url.pathname);
  if (requestPath === '/' || requestPath === '/dashboards' || requestPath.startsWith('/dashboards/')) {
    requestPath = '/index.html';
  }

  const candidate = path.normalize(path.join(portalDist, requestPath));
  const safeRoot = portalDist + path.sep;
  const filePath = candidate.startsWith(safeRoot) ? candidate : path.join(portalDist, 'index.html');
  const finalPath = fs.existsSync(filePath) && fs.statSync(filePath).isFile()
    ? filePath
    : path.join(portalDist, 'index.html');

  fs.readFile(finalPath, (error, data) => {
    if (error) {
      json(res, 500, {
        error: 'portal dist unavailable',
        detail: error.message,
        expected: portalDist,
      });
      return;
    }
    res.writeHead(200, {
      'Content-Type': contentTypeFor(finalPath),
      'Cache-Control': 'no-store',
    });
    res.end(data);
  });
  return true;
};

const clusterSummary = () => ({
  apiUrl: 'https://api.local-aiops.invalid:6443',
  healthScore: 92,
  updatedAt: nowIso(),
  version: {
    version: '4.20-local',
    channel: 'stable-local',
    updateAvailable: false,
    upgradeable: true,
    availableUpdates: [],
  },
  nodes: {
    total: 1,
    ready: 1,
    notReady: 0,
    pressureCount: 0,
    metricsAvailable: true,
    items: [
      {
        name: 'local-control-plane-0',
        ready: true,
        roles: ['control-plane', 'worker'],
        kubeletVersion: 'v1.31-local',
        osImage: 'RHCOS local fixture',
        pressures: { disk: false, memory: false, pid: false },
        usage: { cpu: '31%', memory: '58%' },
      },
    ],
  },
  operators: {
    total: 8,
    available: 8,
    unavailable: 0,
    progressing: 0,
    degraded: 0,
    issues: [],
  },
  aiopsWorkloads: {
    total: 3,
    issues: 1,
    namespaces: ['komsco-ai-local', 'openshift-marketplace'],
    deployments: [
      {
        kind: 'Deployment',
        namespace: 'komsco-ai-local',
        name: 'aiops-local-worker',
        desired: 3,
        ready: 3,
        available: 3,
        updated: 3,
        severity: 'ok',
        detail: 'local simulator state: ready 3/3',
      },
      {
        kind: 'Deployment',
        namespace: 'komsco-ai-local',
        name: 'aiops-scenario-crashloop',
        desired: 1,
        ready: 0,
        available: 0,
        updated: 1,
        severity: 'risk',
        detail: 'CrashLoopBackOff fixture for Action Plan testing',
      },
    ],
    daemonsets: [],
  },
  resources: {
    total: 4,
    issues: 1,
    items: [
      {
        id: 'alert-kubepodnotready-local',
        kind: 'Alert',
        name: 'KubePodNotReady',
        detail: 'openshift-marketplace/appscan360-catalog fixture is not ready',
        ready: 'firing',
        total: 1,
        issues: 1,
        score: 'risk',
        severity: 'risk',
      },
      {
        id: 'deployment-aiops-local-worker',
        kind: 'Deployment',
        name: 'aiops-local-worker',
        detail: 'ready 3/3 in local simulator',
        ready: 3,
        total: 3,
        issues: 0,
        score: 'ok',
        severity: 'ok',
      },
    ],
  },
});

const aiopsStatus = () => ({
  spec: {
    capabilities: {
      actionExecutorConfigured: true,
      diagnosticsControllerConfigured: true,
      diagnosticsEnabled: true,
      mutationsEnabled: true,
      unrestrictedCommandsEnabled: true,
      recordStoreEnabled: true,
      recordStoreConfigMap: 'local-aiops-fixture-ledger',
      rag: { backend: 'local-fixture', enabled: true },
      safetyContract: { mode: 'local-only', companyMutation: false },
    },
    subject: {
      username: 'local-admin',
      server: 'https://api.local-aiops.invalid:6443',
    },
    safetyContract: {
      mode: 'controlled_execution',
      allowedReadOnlyVerbs: ['get', 'list', 'watch'],
      forbiddenActions: [],
      capabilityGates: {
        actionExecution: true,
        unrestrictedCommands: true,
        localOnly: true,
      },
      evidenceStatus: [
        { label: '수집 근거', status: 'ok', value: '2' },
        { label: '추가 확인', status: 'warn', value: '1' },
        { label: 'Action Plan', status: 'ok', value: '가능' },
      ],
      product: {
        name: 'AIOps Copilot',
        mission: 'local-only controlled execution fixture',
        mode: 'local-fixture',
      },
      lightspeedStatus: {
        fallbackActive: false,
        lastStatus: 'local_fixture',
        status: 'ok',
        streamProbe: 'ok',
      },
    },
    records: {
      actionProposals: [localProposalRecord(), ...Array.from(LOCAL_ACTION_PROPOSALS.values())],
      sealedActionPlans: [localSealedPlanRecord(), ...Array.from(LOCAL_SEALED_PLANS.values())],
      approvalDecisions: Array.from(LOCAL_APPROVALS.values()),
      executionRecords: Array.from(LOCAL_EXECUTIONS.values()),
      auditRecords: [localAuditRecord()],
      diagnosticRequests: [],
      chatTranscripts: [],
      chatFeedback: Array.from(LOCAL_CHAT_FEEDBACK.values()),
    },
  },
});

const actionCandidates = () => ({
  apiVersion: 'aiops.komsco/v1',
  kind: 'AIOpsActionCandidateSummary',
  metadata: { name: 'local-aiops-action-candidates', generatedAt: nowIso() },
  spec: {
    candidates: [
      {
        id: 'candidate-local-crashloop-restart',
        title: 'CrashLoopBackOff Deployment 재시작',
        severity: 'risk',
        confidence: 'high',
        riskLevel: 'low',
        riskLabel: '낮음',
        statusLabel: '승인 필요',
        sourceType: 'local-fixture',
        sourceFindingId: 'ev-local-alert-notready',
        target: LOCAL_TARGET,
        evidence:
          'KubePodNotReady alert와 0/1 ready Deployment 상태가 동시에 확인되었습니다.',
        expectedImpact: '로컬 fixture 대상 Deployment 1개만 재시작 시뮬레이션합니다.',
        recommendationSteps: [
          '대상 Deployment 상태 확인',
          'rollout restart 승인',
          'ready replica 1/1 회복 확인',
        ],
        verificationChecks: ['Deployment ready replica가 1/1인지 확인'],
        prerequisiteChecks: ['local-only fixture mode 확인'],
        executable: true,
        approvalRequired: true,
        executionPolicy: {
          executionEnabled: true,
          mode: 'local-only',
          proposalOnly: false,
        },
        evidenceRefs: [{ id: 'ev-local-alert-notready', source: 'local-fixture' }],
      },
      {
        id: 'candidate-local-namespace-cleanup-komsco-aiops-lab',
        title: '미사용 namespace 정리',
        severity: 'review',
        confidence: 'medium',
        riskLevel: 'medium',
        riskLabel: '중간',
        statusLabel: '승인 필요',
        sourceType: 'oc-read-only-inventory',
        sourceFindingId: 'ev-local-namespace-cleanup-komsco-aiops-lab',
        target: LOCAL_NAMESPACE_CLEANUP_TARGET,
        evidence:
          'komsco-aiops-lab namespace에서 workload/PVC/route가 없고 정리 검토 가능 상태로 분류되었습니다.',
        expectedImpact:
          '승인 후 komsco-aiops-lab namespace 삭제를 시뮬레이션합니다. 승인 전에는 삭제하지 않습니다.',
        recommendationSteps: [
          '소유자와 데이터 보존 필요 여부 확인',
          'PVC/Route/Workload 잔존 여부 재확인',
          'Namespace 삭제 계획 승인',
        ],
        verificationChecks: ['Namespace가 삭제되었거나 deletionTimestamp가 설정되었는지 확인'],
        prerequisiteChecks: ['소유자 확인', '백업 필요 없음 확인', 'PVC/Route 잔존 없음 확인'],
        executable: true,
        approvalRequired: true,
        executionPolicy: {
          executionEnabled: true,
          mode: 'controlled-execution',
          proposalOnly: false,
        },
        evidenceRefs: [{ id: 'ev-local-namespace-cleanup-komsco-aiops-lab', source: 'oc' }],
      },
      {
        id: 'candidate-local-create-test-pods-gpu-test-kugnus',
        title: '테스트 Pod 3개 생성',
        severity: 'review',
        confidence: 'high',
        riskLevel: 'low',
        riskLabel: '낮음',
        statusLabel: '승인 필요',
        sourceType: 'chat-request',
        sourceFindingId: 'ev-local-user-request-test-pods',
        target: LOCAL_TEST_POD_TARGET,
        evidence: '사용자가 gpu-test-kugnus namespace에 테스트 Pod 3개 생성을 요청했습니다.',
        expectedImpact: 'gpu-test-kugnus namespace에 테스트 Pod 3개를 생성합니다.',
        recommendationSteps: [
          '대상 namespace 존재 확인',
          '테스트 Pod 생성 계획 승인',
          'Pod 오브젝트 3개 생성 확인',
        ],
        verificationChecks: ['label aiops.komsco.local/request-id 기준 Pod 3개 조회'],
        prerequisiteChecks: ['oc whoami --show-server 회사 서버 일치', 'gpu-test-kugnus namespace 존재'],
        executable: true,
        approvalRequired: true,
        executionPolicy: {
          executionEnabled: true,
          mode: 'controlled-execution',
          proposalOnly: false,
        },
        evidenceRefs: [{ id: 'ev-local-user-request-test-pods', source: 'chat' }],
      },
    ],
    dataSources: [
      { name: 'local-fixture', status: 'ok', detail: 'deterministic local simulator' },
    ],
    safety: {
      forbiddenMutationVerbs: [],
      mode: 'local-only',
    },
  },
});

const makeApprovalRecord = (approvalScope = 'single-target', actionType = 'crashloop') => {
  const approvalId = `approval-local-${Date.now()}`;
  const approvedAt = nowIso();
  const target = targetForAction(actionType);
  const planDigest = planDigestForAction(actionType);
  const action = localAction(actionType);
  const record = {
    schemaVersion: 'v1',
    apiVersion: 'aiops.komsco/v1',
    kind: 'ApprovalDecisionRecord',
    metadata: { name: approvalId, createdAt: approvedAt },
    spec: {
      approvalDecision: {
        approvalId,
        planDigest,
        status: 'approved',
        approver: LOCAL_SUBJECT,
        approvedAt,
        expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
        approvalScope,
        target,
        authorizationAttestationRef: {
          attestationId: `attestation-${approvalId}`,
          attestationDigest: `sha256:${approvalId}`,
          bearerAttestationStored: false,
          issuer: 'local-fixture',
          audience: 'aiops-action-executor',
        },
        kubernetesAuthorization: {
          apiGroup: action.authorization.apiGroup,
          resource: action.authorization.resource,
          subresource: '',
          verb: action.authorization.verb,
          ssarDecision: 'allowed',
          evaluatedAt: approvedAt,
          review: { allowed: true, reason: 'local fixture approval' },
        },
        action,
        ...(approvalScope === 'lab-auto-unrestricted'
          ? {
              decidedBy: 'auto-policy',
              decisionPolicy: {
                toolName: action.toolName,
                triggeredBy: 'local-fixture-unrestricted-mode',
              },
            }
          : {}),
      },
    },
    subject: LOCAL_SUBJECT,
  };

  LOCAL_APPROVALS.set(approvalId, record);
  return record;
};

const makeExecutionRecord = async (approvalId, actionType = 'crashloop') => {
  const executionId = `execution-local-${Date.now()}`;
  const createdAt = nowIso();
  const isTestPods = actionType === 'test-pods';
  const isNamespaceCleanup = actionType === 'namespace-cleanup';
  const executionResult = isTestPods ? await executeTestPodCreatePlan() : null;
  const target = targetForAction(actionType);
  const planId = planIdForAction(actionType);
  const planDigest = planDigestForAction(actionType);
  const record = {
    schemaVersion: 'v1',
    apiVersion: 'aiops.komsco/v1',
    kind: 'ExecutionRecord',
    metadata: { name: executionId, createdAt },
    spec: {
      executionId,
      approvalId,
      planId,
      planDigest,
      executionGrantRef: {
        grantId: `grant-${executionId}`,
        grantDigest: `sha256:${executionId}`,
        bearerGrantStored: false,
      },
      mutationOutcome: {
        status: isTestPods ? executionResult.status : 'mutation_succeeded',
        reason: isTestPods
          ? executionResult.reason
          : isNamespaceCleanup
            ? 'local simulator accepted namespace cleanup after approval'
            : 'local simulator accepted rollout restart',
      },
      remediationOutcome: {
        status: isTestPods && !executionResult.ok ? 'verification_failed' : 'verified',
        reason: isNamespaceCleanup
          ? `${target.name} namespace cleanup simulated`
          : isTestPods
          ? `observed ${executionResult.observedPods || 0}/${LOCAL_TEST_POD_COUNT} created pods`
          : 'restart_annotation_observed',
      },
      executorTrace: {
        mutationSubmitted: isTestPods ? executionResult.companyMutationExecuted : true,
        companyMutationExecuted: isTestPods ? executionResult.companyMutationExecuted : false,
        mode: isTestPods ? 'oc-company-server' : 'local-only',
        ...(isTestPods
          ? {
              createdPods: executionResult.createdPods,
              requestId: executionResult.requestId,
              server: executionResult.server,
              target,
            }
          : {}),
      },
      executionAuthorization: {
        allowed: !isTestPods || executionResult.ok,
        reason: isTestPods ? executionResult.reason : 'local fixture execution',
      },
    },
    subject: LOCAL_SUBJECT,
  };
  const approval = LOCAL_APPROVALS.get(approvalId);
  const decision = approval?.spec?.approvalDecision;
  if (decision) {
    decision.status = 'executed';
    decision.executedAt = createdAt;
  }
  LOCAL_EXECUTIONS.set(executionId, record);
  return record;
};

const eventFeed = () => ({
  metadata: {
    name: 'local-aiops-fixture-events',
    generatedAt: nowIso(),
  },
  spec: {
    pollIntervalSeconds: 15,
    sources: ['local-fixture'],
    items: [
      {
        id: 'ev-local-alert-notready',
        category: 'alert',
        severity: 'risk',
        source: 'local-fixture',
        title: 'KubePodNotReady',
        detail: 'openshift-marketplace/appscan360-catalog fixture is not ready',
        namespace: 'openshift-marketplace',
        target: 'appscan360-catalog',
        time: nowIso(),
      },
      {
        id: 'ev-local-action-plan',
        category: 'approval',
        severity: 'warn',
        source: 'local-fixture',
        title: 'Action Plan 승인 필요',
        detail: 'CrashLoopBackOff 복구 조치 후보가 승인 대기 중입니다.',
        namespace: 'komsco-ai-local',
        target: 'aiops-scenario-crashloop',
        time: nowIso(),
      },
    ],
  },
});

const server = http.createServer(async (req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': 'Authorization, Content-Type',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    });
    res.end();
    return;
  }

  const url = new URL(req.url || '/', `http://${req.headers.host || `${host}:${port}`}`);
  if (url.pathname === '/healthz') {
    json(res, 200, { ok: true, mode: 'local-only', companyMutationExecuted: false });
    return;
  }
  if (url.pathname === '/v1/auth/subject') {
    json(res, 200, LOCAL_SUBJECT);
    return;
  }
  if (url.pathname === '/v1/chat/stream' && req.method === 'POST') {
    await streamLocalChat(req, res);
    return;
  }
  if (url.pathname === '/v1/chat/feedback' && req.method === 'POST') {
    const body = await readJsonBody(req);
    const submittedAt = nowIso();
    const feedbackId =
      String(body.feedbackId || '').trim() ||
      `feedback-local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    const record = {
      apiVersion: 'aiops.komsco/v1',
      kind: 'ChatFeedbackRecord',
      metadata: { name: feedbackId, createdAt: submittedAt },
      spec: {
        answerContract: body.answerContract || '',
        answerSource: body.answerSource || '',
        conversationId: body.conversationId || '',
        messageId: body.messageId || '',
        mode: body.mode || '',
        optionalComment: body.optionalComment ? String(body.optionalComment).slice(0, 1000) : '',
        rating: body.rating === 'down' ? 'down' : 'up',
        route: body.route || '',
        intent: body.intent || '',
        submittedAt,
      },
      subject: LOCAL_SUBJECT,
    };
    LOCAL_CHAT_FEEDBACK.set(feedbackId, record);
    json(res, 200, {
      apiVersion: 'aiops.komsco/v1',
      kind: 'ChatFeedback',
      metadata: record.metadata,
      spec: record.spec,
    });
    return;
  }
  if (url.pathname === '/v1/cluster/summary') {
    json(res, 200, clusterSummary());
    return;
  }
  if (url.pathname === '/v1/aiops/status') {
    json(res, 200, aiopsStatus());
    return;
  }
  if (url.pathname === '/v1/aiops/action-candidates') {
    json(res, 200, actionCandidates());
    return;
  }
  if (url.pathname === '/v1/aiops/events') {
    json(res, 200, eventFeed());
    return;
  }
  if (url.pathname === '/v1/rag/uploads') {
    json(res, 200, {
      apiVersion: 'aiops.komsco/v1',
      kind: 'RagUploadedDocumentList',
      metadata: { generatedAt: nowIso(), name: 'local-fixture-rag-uploads' },
      spec: { items: [] },
    });
    return;
  }
  if (url.pathname === '/v1/actions/plans' && req.method === 'POST') {
    const body = await readJsonBody(req);
    const actionType = actionTypeFromProposalId(body.proposalId) || 'crashloop';
    const record = localSealedPlanRecord(actionType);
    if (actionType === 'test-pods' || actionType === 'namespace-cleanup') {
      LOCAL_ACTION_PROPOSALS.set(proposalIdForAction(actionType), localProposalRecord(actionType));
      LOCAL_SEALED_PLANS.set(record.metadata.name, record);
    }
    json(res, 200, {
      apiVersion: 'aiops.komsco/v1',
      kind: 'SealedActionPlan',
      metadata: record.metadata,
      spec: record.spec,
    });
    return;
  }
  if (url.pathname === '/v1/actions/candidate-plans' && req.method === 'POST') {
    const body = await readJsonBody(req);
    const actionType = actionTypeFromCandidateId(body.candidateId) || 'crashloop';
    const proposal = localProposalRecord(actionType);
    const plan = localSealedPlanRecord(actionType);
    if (actionType === 'test-pods' || actionType === 'namespace-cleanup') {
      LOCAL_ACTION_PROPOSALS.set(proposal.metadata.name, proposal);
      LOCAL_SEALED_PLANS.set(plan.metadata.name, plan);
    }
    json(res, 200, {
      apiVersion: 'aiops.komsco/v1',
      kind: 'ActionCandidatePlan',
      metadata: {
        name:
          actionType === 'namespace-cleanup'
            ? 'candidate-plan-local-namespace-cleanup'
            : actionType === 'test-pods'
            ? 'candidate-plan-local-test-pods'
            : 'candidate-plan-local-crashloop',
        createdAt: nowIso(),
      },
      spec: {
        candidateId:
          body.candidateId ||
          (actionType === 'namespace-cleanup'
            ? 'candidate-local-namespace-cleanup-komsco-aiops-lab'
            : actionType === 'test-pods'
            ? 'candidate-local-create-test-pods-gpu-test-kugnus'
            : 'candidate-local-crashloop-restart'),
        plan: {
          apiVersion: 'aiops.komsco/v1',
          kind: 'SealedActionPlan',
          metadata: plan.metadata,
          spec: plan.spec,
        },
        planDigest: planDigestForAction(actionType),
        planId: plan.metadata.name,
        proposal: {
          apiVersion: 'aiops.komsco/v1',
          kind: 'ActionProposal',
          metadata: proposal.metadata,
          spec: proposal.spec,
        },
        proposalId: proposal.metadata.name,
        status: 'planned',
        target: targetForAction(actionType),
        title: actionTitleForAction(actionType),
      },
    });
    return;
  }
  if (url.pathname === '/v1/actions/approvals' && req.method === 'POST') {
    const body = await readJsonBody(req);
    const actionType =
      actionTypeFromPlanDigest(body.expectedPlanDigest) || actionTypeFromPlanId(body.planId) || 'crashloop';
    if (
      body.expectedPlanDigest &&
      !localPlanDigests().includes(body.expectedPlanDigest)
    ) {
      json(res, 409, { detail: 'expectedPlanDigest does not match the sealed plan' });
      return;
    }
    const record = makeApprovalRecord(body.approvalScope || 'single-target', actionType);
    json(res, 200, {
      apiVersion: 'aiops.komsco/v1',
      kind: 'ApprovalDecision',
      metadata: record.metadata,
      spec: record.spec,
    });
    return;
  }
  if (url.pathname === '/v1/actions/rejections' && req.method === 'POST') {
    const body = await readJsonBody(req);
    const actionType =
      actionTypeFromPlanDigest(body.expectedPlanDigest) || actionTypeFromPlanId(body.planId) || 'crashloop';
    if (
      body.expectedPlanDigest &&
      !localPlanDigests().includes(body.expectedPlanDigest)
    ) {
      json(res, 409, { detail: 'expectedPlanDigest does not match the sealed plan' });
      return;
    }
    const rejectedAt = nowIso();
    const rejectionId = `rejection-local-${Date.now()}`;
    const record = {
      apiVersion: 'aiops.komsco/v1',
      kind: 'ApprovalDecision',
      metadata: { name: rejectionId, createdAt: rejectedAt },
      spec: {
        approvalDecision: {
          approvalId: rejectionId,
          planDigest: planDigestForAction(actionType),
          status: 'rejected',
          approver: LOCAL_SUBJECT,
          rejectedAt,
          reason: body.reason || 'operator rejected the proposed action',
          approvalScope: 'single-target',
          target: targetForAction(actionType),
          action: localAction(actionType),
        },
      },
    };
    LOCAL_APPROVALS.set(rejectionId, {
      ...record,
      schemaVersion: 'v1',
      kind: 'ApprovalDecisionRecord',
      subject: LOCAL_SUBJECT,
    });
    json(res, 200, record);
    return;
  }
  if (url.pathname === '/v1/actions/execute' && req.method === 'POST') {
    const body = await readJsonBody(req);
    const actionType =
      actionTypeFromPlanDigest(body.expectedPlanDigest) || actionTypeFromPlanId(body.planId) || 'crashloop';
    if (
      body.expectedPlanDigest &&
      !localPlanDigests().includes(body.expectedPlanDigest)
    ) {
      json(res, 409, { detail: 'Execution request is stale for this sealed plan' });
      return;
    }
    const approvalId =
      body.approvalId || makeApprovalRecord('lab-auto-unrestricted', actionType).metadata.name;
    const record = await makeExecutionRecord(approvalId, actionType);
    json(res, 200, {
      apiVersion: 'aiops.komsco/v1',
      kind: 'ExecutionRecord',
      metadata: record.metadata,
      spec: record.spec,
    });
    return;
  }
  if (serveDocsArtifact(url, res)) {
    return;
  }
  if (serveStaticPortal && serveStaticPortal(url, res)) {
    return;
  }

  json(res, 404, {
    error: 'local fixture route not found',
    path: url.pathname,
    mode: 'local-only',
  });
});

server.listen(port, host, () => {
  const mode = servePortal ? 'fixture gateway + portal' : 'fixture gateway';
  console.log(`v0.2.8.1 local AIOps ${mode} listening on http://${host}:${port}`);
});
