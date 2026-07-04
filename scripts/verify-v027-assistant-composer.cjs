#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const WebSocket = require('ws');

const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9354');
const targetUrl = process.env.AIOPS_CONSOLE_URL || 'http://localhost:9000/dashboards/aiops';
const screenshotPath =
  process.env.AIOPS_SCREENSHOT_PATH || '/tmp/v027-assistant-composer.png';
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-composer-'));
let chromeProcess;
let chromeWebSocket;

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const fetchJson = async (url) => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} -> ${response.status}`);
  }
  return response.json();
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
      '--window-size=1440,900',
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      targetUrl,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

const main = async () => {
  chromeProcess = launchChrome();
  let stderr = '';
  chromeProcess.stderr.on('data', (chunk) => {
    stderr += chunk.toString();
  });

  await waitForJson(`http://127.0.0.1:${port}/json/version`);
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
    const message = JSON.parse(String(raw));
    if (!message.id || !pending.has(message.id)) {
      return;
    }
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) {
      reject(new Error(JSON.stringify(message.error)));
    } else {
      resolve(message.result);
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
      await sleep(500);
    }
    throw new Error(`Timed out waiting for ${label}. Last=${JSON.stringify(last)}`);
  };

  await send('Page.enable');
  await send('Runtime.enable');

  await poll(
    `(() => ({
      ready: Boolean(document.querySelector('[aria-label="Open Cywell AI"]')) &&
        (document.body?.innerText || '').includes('AIOps for OCP / 대시보드'),
      overlay: Boolean(document.querySelector('#webpack-dev-server-client-overlay'))
    }))()`,
    (value) => value?.ready && !value.overlay,
    'dashboard and assistant FAB',
  );

  await evaluate(`document.querySelector('[aria-label="Open Cywell AI"]')?.click()`);
  await poll(
    `(() => ({
      surface: Boolean(document.querySelector('[aria-label="Cywell AI assistant"]')),
      composer: Boolean(document.querySelector('.komsco-ai__composer'))
    }))()`,
    (value) => value?.surface && value?.composer,
    'assistant composer',
  );

  await evaluate(`document.querySelector('.komsco-ai__quick-menu-trigger')?.click()`);
  const quickMenu = await poll(
    `(() => {
      const panel = document.querySelector('.komsco-ai__quick-menu-panel');
      const surface = document.querySelector('[aria-label="Cywell AI assistant"]');
      if (!panel || !surface) return { open: false };
      const rect = panel.getBoundingClientRect();
      const surfaceRect = surface.getBoundingClientRect();
      const items = Array.from(panel.querySelectorAll('.komsco-ai__quick-menu-item'));
      return {
        open: true,
        itemCount: items.length,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height, bottom: rect.bottom },
        surfaceRect: { x: surfaceRect.x, y: surfaceRect.y, width: surfaceRect.width, height: surfaceRect.height, bottom: surfaceRect.bottom },
        visibleInViewport:
          rect.width > 120 &&
          rect.height > 120 &&
          rect.top >= 0 &&
          rect.left >= 0 &&
          rect.right <= window.innerWidth &&
          rect.bottom <= window.innerHeight,
        visibleAboveComposer: rect.bottom < surfaceRect.bottom - 72,
        overflow: Math.max(0, panel.scrollWidth - panel.clientWidth),
        text: panel.innerText.slice(0, 500)
      };
    })()`,
    (value) =>
      value?.open &&
      value.itemCount >= 4 &&
      value.visibleInViewport &&
      value.visibleAboveComposer &&
      value.overflow === 0,
    'quick prompt menu visible without clipping',
  );

  await evaluate(`document.querySelector('.komsco-ai__task-mode-button')?.click()`);
  const taskModeMenu = await poll(
    `(() => {
      const panel = document.querySelector('.komsco-ai__task-mode-menu');
      if (!panel) return { open: false };
      const rect = panel.getBoundingClientRect();
      const options = Array.from(panel.querySelectorAll('.komsco-ai__task-mode-option'));
      return {
        open: true,
        optionCount: options.length,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height, bottom: rect.bottom },
        visibleInViewport:
          rect.width > 120 &&
          rect.height > 60 &&
          rect.top >= 0 &&
          rect.left >= 0 &&
          rect.right <= window.innerWidth &&
          rect.bottom <= window.innerHeight,
        overflow: Math.max(0, panel.scrollWidth - panel.clientWidth),
        text: panel.innerText.slice(0, 300)
      };
    })()`,
    (value) =>
      value?.open &&
      value.optionCount >= 2 &&
      value.visibleInViewport &&
      value.overflow === 0,
    'task mode menu visible without clipping',
  );

  const screenshot = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  fs.writeFileSync(screenshotPath, Buffer.from(screenshot.data, 'base64'));

  console.log(
    JSON.stringify(
      {
        chrome: (await waitForJson(`http://127.0.0.1:${port}/json/version`)).Browser,
        passed: true,
        quickMenu,
        screenshotPath,
        taskModeMenu,
      },
      null,
      2,
    ),
  );
};

main()
  .catch((error) => {
    console.error(error.stack || error.message);
    process.exitCode = 1;
  })
  .finally(async () => {
    try {
      chromeWebSocket?.close();
    } catch (_error) {
      // no-op
    }
    if (chromeProcess && !chromeProcess.killed) {
      chromeProcess.kill('SIGTERM');
    }
    await sleep(100);
    fs.rmSync(userDataDir, { force: true, recursive: true });
  });
