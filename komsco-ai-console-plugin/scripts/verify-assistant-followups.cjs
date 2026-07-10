#!/usr/bin/env node

const assert = require('assert');
const fs = require('fs');
const path = require('path');
const {
  cleanAssistantFollowupPrompt,
  parseAssistantFollowupBlock,
  rewriteAssistantFollowupQuery,
} = require('../src/components/assistant.followups');

const root = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

const parsed = parseAssistantFollowupBlock(`## 확인 결과

문제 Pod 2건을 확인했습니다.

### 다음으로 무엇을 확인할까요?

1. **로그 확인**: \`gpu-test-kugnus\`의 최근 로그를 확인할까요?
2. 이벤트와 재시작 원인을 함께 확인할까요?
3. 승인 가능한 Action Plan 초안을 만들까요?

---

후속 기록`);

assert.ok(parsed, 'exact Korean heading should parse');
assert.strictEqual(parsed.options.length, 3, 'only three choices should be exposed');
assert.ok(parsed.before.includes('문제 Pod 2건'), 'markdown before the choices must be preserved');
assert.ok(parsed.after.startsWith('---'), 'markdown after the choices must be preserved');
assert.strictEqual(
  parsed.options[0].prompt,
  '로그 확인: gpu-test-kugnus의 최근 로그를 확인할까요?',
  'choice markdown should be cleaned without shortening the sentence',
);

const duplicatedMarkdownHeading = parseAssistantFollowupBlock(`현재 판단입니다.

### ### 다음으로 무엇을 확인할까요?
1. Pod 로그 상세 확인
2. 최근 종료 원인과 이벤트 확인
3. 노드 Pressure 상태 확인`);
assert.ok(
  duplicatedMarkdownHeading,
  'a duplicated Markdown marker must still become interactive follow-up choices',
);
assert.strictEqual(duplicatedMarkdownHeading.options.length, 3);

const english = parseAssistantFollowupBlock(`Answer first.

### What would you like to check next?
1. Check the affected Pod events?
2. Compare the previous container logs?`);
assert.ok(english, 'exact English heading should parse');
assert.strictEqual(english.options.length, 2);

const legacy = parseAssistantFollowupBlock(`Answer first.

**다음 단계로 무엇을 도와드릴까요?**:
1. 첫 번째 대상을 확인할까요?
2. 두 번째 대상을 확인할까요?`);
assert.ok(legacy, 'legacy follow-up heading should remain compatible');

assert.strictEqual(
  parseAssistantFollowupBlock('1. 요청 확인\n2. 권한 확인\n3. 조회 실행'),
  null,
  'ordinary ordered lists must remain markdown',
);
assert.strictEqual(
  parseAssistantFollowupBlock('### 추가 확인\n1. Event 확인\n2. 로그 확인'),
  null,
  'Additional Checks must remain markdown',
);
assert.strictEqual(
  parseAssistantFollowupBlock('```text\n### 다음으로 무엇을 확인할까요?\n1. 예시\n```'),
  null,
  'numbered content inside code fences must remain code',
);
assert.strictEqual(
  parseAssistantFollowupBlock('~~~text\n### 다음으로 무엇을 확인할까요?\n1. 예시\n~~~'),
  null,
  'numbered content inside tilde code fences must remain code',
);
assert.strictEqual(
  cleanAssistantFollowupPrompt('**원인 분석**: `Pod` 이벤트를 확인할까요?'),
  '원인 분석: Pod 이벤트를 확인할까요?',
);
assert.strictEqual(
  rewriteAssistantFollowupQuery(
    '`gpu-test-kugnus`의 CrashLoopBackOff Pod 로그를 상세히 확인하시겠습니까?',
  ),
  'gpu-test-kugnus의 CrashLoopBackOff Pod 로그를 상세히 확인해줘',
);
assert.strictEqual(
  rewriteAssistantFollowupQuery('Critical 알림 리스트를 표 형태로 정리해 드릴까요?'),
  'Critical 알림 리스트를 표 형태로 정리해줘',
);
assert.strictEqual(
  rewriteAssistantFollowupQuery('승인 가능한 Action Plan 초안을 만들까요?'),
  '승인 가능한 Action Plan 초안을 만들어줘',
);

const component = read('src/components/AssistantFollowupChoices.tsx');
const launcher = read('src/components/AssistantLauncher.tsx');
const tableWrap = read('src/components/AssistantTableWrap.tsx');
const css = read('src/components/assistant.followups.css');
const legacyCss = read('src/components/assistant.css');

assert.ok(component.includes('<button'), 'each number toggle must be a native button');
assert.ok(component.includes('aria-label={selectionLabel}'));
assert.ok(component.includes('rewriteAssistantFollowupQuery(option.prompt)'));
assert.ok(component.includes('selectionLockRef.current'), 'rapid repeat clicks must be locked');
assert.ok(component.includes('if (!accepted)'), 'rejected sends must release selection state');
assert.ok(component.includes('parseAssistantFollowupBlock(message.content)'));
assert.ok(
  launcher.includes('enabled={'),
  'only the completed latest message should be interactive',
);
assert.ok(
  launcher.includes('visible={isLatestAssistantMessage && hasContent}'),
  'the latest streaming answer should replace raw follow-up markdown as soon as choices arrive',
);
assert.ok(component.includes('disabled={!enabled}'));
assert.ok(
  !launcher.includes('komsco-ai__followup-prompts'),
  'detached duplicate pills must be removed',
);
assert.ok(!legacyCss.includes('.komsco-ai__followup-prompt {'), 'legacy pill CSS must be removed');
assert.ok(css.includes('grid-template-columns: 26px minmax(0, 1fr)'));
assert.ok(css.includes('border-radius: 6px'));
assert.ok(css.includes('font-size: 12.5px'));
assert.ok(css.includes('font-size: 13px'));
assert.ok(css.includes('font-size: 11px'));
assert.ok(css.includes('white-space: normal'));
assert.ok(css.includes('overflow-wrap: anywhere'));
assert.ok(!css.includes('box-shadow: 0 '), 'choice rows must not use pill shadows');
assert.ok(
  /<button[\s\S]{0,200}className="komsco-ai__followup-choice"/.test(component),
  'the full numbered sentence row must be a native button',
);
assert.ok(
  tableWrap.includes('assistant-table-content-${shortTextHash(tableSignature)}'),
  'streaming table remounts must restore horizontal scroll by stable content identity',
);
assert.ok(
  tableWrap.includes('tableScrollPositions.set(effectiveScrollKey, nextScrollLeft)'),
  'horizontal scroll changes must be saved immediately',
);

console.log('assistant follow-up verifier PASS');
