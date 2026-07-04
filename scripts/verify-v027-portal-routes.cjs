#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const WebSocket = require('ws');

const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9347');
const baseUrl = process.env.AIOPS_PORTAL_BASE_URL || 'http://localhost:5174';
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-portal-routes-'));

const routes = [
  {
    label: '대시보드',
    path: '/dashboards/aiops',
    requiredText: ['AIOps for OCP', '대시보드', '시스템 건강도'],
  },
  {
    label: 'RCA 센터',
    path: '/dashboards/aiops/audit',
    requiredText: ['RCA 센터', 'RCA-', '원본 증거'],
  },
  {
    label: '서비스 맵',
    path: '/dashboards/aiops/service-map',
    requiredText: ['서비스 맵', '클러스터 토폴로지'],
  },
  {
    label: '클러스터 리소스',
    path: '/dashboards/aiops/endpoints',
    requiredText: ['클러스터 리소스', '리소스 그룹 분포'],
  },
  {
    label: '알림 & 이벤트',
    path: '/dashboards/aiops/alerts',
    requiredText: ['알림 & 이벤트', '이벤트 인박스'],
  },
  {
    label: '위키 문서 관리',
    path: '/dashboards/aiops/docs',
    requiredText: ['위키 문서 관리', 'Runbook'],
  },
  {
    label: '보고서',
    path: '/dashboards/aiops/reports',
    requiredText: ['보고서', '보고서 유형'],
  },
];

let chromeProcess;
let chromeWebSocket;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

const launchChrome = (url) =>
  spawn(
    chrome,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--window-size=1440,900',
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      url,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

const main = async () => {
  chromeProcess = launchChrome(`${baseUrl}${routes[0].path}`);
  let stderr = '';
  chromeProcess.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });

  const version = await waitForJson(`http://127.0.0.1:${port}/json/version`);
  const targets = await waitForJson(`http://127.0.0.1:${port}/json/list`);
  const target = targets.find((item) => item.type === 'page') || targets[0];
  if (!target?.webSocketDebuggerUrl) {
    throw new Error(`No page websocket target. Chrome stderr: ${stderr.slice(0, 1000)}`);
  }

  chromeWebSocket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    chromeWebSocket.once('open', resolve);
    chromeWebSocket.once('error', reject);
  });

  let nextId = 1;
  const pending = new Map();
  chromeWebSocket.on('message', (raw) => {
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
    chromeWebSocket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  };

  const evaluate = async (expression) => {
    const result = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
      timeout: 20000,
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

  await send('Page.enable');
  await send('Runtime.enable');

  const results = [];
  for (const route of routes) {
    const url = `${baseUrl}${route.path}`;
    await send('Page.navigate', { url });
    await poll(
      `(() => ({
        ready: document.readyState === 'complete' && Boolean(document.body?.innerText?.trim()),
        text: document.body?.innerText?.slice(0, 800) || '',
        hasOverlayFrame: Boolean(document.querySelector('#webpack-dev-server-client-overlay'))
      }))()`,
      (value) => value?.ready && !value.hasOverlayFrame,
      `portal route ${route.path}`,
      90000,
    );
    await sleep(700);

    const metrics = await evaluate(`(() => {
      const text = document.body?.innerText || '';
      const activeNav = document.querySelector('.portal-nav__item.is-active')?.textContent?.replace(/\\s+/g, ' ').trim() || '';
      const doc = document.documentElement;
      const body = document.body;
      const requiredText = ${JSON.stringify(route.requiredText)};
      return {
        activeNav,
        bodyOverflow: body.scrollWidth - body.clientWidth,
        documentOverflow: doc.scrollWidth - doc.clientWidth,
        fallbackDashboard: ${JSON.stringify(route.label)} !== '대시보드' && activeNav.includes('대시보드'),
        missingText: requiredText.filter((item) => !text.includes(item)),
        pathname: location.pathname,
        title: document.title,
        textSample: text.slice(0, 500),
      };
    })()`);

    const pass =
      metrics.pathname === route.path &&
      metrics.activeNav.includes(route.label) &&
      metrics.missingText.length === 0 &&
      metrics.bodyOverflow <= 1 &&
      metrics.documentOverflow <= 1 &&
      !metrics.fallbackDashboard;
    results.push({ ...metrics, label: route.label, pass, path: route.path, url });
  }

  const failed = results.filter((result) => !result.pass);
  chromeWebSocket.close();
  chromeProcess.kill('SIGTERM');

  const output = {
    chrome: version.Browser,
    failedCount: failed.length,
    passed: failed.length === 0,
    results,
  };
  console.log(JSON.stringify(output, null, 2));
  if (failed.length > 0) {
    process.exitCode = 1;
  }
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
