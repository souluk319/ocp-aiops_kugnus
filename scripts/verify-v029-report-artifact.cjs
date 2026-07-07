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

const portalApp = readFile('komsco-ai-console-plugin/src/portal/PortalApp.tsx');
const portalCss = readFile('komsco-ai-console-plugin/src/portal/styles.css');

assert(portalApp.includes("kind: 'AIOpsReportArtifact'"), 'Generated reports must create an AIOpsReportArtifact JSON package');
assert(portalApp.includes('artifact: ReportArtifact;'), 'GeneratedReport must carry the report artifact alongside HTML');
assert(portalApp.includes('const createReportArtifact ='), 'Report artifact builder must exist');
assert(portalApp.includes('apiVersion: \'aiops.komsco/v1\''), 'Report artifact must carry the aiops.komsco API version');
assert(portalApp.includes('metadata: {') && portalApp.includes('sourceSnapshotId') && portalApp.includes('templateId'), 'Report artifact metadata must include report/source/template IDs');
assert(portalApp.includes('evidencePackage: {'), 'Report artifact must include an RCA evidence package section');
assert(portalApp.includes('actionsAndAudit: {'), 'Report artifact must include action and audit summary');
assert(portalApp.includes('actionProposals: records.actionProposals.length'), 'Report artifact must count ActionProposal records');
assert(portalApp.includes('sealedActionPlans: records.sealedActionPlans.length'), 'Report artifact must count sealed action plans');
assert(portalApp.includes('approvalDecisions: records.approvalDecisions.length'), 'Report artifact must count approval decisions');
assert(portalApp.includes('executionRecords: records.executionRecords.length'), 'Report artifact must count execution records');
assert(portalApp.includes('auditRecords: records.auditRecords?.length ?? 0'), 'Report artifact must count audit records');
assert(
  portalApp.includes('buildLedgerEntries(actionRecords(status), records.auditRecords ?? [], { sample: false })'),
  'Report artifact must be derived from the same action/audit ledger source',
);
assert(portalApp.includes('.slice(-24)'), 'Report artifact must keep a bounded recent ledger summary instead of dumping unbounded records');
assert(portalApp.includes('ledgerTargetLabel(entry)'), 'Report artifact ledger entries must expose readable targets');
assert(portalApp.includes('ledgerActionLabel(entry.action)'), 'Report artifact ledger entries must expose readable action labels');
assert(portalApp.includes('ledgerResultLabel(entry.result)'), 'Report artifact ledger entries must expose readable result labels');
assert(portalApp.includes('reportJudgement: reportJudgement(report, rows, options)'), 'Report artifact must preserve report judgement');
assert(portalApp.includes('executiveSummary: reportExecutiveSummary(report, rows, options)'), 'Report artifact must preserve executive summary');
assert(portalApp.includes('requiredData: report.requiredData'), 'Report artifact must preserve required data contract');
assert(portalApp.includes('sourceStatus: {'), 'Report artifact must include source capability status');
assert(portalApp.includes('mutationsEnabled: status.spec.capabilities.mutationsEnabled'), 'Report artifact must include mutation capability state');
assert(portalApp.includes('recordStoreEnabled: status.spec.capabilities.recordStoreEnabled'), 'Report artifact must include record store state');
assert(portalApp.includes('stripPublicWebUrls(String(value ?? \'\'))'), 'Report text compaction must strip public web URLs from report rows');

assert(portalApp.includes('const downloadJsonContent ='), 'Report center must provide JSON download helper');
assert(portalApp.includes('const downloadGeneratedArtifact ='), 'Generated report artifact download handler must exist');
assert(portalApp.includes('onDownloadArtifact={downloadGeneratedArtifact}'), 'Report viewer drawer must receive artifact download handler');
assert(portalApp.includes('산출물 JSON'), 'Report viewer must expose a product-language JSON artifact download button');
assert(portalApp.includes('report-history-actions'), 'Report history must expose per-report artifact actions');
assert(portalApp.includes('보고서 메타데이터, 증거 패키지, 조치/감사 요약 포함'), 'Export settings must describe the JSON artifact contents');

assert(portalCss.includes('.report-history-actions'), 'Report history action layout CSS must exist');
assert(
  /grid-template-columns:\s*96px minmax\(150px,\s*1\.2fr\) minmax\(130px,\s*1fr\) 70px 82px 132px;/.test(portalCss),
  'Report history table must reserve enough width for Open + JSON actions',
);
assert(portalCss.includes('.report-history-actions .portal-button'), 'Report history JSON buttons must have stable compact button CSS');

console.log('PASS verify-v029-report-artifact');
