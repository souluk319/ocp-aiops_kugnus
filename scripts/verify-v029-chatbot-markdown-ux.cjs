#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');

const readFile = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

const assert = (condition, message, evidence = undefined) => {
  if (!condition) {
    const detail = evidence === undefined ? '' : `\n${JSON.stringify(evidence, null, 2)}`;
    throw new Error(`${message}${detail}`);
  }
};

const packageJson = JSON.parse(readFile('komsco-ai-console-plugin/package.json'));
const markdown = readFile('komsco-ai-console-plugin/src/components/AssistantMarkdown.tsx');
const messageContent = readFile('komsco-ai-console-plugin/src/components/AssistantMessageContent.tsx');
const actionPlanButtons = readFile('komsco-ai-console-plugin/src/components/AssistantCreateActionPlanButtons.tsx');
const actionRecords = readFile('komsco-ai-console-plugin/src/components/AssistantActionRecords.tsx');
const actionRecordHelpers = readFile('komsco-ai-console-plugin/src/components/assistant.actionRecords.ts');
const launcher = readFile('komsco-ai-console-plugin/src/components/AssistantLauncher.tsx');
const header = readFile('komsco-ai-console-plugin/src/components/AssistantHeader.tsx');
const historyPanel = readFile('komsco-ai-console-plugin/src/components/AssistantHistoryPanel.tsx');
const progressTimeline = readFile('komsco-ai-console-plugin/src/components/AssistantProgressTimeline.tsx');
const assistantConstants = readFile('komsco-ai-console-plugin/src/components/assistant.constants.tsx');
const evidenceFooter = readFile('komsco-ai-console-plugin/src/components/AssistantEvidenceFooter.tsx');
const toolPlanFooter = readFile('komsco-ai-console-plugin/src/components/AssistantToolPlanFooter.tsx');
const insightRail = readFile('komsco-ai-console-plugin/src/components/AssistantInsightRail.tsx');
const copy = readFile('komsco-ai-console-plugin/src/components/assistant.copy.tsx');
const types = readFile('komsco-ai-console-plugin/src/components/assistant.types.ts');
const gatewayTypes = readFile('komsco-ai-console-plugin/src/services/aiGateway.ts');
const portalApp = readFile('komsco-ai-console-plugin/src/portal/PortalApp.tsx');
const actionCandidatesSource = readFile('komsco-ai-console-plugin/src/components/assistant.actionCandidates.ts');
const actionState = readFile('komsco-ai-console-plugin/src/components/assistant.actionState.ts');
const commandDetection = readFile('komsco-ai-console-plugin/src/components/assistant.commandDetection.ts');
const markdownPrepare = readFile('komsco-ai-console-plugin/src/components/assistant.markdownPrepare.ts');
const css = readFile('komsco-ai-console-plugin/src/components/assistant.css');
const gateway = readFile('komsco-ai-gateway/komsco_ai_gateway/main.py');
const contracts = readFile('komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py');

const deps = packageJson.dependencies || {};
assert(deps['react-markdown'] === '8.0.7', 'React 17-compatible react-markdown must be pinned');
assert(deps['remark-gfm'] === '3.0.1', 'remark-gfm must be pinned for GFM tables/lists');
assert(deps['rehype-sanitize'] === '5.0.1', 'rehype-sanitize must be pinned for safe markdown HTML handling');

assert(markdown.includes('ReactMarkdown'), 'AssistantMarkdown must use react-markdown');
assert(markdown.includes('remarkGfm'), 'AssistantMarkdown must enable GFM');
assert(markdown.includes('rehypeSanitize'), 'AssistantMarkdown must sanitize rendered markdown');
assert(markdown.includes('skipHtml'), 'AssistantMarkdown must skip raw HTML');
assert(markdown.includes('prepareMarkdownContent'), 'AssistantMarkdown must normalize markdown before rendering');
assert(markdownPrepare.includes('isMarkdownHeadingLine'), 'Markdown preparation must reject markdown headings as command lines');
assert(markdownPrepare.includes('repairFencedCommandBlocks'), 'Markdown preparation must repair malformed command fences');
assert(markdownPrepare.includes('wrapStandaloneCommands'), 'Markdown preparation must promote standalone commands into command blocks');
assert(markdownPrepare.includes('stripPublicWebReferenceLines'), 'Markdown preparation must strip public web references from default answers');
assert(markdown.includes('isPublicWebReferenceHref'), 'Markdown links must suppress public web references in closed-network mode');
assert(markdown.includes('data-aiops-command-card'), 'Command cards must expose a stable data attribute');
assert(markdown.includes('data-command-risk'), 'Command cards must expose read-only/approval risk');
assert(markdown.includes('approval-required'), 'Command cards must mark mutation-like commands as approval-required');
assert(markdown.includes('read-only'), 'Command cards must mark safe query commands as read-only');
assert(markdown.includes('navigator.clipboard.writeText'), 'Command/code blocks must keep copy support');
assert(markdown.includes('komsco-ai__code-wrap-toggle'), 'Command/code blocks must keep wrap toggle support');

