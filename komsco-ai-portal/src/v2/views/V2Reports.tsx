// v1 src/App.tsx의 ReportsView/ReportViewerDrawer를 복사한 ver.2 사본.
// 보고서 생성(HTML/PDF) 로직은 v1과 동일하게 유지하고, 겉 레이아웃만 v2 토큰으로 스타일한다.
import React from 'react';
import { BarChart3, FileText, GitBranch, X } from 'lucide-react';
import { StatusBadge, severityLabel } from '../../portalBadges';
import type { ClusterSummary, AiopsRuntimeStatus, Severity } from '../../types';
import type { V2Runtime } from '../V2App';
import { Card } from '../components/primitives';
import {
  actionRecords,
  buildQueues,
  clusterLabel,
  formatTime,
  reportHealthLabel,
  reportPrimarySignal,
  reportSecondarySignal,
  reportStatusSeverity,
  sampleRcaQueues,
  sampleReportItems,
  sourceLabel,
  type GeneratedReport,
  type ReportBuildOptions,
  type ReportFact,
  type ReportHero,
  type ReportIssueRow,
  type ReportItem,
  type ReportOutputFormat,
  type ReportRecommendation,
  type ReportTableSpec,
} from '../lib/model';

const Panel: React.FC<{
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  title: string;
}> = ({ action, children, className = '', title }) => (
  <Card actions={action} className={className} title={title}>
    {children}
  </Card>
);

const ReportViewerDrawer: React.FC<{
  onClose: () => void;
  onDownloadHtml: (report: GeneratedReport) => void;
  onPrintPdf: (report: GeneratedReport) => void;
  report: GeneratedReport | null;
}> = ({ onClose, onDownloadHtml, onPrintPdf, report }) => (
  <div className={`portal-drawer report-viewer-drawer ${report ? 'is-open' : ''}`} onClick={onClose}>
    <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
      <div className="portal-drawer__head">
        <div>
          <span>보고서 보기</span>
          <strong>{report?.title ?? '생성된 보고서'}</strong>
        </div>
        <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
          <X />
        </button>
      </div>
      <div className="portal-drawer__body">
        {report && (
          <>
            <div className="report-viewer-toolbar">
              <StatusBadge label={`${report.format} 생성 완료`} severity="ok" />
              <span className="report-viewer-meta">{report.reportId} · {report.scope} · {report.time}</span>
              <div className="report-viewer-actions">
                <button className="portal-button" onClick={() => onDownloadHtml(report)} type="button">HTML 다운로드</button>
                <button className="portal-button" onClick={() => onPrintPdf(report)} type="button">PDF 다운로드</button>
              </div>
            </div>
            <iframe className="report-viewer-frame" srcDoc={report.html} title={`${report.title} 미리보기`} />
          </>
        )}
      </div>
    </aside>
  </div>
);

