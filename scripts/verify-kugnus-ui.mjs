#!/usr/bin/env node

import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { execFileSync, spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const escapePwshSingleQuoted = (value) => String(value).replace(/'/g, "''");

const delegateWslRunToWindowsNode = async () => {
  const cwd = execFileSync('wslpath', ['-w', process.cwd()], { encoding: 'utf8' }).trim();
  const script = execFileSync('wslpath', ['-w', fileURLToPath(import.meta.url)], {
    encoding: 'utf8',
  }).trim();
  const forwardedEnv = [
    'KUGNUS_UI_WINDOWS_DELEGATED',
    'KUGNUS_UI_URL',
    'KUGNUS_UI_VERIFY_MODE',
    'KUGNUS_CHROME_DEBUG_HOST',
    'KUGNUS_CHROME_DEBUG_PORT',
    'KUGNUS_UI_SCREENSHOT_DIR',
    'KUGNUS_UI_AUTOSTART_CHROME',
  ];
  const envAssignments = forwardedEnv
    .filter((name) => process.env[name] !== undefined)
    .map((name) => `$env:${name}='${escapePwshSingleQuoted(process.env[name])}'`)
    .join('; ');
  const command = [
    "$env:KUGNUS_UI_WINDOWS_DELEGATED='1'",
    envAssignments,
    `Set-Location -LiteralPath '${escapePwshSingleQuoted(cwd)}'`,
    `node '${escapePwshSingleQuoted(script)}'`,
  ]
    .filter(Boolean)
    .join('; ');

  const child = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command], {
    stdio: 'inherit',
  });

  const exitCode = await new Promise((resolve) => {
    child.on('exit', (code) => resolve(code ?? 1));
  });
  process.exit(exitCode);
};

if (os.release().toLowerCase().includes('microsoft') && process.env.KUGNUS_UI_WINDOWS_DELEGATED !== '1') {
  await delegateWslRunToWindowsNode();
}

const chromePort = Number(process.env.KUGNUS_CHROME_DEBUG_PORT || 9231);
const uiUrl = process.env.KUGNUS_UI_URL || 'http://localhost:9000/aiops-kugnus';
const verifyMode =
  process.env.KUGNUS_UI_VERIFY_MODE ||
  (new URL(uiUrl).pathname === '/aiops-kugnus' ? 'dashboard' : 'overlay');
const screenshotDir = process.env.KUGNUS_UI_SCREENSHOT_DIR || process.cwd();
const autostartChrome = process.env.KUGNUS_UI_AUTOSTART_CHROME !== 'false';

const results = [];
const browserDiagnostics = {
  console: [],
  exceptions: [],
  networkFailures: [],
  responses: [],
};
let activeChromeHost = '127.0.0.1';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const withTimeout = (promise, timeoutMs, label) =>
  Promise.race([
    promise,
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error(`${label} timed out after ${timeoutMs}ms`)), timeoutMs),
    ),
  ]);

const isWsl = () => os.release().toLowerCase().includes('microsoft');

const detectWindowsHostFromWsl = async () => {
  try {
    const resolvConf = await fs.readFile('/etc/resolv.conf', 'utf8');
    const match = resolvConf.match(/^nameserver\s+(\S+)/m);
    return match?.[1] || null;
  } catch {
    return null;
  }
};

const record = (name, ok, evidence = {}) => {
  results.push({ name, ok, evidence });
  const prefix = ok ? 'PASS' : 'FAIL';
  console.log(`${prefix} ${name}${Object.keys(evidence).length ? ` ${JSON.stringify(evidence)}` : ''}`);
};

const assertCheck = (name, condition, evidence = {}) => {
  record(name, Boolean(condition), evidence);
  if (!condition) {
    throw new Error(name);
  }
};

const counterAfterLabel = (text, label) => {
  const match = String(text || '').match(new RegExp(`${label}\\s*([0-9]+)`, 'i'));
  return match ? Number(match[1]) : -1;
};

const rcaContextTextHasTraceFields = (text) => {
  const body = String(text || '');
  return (
    /"kind"\s*:\s*"RcaContext"/.test(body) &&
    /"metadata"\s*:/.test(body) &&
    /"digest"\s*:/.test(body) &&
    /"contextId"\s*:/.test(body) &&
    /"evidence"\s*:/.test(body) &&
    /"collectedRefs"\s*:/.test(body) &&
    /"failedRefs"\s*:/.test(body) &&
    /"missing"\s*:/.test(body) &&
    /"evidence_refs"\s*:/.test(body)
  );
};

const cssPx = (value) => Number.parseFloat(String(value || '0')) || 0;

const parseRgb = (value) => {
  const match = String(value || '').match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
  return match ? match.slice(1, 4).map((part) => Number(part)) : null;
};

const fetchJsonFromHost = async (host, pathname, options = {}) => {
  const response = await fetch(`http://${host}:${chromePort}${pathname}`, options);
  if (!response.ok) {
    throw new Error(`Chrome CDP HTTP ${response.status} for ${host}:${chromePort}${pathname}`);
  }
  return response.json();
};

const fetchJson = async (pathname, options = {}) => fetchJsonFromHost(activeChromeHost, pathname, options);

const getChromeHostCandidates = async () => {
  if (process.env.KUGNUS_CHROME_DEBUG_HOST) {
    return [process.env.KUGNUS_CHROME_DEBUG_HOST];
  }

  if (!isWsl()) {
    return ['127.0.0.1', 'localhost'];
  }

  const windowsHost = await detectWindowsHostFromWsl();
  return [windowsHost, 'host.docker.internal', '127.0.0.1', 'localhost'].filter(Boolean);
};

const waitForChrome = async (timeoutMs = 20000) => {
  const deadline = Date.now() + timeoutMs;
  let lastError;

  while (Date.now() < deadline) {
    const candidates = await getChromeHostCandidates();
    for (const host of candidates) {
      try {
        await fetchJsonFromHost(host, '/json/version');
        activeChromeHost = host;
        return true;
      } catch (error) {
        lastError = error;
      }
    }
    await sleep(500);
  }

  throw lastError || new Error(`Chrome CDP is not reachable on port ${chromePort}`);
};

const startWindowsChrome = () => {
  const profileName = `kugnus-aiops-ui-${chromePort}`;
  const command = `
$chrome = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
if (-not (Test-Path $chrome)) { $chrome = 'C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe' }
if (-not (Test-Path $chrome)) { throw 'Chrome executable not found' }
$profile = Join-Path $env:TEMP '${profileName}'
if (Test-Path $profile) { Remove-Item -LiteralPath $profile -Recurse -Force }
Start-Process -FilePath $chrome -WindowStyle Hidden -ArgumentList @(
  '--headless=new',
  '--disable-gpu',
  '--no-first-run',
  '--no-default-browser-check',
  '--remote-debugging-address=0.0.0.0',
  '--remote-debugging-port=${chromePort}',
  '--window-size=1440,1000',
  "--user-data-dir=$profile",
  'about:blank'
)
`;

  const child = spawn('powershell.exe', ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command], {
    detached: true,
    stdio: 'ignore',
  });
  child.unref();
};

const startLinuxChrome = () => {
  const candidates = ['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'];
  const profileDir = path.join(os.tmpdir(), `kugnus-aiops-ui-${chromePort}`);
  const args = [
    '--headless=new',
    '--disable-gpu',
    '--no-first-run',
    '--no-default-browser-check',
    '--remote-debugging-address=0.0.0.0',
    `--remote-debugging-port=${chromePort}`,
    '--window-size=1440,1000',
    `--user-data-dir=${profileDir}`,
    'about:blank',
  ];

  for (const candidate of candidates) {
    try {
      const child = spawn(candidate, args, { detached: true, stdio: 'ignore' });
      child.unref();
      return;
    } catch {
      // Try the next browser candidate.
    }
  }

  throw new Error('Chrome or Chromium executable not found');
};

const ensureChrome = async () => {
  try {
    await waitForChrome(1500);
    return;
  } catch {
    if (!autostartChrome) {
      throw new Error(`Chrome CDP is not running on port ${chromePort}`);
    }
  }

  if (process.platform === 'win32' || isWsl()) {
    startWindowsChrome();
  } else {
    startLinuxChrome();
  }

  await waitForChrome();
};

class CdpClient {
  constructor(webSocketDebuggerUrl) {
    this.webSocketDebuggerUrl = webSocketDebuggerUrl;
    this.nextId = 1;
    this.pending = new Map();
    this.eventHandlers = new Map();
  }

  async connect() {
    this.ws = new WebSocket(this.webSocketDebuggerUrl);
    await new Promise((resolve, reject) => {
      this.ws.addEventListener('open', resolve, { once: true });
      this.ws.addEventListener('error', reject, { once: true });
    });

    this.ws.addEventListener('message', (event) => {
      const message = JSON.parse(event.data);
      if (!message.id || !this.pending.has(message.id)) {
        const handlers = this.eventHandlers.get(message.method) || [];
        handlers.forEach((handler) => handler(message.params || {}));
        return;
      }

      const { resolve, reject } = this.pending.get(message.id);
      this.pending.delete(message.id);

      if (message.error) {
        reject(new Error(`${message.error.message}: ${message.error.data || ''}`));
        return;
      }

      resolve(message.result);
    });
  }

  send(method, params = {}, timeoutMs = 30000) {
    const id = this.nextId;
    this.nextId += 1;

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`CDP ${method} timed out after ${timeoutMs}ms`));
      }, timeoutMs);
      this.pending.set(id, {
        reject: (error) => {
          clearTimeout(timer);
          reject(error);
        },
        resolve: (value) => {
          clearTimeout(timer);
          resolve(value);
        },
      });

      try {
        this.ws.send(JSON.stringify({ id, method, params }));
      } catch (error) {
        clearTimeout(timer);
        this.pending.delete(id);
        reject(error);
      }
    });
  }

  on(method, handler) {
    const handlers = this.eventHandlers.get(method) || [];
    handlers.push(handler);
    this.eventHandlers.set(method, handlers);
  }

  async close() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

const pushDiagnostic = (bucket, value, limit = 12) => {
  bucket.push(value);
  if (bucket.length > limit) {
    bucket.shift();
  }
};

const attachCdpDiagnostics = (cdp, label) => {
  cdp.on('Runtime.consoleAPICalled', (params) => {
    pushDiagnostic(browserDiagnostics.console, {
      label,
      type: params.type,
      text: (params.args || [])
        .map((arg) => arg.value ?? arg.description ?? '')
        .join(' ')
        .slice(0, 500),
    });
  });
  cdp.on('Runtime.exceptionThrown', (params) => {
    pushDiagnostic(browserDiagnostics.exceptions, {
      label,
      text: params.exceptionDetails?.exception?.description || params.exceptionDetails?.text || '',
    });
  });
  cdp.on('Network.loadingFailed', (params) => {
    pushDiagnostic(browserDiagnostics.networkFailures, {
      label,
      errorText: params.errorText,
      requestId: params.requestId,
      type: params.type,
    });
  });
  cdp.on('Network.responseReceived', (params) => {
    if (params.response?.status >= 400) {
      pushDiagnostic(browserDiagnostics.responses, {
        label,
        status: params.response.status,
        type: params.type,
        url: params.response.url,
      });
    }
  });
};

const openPage = async () => {
  let target;
  try {
    target = await fetchJson(`/json/new?${encodeURIComponent('about:blank')}`, { method: 'PUT' });
  } catch {
    const targets = await fetchJson('/json/list');
    target = targets.find((item) => item.type === 'page');
  }

  if (!target?.webSocketDebuggerUrl) {
    throw new Error('No Chrome page target is available');
  }

  const cdp = new CdpClient(target.webSocketDebuggerUrl);
  await cdp.connect();
  attachCdpDiagnostics(cdp, 'fresh-target');
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('DOM.enable');
  await cdp.send('Network.enable');
  await cdp.send('Network.clearBrowserCache');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  await cdp.send('Input.setIgnoreInputEvents', { ignore: false });
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await cdp.send('Page.navigate', { url: uiUrl });
  return cdp;
};

const connectToTarget = async (target) => {
  const cdp = new CdpClient(target.webSocketDebuggerUrl);
  await cdp.connect();
  attachCdpDiagnostics(cdp, 'recovered-target');
  await cdp.send('Page.enable');
  await cdp.send('Runtime.enable');
  await cdp.send('DOM.enable');
  await cdp.send('Network.enable');
  await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
  await cdp.send('Input.setIgnoreInputEvents', { ignore: false });
  await cdp.send('Emulation.setDeviceMetricsOverride', {
    width: 1440,
    height: 1000,
    deviceScaleFactor: 1,
    mobile: false,
  });
  return cdp;
};