assert(messageContent.includes('AssistantMarkdown'), 'AssistantMessageContent must route answers through AssistantMarkdown');
assert(messageContent.includes("message.answerContract !== 'legacy_line_parser'"), 'Legacy parser must not remain the default renderer');
assert(types.includes('streaming?: boolean;'), 'Message type must include streaming state');
assert(launcher.includes('streaming: true'), 'Assistant stream start must mark the assistant message as streaming');
assert(launcher.includes('markLastAssistantStreaming(prev, false)'), 'Assistant stream completion must clear streaming state');
assert(launcher.includes('dedupeActionCandidates(matched)'), 'Action candidates must be deduped before rendering buttons');
assert(
  !launcher.includes('hasContent &&\n                          executionModeAllowsActions(executionMode)'),
  'Read-only mode must still compute Action Plan candidates for preview',
);
assert(
  launcher.includes('읽기 전용: 후보만 표시') &&
    launcher.includes('createDisabledReason={createPlanDisabledReason}') &&
    actionPlanButtons.includes('createDisabledReason'),
  'Read-only mode must show Action Plan candidates but lock plan creation',
);
assert(launcher.includes('mergeConversationActionRefs'), 'Action refs must share one merge/dedupe path');
assert(launcher.includes('setConversationHistory((prev) =>') && launcher.includes('actionRefs: mergeConversationActionRefs'), 'Created Action Plans must be reflected in conversation history immediately');
assert(
  launcher.includes('showActionPrepGroup') &&
    launcher.includes('data-aiops-action-prep') &&
    css.includes('.komsco-ai__action-prep') &&
    css.includes('.komsco-ai__action-prep .komsco-ai__create-action-plan-row'),
  'Query plan and Action Plan candidates must be visually grouped when both are present',
);
assert(launcher.includes('podDiagnosticCandidateFromAnswer'), 'Answer-derived Pod diagnostic candidates must be available when the answer names a target Pod');
assert(launcher.includes('targetRequiredDiagnosticCandidateFromAnswer'), 'Execution-enabled targetless answers must render a target-required plan candidate');
assert(launcher.includes("sourceType: 'pod_diagnostic_review'"), 'Target-required and Pod diagnostic candidates must route to pod diagnostic review');
assert(launcher.includes('answerHasConfirmedPodRootCause'), 'Confirmed pod root cause answers must use a separate candidate path');
assert(launcher.includes("sourceType: 'pod_fix_or_rollback_review'"), 'Confirmed pod root cause answers must route to fix/rollback review, not another cause check');
assert(launcher.includes("sourceType: 'deployment_container_command_fix'"), 'Confirmed command-driven CrashLoopBackOff answers must create a real Deployment command fix candidate when safe');
assert(launcher.includes('stableCommandForConfirmedCrashloop'), 'Demo/test CrashLoopBackOff command fixes must provide executable command parameters');
assert(
  launcher.includes('! /pod_diagnostic_review|diagnostic|원인\\s*확인/i.test') ||
    launcher.includes('return !/pod_diagnostic_review|diagnostic|원인\\s*확인/i.test'),
  'Confirmed pod root cause answers must remove stale diagnostic/cause-check candidates',
);
assert(launcher.includes('.filter((candidate) => !candidate.planDisabledReason)'), 'Auto-propose must not submit target-required disabled candidates');
assert(gatewayTypes.includes('planDisabledReason?: string;'), 'Action candidate type must carry a visible disabled reason');
assert(gatewayTypes.includes('parameters?: Record<string, unknown>;'), 'Action candidate type must carry executable parameters');
assert(gatewayTypes.includes('parameters: candidate.parameters ?? {}'), 'Create Action Plan API must forward executable candidate parameters');
assert(types.includes('pinned?: boolean;'), 'Conversation history items must persist pinned state');
assert(actionCandidatesSource.includes('candidateDedupeKey'), 'Action candidate dedupe key must be implemented');
assert(actionCandidatesSource.includes('candidateActionType'), 'Action candidate dedupe must include action type');
assert(actionCandidatesSource.includes('namespace') && actionCandidatesSource.includes('kind') && actionCandidatesSource.includes('name'), 'Action candidate dedupe must include target namespace/kind/name');
assert(commandDetection.includes('isMarkdownHeadingLine'), 'Command detector must expose markdown heading detection');

