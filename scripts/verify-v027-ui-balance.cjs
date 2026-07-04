#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const WebSocket = require('ws');

const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9343');
const screenshotDir = process.env.AIOPS_SCREENSHOT_DIR || '/tmp';
const defaultUrls = [
  'http://localhost:9000/dashboards/aiops',
  'http://localhost:9000/dashboards/aiops/audit',
  'http://localhost:9000/dashboards/aiops/service-map',
  'http://localhost:9000/dashboards/aiops/endpoints',
  'http://localhost:9000/dashboards/aiops/alerts',
  'http://localhost:9000/dashboards/aiops/docs',
  'http://localhost:9000/dashboards/aiops/reports',
];
const urls = (process.env.AIOPS_UI_BALANCE_URLS || defaultUrls.join(','))
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean);
const parseViewport = (spec) => {
  const [rawLabel, rawSize = rawLabel] = spec.includes(':') ? spec.split(':') : ['viewport', spec];
  const [width, height] = rawSize
    .toLowerCase()
    .replace('x', ',')
    .split(',')
    .map((value) => Number.parseInt(value.trim(), 10));
  if (!Number.isFinite(width) || !Number.isFinite(height) || width <= 0 || height <= 0) {
    throw new Error(`Invalid viewport spec: ${spec}`);
  }
  return {
    height,
    label: rawLabel.trim() || `${width}x${height}`,
    mobile: width < 700,
    width,
  };
};
const viewportSpecs = (process.env.AIOPS_UI_BALANCE_VIEWPORTS || 'desktop:1440x900,mobile:390x844')
  .split(',')
  .map((value) => value.trim())
  .filter(Boolean)
  .map(parseViewport);
const colorSchemes = (process.env.AIOPS_UI_BALANCE_COLOR_SCHEMES || 'light,dark')
  .split(',')
  .map((value) => value.trim().toLowerCase())
  .filter(Boolean);
const launchViewport = viewportSpecs.reduce(
  (largest, item) => ({
    height: Math.max(largest.height, item.height),
    width: Math.max(largest.width, item.width),
  }),
  { height: 900, width: 1440 },
);
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-ui-balance-'));
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
      `--window-size=${launchViewport.width},${launchViewport.height}`,
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      urls[0],
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