const recoverLoadedAiopsPage = async (currentCdp) => {
  const targets = await fetchJson('/json/list');
  const ui = new URL(uiUrl);
  const candidates = targets.filter(
    (item) =>
      item.type === 'page' &&
      item.webSocketDebuggerUrl &&
      item.url &&
      new URL(item.url).origin === ui.origin &&
      new URL(item.url).pathname === ui.pathname,
  );

  for (const target of candidates) {
    const candidate = await connectToTarget(target);
    const hasRoot = await evaluate(
      candidate,
      "document.readyState === 'complete' && !!document.querySelector('.komsco-ai')",
    );
    if (hasRoot) {
      await currentCdp.close();
      return candidate;
    }
    await candidate.close();
  }

  return currentCdp;
};

const evaluate = async (cdp, expression) => {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });

  if (result.exceptionDetails) {
    const detail = result.exceptionDetails.exception?.description || result.exceptionDetails.text;
    throw new Error(`${detail} while evaluating: ${expression.slice(0, 360)}`);
  }

  return result.result.value;
};

const waitFor = async (cdp, name, expression, timeoutMs = 20000) => {
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    const value = await evaluate(cdp, expression);
    if (value) {
      return value;
    }
    await sleep(250);
  }

  throw new Error(`Timed out waiting for ${name}`);
};

const getPageDiagnostics = async (cdp, extra = {}) => {
  let page = {};
  try {
    page = await evaluate(
      cdp,
      `(() => ({
        href: window.location.href,
        readyState: document.readyState,
        title: document.title,
        hasAiopsRoot: !!document.querySelector('.komsco-ai'),
        hasAiopsPage: !!document.querySelector('.komsco-ai-page'),
        bodyPreview: document.body?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim().slice(0, 900) || '',
      }))()`,
    );
  } catch (error) {
    page = {
      diagnosticError: error instanceof Error ? error.message : String(error),
    };
  }

  return {
    ...extra,
    verifyMode,
    page,
    browserDiagnostics,
  };
};

const activeSurfaceExpression = `
  document.querySelector('.komsco-ai__surface--fullscreen')
  || document.querySelector('.komsco-ai--embedded .komsco-ai__surface')
  || document.querySelector('.komsco-ai__surface')
`;

const initialRootExpression =
  verifyMode === 'dashboard'
    ? "document.readyState === 'complete' && !!document.querySelector('.komsco-ai-page')"
    : "document.readyState === 'complete' && !!document.querySelector('.komsco-ai')";

const click = async (cdp, selector) => {
  const clicked = await evaluate(
    cdp,
    `(() => {
      const activeSurface = ${activeSurfaceExpression};
      const el = activeSurface?.querySelector(${JSON.stringify(selector)})
        || document.querySelector(${JSON.stringify(selector)});
      if (!el) return false;
      const originalScrollX = window.scrollX;
      el.scrollIntoView({ block: 'center', inline: 'nearest' });
      if (window.scrollX !== originalScrollX) {
        window.scrollTo(originalScrollX, window.scrollY);
      }
      const rect = el.getBoundingClientRect();
      const clientX = rect.left + rect.width / 2;
      const clientY = rect.top + rect.height / 2;
      const pointerEvent = typeof PointerEvent === 'function' ? PointerEvent : MouseEvent;
      el.dispatchEvent(
        new pointerEvent('pointerdown', {
          bubbles: true,
          cancelable: true,
          clientX,
          clientY,
          pointerId: 1,
          pointerType: 'mouse',
        }),
      );
      el.dispatchEvent(
        new MouseEvent('mousedown', { bubbles: true, cancelable: true, clientX, clientY }),
      );
      el.dispatchEvent(
        new pointerEvent('pointerup', {
          bubbles: true,
          cancelable: true,
          clientX,
          clientY,
          pointerId: 1,
          pointerType: 'mouse',
        }),
      );
      el.dispatchEvent(
        new MouseEvent('mouseup', { bubbles: true, cancelable: true, clientX, clientY }),
      );
      el.dispatchEvent(
        new MouseEvent('click', { bubbles: true, cancelable: true, clientX, clientY }),
      );
      return true;
    })()`,
  );

  if (!clicked) {
    throw new Error(`Missing clickable element: ${selector}`);
  }
  await sleep(200);
};

const dragResizeHandle = async (cdp, deltaX, deltaY) => {
  const dragged = await evaluate(
    cdp,
    `(() => new Promise((resolve) => {
      const surface = ${activeSurfaceExpression};
      const grip = surface?.querySelector('.komsco-ai__resize-grip');
      if (!surface || !grip) {
        resolve(false);
        return;
      }
      const r = grip.getBoundingClientRect();
      const x = r.left + r.width / 2;
      const y = r.top + r.height / 2;
      grip.dispatchEvent(
        new MouseEvent('mousedown', {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: x,
          clientY: y,
          button: 0,
          buttons: 1,
        }),
      );
      document.dispatchEvent(
        new MouseEvent('mousemove', {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: x + ${Number(deltaX)},
          clientY: y + ${Number(deltaY)},
          button: 0,
          buttons: 1,
        }),
      );
      document.dispatchEvent(
        new MouseEvent('mouseup', {
          bubbles: true,
          cancelable: true,
          view: window,
          clientX: x + ${Number(deltaX)},
          clientY: y + ${Number(deltaY)},
          button: 0,
          buttons: 0,
        }),
      );
      setTimeout(() => resolve(true), 80);
    }))()`,
  );

  if (!dragged) {
    throw new Error('Missing assistant surface for resize drag');
  }
  await sleep(300);
};

const setComposerText = async (cdp, text) => {
  const result = await evaluate(
    cdp,
    `(() => {
      const surface = ${activeSurfaceExpression};
      try {
        const textarea = surface?.querySelector('textarea.komsco-ai__textarea, .komsco-ai__textarea textarea, textarea');
        if (!textarea) return { ok: false, error: 'Missing chat composer textarea' };
        textarea.focus();
        const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
        if (setter) {
          setter.call(textarea, ${JSON.stringify(text)});
        } else {
          textarea.value = ${JSON.stringify(text)};
        }
        textarea.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${JSON.stringify(text)}, inputType: 'insertText' }));
        textarea.dispatchEvent(new Event('change', { bubbles: true }));
        return { ok: true };
      } catch (error) {
        return {
          ok: false,
          error: String(error?.stack || error?.message || error),
        };
      }
    })()`,
  );

  if (!result?.ok) {
    throw new Error(result?.error || 'Missing chat composer textarea');
  }
  await sleep(250);
};

const getChatInteractionState = async (cdp) =>
  evaluate(
    cdp,
    `(() => {
      const surface = ${activeSurfaceExpression};
      const send = surface?.querySelector('.komsco-ai__send');
      const textarea = surface?.querySelector('textarea.komsco-ai__textarea, .komsco-ai__textarea textarea, textarea');
      const rect = (node) => {
        if (!node) return null;
        const r = node.getBoundingClientRect();
        return {
          bottom: r.bottom,
          height: r.height,
          left: r.left,
          right: r.right,
          top: r.top,
          width: r.width,
        };
      };
      const messages = [...(surface?.querySelectorAll('.komsco-ai__message') || [])].map((node) => {
        const avatar = node.querySelector('.komsco-ai__message-avatar');
        const content = node.querySelector('.komsco-ai__message-content');
        const evidenceFooter = node.querySelector('.komsco-ai__evidence-footer');
        const evidenceText = evidenceFooter?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '';
        const fallbackBadge = node.querySelector('.komsco-ai__message-fallback');
        const label = node.querySelector('.komsco-ai__message-label');
        return {
          avatar: rect(avatar),
          cls: node.className,
          content: rect(content),
          evidenceFooter: evidenceFooter
            ? {
                contextId: evidenceFooter.getAttribute('data-evidence-context-id') || '',
                digest: evidenceFooter.getAttribute('data-evidence-digest') || '',
                missingText: evidenceFooter.querySelector('.komsco-ai__evidence-missing')?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
                rect: rect(evidenceFooter),
                text: evidenceText,
                collectedCount: evidenceFooter.querySelectorAll('.komsco-ai__evidence-pill--collected').length,
                collectedNumber: Number((evidenceText.match(/수집\\s*([0-9]+)/) || [])[1] || 0),
                missingCount: evidenceFooter.querySelectorAll('.komsco-ai__evidence-pill--missing').length,
                missingNumber: Number((evidenceText.match(/추가 확인\\s*([0-9]+)/) || [])[1] || 0),
                refCount: evidenceFooter.querySelectorAll('.komsco-ai__evidence-ref').length,
              }
            : null,
          fallbackBadgeText: fallbackBadge?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
          formattedCodeBlockCount: node.querySelectorAll('.komsco-ai__formatted-code-block').length,
          formattedHeadingCount: node.querySelectorAll('.komsco-ai__formatted-heading').length,
          formattedListCount: node.querySelectorAll('.komsco-ai__formatted-list').length,
          formattedTableCount: node.querySelectorAll('.komsco-ai__table').length,
          labelText: label?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
          message: rect(node),
          text: node.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim(),
        };
      });

      return {
        inputValue: textarea?.value || '',
        sendAria: send?.getAttribute('aria-label') || '',
        sendClass: String(send?.className || ''),
        sendDisabled: send ? send.disabled || send.getAttribute('aria-disabled') === 'true' : null,
        messageCount: messages.length,
        messages,
      };
    })()`,
  );

const makeConversationScrollableAndScrollUp = async (cdp) => {
  const updated = await evaluate(
    cdp,
    `(() => {
      const surface = ${activeSurfaceExpression};
      const body = surface?.querySelector('.komsco-ai__body');
      const inner = surface?.querySelector('.komsco-ai__conversation-inner');
      if (!body || !inner) return false;

      const filler = document.createElement('div');
      filler.setAttribute('data-kugnus-ui-scroll-filler', 'true');
      filler.style.display = 'grid';
      filler.style.gap = '12px';
      filler.style.padding = '12px 0';

      for (let index = 0; index < 18; index += 1) {
        const row = document.createElement('div');
        row.className = 'komsco-ai__message komsco-ai__message--assistant';
        row.style.minHeight = '76px';
        row.style.border = '1px solid transparent';
        row.textContent = \`scroll verification filler \${index + 1}\`;
        filler.appendChild(row);
      }

      inner.insertBefore(filler, inner.firstChild);
      body.scrollTop = body.scrollHeight;
      body.dispatchEvent(new Event('scroll', { bubbles: true }));
      body.scrollTop = 0;
      body.dispatchEvent(new Event('scroll', { bubbles: true }));
      return body.scrollHeight > body.clientHeight + 120;
    })()`,
  );

  if (!updated) {
    throw new Error('Could not create scrollable assistant conversation');
  }
  await sleep(350);
};

const screenshot = async (cdp, filename) => {
  const outputPath = path.join(screenshotDir, filename);
  let shot;

  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      shot = await withTimeout(
        cdp.send('Page.captureScreenshot', {
          format: 'png',
          captureBeyondViewport: false,
        }),
        10000,
        `Page.captureScreenshot ${filename} attempt ${attempt}`,
      );
      break;
    } catch (error) {
      if (attempt === 2) {
        throw error;
      }
      await sleep(500);
    }
  }

  await fs.writeFile(outputPath, Buffer.from(shot.data, 'base64'));
  return outputPath;
};

