#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const requireFromPlugin = require('module').createRequire(
  path.join(__dirname, '..', 'komsco-ai-console-plugin', 'package.json'),
);

let WebSocket;
try {
  WebSocket = require('ws');
} catch (_error) {
  WebSocket = requireFromPlugin('ws');
}

const root = path.resolve(__dirname, '..');
const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9362');
const consoleUrl =
  process.env.AIOPS_CONSOLE_URL ||
  'http://localhost:9000/dashboards/aiops?codex_v=029-action-history';
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-v029-action-history-'));

let chromeProcess;
let chromeWebSocket;
let nextId = 1;
const pending = new Map();

const question = [
  '다음 네임스페이스들이 실제 사용 중인지, 오래된 테스트인지 판단하고 싶어.',
  'aiops-demo',
  'cywell-aiops',
  'gpu-test-kugnus',
  'komsco-ai',
  'komsco-ai-dev',
  'komsco-aiops-lab',
  '각 네임스페이스별 판단 기준과 read-only oc 확인 명령을 정리하고,',
  '정리 후보가 있으면 실행 전 승인 가능한 Action Plan 후보까지 만들어줘.',
].join('\n');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const assert = (condition, message, evidence = undefined) => {
  if (!condition) {
    const detail = evidence === undefined ? '' : `\n${JSON.stringify(evidence, null, 2)}`;
    throw new Error(`${message}${detail}`);
  }
};

