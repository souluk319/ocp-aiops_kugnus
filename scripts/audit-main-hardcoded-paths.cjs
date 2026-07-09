#!/usr/bin/env node

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const sourceRel = 'komsco-ai-gateway/komsco_ai_gateway/main.py';
const defaultOutput = '.tmp-kugnus-demo/main-hardcoding-audit.json';
const defaultMarkdown = '.tmp-kugnus-demo/main-hardcoding-audit.md';

const args = process.argv.slice(2);

const getArg = (name, fallback) => {
  const index = args.indexOf(name);
  if (index >= 0 && args[index + 1]) {
    return args[index + 1];
  }
  const inline = args.find((arg) => arg.startsWith(`${name}=`));
  return inline ? inline.slice(name.length + 1) : fallback;
};

const outputPath = getArg('--output', defaultOutput);
const markdownPath = getArg('--markdown', defaultMarkdown);

const abs = (target) => path.resolve(root, target);
const rel = (target) => path.relative(root, path.resolve(root, target)).replace(/\\/g, '/');
const readText = (target) => fs.readFileSync(abs(target), 'utf8');

const runGit = (gitArgs) => {
  try {
    return execFileSync('git', gitArgs, {
      cwd: root,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  } catch (_error) {
    return '';
  }
};

const source = readText(sourceRel);
const lines = source.split(/\r?\n/);

const branch = runGit(['branch', '--show-current']);
const head = runGit(['rev-parse', '--short', 'HEAD']);
const statusShort = runGit(['status', '--short']);
const dirtyEntries = statusShort ? statusShort.split(/\r?\n/).filter(Boolean) : [];

const categories = [
  {
    id: 'test_pod_create',
    label: '테스트 Pod 생성 전용',
    severity: 'high',
    reason: '실제 mutation 기능처럼 보이지만 테스트 목적, allowlist, 기본값, 고정 manifest가 섞인 경로입니다.',
    regex:
      /\b(TEST_POD_CREATE|test_pod_create|create_crashloop_test_pods|crashloop_test_pod|aiops-test-pod|aiops-test-pods|gpu-test-kugnus)\b/i,
    targetModule: 'komsco_ai_gateway/test_pod_actions.py',
  },
  {
    id: 'demo_scenario',
    label: '데모/시나리오 전용',
    severity: 'medium',
    reason: '제품 기능과 데모 연출/시나리오 증거 경로가 같은 route 파일에 섞여 있습니다.',
    regex: /\b(crashloop_demo|past_pod_restart_demo|demo_cycle|DEMO|demoSeed|scenarioId|scenario)\b/i,
    targetModule: 'komsco_ai_gateway/demo_scenarios.py',
  },
  {
    id: 'fallback_answer',
    label: 'fallback 답변/우회 경로',
    severity: 'medium',
    reason: '모델/증거 실패 시의 우회 답변이 제품 답변처럼 보일 수 있어 별도 렌더러로 격리해야 합니다.',
    regex: /\b(fallback|gateway_fallback|Fallback|DEV_ECHO|not_configured)\b/,
    targetModule: 'komsco_ai_gateway/fallback_answers.py',
  },
  {
    id: 'answer_template',
    label: '고정 답변 템플릿',
    severity: 'medium',
    reason: '운영자에게 보이는 문구와 runtime orchestration이 같은 파일에 있어 과잉 답변/말투 회귀가 반복됩니다.',
    regex: /\b(_answer|_response|answerContract|Terminal Check Commands|터미널 확인 명령|현재 판단|Action Plan)\b/,
    targetModule: 'komsco_ai_gateway/answer_templates.py',
  },
  {
    id: 'hardcoded_resource',
    label: '고정 리소스/namespace/name',
    severity: 'high',
    reason: '특정 namespace/name/label이 제품 경로에 박히면 사용자 요청보다 fixture가 우선될 위험이 있습니다.',
    regex: /\b(gpu-test-kugnus|komsco-ai-dev|cyntra|aiops-two-pod-exec|openshift-marketplace|nginx-gateway|appscan-nfs-provisioner)\b/,
    targetModule: 'configuration/env or scenario fixture',
  },
  {
    id: 'runtime_default',
    label: 'runtime 기본값/상수',
    severity: 'medium',
    reason: '기본값은 필요하지만 생성 수량/대상 같은 운영 값은 확인 없이 자동 결정되면 안 됩니다.',
    regex: /\b(DEFAULT_|_DEFAULT_|MAX_|MIN_|ALLOWED_|ENABLED|DISABLED|BASE_URL|_URL|_TIMEOUT)\b/,
    targetModule: 'komsco_ai_gateway/settings.py',
  },
  {
    id: 'synthetic_data',
    label: 'synthetic/mock 데이터',
    severity: 'medium',
    reason: '합성 데이터는 학습/검증용으로 유효하지만 제품 화면에 섞이면 실조회와 혼동됩니다.',
    regex: /\b(synthetic|mock|sample|fixture|seed|local-fixture)\b/i,
    targetModule: 'fixtures or eval support module',
  },
  {
    id: 'rag_embedding_fallback',
    label: 'RAG/embedding fallback',
    severity: 'low',
    reason: 'RAG 임베딩 fallback은 필요할 수 있으나 검색 품질과 제품 답변 신뢰도를 구분해 표시해야 합니다.',
    regex: /\b(RAG_.*FALLBACK|embedding_fallback|hashing-bow|_warn_embedding_fallback)\b/i,
    targetModule: 'komsco_ai_gateway/rag_runtime.py',
  },
];

const functionAtLine = (() => {
  let current = '<module>';
  const names = [];
  for (let index = 0; index < lines.length; index += 1) {
    const match = lines[index].match(/^(?:async\s+def|def|class)\s+([A-Za-z_][A-Za-z0-9_]*)/);
    if (match) {
      current = match[1];
    }
    names[index + 1] = current;
  }
  return names;
})();

const findings = [];
for (let index = 0; index < lines.length; index += 1) {
  const text = lines[index];
  for (const category of categories) {
    if (!category.regex.test(text)) {
      continue;
    }
    findings.push({
      category: category.id,
      evidence: text.trim().slice(0, 220),
      functionName: functionAtLine[index + 1],
      line: index + 1,
      severity: category.severity,
    });
    break;
  }
}

const categoryById = Object.fromEntries(categories.map((category) => [category.id, category]));
const countsByCategory = categories.map((category) => ({
  category: category.id,
  label: category.label,
  severity: category.severity,
  count: findings.filter((finding) => finding.category === category.id).length,
  targetModule: category.targetModule,
}));

const functions = new Map();
for (const finding of findings) {
  const key = finding.functionName || '<module>';
  if (!functions.has(key)) {
    functions.set(key, {
      categories: {},
      firstLine: finding.line,
      functionName: key,
      lastLine: finding.line,
      total: 0,
    });
  }
  const item = functions.get(key);
  item.total += 1;
  item.firstLine = Math.min(item.firstLine, finding.line);
  item.lastLine = Math.max(item.lastLine, finding.line);
  item.categories[finding.category] = (item.categories[finding.category] || 0) + 1;
}

const functionHotspots = [...functions.values()]
  .sort((left, right) => right.total - left.total || left.firstLine - right.firstLine)
  .slice(0, 30);

const highRiskFindings = findings
  .filter((finding) => categoryById[finding.category]?.severity === 'high')
  .slice(0, 80);

const recommendations = [
  {
    order: 1,
    title: '테스트 Pod 생성 경로 격리',
    detail:
      'TEST_POD_CREATE_* 상수, preflight, 후보 생성, 답변 템플릿, executor를 test_pod_actions.py로 이동합니다. 기본 수량 3은 확인 필요 상태로 바꿉니다.',
  },
  {
    order: 2,
    title: '데모 시나리오 경로 격리',
    detail:
      'CrashLoop/Past restart demo evidence와 route 분기를 demo_scenarios.py로 이동하고, 제품 배포 모드에서 활성 조건을 명확히 둡니다.',
  },
  {
    order: 3,
    title: '답변 템플릿 분리',
    detail:
      '운영자에게 보이는 고정 문구를 answer_templates.py로 모아 질문 의도별 짧은 답변/상세 답변 기준을 테스트할 수 있게 합니다.',
  },
  {
    order: 4,
    title: 'fallback 경로 표시 규칙 고정',
    detail:
      'fallback 답변은 실조회/LLM/RAG 실패와 구분되게 하고, 기본 화면에 내부 용어가 나오지 않도록 별도 렌더러로 격리합니다.',
  },
  {
    order: 5,
    title: 'main.py route orchestration만 남기기',
    detail:
      '상태 저장과 chat stream은 마지막에 건드리고, 먼저 순수 함수와 템플릿부터 move-only로 줄입니다.',
  },
];

const report = {
  branch,
  dirtyWorktree: dirtyEntries.length > 0,
  dirtyEntries,
  generatedAt: new Date().toISOString(),
  head,
  lineCount: lines.length,
  source: sourceRel,
  summary: {
    categories: countsByCategory,
    findingCount: findings.length,
    highRiskCount: findings.filter((finding) => categoryById[finding.category]?.severity === 'high').length,
    hotspotCount: functionHotspots.length,
  },
  functionHotspots,
  highRiskFindings,
  recommendations,
};

const mdLine = (finding) =>
  `| ${finding.line} | \`${finding.functionName}\` | ${categoryById[finding.category].label} | \`${finding.evidence.replace(/\|/g, '\\|')}\` |`;

const markdown = [
  '# main.py 하드코딩/테스트 경로 감사표',
  '',
  `- 생성 시각: ${report.generatedAt}`,
  `- branch/head: \`${branch || '-'}\` / \`${head || '-'}\``,
  `- source: \`${sourceRel}\``,
  `- line count: ${lines.length}`,
  `- finding count: ${findings.length}`,
  `- dirty worktree: ${report.dirtyWorktree ? 'yes' : 'no'}`,
  '',
  '## 분류별 집계',
  '',
  '| 분류 | 심각도 | 건수 | 우선 분리 위치 |',
  '| :--- | :---: | ---: | :--- |',
  ...countsByCategory.map(
    (item) => `| ${item.label} | ${item.severity} | ${item.count} | \`${item.targetModule}\` |`,
  ),
  '',
  '## 함수/구간 hotspot',
  '',
  '| 함수/구간 | 라인 | 건수 | 주요 분류 |',
  '| :--- | :--- | ---: | :--- |',
  ...functionHotspots.map((item) => {
    const categoriesText = Object.entries(item.categories)
      .sort((a, b) => b[1] - a[1])
      .map(([category, count]) => `${categoryById[category].label} ${count}`)
      .join(', ');
    return `| \`${item.functionName}\` | ${item.firstLine}-${item.lastLine} | ${item.total} | ${categoriesText} |`;
  }),
  '',
  '## high risk 근거 샘플',
  '',
  '| line | 함수/구간 | 분류 | 코드 조각 |',
  '| ---: | :--- | :--- | :--- |',
  ...highRiskFindings.slice(0, 40).map(mdLine),
  '',
  '## 정리 순서 제안',
  '',
  ...recommendations.map((item) => `${item.order}. **${item.title}**: ${item.detail}`),
  '',
  '## 판정',
  '',
  '- 이 보고서는 동작을 바꾸지 않는 정적 감사표입니다.',
  '- 지금 상태에서 바로 삭제할 항목을 고르는 용도가 아니라, 제품 기능과 테스트/데모 기능을 분리하기 위한 지도입니다.',
  '- protected docs, PDF, docs/Ver.0.2.9 자료는 수정하지 않습니다.',
  '',
].join('\n');

fs.mkdirSync(path.dirname(abs(outputPath)), { recursive: true });
fs.writeFileSync(abs(outputPath), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
fs.writeFileSync(abs(markdownPath), markdown, 'utf8');

console.log(`PASS main hardcoding audit`);
console.log(`source=${sourceRel}`);
console.log(`lines=${lines.length} findings=${findings.length} highRisk=${report.summary.highRiskCount}`);
console.log(`json=${rel(outputPath)}`);
console.log(`markdown=${rel(markdownPath)}`);
