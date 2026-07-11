import { actionRecords } from './executionLedgerModel';
import type { LedgerEntry } from './executionLedgerModel';
import type {
  AiopsRuntimeStatus,
  ClusterSummary,
  QueueItem,
  Severity,
} from './types';

const PUBLIC_WEB_URL_RE =
  /\bhttps?:\/\/(?:github\.com|docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com)\/[^\s)]+/gi;

export const stripPublicWebUrls = (value: string): string =>
  value
    .replace(/\s*See also\s+https?:\/\/(?:github\.com|docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com)\/[^\s)]+/gi, '')
    .replace(PUBLIC_WEB_URL_RE, '')
    .replace(/\s{2,}/g, ' ')
    .trim();

export const sourceLabel = (value?: string): string => {
  const labels: Record<string, string> = {
    'AIOps Gateway': 'AIOps 게이트웨이',
    'Gateway cluster summary': '게이트웨이 클러스터 요약',
    'Kubernetes Event': '쿠버네티스 이벤트',
    'OpenShift ClusterOperator API': 'OpenShift ClusterOperator API',
    'OpenShift ClusterVersion API': 'OpenShift ClusterVersion API',
    'OpenShift Node API': 'OpenShift Node API',
  };
  return value ? labels[value] ?? value : '-';
};

export type ReportItem = {
  id: string;
  title: string;
  subtitle: string;
  period: string;
  status: '생성 가능' | '이슈 선택 필요' | '준비 중';
  statusDetail: string;
  metric: string;
  summary: string;
  sections: string[];
  requiredData: string[];
  outputs: string[];
};

export type ReportOutputFormat = 'HTML' | 'PDF';

export type ReportBuildOptions = {
  dataWindowLabel: string;
  generatedAt: string;
  issue?: QueueItem;
  outputFormat: ReportOutputFormat;
  reportId: string;
  sections: string[];
  sourceSnapshotId: string;
};

export type GeneratedReport = {
  artifact: ReportArtifact;
  format: ReportOutputFormat;
  generatedAt: string;
  html: string;
  id: string;
  reportId: string;
  scope: string;
  sections: string[];
  sourceSnapshotId: string;
  status: '완료';
  subtitle: string;
  templateId: string;
  time: string;
  title: string;
};

export type ReportArtifact = {
  apiVersion: 'aiops.komsco/v1';
  kind: 'AIOpsReportArtifact';
  metadata: {
    cluster: string;
    dataWindow: string;
    format: ReportOutputFormat;
    generatedAt: string;
    reportId: string;
    sourceSnapshotId: string;
    templateId: string;
  };
  spec: {
    actionsAndAudit: {
      actionProposals: number;
      approvalDecisions: number;
      auditRecords: number;
      executionRecords: number;
      ledgerEntries: Array<Pick<LedgerEntry, 'action' | 'actor' | 'artifact' | 'category' | 'gate' | 'id' | 'phase' | 'result' | 'target' | 'time' | 'title' | 'variant'>>;
      sealedActionPlans: number;
    };
    evidencePackage: {
      issue?: {
        category?: string;
        id: string;
        severity: Severity;
        target?: string;
        title: string;
      };
      rows: ReportIssueRow[];
    };
    executiveSummary: string;
    recommendations: ReportRecommendation[];
    reportJudgement: string;
    requiredData: string[];
    sections: string[];
    sourceStatus: {
      actionExecutorConfigured: boolean;
      mutationsEnabled: boolean;
      recordStoreEnabled: boolean;
    };
    title: string;
  };
};

export type ReportIssueRow = {
  detail: string;
  resource: string;
  scope: string;
  severity: Severity;
  signal: string;
};

export type ReportRecommendation = {
  description: string;
  title: string;
};

export type ReportFact = {
  hint: string;
  label: string;
  tone: 'good' | 'warn' | 'bad';
  value: string;
};

export type ReportHero = {
  label: string;
  status: string;
  tone: Severity;
  unit?: string;
  value: string;
};

export type ReportTableSpec = {
  detailHeader: string;
  resourceHeader: string;
  statusHeader: string;
  title: string;
};

