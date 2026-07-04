#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const WebSocket = require('ws');

const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9333');
const targetUrl = process.env.AIOPS_CONSOLE_URL || 'http://localhost:9000/dashboards/aiops';
const screenshotPath =
  process.env.AIOPS_SCREENSHOT_PATH || '/tmp/v027-expanded-assistant-rail.png';
const viewportSize = process.env.AIOPS_VIEWPORT_SIZE || '1440,900';
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-chrome-'));
let chromeProcess;
let chromeWebSocket;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const clusterSummaryUrl =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/cluster/summary';
const aiopsStatusUrl =
  '/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status';

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

const launchChrome = () =>
  spawn(
    chrome,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      `--window-size=${viewportSize}`,
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      targetUrl,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

const main = async () => {
  const proc = launchChrome();
  chromeProcess = proc;
  let stderr = '';
  proc.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });

  const version = await waitForJson(`http://127.0.0.1:${port}/json/version`);
  const targets = await waitForJson(`http://127.0.0.1:${port}/json/list`);
  const target = targets.find((item) => item.type === 'page') || targets[0];
  if (!target?.webSocketDebuggerUrl) {
    throw new Error(`No page websocket target. Chrome stderr: ${stderr.slice(0, 1000)}`);
  }

  const ws = new WebSocket(target.webSocketDebuggerUrl);
  chromeWebSocket = ws;
  await new Promise((resolve, reject) => {
    ws.once('open', resolve);
    ws.once('error', reject);
  });

  let nextId = 1;
  const pending = new Map();
  ws.on('message', (raw) => {
    const msg = JSON.parse(String(raw));
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

  const send = (method, params = {}) => {
    const id = nextId++;
    ws.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  };

  const evaluate = async (expression) => {
    const result = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
      timeout: 15000,
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
      await sleep(750);
    }
    throw new Error(`Timed out waiting for ${label}. Last=${JSON.stringify(last)}`);
  };

  await send('Page.enable');
  await send('Runtime.enable');

  await poll(
    `(() => {
      const body = document.body;
      const doc = document.documentElement;
      const text = body?.innerText || '';
      return {
        ready: Boolean(body && doc && document.querySelector('[aria-label="Open Cywell AI"]')) &&
          text.includes('AIOps for OCP / 대시보드'),
        hasOverlayFrame: Boolean(document.querySelector('#webpack-dev-server-client-overlay')),
        text: text.slice(0, 800),
        width: doc?.clientWidth || 0,
        scrollWidth: doc?.scrollWidth || 0
      };
    })()`,
    (value) => value && value.ready,
    'dashboard and FAB',
  );

  await evaluate(
    `(() => { document.querySelector('[aria-label="Open Cywell AI"]')?.click(); return true; })()`,
  );
  await poll(
    `(() => ({
      hasSurface: Boolean(document.querySelector('[aria-label="Cywell AI assistant"]')),
      text: (document.body?.innerText || '').slice(0, 500)
    }))()`,
    (value) => value && value.hasSurface,
    'assistant surface',
  );

  await evaluate(
    `(() => { document.querySelector('[aria-label="Open full screen"]')?.click(); return true; })()`,
  );
  await poll(
    `(() => ({
      full: Boolean(document.querySelector('.komsco-ai__surface--fullscreen')),
      rail: Boolean(document.querySelector('.komsco-ai__insight-rail')),
      text: (document.body?.innerText || '').slice(0, 600)
    }))()`,
    (value) => value && value.full && value.rail,
    'fullscreen rail',
  );
  await poll(
    `(async () => {
      const railText = document.querySelector('.komsco-ai__insight-rail')?.innerText || '';
      const bodyText = document.body?.innerText || '';
      const requestJson = async (url) => {
        const response = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!response.ok) {
          throw new Error(url + ' -> ' + response.status);
        }
        return response.json();
      };
      let summary;
      let status;
      try {
        [summary, status] = await Promise.all([
          requestJson('${clusterSummaryUrl}'),
          requestJson('${aiopsStatusUrl}')
        ]);
      } catch (error) {
        return {
          ready: false,
          error: String(error && error.message ? error.message : error),
          railText: railText.slice(0, 1200)
        };
      }
      const records = status?.spec?.records || {};
      const actionRecordCount =
        (records.actionProposals?.length || 0) +
        (records.sealedActionPlans?.length || 0) +
        (records.approvalDecisions?.length || 0) +
        (records.executionRecords?.length || 0);
      const diagnosticRecordCount = records.diagnosticRequests?.length || 0;
      const liveSignals = {
        apiHost: summary.apiUrl ? railText.includes(summary.apiUrl) : bodyText.includes('api.ocp.cywell.server'),
        healthScore:
          railText.includes(String(summary.healthScore)) &&
          railText.includes('/ 100'),
        node:
          railText.includes('Node ' + summary.nodes.ready + '/' + summary.nodes.total) &&
          railText.includes(summary.nodes.ready + '/' + summary.nodes.total + ' Ready'),
        operator:
          railText.includes('Operator ' + summary.operators.available + '/' + summary.operators.total) &&
          railText.includes('정상 Operator ' + summary.operators.available + '/' + summary.operators.total),
        firstNode:
          !summary.nodes.items?.[0]?.name || railText.includes(summary.nodes.items[0].name),
        version:
          !summary.version?.version || railText.includes(summary.version.version),
        diagnosticRecords:
          railText.includes('최근 진단') && railText.includes(diagnosticRecordCount + '건'),
        actionRecords:
          railText.includes('승인·실행') && railText.includes(actionRecordCount + '건')
      };
      return {
        ready: Object.values(liveSignals).every(Boolean),
        liveSignals,
        apiSnapshot: {
          apiUrl: summary.apiUrl,
          healthScore: summary.healthScore,
          nodeReady: summary.nodes.ready,
          nodeTotal: summary.nodes.total,
          operatorAvailable: summary.operators.available,
          operatorTotal: summary.operators.total,
          actionRecordCount,
          diagnosticRecordCount,
          version: summary.version?.version,
          firstNodeName: summary.nodes.items?.[0]?.name
        },
        railText: railText.slice(0, 1200)
      };
    })()`,
    (value) => value && value.ready,
    'fullscreen rail data matched to gateway API',
    90000,
  );

  await evaluate(
    `(() => { document.querySelector('.komsco-ai__sidebar-toggle')?.click(); return true; })()`,
  );
  await poll(
    `(() => ({
      historyOpen: Boolean(document.querySelector('.komsco-ai__surface--history-open')),
      history: Boolean(document.querySelector('.komsco-ai__history-sidebar')),
      panel: Boolean(document.querySelector('.komsco-ai__panel--fullscreen')),
      rail: Boolean(document.querySelector('.komsco-ai__insight-rail'))
    }))()`,
    (value) => value && value.historyOpen && value.history && value.panel && value.rail,
    'fullscreen history sidebar',
  );

  const metrics = await evaluate(
    `(async () => {
      const rectOf = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          x: Math.round(r.x),
          y: Math.round(r.y),
          width: Math.round(r.width),
          height: Math.round(r.height)
        };
      };
      const overflowOf = (el) => el ? ({
        scrollWidth: el.scrollWidth,
        clientWidth: el.clientWidth,
        ok: el.scrollWidth <= el.clientWidth + 1
      }) : null;
      const doc = document.documentElement;
      const body = document.body;
      const text = body?.innerText || '';
      const rail = document.querySelector('.komsco-ai__insight-rail');
      const railText = rail?.innerText || '';
      const surface = document.querySelector('.komsco-ai__surface--fullscreen');
      const history = document.querySelector('.komsco-ai__history-sidebar');
      const workspace = document.querySelector('.komsco-ai__workspace');
      const panel = document.querySelector('.komsco-ai__panel--fullscreen');
      const header = document.querySelector('.komsco-ai__header');
      const headerStatus = document.querySelector('.komsco-ai__header-status');
      const requestJson = async (url) => {
        const response = await fetch(url, { headers: { Accept: 'application/json' } });
        if (!response.ok) {
          throw new Error(url + ' -> ' + response.status);
        }
        return response.json();
      };
      const [summary, status] = await Promise.all([
        requestJson('${clusterSummaryUrl}'),
        requestJson('${aiopsStatusUrl}')
      ]);
      const records = status?.spec?.records || {};
      const actionRecordCount =
        (records.actionProposals?.length || 0) +
        (records.sealedActionPlans?.length || 0) +
        (records.approvalDecisions?.length || 0) +
        (records.executionRecords?.length || 0);
      const diagnosticRecordCount = records.diagnosticRequests?.length || 0;
      const surfaceRect = surface?.getBoundingClientRect();
      const historyRect = history?.getBoundingClientRect();
      const panelRect = panel?.getBoundingClientRect();
      const headerRect = header?.getBoundingClientRect();
      const headerStatusRect = headerStatus?.getBoundingClientRect();
      const headerLineClearance =
        headerRect && headerStatusRect ? Math.round(headerRect.bottom - headerStatusRect.bottom) : null;
      const historyGap =
        historyRect && panelRect ? Math.round(panelRect.left - historyRect.right) : null;
      const historyFlushLeft =
        surfaceRect && historyRect ? Math.abs(Math.round(historyRect.left - surfaceRect.left)) <= 1 : false;
      return {
        url: location.href,
        title: document.title,
        hasOverlayFrame: Boolean(document.querySelector('#webpack-dev-server-client-overlay')),
        apiSnapshot: {
          apiUrl: summary.apiUrl,
          healthScore: summary.healthScore,
          nodeReady: summary.nodes.ready,
          nodeTotal: summary.nodes.total,
          operatorAvailable: summary.operators.available,
          operatorTotal: summary.operators.total,
          actionRecordCount,
          diagnosticRecordCount,
          version: summary.version?.version,
          firstNodeName: summary.nodes.items?.[0]?.name
        },
        liveSignals: {
          apiHost: summary.apiUrl ? railText.includes(summary.apiUrl) : text.includes('api.ocp.cywell.server'),
          healthScore:
            railText.includes(String(summary.healthScore)) &&
            railText.includes('/ 100'),
          node:
            railText.includes('Node ' + summary.nodes.ready + '/' + summary.nodes.total) &&
            railText.includes(summary.nodes.ready + '/' + summary.nodes.total + ' Ready'),
          operator:
            railText.includes('Operator ' + summary.operators.available + '/' + summary.operators.total) &&
            railText.includes('정상 Operator ' + summary.operators.available + '/' + summary.operators.total),
          firstNode:
            !summary.nodes.items?.[0]?.name || railText.includes(summary.nodes.items[0].name),
          version:
            !summary.version?.version || railText.includes(summary.version.version),
          diagnosticRecords:
            railText.includes('최근 진단') && railText.includes(diagnosticRecordCount + '건'),
          actionRecords:
            railText.includes('승인·실행') && railText.includes(actionRecordCount + '건')
        },
        rects: {
          surface: rectOf(surface),
          history: rectOf(history),
          panel: rectOf(panel),
          header: rectOf(header),
          headerStatus: rectOf(headerStatus),
          workspace: rectOf(workspace),
          rail: rectOf(rail)
        },
        layoutChecks: {
          fullscreenHistoryOpen: Boolean(document.querySelector('.komsco-ai__surface--fullscreen.komsco-ai__surface--history-open')),
          historyFlushLeft,
          historyTouchesPanel: historyGap !== null && Math.abs(historyGap) <= 1,
          historyGap,
          headerLineClearance,
          headerLineHasRoom: headerLineClearance !== null && headerLineClearance >= 4
        },
        overflow: {
          document: {
            scrollWidth: doc?.scrollWidth || 0,
            clientWidth: doc?.clientWidth || 0,
            ok: Boolean(doc) && doc.scrollWidth <= doc.clientWidth + 1
          },
          body: {
            scrollWidth: body?.scrollWidth || 0,
            clientWidth: body?.clientWidth || 0,
            ok: Boolean(body) && body.scrollWidth <= body.clientWidth + 1
          },
          surface: overflowOf(surface),
          workspace: overflowOf(workspace),
          rail: overflowOf(rail)
        },
        railText: railText.slice(0, 1800),
        oldLabelsPresent: /KOMSCO AI AGENT|OpenShift Lightspeed/.test(text),
        rawInternalReasonPresent: /Action Executor URL not configured|mutation gate disabled|unrestricted command gate|evidence-check UI blocks|Conflict/.test(text)
      };
    })()`,
  );

  const allLiveSignals = Object.values(metrics.liveSignals).every(Boolean);
  const allOverflowOk = Object.values(metrics.overflow).every((value) => value?.ok === true);
  const allLayoutOk =
    metrics.layoutChecks.fullscreenHistoryOpen &&
    metrics.layoutChecks.historyFlushLeft &&
    metrics.layoutChecks.historyTouchesPanel &&
    metrics.layoutChecks.headerLineHasRoom;
  if (
    !allLiveSignals ||
    !allOverflowOk ||
    !allLayoutOk ||
    metrics.oldLabelsPresent ||
    metrics.rawInternalReasonPresent ||
    metrics.hasOverlayFrame
  ) {
    throw new Error(
      JSON.stringify(
        {
          allLiveSignals,
          allOverflowOk,
          allLayoutOk,
          hasOverlayFrame: metrics.hasOverlayFrame,
          oldLabelsPresent: metrics.oldLabelsPresent,
          metrics,
        },
        null,
        2,
      ),
    );
  }

  const shot = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  fs.writeFileSync(screenshotPath, Buffer.from(shot.data, 'base64'));
  ws.close();
  proc.kill('SIGTERM');

  console.log(
    JSON.stringify(
      {
        chrome: version.Browser,
        screenshotPath,
        metrics,
      },
      null,
      2,
    ),
  );
};

main().catch((error) => {
  try {
    chromeWebSocket?.close();
  } catch (_closeError) {
    // best effort cleanup
  }
  try {
    chromeProcess?.kill('SIGTERM');
  } catch (_killError) {
    // best effort cleanup
  }
  console.error(error.stack || error.message || String(error));
  process.exitCode = 1;
});
