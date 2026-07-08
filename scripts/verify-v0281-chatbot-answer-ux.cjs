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
  const assistantConstants = readFile('komsco-ai-console-plugin/src/components/assistant.constants.tsx');
  const historyPanel = readFile('komsco-ai-console-plugin/src/components/AssistantHistoryPanel.tsx');
  const insightRail = readFile('komsco-ai-console-plugin/src/components/AssistantInsightRail.tsx');
  const insightRailHelpers = readFile('komsco-ai-console-plugin/src/components/assistant.insightRailHelpers.tsx');
  const launcher = readFile('komsco-ai-console-plugin/src/components/AssistantLauncher.tsx');
  const composer = readFile('komsco-ai-console-plugin/src/components/AssistantComposer.tsx');
  const conversationRail = readFile('komsco-ai-console-plugin/src/components/AssistantConversationRail.tsx');
  const evidenceFooter = readFile('komsco-ai-console-plugin/src/components/AssistantEvidenceFooter.tsx');
  const imageLightbox = readFile('komsco-ai-console-plugin/src/components/AssistantImageLightbox.tsx');
  const messageHeader = readFile('komsco-ai-console-plugin/src/components/AssistantMessageHeader.tsx');
  const messageContent = readFile('komsco-ai-console-plugin/src/components/AssistantMessageContent.tsx');
  const progressTimeline = readFile('komsco-ai-console-plugin/src/components/AssistantProgressTimeline.tsx');
  const toolPlanFooter = readFile('komsco-ai-console-plugin/src/components/AssistantToolPlanFooter.tsx');
  const gatewayService = readFile('komsco-ai-console-plugin/src/services/aiGateway.ts');
  const localGateway = readFile('scripts/serve-v0281-local-aiops-gateway.cjs');
  const css = readFile('komsco-ai-console-plugin/src/components/assistant.css');
  const portal = readFile('komsco-ai-portal/src/App.tsx');

  assert(actionRecords.includes('ActionStageIcon'), 'Action Plan cards must expose lifecycle icons');
  assert(
    actionRecords.includes("const readOnlyBlocked = executionMode === 'read-only'") &&
      actionRecords.includes('읽기 전용 모드입니다. 승인·실행은 보내지 않고 제한 사유만 확인합니다.') &&
      actionRecords.includes('읽기 전용 모드에서는 승인·실행 요청을 보내지 않습니다.') &&
      actionRecords.includes('isDisabled={busy || Boolean(item.disabledReason)}'),
    'read-only and policy-blocked action buttons must stay visible but actually disabled with reasons',
  );
  assert(
    actionRecords.includes("strong>Action Plan</strong"),
    'answer action section must be named Action Plan',
  );
  assert(
    actionRecords.includes('getActionRecordToolLabel(record, language)') &&
      actionRecords.includes('getActionToolLabel(ref.toolName, language)') &&
      actionRecords.includes("'기록 원문'") &&
      !actionRecords.includes("'상세보기 (JSON)'"),
    'default action lifecycle rail must show human action labels and hide raw JSON behind record detail',
  );
  assert(
    historyPanel.includes('HistoryActionStageIcon'),
    'history sidebar action refs must include stage icons',
  );
  assert(
    historyPanel.includes('historyActionDetailLabel') &&
      historyPanel.includes('getActionToolLabel(actionRef.toolName, language)') &&
      !historyPanel.includes('`${actionRef.toolName} · ${actionRef.targetKey}`'),
    'history action refs must render human action labels instead of raw tool names',
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
    messageHeader.includes('Gateway live query') &&
      messageHeader.includes('OCP guide') &&
      messageHeader.includes('Request clarification') &&
      messageHeader.includes('Lightspeed connected') &&
      messageHeader.includes('AIOps for OCP') &&
      messageHeader.includes('Deterministic lookup did not call Lightspeed'),
    'assistant message source badges and titles must distinguish OCP guidance, live Gateway queries, clarification, and Lightspeed in English mode',
  );
  assert(
    conversationRail.includes('AIOps for OCP') &&
      messageHeader.includes("return 'AIOps for OCP';"),
    'assistant sender labels must use the official AIOps for OCP name',
  );
  assert(
    launcher.includes('publicFeedbackAnswerContract') &&
      launcher.includes('publicFeedbackSource') &&
      insightRail.includes('publicFeedbackValue'),
    'feedback payload/export must normalize local fixture/debug source values before tester review',
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
    messageContent.includes("terminal: '터미널 확인 명령'") &&
      messageContent.includes('터미널에서 안전하게 확인할 read-only 명령'),
    'runbook answer must render terminal command sections instead of truncating them under Action Plan',
  );
  assert(
    messageContent.includes("decisions: 'Namespace Decisions'") &&
      messageContent.includes("decisions: '판단 결과'") &&
      messageContent.includes('isMarkdownTableSeparator') &&
      messageContent.includes('komsco-ai__runbook-table-block'),
    'runbook answer must render namespace decision tables as a dedicated section',
  );
  assert(
    messageContent.includes('onPreviewAttachment, language') &&
      readFile('komsco-ai-console-plugin/src/components/assistant.render.tsx').includes(
        "copyCommand: 'Copy command'",
      ) &&
      readFile('komsco-ai-console-plugin/src/components/assistant.render.tsx').includes(
        "showWrapped: 'Wrap lines'",
      ),
    'assistant formatted content controls must localize code and attachment actions in English mode',
  );
  assert(
    launcher.includes('showActionPrepGroup') &&
      launcher.includes('data-aiops-action-prep') &&
      css.includes('.komsco-ai__action-prep'),
    'assistant query plan and Action Plan candidates must render as one visual preparation group when both exist',
  );
  assert(
      launcher.includes('buildEvidenceCopyText(') &&
      launcher.includes('uiLanguage') &&
      launcher.includes('language={uiLanguage}') &&
      evidenceFooter.includes("isKo ? '확인 결과' : 'Evidence'") &&
      evidenceFooter.includes('komsco-ai__footer-inline-summary') &&
      evidenceFooter.includes('komsco-ai__footer-detail-toggle') &&
      toolPlanFooter.includes("isKo ? '조회 계획' : 'Query plan'") &&
      toolPlanFooter.includes('executionMode: AiopsExecutionMode') &&
      launcher.includes('executionMode={executionMode}') &&
      toolPlanFooter.includes('komsco-ai__footer-inline-summary') &&
      toolPlanFooter.includes('komsco-ai__footer-detail-toggle'),
    'assistant evidence and tool-plan footers must localize visible details in English mode',
  );
  assert(
    launcher.includes('<AssistantImageLightbox') &&
      launcher.includes('language={uiLanguage}') &&
      imageLightbox.includes("language === 'en' ? `Preview ${attachment.name}`") &&
      imageLightbox.includes("language === 'en' ? 'Close image preview'"),
    'assistant image preview dialog must localize close and preview labels in English mode',
  );
  assert(
    composer.includes('CoolPaperclipIcon') &&
      composer.includes('className="komsco-ai__tool-button komsco-ai__attach"') &&
      composer.includes('onClick={() => fileInputRef.current?.click()}') &&
      composer.includes('onDragEnter={onDragEnter}') &&
      composer.includes('onDrop={onDrop}') &&
      composer.includes('onPaste={onPaste}') &&
      launcher.includes('filesFromClipboardData(event.clipboardData)') &&
      launcher.includes('Array.from(data.items ?? [])') &&
      launcher.includes('fallbackImageName(file, mimeType)') &&
      launcher.includes('filesFromClipboardData(event.dataTransfer)'),
    'assistant image input must support paperclip file selection, drag/drop, and pasted clipboard images through one attachment pipeline',
  );
  assert(
    progressTimeline.includes('Test Pod creation preflight') &&
      progressTimeline.includes('Target namespace and server check') &&
      assistantConstants.includes("oc_test_pod_create_preflight: '테스트 Pod 생성 사전 확인'"),
    'progress timeline must translate test Pod preflight tool names into product labels',
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
    insightRailHelpers.includes('Gateway 검증 환경') &&
      historyPanel.includes('getHistoryUserLabel(authSubject, authSubjectError, uiLanguage)') &&
      historyPanel.includes('검증 사용자') &&
      historyPanel.includes('getClusterHost(clusterSummary?.apiUrl, uiLanguage)'),
    'history user footer must hide local fixture user and invalid hosts behind human validation labels',
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
      launcher.includes('좋지 않은 답변') &&
      launcher.includes('komsco-ai__message-action-status') &&
      launcher.includes('좋아요 선택됨') &&
      launcher.includes('싫어요 선택됨') &&
      launcher.includes('좋아요 저장됨') &&
      launcher.includes('싫어요 저장됨') &&
      css.includes('.komsco-ai__message-action-status'),
    'message-level actions must preserve controls and distinguish selected feedback from saved feedback',
  );
  assert(
    launcher.includes('komsco-ai__feedback-comment') &&
      launcher.includes('feedbackCommentPlaceholder') &&
      launcher.includes('Note what was wrong or confusing') &&
      launcher.includes('Note what should stay this good') &&
      launcher.includes('기록: 브라우저+Gateway') &&
      launcher.includes('STORED_MESSAGE_FEEDBACK_KEY') &&
      css.includes('.komsco-ai__feedback-prompt') &&
      launcher.includes('submitMessageFeedbackComment') &&
      launcher.includes('optionalComment'),
    'assistant feedback must support tester comments and disclose where feedback is stored',
  );
  assert(
    insightRail.includes("'답변 피드백'") &&
      insightRail.includes("'Answer feedback'") &&
      insightRail.includes("'최근 개선 의견'") &&
      insightRail.includes("'Latest needs-work note'") &&
      insightRail.includes("'최근 좋았던 점'") &&
      insightRail.includes("'Latest good note'") &&
      insightRail.includes("'피드백 JSON 복사'") &&
      insightRail.includes("'Copy feedback JSON'") &&
      insightRail.includes('komsco-ai__rail-feedback-copy') &&
      insightRail.includes('latestByRating') &&
      insightRail.includes('chatFeedback') &&
      css.includes('.komsco-ai__rail-feedback-copy'),
    'insight rail must expose separate good and needs-work feedback notes and export them for tester review',
  );
  assert(
    launcher.includes('.then(() => refreshAiopsRuntimeStatus())'),
    'chat feedback persistence must refresh AIOps status so the rail updates without waiting for the next poll',
  );
  assert(
    gatewayService.includes('optionalComment?: string') &&
      gatewayService.includes('source?: string') &&
      gatewayService.includes('/v1/chat/feedback'),
    'console gateway service must include deployable chat feedback payload contract',
  );
  assert(
    localGateway.includes('optionalComment: body.optionalComment') &&
      localGateway.includes('source: body.source || body.answerSource') &&
      localGateway.includes('LOCAL_CHAT_FEEDBACK.set'),
    'local fixture gateway must persist feedback comments for browser acceptance tests',
  );
  assert(
    localGateway.includes('parseTestPodCreateRequest') &&
      localGateway.includes('create_test_pod_action_candidate') &&
      localGateway.includes('namespace_check_deferred') &&
      localGateway.includes('실행 전 namespace 재확인 필요'),
    'local gateway must support test Pod creation as an approval-gated execution request',
  );
  assert(
    localGateway.includes("source: 'copilot_reply'") &&
      localGateway.includes('casualLocalChatAnswer') &&
      launcher.includes("event.source === 'copilot_reply'") &&
      messageHeader.includes("message.answerSource === 'copilot_reply'"),
    'short casual chat must render as an AIOps reply, not as Gateway live query or request clarification',
  );
  assert(
    localGateway.includes('approvalId is required; execution never creates approval automatically') &&
      !localGateway.includes("body.approvalId || makeApprovalRecord('lab-auto-unrestricted'") &&
      launcher.includes("action.step === 'approve-execute-plan'") &&
      launcher.includes("executionMode !== 'unrestricted'") &&
      launcher.includes('canUseUnrestrictedCommands(aiopsStatus)'),
    'approval and execution must be separated: execute cannot auto-create approvals, and approve+execute is unrestricted-only',
  );
  assert(
    localGateway.includes('isGeneralConceptQuestion') &&
      localGateway.includes('generalConceptLocalAnswer') &&
      localGateway.includes("intent: 'general_concept'"),
    'OpenShift concept questions must use the fast OCP guide path instead of live operational lookup',
  );
  assert(
    /\.komsco-ai__surface \.komsco-ai__empty-mark\s*\{[\s\S]*background: transparent;[\s\S]*border: 0;[\s\S]*box-shadow: none;[\s\S]*\}/.test(css) &&
      /\.komsco-ai__surface \.komsco-ai__empty-logo\s*\{[\s\S]*width: 52px;[\s\S]*height: 52px;[\s\S]*\}/.test(css),
    'empty-state assistant icon should be enlarged without an outer card frame',
  );
  assert(
    css.includes('v0.2.8.1: responding header light rail') &&
      css.includes('.komsco-ai__surface.komsco-ai__surface--responding .komsco-ai__header::after') &&
      !css.includes('komsco-ai-header-bottom-scan') &&
      !css.includes('komsco-ai-header-bottom-glow'),
    'assistant header must keep a calm static rail while responding, not a scanner animation',
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

const fetchTextStatus = async (url) => {
  const res = await fetch(url);
  const text = await res.text();
  return {
    contentType: res.headers.get('content-type') || '',
    ok: res.ok,
    status: res.status,
    text,
    url,
  };
};

const resetLocalGatewayState = async () => {
  const resetUrl = `${localGatewayUrl}/v1/local/reset`;
  const response = await fetch(resetUrl, { method: 'POST' });
  if (response.status === 404) {
    return { skipped: true, status: 404 };
  }
  const payload = await response.json().catch(() => ({}));
  assert(response.ok && payload.ok === true, 'local gateway reset endpoint must succeed', {
    payload,
    status: response.status,
    url: resetUrl,
  });
  return payload;
};

const isJavaScriptResponse = (result) =>
  result.ok &&
  /(?:application|text)\/javascript|application\/x-javascript/i.test(result.contentType);

const verifyConsolePluginChunkProxy = async () => {
  const base = new URL('/api/plugins/cywell-aiops-console-plugin/', consoleUrl).toString();
  const manifest = await fetchJson(new URL('plugin-manifest.json', base).toString());
  const entryScript =
    Array.isArray(manifest.loadScripts) && typeof manifest.loadScripts[0] === 'string'
      ? manifest.loadScripts[0]
      : 'plugin-entry.js';
  const entry = await fetchTextStatus(new URL(entryScript, base).toString());
  assert(
    isJavaScriptResponse(entry) && entry.text.includes('useAssistantOverlay'),
    'local OKD console must serve the AIOps plugin entry through the 9000 proxy',
    {
      contentType: entry.contentType,
      entryScript,
      hint: 'Check that the console plugin webpack dev server is listening on 9001.',
      status: entry.status,
      url: entry.url,
    },
  );

  const directChunkScripts = [
    ...new Set(
      [...entry.text.matchAll(/([A-Za-z0-9_-]+-chunk-[a-f0-9]+\.min\.js)/g)]
        .map((match) => match[1])
        .filter(Boolean),
    ),
  ];
  let criticalChunkScripts = directChunkScripts.filter((script) =>
    [
      'exposed-NullContextProvider',
      'exposed-useAssistantOverlay',
      'exposed-AiopsDashboardPage',
    ].some((prefix) => script.startsWith(prefix)),
  );

  if (criticalChunkScripts.length < 3) {
    const referencedChunkIds = new Set(
      [...entry.text.matchAll(/\.e\((\d+)\)/g)].map((match) => match[1]).filter(Boolean),
    );
    const chunkNames = new Map();
    const chunkHashes = new Map();
    for (const [, id, value] of entry.text.matchAll(/(\d+):"([^"]+)"/g)) {
      if (/^[a-f0-9]{16,}$/i.test(value)) {
        chunkHashes.set(id, value);
      } else if (value.includes('exposed-') || value.includes('vendors-')) {
        chunkNames.set(id, value);
      }
    }
    const chunkByName = (name) =>
      [...chunkNames.entries()].find(([, value]) => value === name)?.[0];
    criticalChunkScripts = [
      chunkByName('exposed-NullContextProvider'),
      chunkByName('exposed-useAssistantOverlay'),
      chunkByName('exposed-AiopsDashboardPage'),
    ]
      .filter((id) => id && referencedChunkIds.has(id) && chunkHashes.has(id))
      .map((id) => `${chunkNames.get(id)}-chunk-${chunkHashes.get(id)}.min.js`);
  }

  if (criticalChunkScripts.length < 3) {
    const distDir = path.join(root, 'komsco-ai-console-plugin', 'dist');
    const distFiles = fs.existsSync(distDir) ? fs.readdirSync(distDir) : [];
    criticalChunkScripts = distFiles.filter((script) =>
      [
        'exposed-NullContextProvider-chunk-',
        'exposed-useAssistantOverlay-chunk-',
        'exposed-AiopsDashboardPage-chunk-',
      ].some((prefix) => script.startsWith(prefix) && script.endsWith('.min.js')) ||
      [
        'exposed-NullContextProvider-chunk.js',
        'exposed-useAssistantOverlay-chunk.js',
        'exposed-AiopsDashboardPage-chunk.js',
      ].includes(script),
    );
  }

  const checks = [];
  for (const script of criticalChunkScripts) {
    const result = await fetchTextStatus(new URL(script, base).toString());
    checks.push({
      script,
      contentType: result.contentType,
      ok: isJavaScriptResponse(result),
      status: result.status,
      url: result.url,
    });
  }

  assert(
    checks.length >= 3 && checks.every((item) => item.ok),
    'local OKD console plugin chunks must be reachable through the 9000 proxy before browser acceptance',
    {
      checks,
      hint:
        'If chunks are 404 or text/html, restart the 9001 plugin webpack dev server after running the production plugin build.',
    },
  );

  return checks;
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

const setViewport = async (width, height) => {
  await send('Emulation.setDeviceMetricsOverride', {
    deviceScaleFactor: 1,
    height,
    mobile: false,
    screenHeight: height,
    screenWidth: width,
    width,
  });
  await send('Emulation.setVisibleSize', { height, width }).catch(() => {});
  await sleep(300);
};

const captureScreenshot = async (filePath, elementExpression = '') => {
  const params = { format: 'png', fromSurface: true };
  if (elementExpression) {
    const clip = await evaluate(`(() => {
      const element = ${elementExpression};
      if (!element) {
        return null;
      }
      element.scrollIntoView({ block: 'center', inline: 'nearest' });
      const rect = element.getBoundingClientRect();
      const pad = 12;
      const x = Math.max(0, rect.left - pad);
      const y = Math.max(0, rect.top - pad);
      const right = Math.min(window.innerWidth, rect.right + pad);
      const bottom = Math.min(window.innerHeight, rect.bottom + pad);
      return {
        height: Math.max(1, bottom - y),
        scale: 1,
        width: Math.max(1, right - x),
        x,
        y
      };
    })()`);
    if (clip && clip.width > 1 && clip.height > 1) {
      params.clip = clip;
    }
  }
  await send('Page.captureScreenshot', params).then((result) => {
    fs.writeFileSync(filePath, Buffer.from(result.data, 'base64'));
  });
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

const IN_USE_NAMESPACE_CLEANUP_QUESTION = [
  'gpu-test-kugnus 네임스페이스가 실제 사용 중인지 확인해줘.',
  '사용 중이면 삭제 Action Plan은 만들지 말고,',
  '실행 가능 모드에서 왜 계획을 만들지 않는지 명확히 설명해줘.',
].join('\n');

const EN_NAMESPACE_CLEANUP_QUESTION_WITH_TEST_WORD = [
  'Review whether these namespaces are actually in use or stale test namespaces.',
  'aiops-demo',
  'cywell-aiops',
  'gpu-test-kugnus',
  'komsco-ai',
  'komsco-ai-dev',
  'komsco-aiops-lab',
  'For each namespace, summarize the decision criteria and read-only oc commands.',
  'If there is a cleanup candidate, create an approval-ready Action Plan candidate.',
].join('\n');

const TEST_POD_CREATE_QUESTION = [
  'gpu-test-kugnus 네임스페이스에 테스트 Pod 3개 생성해.',
  '읽기 전용이면 조회 명령만 알려주고,',
  '실행 가능이면 승인 가능한 Action Plan 후보까지 보여줘.',
].join('\n');

const UNCLEAR_CHAT_QUESTIONS = ['야', '명청한 챗봇', '오늘 날씨 알려줘'];
const AMBIGUOUS_OPERATIONAL_QUESTIONS = ['OpenShift 좀 봐줘', '네임스페이스', '조치해줘'];

const verifyCasualChatContracts = async () => {
  const runQuestion = async (question, mode = 'read-only', language = 'ko') => {
    const response = await fetch(`${localGatewayUrl}/v1/chat/stream`, {
      body: JSON.stringify({
        conversationId: `v0281-casual-${question.replace(/\s+/g, '-')}`,
        language,
        message: question,
        pageContext: {
          aiopsExecutionMode: mode,
          aiopsUiLanguage: language,
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
    const eventJson = JSON.stringify(events);
    return {
      answerPreview: answerText.slice(0, 600),
      eventTypes: events.map((event) => event.type),
      hasActionPlan: /Action Plan 후보|승인 필요 후보|Action Plan candidate/.test(answerText),
      hasDone: raw.includes('[DONE]'),
      hasInternalLeak: /5174|local fixture|local-fixture|local_fixture|local-only|시나리오 처리 범위|unclear_or_out_of_scope|insufficient_operational_context|request_intent_classifier|confidence/.test(
        answerText + eventJson,
      ),
      hasOperationalClarification:
        answerText.includes('요청 확인') ||
        answerText.includes('필요한 정보') ||
        answerText.includes('지금 가능한 요청 예시') ||
        answerText.includes('Request Clarification') ||
        answerText.includes('Needed Information') ||
        answerText.includes('Good Request Examples'),
      hasIdentityGuide:
        answerText.includes('AIOps for OCP') &&
        answerText.includes('전문 AIOps 모델') &&
        answerText.includes('OpenShift') &&
        answerText.includes('Action Plan') &&
        (answerText.includes('승인') || answerText.includes('approval')),
      hasWeakCasualReply:
        answerText.includes('네, 보고 있습니다') ||
        answerText.includes("I'm here") ||
        answerText.includes('확인할 대상과 원하는 작업을 적어주면'),
      mode,
      ok: response.ok,
      question,
      source: events.find((event) => event.type === 'text')?.source || '',
      status: response.status,
      textLength: answerText.length,
      toolEventCount: events.filter((event) => event.type === 'tool_call' || event.type === 'tool_plan').length,
    };
  };

  const terse = await runQuestion(UNCLEAR_CHAT_QUESTIONS[0], 'read-only');
  const insult = await runQuestion(UNCLEAR_CHAT_QUESTIONS[1], 'execute');
  const general = await runQuestion(UNCLEAR_CHAT_QUESTIONS[2], 'execute');
  const questionMark = await runQuestion('뭐야', 'unrestricted');
  const englishHey = await runQuestion('hey', 'read-only', 'en');
  const openshiftConcept = await runQuestion('오픈시프트가 뭐야', 'execute');
  const englishOpenshiftConcept = await runQuestion('what is OpenShift', 'execute', 'en');
  const metrics = {
    englishHey,
    englishOpenshiftConcept,
    general,
    insult,
    openshiftConcept,
    questionMark,
    terse,
  };

  for (const item of [terse, insult, questionMark]) {
    assert(
      item.ok &&
        item.hasDone &&
        item.source === 'copilot_reply' &&
        item.hasIdentityGuide &&
        !item.hasWeakCasualReply &&
        item.textLength > 80 &&
        item.textLength < 320 &&
        item.toolEventCount === 0 &&
        !item.hasActionPlan &&
        !item.hasInternalLeak &&
        !item.hasOperationalClarification,
      'short casual input must return an AIOps for OCP identity guide without operational clarification, tool plan, or internal routing leak',
      metrics,
    );
  }

  assert(
    englishHey.ok &&
      englishHey.hasDone &&
      englishHey.source === 'copilot_reply' &&
      englishHey.answerPreview.includes('AIOps for OCP') &&
      englishHey.answerPreview.includes('AIOps model specialized for OCP') &&
      englishHey.answerPreview.includes('Action Plan') &&
      englishHey.answerPreview.includes('approval') &&
      !/[가-힣]/.test(englishHey.answerPreview) &&
      !englishHey.hasOperationalClarification &&
      !englishHey.hasInternalLeak,
    'English casual input must return the AIOps for OCP identity guide in English without Korean text',
    metrics,
  );

  assert(
    openshiftConcept.ok &&
      openshiftConcept.hasDone &&
      openshiftConcept.source === 'copilot_reply' &&
      openshiftConcept.answerPreview.includes('OpenShift') &&
      openshiftConcept.answerPreview.includes('Kubernetes') &&
      openshiftConcept.answerPreview.includes('AIOps for OCP') &&
      openshiftConcept.toolEventCount === 0 &&
      !openshiftConcept.hasOperationalClarification &&
      !openshiftConcept.hasInternalLeak,
    'Korean OpenShift concept question must return a fast OCP guide answer without live lookup or tool events',
    metrics,
  );

  assert(
    englishOpenshiftConcept.ok &&
      englishOpenshiftConcept.hasDone &&
      englishOpenshiftConcept.source === 'copilot_reply' &&
      englishOpenshiftConcept.answerPreview.includes('OpenShift') &&
      englishOpenshiftConcept.answerPreview.includes('Kubernetes') &&
      englishOpenshiftConcept.answerPreview.includes('AIOps for OCP') &&
      !/[가-힣]/.test(englishOpenshiftConcept.answerPreview) &&
      englishOpenshiftConcept.toolEventCount === 0 &&
      !englishOpenshiftConcept.hasOperationalClarification &&
      !englishOpenshiftConcept.hasInternalLeak,
    'English OpenShift concept question must stay English and avoid operational lookup',
    metrics,
  );

  return metrics;
};

const verifyAmbiguousOperationalContracts = async () => {
  const runQuestion = async (question, mode = 'execute') => {
    const response = await fetch(`${localGatewayUrl}/v1/chat/stream`, {
      body: JSON.stringify({
        conversationId: `v0281-ambiguous-${question.replace(/\s+/g, '-')}`,
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
    const eventJson = JSON.stringify(events);
    return {
      answerPreview: answerText.slice(0, 600),
      eventTypes: events.map((event) => event.type),
      hasActionPlan: /Action Plan 후보|승인 필요 후보|Action Plan candidate/.test(answerText),
      hasDone: raw.includes('[DONE]'),
      hasInternalLeak: /5174|local fixture|local-fixture|local_fixture|local-only|시나리오 처리 범위|unclear_or_out_of_scope|insufficient_operational_context|request_intent_classifier|confidence/.test(
        answerText + eventJson,
      ),
      hasRequiredPrompt:
        answerText.includes('대상과 작업이 아직 부족합니다.') ||
        answerText.includes('target and task are not clear enough'),
      mode,
      ok: response.ok,
      question,
      source: events.find((event) => event.type === 'text')?.source || '',
      status: response.status,
      textLength: answerText.length,
      toolEventCount: events.filter((event) => event.type === 'tool_call' || event.type === 'tool_result' || event.type === 'tool_plan').length,
    };
  };

  const metrics = {};
  for (const [index, question] of AMBIGUOUS_OPERATIONAL_QUESTIONS.entries()) {
    metrics[`case${index + 1}`] = await runQuestion(question, index === 0 ? 'execute' : 'read-only');
  }

  for (const item of Object.values(metrics)) {
    assert(
      item.ok &&
        item.hasDone &&
        item.source === 'copilot_clarification' &&
        item.textLength > 40 &&
        item.textLength < 320 &&
        item.toolEventCount === 0 &&
        item.hasRequiredPrompt &&
        !item.hasActionPlan &&
        !item.hasInternalLeak,
      'ambiguous operational input must ask for target/task without tool events or internal routing leaks in SSE',
      metrics,
    );
  }

  return metrics;
};

const verifyModeAnswerContracts = async () => {
  const question = NAMESPACE_CLEANUP_QUESTION;

  const runMode = async (mode, inputQuestion = question) => {
    const response = await fetch(`${localGatewayUrl}/v1/chat/stream`, {
      body: JSON.stringify({
        conversationId: `v0281-mode-contract-${mode}-${inputQuestion.length}`,
        message: inputQuestion,
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
      hasInternalLeak: /5174|local fixture|local-fixture|local_fixture|local-only|시나리오 처리 범위/.test(answerText),
      hasNaturalActionExecute: eventJson.includes('natural_action_execute'),
      mode,
      mutationsEnabled: toolPlan?.execution_policy?.mutations_enabled,
      ok: response.ok,
      status: response.status,
      textHash: `${answerText.length}:${answerText.slice(0, 80)}`,
      textIncludesActionPlanCandidate: /Action Plan 후보|승인 필요 후보/.test(answerText),
      textIncludesNoSafeDeleteCandidate:
        answerText.includes('안전한 정리 후보') ||
        answerText.includes('no approval-ready delete candidate') ||
        answerText.includes('no safe cleanup candidate'),
      textIncludesReadOnlyCommand:
        answerText.includes('oc get namespaces') &&
        answerText.includes('oc get all,pvc,route,event'),
      textIncludesReadOnlyPlanBlock:
        answerText.includes('읽기 전용 모드에서는 Action Plan') ||
        answerText.includes('읽기 전용 모드라 계획 생성') ||
        answerText.includes('Read-only mode does not create'),
      textIncludesReadOnlyMode: answerText.includes('읽기 전용 모드'),
      textIncludesExecuteMode: answerText.includes('실행 가능 모드'),
      textIncludesUnrestrictedMode: answerText.includes('실행 무제한 모드'),
      toolPlanMode: toolPlan?.execution_policy?.mode || '',
      validationStatus: toolPlan?.validation?.status || '',
    };
  };

  const readOnly = await runMode('read-only');
  const execute = await runMode('execute');
  const executeInUse = await runMode('execute', IN_USE_NAMESPACE_CLEANUP_QUESTION);
  const unrestricted = await runMode('unrestricted');
  const metrics = {
    distinct:
      readOnly.textHash !== execute.textHash &&
      execute.textHash !== unrestricted.textHash &&
      readOnly.toolPlanMode !== execute.toolPlanMode &&
      execute.toolPlanMode !== unrestricted.toolPlanMode,
    execute,
    executeInUse,
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
      !metrics.execute.textIncludesReadOnlyPlanBlock &&
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

  assert(
    metrics.executeInUse.ok &&
      metrics.executeInUse.hasDone &&
      metrics.executeInUse.textIncludesExecuteMode &&
      metrics.executeInUse.textIncludesNoSafeDeleteCandidate &&
      !metrics.executeInUse.textIncludesReadOnlyPlanBlock &&
      !metrics.executeInUse.textIncludesActionPlanCandidate &&
      !metrics.executeInUse.hasCandidateTool &&
      metrics.executeInUse.mutationsEnabled === true &&
      !metrics.executeInUse.hasInternalLeak,
    'execute mode with an in-use namespace must explain no safe delete candidate instead of falling back to read-only wording or Action Plan CTA',
    metrics.executeInUse,
  );

  return metrics;
};

const verifyEnglishNamespaceExtractionContract = async () => {
  const response = await fetch(`${localGatewayUrl}/v1/chat/stream`, {
    body: JSON.stringify({
      conversationId: 'v0281-english-namespace-extraction',
      message: EN_NAMESPACE_CLEANUP_QUESTION_WITH_TEST_WORD,
      pageContext: {
        aiopsExecutionMode: 'execute',
        aiopsUiLanguage: 'en',
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
  const inventoryResult = events.find(
    (event) => event.type === 'tool_result' && event.name === 'oc_namespace_inventory',
  )?.result;
  const requestedNames = Array.isArray(inventoryResult?.requestedNames)
    ? inventoryResult.requestedNames
    : [];
  const metrics = {
    answerPreview: answerText.slice(0, 900),
    hasKorean: /[가-힣]/.test(answerText),
    hasStandaloneTestNamespace: requestedNames.includes('test'),
    ok: response.ok,
    requestedNames,
    status: response.status,
  };

  assert(
    metrics.ok &&
      !metrics.hasKorean &&
      !metrics.hasStandaloneTestNamespace &&
      JSON.stringify(metrics.requestedNames) ===
        JSON.stringify([
          'aiops-demo',
          'cywell-aiops',
          'gpu-test-kugnus',
          'komsco-ai',
          'komsco-ai-dev',
          'komsco-aiops-lab',
        ]),
    'English namespace cleanup prompt must not treat prose word "test" as a namespace',
    metrics,
  );

  return metrics;
};

const verifyTestPodCreateContracts = async () => {
  const runMode = async (mode) => {
    const response = await fetch(`${localGatewayUrl}/v1/chat/stream`, {
      body: JSON.stringify({
        conversationId: `v0281-test-pod-contract-${mode}`,
        message: TEST_POD_CREATE_QUESTION,
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
      hasCandidateTool: toolPlanJson.includes('create_test_pod_action_candidate'),
      hasDone: raw.includes('[DONE]'),
      hasInternalLeak: /5174|local fixture|local-fixture|local_fixture|local-only|시나리오 처리 범위/.test(answerText),
      hasMutationExecute: eventJson.includes('mutation_succeeded'),
      mode,
      mutationsEnabled: toolPlan?.execution_policy?.mutations_enabled,
      ok: response.ok,
      status: response.status,
      textHash: `${answerText.length}:${answerText.slice(0, 80)}`,
      textIncludesActionPlanCandidate: /Action Plan 후보|승인 필요 후보/.test(answerText),
      textIncludesReadOnlyCommand:
        answerText.includes('oc whoami --show-server') &&
        answerText.includes('oc get namespace gpu-test-kugnus') &&
        answerText.includes('oc get pods -n gpu-test-kugnus'),
      textIncludesReadOnlyMode: answerText.includes('읽기 전용 모드'),
      textIncludesExecuteMode: answerText.includes('실행 가능 모드'),
      textIncludesUnrestrictedMode: answerText.includes('실행 무제한 모드'),
      textIncludesVerificationGate:
        answerText.includes('실행 전 namespace 재확인 필요') ||
        answerText.includes('namespace 존재 확인'),
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
      metrics.execute.textIncludesVerificationGate &&
      metrics.unrestricted.textIncludesUnrestrictedMode &&
      metrics.unrestricted.toolPlanMode === 'unrestricted_pending_approval' &&
      metrics.unrestricted.mutationsEnabled === true &&
      metrics.unrestricted.hasCandidateTool &&
      metrics.unrestricted.textIncludesActionPlanCandidate &&
      !metrics.execute.hasMutationExecute &&
      !metrics.unrestricted.hasMutationExecute &&
      metrics.distinct &&
      !metrics.readOnly.hasInternalLeak &&
      !metrics.execute.hasInternalLeak &&
      !metrics.unrestricted.hasInternalLeak,
    'test Pod creation request must produce distinct safe answers and approval-gated Action Plan capability by execution mode',
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
      '확인 결과',
      '- Alert: KubePodNotReady / severity=warning',
      '- Metric: restart increase observed',
      '',
      '원인 후보',
      '- readiness probe 실패 또는 image pull 상태 확인이 필요합니다.',
      '',
      'Action Plan',
      '- 대상: komsco-ai-dev/aiops-scenario-1-crashloop',
      '- 실행 전 검증: Events, logs, rollout 상태 확인',
      '- 승인 조건: 확인 결과가 정리되고 영향/롤백 경로가 확인된 경우',
      '',
      '검증/롤백',
      '- 실행 후 Ready 상태와 restart 증가 중단 여부를 확인합니다.',
      '- 실패하면 이전 ReplicaSet 또는 수동 확인 절차로 전환합니다.',
      '',
      '확인 결과 상세',
      '- 참고 문서와 운영 조회 결과는 상세 안에서만 확인합니다.'
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
    const longHistory = Array.from({ length: 22 }, (_, index) => {
      const updatedAt = Date.now() - 40000 - index * 9000;
      return {
        id: 'v0281-fixture-session-long-' + index,
        title: [
          '최근 문제있었던 네임스페이스가있어?',
          '이건 어떻게 조치할 수있어?',
          '원인파악해줘',
          'CrashLoopBackOff 상태인 Pod를 확인해줘',
          '최근 OpenShift 경고 우선 확인할 항목'
        ][index % 5],
        updatedAt,
        conversationId: 'v0281-fixture-conversation-long-' + index,
        messages: olderMessages.map((message) => ({ ...message, timestamp: updatedAt })),
        actionRefs: index % 3 === 0 ? olderRefs : [],
        actionTargetKeys: index % 3 === 0 ? olderRefs.map((ref) => ref.targetKey) : []
      };
    });
    const history = [
      {
        id: 'v0281-fixture-session',
        title: 'v0.2.8.1 Action Plan UX 검증 대화',
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
      },
      ...longHistory
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
    await evaluate(`(() => {
      const close = Array.from(document.querySelectorAll('.komsco-ai__header-actions button'))
        .find((el) => ['AIOps for OCP 닫기', 'Close AIOps for OCP'].includes(el.getAttribute('aria-label') || ''));
      close?.click();
      return true;
    })()`);
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
      ['질문 전송', 'Send question'].includes(value?.label) &&
      value?.disabled === false,
    'composer send button enabled for live mode test',
    10000,
  );
};

const sendLiveQuestion = async ({ label, language = 'ko', mode, question }) => {
  await closeAndReopenEmptyAssistant();
  await setUiLanguageInUi(language);
  await setExecutionModeInUi(mode);
  let sendObserved = null;
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    await setComposerValue(question);
    const clicked = await evaluate(`(() => {
      const button = document.querySelector('.komsco-ai__send');
      const textarea = document.querySelector('.komsco-ai__composer textarea');
      const disabled = Boolean(button?.disabled);
      const label = button?.getAttribute('aria-label') || '';
      if (!button || disabled) {
        return { ok: false, attempt: ${attempt}, disabled, label, textareaValue: textarea?.value || '' };
      }
      button.click();
      return { ok: true, attempt: ${attempt}, disabled, label, textareaValue: textarea?.value || '' };
    })()`);
    assert(clicked?.ok, 'send button must accept the live test question click', clicked);
    try {
      sendObserved = await poll(
        `(() => ({
          assistantMessages: document.querySelectorAll('.komsco-ai__message--assistant').length,
          loading: Boolean(document.querySelector('.komsco-ai__surface--responding')),
          userMessages: document.querySelectorAll('.komsco-ai__message--user').length
        }))()`,
        (value) => value?.userMessages >= 1 || value?.loading,
        `live UI question submit observed for ${label || mode} attempt ${attempt}`,
        6000,
      );
      break;
    } catch (error) {
      if (attempt === 2) {
        throw error;
      }
      await sleep(250);
    }
  }
  assert(sendObserved, 'live UI question submit must be observed before waiting for the answer');

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
      const sectionHeaders = Array.from(
        latest?.querySelectorAll('.komsco-ai__runbook-section-title') || []
      ).map((el) => el.textContent.replace(/\\s+/g, ' ').trim()).filter(Boolean);
      const decisionTableCount =
        latest?.querySelectorAll('.komsco-ai__runbook-section.is-decisions .komsco-ai__table')
          .length || 0;
      const decisionTableText = Array.from(
        latest?.querySelectorAll('.komsco-ai__runbook-section.is-decisions .komsco-ai__table') ||
          []
      )
        .map((el) => el.textContent.replace(/\\s+/g, ' ').trim())
        .join(' ');
      const decisionSectionVisible = sectionHeaders.some((header) =>
        header === 'Namespace Decisions' || header === 'Name pace Deci ion'
      );
      const decisionTableHasExpectedColumns =
        (/Namespace|Name pace/.test(decisionTableText)) &&
        (/Decision|Deci ion/.test(decisionTableText)) &&
        decisionTableText.includes('Next Step');
      const codeActionLabels = Array.from(
        latest?.querySelectorAll('.komsco-ai__code-actions button') || []
      )
        .map((el) =>
          ((el.getAttribute('aria-label') || '') + ' ' + (el.getAttribute('title') || '')).trim()
        )
        .filter(Boolean);
      const detailChromeLabels = Array.from(
        latest?.querySelectorAll(
          '.komsco-ai__evidence-footer summary, .komsco-ai__toolplan-footer summary, .komsco-ai__evidence-title, .komsco-ai__evidence-query-plan, .komsco-ai__evidence-list, .komsco-ai__evidence-missing, .komsco-ai__toolplan-violations, .komsco-ai__toolplan-json button'
        ) || []
      )
        .map((el) =>
          [
            el.textContent || '',
            el.getAttribute('aria-label') || '',
            el.getAttribute('title') || '',
          ]
            .join(' ')
            .replace(/\\s+/g, ' ')
            .trim()
        )
        .filter(Boolean);
      const railChromeLabels = Array.from(
        document.querySelectorAll(
          [
            '.komsco-ai__rail-title',
            '.komsco-ai__connection-main',
            '.komsco-ai__connection-metrics',
            '.komsco-ai__health-head',
            '.komsco-ai__rail-status-pair',
            '.komsco-ai__rail-section-head',
            '.komsco-ai__rail-feedback-copy',
            '.komsco-ai__rail-empty',
            '.komsco-ai__scope-list--secondary',
            '.komsco-ai__scope-list--execution',
            '.komsco-ai__action-lifecycle-steps',
            '.komsco-ai__action-lifecycle-summary',
            '.komsco-ai__rail-command-head',
            '.komsco-ai__rail-action-proof',
            '.komsco-ai__plan-summary',
            '.komsco-ai__rail-action-row',
            '.komsco-ai__rail-command-detail > summary'
          ].join(', ')
        ) || []
      )
        .map((el) => {
          const style = window.getComputedStyle(el);
          const visible = style.display !== 'none' && style.visibility !== 'hidden';
          if (!visible) return '';
          return [
            el.textContent || '',
            el.getAttribute('aria-label') || '',
            el.getAttribute('title') || '',
          ]
            .join(' ')
            .replace(/\\s+/g, ' ')
            .trim();
        })
        .filter(Boolean);
      const railChromeText = railChromeLabels.join(' ');
      const expectedEnglishRailLabels = [
        'Current cluster context',
        'Cluster health',
        'Conversation summary',
        'Question-answer timeline',
        'Saved reports',
        'Node status',
        'Cluster status',
        'Operator issues',
        'AIOps execution status',
        'Answer context',
        'Answer feedback',
        'Copy feedback JSON',
        'Recent diagnostics',
        'Approval and execution',
        'Read only',
        'Execute',
        'Unrestricted',
        'Candidate',
        'Plan',
        'Approval',
        'Execution',
        'Audit detail'
      ];
      const missingEnglishRailLabels = expectedEnglishRailLabels.filter(
        (expected) => !railChromeText.includes(expected)
      );
      const rawRailTerms = [
        'proposal-local',
        'plan-local',
        'approval-local',
        'execution-local',
        'mutation_succeeded',
        'review_recorded',
        'mutation_failed',
        'delete_namespace_after_approval',
        'Details (JSON)',
        '상세보기 (JSON)'
      ].filter((term) => railChromeText.includes(term));
      const actionPlanButtons = Array.from(
        latest?.querySelectorAll('.komsco-ai__create-action-plan-button') || []
      ).map((el) => el.textContent.trim());
      const actionCandidateGroups = Array.from(
        latest?.querySelectorAll('.komsco-ai__create-action-plan') || []
      ).map((group) => {
        const rows = Array.from(group.querySelectorAll('.komsco-ai__create-action-plan-row'));
        const visibleRows = rows.filter((row) => {
          const style = getComputedStyle(row);
          const rect = row.getBoundingClientRect();
          return style.display !== 'none' && style.visibility !== 'hidden' && rect.width > 0 && rect.height > 0;
        });
        const count = Number(group.getAttribute('data-aiops-action-candidate-count') || rows.length || 0);
        const expanded = group.getAttribute('data-aiops-action-candidates-expanded') === 'true';
        const summary = group.querySelector('.komsco-ai__create-action-plan-summary');
        return {
          count,
          expanded,
          hasSummary: Boolean(summary),
          rowCount: rows.length,
          visibleRowCount: visibleRows.length,
          summaryText: summary?.textContent?.replace(/\\s+/g, ' ').trim() || ''
        };
      });
      const answerActionButtons = Array.from(
        latest?.querySelectorAll('.komsco-ai__answer-action-controls .komsco-ai__action-button') || []
      ).map((el) => el.textContent.trim());
      const answerLifecycleStages = Array.from(
        latest?.querySelectorAll('[data-action-lifecycle-stage]') || []
      ).map((el) => el.getAttribute('data-action-lifecycle-stage') || '');
      const loading =
        Boolean(document.querySelector('.komsco-ai__surface--responding')) ||
        ['응답 중지', 'Stop response'].includes(
          document.querySelector('.komsco-ai__send')?.getAttribute('aria-label') || ''
        );
      const rawTerms = [
        '5174',
        'local fixture',
        'local-fixture',
        'local_fixture',
        'local-only',
        '시나리오 처리 범위',
        'unclear_or_out_of_scope',
        'insufficient_operational_context',
        'request_intent_classifier',
        'confidence',
      ]
        .filter((term) => text.includes(term));
      const rawProgressTerms = [
        'Oc Namespace Inventory',
        'Oc Test Pod Create Preflight',
        'oc read-only namespace inventory',
        'oc_test_pod_create_preflight',
        'namespace and server preflight',
        'request_intent_classifier',
        'Request Intent Classifier',
        'unclear_or_out_of_scope',
        'insufficient_operational_context',
        'confidence',
        'AI 응답 대기',
        '화면 표시 준비',
        '화면 표시 중',
        '도구 호출',
        '도구 응답을 기다리는 중입니다',
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
        actionCandidateDefaultCollapsed: actionCandidateGroups.every((group) =>
          group.count <= 1 || (!group.expanded && group.hasSummary && group.visibleRowCount === 0)
        ),
        actionCandidateGroups,
        answerActionButtons,
        answerLifecycleStages,
        assistantMessages: assistantMessages.length,
        hasGatewayFallback: source.includes('fallback'),
        hasGatewayDirect: source.includes('Gateway 실조회') || source.includes('Gateway live query'),
        hasInternalLeak: rawTerms.length > 0,
        hasScenarioLeak: scenarioTerms.length > 0,
        loading,
        mode: ${JSON.stringify(mode)},
        preview: text.slice(0, 900),
        answerHasKorean: /[가-힣]/.test(text),
        progressText,
        progressTexts,
        rawProgressTerms,
        rawRailTerms,
        rawTerms,
        scenarioTerms,
        decisionTableCount,
        decisionSectionVisible,
        decisionTableHasExpectedColumns,
        decisionTableText,
        codeActionLabels,
        codeActionLabelsHaveKorean: codeActionLabels.some((label) => /[가-힣]/.test(label)),
        detailChromeLabels,
        detailChromeLabelsHaveKorean: detailChromeLabels.some((label) => /[가-힣]/.test(label)),
        railChromeLabels,
        railChromeHasKorean: railChromeLabels.some((label) => /[가-힣]/.test(label)),
        railChromeMissingEnglishLabels: missingEnglishRailLabels,
        railChromeUsesEnglish:
          railChromeLabels.length > 0 &&
          !railChromeLabels.some((label) => /[가-힣]/.test(label)) &&
          missingEnglishRailLabels.length === 0,
        sectionHeaders,
        source,
        sourceHasKorean:
          /[가-힣]/.test(source + ' ' + sourceTitle),
        sourceTitle,
        sourceUsesEnglishLabel:
          ['OCP guide', 'Gateway live query', 'Request clarification', 'Lightspeed connected', 'Gateway fallback'].includes(source) &&
          !/[가-힣]/.test(source + ' ' + sourceTitle),
        textIncludesCasualReply:
          text.includes('AIOps for OCP') &&
          (text.includes('전문 AIOps 모델') || text.includes('AIOps model specialized for OCP')) &&
          text.includes('OpenShift') &&
          text.includes('Action Plan') &&
          (text.includes('승인') || text.includes('approval')) &&
          !text.includes('네, 보고 있습니다') &&
          !text.includes("I'm here"),
        textHash: text.length + ':' + text.slice(0, 80),
        textIncludesClarification:
          text.includes('대상과 작업이 아직 부족합니다.') &&
          text.includes('Action Plan이나 클러스터 변경은 만들지 않았습니다.'),
        progressUsesOperatorLabels:
          progressText.length > 0 &&
          !rawProgressTerms.length &&
          (
            progressText.includes('요청 해석 확인') ||
            progressText.includes('네임스페이스 사용 여부 확인') ||
            progressText.includes('테스트 Pod 생성 사전 확인') ||
            progressText.includes('조회 계획') ||
            progressText.includes('모델 답변 생성') ||
            progressText.includes('답변 작성')
          ),
        progressUsesEnglishOperatorLabels:
          progressText.length > 0 &&
          !rawProgressTerms.length &&
          !/[가-힣]/.test(progressText) &&
          (
            progressText.includes('Request interpretation') ||
            progressText.includes('Namespace usage check') ||
            progressText.includes('Test Pod creation preflight') ||
            progressText.includes('Evidence plan') ||
            progressText.includes('Generating model answer') ||
            progressText.includes('Writing answer')
          ),
        progressHasKorean:
          /[가-힣]/.test(progressText),
        textIncludesActionPlanCandidate: /Action Plan 후보|승인 필요 후보/.test(text),
        textIncludesEnglishActionPlanCandidate:
          /approval-ready Action Plan candidate|Approval-required candidates|Action Plan candidate can be created/.test(text),
        textIncludesEnglishClarification:
          text.includes('Request Clarification') &&
          text.includes('Needed Information') &&
          text.includes('Good Request Examples') &&
          text.includes('processing status: more information required') &&
          text.includes('execution status: no change created'),
        textIncludesEnglishExecuteMode: text.includes('Execution-enabled mode'),
        textIncludesEnglishReadOnlyMode: text.includes('Read-only mode'),
        textIncludesEnglishUnrestrictedMode: text.includes('Unrestricted mode'),
        textIncludesExecuteMode: text.includes('실행 가능 모드'),
        textIncludesReadOnlyCommand:
          text.includes('oc get namespaces') &&
          text.includes('oc get all,pvc,route,event'),
        textIncludesReadOnlyMode: text.includes('읽기 전용 모드'),
        textIncludesTestPodCommand:
          text.includes('oc get namespace gpu-test-kugnus') &&
          text.includes('oc get pods -n gpu-test-kugnus'),
        textIncludesTestPodTarget:
          text.includes('테스트 Pod') &&
          text.includes('gpu-test-kugnus') &&
          text.includes('aiops-test-pods'),
        textIncludesVerificationGate:
          text.includes('실행 전 namespace 재확인 필요') ||
          text.includes('namespace 존재 확인'),
        textIncludesUnrestrictedMode: text.includes('실행 무제한 모드'),
        userMessages: userMessages.length
      };
    })()`,
    (value) =>
      value?.assistantMessages === 1 &&
      value?.userMessages === 1 &&
      !value?.loading &&
      value?.preview?.length > 20,
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

const hasActionPlanCreateButton = (answer) =>
  answer.actionPlanButtons.includes('Action Plan 생성') ||
  answer.actionPlanButtons.includes('Create Action Plan');

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
      !hasActionPlanCreateButton(readOnly) &&
      readOnly.actionCandidateDefaultCollapsed &&
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
      execute.actionCandidateDefaultCollapsed &&
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
      unrestricted.actionCandidateDefaultCollapsed &&
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

const sendLiveTestPodCreateQuestion = async (mode) =>
  sendLiveQuestion({
    label: `test Pod create ${mode}`,
    mode,
    question: TEST_POD_CREATE_QUESTION,
  });

const verifyLiveTestPodCreateAnswers = async () => {
  const readOnly = await sendLiveTestPodCreateQuestion('read-only');
  const execute = await sendLiveTestPodCreateQuestion('execute');
  const unrestricted = await sendLiveTestPodCreateQuestion('unrestricted');
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
      readOnly.textIncludesTestPodCommand &&
      readOnly.textIncludesTestPodTarget &&
      !hasActionPlanCreateButton(readOnly) &&
      !readOnly.textIncludesActionPlanCandidate &&
      readOnly.hasGatewayDirect &&
      !readOnly.hasGatewayFallback &&
      !readOnly.hasInternalLeak &&
      readOnly.progressUsesOperatorLabels,
    'read-only test Pod creation answer must provide safe commands without an Action Plan CTA',
    metrics,
  );
  assert(
    execute.textIncludesExecuteMode &&
      execute.textIncludesTestPodTarget &&
      execute.textIncludesActionPlanCandidate &&
      execute.textIncludesVerificationGate &&
      execute.actionPlanButtons.includes('Action Plan 생성') &&
      execute.hasGatewayDirect &&
      !execute.hasGatewayFallback &&
      !execute.hasInternalLeak &&
      execute.progressUsesOperatorLabels,
    'execute test Pod creation answer must render an approval-gated Action Plan CTA',
    metrics,
  );
  assert(
    unrestricted.textIncludesUnrestrictedMode &&
      unrestricted.textIncludesTestPodTarget &&
      unrestricted.textIncludesActionPlanCandidate &&
      unrestricted.actionPlanButtons.includes('Action Plan 생성') &&
      unrestricted.hasGatewayDirect &&
      !unrestricted.hasGatewayFallback &&
      !unrestricted.hasInternalLeak &&
      unrestricted.progressUsesOperatorLabels,
    'unrestricted test Pod creation answer must still require the approval-gated Action Plan CTA',
    metrics,
  );
  assert(
    metrics.distinct,
    'same test Pod creation question must render distinct live UI answers by execution mode',
    metrics,
  );

  return metrics;
};

const verifyLiveCasualAnswers = async () => {
  const terse = await sendLiveQuestion({
    label: 'terse casual Korean input',
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
      item.textIncludesCasualReply &&
        item.source === 'OCP 안내' &&
        !item.hasGatewayDirect &&
        !item.hasGatewayFallback &&
        !item.hasInternalLeak &&
        !item.hasScenarioLeak &&
        item.rawProgressTerms.length === 0 &&
        item.rawRailTerms.length === 0 &&
        !/요청 해석|네임스페이스 사용 여부|테스트 Pod 생성|증거 수집|조회 계획|Action Plan|Request interpretation|Namespace usage|Test Pod creation|Evidence plan/.test(
          item.progressText,
        ) &&
        item.actionPlanButtons.length === 0 &&
        item.answerActionButtons.length === 0 &&
        !item.textIncludesActionPlanCandidate &&
        !item.textIncludesClarification,
      'short casual live UI input must return an AIOps for OCP identity guide without operational clarification, internal routing, or Action Plan CTA',
      metrics,
    );
  }

  const casualLayoutMetrics = await evaluate(`(() => {
    const userMessages = Array.from(document.querySelectorAll('.komsco-ai__message--user'));
    const latestUser = userMessages[userMessages.length - 1];
    const userContent = latestUser?.querySelector('.komsco-ai__message-content');
    const userText = userContent?.textContent?.trim() || '';
    const userRect = userContent?.getBoundingClientRect();
    const userStyle = userContent ? getComputedStyle(userContent) : null;
    const lineHeight = userStyle ? parseFloat(userStyle.lineHeight) : 0;
    const contentHeight = userRect ? Math.round(userRect.height) : 0;
    const textarea = document.querySelector('.komsco-ai__composer textarea');
    const input = document.querySelector('.komsco-ai__input');
    const send = document.querySelector('.komsco-ai__send');
    const composerWrap = document.querySelector('.komsco-ai__composer-wrap');
    const textareaStyle = textarea ? getComputedStyle(textarea) : null;
    const inputStyle = input ? getComputedStyle(input) : null;
    const sendStyle = send ? getComputedStyle(send) : null;
    const wrapStyle = composerWrap ? getComputedStyle(composerWrap) : null;
    const darkBackground = (value) =>
      /rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/.test(value)
        ? value.match(/\\d+/g).slice(0, 3).map(Number).every((part) => part < 48)
        : false;
    return {
      contentHeight,
      inputBackground: inputStyle?.backgroundColor || '',
      lineHeight,
      ok:
        userText === ${JSON.stringify(UNCLEAR_CHAT_QUESTIONS[1])} &&
        Boolean(userRect) &&
        userRect.width >= 42 &&
        userRect.width <= 170 &&
        contentHeight <= Math.ceil(lineHeight * 2.25) &&
        Boolean(textareaStyle) &&
        parseFloat(textareaStyle.minHeight) <= 34 &&
        parseFloat(textareaStyle.maxHeight) <= 80 &&
        !darkBackground(inputStyle?.backgroundColor || '') &&
        !darkBackground(wrapStyle?.backgroundColor || '') &&
        !darkBackground(sendStyle?.backgroundColor || ''),
      sendBackground: sendStyle?.backgroundColor || '',
      textareaMaxHeight: textareaStyle?.maxHeight || '',
      textareaMinHeight: textareaStyle?.minHeight || '',
      userText,
      userWidth: userRect ? Math.round(userRect.width) : 0,
      wrapBackground: wrapStyle?.backgroundColor || ''
    };
  })()`);
  assert(
    casualLayoutMetrics.ok,
    'short casual user bubble and composer must stay compact without dark oversized input chrome',
    casualLayoutMetrics,
  );

  return metrics;
};

const verifyLiveActionPlanClickThrough = async () => {
  const statusSnapshot = async () =>
    evaluate(`(async () => {
      const response = await fetch('/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status');
      if (!response.ok) return { ok: false, status: response.status };
      const payload = await response.json();
      const records = payload?.spec?.records || {};
      return {
        approvals: (records.approvalDecisions || []).map((record) => ({
          name: record?.metadata?.name || '',
          planDigest: record?.spec?.approvalDecision?.planDigest || '',
          status: record?.spec?.approvalDecision?.status || ''
        })),
        approvalCount: (records.approvalDecisions || []).length,
        executionCount: (records.executionRecords || []).length,
        executions: (records.executionRecords || []).map((record) => ({
          name: record?.metadata?.name || '',
          planDigest: record?.spec?.planDigest || record?.spec?.executionRecord?.planDigest || '',
          mutationReason: record?.spec?.mutationOutcome?.reason || '',
          mutationStatus: record?.spec?.mutationOutcome?.status || '',
          remediationReason: record?.spec?.remediationOutcome?.reason || '',
          targetName: record?.spec?.executorTrace?.target?.name || ''
        })),
        ok: true,
        planCount: (records.sealedActionPlans || []).length,
        plans: (records.sealedActionPlans || []).map((record) => ({
          digest: record?.spec?.sealedActionPlan?.digest?.planDigest || record?.spec?.planDigest || '',
          name: record?.metadata?.name || '',
          targetName: record?.spec?.sealedActionPlan?.target?.name || record?.spec?.target?.name || ''
        }))
      };
    })()`);

  const latestLifecycleRecordJson = async (stage) =>
    evaluate(`(() => {
      const stage = ${JSON.stringify(stage || '')};
      const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
      const scoped = latest?.querySelector(stage
        ? '[data-action-lifecycle-stage="' + stage + '"] .komsco-ai__rail-command-detail pre'
        : '.komsco-ai__rail-command-detail pre');
      const candidates = scoped ? [scoped] : Array.from(latest?.querySelectorAll('.komsco-ai__rail-command-detail pre') || []);
      for (const node of candidates) {
        try {
          const parsed = JSON.parse(node.textContent || '{}');
          const sealed = parsed?.spec?.sealedActionPlan || {};
          const digest = sealed?.digest?.planDigest || parsed?.spec?.planDigest || '';
          if (digest) {
            return {
              kind: parsed?.kind || '',
              name: parsed?.metadata?.name || '',
              planDigest: digest,
              planId: sealed?.metadata?.planId || parsed?.metadata?.name || '',
              targetName: sealed?.target?.name || parsed?.spec?.target?.name || ''
            };
          }
        } catch (_error) {}
      }
      return null;
    })()`);

  const before = await statusSnapshot();
  assert(before?.ok, 'Action Plan click-through must read AIOps status before starting', before);

  const answer = await sendLiveQuestion({
    label: 'namespace cleanup Action Plan click-through',
    mode: 'execute',
    question: NAMESPACE_CLEANUP_QUESTION,
  });
  assert(
    answer.actionPlanButtons.includes('Action Plan 생성') &&
      answer.textIncludesActionPlanCandidate &&
      answer.hasGatewayDirect,
    'execute mode namespace cleanup answer must expose an actionable Action Plan CTA before click-through',
    answer,
  );

  const expandedCandidateGroup = await evaluate(`(() => {
    const assistantMessages = Array.from(document.querySelectorAll('.komsco-ai__message--assistant'));
    const latest = assistantMessages[assistantMessages.length - 1];
    const group = latest?.querySelector('.komsco-ai__create-action-plan[data-aiops-action-candidates-expanded="false"]');
    const summary = group?.querySelector('.komsco-ai__create-action-plan-summary');
    if (!group || !summary) return { clicked: false, expanded: true, ok: true };
    summary.click();
    return {
      clicked: true,
      expanded: group.getAttribute('data-aiops-action-candidates-expanded') === 'true',
      ok: true,
      text: summary.textContent.replace(/\\s+/g, ' ').trim()
    };
  })()`);
  if (expandedCandidateGroup?.clicked) {
    await poll(
      `(() => {
        const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
        const group = latest?.querySelector('.komsco-ai__create-action-plan');
        return {
          expanded: group?.getAttribute('data-aiops-action-candidates-expanded') === 'true',
          visibleButtons: Array.from(latest?.querySelectorAll('.komsco-ai__create-action-plan-button') || [])
            .filter((button) => {
              const rect = button.getBoundingClientRect();
              const style = getComputedStyle(button);
              return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden';
            }).length
        };
      })()`,
      (value) => value?.expanded && value?.visibleButtons >= 1,
      'collapsed Action Plan candidates expand before click-through',
      10000,
    );
  }

  const createClick = await evaluate(`(() => {
    const assistantMessages = Array.from(document.querySelectorAll('.komsco-ai__message--assistant'));
    const latest = assistantMessages[assistantMessages.length - 1];
    const button = latest?.querySelector('.komsco-ai__create-action-plan-button');
    const label = button?.textContent?.trim() || '';
    const disabled = Boolean(button?.disabled);
    if (!button || disabled) return { disabled, label, ok: false };
    button.click();
    return { disabled, label, ok: true };
  })()`);
  assert(createClick?.ok, 'Action Plan 생성 CTA must be clickable on the latest answer', createClick);

  const planReady = await poll(
    `(() => {
      const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
      const text = latest?.textContent || '';
      const approveButton = latest?.querySelector('[data-answer-action-step="approve-plan"]');
      const createButtons = latest?.querySelectorAll('.komsco-ai__create-action-plan-button') || [];
      return {
        hasApproveButton: Boolean(approveButton),
        createButtonCount: createButtons.length,
        text: text.slice(0, 1200)
      };
    })()`,
    (value) => value?.hasApproveButton && value?.createButtonCount === 0,
    'Action Plan CTA click creates an approval-ready plan in the answer',
    30000,
  );
  const createdPlan = await latestLifecycleRecordJson('plan');
  assert(
    createdPlan?.planId && createdPlan?.planDigest,
    'Action Plan CTA click must render a sealed plan audit record with planId and planDigest',
    { planReady, createdPlan },
  );

  const planStatus = await statusSnapshot();
  assert(
    planStatus?.plans?.some(
      (plan) => plan.name === createdPlan.planId && plan.digest === createdPlan.planDigest,
    ) &&
      planStatus.planCount >= before.planCount,
    'Action Plan CTA click must create a sealed plan record for the rendered plan digest',
    { before, createdPlan, planReady, planStatus },
  );

  const approveClick = await evaluate(`(() => {
    const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
    const button = latest?.querySelector('[data-answer-action-step="approve-plan"]');
    const label = button?.textContent?.trim() || '';
    const disabled = Boolean(button?.disabled);
    if (!button || disabled) return { disabled, label, ok: false };
    button.click();
    return { disabled, label, ok: true };
  })()`);
  assert(approveClick?.ok, 'approval button must be clickable after creating the plan', approveClick);

  const approvalReady = await poll(
    `(() => {
      const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
      const text = latest?.textContent || '';
      const executeButton = latest?.querySelector('[data-answer-action-step="execute-approval"]');
      const createButtons = latest?.querySelectorAll('.komsco-ai__create-action-plan-button') || [];
      return {
        hasExecuteButton: Boolean(executeButton),
        createButtonCount: createButtons.length,
        text: text.slice(0, 1200)
      };
    })()`,
    (value) => value?.hasExecuteButton && value?.createButtonCount === 0,
    'approval click creates an executable approval record in the answer',
    30000,
  );

  const approvalStatus = await statusSnapshot();
  assert(
    approvalStatus?.approvals?.some(
      (approval) =>
        approval.planDigest === createdPlan.planDigest &&
        ['approved', 'executed'].includes(approval.status),
    ),
    'approval click must add an approval decision record for the rendered plan digest',
    { approvalReady, approvalStatus, before, createdPlan },
  );

  const executeClick = await evaluate(`(() => {
    const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
    const button = latest?.querySelector('[data-answer-action-step="execute-approval"]');
    const label = button?.textContent?.trim() || '';
    const disabled = Boolean(button?.disabled);
    if (!button || disabled) return { disabled, label, ok: false };
    button.click();
    return { disabled, label, ok: true };
  })()`);
  assert(executeClick?.ok, 'execute button must be clickable after approval', executeClick);

  const executionReady = await poll(
    `(async () => {
      const response = await fetch('/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status');
      if (!response.ok) return { ok: false, status: response.status };
      const payload = await response.json();
      const records = payload?.spec?.records || {};
      const executions = records.executionRecords || [];
      const matched = executions.find((record) =>
        (record?.spec?.planDigest === ${JSON.stringify(createdPlan.planDigest)}) &&
        String(record?.spec?.mutationOutcome?.reason || '').includes('namespace cleanup')
      );
      const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
      const text = latest?.textContent || '';
      const createButtons = latest?.querySelectorAll('.komsco-ai__create-action-plan-button') || [];
      const executionCard = latest?.querySelector('[data-action-lifecycle-stage="execution"]');
      return {
        executionCount: executions.length,
        matched: matched ? {
          name: matched?.metadata?.name || '',
          mutationReason: matched?.spec?.mutationOutcome?.reason || '',
          mutationStatus: matched?.spec?.mutationOutcome?.status || '',
          remediationReason: matched?.spec?.remediationOutcome?.reason || ''
        } : null,
        createButtonCount: createButtons.length,
        hasExecutionCard: Boolean(executionCard),
        ok: Boolean(matched)
      };
    })()`,
    (value) => value?.ok && value?.executionCount > before.executionCount && value?.hasExecutionCard && value?.createButtonCount === 0,
    'execution click creates a namespace cleanup execution record',
    30000,
  );

  const repeatAnswer = await sendLiveQuestion({
    label: 'namespace cleanup repeated after execution',
    mode: 'execute',
    question: NAMESPACE_CLEANUP_QUESTION,
  });
  const repeatNeedsCreate = repeatAnswer.actionPlanButtons.includes('Action Plan 생성');
  const repeatAlreadyResolved =
    repeatAnswer.answerLifecycleStages.includes('execution') &&
    repeatAnswer.actionPlanButtons.length === 0;
  assert(
    (repeatNeedsCreate && repeatAnswer.textIncludesActionPlanCandidate) || repeatAlreadyResolved,
    'repeated namespace cleanup answer must either expose a fresh Action Plan CTA or resolve to the existing executed lifecycle state',
    repeatAnswer,
  );

  let repeatCreateClick = { skipped: true, reason: 'already-resolved' };
  let repeatedResolved = repeatAnswer;
  if (repeatNeedsCreate) {
    repeatCreateClick = await evaluate(`(() => {
      const assistantMessages = Array.from(document.querySelectorAll('.komsco-ai__message--assistant'));
      const latest = assistantMessages[assistantMessages.length - 1];
      const button = latest?.querySelector('.komsco-ai__create-action-plan-button');
      const label = button?.textContent?.trim() || '';
      const disabled = Boolean(button?.disabled);
      if (!button || disabled) return { disabled, label, ok: false };
      button.click();
      return { disabled, label, ok: true };
    })()`);
    assert(
      repeatCreateClick?.ok,
      'repeated Action Plan CTA must remain clickable when a fresh CTA is rendered',
      repeatCreateClick,
    );

    repeatedResolved = await poll(
      `(async () => {
        const latest = Array.from(document.querySelectorAll('.komsco-ai__message--assistant')).pop();
        const text = latest?.textContent || '';
        const executionCard = latest?.querySelector('[data-action-lifecycle-stage="execution"]');
        const response = await fetch('/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status');
        const payload = response.ok ? await response.json() : {};
        const records = payload?.spec?.records || {};
        return {
          actionPlanButtons: Array.from(latest?.querySelectorAll('.komsco-ai__create-action-plan-button') || [])
            .map((button) => button.textContent?.trim() || ''),
          answerActionRootCount: latest?.querySelectorAll('.komsco-ai__answer-actions').length || 0,
          cards: Array.from(latest?.querySelectorAll('[data-action-lifecycle-stage]') || [])
            .map((card) => ({
              stage: card.getAttribute('data-action-lifecycle-stage'),
              text: (card.textContent || '').slice(0, 220)
            })),
          hasApproveButton: Boolean(latest?.querySelector('[data-answer-action-step="approve-plan"]')),
          hasExecutionCard: Boolean(executionCard),
          status: response.ok ? {
            approvals: (records.approvalDecisions || []).map((record) => ({
              name: record?.metadata?.name || '',
              digest: record?.spec?.approvalDecision?.planDigest || '',
              status: record?.spec?.approvalDecision?.status || '',
              target: record?.spec?.approvalDecision?.target?.name || ''
            })),
            executions: (records.executionRecords || []).map((record) => ({
              name: record?.metadata?.name || '',
              approvalId: record?.spec?.approvalId || '',
              digest: record?.spec?.planDigest || '',
              reason: record?.spec?.mutationOutcome?.reason || ''
            })),
            plans: (records.sealedActionPlans || []).map((record) => ({
              name: record?.metadata?.name || '',
              digest: record?.spec?.sealedActionPlan?.digest?.planDigest || '',
              target: record?.spec?.sealedActionPlan?.target?.name || ''
            })),
            proposals: (records.actionProposals || []).map((record) => ({
              name: record?.metadata?.name || '',
              target: record?.spec?.candidateActionRequest?.target?.name || ''
            }))
          } : { ok: false, status: response.status },
          text: text.slice(0, 1200)
        };
      })()`,
      (value) =>
        (value?.actionPlanButtons || []).length === 0 &&
        (
          (value?.hasExecutionCard && !value?.hasApproveButton) ||
          (value?.hasApproveButton && value?.cards?.some((card) => card.stage === 'plan'))
        ),
      'repeated Action Plan CTA must resolve to either a fresh approval-ready plan or an executed lifecycle card',
      30000,
    );
  }

  return {
    approvalReady,
    approvalStatus,
    before,
    createClick,
    executeClick,
    executionReady,
    planReady,
    planStatus,
    repeatedResolved,
    repeatCreateClick,
  };
};

const verifyLiveEnglishProgressLabels = async () => {
  const unclear = await sendLiveQuestion({
    label: 'English UI unclear Korean input',
    language: 'en',
    mode: 'read-only',
    question: UNCLEAR_CHAT_QUESTIONS[0],
  });
  const englishHey = await sendLiveQuestion({
    label: 'English UI English casual input',
    language: 'en',
    mode: 'read-only',
    question: 'hey',
  });
  const namespace = await sendLiveQuestion({
    label: 'English UI namespace progress',
    language: 'en',
    mode: 'execute',
    question: NAMESPACE_CLEANUP_QUESTION,
  });
  const metrics = { englishHey, namespace, unclear };
  const englishFeedbackCopy = await evaluate(`(async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value) => {
          window.__copiedEnglishFeedbackJson = value;
        }
      }
    });
    const button = document.querySelector('.komsco-ai__rail-feedback-copy');
    const beforeLabel = button?.getAttribute('aria-label') || '';
    button?.click();
    await new Promise((resolve) => setTimeout(resolve, 80));
    const afterLabel = button?.getAttribute('aria-label') || '';
    const copied = window.__copiedEnglishFeedbackJson || '';
    let parsed = null;
    try {
      parsed = JSON.parse(copied);
    } catch {
      parsed = null;
    }
    return {
      afterLabel,
      beforeLabel,
      copiedLength: copied.length,
      ok: beforeLabel === 'Copy feedback JSON' &&
        afterLabel === 'Feedback JSON copied' &&
        Boolean(parsed) &&
        parsed.summary?.total >= 1 &&
        Array.isArray(parsed.records) &&
        !copied.includes('"subject"') &&
        !copied.includes('"groups"') &&
        !copied.includes('"uid"') &&
        !/fixture|local-fixture|local_fixture|local-only/.test(copied)
    };
  })()`);
  metrics.englishFeedbackCopy = englishFeedbackCopy;
  const englishFeedbackRailNotes = await evaluate(`(() => {
    const section = Array.from(document.querySelectorAll('.komsco-ai__rail-section'))
      .find((el) => (el.textContent || '').includes('Answer feedback'));
    const text = section?.textContent?.replace(/\\s+/g, ' ').trim() || '';
    return {
      hasKoreanLabels: text.includes('최근 개선 의견') || text.includes('최근 좋았던 점'),
      ok: text.includes('Answer feedback') &&
        text.includes('Latest needs-work note') &&
        text.includes('Latest good note') &&
        !text.includes('최근 개선 의견') &&
        !text.includes('최근 좋았던 점'),
      text
    };
  })()`);
  metrics.englishFeedbackRailNotes = englishFeedbackRailNotes;

  assert(
    unclear.source === 'OCP guide' &&
      unclear.textIncludesCasualReply &&
      unclear.sourceUsesEnglishLabel &&
      !unclear.sourceHasKorean &&
      !unclear.progressHasKorean &&
      !unclear.answerHasKorean &&
      !unclear.rawProgressTerms.length &&
      !unclear.rawRailTerms.length &&
      !unclear.textIncludesEnglishClarification,
    'English UI short casual answer must show the AIOps for OCP identity guide, not request clarification',
    metrics,
  );
  assert(
    englishHey.source === 'OCP guide' &&
      englishHey.textIncludesCasualReply &&
      englishHey.sourceUsesEnglishLabel &&
      !englishHey.sourceHasKorean &&
      !englishHey.progressHasKorean &&
      !englishHey.answerHasKorean &&
      !englishHey.rawProgressTerms.length &&
      !englishHey.rawRailTerms.length &&
      !englishHey.textIncludesEnglishClarification,
    'English UI English casual answer must stay English and must not fall back to Korean identity copy',
    metrics,
  );
  assert(
    namespace.progressUsesEnglishOperatorLabels &&
      namespace.sourceUsesEnglishLabel &&
      !namespace.sourceHasKorean &&
      !namespace.progressHasKorean &&
      !namespace.answerHasKorean &&
      !namespace.rawProgressTerms.length &&
      !namespace.rawRailTerms.length,
    'English UI operational answer, progress, and source labels must stay English and hide raw operator names',
    metrics,
  );
  assert(
    namespace.source === 'Gateway live query' &&
      namespace.hasGatewayDirect &&
      namespace.textIncludesEnglishExecuteMode &&
      namespace.textIncludesEnglishActionPlanCandidate &&
      namespace.textIncludesReadOnlyCommand &&
      namespace.decisionSectionVisible &&
      namespace.decisionTableCount >= 1 &&
      namespace.decisionTableHasExpectedColumns &&
      namespace.codeActionLabels.length > 0 &&
      !namespace.codeActionLabelsHaveKorean &&
      namespace.detailChromeLabels.length > 0 &&
      !namespace.detailChromeLabelsHaveKorean &&
      namespace.railChromeUsesEnglish &&
      !namespace.railChromeHasKorean &&
      namespace.railChromeMissingEnglishLabels.length === 0 &&
      englishFeedbackCopy.ok &&
      englishFeedbackRailNotes.ok,
    'English UI live answers must localize clarification, execution mode, Action Plan, Gateway source badges, decision tables, feedback notes, code action labels, footer details, and insight rail chrome',
    metrics,
  );

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
  assert(clickedConversation, 'history seeded conversation must be loadable from the sidebar');
  await poll(
    `Boolean(document.querySelector('.komsco-ai__message--assistant .komsco-ai__message-content'))`,
    Boolean,
    'seeded conversation loaded from history',
    60000,
  );
};

const verifyCompactViewportChrome = async () => {
  await setViewport(1280, 720);
  const compactFixture = await installAssistantFixture();
  await send('Page.reload', { ignoreCache: true });
  await poll(
    `document.readyState === 'complete' && Boolean(document.body?.innerText?.trim())`,
    Boolean,
    'compact viewport console reload',
    90000,
  );
  await openAssistant();
  await setUiLanguageInUi('ko');
  await setComposerValue('야');

  const chromeMetrics = await poll(
    `(() => {
      const rect = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          bottom: Math.round(r.bottom),
          height: Math.round(r.height),
          left: Math.round(r.left),
          right: Math.round(r.right),
          top: Math.round(r.top),
          width: Math.round(r.width)
        };
      };
      const inside = (child, parent, pad = 1) =>
        Boolean(child && parent) &&
        child.left >= parent.left - pad &&
        child.top >= parent.top - pad &&
        child.right <= parent.right + pad &&
        child.bottom <= parent.bottom + pad;
      const darkBackground = (value) =>
        /rgb\\((\\d+),\\s*(\\d+),\\s*(\\d+)\\)/.test(value)
          ? value.match(/\\d+/g).slice(0, 3).map(Number).every((part) => part < 48)
          : false;
      const surface = document.querySelector('.komsco-ai__surface');
      const header = document.querySelector('.komsco-ai__header');
      const brand = document.querySelector('.komsco-ai__brand');
      const headerActions = document.querySelector('.komsco-ai__header-actions');
      const status = document.querySelector('.komsco-ai__header-status');
      const workspace = document.querySelector('.komsco-ai__workspace');
      const composerWrap = document.querySelector('.komsco-ai__composer-wrap');
      const composer = document.querySelector('.komsco-ai__composer');
      const input = document.querySelector('.komsco-ai__input');
      const textarea = document.querySelector('.komsco-ai__composer textarea');
      const sendButton = document.querySelector('.komsco-ai__send');
      const surfaceRect = rect(surface);
      const composerWrapRect = rect(composerWrap);
      const composerBottomGap =
        surfaceRect && composerWrapRect ? Math.round(surfaceRect.bottom - composerWrapRect.bottom) : null;
      const viewport = { height: window.innerHeight, width: window.innerWidth };
      const importantElements = [
        ['header', header],
        ['brand', brand],
        ['headerActions', headerActions],
        ['status', status],
        ['workspace', workspace],
        ['composerWrap', composerWrap],
        ['composer', composer],
        ['input', input],
        ['sendButton', sendButton],
      ];
      const outsideSurface = importantElements
        .map(([name, el]) => ({ name, rect: rect(el) }))
        .filter((item) => item.rect && !inside(item.rect, surfaceRect, 2));
      const controls = Array.from(document.querySelectorAll(
        '.komsco-ai__sidebar-toggle, .komsco-ai__language-button, .komsco-ai__header-actions .komsco-ai__icon-button, .komsco-ai__mode-toggle-button, .komsco-ai__quick-menu-trigger, .komsco-ai__attach, .komsco-ai__send'
      ));
      const overflowingControls = controls
        .filter((el) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
        .map((el) => ({
          className: String(el.className),
          label: el.getAttribute('aria-label') || el.textContent.trim(),
          size: {
            ch: el.clientHeight,
            cw: el.clientWidth,
            sh: el.scrollHeight,
            sw: el.scrollWidth
          }
        }));
      const headerButtons = Array.from(document.querySelectorAll(
        '.komsco-ai__sidebar-toggle, .komsco-ai__header-actions .komsco-ai__icon-button'
      ));
      const headerButtonRects = headerButtons.map((el, index) => ({
        index,
        label: el.getAttribute('aria-label') || el.textContent.trim(),
        rect: rect(el)
      })).filter((item) => item.rect);
      const headerOverlaps = [];
      for (let i = 0; i < headerButtonRects.length; i += 1) {
        for (let j = i + 1; j < headerButtonRects.length; j += 1) {
          const a = headerButtonRects[i].rect;
          const b = headerButtonRects[j].rect;
          const separated = a.right <= b.left || b.right <= a.left || a.bottom <= b.top || b.bottom <= a.top;
          if (!separated) headerOverlaps.push([headerButtonRects[i].label, headerButtonRects[j].label]);
        }
      }
      const inputStyle = input ? getComputedStyle(input) : null;
      const sendStyle = sendButton ? getComputedStyle(sendButton) : null;
      const modeLabels = Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button span'))
        .map((el) => el.textContent.trim());
      const languageCode = document.querySelector('.komsco-ai__language-code')?.textContent.trim() || '';
      const visibleText = document.body?.innerText || '';
      const visibleInternalLeaks = [
        'api.local-aiops.invalid',
        '4.20-local',
        'local simulator',
        'local fixture',
        'local-admin',
        'fixture is not ready'
      ].filter((term) => visibleText.toLowerCase().includes(term.toLowerCase()));
      const visibleInternalLeakSnippets = visibleInternalLeaks.map((term) => {
        const index = visibleText.toLowerCase().indexOf(term.toLowerCase());
        return index < 0 ? term : visibleText.slice(Math.max(0, index - 90), index + term.length + 140);
      });
      return {
        darkInput: darkBackground(inputStyle?.backgroundColor || ''),
        darkSend: darkBackground(sendStyle?.backgroundColor || ''),
        composerBottomGap,
        composerWrapRect,
        headerOverlaps,
        languageCode,
        modeLabels,
        ok:
          Boolean(surfaceRect) &&
          surfaceRect.left >= 0 &&
          surfaceRect.top >= 0 &&
          surfaceRect.right <= viewport.width + 1 &&
          surfaceRect.bottom <= viewport.height + 1 &&
          modeLabels.includes('읽기 전용') &&
          modeLabels.includes('실행 가능') &&
          modeLabels.includes('실행 무제한') &&
          languageCode === 'KR' &&
          textarea?.value === '야' &&
          outsideSurface.length === 0 &&
          composerBottomGap !== null &&
          composerBottomGap >= -1 &&
          composerBottomGap <= 12 &&
          overflowingControls.length === 0 &&
          headerOverlaps.length === 0 &&
          visibleInternalLeaks.length === 0 &&
          !darkBackground(inputStyle?.backgroundColor || '') &&
          !darkBackground(sendStyle?.backgroundColor || ''),
        outsideSurface,
        overflowingControls,
        sendBackground: sendStyle?.backgroundColor || '',
        surfaceRect,
        textareaValue: textarea?.value || '',
        visibleInternalLeaks,
        visibleInternalLeakSnippets,
        viewport,
        wrapBackground: inputStyle?.backgroundColor || ''
      };
    })()`,
    (value) => value?.ok,
    'compact 1280x720 Korean assistant chrome without overflow',
    10000,
  );

  await setUiLanguageInUi('en');
  const englishMetrics = await poll(
    `(() => {
      const controls = Array.from(document.querySelectorAll(
        '.komsco-ai__sidebar-toggle, .komsco-ai__language-button, .komsco-ai__header-actions .komsco-ai__icon-button, .komsco-ai__mode-toggle-button, .komsco-ai__quick-menu-trigger, .komsco-ai__attach, .komsco-ai__send'
      ));
      const overflowingControls = controls
        .filter((el) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
        .map((el) => ({
          className: String(el.className),
          label: el.getAttribute('aria-label') || el.textContent.trim(),
          size: {
            ch: el.clientHeight,
            cw: el.clientWidth,
            sh: el.scrollHeight,
            sw: el.scrollWidth
          }
        }));
      const labels = controls
        .map((el) => el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent.trim())
        .filter(Boolean);
      const modeLabels = Array.from(document.querySelectorAll('.komsco-ai__mode-toggle-button span'))
        .map((el) => el.textContent.trim());
      const languageCode = document.querySelector('.komsco-ai__language-code')?.textContent.trim() || '';
      return {
        koreanLabels: labels.filter((label) => /[가-힣]/.test(label)),
        languageCode,
        modeLabels,
        ok:
          languageCode === 'EN' &&
          modeLabels.includes('Read only') &&
          modeLabels.includes('Execute') &&
          modeLabels.includes('Unrestricted') &&
          overflowingControls.length === 0 &&
          labels.every((label) => !/[가-힣]/.test(label)),
        overflowingControls
      };
    })()`,
    (value) => value?.ok,
    'compact 1280x720 English assistant chrome without overflow or untranslated controls',
    10000,
  );

  await setUiLanguageInUi('ko');
  await openHistoryActionList(0);
  const historyMetrics = await poll(
    `(() => {
      const rect = (el) => {
        if (!el) return null;
        const r = el.getBoundingClientRect();
        return {
          bottom: Math.round(r.bottom),
          height: Math.round(r.height),
          left: Math.round(r.left),
          right: Math.round(r.right),
          top: Math.round(r.top),
          width: Math.round(r.width)
        };
      };
      const surface = document.querySelector('.komsco-ai__surface');
      const sidebar = document.querySelector('.komsco-ai__history-sidebar');
      const historyList = document.querySelector('.komsco-ai__history-list');
      const userFooter = document.querySelector('.komsco-ai__history-user');
      const refs = Array.from(document.querySelectorAll('.komsco-ai__history-action-ref'));
      const rows = Array.from(document.querySelectorAll('.komsco-ai__history-item-row'));
      const surfaceRect = rect(surface);
      const sidebarRect = rect(sidebar);
      const historyListRect = rect(historyList);
      const userFooterRect = rect(userFooter);
      const historyListFooterGap =
        historyListRect && userFooterRect ? Math.round(userFooterRect.top - historyListRect.bottom) : null;
      const userFooterBottomInset =
        sidebarRect && userFooterRect ? Math.round(sidebarRect.bottom - userFooterRect.bottom) : null;
      const viewport = { height: window.innerHeight, width: window.innerWidth };
      const overflowingRefs = refs
        .filter((el) => el.scrollWidth > el.clientWidth + 1 || el.scrollHeight > el.clientHeight + 1)
        .map((el) => el.textContent.replace(/\\s+/g, ' ').trim());
      const overflowingRows = rows
        .filter((el) => el.scrollWidth > el.clientWidth + 1)
        .map((el) => el.textContent.replace(/\\s+/g, ' ').trim().slice(0, 120));
      const rawHistoryTerms = [
        'delete_namespace_after_approval',
        'rollout_restart_deployment',
        'ExecutionRecord',
        'SealedActionPlanRecord',
        'ActionProposalRecord',
        'ApprovalDecisionRecord',
        'proposal-local',
        'plan-local',
        'approval-local',
        'execution-local',
        'mutation_succeeded',
        'review_recorded',
        'mutation_failed'
      ].filter((term) => refs.some((el) => (el.textContent || '').includes(term) || (el.getAttribute('title') || '').includes(term)));
      const genericHistoryActionLabels = refs
        .filter((el) => {
          const stage = el.querySelector('.komsco-ai__history-action-ref-stage')?.textContent.trim() || '';
          const primary = el.querySelector('strong')?.textContent.trim() || '';
          return (
            stage === 'Action Plan' ||
            /^(승인 필요|실행 완료|후보 접수|Candidate received|Approval required|Executed)$/i.test(primary)
          );
        })
        .map((el) => el.textContent.replace(/\\s+/g, ' ').trim());
      const purposeActionLabels = refs
        .map((el) => el.querySelector('strong')?.textContent.trim() || '')
        .filter((label) => /정리|Pod|Namespace|review|plan/i.test(label));
      const userFooterText = userFooter?.textContent?.replace(/\\s+/g, ' ').trim() || '';
      const userFooterHasInternalFixture = /local-aiops|\\.invalid|local-admin|fixture/i.test(userFooterText);
      const userFooterHasExpectedIdentity =
        (
          userFooterText.includes('검증 사용자') &&
          userFooterText.includes('Gateway 검증 환경')
        ) ||
        (
          userFooterText.includes('admin') &&
          userFooterText.includes('api.ocp.cywell.server:6443')
        );
      return {
        actionRefCount: refs.length,
        compactFixture: ${JSON.stringify(compactFixture)},
        ok:
          Boolean(surfaceRect && sidebarRect) &&
          surfaceRect.left >= 0 &&
          surfaceRect.top >= 0 &&
          surfaceRect.right <= viewport.width + 1 &&
          surfaceRect.bottom <= viewport.height + 1 &&
          sidebarRect.left >= surfaceRect.left - 1 &&
          sidebarRect.top >= surfaceRect.top - 1 &&
          sidebarRect.bottom <= surfaceRect.bottom + 1 &&
          sidebarRect.width >= 260 &&
          Boolean(historyListRect && userFooterRect) &&
          historyListFooterGap !== null &&
          historyListFooterGap >= 0 &&
          userFooterBottomInset !== null &&
          userFooterBottomInset >= -1 &&
          userFooterRect.top >= sidebarRect.top &&
          refs.length >= 1 &&
          overflowingRefs.length === 0 &&
          overflowingRows.length === 0 &&
          rawHistoryTerms.length === 0 &&
          genericHistoryActionLabels.length === 0 &&
          purposeActionLabels.length >= 1 &&
          !userFooterHasInternalFixture &&
          userFooterHasExpectedIdentity,
        overflowingRefs,
        overflowingRows,
        rawHistoryTerms,
        genericHistoryActionLabels,
        purposeActionLabels,
        historyListFooterGap,
        historyListRect,
        sidebarRect,
        surfaceRect,
        userFooterBottomInset,
        userFooterHasInternalFixture,
        userFooterHasExpectedIdentity,
        userFooterRect,
        userFooterText,
        viewport
      };
    })()`,
    (value) => value?.ok,
    'compact 1280x720 history sidebar and action refs without overflow',
    10000,
  );

  await setViewport(792, 891);
  await openHistory();
  const tallHistoryMetrics = await poll(
    `(() => {
      const rect = (selector) => {
        const el = document.querySelector(selector);
        if (!el) return null;
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return {
          bottom: Math.round(r.bottom),
          gridTemplateRows: s.gridTemplateRows,
          height: Math.round(r.height),
          left: Math.round(r.left),
          maxHeight: s.maxHeight,
          minHeight: s.minHeight,
          overflowY: s.overflowY,
          right: Math.round(r.right),
          top: Math.round(r.top),
          width: Math.round(r.width)
        };
      };
      const surfaceRect = rect('.komsco-ai__surface');
      const panelRect = rect('.komsco-ai__panel');
      const sidebarRect = rect('.komsco-ai__history-sidebar');
      const historyListRect = rect('.komsco-ai__history-list');
      const userFooterRect = rect('.komsco-ai__history-user');
      const composerRect = rect('.komsco-ai__composer-wrap');
      const surfaceRowHeight = surfaceRect?.gridTemplateRows
        ?.split(' ')
        .map((part) => Number.parseFloat(part))
        .find((value) => Number.isFinite(value)) ?? null;
      const viewport = { height: window.innerHeight, width: window.innerWidth };
      const composerBottomGapToSurface =
        surfaceRect && composerRect ? Math.round(surfaceRect.bottom - composerRect.bottom) : null;
      const panelBottomGapToSurface =
        surfaceRect && panelRect ? Math.round(surfaceRect.bottom - panelRect.bottom) : null;
      const listFooterGap =
        historyListRect && userFooterRect ? Math.round(userFooterRect.top - historyListRect.bottom) : null;
      const footerBottomInset =
        sidebarRect && userFooterRect ? Math.round(sidebarRect.bottom - userFooterRect.bottom) : null;
      const footerViewportBottomGap = userFooterRect ? Math.round(viewport.height - userFooterRect.bottom) : null;
      return {
        ok:
          Boolean(surfaceRect && panelRect && sidebarRect && historyListRect && userFooterRect && composerRect) &&
          surfaceRect.bottom <= viewport.height + 1 &&
          sidebarRect.bottom <= surfaceRect.bottom + 1 &&
          panelRect.bottom >= surfaceRect.bottom - 1 &&
          panelRect.bottom <= surfaceRect.bottom + 1 &&
          composerBottomGapToSurface !== null &&
          composerBottomGapToSurface >= -1 &&
          composerBottomGapToSurface <= 2 &&
          panelBottomGapToSurface !== null &&
          panelBottomGapToSurface >= -1 &&
          panelBottomGapToSurface <= 2 &&
          listFooterGap !== null &&
          listFooterGap >= 0 &&
          footerBottomInset !== null &&
          footerBottomInset >= -1 &&
          footerViewportBottomGap !== null &&
          footerViewportBottomGap >= 0 &&
          (surfaceRowHeight === null || surfaceRowHeight <= surfaceRect.height + 1),
        composerBottomGapToSurface,
        footerBottomInset,
        footerViewportBottomGap,
        historyListRect,
        listFooterGap,
        panelBottomGapToSurface,
        panelRect,
        sidebarRect,
        surfaceRect,
        surfaceRowHeight,
        userFooterRect,
        viewport
      };
    })()`,
    (value) => value?.ok,
    '792x891 history-open assistant layout without composer gap or lost user footer',
    10000,
  );

  const screenshotPath = path.join(screenshotDir, 'v0281-chatbot-compact.png');
  await captureScreenshot(screenshotPath);
  const tallHistoryScreenshotPath = path.join(screenshotDir, 'v0281-chatbot-history-open-792x891.png');
  await captureScreenshot(tallHistoryScreenshotPath);

  return {
    chromeMetrics,
    englishMetrics,
    historyMetrics,
    tallHistoryMetrics,
    tallHistoryScreenshotPath,
    screenshotPath,
  };
};

const verifyConsoleAssistant = async () => {
  const reset = await resetLocalGatewayState();
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
    const rawTerms = [
      '[RAG 근거]',
      '[ 참고 문서 ]',
      'source:',
      'score=',
      'post_answer',
      'RCA 문맥 연결',
      'Tool Plan JSON',
      'ActionProposal/SealedActionPlan',
      '답변 근거 연결 완료',
      '최종 답변에 사용한 근거',
      '조회 근거',
      '확인한 근거',
      '근거 기반 조치 후보',
      '근거 수집',
      '근거 상세보기',
      'github.com/openshift',
      'docs.openshift.com',
      'https://access.redhat.com'
    ]
      .filter((term) => text.includes(term));
    const rawTermSnippets = Object.fromEntries(rawTerms.map((term) => {
      const index = text.indexOf(term);
      return [
        term,
        index >= 0 ? text.slice(Math.max(0, index - 220), index + term.length + 220) : ''
      ];
    }));
    return {
      actionButtonLabels: Array.from(document.querySelectorAll('.komsco-ai__answer-action-controls .komsco-ai__action-button')).map((el) => el.textContent.trim()),
      actionCards: document.querySelectorAll('.komsco-ai__answer-action-card').length,
      disabledActionButtons: document.querySelectorAll('.komsco-ai__answer-action-controls .komsco-ai__action-button[disabled]').length,
      fontSize: style ? parseFloat(style.fontSize) : 0,
      lineHeight: style ? parseFloat(style.lineHeight) : 0,
      rawTerms,
      rawTermSnippets,
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

  await evaluate(`(() => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (text) => {
          window.__aiopsLastMessageCopy = text;
        }
      }
    });
    return true;
  })()`);
  await evaluate(`(() => {
    document.querySelector('.komsco-ai__message--assistant [data-message-actions="assistant"] [aria-label="복사"]')?.click();
    return true;
  })()`);
  const assistantCopyStatus = await poll(
    `(() => {
      const actions = document.querySelector('.komsco-ai__message--assistant [data-message-actions="assistant"]');
      const status = actions?.querySelector('.komsco-ai__message-action-status')?.textContent.trim() || '';
      const labels = Array.from(actions?.querySelectorAll('button') || []).map((el) => el.getAttribute('aria-label') || '');
      return {
        copiedTextLength: String(window.__aiopsLastMessageCopy || '').length,
        labels,
        ok: status === '복사됨' && labels.includes('복사됨') && String(window.__aiopsLastMessageCopy || '').length > 0,
        status
      };
    })()`,
    (value) => value?.ok,
    'assistant copy icon visible feedback',
    5000,
  );
  const messageCopyScreenshotPath = path.join(screenshotDir, 'v0281-chatbot-message-copy.png');
  await captureScreenshot(
    messageCopyScreenshotPath,
    "document.querySelector('.komsco-ai__message--assistant [data-message-actions=\"assistant\"]')?.closest('.komsco-ai__message')",
  );
  const userCopyBefore = await evaluate(`(() => {
    const userButtons = Array.from(document.querySelectorAll('.komsco-ai__message--user [data-message-actions="user"] button'));
    const button = userButtons[userButtons.length - 1];
    const rect = button?.getBoundingClientRect();
    return rect ? { left: rect.left, right: rect.right } : null;
  })()`);
  await evaluate(`(() => {
    const userButtons = Array.from(document.querySelectorAll('.komsco-ai__message--user [data-message-actions="user"] button'));
    userButtons[userButtons.length - 1]?.click();
    return true;
  })()`);
  const userCopyStatus = await poll(
    `(() => {
      const actions = document.querySelector('.komsco-ai__message--user [data-message-actions="user"]');
      const status = actions?.querySelector('.komsco-ai__message-action-status')?.textContent.trim() || '';
      const labels = Array.from(actions?.querySelectorAll('button') || []).map((el) => el.getAttribute('aria-label') || '');
      const userButtons = Array.from(actions?.querySelectorAll('button') || []);
      const button = userButtons[userButtons.length - 1];
      const rect = button?.getBoundingClientRect();
      const before = ${JSON.stringify(userCopyBefore)};
      const copyButtonStayedPut = Boolean(
        rect &&
        before &&
        Math.abs(rect.left - before.left) <= 1 &&
        Math.abs(rect.right - before.right) <= 1
      );
      return {
        copyButtonStayedPut,
        copiedTextLength: String(window.__aiopsLastMessageCopy || '').length,
        labels,
        ok: status === '복사됨' &&
          labels.includes('복사됨') &&
          String(window.__aiopsLastMessageCopy || '').length > 0 &&
          copyButtonStayedPut,
        status
      };
    })()`,
    (value) => value?.ok,
    'user copy icon visible feedback',
    5000,
  );
  const userMessageCopyScreenshotPath = path.join(screenshotDir, 'v0281-chatbot-user-message-copy.png');
  await captureScreenshot(
    userMessageCopyScreenshotPath,
    "document.querySelector('.komsco-ai__message--user [data-message-actions=\"user\"]')?.closest('.komsco-ai__message')",
  );
  await sleep(1500);

  await setUiLanguageInUi('en');
  const englishActionMetrics = await evaluate(`(() => {
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
    JSON.stringify(englishActionMetrics.userActions) === JSON.stringify(['Edit and resend', 'Copy']),
    'English user message footer must expose edit-resend and copy only',
    englishActionMetrics,
  );
  assert(
    JSON.stringify(englishActionMetrics.assistantActions) ===
      JSON.stringify(['Copy', 'Good response', 'Bad response']),
    'English assistant message footer must expose copy, good response, and bad response only',
    englishActionMetrics,
  );
  assert(
    !englishActionMetrics.hiddenFullscreenInMessageActions,
    'English message footer must not contain a fullscreen action',
    englishActionMetrics,
  );

  const englishFeedbackClickMetrics = await evaluate(`(() => {
    const down = document.querySelector('.komsco-ai__message--assistant [aria-label="Bad response"]');
    down?.click();
    const form = document.querySelector('.komsco-ai__feedback-comment');
    const input = form?.querySelector('input');
    const status = document.querySelector('.komsco-ai__message--assistant [data-message-actions="assistant"] .komsco-ai__message-action-status')?.textContent.trim() || '';
    const metrics = {
      formTextBeforeSubmit: form?.textContent.trim() || '',
      inputPlaceholder: input?.getAttribute('placeholder') || '',
      inputValue: input?.value || '',
      pressed: down?.getAttribute('aria-pressed') || '',
      status
    };
    down?.click();
    return metrics;
  })()`);
  assert(
      englishFeedbackClickMetrics.pressed === 'true' &&
      englishFeedbackClickMetrics.formTextBeforeSubmit.includes('Improve') &&
      englishFeedbackClickMetrics.formTextBeforeSubmit.includes('saved: browser+Gateway') &&
      englishFeedbackClickMetrics.inputPlaceholder === 'Note what was wrong or confusing' &&
      englishFeedbackClickMetrics.inputValue === '' &&
      englishFeedbackClickMetrics.status === 'Needs work selected',
    'English thumbs-down feedback must open a localized tester comment rail',
    englishFeedbackClickMetrics,
  );
  await setUiLanguageInUi('ko');

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
    const status = document.querySelector('.komsco-ai__message--assistant [data-message-actions="assistant"] .komsco-ai__message-action-status')?.textContent.trim() || '';
    return {
      formTextBeforeSubmit: form?.textContent.trim() || '',
      inputValue: input?.value || '',
      pressed: down?.getAttribute('aria-pressed') || '',
      status
    };
  })()`);
  assert(
      feedbackClickMetrics.pressed === 'true' &&
      feedbackClickMetrics.formTextBeforeSubmit.includes('개선점') &&
      feedbackClickMetrics.formTextBeforeSubmit.includes('기록: 브라우저+Gateway') &&
      feedbackClickMetrics.inputValue === '' &&
      feedbackClickMetrics.status === '싫어요 선택됨',
    'thumbs-down feedback must open an editable tester comment rail',
    feedbackClickMetrics,
  );
  const messageFeedbackScreenshotPath = path.join(screenshotDir, 'v0281-chatbot-message-feedback.png');
  await captureScreenshot(
    messageFeedbackScreenshotPath,
    "document.querySelector('.komsco-ai__feedback-comment')",
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
  const feedbackSavedStatus = await poll(
    `(() => {
      const actions = document.querySelector('.komsco-ai__message--assistant [data-message-actions="assistant"]');
      const status = actions?.querySelector('.komsco-ai__message-action-status')?.textContent.trim() || '';
      const button = document.querySelector('.komsco-ai__feedback-comment button');
      return {
        buttonText: button?.textContent.trim() || '',
        ok: status === '싫어요 저장됨' && button?.textContent.trim() === '저장됨',
        status
      };
    })()`,
    (value) => value?.ok,
    'thumbs-down feedback saved status after tester comment submit',
    10000,
  );
  const feedbackStored = await poll(
    `(() => {
      const feedbackKey = 'komsco-ai.assistant.message-feedback.v1';
      const records = JSON.parse(localStorage.getItem(feedbackKey) || '[]');
      const latest = records[0] || {};
      return {
        latest,
        ok: latest.rating === 'down' &&
          latest.optionalComment === ${JSON.stringify(feedbackComment)} &&
          typeof latest.source === 'string' &&
          latest.source.length > 0 &&
          latest.source !== 'unknown'
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
      const matching = records.find((record) =>
        record?.spec?.rating === 'down' &&
        record?.spec?.optionalComment === ${JSON.stringify(feedbackComment)}
      );
      const latest = matching || records[records.length - 1] || {};
      return {
        latest,
        ok: Boolean(matching) &&
          typeof latest?.spec?.source === 'string' &&
          latest.spec.source.length > 0 &&
          latest.spec.source !== 'unknown'
      };
    })()`,
    (value) => value?.ok,
    'gateway feedback record with optional comment',
    30000,
  );
  const feedbackRail = await poll(
    `(() => {
      const section = Array.from(document.querySelectorAll('.komsco-ai__rail-section'))
        .find((el) => (el.textContent || '').includes('답변 피드백'));
      const text = section?.textContent?.replace(/\\s+/g, ' ').trim() || '';
      return {
        ok: text.includes('답변 피드백') &&
          text.includes('개선') &&
          text.includes('최근 개선 의견') &&
          text.includes(${JSON.stringify(feedbackComment)}),
        text
      };
    })()`,
    (value) => value?.ok,
    'insight rail answer feedback summary with latest needs-work tester comment',
    30000,
  );
  const feedbackCopy = await evaluate(`(async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value) => {
          window.__copiedFeedbackJson = value;
        }
      }
    });
    const button = document.querySelector('.komsco-ai__rail-feedback-copy');
    button?.click();
    await new Promise((resolve) => setTimeout(resolve, 50));
    const copied = window.__copiedFeedbackJson || '';
    let parsed = null;
    try {
      parsed = JSON.parse(copied);
    } catch {
      parsed = null;
    }
    return {
      buttonLabel: button?.getAttribute('aria-label') || '',
      copied,
      ok: Boolean(parsed) &&
        parsed.summary?.total >= 1 &&
        parsed.summary?.needsWork >= 1 &&
        parsed.latestByRating?.needsWork?.rating === 'down' &&
        parsed.latestByRating?.needsWork?.optionalComment === ${JSON.stringify(feedbackComment)} &&
        copied.includes(${JSON.stringify(feedbackComment)}) &&
        !copied.includes('"subject"') &&
        !copied.includes('"groups"') &&
        !copied.includes('"uid"') &&
        !/fixture|local-fixture|local_fixture|local-only/.test(copied)
    };
  })()`);
  assert(
    feedbackCopy.ok,
    'feedback rail copy button must copy reviewable JSON with latest tester comment and no subject/debug source block',
    feedbackCopy,
  );

  const positiveFeedbackComment = '검증 스크립트: 이 답변 구조는 유지';
  const positiveFeedbackClickMetrics = await evaluate(`(() => {
    const up = document.querySelector('.komsco-ai__message--assistant [aria-label="좋은 답변"]');
    up?.click();
    const form = document.querySelector('.komsco-ai__feedback-comment');
    const input = form?.querySelector('input');
    return {
      formTextBeforeSubmit: form?.textContent.trim() || '',
      inputPlaceholder: input?.getAttribute('placeholder') || '',
      inputValue: input?.value || '',
      pressed: up?.getAttribute('aria-pressed') || ''
    };
  })()`);
  assert(
    positiveFeedbackClickMetrics.pressed === 'true' &&
      positiveFeedbackClickMetrics.formTextBeforeSubmit.includes('좋았던 점') &&
      positiveFeedbackClickMetrics.formTextBeforeSubmit.includes('기록: 브라우저+Gateway') &&
      positiveFeedbackClickMetrics.inputPlaceholder === '유지할 만한 좋은 점을 짧게 입력' &&
      positiveFeedbackClickMetrics.inputValue === '',
    'thumbs-up feedback must ask what should be preserved with a specific placeholder',
    positiveFeedbackClickMetrics,
  );
  await evaluate(`(() => {
    const input = document.querySelector('.komsco-ai__feedback-comment input');
    if (!input) return false;
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
    setter?.call(input, ${JSON.stringify(positiveFeedbackComment)});
    input.dispatchEvent(new Event('input', { bubbles: true }));
    return true;
  })()`);
  const positiveFeedbackDraftMetrics = await poll(
    `(() => {
      const form = document.querySelector('.komsco-ai__feedback-comment');
      const input = form?.querySelector('input');
      const submit = form?.querySelector('button');
      return {
        buttonDisabledBeforeSubmit: Boolean(submit?.disabled),
        buttonTextBeforeSubmit: submit?.textContent.trim() || '',
        inputValue: input?.value || '',
        ok: input?.value === ${JSON.stringify(positiveFeedbackComment)} &&
          submit?.textContent.trim() === '저장' &&
          !submit?.disabled
      };
    })()`,
    (value) => value?.ok,
    'editable positive feedback comment dirty state',
    10000,
  );
  await evaluate(`document.querySelector('.komsco-ai__feedback-comment button')?.click(); true;`);
  const positiveFeedbackStored = await poll(
    `(() => {
      const feedbackKey = 'komsco-ai.assistant.message-feedback.v1';
      const records = JSON.parse(localStorage.getItem(feedbackKey) || '[]');
      const latest = records[0] || {};
      return {
        latest,
        ok: latest.rating === 'up' &&
          latest.optionalComment === ${JSON.stringify(positiveFeedbackComment)}
      };
    })()`,
    (value) => value?.ok,
    'local positive feedback payload with optional comment',
    10000,
  );
  const positiveFeedbackGateway = await poll(
    `(async () => {
      const response = await fetch('/api/proxy/plugin/cywell-aiops-console-plugin/ai-gateway/v1/aiops/status');
      if (!response.ok) return { ok: false, status: response.status };
      const payload = await response.json();
      const records = payload?.spec?.records?.chatFeedback || [];
      const matched = records.find((record) =>
        record?.spec?.rating === 'up' &&
        record?.spec?.optionalComment === ${JSON.stringify(positiveFeedbackComment)}
      );
      return { matched, ok: Boolean(matched) };
    })()`,
    (value) => value?.ok,
    'gateway positive feedback record with optional comment',
    30000,
  );
  const combinedFeedbackRail = await poll(
    `(() => {
      const section = Array.from(document.querySelectorAll('.komsco-ai__rail-section'))
        .find((el) => (el.textContent || '').includes('답변 피드백'));
      const text = section?.textContent?.replace(/\\s+/g, ' ').trim() || '';
      return {
        ok: text.includes('최근 개선 의견') &&
          text.includes(${JSON.stringify(feedbackComment)}) &&
          text.includes('최근 좋았던 점') &&
          text.includes(${JSON.stringify(positiveFeedbackComment)}),
        text
      };
    })()`,
    (value) => value?.ok,
    'insight rail answer feedback summary with separate good and needs-work comments',
    30000,
  );
  const combinedFeedbackCopy = await evaluate(`(async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: {
        writeText: async (value) => {
          window.__copiedCombinedFeedbackJson = value;
        }
      }
    });
    const button = document.querySelector('.komsco-ai__rail-feedback-copy');
    button?.click();
    await new Promise((resolve) => setTimeout(resolve, 50));
    const copied = window.__copiedCombinedFeedbackJson || '';
    let parsed = null;
    try {
      parsed = JSON.parse(copied);
    } catch {
      parsed = null;
    }
    return {
      copiedLength: copied.length,
      ok: Boolean(parsed) &&
        parsed.latestByRating?.needsWork?.rating === 'down' &&
        parsed.latestByRating?.needsWork?.optionalComment === ${JSON.stringify(feedbackComment)} &&
        parsed.latestByRating?.good?.rating === 'up' &&
        parsed.latestByRating?.good?.optionalComment === ${JSON.stringify(positiveFeedbackComment)} &&
        !copied.includes('"subject"') &&
        !copied.includes('"groups"') &&
        !copied.includes('"uid"') &&
        !/fixture|local-fixture|local_fixture|local-only/.test(copied)
    };
  })()`);
  assert(
    combinedFeedbackCopy.ok,
    'feedback JSON copy must expose latest good and needs-work notes without subject/debug source block',
    combinedFeedbackCopy,
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
        '.komsco-ai__sidebar-toggle, .komsco-ai__language-button, .komsco-ai__header-actions .komsco-ai__icon-button, .komsco-ai__mode-toggle-button, .komsco-ai__quick-menu-trigger, .komsco-ai__attach, .komsco-ai__send'
      ));
      const controlLabels = controls
        .map((el) => el.getAttribute('aria-label') || el.getAttribute('title') || el.textContent.trim())
        .filter(Boolean);
      const requiredControlLabels = [
        'Conversation sidebar',
        'Switch to Korean',
        'Open full screen',
        'Unlock window size',
        'Close AIOps for OCP',
        'Open common check prompts',
        'Attach file',
        'Send question'
      ];
      const missingControlLabels = requiredControlLabels.filter((label) => !controlLabels.includes(label));
      const koreanControlLabels = controlLabels.filter((label) => /[가-힣]/.test(label));
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
          missingControlLabels.length === 0 &&
          koreanControlLabels.length === 0 &&
          overflowingControls.length === 0,
        controlLabels,
        executionBadgeText,
        koreanControlLabels,
        missingControlLabels,
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

  await evaluate(`(() => {
    const close = Array.from(document.querySelectorAll('.komsco-ai__header-actions button'))
      .find((el) => ['AIOps for OCP 닫기', 'Close AIOps for OCP'].includes(el.getAttribute('aria-label') || ''));
    close?.click();
    return true;
  })()`);
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
      (respondingRailMetrics.animationName === 'none' ||
        respondingRailMetrics.animationName === '') &&
      parseFloat(respondingRailMetrics.height) >= 2,
    'responding assistant header must keep a calm static bottom rail',
    respondingRailMetrics,
  );

  await openHistoryActionList(0);
  const historyMetrics = await evaluate(`(() => {
    const sidebar = document.querySelector('.komsco-ai__history-sidebar');
    const brand = document.querySelector('.komsco-ai__history-brand');
    const historyList = document.querySelector('.komsco-ai__history-list');
    const userFooter = document.querySelector('.komsco-ai__history-user');
    const refs = Array.from(document.querySelectorAll('.komsco-ai__history-action-ref'));
    const sidebarRect = sidebar?.getBoundingClientRect();
    const historyListRect = historyList?.getBoundingClientRect();
    const userFooterRect = userFooter?.getBoundingClientRect();
    const historyListFooterGap =
      historyListRect && userFooterRect ? Math.round(userFooterRect.top - historyListRect.bottom) : null;
    const userFooterBottomInset =
      sidebarRect && userFooterRect ? Math.round(sidebarRect.bottom - userFooterRect.bottom) : null;
    const brandStyle = brand ? getComputedStyle(brand) : null;
    const rawHistoryTerms = [
      'delete_namespace_after_approval',
      'rollout_restart_deployment',
      'ExecutionRecord',
      'SealedActionPlanRecord',
      'ActionProposalRecord',
      'ApprovalDecisionRecord',
      'proposal-local',
      'plan-local',
      'approval-local',
      'execution-local',
      'mutation_succeeded',
      'review_recorded',
      'mutation_failed'
    ].filter((term) => refs.some((el) => (el.textContent || '').includes(term) || (el.getAttribute('title') || '').includes(term)));
    const userFooterUserText = userFooter?.querySelector('strong')?.textContent?.replace(/\\s+/g, ' ').trim() || '';
    const userFooterClusterText = userFooter?.querySelector('small')?.textContent?.replace(/\\s+/g, ' ').trim() || '';
    const userFooterText = [userFooterUserText, userFooterClusterText].filter(Boolean).join(' · ');
    const userFooterHasInternalFixture = /local-aiops|\\.invalid|local-admin|fixture/i.test(userFooterText);
    return {
      actionRefCount: refs.length,
      aggregatePanelCount: document.querySelectorAll('.komsco-ai__session-actions').length,
      iconCount: document.querySelectorAll('.komsco-ai__history-action-ref-icon').length,
      groupedRefs: refs.filter((el) => Boolean(el.closest('.komsco-ai__history-item-row'))).length,
      logoBoxBackground: brandStyle?.backgroundColor || '',
      logoBoxShadow: brandStyle?.boxShadow || '',
      overflowingRefs: refs.filter((el) => el.scrollWidth > el.clientWidth + 1).length,
      rawHistoryTerms,
      footerPinned:
        Boolean(sidebarRect && historyListRect && userFooterRect) &&
        historyListFooterGap !== null &&
        historyListFooterGap >= 0 &&
        userFooterBottomInset !== null &&
        userFooterBottomInset >= -1 &&
        userFooterRect.top >= sidebarRect.top,
      historyListRect: historyListRect ? {
        bottom: Math.round(historyListRect.bottom),
        top: Math.round(historyListRect.top)
      } : null,
      historyListFooterGap,
      sidebarWidth: sidebarRect ? Math.round(sidebarRect.width) : 0,
      userFooterBottomInset,
      userFooterHasInternalFixture,
      userFooterRect: userFooterRect ? {
        bottom: Math.round(userFooterRect.bottom),
        top: Math.round(userFooterRect.top)
      } : null,
      userFooterUserText,
      userFooterClusterText,
      userFooterText,
      userFooterVisibleInternalHost: /local-aiops|\\.invalid/i.test(userFooterText)
    };
  })()`);
  assert(historyMetrics.actionRefCount >= 1, 'history sidebar must show action refs', {
    fixture,
    reset,
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
  assert(historyMetrics.footerPinned, 'history user footer must stay pinned below the scrollable history list', historyMetrics);
  assert(
    historyMetrics.logoBoxBackground !== 'rgba(0, 0, 0, 0)' &&
      historyMetrics.logoBoxBackground !== 'transparent',
    'history logo wrapper must keep the product app icon treatment',
    historyMetrics,
  );
  assert(historyMetrics.overflowingRefs === 0, 'history action refs must not overflow', historyMetrics);
  assert(
    historyMetrics.rawHistoryTerms.length === 0,
    'history action refs must not expose raw action tool, record kind, or local record ids',
    historyMetrics,
  );
  assert(
    !historyMetrics.userFooterHasInternalFixture &&
      !historyMetrics.userFooterVisibleInternalHost &&
      historyMetrics.userFooterUserText.length > 0 &&
      historyMetrics.userFooterClusterText.length > 0,
    'history user footer must not visibly expose local fixture user or invalid host',
    historyMetrics,
  );

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
  assert(clickedOlderAction, 'history seeded data must expose a second conversation action ref');
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

  await captureScreenshot(path.join(screenshotDir, 'v0281-chatbot-history.png'));

  const liveModeRenderedAnswers = await verifyLiveModeRenderedAnswers();
  const liveActionPlanClickThrough = await verifyLiveActionPlanClickThrough();
  const liveTestPodCreateAnswers = await verifyLiveTestPodCreateAnswers();
  const liveCasualAnswers = await verifyLiveCasualAnswers();
  const liveEnglishProgressLabels = await verifyLiveEnglishProgressLabels();
  const compactViewportMetrics = await verifyCompactViewportChrome();

  return {
    closeReopenMetrics,
    compactViewportMetrics,
    feedbackCopy,
    feedbackGateway,
    feedbackRail,
    feedbackStored,
    fixture,
    historyMetrics,
    liveActionPlanClickThrough,
    liveCasualAnswers,
    liveEnglishProgressLabels,
    liveModeRenderedAnswers,
    liveTestPodCreateAnswers,
    messageCopyScreenshotPath,
    messageFeedbackScreenshotPath,
    userMessageCopyScreenshotPath,
    metrics,
    resizeMetrics,
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
        visibleInternalLeaks: [
          'api.local-aiops.invalid',
          '4.20-local',
          'local simulator',
          'local fixture',
          'local-admin',
          'fixture is not ready'
        ].filter((term) => text.toLowerCase().includes(term.toLowerCase())),
        visibleInternalLeakSnippets: [
          'api.local-aiops.invalid',
          '4.20-local',
          'local simulator',
          'local fixture',
          'local-admin',
          'fixture is not ready'
        ]
          .filter((term) => text.toLowerCase().includes(term.toLowerCase()))
          .map((term) => {
            const index = text.toLowerCase().indexOf(term.toLowerCase());
            return index < 0 ? term : text.slice(Math.max(0, index - 90), index + term.length + 140);
          }),
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
  assert(
    metrics.visibleInternalLeaks.length === 0,
    'standalone portal must not expose local fixture internals in visible text',
    metrics,
  );
  return metrics;
};

const main = async () => {
  sourceReview();
  const casualContracts = await verifyCasualChatContracts();
  const ambiguousOperationalContracts = await verifyAmbiguousOperationalContracts();
  const modeContracts = await verifyModeAnswerContracts();
  const englishNamespaceExtraction = await verifyEnglishNamespaceExtractionContract();
  const testPodContracts = await verifyTestPodCreateContracts();
  const consolePluginChunks = await verifyConsolePluginChunkProxy();
  const chromeVersion = await setupBrowser();
  const consoleResult = await verifyConsoleAssistant();
  const portalResult = await verifyStandalonePortal();

  chromeWebSocket.close();
  chromeProcess.kill('SIGTERM');

  const output = {
    chrome: chromeVersion,
    ambiguousOperationalContracts,
    casualContracts,
    consolePluginChunks,
    consoleResult,
    englishNamespaceExtraction,
    modeContracts,
    passed: true,
    portalResult,
    screenshots: [
      path.join(screenshotDir, 'v0281-chatbot-history.png'),
      path.join(screenshotDir, 'v0281-chatbot-compact.png'),
      path.join(screenshotDir, 'v0281-chatbot-message-copy.png'),
      path.join(screenshotDir, 'v0281-chatbot-message-feedback.png'),
      path.join(screenshotDir, 'v0281-chatbot-user-message-copy.png'),
    ],
    testPodContracts,
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