const ReportsView: React.FC<{ status: AiopsRuntimeStatus; summary: ClusterSummary }> = ({ status, summary }) => {
  const auditCount = status.spec.records.auditRecords?.length ?? 0;
  const actionCount = actionRecords(status).length;
  const queues = buildQueues(summary, status);
  const issueOptions = queues.length > 0 ? queues : sampleRcaQueues;
  const [selectedReportId, setSelectedReportId] = React.useState(sampleReportItems[0].id);
  const [selectedIssueId, setSelectedIssueId] = React.useState(issueOptions[0]?.id ?? '');
  const [dataWindow, setDataWindow] = React.useState('today');
  const [outputFormat, setOutputFormat] = React.useState<ReportOutputFormat>('HTML');
  const [selectedSections, setSelectedSections] = React.useState(sampleReportItems[0].sections);
  const [generatedReports, setGeneratedReports] = React.useState<GeneratedReport[]>([]);
  const [historyTab, setHistoryTab] = React.useState<'history' | 'schedule' | 'export'>('history');
  const [openReport, setOpenReport] = React.useState<GeneratedReport | null>(null);
  const selectedIssue = issueOptions.find((item) => item.id === selectedIssueId) ?? issueOptions[0];
  const reports = sampleReportItems.map((report) => {
    if (report.id === 'daily-ops') {
      return { ...report, metric: `건강도 ${summary.healthScore}% · ${reportHealthLabel(summary)}` };
    }
    if (report.id === 'rca-pack') {
      return {
        ...report,
        metric: selectedIssue ? `${selectedIssue.title} 기준` : `감사 ${auditCount} · 조치 ${actionCount}`,
        status: selectedIssue ? '생성 가능' : report.status,
        statusDetail: selectedIssue ? '대상 이슈 선택됨' : report.statusDetail,
      };
    }
    return { ...report, metric: `리소스 이슈 ${summary.resources?.issues ?? 0}건` };
  });
  const selectedReport = reports.find((report) => report.id === selectedReportId) ?? reports[0];
  const dataWindowLabel = dataWindow === 'today'
    ? '오늘 00:00-현재'
    : dataWindow === 'snapshot'
      ? `스냅샷 ${formatTime(summary.updatedAt)}`
      : '최근 24시간';
  const snapshotStamp = summary.updatedAt.slice(0, 16).replace(/[-:T]/g, '') || 'snapshot';
  const sourceSnapshotId = `GWS-${snapshotStamp}`;

  React.useEffect(() => {
    setSelectedIssueId((current) => (issueOptions.some((item) => item.id === current) ? current : issueOptions[0]?.id ?? ''));
  }, [issueOptions]);

  React.useEffect(() => {
    setSelectedSections(selectedReport.sections);
    setOutputFormat('HTML');
  }, [selectedReport.id]);

  const toggleReportSection = (section: string) => {
    setSelectedSections((current) => (
      current.includes(section)
        ? current.filter((item) => item !== section)
        : [...current, section]
    ));
  };

  const escapeHtml = (value: unknown) => String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');

  const currentReportBuildOptions = (
    report: ReportItem = selectedReport,
    format: ReportOutputFormat = outputFormat,
    generatedAt = new Date().toISOString(),
  ): ReportBuildOptions => {
    const generatedStamp = generatedAt.slice(0, 19).replace(/[-:T]/g, '') || snapshotStamp;
    return {
      dataWindowLabel: report.id === selectedReport.id ? dataWindowLabel : report.period,
      generatedAt,
      issue: selectedIssue,
      outputFormat: format,
      reportId: `RPT-${generatedStamp.slice(0, 12)}-${report.id.replace(/-/g, '').toUpperCase().slice(0, 6)}`,
      sections: report.id === selectedReport.id ? [...selectedSections] : [...report.sections],
      sourceSnapshotId,
    };
  };

  const reportCode = (report: ReportItem): string => {
    if (report.id === 'daily-ops') {
      return 'DAILY';
    }
    if (report.id === 'rca-pack') {
      return 'RCA';
    }
    return 'CAPACITY';
  };

  const reportHealthSeverity = (): Severity => {
    if (summary.healthScore >= 90) {
      return 'ok';
    }
    if (summary.healthScore >= 70) {
      return 'warn';
    }
    return 'risk';
  };

  const reportSeverityClass = (severity: Severity): string =>
    severity === 'risk' ? 'danger' : severity === 'warn' ? 'warn' : 'good';

  const compactReportText = (value: unknown, maxLength = 86): string => {
    const text = String(value ?? '').replace(/\s+/g, ' ').trim();
    return text.length > maxLength ? `${text.slice(0, maxLength - 1)}…` : text;
  };

  const reportIssueRows = (report: ReportItem, options: ReportBuildOptions): ReportIssueRow[] => {
    if (report.id === 'rca-pack') {
      const issue = options.issue ?? selectedIssue;
      const evidenceRows = (issue?.evidence ?? []).slice(0, 4).map((evidence, index): ReportIssueRow => ({
        detail: index === 0 ? compactReportText(issue?.detail ?? '선택 이슈 상세 확인 필요') : '선택 이슈의 원인 판단에 포함된 증거입니다.',
        resource: `증거 ${String(index + 1).padStart(2, '0')}`,
        scope: issue?.source ? sourceLabel(issue.source) : issue?.category ?? 'Evidence',
        severity: issue?.severity ?? 'warn',
        signal: compactReportText(evidence, 58),
      }));

      const decisionRows: ReportIssueRow[] = [
        {
          detail: issue?.target ? `대상 ${issue.target} 기준 영향 범위를 확인합니다.` : '선택 이슈 대상 리소스 기준으로 영향 범위를 확인합니다.',
          resource: '대상 리소스',
          scope: issue?.category ?? 'RCA Target',
          severity: issue?.severity ?? 'warn',
          signal: compactReportText(issue?.title ?? '이슈 미선택', 58),
        },
        {
          detail: '실행/승인/감사 기록을 RCA 증거 패키지에 포함합니다.',
          resource: '감사 기록',
          scope: 'Audit ledger',
          severity: actionCount > 0 || auditCount > 0 ? 'warn' : 'ok',
          signal: `실행 ${actionCount} · 감사 ${auditCount}`,
        },
      ];

      return [...decisionRows, ...evidenceRows].slice(0, 6);
    }

    if (report.id === 'monthly-capacity') {
      const resourceRows = (summary.resources?.items ?? []).map((resource): ReportIssueRow => ({
        detail: resource.issues > 0
          ? `${resource.kind} 계열 반복 이슈 ${resource.issues}건을 용량/가용성 후보로 분류합니다.`
          : `${resource.kind} 계열은 현재 기준 안정 범위입니다.`,
        resource: resource.name,
        scope: resource.kind,
        severity: resource.severity,
        signal: resource.ready !== undefined && resource.total ? `${resource.ready}/${resource.total}` : compactReportText(resource.score, 44),
      }));

      const workloadRows: ReportIssueRow[] = [
        {
          detail: `AIOps 워크로드 ${summary.aiopsWorkloads?.total ?? 0}개, 이슈 ${summary.aiopsWorkloads?.issues ?? 0}건 기준입니다.`,
          resource: 'AIOps workloads',
          scope: 'Deployment / DaemonSet',
          severity: (summary.aiopsWorkloads?.issues ?? 0) > 0 ? 'warn' : 'ok',
          signal: `${summary.aiopsWorkloads?.total ?? 0} workloads`,
        },
        {
          detail: `노드 pressure ${summary.nodes.pressureCount}건, NotReady ${summary.nodes.notReady}건을 월간 추세 후보로 기록합니다.`,
          resource: 'Node capacity',
          scope: 'Cluster nodes',
          severity: summary.nodes.notReady > 0 || summary.nodes.pressureCount > 0 ? 'risk' : 'ok',
          signal: `${summary.nodes.ready}/${summary.nodes.total} Ready`,
        },
      ];

      return [...resourceRows, ...workloadRows]
        .sort((left, right) => {
          const weight: Record<Severity, number> = { risk: 0, warn: 1, ok: 2 };
          return weight[left.severity] - weight[right.severity];
        })
        .slice(0, 6);
    }

    const resourceRows = (summary.resources?.items ?? [])
      .filter((resource) => resource.severity !== 'ok' || resource.issues > 0)
      .map((resource): ReportIssueRow => ({
        detail: compactReportText(resource.score || resource.detail || `${resource.kind} 상태 확인 필요`),
        resource: `${resource.name} ${resource.severity === 'risk' ? 'degraded' : 'drift'}`,
        scope: resource.kind,
        severity: resource.severity,
        signal: resource.ready !== undefined && resource.total ? `Ready ${resource.ready}/${resource.total}` : compactReportText(resource.score, 42),
      }));

    const queueRows = issueOptions
      .filter((item) => report.id !== 'daily-ops' || item.severity === 'risk')
      .slice(0, 3)
      .map((item): ReportIssueRow => ({
        detail: compactReportText(item.detail),
        resource: item.title,
        scope: item.category ?? sourceLabel(item.source),
        severity: item.severity,
        signal: compactReportText(item.evidence[0] ?? item.updatedAt ?? '증거 확인 필요', 46),
      }));

    const selectedIssueRow: ReportIssueRow[] =
      report.id === 'rca-pack' && options.issue
        ? [{
            detail: compactReportText(options.issue.detail),
            resource: options.issue.title,
            scope: options.issue.category ?? sourceLabel(options.issue.source),
            severity: options.issue.severity,
            signal: compactReportText(options.issue.evidence[0] ?? options.issue.updatedAt ?? '증거 확인 필요', 46),
          }]
        : [];

    const merged = [...selectedIssueRow, ...resourceRows, ...queueRows];
    const uniqueRows = merged.filter((row, index, rows) =>
      rows.findIndex((candidate) => candidate.resource === row.resource && candidate.signal === row.signal) === index,
    );

    if (uniqueRows.length > 0) {
      return uniqueRows
        .sort((left, right) => {
          const weight: Record<Severity, number> = { risk: 0, warn: 1, ok: 2 };
          return weight[left.severity] - weight[right.severity];
        })
        .slice(0, 5);
    }

    return [{
      detail: '현재 Gateway 요약 기준으로 위험 또는 주의 리소스가 없습니다.',
      resource: 'Cluster baseline',
      scope: 'Cluster',
      severity: 'ok',
      signal: `Health ${summary.healthScore}%`,
    }];
  };

  const reportHero = (report: ReportItem, rows: ReportIssueRow[], options: ReportBuildOptions): ReportHero => {
    if (report.id === 'rca-pack') {
      const severity = options.issue?.severity ?? rows[0]?.severity ?? 'warn';
      return {
        label: 'RCA Case Severity',
        status: options.issue ? `${options.issue.category ?? '이슈'} 분석 대상` : '이슈 선택 필요',
        tone: severity,
        value: severityLabel[severity],
      };
    }

    if (report.id === 'monthly-capacity') {
      const capacityWarnings = rows.filter((row) => row.severity !== 'ok').length;
      return {
        label: 'Capacity Watch',
        status: capacityWarnings > 0 ? '계획 후보 존재' : '안정 범위',
        tone: capacityWarnings > 0 ? 'warn' : 'ok',
        value: String(capacityWarnings),
        unit: '건',
      };
    }

    const healthSeverity = reportHealthSeverity();
    return {
      label: 'Cluster Health',
      status: `${reportHealthLabel(summary)} 상태`,
      tone: healthSeverity,
      value: String(summary.healthScore),
      unit: '%',
    };
  };

  const reportCoverDescription = (report: ReportItem): string => {
    if (report.id === 'rca-pack') {
      return '선택 이슈의 증거, 영향 경로, 감사 기록, 다음 판단 단계를 묶은 RCA 제출용 산출물입니다.';
    }
    if (report.id === 'monthly-capacity') {
      return '노드, 워크로드, 컨트롤러, 스토리지 계열 신호를 용량 계획 관점으로 정리한 월간 리소스 보고서입니다.';
    }
    return '운영 상태, 주요 신호, 권장 확인 항목을 요약한 일일 운영 브리핑입니다.';
  };

  const reportSummaryMinis = (report: ReportItem, rows: ReportIssueRow[], options: ReportBuildOptions): Array<{ label: string; value: string }> => {
    if (report.id === 'rca-pack') {
      return [
        { label: '대상 이슈', value: options.issue?.category ?? 'RCA' },
        { label: '증거 항목', value: String(options.issue?.evidence.length ?? rows.length) },
        { label: '실행 기록', value: String(actionCount) },
        { label: '감사 기록', value: String(auditCount) },
      ];
    }
    if (report.id === 'monthly-capacity') {
      return [
        { label: '리소스 이슈', value: String(summary.resources?.issues ?? 0) },
        { label: 'AIOps 워크로드', value: String(summary.aiopsWorkloads?.total ?? 0) },
        { label: '노드 Ready', value: `${summary.nodes.ready}/${summary.nodes.total}` },
        { label: 'OpenShift', value: summary.version.version ?? '-' },
      ];
    }
    return [
      { label: '리소스 이슈', value: String(summary.resources?.issues ?? rows.length) },
      { label: '오퍼레이터 저하', value: String(summary.operators.degraded) },
      { label: 'OpenShift', value: summary.version.version ?? '-' },
      { label: '최근 스냅샷', value: formatTime(summary.updatedAt) },
    ];
  };

  const reportFacts = (report: ReportItem, rows: ReportIssueRow[]): ReportFact[] => {
    const riskCount = rows.filter((row) => row.severity === 'risk').length;
    const warnCount = rows.filter((row) => row.severity === 'warn').length;

    if (report.id === 'rca-pack') {
      return [
        { label: 'Case Severity', value: severityLabel[(selectedIssue?.severity ?? 'warn')], hint: selectedIssue?.category ?? '선택 이슈', tone: selectedIssue?.severity === 'risk' ? 'bad' : 'warn' },
        { label: 'Evidence', value: String(selectedIssue?.evidence.length ?? rows.length), hint: '증거 항목', tone: rows.length > 0 ? 'warn' : 'good' },
        { label: 'Actions', value: String(actionCount), hint: '실행/승인 기록', tone: actionCount > 0 ? 'warn' : 'good' },
        { label: 'Audit', value: String(auditCount), hint: '감사 이벤트', tone: auditCount > 0 ? 'good' : 'warn' },
      ];
    }

    if (report.id === 'monthly-capacity') {
      return [
        { label: 'Resource Issues', value: String(summary.resources?.issues ?? 0), hint: '용량 후보', tone: (summary.resources?.issues ?? 0) > 0 ? 'warn' : 'good' },
        { label: 'Workloads', value: String(summary.aiopsWorkloads?.total ?? 0), hint: 'AIOps 배포 대상', tone: (summary.aiopsWorkloads?.issues ?? 0) > 0 ? 'warn' : 'good' },
        { label: 'Nodes', value: `${summary.nodes.ready}/${summary.nodes.total}`, hint: 'Ready 상태', tone: summary.nodes.notReady > 0 ? 'bad' : 'good' },
        { label: 'Pressure', value: String(summary.nodes.pressureCount), hint: '노드 pressure', tone: summary.nodes.pressureCount > 0 ? 'bad' : 'good' },
      ];
    }

    return [
      { label: 'Health', value: `${summary.healthScore}%`, hint: '시스템 건강도', tone: reportHealthSeverity() === 'ok' ? 'good' : reportHealthSeverity() === 'warn' ? 'warn' : 'bad' },
      { label: 'Critical Signals', value: String(riskCount + warnCount), hint: '위험/주의 신호', tone: riskCount > 0 ? 'bad' : warnCount > 0 ? 'warn' : 'good' },
      { label: 'Resource Issues', value: String(summary.resources?.issues ?? 0), hint: 'Gateway 요약', tone: (summary.resources?.issues ?? 0) > 0 ? 'warn' : 'good' },
      { label: 'Nodes', value: `${summary.nodes.ready}/${summary.nodes.total}`, hint: 'Ready 상태', tone: summary.nodes.notReady > 0 ? 'bad' : 'good' },
    ];
  };

  const reportTableSpec = (report: ReportItem): ReportTableSpec => {
    if (report.id === 'rca-pack') {
      return {
        detailHeader: '판단 근거',
        resourceHeader: '증거',
        statusHeader: '상태',
        title: '증거 패키지',
      };
    }
    if (report.id === 'monthly-capacity') {
      return {
        detailHeader: '용량 판단',
        resourceHeader: '리소스 그룹',
        statusHeader: '상태',
        title: '리소스 및 용량 후보',
      };
    }
    return {
      detailHeader: '핵심 신호',
      resourceHeader: '리소스',
      statusHeader: '상태',
      title: '주요 이슈',
    };
  };

  const reportRecommendationTitle = (report: ReportItem): string => {
    if (report.id === 'rca-pack') {
      return 'RCA 판단 게이트';
    }
    if (report.id === 'monthly-capacity') {
      return '용량 계획 권장';
    }
    return '실행 권장';
  };

  const reportRecommendations = (report: ReportItem, rows: ReportIssueRow[], options: ReportBuildOptions): ReportRecommendation[] => {
    if (report.id === 'rca-pack') {
      return [
        {
          title: '선택 이슈의 증거 타임라인 확정',
          description: `${options.issue?.title ?? '선택된 이슈'} 기준으로 이벤트, 리소스 상태, 실행 기록의 시간 순서를 먼저 고정합니다.`,
        },
        {
          title: '서비스 영향 경로와 Owner chain 대조',
          description: 'Route, Service, Deployment, ReplicaSet, Pod 흐름에서 실제 실패 지점과 파생 신호를 분리합니다.',
        },
        {
          title: '감사용 RCA 증거 패키지 보관',
          description: '최종 원인 후보, 배제 근거, 승인/실행 기록을 보고서 이력에 남겨 재현 가능하게 관리합니다.',
        },
      ];
    }

    if (report.id === 'monthly-capacity') {
      return [
        {
          title: '상위 리소스 이슈의 30일 추세 확인',
          description: 'Pod, Deployment, ReplicaSet, Node, PVC 계열의 반복 이슈를 용량 계획 후보로 분류합니다.',
        },
        {
          title: 'Ready/Desired 차이가 반복되는 워크로드 선별',
          description: '일시 장애와 구조적 부족을 구분하기 위해 컨트롤러별 가용성 변동을 누적 비교합니다.',
        },
        {
          title: '증설 또는 제한값 조정 후보 기록',
          description: '리소스 요청/제한, HPA 정책, 스토리지 사용량을 함께 확인해 변경 후보를 남깁니다.',
        },
      ];
    }

    const primaryRow = rows.find((row) => row.severity === 'risk') ?? rows[0];
    return [
      {
        title: 'Pod 이벤트와 컨테이너 상태 우선 확인',
        description: `${primaryRow.resource} 신호를 기준으로 BackOff, Failed, ProbeError, ImagePullBackOff 이벤트를 먼저 분류합니다.`,
      },
      {
        title: '컨트롤러 파생 신호 분리',
        description: 'Deployment / ReplicaSet 가용 차이가 Pod readiness에서 파생된 것인지 Owner chain 기준으로 확인합니다.',
      },
      {
        title: '필요 시 RCA 증거 패키지 생성',
        description: '영향 후보가 지속되면 선택 이슈 기준으로 증거, 의존성 경로, 실행 기록을 감사 가능한 산출물로 보관합니다.',
      },
    ];
  };

  const reportExecutiveSummary = (report: ReportItem, rows: ReportIssueRow[], options: ReportBuildOptions): string => {
    if (report.id === 'rca-pack') {
      return `${options.issue?.title ?? '선택된 이슈'} 기준으로 증거 ${options.issue?.evidence.length ?? rows.length}건, 실행 기록 ${actionCount}건, 감사 기록 ${auditCount}건을 묶었습니다. 이 보고서는 상태 요약보다 원인 후보, 파생 영향, 보류 판단을 감사 가능하게 남기는 데 초점을 둡니다.`;
    }
    if (report.id === 'monthly-capacity') {
      return `월간 리소스 관점에서 리소스 이슈 ${summary.resources?.issues ?? 0}건, AIOps 워크로드 ${summary.aiopsWorkloads?.total ?? 0}개, 노드 Ready ${summary.nodes.ready}/${summary.nodes.total} 상태를 검토했습니다. 반복 이슈 후보와 증설/튜닝 검토 대상을 분리해 용량 계획 입력값으로 정리합니다.`;
    }
    return `클러스터 건강도는 ${summary.healthScore}%로 ${reportHealthLabel(summary)} 범위입니다. 오퍼레이터 저하 ${summary.operators.degraded}건, 리소스 이슈 ${summary.resources?.issues ?? 0}건, 노드 Ready ${summary.nodes.ready}/${summary.nodes.total} 상태를 기준으로 운영 브리핑을 구성했습니다.`;
  };

  const reportJudgement = (report: ReportItem, rows: ReportIssueRow[], options: ReportBuildOptions): string => {
    const riskCount = rows.filter((row) => row.severity === 'risk').length;
    if (report.id === 'rca-pack') {
      return `${options.issue?.title ?? '선택 이슈'}는 증거 기준의 RCA 판단 대상으로 분류됩니다. 현재 문서는 즉시 조치 지시서가 아니라 원인 후보와 파생 영향, 감사 가능한 증거를 고정하는 패키지입니다.`;
    }
    if (report.id === 'monthly-capacity') {
      const capacityCandidates = rows.filter((row) => row.severity !== 'ok').length;
      return `월간 관점에서는 ${capacityCandidates}개 리소스 그룹을 용량/안정성 검토 후보로 봅니다. 즉시 장애 대응보다 반복 이슈, Ready/Desired 차이, 노드 pressure 추세를 다음 계획 주기에 반영하는 것이 핵심입니다.`;
    }
    if (riskCount > 0) {
      return `현재 상태는 운영 가능 범위이나 위험 신호 ${riskCount}건이 존재합니다. 운영자는 영향 후보 리소스의 이벤트와 컨테이너 상태를 먼저 검토한 뒤, 필요 시 RCA 센터로 전환하는 것이 좋습니다.`;
    }
    if (summary.healthScore < 90) {
      return '현재 상태는 주의 범위입니다. 반복되는 경고 신호가 있는지 리소스별 최근 이벤트와 컨트롤러 가용성을 확인해야 합니다.';
    }
    return '현재 상태는 정상 범위입니다. 정기 운영 브리핑 관점에서 주요 지표와 최근 스냅샷을 보관하면 됩니다.';
  };

  const reportHtml = (report: ReportItem, options: ReportBuildOptions = currentReportBuildOptions(report)) => {
    const rows = reportIssueRows(report, options);
    const recommendations = reportRecommendations(report, rows, options);
    const hero = reportHero(report, rows, options);
    const facts = reportFacts(report, rows);
    const minis = reportSummaryMinis(report, rows, options);
    const tableSpec = reportTableSpec(report);
    const reportTitle = escapeHtml(report.title);
    const reportSubtitle = escapeHtml(report.subtitle);
    const reportPeriod = escapeHtml(options.dataWindowLabel);
    const reportCluster = escapeHtml(clusterLabel(summary));
    const generatedAt = escapeHtml(formatTime(options.generatedAt));
    const outputLabel = `${options.outputFormat} · HTML/PDF 지원`;
    const issueRowsMarkup = rows.map((row) => `
                <tr>
                  <td><span class="sev ${reportSeverityClass(row.severity)}">${escapeHtml(severityLabel[row.severity])}</span></td>
                  <td><div class="resource-name">${escapeHtml(row.resource)}</div><div class="resource-sub">${escapeHtml(row.scope)}</div></td>
                  <td><span class="metric">${escapeHtml(row.signal)}</span><div class="resource-sub">${escapeHtml(row.detail)}</div></td>
                </tr>`).join('');
    const recommendationMarkup = recommendations.map((recommendation, index) => `
              <div class="rec">
                <div class="rec-num">${String(index + 1).padStart(2, '0')}</div>
                <div><div class="rec-title">${escapeHtml(recommendation.title)}</div><div class="rec-desc">${escapeHtml(recommendation.description)}</div></div>
              </div>`).join('');
    const miniMarkup = minis.map((item) => `<div class="mini"><b>${escapeHtml(item.value)}</b><span>${escapeHtml(item.label)}</span></div>`).join('');
    const factMarkup = facts.map((fact) => `
          <div class="fact"><div class="label">${escapeHtml(fact.label)}</div><div class="value ${fact.tone}">${escapeHtml(fact.value)}</div><div class="hint">${escapeHtml(fact.hint)}</div></div>`).join('');

    return `<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>AIOps for OCP · ${reportTitle}</title>
  <style>
    :root {
      --ink: #0f172a;
      --muted: #64748b;
      --line: #dbe5f1;
      --soft: #f6f9fc;
      --panel: #ffffff;
      --blue: #2563eb;
      --green: #10b981;
      --amber: #f59e0b;
      --red: #ef4444;
      --shadow: 0 22px 70px rgba(15, 23, 42, .12);
      --radius: 18px;
      --mono: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
      --sans: Pretendard, Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif;
    }
    * { box-sizing: border-box; }
    html, body { margin: 0; padding: 0; }
    body {
      min-height: 100vh;
      color: var(--ink);
      font-family: var(--sans);
      background:
        radial-gradient(circle at 14% 0%, rgba(37, 99, 235, .12), transparent 34%),
        radial-gradient(circle at 88% 5%, rgba(16, 185, 129, .10), transparent 35%),
        linear-gradient(180deg, #f8fbff 0%, #eef4fb 100%);
      padding: 48px 28px;
    }
    .page {
      width: min(1120px, 100%);
      margin: 0 auto;
      overflow: hidden;
      background: var(--panel);
      border: 1px solid rgba(148, 163, 184, .35);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }
    .cover {
      position: relative;
      padding: 34px 38px 30px;
      color: #e5edff;
      background:
        linear-gradient(135deg, rgba(37, 99, 235, .95), rgba(14, 165, 233, .65) 38%, rgba(11, 18, 32, 1) 100%),
        linear-gradient(90deg, rgba(255,255,255,.10) 1px, transparent 1px),
        linear-gradient(180deg, rgba(255,255,255,.08) 1px, transparent 1px);
      background-size: auto, 28px 28px, 28px 28px;
    }
    .cover:after {
      position: absolute;
      inset: 0;
      background: radial-gradient(circle at 78% 25%, rgba(34, 211, 238, .28), transparent 24%);
      content: "";
      pointer-events: none;
    }
    .cover-inner { position: relative; z-index: 1; }
    .brand-row {
      display: flex;
      gap: 24px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 28px;
    }
    .brand {
      display: flex;
      gap: 12px;
      align-items: center;
      font-weight: 900;
      letter-spacing: .02em;
    }
    .mark {
      display: grid;
      width: 34px;
      height: 34px;
      background: linear-gradient(135deg, #ff4757, #ff7a59);
      border-radius: 10px;
      box-shadow: 0 10px 24px rgba(239, 68, 68, .35);
      place-items: center;
    }
    .mark:before {
      width: 15px;
      height: 15px;
      border: 2px solid rgba(255,255,255,.88);
      border-radius: 4px;
      content: "";
      transform: rotate(45deg);
    }
    .report-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      justify-content: flex-end;
      color: rgba(226, 232, 240, .92);
      font-size: 12px;
    }
    .pill {
      display: inline-flex;
      gap: 7px;
      align-items: center;
      padding: 7px 10px;
      white-space: nowrap;
      background: rgba(255,255,255,.10);
      border: 1px solid rgba(255,255,255,.20);
      border-radius: 999px;
      backdrop-filter: blur(10px);
    }
    .dot {
      width: 7px;
      height: 7px;
      background: var(--green);
      border-radius: 50%;
      box-shadow: 0 0 0 4px rgba(16,185,129,.16);
    }
    .eyebrow {
      margin: 0 0 6px;
      color: rgba(219, 234, 254, .88);
      font-size: 13px;
      font-weight: 900;
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    h1 {
      margin: 0;
      color: #ffffff;
      font-size: 38px;
      line-height: 1.12;
      letter-spacing: -.03em;
    }
    .subtitle {
      margin: 12px 0 0;
      color: rgba(226, 232, 240, .9);
      font-size: 15px;
      line-height: 1.55;
    }
    .hero-grid {
      display: grid;
      grid-template-columns: 1.05fr .95fr;
      gap: 18px;
      margin-top: 26px;
    }
    .score-card, .summary-card {
      padding: 18px;
      background: rgba(255,255,255,.10);
      border: 1px solid rgba(255,255,255,.18);
      border-radius: 18px;
      backdrop-filter: blur(14px);
    }
    .score-line {
      display: flex;
      gap: 20px;
      align-items: flex-end;
      justify-content: space-between;
      margin-bottom: 14px;
    }
    .score-label {
      color: rgba(226,232,240,.8);
      font-size: 12px;
      font-weight: 900;
      letter-spacing: .08em;
      text-transform: uppercase;
    }
    .score-value {
      color: #ffffff;
      font-size: 52px;
      font-weight: 950;
      line-height: .95;
      letter-spacing: -.05em;
    }
    .score-value span { color: rgba(255,255,255,.70); font-size: 22px; letter-spacing: -.02em; }
    .health-chip {
      padding: 8px 11px;
      font-size: 12px;
      font-weight: 900;
      white-space: nowrap;
      border-radius: 999px;
    }
    .health-chip.good { color: #bbf7d0; background: rgba(16,185,129,.12); border: 1px solid rgba(16,185,129,.28); }
    .health-chip.warn { color: #fde68a; background: rgba(245,158,11,.14); border: 1px solid rgba(245,158,11,.32); }
    .health-chip.danger { color: #fecaca; background: rgba(239,68,68,.16); border: 1px solid rgba(239,68,68,.34); }
    .spark {
      width: 100%;
      height: 42px;
      margin-top: 4px;
    }
    .summary-card h2 {
      margin: 0 0 12px;
      color: #ffffff;
      font-size: 15px;
    }
    .summary-card p {
      margin: 0 0 10px;
      color: rgba(226, 232, 240, .92);
      font-size: 13px;
      line-height: 1.55;
    }
    .summary-points {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 10px;
      margin-top: 14px;
    }
    .mini {
      padding: 12px;
      background: rgba(15, 23, 42, .22);
      border: 1px solid rgba(255,255,255,.13);
      border-radius: 14px;
    }
    .mini b { display: block; color: #ffffff; font-size: 18px; line-height: 1; }
    .mini span { display: block; margin-top: 5px; color: rgba(226, 232, 240, .78); font-size: 11px; }
    main { padding: 30px 38px 36px; }
    .section { margin-top: 26px; }
    .section:first-child { margin-top: 0; }
    .section-head {
      display: flex;
      gap: 16px;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 12px;
    }
    .section-title {
      display: flex;
      gap: 9px;
      align-items: center;
      font-size: 16px;
      font-weight: 950;
      letter-spacing: -.02em;
    }
    .section-title:before {
      width: 9px;
      height: 9px;
      background: var(--blue);
      border-radius: 3px;
      box-shadow: 0 0 0 4px rgba(37,99,235,.12);
      content: "";
    }
    .section-note { color: var(--muted); font-size: 12px; }
    .facts {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
    }
    .fact {
      padding: 15px 15px 14px;
      background: linear-gradient(180deg, #fff, #f8fbff);
      border: 1px solid var(--line);
      border-radius: 16px;
    }
    .fact .label {
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      letter-spacing: .06em;
      text-transform: uppercase;
    }
    .fact .value {
      margin-top: 8px;
      color: var(--ink);
      font-size: 21px;
      font-weight: 950;
      letter-spacing: -.03em;
    }
    .fact .value.good { color: #059669; }
    .fact .value.warn { color: #d97706; }
    .fact .value.bad { color: #dc2626; }
    .fact .hint { margin-top: 7px; color: var(--muted); font-size: 12px; }
    .two-col {
      display: grid;
      grid-template-columns: 1.05fr .95fr;
      gap: 18px;
    }
    .panel {
      overflow: hidden;
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: var(--radius);
    }
    .panel-body { padding: 18px; }
    .callout {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 13px;
      padding: 16px;
      background: linear-gradient(135deg, #eff6ff, #fff 70%);
      border: 1px solid #bfdbfe;
      border-radius: 16px;
    }
    .callout .icon {
      display: grid;
      width: 32px;
      height: 32px;
      color: #1d4ed8;
      font-weight: 950;
      background: #dbeafe;
      border-radius: 10px;
      place-items: center;
    }
    .callout strong { display: block; margin-bottom: 5px; font-size: 14px; }
    .callout p { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.55; }
    .issue-table {
      width: 100%;
      margin-top: 12px;
      font-size: 13px;
      border-collapse: separate;
      border-spacing: 0;
    }
    .issue-table th {
      padding: 12px 14px;
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      text-align: left;
      text-transform: uppercase;
      letter-spacing: .06em;
      background: #f8fafc;
      border-bottom: 1px solid var(--line);
    }
    .issue-table td {
      padding: 14px;
      vertical-align: top;
      border-bottom: 1px solid #edf2f7;
    }
    .issue-table tr:last-child td { border-bottom: 0; }
    .sev {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 46px;
      min-height: 24px;
      padding: 5px 8px;
      font-size: 11.5px;
      font-weight: 950;
      line-height: 1.2;
      border-radius: 999px;
      white-space: nowrap;
    }
    .sev.danger { color: #b91c1c; background: #fee2e2; }
    .sev.warn { color: #92400e; background: #fef3c7; }
    .sev.good { color: #047857; background: #d1fae5; }
    .resource-name { color: var(--ink); font-weight: 900; }
    .resource-sub { margin-top: 4px; color: var(--muted); font-size: 12px; line-height: 1.45; }
    .metric { color: #334155; font-family: var(--mono); font-weight: 800; }
    .rec-list {
      display: grid;
      gap: 10px;
      margin-top: 12px;
    }
    .rec {
      display: grid;
      grid-template-columns: 32px 1fr;
      gap: 12px;
      padding: 13px;
      background: #ffffff;
      border: 1px solid var(--line);
      border-radius: 14px;
    }
    .rec-num {
      display: grid;
      width: 28px;
      height: 28px;
      color: var(--blue);
      font-size: 12px;
      font-weight: 950;
      background: #eff6ff;
      border-radius: 50%;
      place-items: center;
    }
    .rec-title { font-size: 13px; font-weight: 900; }
    .rec-desc { margin-top: 3px; color: var(--muted); font-size: 12px; line-height: 1.5; }
    .meta-grid {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
      margin-top: 12px;
    }
    .meta-item {
      padding: 13px;
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 14px;
    }
    .meta-item span {
      display: block;
      color: var(--muted);
      font-size: 11px;
      font-weight: 900;
      letter-spacing: .05em;
      text-transform: uppercase;
    }
    .meta-item b { display: block; margin-top: 7px; color: var(--ink); font-size: 13px; word-break: break-word; }
    .footer {
      display: flex;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
      margin-top: 32px;
      padding-top: 18px;
      color: var(--muted);
      font-size: 12px;
      border-top: 1px solid var(--line);
    }
    .footer b { color: var(--ink); }
    @media print {
      body { padding: 0; background: #ffffff; }
      .page { width: 100%; border: 0; border-radius: 0; box-shadow: none; }
      .cover { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .panel, .fact, .callout, .rec { break-inside: avoid; }
    }
    @media (max-width: 860px) {
      body { padding: 20px; }
      .cover, main { padding-left: 22px; padding-right: 22px; }
      .brand-row, .section-head, .footer { align-items: flex-start; flex-direction: column; }
      .hero-grid, .two-col, .facts, .meta-grid { grid-template-columns: 1fr; }
      h1 { font-size: 30px; }
      .score-value { font-size: 44px; }
    }
  </style>
</head>
<body>
  <article class="page">
    <header class="cover">
      <div class="cover-inner">
        <div class="brand-row">
          <div class="brand"><span class="mark"></span><span>AIOps for OCP</span></div>
          <div class="report-meta">
            <span class="pill"><span class="dot"></span>${summary.apiUrl ? 'Gateway connected' : 'Gateway pending'}</span>
            <span class="pill">${escapeHtml(options.outputFormat)} Report</span>
            <span class="pill">${escapeHtml(options.reportId)}</span>
          </div>
        </div>
        <p class="eyebrow">${reportSubtitle}</p>
        <h1>${reportTitle}</h1>
        <p class="subtitle">${reportCluster} · ${reportPeriod} · ${escapeHtml(reportCoverDescription(report))}</p>
        <section class="hero-grid" aria-label="Report overview">
          <div class="score-card">
            <div class="score-line">
              <div>
                <div class="score-label">${escapeHtml(hero.label)}</div>
                <div class="score-value">${escapeHtml(hero.value)}${hero.unit ? `<span>${escapeHtml(hero.unit)}</span>` : ''}</div>
              </div>
              <div class="health-chip ${reportSeverityClass(hero.tone)}">${escapeHtml(hero.status)}</div>
            </div>
            <svg class="spark" viewBox="0 0 420 42" preserveAspectRatio="none" aria-hidden="true">
              <defs>
                <linearGradient id="sparkFill" x1="0" x2="1" y1="0" y2="0">
                  <stop offset="0%" stop-color="#22d3ee" stop-opacity=".28" />
                  <stop offset="100%" stop-color="#10b981" stop-opacity=".28" />
                </linearGradient>
              </defs>
              <path d="M0,34 L35,27 L70,29 L105,20 L140,31 L175,12 L210,24 L245,8 L280,17 L315,10 L350,13 L385,6 L420,0 L420,42 L0,42 Z" fill="url(#sparkFill)" />
              <path d="M0,34 L35,27 L70,29 L105,20 L140,31 L175,12 L210,24 L245,8 L280,17 L315,10 L350,13 L385,6 L420,0" fill="none" stroke="#86efac" stroke-width="3" stroke-linecap="round" />
            </svg>
          </div>
          <div class="summary-card">
            <h2>Executive Summary</h2>
            <p>${escapeHtml(reportExecutiveSummary(report, rows, options))}</p>
            <div class="summary-points">${miniMarkup}</div>
          </div>
        </section>
      </div>
    </header>
    <main>
      <section class="section">
        <div class="section-head">
          <div class="section-title">${report.id === 'rca-pack' ? 'RCA 판단 스코어카드' : report.id === 'monthly-capacity' ? '용량 스코어카드' : '운영 스코어카드'}</div>
          <div class="section-note">${reportPeriod} 기준</div>
        </div>
        <div class="facts">${factMarkup}
        </div>
      </section>
      <section class="section two-col">
        <div class="panel">
          <div class="panel-body">
            <div class="section-title">${escapeHtml(tableSpec.title)}</div>
            <table class="issue-table">
              <thead>
                <tr><th>${escapeHtml(tableSpec.statusHeader)}</th><th>${escapeHtml(tableSpec.resourceHeader)}</th><th>${escapeHtml(tableSpec.detailHeader)}</th></tr>
              </thead>
              <tbody>${issueRowsMarkup}
              </tbody>
            </table>
          </div>
        </div>
        <div class="panel">
          <div class="panel-body">
            <div class="section-title">${escapeHtml(reportRecommendationTitle(report))}</div>
            <div class="rec-list">${recommendationMarkup}
            </div>
          </div>
        </div>
      </section>
      <section class="section two-col">
        <div class="callout">
          <div class="icon">!</div>
          <div>
            <strong>보고서 판단</strong>
            <p>${escapeHtml(reportJudgement(report, rows, options))}</p>
          </div>
        </div>
        <div class="panel">
          <div class="panel-body">
            <div class="section-title">보고서 메타데이터</div>
            <div class="meta-grid">
              <div class="meta-item"><span>Report ID</span><b>${escapeHtml(options.reportId)}</b></div>
              <div class="meta-item"><span>Source Snapshot</span><b>${escapeHtml(options.sourceSnapshotId)}</b></div>
              <div class="meta-item"><span>Data Window</span><b>${reportPeriod}</b></div>
              <div class="meta-item"><span>Output</span><b>${escapeHtml(outputLabel)}</b></div>
            </div>
          </div>
        </div>
      </section>
      <footer class="footer">
        <span><b>AIOps for OCP Report Center</b> · Generated ${generatedAt}</span>
        <span>${reportCluster} · ${escapeHtml(reportCode(report))}</span>
      </footer>
    </main>
  </article>
</body>
</html>`;
  };

  const downloadHtmlContent = (html: string, filename: string) => {
    const blob = new Blob([html], { type: 'text/html;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  };

  const printHtmlContent = (html: string, fallbackFilename: string) => {
    const popup = window.open('', '_blank', 'noopener,noreferrer,width=1024,height=768');
    if (!popup) {
      downloadHtmlContent(html, fallbackFilename);
      return;
    }
    popup.document.open();
    popup.document.write(html);
    popup.document.close();
    popup.focus();
    window.setTimeout(() => popup.print(), 300);
  };

  const downloadHtmlReport = (report: ReportItem) => {
    downloadHtmlContent(reportHtml(report), `${report.id}-report.html`);
  };

  const printPdfReport = (report: ReportItem) => {
    printHtmlContent(reportHtml(report), `${report.id}-report.html`);
  };

  const createGeneratedReport = (report: ReportItem, format: ReportOutputFormat): GeneratedReport => {
    const generatedAt = new Date().toISOString();
    const options = currentReportBuildOptions(report, format, generatedAt);
    const html = reportHtml(report, options);

    return {
      format,
      generatedAt,
      html,
      id: `${options.reportId}-${Math.random().toString(36).slice(2, 7)}`,
      reportId: options.reportId,
      scope: options.dataWindowLabel,
      sections: options.sections,
      sourceSnapshotId: options.sourceSnapshotId,
      status: '완료',
      subtitle: report.subtitle,
      templateId: report.id,
      time: formatTime(generatedAt),
      title: report.title,
    };
  };

  const generateSelectedReport = () => {
    const generated = createGeneratedReport(selectedReport, outputFormat);
    setGeneratedReports((current) => [generated, ...current]);
    setHistoryTab('history');
    setOpenReport(generated);
  };

  const downloadGeneratedReport = (report: GeneratedReport) => {
    downloadHtmlContent(report.html, `${report.reportId}.html`);
  };

  const printGeneratedReport = (report: GeneratedReport) => {
    printHtmlContent(report.html, `${report.reportId}.html`);
  };

  const previewOptions = currentReportBuildOptions(selectedReport, outputFormat, summary.updatedAt || new Date().toISOString());
  const previewRows = reportIssueRows(selectedReport, previewOptions);
  const previewRecommendations = reportRecommendations(selectedReport, previewRows, previewOptions);
  const previewHero = reportHero(selectedReport, previewRows, previewOptions);
  const previewFacts = reportFacts(selectedReport, previewRows);
  const previewTableSpec = reportTableSpec(selectedReport);

  return (
    <section className="reports-workbench stack-view">
      <section className="report-builder-grid">
        <Panel title="보고서 유형">
          <div className="report-type-rail">
            {reports.map((report) => (
              <button
                className={selectedReport.id === report.id ? 'is-selected' : ''}
                key={report.id}
                onClick={() => setSelectedReportId(report.id)}
                type="button"
              >
                <span className="report-type-rail__top">
                  <i className="report-type-rail__icon" aria-hidden="true">
                    {report.id === 'rca-pack' ? (
                      <GitBranch size={15} />
                    ) : report.id === 'monthly-capacity' ? (
                      <BarChart3 size={15} />
                    ) : (
                      <FileText size={15} />
                    )}
                  </i>
                  <StatusBadge label={report.status} severity={reportStatusSeverity(report.status)} />
                </span>
                <strong>{report.title}</strong>
                <span>{reportPrimarySignal(report, summary, selectedIssue)}</span>
                <small>{reportSecondarySignal(report, summary, status, selectedIssue)}</small>
              </button>
            ))}
          </div>
        </Panel>

        <Panel title="보고서 작성 / 미리보기" action={<StatusBadge label={selectedReport.status} severity={reportStatusSeverity(selectedReport.status)} />}>
          <article className="report-document-canvas">
            <header className="report-preview-cover">
              <div className="report-preview-brand">
                <span>AIOps for OCP</span>
                <b>{previewOptions.outputFormat} Report</b>
              </div>
              <div className="report-preview-title">
                <span>{selectedReport.subtitle}</span>
                <h2>{selectedReport.title}</h2>
                <p>{clusterLabel(summary)} · {previewOptions.dataWindowLabel} · {reportCoverDescription(selectedReport)}</p>
              </div>
              <div className="report-preview-meta-strip">
                <b>{summary.apiUrl ? 'Gateway connected' : 'Gateway pending'}</b>
                <b>{previewOptions.reportId}</b>
              </div>
            </header>

            <div className="report-preview-hero">
              <div className="report-preview-score">
                <span>{previewHero.label}</span>
                <strong>{previewHero.value}{previewHero.unit && <small>{previewHero.unit}</small>}</strong>
                <b className={`is-${previewHero.tone}`}>{previewHero.status}</b>
              </div>
              <div className="report-preview-summary">
                <h3>Executive Summary</h3>
                <p>{reportExecutiveSummary(selectedReport, previewRows, previewOptions)}</p>
              </div>
            </div>

            <section>
              <h3>{selectedReport.id === 'rca-pack' ? 'RCA 판단 스코어카드' : selectedReport.id === 'monthly-capacity' ? '용량 스코어카드' : '운영 스코어카드'}</h3>
              <div className="report-preview-scorecard">
                {previewFacts.map((fact) => (
                  <div key={fact.label}><span>{fact.label}</span><strong className={`is-${fact.tone}`}>{fact.value}</strong><small>{fact.hint}</small></div>
                ))}
              </div>
            </section>

            <section className="report-preview-two-col">
              <div>
                <h3>{previewTableSpec.title}</h3>
                <table className="report-preview-table">
                  <thead>
                    <tr><th>{previewTableSpec.statusHeader}</th><th>{previewTableSpec.resourceHeader}</th><th>{previewTableSpec.detailHeader}</th></tr>
                  </thead>
                  <tbody>
                    {previewRows.slice(0, 4).map((row) => (
                      <tr key={`${row.resource}-${row.signal}`}>
                        <td><span className={`report-preview-sev is-${row.severity}`}>{severityLabel[row.severity]}</span></td>
                        <td><strong>{row.resource}</strong><small>{row.scope}</small></td>
                        <td><b>{row.signal}</b><small>{row.detail}</small></td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <div>
                <h3>{reportRecommendationTitle(selectedReport)}</h3>
                <div className="report-preview-rec-list">
                  {previewRecommendations.slice(0, 3).map((recommendation, index) => (
                    <article key={recommendation.title}>
                      <span>{String(index + 1).padStart(2, '0')}</span>
                      <div>
                        <strong>{recommendation.title}</strong>
                        <p>{recommendation.description}</p>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            </section>

            <section className="report-preview-metadata">
              <h3>보고서 메타데이터</h3>
              <div>
                <article><span>Report ID</span><strong>{previewOptions.reportId}</strong></article>
                <article><span>Source Snapshot</span><strong>{previewOptions.sourceSnapshotId}</strong></article>
                <article><span>Data Window</span><strong>{previewOptions.dataWindowLabel}</strong></article>
                <article><span>Output</span><strong>{outputFormat} · HTML/PDF 지원</strong></article>
              </div>
            </section>

            <footer>
              AIOps for OCP Report Center · {clusterLabel(summary)} · {reportCode(selectedReport)}
            </footer>
          </article>
        </Panel>

        <Panel title="생성 설정">
          <div className="report-builder-settings">
            <label>
              <span>보고서</span>
              <strong>{selectedReport.title}</strong>
            </label>
            <label>
              <span>데이터 범위</span>
              <select onChange={(event) => setDataWindow(event.target.value)} value={dataWindow}>
                <option value="today">오늘 00:00-현재</option>
                <option value="24h">최근 24시간</option>
                <option value="snapshot">현재 스냅샷</option>
              </select>
            </label>
            {selectedReport.id === 'rca-pack' && (
              <label>
                <span>대상 이슈</span>
                <select onChange={(event) => setSelectedIssueId(event.target.value)} value={selectedIssue?.id ?? ''}>
                  {issueOptions.map((item) => (
                    <option key={item.id} value={item.id}>{item.title}</option>
                  ))}
                </select>
              </label>
            )}
            <div className="report-format-options">
              <span>출력 형식</span>
              <label><input checked={outputFormat === 'HTML'} onChange={() => setOutputFormat('HTML')} type="radio" /> HTML</label>
              <label><input checked={outputFormat === 'PDF'} onChange={() => setOutputFormat('PDF')} type="radio" /> PDF</label>
              <label className="is-disabled"><input disabled type="radio" /> DOCX 준비 중</label>
            </div>
            <div className="report-section-checks">
              <span>포함 섹션</span>
              {selectedReport.sections.map((section) => (
                <label key={section}>
                  <input checked={selectedSections.includes(section)} onChange={() => toggleReportSection(section)} type="checkbox" />
                  {section}
                </label>
              ))}
            </div>
            <div className="report-source-list">
              <span>데이터 소스</span>
              {selectedReport.requiredData.map((source) => <b key={source}>{source}</b>)}
            </div>
            <button className="portal-button is-primary report-generate-button" onClick={generateSelectedReport} type="button">
              보고서 생성
            </button>
            <div className="report-secondary-actions">
              <button className="portal-button" onClick={() => downloadHtmlReport(selectedReport)} type="button">HTML 다운로드</button>
              <button className="portal-button" onClick={() => printPdfReport(selectedReport)} type="button">PDF 다운로드</button>
            </div>
          </div>
        </Panel>
      </section>

      <Panel
        title="보고서 이력"
        action={
          <div className="portal-tabs report-history-tabs">
            <button className={historyTab === 'history' ? 'is-active' : ''} onClick={() => setHistoryTab('history')} type="button">생성 이력</button>
            <button className={historyTab === 'schedule' ? 'is-active' : ''} onClick={() => setHistoryTab('schedule')} type="button">예약 보고서</button>
            <button className={historyTab === 'export' ? 'is-active' : ''} onClick={() => setHistoryTab('export')} type="button">내보내기 설정</button>
          </div>
        }
      >
        {historyTab === 'history' && (
          <>
            {generatedReports.length === 0 ? (
              <div className="report-empty-state">
                <strong>생성된 보고서가 없습니다.</strong>
                <span>오른쪽 생성 설정에서 범위와 출력 형식을 선택한 뒤 보고서를 생성하면 이력에 쌓이고 바로 열 수 있습니다.</span>
                <button className="portal-button is-primary" onClick={generateSelectedReport} type="button">현재 설정으로 생성</button>
              </div>
            ) : (
              <div className="report-history-table">
                <div className="report-history-table__head">
                  <span>시간</span>
                  <span>보고서</span>
                  <span>범위</span>
                  <span>형식</span>
                  <span>상태</span>
                  <span>액션</span>
                </div>
                {generatedReports.map((item) => (
                  <article key={item.id}>
                    <time>{item.time}</time>
                    <strong>{item.title}</strong>
                    <span>{item.scope}</span>
                    <b>{item.format}</b>
                    <StatusBadge label={item.status} severity="ok" />
                    <button className="portal-button" onClick={() => setOpenReport(item)} type="button">열기</button>
                  </article>
                ))}
              </div>
            )}
          </>
        )}
        {historyTab === 'schedule' && (
          <div className="report-schedule-list">
            <article>
              <strong>일일 운영 브리핑</strong>
              <span>매일 18:00 · HTML/PDF · 운영팀 공유</span>
            </article>
            <article>
              <strong>월간 리소스 및 용량 리포트</strong>
              <span>매월 1일 · 30일 메트릭 충족 후 활성화</span>
            </article>
          </div>
        )}
        {historyTab === 'export' && (
          <div className="report-export-settings">
            <article><span>HTML</span><strong>다운로드 가능</strong></article>
            <article><span>PDF</span><strong>브라우저 저장 PDF 지원</strong></article>
            <article><span>DOCX</span><strong>준비 중</strong></article>
          </div>
        )}
      </Panel>

      <ReportViewerDrawer
        onClose={() => setOpenReport(null)}
        onDownloadHtml={downloadGeneratedReport}
        onPrintPdf={printGeneratedReport}
        report={openReport}
      />
    </section>
  );
};


export const V2Reports: React.FC<{ runtime: V2Runtime }> = ({ runtime }) => (
  <ReportsView status={runtime.status} summary={runtime.summary} />
);
