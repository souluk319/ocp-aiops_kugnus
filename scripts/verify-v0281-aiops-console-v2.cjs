#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const requireFromPlugin = require('module').createRequire(
  path.join(root, 'komsco-ai-console-plugin', 'package.json'),
);
let WebSocket;
try {
  WebSocket = require('ws');
} catch (_error) {
  WebSocket = requireFromPlugin('ws');
}

const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9362');
const baseUrl =
  process.env.AIOPS_V2_URL || 'http://localhost:5174/dashboards/aiops/v2';
const screenshotDir = process.env.AIOPS_SCREENSHOT_DIR || '/tmp';
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-v0281-v2-'));

const routes = [
  { view: 'dashboard', title: '대시보드', requiredText: ['대시보드', '클러스터 상태'] },
  { view: 'executions', title: '실행 기록', requiredText: ['실행 기록', '활성 실행'] },
  { view: 'reports', title: '보고서', requiredText: ['보고서', '보고서 작성'] },
  { view: 'rca', title: 'RCA 센터', requiredText: ['RCA 센터', '근거'] },
  { view: 'service-map', title: '서비스 맵', requiredText: ['서비스 맵', '클러스터 토폴로지'] },
];

const themes = ['dark', 'light'];
const leakTerms = [
  'ActionProposalRecord',
  'SealedActionPlanRecord',
  'ApprovalDecisionRecord',
  'ExecutionRecord',
  'api.local-aiops.invalid',
  '4.20-local',
  'komsco-ai-local',
  'local-aiops-fixture-ledger',
  'local-only AIOps fixture',
  'local simulator',
  'local fixture',
  'local-admin',
  'mutation_succeeded',
  'run-local-fixture',
  'served local-only',
  'fixture is not ready',
  '로컬 화면 설정',
  '시뮬레이션',
];

let chromeProcess;
let chromeWebSocket;
let nextId = 1;
const pending = new Map();

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
      '--window-size=1280,720',
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      url,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

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

const navigate = async (url) => {
  await send('Page.navigate', { url });
  return poll(
    `(() => ({
      ready: document.readyState === 'complete' && Boolean(document.body?.innerText?.trim()),
      hasOverlayFrame: Boolean(document.querySelector('#webpack-dev-server-client-overlay')),
      text: document.body?.innerText?.slice(0, 600) || ''
    }))()`,
    (value) => value?.ready && !value.hasOverlayFrame,
    `v2 page ready ${url}`,
    90000,
  );
};

const captureScreenshot = async (theme, view) => {
  const file = path.join(screenshotDir, `v0281-v2-${theme}-${view}.png`);
  const result = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  fs.writeFileSync(file, Buffer.from(result.data, 'base64'));
  return file;
};

const routeUrl = (view) => `${baseUrl}#v2/${view}`;

const verifyRoute = async (theme, route) => {
  await navigate(routeUrl(route.view));
  await evaluate(`localStorage.setItem('aiops-v2-theme', ${JSON.stringify(theme)})`);
  await send('Page.reload', { ignoreCache: true });
  await poll(
    `(() => ({
      ready: document.readyState === 'complete' && Boolean(document.body?.innerText?.trim()),
      hasOverlayFrame: Boolean(document.querySelector('#webpack-dev-server-client-overlay')),
      text: document.body?.innerText?.slice(0, 600) || ''
    }))()`,
    (value) => value?.ready && !value.hasOverlayFrame,
    `v2 page reloaded ${route.view} ${theme}`,
    90000,
  );
  await sleep(800);

  const metrics = await evaluate(`(() => {
    const text = document.body?.innerText || '';
    const doc = document.documentElement;
    const body = document.body;
    const leakTerms = ${JSON.stringify(leakTerms)};
    const requiredText = ${JSON.stringify(route.requiredText)};
    const root = document.querySelector('.v2-root');
    const controls = Array.from(document.querySelectorAll(
      'button, .v2-chip, .v2-pill, .v2-sev, .v2-tab, .v2-nav__item, .v2-stat, .v2-mode-pill, .v2-theme-option'
    ));
    const overflowingControls = controls
      .filter((el) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
      .map((el) => ({
        className: String(el.className),
        label: (el.getAttribute('aria-label') || el.textContent || '').replace(/\\s+/g, ' ').trim().slice(0, 140),
        size: { ch: el.clientHeight, cw: el.clientWidth, sh: el.scrollHeight, sw: el.scrollWidth }
      }));
    const leaks = leakTerms.filter((term) => text.toLowerCase().includes(term.toLowerCase()));
    const leakSnippets = leaks.map((term) => {
      const index = text.toLowerCase().indexOf(term.toLowerCase());
      return index < 0 ? term : text.slice(Math.max(0, index - 90), index + term.length + 140);
    });
    return {
      bodyOverflow: body.scrollWidth - body.clientWidth,
      documentOverflow: doc.scrollWidth - doc.clientWidth,
      leaks,
      leakSnippets,
      missingText: requiredText.filter((item) => !text.includes(item)),
      rootTheme: root?.getAttribute('data-v2-theme') || '',
      textSample: text.slice(0, 1400),
      title: document.querySelector('.v2-topbar h1')?.textContent?.trim() || '',
      overflowingControls,
      url: location.href,
      viewport: { height: window.innerHeight, width: window.innerWidth }
    };
  })()`);

  const screenshot = await captureScreenshot(theme, route.view);
  const pass =
    metrics.rootTheme === theme &&
    metrics.missingText.length === 0 &&
    metrics.leaks.length === 0 &&
    metrics.overflowingControls.length === 0 &&
    metrics.bodyOverflow <= 1 &&
    metrics.documentOverflow <= 1;

  return { ...metrics, pass, screenshot, theme, view: route.view };
};

const main = async () => {
  fs.mkdirSync(screenshotDir, { recursive: true });
  chromeProcess = launchChrome(routeUrl(routes[0].view));
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

  await send('Page.enable');
  await send('Runtime.enable');

  const results = [];
  for (const theme of themes) {
    for (const route of routes) {
      results.push(await verifyRoute(theme, route));
    }
  }

  const failed = results.filter((result) => !result.pass);
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

main()
  .catch((error) => {
    console.error(error.stack || error.message || String(error));
    process.exitCode = 1;
  })
  .finally(() => {
    try {
      chromeWebSocket?.close();
    } catch (_error) {
      // best effort cleanup
    }
    try {
      chromeProcess?.kill('SIGTERM');
    } catch (_error) {
      // best effort cleanup
    }
  });
