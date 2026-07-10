require('ts-node/register/transpile-only');

const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { buildRcaViewPageContext } = require('../src/portal/aiopsPageContext');

const context = buildRcaViewPageContext({
  caseHeader: {
    baseline: 'OCP 4.20',
    caseState: '조사 중',
    family: '워크로드 런타임 / RCA 케이스',
    finding: '활성 파드 상태 변화가 감지되었습니다.',
    issueLine: '실패 2 · 대기 1',
    metrics: [{ label: '실패', value: '2' }],
    scope: '전체 네임스페이스',
    title: '파드 상태 저하',
  },
  caseId: 'RCA-TEST-001',
  cluster: 'api.ocp.example',
  dataSource: 'live',
  evidence: [{ source: '파드 인벤토리', field: '실패', value: '2' }],
  findings: [{ kicker: '주 원인 후보', title: '파드 런타임 이상 신호' }],
  issueType: 'WORKLOAD_PODS',
  runbookGates: [{ title: '이벤트 확인', status: '필수' }],
  selectedIssue: { id: 'pod-health', title: '파드 상태 저하' },
  timeline: [{ title: '파드 인벤토리 수집', detail: '완료' }],
});

const view = context.aiopsViewContext;
assert.equal(view.pageTitle, 'RCA 센터');
assert.equal(view.route, '/dashboards/aiops/audit');
assert.equal(view.evidencePolicy, 'live_dashboard_context');
assert.equal(view.case.caseId, 'RCA-TEST-001');
assert.equal(view.case.issueType, 'WORKLOAD_PODS');
assert.equal(view.selectedIssue.title, '파드 상태 저하');
assert.equal(view.findings[0].title, '파드 런타임 이상 신호');
assert.equal(view.evidence[0].value, '2');
assert.equal(view.runbookGates[0].status, '필수');
assert.equal(view.timeline[0].title, '파드 인벤토리 수집');

const portalSource = fs.readFileSync(path.join(__dirname, '../src/portal/PortalApp.tsx'), 'utf8');
assert.match(portalSource, /<RcaView[\s\S]*onPageContextChange=\{onPageContextChange\}/);
assert.match(portalSource, /onPageContextChange\?\.\(rcaPageContext\)/);

console.log('PASS: RCA Center publishes visible case, findings, evidence, gates, and timeline.');