const getUiState = async (cdp) =>
  evaluate(
    cdp,
    `(() => {
      const surface = ${activeSurfaceExpression};
      const rectOf = (selector) => {
        const el = selector === '.komsco-ai__surface'
          ? surface
          : surface?.querySelector(selector) || document.querySelector(selector);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return {
          left: r.left,
          right: r.right,
          top: r.top,
          bottom: r.bottom,
          width: r.width,
          height: r.height,
          borderBottomWidth: style.borderBottomWidth,
          borderBottomColor: style.borderBottomColor,
          borderBottomLeftRadius: style.borderBottomLeftRadius,
          borderBottomRightRadius: style.borderBottomRightRadius,
          borderLeftWidth: style.borderLeftWidth,
          borderLeftColor: style.borderLeftColor,
          borderRadius: style.borderRadius,
          borderRightWidth: style.borderRightWidth,
          borderRightColor: style.borderRightColor,
          borderTopWidth: style.borderTopWidth,
          borderTopColor: style.borderTopColor,
          borderTopLeftRadius: style.borderTopLeftRadius,
          borderTopRightRadius: style.borderTopRightRadius,
          boxShadow: style.boxShadow,
          display: style.display,
          outlineStyle: style.outlineStyle,
          outlineWidth: style.outlineWidth,
          paddingBottom: style.paddingBottom,
          paddingLeft: style.paddingLeft,
          paddingRight: style.paddingRight,
          paddingTop: style.paddingTop,
          resize: style.resize,
        };
      };

      const title = surface?.querySelector('.komsco-ai__title');
      const language = surface?.querySelector('.komsco-ai__language-button');
      const workspace = surface?.querySelector('.komsco-ai__workspace');
      const rail = surface?.querySelector('.komsco-ai__insight-rail');
      const input = surface?.querySelector('.komsco-ai__textarea textarea, textarea.komsco-ai__textarea');
      const send = surface?.querySelector('.komsco-ai__send');
      const quickMenuTrigger = surface?.querySelector('.komsco-ai__quick-menu-trigger');
      const quickMenuItems = [...(surface?.querySelectorAll('.komsco-ai__quick-menu-item') || [])];
      const inlineQuickPrompts = [...(surface?.querySelectorAll('.komsco-ai__composer-wrap > .komsco-ai__quick-prompts .komsco-ai__quick-prompt') || [])];
      const attach = surface?.querySelector('.komsco-ai__attach');
      const fileInput = surface?.querySelector('input.komsco-ai__file-input[type="file"]');
      const taskModeButton = surface?.querySelector('.komsco-ai__task-mode-button');
      const taskModeOptions = [...(surface?.querySelectorAll('.komsco-ai__task-mode-option') || [])];
      const headerStatus = surface?.querySelector('.komsco-ai__header-status');
      const headerActions = surface?.querySelector('.komsco-ai__header-actions');
      const headerModeButtons = [...(headerStatus?.querySelectorAll('.komsco-ai__mode-toggle-button') || [])];
      const actionLifecycle = surface?.querySelector('.komsco-ai__action-lifecycle');
      const actionLifecycleSteps = [...(actionLifecycle?.querySelectorAll('[data-action-lifecycle-step]') || [])];
      const actionLifecycleStepRects = actionLifecycleSteps.map((step) => {
        const r = step.getBoundingClientRect();
        return { height: r.height, width: r.width };
      });
      const resizeHandles = [...(surface?.querySelectorAll('.komsco-ai__resize-handle') || [])];
      const titleStyle = title ? window.getComputedStyle(title) : null;
      const brandCopy = surface?.querySelector('.komsco-ai__brand-copy');
      const historySidebar = surface?.querySelector('.komsco-ai__history-sidebar') || document.querySelector('.komsco-ai__history-sidebar');
      const historyUser = historySidebar?.querySelector('.komsco-ai__history-user');
      const historyItems = [...(historySidebar?.querySelectorAll('.komsco-ai__history-item') || [])];
      const historyItemHeights = historyItems.map((item) => item.getBoundingClientRect().height);
      const historySidebarRect = historySidebar?.getBoundingClientRect();
      const historyTopElement =
        historySidebarRect && historySidebarRect.width > 0 && historySidebarRect.height > 0
          ? document.elementFromPoint(historySidebarRect.left + 20, historySidebarRect.top + 30)
          : null;

      return {
        rootExists: Boolean(document.querySelector('.komsco-ai')),
        surfaceExists: Boolean(surface),
        surfaceParentTag: surface?.parentElement?.tagName || null,
        surfaceClasses: surface?.className || '',
        title: title?.textContent?.trim() || '',
        languageText: language?.textContent?.trim() || '',
        headerStatusText: headerStatus?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        railText: rail?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        quickMenuTriggerExists: Boolean(quickMenuTrigger),
        quickMenuExpanded: quickMenuTrigger?.getAttribute('aria-expanded') || '',
        quickMenuItemCount: quickMenuItems.length,
        quickMenuItemLabels: quickMenuItems.map((item) =>
          item.querySelector('strong')?.textContent?.trim() || item.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        ),
        inlineQuickPromptCount: inlineQuickPrompts.length,
        attachExists: Boolean(attach),
        fileInputExists: Boolean(fileInput),
        taskModeText: taskModeButton?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        taskModeValue: taskModeButton?.getAttribute('data-assistant-task-mode') || '',
        taskModeOptionCount: taskModeOptions.length,
        taskModeOptionValues: taskModeOptions.map((item) => item.getAttribute('data-komsco-task-mode') || ''),
        historyUserText: historyUser?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        historyUserExists: Boolean(historyUser),
        historyTopElementClass: String(historyTopElement?.className || ''),
        historyTopElementText: historyTopElement?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim().slice(0, 80) || '',
        historyItemCount: historyItems.length,
        historyItemMaxHeight: historyItemHeights.length ? Math.max(...historyItemHeights) : 0,
        headerModeButtonCount: headerModeButtons.length,
        headerModeButtons: headerModeButtons.map((button) => ({
          ariaLabel: button.getAttribute('aria-label') || '',
          disabled: button.hasAttribute('disabled'),
          disabledReason: button.getAttribute('data-disabled-reason') || '',
          title: button.getAttribute('title') || '',
        })),
        actionLifecycleText: actionLifecycle?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        actionLifecycleStepCount: actionLifecycleSteps.length,
        actionLifecycleStepKeys: actionLifecycleSteps.map((step) => step.getAttribute('data-action-lifecycle-step') || ''),
        actionLifecycleStepRects,
        actionLifecycleAttrs: {
          actionExecutorState: actionLifecycle?.getAttribute('data-action-executor-state') || '',
          executeGuard: actionLifecycle?.getAttribute('data-execute-guard') || '',
          mutationFlagState: actionLifecycle?.getAttribute('data-mutation-flag-state') || '',
          uiExecutionMode: actionLifecycle?.getAttribute('data-ui-execution-mode') || '',
        },
        headerStatusLabel: headerStatus?.querySelector('.komsco-ai__status-chip')?.getAttribute('aria-label') || '',
        headerStatusTitle: headerStatus?.querySelector('.komsco-ai__status-chip')?.getAttribute('title') || '',
        hasHeaderStatusChip: Boolean(headerStatus?.querySelector('.komsco-ai__status-chip')),
        hasHeaderModeChip: Boolean(headerStatus?.querySelector('.komsco-ai__mode-chip')),
        headerTitleClipped: title ? title.scrollWidth > title.clientWidth + 1 : false,
        headerTitleMetrics: title
          ? {
              clientWidth: title.clientWidth,
              computedOverflow: titleStyle?.overflow || '',
              computedTextOverflow: titleStyle?.textOverflow || '',
              computedWidth: titleStyle?.width || '',
              scrollWidth: title.scrollWidth,
            }
          : null,
        resizeHandleCount: resizeHandles.length,
        resizeHandleCursors: resizeHandles.map((handle) => window.getComputedStyle(handle).cursor),
        isEmbedded: Boolean(document.querySelector('.komsco-ai--embedded')),
        hasWorkspaceHistoryClass: Boolean(surface?.querySelector('.komsco-ai__workspace--history-open')),
        workspaceGrid: workspace ? window.getComputedStyle(workspace).gridTemplateColumns : null,
        documentOverflowWidth: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        railHorizontalOverflow: rail ? rail.scrollWidth - rail.clientWidth : 0,
        surface: rectOf('.komsco-ai__surface'),
        toggle: rectOf('.komsco-ai__sidebar-toggle'),
        logo: rectOf('.komsco-ai__brand-logo'),
        brand: rectOf('.komsco-ai__brand'),
        brandCopy: rectOf('.komsco-ai__brand-copy'),
        titleRect: rectOf('.komsco-ai__title'),
        header: rectOf('.komsco-ai__header'),
        headerStatus: rectOf('.komsco-ai__header-status'),
        headerActions: rectOf('.komsco-ai__header-actions'),
        history: rectOf('.komsco-ai__history-sidebar'),
        composerWrap: rectOf('.komsco-ai__composer-wrap'),
        inputBox: rectOf('.komsco-ai__input'),
        textarea: rectOf('.komsco-ai__input textarea'),
        panel: rectOf('.komsco-ai__panel'),
        chat: rectOf('.komsco-ai__chat-column'),
        rail: rectOf('.komsco-ai__insight-rail'),
        actionLifecycle: rectOf('.komsco-ai__action-lifecycle'),
        railDisplay: rail ? window.getComputedStyle(rail).display : null,
        sendDisabled: send ? send.disabled || send.getAttribute('aria-disabled') === 'true' : null,
        inputExists: Boolean(input),
      };
    })()`,
  );

const getDashboardState = async (cdp) =>
  evaluate(
    cdp,
    `(() => {
      const rectOf = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          top: r.top,
          bottom: r.bottom,
          left: r.left,
          right: r.right,
          width: r.width,
          height: r.height,
        };
      };
      const panelText = (heading) => {
        const title = [...document.querySelectorAll('.komsco-ai-page__panel-heading h2')]
          .find((node) => node.textContent?.trim() === heading);
        return title?.closest('section')?.textContent?.trim() || '';
      };
      const clippedText = (selector) =>
        [...document.querySelectorAll(selector)]
          .filter((node) => node.scrollWidth > node.clientWidth + 1)
          .map((node) => ({
            className: node.className,
            clientWidth: Math.round(node.clientWidth),
            scrollWidth: Math.round(node.scrollWidth),
            text: node.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
          }));

      return {
        title: document.querySelector('.komsco-ai-page h1')?.textContent?.trim() || '',
        pageExists: Boolean(document.querySelector('.komsco-ai-page')),
        healthScoreText: document.querySelector('.komsco-ai-page__health-dial strong')?.textContent?.trim() || '',
        overviewSideText: document.querySelector('.komsco-ai-page__overview-side')?.textContent?.trim() || '',
        quickToggleVisible: (() => {
          const el = document.querySelector('.komsco-ai-page__assistant-quick-toggle');
          if (!el) return false;
          const r = el.getBoundingClientRect();
          const style = window.getComputedStyle(el);
          return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
        })(),
        floatingFabVisible: [...document.querySelectorAll('.komsco-ai:not(.komsco-ai--embedded) .komsco-ai__fab')]
          .some((el) => {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
          }),
        overview: rectOf('.komsco-ai-page__overview'),
        operatorFlow: rectOf('.komsco-ai-page__operator-flow'),
        metrics: rectOf('.komsco-ai-page__metrics'),
        anomalyBoard: rectOf('.komsco-ai-page__anomaly-board'),
        actionCandidateBoard: rectOf('.komsco-ai-page__action-candidate-board'),
        sourceBoard: rectOf('.komsco-ai-page__source-board'),
        assistant: rectOf('.komsco-ai-page__assistant-stage'),
        dashboardGrid: rectOf('.komsco-ai-page__dashboard-grid'),
        metricCount: document.querySelectorAll('.komsco-ai-page__metric').length,
        metricLabels: [...document.querySelectorAll('.komsco-ai-page__metric-label')].map((node) =>
          node.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim(),
        ),
        operatorFlowText: document.querySelector('.komsco-ai-page__operator-flow')?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        operatorFlowItemCount: document.querySelectorAll('.komsco-ai-page__operator-flow-item').length,
        operatorFlowLabels: [...document.querySelectorAll('.komsco-ai-page__operator-flow-label')].map((node) =>
          node.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim(),
        ),
        operatorFlowClippedItems: clippedText(
          '.komsco-ai-page__operator-flow-item strong, .komsco-ai-page__operator-flow-item small, .komsco-ai-page__operator-flow-label',
        ),
        essentialClippedItems: clippedText(
          '.komsco-ai-page__operator-flow-item strong, .komsco-ai-page__operator-flow-item small, .komsco-ai-page__operator-flow-label, .komsco-ai-page__anomaly-item-head strong, .komsco-ai-page__action-candidate-title strong',
        ),
        panelHeadings: [...document.querySelectorAll('.komsco-ai-page__panel-heading h2')].map((node) =>
          node.textContent?.trim(),
        ),
        adapterPanelText: panelText('OS-aware adapters'),
        anomalyText: document.querySelector('.komsco-ai-page__anomaly-board')?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        anomalyStatus: document.querySelector('.komsco-ai-page__anomaly-board')?.getAttribute('data-anomaly-status') || '',
        anomalyTotal: Number(document.querySelector('.komsco-ai-page__anomaly-board')?.getAttribute('data-anomaly-total') || '0'),
        anomalyItemCount: document.querySelectorAll('.komsco-ai-page__anomaly-item').length,
        anomalyVisibleCount: Number(document.querySelector('.komsco-ai-page__anomaly-list')?.getAttribute('data-visible-anomaly-count') || document.querySelector('.komsco-ai-page__anomaly-normal')?.getAttribute('data-visible-anomaly-count') || '0'),
        anomalyItemTexts: [...document.querySelectorAll('.komsco-ai-page__anomaly-item')].map((node) =>
          node.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        ),
        anomalyTotalsText: document.querySelector('.komsco-ai-page__anomaly-totals')?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        actionCandidateText: document.querySelector('.komsco-ai-page__action-candidate-board')?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        actionCandidateStatus: document.querySelector('.komsco-ai-page__action-candidate-board')?.getAttribute('data-action-candidate-status') || '',
        actionCandidateTotal: Number(document.querySelector('.komsco-ai-page__action-candidate-board')?.getAttribute('data-action-candidate-total') || '0'),
        actionCandidateExecution: document.querySelector('.komsco-ai-page__action-candidate-board')?.getAttribute('data-action-candidate-execution') || '',
        actionCandidateMode: document.querySelector('.komsco-ai-page__action-candidate-board')?.getAttribute('data-action-candidate-mode') || '',
        actionCandidateItemCount: document.querySelectorAll('.komsco-ai-page__action-candidate').length,
        actionCandidateVisibleCount: Number(document.querySelector('.komsco-ai-page__action-candidate-list')?.getAttribute('data-visible-action-candidate-count') || document.querySelector('.komsco-ai-page__action-candidate-empty')?.getAttribute('data-visible-action-candidate-count') || '0'),
        actionCandidateItemTexts: [...document.querySelectorAll('.komsco-ai-page__action-candidate')].map((node) =>
          node.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '',
        ),
        evidencePanelText: panelText('Evidence posture'),
        lightspeedPanelText: panelText('Lightspeed link'),
        rcaContextText: panelText('RCA Context JSON'),
        horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    })()`,
  );

