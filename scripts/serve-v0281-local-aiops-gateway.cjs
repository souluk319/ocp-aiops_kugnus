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
const LOCAL_ACTION_REGISTRY_DIGEST = 'sha256:local-action-registry-v1';
const LOCAL_POLICY_DIGEST = 'sha256:local-policy-v1';
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

const localAction = () => ({
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
});

const localProposalRecord = () => ({
  schemaVersion: 'v1',
  apiVersion: 'aiops.komsco/v1',
  kind: 'ActionProposalRecord',
  metadata: { name: 'proposal-local-crashloop', createdAt: nowIso() },
  spec: {
    candidateActionRequest: {
      schemaVersion: 'v1',
      title: 'CrashLoopBackOff 복구 조치 후보',
      target: LOCAL_TARGET,
      action: localAction(),
      requester: LOCAL_SUBJECT,
      policy: {
        mode: 'local-only',
        sourceType: 'local-fixture',
        policyDecisionDigest: LOCAL_POLICY_DIGEST,
      },
    },
    candidateRequestDigest: 'sha256:local-candidate-request-v1',
    digestSchema: {
      name: 'candidate-action-request-digest-v1',
      canonicalization: 'stable-json-sort-keys',
    },
    evidenceRefs: [
      {
        id: 'ev-local-alert-notready',
        kind: 'Alert',
        source: 'local-fixture',
      },
    ],
    incidentId: 'inc-local-crashloop',
    runId: 'run-local-fixture',
    runbookRefs: [
      {
        title: 'Deployment restart runbook',
        uri: 'local-fixture://runbooks/deployment-restart',
      },
    ],
    sourceType: 'local-fixture',
    status: { phase: 'proposed' },
  },
  subject: LOCAL_SUBJECT,
});

const localSealedPlanRecord = () => {
  const createdAt = nowIso();
  const plan = {
    schemaVersion: 'v1',
    clusterId: 'local-aiops-fixture',
    metadata: {
      planId: 'plan-local-crashloop',
      incidentId: 'inc-local-crashloop',
      requester: LOCAL_SUBJECT,
      idempotencyKey: 'idem-local-crashloop',
      createdAt,
      apiCallTimeout: '30s',
      verificationDeadline: '10m',
      maxMutationAttempts: 1,
      maxVerificationAttempts: 3,
    },
    target: LOCAL_TARGET,
    action: localAction(),
    safety: {
      risk: 'low',
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
        { type: 'TargetExists', value: true },
        { type: 'LocalFixtureOnly', value: true },
      ],
      hardPostconditions: [{ type: 'ExecutionRecordTerminalState', value: true }],
      observationalPostconditions: [
        { type: 'DeploymentRestartObserved', value: LOCAL_TARGET.name },
      ],
      rollbackDescription: '필요 시 직전 ReplicaSet으로 rollout undo를 수행합니다.',
      rollbackRequiresApproval: true,
      rollbackPossible: true,
      expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
    },
    approvalPresentation: {
      impact: {
        affectedWorkloads: 1,
        affectedPods: 1,
        availabilityRisk: 'low',
        summaryDigest: 'sha256:local-impact-v1',
      },
      dryRun: {
        decision: 'local_fixture_validated',
        normalizedDiffDigest: 'sha256:local-dry-run-v1',
      },
      evidenceRefs: [{ id: 'ev-local-alert-notready', source: 'local-fixture' }],
      runbookRefs: [{ title: 'Deployment restart runbook' }],
    },
    digest: {
      planDigest: LOCAL_PLAN_DIGEST,
      canonicalization: 'stable-json-sort-keys',
      digestSchema: 'sealed-action-plan-digest-v1',
    },
  };

  return {
    schemaVersion: 'v1',
    apiVersion: 'aiops.komsco/v1',
    kind: 'SealedActionPlanRecord',
    metadata: { name: 'plan-local-crashloop', createdAt },
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
  res.write(`data: ${JSON.stringify(payload)}\n\n`);
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
  return /(openshift|오픈시프트|경고|alert|event|이벤트|operator|pod|clusteroperator|co\b)/i.test(text);
};

const ocReadTimeoutMs = Number(process.env.AIOPS_LOCAL_OC_TIMEOUT_MS || 12000);
const namespaceNamePattern = /\b[a-z0-9](?:[-a-z0-9]*[a-z0-9])?\b/g;
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

