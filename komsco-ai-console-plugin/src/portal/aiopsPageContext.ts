export type RcaViewContextInput = {
  caseHeader: {
    baseline: string;
    caseState: string;
    family: string;
    finding: string;
    issueLine: string;
    metrics: Array<{ label: string; value: string }>;
    scope: string;
    title: string;
  };
  caseId: string;
  cluster: string;
  dataSource: 'live' | 'sample';
  evidence: Array<Record<string, unknown>>;
  findings: Array<Record<string, unknown>>;
  issueType: string;
  runbookGates: Array<Record<string, unknown>>;
  selectedIssue?: Record<string, unknown>;
  timeline: Array<Record<string, unknown>>;
};

export const buildRcaViewPageContext = (input: RcaViewContextInput): Record<string, unknown> => ({
  aiopsViewContext: {
    case: {
      baseline: input.caseHeader.baseline,
      caseId: input.caseId,
      caseState: input.caseHeader.caseState,
      family: input.caseHeader.family,
      issueLine: input.caseHeader.issueLine,
      issueType: input.issueType,
      metrics: input.caseHeader.metrics,
      scope: input.caseHeader.scope,
      title: input.caseHeader.title,
    },
    cluster: input.cluster,
    dataSource: input.dataSource,
    evidencePolicy: input.dataSource === 'sample'
      ? 'display_sample_only_not_operational_evidence'
      : 'live_dashboard_context',
    evidence: input.evidence,
    findings: input.findings,
    pageTitle: 'RCA 센터',
    route: '/dashboards/aiops/audit',
    runbookGates: input.runbookGates,
    selectedIssue: input.selectedIssue,
    summary: input.caseHeader.finding,
    timeline: input.timeline,
  },
});