const run = async () => {
  await ensureChrome();
  let cdp = await openPage();

  try {
    try {
      await waitFor(
        cdp,
        'Cywell AI initial root',
        initialRootExpression,
        60000,
      );
    } catch (error) {
      if (verifyMode === 'dashboard') {
        record(
          'fresh dashboard target loads Cywell AI root without stale-tab recovery',
          false,
          await getPageDiagnostics(cdp, {
            reason: error instanceof Error ? error.message : String(error),
          }),
        );
        throw error;
      }
      cdp = await recoverLoadedAiopsPage(cdp);
      await waitFor(
        cdp,
        'Cywell AI initial root',
        initialRootExpression,
        60000,
      );
      record('recovered loaded Cywell AI tab after stale console target', true, {
        reason: error instanceof Error ? error.message : String(error),
      });
    }
    record('initial Cywell AI route root mounted', true, {
      mode: verifyMode,
      url: await evaluate(cdp, 'window.location.href'),
    });
    await evaluate(
      cdp,
      `(() => {
        document
          .querySelectorAll('.komsco-ai__surface--fullscreen button[aria-label="Exit full screen"]')
          .forEach((button) => button.click());
        document
          .querySelectorAll('.komsco-ai:not(.komsco-ai--embedded) .komsco-ai__surface button[aria-label="Close Cywell AI"]')
          .forEach((button) => button.click());
        document
          .querySelectorAll('.komsco-ai__surface--history-open .komsco-ai__sidebar-toggle')
          .forEach((button) => button.click());
      })()`,
    );
    await waitFor(
      cdp,
      'fullscreen and history cleanup',
      "!document.querySelector('.komsco-ai__surface--fullscreen') && !document.querySelector('.komsco-ai__surface--history-open')",
    );

    try {
      await waitFor(
        cdp,
        'embedded assistant surface',
        "!!document.querySelector('.komsco-ai--embedded .komsco-ai__surface')",
        7000,
      );
    } catch {
      await waitFor(
        cdp,
        'assistant surface or toggle',
        "!!document.querySelector('.komsco-ai__surface') || !!document.querySelector('.komsco-ai__fab')",
      );
    }

    const hasSurface = await evaluate(cdp, "!!document.querySelector('.komsco-ai__surface')");
    const hasEmbeddedSurface = await evaluate(cdp, "!!document.querySelector('.komsco-ai--embedded .komsco-ai__surface')");
    if (!hasSurface && !hasEmbeddedSurface) {
      const hasFab = await evaluate(cdp, "!!document.querySelector('.komsco-ai__fab')");
      assertCheck('assistant toggle exists when surface is closed', hasFab);
      await click(cdp, '.komsco-ai__fab');
    }

    await waitFor(cdp, 'assistant surface', "!!document.querySelector('.komsco-ai__surface')");

    let dashboardState = await getDashboardState(cdp);
    const currentHasSurface = await evaluate(cdp, "!!document.querySelector('.komsco-ai__surface')");
    const currentHasEmbeddedSurface = await evaluate(cdp, "!!document.querySelector('.komsco-ai--embedded .komsco-ai__surface')");
    const isAiopsDashboardRoute = dashboardState.pageExists && dashboardState.title.includes('Cywell AI');
    if (verifyMode === 'dashboard' && !isAiopsDashboardRoute) {
      assertCheck('dashboard verifier is running against /aiops-kugnus product route', false, {
        pageExists: dashboardState.pageExists,
        title: dashboardState.title,
        url: await evaluate(cdp, 'window.location.href'),
      });
      throw new Error('Expected /aiops-kugnus dashboard route, but Cywell AI dashboard page was not mounted');
    }
    if (isAiopsDashboardRoute) {
      assertCheck('dashboard page is Cywell AI', true, {
        title: dashboardState.title,
      });
      assertCheck('dashboard route does not show duplicate global assistant FAB', !dashboardState.floatingFabVisible, {
        floatingFabVisible: dashboardState.floatingFabVisible,
      });
      assertCheck('dashboard route keeps K assistant quick toggle visible after refresh', dashboardState.quickToggleVisible, {
        quickToggleVisible: dashboardState.quickToggleVisible,
      });
      await evaluate(cdp, 'window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "auto" })');
      await sleep(250);
      await click(cdp, '.komsco-ai-page__assistant-quick-toggle');
      await waitFor(
        cdp,
        'assistant quick toggle scrolls to embedded assistant',
        `(() => {
          const stage = document.querySelector('.komsco-ai-page__assistant-stage');
          if (!stage) return false;
          const r = stage.getBoundingClientRect();
          return r.top >= 0 && r.top < window.innerHeight * 0.75;
        })()`,
        5000,
      );
      record('dashboard K assistant quick toggle scrolls to embedded assistant', true);
      assertCheck('dashboard health score is loaded from gateway data', /^\d+$/.test(dashboardState.healthScoreText), {
        healthScoreText: dashboardState.healthScoreText,
      });
      assertCheck(
        'dashboard overview side shows API, version, safety, and Lightspeed values',
        dashboardState.overviewSideText.includes('API') &&
          dashboardState.overviewSideText.includes('Version') &&
          dashboardState.overviewSideText.includes('Safety') &&
          dashboardState.overviewSideText.includes('Lightspeed stream') &&
          !dashboardState.overviewSideText.includes('상태 확인 중'),
        {
          overviewSideText: dashboardState.overviewSideText,
        },
      );
      assertCheck(
        'dashboard overview appears before assistant stage',
        Boolean(dashboardState.overview && dashboardState.assistant) &&
          dashboardState.overview.top < dashboardState.assistant.top,
        {
          overviewTop: Math.round(dashboardState.overview?.top || 0),
          assistantTop: Math.round(dashboardState.assistant?.top || 0),
        },
      );
      assertCheck(
        'dashboard exposes Stage 5 operator flow summary before metrics',
        Boolean(dashboardState.overview && dashboardState.operatorFlow && dashboardState.metrics) &&
          dashboardState.overview.bottom <= dashboardState.operatorFlow.top + 2 &&
          dashboardState.operatorFlow.bottom <= dashboardState.metrics.top + 2 &&
          dashboardState.operatorFlowItemCount === 6 &&
          ['클러스터 상태', '이상 징후', 'RCA 근거', '조치 후보', '감사·대화', '안전 정책'].every((label) =>
            dashboardState.operatorFlowLabels.includes(label),
          ) &&
          dashboardState.operatorFlowText.includes('제안만 함 / 실행 안 함') &&
          dashboardState.operatorFlowText.includes('대화 기록 기본 접힘') &&
          /mutation (disabled|enabled)|mutation 상태 확인 중/.test(dashboardState.operatorFlowText) &&
          !/(overview pending|waiting_for_question|status pending)/i.test(dashboardState.operatorFlowText),
        {
          metricsTop: Math.round(dashboardState.metrics?.top || 0),
          operatorFlowBottom: Math.round(dashboardState.operatorFlow?.bottom || 0),
          operatorFlowItemCount: dashboardState.operatorFlowItemCount,
          operatorFlowLabels: dashboardState.operatorFlowLabels,
          operatorFlowText: dashboardState.operatorFlowText.slice(0, 720),
          overviewBottom: Math.round(dashboardState.overview?.bottom || 0),
        },
      );
      assertCheck('dashboard Stage 5 operator flow text is not clipped', dashboardState.operatorFlowClippedItems.length === 0, {
        operatorFlowClippedItems: dashboardState.operatorFlowClippedItems,
      });
      assertCheck('dashboard essential operational titles are not clipped', dashboardState.essentialClippedItems.length === 0, {
        essentialClippedItems: dashboardState.essentialClippedItems,
      });
      assertCheck('dashboard exposes four primary metrics', dashboardState.metricCount >= 4, {
        metricCount: dashboardState.metricCount,
      });
      ['Ready nodes', 'Operator issues', 'Audit records', 'Execution records'].forEach((metricLabel) => {
        assertCheck(`dashboard metric connected: ${metricLabel}`, dashboardState.metricLabels.includes(metricLabel), {
          metricLabels: dashboardState.metricLabels,
        });
      });
      assertCheck(
        'dashboard exposes Stage 2 anomaly summary board',
        Boolean(dashboardState.anomalyBoard) &&
          dashboardState.anomalyText.includes('Cywell AI 이상 징후 자동 정리') &&
          ['normal', 'warning', 'attention', 'risk', 'error', 'unknown'].includes(dashboardState.anomalyStatus),
        {
          anomalyStatus: dashboardState.anomalyStatus,
          anomalyText: dashboardState.anomalyText.slice(0, 640),
        },
      );
      assertCheck(
        'dashboard anomaly and action candidates sit between metrics and source board before assistant',
        Boolean(
          dashboardState.metrics &&
            dashboardState.anomalyBoard &&
            dashboardState.actionCandidateBoard &&
            dashboardState.sourceBoard &&
            dashboardState.assistant,
        ) &&
          dashboardState.metrics.bottom <= dashboardState.anomalyBoard.top + 2 &&
          dashboardState.anomalyBoard.bottom <= dashboardState.actionCandidateBoard.top + 2 &&
          dashboardState.actionCandidateBoard.bottom <= dashboardState.sourceBoard.top + 2 &&
          dashboardState.sourceBoard.bottom <= dashboardState.assistant.top + 2,
        {
          actionCandidateTop: Math.round(dashboardState.actionCandidateBoard?.top || 0),
          anomalyTop: Math.round(dashboardState.anomalyBoard?.top || 0),
          assistantTop: Math.round(dashboardState.assistant?.top || 0),
          metricsBottom: Math.round(dashboardState.metrics?.bottom || 0),
          sourceTop: Math.round(dashboardState.sourceBoard?.top || 0),
        },
      );
      assertCheck(
        'dashboard anomaly summary shows compact top three issues only',
        dashboardState.anomalyVisibleCount <= 3 && dashboardState.anomalyItemCount <= 3,
        {
          anomalyItemCount: dashboardState.anomalyItemCount,
          anomalyVisibleCount: dashboardState.anomalyVisibleCount,
        },
      );
      assertCheck(
        'dashboard anomaly totals expose severity buckets',
        ['위험', '확인 필요', '주의', '총'].every((label) => dashboardState.anomalyTotalsText.includes(label)),
        {
          anomalyTotalsText: dashboardState.anomalyTotalsText,
        },
      );
      if (dashboardState.anomalyItemCount > 0) {
        assertCheck(
          'dashboard anomaly items explain priority, target, cause, evidence, and next check',
          dashboardState.anomalyItemTexts.every(
            (text) =>
              text.includes('P') &&
              text.includes('대상') &&
              text.includes('원인 후보') &&
              text.includes('근거') &&
              text.includes('다음 확인'),
          ),
          {
            anomalyItemTexts: dashboardState.anomalyItemTexts,
          },
        );
      } else {
        assertCheck(
          'dashboard anomaly empty state does not falsely report normal when sources are incomplete',
          dashboardState.anomalyStatus === 'normal'
            ? dashboardState.anomalyText.includes('주요 이상 징후 없음')
            : dashboardState.anomalyText.includes('정상으로 단정할 수 없음') ||
                dashboardState.anomalyText.includes('데이터 소스'),
          {
            anomalyStatus: dashboardState.anomalyStatus,
            anomalyText: dashboardState.anomalyText,
          },
        );
      }
      assertCheck(
        'dashboard exposes Stage 4 read-only action candidate board',
        Boolean(dashboardState.actionCandidateBoard) &&
          dashboardState.actionCandidateText.includes('Cywell AI 조치 후보') &&
          ['normal', 'candidates', 'blocked', 'unknown'].includes(dashboardState.actionCandidateStatus) &&
          dashboardState.actionCandidateExecution === 'not-executed' &&
          dashboardState.actionCandidateMode === 'read-only' &&
          dashboardState.actionCandidateText.includes('제안만 함 / 실행 안 함'),
        {
          actionCandidateExecution: dashboardState.actionCandidateExecution,
          actionCandidateMode: dashboardState.actionCandidateMode,
          actionCandidateStatus: dashboardState.actionCandidateStatus,
          actionCandidateText: dashboardState.actionCandidateText.slice(0, 720),
        },
      );
      assertCheck(
        'dashboard action candidate board states mutation-disabled forbidden actions',
        dashboardState.actionCandidateText.includes('mutation disabled') &&
          ['apply', 'delete', 'patch', 'scale', 'exec'].every((verb) =>
            dashboardState.actionCandidateText.includes(verb),
          ),
        {
          actionCandidateText: dashboardState.actionCandidateText.slice(0, 720),
        },
      );
      assertCheck(
        'dashboard action candidate board shows compact top three candidates only',
        dashboardState.actionCandidateVisibleCount <= 3 && dashboardState.actionCandidateItemCount <= 3,
        {
          actionCandidateItemCount: dashboardState.actionCandidateItemCount,
          actionCandidateVisibleCount: dashboardState.actionCandidateVisibleCount,
        },
      );
      if (dashboardState.actionCandidateItemCount > 0) {
        assertCheck(
          'dashboard action candidates expose risk, precheck, impact, approval, and verification',
          dashboardState.actionCandidateItemTexts.every(
            (text) =>
              text.includes('대상') &&
              text.includes('상태') &&
              text.includes('선행 확인') &&
              text.includes('예상 영향') &&
              text.includes('승인') &&
              text.includes('검증') &&
              text.includes('실행 안 함'),
          ),
          {
            actionCandidateItemTexts: dashboardState.actionCandidateItemTexts,
          },
        );
      } else {
        assertCheck(
          'dashboard action candidate empty state avoids fake execution claims',
          dashboardState.actionCandidateText.includes('제안할 조치 후보 없음') ||
            dashboardState.actionCandidateText.includes('근거가 충분하지 않음') ||
            dashboardState.actionCandidateText.includes('필수 데이터 소스'),
          {
            actionCandidateStatus: dashboardState.actionCandidateStatus,
            actionCandidateText: dashboardState.actionCandidateText,
          },
        );
      }
      await evaluate(
        cdp,
        `document.querySelector('.komsco-ai-page__action-candidate-board')?.scrollIntoView({ block: 'center', inline: 'nearest' })`,
      );
      await sleep(250);
      const actionCandidateShot = await screenshot(cdp, '.tmp-aiops-kugnus-ui-verify-action-candidates.png');
      record('action candidate screenshot saved', true, { path: actionCandidateShot });
      [
        'Evidence posture',
        'Lightspeed link',
        'Tool Plan JSON',
        'RCA Context JSON',
        'OS-aware adapters',
        'Safety contract',
      ].forEach((heading) => {
        assertCheck(`dashboard panel present: ${heading}`, dashboardState.panelHeadings.includes(heading), {
          panelHeadings: dashboardState.panelHeadings,
        });
      });
      assertCheck(
        'dashboard adapter panel explains OpenShift Linux and Windows states',
        dashboardState.adapterPanelText.includes('OpenShift') &&
          dashboardState.adapterPanelText.includes('Linux') &&
          dashboardState.adapterPanelText.includes('Windows') &&
          dashboardState.adapterPanelText.includes('openshift_event_lookup') &&
          dashboardState.adapterPanelText.includes('disabled') &&
          dashboardState.adapterPanelText.includes('planned') &&
          dashboardState.adapterPanelText.includes('Enable diagnostics') &&
          dashboardState.adapterPanelText.includes('Windows node agent') &&
          dashboardState.adapterPanelText.includes('read-only event log credential') &&
          dashboardState.adapterPanelText.includes('network path from Gateway'),
        {
          adapterPanelText: dashboardState.adapterPanelText,
        },
      );
      assertCheck(
        'dashboard Lightspeed panel exposes stream status without stale not-probed placeholder',
        dashboardState.lightspeedPanelText.includes('Lightspeed service') &&
          dashboardState.lightspeedPanelText.includes('komsco-ai-console-plugin-kugnus') &&
          !dashboardState.lightspeedPanelText.includes('not_probed_by_status_endpoint'),
        {
          lightspeedPanelText: dashboardState.lightspeedPanelText,
        },
      );
    } else {
      assertCheck('console dashboards route hosts K assistant surface', Boolean(currentHasSurface || currentHasEmbeddedSurface), {
        hasEmbeddedSurface: currentHasEmbeddedSurface,
        hasSurface: currentHasSurface,
        pageExists: dashboardState.pageExists,
        title: dashboardState.title,
        url: uiUrl,
      });
    }
    assertCheck('dashboard has no horizontal overflow', dashboardState.horizontalOverflow <= 1, {
      horizontalOverflow: dashboardState.horizontalOverflow,
    });

    let state = await getUiState(cdp);
    assertCheck('assistant surface loaded', state.surfaceExists, { url: uiUrl });
    assertCheck('header removes Cywell AI title from compact toolbar', state.title === '', {
      title: state.title,
    });
    assertCheck('header sidebar toggle is left of KOMSCO logo', state.toggle.right <= state.logo.left, {
      toggleRight: Math.round(state.toggle.right),
      logoLeft: Math.round(state.logo.left),
      gap: Math.round(state.logo.left - state.toggle.right),
    });
    assertCheck('header keeps KOMSCO logo visible', state.logo.width >= 120 && state.logo.height >= 24, {
      logoWidth: Math.round(state.logo.width),
      logoHeight: Math.round(state.logo.height),
    });
    assertCheck('history sidebar is closed by default', !state.surfaceClasses.includes('komsco-ai__surface--history-open'), {
      surfaceClasses: state.surfaceClasses,
    });
    assertCheck(
      'header logo, runtime status, and action buttons do not overlap',
      state.brand.right <= state.headerStatus.left + 2 &&
        state.headerStatus.right <= state.headerActions.left + 2,
      {
        actionsLeft: Math.round(state.headerActions.left),
        brandRight: Math.round(state.brand.right),
        headerStatusLeft: Math.round(state.headerStatus.left),
        headerStatusRight: Math.round(state.headerStatus.right),
      },
    );
    const headerCenterY = (state.header.top + state.header.bottom) / 2;
    const headerCenterDeltas = {
      actions: Math.round(((state.headerActions.top + state.headerActions.bottom) / 2 - headerCenterY) * 10) / 10,
      logo: Math.round(((state.logo.top + state.logo.bottom) / 2 - headerCenterY) * 10) / 10,
      status: Math.round(((state.headerStatus.top + state.headerStatus.bottom) / 2 - headerCenterY) * 10) / 10,
      toggle: Math.round(((state.toggle.top + state.toggle.bottom) / 2 - headerCenterY) * 10) / 10,
    };
    assertCheck(
      'header controls share a consistent vertical centerline',
      Object.values(headerCenterDeltas).every((delta) => Math.abs(delta) <= 3),
      {
        headerCenterY: Math.round(headerCenterY * 10) / 10,
        headerCenterDeltas,
      },
    );
    assertCheck(
      'header restores compact runtime status and mode controls',
      state.hasHeaderStatusChip &&
        state.hasHeaderModeChip &&
        state.headerModeButtonCount === 3 &&
        state.headerStatusText.includes('읽기'),
      {
        headerModeButtonCount: state.headerModeButtonCount,
        headerStatusText: state.headerStatusText,
        hasHeaderModeChip: state.hasHeaderModeChip,
        hasHeaderStatusChip: state.hasHeaderStatusChip,
      },
    );
    assertCheck(
      'header status controls expose labels and disabled reasons',
      state.headerStatusLabel.includes('Lightspeed stream') &&
        state.headerStatusLabel.includes('Safety mode') &&
        state.headerModeButtons.length === 3 &&
        state.headerModeButtons
          .filter((button) => button.disabled)
          .every((button) => button.disabledReason && button.title.includes(button.disabledReason)),
      {
        headerModeButtons: state.headerModeButtons,
        headerStatusLabel: state.headerStatusLabel,
        headerStatusTitle: state.headerStatusTitle,
      },
    );
    const languageBefore = state.languageText;
    await click(cdp, '.komsco-ai__language-button');
    await waitFor(
      cdp,
      'language toggle',
      `(${activeSurfaceExpression})?.querySelector('.komsco-ai__language-button')?.textContent?.trim() !== ${JSON.stringify(languageBefore)}`,
    );
    state = await getUiState(cdp);
    assertCheck('language toggle changes KO/EN label', state.languageText !== languageBefore, {
      before: languageBefore,
      after: state.languageText,
    });
    await click(cdp, '.komsco-ai__language-button');

    state = await getUiState(cdp);
    if (state.surfaceClasses.includes('komsco-ai__surface--history-open')) {
      await click(cdp, '.komsco-ai__sidebar-toggle');
      await waitFor(cdp, 'history sidebar closed', `!(${activeSurfaceExpression})?.className.includes('komsco-ai__surface--history-open')`);
    }
    const historyClosedState = await getUiState(cdp);
    assertCheck(
      'history closed keeps the main panel softly rounded',
      cssPx(historyClosedState.panel.borderTopLeftRadius) >= 6 &&
        cssPx(historyClosedState.panel.borderTopRightRadius) >= 6 &&
        cssPx(historyClosedState.panel.borderBottomRightRadius) >= 6 &&
        cssPx(historyClosedState.panel.borderBottomLeftRadius) >= 6,
      {
        bottomLeft: historyClosedState.panel.borderBottomLeftRadius,
        bottomRight: historyClosedState.panel.borderBottomRightRadius,
        topLeft: historyClosedState.panel.borderTopLeftRadius,
        topRight: historyClosedState.panel.borderTopRightRadius,
      },
    );
    await click(cdp, '.komsco-ai__sidebar-toggle');
    await waitFor(cdp, 'history sidebar open', `(${activeSurfaceExpression})?.className.includes('komsco-ai__surface--history-open')`);
    await waitFor(
      cdp,
      'history user footer resolves current OpenShift user',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const text = (surface?.querySelector('.komsco-ai__history-user') || document.querySelector('.komsco-ai__history-user'))?.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim() || '';
        return text && !text.includes('OpenShift user') && !text.includes('인증 확인 필요') && !text.includes('확인 중') && !text.includes('cluster pending');
      })()`,
      12000,
    );

    state = await getUiState(cdp);
    assertCheck(
      'history sidebar shows current OpenShift user footer',
      state.historyUserExists &&
        !state.historyUserText.includes('OpenShift user') &&
        !state.historyUserText.includes('인증 확인 필요') &&
        !state.historyUserText.includes('확인 중'),
      {
        historyUserText: state.historyUserText,
      },
    );
    assertCheck(
      'history saved conversation cards stay compact',
      state.historyItemCount === 0 || state.historyItemMaxHeight <= 72,
      {
        historyItemCount: state.historyItemCount,
        historyItemMaxHeight: Math.round(state.historyItemMaxHeight),
      },
    );
    assertCheck(
      'history drawer extends outside the main panel without resizing it',
      Boolean(state.history) &&
        Math.abs(state.panel.width - historyClosedState.panel.width) <= 2 &&
        Math.abs(state.panel.left - historyClosedState.panel.left) <= 2 &&
        Math.abs(state.surface.width - historyClosedState.surface.width) <= 2 &&
        state.history.right <= state.panel.left + 2 &&
        !state.historyTopElementClass.includes('pf-v6-c-nav__link'),
      {
        closedPanelLeft: Math.round(historyClosedState.panel.left),
        closedPanelWidth: Math.round(historyClosedState.panel.width),
        closedSurfaceWidth: Math.round(historyClosedState.surface.width),
        historyLeft: Math.round(state.history?.left || 0),
        historyRight: Math.round(state.history?.right || 0),
        openPanelLeft: Math.round(state.panel?.left || 0),
        openPanelWidth: Math.round(state.panel?.width || 0),
        openSurfaceWidth: Math.round(state.surface?.width || 0),
        topClass: state.historyTopElementClass,
        topText: state.historyTopElementText,
      },
    );
    assertCheck('history open does not split chat workspace', !state.hasWorkspaceHistoryClass, {
      workspaceGrid: state.workspaceGrid,
    });
    assertCheck(
      'history open keeps only the visible outer corners rounded',
      cssPx(state.history.borderTopLeftRadius) >= 6 &&
        cssPx(state.history.borderBottomLeftRadius) >= 6 &&
        cssPx(state.history.borderTopRightRadius) <= 1 &&
        cssPx(state.history.borderBottomRightRadius) <= 1 &&
        cssPx(state.panel.borderTopLeftRadius) <= 1 &&
        cssPx(state.panel.borderBottomLeftRadius) <= 1 &&
        cssPx(state.panel.borderTopRightRadius) >= 6 &&
        cssPx(state.panel.borderBottomRightRadius) >= 6,
      {
        historyBottomLeft: state.history.borderBottomLeftRadius,
        historyBottomRight: state.history.borderBottomRightRadius,
        historyTopLeft: state.history.borderTopLeftRadius,
        historyTopRight: state.history.borderTopRightRadius,
        panelBottomLeft: state.panel.borderBottomLeftRadius,
        panelBottomRight: state.panel.borderBottomRightRadius,
        panelTopLeft: state.panel.borderTopLeftRadius,
        panelTopRight: state.panel.borderTopRightRadius,
      },
    );

    await click(cdp, 'button[aria-label="Open full screen"]');
    await waitFor(cdp, 'fullscreen surface', "!!document.querySelector('.komsco-ai__surface--fullscreen')");
    await waitFor(
      cdp,
      'visible action lifecycle loaded in fullscreen rail',
      `(() => {
        const surface = document.querySelector('.komsco-ai__surface--fullscreen');
        const rail = surface?.querySelector('.komsco-ai__insight-rail');
        const lifecycle = surface?.querySelector('.komsco-ai__action-lifecycle');
        const rect = lifecycle?.getBoundingClientRect();
        return rail &&
          window.getComputedStyle(rail).display !== 'none' &&
          lifecycle &&
          rect.width > 0 &&
          rect.height > 0 &&
          lifecycle.getAttribute('data-action-executor-state') !== 'pending';
      })()`,
      15000,
    );
    state = await getUiState(cdp);
    assertCheck('fullscreen surface is portaled to body', state.surfaceParentTag === 'BODY', {
      surfaceParentTag: state.surfaceParentTag,
    });
    assertCheck('fullscreen history drawer overlays without resizing main panel', Boolean(state.history) && state.history.right < state.panel.right, {
      historyRight: Math.round(state.history?.right || 0),
      panelLeft: Math.round(state.panel?.left || 0),
      panelRight: Math.round(state.panel?.right || 0),
    });
    if (state.railDisplay !== 'none') {
      assertCheck('fullscreen keeps chat and right rail separate', state.chat.right <= state.rail.left + 2, {
        chatRight: Math.round(state.chat.right),
        railLeft: Math.round(state.rail.left),
      });
    }
    assertCheck(
      'visible fullscreen rail exposes action lifecycle in exact stage order',
      state.railDisplay !== 'none' &&
        state.actionLifecycle &&
        state.actionLifecycle.width > 0 &&
        state.actionLifecycle.height > 0 &&
        state.actionLifecycleStepCount === 4 &&
        state.actionLifecycleStepKeys.join('|') === 'proposal|plan|approval|execution' &&
        state.actionLifecycleStepRects.every((rect) => rect.width > 0 && rect.height > 0) &&
        ['Proposal', 'Sealed plan', 'Approval', 'Execution'].every((label) =>
          state.actionLifecycleText.includes(label),
        ),
      {
        actionLifecycleRect: state.actionLifecycle,
        actionLifecycleStepCount: state.actionLifecycleStepCount,
        actionLifecycleStepKeys: state.actionLifecycleStepKeys,
        actionLifecycleStepRects: state.actionLifecycleStepRects,
        railDisplay: state.railDisplay,
      },
    );
    assertCheck(
      'visible action lifecycle exposes stable local read-only gate states',
      state.actionLifecycleAttrs.actionExecutorState === 'not-configured' &&
        state.actionLifecycleAttrs.mutationFlagState === 'disabled' &&
        state.actionLifecycleAttrs.uiExecutionMode === 'read-only' &&
        state.actionLifecycleText.includes('Action Executor URL not configured') &&
        state.actionLifecycleText.includes('mutation execution disabled') &&
        state.actionLifecycleText.includes('read-only UI blocks proposal, approval, and execution mutations'),
      {
        actionLifecycleAttrs: state.actionLifecycleAttrs,
        actionLifecycleTextPreview: state.actionLifecycleText.slice(0, 640),
      },
    );
    assertCheck(
      'visible action lifecycle documents execute guard proof tokens',
      ['sealed-plan-digest', 'active-approval', 'evidence-freshness', 'ssar', 'mutation-flag'].every(
        (token) => state.actionLifecycleAttrs.executeGuard.includes(token),
      ) &&
        ['sealed plan digest', 'active approval', 'evidence freshness', 'SSAR', 'mutation flag'].every(
          (label) => state.actionLifecycleText.includes(label),
        ) &&
        state.actionLifecycleText.includes('Expired or stale evidence blocks execution') &&
        state.actionLifecycleText.includes('create a new plan and approval'),
      {
        actionLifecycleAttrs: state.actionLifecycleAttrs,
        actionLifecycleTextPreview: state.actionLifecycleText.slice(0, 720),
      },
    );
    assertCheck('visible insight rail action lifecycle has no horizontal overflow', state.railHorizontalOverflow <= 1, {
      railDisplay: state.railDisplay,
      railHorizontalOverflow: state.railHorizontalOverflow,
    });
    const fullscreenShot = await screenshot(cdp, '.tmp-aiops-kugnus-ui-verify-fullscreen.png');
    record('fullscreen screenshot saved', true, { path: fullscreenShot });

    await click(cdp, 'button[aria-label="Exit full screen"]');
    await waitFor(cdp, 'exit fullscreen', "!document.querySelector('.komsco-ai__surface--fullscreen')");

    state = await getUiState(cdp);
    if (state.surfaceClasses.includes('komsco-ai__surface--resize-unlocked')) {
      await click(cdp, 'button[aria-label="창 크기 잠금"]');
      await waitFor(cdp, 'resize locked', `!(${activeSurfaceExpression})?.className.includes('komsco-ai__surface--resize-unlocked')`);
    }
    state = await getUiState(cdp);
    assertCheck('resize is locked by default', state.surface.resize === 'none', { resize: state.surface.resize });

    const lockedBeforeUnlock = state;
    await click(cdp, 'button[aria-label="창 크기 잠금 해제"]');
    await waitFor(cdp, 'resize unlocked', `(${activeSurfaceExpression})?.className.includes('komsco-ai__surface--resize-unlocked')`);
    const beforeResize = await getUiState(cdp);
    assertCheck(
      'resize unlock keeps current panel size unchanged',
      Math.abs(beforeResize.surface.height - lockedBeforeUnlock.surface.height) <= 2 &&
        Math.abs(beforeResize.surface.width - lockedBeforeUnlock.surface.width) <= 2,
      {
        beforeHeight: Math.round(lockedBeforeUnlock.surface.height),
        afterHeight: Math.round(beforeResize.surface.height),
        beforeWidth: Math.round(lockedBeforeUnlock.surface.width),
        afterWidth: Math.round(beforeResize.surface.width),
      },
    );
    const expectedResize = 'both';
    assertCheck('resize unlock uses correct resize axis', beforeResize.surface.resize === expectedResize, {
      resize: beforeResize.surface.resize,
      isEmbedded: beforeResize.isEmbedded,
    });
    assertCheck(
      'resize unlock exposes edge and corner cursors',
      beforeResize.resizeHandleCount === 8 &&
        beforeResize.resizeHandleCursors.includes('ns-resize') &&
        beforeResize.resizeHandleCursors.includes('ew-resize') &&
        beforeResize.resizeHandleCursors.includes('nwse-resize') &&
        beforeResize.resizeHandleCursors.includes('nesw-resize'),
      {
        cursors: beforeResize.resizeHandleCursors,
        resizeHandleCount: beforeResize.resizeHandleCount,
      },
    );

    await dragResizeHandle(cdp, beforeResize.isEmbedded ? 80 : 70, 90);
    const afterResize = await getUiState(cdp);
    assertCheck('resize handle changes panel height', afterResize.surface.height >= beforeResize.surface.height + 24, {
      beforeHeight: Math.round(beforeResize.surface.height),
      afterHeight: Math.round(afterResize.surface.height),
    });
    if (beforeResize.isEmbedded) {
      assertCheck('embedded resize does not create horizontal page overflow', afterResize.documentOverflowWidth <= 1, {
        overflowWidth: afterResize.documentOverflowWidth,
        beforeWidth: Math.round(beforeResize.surface.width),
        afterWidth: Math.round(afterResize.surface.width),
      });
    }
    const resizeShot = await screenshot(cdp, '.tmp-aiops-kugnus-ui-verify-resize.png');
    record('resize screenshot saved', true, { path: resizeShot });

    await click(cdp, 'button[aria-label="창 크기 잠금"]');
    await waitFor(cdp, 'resize relocked', `!(${activeSurfaceExpression})?.className.includes('komsco-ai__surface--resize-unlocked')`);
    state = await getUiState(cdp);
    assertCheck(
      'resize lock keeps current panel size unchanged',
      Math.abs(state.surface.height - afterResize.surface.height) <= 2 &&
        Math.abs(state.surface.width - afterResize.surface.width) <= 2,
      {
        beforeHeight: Math.round(afterResize.surface.height),
        afterHeight: Math.round(state.surface.height),
        beforeWidth: Math.round(afterResize.surface.width),
        afterWidth: Math.round(state.surface.width),
      },
    );
    assertCheck('resize lock disables manual resize again', state.surface.resize === 'none', {
      resize: state.surface.resize,
    });

    const composerGaps = {
      bottom: state.composerWrap.bottom - state.inputBox.bottom,
      left: state.inputBox.left - state.composerWrap.left,
      right: state.composerWrap.right - state.inputBox.right,
      top: state.inputBox.top - state.composerWrap.top,
    };
    const composerGapValues = Object.values(composerGaps);
    assertCheck(
      'composer spacing is balanced around one visible input box',
      composerGapValues.every((gap) => gap >= 6 && gap <= 12) &&
        Math.max(...composerGapValues) - Math.min(...composerGapValues) <= 4,
      {
        bottomGap: Math.round(composerGaps.bottom),
        leftGap: Math.round(composerGaps.left),
        rightGap: Math.round(composerGaps.right),
        topGap: Math.round(composerGaps.top),
      },
    );
    const inputBorderRgb = parseRgb(state.inputBox.borderTopColor);
    const inputBorderIsBlackish = inputBorderRgb && inputBorderRgb.every((channel) => channel <= 65);
    assertCheck(
      'composer border uses neutral UI color instead of black',
      Boolean(inputBorderRgb) && !inputBorderIsBlackish,
      {
        inputBorderColor: state.inputBox.borderTopColor,
      },
    );
    assertCheck(
      'composer text has breathing room inside the border',
      Number.parseFloat(state.textarea.paddingLeft) >= 10 &&
        Number.parseFloat(state.textarea.paddingTop) >= 10,
      {
        textareaPaddingLeft: state.textarea.paddingLeft,
        textareaPaddingTop: state.textarea.paddingTop,
      },
    );
    assertCheck(
      'composer uses a single visible input border',
      Number.parseFloat(state.textarea.borderTopWidth) === 0 &&
        Number.parseFloat(state.textarea.borderRightWidth) === 0 &&
        Number.parseFloat(state.textarea.borderBottomWidth) === 0 &&
        Number.parseFloat(state.textarea.borderLeftWidth) === 0 &&
        (state.textarea.boxShadow === 'none' || state.textarea.boxShadow === '') &&
        (state.textarea.outlineStyle === 'none' || Number.parseFloat(state.textarea.outlineWidth) === 0),
      {
        boxShadow: state.textarea.boxShadow,
        borderBottomWidth: state.textarea.borderBottomWidth,
        borderLeftWidth: state.textarea.borderLeftWidth,
        borderRightWidth: state.textarea.borderRightWidth,
        borderTopWidth: state.textarea.borderTopWidth,
        outlineStyle: state.textarea.outlineStyle,
        outlineWidth: state.textarea.outlineWidth,
      },
    );

    assertCheck('composer quick prompts are hidden behind the plus menu', state.inlineQuickPromptCount === 0, {
      inlineQuickPromptCount: state.inlineQuickPromptCount,
    });
    assertCheck('composer keeps image attachment control visible', state.attachExists && state.fileInputExists, {
      attachExists: state.attachExists,
      fileInputExists: state.fileInputExists,
    });
    assertCheck('composer task mode defaults to Ask', state.taskModeValue === 'ask' && state.taskModeText.includes('Ask'), {
      taskModeText: state.taskModeText,
      taskModeValue: state.taskModeValue,
    });

    await click(cdp, '.komsco-ai__quick-menu-trigger');
    await waitFor(
      cdp,
      'quick prompt menu opens',
      `(() => {
        const surface = ${activeSurfaceExpression};
        return (surface?.querySelectorAll('.komsco-ai__quick-menu-item') || []).length === 4;
      })()`,
      5000,
    );
    state = await getUiState(cdp);
    assertCheck(
      'composer plus menu contains frequent operation prompts',
      state.quickMenuItemCount === 4 &&
        ['Node 상태', '최근 경고', '조치 절차', '조치 후보 검토'].every((label) =>
          state.quickMenuItemLabels.includes(label),
        ),
      {
        quickMenuExpanded: state.quickMenuExpanded,
        quickMenuItemCount: state.quickMenuItemCount,
        quickMenuItemLabels: state.quickMenuItemLabels,
      },
    );

    await click(cdp, '.komsco-ai__quick-menu-trigger');
    await click(cdp, '.komsco-ai__task-mode-button');
    await waitFor(
      cdp,
      'task mode menu opens',
      `(() => {
        const surface = ${activeSurfaceExpression};
        return (surface?.querySelectorAll('.komsco-ai__task-mode-option') || []).length === 2;
      })()`,
      5000,
    );
    state = await getUiState(cdp);
    assertCheck(
      'composer exposes Ask and Troubleshooting task modes',
      state.taskModeOptionCount === 2 &&
        state.taskModeOptionValues.includes('ask') &&
        state.taskModeOptionValues.includes('troubleshooting'),
      {
        taskModeOptionCount: state.taskModeOptionCount,
        taskModeOptionValues: state.taskModeOptionValues,
      },
    );
    await click(cdp, '[data-komsco-task-mode="troubleshooting"]');
    state = await getUiState(cdp);
    assertCheck(
      'composer task mode switches to Troubleshooting',
      state.taskModeValue === 'troubleshooting' && state.taskModeText.includes('Troubleshooting'),
      {
        taskModeText: state.taskModeText,
        taskModeValue: state.taskModeValue,
      },
    );
    await click(cdp, '.komsco-ai__task-mode-button');
    await waitFor(
      cdp,
      'task mode menu reopens',
      `(() => {
        const surface = ${activeSurfaceExpression};
        return (surface?.querySelectorAll('.komsco-ai__task-mode-option') || []).length === 2;
      })()`,
      5000,
    );
    await click(cdp, '[data-komsco-task-mode="ask"]');
    state = await getUiState(cdp);

    if (state.inputExists) {
      assertCheck('composer send starts disabled without prompt', state.sendDisabled === true, {
        sendDisabled: state.sendDisabled,
      });
    }

    await setComposerText(cdp, '현재 연결 상태를 한 줄로만 확인해줘');
    await waitFor(
      cdp,
      'composer send enabled after input',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const send = surface?.querySelector('.komsco-ai__send');
        return Boolean(send) && send.disabled !== true && send.getAttribute('aria-disabled') !== 'true';
      })()`,
      5000,
    );
    let chatState = await getChatInteractionState(cdp);
    assertCheck('composer send enables when prompt is entered', chatState.sendDisabled === false, {
      sendDisabled: chatState.sendDisabled,
      inputValue: chatState.inputValue,
    });

    const messageCountBeforeSend = chatState.messageCount;
    await click(cdp, '.komsco-ai__send');
    await waitFor(
      cdp,
      'composer send becomes stop while streaming',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const send = surface?.querySelector('.komsco-ai__send');
        return send?.getAttribute('aria-label') === '응답 중지'
          || String(send?.className || '').includes('komsco-ai__send--stop');
      })()`,
      8000,
    );
    chatState = await getChatInteractionState(cdp);
    assertCheck('composer send button turns into stop during response', chatState.sendAria === '응답 중지', {
      sendAria: chatState.sendAria,
      sendClass: chatState.sendClass,
    });

    await click(cdp, '.komsco-ai__send');
    await waitFor(
      cdp,
      'composer returns to send after stop',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const send = surface?.querySelector('.komsco-ai__send');
        return send?.getAttribute('aria-label') === '질문 전송'
          && !String(send?.className || '').includes('komsco-ai__send--stop');
      })()`,
      12000,
    );
    chatState = await getChatInteractionState(cdp);
    assertCheck('composer stop returns control to normal send button', chatState.sendAria === '질문 전송', {
      sendAria: chatState.sendAria,
      sendClass: chatState.sendClass,
    });
    assertCheck('chat interaction creates visible conversation messages', chatState.messageCount >= messageCountBeforeSend + 1, {
      before: messageCountBeforeSend,
      after: chatState.messageCount,
      messages: chatState.messages.slice(-3),
    });
    const latestAssistantMessage = [...chatState.messages]
      .reverse()
      .find((message) => String(message.cls || '').includes('komsco-ai__message--assistant'));
    assertCheck(
      'assistant answer label is KOMSCO AI AGENT',
      latestAssistantMessage?.labelText === 'KOMSCO AI AGENT',
      {
        labelText: latestAssistantMessage?.labelText,
      },
    );
    assertCheck(
      'assistant K logo sits in the answer header without indenting content',
      Boolean(latestAssistantMessage?.avatar) &&
        Boolean(latestAssistantMessage?.content) &&
        Math.abs(latestAssistantMessage.content.left - latestAssistantMessage.message.left) <= 2 &&
        latestAssistantMessage.avatar.top <= latestAssistantMessage.content.top,
      {
        avatarTop: Math.round(latestAssistantMessage?.avatar?.top || 0),
        contentLeft: Math.round(latestAssistantMessage?.content?.left || 0),
        contentTop: Math.round(latestAssistantMessage?.content?.top || 0),
        messageLeft: Math.round(latestAssistantMessage?.message?.left || 0),
      },
    );

    await setComposerText(cdp, 'aiops-two-pod-exec 파드 몇개 띄었어?');
    await waitFor(
      cdp,
      'composer send enables for RCA semantic check',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const send = surface?.querySelector('.komsco-ai__send');
        return send && !send.disabled && send.getAttribute('aria-disabled') !== 'true';
      })()`,
      5000,
    );
    await click(cdp, '.komsco-ai__send');
    await waitFor(
      cdp,
      'RCA semantic check finishes streaming',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const send = surface?.querySelector('.komsco-ai__send');
        return send?.getAttribute('aria-label') === '질문 전송';
      })()`,
      60000,
    );
    await waitFor(
      cdp,
      'assistant rail exposes RCA Context collected evidence counters',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const railText = surface?.querySelector('.komsco-ai__insight-rail')?.textContent || '';
        const collected = Number((railText.match(/Collected\\s*([0-9]+)/i) || [])[1] || 0);
        return railText.includes('RCA Context')
          && collected > 0
          && /Missing\\s*[0-9]+/i.test(railText);
      })()`,
      15000,
    );
    state = await getUiState(cdp);
    const railCollectedCount = counterAfterLabel(state.railText, 'Collected');
    const railMissingCount = counterAfterLabel(state.railText, 'Missing');
    assertCheck(
      'assistant rail exposes RCA Context collected evidence counters',
      state.railText.includes('RCA Context') &&
        railCollectedCount > 0 &&
        railMissingCount >= 0,
      {
        railCollectedCount,
        railMissingCount,
        railTextPreview: state.railText.slice(0, 360),
      },
    );
    chatState = await getChatInteractionState(cdp);
    const rcaAssistantMessage = [...chatState.messages]
      .reverse()
      .find((message) => String(message.cls || '').includes('komsco-ai__message--assistant'));
    const evidenceFooter = rcaAssistantMessage?.evidenceFooter;
    const rcaText = rcaAssistantMessage?.text || '';
    const requiredRcaSections = [
      'RCA 보고서',
      '우선 판단',
      '수집 근거',
      '원인 후보',
      '확인 불가',
      '다음 확인',
      '우선순위',
    ];
    const structuredBlockCount =
      (rcaAssistantMessage?.formattedHeadingCount || 0) +
      (rcaAssistantMessage?.formattedListCount || 0) +
      (rcaAssistantMessage?.formattedCodeBlockCount || 0) +
      (rcaAssistantMessage?.formattedTableCount || 0);
    const hasRcaOperationsReport =
      requiredRcaSections.every((section) => rcaText.includes(section)) && structuredBlockCount >= 3;
    const hasDirectStatusAnswer =
      /aiops-two-pod-exec/.test(rcaText) &&
      /총\s*3개|Running\s*3개|Ready\s*3\/3/.test(rcaText) &&
      (rcaAssistantMessage?.formattedTableCount || 0) >= 1 &&
      /read-only|변경 조치는 수행하지 않았습니다/.test(rcaText);
    assertCheck(
      'assistant answer uses the correct operations structure for the question type',
      hasRcaOperationsReport || hasDirectStatusAnswer,
      {
        codeBlocks: rcaAssistantMessage?.formattedCodeBlockCount,
        hasDirectStatusAnswer,
        hasRcaOperationsReport,
        headings: rcaAssistantMessage?.formattedHeadingCount,
        lists: rcaAssistantMessage?.formattedListCount,
        missingSections: requiredRcaSections.filter((section) => !rcaText.includes(section)),
        structuredBlockCount,
        tables: rcaAssistantMessage?.formattedTableCount,
        textPreview: rcaText.slice(0, 420),
      },
    );
    assertCheck(
      'assistant RCA answer keeps mutation commands out of read-only guidance',
      !/oc\\s+(apply|delete|patch|scale|exec)\\b/i.test(rcaText) &&
        !/실행\\s*(완료|했습니다)|적용\\s*(완료|했습니다)|삭제\\s*(완료|했습니다)/.test(rcaText),
      {
        textPreview: rcaText.slice(0, 520),
      },
    );
    assertCheck(
      'assistant answer exposes compact evidence footer with trace id',
      Boolean(evidenceFooter) &&
        /근거/.test(evidenceFooter.text) &&
        /수집\s*[1-9]/.test(evidenceFooter.text) &&
        /추가 확인\s*[0-9]/.test(evidenceFooter.text) &&
        (evidenceFooter.contextId.startsWith('rca-') || evidenceFooter.digest.startsWith('sha256:')),
      {
        contextId: evidenceFooter?.contextId,
        digestPreview: evidenceFooter?.digest?.slice(0, 24),
        footerText: evidenceFooter?.text?.slice(0, 420),
      },
    );
    state = await getUiState(cdp);
    assertCheck(
      'direct Gateway RCA answer is not labelled as Lightspeed fallback',
      rcaAssistantMessage?.fallbackBadgeText !== 'Gateway fallback' &&
        !state.headerStatusLabel.includes('Gateway fallback active'),
      {
        fallbackBadgeText: rcaAssistantMessage?.fallbackBadgeText,
        headerStatusLabel: state.headerStatusLabel,
      },
    );
    assertCheck(
      'assistant evidence footer separates collected and missing evidence without crowding answer',
      Boolean(evidenceFooter) &&
        evidenceFooter.collectedNumber >= 1 &&
        evidenceFooter.missingNumber >= 0 &&
        evidenceFooter.collectedCount >= 1 &&
        evidenceFooter.missingCount >= 0 &&
        evidenceFooter.refCount >= 1 &&
        evidenceFooter.rect &&
        evidenceFooter.rect.width <= rcaAssistantMessage.message.width + 1 &&
        evidenceFooter.rect.height <= 140,
      {
        collectedPills: evidenceFooter?.collectedCount,
        footerHeight: evidenceFooter?.rect?.height,
        messageWidth: rcaAssistantMessage?.message?.width,
        missingPills: evidenceFooter?.missingCount,
        refCount: evidenceFooter?.refCount,
      },
    );
    assertCheck(
      'assistant distinguishes no-evidence stopped answer from collected evidence footer',
      chatState.messages.some((message) =>
        String(message.cls || '').includes('komsco-ai__message--assistant') &&
        /응답 생성을 중지했습니다|오류 확인 필요/.test(message.text || '') &&
        (!message.evidenceFooter ||
          (message.evidenceFooter.collectedNumber === 0 && message.evidenceFooter.refCount === 0)),
      ) &&
        Boolean(evidenceFooter) &&
        evidenceFooter.collectedNumber > 0 &&
        evidenceFooter.missingNumber >= 0 &&
        evidenceFooter.refCount > 0,
      {
        noEvidenceAssistantMessages: chatState.messages.filter((message) =>
          String(message.cls || '').includes('komsco-ai__message--assistant') &&
          (!message.evidenceFooter ||
            (message.evidenceFooter.collectedNumber === 0 && message.evidenceFooter.refCount === 0)),
        ).length,
        withEvidenceFooterText: evidenceFooter?.text?.slice(0, 240),
      },
    );
    assertCheck(
      'assistant evidence footer redacts sensitive identity and token-like values',
      Boolean(evidenceFooter) &&
        !/Bearer\s+[A-Za-z0-9._~+/=-]+/i.test(evidenceFooter.text) &&
        !/sha256~[A-Za-z0-9._~-]+/i.test(evidenceFooter.text) &&
        !/\b(admin|kubeadmin)\b/i.test(evidenceFooter.text) &&
        !/@/.test(evidenceFooter.text),
      {
        footerText: evidenceFooter?.text?.slice(0, 420),
      },
    );
    const copiedEvidenceText = await evaluate(
      cdp,
      `(async () => {
        const surface = ${activeSurfaceExpression};
        const messages = [...(surface?.querySelectorAll('.komsco-ai__message--assistant') || [])];
        const target = messages.reverse().find((message) =>
          message.querySelector('.komsco-ai__evidence-footer .komsco-ai__evidence-ref')
        );
        const copyButton = target?.querySelector('.komsco-ai__message-copy');
        if (!target || !copyButton) {
          return { copied: '', patched: false, reason: 'copy target not found' };
        }

        const originalClipboard = navigator.clipboard;
        let copied = '';
        Object.defineProperty(navigator, 'clipboard', {
          configurable: true,
          value: {
            writeText: async (value) => {
              copied = String(value || '');
            },
          },
        });

        copyButton.click();
        await new Promise((resolve) => setTimeout(resolve, 150));

        if (originalClipboard) {
          Object.defineProperty(navigator, 'clipboard', {
            configurable: true,
            value: originalClipboard,
          });
        }

        return { copied, patched: true };
      })()`,
    );
    assertCheck(
      'assistant copy text includes evidence block without sensitive values',
      Boolean(copiedEvidenceText?.copied) &&
        copiedEvidenceText.copied.includes('[Evidence]') &&
        /additional_check_required:\s*[0-9]+/.test(copiedEvidenceText.copied) &&
        !/Bearer\s+[A-Za-z0-9._~+/=-]+/i.test(copiedEvidenceText.copied) &&
        !/sha256~[A-Za-z0-9._~-]+/i.test(copiedEvidenceText.copied) &&
        !/\b(admin|kubeadmin)\b/i.test(copiedEvidenceText.copied) &&
        !/@/.test(copiedEvidenceText.copied),
      {
        copiedPreview: copiedEvidenceText?.copied?.slice(0, 420),
        patched: copiedEvidenceText?.patched,
        reason: copiedEvidenceText?.reason,
      },
    );
    const evidenceFooterShot = await screenshot(cdp, '.tmp-aiops-kugnus-ui-verify-evidence-footer.png');
    record('evidence footer screenshot saved', true, { path: evidenceFooterShot });
    if (isAiopsDashboardRoute) {
      const dashboardRefreshClicked = await evaluate(
        cdp,
        `(() => {
          const button = [...document.querySelectorAll('button')]
            .find((node) => node.textContent?.includes('새로고침'));
          if (!button || button.disabled) return false;
          button.click();
          return true;
        })()`,
      );
      assertCheck('dashboard refresh button updates status after RCA chat event', dashboardRefreshClicked);
      await waitFor(
        cdp,
        'dashboard RCA Context JSON exposes collected evidence trace fields',
        `(() => {
          const title = [...document.querySelectorAll('.komsco-ai-page__panel-heading h2')]
            .find((node) => node.textContent?.trim() === 'RCA Context JSON');
          const text = title?.closest('section')?.textContent || '';
          return /"kind"\\s*:\\s*"RcaContext"/.test(text)
            && /"digest"\\s*:/.test(text)
            && /"contextId"\\s*:/.test(text)
            && /"evidence_refs"\\s*:/.test(text)
            && /"collectedRefs"\\s*:\\s*\\[\\s*\\{/.test(text)
            && /"failedRefs"\\s*:/.test(text)
            && /"missing"\\s*:/.test(text);
        })()`,
        15000,
      );
      dashboardState = await getDashboardState(cdp);
      assertCheck(
        'dashboard RCA Context JSON keeps real trace fields for collected, failed, and missing evidence',
        rcaContextTextHasTraceFields(dashboardState.rcaContextText) &&
          /"collectedRefs"\s*:\s*\[\s*\{/.test(dashboardState.rcaContextText),
        {
          rcaContextTextPreview: dashboardState.rcaContextText.slice(0, 720),
        },
      );
      assertCheck(
        'dashboard Evidence posture exposes positive collected evidence after RCA chat event',
        /[1-9][0-9]*\s*collected/i.test(dashboardState.evidencePanelText),
        {
          evidencePanelText: dashboardState.evidencePanelText,
        },
      );
    } else {
      record('console dashboards route uses assistant evidence footer as Stage 2 proof', true, {
        url: uiUrl,
      });
    }

    await setComposerText(cdp, '최근 OpenShift 경고와 우선 확인할 항목을 정리해줘.');
    await waitFor(
      cdp,
      'composer send enables for Lightspeed fallback check',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const send = surface?.querySelector('.komsco-ai__send');
        return send && !send.disabled && send.getAttribute('aria-disabled') !== 'true';
      })()`,
      5000,
    );
    await click(cdp, '.komsco-ai__send');
    await waitFor(
      cdp,
      'Lightspeed fallback check finishes streaming',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const send = surface?.querySelector('.komsco-ai__send');
        return send?.getAttribute('aria-label') === '질문 전송';
      })()`,
      60000,
    );
    state = await getUiState(cdp);
    chatState = await getChatInteractionState(cdp);
    const fallbackAssistantMessage = [...chatState.messages]
      .reverse()
      .find((message) => String(message.cls || '').includes('komsco-ai__message--assistant'));
    assertCheck(
      'Lightspeed fallback is visibly labelled when Gateway answers from local evidence',
      fallbackAssistantMessage?.fallbackBadgeText === 'Gateway fallback' &&
        state.headerStatusLabel.includes('Gateway fallback active') &&
        state.headerStatusLabel.includes('Lightspeed stream'),
      {
        fallbackBadgeText: fallbackAssistantMessage?.fallbackBadgeText,
        headerStatusLabel: state.headerStatusLabel,
        latestAssistantText: fallbackAssistantMessage?.text?.slice(0, 360),
      },
    );

    await makeConversationScrollableAndScrollUp(cdp);
    await waitFor(
      cdp,
      'scroll-to-bottom button appears after manual scroll up',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const button = surface?.querySelector('.komsco-ai__scroll-bottom');
        if (!button) return false;
        const r = button.getBoundingClientRect();
        const style = window.getComputedStyle(button);
        return r.width > 0 && r.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
      })()`,
      5000,
    );
    let scrollState = await evaluate(
      cdp,
      `(() => {
        const surface = ${activeSurfaceExpression};
        const body = surface?.querySelector('.komsco-ai__body');
        const button = surface?.querySelector('.komsco-ai__scroll-bottom');
        return {
          buttonVisible: Boolean(button),
          scrollTop: Math.round(body?.scrollTop || 0),
          distanceToBottom: Math.round((body?.scrollHeight || 0) - (body?.scrollTop || 0) - (body?.clientHeight || 0)),
        };
      })()`,
    );
    assertCheck('scroll up unlocks bottom lock and shows jump button', scrollState.buttonVisible === true && scrollState.distanceToBottom > 90, scrollState);

    await click(cdp, '.komsco-ai__scroll-bottom');
    await sleep(800);
    scrollState = await evaluate(
      cdp,
      `(() => {
        const surface = ${activeSurfaceExpression};
        const body = surface?.querySelector('.komsco-ai__body');
        const button = surface?.querySelector('.komsco-ai__scroll-bottom');
        return {
          buttonVisible: Boolean(button),
          scrollTop: Math.round(body?.scrollTop || 0),
          scrollHeight: Math.round(body?.scrollHeight || 0),
          clientHeight: Math.round(body?.clientHeight || 0),
          distanceToBottom: Math.round((body?.scrollHeight || 0) - (body?.scrollTop || 0) - (body?.clientHeight || 0)),
        };
      })()`,
    );
    record('scroll jump state after click', true, scrollState);
    await waitFor(
      cdp,
      'scroll-to-bottom button hides after jump',
      `(() => {
        const surface = ${activeSurfaceExpression};
        const body = surface?.querySelector('.komsco-ai__body');
        const button = surface?.querySelector('.komsco-ai__scroll-bottom');
        const distanceToBottom = (body?.scrollHeight || 0) - (body?.scrollTop || 0) - (body?.clientHeight || 0);
        return !button && distanceToBottom <= 24;
      })()`,
      6000,
    );
    scrollState = await evaluate(
      cdp,
      `(() => {
        const surface = ${activeSurfaceExpression};
        const body = surface?.querySelector('.komsco-ai__body');
        const button = surface?.querySelector('.komsco-ai__scroll-bottom');
        return {
          buttonVisible: Boolean(button),
          scrollTop: Math.round(body?.scrollTop || 0),
          distanceToBottom: Math.round((body?.scrollHeight || 0) - (body?.scrollTop || 0) - (body?.clientHeight || 0)),
        };
      })()`,
    );
    assertCheck('jump button returns conversation to latest message', scrollState.buttonVisible === false && scrollState.distanceToBottom <= 24, scrollState);

    await cdp.send('Page.navigate', { url: new URL('/dashboards', uiUrl).toString() });
    await waitFor(cdp, 'dashboard page reload', "document.readyState === 'complete'");
    try {
      await waitFor(
        cdp,
        'floating assistant after console refresh',
        "!!document.querySelector('.komsco-ai:not(.komsco-ai--embedded) .komsco-ai__surface') || !!document.querySelector('.komsco-ai__fab')",
      );
    } catch (error) {
      cdp = await recoverLoadedAiopsPage(cdp);
      await waitFor(
        cdp,
        'floating assistant after console refresh',
        "!!document.querySelector('.komsco-ai:not(.komsco-ai--embedded) .komsco-ai__surface') || !!document.querySelector('.komsco-ai__fab')",
      );
      record('recovered loaded Cywell AI tab after refresh target stalled', true, {
        reason: error instanceof Error ? error.message : String(error),
      });
    }
    const refreshHasSurface = await evaluate(
      cdp,
      "!!document.querySelector('.komsco-ai:not(.komsco-ai--embedded) .komsco-ai__surface')",
    );
    if (!refreshHasSurface) {
      await click(cdp, '.komsco-ai__fab');
    }
    await waitFor(cdp, 'floating assistant surface', "!!document.querySelector('.komsco-ai:not(.komsco-ai--embedded) .komsco-ai__surface')");
    const floatingState = await getUiState(cdp);
    assertCheck(
      'floating header does not overlap or clip after refresh',
      !floatingState.isEmbedded &&
        floatingState.title === '' &&
        floatingState.logo.width >= 120 &&
        floatingState.brand.right <= floatingState.headerStatus.left + 2 &&
        floatingState.headerStatus.right <= floatingState.headerActions.left + 2,
      {
        actionsLeft: Math.round(floatingState.headerActions.left),
        brandRight: Math.round(floatingState.brand.right),
        brandWidth: Math.round(floatingState.brand.width),
        brandCopyWidth: Math.round(floatingState.brandCopy?.width || 0),
        headerStatusLeft: Math.round(floatingState.headerStatus.left),
        headerStatusRight: Math.round(floatingState.headerStatus.right),
        logoWidth: Math.round(floatingState.logo.width),
        title: floatingState.title,
      },
    );

    await click(cdp, 'button[aria-label="창 크기 잠금 해제"]');
    await waitFor(cdp, 'floating resize unlocked', `(${activeSurfaceExpression})?.className.includes('komsco-ai__surface--resize-unlocked')`);
    const floatingBeforeResize = await getUiState(cdp);
    assertCheck(
      'floating resize unlock exposes edge and corner cursors',
      !floatingBeforeResize.isEmbedded &&
        floatingBeforeResize.surface.resize === 'both' &&
        floatingBeforeResize.resizeHandleCount === 8 &&
        floatingBeforeResize.resizeHandleCursors.includes('ns-resize') &&
        floatingBeforeResize.resizeHandleCursors.includes('ew-resize') &&
        floatingBeforeResize.resizeHandleCursors.includes('nwse-resize') &&
        floatingBeforeResize.resizeHandleCursors.includes('nesw-resize'),
      {
        cursors: floatingBeforeResize.resizeHandleCursors,
        resize: floatingBeforeResize.surface.resize,
        resizeHandleCount: floatingBeforeResize.resizeHandleCount,
      },
    );
    await dragResizeHandle(cdp, 70, 70);
    const floatingAfterResize = await getUiState(cdp);
    assertCheck(
      'floating resize handle changes panel width and height',
      floatingAfterResize.surface.width > floatingBeforeResize.surface.width + 20 &&
        floatingAfterResize.surface.height > floatingBeforeResize.surface.height + 20,
      {
        afterHeight: Math.round(floatingAfterResize.surface.height),
        afterWidth: Math.round(floatingAfterResize.surface.width),
        beforeHeight: Math.round(floatingBeforeResize.surface.height),
        beforeWidth: Math.round(floatingBeforeResize.surface.width),
      },
    );
  } finally {
    await cdp.close();
  }

  const failed = results.filter((item) => !item.ok);
  console.log(
    JSON.stringify(
      {
        ok: failed.length === 0,
        checked: results.length,
        failed: failed.map((item) => item.name),
        url: uiUrl,
      },
      null,
      2,
    ),
  );

  if (failed.length > 0) {
    process.exitCode = 1;
  }
};

run().catch((error) => {
  record('kugnus ui verifier crashed', false, { message: error.message });
  console.log(
    JSON.stringify(
      {
        ok: false,
        checked: results.length,
        failed: results.filter((item) => !item.ok).map((item) => item.name),
        url: uiUrl,
      },
      null,
      2,
    ),
  );
  process.exitCode = 1;
});
