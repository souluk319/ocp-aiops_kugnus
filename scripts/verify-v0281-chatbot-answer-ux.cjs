#!/usr/bin/env node

const { spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');
const WebSocket = require('ws');

const root = path.resolve(__dirname, '..');
const chrome = process.env.AIOPS_CHROME_BIN || '/home/kugnus/.local/bin/google-chrome';
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9361');
const consoleUrl =
  process.env.AIOPS_CONSOLE_URL || 'http://localhost:9000/dashboards/aiops?codex_v=0281';
const portalUrl =
  process.env.AIOPS_PORTAL_URL || 'http://localhost:5174/dashboards/aiops?codex_v=0281';
const screenshotDir = process.env.AIOPS_SCREENSHOT_DIR || '/tmp';
const userDataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'aiops-v0281-'));

let chromeProcess;
let chromeWebSocket;
let nextId = 1;
const pending = new Map();

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const readFile = (relativePath) =>
  fs.readFileSync(path.join(root, relativePath), 'utf8');

const assert = (condition, message, evidence = undefined) => {
  if (!condition) {
    const detail = evidence === undefined ? '' : `\n${JSON.stringify(evidence, null, 2)}`;
    throw new Error(`${message}${detail}`);
  }
};

const sourceReview = () => {
  const actionRecords = readFile('komsco-ai-console-plugin/src/components/AssistantActionRecords.tsx');
  const historyPanel = readFile('komsco-ai-console-plugin/src/components/AssistantHistoryPanel.tsx');
  const launcher = readFile('komsco-ai-console-plugin/src/components/AssistantLauncher.tsx');
  const messageContent = readFile('komsco-ai-console-plugin/src/components/AssistantMessageContent.tsx');
  const css = readFile('komsco-ai-console-plugin/src/components/assistant.css');
  const portal = readFile('komsco-ai-portal/src/App.tsx');

  assert(actionRecords.includes('ActionStageIcon'), 'Action Plan cards must expose lifecycle icons');
  assert(
    /readOnlyBlocked\s*\?\s*\[\]/.test(actionRecords),
    'read-only mode must hide repeated action buttons',
  );
  assert(
    actionRecords.includes("strong>Action Plan</strong"),
    'answer action section must be named Action Plan',
  );
  assert(
    historyPanel.includes('HistoryActionStageIcon'),
    'history sidebar action refs must include stage icons',
  );
  assert(
    historyPanel.includes('komsco-ai__history-item-main'),
    'history sidebar must group conversation title and action refs under one row',
  );
  assert(
    launcher.includes('productIcon={aiopsIcon}') && !launcher.includes('aiops_mark.svg'),
    'history sidebar must keep the original app icon; border removal only applies to message avatars',
  );
  assert(
    launcher.includes('suppressNextHistoryAutosaveRef') &&
      launcher.includes('saveCurrentConversation({ preserveUpdatedAt: true, promote: false })'),
    'loading an existing history item must not promote or reorder the sidebar list',
  );
  assert(
    !historyPanel.includes('이번 대화의 조치 계획') && !historyPanel.includes('komsco-ai__session-actions'),
    'history sidebar must not promote clicked actions into a separate top aggregate panel',
  );
  assert(
    messageContent.includes("summary: '현재 판단'"),
    'runbook answer must start with current judgment label',
  );
  assert(
    css.includes('v0.2.8.1: Action Plan-first chatbot answer UX'),
    'v0.2.8.1 CSS guard block missing',
  );
  assert(css.includes('font-size: 14.5px'), 'assistant answer body font must be >= 14px');
  assert(css.includes('--komsco-history-width: 268px'), 'history sidebar must be slightly wider');
  assert(css.includes('v0.2.8.1: group history actions under each conversation'), 'history grouping CSS guard missing');
  assert(
    css.includes('header chrome alignment and message icon scope fix'),
    'header alignment and message icon scope guard missing',
  );
  assert(
    css.includes('.komsco-ai__message--assistant .komsco-ai__message-avatar') &&
      css.includes('background: transparent') &&
      css.includes('border: 0'),
    'only assistant message avatar should lose its outer frame',
  );
  assert(
    /\.komsco-ai__surface \.komsco-ai__empty-mark\s*\{[\s\S]*background: transparent;[\s\S]*border: 0;[\s\S]*box-shadow: none;[\s\S]*\}/.test(css) &&
      /\.komsco-ai__surface \.komsco-ai__empty-logo\s*\{[\s\S]*width: 52px;[\s\S]*height: 52px;[\s\S]*\}/.test(css),
    'empty-state assistant icon should be enlarged without an outer card frame',
  );
  assert(
    css.includes('v0.2.8.1: responding header light rail') &&
      css.includes('komsco-ai-header-bottom-scan') &&
      css.includes('.komsco-ai__surface.komsco-ai__surface--responding .komsco-ai__header::after'),
    'assistant header must show a moving light rail while responding',
  );
  assert(
    portal.includes('OpenShift 인증 필요') && portal.includes('portalConnectionLabel'),
    'standalone portal must distinguish OpenShift auth from Gateway outage',
  );
  assert(
    portal.includes('clusterLabel(summary, error)'),
    'standalone portal cluster selector must not call auth failures a Gateway wait state',
  );
};