const fetchJson = async (url) => {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} -> HTTP ${response.status}`);
  }
  return response.json();
};

const waitForJson = async (url, timeoutMs = 30000) => {
  const started = Date.now();
  let lastError;
  while (Date.now() - started < timeoutMs) {
    try {
      return await fetchJson(url);
    } catch (error) {
      lastError = error;
      await sleep(250);
    }
  }
  throw lastError || new Error(`Timed out waiting for ${url}`);
};

const launchChrome = () =>
  spawn(
    chrome,
    [
      '--headless=new',
      '--disable-gpu',
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--window-size=1440,960',
      `--remote-debugging-port=${port}`,
      `--user-data-dir=${userDataDir}`,
      consoleUrl,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

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
    if (predicate(last)) {
      return last;
    }
    await sleep(500);
  }
  throw new Error(`Timed out waiting for ${label}. Last=${JSON.stringify(last)}`);
};

const setupBrowser = async () => {
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

  await new Promise((resolve, reject) => {
    chromeWebSocket.once('open', resolve);
    chromeWebSocket.once('error', reject);
  });
  await send('Page.enable');
  await send('Runtime.enable');
  return version.Browser;
};

const setExecutionMode = async (mode) => {
  const labels = {
    execute: ['승인 후 실행 모드', 'Approval-gated execution mode'],
    'read-only': ['읽기 전용 모드', 'Read-only mode'],
    unrestricted: ['실행 무제한 모드', 'Unrestricted execution mode'],
  }[mode];
  const clicked = await evaluate(`(() => {
    const labels = ${JSON.stringify(labels)};
    const button = Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button'))
      .find((el) => labels.includes(el.getAttribute('aria-label') || ''));
    if (!button) {
      return {
        ok: false,
        labels: Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button'))
          .map((el) => el.getAttribute('aria-label') || el.textContent.trim())
      };
    }
    button.click();
    return { ok: true, label: button.getAttribute('aria-label') };
  })()`);
  assert(clicked?.ok, `execution mode ${mode} must be selectable`, clicked);
};

const openAssistant = async () => {
  await poll(
    `Boolean(document.querySelector('.komsco-ai__fab'))`,
    Boolean,
    'assistant FAB visible',
    60000,
  );
  await evaluate(`document.querySelector('.komsco-ai__fab')?.click(); true;`);
  await poll(
    `Boolean(document.querySelector('.komsco-ai__surface'))`,
    Boolean,
    'assistant surface open',
    60000,
  );
};

const askQuestion = async () => {
  await setExecutionMode('execute');
  const changed = await evaluate(`(() => {
    const textarea = document.querySelector('.komsco-ai__composer textarea');
    if (!textarea) return { ok: false, reason: 'missing textarea' };
    const setter = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    setter?.call(textarea, ${JSON.stringify(question)});
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    textarea.dispatchEvent(new Event('change', { bubbles: true }));
    return { ok: true, value: textarea.value };
  })()`);
  assert(changed?.ok && changed.value === question, 'composer textarea must accept test question', changed);
  await poll(
    `(() => {
      const button = document.querySelector('.komsco-ai__send');
      return { disabled: Boolean(button?.disabled), label: button?.getAttribute('aria-label') || '' };
    })()`,
    (value) => value?.disabled === false && ['질문 전송', 'Send question'].includes(value.label),
    'send button enabled',
    10000,
  );
  await evaluate(`document.querySelector('.komsco-ai__send')?.click(); true;`);
  return poll(
    `(() => {
      const assistantMessages = Array.from(document.querySelectorAll('.komsco-ai__message--assistant'));
      const latest = assistantMessages[assistantMessages.length - 1];
      const text = latest?.textContent || '';
      return {
        assistantCount: assistantMessages.length,
        actionButtonCount: latest?.querySelectorAll('.komsco-ai__create-action-plan-button').length || 0,
        hasCollapsedGroup: Boolean(latest?.querySelector('.komsco-ai__create-action-plan[data-aiops-action-candidates-expanded="false"]')),
        responding: Boolean(document.querySelector('.komsco-ai__surface--responding')),
        text: text.slice(0, 1200)
      };
    })()`,
    (value) =>
      value?.assistantCount >= 1 &&
      !value.responding &&
      value.text.length > 120 &&
      (value.actionButtonCount >= 1 || value.hasCollapsedGroup),
    'assistant answer with Action Plan candidate',
    180000,
  );
};

const createPlan = async () => {
  const marked = await evaluate(`(() => {
    document.querySelectorAll('[data-v029-action-target="true"]')
      .forEach((node) => node.removeAttribute('data-v029-action-target'));
    const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
    if (!latest) return { ok: false, reason: 'missing assistant message' };
    latest.setAttribute('data-v029-action-target', 'true');
    return {
      ok: true,
      anchor: latest.getAttribute('data-action-anchor'),
      text: latest.textContent?.replace(/\\s+/g, ' ').trim().slice(0, 240) || ''
    };
  })()`);
  assert(marked?.ok, 'Action Plan verification target message must be markable', marked);

  const expanded = await evaluate(`(() => {
    const latest = document.querySelector('.komsco-ai__message--assistant[data-v029-action-target="true"]') ||
      Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
    const group = latest?.querySelector('.komsco-ai__create-action-plan[data-aiops-action-candidates-expanded="false"]');
    const summary = group?.querySelector('.komsco-ai__create-action-plan-summary');
    if (!group || !summary) return { clicked: false, expanded: true };
    summary.click();
    return { clicked: true, expanded: group.getAttribute('data-aiops-action-candidates-expanded') === 'true' };
  })()`);
  if (expanded?.clicked) {
    await poll(
      `(() => {
        const latest = document.querySelector('.komsco-ai__message--assistant[data-v029-action-target="true"]') ||
          Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
        const group = latest?.querySelector('.komsco-ai__create-action-plan');
        const visibleButtons = Array.from(latest?.querySelectorAll('.komsco-ai__create-action-plan-button') || [])
          .filter((button) => {
            const rect = button.getBoundingClientRect();
            return rect.width > 0 && rect.height > 0;
          });
        return { expanded: group?.getAttribute('data-aiops-action-candidates-expanded') === 'true', visibleButtonCount: visibleButtons.length };
      })()`,
      (value) => value?.expanded && value.visibleButtonCount >= 1,
      'candidate group expanded',
      10000,
    );
  }

  const clicked = await evaluate(`(() => {
    const latest = document.querySelector('.komsco-ai__message--assistant[data-v029-action-target="true"]') ||
      Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
    const button = latest?.querySelector('.komsco-ai__create-action-plan-button');
    const label = button?.textContent?.trim() || '';
    const disabled = Boolean(button?.disabled);
    if (!button || disabled) return { ok: false, disabled, label };
    button.click();
    return { ok: true, disabled, label };
  })()`);
  assert(clicked?.ok, 'Action Plan 생성 button must be clickable', clicked);

  return poll(
    `(() => {
	      const latest = document.querySelector('.komsco-ai__message--assistant[data-v029-action-target="true"]') ||
	        Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
	      const records = Array.from(latest?.querySelectorAll('[data-action-lifecycle-stage]') || []);
	      const detail = latest?.querySelector('.komsco-ai__rail-command-detail');
	      const fallbackCards = Array.from(latest?.querySelectorAll('.komsco-ai__answer-action-card--fallback') || []);
	      const fields = Array.from(latest?.querySelectorAll('[data-action-plan-field]') || [])
	        .map((node) => ({
	          key: node.getAttribute('data-action-plan-field'),
	          text: node.textContent.replace(/\\s+/g, ' ').trim()
	        }));
      const text = latest?.textContent || '';
	      return {
	        createButtonCount: latest?.querySelectorAll('.komsco-ai__create-action-plan-button').length || 0,
	        detailCount: latest?.querySelectorAll('.komsco-ai__rail-command-detail').length || 0,
	        fallbackCardCount: fallbackCards.length,
	        fieldKeys: Array.from(new Set(fields.map((field) => field.key).filter(Boolean))),
	        fields,
	        hasApprovalButton: Boolean(latest?.querySelector('[data-answer-action-step="approve-plan"]')),
	        hasExecuteButton: Boolean(latest?.querySelector('[data-answer-action-step="execute-approval"]')),
	        hasExecutionOutcome: Boolean(latest?.querySelector('.komsco-ai__answer-action-outcome-title')),
	        hasRejectButton: Boolean(latest?.querySelector('[data-answer-action-step="reject-plan"]')),
	        notes: Array.from(latest?.querySelectorAll('.komsco-ai__answer-action-note,.komsco-ai__rail-error') || [])
	          .map((node) => node.textContent.replace(/\\s+/g, ' ').trim()),
        stages: records.map((record) => record.getAttribute('data-action-lifecycle-stage')),
        text: text.slice(0, 1200),
        hasDetail: Boolean(detail)
      };
    })()`,
	    (value) =>
	      value?.createButtonCount === 0 &&
	      value.detailCount >= 1 &&
	      value.fallbackCardCount === 0 &&
	      ['target', 'problem', 'evidence', 'action', 'impact', 'verification', 'rollback', 'approval']
	        .every((key) => value.fieldKeys?.includes(key)) &&
	      value.stages?.includes('plan') &&
	      value.hasApprovalButton &&
	      value.hasRejectButton &&
	      !value.stages?.includes('execution'),
    'created action lifecycle card appears with approval CTA',
    60000,
  );
};

const approvePlan = async () => {
  const clicked = await evaluate(`(() => {
    const latest = document.querySelector('.komsco-ai__message--assistant[data-v029-action-target="true"]') ||
      Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
    const button = latest?.querySelector('[data-answer-action-step="approve-plan"]');
    const label = button?.textContent?.replace(/\\s+/g, ' ').trim() || '';
    const disabled = Boolean(button?.disabled);
    const title = button?.getAttribute('title') || '';
    if (!button || disabled) return { ok: false, disabled, label, title };
    button.click();
    return { ok: true, disabled, label, title };
  })()`);
  assert(clicked?.ok, '승인 요청 button must be clickable after Action Plan creation', clicked);

  return poll(
    `(() => {
      const latest = document.querySelector('.komsco-ai__message--assistant[data-v029-action-target="true"]') ||
        Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
      const records = Array.from(latest?.querySelectorAll('[data-action-lifecycle-stage]') || []);
      const text = latest?.textContent || '';
      return {
        createButtonCount: latest?.querySelectorAll('.komsco-ai__create-action-plan-button').length || 0,
        hasExecuteButton: Boolean(latest?.querySelector('[data-answer-action-step="execute-approval"]')),
        stages: records.map((record) => record.getAttribute('data-action-lifecycle-stage')),
        text: text.slice(0, 1200)
      };
    })()`,
    (value) =>
      value?.stages?.includes('approval') &&
      value.hasExecuteButton &&
      value.createButtonCount === 0,
    'approved action lifecycle card appears with execute CTA',
    60000,
  );
};

const executePlan = async () => {
  const before = await evaluate(`document.querySelectorAll('[data-action-lifecycle-stage="execution"]').length`);
  const clicked = await evaluate(`(() => {
    const latest = document.querySelector('.komsco-ai__message--assistant[data-v029-action-target="true"]') ||
      Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
    const button = latest?.querySelector('[data-answer-action-step="execute-approval"]');
    const label = button?.textContent?.replace(/\\s+/g, ' ').trim() || '';
    const disabled = Boolean(button?.disabled);
    const title = button?.getAttribute('title') || '';
    if (!button || disabled) return { ok: false, disabled, label, title };
    button.click();
    return { ok: true, disabled, label, title };
  })()`);
  assert(clicked?.ok, '실행 button must be clickable after approval', clicked);

  return poll(
    `(() => {
      const latest = document.querySelector('.komsco-ai__message--assistant[data-v029-action-target="true"]') ||
        Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
      const records = Array.from(latest?.querySelectorAll('[data-action-lifecycle-stage]') || []);
      const executionCards = Array.from(latest?.querySelectorAll('[data-action-lifecycle-stage="execution"]') || []);
      const text = latest?.textContent || '';
      return {
        before: ${Number(before) || 0},
        createButtonCount: latest?.querySelectorAll('.komsco-ai__create-action-plan-button').length || 0,
        executionCount: document.querySelectorAll('[data-action-lifecycle-stage="execution"]').length,
        latestExecutionCards: executionCards.length,
        stages: records.map((record) => record.getAttribute('data-action-lifecycle-stage')),
        text: text.slice(0, 1400)
      };
    })()`,
    (value) =>
      value?.stages?.includes('execution') &&
      value.latestExecutionCards >= 1 &&
      value.executionCount > value.before &&
      value.createButtonCount === 0,
    'executed action lifecycle card appears with execution result',
    60000,
  );
};

const verifyHistoryAndJson = async () => {
  const opened = await poll(
    `(() => {
      const sidebar = document.querySelector('.komsco-ai__history-sidebar');
      if (sidebar) return { ok: true, alreadyOpen: true };
      const button = Array.from(document.querySelectorAll('.komsco-ai__sidebar-toggle'))
        .find((candidate) => {
          const rect = candidate.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        });
      if (!button) return {
        ok: false,
        reason: 'missing sidebar toggle',
        bodyText: document.body?.innerText?.slice(0, 260) || '',
        fabCount: document.querySelectorAll('.komsco-ai__fab').length,
        headerCount: document.querySelectorAll('.komsco-ai__header').length,
        surfaceCount: document.querySelectorAll('.komsco-ai__surface').length,
        toggleCount: document.querySelectorAll('.komsco-ai__sidebar-toggle').length
      };
      button.click();
      return { ok: true, alreadyOpen: false };
    })()`,
    (value) => value?.ok,
    'history sidebar toggle available',
    10000,
  );
  assert(opened?.ok, 'history sidebar must be openable', opened);
  await poll(
    `Boolean(document.querySelector('.komsco-ai__history-sidebar'))`,
    Boolean,
    'history sidebar visible',
    10000,
  );

  const menuOpened = await poll(
    `(() => {
      const row = document.querySelector('.komsco-ai__history-item-row--active');
      const trigger = row?.querySelector('.komsco-ai__history-item-menu-trigger');
      if (!trigger) {
        return {
          ok: false,
          reason: row ? 'missing active row menu trigger' : 'missing active history row',
          rowCount: document.querySelectorAll('.komsco-ai__history-item-row').length,
          sidebarText: document.querySelector('.komsco-ai__history-sidebar')?.textContent?.replace(/\\s+/g, ' ').trim().slice(0, 500) || '',
          surfaceText: document.querySelector('.komsco-ai__surface')?.textContent?.replace(/\\s+/g, ' ').trim().slice(0, 500) || ''
        };
      }
      trigger.click();
      return { ok: true, title: row.textContent.replace(/\\s+/g, ' ').trim().slice(0, 180) };
    })()`,
    (value) => value?.ok,
    'active history row menu available',
    10000,
  );
  assert(menuOpened?.ok, 'history row menu must open', menuOpened);

  const actionHistoryOpened = await poll(
    `(() => {
      const items = Array.from(document.querySelectorAll('.komsco-ai__history-item-menu-panel [role="menuitem"]'));
      const item = items.find((candidate) => /조치내역|Action history/.test(candidate.textContent || ''));
      if (!item) return { ok: false, labels: items.map((candidate) => candidate.textContent.trim()) };
      item.click();
      return { ok: true, labels: items.map((candidate) => candidate.textContent.trim()) };
    })()`,
    (value) => value?.ok,
    'action history menu item available',
    10000,
  );
  assert(actionHistoryOpened?.ok, 'history row menu must expose action history', actionHistoryOpened);

  const historyRefs = await poll(
    `(() => {
      const row = document.querySelector('.komsco-ai__history-item-row--active');
      const refs = Array.from(row?.querySelectorAll('.komsco-ai__history-action-ref') || []);
      const answerStages = Array.from(document.querySelectorAll('.komsco-ai__answer-actions [data-action-lifecycle-stage]'))
        .map((record) => record.getAttribute('data-action-lifecycle-stage'));
      return {
        answerStages,
        count: refs.length,
        labels: refs.map((ref) => ref.textContent.replace(/\\s+/g, ' ').trim()),
        primaryLabels: refs.map((ref) => ref.querySelector('strong')?.textContent.trim() || ''),
        stageLabels: refs.map((ref) => ref.querySelector('.komsco-ai__history-action-ref-stage')?.textContent.trim() || ''),
        statusLabels: refs.map((ref) => ref.querySelector('small')?.textContent.trim() || ''),
        stages: refs.map((ref) => ref.getAttribute('data-action-stage')),
        grouped: refs.filter((ref) => Boolean(ref.closest('.komsco-ai__history-item-row'))).length
      };
    })()`,
    (value) =>
      value?.count >= 1 &&
      value.grouped === value.count &&
      value.stageLabels?.every((label) => label !== 'Action Plan') &&
      value.primaryLabels?.every((label) => !/^(승인 필요|실행 완료|후보 접수|Candidate received|Approval required|Executed)$/i.test(label)) &&
      value.primaryLabels?.some((label) => /정리|Pod|Namespace|review|plan/i.test(label)) &&
      (!value.answerStages?.includes('execution') || value.stages?.includes('execution')),
    'history action refs grouped under conversation',
    10000,
  );

  const refClicked = await evaluate(`(() => {
    const row = document.querySelector('.komsco-ai__history-item-row--active');
    const ref = row?.querySelector('.komsco-ai__history-action-ref');
    if (!ref) return { ok: false };
    ref.click();
    return { ok: true, text: ref.textContent.replace(/\\s+/g, ' ').trim() };
  })()`);
  assert(refClicked?.ok, 'history action ref must be clickable', refClicked);

  const auditJson = await poll(
    `(() => {
      const targetMessage = Array.from(document.querySelectorAll('.komsco-ai__message--assistant[data-v029-action-target="true"]')).pop();
      const executionDetail = document.querySelector('.komsco-ai__answer-actions [data-action-lifecycle-stage="execution"] .komsco-ai__rail-command-detail');
      const scopedDetails = executionDetail
        ? [executionDetail]
        : Array.from(targetMessage?.querySelectorAll('.komsco-ai__rail-command-detail') || []);
      const details = scopedDetails.length
        ? scopedDetails
        : Array.from(document.querySelectorAll('.komsco-ai__rail-command-detail'));
      const detail = details.find((item) => /감사 상세|Audit detail/.test(item.textContent || '')) || details[0];
      if (!detail) return { ok: false, reason: 'missing audit detail' };
      const summary = detail.querySelector('summary');
      if (!detail.open) summary?.click();
      const raw = detail.querySelector('pre')?.textContent || '';
      let parsed = null;
      try {
        parsed = JSON.parse(raw);
      } catch (_error) {}
      return {
        ok: Boolean(parsed?.kind || parsed?.metadata),
        kind: parsed?.kind || '',
        name: parsed?.metadata?.name || '',
        rawLength: raw.length,
        summary: summary?.textContent.trim() || ''
      };
    })()`,
    (value) => value?.ok && value.rawLength > 40,
    'audit detail JSON opens and parses',
    10000,
  );

  const highestHistoryStage = historyRefs.stages.includes('execution')
    ? 'execution'
    : historyRefs.stages.includes('approval')
      ? 'approval'
      : historyRefs.stages.includes('plan')
        ? 'plan'
        : 'proposal';
  const expectedKindByStage = {
    approval: 'ApprovalDecisionRecord',
    execution: 'ExecutionRecord',
    plan: 'SealedActionPlanRecord',
    proposal: 'ActionProposalRecord',
  };
  assert(
    auditJson.kind === expectedKindByStage[highestHistoryStage],
    'audit detail must match the highest visible action history stage',
    { auditJson, expectedKind: expectedKindByStage[highestHistoryStage], historyRefs },
  );

  return { auditJson, historyRefs, refClicked };
};

const cleanup = () => {
  if (chromeWebSocket) {
    chromeWebSocket.close();
  }
  if (chromeProcess) {
    chromeProcess.kill('SIGTERM');
  }
  try {
    fs.rmSync(userDataDir, {
      force: true,
      maxRetries: 5,
      recursive: true,
      retryDelay: 100,
    });
  } catch (_error) {
    // Chrome can keep a profile file open briefly after SIGTERM; the temp dir is best-effort cleanup.
  }
};

const main = async () => {
  assert(fs.existsSync(chrome), 'Chrome binary must exist for browser verification', { chrome });
  const chromeVersion = await setupBrowser();
  await poll(
    `(() => ({
      ready: document.readyState === 'complete' && Boolean(document.body?.innerText?.trim()),
      overlay: Boolean(document.querySelector('#webpack-dev-server-client-overlay')),
      text: document.body?.innerText?.slice(0, 600) || ''
    }))()`,
    (value) => value?.ready && !value.overlay,
    'console page ready',
    60000,
  );

  await openAssistant();
  const answer = await askQuestion();
  const plan = await createPlan();
  const approval = await approvePlan();
  const execution = await executePlan();
  const history = await verifyHistoryAndJson();

  console.log(
    JSON.stringify(
      {
        answer: {
          actionButtonCount: answer.actionButtonCount,
          text: answer.text.slice(0, 240),
        },
        chrome: chromeVersion,
        history,
        passed: true,
        path: 'approval-then-execution',
        approval: {
          hasExecuteButton: approval?.hasExecuteButton ?? false,
          stages: approval?.stages ?? [],
        },
        execution: {
          executionCount: execution.executionCount,
          stages: execution.stages,
        },
        plan: {
          detailCount: plan.detailCount,
          fieldKeys: plan.fieldKeys,
          hasApprovalButton: plan.hasApprovalButton,
          hasExecuteButton: plan.hasExecuteButton,
          hasRejectButton: plan.hasRejectButton,
          stages: plan.stages,
        },
      },
      null,
      2,
    ),
  );
};

main()
  .catch((error) => {
    console.error(error.stack || String(error));
    process.exitCode = 1;
  })
  .finally(cleanup);