const namespaceInventoryAnswer = (inventory) => {
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

  const lines = [
    '## 현재 판단',
    '실제 `oc` 읽기 전용 조회 결과로만 분류했습니다. 삭제나 변경은 실행하지 않았습니다.',
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
    '- `정리 검토 가능`만 삭제 계획 후보로 올립니다.',
    '- `사용 중`, `삭제 보류`, `보호`는 삭제 계획을 만들지 않습니다.',
    '- 삭제 전 승인 조건: 소유자 확인, PVC/Route 잔존 여부 확인, 백업 필요 여부 확인.',
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

const unsupportedLocalQuestionAnswer = () => [
  '## 현재 상태',
  '이 질문은 5174 local fixture의 실행 가능한 시나리오로 처리하지 않았습니다.',
  '',
  '## 실행한 조회',
  '- 없음',
  '',
  '## 가능한 요청',
  '- 최근 OpenShift 경고와 Action Plan 테스트',
  '- 특정 네임스페이스의 사용 여부 read-only 조회',
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

  if (isNamespaceCleanupQuestion(userMessage)) {
    sse(res, {
      type: 'run_status',
      runId,
      stage: 'started',
      message: '네임스페이스 read-only 조회를 시작했습니다.',
    });
    sse(res, {
      type: 'tool_call',
      id: 'namespace-inventory-local',
      name: 'oc_namespace_inventory',
      summary: 'oc read-only namespace inventory',
    });
    const inventory = await buildNamespaceInventory(userMessage);
    const answer = namespaceInventoryAnswer(inventory);
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
          mode: 'read_only_review',
          mutations_enabled: false,
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
        ],
        validation: {
          ok: inventory.ok,
          status: inventory.ok ? 'read_only_inventory_collected' : inventory.status,
        },
      },
      status: inventory.ok ? 'success' : 'failed',
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
      message: inventory.ok ? '네임스페이스 read-only 조회를 완료했습니다.' : '네임스페이스 조회에 실패했습니다.',
    });
    sse(res, { type: 'end', conversationId: `local-fixture-${Date.now()}` });
    res.end();
    return;
  }

  if (isOpenShiftSignalQuestion(userMessage)) {
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
    sse(res, { type: 'end', conversationId: `local-fixture-${Date.now()}` });
    res.end();
    return;
  }

  if (!isCrashloopDemoQuestion(userMessage)) {
    sse(res, {
      type: 'run_status',
      runId,
      stage: 'skipped',
      message: 'local fixture 처리 범위 밖의 질문입니다.',
    });
    sse(res, {
      type: 'text',
      content: unsupportedLocalQuestionAnswer(),
      source: 'local_fixture_guard',
      streamProbe: 'not_used',
    });
    sse(res, { type: 'end', conversationId: `local-fixture-${Date.now()}` });
    res.end();
    return;
  }

  const contextDigest = 'sha256:local-rca-context-v1';
  const toolPlan = {
    task_type: 'pod_restart_rca',
    target: LOCAL_TARGET,
    execution_policy: {
      mode: 'controlled_execution',
      mutations_enabled: true,
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
      {
        step: 3,
        adapter: 'AI Gateway',
        tool: 'gateway_pending_action_plan_lookup',
        verb: 'get',
        purpose: '승인 가능한 Action Plan 확인',
      },
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
    { label: 'Action Plan', status: 'ok', value: '가능' },
  ];
  const answer = [
    '## 요약',
    '`로컬 시뮬레이션 응답`입니다.',
    '실제 OLS/클러스터 분석 결과가 아니라 5174 fixture의 고정 테스트 데이터입니다.',
    '테스트 대상: CrashLoopBackOff 복구 fixture',
    '현재 상태: 로컬 fixture에 CrashLoopBackOff가 주입되어 있습니다.',
    '대기 중인 계획: `plan-local-crashloop` Action Plan',
    '',
    '## 확인한 근거',
    '- `KubePodNotReady` 경고가 firing 상태입니다.',
    '- 대상 Deployment 1개가 `0/1 ready` 상태입니다.',
    '- Gateway 상태는 local-only fixture, mutation simulator enabled입니다.',
    '',
    '## 추가 확인',
    '- 실제 운영 판단에서는 Pod 로그와 이벤트가 필요합니다.',
    '- 최근 배포 변경 이력을 확인해야 원인을 확정할 수 있습니다.',
    '- 실행 전 local-only 시뮬레이션인지 다시 확인해야 합니다.',
    '',
    '## Action Plan',
    '- 승인 계획: `plan-local-crashloop`',
    '- 조치: Deployment rollout restart',
    '- 검증: 재시작 후 ready replica가 `1/1`로 회복되는지 확인',
    '- 롤백: 필요 시 직전 ReplicaSet으로 rollout undo',
  ].join('\n');

  sse(res, {
    type: 'run_status',
    runId,
    stage: 'started',
    message: '로컬 fixture 응답 렌더링을 시작했습니다.',
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
    message: '로컬 fixture 응답, 근거 연결, Action Plan 확인을 완료했습니다.',
  });
  sse(res, { type: 'end', conversationId: `local-fixture-${Date.now()}` });
  res.end();
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
      actionProposals: [localProposalRecord()],
      sealedActionPlans: [localSealedPlanRecord()],
      approvalDecisions: Array.from(LOCAL_APPROVALS.values()),
      executionRecords: Array.from(LOCAL_EXECUTIONS.values()),
      auditRecords: [localAuditRecord()],
      diagnosticRequests: [],
      chatTranscripts: [],
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

const makeApprovalRecord = (approvalScope = 'single-target') => {
  const approvalId = `approval-local-${Date.now()}`;
  const approvedAt = nowIso();
  const record = {
    schemaVersion: 'v1',
    apiVersion: 'aiops.komsco/v1',
    kind: 'ApprovalDecisionRecord',
    metadata: { name: approvalId, createdAt: approvedAt },
    spec: {
      approvalDecision: {
        approvalId,
        planDigest: LOCAL_PLAN_DIGEST,
        status: 'approved',
        approver: LOCAL_SUBJECT,
        approvedAt,
        expiresAt: new Date(Date.now() + 5 * 60 * 1000).toISOString(),
        approvalScope,
        target: LOCAL_TARGET,
        authorizationAttestationRef: {
          attestationId: `attestation-${approvalId}`,
          attestationDigest: `sha256:${approvalId}`,
          bearerAttestationStored: false,
          issuer: 'local-fixture',
          audience: 'aiops-action-executor',
        },
        kubernetesAuthorization: {
          apiGroup: 'apps',
          resource: 'deployments',
          subresource: '',
          verb: 'patch',
          ssarDecision: 'allowed',
          evaluatedAt: approvedAt,
          review: { allowed: true, reason: 'local fixture approval' },
        },
        action: localAction(),
        ...(approvalScope === 'lab-auto-unrestricted'
          ? {
              decidedBy: 'auto-policy',
              decisionPolicy: {
                toolName: 'rollout_restart_deployment',
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

const makeExecutionRecord = (approvalId) => {
  const executionId = `execution-local-${Date.now()}`;
  const createdAt = nowIso();
  const record = {
    schemaVersion: 'v1',
    apiVersion: 'aiops.komsco/v1',
    kind: 'ExecutionRecord',
    metadata: { name: executionId, createdAt },
    spec: {
      executionId,
      approvalId,
      planId: 'plan-local-crashloop',
      planDigest: LOCAL_PLAN_DIGEST,
      executionGrantRef: {
        grantId: `grant-${executionId}`,
        grantDigest: `sha256:${executionId}`,
        bearerGrantStored: false,
      },
      mutationOutcome: {
        status: 'mutation_succeeded',
        reason: 'local simulator accepted rollout restart',
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
      executionAuthorization: { allowed: true, reason: 'local fixture execution' },
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
    await readJsonBody(req);
    const record = localSealedPlanRecord();
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
    const proposal = localProposalRecord();
    const plan = localSealedPlanRecord();
    json(res, 200, {
      apiVersion: 'aiops.komsco/v1',
      kind: 'ActionCandidatePlan',
      metadata: { name: 'candidate-plan-local-crashloop', createdAt: nowIso() },
      spec: {
        candidateId: body.candidateId || 'candidate-local-crashloop-restart',
        plan: {
          apiVersion: 'aiops.komsco/v1',
          kind: 'SealedActionPlan',
          metadata: plan.metadata,
          spec: plan.spec,
        },
        planDigest: LOCAL_PLAN_DIGEST,
        planId: plan.metadata.name,
        proposal: {
          apiVersion: 'aiops.komsco/v1',
          kind: 'ActionProposal',
          metadata: proposal.metadata,
          spec: proposal.spec,
        },
        proposalId: proposal.metadata.name,
        status: 'planned',
        target: LOCAL_TARGET,
        title: 'CrashLoopBackOff Deployment 재시작',
      },
    });
    return;
  }
  if (url.pathname === '/v1/actions/approvals' && req.method === 'POST') {
    const body = await readJsonBody(req);
    if (body.expectedPlanDigest && body.expectedPlanDigest !== LOCAL_PLAN_DIGEST) {
      json(res, 409, { detail: 'expectedPlanDigest does not match the sealed plan' });
      return;
    }
    const record = makeApprovalRecord(body.approvalScope || 'single-target');
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
    if (body.expectedPlanDigest && body.expectedPlanDigest !== LOCAL_PLAN_DIGEST) {
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
          planDigest: LOCAL_PLAN_DIGEST,
          status: 'rejected',
          approver: LOCAL_SUBJECT,
          rejectedAt,
          reason: body.reason || 'operator rejected the proposed action',
          approvalScope: 'single-target',
          target: LOCAL_TARGET,
          action: localAction(),
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
    if (body.expectedPlanDigest && body.expectedPlanDigest !== LOCAL_PLAN_DIGEST) {
      json(res, 409, { detail: 'Execution request is stale for this sealed plan' });
      return;
    }
    const approvalId = body.approvalId || makeApprovalRecord('lab-auto-unrestricted').metadata.name;
    const record = makeExecutionRecord(approvalId);
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