const main = async () => {
  chromeProcess = launchChrome();
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
      await sleep(750);
    }
    throw new Error(`Timed out waiting for ${label}. Last=${JSON.stringify(last)}`);
  };

  const navigate = async (url) => {
    await send('Page.navigate', { url });
    await poll(
      `(() => ({
        ready: document.readyState === 'complete' && Boolean(document.body?.innerText?.trim()),
        text: document.body?.innerText?.slice(0, 600) || '',
        hasOverlayFrame: Boolean(document.querySelector('#webpack-dev-server-client-overlay'))
      }))()`,
      (value) => value?.ready && !value.hasOverlayFrame,
      `page ${url}`,
      90000,
    );
    await sleep(1200);
  };

  const setViewportAndTheme = async (viewport, colorScheme) => {
    await send('Emulation.setDeviceMetricsOverride', {
      deviceScaleFactor: 1,
      height: viewport.height,
      mobile: viewport.mobile,
      screenHeight: viewport.height,
      screenWidth: viewport.width,
      width: viewport.width,
    });
    await send('Emulation.setEmulatedMedia', {
      features: [{ name: 'prefers-color-scheme', value: colorScheme }],
    });
  };

  const applyThemeClass = async (colorScheme) => {
    await evaluate(`(() => {
      const dark = ${JSON.stringify(colorScheme)} === 'dark';
      for (const el of [document.documentElement, document.body]) {
        el.classList.toggle('pf-v6-theme-dark', dark);
        el.classList.toggle('pf-theme-dark', dark);
        el.dataset.theme = dark ? 'dark' : 'light';
        el.style.colorScheme = dark ? 'dark' : 'light';
      }
      return true;
    })()`);
  };

  const capture = async (label) => {
    const file = path.join(
      screenshotDir,
      `v027-ui-balance-${label.replace(/[^a-z0-9_-]+/gi, '-')}.png`,
    );
    const result = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
    fs.writeFileSync(file, Buffer.from(result.data, 'base64'));
    return file;
  };

  const inspectBalance = (context) =>
    evaluate(`(() => {
      const selectors = [
        '.status-badge',
        '.portal-alarm__badge',
        '.portal-mode',
        '.portal-sidebar__status',
        '.live-data-badge',
        '.guardrail-pill',
        '.hero-pill',
        '.impact-edge-label',
        '.impact-stack-section__label',
        '.impact-stack-row__chips span',
        '.doc-tags b',
        '.trace-row__result',
        '.trace-row__sample',
        '.komsco-ai__context-pill',
        '.komsco-ai__evidence-pill',
        '.komsco-ai__header-op-chip',
        '.komsco-ai__history-action-ref-stage',
        '.komsco-ai__rail-badge',
        '.komsco-ai__runbook-badge',
        '.komsco-ai__scope-tag',
        '.komsco-ai__status-tag',
        '.komsco-ai__mode-chip',
        '.komsco-ai__message-source',
        '.komsco-ai__task-mode-button',
        '.komsco-ai__tool-button',
        '.komsco-ai__toolplan-source',
        '.komsco-ai__plan-summary-policy',
        '.komsco-ai__plan-summary-rollback'
      ].join(',');
      const rawTerms = [
        'Action Executor URL not configured',
        'mutation gate disabled',
        'unrestricted command gate',
        'evidence-check UI blocks',
        'Conflict',
        '봉인됨',
        '봉인 계획',
        '승인 봉인'
      ];
      const bodyText = document.body?.innerText || '';
      const rawInternalTerms = rawTerms.filter((term) => bodyText.includes(term));
      const px = (value) => {
        const parsed = Number.parseFloat(String(value || '0'));
        return Number.isFinite(parsed) ? parsed : 0;
      };
      const visible = (el) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' && style.opacity !== '0';
      };
      const compactText = (el) => (el.textContent || '').replace(/[\\n\\r\\t ]+/g, ' ').trim();
      const candidates = Array.from(document.querySelectorAll(selectors))
        .filter(visible)
        .map((el, index) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          const text = compactText(el);
          const className = String(el.className || '');
          const tag = el.tagName.toLowerCase();
          const display = style.display;
          const alignItems = style.alignItems;
          const paddingTop = px(style.paddingTop);
          const paddingBottom = px(style.paddingBottom);
          const lineHeight = px(style.lineHeight);
          const fontSize = px(style.fontSize);
          const issues = [];
          const flexLike = display.includes('flex') || display.includes('grid');
          const mustCenter = /status-badge|badge|pill|chip|tag|portal-mode|portal-sidebar__status|impact-edge-label|trace-row__result|trace-row__sample|tool-button|task-mode-button|plan-summary|history-action-ref-stage/.test(className);
          if (mustCenter && flexLike && !['center', 'normal'].includes(alignItems)) {
            issues.push('not-center-aligned');
          }
          if (mustCenter && !flexLike && rect.height <= 42) {
            issues.push('not-flex-centered');
          }
          if (Math.abs(paddingTop - paddingBottom) > 2) {
            issues.push('padding-imbalance');
          }
          if (lineHeight > 0 && rect.height > 0 && lineHeight > rect.height + 3 && rect.height <= 44) {
            issues.push('line-height-clips-compact-badge');
          }
          if (text.length >= 2 && rect.height > rect.width * 1.35 && rect.width < 42) {
            issues.push('vertical-looking-text');
          }
          if (el.scrollWidth > el.clientWidth + 1 && rect.height <= 48) {
            issues.push('horizontal-text-clipping');
          }
          return {
            alignItems,
            className,
            display,
            fontSize,
            index,
            issues,
            lineHeight,
            paddingBottom,
            paddingTop,
            rect: {
              height: Math.round(rect.height),
              width: Math.round(rect.width),
              x: Math.round(rect.x),
              y: Math.round(rect.y)
            },
            scrollWidth: el.scrollWidth,
            clientWidth: el.clientWidth,
            tag,
            text: text.slice(0, 80)
          };
        });
      const issueItems = candidates.filter((item) => item.issues.length > 0);
      const iconIssues = Array.from(
        document.querySelectorAll(
          '.komsco-ai__fab, .komsco-ai__icon-button, .komsco-ai__tool-button, .komsco-ai__task-mode-button, .komsco-ai__send'
        )
      )
        .filter(visible)
        .map((el, index) => {
          const style = window.getComputedStyle(el);
          const rect = el.getBoundingClientRect();
          const text = compactText(el) || el.getAttribute('aria-label') || '';
          const issues = [];
          if (rect.width < 24 || rect.height < 24) {
            issues.push('icon-hit-area-too-small');
          }
          if (Number.parseFloat(style.opacity || '1') < 0.35) {
            issues.push('icon-opacity-too-low');
          }
          if (style.visibility === 'hidden' || style.display === 'none') {
            issues.push('icon-hidden');
          }
          if (/rgba\\([^)]*,\\s*0\\)|transparent/i.test(style.color)) {
            issues.push('icon-transparent-color');
          }
          return {
            className: String(el.className || ''),
            color: style.color,
            index,
            issues,
            opacity: style.opacity,
            rect: {
              height: Math.round(rect.height),
              width: Math.round(rect.width),
              x: Math.round(rect.x),
              y: Math.round(rect.y)
            },
            text: text.slice(0, 80)
          };
        })
        .filter((item) => item.issues.length > 0);
      const overflow = {
        body: {
          clientWidth: document.body.clientWidth,
          ok: document.body.scrollWidth <= document.body.clientWidth + 1,
          scrollWidth: document.body.scrollWidth
        },
        document: {
          clientWidth: document.documentElement.clientWidth,
          ok: document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1,
          scrollWidth: document.documentElement.scrollWidth
        }
      };
      return {
        candidateCount: candidates.length,
        context: ${JSON.stringify(context)},
        iconIssues,
        issueItems,
        overflow,
        rawInternalTerms,
        title: document.title,
        url: location.href
      };
    })()`);

  await send('Page.enable');
  await send('Runtime.enable');

  const results = [];
  for (const viewport of viewportSpecs) {
    for (const colorScheme of colorSchemes) {
      await setViewportAndTheme(viewport, colorScheme);
      for (const url of urls) {
        await navigate(url);
        await applyThemeClass(colorScheme);
        results.push(await inspectBalance({ colorScheme, state: 'page', viewport: viewport.label }));

        const hasFab = await evaluate(
          `Boolean(document.querySelector('[aria-label="Open Cywell AI"]'))`,
        );
        if (hasFab) {
          await evaluate(`document.querySelector('[aria-label="Open Cywell AI"]')?.click()`);
          await poll(
            `Boolean(document.querySelector('[aria-label="Cywell AI assistant"]'))`,
            Boolean,
            'assistant open',
          );
          await applyThemeClass(colorScheme);
          results.push(
            await inspectBalance({ colorScheme, state: 'assistant-docked', viewport: viewport.label }),
          );
          await evaluate(`document.querySelector('[aria-label="Open full screen"]')?.click()`);
          await poll(
            `Boolean(document.querySelector('.komsco-ai__surface--fullscreen'))`,
            Boolean,
            'assistant fullscreen',
          );
          await sleep(1000);
          await applyThemeClass(colorScheme);
          results.push(
            await inspectBalance({
              colorScheme,
              state: 'assistant-fullscreen',
              viewport: viewport.label,
            }),
          );
          await capture(
            `assistant-fullscreen-${viewport.label}-${colorScheme}-${new URL(url).pathname
              .split('/')
              .join('-')}`,
          );
          await evaluate(`document.querySelector('[aria-label="Close Cywell AI"]')?.click()`);
          await sleep(500);
        }
      }
    }
  }

  const failed = results.filter(
    (result) =>
      result.rawInternalTerms.length > 0 ||
      !result.overflow.body.ok ||
      !result.overflow.document.ok ||
      result.issueItems.length > 0 ||
      result.iconIssues.length > 0,
  );
  const summary = {
    chrome: version.Browser,
    failedCount: failed.length,
    passed: failed.length === 0,
    results: results.map((result) => ({
      candidateCount: result.candidateCount,
      context: result.context,
      iconIssues: result.iconIssues.slice(0, 12),
      iconIssueCount: result.iconIssues.length,
      issueItems: result.issueItems.slice(0, 12),
      issueCount: result.issueItems.length,
      overflow: result.overflow,
      rawInternalTerms: result.rawInternalTerms,
      title: result.title,
      url: result.url,
    })),
  };
  console.log(JSON.stringify(summary, null, 2));
  if (!summary.passed) {
    throw new Error(`UI balance verifier failed: ${failed.length} context(s) have issues.`);
  }
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
      // ignore cleanup errors
    }
    try {
      chromeProcess?.kill('SIGTERM');
    } catch (_error) {
      // ignore cleanup errors
    }
    try {
      fs.rmSync(userDataDir, { force: true, recursive: true });
    } catch (_error) {
      // ignore cleanup errors
    }
  });
