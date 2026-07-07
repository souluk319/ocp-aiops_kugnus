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
const launcher = readFile('komsco-ai-console-plugin/src/components/AssistantLauncher.tsx');
const types = readFile('komsco-ai-console-plugin/src/components/assistant.types.ts');
const actionCandidatesSource = readFile('komsco-ai-console-plugin/src/components/assistant.actionCandidates.ts');
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
assert(
  messageContent.includes('prepareMarkdownContent(stripDefaultEvidenceAppendix(content), false)'),
  'Runbook section parser must normalize malformed fences before splitting sections',
);
assert(
  messageContent.includes('조치 방법 및 추가 확인'),
  'Runbook section parser must recognize the screenshot action heading',
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
assert(actionPlanButtons.includes('대상') && actionPlanButtons.includes('문제') && actionPlanButtons.includes('조치') && actionPlanButtons.includes('승인 조건'), 'Action Plan candidate cards must show target/problem/action/approval fields');
assert(!actionPlanButtons.includes('검토 대기 조치 후보'), 'Action Plan card title must not be the generic duplicate-looking label');
assert(!/>Action Plan<\/span>/.test(actionPlanButtons), 'Action Plan candidate card heading must not be Action Plan alone');
assert(actionPlanButtons.includes('data-aiops-action-candidate-count'), 'Action Plan candidate group must expose candidate count for regression checks');
assert(actionPlanButtons.includes('data-aiops-action-candidates-expanded'), 'Action Plan candidate group must expose collapsed/expanded state');
assert(actionPlanButtons.includes('Action Plan 후보 ${candidates.length}건'), 'Multiple Action Plan candidates must render a collapsed summary count');
assert(actionPlanButtons.includes('우선 후보:'), 'Collapsed Action Plan candidate summary must show the primary candidate purpose');
assert(actionPlanButtons.includes('펼쳐보기'), 'Collapsed Action Plan candidate summary must expose an expand control');
assert(actionPlanButtons.includes('hidden={multiple && !expanded}'), 'Multiple Action Plan candidate cards must be hidden by default until expanded');
assert(css.includes('.komsco-ai__create-action-plan-summary'), 'Action Plan candidate group summary CSS must exist');
assert(css.includes('.komsco-ai__create-action-plan-list[hidden]'), 'Hidden Action Plan candidate list CSS must exist');
assert(
  css.includes('.komsco-ai__create-action-plan--grouped.is-expanded .komsco-ai__create-action-plan-list') &&
    css.includes('overflow-y: auto'),
  'Expanded Action Plan candidate groups must scroll internally instead of pushing the composer',
);
assert(css.includes('v0.2.9 layout lock'), 'Layout lock CSS marker must exist for composer/history regression checks');
assert(css.includes('grid-template-rows: minmax(0, 1fr) auto !important'), 'Chat column must reserve a fixed composer row');
assert(css.includes('padding: 6px 8px 8px !important'), 'Composer bottom padding must stay capped at 8px');
assert(css.includes('grid-template-areas') && css.includes('"history-user"'), 'History sidebar must reserve a fixed user footer grid area');
assert(css.includes('grid-area: history-list') && css.includes('grid-area: history-user'), 'History list and user footer must occupy separate grid areas');
assert(css.includes('max-height: calc(100dvh - var(--komsco-history-top'), 'History sidebar must cap height to the visible viewport');
assert(css.includes('overscroll-behavior: contain'), 'History list scroll must be contained so the footer is not pushed away');

assert(gateway.includes('코드블록 안에는 실행 가능한 명령만'), 'Gateway prompt must forbid prose inside code blocks');
assert(gateway.includes('Tip`, 주의사항, 확인 항목, 제목, 목록 문장은 코드블록 밖'), 'Gateway prompt must keep tips/headings/lists outside code blocks');
assert(gateway.includes('현재 판단`, `원인 후보`, `확인한 근거`, `조치 방법`, `추가 확인`'), 'Gateway prompt must define v0.2.9 answer order');
assert(contracts.includes('"확인한 근거"'), 'RCA contract must use 확인한 근거');
assert(contracts.includes('"조치 방법"'), 'RCA contract must use 조치 방법');
assert(!contracts.includes('"확인한 증적"'), 'RCA contract must not use old 확인한 증적 wording');

const screenshotRegressionTerms = [
  '```bash\\nPod의 상태 정보',
  '```bash\\n현재 실행 중인 컨테이너는',
  '코드블록 안에 다시 ```bash',
];
const sourceBundle = [markdown, messageContent].join('\n');
const leakedTerms = screenshotRegressionTerms.filter((term) => sourceBundle.includes(term));
assert(leakedTerms.length === 0, 'Screenshot markdown regression fixtures must not be hard-coded as broken output', leakedTerms);

console.log('v0.2.9 chatbot markdown UX verifier PASS');