const pluginRoot = path.join(root, 'komsco-ai-console-plugin');
const originalCwd = process.cwd();
process.chdir(pluginRoot);
require(path.join(pluginRoot, 'node_modules/ts-node/register/transpile-only'));
const detector = require(path.join(pluginRoot, 'src/components/assistant.commandDetection.ts'));
const prepare = require(path.join(pluginRoot, 'src/components/assistant.markdownPrepare.ts'));
const actionCandidates = require(path.join(pluginRoot, 'src/components/assistant.actionCandidates.ts'));
process.chdir(originalCwd);

assert(
  detector.isMarkdownHeadingLine('### 4. 조치 방법 및 추가 확인'),
  'Screenshot heading must be detected as markdown heading',
);
assert(
  !detector.isCommandLikeLine('### 4. 조치 방법 및 추가 확인'),
  'Screenshot heading must not be detected as a command',
);
assert(!detector.isCommandLikeLine('# 조치 방법'), 'Korean markdown heading must not become a command');
assert(
  detector.isCommandLikeLine('oc describe pod aiops-scenario-1-crashloop -n komsco-ai-dev'),
  'oc read command must still be detected as a command',
);

const target = { apiVersion: 'v1', kind: 'Namespace', name: 'komsco-aiops-lab', namespace: 'komsco-aiops-lab' };
const dedupedCandidates = actionCandidates.dedupeActionCandidates([
  {
    id: 'chat-namespace-cleanup-komsco-aiops-lab',
    sourceType: 'namespace_cleanup_review',
    target,
    title: 'Namespace 정리 검토',
    priority: 40,
  },
  {
    evidenceRefs: [{ type: 'event' }],
    id: 'gateway-namespace-cleanup-komsco-aiops-lab',
    sourceType: 'namespace_cleanup_review',
    target,
    title: 'Namespace 정리 검토',
    priority: 40,
  },
]);
assert(dedupedCandidates.length === 1, 'Duplicate action candidates for the same action target must collapse', dedupedCandidates);
assert(
  dedupedCandidates[0].id === 'gateway-namespace-cleanup-komsco-aiops-lab',
  'More specific Gateway action candidate must win over synthetic answer-derived candidate',
  dedupedCandidates,
);
const differentActionCandidates = actionCandidates.dedupeActionCandidates([
  {
    id: 'chat-namespace-cleanup-komsco-aiops-lab',
    sourceType: 'namespace_cleanup_review',
    target,
    title: 'Namespace 정리 검토',
  },
  {
    id: 'chat-test-pod-create-komsco-aiops-lab',
    sourceType: 'test_pod_create_review',
    target,
    title: '테스트 Pod 3개 생성',
  },
]);
assert(
  differentActionCandidates.length === 2,
  'Different action types on the same target must remain separate candidates',
  differentActionCandidates,
);

const repairedScreenshotMarkdown = prepare.prepareMarkdownContent(
  ['### 원인 후보', '- 원인 설명', '```bash', '### 4. 조치 방법 및 추가 확인', '```', '1. 로그 분석'].join('\n'),
  false,
);
assert(
  !repairedScreenshotMarkdown.includes('```bash\n### 4. 조치 방법 및 추가 확인'),
  'Screenshot heading must be repaired out of a bash code fence',
  repairedScreenshotMarkdown,
);
assert(
  repairedScreenshotMarkdown.includes('### 4. 조치 방법 및 추가 확인'),
  'Screenshot heading must remain available as markdown heading after repair',
  repairedScreenshotMarkdown,
);

