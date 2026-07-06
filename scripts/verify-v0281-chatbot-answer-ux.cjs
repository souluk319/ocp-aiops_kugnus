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
const port = Number(process.env.AIOPS_CHROME_DEBUG_PORT || '9361');
const consoleUrl =
  process.env.AIOPS_CONSOLE_URL || 'http://localhost:9000/dashboards/aiops?codex_v=0281';
const portalUrl =
  process.env.AIOPS_PORTAL_URL || 'http://localhost:5174/dashboards/aiops?codex_v=0281';
const localGatewayUrl = process.env.AIOPS_LOCAL_GATEWAY_URL || 'http://127.0.0.1:5174';
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
  const insightRailHelpers = readFile('komsco-ai-console-plugin/src/components/assistant.insightRailHelpers.tsx');
  const launcher = readFile('komsco-ai-console-plugin/src/components/AssistantLauncher.tsx');
  const messageContent = readFile('komsco-ai-console-plugin/src/components/AssistantMessageContent.tsx');
  const gatewayService = readFile('komsco-ai-console-plugin/src/services/aiGateway.ts');
  const localGateway = readFile('scripts/serve-v0281-local-aiops-gateway.cjs');
  const css = readFile('komsco-ai-console-plugin/src/components/assistant.css');
  const portal = readFile('komsco-ai-portal/src/App.tsx');

  assert(actionRecords.includes('ActionStageIcon'), 'Action Plan cards must expose lifecycle icons');
  assert(
    actionRecords.includes("const readOnlyBlocked = executionMode === 'read-only'") &&
      actionRecords.includes('읽기 전용 모드입니다. 버튼은 유지하고 클릭 시 실행 제한 사유를 표시합니다.') &&
      actionRecords.includes('읽기 전용 모드에서는 승인·실행 요청을 보내지 않습니다.'),
    'read-only mode must keep Action Plan CTAs visible but show execution-limit reasons',
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
    historyPanel.includes("uiLanguage === 'en' ? 'Rename' : '이름 변경'") &&
      historyPanel.includes("uiLanguage === 'en' ? 'Action history' : '조치내역'") &&
      historyPanel.includes("uiLanguage === 'en' ? 'Delete chat' : '대화 삭제'"),
    'history row menu must translate all visible menu items in English mode',
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
    insightRailHelpers.includes("isKo ? '읽기 전용' : 'Read only'") &&
      insightRailHelpers.includes("isKo ? '실행 가능' : 'Execute'") &&
      insightRailHelpers.includes("isKo ? '실행 무제한' : 'Unrestricted'"),
    'execution capability badges must translate read-only, execute, and unrestricted labels',
  );
  assert(
    css.includes('.komsco-ai__message--assistant .komsco-ai__message-avatar') &&
      css.includes('background: transparent') &&
      css.includes('border: 0'),
    'only assistant message avatar should lose its outer frame',
  );
  assert(
    launcher.includes('data-message-actions="user"') &&
      launcher.includes('data-message-actions="assistant"') &&
      launcher.includes('수정해서 다시 보내기') &&
      launcher.includes('좋은 답변') &&
      launcher.includes('좋지 않은 답변'),
    'message-level actions must preserve user edit/copy and assistant copy/rating controls',
  );
  assert(
    launcher.includes('komsco-ai__feedback-comment') &&
      launcher.includes('feedbackCommentPlaceholder') &&
      launcher.includes('submitMessageFeedbackComment') &&
      launcher.includes('optionalComment'),
    'assistant feedback must support an inline tester comment, not only a local icon state',
  );
  assert(
    gatewayService.includes('optionalComment?: string') &&
      gatewayService.includes('/v1/chat/feedback'),
    'console gateway service must include deployable chat feedback payload contract',
  );
  assert(
    localGateway.includes('optionalComment: body.optionalComment') &&
      localGateway.includes('LOCAL_CHAT_FEEDBACK.set'),
    'local fixture gateway must persist feedback comments for browser acceptance tests',
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

const parseSseEvents = (raw) =>
  raw
    .split(/\n\n+/)
    .map((block) => block.split(/\n/).find((line) => line.startsWith('data: ')))
    .filter(Boolean)
    .map((line) => line.replace(/^data:\s*/, '').trim())
    .filter((data) => data && data !== '[DONE]')
    .map((data) => {
      try {
        return JSON.parse(data);
      } catch (_error) {
        return { type: 'parse_error', raw: data };
      }
    });

const NAMESPACE_CLEANUP_QUESTION = [
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

const UNCLEAR_CHAT_QUESTIONS = ['야', '명청한챗봇'];

const verifyModeAnswerContracts = async () => {
  const question = NAMESPACE_CLEANUP_QUESTION;

  const runMode = async (mode) => {
    const response = await fetch(`${localGatewayUrl}/v1/chat/stream`, {
      body: JSON.stringify({
        conversationId: `v0281-mode-contract-${mode}`,
        message: question,
        pageContext: {
          aiopsExecutionMode: mode,
          route: '/dashboards/aiops',
        },
      }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    });
    const raw = await response.text();
    const events = parseSseEvents(raw);
    const answerText = events
      .filter((event) => event.type === 'text')
      .map((event) => event.content || '')
      .join('\n');
    const toolPlan = events.find((event) => event.type === 'tool_plan')?.plan || {};
    const toolPlanJson = JSON.stringify(toolPlan);
    const eventJson = JSON.stringify(events);
    return {
      answerPreview: answerText.slice(0, 900),
      eventTypes: events.map((event) => event.type),
      hasActionCandidateReady: toolPlanJson.includes('action_candidate_ready'),
      hasCandidateTool: toolPlanJson.includes('create_namespace_cleanup_action_candidate'),
      hasDone: raw.includes('[DONE]'),
      hasInternalLeak: /5174|local fixture|시나리오 처리 범위/.test(answerText),
      hasNaturalActionExecute: eventJson.includes('natural_action_execute'),
      mode,
      mutationsEnabled: toolPlan?.execution_policy?.mutations_enabled,
      ok: response.ok,
      status: response.status,
      textHash: `${answerText.length}:${answerText.slice(0, 80)}`,
      textIncludesActionPlanCandidate: /Action Plan 후보|승인 필요 후보/.test(answerText),
      textIncludesReadOnlyCommand:
        answerText.includes('oc get namespaces') &&
        answerText.includes('oc get all,pvc,route,event'),
      textIncludesReadOnlyMode: answerText.includes('읽기 전용 모드'),
      textIncludesExecuteMode: answerText.includes('실행 가능 모드'),
      textIncludesUnrestrictedMode: answerText.includes('실행 무제한 모드'),
      toolPlanMode: toolPlan?.execution_policy?.mode || '',
      validationStatus: toolPlan?.validation?.status || '',
    };
  };

  const readOnly = await runMode('read-only');
  const execute = await runMode('execute');
  const unrestricted = await runMode('unrestricted');
  const metrics = {
    distinct:
      readOnly.textHash !== execute.textHash &&
      execute.textHash !== unrestricted.textHash &&
      readOnly.toolPlanMode !== execute.toolPlanMode &&
      execute.toolPlanMode !== unrestricted.toolPlanMode,
    execute,
    readOnly,
    unrestricted,
  };

  assert(
    metrics.readOnly.ok &&
      metrics.execute.ok &&
      metrics.unrestricted.ok &&
      metrics.readOnly.hasDone &&
      metrics.execute.hasDone &&
      metrics.unrestricted.hasDone &&
      metrics.readOnly.textIncludesReadOnlyMode &&
      metrics.readOnly.textIncludesReadOnlyCommand &&
      metrics.readOnly.toolPlanMode === 'read_only_review' &&
      metrics.readOnly.mutationsEnabled === false &&
      !metrics.readOnly.hasCandidateTool &&
      !metrics.readOnly.textIncludesActionPlanCandidate &&
      metrics.execute.textIncludesExecuteMode &&
      metrics.execute.toolPlanMode === 'controlled_execution' &&
      metrics.execute.mutationsEnabled === true &&
      metrics.execute.hasCandidateTool &&
      metrics.execute.hasActionCandidateReady &&
      metrics.execute.textIncludesActionPlanCandidate &&
      metrics.unrestricted.textIncludesUnrestrictedMode &&
      metrics.unrestricted.toolPlanMode === 'unrestricted_pending_approval' &&
      metrics.unrestricted.mutationsEnabled === true &&
      metrics.unrestricted.hasCandidateTool &&
      !metrics.unrestricted.hasNaturalActionExecute &&
      metrics.distinct &&
      !metrics.readOnly.hasInternalLeak &&
      !metrics.execute.hasInternalLeak &&
      !metrics.unrestricted.hasInternalLeak,
    'same namespace cleanup question must produce distinct safe answers and Action Plan capability by execution mode',
    metrics,
  );

  return metrics;
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
    const feedbackKey = 'komsco-ai.assistant.message-feedback.v1';
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
    localStorage.setItem(feedbackKey, JSON.stringify([]));
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

const closeAndReopenEmptyAssistant = async () => {
  const surfaceOpen = await evaluate(`Boolean(document.querySelector('.komsco-ai__surface'))`);
  if (surfaceOpen) {
    await evaluate(`document.querySelector('[aria-label="Close AIOps Copilot"]')?.click(); true;`);
    await poll(
      `(() => ({
        fabVisible: Boolean(document.querySelector('.komsco-ai__fab')),
        surfaceOpen: Boolean(document.querySelector('.komsco-ai__surface'))
      }))()`,
      (value) => value?.fabVisible && !value?.surfaceOpen,
      'assistant closed before live mode test',
      10000,
    );
  }

  await openAssistant();
  return poll(
    `(() => ({
      assistantMessages: document.querySelectorAll('.komsco-ai__message--assistant').length,
      userMessages: document.querySelectorAll('.komsco-ai__message--user').length
    }))()`,
    (value) => value?.assistantMessages === 0 && value?.userMessages === 0,
    'assistant reopened with empty current chat before live mode test',
    10000,
  );
};

const setExecutionModeInUi = async (mode) => {
  const labelByMode = {
    execute: ['승인 후 실행 모드', 'Approval-gated execution mode'],
    'read-only': ['읽기 전용 모드', 'Read-only mode'],
    unrestricted: ['실행 무제한 모드', 'Unrestricted execution mode'],
  };
  const ariaLabels = labelByMode[mode];
  const clicked = await evaluate(`(() => {
    const labels = ${JSON.stringify(ariaLabels)};
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
  assert(clicked?.ok, `execution mode ${mode} must be selectable in the real UI`, clicked);
  return poll(
    `(() => {
      const labels = ${JSON.stringify(ariaLabels)};
      const button = Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button'))
        .find((el) => labels.includes(el.getAttribute('aria-label') || ''));
      return {
        label: button?.getAttribute('aria-label') || '',
        pressed: button?.getAttribute('aria-pressed') || 'false',
        text: button?.textContent.trim() || ''
      };
    })()`,
    (value) => value?.pressed === 'true',
    `execution mode ${mode} selected in UI`,
    10000,
  );
};

const setUiLanguageInUi = async (language) => {
  const expectedCode = language === 'en' ? 'EN' : 'KR';
  const currentCode = await evaluate(
    `document.querySelector('.komsco-ai__language-code')?.textContent.trim() || ''`,
  );
  if (currentCode !== expectedCode) {
    await evaluate(`document.querySelector('.komsco-ai__language-button')?.click(); true;`);
  }

  return poll(
    `document.querySelector('.komsco-ai__language-code')?.textContent.trim() || ''`,
    (value) => value === expectedCode,
    `${expectedCode} UI language selected`,
    10000,
  );
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
  assert(changed?.ok && changed.value === question, 'composer textarea must accept the live test question', changed);
  return poll(
    `(() => {
      const button = document.querySelector('.komsco-ai__send');
      const textarea = document.querySelector('.komsco-ai__composer textarea');
      return {
        disabled: Boolean(button?.disabled),
        label: button?.getAttribute('aria-label') || '',
        textareaValue: textarea?.value || ''
      };
    })()`,
    (value) =>
      value?.textareaValue === question &&
      value?.label === '질문 전송' &&
      value?.disabled === false,
    'composer send button enabled for live mode test',
    10000,
  );
};

const sendLiveQuestion = async ({ label, language = 'ko', mode, question }) => {
  await closeAndReopenEmptyAssistant();
  await setUiLanguageInUi(language);
  await setExecutionModeInUi(mode);
  await setComposerValue(question);
  await evaluate(`document.querySelector('.komsco-ai__send')?.click(); true;`);

  return poll(
    `(() => {
      const assistantMessages = Array.from(document.querySelectorAll('.komsco-ai__message--assistant'));
      const userMessages = Array.from(document.querySelectorAll('.komsco-ai__message--user'));
      const latest = assistantMessages[assistantMessages.length - 1];
      latest?.querySelectorAll('.komsco-ai__progress').forEach((el) => {
        el.open = true;
      });
      const content = latest?.querySelector('.komsco-ai__message-content');
      const text = content?.textContent || '';
      const progressTexts = Array.from(latest?.querySelectorAll(
        '.komsco-ai__progress-summary, .komsco-ai__progress-step-copy'
      ) || []).map((el) => el.textContent.replace(/\\s+/g, ' ').trim()).filter(Boolean);
      const progressText = progressTexts.join(' ');
      const source = latest?.querySelector('.komsco-ai__message-source')?.textContent.trim() || '';
      const sourceTitle = latest?.querySelector('.komsco-ai__message-source')?.getAttribute('title') || '';
      const actionPlanButtons = Array.from(
        document.querySelectorAll('.komsco-ai__create-action-plan-button')
      ).map((el) => el.textContent.trim());
      const answerActionButtons = Array.from(
        document.querySelectorAll('.komsco-ai__answer-action-controls .komsco-ai__action-button')
      ).map((el) => el.textContent.trim());
      const loading =
        Boolean(document.querySelector('.komsco-ai__surface--responding')) ||
        document.querySelector('.komsco-ai__send')?.getAttribute('aria-label') === '응답 중지';
      const rawTerms = [
        '5174',
        'local fixture',
        '시나리오 처리 범위',
        'unclear_or_out_of_scope',
        'insufficient_operational_context',
        'request_intent_classifier',
        'confidence',
      ]
        .filter((term) => text.includes(term));
      const rawProgressTerms = [
        'Oc Namespace Inventory',
        'oc read-only namespace inventory',
        'request_intent_classifier',
        'Request Intent Classifier',
        'unclear_or_out_of_scope',
        'insufficient_operational_context',
        'confidence',
      ].filter((term) => progressText.includes(term));
      const scenarioTerms = [
        'KubePodNotReady',
        'CrashLoopBackOff',
        'komsco-ai-local/aiops-scenario',
        '로컬 시뮬레이션',
        'local simulator',
      ].filter((term) => text.includes(term));
      return {
        actionPlanButtons,
        answerActionButtons,
        assistantMessages: assistantMessages.length,
        hasGatewayFallback: source.includes('fallback'),
        hasGatewayDirect: source.includes('Gateway 실조회'),
        hasInternalLeak: rawTerms.length > 0,
        hasScenarioLeak: scenarioTerms.length > 0,
        loading,
        mode: ${JSON.stringify(mode)},
        preview: text.slice(0, 900),
        progressText,
        progressTexts,
        rawProgressTerms,
        rawTerms,
        scenarioTerms,
        source,
        sourceTitle,
        textHash: text.length + ':' + text.slice(0, 80),
        textIncludesClarification:
          text.includes('요청 확인') &&
          text.includes('필요한 정보') &&
          text.includes('지금 가능한 요청 예시') &&
          text.includes('처리 상태: 추가 정보 필요') &&
          text.includes('실행 상태: 변경 작업 없음'),
        progressUsesOperatorLabels:
          progressText.length > 0 &&
          !rawProgressTerms.length &&
          (
            progressText.includes('요청 해석 확인') ||
            progressText.includes('네임스페이스 사용 여부 확인') ||
            progressText.includes('증거 수집 계획')
          ),
        progressUsesEnglishOperatorLabels:
          progressText.length > 0 &&
          !rawProgressTerms.length &&
          !/[가-힣]/.test(progressText) &&
          (
            progressText.includes('Request interpretation') ||
            progressText.includes('Namespace usage check') ||
            progressText.includes('Evidence plan')
          ),
        progressHasKorean:
          /[가-힣]/.test(progressText),
        textIncludesActionPlanCandidate: /Action Plan 후보|승인 필요 후보/.test(text),
        textIncludesExecuteMode: text.includes('실행 가능 모드'),
        textIncludesReadOnlyCommand:
          text.includes('oc get namespaces') &&
          text.includes('oc get all,pvc,route,event'),
        textIncludesReadOnlyMode: text.includes('읽기 전용 모드'),
        textIncludesUnrestrictedMode: text.includes('실행 무제한 모드'),
        userMessages: userMessages.length
      };
    })()`,
    (value) =>
      value?.assistantMessages === 1 &&
      value?.userMessages === 1 &&
      !value?.loading &&
      value?.preview?.length > 160,
    `live UI answer completed for ${label || mode}`,
    90000,
  );
};

const sendLiveModeQuestion = async (mode) =>
  sendLiveQuestion({
    label: `namespace cleanup ${mode}`,
    mode,
    question: NAMESPACE_CLEANUP_QUESTION,
  });

const verifyLiveModeRenderedAnswers = async () => {
  const readOnly = await sendLiveModeQuestion('read-only');
  const execute = await sendLiveModeQuestion('execute');
  const unrestricted = await sendLiveModeQuestion('unrestricted');
  const metrics = {
    distinct:
      readOnly.textHash !== execute.textHash &&
      execute.textHash !== unrestricted.textHash &&
      readOnly.textHash !== unrestricted.textHash,
    execute,
    readOnly,
    unrestricted,
  };

  assert(
    readOnly.textIncludesReadOnlyMode &&
      readOnly.textIncludesReadOnlyCommand &&
      readOnly.actionPlanButtons.length === 0 &&
      !readOnly.textIncludesActionPlanCandidate &&
      readOnly.hasGatewayDirect &&
      !readOnly.hasGatewayFallback &&
      !readOnly.hasInternalLeak &&
      readOnly.progressUsesOperatorLabels,
    'read-only live UI answer must stay query-only and must not expose Action Plan creation CTA',
    metrics,
  );
  assert(
    execute.textIncludesExecuteMode &&
      execute.textIncludesActionPlanCandidate &&
      execute.actionPlanButtons.includes('Action Plan 생성') &&
      execute.hasGatewayDirect &&
      !execute.hasGatewayFallback &&
      !execute.hasInternalLeak &&
      execute.progressUsesOperatorLabels,
    'execute live UI answer must render a distinct approval-gated Action Plan CTA',
    metrics,
  );
  assert(
    unrestricted.textIncludesUnrestrictedMode &&
      unrestricted.textIncludesActionPlanCandidate &&
      unrestricted.actionPlanButtons.includes('Action Plan 생성') &&
      unrestricted.hasGatewayDirect &&
      !unrestricted.hasGatewayFallback &&
      !unrestricted.hasInternalLeak &&
      unrestricted.progressUsesOperatorLabels,
    'unrestricted live UI answer must still render approval-gated Action Plan CTA without auto mutation',
    metrics,
  );
  assert(
    metrics.distinct,
    'same namespace cleanup question must render distinct live UI answers by execution mode',
    metrics,
  );

  return metrics;
};

const verifyLiveClarificationAnswers = async () => {
  const terse = await sendLiveQuestion({
    label: 'terse unclear Korean input',
    mode: 'read-only',
    question: UNCLEAR_CHAT_QUESTIONS[0],
  });
  const insult = await sendLiveQuestion({
    label: 'non-operational insult input',
    mode: 'execute',
    question: UNCLEAR_CHAT_QUESTIONS[1],
  });
  const metrics = { insult, terse };

  for (const item of [terse, insult]) {
    assert(
      item.textIncludesClarification &&
        item.source === '요청 확인' &&
        !item.hasGatewayDirect &&
        !item.hasGatewayFallback &&
        !item.hasInternalLeak &&
        !item.hasScenarioLeak &&
        item.progressUsesOperatorLabels &&
        item.actionPlanButtons.length === 0 &&
        item.answerActionButtons.length === 0 &&
        !item.textIncludesActionPlanCandidate,
      'unclear live UI input must ask for clarification without hardcoded scenario, internal routing, or Action Plan CTA',
      metrics,
    );
  }

  return metrics;
};

const verifyLiveEnglishProgressLabels = async () => {
  const unclear = await sendLiveQuestion({
    label: 'English UI unclear Korean input',
    language: 'en',
    mode: 'read-only',
    question: UNCLEAR_CHAT_QUESTIONS[0],
  });
  const namespace = await sendLiveQuestion({
    label: 'English UI namespace progress',
    language: 'en',
    mode: 'execute',
    question: NAMESPACE_CLEANUP_QUESTION,
  });
  const metrics = { namespace, unclear };

  for (const item of [unclear, namespace]) {
    assert(
      item.progressUsesEnglishOperatorLabels &&
        !item.progressHasKorean &&
        !item.rawProgressTerms.length,
      'English UI progress labels must stay English and hide raw operator names',
      metrics,
    );
  }

  await setUiLanguageInUi('ko');
  return metrics;
};

const openHistory = async () => {
  const before = await evaluate(`(() => {
    const sidebar = document.querySelector('.komsco-ai__history-sidebar');
    const rect = sidebar?.getBoundingClientRect();
    return {
      isOpen: Boolean(rect && rect.width > 160)
    };
  })()`);
  if (!before?.isOpen) {
    await evaluate(`document.querySelector('.komsco-ai__sidebar-toggle')?.click(); true;`);
  }
  await poll(
    `(() => {
      const sidebar = document.querySelector('.komsco-ai__history-sidebar');
      const rect = sidebar?.getBoundingClientRect();
      return Boolean(rect && rect.width > 160);
    })()`,
    Boolean,
    'history sidebar open',
    60000,
  );
};

const openHistoryActionList = async (rowIndex = 0) => {
  await openHistory();
  const openedMenu = await evaluate(`(() => {
    const rows = Array.from(document.querySelectorAll('.komsco-ai__history-item-row'));
    const row = rows[${rowIndex}];
    const trigger = row?.querySelector('.komsco-ai__history-item-menu-trigger');
    if (!trigger) return { ok: false, reason: 'missing trigger', rowCount: rows.length };
    trigger.click();
    return { ok: true, rowCount: rows.length };
  })()`);
  assert(openedMenu?.ok, 'history row menu must be openable', openedMenu);
  await poll(
    `Boolean(document.querySelector('.komsco-ai__history-item-menu-panel'))`,
    Boolean,
    'history row menu panel',
    10000,
  );
  const clickedActionHistory = await evaluate(`(() => {
    const items = Array.from(document.querySelectorAll('.komsco-ai__history-item-menu-panel [role="menuitem"]'));
    const actionItem = items.find((item) => item.textContent.includes('조치내역'));
    if (!actionItem) {
      return { ok: false, labels: items.map((item) => item.textContent.trim()) };
    }
    actionItem.click();
    return { ok: true, labels: items.map((item) => item.textContent.trim()) };
  })()`);
  assert(clickedActionHistory?.ok, 'history row menu must expose 조치내역', clickedActionHistory);
  await poll(
    `(() => {
      const rows = Array.from(document.querySelectorAll('.komsco-ai__history-item-row'));
      const row = rows[${rowIndex}];
      return Boolean(row?.querySelector('.komsco-ai__history-action-refs'));
    })()`,
    Boolean,
    'history action list expanded',
    10000,
  );
};

const ensureFixtureConversationLoaded = async () => {
  const hasAssistantMessage = await evaluate(
    `Boolean(document.querySelector('.komsco-ai__message--assistant .komsco-ai__message-content'))`,
  );
  if (hasAssistantMessage) {
    return;
  }

  await openHistory();
  const clickedConversation = await evaluate(`(() => {
    const item = document.querySelector('.komsco-ai__history-item-row .komsco-ai__history-item');
    if (!item) return false;
    item.click();
    return true;
  })()`);
  assert(clickedConversation, 'history fixture conversation must be loadable from the sidebar');
  await poll(
    `Boolean(document.querySelector('.komsco-ai__message--assistant .komsco-ai__message-content'))`,
    Boolean,
    'fixture conversation loaded from history',
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
  const emptyAfterReload = await evaluate(`(() => ({
    assistantMessages: document.querySelectorAll('.komsco-ai__message--assistant').length,
    userMessages: document.querySelectorAll('.komsco-ai__message--user').length
  }))()`);
  assert(
    emptyAfterReload.assistantMessages === 0 && emptyAfterReload.userMessages === 0,
    'refresh/reopen must start with an empty current chat; prior conversations stay in history',
    emptyAfterReload,
  );
  await ensureFixtureConversationLoaded();

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
  assert(metrics.disabledActionButtons === 0, 'read-only mode must not render inert disabled action buttons', metrics);
  assert(metrics.rawTerms.length === 0, 'default assistant answer must not expose raw internal terms', metrics);

  const actionMetrics = await evaluate(`(() => {
    const labelOf = (el) => el.getAttribute('aria-label') || el.textContent.trim();
    const userActions = Array.from(
      document.querySelectorAll('.komsco-ai__message--user [data-message-actions="user"] button')
    ).map(labelOf);
    const assistantActions = Array.from(
      document.querySelectorAll('.komsco-ai__message--assistant [data-message-actions="assistant"] button')
    ).map(labelOf);
    const allMessageActions = Array.from(document.querySelectorAll('.komsco-ai__message-actions button')).map(labelOf);
    return {
      assistantActions,
      hiddenFullscreenInMessageActions: allMessageActions.some((label) => /full screen|fullscreen|전체.?화면/i.test(label)),
      userActions
    };
  })()`);
  assert(
    JSON.stringify(actionMetrics.userActions) === JSON.stringify(['수정해서 다시 보내기', '복사']),
    'user message footer must expose edit-resend and copy only',
    actionMetrics,
  );
  assert(
    JSON.stringify(actionMetrics.assistantActions) ===
      JSON.stringify(['복사', '좋은 답변', '좋지 않은 답변']),
    'assistant message footer must expose copy, good response, and bad response only',
    actionMetrics,
  );
  assert(
    !actionMetrics.hiddenFullscreenInMessageActions,
    'message footer must not contain a fullscreen action',
    actionMetrics,
  );

  const editResendMetrics = await evaluate(`(() => {
    const edit = document.querySelector('.komsco-ai__message--user [aria-label="수정해서 다시 보내기"]');
    const textarea = document.querySelector('.komsco-ai__composer textarea');
    edit?.click();
    return {
      textareaValue: textarea?.value || '',
      userText: document.querySelector('.komsco-ai__message--user .komsco-ai__message-content')?.textContent.trim() || ''
    };
  })()`);
  assert(
    editResendMetrics.textareaValue === editResendMetrics.userText,
    'edit-resend must move the exact user message back into the composer',
    editResendMetrics,
  );

  const feedbackComment = '검증 스크립트: 답변 예시는 더 짧게 유지';
  const feedbackClickMetrics = await evaluate(`(() => {
    const down = document.querySelector('.komsco-ai__message--assistant [aria-label="좋지 않은 답변"]');
    down?.click();
    const form = document.querySelector('.komsco-ai__feedback-comment');
    const input = form?.querySelector('input');
    return {
      formTextBeforeSubmit: form?.textContent.trim() || '',
      inputValue: input?.value || '',
      pressed: down?.getAttribute('aria-pressed') || ''
    };
  })()`);
  assert(
    feedbackClickMetrics.pressed === 'true' &&
      feedbackClickMetrics.formTextBeforeSubmit.includes('무엇을 개선할까요?') &&
      feedbackClickMetrics.inputValue === '',
    'thumbs-down feedback must open an editable tester comment rail',
    feedbackClickMetrics,
  );
  await evaluate(`(() => {
    const input = document.querySelector('.komsco-ai__feedback-comment input');
    if (!input) return false;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, ${JSON.stringify(feedbackComment)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  const feedbackDraftMetrics = await poll(
    `(() => {
      const form = document.querySelector('.komsco-ai__feedback-comment');
      const input = form?.querySelector('input');
      const submit = form?.querySelector('button');
      return {
        buttonDisabledBeforeSubmit: Boolean(submit?.disabled),
        buttonTextBeforeSubmit: submit?.textContent.trim() || '',
        inputValue: input?.value || '',
        ok: input?.value === ${JSON.stringify(feedbackComment)} &&
          submit?.textContent.trim() === '저장' &&
          !submit?.disabled
      };
    })()`,
    (value) => value?.ok,
    'editable feedback comment dirty state',
    10000,
  );
  await evaluate(`document.querySelector('.komsco-ai__feedback-comment button')?.click(); true;`);
  const feedbackStored = await poll(
    `(() => {
      const feedbackKey = 'komsco-ai.assistant.message-feedback.v1';
      const records = JSON.parse(localStorage.getItem(feedbackKey) || '[]');
      const latest = records[records.length - 1] || {};
      return {
        latest,
        ok: latest.rating === 'down' && latest.optionalComment === ${JSON.stringify(feedbackComment)}
      };
    })()`,
    (value) => value?.ok,
    'local feedback payload with optional comment',
    10000,
  );
  const feedbackGateway = await poll(
    `(async () => {
      const response = await fetch('/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status');
      if (!response.ok) return { ok: false, status: response.status };
      const payload = await response.json();
      const records = payload?.spec?.records?.chatFeedback || [];
      const latest = records[records.length - 1] || {};
      return {
        latest,
        ok: latest?.spec?.rating === 'down' && latest?.spec?.optionalComment === ${JSON.stringify(feedbackComment)}
      };
    })()`,
    (value) => value?.ok,
    'gateway feedback record with optional comment',
    30000,
  );

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

  await evaluate(`document.querySelector('.komsco-ai__language-button')?.click(); true;`);
  const englishChromeMetrics = await poll(
    `(() => {
      const modeLabels = Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button span'))
        .map((el) => el.textContent.trim());
      const executionBadgeText = document.querySelector('.komsco-ai__scope-list--execution')?.textContent || '';
      const languageCode = document.querySelector('.komsco-ai__language-code')?.textContent.trim() || '';
      const sidebar = document.querySelector('.komsco-ai__history-sidebar');
      const sidebarRect = sidebar?.getBoundingClientRect();
      if (!(sidebarRect && sidebarRect.width > 160)) {
        document.querySelector('.komsco-ai__sidebar-toggle')?.click();
      }
      const trigger = document.querySelector('.komsco-ai__history-item-row .komsco-ai__history-item-menu-trigger');
      if (trigger && !document.querySelector('.komsco-ai__history-item-menu-panel')) {
        trigger.click();
      }
      const menuLabels = Array.from(
        document.querySelectorAll('.komsco-ai__history-item-menu-panel [role="menuitem"]')
      ).map((item) => item.textContent.trim());
      const controls = Array.from(document.querySelectorAll(
        '.komsco-ai__language-button, .komsco-ai__header-actions .komsco-ai__icon-button, .komsco-ai__mode-toggle-button'
      ));
      const overflowingControls = controls
        .filter((el) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
        .map((el) => ({
          label: el.getAttribute('aria-label') || el.textContent.trim(),
          className: String(el.className),
          sw: el.scrollWidth,
          cw: el.clientWidth,
          sh: el.scrollHeight,
          ch: el.clientHeight
        }));
      return {
        languageCode,
        menuLabels,
        modeLabels,
        ok:
          languageCode === 'EN' &&
          modeLabels.includes('Read only') &&
          modeLabels.includes('Execute') &&
          modeLabels.includes('Unrestricted') &&
          menuLabels.includes('Rename') &&
          menuLabels.includes('Action history') &&
          menuLabels.includes('Delete chat') &&
          !modeLabels.join(' ').includes('읽기 전용') &&
          !modeLabels.join(' ').includes('실행 무제한') &&
          !menuLabels.join(' ').includes('조치내역') &&
          !executionBadgeText.includes('읽기 전용') &&
          !executionBadgeText.includes('실행 가능') &&
          !executionBadgeText.includes('실행 무제한') &&
          overflowingControls.length === 0,
        executionBadgeText,
        overflowingControls
      };
    })()`,
    (value) => value?.ok,
    'English language toggle must translate execution modes and history menu without overflow',
    10000,
  );
  await evaluate(`(() => {
    const actionHistory = Array.from(
      document.querySelectorAll('.komsco-ai__history-item-menu-panel [role="menuitem"]')
    ).find((item) => item.textContent.includes('Action history'));
    actionHistory?.click();
    document.querySelector('.komsco-ai__language-button')?.click();
    return true;
  })()`);
  const koreanRestoredMetrics = await poll(
    `(() => {
      const modeLabels = Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button span'))
        .map((el) => el.textContent.trim());
      const languageCode = document.querySelector('.komsco-ai__language-code')?.textContent.trim() || '';
      return {
        languageCode,
        modeLabels,
        ok:
          languageCode === 'KR' &&
          modeLabels.includes('읽기 전용') &&
          modeLabels.includes('실행 가능') &&
          modeLabels.includes('실행 무제한')
      };
    })()`,
    (value) => value?.ok,
    'Korean language toggle restore',
    10000,
  );
  await evaluate(`(() => {
    const sidebar = document.querySelector('.komsco-ai__history-sidebar');
    const rect = sidebar?.getBoundingClientRect();
    if (rect && rect.width > 160) {
      document.querySelector('.komsco-ai__sidebar-toggle')?.click();
    }
    return true;
  })()`);
  await poll(
    `(() => {
      const sidebar = document.querySelector('.komsco-ai__history-sidebar');
      const rect = sidebar?.getBoundingClientRect();
      return !rect || rect.width <= 160;
    })()`,
    Boolean,
    'history sidebar closed before resize acceptance',
    10000,
  );

  const resizeStartMetrics = await evaluate(`(() => {
    const surface = document.querySelector('.komsco-ai__surface');
    const unlock = document.querySelector('[aria-label="창 크기 잠금 해제"]');
    const before = surface?.getBoundingClientRect();
    window.__v0281ResizeBefore = before
      ? { height: Math.round(before.height), width: Math.round(before.width), left: Math.round(before.left), right: Math.round(before.right), top: Math.round(before.top), bottom: Math.round(before.bottom) }
      : null;
    unlock?.click();
    return {
      before: window.__v0281ResizeBefore,
      clicked: Boolean(unlock)
    };
  })()`);
  assert(resizeStartMetrics.clicked, 'resize unlock button must be clickable', resizeStartMetrics);
  const resizeUnlockMetrics = await poll(
    `(() => {
      const surface = document.querySelector('.komsco-ai__surface');
      const handles = Array.from(document.querySelectorAll('.komsco-ai__resize-handle'))
        .map((el) => Array.from(el.classList).find((item) => item.startsWith('komsco-ai__resize-handle--'))?.replace('komsco-ai__resize-handle--', ''))
        .filter(Boolean)
        .sort();
      const workspace = document.querySelector('.komsco-ai__workspace');
      const workspaceRect = workspace?.getBoundingClientRect();
      const expectedHandles = ['e', 'n', 'ne', 'nw', 's', 'se', 'sw', 'w'];
      return {
        handles,
        hasAllHandles: JSON.stringify(handles) === JSON.stringify(expectedHandles),
        resizeUnlocked: surface?.classList.contains('komsco-ai__surface--resize-unlocked') || false,
        workspaceHeight: workspaceRect ? Math.round(workspaceRect.height) : 0
      };
    })()`,
    (value) => value?.resizeUnlocked && value?.hasAllHandles && value?.workspaceHeight >= 220,
    'resize unlock handles and non-collapsed workspace',
    10000,
  );
  const resizeHandleMetrics = await evaluate(`(() => {
    const w = document.querySelector('.komsco-ai__resize-handle--w');
    const wRect = w?.getBoundingClientRect();
    return {
      ok: Boolean(w && wRect),
      x: wRect ? Math.round(wRect.left + wRect.width / 2) : 0,
      y: wRect ? Math.round(wRect.top + wRect.height / 2) : 0
    };
  })()`);
  assert(resizeHandleMetrics.ok, 'west resize handle must be measurable for real mouse drag', resizeHandleMetrics);
  await send('Input.dispatchMouseEvent', {
    button: 'left',
    buttons: 1,
    clickCount: 1,
    type: 'mousePressed',
    x: resizeHandleMetrics.x,
    y: resizeHandleMetrics.y,
  });
  await send('Input.dispatchMouseEvent', {
    buttons: 1,
    type: 'mouseMoved',
    x: resizeHandleMetrics.x - 64,
    y: resizeHandleMetrics.y,
  });
  await send('Input.dispatchMouseEvent', {
    button: 'left',
    buttons: 0,
    clickCount: 1,
    type: 'mouseReleased',
    x: resizeHandleMetrics.x - 64,
    y: resizeHandleMetrics.y,
  });
  const resizeMetrics = await poll(
    `(() => {
      const before = window.__v0281ResizeBefore;
      const surface = document.querySelector('.komsco-ai__surface');
      const after = surface?.getBoundingClientRect();
      const workspace = document.querySelector('.komsco-ai__workspace');
      const workspaceRect = workspace?.getBoundingClientRect();
      return {
        after: after ? { height: Math.round(after.height), width: Math.round(after.width), left: Math.round(after.left), right: Math.round(after.right), top: Math.round(after.top), bottom: Math.round(after.bottom) } : null,
        before,
        handles: ${JSON.stringify(resizeUnlockMetrics.handles)},
        hasAllHandles: ${JSON.stringify(resizeUnlockMetrics.hasAllHandles)},
        resizeUnlocked: surface?.classList.contains('komsco-ai__surface--resize-unlocked') || false,
        sizeChanged: Boolean(before && after && (Math.abs(after.width - before.width) >= 8 || Math.abs(after.height - before.height) >= 8)),
        viewport: { height: window.innerHeight, width: window.innerWidth },
        workspaceHeight: workspaceRect ? Math.round(workspaceRect.height) : 0
      };
    })()`,
    (value) =>
      value?.resizeUnlocked &&
      value?.hasAllHandles &&
      value?.workspaceHeight >= 220 &&
      value?.sizeChanged &&
      value?.after?.left >= 0 &&
      value?.after?.top >= 0 &&
      value?.after?.right <= value?.viewport?.width + 1 &&
      value?.after?.bottom <= value?.viewport?.height + 1,
    'unlocked assistant resize result',
    10000,
  );
  assert(
    resizeMetrics.resizeUnlocked &&
      resizeMetrics.hasAllHandles &&
      resizeMetrics.workspaceHeight >= 220 &&
      resizeMetrics.sizeChanged &&
      resizeMetrics.after.left >= 0 &&
      resizeMetrics.after.top >= 0 &&
      resizeMetrics.after.right <= resizeMetrics.viewport.width + 1 &&
      resizeMetrics.after.bottom <= resizeMetrics.viewport.height + 1,
    'unlocked assistant must resize from all boundaries without collapsing or leaving the viewport',
    resizeMetrics,
  );

  await evaluate(`document.querySelector('[aria-label="Close AIOps Copilot"]')?.click(); true;`);
  const closeMetrics = await poll(
    `(() => ({
      fabVisible: Boolean(document.querySelector('.komsco-ai__fab')),
      surfaceOpen: Boolean(document.querySelector('.komsco-ai__surface'))
    }))()`,
    (value) => value?.fabVisible && !value?.surfaceOpen,
    'assistant closes to FAB after resize',
    10000,
  );
  await evaluate(`document.querySelector('.komsco-ai__fab')?.click(); true;`);
  const closeReopenMetrics = await poll(
    `(() => {
    const surface = document.querySelector('.komsco-ai__surface');
    const rect = surface?.getBoundingClientRect();
    return {
      assistantMessages: document.querySelectorAll('.komsco-ai__message--assistant').length,
      closeMetrics: ${JSON.stringify(closeMetrics)},
      fabVisible: Boolean(document.querySelector('.komsco-ai__fab')),
      handleCount: document.querySelectorAll('.komsco-ai__resize-handle').length,
      rect: rect ? { height: Math.round(rect.height), width: Math.round(rect.width), left: Math.round(rect.left), right: Math.round(rect.right), top: Math.round(rect.top), bottom: Math.round(rect.bottom) } : null,
      resizeUnlocked: surface?.classList.contains('komsco-ai__surface--resize-unlocked') || false,
      surfaceOpen: Boolean(surface),
      transform: surface ? getComputedStyle(surface).transform : '',
      userMessages: document.querySelectorAll('.komsco-ai__message--user').length,
      viewport: { height: window.innerHeight, width: window.innerWidth }
    };
  })()`,
    (value) =>
      value?.closeMetrics?.fabVisible &&
      value?.surfaceOpen &&
      !value?.resizeUnlocked &&
      value?.handleCount === 0 &&
      value?.assistantMessages === 0 &&
      value?.userMessages === 0 &&
      value?.rect?.left >= 0 &&
      value?.rect?.top >= 0 &&
      value?.rect?.right <= value?.viewport?.width + 1 &&
      value?.rect?.bottom <= value?.viewport?.height + 1,
    'assistant reopens cleanly after resize close',
    10000,
  );
  assert(
    closeReopenMetrics.closeMetrics?.fabVisible &&
      closeReopenMetrics.surfaceOpen &&
      !closeReopenMetrics.resizeUnlocked &&
      closeReopenMetrics.handleCount === 0 &&
      closeReopenMetrics.assistantMessages === 0 &&
      closeReopenMetrics.userMessages === 0 &&
      closeReopenMetrics.rect.left >= 0 &&
      closeReopenMetrics.rect.top >= 0 &&
      closeReopenMetrics.rect.right <= closeReopenMetrics.viewport.width + 1 &&
      closeReopenMetrics.rect.bottom <= closeReopenMetrics.viewport.height + 1,
    'closing and reopening after resize must reset to a clean, unbroken empty chat surface',
    closeReopenMetrics,
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

  await openHistoryActionList(0);
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
  await openHistoryActionList(1);
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

  const liveModeRenderedAnswers = await verifyLiveModeRenderedAnswers();
  const liveClarificationAnswers = await verifyLiveClarificationAnswers();
  const liveEnglishProgressLabels = await verifyLiveEnglishProgressLabels();

  return {
    feedbackGateway,
    feedbackStored,
    fixture,
    historyMetrics,
    liveClarificationAnswers,
    liveEnglishProgressLabels,
    liveModeRenderedAnswers,
    metrics,
  };
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
  const modeContracts = await verifyModeAnswerContracts();
  const chromeVersion = await setupBrowser();
  const consoleResult = await verifyConsoleAssistant();
  const portalResult = await verifyStandalonePortal();

  chromeWebSocket.close();
  chromeProcess.kill('SIGTERM');

  const output = {
    chrome: chromeVersion,
    consoleResult,
    modeContracts,
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
