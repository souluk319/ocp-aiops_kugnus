#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const WebSocket = require('ws');

const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9345');
const targetUrl = process.env.AIOPS_CONSOLE_URL || 'http://localhost:9000/dashboards/aiops';
const screenshotPath = process.env.AIOPS_SCREENSHOT_PATH || '/tmp/v027-toolplan-chat-ui.png';
const viewportSize = process.env.AIOPS_VIEWPORT_SIZE || '1440,900';
const question =
  process.env.AIOPS_TOOLPLAN_QUESTION ||
  'clusteroperator 상태 확인해줘. 조회 계획과 근거를 같이 보여줘.';
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-chrome-toolplan-'));

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

  await waitForJson(`http://127.0.0.1:${port}/json/version`);
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

  const evaluate = async (expression, timeout = 15000) => {
    const result = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
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
      await sleep(750);
    }
    throw new Error(`Timed out waiting for ${label}. Last=${JSON.stringify(last)}`);
  };

  await send('Page.enable');
  await send('Runtime.enable');

  await poll(
    `(() => {
      const text = document.body?.innerText || '';
      return {
        ready: Boolean(document.querySelector('[aria-label="Open Cywell AI"]')) &&
          text.includes('AIOps for OCP / 대시보드'),
        hasOverlayFrame: Boolean(document.querySelector('#webpack-dev-server-client-overlay')),
        text: text.slice(0, 800)
      };
    })()`,
    (value) => value && value.ready && !value.hasOverlayFrame,
    'dashboard and FAB',
  );

  const gatewayHealth = await evaluate(
    `(async () => {
      const response = await fetch('/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/healthz');
      return { ok: response.ok, status: response.status, text: await response.text() };
    })()`,
  );
  if (!gatewayHealth.ok) {
    throw new Error(`Gateway proxy health failed: ${JSON.stringify(gatewayHealth)}`);
  }

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
    `(() => {
      const surface = document.querySelector('[aria-label="Cywell AI assistant"]');
      const textarea = surface?.querySelector('textarea.komsco-ai__textarea, .komsco-ai__textarea textarea, textarea');
      if (!textarea) return { ok: false, reason: 'textarea missing' };
      const value = ${JSON.stringify(question)};
      textarea.focus();
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
      if (setter) {
        setter.call(textarea, value);
      } else {
        textarea.value = value;
      }
      textarea.dispatchEvent(new InputEvent('input', { bubbles: true, data: value, inputType: 'insertText' }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
      return { ok: true, value: textarea.value };
    })()`,
  );

  await poll(
    `(() => {
      const surface = document.querySelector('[aria-label="Cywell AI assistant"]');
      const send = surface?.querySelector('.komsco-ai__send');
      return {
        ready: Boolean(send) && send.disabled !== true && send.getAttribute('aria-disabled') !== 'true',
        disabled: send?.disabled ?? null,
        ariaDisabled: send?.getAttribute('aria-disabled') || ''
      };
    })()`,
    (value) => value && value.ready,
    'send button enabled',
  );

  await evaluate(
    `(() => { document.querySelector('[aria-label="Cywell AI assistant"] .komsco-ai__send')?.click(); return true; })()`,
  );

  await poll(
    `(() => {
      const footers = [...document.querySelectorAll('.komsco-ai__toolplan-footer')];
      const latest = footers.at(-1);
      const text = latest?.innerText || '';
      return {
        ready: Boolean(latest) &&
          text.includes('조회 계획') &&
          (text.includes('조회 전용') || text.includes('승인 후 실행')) &&
          text.includes('조회 계획 상세보기'),
        footerCount: footers.length,
        text: text.slice(0, 1000)
      };
    })()`,
    (value) => value && value.ready,
    'tool plan footer in assistant answer',
    180000,
  );

  const defaultMetrics = await evaluate(
    `(() => {
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
      const footer = [...document.querySelectorAll('.komsco-ai__toolplan-footer')].at(-1);
      const messageStack = footer?.closest('.komsco-ai__message-stack');
      const answer = messageStack?.querySelector('.komsco-ai__message-content');
      const answerActions = messageStack?.querySelector('.komsco-ai__answer-actions');
      const detail = footer?.querySelector('.komsco-ai__evidence-detail');
      const jsonDetail = footer?.querySelector('.komsco-ai__toolplan-json');
      const footerText = footer?.innerText || '';
      const answerText = answer?.innerText || '';
      const answerActionText = answerActions?.innerText || '';
      return {
        footerText,
        answerText: answerText.slice(0, 1600),
        answerActionText: answerActionText.slice(0, 1200),
        answerActionVisible: Boolean(answerActions && answerActions.getClientRects().length > 0),
        defaultDetailOpen: Boolean(detail?.open),
        defaultJsonOpen: Boolean(jsonDetail?.open),
        footerRect: rectOf(footer),
        answerRect: rectOf(answer),
        answerActionRect: rectOf(answerActions),
        overflow: {
          footer: footer ? footer.scrollWidth - footer.clientWidth : null,
          answer: answer ? answer.scrollWidth - answer.clientWidth : null,
          answerActions: answerActions ? answerActions.scrollWidth - answerActions.clientWidth : null,
          document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          body: document.body.scrollWidth - document.body.clientWidth
        },
        rawVisible:
          /"tool_plan"|"execution_policy"|RCA Context|post_answer|Sealed plan|Conflict|Action Executor URL not configured|mutation gate disabled/.test(footerText)
      };
    })()`,
  );

  if (
    defaultMetrics.defaultDetailOpen ||
    defaultMetrics.defaultJsonOpen ||
    defaultMetrics.answerActionVisible ||
    defaultMetrics.rawVisible ||
    Object.values(defaultMetrics.overflow).some((value) => typeof value === 'number' && value > 1)
  ) {
    throw new Error(`Tool Plan default UI contract failed: ${JSON.stringify(defaultMetrics, null, 2)}`);
  }

  await evaluate(
    `(() => {
      const detail = [...document.querySelectorAll('.komsco-ai__toolplan-footer .komsco-ai__evidence-detail')].at(-1);
      detail?.querySelector('summary')?.click();
      return Boolean(detail);
    })()`,
  );

  await poll(
    `(() => {
      const footer = [...document.querySelectorAll('.komsco-ai__toolplan-footer')].at(-1);
      const detail = footer?.querySelector('.komsco-ai__evidence-detail');
      const text = footer?.innerText || '';
      const steps = footer?.querySelectorAll('.komsco-ai__evidence-query-plan li') || [];
      const jsonDetail = footer?.querySelector('.komsco-ai__toolplan-json');
      return {
        ready: Boolean(detail?.open) &&
          text.includes('Gateway 안전 플래너') &&
          text.includes('Gateway가 정책과 근거 수집 계약') &&
          steps.length > 0 &&
          Boolean(jsonDetail) &&
          jsonDetail.open === false,
        text: text.slice(0, 1400),
        stepCount: steps.length,
        jsonOpen: Boolean(jsonDetail?.open)
      };
    })()`,
    (value) => value && value.ready,
    'opened tool plan details',
  );

  const openedMetrics = await evaluate(
    `(() => {
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
      const footer = [...document.querySelectorAll('.komsco-ai__toolplan-footer')].at(-1);
      const messageStack = footer?.closest('.komsco-ai__message-stack');
      const answer = messageStack?.querySelector('.komsco-ai__message-content');
      const answerActions = messageStack?.querySelector('.komsco-ai__answer-actions');
      const source = footer?.querySelector('.komsco-ai__toolplan-source');
      const steps = [...(footer?.querySelectorAll('.komsco-ai__evidence-query-plan li') || [])];
      const jsonDetail = footer?.querySelector('.komsco-ai__toolplan-json');
      const pre = footer?.querySelector('.komsco-ai__toolplan-json pre');
      const answerActionText = answerActions?.innerText || '';
      return {
        footerText: (footer?.innerText || '').slice(0, 1800),
        answerActionText: answerActionText.slice(0, 1200),
        answerActionVisible: Boolean(answerActions && answerActions.getClientRects().length > 0),
        sourceText: source?.innerText || '',
        stepCount: steps.length,
        jsonOpen: Boolean(jsonDetail?.open),
        jsonPreVisible: Boolean(pre && pre.getClientRects().length > 0),
        rects: {
          footer: rectOf(footer),
          answer: rectOf(answer),
          answerActions: rectOf(answerActions),
          source: rectOf(source)
        },
        overflow: {
          footer: footer ? footer.scrollWidth - footer.clientWidth : null,
          answer: answer ? answer.scrollWidth - answer.clientWidth : null,
          answerActions: answerActions ? answerActions.scrollWidth - answerActions.clientWidth : null,
          source: source ? source.scrollWidth - source.clientWidth : null,
          document: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          body: document.body.scrollWidth - document.body.clientWidth
        },
        rawInternalTermsVisible: /RCA Context|post_answer|Sealed plan|Conflict|Action Executor URL not configured|mutation gate disabled/.test(footer?.innerText || '')
      };
    })()`,
  );

  if (
    openedMetrics.stepCount < 1 ||
    openedMetrics.jsonOpen ||
    openedMetrics.jsonPreVisible ||
    openedMetrics.answerActionVisible ||
    openedMetrics.rawInternalTermsVisible ||
    Object.values(openedMetrics.overflow).some((value) => typeof value === 'number' && value > 1)
  ) {
    throw new Error(`Tool Plan opened UI contract failed: ${JSON.stringify(openedMetrics, null, 2)}`);
  }

  const shot = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  fs.writeFileSync(screenshotPath, Buffer.from(shot.data, 'base64'));

  const result = {
    chrome: (await waitForJson(`http://127.0.0.1:${port}/json/version`)).Browser,
    question,
    gatewayHealth,
    screenshotPath,
    defaultMetrics,
    openedMetrics,
  };
  console.log(JSON.stringify(result, null, 2));

  ws.close();
  proc.kill('SIGTERM');
};

main()
  .catch((error) => {
    console.error(error.stack || String(error));
    if (chromeWebSocket) {
      chromeWebSocket.close();
    }
    if (chromeProcess) {
      chromeProcess.kill('SIGTERM');
    }
    process.exit(1);
  })
  .finally(() => {
    try {
      fs.rmSync(userDataDir, { force: true, recursive: true });
    } catch (_error) {
      // Chrome may still be releasing the profile directory on slower WSL filesystems.
    }
  });
