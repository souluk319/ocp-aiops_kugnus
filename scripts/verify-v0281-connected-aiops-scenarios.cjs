#!/usr/bin/env node

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const root = path.resolve(__dirname, '..');
const requireFirst = (candidates) => {
  const errors = [];
  for (const candidate of candidates) {
    try {
      return require(candidate);
    } catch (error) {
      errors.push(`${candidate}: ${error.message}`);
    }
  }
  throw new Error(`Unable to load module. Tried:\n${errors.join('\n')}`);
};

const WebSocket = requireFirst([
  'ws',
  path.join(root, 'komsco-ai-console-plugin', 'node_modules', 'ws'),
]);
const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const debugPort = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9375');
const expectedServer =
  process.env.KOMSCO_AIOPS_COMPANY_SERVER || 'https://api.ocp.cywell.server:6443';
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-v0281-connected-'));

const defaults = {
  cleanup: false,
  consoleUrl: process.env.AIOPS_CONSOLE_URL || 'http://localhost:9000/dashboards/aiops?codex_v=0281-connected',
  namespace: process.env.AIOPS_CONNECTED_NAMESPACE || '',
  report: path.join(root, 'docs', 'Ver.0.2.8.1', 'connected-aiops-scenario-test-report.json'),
  screenshotDir: path.join(root, 'docs', 'Ver.0.2.8.1', 'connected-aiops-screenshots'),
  session: process.env.AIOPS_CONNECTED_SESSION || '',
  setup: false,
};

const parseArgs = () => {
  const args = process.argv.slice(2);
  const parsed = { ...defaults };
  for (let index = 0; index < args.length; index += 1) {
    const item = args[index];
    if (item === '--setup') {
      parsed.setup = true;
    } else if (item === '--cleanup') {
      parsed.cleanup = true;
    } else if (item === '--namespace') {
      parsed.namespace = args[index + 1] || '';
      index += 1;
    } else if (item === '--session') {
      parsed.session = args[index + 1] || '';
      index += 1;
    } else if (item === '--report') {
      parsed.report = path.resolve(root, args[index + 1] || parsed.report);
      index += 1;
    } else if (item === '--screenshot-dir') {
      parsed.screenshotDir = path.resolve(root, args[index + 1] || parsed.screenshotDir);
      index += 1;
    } else if (item === '--console-url') {
      parsed.consoleUrl = args[index + 1] || parsed.consoleUrl;
      index += 1;
    } else if (item === '-h' || item === '--help') {
      console.log(`Usage: node scripts/verify-v0281-connected-aiops-scenarios.cjs [--setup] [--cleanup] [--namespace NAME --session SESSION]

Runs the connected OKD AIOps Copilot scenario against a safe aiops-copilot-e2e-* namespace.
Use --setup --cleanup for a full disposable run.`);
      process.exit(0);
    } else {
      throw new Error(`Unknown argument: ${item}`);
    }
  }
  return parsed;
};

const cli = parseArgs();
fs.mkdirSync(path.dirname(cli.report), { recursive: true });
fs.mkdirSync(cli.screenshotDir, { recursive: true });

const report = {
  apiVersion: 'aiops.komsco/v1',
  kind: 'ConnectedAIOpsScenarioTestReport',
  metadata: {
    createdAt: new Date().toISOString(),
    name: 'v0281-connected-aiops-scenario-test',
  },
  spec: {
    consoleUrl: cli.consoleUrl,
    expectedServer,
    namespace: cli.namespace,
    screenshotDir: path.relative(root, cli.screenshotDir),
    session: cli.session,
  },
  status: {
    completedAt: '',
    failures: [],
    screenshots: [],
    scenarios: [],
    state: 'running',
  },
};

let chromeProcess;
let chromeWebSocket;
let nextId = 1;
const pending = new Map();
const runtimeErrors = [];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const writeReport = (state = report.status.state) => {
  report.status.state = state;
  report.status.completedAt = new Date().toISOString();
  fs.writeFileSync(cli.report, `${JSON.stringify(report, null, 2)}\n`);
};

const rel = (file) => path.relative(root, file).replace(/\\/g, '/');