const launchChrome = (url) =>
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
      url,
    ],
    { stdio: ['ignore', 'pipe', 'pipe'] },
  );

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
  chromeProcess = launchChrome(consoleUrl);
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

  await new Promise((resolve, reject) => {
    chromeWebSocket.once('open', resolve);
    chromeWebSocket.once('error', reject);
  });

  await send('Page.enable');
  await send('Runtime.enable');

  return version.Browser;
};

const navigate = async (url) => {
  await send('Page.navigate', { url });
  await poll(
    `(() => ({
      ready: document.readyState === 'complete' && Boolean(document.body?.innerText?.trim()),
      hasOverlayFrame: Boolean(document.querySelector('#webpack-dev-server-client-overlay')),
      text: document.body?.innerText?.slice(0, 600) || ''
    }))()`,
    (value) => value?.ready && !value.hasOverlayFrame,
    `page ready ${url}`,
    90000,
  );
};

const installAssistantFixture = async () =>
  evaluate(`(async () => {
    const historyKey = 'komsco-ai.assistant.conversation-history.v1';
    const activeKey = 'komsco-ai.assistant.active-conversation.v1';
    const languageKey = 'komsco-ai.assistant.ui-language.v1';
    const messageAnchor = 'assistant-message-1';

    const asObject = (value) => value && typeof value === 'object' ? value : {};
    const specOf = (record) => asObject(record?.spec);
    const metadataName = (record) => record?.metadata?.name || '';
    const planDigest = (record) => {
      const sealed = asObject(specOf(record).sealedActionPlan);
      const digest = asObject(sealed.digest);
      return typeof digest.planDigest === 'string' ? digest.planDigest : '';
    };
    const approvalPlanDigest = (record) => {
      const decision = asObject(specOf(record).approvalDecision);
      return typeof decision.planDigest === 'string' ? decision.planDigest : '';
    };
    const targetLabel = (record) => {
      const spec = specOf(record);
      const sealed = asObject(spec.sealedActionPlan);
      const approval = asObject(spec.approvalDecision);
      const candidate = asObject(spec.candidate);
      const candidateRequest = asObject(spec.candidateActionRequest);
      const target =
        asObject(spec.target).name ? asObject(spec.target) :
        asObject(candidate.targetNode).name ? asObject(candidate.targetNode) :
        asObject(candidateRequest.target).name ? asObject(candidateRequest.target) :
        asObject(sealed.target).name ? asObject(sealed.target) :
        asObject(approval.target).name ? asObject(approval.target) :
        {};
      if (!target.name) {
        return metadataName(record) || 'unknown';
      }
      return target.namespace ? target.namespace + '/' + target.name : String(target.name);
    };
    const toolName = (record) => {
      const spec = specOf(record);
      const candidateRequest = asObject(spec.candidateActionRequest);
      const candidateAction = asObject(candidateRequest.action);
      const sealed = asObject(spec.sealedActionPlan);
      const sealedAction = asObject(sealed.action);
      const approval = asObject(spec.approvalDecision);
      const approvalAction = asObject(approval.action);
      return String(candidateAction.toolName || sealedAction.toolName || approvalAction.toolName || spec.action || record?.kind || 'action');
    };
    const stageOf = (record) => {
      const spec = specOf(record);
      if (record?.kind === 'ExecutionRecord' || spec.mutationOutcome || spec.approvalId) return 'execution';
      if (record?.kind === 'ApprovalDecisionRecord' || spec.approvalDecision) return 'approval';
      if (record?.kind === 'SealedActionPlanRecord' || spec.sealedActionPlan) return 'plan';
      return 'proposal';
    };
    const labelFor = (stage) => ({
      proposal: '1단계 · 후보 접수',
      plan: '2단계 · 승인 필요',
      approval: '3단계 · 실행 대기',
      execution: '4단계 · 실행 완료'
    }[stage] || '1단계 · 후보 접수');

    let status = null;
    try {
      const response = await fetch('/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status');
      if (response.ok) status = await response.json();
    } catch (_error) {
      status = null;
    }
    const records = status?.spec?.records || {};
    const sourceRecords = [
      ...(records.actionProposals || []),
      ...(records.sealedActionPlans || []),
      ...(records.approvalDecisions || []),
      ...(records.executionRecords || []),
    ].slice(0, 4);
    const actionRefs = sourceRecords.map((record, index) => {
      const stage = stageOf(record);
      return {
        id: 'v0281|' + index + '|' + metadataName(record),
        label: labelFor(stage),
        messageAnchor,
        planDigest: planDigest(record) || approvalPlanDigest(record) || undefined,
        recordKind: record?.kind,
        recordName: metadataName(record) || undefined,
        stage,
        targetKey: targetLabel(record),
        toolName: toolName(record),
        updatedAt: Date.now() - index * 1000
      };
    });
    const fallbackRef = {
      id: 'v0281|fixture|proposal',
      label: '1단계 · 후보 접수',
      messageAnchor,
      stage: 'proposal',
      targetKey: 'komsco-ai-dev/aiops-scenario-1-crashloop',
      toolName: 'rollout_restart_deployment',
      updatedAt: Date.now()
    };
    const refs = actionRefs.length ? actionRefs : [fallbackRef];
    const content = [
      '상세 분석',
      '- 현재 우선 확인할 항목은 appscan360 catalog Pod NotReady와 control-plane memory pressure입니다.',
      '',
      '영향 범위',
      '- marketplace catalog 기능과 API 응답 지연 가능성이 있습니다.',
      '',
      '확인한 근거',
      '- Alert: KubePodNotReady / severity=warning',
      '- Metric: restart increase observed',
      '',
      '원인 후보',
      '- readiness probe 실패 또는 image pull 상태 확인이 필요합니다.',
      '',
      'Action Plan',
      '- 대상: komsco-ai-dev/aiops-scenario-1-crashloop',
      '- 실행 전 검증: Events, logs, rollout 상태 확인',
      '- 승인 조건: 근거가 수집되고 영향/롤백 경로가 확인된 경우',
      '',
      '검증/롤백',
      '- 실행 후 Ready 상태와 restart 증가 중단 여부를 확인합니다.',
      '- 실패하면 이전 ReplicaSet 또는 수동 확인 절차로 전환합니다.',
      '',
      '근거 상세보기',
      '- 문서 근거와 운영 증거는 상세 안에서만 확인합니다.'
    ].join('\\n');
    const messages = [
      { role: 'user', content: '최근 OpenShift 경고를 운영자가 볼 수 있게 정리해줘.', timestamp: Date.now() - 10000 },
      { role: 'assistant', content, answerContract: 'v0281-fixture', timestamp: Date.now() - 9000 }
    ];
    const snapshot = {
      activeSessionId: 'v0281-fixture-session',
      actionRefs: refs,
      actionTargetKeys: refs.map((ref) => ref.targetKey),
      conversationId: 'v0281-fixture-conversation',
      messages
    };
    const olderMessages = [
      { role: 'user', content: '현재 화면의 대상 리소스에 대해 가능한 안전 조회를 실행해줘.', timestamp: Date.now() - 30000 },
      { role: 'assistant', content: content.replace('상세 분석', '현재 판단'), answerContract: 'v0281-fixture-older', timestamp: Date.now() - 29000 }
    ];
    const olderRefs = refs.map((ref, index) => ({
      ...ref,
      id: ref.id + '|older',
      messageAnchor: 'assistant-message-1',
      updatedAt: Date.now() - 20000 - index * 1000
    }));
    const history = [
      {
        id: 'v0281-fixture-session',
        title: 'v0.2.8.1 Action Plan UX fixture',
        updatedAt: Date.now(),
        conversationId: 'v0281-fixture-conversation',
        messages,
        actionRefs: refs,
        actionTargetKeys: refs.map((ref) => ref.targetKey)
      },
      {
        id: 'v0281-fixture-session-older',
        title: '이전 OpenShift 조치 후보',
        updatedAt: Date.now() - 20000,
        conversationId: 'v0281-fixture-conversation-older',
        messages: olderMessages,
        actionRefs: olderRefs,
        actionTargetKeys: olderRefs.map((ref) => ref.targetKey)
      }
    ];
    localStorage.setItem(activeKey, JSON.stringify(snapshot));
    localStorage.setItem(historyKey, JSON.stringify(history));
    localStorage.setItem(languageKey, JSON.stringify('ko'));
    return { refsCount: refs.length, statusLoaded: Boolean(status) };
  })()`);

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

