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
const screenshotDir = process.env.KUGNUS_UI_SCREENSHOT_DIR || process.cwd();
const autostartChrome = process.env.KUGNUS_UI_AUTOSTART_CHROME !== 'false';

const results = [];
let activeChromeHost = '127.0.0.1';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

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

  send(method, params = {}) {
    const id = this.nextId;
    this.nextId += 1;
    this.ws.send(JSON.stringify({ id, method, params }));

    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
  }

  async close() {
    if (this.ws) {
      this.ws.close();
    }
  }
}

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

const evaluate = async (cdp, expression) => {
  const result = await cdp.send('Runtime.evaluate', {
    expression,
    awaitPromise: true,
    returnByValue: true,
  });

  if (result.exceptionDetails) {
    const detail = result.exceptionDetails.exception?.description || result.exceptionDetails.text;
    throw new Error(detail);
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

const activeSurfaceExpression = `
  document.querySelector('.komsco-ai__surface--fullscreen')
  || document.querySelector('.komsco-ai--embedded .komsco-ai__surface')
  || document.querySelector('.komsco-ai__surface')
`;

const click = async (cdp, selector) => {
  const clicked = await evaluate(
    cdp,
    `(() => {
      const activeSurface = ${activeSurfaceExpression};
      const el = activeSurface?.querySelector(${JSON.stringify(selector)})
        || document.querySelector(${JSON.stringify(selector)});
      if (!el) return false;
      el.click();
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
      requestAnimationFrame(() => requestAnimationFrame(() => resolve(true)));
    }))()`,
  );

  if (!dragged) {
    throw new Error('Missing assistant surface for resize drag');
  }
  await sleep(300);
};

const setComposerText = async (cdp, text) => {
  const updated = await evaluate(
    cdp,
    `(() => {
      const surface = ${activeSurfaceExpression};
      const textarea = surface?.querySelector('textarea.komsco-ai__textarea, .komsco-ai__textarea textarea, textarea');
      if (!textarea) return false;
      textarea.focus();
      const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
      if (setter) {
        setter.call(textarea, ${JSON.stringify(text)});
      } else {
        textarea.value = ${JSON.stringify(text)};
      }
      textarea.dispatchEvent(new InputEvent('input', { bubbles: true, data: ${JSON.stringify(text)}, inputType: 'insertText' }));
      textarea.dispatchEvent(new Event('change', { bubbles: true }));
      return true;
    })()`,
  );

  if (!updated) {
    throw new Error('Missing chat composer textarea');
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
      const messages = [...(surface?.querySelectorAll('.komsco-ai__message') || [])].map((node) => ({
        cls: node.className,
        text: node.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim(),
      }));

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
  const shot = await cdp.send('Page.captureScreenshot', {
    format: 'png',
    captureBeyondViewport: false,
  });
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
          : surface?.querySelector(selector);
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
          display: style.display,
          resize: style.resize,
        };
      };

      const title = surface?.querySelector('.komsco-ai__title');
      const language = surface?.querySelector('.komsco-ai__language-button');
      const workspace = surface?.querySelector('.komsco-ai__workspace');
      const rail = surface?.querySelector('.komsco-ai__insight-rail');
      const input = surface?.querySelector('.komsco-ai__textarea textarea, textarea.komsco-ai__textarea');
      const send = surface?.querySelector('.komsco-ai__send');

      return {
        rootExists: Boolean(document.querySelector('.komsco-ai')),
        surfaceExists: Boolean(surface),
        surfaceParentTag: surface?.parentElement?.tagName || null,
        surfaceClasses: surface?.className || '',
        title: title?.textContent?.trim() || '',
        languageText: language?.textContent?.trim() || '',
        isEmbedded: Boolean(document.querySelector('.komsco-ai--embedded')),
        hasWorkspaceHistoryClass: Boolean(surface?.querySelector('.komsco-ai__workspace--history-open')),
        workspaceGrid: workspace ? window.getComputedStyle(workspace).gridTemplateColumns : null,
        documentOverflowWidth: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        surface: rectOf('.komsco-ai__surface'),
        toggle: rectOf('.komsco-ai__sidebar-toggle'),
        logo: rectOf('.komsco-ai__brand-logo'),
        brand: rectOf('.komsco-ai__brand'),
        history: rectOf('.komsco-ai__history-sidebar'),
        panel: rectOf('.komsco-ai__panel'),
        chat: rectOf('.komsco-ai__chat-column'),
        rail: rectOf('.komsco-ai__insight-rail'),
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

      return {
        title: document.querySelector('.komsco-ai-page h1')?.textContent?.trim() || '',
        pageExists: Boolean(document.querySelector('.komsco-ai-page')),
        healthScoreText: document.querySelector('.komsco-ai-page__health-dial strong')?.textContent?.trim() || '',
        overviewSideText: document.querySelector('.komsco-ai-page__overview-side')?.textContent?.trim() || '',
        floatingFabVisible: [...document.querySelectorAll('.komsco-ai:not(.komsco-ai--embedded) .komsco-ai__fab')]
          .some((el) => {
            const r = el.getBoundingClientRect();
            const style = window.getComputedStyle(el);
            return r.width > 0 && r.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
          }),
        overview: rectOf('.komsco-ai-page__overview'),
        metrics: rectOf('.komsco-ai-page__metrics'),
        assistant: rectOf('.komsco-ai-page__assistant-stage'),
        dashboardGrid: rectOf('.komsco-ai-page__dashboard-grid'),
        metricCount: document.querySelectorAll('.komsco-ai-page__metric').length,
        metricLabels: [...document.querySelectorAll('.komsco-ai-page__metric-label')].map((node) =>
          node.textContent?.replace(/[\\n\\r\\t ]+/g, ' ').trim(),
        ),
        panelHeadings: [...document.querySelectorAll('.komsco-ai-page__panel-heading h2')].map((node) =>
          node.textContent?.trim(),
        ),
        horizontalOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      };
    })()`,
  );

const run = async () => {
  await ensureChrome();
  const cdp = await openPage();

  try {
    await waitFor(cdp, 'Cywell AI root', "document.readyState === 'complete' && !!document.querySelector('.komsco-ai')");
    await evaluate(
      cdp,
      `(() => {
        document
          .querySelectorAll('.komsco-ai__surface--fullscreen button[aria-label="Exit full screen"]')
          .forEach((button) => button.click());
        document
          .querySelectorAll('.komsco-ai:not(.komsco-ai--embedded) .komsco-ai__surface button[aria-label="Close Cywell AI"]')
          .forEach((button) => button.click());
      })()`,
    );
    await waitFor(cdp, 'fullscreen cleanup', "!document.querySelector('.komsco-ai__surface--fullscreen')");

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

    const dashboardState = await getDashboardState(cdp);
    assertCheck('dashboard page is Cywell AI', dashboardState.pageExists && dashboardState.title.includes('Cywell AI'), {
      title: dashboardState.title,
    });
    assertCheck('dashboard route does not show duplicate global assistant FAB', !dashboardState.floatingFabVisible, {
      floatingFabVisible: dashboardState.floatingFabVisible,
    });
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
    assertCheck('dashboard exposes four primary metrics', dashboardState.metricCount >= 4, {
      metricCount: dashboardState.metricCount,
    });
    ['Ready nodes', 'Operator issues', 'Audit records', 'Action records'].forEach((metricLabel) => {
      assertCheck(`dashboard metric connected: ${metricLabel}`, dashboardState.metricLabels.includes(metricLabel), {
        metricLabels: dashboardState.metricLabels,
      });
    });
    ['Evidence posture', 'Lightspeed link', 'Tool Plan JSON', 'OS-aware adapters', 'Safety contract'].forEach(
      (heading) => {
        assertCheck(`dashboard panel present: ${heading}`, dashboardState.panelHeadings.includes(heading), {
          panelHeadings: dashboardState.panelHeadings,
        });
      },
    );
    assertCheck('dashboard has no horizontal overflow', dashboardState.horizontalOverflow <= 1, {
      horizontalOverflow: dashboardState.horizontalOverflow,
    });

    let state = await getUiState(cdp);
    assertCheck('assistant surface loaded', state.surfaceExists, { url: uiUrl });
    assertCheck('header title is Cywell AI', state.title === 'Cywell AI', { title: state.title });
    assertCheck('header sidebar toggle is left of KOMSCO logo', state.toggle.right <= state.logo.left, {
      toggleRight: Math.round(state.toggle.right),
      logoLeft: Math.round(state.logo.left),
      gap: Math.round(state.logo.left - state.toggle.right),
    });
    assertCheck('header keeps KOMSCO logo visible', state.logo.width >= 120 && state.logo.height >= 24, {
      logoWidth: Math.round(state.logo.width),
      logoHeight: Math.round(state.logo.height),
    });

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
    if (!state.surfaceClasses.includes('komsco-ai__surface--history-open')) {
      await click(cdp, '.komsco-ai__sidebar-toggle');
      await waitFor(cdp, 'history sidebar open', `(${activeSurfaceExpression})?.className.includes('komsco-ai__surface--history-open')`);
    }

    state = await getUiState(cdp);
    assertCheck('history sidebar opens as surface sibling', Boolean(state.history) && state.history.right <= state.panel.left + 2, {
      historyRight: Math.round(state.history?.right || 0),
      panelLeft: Math.round(state.panel?.left || 0),
    });
    assertCheck('history open does not split chat workspace', !state.hasWorkspaceHistoryClass, {
      workspaceGrid: state.workspaceGrid,
    });
    if (state.isEmbedded) {
      assertCheck('embedded history open hides right rail instead of squeezing chat', state.railDisplay === 'none', {
        railDisplay: state.railDisplay,
        workspaceGrid: state.workspaceGrid,
      });
    }

    await click(cdp, 'button[aria-label="Open full screen"]');
    await waitFor(cdp, 'fullscreen surface', "!!document.querySelector('.komsco-ai__surface--fullscreen')");
    state = await getUiState(cdp);
    assertCheck('fullscreen surface is portaled to body', state.surfaceParentTag === 'BODY', {
      surfaceParentTag: state.surfaceParentTag,
    });
    assertCheck('fullscreen keeps history and main panel separate', Boolean(state.history) && state.history.right <= state.panel.left + 2, {
      historyRight: Math.round(state.history?.right || 0),
      panelLeft: Math.round(state.panel?.left || 0),
    });
    if (state.railDisplay !== 'none') {
      assertCheck('fullscreen keeps chat and right rail separate', state.chat.right <= state.rail.left + 2, {
        chatRight: Math.round(state.chat.right),
        railLeft: Math.round(state.rail.left),
      });
    }
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

    await click(cdp, 'button[aria-label="창 크기 잠금 해제"]');
    await waitFor(cdp, 'resize unlocked', `(${activeSurfaceExpression})?.className.includes('komsco-ai__surface--resize-unlocked')`);
    const beforeResize = await getUiState(cdp);
    const expectedResize = beforeResize.isEmbedded ? 'vertical' : 'both';
    assertCheck('resize unlock uses correct resize axis', beforeResize.surface.resize === expectedResize, {
      resize: beforeResize.surface.resize,
      isEmbedded: beforeResize.isEmbedded,
    });

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
    assertCheck('resize lock disables manual resize again', state.surface.resize === 'none', {
      resize: state.surface.resize,
    });

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