const addScenario = (id, title, state, evidence = {}) => {
  const existing = report.status.scenarios.find((item) => item.id === id);
  const payload = { evidence, id, state, title, updatedAt: new Date().toISOString() };
  if (existing) {
    Object.assign(existing, payload);
  } else {
    report.status.scenarios.push(payload);
  }
};

const fail = (message, evidence = undefined) => {
  const error = evidence === undefined ? new Error(message) : new Error(`${message}\n${JSON.stringify(evidence, null, 2)}`);
  error.evidence = evidence;
  throw error;
};

const assert = (condition, message, evidence = undefined) => {
  if (!condition) fail(message, evidence);
};

const run = (command, args, options = {}) => {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: 'utf8',
    maxBuffer: 10 * 1024 * 1024,
    timeout: options.timeout || 120000,
  });
  const payload = {
    command: [command, ...args].join(' '),
    code: result.status,
    stderr: (result.stderr || '').trim(),
    stdout: (result.stdout || '').trim(),
  };
  if (result.error) {
    throw new Error(`${payload.command} failed: ${result.error.message}`);
  }
  if (result.status !== 0 && !options.allowFailure) {
    throw new Error(`${payload.command} exited ${result.status}\n${payload.stderr || payload.stdout}`);
  }
  return payload;
};

const oc = (args, options = {}) => run('oc', args, options);

const runJson = (command, args) => {
  const result = run(command, args);
  const text = result.stdout.trim();
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`Failed to parse JSON from ${result.command}\n${text}`);
  }
};

const fetchTextStatus = async (url) => {
  const response = await fetch(url, { headers: { Accept: '*/*' } });
  return {
    contentType: response.headers.get('content-type') || '',
    ok: response.ok,
    status: response.status,
    text: await response.text(),
    url,
  };
};

const preflight = async () => {
  const server = oc(['whoami', '--show-server']).stdout;
  const userResult = oc(['whoami'], { allowFailure: true, timeout: 10000 });
  const user = userResult.stdout || 'unavailable';
  assert(server === expectedServer, 'refusing connected test on an unexpected OKD server', {
    expectedServer,
    server,
  });

  if (!cli.namespace || !cli.session) {
    fail('namespace and session are required unless --setup is used', {
      namespace: cli.namespace,
      session: cli.session,
    });
  }

  assert(/^aiops-copilot-e2e-[a-zA-Z0-9][a-zA-Z0-9-]{4,40}$/.test(cli.namespace), 'unsafe namespace name', {
    namespace: cli.namespace,
  });

  const namespaceJson = JSON.parse(oc(['get', 'namespace', cli.namespace, '-o', 'json']).stdout);
  const labels = namespaceJson.metadata?.labels || {};
  const expectedLabels = {
    'app.kubernetes.io/managed-by': 'komsco-aiops-test',
    'aiops.komsco/safe-delete': 'true',
    'aiops.komsco/test-suite': 'v0281-connected',
    'aiops.komsco/session': cli.session,
  };
  for (const [key, value] of Object.entries(expectedLabels)) {
    assert(labels[key] === value, `namespace safety label mismatch: ${key}`, { actual: labels[key], expected: value });
  }

  const checks = {
    createDeployment: oc(['auth', 'can-i', 'create', 'deployment', '-n', cli.namespace], { allowFailure: true }).stdout,
    getPods: oc(['auth', 'can-i', 'get', 'pods', '-n', cli.namespace], { allowFailure: true }).stdout,
    patchDeployment: oc(['auth', 'can-i', 'patch', 'deployment', '-n', cli.namespace], { allowFailure: true }).stdout,
  };
  assert(
    checks.getPods === 'yes' && checks.patchDeployment === 'yes',
    'current user cannot run the connected scenario inside the sandbox namespace',
    checks,
  );

  const consoleVersion = await fetchTextStatus('http://localhost:9000/api/kubernetes/version');
  const pluginEntry = await fetchTextStatus('http://localhost:9000/api/plugins/cywell-aiops-console-plugin/plugin-entry.js');
  const gatewayHealth = await fetchTextStatus(
    'http://localhost:9000/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/healthz',
  );
  assert(consoleVersion.ok && pluginEntry.ok && gatewayHealth.ok, 'local OKD console/plugin/gateway endpoints must be ready', {
    consoleVersion: consoleVersion.status,
    gatewayHealth: gatewayHealth.status,
    pluginEntry: pluginEntry.status,
  });

  report.status.cluster = {
    endpointChecks: {
      consoleVersion: consoleVersion.status,
      gatewayHealth: gatewayHealth.status,
      pluginEntry: pluginEntry.status,
    },
    server,
    user,
  };
  addScenario('01-preflight', 'Preflight', 'passed', report.status.cluster);
};