const openHistory = async () => {
  const before = await evaluate(`(() => {
    const sidebar = document.querySelector('.komsco-ai__history-sidebar');
    const rect = sidebar?.getBoundingClientRect();
    return {
      isOpen: Boolean(rect && rect.width > 160 && document.querySelectorAll('.komsco-ai__history-action-ref').length > 0)
    };
  })()`);
  if (!before?.isOpen) {
    await evaluate(`document.querySelector('.komsco-ai__sidebar-toggle')?.click(); true;`);
  }
  await poll(
    `(() => {
      const sidebar = document.querySelector('.komsco-ai__history-sidebar');
      const rect = sidebar?.getBoundingClientRect();
      return Boolean(rect && rect.width > 160 && document.querySelectorAll('.komsco-ai__history-action-ref').length > 0);
    })()`,
    Boolean,
    'history sidebar open',
    60000,
  );
};

const verifyConsoleAssistant = async () => {
  await navigate(consoleUrl);
  const fixture = await installAssistantFixture();
  await send('Page.reload', { ignoreCache: true });
  await poll(
    `document.readyState === 'complete' && Boolean(document.body?.innerText?.trim())`,
    Boolean,
    'console reload after fixture',
    90000,
  );
  await openAssistant();

  const metrics = await evaluate(`(() => {
    const content = document.querySelector('.komsco-ai__message--assistant .komsco-ai__message-content');
    const style = content ? getComputedStyle(content) : null;
    const text = document.body?.innerText || '';
    const rawTerms = ['[RAG 근거]', 'source:', 'score=', 'post_answer', 'RCA 문맥 연결', 'Tool Plan JSON']
      .filter((term) => text.includes(term));
    return {
      actionButtonLabels: Array.from(document.querySelectorAll('.komsco-ai__answer-action-controls .komsco-ai__action-button')).map((el) => el.textContent.trim()),
      actionCards: document.querySelectorAll('.komsco-ai__answer-action-card').length,
      disabledActionButtons: document.querySelectorAll('.komsco-ai__answer-action-controls .komsco-ai__action-button[disabled]').length,
      fontSize: style ? parseFloat(style.fontSize) : 0,
      lineHeight: style ? parseFloat(style.lineHeight) : 0,
      rawTerms,
      runbookSections: Array.from(document.querySelectorAll('.komsco-ai__runbook-section-title')).map((el) => el.textContent.trim()),
      stageIcons: document.querySelectorAll('.komsco-ai__action-stage-icon').length,
      title: document.title
    };
  })()`);

  assert(metrics.fontSize >= 14, 'assistant answer font must be at least 14px', metrics);
  assert(metrics.lineHeight >= 22, 'assistant answer line-height must be readable', metrics);
  assert(metrics.runbookSections[0] === '현재 판단', 'first runbook card must be current judgment', metrics);
  assert(metrics.runbookSections.includes('Action Plan'), 'runbook must include Action Plan section', metrics);
  assert(metrics.actionCards >= 1, 'assistant answer must show at least one Action Plan lifecycle card', metrics);
  assert(
    metrics.stageIcons >= metrics.actionCards,
    'Action Plan cards must show lifecycle icons',
    metrics,
  );
  assert(metrics.disabledActionButtons === 0, 'read-only mode must not show repeated disabled action buttons', metrics);
  assert(metrics.rawTerms.length === 0, 'default assistant answer must not expose raw internal terms', metrics);

  const headerMetrics = await evaluate(`(() => {
    const header = document.querySelector('.komsco-ai__header');
    const sidebar = document.querySelector('.komsco-ai__sidebar-toggle');
    const brand = document.querySelector('.komsco-ai__brand');
    const actions = document.querySelector('.komsco-ai__header-actions');
    const status = document.querySelector('.komsco-ai__header-status');
    const avatar = document.querySelector('.komsco-ai__message--assistant .komsco-ai__message-avatar');
    const rect = (el) => {
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: r.width, height: r.height };
    };
    const sidebarRect = rect(sidebar);
    const brandRect = rect(brand);
    const actionsRect = rect(actions);
    const statusRect = rect(status);
    const headerStyle = header ? getComputedStyle(header) : null;
    const avatarStyle = avatar ? getComputedStyle(avatar) : null;
    const buttons = Array.from(document.querySelectorAll('.komsco-ai__header-actions .komsco-ai__icon-button, .komsco-ai__sidebar-toggle'));
    const buttonRects = buttons.map(rect).filter(Boolean);
    const overlaps = [];
    for (let i = 0; i < buttonRects.length; i += 1) {
      for (let j = i + 1; j < buttonRects.length; j += 1) {
        const a = buttonRects[i];
        const b = buttonRects[j];
        const separated = a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top;
        if (!separated) overlaps.push([i, j]);
      }
    }
    return {
      actionsRect,
      avatarBackground: avatarStyle?.backgroundColor || '',
      avatarBorderTopWidth: avatarStyle?.borderTopWidth || '',
      brandRect,
      buttonWidths: buttonRects.map((r) => Math.round(r.width)),
      display: headerStyle?.display || '',
      overlaps,
      sidebarRect,
      statusRect
    };
  })()`);
  assert(headerMetrics.display === 'grid', 'assistant header must use a stable grid layout', headerMetrics);
  assert(headerMetrics.overlaps.length === 0, 'assistant header buttons must not overlap', headerMetrics);
  assert(
    headerMetrics.sidebarRect?.right <= headerMetrics.brandRect?.left,
    'sidebar toggle must sit before the AIOps title without colliding',
    headerMetrics,
  );
  assert(
    headerMetrics.brandRect?.right <= headerMetrics.actionsRect?.left,
    'AIOps title must leave room for right header controls',
    headerMetrics,
  );
  assert(
    headerMetrics.statusRect?.top >= headerMetrics.brandRect?.bottom - 1,
    'status and execution mode row must sit under the header title row',
    headerMetrics,
  );
  assert(
    headerMetrics.buttonWidths.every((width) => width >= 28 && width <= 44),
    'header icon buttons must keep balanced control sizes',
    headerMetrics,
  );
  assert(
    headerMetrics.avatarBackground === 'rgba(0, 0, 0, 0)' ||
      headerMetrics.avatarBackground === 'transparent',
    'assistant message icon should not keep an outer filled frame',
    headerMetrics,
  );
  assert(
    headerMetrics.avatarBorderTopWidth === '0px',
    'assistant message icon should not keep an outer border',
    headerMetrics,
  );
  const respondingRailMetrics = await evaluate(`(() => {
    const surface = document.querySelector('.komsco-ai__surface');
    const header = document.querySelector('.komsco-ai__header');
    if (!surface || !header) return null;
    surface.classList.add('komsco-ai__surface--responding');
    const style = getComputedStyle(header, '::after');
    return {
      animationName: style.animationName,
      backgroundImage: style.backgroundImage,
      display: style.display,
      height: style.height,
      opacity: style.opacity
    };
  })()`);
  assert(
    respondingRailMetrics?.display === 'block' &&
      respondingRailMetrics.animationName === 'komsco-ai-header-bottom-scan' &&
      parseFloat(respondingRailMetrics.height) >= 3,
    'responding assistant header must animate a visible bottom light rail',
    respondingRailMetrics,
  );

  await openHistory();
  const historyMetrics = await evaluate(`(() => {
    const sidebar = document.querySelector('.komsco-ai__history-sidebar');
    const brand = document.querySelector('.komsco-ai__history-brand');
    const refs = Array.from(document.querySelectorAll('.komsco-ai__history-action-ref'));
    const sidebarRect = sidebar?.getBoundingClientRect();
    const brandStyle = brand ? getComputedStyle(brand) : null;
    return {
      actionRefCount: refs.length,
      aggregatePanelCount: document.querySelectorAll('.komsco-ai__session-actions').length,
      iconCount: document.querySelectorAll('.komsco-ai__history-action-ref-icon').length,
      groupedRefs: refs.filter((el) => Boolean(el.closest('.komsco-ai__history-item-row'))).length,
      logoBoxBackground: brandStyle?.backgroundColor || '',
      logoBoxShadow: brandStyle?.boxShadow || '',
      overflowingRefs: refs.filter((el) => el.scrollWidth > el.clientWidth + 1).length,
      sidebarWidth: sidebarRect ? Math.round(sidebarRect.width) : 0
    };
  })()`);
  assert(historyMetrics.actionRefCount >= 1, 'history sidebar must show action refs', {
    fixture,
    historyMetrics,
  });
  assert(
    historyMetrics.iconCount >= historyMetrics.actionRefCount,
    'history action refs must show lifecycle icons',
    historyMetrics,
  );
  assert(historyMetrics.aggregatePanelCount === 0, 'history sidebar must not show a top aggregate action panel', historyMetrics);
  assert(historyMetrics.groupedRefs === historyMetrics.actionRefCount, 'history action refs must be grouped under their conversation', historyMetrics);
  assert(historyMetrics.sidebarWidth >= 260, 'history sidebar must be slightly wider than the old narrow panel', historyMetrics);
  assert(
    historyMetrics.logoBoxBackground !== 'rgba(0, 0, 0, 0)' &&
      historyMetrics.logoBoxBackground !== 'transparent',
    'history logo wrapper must keep the product app icon treatment',
    historyMetrics,
  );
  assert(historyMetrics.overflowingRefs === 0, 'history action refs must not overflow', historyMetrics);

  const historyOrderBefore = await evaluate(`(() =>
    Array.from(document.querySelectorAll('.komsco-ai__history-item-row .komsco-ai__history-item span'))
      .map((el) => el.textContent.trim())
  )()`);
  const clickedOlderAction = await evaluate(`(() => {
    const rows = Array.from(document.querySelectorAll('.komsco-ai__history-item-row'));
    const target = rows[1]?.querySelector('.komsco-ai__history-action-ref');
    if (!target) return false;
    target.click();
    return true;
  })()`);
  assert(clickedOlderAction, 'history fixture must expose a second conversation action ref');
  await sleep(600);
  await openHistory();
  const historyOrderAfter = await evaluate(`(() =>
    Array.from(document.querySelectorAll('.komsco-ai__history-item-row .komsco-ai__history-item span'))
      .map((el) => el.textContent.trim())
  )()`);
  assert(
    JSON.stringify(historyOrderAfter) === JSON.stringify(historyOrderBefore),
    'clicking or expanding a history action must not reorder dated conversation list',
    { historyOrderBefore, historyOrderAfter },
  );

  await send('Page.captureScreenshot', { format: 'png', fromSurface: true }).then((result) => {
    fs.writeFileSync(path.join(screenshotDir, 'v0281-chatbot-history.png'), Buffer.from(result.data, 'base64'));
  });

  return { fixture, historyMetrics, metrics };
};