const closedNetworkMarkdown = prepare.prepareMarkdownContent(
  [
    '### 확인 결과',
    'Diagnosis cluster: https://github.com/openshift/runbooks/blob/master/alerts/cluster.md',
    'OpenShift docs: https://docs.openshift.com/container-platform/4.20/support/index.html',
    '- API 서버: https://api.ocp.cywell.server:6443',
    '```bash',
    'curl https://github.com/openshift/runbooks/healthz',
    '```',
  ].join('\n'),
  false,
);
assert(
  !closedNetworkMarkdown.includes('github.com/openshift/runbooks/blob'),
  'Default answer markdown must remove public GitHub runbook URLs',
  closedNetworkMarkdown,
);
assert(
  !closedNetworkMarkdown.includes('docs.openshift.com/container-platform'),
  'Default answer markdown must remove public OpenShift documentation URLs',
  closedNetworkMarkdown,
);
assert(
  closedNetworkMarkdown.includes('https://api.ocp.cywell.server:6443'),
  'Closed-network markdown filtering must keep cluster/internal API URLs',
  closedNetworkMarkdown,
);
assert(
  closedNetworkMarkdown.includes('curl https://github.com/openshift/runbooks/healthz'),
  'Closed-network markdown filtering must not mutate command contents',
  closedNetworkMarkdown,
);
assert(
  messageContent.includes('prepareMarkdownContent(stripDefaultEvidenceAppendix(content), false)'),
  'Runbook section parser must normalize malformed fences before splitting sections',
);
assert(
  messageContent.includes('조치 방법 및 추가 확인'),
  'Runbook section parser must recognize the screenshot action heading',
);
assert(
  messageContent.includes("sectionId === 'followup'") &&
    messageContent.includes('renderFollowupLines') &&
    messageContent.includes('normalizeFollowupLine'),
  'Runbook follow-up section must use a controlled line renderer instead of raw markdown table layout',
);
assert(
  messageContent.includes("/^-{3,}$/.test(trimmed)"),
  'Runbook follow-up section must drop markdown horizontal-rule separators such as ---',
);
assert(
  css.includes('.komsco-ai__runbook-followup-list') &&
    css.includes('.komsco-ai__runbook-section.is-followup .komsco-ai__formatted-code'),
  'Runbook follow-up section must have dedicated readable list styling',
);

