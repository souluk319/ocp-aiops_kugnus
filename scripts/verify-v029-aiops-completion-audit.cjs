#!/usr/bin/env node

const { execFileSync } = require('child_process');
const fs = require('fs');
const path = require('path');

const root = path.resolve(__dirname, '..');
const defaultOutput = '.tmp-kugnus-demo/aiops-completion-audit.json';
const defaultMarkdown = '.tmp-kugnus-demo/aiops-completion-audit.md';

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
const skipStaticChecks = process.env.AIOPS_COMPLETION_AUDIT_SKIP_STATIC === '1';

const rel = (target) => path.relative(root, path.resolve(root, target)).replace(/\\/g, '/');
const abs = (target) => path.resolve(root, target);
const exists = (target) => fs.existsSync(abs(target));
const readText = (target) => (exists(target) ? fs.readFileSync(abs(target), 'utf8') : '');

const readJson = (target) => {
  try {
    return JSON.parse(readText(target));
  } catch (_error) {
    return null;
  }
};

const now = () => new Date().toISOString();

const runGit = (gitArgs) => {
  try {
    return execFileSync('git', gitArgs, { cwd: root, encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
  } catch (error) {
    return '';
  }
};

const branch = runGit(['branch', '--show-current']);
const head = runGit(['rev-parse', '--short', 'HEAD']);
const statusShort = runGit(['status', '--short']);
const dirtyEntries = statusShort ? statusShort.split(/\r?\n/).filter(Boolean) : [];

const taskfile = readText('Taskfile.yml');
const officialMarkdown = readText('docs/Komsco_AIOps_agent_final.md');
const contracts = readText('komsco-ai-gateway/komsco_ai_gateway/aiops_contracts.py');
const gatewayMain = readText('komsco-ai-gateway/komsco_ai_gateway/main.py');
const gatewayTests = readText('komsco-ai-gateway/tests/test_health.py');
const portalApp = readText('komsco-ai-console-plugin/src/portal/PortalApp.tsx');
const portalApi = readText('komsco-ai-console-plugin/src/portal/api.ts');

const makeEvidence = (label, status, source, detail = '') => ({
  label,
  status,
  source,
  detail,
});

const commandText = (command) => command.join(' ');

const runCheck = (id, title, command, timeoutMs = 120000) => {
  if (skipStaticChecks) {
    return {
      id,
      title,
      status: 'skipped',
      ok: false,
      command: commandText(command),
      detail: 'AIOPS_COMPLETION_AUDIT_SKIP_STATIC=1',
    };
  }
  try {
    const stdout = execFileSync(command[0], command.slice(1), {
      cwd: root,
      encoding: 'utf8',
      timeout: timeoutMs,
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    return {
      id,
      title,
      status: 'pass',
      ok: true,
      command: commandText(command),
      detail: stdout.trim().split(/\r?\n/).slice(-3).join('\n'),
    };
  } catch (error) {
    return {
      id,
      title,
      status: 'fail',
      ok: false,
      command: commandText(command),
      detail: String(error.stderr || error.stdout || error.message || '').trim().slice(-2000),
    };
  }
};

const staticChecks = [
  runCheck('v029-chatbot-markdown-ux', 'v0.2.9 챗봇 Markdown/Action UX 정적 검증', [
    'node',
    'scripts/verify-v029-chatbot-markdown-ux.cjs',
  ]),
  runCheck('v029-rag-wiki-live', 'v0.2.9 RAG Wiki live API 연결 정적 검증', [
    'node',
    'scripts/verify-v029-rag-wiki-live.cjs',
  ]),
  runCheck('v029-report-artifact', 'v0.2.9 보고서 산출물 정적 검증', [
    'node',
    'scripts/verify-v029-report-artifact.cjs',
  ]),
  runCheck('v029-learning-dataset-export', 'v0.2.9 학습 데이터 export 검증', [
    'node',
    'scripts/verify-v029-learning-dataset-export.cjs',
  ]),
];

const checkById = new Map(staticChecks.map((check) => [check.id, check]));
const checkOk = (id) => checkById.get(id)?.ok === true;

const isReportFresh = (report) => {
  if (!report || typeof report !== 'object') {
    return false;
  }
  const reportBranch = report.branch || report.metadata?.branch;
  const reportHead = report.head || report.headSha || report.metadata?.headSha;
  if (reportHead) {
    return String(reportHead).startsWith(head);
  }
  if (reportBranch) {
    return String(reportBranch) === branch;
  }
  return false;
};

const scenarioReport = readJson('docs/Ver.0.1.3/aiops-scenario-evaluation-report.json');
const reviewGateReport = readJson('docs/Ver.0.1.9/aiops-review-gate-report.json');
const lightspeedReport = readJson('docs/Ver.0.1.5/live-lightspeed-final-response-verification.json');
const learningDataset = readJson('.tmp-kugnus-demo/aiops-learning-dataset.json');
const actionHistoryReport = readJson('.tmp-kugnus-demo/v029-chatbot-action-history-flow.json');

const scenarioFresh = isReportFresh(scenarioReport);
const scenarioPassed =
  scenarioReport?.scenarioCount >= 1 &&
  scenarioReport?.failed === 0 &&
  scenarioReport?.negativeControlsPassed === true;
const reviewGateFresh = isReportFresh(reviewGateReport);
const reviewGatePassed = reviewGateReport?.passed === true || reviewGateReport?.offlineGatePassed === true;
const lightspeedFresh = isReportFresh(lightspeedReport);
const lightspeedPassed =
  lightspeedReport?.allSucceeded === true &&
  Array.isArray(lightspeedReport?.cases) &&
  lightspeedReport.cases.every((item) => item?.ok === true);
const actionHistoryFresh = isReportFresh(actionHistoryReport);
const actionHistoryPassed = actionHistoryReport?.passed === true && actionHistoryFresh;
const actionHistoryCheck = {
  id: 'v029-chatbot-action-history-flow-report',
  title: 'v0.2.9 Action Plan lifecycle browser report',
  status: actionHistoryReport?.passed ? (actionHistoryFresh ? 'pass' : 'stale') : 'not_run',
  ok: actionHistoryPassed,
  command: 'node scripts/verify-v029-chatbot-action-history-flow.cjs',
  detail: actionHistoryReport
    ? `path=${actionHistoryReport.path || 'approval-then-execution'} generatedAt=${actionHistoryReport.generatedAt || 'unknown'}`
    : 'No .tmp-kugnus-demo/v029-chatbot-action-history-flow.json report found',
};

const probe = async (label, url) => {
  if (typeof fetch !== 'function') {
    return makeEvidence(label, 'not_run', url, 'global fetch is unavailable in this Node runtime');
  }
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 1800);
  try {
    const response = await fetch(url, { signal: controller.signal });
    return makeEvidence(label, response.ok ? 'pass' : 'fail', url, `HTTP ${response.status}`);
  } catch (error) {
    return makeEvidence(label, 'not_run', url, error.name === 'AbortError' ? 'timeout' : error.message);
  } finally {
    clearTimeout(timer);
  }
};

const statusRank = {
  Done: 0,
  Partial: 1,
  Missing: 2,
  Blocked: 3,
  'Not Run': 4,
};

const makeRequirement = ({
  id,
  title,
  officialBasis,
  status,
  requiredEvidence,
  currentEvidence,
  gap,
  nextCommand,
}) => ({
  id,
  title,
  officialBasis,
  status,
  requiredEvidence,
  currentEvidence,
  gap,
  nextCommand,
});

const hasAll = (text, needles) => needles.every((needle) => text.includes(needle));
const verifierEvidence = (id, source) => {
  const check = checkById.get(id);
  if (!check) {
    return makeEvidence(source, 'not_run', source, 'check not registered');
  }
  return makeEvidence(source, check.ok ? 'pass' : check.status, check.command, check.detail);
};

const buildRequirements = async () => {
  const endpointEvidence = await Promise.all([
    probe('gateway health', 'http://127.0.0.1:18080/healthz'),
    probe('OKD console bridge', 'http://127.0.0.1:9000/api/kubernetes/version'),
    probe('console plugin dev server', 'http://127.0.0.1:9001/'),
    probe('standalone fixture', 'http://127.0.0.1:5174/healthz'),
  ]);
  const endpointsOk = endpointEvidence.every((item) => item.status === 'pass');
  const hasDoctorTasks = taskfile.includes('kugnus:dev:doctor') && taskfile.includes('kugnus:aiops:doctor');

  return [
    makeRequirement({
      id: 'local-runtime-stability',
      title: '로컬 실행 연결 안정성',
      officialBasis: 'AI Gateway, Console Plugin, Lightspeed 연동을 로컬에서 재현 가능해야 함',
      status: endpointsOk && hasDoctorTasks ? 'Done' : hasDoctorTasks ? 'Partial' : 'Missing',
      requiredEvidence: ['18080/9000/9001/5174 HTTP 확인', 'doctor task 존재', 'stale listener 진단 경로'],
      currentEvidence: [
        ...endpointEvidence,
        makeEvidence('doctor tasks', hasDoctorTasks ? 'pass' : 'fail', 'Taskfile.yml', 'kugnus:dev:doctor / kugnus:aiops:doctor'),
      ],
      gap: endpointsOk ? '' : '현재 실행 중인 로컬 endpoint 전체가 HTTP OK로 증명되지 않음',
      nextCommand: 'task kugnus:dev:doctor && task kugnus:aiops:doctor',
    }),
    makeRequirement({
      id: 'ocp-native-architecture',
      title: 'OCP 네이티브 구조',
      officialBasis: '기존 OpenShift 환경 보존, Dynamic Console Plugin, AI Gateway, Operator/OLM',
      status:
        exists('docs/Komsco_ai_agent_final.pdf') &&
        exists('komsco-ai-console-plugin') &&
        exists('komsco-ai-gateway') &&
        taskfile.includes('aiops:package')
          ? 'Done'
          : 'Missing',
      requiredEvidence: ['공식 PDF 존재', 'Gateway/Console Plugin 소스', 'OLM package task'],
      currentEvidence: [
        makeEvidence('official PDF', exists('docs/Komsco_ai_agent_final.pdf') ? 'pass' : 'fail', 'docs/Komsco_ai_agent_final.pdf'),
        makeEvidence('gateway/plugin source', exists('komsco-ai-gateway') && exists('komsco-ai-console-plugin') ? 'pass' : 'fail', 'repo'),
        makeEvidence('OLM task', taskfile.includes('aiops:package') ? 'pass' : 'fail', 'Taskfile.yml', 'aiops:package'),
      ],
      gap: '',
      nextCommand: 'task kugnus:package',
    }),
    makeRequirement({
      id: 'auth-rbac-security',
      title: '인증/RBAC/보안/감사',
      officialBasis: 'OpenShift UserToken, RBAC, 민감정보 필터링, 전 구간 감사로그',
      status: hasAll(officialMarkdown + contracts + gatewayMain, ['UserToken', 'RBAC', 'audit']) ? 'Partial' : 'Missing',
      requiredEvidence: ['UserToken/RBAC 차단', 'secret/token redaction', 'audit record 저장', '권한 실패 테스트'],
      currentEvidence: [
        makeEvidence('official security markers', hasAll(officialMarkdown, ['UserToken', 'RBAC']) ? 'pass' : 'fail', 'docs/Komsco_AIOps_agent_final.md'),
        makeEvidence('gateway audit markers', (contracts + gatewayMain).includes('audit') ? 'pass' : 'fail', 'komsco-ai-gateway'),
        makeEvidence('learning redaction verifier', checkOk('v029-learning-dataset-export') ? 'pass' : 'fail', 'scripts/verify-v029-learning-dataset-export.cjs'),
      ],
      gap: reviewGateFresh && !reviewGatePassed
        ? '현재 head 기준 review gate가 실패하여 RBAC/보안 완료 gate를 통과하지 못함'
        : '현재 head 기준 RBAC 실패/권한 초과 차단을 live로 다시 증명한 보고서가 없음',
      nextCommand: 'task kugnus:aiops:review-gate',
    }),
    makeRequirement({
      id: 'os-context-classifier',
      title: 'OS Context 분류',
      officialBasis: 'Linux/Windows/OCP 질문을 구분해 Tool Plan을 생성',
      status: hasAll(contracts, ['Linux', 'Windows', 'OpenShift']) ? 'Partial' : 'Missing',
      requiredEvidence: ['Linux 질문 분류', 'Windows 질문 분류', 'OCP 질문 분류', '각 분류별 Tool Plan'],
      currentEvidence: [
        makeEvidence('adapter names', hasAll(contracts, ['Linux', 'Windows', 'OpenShift']) ? 'pass' : 'fail', 'aiops_contracts.py'),
        makeEvidence('scenario report', scenarioPassed ? (scenarioFresh ? 'pass' : 'stale') : 'fail', 'docs/Ver.0.1.3/aiops-scenario-evaluation-report.json', `fresh=${scenarioFresh}`),
      ],
      gap: scenarioFresh
        ? 'OCP/Linux 시나리오는 통과했지만 Windows Event/Service 분류 시나리오가 별도 완료 증거로 없음'
        : '분류 계약은 있으나 현재 head 기준 Linux/Windows/OCP 전체 분류 회귀가 fresh report로 고정되지 않음',
      nextCommand: 'task kugnus:scenario:verify',
    }),
    makeRequirement({
      id: 'tool-plan-json',
      title: 'Tool Plan JSON',
      officialBasis: 'AIOps Model이 Tool Plan JSON을 만들고 Gateway가 실행/조회 범위를 통제',
      status: hasAll(contracts + gatewayTests, ['tool_plan', 'execution_policy']) && reviewGateFresh && reviewGatePassed
        ? 'Done'
        : hasAll(contracts + gatewayTests, ['tool_plan', 'execution_policy'])
          ? 'Partial'
          : 'Missing',
      requiredEvidence: ['Tool Plan schema', '위험도/실행 정책', 'stream/status 노출', 'schema 회귀 테스트'],
      currentEvidence: [
        makeEvidence('tool plan markers', hasAll(contracts + gatewayTests, ['tool_plan', 'execution_policy']) ? 'pass' : 'fail', 'komsco-ai-gateway'),
        makeEvidence('review gate', reviewGatePassed ? (reviewGateFresh ? 'pass' : 'stale') : 'fail', 'docs/Ver.0.1.9/aiops-review-gate-report.json', `fresh=${reviewGateFresh}`),
      ],
      gap: reviewGateFresh && reviewGatePassed
        ? ''
        : reviewGateFresh && !reviewGatePassed
          ? '현재 head 기준 review gate 실패: Console action approval button wiring'
          : '이전 review gate는 현재 head 기준 fresh하지 않음',
      nextCommand: 'task kugnus:aiops:review-gate',
    }),
    makeRequirement({
      id: 'openshift-adapter',
      title: 'OpenShift Adapter',
      officialBasis: 'Pod/Event/Log/Resource/Operator/Metric 조회를 안전하게 실행',
      status: hasAll(contracts, ['OpenShift', 'event', 'log', 'metric']) ? 'Partial' : 'Missing',
      requiredEvidence: ['Pod 조회', 'Event 조회', 'Log 조회', 'Resource/Operator 조회', 'Metric 조회 또는 unavailable reason'],
      currentEvidence: [
        makeEvidence('OpenShift capability markers', hasAll(contracts, ['OpenShift', 'event', 'log', 'metric']) ? 'pass' : 'fail', 'aiops_contracts.py'),
        makeEvidence('scenario adapter resolution', scenarioPassed ? (scenarioFresh ? 'pass' : 'stale') : 'fail', 'scenario report', `passed=${scenarioReport?.passed ?? 'n/a'}`),
      ],
      gap: scenarioFresh
        ? 'offline adapter resolution은 통과했지만 live Pod/Event/Log/Metric 실행 report는 별도 필요'
        : '현재 head 기준 live OpenShift adapter 실행 결과가 판정표 안에서 fresh하지 않음',
      nextCommand: 'task kugnus:scenario:verify && task kugnus:aiops:doctor',
    }),
    makeRequirement({
      id: 'linux-adapter',
      title: 'Linux Adapter',
      officialBasis: 'journalctl/systemctl/dmesg 등 Linux OS 진단 조회',
      status: contracts.includes('KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_URL') ? 'Partial' : 'Missing',
      requiredEvidence: ['Linux diagnostics controller URL', 'journalctl/systemctl/dmesg 조회', 'credential/network gate'],
      currentEvidence: [
        makeEvidence('diagnostics controller gate', contracts.includes('KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_URL') ? 'pass' : 'fail', 'aiops_contracts.py'),
        makeEvidence('disabled reason', contracts.includes('Linux host diagnostics stay disabled') ? 'warn' : 'fail', 'aiops_contracts.py'),
      ],
      gap: 'Linux 진단 controller가 설정되지 않으면 실제 host command evidence가 없음',
      nextCommand: 'KOMSCO_AI_DIAGNOSTICS_ENABLED=true KOMSCO_AI_HOST_DIAGNOSTICS_CONTROLLER_URL=<internal-url> task kugnus:aiops:doctor',
    }),
    makeRequirement({
      id: 'windows-adapter',
      title: 'Windows Adapter',
      officialBasis: 'Windows Event/Service adapter 실행 준비',
      status: contracts.includes('Windows adapter has no runtime collector') ? 'Missing' : 'Partial',
      requiredEvidence: ['Windows node agent', 'Event Log 조회', 'Service 조회', 'credential bridge'],
      currentEvidence: [
        makeEvidence('planned marker', contracts.includes('Windows') ? 'pass' : 'fail', 'aiops_contracts.py'),
        makeEvidence('runtime collector', contracts.includes('Windows adapter has no runtime collector') ? 'fail' : 'pass', 'aiops_contracts.py'),
      ],
      gap: 'Windows node agent 또는 remote event bridge가 아직 없음',
      nextCommand: 'Windows node agent/credential bridge 설계 후 adapter verifier 추가',
    }),
    makeRequirement({
      id: 'evidence-rca-context',
      title: 'Evidence/RCA Context',
      officialBasis: 'Evidence API, 과거 증적, RCA Context JSON을 Lightspeed 답변 전 구조화',
      status: hasAll(contracts + gatewayTests, ['evidence', 'rca_context']) && scenarioFresh && scenarioPassed ? 'Done' : hasAll(contracts + gatewayTests, ['evidence', 'rca_context']) ? 'Partial' : 'Missing',
      requiredEvidence: ['collected/missing evidence', 'RCA Context JSON', 'digest/audit 연결', 'overclaim 방지'],
      currentEvidence: [
        makeEvidence('Evidence/RCA markers', hasAll(contracts + gatewayTests, ['evidence', 'rca_context']) ? 'pass' : 'fail', 'komsco-ai-gateway'),
        makeEvidence('scenario report', scenarioPassed ? (scenarioFresh ? 'pass' : 'stale') : 'fail', 'scenario report'),
      ],
      gap: scenarioFresh && scenarioPassed ? '' : '현재 head 기준 scenario/evidence report를 다시 생성해야 Done 가능',
      nextCommand: 'task kugnus:scenario:verify',
    }),
    makeRequirement({
      id: 'rag-runbook-sop',
      title: 'RAG/Runbook/SOP',
      officialBasis: '사내 Runbook/SOP와 pgvector RAG를 RCA/조치 후보에 연결',
      status: checkOk('v029-rag-wiki-live') && hasAll(portalApi + portalApp, ['/v1/rag/search', '/v1/rag/uploads']) ? 'Partial' : 'Missing',
      requiredEvidence: ['Gateway RAG API', 'pgvector persistence', 'closed-network corpus', 'answer/action 연결'],
      currentEvidence: [
        verifierEvidence('v029-rag-wiki-live', 'scripts/verify-v029-rag-wiki-live.cjs'),
        makeEvidence('RAG API markers', hasAll(portalApi + portalApp, ['/v1/rag/search', '/v1/rag/uploads']) ? 'pass' : 'fail', 'portal api/app'),
      ],
      gap: '로컬 UI/API 연결은 있으나 회사 폐쇄망 corpus ingestion과 품질 검증은 완료 증거가 아님',
      nextCommand: 'task kugnus:rag:mock-customer:smoke && task kugnus:rag:chat:smoke',
    }),
    makeRequirement({
      id: 'lightspeed-streaming',
      title: 'Lightspeed Streaming',
      officialBasis: 'Gateway context를 Lightspeed API로 전달하고 최종 RCA를 streaming 제공',
      status: lightspeedPassed ? (lightspeedFresh ? 'Done' : 'Partial') : 'Partial',
      requiredEvidence: ['OLS readiness', 'streaming answer', 'fallback 없음', 'context digest 전달'],
      currentEvidence: [
        makeEvidence('live lightspeed report', lightspeedPassed ? (lightspeedFresh ? 'pass' : 'stale') : 'fail', 'docs/Ver.0.1.5/live-lightspeed-final-response-verification.json', `allSucceeded=${lightspeedReport?.allSucceeded ?? 'n/a'}`),
        makeEvidence('review gate live summary', reviewGateReport?.liveVerification?.status === 'proven' ? (reviewGateFresh ? 'pass' : 'stale') : 'fail', 'docs/Ver.0.1.9/aiops-review-gate-report.json'),
      ],
      gap: '성공 보고서가 현재 head 기준 fresh하지 않음',
      nextCommand: 'task kugnus:aiops:live-verify',
    }),
    makeRequirement({
      id: 'chat-ux-action-plan',
      title: '챗봇 UX/Action Plan',
      officialBasis: '운영 답변, 근거 표시, Action Plan 후보/승인/실행 흐름',
      status: checkOk('v029-chatbot-markdown-ux') ? 'Done' : 'Partial',
      requiredEvidence: ['Markdown 안정화', 'Action 후보 dedupe/collapse', '내부 용어 숨김', 'history/layout 회귀'],
      currentEvidence: [verifierEvidence('v029-chatbot-markdown-ux', 'scripts/verify-v029-chatbot-markdown-ux.cjs')],
      gap: checkOk('v029-chatbot-markdown-ux') ? '' : 'v0.2.9 챗봇 UX verifier 실패',
      nextCommand: 'node scripts/verify-v029-chatbot-markdown-ux.cjs',
    }),
    makeRequirement({
      id: 'safety-approval-execution',
      title: 'Safety/Approval/Execution',
      officialBasis: '위험 작업 차단, 승인 필요 여부 판단, 승인 없는 mutation 금지',
      status: actionHistoryPassed ? 'Done' : exists('scripts/verify-v029-chatbot-action-history-flow.cjs') ? 'Partial' : 'Missing',
      requiredEvidence: ['read-only 차단', 'execute 승인 후 실행', 'execution record', 'review-only 기록'],
      currentEvidence: [
        makeEvidence('action history verifier', exists('scripts/verify-v029-chatbot-action-history-flow.cjs') ? 'pass' : 'fail', 'scripts/verify-v029-chatbot-action-history-flow.cjs'),
        makeEvidence('action history report', actionHistoryReport?.passed ? (actionHistoryFresh ? 'pass' : 'stale') : 'not_run', '.tmp-kugnus-demo/v029-chatbot-action-history-flow.json', `fresh=${actionHistoryFresh}`),
        makeEvidence('review gate', reviewGatePassed ? (reviewGateFresh ? 'pass' : 'stale') : 'fail', 'review gate'),
      ],
      gap: actionHistoryPassed ? '' : '브라우저 기반 Action Plan 생성/승인/실행 record 검증을 현재 head 기준으로 다시 실행해야 Done',
      nextCommand: 'node scripts/verify-v029-chatbot-action-history-flow.cjs',
    }),
    makeRequirement({
      id: 'report-artifact',
      title: 'RCA/조치 보고서 산출물',
      officialBasis: 'RCA, 즉시 조치, 재발 방지책, 참고 증적을 Chat UI/보고서로 제공',
      status: checkOk('v029-report-artifact') ? 'Done' : 'Missing',
      requiredEvidence: ['AIOpsReportArtifact JSON', 'evidence package', 'action/audit summary', 'download path'],
      currentEvidence: [verifierEvidence('v029-report-artifact', 'scripts/verify-v029-report-artifact.cjs')],
      gap: checkOk('v029-report-artifact') ? '' : '보고서 산출물 verifier 실패',
      nextCommand: 'node scripts/verify-v029-report-artifact.cjs',
    }),
    makeRequirement({
      id: 'learning-dataset',
      title: '학습/평가 데이터 Export',
      officialBasis: 'SFT, preference, safety, continuous learning을 위한 질문/ToolPlan/RCA/피드백 데이터',
      status: checkOk('v029-learning-dataset-export') && learningDataset?.kind === 'AIOpsLearningDataset' ? 'Done' : 'Partial',
      requiredEvidence: ['AIOpsLearningDataset', 'transcript/feedback/action/audit 연결', 'redaction', 'scenario evaluation 포함'],
      currentEvidence: [
        verifierEvidence('v029-learning-dataset-export', 'scripts/verify-v029-learning-dataset-export.cjs'),
        makeEvidence('latest dataset', learningDataset?.kind === 'AIOpsLearningDataset' ? 'pass' : 'not_run', '.tmp-kugnus-demo/aiops-learning-dataset.json', `records=${learningDataset?.metadata?.counts?.records ?? 'n/a'}`),
      ],
      gap: learningDataset?.kind === 'AIOpsLearningDataset' ? '' : '학습 데이터 산출물을 생성해야 함',
      nextCommand: 'task kugnus:aiops:learning-dataset',
    }),
    makeRequirement({
      id: 'olm-company-deploy',
      title: 'OLM/회사망 배포',
      officialBasis: 'Operator/OLM 기반 Software Catalog 표준 배포, 설치/업그레이드/복구',
      status: 'Blocked',
      requiredEvidence: ['company check', 'publish evidence', 'install evidence', 'status evidence'],
      currentEvidence: [
        makeEvidence('company tasks', hasAll(taskfile, ['aiops:company:check', 'aiops:company:publish', 'aiops:company:install', 'aiops:company:status']) ? 'pass' : 'fail', 'Taskfile.yml'),
        makeEvidence('approval gates', hasAll(taskfile, ['KOMSCO_AIOPS_APPROVE_PUBLISH', 'KOMSCO_AIOPS_APPROVE_INSTALL']) ? 'pass' : 'fail', 'Taskfile.yml'),
      ],
      gap: '회사 서버 publish/install/status는 승인 및 회사망 연결 없이는 완료 처리 금지',
      nextCommand: 'task kugnus:company:check && task kugnus:company:status',
    }),
    makeRequirement({
      id: 'scenario-evaluation',
      title: '시나리오 평가/회귀 Gate',
      officialBasis: '한국어 AIOps scenario, negative control, RCA result schema 자동 평가',
      status: scenarioPassed ? (scenarioFresh ? 'Done' : 'Partial') : 'Missing',
      requiredEvidence: ['scenario count', '0 failed', 'negative control', 'RCA schema'],
      currentEvidence: [
        makeEvidence('scenario report', scenarioPassed ? (scenarioFresh ? 'pass' : 'stale') : 'fail', 'docs/Ver.0.1.3/aiops-scenario-evaluation-report.json', `passed=${scenarioReport?.passed ?? 'n/a'} failed=${scenarioReport?.failed ?? 'n/a'} fresh=${scenarioFresh}`),
      ],
      gap: scenarioFresh ? '' : '시나리오 보고서가 현재 branch/head 기준으로 다시 생성되지 않음',
      nextCommand: 'task kugnus:scenario:verify',
    }),
  ];
};

const renderMarkdown = (report) => {
  const lines = [];
  lines.push('# AIOps 완료 판정표');
  lines.push('');
  lines.push(`- 생성 시각: ${report.generatedAt}`);
  lines.push(`- Branch: \`${report.branch || 'unknown'}\``);
  lines.push(`- HEAD: \`${report.head || 'unknown'}\``);
  lines.push(`- Product complete: \`${report.overall.productComplete}\``);
  lines.push(`- Release ready: \`${report.overall.releaseReady}\``);
  lines.push(`- Dirty worktree: \`${report.dirtyWorktree.isDirty}\` (${report.dirtyWorktree.entries.length} entries)`);
  lines.push('');
  lines.push('| ID | Status | Gap | Next command |');
  lines.push('| --- | --- | --- | --- |');
  for (const requirement of report.requirements) {
    lines.push(
      `| \`${requirement.id}\` | ${requirement.status} | ${requirement.gap || '-'} | \`${requirement.nextCommand}\` |`,
    );
  }
  lines.push('');
  lines.push('## Checks');
  lines.push('');
  for (const check of report.checks) {
    lines.push(`- ${check.status.toUpperCase()} \`${check.id}\`: \`${check.command}\``);
  }
  lines.push('');
  lines.push('## Next Actions');
  lines.push('');
  for (const action of report.nextActions) {
    lines.push(`- [${action.status}] ${action.id}: \`${action.nextCommand}\``);
  }
  lines.push('');
  return `${lines.join('\n')}\n`;
};

const main = async () => {
  const requirements = await buildRequirements();
  const counts = requirements.reduce(
    (acc, item) => {
      acc[item.status] = (acc[item.status] || 0) + 1;
      return acc;
    },
    { Done: 0, Partial: 0, Missing: 0, Blocked: 0, 'Not Run': 0 },
  );
  const productComplete = requirements.every((item) => item.status === 'Done');
  const releaseReady = productComplete && dirtyEntries.length === 0;
  const worstStatus = requirements
    .map((item) => item.status)
    .sort((a, b) => (statusRank[b] ?? 99) - (statusRank[a] ?? 99))[0];

  const report = {
    apiVersion: 'aiops.komsco/v1',
    kind: 'AIOpsCompletionAudit',
    generatedAt: now(),
    branch,
    head,
    dirtyWorktree: {
      isDirty: dirtyEntries.length > 0,
      entries: dirtyEntries,
    },
    sourceOfTruth: {
      officialPdf: {
        path: 'docs/Komsco_ai_agent_final.pdf',
        exists: exists('docs/Komsco_ai_agent_final.pdf'),
      },
      officialMarkdown: {
        path: 'docs/Komsco_AIOps_agent_final.md',
        exists: exists('docs/Komsco_AIOps_agent_final.md'),
      },
      protectedArtifactsLeftUntouchedByThisAudit: [
        'docs/Komsco_ai_agent_final.pdf',
        'docs/Ver.0.2.9/AIOps_Chatbot_plan.md',
        'docs/aiops-beginner-guide.html',
        'docs/Ver.0.1.8/aiops-llm-strategy-brief.html',
      ],
    },
    overall: {
      productComplete,
      releaseReady,
      status: productComplete ? 'Done' : worstStatus || 'Partial',
      counts,
      reason: productComplete
        ? 'All official-PDF-aligned requirement rows are Done.'
        : 'At least one official-PDF-aligned requirement row is not Done.',
    },
    requirements,
    checks: [...staticChecks, actionHistoryCheck],
    nextActions: requirements
      .filter((item) => item.status !== 'Done')
      .sort((a, b) => (statusRank[a.status] ?? 99) - (statusRank[b.status] ?? 99))
      .map((item) => ({
        id: item.id,
        status: item.status,
        gap: item.gap,
        nextCommand: item.nextCommand,
      })),
  };

  fs.mkdirSync(path.dirname(abs(outputPath)), { recursive: true });
  fs.writeFileSync(abs(outputPath), `${JSON.stringify(report, null, 2)}\n`, 'utf8');
  if (markdownPath) {
    fs.mkdirSync(path.dirname(abs(markdownPath)), { recursive: true });
    fs.writeFileSync(abs(markdownPath), renderMarkdown(report), 'utf8');
  }

  console.log(
    `PASS verify-v029-aiops-completion-audit productComplete=${report.overall.productComplete} releaseReady=${report.overall.releaseReady}`,
  );
  console.log(`JSON ${rel(outputPath)}`);
  if (markdownPath) {
    console.log(`MD ${rel(markdownPath)}`);
  }
};

main().catch((error) => {
  console.error(error.stack || error.message || String(error));
  process.exit(1);
});