const verifyStandalonePortal = async () => {
  await navigate(portalUrl);
  const metrics = await poll(
    `(() => {
      const text = document.body?.innerText || '';
      return {
        ready: Boolean(text.trim()),
        hasAuthNeeded: text.includes('OpenShift 인증 필요'),
        hasWrongDisconnected: text.includes('게이트웨이 연결 끊김'),
        hasGatewayWaiting: text.includes('게이트웨이 연결 대기'),
        hasGatewayConnected: text.includes('게이트웨이 연결됨'),
        sample: text.slice(0, 1600)
      };
    })()`,
    (value) => value?.ready && (value.hasAuthNeeded || value.hasGatewayConnected),
    'standalone portal connection wording',
    90000,
  );
  assert(
    !metrics.hasWrongDisconnected,
    'standalone portal must not call auth failures Gateway disconnected',
    metrics,
  );
  assert(
    !metrics.hasGatewayWaiting,
    'standalone portal must not call auth failures Gateway waiting',
    metrics,
  );
  return metrics;
};

const main = async () => {
  sourceReview();
  const chromeVersion = await setupBrowser();
  const consoleResult = await verifyConsoleAssistant();
  const portalResult = await verifyStandalonePortal();

  chromeWebSocket.close();
  chromeProcess.kill('SIGTERM');

  const output = {
    chrome: chromeVersion,
    consoleResult,
    passed: true,
    portalResult,
    screenshots: [path.join(screenshotDir, 'v0281-chatbot-history.png')],
  };
  console.log(JSON.stringify(output, null, 2));
};

main().catch((error) => {
  if (chromeWebSocket) {
    chromeWebSocket.close();
  }
  if (chromeProcess) {
    chromeProcess.kill('SIGTERM');
  }
  console.error(error.stack || String(error));
  process.exit(1);
});