const getDeploymentReplicas = (name) => {
  const payload = JSON.parse(oc(['get', 'deployment', name, '-n', cli.namespace, '-o', 'json']).stdout);
  return {
    availableReplicas: payload.status?.availableReplicas || 0,
    generation: payload.metadata?.generation || 0,
    observedGeneration: payload.status?.observedGeneration || 0,
    readyReplicas: payload.status?.readyReplicas || 0,
    replicas: payload.spec?.replicas || 0,
  };
};

const getPodsText = () =>
  oc(['get', 'pods', '-n', cli.namespace, '-o', 'wide'], { allowFailure: true }).stdout;

const waitForJson = async (url, timeoutMs = 30000) => {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return response.json();
    } catch (_error) {
      // Retry until Chrome exposes the debugger endpoint.
    }
    await sleep(250);
  }
  throw new Error(`Timed out waiting for ${url}`);
};

const send = (method, params = {}) => {
  const id = nextId++;
  chromeWebSocket.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
};

const evaluate = async (expression, timeout = 20000) => {
  const result = await send('Runtime.evaluate', {
    awaitPromise: true,
    expression,
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
    if (predicate(last)) return last;
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${label}. Last=${JSON.stringify(last)}`);
};

const launchChrome = async () => {
  chromeProcess = spawn(
    chrome,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--window-size=1440,960',
      `--remote-debugging-port=${debugPort}`,
      `--user-data-dir=${userDataDir}`,
      cli.consoleUrl,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

  let stderr = '';
  chromeProcess.stderr.on('data', (chunk) => {
    stderr += String(chunk);
  });

  await waitForJson(`http://127.0.0.1:${debugPort}/json/version`, 60000);
  const targets = await waitForJson(`http://127.0.0.1:${debugPort}/json/list`, 60000);
  const targetPage = targets.find((item) => item.type === 'page') || targets[0];
  if (!targetPage?.webSocketDebuggerUrl) {
    throw new Error(`No page websocket target. Chrome stderr: ${stderr.slice(0, 1000)}`);
  }

  chromeWebSocket = new WebSocket(targetPage.webSocketDebuggerUrl);
  chromeWebSocket.on('message', (raw) => {
    const message = JSON.parse(String(raw));
    if (message.method === 'Runtime.exceptionThrown' || message.method === 'Log.entryAdded') {
      runtimeErrors.push(message.params);
      return;
    }
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result);
  });

  await new Promise((resolve, reject) => {
    chromeWebSocket.once('open', resolve);
    chromeWebSocket.once('error', reject);
  });

  await send('Page.enable');
  await send('Runtime.enable');
  await send('Log.enable');
  await poll(
    `document.readyState === 'complete' && Boolean(document.body?.innerText?.trim())`,
    Boolean,
    'OKD console page ready',
    90000,
  );
};

const screenshot = async (id, title) => {
  const file = path.join(cli.screenshotDir, `${id}.png`);
  const result = await send('Page.captureScreenshot', { format: 'png', fromSurface: true });
  fs.writeFileSync(file, Buffer.from(result.data, 'base64'));
  report.status.screenshots.push({ id, path: rel(file), title });
  return file;
};

const openAssistant = async () => {
  await poll(`Boolean(document.querySelector('.komsco-ai__fab'))`, Boolean, 'AIOps Copilot launcher', 60000);
  await evaluate(`(() => {
    const fab = document.querySelector('.komsco-ai__fab');
    fab?.click();
    return Boolean(document.querySelector('.komsco-ai__surface'));
  })()`);
  await poll(`Boolean(document.querySelector('.komsco-ai__surface'))`, Boolean, 'AIOps Copilot surface', 60000);
};

const resetCurrentConversation = async () => {
  await evaluate(`(() => {
    localStorage.removeItem('komsco-ai.assistant.active-conversation.v1');
    localStorage.setItem('komsco-ai.assistant.ui-language.v1', JSON.stringify('ko'));
    return true;
  })()`);
  await send('Page.reload', { ignoreCache: true });
  await poll(
    `document.readyState === 'complete' && Boolean(document.body?.innerText?.trim())`,
    Boolean,
    'OKD console reloaded',
    90000,
  );
  await openAssistant();
};

const setExecutionMode = async (mode) => {
  const labels = {
    execute: ['승인 후 실행 모드', '실행 가능', 'Approval-gated execution mode'],
    'read-only': ['읽기 전용 모드', '읽기 전용', 'Read-only mode'],
    unrestricted: ['실행 무제한 모드', '실행 무제한', 'Unrestricted execution mode'],
  }[mode];
  const clicked = await evaluate(`(() => {
    const labels = ${JSON.stringify(labels)};
    const button = Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button'))
      .find((el) => labels.some((label) => (el.getAttribute('aria-label') || el.textContent || '').includes(label)));
    if (!button) {
      return { ok: false, labels: Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button')).map((el) => el.getAttribute('aria-label') || el.textContent.trim()) };
    }
    button.click();
    return { ok: true };
  })()`);
  assert(clicked?.ok, `execution mode ${mode} must be selectable`, clicked);
  await sleep(500);
};

const setComposerValue = async (question) => {
  const changed = await evaluate(`(() => {
    const textarea = document.querySelector('.komsco-ai__composer textarea');
    if (!textarea) return { ok: false, reason: 'missing textarea' };
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    setter?.call(textarea, ${JSON.stringify(question)});
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.dispatchEvent(new Event('change', { bubbles: true }));
    return { ok: true, value: textarea.value };
  })()`);
  assert(changed?.ok && changed.value === question, 'composer must accept the connected scenario question', changed);
  await poll(
    `(() => {
      const sendButton = document.querySelector('.komsco-ai__send');
      const textarea = document.querySelector('.komsco-ai__composer textarea');
      return { disabled: Boolean(sendButton?.disabled), value: textarea?.value || '' };
    })()`,
    (value) => value?.value === question && value?.disabled === false,
    'send button enabled',
    10000,
  );
};

const sendQuestion = async (mode, question, label) => {
  await resetCurrentConversation();
  await setExecutionMode(mode);
  await setComposerValue(question);
  await evaluate(`document.querySelector('.komsco-ai__send')?.click(); true;`);
  return poll(
    `(() => {
      const assistantMessages = Array.from(document.querySelectorAll('.komsco-ai__message--assistant'));
      const userMessages = Array.from(document.querySelectorAll('.komsco-ai__message--user'));
      const latest = assistantMessages[assistantMessages.length - 1];
      latest?.querySelectorAll('.komsco-ai__progress').forEach((el) => { el.open = true; });
      const text = latest?.innerText || '';
      const source = latest?.querySelector('.komsco-ai__message-source')?.textContent.trim() || '';
      const actionButtons = Array.from(document.querySelectorAll('[data-answer-action-step]')).map((el) => ({
        disabled: Boolean(el.disabled),
        label: el.textContent.trim(),
        step: el.getAttribute('data-answer-action-step'),
      }));
      const createPlanButtons = Array.from(document.querySelectorAll('.komsco-ai__create-action-plan-button')).map((el) => el.textContent.trim());
      const loading = Boolean(document.querySelector('.komsco-ai__surface--responding')) ||
        ['응답 중지', 'Stop response'].includes(document.querySelector('.komsco-ai__send')?.getAttribute('aria-label') || '');
      return {
        actionButtons,
        assistantMessages: assistantMessages.length,
        createPlanButtons,
        loading,
        source,
        text,
        userMessages: userMessages.length,
      };
    })()`,
    (value) => value?.assistantMessages >= 1 && value?.userMessages >= 1 && !value?.loading && value?.text?.length > 120,
    `answer completed: ${label}`,
    120000,
  );
};

const clickActionStep = async (step) => {
  const clicked = await evaluate(`(() => {
    const button = Array.from(document.querySelectorAll('[data-answer-action-step="${step}"]'))
      .find((el) => !el.disabled);
    if (!button) {
      return {
        ok: false,
        buttons: Array.from(document.querySelectorAll('[data-answer-action-step]')).map((el) => ({
          disabled: Boolean(el.disabled),
          label: el.textContent.trim(),
          step: el.getAttribute('data-answer-action-step')
        }))
      };
    }
    button.click();
    return { ok: true, label: button.textContent.trim() };
  })()`);
  assert(clicked?.ok, `action step not clickable: ${step}`, clicked);
  await sleep(1500);
  return clicked;
};

const waitForActionStep = async (step, label) =>
  poll(
    `Array.from(document.querySelectorAll('[data-answer-action-step]')).map((el) => ({
      disabled: Boolean(el.disabled),
      label: el.textContent.trim(),
      step: el.getAttribute('data-answer-action-step')
    }))`,
    (buttons) => buttons.some((button) => button.step === step && !button.disabled),
    label,
    60000,
  );

const runBrowserScenario = async () => {
  await launchChrome();
  await openAssistant();
  await screenshot('01-open-copilot', 'AIOps Copilot opened in OKD console');
  addScenario('02-open-copilot', 'Open AIOps Copilot', 'passed');

  const diagnosisQuestion = [
    `${cli.namespace} namespace에서 CrashLoopBackOff와 ImagePullBackOff 상태를 실제 근거 중심으로 조회해줘.`,
    '변경은 하지 말고 read-only oc 확인 명령도 같이 정리해줘.',
  ].join('\n');
  const readOnly = await sendQuestion('read-only', diagnosisQuestion, 'read-only diagnosis');
  await screenshot('02-readonly-diagnosis', 'Read-only evidence answer');
  assert(readOnly.text.includes(cli.namespace), 'read-only answer must mention the sandbox namespace', readOnly);
  assert(/oc get|oc describe|oc logs/.test(readOnly.text), 'read-only answer must include safe oc inspection commands', readOnly);
  assert(!readOnly.actionButtons.some((button) => ['approve-plan', 'execute-approval', 'approve-execute-plan'].includes(button.step)), 'read-only answer must not expose executable controls', readOnly);
  addScenario('03-readonly-diagnosis', 'Read-only diagnosis', 'passed', {
    source: readOnly.source,
    textPreview: readOnly.text.slice(0, 700),
  });

  const beforePlanReplicas = getDeploymentReplicas('aiops-connected-scale-target');
  const planQuestion = [
    `Deployment ${cli.namespace}/aiops-connected-scale-target 를 2개로 scale하는 실행 계획을 생성해줘.`,
    '승인 전에는 실행하지 말고, 영향/검증/롤백 조건을 포함해줘.',
  ].join('\n');
  const executePlan = await sendQuestion('execute', planQuestion, 'execute plan');
  await screenshot('03-execute-plan', 'Execute mode Action Plan candidate');
  const afterPlanReplicas = getDeploymentReplicas('aiops-connected-scale-target');
  assert(afterPlanReplicas.replicas === beforePlanReplicas.replicas, 'execute-mode planning must not mutate replicas before approval', {
    afterPlanReplicas,
    beforePlanReplicas,
  });
  assert(
    executePlan.actionButtons.some((button) => button.step === 'approve-plan') ||
      executePlan.createPlanButtons.length > 0 ||
      /Action Plan|실행 계획|승인/.test(executePlan.text),
    'execute-mode answer must expose an approval-gated Action Plan path',
    executePlan,
  );
  addScenario('04-execute-plan', 'Execute mode planning', 'passed', {
    afterPlanReplicas,
    beforePlanReplicas,
    source: executePlan.source,
  });
  await screenshot('04-before-approval-no-mutation', 'Before approval mutation check');

  if (executePlan.createPlanButtons.length > 0) {
    await evaluate(`document.querySelector('.komsco-ai__create-action-plan-button')?.click(); true;`);
    await waitForActionStep('approve-plan', 'approve button after creating Action Plan');
  }
  await waitForActionStep('approve-plan', 'approve button available');
  await clickActionStep('approve-plan');
  await screenshot('05-approval-recorded', 'Approval recorded');
  addScenario('05-approval', 'Approval gate', 'passed');

  await waitForActionStep('execute-approval', 'execute button after approval');
  await clickActionStep('execute-approval');
  await screenshot('06-execution-requested', 'Execution requested');

  const executed = await poll(
    `document.body?.innerText || ''`,
    (text) =>
      text.includes('승인된 조치를 실행했습니다') ||
      text.includes('실행했습니다') ||
      text.includes('mutation_succeeded') ||
      text.includes('ExecutionRecord'),
    'execution success text',
    90000,
  );
  const afterExecutionReplicas = getDeploymentReplicas('aiops-connected-scale-target');
  assert(afterExecutionReplicas.replicas === 2, 'approved connected action must scale only the sandbox deployment to 2 replicas', {
    afterExecutionReplicas,
    executedPreview: executed.slice(0, 1200),
  });
  await screenshot('07-post-execution-verification', 'Post execution verification');
  addScenario('06-execution', 'Approved execution', 'passed', { afterExecutionReplicas });

  oc(['rollout', 'status', 'deployment/aiops-connected-scale-target', '-n', cli.namespace, '--timeout=120s']);
  await screenshot('08-rollout-verified', 'Rollout verified');
  addScenario('07-rollout-verification', 'Rollout verification', 'passed', {
    pods: getPodsText(),
    scaleTarget: getDeploymentReplicas('aiops-connected-scale-target'),
  });
};

const setupSandbox = () => {
  if (!cli.setup) return;
  const args = ['scripts/setup-v0281-connected-aiops-sandbox.sh', '--json'];
  if (cli.namespace) args.push('--namespace', cli.namespace);
  if (cli.session) args.push('--session', cli.session);
  let result;
  try {
    result = runJson('bash', args);
  } catch (error) {
    addScenario('00-sandbox-setup', 'Sandbox setup', 'failed', {
      command: ['bash', ...args].join(' '),
      error: error instanceof Error ? error.message : String(error),
    });
    throw error;
  }
  cli.namespace = result.namespace;
  cli.session = result.session;
  report.spec.namespace = cli.namespace;
  report.spec.session = cli.session;
  report.status.sandbox = result;
  addScenario('00-sandbox-setup', 'Sandbox setup', 'passed', result);
};

const cleanupSandbox = () => {
  if (!cli.cleanup || !cli.namespace || !cli.session) return;
  const result = runJson('bash', [
    'scripts/cleanup-v0281-connected-aiops-sandbox.sh',
    '--namespace',
    cli.namespace,
    '--session',
    cli.session,
    '--json',
  ]);
  report.status.cleanup = result;
  addScenario('08-cleanup', 'Sandbox cleanup', result.status === 'deleted' || result.status === 'not_found' ? 'passed' : 'failed', result);
};

const main = async () => {
  try {
    setupSandbox();
    await preflight();
    addScenario('01-workload-state', 'Sandbox workload state', 'passed', {
      pods: getPodsText(),
      scaleTarget: getDeploymentReplicas('aiops-connected-scale-target'),
    });
    await runBrowserScenario();
    cleanupSandbox();
    writeReport('passed');
    console.log(`PASS: connected AIOps scenario report -> ${rel(cli.report)}`);
  } catch (error) {
    report.status.failures.push({
      message: error instanceof Error ? error.message : String(error),
      runtimeErrors: runtimeErrors.slice(-5),
    });
    try {
      cleanupSandbox();
    } catch (cleanupError) {
      report.status.failures.push({
        message: `cleanup failed: ${cleanupError instanceof Error ? cleanupError.message : String(cleanupError)}`,
      });
    }
    writeReport('failed');
    console.error(`FAIL: connected AIOps scenario report -> ${rel(cli.report)}`);
    console.error(error instanceof Error ? error.stack || error.message : String(error));
    process.exitCode = 1;
  } finally {
    if (chromeWebSocket) {
      try {
        chromeWebSocket.close();
      } catch (_error) {
        // Ignore close errors.
      }
    }
    if (chromeProcess) {
      chromeProcess.kill('SIGTERM');
    }
    fs.rmSync(userDataDir, { force: true, recursive: true });
  }
};

main();