export const sampleReportItems: ReportItem[] = [
  {
    id: 'daily-ops',
    title: '일일 운영 브리핑',
    subtitle: 'Daily Operations Brief',
    period: '오늘 00:00 - 현재',
    status: '생성 가능',
    statusDetail: '현재 상태 기준 즉시 생성',
    metric: '운영 상태',
    summary: '클러스터 건강도, 주요 이슈, AIOps 실행 기록을 한 페이지로 요약합니다.',
    sections: ['건강도 추이', '주요 이슈', '실행 권장', '미해결 알림'],
    requiredData: ['Cluster summary', 'Issue queue', 'AIOps activity'],
    outputs: ['HTML', 'PDF 출력', 'DOCX 준비 중'],
  },
  {
    id: 'rca-pack',
    title: 'RCA 증거 패키지',
    subtitle: 'RCA Evidence Package · 감사 제출용',
    period: '선택 이슈 기준',
    status: '이슈 선택 필요',
    statusDetail: '이슈 큐 선택 후 생성',
    metric: '감사 대응',
    summary: '이슈 큐, 증거 스트림, 실행 기록을 감사 제출용 형태로 묶는 보고서입니다.',
    sections: ['이슈 요약', '증거 패키지', '의존성 경로', '런북 게이트', '실행 기록'],
    requiredData: ['Selected issue', 'RCA evidence', 'Audit ledger'],
    outputs: ['HTML', 'PDF 출력', 'DOCX 준비 중'],
  },
  {
    id: 'monthly-capacity',
    title: '월간 리소스 및 용량 리포트',
    subtitle: 'Monthly Capacity Report',
    period: '최근 30일',
    status: '준비 중',
    statusDetail: '30일 이상 메트릭 수집 필요',
    metric: '용량 계획',
    summary: '노드, 파드, 컨트롤러, 스토리지 리소스 상태를 용량 계획 관점으로 정리합니다.',
    sections: ['리소스 분포', '이슈 빈도', '증설 후보', '용량 계획'],
    requiredData: ['30일 metrics', 'Resource inventory', 'Storage status'],
    outputs: ['HTML 샘플', 'PDF 출력', '예약 설정 준비 중'],
  },
];

export const reportStatusSeverity = (status: ReportItem['status']): Severity =>
  status === '생성 가능' ? 'ok' : status === '준비 중' ? 'warn' : 'risk';

export const reportPrimarySignal = (report: ReportItem, summary: ClusterSummary, selectedIssue?: QueueItem): string => {
  if (report.id === 'daily-ops') {
    return `건강도 ${summary.healthScore}%`;
  }
  if (report.id === 'rca-pack') {
    return selectedIssue ? selectedIssue.title : '대상 이슈 미선택';
  }
  return `리소스 이슈 ${summary.resources?.issues ?? 0}건`;
};

export const reportSecondarySignal = (
  report: ReportItem,
  summary: ClusterSummary,
  status: AiopsRuntimeStatus,
  selectedIssue?: QueueItem,
): string => {
  const auditCount = status.spec.records.auditRecords?.length ?? 0;
  const actionCount = actionRecords(status).length;
  if (report.id === 'daily-ops') {
    return `위험 ${summary.resources?.issues ?? 0} · 오퍼레이터 저하 ${summary.operators.degraded} · ${reportHealthLabel(summary)}`;
  }
  if (report.id === 'rca-pack') {
    return selectedIssue ? `증거 ${selectedIssue.evidence?.length ?? 0} · 권장 조치 ${Math.max(1, actionCount)} · 감사 이벤트 ${auditCount}` : '이슈를 선택하면 증거 패키지를 생성합니다.';
  }
  const podResource = summary.resources?.items.find((resource) => resource.id === 'pods');
  return `노드 ${summary.nodes.ready}/${summary.nodes.total} · 파드 ${podResource?.score ?? '-'} · 컨트롤러 ${summary.resources?.total ?? 0}`;
};

export const reportHealthLabel = (summary: ClusterSummary): string => {
  if (summary.healthScore >= 90) {
    return '정상';
  }
  if (summary.healthScore >= 70) {
    return '주의';
  }
  return '위험';
};
