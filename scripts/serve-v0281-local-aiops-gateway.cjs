#!/usr/bin/env node
'use strict';

const http = require('http');
const fs = require('fs');
const path = require('path');

const host = process.env.AIOPS_LOCAL_FIXTURE_HOST || '127.0.0.1';
const port = Number(process.env.AIOPS_LOCAL_FIXTURE_PORT || 18080);
const servePortal = process.env.AIOPS_LOCAL_SERVE_PORTAL === '1';
const repoRoot = path.resolve(__dirname, '..');
const portalDist = path.join(repoRoot, 'komsco-ai-portal', 'dist');
const docsRoot = path.join(repoRoot, 'docs', 'Ver.0.2.8.1');

const nowIso = () => new Date().toISOString();

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
    records: {
      actionProposals: [
        {
          kind: 'ActionProposal',
          metadata: { name: 'proposal-local-crashloop', createdAt: nowIso() },
          spec: {
            title: 'CrashLoopBackOff 복구 조치 후보',
            target: 'komsco-ai-local/deployment/aiops-scenario-crashloop',
            status: 'approval_required',
          },
        },
      ],
      sealedActionPlans: [
        {
          kind: 'SealedActionPlan',
          metadata: { name: 'plan-local-crashloop', createdAt: nowIso() },
          spec: {
            title: '승인 가능한 Action Plan',
            target: 'komsco-ai-local/deployment/aiops-scenario-crashloop',
            action: 'rollout_restart_deployment',
            impact: 'local simulator only',
          },
        },
      ],
      approvalDecisions: [],
      executionRecords: [
        {
          kind: 'ExecutionRecord',
          metadata: { name: 'execution-local-simulated', createdAt: nowIso() },
          spec: {
            result: 'mutation simulated',
            verification: 'passed',
            companyMutationExecuted: false,
          },
        },
      ],
      auditRecords: [
        {
          kind: 'AuditRecord',
          metadata: { name: 'audit-local-fixture', createdAt: nowIso() },
          spec: {
            actor: 'local-fixture-gateway',
            action: 'served local-only AIOps fixture',
            companyMutationExecuted: false,
          },
        },
      ],
      diagnosticRequests: [],
      chatTranscripts: [],
    },
  },
});

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

const server = http.createServer((req, res) => {
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
  if (url.pathname === '/v1/cluster/summary') {
    json(res, 200, clusterSummary());
    return;
  }
  if (url.pathname === '/v1/aiops/status') {
    json(res, 200, aiopsStatus());
    return;
  }
  if (url.pathname === '/v1/aiops/events') {
    json(res, 200, eventFeed());
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