const markdownFontMatch = css.match(/\.komsco-ai__markdown\s*\{[\s\S]*?font-size:\s*([0-9.]+)px/);
assert(markdownFontMatch, 'Markdown body font-size rule must exist');
assert(Number(markdownFontMatch[1]) >= 14, 'Markdown body font must be at least 14px', {
  fontSize: markdownFontMatch[1],
});
assert(css.includes('.komsco-ai__command-card'), 'Command card CSS must exist');
assert(css.includes('.komsco-ai__command-risk.is-read-only'), 'Read-only command risk badge CSS must exist');
assert(css.includes('.komsco-ai__command-risk.is-approval-required'), 'Approval-required command risk badge CSS must exist');
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-title'), 'Action Plan candidate cards must render a concrete plan title');
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-brief'), 'Action Plan candidate cards must keep the default row compact');
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-details'), 'Action Plan candidate details must be collapsible instead of flooding the chat');
assert(
  actionPlanButtons.includes('CoolSettingsIcon') &&
    actionPlanButtons.includes('komsco-ai__create-action-plan-glyph'),
  'Expanded Action Plan candidate rows must keep a relevant settings/gear icon',
);
assert(
  !actionPlanButtons.includes('<CoolSettingsIcon className="komsco-ai__create-action-plan-glyph" />\n              <strong>'),
  'Grouped Action Plan summary must not repeat the gear icon before the candidate count',
);
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-summary-priority'), 'Grouped Action Plan summary must visually separate the primary candidate line');
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-summary-head'), 'Grouped Action Plan candidates must have a structured compact summary head');
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-card-head'), 'Expanded Action Plan candidate rows must keep title grouped');
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-property'), 'Expanded Action Plan candidate rows must render reference-style label/value properties');
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-mode-note'), 'Read-only Action Plan candidate explanation must render once at group level');
assert(
  actionPlanButtons.includes("'상태:'") &&
    actionPlanButtons.includes("'대상:'") &&
    actionPlanButtons.includes("'조치:'") &&
    !css.includes('.komsco-ai__create-action-plan-property strong::after'),
  'Action Plan candidate label/value rows must use direct inline colon labels instead of spaced pseudo separators',
);
assert(actionPlanButtons.includes('로그/describe/Event 확인 계획 생성'), 'Pod diagnostic candidate summary must describe plan creation, not immediate command execution');
assert(actionPlanButtons.includes('승인 후 읽기 조회만 실행'), 'Pod diagnostic approval summary must clarify approval-gated read-only execution');
assert(actionPlanButtons.includes('수정/롤백 검토 계획 생성'), 'Pod fix/rollback candidates must not be relabeled as log/describe cause checks');
assert(actionPlanButtons.includes('Deployment command 수정 계획 생성'), 'Deployment command fix candidates must show the actual mutation plan');
assert(actionPlanButtons.includes('승인 후 Deployment template patch 실행'), 'Deployment command fix candidates must clarify that approval leads to a template patch');
assert(actionPlanButtons.includes('원인 확인 완료'), 'Pod fix/rollback candidates must show that root cause is already confirmed');
assert(actionPlanButtons.includes('승인 전 클러스터 변경 없음, 수정안만 검토'), 'Pod fix/rollback candidate approval text must clarify no mutation before approval');
assert(actionPlanButtons.includes('대상') && actionPlanButtons.includes('문제') && actionPlanButtons.includes('조치') && actionPlanButtons.includes('승인 조건'), 'Action Plan candidate cards must show target/problem/action/approval fields');
assert(!actionPlanButtons.includes('검토 대기 조치 후보'), 'Action Plan card title must not be the generic duplicate-looking label');
assert(!/>Action Plan<\/span>/.test(actionPlanButtons), 'Action Plan candidate card heading must not be Action Plan alone');
assert(actionPlanButtons.includes('data-aiops-action-candidate-count'), 'Action Plan candidate group must expose candidate count for regression checks');
assert(actionPlanButtons.includes('data-aiops-action-candidates-expanded'), 'Action Plan candidate group must expose collapsed/expanded state');
assert(actionPlanButtons.includes('data-aiops-action-candidate-feedback'), 'Action Plan candidate rows must expose create feedback state');
assert(actionPlanButtons.includes('actionFeedback'), 'Action Plan candidate rows must render per-button create feedback');
assert(actionPlanButtons.includes('planDisabledReason'), 'Action Plan candidate cards must show target-required disabled state');
assert(actionPlanButtons.includes('대상 확인 필요'), 'Target-required Action Plan card must use a clear disabled button label');
assert(actionRecords.includes('hasActionMessage'), 'Action errors/notices must stay visible even before action records exist');
assert(
  actionRecords.includes('!hasActionMessage'),
  'Action records must not return null when create-plan error/notice exists',
);
assert(launcher.includes('setActionCandidateFeedback'), 'Create-plan flow must set per-candidate feedback');
assert(launcher.includes('pendingActionCandidatesForRefs'), 'Created Action Plan refs must hide only the created candidate, not every candidate on the same target');
assert(launcher.includes('candidateId: ref.candidateId ?? existing.candidateId'), 'Action refs must preserve candidateId across plan/approval/execution lifecycle upgrades');
assert(launcher.includes('candidateId: candidate.id'), 'Candidate-created Action Plan refs must carry the originating candidate id');
assert(
  launcher.includes('pendingActionCandidates.length > 0') &&
    launcher.includes('candidates={pendingActionCandidates}'),
  'Action Plan candidate buttons must keep remaining candidates visible after one candidate is created',
);
assert(
  launcher.includes('Action Plan을 생성했습니다. 아래 카드에서 승인 또는 실행을 이어갈 수 있습니다.'),
  'Create-plan success must tell the user what changed and where to continue',
);
assert(css.includes('.komsco-ai__create-action-plan-feedback'), 'Action Plan create feedback CSS must exist');
assert(actionPlanButtons.includes('komsco-ai__create-action-plan-disabled-reason'), 'Target-required Action Plan card must render the reason visibly');
assert(actionPlanButtons.includes('Action Plan 후보 ${candidates.length}건'), 'Multiple Action Plan candidates must render a collapsed summary count');
assert(actionPlanButtons.includes('우선 후보:'), 'Collapsed Action Plan candidate summary must show the primary candidate purpose');
assert(actionPlanButtons.includes('펼쳐보기'), 'Collapsed Action Plan candidate summary must expose an expand control');
assert(actionPlanButtons.includes('hidden={multiple && !expanded}'), 'Multiple Action Plan candidate cards must be hidden by default until expanded');
assert(actionRecords.includes('ActionRecordAuditDetail'), 'Action record audit JSON detail must be a shared component');
assert(actionRecords.includes('komsco-ai__answer-action-card') && actionRecords.includes('<ActionRecordAuditDetail language={language} record={record} />'), 'Answer Action Plan cards must keep audit JSON detail');
assert(css.includes('.komsco-ai__create-action-plan-summary'), 'Action Plan candidate group summary CSS must exist');
assert(css.includes('.komsco-ai__create-action-plan-list[hidden]'), 'Hidden Action Plan candidate list CSS must exist');
const actionPlanListCss = css.match(
  /\.komsco-ai__create-action-plan--grouped\.is-expanded \.komsco-ai__create-action-plan-list\s*\{[\s\S]*?\n\}/,
)?.[0] || '';
assert(
  actionPlanListCss.includes('overflow-y: auto'),
  'Expanded Action Plan candidate groups must scroll internally instead of pushing the composer',
);
assert(
  !actionPlanListCss.includes('overscroll-behavior: contain'),
  'Expanded Action Plan candidate group wheel events must chain back to the chat scroll container',
);
assert(css.includes('v0.2.9 layout lock'), 'Layout lock CSS marker must exist for composer/history regression checks');
assert(css.includes('grid-template-rows: minmax(0, 1fr) auto !important'), 'Chat column must reserve a fixed composer row');
assert(css.includes('padding: 6px 8px 8px !important'), 'Composer bottom padding must stay capped at 8px');
assert(css.includes('opening history must not change the main assistant frame height'), 'History-open height lock marker must exist');
assert(launcher.includes("'--komsco-panel-height'"), 'Resizable assistant height must be exported as a CSS variable');
assert(
  css.includes('.komsco-ai__surface.komsco-ai__surface--history-open:not(.komsco-ai__surface--fullscreen)') &&
    css.includes('> .komsco-ai__history-sidebar') &&
    css.includes('> .komsco-ai__panel'),
  'History-open surface, sidebar, and panel must share one constrained grid row',
);
assert(
  css.includes('height: var(--komsco-panel-height, min(852px, calc(100dvh - 32px))) !important'),
  'History-open surface must reuse the normal assistant frame height instead of growing to the viewport',
);
assert(
  !css.includes('var(--komsco-history-height, calc(100dvh - 16px))'),
  'History-open surface must not use history drawer height as the main panel height',
);
assert(css.includes('grid-template-areas') && css.includes('"history-search"') && css.includes('"history-user"'), 'History sidebar must reserve search and fixed user footer grid areas');
assert(css.includes('grid-area: history-list') && css.includes('grid-area: history-user'), 'History list and user footer must occupy separate grid areas');
assert(css.includes('max-height: calc(100dvh - var(--komsco-history-top'), 'History sidebar must cap height to the visible viewport');
assert(css.includes('overscroll-behavior: contain'), 'History list scroll must be contained so the footer is not pushed away');
assert(historyPanel.includes('SquarePen'), 'History new chat control must use a compose icon, not a plain plus');
assert(header.includes('PanelLeft') && header.includes('komsco-ai__sidebar-toggle'), 'Main header must own the sidebar toggle');
assert(!historyPanel.includes('PanelLeft') && !historyPanel.includes('onCloseSidebar'), 'History rail must not duplicate the main sidebar toggle');
assert(historyPanel.includes('komsco-ai__history-tabs') && historyPanel.includes('role="tablist"'), 'History/upload switching must use a text segmented control below the toolbar');
assert(!historyPanel.includes('komsco-ai__history-action-group'), 'History toolbar must not duplicate chat/upload switching with extra icons');
assert(!css.includes('komsco-ai__history-action-group'), 'Removed history icon-switch CSS must not linger');
assert(historyPanel.includes('type="search"'), 'History panel must include conversation search');
assert(historyPanel.includes('toggleConversationPinned'), 'History panel must expose pin/unpin actions');
assert(historyPanel.includes('sortConversationActionRefs') && historyPanel.includes('ACTION_STAGE_RANK'), 'History action refs must be sorted by lifecycle stage and recency');
assert(historyPanel.includes('actionRef.reviewOnly') && historyPanel.includes("'기록'"), 'History action refs must label review-only execution as a record, not ordinary execution');
assert(historyPanel.includes('komsco-ai__history-item-pinned-label'), 'Pinned conversations must show a pinned state marker');
assert(!historyPanel.includes('komsco-ai__history-item-pin${'), 'Unpinned history rows must not show a persistent pin icon');
assert(historyPanel.includes('visibleConversationHistory'), 'History panel must sort/filter the rendered conversation list');
assert(copy.includes('searchHistory') && copy.includes('pinConversation') && copy.includes('unpinConversation'), 'History search and pin labels must be localized');
assert(css.includes('.komsco-ai__history-search'), 'History search CSS must exist');
assert(css.includes('.komsco-ai__history-tabs') && css.includes('.komsco-ai__history-tab--active'), 'History segmented tab CSS must exist');
assert(css.includes('.komsco-ai__history-item-pinned-label'), 'Pinned state marker CSS must exist');

assert(launcher.includes('최종 답변의 확인 결과를 정리했습니다.'), 'RCA context completion copy must be product-facing');
assert(!launcher.includes('최종 답변에 사용한 근거를 연결했습니다.'), 'RCA context completion copy must not expose internal connection wording');
assert(!progressTimeline.includes('답변 근거 연결 완료'), 'Progress timeline must not expose old evidence-link wording');
assert(!progressTimeline.includes('AI 응답 대기') && !launcher.includes('AI 응답 대기'), 'Progress UI must not use generic AI wait wording');
assert(!assistantConstants.includes('화면 표시 준비'), 'Progress wait phases must not end on generic display-prep wording');
assert(progressTimeline.includes('모델에 확인 결과 전달'), 'Progress UI must translate model handoff into an operator-facing stage');
assert(progressTimeline.includes('답변이 도착하는 대로 작성하고 있습니다.'), 'Answer streaming must be framed as answer writing, not screen display');
assert(assistantConstants.includes('모델 답변 생성') && assistantConstants.includes('답변 초안 생성'), 'Response wait phases must expose realistic model/answer stages');
assert(!css.includes('komsco-ai-pulse-ring'), 'Progress animation must not use radar/pulse-ring animation');
assert(!css.includes('flow-pulse--running::after'), 'Progress summary must not use expanding radar-ring pseudo elements');
assert(!css.includes('progress-status--running::after'), 'Progress detail must not use expanding radar-ring pseudo elements');
assert(!css.includes('komsco-ai-header-bottom-scan') && !css.includes('komsco-ai-header-bottom-glow'), 'Responding header must not use scanner/glow waiting animations');
assert(launcher.includes('return `${formatToolTitle(event.name)} 시작`;'), 'Tool-call progress fallback must use the actual tool label instead of generic tool-call wording');
assert(css.includes('@media (prefers-reduced-motion: reduce)'), 'Progress animation must respect reduced-motion preferences');
assert(
  /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*\.komsco-ai__progress-status--running::before[\s\S]*animation:\s*none/.test(css),
  'Reduced-motion CSS must disable the progress detail typing animation',
);
assert(
  /@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*\.komsco-ai__flow-pulse--running::before[\s\S]*animation:\s*none/.test(css),
  'Reduced-motion CSS must disable the progress summary typing animation',
);
assert(evidenceFooter.includes("isKo ? '확인 결과' : 'Evidence'"), 'Evidence footer title must use product-facing Korean copy');
assert(
  evidenceFooter.includes('komsco-ai__footer-inline-summary') &&
    evidenceFooter.includes('komsco-ai__footer-detail-toggle') &&
    toolPlanFooter.includes('komsco-ai__footer-inline-summary') &&
    toolPlanFooter.includes('komsco-ai__footer-detail-toggle'),
  'Evidence and query-plan details must be exposed as compact inline footer toggles',
);
assert(
  toolPlanFooter.includes('executionMode: AiopsExecutionMode') &&
    toolPlanFooter.includes("executionMode === 'read-only'") &&
    launcher.includes('executionMode={executionMode}'),
  'Query-plan footer must hide read-only policy badges when the current execution mode allows actions',
);
assert(!evidenceFooter.includes('확인 결과 상세'), 'Evidence detail toggle must not consume a second visible line');
assert(!toolPlanFooter.includes('조회 계획 상세보기'), 'Tool-plan detail toggle must not consume a second visible line');
assert(!evidenceFooter.includes('근거 상세보기'), 'Evidence footer must not use legal-toned Korean wording');
assert(actionRecords.includes("label: isKo ? '확인 결과' : 'Evidence'"), 'Action Plan card must label evidence as 확인 결과 in Korean');
assert(!actionRecords.includes('근거 기반 조치 후보'), 'Action Plan card must not use legal-toned evidence wording');
assert(!actionRecords.includes('Gateway 기록'), 'Action Plan fallback copy must not expose Gateway internals');
assert(!actionRecords.includes('조치 흐름'), 'Action Plan fallback copy must not use abstract action-flow wording');
assert(actionRecords.includes('Action Plan 상태를 확인 중입니다'), 'Action Plan unresolved state must use plain product-facing copy');
assert(actionRecords.includes('진행한 Action Plan'), 'Fallback Action Plan refs must show a plain status title');
assert(actionRecords.includes('사용자가 진행한 Action Plan 상태'), 'Fallback Action Plan refs must explain that the card is a status summary');
assert(actionRecords.includes('기록 원문'), 'Action record raw JSON detail must use plain record wording');
assert(!actionRecords.includes('감사 상세'), 'Action records must not expose audit jargon in the default UI');
assert(actionRecords.includes('<details') && actionRecords.includes('data-action-plan-decision-collapsed'), 'Action Plan approval decision rows must be collapsed by default');
assert(actionRecords.includes('상세 판단 항목'), 'Action Plan approval card must expose a compact decision-detail toggle');
assert(css.includes('.komsco-ai__action-plan-decision-detail > summary'), 'Collapsed Action Plan decision detail summary CSS must exist');
assert(actionRecordHelpers.includes('review_recorded'), 'Review-only Action Plan records must have a distinct review_recorded phase label');
assert(actionRecordHelpers.includes('검토 기록 완료'), 'Review-only Action Plan records must not be labeled as ordinary execution completion');
assert(actionRecordHelpers.includes('reviewOnly: isReviewOnlyActionRecord'), 'Conversation action refs must persist review-only state for history rendering');
assert(actionState.includes('검토 기록'), 'Review-only Action Plan approval flow must render a record-review action label');
assert(!actionState.includes('Gateway 실행 기능 미구성'), 'Execute mode must not pre-block Action Plan buttons because the executor is not configured');
assert(actionState.includes('modeDisabledReason = !executionModeAllowsActions(executionMode)'), 'Action Plan UI gating must be based on selected execution mode, not mutation backend readiness');
assert(!launcher.includes('위험도가 있는 조치는 요청자 본인이 승인할 수 없거나'), 'Generic 409 handling must not falsely label review-only plans as risky');
assert(launcher.includes('이 승인은 이미 실행 또는 검토 기록에 사용됐습니다'), 'Action errors must explain already-recorded review approvals distinctly');
assert(launcher.includes('현재 화면의 계획/승인 상태와 서버 기록이 맞지 않습니다'), 'Generic conflict errors must point to stale UI/server state, not risk');
assert(gatewayTypes.includes('Approval decision has already been used for execution'), 'Gateway client must translate already-used approval errors');
assert(gatewayTypes.includes('Execution request is stale for this sealed plan'), 'Gateway client must translate stale execution errors');
assert(gatewayTypes.includes('actionExecutionRecordFromErrorPayload'), 'Execute API client must recover mutation-disabled ExecutionRecord payloads');
assert(gatewayTypes.includes('response.status === 403') && gatewayTypes.includes("kind: 'ExecutionRecord'"), 'Execute API client must render server-recorded execution outcomes even when HTTP status is 403');
assert(insightRail.includes("'확인 결과'"), 'Insight rail must use product-facing answer context copy');
assert(!insightRail.includes('답변 근거'), 'Insight rail must not expose old answer evidence wording');
assert(gateway.includes('코드블록 안에는 실행 가능한 명령만'), 'Gateway prompt must forbid prose inside code blocks');
assert(gateway.includes('Tip`, 주의사항, 확인 항목, 제목, 목록 문장은 코드블록 밖'), 'Gateway prompt must keep tips/headings/lists outside code blocks');
assert(gateway.includes('현재 판단`, `원인 후보`, `확인 결과`, `조치 방법`, `추가 확인`'), 'Gateway prompt must define v0.2.9 answer order');
assert(gateway.includes('CrashLoopBackOff는 컨테이너가 시작된 뒤 곧바로 종료되고'), 'CrashLoopBackOff fallback must start with a plain definition before RCA sections');
assert(gateway.includes('첫 문장에 "컨테이너가 시작 후 곧바로 종료되고 Kubernetes가 재시작을 반복하다가 대기 시간을 늘리는 상태"'), 'Gateway prompt must require a first-sentence CrashLoopBackOff definition');
assert(gateway.includes('"set_deployment_container_command"'), 'Gateway action registry must include Deployment command mutation');
assert(gateway.includes('"deployment_container_command_fix_v1"'), 'Gateway runbook registry must include Deployment command fix runbook');
assert(gateway.includes('deployment_container_command_matches'), 'Gateway postcondition must verify Deployment command mutation');
assert(gateway.includes('공용 웹 URL은 기본 답변에 출력하지 마세요'), 'Gateway prompt must forbid public web URLs in default closed-network answers');
assert(contracts.includes('"확인 결과"'), 'RCA contract must use 확인 결과');
assert(contracts.includes('"조치 방법"'), 'RCA contract must use 조치 방법');
assert(!contracts.includes('"확인한 근거"'), 'RCA contract must not use old 확인한 근거 wording');
assert(!contracts.includes('"확인한 증적"'), 'RCA contract must not use old 확인한 증적 wording');
assert(portalApp.includes('확인 결과:'), 'Portal prompt must use 확인 결과 for attached context');
assert(portalApp.includes('확인 결과, 원인 후보, Action Plan, 검증/롤백, 추가 확인'), 'Portal prompt must use product-facing answer order');
assert(!portalApp.includes('확인한 근거'), 'Portal prompt must not use old 확인한 근거 wording');
assert(!portalApp.includes('근거 상세보기'), 'Portal prompt must not use old evidence detail wording');

const screenshotRegressionTerms = [
  '```bash\\nPod의 상태 정보',
  '```bash\\n현재 실행 중인 컨테이너는',
  '코드블록 안에 다시 ```bash',
];
const sourceBundle = [markdown, messageContent].join('\n');
const leakedTerms = screenshotRegressionTerms.filter((term) => sourceBundle.includes(term));
assert(leakedTerms.length === 0, 'Screenshot markdown regression fixtures must not be hard-coded as broken output', leakedTerms);

console.log('v0.2.9 chatbot markdown UX verifier PASS');
