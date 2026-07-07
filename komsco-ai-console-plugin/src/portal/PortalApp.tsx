import * as React from 'react';
import {
  Activity,
  AlertTriangle,
  Bell,
  ChevronLeft,
  ChevronRight,
  ClipboardCheck,
  Cpu,
  FileText,
  GitBranch,
  Network,
  RefreshCw,
  Search,
  ShieldCheck,
  Upload,
  X,
} from 'lucide-react';
import AssistantLauncher from '../components/AssistantLauncher';
import type {
  AiopsExecutionMode,
  AssistantDraftPrompt,
  AssistantLaunchContext,
} from '../components/assistant.types';
import { fetchAiopsEvents, fetchAiopsStatus, fetchClusterSummary } from './api';
import aiopsIconUrl from './assets/aiops_icon.svg';
import {
  navGroupLabel,
  navItems,
  standaloneRouteByView,
  viewFromLocation,
} from './portalNavigation';
import { severityClass, severityLabel, StatusBadge } from './portalBadges';
import type {
  ActivityItem,
  AiopsEventFeed,
  AiopsEventItem,
  AiopsRecord,
  AiopsRuntimeStatus,
  AlertItem,
  ClusterSummary,
  Endpoint,
  NavView,
  QueueItem,
  ScopeItem,
  Severity,
} from './types';
import './styles.css';

type RuntimeState = {
  error: string;
  events: AiopsEventFeed;
  isLive: boolean;
  loading: boolean;
  refresh: (options?: { silent?: boolean }) => Promise<void>;
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
};

type AssistantLaunchRequest = {
  context: AssistantLaunchContext;
  executionMode?: AiopsExecutionMode;
  taskMode?: AssistantDraftPrompt['taskMode'];
};

type AssistantLaunchHandler = (request: AssistantLaunchRequest) => void;

const cleanAssistantText = (value?: string): string | undefined => {
  const text = value?.trim();
  return text && text !== '-' ? text : undefined;
};

const parseAssistantTarget = (
  target?: string,
  fallbackKind?: string,
): Pick<AssistantLaunchContext, 'kind' | 'name' | 'namespace'> => {
  const cleanTarget = cleanAssistantText(target);
  if (!cleanTarget) {
    return fallbackKind ? { kind: fallbackKind } : {};
  }

  const slashParts = cleanTarget
    .split(/\s*\/\s*/)
    .map((part) => part.trim())
    .filter(Boolean);

  if (slashParts.length >= 3) {
    return {
      namespace: cleanAssistantText(slashParts[0]),
      kind: cleanAssistantText(slashParts[1]) ?? fallbackKind,
      name: cleanAssistantText(slashParts.slice(2).join('/')),
    };
  }

  if (slashParts.length === 2) {
    return {
      namespace: cleanAssistantText(slashParts[0]),
      kind: fallbackKind,
      name: cleanAssistantText(slashParts[1]),
    };
  }

  return {
    kind: fallbackKind,
    name: cleanTarget,
  };
};

const assistantTargetLine = (context: AssistantLaunchContext): string =>
  [context.namespace, context.kind, context.name].filter(Boolean).join(' / ') ||
  context.name ||
  context.reason ||
  '클러스터';

const buildAssistantPrompt = (context: AssistantLaunchContext): string => {
  const evidence = context.evidenceRefs?.filter(Boolean).slice(0, 4) ?? [];
  return [
    '다음 AIOps for OCP 운영 신호를 RCA 관점으로 분석하고 필요한 경우 Action Plan 조건까지 정리해줘.',
    '',
    `대상: ${assistantTargetLine(context)}`,
    context.severity ? `심각도: ${context.severity}` : '',
    context.reason ? `이유: ${context.reason}` : '',
    context.actionType ? `요청 작업: ${context.actionType}` : '',
    evidence.length > 0 ? `확인 결과: ${evidence.join(' / ')}` : '',
    '',
    '답변 형식: 요약, 영향 범위, 확인 결과, 원인 후보, Action Plan, 검증/롤백, 추가 확인 순서.',
  ]
    .filter((line) => line !== '')
    .join('\n');
};

const queueAssistantContext = (
  item: QueueItem,
  source: AssistantLaunchContext['source'],
  actionType = 'rca',
): AssistantLaunchContext => {
  const target = parseAssistantTarget(item.target, item.category);
  const base: AssistantLaunchContext = {
    ...target,
    actionType,
    evidenceRefs: item.evidence,
    reason: item.category ?? item.title,
    severity: item.severity,
    source,
    promptDraft: '',
  };
  return {
    ...base,
    promptDraft: buildAssistantPrompt(base),
  };
};

const endpointAssistantContext = (
  endpoint: Endpoint,
  source: AssistantLaunchContext['source'],
): AssistantLaunchContext => {
  const base: AssistantLaunchContext = {
    ...parseAssistantTarget(`${endpoint.group}/${endpoint.name}`, endpoint.type),
    actionType: 'resource-rca',
    evidenceRefs: [endpoint.path, `CPU ${endpoint.cpu}`, `Memory ${endpoint.memory}`, `Latency ${endpoint.latency}`],
    reason: endpoint.lastEvent,
    severity: endpoint.severity,
    source,
    promptDraft: '',
  };
  return {
    ...base,
    promptDraft: buildAssistantPrompt(base),
  };
};

const emptySummary: ClusterSummary = {
  aiopsWorkloads: {
    daemonsets: [],
    deployments: [],
    issues: 0,
    namespaces: [],
    total: 0,
  },
  healthScore: 0,
  nodes: {
    total: 0,
    ready: 0,
    notReady: 0,
    pressureCount: 0,
    metricsAvailable: false,
    items: [],
  },
  operators: {
    available: 0,
    degraded: 0,
    progressing: 0,
    total: 0,
    unavailable: 0,
    issues: [],
  },
  resources: {
    issues: 0,
    items: [],
    total: 0,
  },
  updatedAt: '',
  version: {
    updateAvailable: false,
  },
};

const emptyStatus: AiopsRuntimeStatus = {
  spec: {
    capabilities: {
      actionExecutorConfigured: false,
      diagnosticsControllerConfigured: false,
      diagnosticsEnabled: false,
      mutationsEnabled: false,
      recordStoreEnabled: false,
      unrestrictedCommandsEnabled: false,
    },
    records: {
      actionProposals: [],
      auditRecords: [],
      approvalDecisions: [],
      diagnosticRequests: [],
      executionRecords: [],
      sealedActionPlans: [],
    },
  },
};

const emptyEventFeed: AiopsEventFeed = {
  metadata: {
    name: 'activity-feed',
  },
  spec: {
    items: [],
    pollIntervalSeconds: 30,
    sources: [],
  },
};

const mockExecutionRecords: AiopsRecord[] = [
  {
    kind: 'ActionProposal',
    metadata: { createdAt: '2026-07-03T09:02:00+09:00', name: 'crashloop-remediation-proposal' },
    spec: {
      action: 'restart_rollout',
      actor: 'aiops-gateway',
      evidenceId: 'evidence-crashloop-001',
      gate: 'Approval',
      result: 'proposed',
      status: { phase: 'proposed' },
      target: { kind: 'Deployment', namespace: 'komsco-ai-dev', name: 'aiops-scenario-1-crashloop' },
    },
  },
  {
    kind: 'SealedActionPlan',
    metadata: { createdAt: '2026-07-03T09:05:00+09:00', name: 'readiness-recovery-sealed-plan' },
    spec: {
      action: 'seal_mutation_plan',
      actor: 'aiops-gateway',
      evidenceId: 'evidence-readiness-002',
      gate: 'Approval Seal',
      result: 'waiting_approval',
      status: { phase: 'sealed_pending_approval' },
      target: { kind: 'Deployment', namespace: 'cyntra', name: 'cyntra-api' },
    },
  },
  {
    kind: 'ApprovalDecision',
    metadata: { createdAt: '2026-07-03T09:07:00+09:00', name: 'readiness-probe-approval' },
    spec: {
      action: 'approve_mutation',
      actor: 'platform-operator',
      auditId: 'audit-approval-003',
      gate: 'Approval',
      result: 'approved',
      approvalDecision: { status: 'approved' },
      target: { kind: 'Pod', namespace: 'cyntra', name: 'cyntra-api-5c747b5966-pn9gk' },
    },
  },
  {
    kind: 'ExecutionRecord',
    metadata: { createdAt: '2026-07-03T09:10:00+09:00', name: 'rollout-restart-execution' },
    spec: {
      action: 'rollout_restart',
      actor: 'action-executor',
      auditId: 'audit-mutation-004',
      evidenceId: 'evidence-mutation-004',
      gate: 'Executor',
      result: 'succeeded',
      mutationOutcome: { status: 'mutation_succeeded' },
      target: { kind: 'Deployment', namespace: 'komsco-ai-dev', name: 'aiops-two-pod-exec' },
    },
  },
];

const mockAuditRecords: AiopsRecord[] = [
  {
    kind: 'AuditRecord',
    metadata: { createdAt: '2026-07-03T09:01:00+09:00', name: 'chat-request-accepted' },
    spec: {
      action: 'chat_request_accepted',
      actor: 'ocp-admin',
      auditId: 'audit-intake-001',
      gate: 'Gateway',
      requestId: 'request-crashloop-001',
      result: 'accepted',
      runId: 'crashloop-remediation',
      target: { kind: 'Run', namespace: 'komsco-ai-dev', name: 'crashloop-remediation' },
    },
  },
  {
    kind: 'AuditRecord',
    metadata: { createdAt: '2026-07-03T09:04:00+09:00', name: 'evidence-collected' },
    spec: {
      action: 'evidence_collected',
      actor: 'aiops-gateway',
      auditId: 'audit-evidence-002',
      evidenceId: 'evidence-crashloop-001',
      gate: 'Diagnostics',
      requestId: 'request-crashloop-001',
      result: 'collected',
      runId: 'crashloop-remediation',
      target: { kind: 'Evidence', namespace: 'komsco-ai-dev', name: 'crashloop-pod-status' },
    },
  },
  {
    kind: 'AuditRecord',
    metadata: { createdAt: '2026-07-03T09:08:00+09:00', name: 'approval-recorded' },
    spec: {
      action: 'approval_recorded',
      actor: 'platform-operator',
      auditId: 'audit-approval-003',
      gate: 'Ledger',
      requestId: 'request-crashloop-001',
      result: 'recorded',
      runId: 'crashloop-remediation',
      target: { kind: 'Approval', namespace: 'komsco-ai-dev', name: 'readiness-probe-approval' },
    },
  },
];

const sampleRcaQueues: QueueItem[] = [
  {
    id: 'sample-rca-cluster-update-blocked',
    title: '샘플: 클러스터 업데이트 차단',
    category: '클러스터 버전',
    detail: '현재 4.20.23 · 추천 업데이트 4.20.26, 4.20.25 · AdminAckRequired',
    evidence: [
      'current 4.20.23',
      'recommended updates 4.20.26, 4.20.25',
      'conditional updates 4.20.24',
      'reason AdminAckRequired',
      'issues 1',
    ],
    source: '샘플 데이터',
    target: 'ClusterVersion/version',
    updatedAt: '07. 03. 오전 09:40',
    severity: 'warn',
  },
  {
    id: 'sample-rca-api-latency',
    title: '샘플: API 응답 지연 조사',
    category: '샘플 RCA',
    detail: '서비스 p95 지연 1.8s · 최근 배포 직후 증가 · 파드 재시작 없음',
    evidence: [
      'target cyntra/cyntra-api',
      'cpu 82%',
      'memory 71%',
      'reason readiness probe latency increased',
      'issues 1',
    ],
    source: '샘플 데이터',
    target: 'cyntra/cyntra-api',
    updatedAt: '07. 03. 오전 09:30',
    severity: 'warn',
  },
  {
    id: 'sample-rca-node-pressure',
    title: '샘플: 워커 노드 디스크 압박',
    category: '샘플 RCA',
    detail: 'worker-2 DiskPressure · 이미지 캐시 증가 · evict 후보 파드 3개',
    evidence: [
      'target worker-2',
      'kind Node',
      'reason DiskPressure=True',
      'issues 3',
    ],
    source: '샘플 데이터',
    target: 'worker-2',
    updatedAt: '07. 03. 오전 09:24',
    severity: 'risk',
  },
];

type KnowledgeDoc = {
  category: string;
  chunks: number;
  id: string;
  keywords: string[];
  linkedIssues: string[];
  owner: string;
  rcaLinks: number;
  searchStatus: '색인 완료' | '검증 필요' | '초안';
  status: '검증됨' | '검증 필요' | '초안';
  targetScopes: string[];
  title: string;
  updatedAt: string;
  verifiedAt: string;
  version: string;
  summary: string;
  tags: string[];
  steps: string[];
};

type WikiUploadItem = {
  chunks: number;
  collection: string;
  id: string;
  name: string;
  size: string;
  status: '업로드 대기' | '인덱싱 준비' | '색인됨';
  type: string;
  updatedAt: string;
};

const sampleKnowledgeDocs: KnowledgeDoc[] = [
  {
    category: '장애 대응',
    chunks: 12,
    id: 'runbook-crashloop',
    keywords: ['CrashLoopBackOff', 'BackOff', 'restart count', 'exit code', 'image pull'],
    linkedIssues: ['Pods degraded', 'Deployment availability drift', 'CrashLoopBackOff detected'],
    owner: 'AIOps 운영팀',
    rcaLinks: 3,
    searchStatus: '색인 완료',
    status: '검증됨',
    targetScopes: ['Pod', 'Deployment', 'ReplicaSet', 'RCA'],
    title: 'CrashLoopBackOff 파드 대응 런북',
    updatedAt: '07. 03. 오전 09:20',
    verifiedAt: '07. 03. 오전 09:20',
    version: 'v1.7',
    summary: '반복 재시작 파드의 이벤트, 로그, 최근 배포 변경을 분리해 확인하는 표준 절차입니다.',
    tags: ['Pod', 'Deployment', 'RCA'],
    steps: ['최근 이벤트와 종료 코드를 확인합니다.', '동일 ReplicaSet 내 Pod 상태와 로그를 비교합니다.', '배포 변경, 이미지 pull, probe 실패를 분리합니다.', '승인 게이트 필요 시 변경 요청을 생성합니다.'],
  },
  {
    category: '변경 통제',
    chunks: 8,
    id: 'policy-approval',
    keywords: ['approval gate', 'audit', 'change request', '자동 조치', '승인 정책'],
    linkedIssues: ['조치 승인 대기', 'Runbook gate required'],
    owner: '플랫폼 아키텍트',
    rcaLinks: 2,
    searchStatus: '색인 완료',
    status: '검증됨',
    targetScopes: ['Approval', 'Audit', 'Runbook', 'Policy'],
    title: 'AIOps 조치 승인 정책',
    updatedAt: '07. 02. 오후 05:40',
    verifiedAt: '07. 02. 오후 05:40',
    version: 'v2.1',
    summary: '자동 조치 제안, 승인 검증, 실행 원장 기록에 필요한 운영 통제 기준입니다.',
    tags: ['Approval', 'Audit', 'Policy'],
    steps: ['읽기/증거 수집 단계와 변경 실행 단계를 분리합니다.', '운영자 승인 없이 클러스터 변경을 실행하지 않습니다.', '모든 실행 결과는 감사 원장에 남깁니다.'],
  },
  {
    category: '업데이트',
    chunks: 10,
    id: 'ocp-update-check',
    keywords: ['ClusterVersion', 'Upgradeable=False', 'AdminAck', 'conditional update', '4.20'],
    linkedIssues: ['OCP 업데이트 사전 확인 필요', 'Admin acknowledgement required'],
    owner: 'OpenShift 운영팀',
    rcaLinks: 1,
    searchStatus: '검증 필요',
    status: '검증 필요',
    targetScopes: ['ClusterVersion', 'Update', 'AdminAck', 'Operator'],
    title: 'OCP 업데이트 차단 사전 점검',
    updatedAt: '07. 01. 오후 02:10',
    verifiedAt: '07. 01. 오후 02:10',
    version: 'v0.9',
    summary: 'ClusterVersion Upgradeable=False, AdminAck, conditional update 항목을 점검하는 문서입니다.',
    tags: ['ClusterVersion', 'Update', 'AdminAck'],
    steps: ['ClusterVersion condition을 확인합니다.', '추천 업데이트와 조건부 업데이트를 분리합니다.', 'AdminAck 또는 mirror signature 준비 여부를 확인합니다.'],
  },
];

const formatUploadSize = (size: number): string => {
  if (size >= 1024 * 1024) {
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.ceil(size / 1024)} KB`;
  }
  return `${size} B`;
};

const uploadStatusSeverity = (status: WikiUploadItem['status']): Severity =>
  status === '색인됨' ? 'ok' : 'warn';

const docStatusSeverity = (status: KnowledgeDoc['status']): Severity =>
  status === '검증됨' ? 'ok' : status === '초안' ? 'warn' : 'risk';

const buildDocSearchResults = (docs: KnowledgeDoc[], query: string, activeDoc: KnowledgeDoc): Array<{ doc: KnowledgeDoc; score: string; reason: string }> => {
  const normalized = query.trim().toLowerCase();
  return docs
    .map((doc, index) => {
      const haystack = `${doc.title} ${doc.summary} ${doc.tags.join(' ')} ${doc.keywords.join(' ')}`.toLowerCase();
      const exactMatch = normalized ? haystack.includes(normalized) : doc.id === activeDoc.id;
      const keywordMatch = normalized
        ? doc.keywords.some((keyword) => normalized.includes(keyword.toLowerCase()) || keyword.toLowerCase().includes(normalized))
        : false;
      const baseScore = doc.id === activeDoc.id ? 0.91 : exactMatch ? 0.84 : keywordMatch ? 0.78 : 0.64 - index * 0.06;
      return {
        doc,
        reason: doc.id === activeDoc.id ? '선택 문서 절차와 키워드 매칭' : `${doc.tags.slice(0, 2).join(', ')} 근거 chunk 매칭`,
        score: Math.max(0.42, baseScore).toFixed(2),
      };
    })
    .sort((left, right) => Number(right.score) - Number(left.score))
    .slice(0, 3);
};

type ReportItem = {
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

type ReportOutputFormat = 'HTML' | 'PDF';

type ReportBuildOptions = {
  dataWindowLabel: string;
  generatedAt: string;
  issue?: QueueItem;
  outputFormat: ReportOutputFormat;
  reportId: string;
  sections: string[];
  sourceSnapshotId: string;
};

type GeneratedReport = {
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

type ReportArtifact = {
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

type ReportIssueRow = {
  detail: string;
  resource: string;
  scope: string;
  severity: Severity;
  signal: string;
};

type ReportRecommendation = {
  description: string;
  title: string;
};

type ReportFact = {
  hint: string;
  label: string;
  tone: 'good' | 'warn' | 'bad';
  value: string;
};

type ReportHero = {
  label: string;
  status: string;
  tone: Severity;
  unit?: string;
  value: string;
};

type ReportTableSpec = {
  detailHeader: string;
  resourceHeader: string;
  statusHeader: string;
  title: string;
};

const sampleReportItems: ReportItem[] = [
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

const reportStatusSeverity = (status: ReportItem['status']): Severity =>
  status === '생성 가능' ? 'ok' : status === '준비 중' ? 'warn' : 'risk';

const reportPrimarySignal = (report: ReportItem, summary: ClusterSummary, selectedIssue?: QueueItem): string => {
  if (report.id === 'daily-ops') {
    return `건강도 ${summary.healthScore}%`;
  }
  if (report.id === 'rca-pack') {
    return selectedIssue ? selectedIssue.title : '대상 이슈 미선택';
  }
  return `리소스 이슈 ${summary.resources?.issues ?? 0}건`;
};

const reportSecondarySignal = (
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

const endpointPageSizeOptions = [10, 25, 50];
const eventInboxPageSizeOptions = [10, 25, 50];

const aiopsAlarmCount = (events: AiopsEventFeed): number =>
  events.spec.items.filter((item) => item.severity === 'risk' || item.severity === 'warn').length;

const compactCount = (value: number): string => (value > 99 ? '99+' : String(value));

const formatTime = (value?: string): string => {
  if (!value) {
    return '-';
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleString('ko-KR', {
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    month: '2-digit',
  });
};

const asObject = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : {};

const textValue = (value: unknown, fallback = '-'): string => {
  if (value === undefined || value === null || value === '') {
    return fallback;
  }

  if (typeof value === 'string') {
    return value;
  }

  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }

  return JSON.stringify(value);
};

const PUBLIC_WEB_URL_RE =
  /\bhttps?:\/\/(?:github\.com|docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com)\/[^\s)]+/gi;

const stripPublicWebUrls = (value: string): string =>
  value
    .replace(/\s*See also\s+https?:\/\/(?:github\.com|docs\.openshift\.com|docs\.redhat\.com|access\.redhat\.com)\/[^\s)]+/gi, '')
    .replace(PUBLIC_WEB_URL_RE, '')
    .replace(/\s{2,}/g, ' ')
    .trim();

const localizeTelemetryText = (value: string): string =>
  stripPublicWebUrls(value)
    .replace(/\blocal-aiops-fixture-ledger\b/gi, 'Gateway 검증 원장')
    .replace(/\brun-local-fixture\b/gi, 'Gateway 검증 실행')
    .replace(/\blocal-fixture\b/gi, 'Gateway 검증')
    .replace(/\bserved local-only AIOps fixture\b/gi, 'Gateway 검증 응답 기록')
    .replace(/\blocal-only AIOps fixture\b/gi, 'Gateway 검증 응답')
    .replace(/\blocal simulator state: ready ([0-9]+\/[0-9]+)/gi, '검증 워크로드 ready $1')
    .replace(/\bready ([0-9]+\/[0-9]+) in local simulator\b/gi, 'ready $1')
    .replace(/\bCrashLoopBackOff fixture for Action Plan testing\b/gi, 'Action Plan 검증용 CrashLoopBackOff')
    .replace(/\bopenshift-marketplace\/appscan360-catalog fixture is not ready\b/gi, 'openshift-marketplace/appscan360-catalog 준비 상태 확인 필요')
    .replace(/\blocal simulator\b/gi, '검증 환경')
    .replace(/\blocal fixture\b/gi, '검증 환경')
    .replace(/\bfixture\b/gi, '검증')
    .replace(/\bPod status\b/g, '파드 상태')
    .replace(/\bKubernetes Event\b/g, '쿠버네티스 이벤트')
    .replace(/\bReady replicas\b/g, '정상 레플리카')
    .replace(/\bRunning\b/g, '실행 중')
    .replace(/\bReady\b/g, '정상')
    .replace(/\bNotReady\b/g, '비정상')
    .replace(/\bPending\b/g, '대기')
    .replace(/\bFailed\b/g, '실패')
    .replace(/\bSucceeded\b/g, '성공')
    .replace(/\bRestarts\b/g, '재시작')
    .replace(/\bAvailable\b/g, '가용')
    .replace(/\bUpdated\b/g, '업데이트')
    .replace(/\bIssues\b/g, '이슈')
    .replace(/\bIssue\b/g, '이슈')
    .replace(/\bTotal\b/g, '전체')
    .replace(/\bCurrent\b/g, '현재')
    .replace(/\bDegraded\b/g, '저하')
    .replace(/\bProgressing\b/g, '진행 중')
    .replace(/\bUnavailable\b/g, '사용 불가')
    .replace(/\bUpdate available\b/g, '업데이트 가능')
    .replace(/\bphase=/g, '상태=')
    .replace(/\bready=/g, '준비=')
    .replace(/\brestart=/g, '재시작=')
    .replace(/\bcreated=/g, '생성=')
    .replace(/\blast=/g, '마지막=')
    .replace(/\brunning\b/g, '실행 중')
    .replace(/\bwaiting\b/g, '대기')
    .replace(/\bsucceeded\b/g, '성공')
    .replace(/\bsince\b/g, '이후')
    .replace(/\broles\b/g, '역할');

const sourceLabel = (value?: string): string => {
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

const actionRecords = (status: AiopsRuntimeStatus): AiopsRecord[] => [
  ...status.spec.records.actionProposals,
  ...status.spec.records.sealedActionPlans,
  ...status.spec.records.approvalDecisions,
  ...status.spec.records.executionRecords,
];

const recordPhase = (record: AiopsRecord): string => {
  const spec = asObject(record.spec);
  const status = asObject(spec.status);
  const approvalDecision = asObject(spec.approvalDecision);
  const mutationOutcome = asObject(spec.mutationOutcome);

  return textValue(
    status.phase ?? approvalDecision.status ?? mutationOutcome.status ?? spec.action,
    'recorded',
  );
};

const recordTarget = (record: AiopsRecord): string => {
  const spec = asObject(record.spec);
  const target = asObject(spec.target);
  const candidate = asObject(spec.candidate);
  const candidateTarget = asObject(candidate.targetNode);
  const sealedActionPlan = asObject(spec.sealedActionPlan);
  const sealedTarget = asObject(sealedActionPlan.target);
  const finalTarget =
    Object.keys(target).length > 0
      ? target
      : Object.keys(candidateTarget).length > 0
        ? candidateTarget
        : sealedTarget;
  const namespace = textValue(finalTarget.namespace, '');
  const name = textValue(finalTarget.name ?? finalTarget.nodeName ?? spec.requestId, '');

  if (namespace && name) {
    return `${namespace}/${name}`;
  }

  return name || textValue(spec.runId ?? spec.incidentId, '-');
};

const recordKindLabel = (kind?: string): string => {
  const labels: Record<string, string> = {
    ActionProposal: '조치 제안',
    ApprovalDecision: '승인 결정',
    AuditRecord: '감사',
    DiagnosticRequestRecord: '진단',
    ExecutionRecord: '실행',
    SealedActionPlan: '승인 필요 계획',
  };
  return kind ? labels[kind] ?? kind : '기록';
};

const recordTone = (record: AiopsRecord, variant: 'audit' | 'action' = 'action'): ActivityItem['tone'] => {
  if (variant === 'audit') {
    return 'blue';
  }

  const phase = recordPhase(record).toLowerCase();
  if (phase.includes('failed') || phase.includes('denied') || phase.includes('rejected') || phase.includes('error')) {
    return 'red';
  }
  if (phase.includes('succeeded') || phase.includes('approved') || phase.includes('completed')) {
    return 'green';
  }
  if (phase.includes('pending') || phase.includes('proposed') || phase.includes('sealed')) {
    return 'orange';
  }
  return 'violet';
};

type LedgerEntry = {
  action: string;
  actor: string;
  artifact: string;
  auditId: string;
  category: 'approval' | 'evidence' | 'gateway' | 'mutation' | 'proposal';
  evidenceId: string;
  gate: string;
  id: string;
  kind: string;
  name: string;
  namespace: string;
  phase: string;
  result: string;
  runId: string;
  sample: boolean;
  target: string;
  time: string;
  title: string;
  tone: ActivityItem['tone'];
  variant: 'action' | 'audit';
};

const targetProjection = (record: AiopsRecord): { kind: string; name: string; namespace: string; target: string } => {
  const spec = asObject(record.spec);
  const target = asObject(spec.target);
  const candidate = asObject(spec.candidate);
  const candidateTarget = asObject(candidate.targetNode);
  const sealedActionPlan = asObject(spec.sealedActionPlan);
  const sealedTarget = asObject(sealedActionPlan.target);
  const finalTarget =
    Object.keys(target).length > 0
      ? target
      : Object.keys(candidateTarget).length > 0
        ? candidateTarget
        : sealedTarget;
  const namespace = textValue(finalTarget.namespace, '');
  const kind = textValue(finalTarget.kind ?? finalTarget.resource ?? finalTarget.resourceKind, '');
  const name = textValue(finalTarget.name ?? finalTarget.nodeName ?? spec.runId ?? spec.requestId, '');
  const parts = [namespace, kind, name].filter(Boolean);

  return {
    kind: kind || '-',
    name: name || '-',
    namespace: namespace || '-',
    target: parts.length > 0 ? parts.join(' / ') : recordTarget(record),
  };
};

const ledgerCategory = (record: AiopsRecord, variant: 'action' | 'audit'): LedgerEntry['category'] => {
  const kind = record.kind ?? '';
  const action = textValue(asObject(record.spec).action, '').toLowerCase();
  if (variant === 'audit') {
    if (action.includes('evidence')) {
      return 'evidence';
    }
    if (action.includes('approval')) {
      return 'approval';
    }
    return 'gateway';
  }
  if (kind === 'ExecutionRecord') {
    return 'mutation';
  }
  if (kind === 'ApprovalDecision' || kind === 'SealedActionPlan') {
    return 'approval';
  }
  return 'proposal';
};

const ledgerPhase = (entry: Pick<LedgerEntry, 'category'>, record: AiopsRecord, variant: 'action' | 'audit'): string => {
  if (variant === 'audit') {
    const labels: Record<LedgerEntry['category'], string> = {
      approval: '승인',
      evidence: '증거 수집',
      gateway: '접수',
      mutation: '변경 실행',
      proposal: '조치 제안',
    };
    return labels[entry.category];
  }
  const labels: Record<string, string> = {
    ActionProposal: '조치 제안',
    ApprovalDecision: '승인 완료',
    ExecutionRecord: '변경 실행',
    SealedActionPlan: '승인 필요 계획',
  };
  return labels[record.kind ?? ''] ?? recordKindLabel(record.kind);
};

const buildLedgerEntries = (
  records: AiopsRecord[],
  auditRecords: AiopsRecord[],
  options: { sample: boolean },
): LedgerEntry[] => {
  const input = [
    ...records.map((record) => ({ record, variant: 'action' as const })),
    ...auditRecords.map((record) => ({ record, variant: 'audit' as const })),
  ];

  return input
    .map(({ record, variant }, index): LedgerEntry => {
      const spec = asObject(record.spec);
      const target = targetProjection(record);
      const category = ledgerCategory(record, variant);
      const phase = ledgerPhase({ category }, record, variant);
      const action = textValue(spec.action, variant === 'audit' ? textValue(spec.action, record.metadata?.name ?? 'audit_record') : recordPhase(record));
      const result = textValue(spec.result ?? recordPhase(record), variant === 'audit' ? 'recorded' : 'recorded');
      const runId = textValue(spec.runId ?? spec.requestId, 'crashloop-remediation');
      const time = record.metadata?.createdAt ?? '';
      const title = record.metadata?.name ?? action;

      return {
        action,
        actor: textValue(spec.actor, variant === 'audit' ? 'gateway' : 'aiops-gateway'),
        artifact: textValue(spec.artifact ?? spec.requestId ?? spec.runId, '-'),
        auditId: textValue(spec.auditId ?? record.metadata?.name, '-'),
        category,
        evidenceId: textValue(spec.evidenceId, '-'),
        gate: textValue(spec.gate, category === 'mutation' ? 'Executor' : category === 'approval' ? 'Approval' : 'Gateway'),
        id: `${variant}-${record.kind ?? 'record'}-${record.metadata?.name ?? index}`,
        kind: target.kind,
        name: target.name,
        namespace: target.namespace,
        phase,
        result,
        runId,
        sample: options.sample,
        target: target.target,
        time,
        title,
        tone: recordTone(record, variant),
        variant,
      };
    })
    .sort((a, b) => String(a.time).localeCompare(String(b.time)));
};

const runWindowLabel = (entries: LedgerEntry[]): string => {
  if (entries.length === 0) {
    return '-';
  }
  const first = formatTime(entries[0].time);
  const last = formatTime(entries[entries.length - 1].time);
  return first === last ? first : `${first} - ${last}`;
};

const ledgerActionLabel = (value: string): string => {
  const labels: Record<string, string> = {
    approval_recorded: '승인 기록',
    approve_mutation: '변경 승인',
    audit_record: '감사 기록',
    chat_request_accepted: '요청 접수',
    evidence_collected: '증거 수집',
    restart_rollout: '롤아웃 재시작 제안',
    rollout_restart: '롤아웃 재시작 실행',
    seal_mutation_plan: '변경 계획 봉인',
  };
  return labels[value] ?? value;
};

const ledgerGateLabel = (value: string): string => {
  const labels: Record<string, string> = {
    Approval: '승인',
    'Approval Seal': '승인 검증',
    Diagnostics: '진단',
    Executor: '실행기',
    Gateway: '게이트웨이',
    Ledger: '원장',
  };
  return labels[value] ?? value;
};

const ledgerKindLabel = (value: string): string => {
  const labels: Record<string, string> = {
    Approval: '승인',
    DaemonSet: '데몬셋',
    Deployment: '디플로이먼트',
    Evidence: '증거',
    Node: '노드',
    Pod: '파드',
    ReplicaSet: '레플리카셋',
    Route: '라우트',
    Run: '실행',
    Service: '서비스',
    StatefulSet: '스테이트풀셋',
  };
  return labels[value] ?? value;
};

const resourceNameLabel = (id: string, name: string, kind: string): string => {
  const labels: Record<string, string> = {
    clusteroperators: '클러스터 오퍼레이터',
    daemonsets: '데몬셋',
    deployments: '디플로이먼트',
    nodes: '노드',
    persistentvolumeclaims: 'PVC',
    pods: '파드',
    replicasets: '레플리카셋',
    routes: '라우트',
    services: '서비스',
    statefulsets: '스테이트풀셋',
  };
  const kindLabel = ledgerKindLabel(kind);
  return labels[id] ?? (kindLabel || name);
};

const ledgerTargetLabel = (entry: Pick<LedgerEntry, 'kind' | 'name' | 'namespace' | 'target'>): string => {
  const parts = [
    entry.namespace !== '-' ? entry.namespace : '',
    entry.kind !== '-' ? ledgerKindLabel(entry.kind) : '',
    entry.name !== '-' ? entry.name : '',
  ].filter(Boolean);

  return parts.length > 0 ? parts.join(' / ') : entry.target;
};

const ledgerResultLabel = (value: string): string => {
  const labels: Record<string, string> = {
    accepted: '접수됨',
    approved: '승인됨',
    blocked: '차단됨',
    collected: '수집됨',
    failed: '실패',
    proposed: '제안됨',
    recorded: '기록됨',
    succeeded: '성공',
    waiting_approval: '승인 대기',
  };
  return labels[value] ?? value;
};

const mutationStatusLabel = (value: string): string => {
  const labels: Record<string, string> = {
    Blocked: '차단됨',
    Executed: '실행됨',
    'Not executed': '미실행',
    'Waiting approval': '승인 대기',
  };
  return labels[value] ?? value;
};

const displayApiEndpoint = (apiUrl?: string): string => {
  if (!apiUrl) {
    return 'OpenShift 상태 확인 필요';
  }

  try {
    const host = new URL(apiUrl).hostname;
    if (/local-aiops\.invalid|\.invalid$/i.test(host)) {
      return 'Gateway 검증 환경';
    }
    return host;
  } catch {
    return /local-aiops|\.invalid/i.test(apiUrl) ? 'Gateway 검증 환경' : apiUrl;
  }
};

const displayOpenShiftVersion = (version?: string): string => {
  if (!version) {
    return '-';
  }
  return version.replace(/-local\b/i, '');
};

const displayNamespaceLabel = (namespace?: string): string => {
  if (!namespace) {
    return '-';
  }
  if (/^komsco-ai-local$/i.test(namespace)) {
    return '검증 네임스페이스';
  }
  return localizeTelemetryText(namespace);
};

const clusterLabel = (summary: ClusterSummary): string => {
  if (!summary.apiUrl) {
    return '게이트웨이 연결 대기';
  }
  return displayApiEndpoint(summary.apiUrl);
};

const resourceKeywords: Record<string, string[]> = {
  daemonsets: ['데몬셋', 'daemonset'],
  deployments: ['디플로이', '디플로이먼트', '배포', 'deployment'],
  namespaces: ['네임스페이스', 'namespace', '프로젝트'],
  persistentvolumeclaims: ['pvc', '볼륨', '스토리지', 'persistentvolumeclaim'],
  pods: ['파드', 'pod'],
  replicasets: ['레플리카셋', 'replicaset'],
  routes: ['라우트', 'route'],
  services: ['서비스', 'service'],
  statefulsets: ['스테이트풀셋', 'statefulset'],
};

const pressureLabels = (pressures: ClusterSummary['nodes']['items'][number]['pressures']): string[] => {
  const labels = [];
  if (pressures.disk) {
    labels.push('디스크 압박');
  }
  if (pressures.memory) {
    labels.push('메모리 압박');
  }
  if (pressures.pid) {
    labels.push('PID 압박');
  }
  return labels;
};

const nodeSeverity = (node: ClusterSummary['nodes']['items'][number]): Severity => {
  if (!node.ready) {
    return 'risk';
  }

  return pressureLabels(node.pressures).length > 0 ? 'warn' : 'ok';
};

const operatorSeverity = (operator: ClusterSummary['operators']['issues'][number]): Severity => {
  if (!operator.available || operator.degraded) {
    return 'risk';
  }

  return operator.progressing ? 'warn' : 'ok';
};

const formatCpu = (value?: string): string => {
  if (!value) {
    return '-';
  }

  if (value.endsWith('n')) {
    const cores = Number(value.slice(0, -1)) / 1_000_000_000;
    return Number.isFinite(cores) ? `${cores.toFixed(2)} cores` : value;
  }

  if (value.endsWith('m')) {
    const cores = Number(value.slice(0, -1)) / 1000;
    return Number.isFinite(cores) ? `${cores.toFixed(2)} cores` : value;
  }

  return value;
};

const formatMemory = (value?: string): string => {
  if (!value) {
    return '-';
  }

  if (value.endsWith('Ki')) {
    const gib = Number(value.slice(0, -2)) / 1024 / 1024;
    return Number.isFinite(gib) ? `${gib.toFixed(1)} GiB` : value;
  }

  return value;
};

const aiopsWorkloadItems = (summary: ClusterSummary) => [
  ...(summary.aiopsWorkloads?.deployments ?? []),
  ...(summary.aiopsWorkloads?.daemonsets ?? []),
];

const aiopsWorkloadNames = (summary: ClusterSummary, limit = 3): string => {
  const workloads = aiopsWorkloadItems(summary);
  const names = workloads.slice(0, limit).map((workload) => `${workload.namespace}/${workload.name}`);
  const extra = workloads.length - names.length;
  return extra > 0 ? `${names.join(', ')} 외 ${extra}` : names.join(', ');
};

const buildScopes = (summary: ClusterSummary, status: AiopsRuntimeStatus): ScopeItem[] => {
  const records = actionRecords(status);
  const auditCount = status.spec.records.auditRecords?.length ?? 0;
  const resources = summary.resources?.items ?? [];
  const operatorSeverityValue: Severity =
    summary.operators.degraded > 0 || summary.operators.unavailable > 0
      ? 'risk'
      : summary.operators.progressing > 0
        ? 'warn'
        : 'ok';

  return [
    {
      id: 'cluster',
      keywords: ['클러스터', 'api', 'ocp', 'openshift'],
      name: clusterLabel(summary),
      detail: `OCP ${displayOpenShiftVersion(summary.version.version)} · API ${displayApiEndpoint(summary.apiUrl)}`,
      score: `${summary.healthScore}%`,
      severity: summary.healthScore >= 90 ? 'ok' : summary.healthScore >= 70 ? 'warn' : 'risk',
    },
    {
      id: 'nodes',
      keywords: ['노드', 'node'],
      name: '노드',
      detail: `정상 ${summary.nodes.ready} · 비정상 ${summary.nodes.notReady} · 압박 ${summary.nodes.pressureCount}`,
      score: `${summary.nodes.ready}/${summary.nodes.total}`,
      severity: summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok',
    },
    ...resources.map(
      (resource): ScopeItem => ({
        detail: localizeTelemetryText(resource.detail),
        detailRows: [
          { label: '종류', value: ledgerKindLabel(resource.kind) },
          { label: '전체', value: String(resource.total) },
          { label: '정상', value: String(resource.ready) },
          { label: '이슈', value: String(resource.issues) },
        ],
        id: `resource-${resource.id}`,
        keywords: resourceKeywords[resource.id] ?? [],
        name: resourceNameLabel(resource.id, resource.name, resource.kind),
        score: resource.score,
        severity: resource.severity,
      }),
    ),
    {
      id: 'operators',
      keywords: ['오퍼레이터', 'operator'],
      name: '클러스터 오퍼레이터',
      detail: `정상 ${summary.operators.available} · 저하 ${summary.operators.degraded} · 진행 중 ${summary.operators.progressing}`,
      score: `${summary.operators.available}/${summary.operators.total}`,
      severity: operatorSeverityValue,
    },
    {
      id: 'records',
      keywords: ['aiops', '기록', '감사', '액션'],
      name: 'AIOps 기록',
      detail: `감사 ${auditCount} · 조치 ${records.length}`,
      score: String(auditCount + records.length),
      severity: records.length > 0 ? 'warn' : 'ok',
    },
  ];
};

const scopeDetailRows = (
  scope: ScopeItem,
  summary: ClusterSummary,
  status: AiopsRuntimeStatus,
): Array<{ label: string; value: string }> => {
  const records = actionRecords(status);
  const auditCount = status.spec.records.auditRecords?.length ?? 0;

  if (scope.detailRows) {
    return scope.detailRows;
  }

  if (scope.id === 'nodes') {
    return [
      { label: '정상', value: `${summary.nodes.ready}/${summary.nodes.total}` },
      { label: '비정상', value: String(summary.nodes.notReady) },
      { label: '압박', value: String(summary.nodes.pressureCount) },
      { label: '메트릭', value: summary.nodes.metricsAvailable ? '수집 가능' : '수집 불가' },
    ];
  }

  if (scope.id === 'operators') {
    return [
      { label: '정상', value: `${summary.operators.available}/${summary.operators.total}` },
      { label: '저하', value: String(summary.operators.degraded) },
      { label: '진행 중', value: String(summary.operators.progressing) },
      { label: '사용 불가', value: String(summary.operators.unavailable) },
    ];
  }

  if (scope.id === 'records') {
    return [
      { label: '감사', value: String(auditCount) },
      { label: '조치', value: String(records.length) },
      { label: '진단', value: String(status.spec.records.diagnosticRequests.length) },
      { label: '실행기', value: status.spec.capabilities.actionExecutorConfigured ? '설정됨' : '미설정' },
    ];
  }

  return [
    { label: '건강도', value: `${summary.healthScore}%` },
    { label: 'API', value: displayApiEndpoint(summary.apiUrl) },
    { label: 'OpenShift', value: displayOpenShiftVersion(summary.version.version) },
    { label: '업데이트', value: formatTime(summary.updatedAt) },
  ];
};

const buildQueues = (summary: ClusterSummary, status: AiopsRuntimeStatus): QueueItem[] => {
  const nodeQueues = summary.nodes.items
    .filter((node) => nodeSeverity(node) !== 'ok')
    .map((node): QueueItem => {
      const pressures = pressureLabels(node.pressures);
      const severity: QueueItem['severity'] = !node.ready ? 'risk' : 'warn';
      const detail = [
        `역할 ${node.roles.join(', ') || '-'}`,
        node.ready ? '정상' : '비정상',
        pressures.length ? pressures.join(', ') : '',
      ]
        .filter(Boolean)
        .join(' · ');

      return {
        id: `node-${node.name}`,
        title: node.name,
        category: '노드',
        detail,
        evidence: [
          `kubelet ${node.kubeletVersion ?? '-'}`,
          `cpu ${formatCpu(node.usage.cpu)} · memory ${formatMemory(node.usage.memory)}`,
          `os ${localizeTelemetryText(node.osImage ?? '-')}`,
        ],
        source: 'OpenShift Node API',
        target: node.name,
        updatedAt: formatTime(summary.updatedAt),
        severity,
      };
    });

  const operatorQueues = summary.operators.issues.map((operator): QueueItem => {
    const severity = operatorSeverity(operator) === 'risk' ? 'risk' : 'warn';
    return {
      id: `operator-${operator.name}`,
      title: operator.name,
      category: '오퍼레이터',
      detail: localizeTelemetryText(operator.reason ?? operator.message ?? 'ClusterOperator 이슈'),
      evidence: [
        `available ${operator.available}`,
        `degraded ${operator.degraded}`,
        `progressing ${operator.progressing}`,
        operator.message ?? '',
      ].filter(Boolean),
      source: 'OpenShift ClusterOperator API',
      target: operator.name,
      updatedAt: formatTime(summary.updatedAt),
      severity,
    };
  });

  const versionQueue: QueueItem[] =
    summary.version.updateAvailable && summary.version.upgradeable === false
      ? [
          {
            id: 'version-upgrade-blocked',
            title: 'OCP 업데이트 사전 확인 필요',
            category: '클러스터 버전',
            detail: [
              `현재 ${displayOpenShiftVersion(summary.version.version)}`,
              summary.version.availableUpdates?.length
                ? `추천 업데이트 ${summary.version.availableUpdates.join(', ')}`
                : '추천 업데이트 확인됨',
              summary.version.upgradeableReason ?? 'Upgradeable=False',
            ].join(' · '),
            evidence: [
              `current ${displayOpenShiftVersion(summary.version.version)}`,
              `recommended updates ${summary.version.availableUpdates?.join(', ') || '-'}`,
              `conditional updates ${summary.version.conditionalUpdates?.join(', ') || '-'}`,
              `reason ${summary.version.upgradeableReason ?? 'Upgradeable=False'}`,
              summary.version.upgradeableMessage ?? 'ClusterVersion가 updateAvailable=true를 보고했습니다.',
            ],
            source: 'OpenShift ClusterVersion API',
            target: `OpenShift ${displayOpenShiftVersion(summary.version.version)}`,
            updatedAt: formatTime(summary.updatedAt),
            severity: 'warn',
          },
        ]
      : [];

  const pendingActionQueues = actionRecords(status)
    .filter((record) => {
      const phase = recordPhase(record).toLowerCase();
      return phase.includes('approval') || phase.includes('pending') || phase.includes('failed');
    })
    .map((record): QueueItem => {
      const phase = recordPhase(record);
      const severity: QueueItem['severity'] = phase.toLowerCase().includes('failed') ? 'risk' : 'warn';
      return {
        id: `record-${record.metadata?.name ?? record.kind ?? phase}`,
        title: record.metadata?.name ?? recordKindLabel(record.kind),
        category: 'AIOps 기록',
        detail: `${recordKindLabel(record.kind)} · ${ledgerResultLabel(phase)} · ${recordTarget(record)}`,
        evidence: [`created ${formatTime(record.metadata?.createdAt)}`, `target ${recordTarget(record)}`],
        source: recordKindLabel(record.kind),
        target: recordTarget(record),
        updatedAt: formatTime(record.metadata?.createdAt),
        severity,
      };
    });

  const resourceQueues = (summary.resources?.items ?? [])
    .filter((resource) => resource.issues > 0)
    .map((resource): QueueItem => {
      const severity: QueueItem['severity'] = resource.severity === 'risk' ? 'risk' : 'warn';
      return {
        id: `resource-${resource.id}`,
        title: `${resourceNameLabel(resource.id, resource.name, resource.kind)} 확인 필요`,
        category: '리소스',
        detail: localizeTelemetryText(resource.detail),
        evidence: [
          `kind ${resource.kind}`,
          `total ${resource.total}`,
          `ready ${resource.ready}`,
          `issues ${resource.issues}`,
        ],
        source: '게이트웨이 클러스터 요약',
        target: resourceNameLabel(resource.id, resource.name, resource.kind),
        updatedAt: formatTime(summary.updatedAt),
        severity,
      };
    });

  return [...resourceQueues, ...nodeQueues, ...operatorQueues, ...versionQueue, ...pendingActionQueues];
};

const buildAlerts = (summary: ClusterSummary, status: AiopsRuntimeStatus): AlertItem[] =>
  buildQueues(summary, status).map((item) => ({
    id: `alert-${item.id}`,
    title: item.title,
    target: localizeTelemetryText(item.detail),
    severity: item.severity,
    time: formatTime(summary.updatedAt),
  }));

const buildEndpoints = (summary: ClusterSummary): Endpoint[] => {
  const nodeEndpoints = summary.nodes.items.map((node): Endpoint => ({
    id: `node-${node.name}`,
    name: node.name,
    type: '노드',
    group: node.roles.join(', ') || '-',
    severity: nodeSeverity(node),
    cpu: formatCpu(node.usage.cpu),
    memory: formatMemory(node.usage.memory),
    latency: '-',
    lastEvent: formatTime(summary.updatedAt),
    path: `${localizeTelemetryText(node.osImage ?? '-')} / ${displayOpenShiftVersion(node.kubeletVersion ?? '-')}`,
  }));

  const operatorEndpoints = summary.operators.issues.map((operator): Endpoint => ({
    id: `operator-${operator.name}`,
    name: operator.name,
    type: '클러스터 오퍼레이터',
    group: operator.reason ?? '-',
    severity: operatorSeverity(operator),
    cpu: '-',
    memory: '-',
    latency: '-',
    lastEvent: formatTime(summary.updatedAt),
    path: localizeTelemetryText(operator.message ?? 'ClusterOperator 이슈'),
  }));

  const versionEndpoint: Endpoint[] = summary.version.version
    ? [
        {
          id: 'clusterversion-version',
          name: `OpenShift ${displayOpenShiftVersion(summary.version.version)}`,
          type: 'ClusterVersion',
          group: summary.version.channel ?? '-',
          severity: summary.version.upgradeable === false ? 'warn' : 'ok',
          cpu: '-',
          memory: '-',
          latency: '-',
          lastEvent: formatTime(summary.updatedAt),
          path: summary.version.upgradeableReason ?? (summary.version.updateAvailable ? '업데이트 가능' : '현재 버전'),
        },
      ]
    : [];

  const aiopsWorkloadEndpoints = aiopsWorkloadItems(summary).map((workload): Endpoint => ({
    id: `aiops-${workload.kind}-${workload.namespace}-${workload.name}`,
    name: workload.name,
    type: `AI/Ops ${ledgerKindLabel(workload.kind)}`,
    group: workload.namespace,
    severity: workload.severity,
    cpu: '-',
    memory: '-',
    latency: `정상 ${workload.ready}/${workload.desired}`,
    lastEvent: formatTime(workload.createdAt ?? summary.updatedAt),
    path: localizeTelemetryText(workload.detail),
  }));

  const resourceEndpoints = (summary.resources?.items ?? []).map((resource): Endpoint => ({
    id: `resource-${resource.id}`,
    name: resourceNameLabel(resource.id, resource.name, resource.kind),
    type: ledgerKindLabel(resource.kind),
    group: `전체 ${resource.total}`,
    severity: resource.severity,
    cpu: '-',
    memory: '-',
    latency: `이슈 ${resource.issues}건`,
    lastEvent: formatTime(summary.updatedAt),
    path: localizeTelemetryText(resource.detail),
  }));

  return [
    ...aiopsWorkloadEndpoints,
    ...resourceEndpoints,
    ...nodeEndpoints,
    ...operatorEndpoints,
    ...versionEndpoint,
  ];
};

const eventTone = (event: AiopsEventItem): ActivityItem['tone'] => {
  if (event.severity === 'risk') {
    return 'red';
  }
  if (event.severity === 'warn') {
    return 'orange';
  }
  if (event.source === 'AIOps Gateway') {
    return 'blue';
  }
  return 'green';
};

const eventActivityDetail = (event: AiopsEventItem): string =>
  [
    localizeTelemetryText(event.detail),
    sourceLabel(event.source),
    event.namespace ? `네임스페이스=${displayNamespaceLabel(event.namespace)}` : '',
  ]
    .filter(Boolean)
    .join(' · ');

const buildActivities = (
  summary: ClusterSummary,
  status: AiopsRuntimeStatus,
  eventFeed: AiopsEventFeed,
): ActivityItem[] => {
  const eventActivities = eventFeed.spec.items.map((event): ActivityItem => ({
    category: event.category,
    detail: eventActivityDetail(event),
    id: event.id,
    source: sourceLabel(event.source),
    target: event.target,
    time: event.time,
    title: event.title,
    tone: eventTone(event),
  }));

  if (eventActivities.length > 0) {
    return eventActivities.slice(0, 20);
  }

  const audits = (status.spec.records.auditRecords ?? []).map((record): ActivityItem => ({
    id: `audit-${record.metadata?.name ?? record.metadata?.createdAt}`,
    title: ledgerActionLabel(textValue(asObject(record.spec).action, 'audit_record')),
    detail: `${recordKindLabel(record.kind)} · ${formatTime(record.metadata?.createdAt)}`,
    tone: 'blue',
  }));

  const actions = actionRecords(status).map((record): ActivityItem => ({
    id: `action-${record.kind ?? 'record'}-${record.metadata?.name ?? record.metadata?.createdAt}`,
    title: record.metadata?.name ?? recordKindLabel(record.kind),
    detail: `${ledgerResultLabel(recordPhase(record))} · ${recordTarget(record)}`,
    tone: recordPhase(record).toLowerCase().includes('failed') ? 'red' : 'green',
  }));

  const aiopsWorkloads = summary.aiopsWorkloads;
  const signals: ActivityItem[] = [];

  if (summary.updatedAt) {
    signals.push({
      id: 'signal-summary-refresh',
      title: '클러스터 요약 수집',
      detail: `${clusterLabel(summary)} · ${formatTime(summary.updatedAt)}`,
      tone: 'blue',
    });
  }

  if (aiopsWorkloads && aiopsWorkloads.total > 0) {
    signals.push({
      id: 'signal-aiops-workloads-detected',
      title: 'AI/Ops 워크로드 감지',
      detail: [
        `디플로이먼트 ${aiopsWorkloads.deployments.length}`,
        `데몬셋 ${aiopsWorkloads.daemonsets.length}`,
        `이슈 ${aiopsWorkloads.issues}`,
        aiopsWorkloadNames(summary),
      ]
        .filter(Boolean)
        .join(' · '),
      tone: aiopsWorkloads.issues > 0 ? 'orange' : 'green',
    });
  }

  if (summary.version.upgradeable === false) {
    signals.push({
      id: 'signal-version-upgrade-blocked',
      title: 'ClusterVersion Upgradeable=False',
      detail: `${displayOpenShiftVersion(summary.version.version)} · ${summary.version.upgradeableReason ?? '사전 확인 필요'}`,
      tone: 'orange',
    });
  }

  const resourceSignals = (summary.resources?.items ?? [])
    .filter((resource) => resource.issues > 0)
    .slice(0, 4)
    .map((resource): ActivityItem => ({
      id: `signal-resource-${resource.id}`,
      title: `${resourceNameLabel(resource.id, resource.name, resource.kind)} 이슈 감지`,
      detail: localizeTelemetryText(resource.detail),
      tone: resource.severity === 'risk' ? 'red' : 'orange',
    }));

  return [...signals, ...audits, ...actions, ...resourceSignals].slice(0, 10);
};

type AlertEventRow = {
  category: string;
  detail: string;
  id: string;
  namespace: string;
  sample: boolean;
  severity: Severity;
  source: string;
  target: string;
  time: string;
  title: string;
};

type EventInboxGroup = {
  detail: string;
  id: string;
  kind: string;
  namespace: string;
  reason: string;
  relatedIssue?: QueueItem;
  rows: AlertEventRow[];
  severity: Severity;
  target: string;
  time: string;
  title: string;
};

const sampleAlertEvents: AlertEventRow[] = [
  {
    category: '샘플',
    detail: '게이트웨이 이벤트 스트림이 비어 있을 때 보이는 예시 이벤트입니다.',
    id: 'sample-event-gateway-empty',
    namespace: 'komsco-ai-dev',
    sample: true,
    severity: 'warn',
    source: '샘플 데이터',
    target: 'aiops-gateway',
    time: '07. 03. 오전 09:35',
    title: '샘플: 이벤트 수집 지연',
  },
  {
    category: '샘플',
    detail: '파드 재시작 증가를 알림/이벤트 화면에서 확인하는 예시입니다.',
    id: 'sample-event-pod-restart',
    namespace: 'cyntra',
    sample: true,
    severity: 'risk',
    source: '샘플 데이터',
    target: 'cyntra-api',
    time: '07. 03. 오전 09:28',
    title: '샘플: 파드 재시작 급증',
  },
];

const buildAlertEventRows = (
  summary: ClusterSummary,
  status: AiopsRuntimeStatus,
  eventFeed: AiopsEventFeed,
): AlertEventRow[] => {
  const eventRows = eventFeed.spec.items.map((event): AlertEventRow => ({
    category: event.category || '게이트웨이',
    detail: localizeTelemetryText(event.detail),
    id: `event-${event.id}`,
    namespace: event.namespace ?? '-',
    sample: false,
    severity: event.severity,
    source: sourceLabel(event.source),
    target: event.target ?? '-',
    time: formatTime(event.time),
    title: event.title,
  }));
  const alertRows = buildAlerts(summary, status).map((alert): AlertEventRow => ({
    category: '클러스터 알림',
    detail: alert.target,
    id: `alert-row-${alert.id}`,
    namespace: '-',
    sample: false,
    severity: alert.severity,
    source: '게이트웨이 요약',
    target: alert.target,
    time: alert.time,
    title: alert.title,
  }));
  const rows = [...eventRows, ...alertRows];
  return rows.length > 0 ? rows : sampleAlertEvents;
};

const eventSeverityRank: Record<Severity, number> = {
  ok: 0,
  warn: 1,
  risk: 2,
};

const eventReason = (row: AlertEventRow): string => {
  const text = `${row.title} ${row.detail} ${row.category}`.toLowerCase();
  if (/backoff|crashloopbackoff|imagepullbackoff/.test(text)) {
    return 'BackOff';
  }
  if (/probeerror|probe error/.test(text)) {
    return 'ProbeError';
  }
  if (/unhealthy|readiness|liveness|probe/.test(text)) {
    return 'Readiness 실패';
  }
  if (/build.*fail|docker build|build/.test(text)) {
    return 'Build 실패';
  }
  if (/failed|errimagepull|image pull|pull.*fail|실패/.test(text)) {
    return 'Failed';
  }
  if (/pulled/.test(text)) {
    return 'Pulled';
  }
  if (/created/.test(text)) {
    return 'Created';
  }
  if (/scheduled/.test(text)) {
    return 'Scheduled';
  }
  if (/addedinterface/.test(text)) {
    return 'AddedInterface';
  }
  return row.title.replace(/^샘플:\s*/, '').split(' · ')[0];
};

const eventObjectKind = (row: AlertEventRow): string => {
  const text = `${row.title} ${row.detail} ${row.source} ${row.target}`.toLowerCase();
  if (/build|docker/.test(text)) {
    return 'Build';
  }
  if (/route|ingress/.test(text)) {
    return 'Route';
  }
  if (/node|kubelet|pressure/.test(text)) {
    return 'Node';
  }
  if (/deployment|replicaset|statefulset|daemonset/.test(text)) {
    return 'Workload';
  }
  if (/pod|container|backoff|probe|scheduled|pulled|created/.test(text)) {
    return 'Pod';
  }
  return row.category === '샘플' ? 'Sample' : 'Resource';
};

const isNormalLifecycleEvent = (row: AlertEventRow): boolean =>
  row.severity === 'ok' || /^(Pulled|Created|Scheduled|AddedInterface)$/i.test(eventReason(row));

const relatedIssueForEvent = (group: Pick<EventInboxGroup, 'kind' | 'reason' | 'target'>, queues: QueueItem[]): QueueItem | undefined => {
  const haystack = `${group.kind} ${group.reason} ${group.target}`.toLowerCase();
  if (/pod|backoff|probe|failed|readiness/.test(haystack)) {
    return queues.find(isPodIssue) ?? queues.find(isDerivedWorkloadIssue);
  }
  if (/build/.test(haystack)) {
    return queues.find((item) => /build|deployment|디플로이먼트/i.test(`${item.title} ${item.detail}`));
  }
  return queues.find((item) => item.severity === 'risk') ?? queues[0];
};

const buildEventInboxGroups = (rows: AlertEventRow[], queues: QueueItem[]): EventInboxGroup[] => {
  const groups = new Map<string, EventInboxGroup>();

  rows.forEach((row) => {
    const reason = eventReason(row);
    const kind = eventObjectKind(row);
    const key = `${reason}-${kind}-${row.severity}`;
    const current = groups.get(key);
    if (!current) {
      const seed: EventInboxGroup = {
        detail: row.detail,
        id: key,
        kind,
        namespace: row.namespace,
        reason,
        rows: [row],
        severity: row.severity,
        target: row.target,
        time: row.time,
        title: reason,
      };
      seed.relatedIssue = relatedIssueForEvent(seed, queues);
      groups.set(key, seed);
      return;
    }

    current.rows.push(row);
    current.severity = eventSeverityRank[row.severity] > eventSeverityRank[current.severity] ? row.severity : current.severity;
    if (current.target === '-' && row.target !== '-') {
      current.target = row.target;
    }
    if (current.namespace === '-' && row.namespace !== '-') {
      current.namespace = row.namespace;
    }
  });

  return Array.from(groups.values()).sort((a, b) => eventSeverityRank[b.severity] - eventSeverityRank[a.severity] || b.rows.length - a.rows.length);
};

const eventGroupFromRow = (row: AlertEventRow, queues: QueueItem[]): EventInboxGroup => {
  const reason = eventReason(row);
  const group: EventInboxGroup = {
    detail: row.detail,
    id: row.id,
    kind: eventObjectKind(row),
    namespace: row.namespace,
    reason,
    rows: [row],
    severity: row.severity,
    target: row.target,
    time: row.time,
    title: reason,
  };
  group.relatedIssue = relatedIssueForEvent(group, queues);
  return group;
};

const eventAssistantContext = (
  group: EventInboxGroup,
  source: AssistantLaunchContext['source'],
): AssistantLaunchContext => {
  const base: AssistantLaunchContext = {
    ...parseAssistantTarget(
      [group.namespace, group.target].filter((value) => value && value !== '-').join('/'),
      group.kind,
    ),
    actionType: 'event-rca',
    evidenceRefs: [
      group.detail,
      `${group.rows.length} events`,
      group.relatedIssue?.title ?? '',
    ].filter(Boolean),
    reason: group.reason,
    severity: group.severity,
    source,
    promptDraft: '',
  };
  return {
    ...base,
    promptDraft: buildAssistantPrompt(base),
  };
};

const eventCommands = (group: EventInboxGroup): Array<{ command: string; title: string }> => {
  const namespace = group.namespace && group.namespace !== '-' ? group.namespace : '<namespace>';
  const target = group.target && group.target !== '-' ? group.target : '<name>';
  if (group.kind === 'Pod') {
    return [
      { title: 'Pod 상세', command: `oc describe pod -n ${namespace} ${target}` },
      { title: 'Pod 로그', command: `oc logs -n ${namespace} ${target} --all-containers --tail=120` },
      { title: '최근 이벤트', command: `oc get events -n ${namespace} --sort-by=.lastTimestamp` },
    ];
  }
  if (group.kind === 'Build') {
    return [
      { title: 'Build 로그', command: `oc logs -n ${namespace} build/${target}` },
      { title: 'Build 상세', command: `oc describe build -n ${namespace} ${target}` },
    ];
  }
  return [
    { title: '대상 이벤트', command: `oc get events -A --field-selector involvedObject.name=${target} --sort-by=.lastTimestamp` },
  ];
};

const reportHealthLabel = (summary: ClusterSummary): string => {
  if (summary.healthScore >= 90) {
    return '정상';
  }
  if (summary.healthScore >= 70) {
    return '주의';
  }
  return '위험';
};

type RcaQueueGroup = {
  id: string;
  items: QueueItem[];
  title: string;
};

type RcaEvidencePackRow = {
  collector: string;
  command: string;
  field: string;
  freshness: string;
  source: string;
  status: 'attention' | 'collected' | 'excluded' | 'normal';
  value: string;
};

type RcaFindingRow = {
  detail: string;
  kicker: string;
  meta: string;
  title: string;
  tone: 'primary' | 'supporting' | 'validation';
};

type RcaRunbookGate = {
  command: string;
  detail: string;
  gate: string;
  id: string;
  status: string;
  title: string;
  tone: 'ok' | 'warn' | 'risk';
};

type RcaIssueType =
  | 'WORKLOAD_PODS'
  | 'WORKLOAD_DERIVED'
  | 'PLATFORM_UPDATE'
  | 'CLUSTER_OPERATOR'
  | 'NODE_HEALTH'
  | 'AIOPS_CONTROL'
  | 'OTHER';

type PodRcaSummary = {
  active: number;
  completed: number;
  failed: number;
  issueCandidates: number;
  pending: number;
  ready: number;
  restartsTotal: number;
  running: number;
  runningNotReady: number;
  total: number;
};

type RcaCaseHeaderModel = {
  baseline: string;
  caseState: string;
  family: string;
  finding: string;
  issueLine: string;
  metrics: Array<{ label: string; value: string }>;
  scope: string;
  title: string;
};

type RcaCommandBundleItem = {
  command: string;
  title: string;
};

type RcaTimelineItem = {
  detail: string;
  title: string;
};

type TopologyNodeKey =
  | 'daemonsets'
  | 'deployments'
  | 'nodes'
  | 'persistentvolumeclaims'
  | 'pods'
  | 'replicasets'
  | 'routes'
  | 'services'
  | 'statefulsets';

type TopologyEdgeMode = 'all' | 'ownership' | 'runtime' | 'traffic';

type TraceInspectorModel = {
  commands: Array<{ command: string; title: string }>;
  focus: string;
  insight: string;
  reasons: Array<{ detail: string; label: string }>;
  severity: Severity;
  signals: Array<{ label: string; tone?: Severity; value: string }>;
  title: string;
  trace: string;
};

const isClusterUpdateIssue = (item: QueueItem): boolean =>
  item.category === '클러스터 버전' || /clusterversion|cluster update|upgradeable|업데이트 사전|ocp 업데이트/i.test(`${item.id} ${item.title} ${item.target ?? ''}`);

const isPodIssue = (item: QueueItem | undefined): boolean =>
  Boolean(item && /(^resource-pods$)|pod|pods|파드/i.test(`${item.id} ${item.title} ${item.target ?? ''}`));

const isDerivedWorkloadIssue = (item: QueueItem | undefined): boolean =>
  Boolean(item && /deployment|디플로이먼트|replicaset|레플리카셋|statefulset|daemonset/i.test(`${item.id} ${item.title} ${item.target ?? ''}`));

const rcaIssueType = (item: QueueItem | undefined): RcaIssueType => {
  if (!item) {
    return 'OTHER';
  }
  if (isPodIssue(item)) {
    return 'WORKLOAD_PODS';
  }
  if (isDerivedWorkloadIssue(item)) {
    return 'WORKLOAD_DERIVED';
  }
  if (isClusterUpdateIssue(item)) {
    return 'PLATFORM_UPDATE';
  }
  if (item.category === '오퍼레이터') {
    return 'CLUSTER_OPERATOR';
  }
  if (item.category === '노드') {
    return 'NODE_HEALTH';
  }
  if (item.category === 'AIOps 기록') {
    return 'AIOPS_CONTROL';
  }
  return 'OTHER';
};

const resourceById = (summary: ClusterSummary, id: string) =>
  (summary.resources?.items ?? []).find((resource) => resource.id === id);

const detailNumber = (detail: string | undefined, label: string): number => {
  if (!detail) {
    return 0;
  }
  const match = detail.match(new RegExp(`(?:^|[·,])\\s*${label}\\s+([0-9]+)`, 'i'));
  return match ? Number(match[1]) : 0;
};

const buildPodRcaSummary = (summary: ClusterSummary): PodRcaSummary => {
  const pods = resourceById(summary, 'pods');
  const running = detailNumber(pods?.detail, 'Running');
  const ready = detailNumber(pods?.detail, 'Ready') || Number(pods?.ready ?? 0);
  const pending = detailNumber(pods?.detail, 'Pending');
  const failed = detailNumber(pods?.detail, 'Failed');
  const completed = detailNumber(pods?.detail, 'Succeeded') || detailNumber(pods?.detail, 'Completed');
  const restartsTotal = detailNumber(pods?.detail, 'Restarts');
  const runningNotReady = Math.max(0, running - ready);
  const calculatedCandidates = pending + failed + runningNotReady;
  const issueCandidates = calculatedCandidates || pods?.issues || 0;

  return {
    active: running + pending + failed,
    completed,
    failed,
    issueCandidates,
    pending,
    ready,
    restartsTotal,
    running,
    runningNotReady,
    total: pods?.total ?? 0,
  };
};

const podMetricLine = (podSummary: PodRcaSummary): string =>
  `실행중 ${podSummary.running} · 준비 ${podSummary.ready} · 대기 ${podSummary.pending} · 실패 ${podSummary.failed} · 완료 ${podSummary.completed} · 재시작 ${podSummary.restartsTotal}`;

const podIssueFormula = (podSummary: PodRcaSummary): string =>
  `이슈 후보 ${podSummary.issueCandidates} = 대기 ${podSummary.pending} + 실패 ${podSummary.failed} + 실행중 미준비 ${podSummary.runningNotReady}`;

const buildRcaQueueGroups = (queues: QueueItem[]): RcaQueueGroup[] => {
  const groupedIds = new Set<string>();
  const take = (predicate: (item: QueueItem) => boolean) =>
    queues.filter((item) => {
      if (!predicate(item) || groupedIds.has(item.id)) {
        return false;
      }
      groupedIds.add(item.id);
      return true;
    });
  const workloadOrder = (item: QueueItem): number => {
    if (isPodIssue(item)) {
      return 0;
    }
    if (/deployment|디플로이먼트/i.test(`${item.id} ${item.title} ${item.target ?? ''}`)) {
      return 1;
    }
    if (/replicaset|레플리카셋/i.test(`${item.id} ${item.title} ${item.target ?? ''}`)) {
      return 2;
    }
    return 3;
  };
  const workloadItems = take((item) => isPodIssue(item) || isDerivedWorkloadIssue(item)).sort(
    (a, b) => workloadOrder(a) - workloadOrder(b),
  );
  const groups: RcaQueueGroup[] = [
    { id: 'workload', title: '워크로드 런타임', items: workloadItems },
    { id: 'platform', title: '플랫폼 라이프사이클', items: take((item) => isClusterUpdateIssue(item) || item.category === '오퍼레이터') },
    { id: 'infra', title: '인프라', items: take((item) => item.category === '노드') },
    { id: 'aiops', title: 'AIOps 제어', items: take((item) => item.category === 'AIOps 기록') },
  ];
  const other = queues.filter((item) => !groupedIds.has(item.id));
  if (other.length > 0) {
    groups.push({ id: 'other', title: '기타 신호', items: other });
  }
  return groups.filter((group) => group.items.length > 0);
};

const defaultRcaSelection = (queues: QueueItem[]): string =>
  queues.find(isPodIssue)?.id ?? queues.find((item) => item.severity === 'risk')?.id ?? queues.find(isClusterUpdateIssue)?.id ?? queues[0]?.id ?? '';

const rcaCaseId = (item: QueueItem | undefined, index: number): string =>
  item && isClusterUpdateIssue(item) ? 'RCA-20250703-004' : `RCA-20250703-${String(index + 1).padStart(3, '0')}`;

const rcaReason = (summary: ClusterSummary, item?: QueueItem): string => {
  const reasonEvidence = item ? evidenceRows(item).find((row) => row.label === 'reason')?.value : '';
  return summary.version.upgradeableReason ?? reasonEvidence ?? 'AdminAckRequired';
};

const rcaCurrentVersion = (summary: ClusterSummary, item?: QueueItem): string => {
  const current = item ? evidenceRows(item).find((row) => row.label === 'current')?.value : '';
  return displayOpenShiftVersion(summary.version.version ?? current ?? '-');
};

const rcaAvailableUpdates = (summary: ClusterSummary, item?: QueueItem): string => {
  const evidence = item ? evidenceRows(item).find((row) => row.label === 'recommended updates')?.value : '';
  return summary.version.availableUpdates?.join(' · ') || evidence || '-';
};

const rcaConditionalUpdates = (summary: ClusterSummary, item?: QueueItem): string => {
  const evidence = item ? evidenceRows(item).find((row) => row.label === 'conditional updates')?.value : '';
  return summary.version.conditionalUpdates?.join(' · ') || evidence || '-';
};

const buildRcaCaseHeader = (
  summary: ClusterSummary,
  item: QueueItem | undefined,
  podSummary: PodRcaSummary,
): RcaCaseHeaderModel => {
  const issueType = rcaIssueType(item);
  if (issueType === 'PLATFORM_UPDATE') {
    return {
      baseline: `클러스터 기준: OCP ${rcaCurrentVersion(summary, item)}`,
      caseState: '조사 중 · 관리자 확인 필요 · 변경 창 검증 필요',
      family: '플랫폼 라이프사이클 / RCA 케이스',
      finding: `ClusterVersion Upgradeable=False · 사유 ${rcaReason(summary, item)}`,
      issueLine: `업데이트 후보 ${rcaAvailableUpdates(summary, item)} · 조건부 업데이트 ${rcaConditionalUpdates(summary, item)}`,
      metrics: [
        { label: '현재', value: rcaCurrentVersion(summary, item) },
        { label: '후보', value: rcaAvailableUpdates(summary, item) },
        { label: '조건부', value: rcaConditionalUpdates(summary, item) },
        { label: 'CO 저하', value: String(summary.operators.degraded) },
      ],
      scope: `ClusterVersion/version · 스냅샷 ${formatTime(summary.updatedAt)} · 게이트웨이 정상`,
      title: '클러스터 업데이트 차단',
    };
  }

  if (issueType === 'WORKLOAD_PODS' || issueType === 'WORKLOAD_DERIVED') {
    const derivedTitle = issueType === 'WORKLOAD_DERIVED'
      ? `${item?.target ?? item?.title ?? '워크로드'} 가용성 변화`
      : '파드 상태 저하';
    return {
      baseline: `클러스터 기준: OCP ${displayOpenShiftVersion(summary.version.version)}`,
      caseState: '조사 중 · 증거 일부 수집 · 노드/PVC 검증 필요',
      family: issueType === 'WORKLOAD_DERIVED' ? '워크로드 런타임 / 파생 신호' : '워크로드 런타임 / RCA 케이스',
      finding: issueType === 'WORKLOAD_DERIVED'
        ? '컨트롤러 가용성 변화는 파드 준비 상태와 소유 관계를 함께 검증해야 합니다'
        : '활성 파드 상태 변화가 감지되어 컨테이너/이벤트 검증이 필요합니다',
      issueLine: `${podIssueFormula(podSummary)} · 완료 파드는 활성 상태 점수에서 제외`,
      metrics: [
        { label: '실행중', value: String(podSummary.running) },
        { label: '준비', value: String(podSummary.ready) },
        { label: '대기', value: String(podSummary.pending) },
        { label: '실패', value: String(podSummary.failed) },
        { label: '완료', value: String(podSummary.completed) },
        { label: '재시작', value: String(podSummary.restartsTotal) },
      ],
      scope: `전체 네임스페이스 · 이슈 후보 ${podSummary.issueCandidates} · 스냅샷 ${formatTime(summary.updatedAt)} · 게이트웨이 정상`,
      title: derivedTitle,
    };
  }

  return {
    baseline: `클러스터 기준: OCP ${displayOpenShiftVersion(summary.version.version)}`,
    caseState: '조사 중 · 증거 일부 수집 · 수동 검증 필요',
    family: `${issueType} / RCA 케이스`,
    finding: item?.detail ?? '게이트웨이 신호 검증 필요',
    issueLine: item?.evidence.slice(0, 3).join(' · ') || '증거 수집 대기',
    metrics: [
      { label: '클러스터', value: clusterLabel(summary) },
      { label: '심각도', value: item?.severity === 'risk' ? '높음' : '중간' },
      { label: '출처', value: item?.source ?? '게이트웨이 요약' },
      { label: '스냅샷', value: formatTime(summary.updatedAt) },
    ],
    scope: `${item?.target ?? '클러스터 범위'} · 게이트웨이 정상`,
    title: item?.title ?? '조사 대상 없음',
  };
};

const rcaQueueBadgeLabel = (item: QueueItem): string => {
  if (isDerivedWorkloadIssue(item)) {
    return '파생';
  }
  return item.severity === 'risk' ? '높음' : '중간';
};

const rcaQueueDetail = (summary: ClusterSummary, item: QueueItem, podSummary: PodRcaSummary): string => {
  if (isPodIssue(item)) {
    return `활성 이슈 후보 ${podSummary.issueCandidates}개 · 재시작 ${podSummary.restartsTotal}`;
  }
  if (isDerivedWorkloadIssue(item)) {
    return `${item.detail} · 파드 준비 상태에서 파생`;
  }
  if (isClusterUpdateIssue(item)) {
    return `ClusterVersion ${rcaCurrentVersion(summary, item)} · ${rcaReason(summary, item)}`;
  }
  return item.detail;
};

const buildRcaFindings = (summary: ClusterSummary, item: QueueItem | undefined, podSummary: PodRcaSummary): RcaFindingRow[] => {
  if (!item) {
    return [];
  }

  if (isClusterUpdateIssue(item)) {
    const reason = rcaReason(summary, item);
    return [
      {
        detail: `Reason ${reason}`,
        kicker: '주 원인',
        meta: '신뢰도 높음 · 증거 5 · 미검증 2 · 반증 0',
        title: 'ClusterVersion Upgradeable=False',
        tone: 'primary',
      },
      {
        detail: `${rcaCurrentVersion(summary, item)} -> ${rcaAvailableUpdates(summary, item)}`,
        kicker: '보조 근거',
        meta: `conditionalUpdates ${rcaConditionalUpdates(summary, item)}`,
        title: '추천 업데이트 경로 존재',
        tone: 'supporting',
      },
      {
        detail: 'ClusterOperators, MachineConfigPools, Nodes 상태를 추가 검증해야 합니다.',
        kicker: '추가 검증',
        meta: 'CO status · MCP degraded/updating · NotReady nodes',
        title: '플랫폼 의존성 게이트',
        tone: 'validation',
      },
    ];
  }

  if (isPodIssue(item) || isDerivedWorkloadIssue(item)) {
    return [
      {
        detail: '활성 파드 상태 변화 감지',
        kicker: '주 원인',
        meta: `${podMetricLine(podSummary)} · 이슈 후보 ${podSummary.issueCandidates}`,
        title: isDerivedWorkloadIssue(item) ? '컨트롤러 가용성 변화' : '활성 파드 상태 변화',
        tone: 'primary',
      },
      {
        detail: '파드 -> 컨테이너 상태 -> 이벤트 -> 소유 관계 -> 노드 -> PVC 순서로 검증합니다.',
        kicker: '보조 근거',
        meta: `활성 ${podSummary.active} · 완료 ${podSummary.completed} 제외 · 재시작 ${podSummary.restartsTotal}`,
        title: '예상 점검 경로',
        tone: 'supporting',
      },
      {
        detail: '컨테이너 대기 사유, 마지막 종료 상태, 재시작 상위 파드, 경고 이벤트, 노드 압박, 볼륨 마운트 실패 증거가 아직 필요합니다.',
        kicker: '추가 검증',
        meta: '컨테이너 상태 · 이벤트 · 재시작 상위 · 노드 압박 · PVC 마운트',
        title: '미수집 증거',
        tone: 'validation',
      },
    ];
  }

  return [
    {
      detail: item.detail,
      kicker: '주 원인',
      meta: `${item.category ?? '운영 이슈'} · ${item.source ?? '게이트웨이 요약'}`,
      title: item.title,
      tone: 'primary',
    },
    {
      detail: 'Pod phase, container state, restart count, events를 같은 네임스페이스 기준으로 확인합니다.',
      kicker: '보조 근거',
      meta: 'Pod lifecycle · Event stream · Controller status',
      title: '워크로드 런타임 신호',
      tone: 'supporting',
    },
    {
      detail: 'Node condition, PVC mount, image pull, readiness/liveness probe를 배제해야 합니다.',
      kicker: '추가 검증',
      meta: 'Node · PVC · Image · Probe',
      title: '런타임 의존성 점검',
      tone: 'validation',
    },
  ];
};

const buildRcaEvidencePack = (
  summary: ClusterSummary,
  item: QueueItem | undefined,
  podSummary: PodRcaSummary,
): RcaEvidencePackRow[] => {
  const collectedAt = formatTime(summary.updatedAt) || item?.updatedAt || '-';
  if (item && isClusterUpdateIssue(item)) {
    const reason = rcaReason(summary, item);
    return [
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o yaml',
        field: 'status.desired.version',
        freshness: '실시간',
        source: 'ClusterVersion/version',
        status: 'normal',
        value: rcaCurrentVersion(summary, item),
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o jsonpath={.status.availableUpdates}',
        field: 'status.availableUpdates',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'collected',
        value: rcaAvailableUpdates(summary, item),
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o jsonpath={.status.conditionalUpdates}',
        field: 'status.conditionalUpdates',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'collected',
        value: rcaConditionalUpdates(summary, item),
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o yaml',
        field: 'conditions[Upgradeable].status',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'attention',
        value: summary.version.upgradeable === false || reason !== '-' ? 'False' : '-',
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o yaml',
        field: 'conditions[Upgradeable].reason',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'attention',
        value: reason,
      },
      {
        collector: 'gateway/config.openshift.io',
        command: 'oc get clusterversion version -o yaml',
        field: 'conditions[Upgradeable].message',
        freshness: collectedAt,
        source: 'ClusterVersion/version',
        status: 'collected',
        value: summary.version.upgradeableMessage ?? 'Admin acknowledgement required before this update edge can proceed.',
      },
    ];
  }

  if (item && (isPodIssue(item) || isDerivedWorkloadIssue(item))) {
    const inventoryCommand = 'oc get pods -A -o json';
    return [
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '종류',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'collected',
        value: 'Pod',
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '전체',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'collected',
        value: String(podSummary.total),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '실행중',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'collected',
        value: String(podSummary.running),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '준비',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'collected',
        value: String(podSummary.ready),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '대기',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: podSummary.pending > 0 ? 'attention' : 'normal',
        value: String(podSummary.pending),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '실패',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: podSummary.failed > 0 ? 'attention' : 'normal',
        value: String(podSummary.failed),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '완료',
        freshness: collectedAt,
        source: '파드 인벤토리',
        status: 'excluded',
        value: String(podSummary.completed),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '이슈 후보',
        freshness: collectedAt,
        source: '파드 상태 계산',
        status: podSummary.issueCandidates > 0 ? 'attention' : 'normal',
        value: String(podSummary.issueCandidates),
      },
      {
        collector: '게이트웨이 클러스터 요약',
        command: inventoryCommand,
        field: '총 재시작',
        freshness: collectedAt,
        source: '파드 재시작 요약',
        status: podSummary.restartsTotal > 0 ? 'attention' : 'normal',
        value: String(podSummary.restartsTotal),
      },
    ];
  }

  return (item ? evidenceRows(item) : []).map((row): RcaEvidencePackRow => ({
    collector: item?.source ?? '게이트웨이 요약',
    command: item?.category === '노드' ? 'oc describe node <node>' : 'oc describe pod -n <namespace> <pod>',
    field: evidenceLabel(row.label),
    freshness: item?.updatedAt ?? collectedAt,
    source: item?.target ?? item?.title ?? '-',
    status: row.status,
    value: row.value,
  }));
};

const buildRcaRunbookGates = (
  summary: ClusterSummary,
  item: QueueItem | undefined,
  podSummary: PodRcaSummary,
): RcaRunbookGate[] => {
  if (item && isClusterUpdateIssue(item)) {
    return [
      {
        command: 'oc get clusterversion version -o yaml',
        detail: 'ClusterVersion 조건과 history를 원본 YAML로 확인합니다.',
        gate: 'Upgradeable=False',
        id: 'cv-condition',
        status: '필수',
        title: 'ClusterVersion 조건 확인',
        tone: 'warn',
      },
      {
        command: 'oc get clusterversion version -o jsonpath={.status.conditions[?(@.type=="Upgradeable")].reason}',
        detail: `Reason ${rcaReason(summary, item)}`,
        gate: 'AdminAckRequired',
        id: 'upgradeable-reason',
        status: '게이트 실패',
        title: 'Upgradeable 사유 확인',
        tone: 'risk',
      },
      {
        command: 'oc get clusterversion version -o jsonpath={.status.availableUpdates}',
        detail: `availableUpdates ${rcaAvailableUpdates(summary, item)} · conditionalUpdates ${rcaConditionalUpdates(summary, item)}`,
        gate: '추천 edge / 조건부 edge 분리',
        id: 'update-edges',
        status: '수집됨',
        title: '업데이트 경로 비교',
        tone: 'ok',
      },
      {
        command: 'oc get clusteroperators',
        detail: `Available ${summary.operators.available}/${summary.operators.total} · Degraded ${summary.operators.degraded}`,
        gate: 'Available=True, Degraded=False',
        id: 'clusteroperators',
        status: summary.operators.degraded > 0 ? '게이트 실패' : '수집됨',
        title: 'ClusterOperators 점검',
        tone: summary.operators.degraded > 0 ? 'risk' : 'ok',
      },
      {
        command: 'oc get mcp && oc get nodes',
        detail: `Ready nodes ${summary.nodes.ready}/${summary.nodes.total} · NotReady ${summary.nodes.notReady}`,
        gate: 'DEGRADED=False, NotReady=0',
        id: 'mcp-nodes',
        status: '미수집',
        title: 'MCP / 노드 준비 상태 점검',
        tone: summary.nodes.notReady > 0 ? 'risk' : 'warn',
      },
      {
        command: 'oc adm upgrade --acknowledge <admin-ack-id>',
        detail: 'Admin acknowledgement 또는 change ticket 필요 여부를 결정합니다.',
        gate: '변경 승인 필요',
        id: 'change-request',
        status: '권장',
        title: '변경 승인 생성',
        tone: 'warn',
      },
    ];
  }

  if (item && (isPodIssue(item) || isDerivedWorkloadIssue(item))) {
    return [
      {
        command: 'oc get pods -A -o wide',
        detail: podMetricLine(podSummary),
        gate: `대기 / 실패 / 실행중 미준비 / 재시작 상위 파드 확인 · ${podIssueFormula(podSummary)}`,
        id: 'pod-inventory',
        status: '수집됨',
        title: '파드 인벤토리 및 준비 상태',
        tone: podSummary.issueCandidates > 0 ? 'risk' : 'ok',
      },
      {
        command: 'oc get pods -A -o json',
        detail: '컨테이너 대기 사유, 마지막 종료 상태, restartCount 상위 파드가 필요합니다.',
        gate: '컨테이너 대기/종료/재시작 상태',
        id: 'container-state',
        status: '미수집',
        title: '컨테이너 상태 증거',
        tone: 'warn',
      },
      {
        command: 'oc get events -A --field-selector involvedObject.kind=Pod --sort-by=.lastTimestamp',
        detail: '최근 Warning 이벤트와 probe/image/volume 관련 reason을 확인합니다.',
        gate: '최근 경고 이벤트',
        id: 'pod-events',
        status: '필수',
        title: '최근 파드 경고 이벤트',
        tone: 'warn',
      },
      {
        command: 'oc get deploy,rs,sts,ds -A',
        detail: 'Deployment / ReplicaSet / StatefulSet / DaemonSet owner chain을 파드 후보와 연결합니다.',
        gate: '소유 관계 매핑',
        id: 'owner-chain',
        status: isDerivedWorkloadIssue(item) ? '필수' : '권장',
        title: '컨트롤러 소유 관계',
        tone: 'warn',
      },
      {
        command: 'oc get nodes && oc get pvc -A',
        detail: `Node Ready ${summary.nodes.ready}/${summary.nodes.total} · PVC ${resourceById(summary, 'persistentvolumeclaims')?.score ?? '-'}`,
        gate: '노드 압박 / PVC 마운트 검증',
        id: 'runtime-dependency',
        status: '미수집',
        title: '런타임 의존성 검증',
        tone: summary.nodes.notReady > 0 ? 'risk' : 'warn',
      },
    ];
  }

  return [
    {
      command: 'oc get pods -A -o wide',
      detail: '비정상 파드를 네임스페이스 기준으로 분리합니다.',
      gate: 'Pending/Failed/CrashLoopBackOff',
      id: 'pod-phase',
      status: '필수',
      title: '파드 phase / 컨테이너 상태 확인',
      tone: 'warn',
    },
    {
      command: 'oc describe pod -n <namespace> <pod>',
      detail: '이벤트, probe, image pull, volume mount 실패를 확인합니다.',
      gate: 'Events / Probe / Image / Volume',
      id: 'pod-events',
      status: '필수',
      title: '파드 이벤트 확인',
      tone: 'warn',
    },
    {
      command: 'oc get node && oc describe node <node>',
      detail: '스케줄링/노드 압박/NotReady를 배제합니다.',
      gate: 'Node Ready=True',
      id: 'node-check',
      status: '미수집',
      title: '노드 의존성 점검',
      tone: 'warn',
    },
  ];
};

const buildRcaCommandBundle = (
  item: QueueItem | undefined,
  runbookGates: RcaRunbookGate[],
): RcaCommandBundleItem[] => {
  if (item && (isPodIssue(item) || isDerivedWorkloadIssue(item))) {
    return [
      { title: '파드 인벤토리', command: 'oc get pods -A -o wide' },
      {
        title: '최근 파드 경고',
        command: 'oc get events -A --field-selector involvedObject.kind=Pod --sort-by=.lastTimestamp',
      },
      { title: '선택 파드 상세', command: 'oc describe pod -n <namespace> <pod>' },
      { title: '파드 YAML', command: 'oc get pod -n <namespace> <pod> -o yaml' },
      { title: '소유 관계', command: 'oc get deploy,rs,sts,ds -A' },
    ];
  }

  return runbookGates.map((gate) => ({ title: gate.title, command: gate.command }));
};

const buildRcaTimeline = (
  summary: ClusterSummary,
  item: QueueItem | undefined,
  podSummary: PodRcaSummary,
  findings: RcaFindingRow[],
): RcaTimelineItem[] => {
  if (item && (isPodIssue(item) || isDerivedWorkloadIssue(item))) {
    return [
      {
        detail: podMetricLine(podSummary),
        title: '파드 인벤토리 수집',
      },
      {
        detail: `${podIssueFormula(podSummary)} · 완료 ${podSummary.completed}개 제외`,
        title: '이슈 후보 계산',
      },
      {
        detail: 'Deployment · ReplicaSet · StatefulSet · DaemonSet 소유 관계 매핑 필요',
        title: '컨트롤러 소유 관계 대기',
      },
      {
        detail: `노드 정상 ${summary.nodes.ready}/${summary.nodes.total} · PVC ${resourceById(summary, 'persistentvolumeclaims')?.score ?? '-'}`,
        title: '런타임 의존성 연결',
      },
      {
        detail: findings[0]?.title ?? '컨테이너/이벤트 검증 필요',
        title: 'RCA 판단 생성',
      },
    ];
  }

  if (item && isClusterUpdateIssue(item)) {
    return [
      { detail: 'ClusterVersion Upgradeable 상태 수집', title: 'ClusterVersion condition collected' },
      { detail: 'availableUpdates / conditionalUpdates 비교', title: 'Update edges parsed' },
      { detail: `Reason ${rcaReason(summary, item)}`, title: 'AdminAckRequired detected' },
      { detail: findings[0]?.title ?? 'ClusterVersion finding generated', title: 'RCA judgment generated' },
    ];
  }

  return [
    { detail: item?.source ?? '게이트웨이 요약', title: 'Signal collected' },
    { detail: item?.detail ?? '증거 수집 대기', title: 'Evidence reviewed' },
    { detail: findings[0]?.title ?? '판단 생성 대기', title: 'RCA judgment generated' },
  ];
};

const useLiveClock = (): string => {
  const [clock, setClock] = React.useState(() =>
    new Date().toLocaleTimeString('ko-KR', { hour12: false }),
  );

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      setClock(new Date().toLocaleTimeString('ko-KR', { hour12: false }));
    }, 1000);

    return () => window.clearInterval(timer);
  }, []);

  return clock;
};

const usePortalRuntime = (): RuntimeState => {
  const [summary, setSummary] = React.useState<ClusterSummary>(emptySummary);
  const [status, setStatus] = React.useState<AiopsRuntimeStatus>(emptyStatus);
  const [events, setEvents] = React.useState<AiopsEventFeed>(emptyEventFeed);
  const [loading, setLoading] = React.useState(true);
  const [isLive, setIsLive] = React.useState(false);
  const [error, setError] = React.useState('');

  const refresh = React.useCallback(async (options?: { silent?: boolean }) => {
    const silent = options?.silent ?? false;
    if (!silent) {
      setLoading(true);
    }

    const [summaryResult, statusResult, eventResult] = await Promise.allSettled([
      fetchClusterSummary(),
      fetchAiopsStatus(),
      fetchAiopsEvents(),
    ]);

    if (summaryResult.status === 'fulfilled') {
      setSummary(summaryResult.value);
    }

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value);
    }

    if (eventResult.status === 'fulfilled') {
      setEvents(eventResult.value);
    }

    const errors = [summaryResult, statusResult, eventResult]
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) => (result.reason instanceof Error ? result.reason.message : String(result.reason)));

    setIsLive(errors.length === 0);
    setError(errors.join('\n'));
    if (!silent) {
      setLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  React.useEffect(() => {
    const timer = window.setInterval(() => {
      void refresh({ silent: true });
    }, 30000);

    return () => window.clearInterval(timer);
  }, [refresh]);

  return { error, events, isLive, loading, refresh, status, summary };
};

const Sidebar: React.FC<{
  activeView: NavView;
  clock: string;
  setActiveView: (view: NavView) => void;
  summary: ClusterSummary;
}> = ({ activeView, clock, setActiveView, summary }) => (
  <aside className="portal-sidebar">
    <div className="portal-brand">
      <img alt="" aria-hidden="true" className="portal-brand__mark" src={aiopsIconUrl} />
      <div>
        <h1>AIOps for OCP</h1>
        <p>AI 운영 포털</p>
      </div>
    </div>

    <div className="portal-health">
      <div className="portal-health__label">시스템 건강도</div>
      <div className="portal-health__value">{summary.healthScore}%</div>
      <div className="portal-health__note">최근 업데이트 {formatTime(summary.updatedAt)}</div>
      <Sparkline color="#5df2ad" />
    </div>

    <nav className="portal-nav">
      {(['MONITORING', 'OPERATIONS'] as const).map((group) => (
        <React.Fragment key={group}>
          <div className="portal-nav__title">{navGroupLabel[group]}</div>
          {navItems
            .filter((item) => item.group === group)
            .map((item) => (
              <button
                className={`portal-nav__item ${activeView === item.id ? 'is-active' : ''}`}
                key={item.id}
                onClick={() => setActiveView(item.id)}
                type="button"
              >
                <span className="portal-nav__icon">{item.icon}</span>
                <span>{item.label}</span>
              </button>
            ))}
        </React.Fragment>
      ))}
    </nav>

    <div className="portal-sidebar__bottom">
      시스템 상태
      <div className="portal-sidebar__status">
        <span className="portal-sidebar__dot" />
        {summary.healthScore >= 90 ? '정상 상태' : '확인 필요'}
      </div>
      <div className="portal-sidebar__time">{clock} KST</div>
    </div>
  </aside>
);

const Topbar: React.FC<{
  activeView: NavView;
  alarmCount: number;
  isLive: boolean;
  loading: boolean;
  onNavigate: (view: NavView) => void;
  onRefresh: () => void;
  summary: ClusterSummary;
}> = ({ activeView, alarmCount, isLive, loading, onNavigate, onRefresh, summary }) => {
  const activeItem = navItems.find((item) => item.id === activeView);

  return (
    <header className="portal-topbar">
      <div>
        <div className="portal-crumb">AIOps for OCP / {activeItem?.label ?? '대시보드'}</div>
        <div className="portal-title">{activeItem?.label ?? '대시보드'}</div>
      </div>
      <div className="portal-topbar__controls">
        <select aria-label="클러스터 선택" className="portal-select">
          <option>{clusterLabel(summary)}</option>
        </select>
        <select aria-label="조회 시간 선택" className="portal-select">
          <option>현재 상태</option>
          <option>최근 게이트웨이 응답</option>
        </select>
        <span className={`portal-mode ${isLive ? 'is-live' : 'is-demo'}`}>
          {isLive ? '게이트웨이 연결됨' : '게이트웨이 연결 끊김'}
        </span>
        <button
          aria-label="새로고침"
          className="portal-icon-btn"
          disabled={loading}
          onClick={onRefresh}
          title="새로고침"
          type="button"
        >
          <RefreshCw />
        </button>
        <button
          aria-label={`AIOps 위험/주의 이벤트 ${alarmCount}건`}
          className="portal-icon-btn portal-alarm"
          onClick={() => onNavigate('alerts')}
          title={`AIOps 위험/주의 이벤트 ${alarmCount}건`}
          type="button"
        >
          <Bell />
          {alarmCount > 0 && <span className="portal-alarm__badge">{compactCount(alarmCount)}</span>}
        </button>
        <div className="portal-user">
          <span>OC</span>
          OpenShift
        </div>
      </div>
    </header>
  );
};

const Sparkline: React.FC<{ color: string }> = ({ color }) => (
  <svg aria-hidden="true" className="sparkline" viewBox="0 0 190 44">
    <path
      d="M0 32 L18 27 L30 29 L42 36 L54 22 L66 31 L78 18 L90 25 L104 13 L118 19 L132 12 L146 15 L160 8 L174 12 L190 4 L190 44 L0 44Z"
      fill={color}
      opacity=".16"
    />
    <path
      d="M0 32 L18 27 L30 29 L42 36 L54 22 L66 31 L78 18 L90 25 L104 13 L118 19 L132 12 L146 15 L160 8 L174 12 L190 4"
      fill="none"
      stroke={color}
      strokeLinecap="round"
      strokeWidth="2"
    />
  </svg>
);

const MiniTrend: React.FC<{ color: string }> = ({ color }) => (
  <svg aria-hidden="true" className="mini-trend" viewBox="0 0 160 32">
    <path
      d="M0 24 C25 22 30 25 50 20 C72 12 95 8 120 15 C140 20 150 12 160 16"
      fill="none"
      stroke={color}
      strokeLinecap="round"
      strokeWidth="2"
    />
  </svg>
);

const EmptyState: React.FC<{ label: string }> = ({ label }) => (
  <div className="empty-state">{label}</div>
);

const resourceNodeDetail = (
  resource: NonNullable<ClusterSummary['resources']>['items'][number] | undefined,
  fallback: string,
): string => (resource ? `${resource.score} · ${resource.issues > 0 ? `이슈 ${resource.issues}건` : '정상'}` : fallback);

const resourceNodeSeverity = (
  resource: NonNullable<ClusterSummary['resources']>['items'][number] | undefined,
  fallback: Severity = 'ok',
): Severity => resource?.severity ?? fallback;

const topologyNodeLabel: Record<TopologyNodeKey, string> = {
  daemonsets: '데몬셋',
  deployments: '디플로이먼트',
  nodes: '노드',
  persistentvolumeclaims: 'PVC',
  pods: '파드',
  replicasets: '레플리카셋',
  routes: '라우트',
  services: '서비스',
  statefulsets: '스테이트풀셋',
};

const topologyPrimarySignals = (summary: ClusterSummary): number =>
  resourceById(summary, 'pods')?.issues ?? 0;

const topologyDerivedSignals = (summary: ClusterSummary): number =>
  (resourceById(summary, 'deployments')?.issues ?? 0) + (resourceById(summary, 'replicasets')?.issues ?? 0);

const topologyOtherSignals = (summary: ClusterSummary): number =>
  Math.max(0, (summary.resources?.issues ?? 0) - topologyPrimarySignals(summary) - topologyDerivedSignals(summary));

const topologyNodeSummary = (
  summary: ClusterSummary,
  key: TopologyNodeKey,
): { detail: string; score: string; severity: Severity; title: string } => {
  if (key === 'nodes') {
    return {
      detail: summary.nodes.total === 1
        ? `정상 ${summary.nodes.ready}/${summary.nodes.total} · 단일 노드 런타임`
        : `정상 ${summary.nodes.ready}/${summary.nodes.total} · 비정상 ${summary.nodes.notReady}`,
      score: `${summary.nodes.ready}/${summary.nodes.total}`,
      severity: summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok',
      title: '노드',
    };
  }

  const resource = resourceById(summary, key);
  return {
    detail: resourceNodeDetail(resource, `${topologyNodeLabel[key]} 스냅샷 없음`),
    score: resource?.score ?? '-',
    severity: resourceNodeSeverity(resource),
    title: resource ? resourceNameLabel(resource.id, resource.name, resource.kind) : topologyNodeLabel[key],
  };
};

const topologyTracePath = (key: TopologyNodeKey): string => {
  const paths: Record<TopologyNodeKey, string> = {
    daemonsets: 'DaemonSet -> Pods',
    deployments: 'Deployment -> ReplicaSet -> Pods',
    nodes: 'Pods -> Nodes',
    persistentvolumeclaims: 'Pods -> PVC',
    pods: 'Route -> Service -> Pods',
    replicasets: 'Deployment -> ReplicaSet -> Pods',
    routes: 'Route -> Service',
    services: 'Route -> Service -> Pods',
    statefulsets: 'StatefulSet -> Pods',
  };
  return paths[key];
};

const buildTraceInspector = (summary: ClusterSummary, key: TopologyNodeKey): TraceInspectorModel => {
  const resource = resourceById(summary, key);
  const podSummary = buildPodRcaSummary(summary);
  const nodeSummary = topologyNodeSummary(summary, key);

  if (key === 'pods') {
    return {
      commands: [
        { title: '파드 인벤토리', command: 'oc get pods -A -o wide' },
        { title: '최근 파드 이벤트', command: 'oc get events -A --field-selector involvedObject.kind=Pod --sort-by=.lastTimestamp' },
        { title: '파드 상세', command: 'oc describe pod -n <namespace> <pod>' },
      ],
      focus: 'Pods · 런타임 수렴 지점',
      insight: '서비스 선택자와 컨트롤러 소유 관계가 Pod로 모입니다. 영향 후보는 활성 Pod 기준으로 계산합니다.',
      reasons: [
        { label: '서비스 선택 대상', detail: 'Service가 선택하는 실제 런타임 대상' },
        { label: '컨트롤러 소유 대상', detail: 'Deployment / ReplicaSet / StatefulSet / DaemonSet의 ownerRef 종착점' },
        { label: '런타임 의존성 대상', detail: 'Node와 PVC 상태가 직접 영향을 주는 대상' },
        { label: '헬스 신호 원천', detail: '대기 / 실패 / 미준비 / 재시작이 관측되는 지점' },
      ],
      severity: nodeSummary.severity,
      signals: [
        { label: '영향 후보', tone: nodeSummary.severity, value: String(podSummary.issueCandidates) },
        { label: '활성 Ready', value: String(podSummary.ready) },
        { label: '전체 Pod', value: String(podSummary.total) },
        { label: '실패', tone: podSummary.failed > 0 ? 'risk' : 'ok', value: String(podSummary.failed) },
        { label: '재시작', tone: podSummary.restartsTotal > 0 ? 'warn' : 'ok', value: String(podSummary.restartsTotal) },
        { label: '완료 제외', value: String(podSummary.completed) },
      ],
      title: '파드',
      trace: topologyTracePath(key),
    };
  }

  if (key === 'nodes') {
    return {
      commands: [
        { title: '노드 목록', command: 'oc get nodes -o wide' },
        { title: '노드 상태', command: 'oc describe node <node>' },
      ],
      focus: `Nodes · ${summary.nodes.total === 1 ? '단일 노드 런타임' : '스케줄링 기반'}`,
      insight: summary.nodes.total === 1
        ? '단일 노드에서는 Pod 장애가 노드 중복성 부족과 함께 해석됩니다.'
        : 'Pod가 스케줄링되는 기반입니다. 비정상 노드와 압박 신호를 먼저 배제합니다.',
      reasons: [
        { label: '스케줄링 대상', detail: 'Pod가 실제로 실행되는 노드 기반' },
        { label: '런타임 압박', detail: 'Disk / Memory / PID pressure가 Pod 준비 상태에 영향' },
        { label: '배제 근거', detail: 'Ready 상태와 pressure 신호가 정상이면 Pod 원인에서 분리' },
      ],
      severity: nodeSummary.severity,
      signals: [
        { label: 'Ready', tone: nodeSummary.severity, value: `${summary.nodes.ready}/${summary.nodes.total}` },
        { label: '비정상', tone: summary.nodes.notReady > 0 ? 'risk' : 'ok', value: String(summary.nodes.notReady) },
        { label: 'Pressure', tone: summary.nodes.pressureCount > 0 ? 'warn' : 'ok', value: String(summary.nodes.pressureCount) },
        { label: 'Metrics', value: summary.nodes.metricsAvailable ? '수집됨' : '미수집' },
      ],
      title: '노드',
      trace: topologyTracePath(key),
    };
  }

  if (key === 'persistentvolumeclaims') {
    return {
      commands: [
        { title: 'PVC 목록', command: 'oc get pvc -A' },
        { title: 'PVC 상세', command: 'oc describe pvc -n <namespace> <pvc>' },
      ],
      focus: 'PVC · 스토리지 의존성',
      insight: resource?.issues
        ? 'PVC 신호가 있어 Pod 마운트와 이벤트를 같이 확인해야 합니다.'
        : 'PVC는 현재 Bound 상태로 보이며, Pod 원인에서 우선 배제할 수 있습니다.',
      reasons: [
        { label: '볼륨 마운트 대상', detail: 'Pod 실행에 필요한 스토리지 연결 지점' },
        { label: '스토리지 배제', detail: 'Bound와 mount 이벤트 이상 여부로 영향 여부 판단' },
        { label: '집계 한계', detail: '현재 화면은 개별 Pod-PVC 매핑까지는 분리하지 않음' },
      ],
      severity: nodeSummary.severity,
      signals: [
        { label: 'Bound', tone: nodeSummary.severity, value: resource?.score ?? '-' },
        { label: '전체 PVC', value: String(resource?.total ?? '-') },
        { label: '이슈', tone: resource?.issues ? 'warn' : 'ok', value: String(resource?.issues ?? 0) },
      ],
      title: 'PVC',
      trace: topologyTracePath(key),
    };
  }

  const relationNote: Record<TopologyNodeKey, string> = {
    daemonsets: 'DaemonSet은 노드 단위 파드를 소유하며 파드 런타임 신호로 파생될 수 있습니다.',
    deployments: 'Deployment 가용성 변화는 ReplicaSet과 파드 준비 상태에서 파생될 수 있습니다.',
    nodes: '',
    persistentvolumeclaims: '',
    pods: '',
    replicasets: 'ReplicaSet은 Deployment와 Pod 사이의 소유 관계를 구성합니다.',
    routes: 'Route 리소스는 Service 대상을 외부/내부 트래픽 진입점으로 노출합니다.',
    services: 'Service는 셀렉터/엔드포인트 관계로 Pod 집합을 선택합니다.',
    statefulsets: 'StatefulSet은 안정적인 identity와 볼륨을 가진 파드를 소유합니다.',
  };

  const focusLabel: Record<TopologyNodeKey, string> = {
    daemonsets: 'DaemonSet · 노드 단위 소유자',
    deployments: 'Deployment · 워크로드 선언',
    nodes: '',
    persistentvolumeclaims: '',
    pods: '',
    replicasets: 'ReplicaSet · Pod 소유 체인',
    routes: 'Route · 트래픽 진입점',
    services: 'Service · 셀렉터 경계',
    statefulsets: 'StatefulSet · 안정 identity 소유자',
  };

  const commandByNode: Record<TopologyNodeKey, Array<{ command: string; title: string }>> = {
    daemonsets: [{ title: '데몬셋', command: 'oc get ds -A' }],
    deployments: [{ title: '디플로이먼트', command: 'oc get deploy -A' }],
    nodes: [],
    persistentvolumeclaims: [],
    pods: [],
    replicasets: [{ title: '레플리카셋', command: 'oc get rs -A' }],
    routes: [{ title: '라우트', command: 'oc get routes -A' }],
    services: [
      { title: '서비스', command: 'oc get svc -A' },
      { title: 'EndpointSlice', command: 'oc get endpointslice -A' },
    ],
    statefulsets: [{ title: '스테이트풀셋', command: 'oc get sts -A' }],
  };

  return {
    commands: commandByNode[key],
    focus: focusLabel[key],
    insight: relationNote[key] || '선택한 리소스의 상태와 관계를 기준으로 영향 경로를 확인합니다.',
    reasons: [
      { label: key === 'routes' ? '노출 경계' : key === 'services' ? '셀렉터 경계' : '소유 관계', detail: relationNote[key] || '리소스 관계 확인 대상' },
      { label: '현재 상태', detail: resource?.detail ? localizeTelemetryText(resource.detail) : '스냅샷 없음' },
      { label: resource?.issues ? '영향 신호' : '배제 근거', detail: resource?.issues ? `이슈 ${resource.issues}건이 감지됨` : '현재 활성 이슈 없음' },
    ],
    severity: nodeSummary.severity,
    signals: [
      { label: '상태', tone: nodeSummary.severity, value: nodeSummary.score },
      { label: '전체', value: String(resource?.total ?? '-') },
      { label: '이슈', tone: resource?.issues ? nodeSummary.severity : 'ok', value: String(resource?.issues ?? 0) },
    ],
    title: topologyNodeLabel[key],
    trace: topologyTracePath(key),
  };
};

type ResourceSummaryItem = NonNullable<ClusterSummary['resources']>['items'][number];

type ImpactSignalRow = {
  actionLabel?: string;
  chips: string[];
  description: string;
  detail: string;
  id: string;
  metric: string;
  node: TopologyNodeKey;
  severity: Severity;
  title: string;
};

type ImpactSignalSection = {
  id: 'primary' | 'derived' | 'cleared';
  label: string;
  rows: ImpactSignalRow[];
};

const resourceReadyText = (resource: ResourceSummaryItem | undefined): string =>
  resource ? String(resource.ready) : '-';

const buildDerivedImpactRow = (resource: ResourceSummaryItem): ImpactSignalRow => {
  const isReplicaSet = /replicaset/i.test(resource.id);
  const node: TopologyNodeKey = isReplicaSet
    ? 'replicasets'
    : /statefulset/i.test(resource.id)
      ? 'statefulsets'
      : /daemonset/i.test(resource.id)
        ? 'daemonsets'
        : 'deployments';
  const driftLabel = isReplicaSet ? '준비 차이' : '가용 차이';
  const sourceLabel = isReplicaSet ? 'ownerRef 체인에서 파생' : 'Pod 준비 상태 신호에서 파생';

  return {
    actionLabel: '관련 경로 보기',
    chips: [
      `${driftLabel} ${resource.issues}`,
      `목표 ${resource.total}`,
      `${isReplicaSet ? '준비' : '가용'} ${resourceReadyText(resource)}`,
      isReplicaSet ? '소유관계' : '파생',
    ],
    description: sourceLabel,
    detail: localizeTelemetryText(resource.detail),
    id: resource.id,
    metric: `${driftLabel} ${resource.issues}건`,
    node,
    severity: resource.severity,
    title: resourceNameLabel(resource.id, resource.name, resource.kind),
  };
};

const buildImpactSignalStack = (summary: ClusterSummary): ImpactSignalSection[] => {
  const podResource = resourceById(summary, 'pods');
  const podSummary = buildPodRcaSummary(summary);
  const pvcResource = resourceById(summary, 'persistentvolumeclaims');
  const derivedRows = (summary.resources?.items ?? [])
    .filter((resource) => ['deployments', 'replicasets', 'statefulsets', 'daemonsets'].includes(resource.id) && resource.issues > 0)
    .map(buildDerivedImpactRow);

  const sections: ImpactSignalSection[] = [
    {
      id: 'primary',
      label: '주 신호',
      rows: [
        {
          actionLabel: 'RCA 열기',
          chips: [
            `대기 ${podSummary.pending}`,
            `실패 ${podSummary.failed}`,
            `미준비 ${podSummary.runningNotReady}`,
            `재시작 ${podSummary.restartsTotal}`,
          ],
          description: '서비스 선택자와 컨트롤러 ownerRef가 수렴하는 런타임 지점',
          detail: '경로: Route -> Service -> Pods <- ReplicaSet / StatefulSet / DaemonSet',
          id: 'primary-pods',
          metric: `영향 후보 ${podSummary.issueCandidates}건`,
          node: 'pods',
          severity: podResource?.severity ?? (podSummary.issueCandidates > 0 ? 'risk' : 'ok'),
          title: '파드',
        },
      ],
    },
    {
      id: 'derived',
      label: '파생 영향',
      rows: derivedRows,
    },
    {
      id: 'cleared',
      label: '배제된 의존성',
      rows: [
        {
          chips: [
            `Ready ${summary.nodes.ready}/${summary.nodes.total}`,
            `압박 ${summary.nodes.pressureCount}`,
            summary.nodes.metricsAvailable ? '메트릭 수집' : '메트릭 미수집',
          ],
          description: summary.nodes.pressureCount > 0 ? '노드 압박 신호 확인 필요' : '노드 압박 신호 없음',
          detail: summary.nodes.total === 1 ? '단일 노드 런타임 · 영향 해석 시 중복성 제한 고려' : '스케줄링 기반 확인 완료',
          id: 'cleared-nodes',
          metric: `Ready ${summary.nodes.ready}/${summary.nodes.total}`,
          node: 'nodes',
          severity: summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok',
          title: '노드',
        },
        {
          chips: [
            `Bound ${pvcResource?.score ?? '-'}`,
            `PVC ${pvcResource?.total ?? '-'}`,
            pvcResource?.issues ? `이슈 ${pvcResource.issues}` : '스토리지 신호 없음',
          ],
          description: pvcResource?.issues ? 'PVC 마운트/스토리지 신호 확인 필요' : '마운트/스토리지 신호 없음',
          detail: pvcResource?.detail ? localizeTelemetryText(pvcResource.detail) : 'PVC 스냅샷 없음',
          id: 'cleared-pvc',
          metric: pvcResource?.score ? `Bound ${pvcResource.score}` : 'Bound -',
          node: 'persistentvolumeclaims',
          severity: pvcResource?.severity ?? 'ok',
          title: 'PVC',
        },
      ],
    },
  ];

  return sections.filter((section) => section.id !== 'derived' || section.rows.length > 0);
};

const ClusterTopologyMap: React.FC<{
  affectedOnly?: boolean;
  edgeMode?: TopologyEdgeMode;
  onSelectNode?: (node: TopologyNodeKey) => void;
  selectedNode?: TopologyNodeKey;
  showEdgeLabels?: boolean;
  summary: ClusterSummary;
  variant?: 'service' | 'runtime';
}> = ({
  affectedOnly = false,
  edgeMode = 'all',
  onSelectNode,
  selectedNode,
  showEdgeLabels = true,
  summary,
  variant = 'service',
}) => {
  const nodeState: Severity = summary.nodes.notReady > 0 ? 'risk' : summary.nodes.pressureCount > 0 ? 'warn' : 'ok';
  const resources = summary.resources?.items ?? [];
  const routes = resources.find((resource) => resource.id === 'routes');
  const services = resources.find((resource) => resource.id === 'services');
  const deployments = resources.find((resource) => resource.id === 'deployments');
  const statefulSets = resources.find((resource) => resource.id === 'statefulsets');
  const daemonSets = resources.find((resource) => resource.id === 'daemonsets');
  const replicaSets = resources.find((resource) => resource.id === 'replicasets');
  const pods = resources.find((resource) => resource.id === 'pods');
  const pvcs = resources.find((resource) => resource.id === 'persistentvolumeclaims');
  const issueCount = summary.resources?.issues ?? 0;
  const podSummary = buildPodRcaSummary(summary);
  const isRuntimeTrace = variant === 'runtime';
  const nodeInteraction = (node: TopologyNodeKey) => {
    const nodeSummary = topologyNodeSummary(summary, node);
    return {
      dimmed: affectedOnly && nodeSummary.severity === 'ok',
      nodeId: node,
      onSelectNode,
      selected: selectedNode === node,
    };
  };

  const mapClassName = [
    'impact-map',
    isRuntimeTrace ? 'is-runtime-trace' : '',
    affectedOnly ? 'is-affected-only' : '',
    `is-edge-${edgeMode}`,
    showEdgeLabels ? 'has-edge-labels' : 'has-hidden-edge-labels',
  ].filter(Boolean).join(' ');

  return (
    <div className={mapClassName} role="img" aria-label={isRuntimeTrace ? '워크로드 런타임 추적' : '클러스터 리소스 관계도'}>
      <div className="impact-map__grid" aria-hidden="true" />
      <div className="impact-map__top">
        <div>
          <span>{isRuntimeTrace ? '워크로드 런타임 추적' : '서비스 영향 경로'}</span>
          <strong>{clusterLabel(summary)}</strong>
        </div>
        <div className="impact-map__snapshot">
          <span>스냅샷</span>
          <strong>{formatTime(summary.updatedAt)}</strong>
        </div>
      </div>

      <div className="impact-map__canvas">
        <svg aria-hidden="true" className="impact-map__links" preserveAspectRatio="none" viewBox="0 0 100 100">
          <defs>
            <marker id="impact-arrow" markerHeight="5" markerUnits="strokeWidth" markerWidth="5" orient="auto" refX="4.4" refY="2.5">
              <path d="M0,0 L5,2.5 L0,5 Z" fill="#7aa7d9" />
            </marker>
            <marker id="impact-arrow-warn" markerHeight="5" markerUnits="strokeWidth" markerWidth="5" orient="auto" refX="4.4" refY="2.5">
              <path d="M0,0 L5,2.5 L0,5 Z" fill="#f59e0b" />
            </marker>
          </defs>
          <path className="impact-link is-traffic" d="M14 27 C14 34 14 42 14 49" markerEnd="url(#impact-arrow)" />
          <path className="impact-link is-selector" d="M23 56 C37 56 55 53 72 53" markerEnd="url(#impact-arrow)" />
          <path className="impact-link is-owner" d="M50 20 C52 20 53 20 55 20" markerEnd="url(#impact-arrow)" />
          <path className="impact-link is-warn" d="M71 22 C76 28 77 40 72 48" markerEnd="url(#impact-arrow-warn)" />
          <path className="impact-link is-owner is-warn" d="M50 50 C57 50 64 51 72 53" markerEnd="url(#impact-arrow-warn)" />
          <path className="impact-link is-owner is-warn" d="M50 78 C59 75 66 64 72 57" markerEnd="url(#impact-arrow-warn)" />
          <path className="impact-link is-runtime" d="M70 76 C73 70 78 65 81 62" markerEnd="url(#impact-arrow)" />
          <path className="impact-link is-runtime" d="M88 76 C88 70 85 65 83 62" markerEnd="url(#impact-arrow)" />
        </svg>

        <div className="impact-map__zone impact-map__zone--entry">트래픽 진입</div>
        <div className="impact-map__zone impact-map__zone--workload">워크로드 컨트롤러</div>
        <div className="impact-map__zone impact-map__zone--runtime">파드 런타임</div>
        <div className="impact-map__zone impact-map__zone--substrate">런타임 기반</div>
        <span className="impact-edge-label impact-edge-label--exposes">노출</span>
        <span className="impact-edge-label impact-edge-label--selector">선택</span>
        <span className="impact-edge-label impact-edge-label--owner">소유</span>
        <span className="impact-edge-label impact-edge-label--scheduled">스케줄</span>
        <span className="impact-edge-label impact-edge-label--mounts">마운트</span>

        <ImpactNode
          className="impact-node--routes"
          detail={resourceNodeDetail(routes, '라우트 스냅샷 없음')}
          icon={<Network />}
          label={routes ? resourceNameLabel(routes.id, routes.name, routes.kind) : '라우트'}
          severity={resourceNodeSeverity(routes)}
          {...nodeInteraction('routes')}
        />
        <ImpactNode
          className="impact-node--services"
          detail={resourceNodeDetail(services, '서비스 스냅샷 없음')}
          icon={<Network />}
          label={services ? resourceNameLabel(services.id, services.name, services.kind) : '서비스'}
          severity={resourceNodeSeverity(services)}
          {...nodeInteraction('services')}
        />
        <ImpactNode
          className="impact-node--deployments"
          detail={resourceNodeDetail(deployments, '디플로이먼트 스냅샷 없음')}
          icon={<Cpu />}
          label={deployments ? resourceNameLabel(deployments.id, deployments.name, deployments.kind) : '디플로이먼트'}
          severity={resourceNodeSeverity(deployments)}
          {...nodeInteraction('deployments')}
        />
        <ImpactNode
          className="impact-node--statefulsets"
          detail={resourceNodeDetail(statefulSets, '스테이트풀셋 스냅샷 없음')}
          icon={<Cpu />}
          label={statefulSets ? resourceNameLabel(statefulSets.id, statefulSets.name, statefulSets.kind) : '스테이트풀셋'}
          severity={resourceNodeSeverity(statefulSets)}
          {...nodeInteraction('statefulsets')}
        />
        <ImpactNode
          className="impact-node--daemonsets"
          detail={resourceNodeDetail(daemonSets, '데몬셋 스냅샷 없음')}
          icon={<Cpu />}
          label={daemonSets ? resourceNameLabel(daemonSets.id, daemonSets.name, daemonSets.kind) : '데몬셋'}
          severity={resourceNodeSeverity(daemonSets)}
          {...nodeInteraction('daemonsets')}
        />
        <ImpactNode
          className="impact-node--replicasets"
          detail={resourceNodeDetail(replicaSets, '레플리카셋 스냅샷 없음')}
          icon={<Cpu />}
          label={replicaSets ? resourceNameLabel(replicaSets.id, replicaSets.name, replicaSets.kind) : '레플리카셋'}
          severity={resourceNodeSeverity(replicaSets)}
          {...nodeInteraction('replicasets')}
        />
        <ImpactNode
          className="impact-node--pods"
          detail={resourceNodeDetail(pods, '파드 스냅샷 없음')}
          icon={<Cpu />}
          label={pods ? resourceNameLabel(pods.id, pods.name, pods.kind) : '파드'}
          severity={resourceNodeSeverity(pods)}
          {...nodeInteraction('pods')}
        />
        <ImpactNode
          className="impact-node--nodes"
          detail={topologyNodeSummary(summary, 'nodes').detail}
          icon={<ShieldCheck />}
          label="노드"
          severity={nodeState}
          {...nodeInteraction('nodes')}
        />
        <ImpactNode
          className="impact-node--pvcs"
          detail={resourceNodeDetail(pvcs, 'PVC 스냅샷 없음')}
          icon={<GitBranch />}
          label={pvcs ? resourceNameLabel(pvcs.id, pvcs.name, pvcs.kind) : 'PVC'}
          severity={resourceNodeSeverity(pvcs)}
          {...nodeInteraction('persistentvolumeclaims')}
        />

        <div className="impact-map__legend">
          {isRuntimeTrace ? (
            <>
              <span><i className="is-warn" /> 이상 신호</span>
              <span><i className="is-owner" /> 소유 관계</span>
              <span><i className="is-selector" /> 서비스 셀렉터</span>
              <span><i className="is-runtime" /> 런타임 의존성</span>
              <strong>
                라우트가 서비스를 노출 · 서비스가 파드를 선택 · 컨트롤러가 파드를 소유 · 노드/PVC가 런타임을 지원 · 활성 파드 이슈 후보 {podSummary.issueCandidates}건
              </strong>
            </>
          ) : (
            <>
              <span><i className="is-ok" /> 정상</span>
              <span><i className="is-warn" /> 이상 신호</span>
              <span><i className="is-selector" /> 노출/선택</span>
              <span><i className="is-owner" /> 소유 관계</span>
              <span><i className="is-runtime" /> 스케줄/마운트</span>
              <strong>
                라우트가 서비스를 노출 · 서비스가 파드를 선택 · 컨트롤러가 파드를 소유 · 노드/PVC가 런타임을 지원 · 영향 후보 {issueCount}건
              </strong>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

const ImpactNode: React.FC<{
  className: string;
  detail: string;
  dimmed?: boolean;
  icon: React.ReactNode;
  label: string;
  nodeId?: TopologyNodeKey;
  onSelectNode?: (node: TopologyNodeKey) => void;
  selected?: boolean;
  severity: Severity;
}> = ({ className, detail, dimmed = false, icon, label, nodeId, onSelectNode, selected = false, severity }) => {
  const interactive = Boolean(nodeId && onSelectNode);
  const handleSelect = () => {
    if (nodeId && onSelectNode) {
      onSelectNode(nodeId);
    }
  };

  return (
    <article
      aria-pressed={interactive ? selected : undefined}
      className={`impact-node ${className} ${severityClass(severity)} ${selected ? 'is-selected' : ''} ${dimmed ? 'is-dimmed' : ''}`}
      onClick={interactive ? handleSelect : undefined}
      onKeyDown={
        interactive
          ? (event) => {
              if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                handleSelect();
              }
            }
          : undefined
      }
      role={interactive ? 'button' : undefined}
      tabIndex={interactive ? 0 : undefined}
    >
      <span className="impact-node__icon">{icon}</span>
      <div>
        <strong>{label}</strong>
        <small>{detail}</small>
      </div>
      <span aria-label={severityLabel[severity]} className="impact-node__status-dot" />
    </article>
  );
};

const issueSeverityLabel: Record<QueueItem['severity'], string> = {
  risk: '위험',
  warn: '주의',
};

const issueNextSteps = (item: QueueItem): string[] => {
  if (item.category === '클러스터 버전') {
    return [
      'ClusterVersion의 Upgradeable=False reason/message를 확인합니다.',
      '추천 업데이트와 조건부 업데이트를 구분해 적용 가능 범위를 확인합니다.',
      'AdminAck 또는 mirror signature 준비가 필요하면 업데이트 전 사전 작업으로 분리합니다.',
    ];
  }

  if (item.category === '리소스') {
    return [
      '클러스터 리소스 테이블에서 같은 리소스 유형의 상세 상태를 확인합니다.',
      '실패/대기/사용 불가 항목이 어떤 네임스페이스에 있는지 추가 조회합니다.',
      '조치가 필요하면 RCA 센터에서 증거와 실행 계획을 분리합니다.',
    ];
  }

  if (item.category === '오퍼레이터') {
    return [
      'ClusterOperator 조건의 reason/message를 우선 확인합니다.',
      '관련 네임스페이스의 파드 및 이벤트를 함께 조회합니다.',
      '진행 중인 업데이트나 재시도 상태인지 RCA 센터에서 교차 확인합니다.',
    ];
  }

  return [
    '게이트웨이가 수집한 증거와 현재 상태를 먼저 대조합니다.',
    '관련 리소스의 최근 이벤트와 상태 변화를 확인합니다.',
    '변경 작업은 승인/실행 기록 화면에서 별도로 추적합니다.',
  ];
};

const incidentLevelLabel: Record<QueueItem['severity'], string> = {
  risk: '심각 신호',
  warn: '주의 신호',
};

const evidencePrefixes = [
  'recommended updates',
  'conditional updates',
  'current',
  'reason',
  'available',
  'degraded',
  'progressing',
  'created',
  'target',
  'kubelet',
  'cpu',
  'memory',
  'kind',
  'total',
  'ready',
  'issues',
  'os',
];

const evidenceLabel = (label: string): string => {
  const labels: Record<string, string> = {
    available: '정상 여부',
    conditional: '조건부 업데이트',
    'conditional updates': '조건부 업데이트',
    cpu: 'CPU',
    created: '생성 시각',
    current: '현재 버전',
    degraded: '저하',
    kind: '종류',
    kubelet: 'Kubelet',
    memory: '메모리',
    os: 'OS',
    progressing: '진행 중',
    ready: '정상',
    reason: '사유',
    'recommended updates': '추천 업데이트',
    target: '대상',
    total: '전체',
    issues: '이슈',
  };
  return labels[label] ?? label;
};

const evidenceStatusLabel = (status: 'attention' | 'collected' | 'excluded' | 'normal'): string => {
  const labels: Record<typeof status, string> = {
    attention: '확인 필요',
    collected: '수집됨',
    excluded: '제외',
    normal: '정상',
  };
  return labels[status];
};

const splitEvidenceLine = (line: string): { label: string; value: string } => {
  const normalized = line.trim();
  const lower = normalized.toLowerCase();
  const prefix = evidencePrefixes.find((candidate) => lower.startsWith(`${candidate} `));

  if (prefix) {
    return {
      label: prefix,
      value: normalized.slice(prefix.length).trim(),
    };
  }

  const [label, ...value] = normalized.split(/\s+/);
  return {
    label: label || 'signal',
    value: value.join(' ') || '-',
  };
};

const evidenceStatus = (label: string, value: string): 'attention' | 'collected' | 'normal' => {
  const combined = `${label} ${value}`.toLowerCase();
  if (/(issue|failed|pending|degraded|notready|unavailable|blocked|adminack|required|pressure)/.test(combined)) {
    return 'attention';
  }
  if (/(ready|available|current|collected|true|normal|succeeded)/.test(combined)) {
    return 'normal';
  }
  return 'collected';
};

const evidenceRows = (item: QueueItem): Array<{ label: string; status: 'attention' | 'collected' | 'normal'; value: string }> =>
  item.evidence.map((line) => {
    const parsed = splitEvidenceLine(line);
    return {
      ...parsed,
      status: evidenceStatus(parsed.label, parsed.value),
    };
  });

const issueMetrics = (item: QueueItem): string[] =>
  item.detail
    .split(' · ')
    .map((metric) => metric.trim())
    .filter(Boolean)
    .slice(0, 6);

const affectedScope = (item: QueueItem): string => {
  const issueEvidence = evidenceRows(item).find((row) => row.label === 'issues');
  if (issueEvidence?.value && issueEvidence.value !== '0') {
    return `이슈 후보 ${issueEvidence.value}건`;
  }

  const failedMetric = issueMetrics(item).find((metric) => /failed|pending|notready|unavailable|issues/i.test(metric));
  return failedMetric ?? issueSeverityLabel[item.severity];
};

const impactRows = (item: QueueItem): Array<{ label: string; value: string }> => [
  { label: '리소스', value: item.target ?? item.title },
  { label: '분류', value: item.category ?? '운영 이슈' },
  { label: '데이터 소스', value: item.source ?? '게이트웨이 요약' },
  { label: '스냅샷', value: item.updatedAt ?? '-' },
  { label: '영향 범위', value: affectedScope(item) },
];

const commandResourceLabel = (item: QueueItem): string => {
  if (item.target) {
    return `${item.target} 보기`;
  }
  if (item.category === '리소스') {
    return '리소스 보기';
  }
  return '관련 리소스 보기';
};

const DetailDrawer: React.FC<{
  clusterName: string;
  item: QueueItem | null;
  onAssistantLaunch?: AssistantLaunchHandler;
  onClose: () => void;
  onNavigate: (view: NavView) => void;
}> = ({ clusterName, item, onAssistantLaunch, onClose, onNavigate }) => {
  const runCommand = (view: NavView) => {
    onClose();
    onNavigate(view);
  };
  const metrics = item ? issueMetrics(item) : [];
  const impacts = item ? impactRows(item) : [];
  const evidence = item ? evidenceRows(item) : [];
  const runbook = item ? issueNextSteps(item) : [];

  return (
    <div className={`portal-drawer ${item ? 'is-open' : ''}`} onClick={onClose}>
      <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
        <div className="portal-drawer__head">
          <div>
            <span>이슈 대응 레일</span>
            <strong>{item ? item.title : '이슈 상세'}</strong>
          </div>
          <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
            <X />
          </button>
        </div>
        <div className="portal-drawer__body">
          {item ? (
            <>
              <section className={`incident-header ${severityClass(item.severity)}`}>
                <div className="incident-header__edge" aria-hidden="true" />
                <div className="incident-header__signal">
                  <span>{incidentLevelLabel[item.severity]}</span>
                  <h2>{item.title}</h2>
                  <p>
                    {clusterName} / {item.category ?? '운영 이슈'} / {item.target ?? item.title}
                  </p>
                </div>
                <div className="incident-header__telemetry">
                  <span>감지 시각</span>
                  <strong>{item.updatedAt ?? '-'}</strong>
                  <span>데이터 소스</span>
                  <strong>{item.source ?? '게이트웨이 요약'}</strong>
                  <span>신뢰도</span>
                  <strong>{item.updatedAt ? '실시간 소스' : '스냅샷'}</strong>
                </div>
                <div className="incident-metrics">
                  {metrics.map((metric) => (
                    <span key={metric}>{metric}</span>
                  ))}
                </div>
              </section>

              <section className="incident-block">
                <div className="incident-block__title">
                  <Network />
                  영향 범위
                </div>
                <div className="impact-rows">
                  {impacts.map((row) => (
                    <div className="impact-row" key={row.label}>
                      <span>{row.label}</span>
                      <strong>{row.value}</strong>
                    </div>
                  ))}
                </div>
              </section>

              <section className="incident-block">
                <div className="incident-block__title">
                  <FileText />
                  증거 스트림
                </div>
                <div className="evidence-stream">
                  <div className="evidence-stream__head">
                    <span>신호</span>
                    <span>값</span>
                    <span>상태</span>
                  </div>
                  {evidence.map((row) => (
                    <div className="evidence-row" key={`${row.label}-${row.value}`}>
                      <span>{evidenceLabel(row.label)}</span>
                      <strong>{row.value}</strong>
                      <em className={`is-${row.status}`}>{evidenceStatusLabel(row.status)}</em>
                    </div>
                  ))}
                </div>
              </section>

              <section className="incident-block">
                <div className="incident-block__title">
                  <ClipboardCheck />
                  런북 체크포인트
                </div>
                <ol className="runbook-list">
                  {runbook.map((step, index) => (
                    <li key={step}>
                      <span>{String(index + 1).padStart(2, '0')}</span>
                      <p>{step}</p>
                      <em>{index === 2 ? '자동화 가능' : '미확인'}</em>
                    </li>
                  ))}
                </ol>
              </section>
            </>
          ) : (
            <EmptyState label="선택된 이슈가 없습니다." />
          )}
        </div>
        {item && (
          <div className="incident-command-bar">
            <div>
              <span>다음 명령</span>
              <strong>권장: RCA 추적</strong>
            </div>
            <button className="incident-command-bar__primary" onClick={() => runCommand('rca')} type="button">
              RCA 추적 열기
            </button>
            {onAssistantLaunch && (
              <button
                onClick={() => onAssistantLaunch({ context: queueAssistantContext(item, 'issue-detail') })}
                type="button"
              >
                Assistant RCA
              </button>
            )}
	            <button onClick={() => runCommand('endpoints')} type="button">
	              {commandResourceLabel(item)}
            </button>
            <button onClick={onClose} type="button">
              닫기
            </button>
          </div>
        )}
      </aside>
    </div>
  );
};

const Panel: React.FC<{
  action?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
  title: string;
}> = ({ action, children, className = '', title }) => (
  <section className={`portal-panel ${className}`}>
    <div className="portal-panel__head">
      <div className="portal-panel__title">{title}</div>
      {action}
    </div>
    <div className="portal-panel__body">{children}</div>
  </section>
);

const DashboardView: React.FC<{
  clock: string;
  events: AiopsEventFeed;
  onAssistantLaunch?: AssistantLaunchHandler;
  onNavigate: (view: NavView) => void;
  onOpenItem: (item: QueueItem) => void;
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
}> = ({ clock, events, onAssistantLaunch, onNavigate, onOpenItem, status, summary }) => {
  const [queueFilter, setQueueFilter] = React.useState<'all' | 'risk' | 'warn'>('all');
  const [scopeQuery, setScopeQuery] = React.useState('');
  const [activeScope, setActiveScope] = React.useState('cluster');
  const scopeListRef = React.useRef<HTMLDivElement>(null);
  const scopes = buildScopes(summary, status);
  const queues = buildQueues(summary, status);
  const alerts = buildAlerts(summary, status);
  const endpoints = buildEndpoints(summary);
  const activities = buildActivities(summary, status, events);
  const actionCount = actionRecords(status).length;
  const auditCount = status.spec.records.auditRecords?.length ?? 0;
  const riskCount = queues.filter((item) => item.severity === 'risk').length;
  const warnCount = queues.filter((item) => item.severity === 'warn').length;
  const filteredScopes = scopes.filter((scope) =>
    `${scope.name} ${scope.detail} ${scope.keywords?.join(' ') ?? ''}`
      .toLowerCase()
      .includes(scopeQuery.toLowerCase()),
  );
  const visibleQueues =
    queueFilter === 'all' ? queues : queues.filter((item) => item.severity === queueFilter);
  const queueTabs: Array<{ id: 'all' | 'risk' | 'warn'; label: string; value: number }> = [
    { id: 'all', label: '전체', value: queues.length },
    { id: 'risk', label: '위험', value: riskCount },
    { id: 'warn', label: '주의', value: warnCount },
  ];

  React.useEffect(() => {
    const activeItem = scopeListRef.current?.querySelector<HTMLElement>('[data-scope-active="true"]');
    activeItem?.scrollIntoView({ block: 'nearest' });
  }, [activeScope]);

  return (
    <div className="dashboard-view">
      <section className="hero-grid">
        <div className="hero-card">
          <span className="hero-pill">{summary.healthScore >= 90 ? '시스템 정상' : '확인 필요'}</span>
          <h2>운영 대시보드</h2>
          <div className="hero-card__metrics">
            <div>
              <span>시스템 정상률</span>
              <strong>{summary.healthScore}%</strong>
            </div>
            <div>
              <span>최근 업데이트</span>
              <b>{formatTime(summary.updatedAt) || clock}</b>
            </div>
            <div>
              <span>OpenShift</span>
              <b>{displayOpenShiftVersion(summary.version.version)}</b>
            </div>
          </div>
          <svg aria-hidden="true" className="hero-line" viewBox="0 0 420 40">
            <path
              d="M0 28 C30 22 40 27 65 21 C94 14 100 25 125 18 C150 10 168 16 190 12 C220 8 232 12 254 9 C292 4 310 13 340 8 C374 3 390 10 420 4"
              fill="none"
              stroke="#16d5c0"
              strokeLinecap="round"
              strokeWidth="3"
            />
          </svg>
        </div>
        <KpiCard color={riskCount > 0 ? 'red' : 'green'} label="즉시 확인" sub={`위험 ${riskCount} · 주의 ${warnCount}`} value={queues.length} />
        <KpiCard color={summary.nodes.notReady > 0 ? 'red' : 'green'} label="비정상 노드" sub={`정상 ${summary.nodes.ready}/${summary.nodes.total}`} value={summary.nodes.notReady} />
        <KpiCard color={summary.operators.issues.length > 0 ? 'red' : 'green'} label="오퍼레이터 이슈" sub={`정상 ${summary.operators.available}/${summary.operators.total}`} value={summary.operators.issues.length} />
        <KpiCard color={actionCount > 0 ? 'blue' : 'green'} label="AIOps 기록" sub={`감사 ${auditCount} · 조치 ${actionCount}`} value={auditCount + actionCount} />
      </section>

      <section className="portal-grid portal-grid--resource-map">
        <Panel
          title="리소스"
          action={
            <label className="portal-search">
              <Search />
              <input
                onChange={(event) => setScopeQuery(event.target.value)}
                placeholder="파드, 디플로이먼트, 노드 검색"
                value={scopeQuery}
              />
            </label>
          }
        >
          <div className="scope-list" ref={scopeListRef}>
            {filteredScopes.map((scope) => (
              <div
                className={`scope-item ${activeScope === scope.id ? 'is-active' : ''}`}
                data-scope-active={activeScope === scope.id ? 'true' : undefined}
                key={scope.id}
              >
                <button
                  aria-controls={`scope-detail-${scope.id}`}
                  aria-expanded={activeScope === scope.id}
                  className={`scope-row ${activeScope === scope.id ? 'is-active is-expanded' : ''}`}
                  onClick={() => setActiveScope(scope.id)}
                  type="button"
                >
                  <ChevronRight />
                  <span>
                    <strong>{scope.name}</strong>
                    <small>{scope.detail}</small>
                  </span>
                  <b>{scope.score}</b>
                </button>
                {activeScope === scope.id && (
                  <div className="scope-detail" id={`scope-detail-${scope.id}`}>
                    {scopeDetailRows(scope, summary, status).map((row) => (
                      <span key={`${scope.id}-${row.label}`}>
                        {row.label}
                        <strong>{row.value}</strong>
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {filteredScopes.length === 0 && <EmptyState label="일치하는 리소스가 없습니다." />}
          </div>
        </Panel>

        <Panel
          className="portal-panel--map"
          title="서비스 영향 지도"
          action={
            <button className="portal-button" onClick={() => onNavigate('service-map')} type="button">
              지도 확대
            </button>
          }
        >
          <ClusterTopologyMap summary={summary} />
        </Panel>
      </section>

      <section className="portal-grid portal-grid--issue-band">
        <Panel
          title="이슈 큐"
          action={
            <div className="portal-tabs">
              {queueTabs.map((tab) => (
                <button
                  className={queueFilter === tab.id ? 'is-active' : ''}
                  key={tab.id}
                  onClick={() => setQueueFilter(tab.id)}
                  type="button"
                >
                  {tab.label} {tab.value}
                </button>
              ))}
            </div>
          }
        >
          <QueueList items={visibleQueues} onAssistantLaunch={onAssistantLaunch} onOpenItem={onOpenItem} />
        </Panel>

        <Panel
          title="알림"
          action={
            <button className="portal-button" onClick={() => onNavigate('alerts')} type="button">
              전체 알림
            </button>
          }
        >
          <AlertList alerts={alerts} />
        </Panel>

        <IssueSummary queues={queues} summary={summary} />
      </section>

      <EndpointTable endpoints={endpoints} onAssistantLaunch={onAssistantLaunch} />

      <section className="portal-grid portal-grid--activity">
        <ActivityTimeline activities={activities} />
      </section>
    </div>
  );
};

const KpiCard: React.FC<{ color: 'red' | 'green' | 'blue'; label: string; sub: string; value: string | number }> = ({
  color,
  label,
  sub,
  value,
}) => (
  <div className={`kpi-card is-${color}`}>
    <span>{label}</span>
    <strong>{value}</strong>
    <small>{sub}</small>
    <MiniTrend color={color === 'red' ? '#ef4444' : color === 'green' ? '#10b981' : '#2563eb'} />
  </div>
);

const queueMetaItems = (item: QueueItem): string[] =>
  [
    item.category ?? '운영 이슈',
    item.target ? `대상 ${item.target}` : '',
    item.updatedAt ? `업데이트 ${item.updatedAt}` : '',
  ].filter(Boolean);

const QueueList: React.FC<{
  items: QueueItem[];
  onAssistantLaunch?: AssistantLaunchHandler;
  onOpenItem: (item: QueueItem) => void;
}> = ({
  items,
  onAssistantLaunch,
  onOpenItem,
}) => {
  if (items.length === 0) {
    return <EmptyState label="현재 게이트웨이 요약 기준 위험/주의 항목이 없습니다." />;
  }

  return (
    <div className="queue-list">
      {items.map((item) => (
        <div className={`queue-row ${severityClass(item.severity)}`} key={item.id}>
          <StatusBadge severity={item.severity} />
          <div className="queue-row__content">
            <strong>{item.title}</strong>
            <span>{item.detail}</span>
            <div className="queue-row__meta">
              {queueMetaItems(item).map((meta) => (
                <small key={meta}>{meta}</small>
              ))}
            </div>
          </div>
          <div className="queue-row__actions">
            {onAssistantLaunch && (
              <button
                className="portal-button is-primary"
                onClick={() => onAssistantLaunch({ context: queueAssistantContext(item, 'dashboard-queue') })}
                type="button"
              >
                RCA
              </button>
            )}
            <button className="portal-button" onClick={() => onOpenItem(item)} type="button">
              상세
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};

const AlertList: React.FC<{ alerts: AlertItem[] }> = ({ alerts }) => {
  if (alerts.length === 0) {
    return <EmptyState label="현재 게이트웨이 요약 기준 알림이 없습니다." />;
  }

  return (
    <div className="alert-list">
      {alerts.map((alert) => (
        <article className="alert-row" key={alert.id}>
          <span className={`alert-row__icon ${severityClass(alert.severity)}`}>
            <AlertTriangle />
          </span>
          <div>
            <strong>{alert.title}</strong>
            <span>{alert.target}</span>
          </div>
          <time>{alert.time}</time>
        </article>
      ))}
    </div>
  );
};

const IssueSummary: React.FC<{ queues: QueueItem[]; summary: ClusterSummary }> = ({ queues, summary }) => (
  <Panel
    title="이슈 요약"
    action={<StatusBadge label={`이슈 ${queues.length}`} severity={queues.length > 0 ? 'warn' : 'ok'} />}
  >
    {queues.length === 0 ? (
      <EmptyState label="현재 게이트웨이 요약 기준 RCA 후보가 없습니다." />
    ) : (
      <>
        <div className="rca-summary">게이트웨이가 수집한 OpenShift 상태에서 확인 필요한 항목입니다.</div>
        <div className="rca-grid">
          <div>
            <b>주요 신호</b>
            {queues.slice(0, 3).map((queue, index) => (
              <span key={queue.id}>{index + 1} {queue.title}</span>
            ))}
          </div>
          <div>
            <b>확인 기준</b>
            <span>노드 <strong>{summary.nodes.ready}/{summary.nodes.total}</strong></span>
            <span>오퍼레이터 <strong>{summary.operators.available}/{summary.operators.total}</strong></span>
            <span>OCP <strong>{displayOpenShiftVersion(summary.version.version)}</strong></span>
          </div>
        </div>
      </>
    )}
  </Panel>
);

const EndpointTable: React.FC<{
  endpoints: Endpoint[];
  onAssistantLaunch?: AssistantLaunchHandler;
}> = ({ endpoints, onAssistantLaunch }) => {
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(10);
  const [query, setQuery] = React.useState('');
  const [severityFilter, setSeverityFilter] = React.useState<'all' | Severity>('all');
  const okCount = endpoints.filter((endpoint) => endpoint.severity === 'ok').length;
  const warnCount = endpoints.filter((endpoint) => endpoint.severity === 'warn').length;
  const riskCount = endpoints.filter((endpoint) => endpoint.severity === 'risk').length;
  const endpointTabs: Array<{ id: 'all' | Severity; label: string; value: number }> = [
    { id: 'all', label: '전체', value: endpoints.length },
    { id: 'ok', label: '정상', value: okCount },
    { id: 'warn', label: '주의', value: warnCount },
    { id: 'risk', label: '위험', value: riskCount },
  ];
  const normalizedQuery = query.trim().toLowerCase();
  const visibleEndpoints = endpoints.filter((endpoint) => {
    const matchesSeverity = severityFilter === 'all' || endpoint.severity === severityFilter;
    const searchable = `${endpoint.name} ${endpoint.type} ${endpoint.group} ${endpoint.path}`.toLowerCase();
    return matchesSeverity && (!normalizedQuery || searchable.includes(normalizedQuery));
  });
  const pageCount = Math.max(1, Math.ceil(visibleEndpoints.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const startIndex = (currentPage - 1) * pageSize;
  const pageEndpoints = visibleEndpoints.slice(startIndex, startIndex + pageSize);
  const rangeStart = visibleEndpoints.length === 0 ? 0 : startIndex + 1;
  const rangeEnd = Math.min(startIndex + pageSize, visibleEndpoints.length);

  React.useEffect(() => {
    setPage(1);
  }, [normalizedQuery, pageSize, severityFilter]);

  React.useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  return (
    <section className="portal-panel table-panel">
      <div className="table-panel__top">
        <div className="portal-panel__title">클러스터 리소스</div>
        <div className="portal-tabs">
          {endpointTabs.map((tab) => (
            <button
              className={severityFilter === tab.id ? 'is-active' : ''}
              key={tab.id}
              onClick={() => setSeverityFilter(tab.id)}
              type="button"
            >
              {tab.label} {tab.value}
            </button>
          ))}
        </div>
        <label className="portal-search">
          <Search />
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="리소스 검색"
            value={query}
          />
        </label>
        <label className="table-page-size">
          <span>페이지당</span>
          <select
            aria-label="페이지당 리소스 수"
            onChange={(event) => setPageSize(Number(event.target.value))}
            value={pageSize}
          >
            {endpointPageSizeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-scroll">
        <table className="endpoint-table">
          <thead>
            <tr>
              <th>이름</th>
              <th>유형</th>
              <th>그룹</th>
              <th>상태</th>
              <th>CPU</th>
              <th>메모리</th>
              <th>응답시간</th>
              <th>최근 이벤트</th>
              {onAssistantLaunch && <th>Assistant</th>}
            </tr>
          </thead>
          <tbody>
            {visibleEndpoints.length === 0 ? (
              <tr>
                <td colSpan={onAssistantLaunch ? 9 : 8}>조건에 맞는 리소스가 없습니다.</td>
              </tr>
            ) : (
              pageEndpoints.map((endpoint) => (
                <tr key={endpoint.id}>
                  <td>
                    <strong>{endpoint.name}</strong>
                    <small>{endpoint.path}</small>
                  </td>
                  <td>{endpoint.type}</td>
                  <td>{endpoint.group}</td>
                  <td>
                    <StatusBadge severity={endpoint.severity} />
                  </td>
                  <td>{endpoint.cpu}</td>
                  <td>{endpoint.memory}</td>
                  <td>{endpoint.latency}</td>
                  <td>
                    <span className={`event-dot ${severityClass(endpoint.severity)}`} />
                    {endpoint.lastEvent}
                  </td>
                  {onAssistantLaunch && (
                    <td>
                      <button
                        className="portal-button"
                        onClick={() => onAssistantLaunch({ context: endpointAssistantContext(endpoint, 'resource-table') })}
                        type="button"
                      >
                        RCA
                      </button>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="table-pagination">
        <span className="table-pagination__summary">
          {rangeStart}-{rangeEnd} / {visibleEndpoints.length}
        </span>
        <div className="table-pagination__controls">
          <button
            aria-label="이전 페이지"
            className="portal-icon-btn"
            disabled={currentPage <= 1}
            onClick={() => setPage((current) => Math.max(1, current - 1))}
            title="이전 페이지"
            type="button"
          >
            <ChevronLeft />
          </button>
          <strong>{currentPage} / {pageCount}</strong>
          <button
            aria-label="다음 페이지"
            className="portal-icon-btn"
            disabled={currentPage >= pageCount}
            onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
            title="다음 페이지"
            type="button"
          >
            <ChevronRight />
          </button>
        </div>
      </div>
    </section>
  );
};

const activityToneLabel: Record<ActivityItem['tone'], string> = {
  blue: '수집',
  green: '정상',
  orange: '주의',
  red: '위험',
  violet: '기록',
};

const ActivityTimeline: React.FC<{ activities: ActivityItem[] }> = ({ activities }) => (
  <section className="portal-panel timeline-panel">
    <div className="timeline-panel__top">
      <div className="portal-panel__title">AIOps 활동 타임라인</div>
      <div className="portal-tabs">
        <span className="is-active">전체 {activities.length}</span>
      </div>
    </div>
    {activities.length === 0 ? (
      <EmptyState label="현재 클러스터/게이트웨이 기준 활동이 없습니다." />
    ) : (
      <div className="activity-table-wrap">
        <table className="activity-table">
          <thead>
            <tr>
              <th>시간</th>
              <th>이벤트</th>
              <th>대상</th>
              <th>상세</th>
              <th>상태</th>
            </tr>
          </thead>
          <tbody>
            {activities.map((activity) => (
              <tr key={activity.id}>
                <td>{formatTime(activity.time)}</td>
                <td>
                  <div className="activity-event-cell">
                    <span className={`activity-row-icon is-${activity.tone}`}>
                      <Activity />
                    </span>
                    <span>
                      <strong>{activity.title}</strong>
                      <small>{sourceLabel(activity.source ?? activity.category ?? 'AIOps')}</small>
                    </span>
                  </div>
                </td>
                <td>{activity.target ?? '-'}</td>
                <td>{activity.detail}</td>
                <td>
                  <span className={`activity-tone is-${activity.tone}`}>{activityToneLabel[activity.tone]}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )}
  </section>
);

const ExecutionRecordsView: React.FC<{ onNavigate: (view: NavView) => void; status: AiopsRuntimeStatus }> = ({
  onNavigate,
  status,
}) => {
  const realRecords = actionRecords(status);
  const realAuditRecords = status.spec.records.auditRecords ?? [];
  const realRecordCount = realRecords.length + realAuditRecords.length;
  const [showSyntheticReplay, setShowSyntheticReplay] = React.useState(true);
  const syntheticReplay = realRecordCount === 0 && showSyntheticReplay;
  const records = syntheticReplay ? mockExecutionRecords : realRecords;
  const auditRecords = syntheticReplay ? mockAuditRecords : realAuditRecords;
  const entries = React.useMemo(
    () => buildLedgerEntries(records, auditRecords, { sample: syntheticReplay }),
    [auditRecords, records, syntheticReplay],
  );
  const [selectedEntryId, setSelectedEntryId] = React.useState('');
  const selectedEntry = entries.find((entry) => entry.id === selectedEntryId) ?? entries[0];

  React.useEffect(() => {
    if (!entries.length) {
      setSelectedEntryId('');
      return;
    }
    setSelectedEntryId((current) => (entries.some((entry) => entry.id === current) ? current : entries[0].id));
  }, [entries]);

  const exportAuditBundle = React.useCallback(() => {
    const bundle = {
      apiVersion: 'aiops.komsco/v1',
      generatedAt: new Date().toISOString(),
      kind: 'OperationLedgerExport',
      mode: syntheticReplay ? 'synthetic-replay' : 'live-gateway',
      entries,
    };
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `operation-ledger-${syntheticReplay ? 'synthetic' : 'live'}-${new Date().toISOString().slice(0, 10)}.json`;
    link.click();
    URL.revokeObjectURL(url);
  }, [entries, syntheticReplay]);

  return (
    <section className="operation-ledger stack-view">
      <DataSourceStatusStrip
        entries={entries}
        onExport={exportAuditBundle}
        onGatewayLogs={() => onNavigate('alerts')}
        onToggleSynthetic={() => setShowSyntheticReplay((current) => !current)}
        realRecordCount={realRecordCount}
        showSyntheticReplay={showSyntheticReplay}
        syntheticReplay={syntheticReplay}
      />
      <RunOverviewStrip
        auditRecords={auditRecords}
        entries={entries}
        records={records}
        syntheticReplay={syntheticReplay}
      />
      <section className="operation-ledger__workspace">
        <ExecutionTracePanel
          entries={entries}
          onSelectEntry={setSelectedEntryId}
          selectedEntryId={selectedEntry?.id ?? ''}
        />
        <ControlGatesPanel entries={entries} selectedEntry={selectedEntry} status={status} />
      </section>
      <AuditLedgerTable entries={entries} />
    </section>
  );
};

const DataSourceStatusStrip: React.FC<{
  entries: LedgerEntry[];
  onExport: () => void;
  onGatewayLogs: () => void;
  onToggleSynthetic: () => void;
  realRecordCount: number;
  showSyntheticReplay: boolean;
  syntheticReplay: boolean;
}> = ({ entries, onExport, onGatewayLogs, onToggleSynthetic, realRecordCount, showSyntheticReplay, syntheticReplay }) => (
  <section className={`ledger-source-strip ${syntheticReplay ? 'is-synthetic' : 'is-live'}`}>
    <span className="ledger-source-strip__pulse" aria-hidden="true" />
    <div>
      <strong>{syntheticReplay ? '데이터 소스 · 샘플 재생 모드' : '데이터 소스 · 실시간 게이트웨이'}</strong>
      <span>
        {syntheticReplay
          ? '게이트웨이 실행/감사 스트림이 비어 있어 샘플 실행 흐름을 재생 중입니다. 실제 클러스터 변경 기록이 아닙니다.'
          : '실시간 게이트웨이 런타임에서 수집한 실행/감사 기록을 표시합니다.'}
      </span>
      <small>
        마지막 게이트웨이 확인 {formatTime(new Date().toISOString())} · 실제 기록 {realRecordCount}건 · 표시 이벤트 {entries.length}건
      </small>
    </div>
    <div className="ledger-source-strip__actions">
      <button onClick={onGatewayLogs} type="button">게이트웨이 이벤트</button>
      <button onClick={onExport} type="button">감사 번들</button>
      {realRecordCount === 0 && (
        <button onClick={onToggleSynthetic} type="button">
          {showSyntheticReplay ? '샘플 숨기기' : '샘플 보기'}
        </button>
      )}
    </div>
  </section>
);

const RunOverviewStrip: React.FC<{
  auditRecords: AiopsRecord[];
  entries: LedgerEntry[];
  records: AiopsRecord[];
  syntheticReplay: boolean;
}> = ({ auditRecords, entries, records, syntheticReplay }) => {
  const proposals = entries.filter((entry) => entry.category === 'proposal').length;
  const approvals = entries.filter((entry) => entry.category === 'approval').length;
  const mutations = entries.filter((entry) => entry.category === 'mutation').length;
  const failed = entries.filter((entry) => entry.tone === 'red').length;
  const runId = entries[0]?.runId ?? '-';
  const namespace = entries.find((entry) => entry.namespace !== '-')?.namespace ?? '-';
  const mutationStatus = mutations > 0 ? 'Executed' : approvals > 0 ? 'Waiting approval' : failed > 0 ? 'Blocked' : 'Not executed';

  return (
    <section className="ledger-run-overview">
      <div>
        <span>{syntheticReplay ? '샘플 실행' : '활성 실행'}</span>
        <strong>{runId}</strong>
      </div>
      <div className="ledger-run-overview__facts">
        <span>{runWindowLabel(entries)}</span>
        <b>이벤트 {entries.length}건</b>
        <b>제안 {proposals}건</b>
        <b>승인 게이트 {approvals}건</b>
        <b>변경 실행 {mutations}건</b>
        <b>감사 기록 {auditRecords.length}건</b>
      </div>
      <div className="ledger-run-overview__meta">
        <span>대상 네임스페이스 <strong>{namespace}</strong></span>
        <span>정책 모드 <strong>{approvals > 0 ? '승인 필요' : '읽기 전용 증거 수집'}</strong></span>
        <span>변경 상태 <strong>{mutationStatusLabel(mutationStatus)}</strong></span>
        <span>조치 기록 <strong>{records.length}건</strong></span>
      </div>
    </section>
  );
};

const ExecutionTracePanel: React.FC<{
  entries: LedgerEntry[];
  onSelectEntry: (id: string) => void;
  selectedEntryId: string;
}> = ({ entries, onSelectEntry, selectedEntryId }) => (
  <section className="portal-panel execution-trace-panel">
    <div className="portal-panel__head">
      <div className="portal-panel__title">실행 추적</div>
    </div>
    <div className="execution-trace">
      {entries.length === 0 ? (
        <EmptyState label="표시할 실행 추적 기록이 없습니다." />
      ) : (
        entries.map((entry, index) => (
          <button
            className={`trace-row is-${entry.tone} ${entry.id === selectedEntryId ? 'is-selected' : ''}`}
            key={entry.id}
            onClick={() => onSelectEntry(entry.id)}
            type="button"
          >
            <span className="trace-row__index">{String(index + 1).padStart(2, '0')}</span>
            <span className="trace-row__time">{formatTime(entry.time)}</span>
            <span className="trace-row__body">
              <strong>{entry.phase}</strong>
              <b>{ledgerActionLabel(entry.action)}</b>
              <small>{ledgerTargetLabel(entry)}</small>
            </span>
            <span className="trace-row__result">{ledgerResultLabel(entry.result)}</span>
            {entry.sample && <span className="trace-row__sample">샘플</span>}
          </button>
        ))
      )}
    </div>
  </section>
);

const ControlGatesPanel: React.FC<{
  entries: LedgerEntry[];
  selectedEntry?: LedgerEntry;
  status: AiopsRuntimeStatus;
}> = ({ entries, selectedEntry, status }) => {
  const capabilities = status.spec.capabilities;
  const items: Array<{ label: string; value: string; tone: 'ok' | 'warn' | 'risk'; detail: string }> = [
    {
      detail: capabilities.mutationsEnabled ? '승인되지 않은 변경은 게이트웨이 정책에서 차단합니다.' : '읽기/증거 수집 모드입니다. 클러스터 변경은 차단됩니다.',
      label: '변경 게이트',
      tone: capabilities.mutationsEnabled ? 'ok' : 'warn',
      value: capabilities.mutationsEnabled ? '켜짐' : '꺼짐',
    },
    {
      detail: entries.some((entry) => entry.category === 'approval') ? '이 실행 흐름에 승인 검증 기록이 포함되어 있습니다.' : '현재 스트림에 승인 검증 기록이 없습니다.',
      label: '승인 검증',
      tone: entries.some((entry) => entry.category === 'approval') ? 'ok' : 'warn',
      value: entries.some((entry) => entry.category === 'approval') ? '준비됨' : '없음',
    },
    {
      detail: capabilities.actionExecutorConfigured ? '승인된 클러스터 조치를 실행할 수 있습니다.' : '외부 실행기가 설정되어 있지 않습니다.',
      label: '조치 실행기',
      tone: capabilities.actionExecutorConfigured ? 'ok' : 'warn',
      value: capabilities.actionExecutorConfigured ? '준비됨' : '미설정',
    },
    {
      detail: capabilities.diagnosticsEnabled ? '진단 증거 수집 경로가 활성화되어 있습니다.' : '증거는 현재 사용 가능한 게이트웨이 기록으로 제한됩니다.',
      label: '진단 수집',
      tone: capabilities.diagnosticsEnabled ? 'ok' : 'warn',
      value: capabilities.diagnosticsEnabled ? '켜짐' : '꺼짐',
    },
    {
      detail: capabilities.recordStoreEnabled ? capabilities.recordStoreConfigMap || '영구 감사 원장이 활성화되어 있습니다.' : '기록이 게이트웨이 영구 원장에 저장되지 않습니다.',
      label: '기록 원장',
      tone: capabilities.recordStoreEnabled ? 'ok' : 'warn',
      value: capabilities.recordStoreEnabled ? '켜짐' : '꺼짐',
    },
  ];

  return (
    <section className="portal-panel control-gates-panel">
      <div className="portal-panel__head">
        <div className="portal-panel__title">실행 제어 게이트</div>
        <span className="live-data-badge">게이트웨이 상태</span>
      </div>
      <div className="control-gate-list">
        {items.map((item) => (
          <article key={item.label}>
            <div>
              <strong>{item.label}</strong>
              <small>{item.detail}</small>
            </div>
            <span className={`guardrail-pill is-${item.tone}`}>{item.value}</span>
          </article>
        ))}
      </div>
      <SelectedLedgerEvent entry={selectedEntry} />
    </section>
  );
};

const SelectedLedgerEvent: React.FC<{ entry?: LedgerEntry }> = ({ entry }) => (
  <div className="selected-ledger-event">
    <div className="selected-ledger-event__title">선택된 이벤트</div>
    {entry ? (
      <dl>
        <div>
          <dt>단계</dt>
          <dd>{entry.phase}</dd>
        </div>
        <div>
          <dt>대상</dt>
          <dd>{ledgerTargetLabel(entry)}</dd>
        </div>
        <div>
          <dt>게이트</dt>
          <dd>{ledgerGateLabel(entry.gate)}</dd>
        </div>
        <div>
          <dt>결과</dt>
          <dd>{ledgerResultLabel(entry.result)}</dd>
        </div>
        <div>
          <dt>증거</dt>
          <dd>{entry.evidenceId}</dd>
        </div>
        <div>
          <dt>감사 ID</dt>
          <dd>{entry.auditId}</dd>
        </div>
      </dl>
    ) : (
      <EmptyState label="선택된 이벤트가 없습니다." />
    )}
  </div>
);

const auditLedgerFilters: Array<{ id: 'all' | LedgerEntry['category']; label: string }> = [
  { id: 'all', label: '전체' },
  { id: 'approval', label: '승인' },
  { id: 'mutation', label: '변경 실행' },
  { id: 'gateway', label: '게이트웨이' },
  { id: 'evidence', label: '증거' },
];

const AuditLedgerTable: React.FC<{ entries: LedgerEntry[] }> = ({ entries }) => {
  const [activeFilter, setActiveFilter] = React.useState<'all' | LedgerEntry['category']>('all');
  const filteredEntries =
    activeFilter === 'all' ? entries : entries.filter((entry) => entry.category === activeFilter);

  return (
    <section className="portal-panel audit-ledger-panel">
      <div className="portal-panel__head">
        <div className="portal-panel__title">감사 원장</div>
        <div className="portal-tabs">
          {auditLedgerFilters.map((filter) => (
            <button
              className={activeFilter === filter.id ? 'is-active' : ''}
              key={filter.id}
              onClick={() => setActiveFilter(filter.id)}
              type="button"
            >
              {filter.label}
            </button>
          ))}
        </div>
      </div>
      <div className="table-scroll">
        <table className="audit-ledger-table">
          <thead>
            <tr>
              <th>시간</th>
              <th>단계</th>
              <th>조치</th>
              <th>네임스페이스</th>
              <th>종류</th>
              <th>이름</th>
              <th>게이트</th>
              <th>결과</th>
              <th>증거</th>
              <th>감사 ID</th>
            </tr>
          </thead>
          <tbody>
            {filteredEntries.length === 0 ? (
              <tr>
                <td colSpan={10}>표시할 감사 원장 항목이 없습니다.</td>
              </tr>
            ) : (
              filteredEntries.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatTime(entry.time)}</td>
                  <td>
                    <span className={`ledger-phase is-${entry.tone}`}>{entry.phase}</span>
                  </td>
                  <td>
                    <strong>{ledgerActionLabel(entry.action)}</strong>
                    <small>{entry.actor}{entry.sample ? ' · 샘플' : ''}</small>
                  </td>
                  <td>{entry.namespace}</td>
                  <td>{ledgerKindLabel(entry.kind)}</td>
                  <td>{entry.name}</td>
                  <td>{ledgerGateLabel(entry.gate)}</td>
                  <td>{ledgerResultLabel(entry.result)}</td>
                  <td>{entry.evidenceId}</td>
                  <td>{entry.auditId}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
};

const RcaView: React.FC<{
  onAssistantLaunch?: AssistantLaunchHandler;
  onNavigate: (view: NavView) => void;
  onOpenItem: (item: QueueItem) => void;
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
}> = ({ onAssistantLaunch, onNavigate, onOpenItem, status, summary }) => {
  const liveQueues = buildQueues(summary, status);
  const sampleMode = liveQueues.length === 0;
  const queues = sampleMode ? sampleRcaQueues : liveQueues;
  const [selectedId, setSelectedId] = React.useState(() => defaultRcaSelection(queues));
  const selected = queues.find((item) => item.id === selectedId) ?? queues[0];
  const selectedIndex = Math.max(0, queues.findIndex((item) => item.id === selected?.id));
  const selectedIsUpdate = selected ? isClusterUpdateIssue(selected) : false;
  const selectedIssueType = rcaIssueType(selected);
  const podSummary = buildPodRcaSummary(summary);
  const queueGroups = buildRcaQueueGroups(queues);
  const findings = buildRcaFindings(summary, selected, podSummary);
  const evidencePack = buildRcaEvidencePack(summary, selected, podSummary);
  const runbookGates = buildRcaRunbookGates(summary, selected, podSummary);
  const commandBundle = buildRcaCommandBundle(selected, runbookGates);
  const timeline = buildRcaTimeline(summary, selected, podSummary, findings);
  const caseHeader = buildRcaCaseHeader(summary, selected, podSummary);
  const caseId = rcaCaseId(selected, selectedIndex);
  const [actionNote, setActionNote] = React.useState('');

  React.useEffect(() => {
    setSelectedId((current) => (queues.some((item) => item.id === current) ? current : defaultRcaSelection(queues)));
  }, [queues]);

  const copyCommands = React.useCallback(() => {
    const commands = commandBundle.map((command) => `# ${command.title}\n${command.command}`).join('\n\n');
    void navigator.clipboard?.writeText(commands);
    setActionNote('oc 명령 묶음을 클립보드에 복사했습니다.');
  }, [commandBundle]);

  const exportBundle = React.useCallback(() => {
    const bundle = {
      apiVersion: 'aiops.komsco/v1',
      generatedAt: new Date().toISOString(),
      kind: 'RcaBundle',
      caseId,
      cluster: clusterLabel(summary),
      selected,
      issueType: selectedIssueType,
      podSummary: selectedIssueType === 'WORKLOAD_PODS' || selectedIssueType === 'WORKLOAD_DERIVED' ? podSummary : undefined,
      findings,
      evidencePack,
      runbookGates,
      commandBundle,
      timeline,
    };
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${caseId.toLowerCase()}-bundle.json`;
    link.click();
    URL.revokeObjectURL(url);
    setActionNote('RCA 번들 JSON을 생성했습니다.');
  }, [caseId, commandBundle, evidencePack, findings, podSummary, runbookGates, selected, selectedIssueType, summary, timeline]);

  const launchSelectedAssistant = React.useCallback(
    (actionType: string) => {
      if (!selected || !onAssistantLaunch) {
        return;
      }
      onAssistantLaunch({
        context: queueAssistantContext(selected, 'rca-center', actionType),
      });
      setActionNote('선택한 RCA 컨텍스트를 Assistant에 전달했습니다.');
    },
    [onAssistantLaunch, selected],
  );

  return (
    <section className="rca-workbench-v2 stack-view">
      <section className={`rca-case-header is-${selectedIssueType.toLowerCase().replaceAll('_', '-')}`}>
        <div className="rca-case-header__rail" aria-hidden="true">
          <span />
        </div>
        <div className="rca-case-header__main">
          <span className="rca-case-header__family">{caseHeader.family}</span>
          <h2><small>{caseId}</small>{caseHeader.title}</h2>
          <p>{caseHeader.finding}</p>
          <div className="rca-telemetry-row">
            {caseHeader.metrics.map((metric) => (
              <span key={`${metric.label}-${metric.value}`}>
                {metric.label}
                <strong>{metric.value}</strong>
              </span>
            ))}
          </div>
          <div className="rca-case-header__meta">
            <span>{caseHeader.issueLine}</span>
            <span>{caseHeader.scope}</span>
            <span>{caseHeader.caseState}</span>
            <span>{caseHeader.baseline}</span>
          </div>
        </div>
        <div className="rca-case-header__actions">
          {onAssistantLaunch && (
            <button className="portal-button is-primary" onClick={() => launchSelectedAssistant('rca')} type="button">
              Assistant RCA
            </button>
          )}
          <button className="portal-button" onClick={copyCommands} type="button">oc 묶음</button>
          <button className="portal-button" onClick={() => setActionNote('원본 증거 YAML은 BE evidence store 연동 후 열 수 있습니다.')} type="button">원본 증거</button>
          <button className="portal-button" onClick={exportBundle} type="button">RCA 보고서</button>
        </div>
      </section>

      <section className="rca-main-grid">
        <Panel
          className="rca-queue-panel"
          title="조사 큐"
          action={<StatusBadge label={sampleMode ? '샘플 데이터' : '실시간'} severity={sampleMode ? 'warn' : 'ok'} />}
        >
          <div className="rca-family-list">
            {queueGroups.map((group) => (
              <section key={group.id}>
                <h3>{group.title}</h3>
                {group.items.map((item) => (
                  <button
                    className={`rca-family-item ${item.id === selected?.id ? 'is-selected' : ''} ${severityClass(item.severity)}`}
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    type="button"
                  >
                    <StatusBadge label={rcaQueueBadgeLabel(item)} severity={item.severity} />
                    <span>
                      <strong>{isPodIssue(item) ? '파드 상태 저하' : isDerivedWorkloadIssue(item) ? `${item.target ?? item.title} 가용성 변화` : item.title}</strong>
                      <small>{rcaQueueDetail(summary, item, podSummary)}</small>
                    </span>
                  </button>
                ))}
              </section>
            ))}
          </div>
        </Panel>

        <Panel
          className="rca-canvas-panel"
          title="원인 분석 캔버스"
          action={
            selected && (
              <button className="portal-button" onClick={() => onOpenItem(selected)} type="button">
                이슈 원본
              </button>
            )
          }
        >
          {selected ? (
            <div className="finding-board">
              {findings.map((finding) => (
                <article className={`is-${finding.tone}`} key={`${finding.kicker}-${finding.title}`}>
                  <div>
                    <span>{finding.kicker}</span>
                    <strong>{finding.title}</strong>
                    <p>{finding.detail}</p>
                  </div>
                  <small>{finding.meta}</small>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState label="분석할 이슈가 없습니다." />
          )}
        </Panel>

        <Panel className="rca-evidence-panel" title="증거 패키지">
          {selected ? (
            <div className="evidence-pack-table">
              <div className="evidence-pack-table__head">
                <span>출처</span>
                <span>필드</span>
                <span>값</span>
                <span>상태</span>
              </div>
              {evidencePack.map((row, index) => {
                const previous = evidencePack[index - 1];
                const showCommand = !previous || previous.source !== row.source || previous.command !== row.command;
                return (
                  <article key={`${row.source}-${row.field}`}>
                    <span>{row.source}</span>
                    <strong>{row.field}</strong>
                    <b>{row.value}</b>
                    <em className={`is-${row.status}`}>{evidenceStatusLabel(row.status)}</em>
                    <small>{row.collector} · {row.freshness}</small>
                    {showCommand && <code>{row.command}</code>}
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyState label="표시할 증거가 없습니다." />
          )}
        </Panel>
      </section>

      <section className="portal-grid rca-trace-grid">
        <Panel
          className="rca-impact-panel"
          title={selectedIsUpdate ? '클러스터 업데이트 의존성 추적' : '워크로드 런타임 의존성 추적'}
        >
          {selectedIsUpdate ? (
            <div className="cluster-update-trace">
              {[
                ['업데이트 채널', summary.version.channel ?? 'stable-4.20', `후보 ${rcaAvailableUpdates(summary, selected)}`],
                ['ClusterVersion', `version · 현재 ${rcaCurrentVersion(summary, selected)}`, `Upgradeable False · ${rcaReason(summary, selected)}`],
                ['CVO', 'Cluster Version Operator', 'RetrievedUpdates True · Progressing False'],
                ['CO', `ClusterOperators · Available ${summary.operators.available}/${summary.operators.total}`, `Degraded ${summary.operators.degraded} · Progressing ${summary.operators.progressing}`],
                ['MCP', 'MachineConfigPools', 'master/worker updated · degraded 0'],
                ['노드', `Ready ${summary.nodes.ready}/${summary.nodes.total}`, `NotReady ${summary.nodes.notReady}`],
                ['워크로드 영향', selected?.severity === 'risk' ? '높음' : '중간', '변경 창 검증 필요'],
              ].map(([title, detail, meta], index, list) => (
                <React.Fragment key={title}>
                  <article className={index === 1 ? 'is-attention' : ''}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <strong>{title}</strong>
                    <p>{detail}</p>
                    <small>{meta}</small>
                  </article>
                  {index < list.length - 1 && <i aria-hidden="true" />}
                </React.Fragment>
              ))}
            </div>
          ) : (
            <ClusterTopologyMap summary={summary} variant="runtime" />
          )}
        </Panel>
        <Panel
          className="runbook-gates-panel"
          title="런북 게이트"
          action={
            <button className="portal-button" onClick={copyCommands} type="button">
              oc 복사
            </button>
          }
        >
          <div className="runbook-gate-list">
            {runbookGates.map((gate, index) => (
              <article className={`is-${gate.tone}`} key={gate.id}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <div>
                  <strong>{gate.title}</strong>
                  <p>{gate.detail}</p>
                  <code>{gate.command}</code>
                </div>
                <em>{gate.status}</em>
                <small>{gate.gate}</small>
              </article>
            ))}
          </div>
        </Panel>
      </section>

      <section className="portal-grid portal-grid--two">
        <Panel
          title="RCA 명령 묶음"
          action={
            <div className="rca-command-actions">
            <button className="portal-button" onClick={copyCommands} type="button">oc 묶음 복사</button>
            <button className="portal-button" onClick={exportBundle} type="button">RCA 번들 내보내기</button>
          </div>
          }
        >
          <div className="rca-command-preview">
            {commandBundle.map((command) => (
              <article key={`${command.title}-${command.command}`}>
                <strong># {command.title}</strong>
                <code>{command.command}</code>
              </article>
            ))}
          </div>
          <div className="rca-command-bar">
            <button className="portal-button" onClick={() => setActionNote('원본 증거 YAML은 BE evidence store 연동 후 열 수 있습니다.')} type="button">원본 증거 열기</button>
            <button
              className="portal-button"
              onClick={() => launchSelectedAssistant('action-plan')}
              type="button"
            >
              변경 요청 생성
            </button>
            <button className="portal-button" onClick={() => onNavigate('executions')} type="button">실행 기록</button>
            {actionNote && <span>{actionNote}</span>}
          </div>
        </Panel>
        <Panel title="감사 / 타임라인">
          <div className="rca-audit-trail">
            {timeline.map((entry) => (
              <article key={`${entry.title}-${entry.detail}`}>
                <time>{formatTime(summary.updatedAt)}</time>
                <strong>{entry.title}</strong>
                <span>{entry.detail}</span>
              </article>
            ))}
          </div>
        </Panel>
      </section>
    </section>
  );
};

const ServiceMapView: React.FC<{ onNavigate: (view: NavView) => void; summary: ClusterSummary }> = ({
  onNavigate,
  summary,
}) => {
  const [affectedOnly, setAffectedOnly] = React.useState(false);
  const [edgeMode, setEdgeMode] = React.useState<TopologyEdgeMode>('all');
  const [showEdgeLabels, setShowEdgeLabels] = React.useState(true);
  const [selectedNode, setSelectedNode] = React.useState<TopologyNodeKey>('pods');
  const [showInspectorCommands, setShowInspectorCommands] = React.useState(false);
  const primarySignals = topologyPrimarySignals(summary);
  const derivedSignals = topologyDerivedSignals(summary);
  const otherSignals = topologyOtherSignals(summary);
  const inspector = buildTraceInspector(summary, selectedNode);
  const impactSignalSections = buildImpactSignalStack(summary);
  const traceNodes = inspector.trace.split(/\s*->\s*/);
  const compactFocus = inspector.focus.includes('·') ? inspector.focus.split('·').slice(1).join('·').trim() : inspector.focus;
  const summarySignals = inspector.signals.filter((signal) => signal.label !== '완료 제외').slice(0, 5);
  const nextChecksByNode: Record<TopologyNodeKey, string[]> = {
    daemonsets: ['DaemonSet 상태', '노드별 Pod', '이벤트'],
    deployments: ['가용 수량', 'ReplicaSet', 'Pod readiness'],
    nodes: ['Node condition', 'Pressure', '스케줄링'],
    persistentvolumeclaims: ['PVC Bound', '마운트 이벤트', 'Pod 볼륨'],
    pods: ['Pod 이벤트', 'Container 상태', 'Owner chain'],
    replicasets: ['Ready 차이', 'Owner chain', 'Pod readiness'],
    routes: ['Route 대상', 'Service 연결', 'TLS/Host'],
    services: ['Selector', 'EndpointSlice', 'Pod 연결'],
    statefulsets: ['Ready 수량', 'PVC 연결', 'Pod identity'],
  };
  const nextChecks = nextChecksByNode[selectedNode];
  const impactRows = impactSignalSections.flatMap((section) =>
    section.id === 'cleared'
      ? []
      : section.rows.map((row) => ({
          ...row,
          roleLabel: section.id === 'primary' ? 'Primary signal' : 'Derived',
        })),
  );
  const clearedRows = impactSignalSections.find((section) => section.id === 'cleared')?.rows ?? [];
  const copyInspectorCommands = React.useCallback(() => {
    const commands = inspector.commands.map((command) => `# ${command.title}\n${command.command}`).join('\n\n');
    void navigator.clipboard?.writeText(commands);
  }, [inspector.commands]);
  const copyCommand = React.useCallback((command: string) => {
    void navigator.clipboard?.writeText(command);
  }, []);
  const edgeButtons: Array<{ id: TopologyEdgeMode; label: string }> = [
    { id: 'all', label: '전체 관계' },
    { id: 'traffic', label: '트래픽' },
    { id: 'ownership', label: '소유 관계' },
    { id: 'runtime', label: '런타임' },
  ];

  return (
    <section className="service-map-workbench stack-view">
      <section className="map-control-strip">
        <div className="map-control-strip__main">
          <span>서비스 맵 / 클러스터 토폴로지</span>
          <strong>{clusterLabel(summary)}</strong>
          <p>
            전체 네임스페이스 · 스냅샷 {formatTime(summary.updatedAt)} · 게이트웨이 정상 · OCP {displayOpenShiftVersion(summary.version.version)}
            {summary.nodes.total === 1 ? ' · 단일 노드 런타임' : ''}
          </p>
          <small>
            활성 신호 {summary.resources?.issues ?? 0}건 · Primary 파드 {primarySignals}건 · Derived 컨트롤러 {derivedSignals}건
            {otherSignals > 0 ? ` · 기타 ${otherSignals}건` : ''}
          </small>
        </div>
        <div className="map-control-strip__controls">
          <button className={affectedOnly ? 'is-active' : ''} onClick={() => setAffectedOnly((value) => !value)} type="button">
            영향만
          </button>
          {edgeButtons.map((button) => (
            <button
              className={edgeMode === button.id ? 'is-active' : ''}
              key={button.id}
              onClick={() => setEdgeMode(button.id)}
              type="button"
            >
              {button.label}
            </button>
          ))}
          <button className={showEdgeLabels ? 'is-active' : ''} onClick={() => setShowEdgeLabels((value) => !value)} type="button">
            관계 라벨
          </button>
        </div>
      </section>

      <section className="portal-panel service-map-page">
        <div className="portal-panel__head">
          <div className="portal-panel__title">클러스터 리소스 관계도</div>
          <StatusBadge label={`노드 ${summary.nodes.ready}/${summary.nodes.total}`} severity={summary.nodes.notReady > 0 ? 'risk' : 'ok'} />
        </div>
        <div className="portal-panel__body">
          <ClusterTopologyMap
            affectedOnly={affectedOnly}
            edgeMode={edgeMode}
            onSelectNode={setSelectedNode}
            selectedNode={selectedNode}
            showEdgeLabels={showEdgeLabels}
            summary={summary}
          />
        </div>
      </section>

      <section className="portal-panel topology-inspector">
        <div className="portal-panel__head">
          <div className="portal-panel__title">선택 경로 요약</div>
          <div className="rca-command-actions">
            <button className="portal-button" onClick={() => onNavigate('rca')} type="button">RCA 열기</button>
            <button
              className="portal-button"
              disabled={inspector.commands.length === 0}
              onClick={() => setShowInspectorCommands((value) => !value)}
              type="button"
            >
              {showInspectorCommands ? 'oc 명령 닫기' : 'oc 명령 보기'}
            </button>
          </div>
        </div>
        <div className="trace-summary">
          <div className="trace-summary__main">
            <span className="trace-summary__eyebrow">선택 경로</span>
            <div className="trace-path" aria-label={inspector.trace}>
              {traceNodes.map((node, index) => (
                <React.Fragment key={`${node}-${index}`}>
                  {index > 0 && <ChevronRight aria-hidden="true" />}
                  <strong>{node}</strong>
                </React.Fragment>
              ))}
            </div>
            <div className="trace-summary__finding">
              <div>
                <strong>{inspector.title} · {compactFocus}</strong>
                <p>{inspector.insight}</p>
              </div>
              <StatusBadge severity={inspector.severity} />
            </div>
          </div>
          <div className="trace-summary__signals">
            {summarySignals.map((signal) => (
              <article key={`${signal.label}-${signal.value}`}>
                <span>{signal.label}</span>
                <strong>{signal.value}</strong>
              </article>
            ))}
          </div>
          <div className="trace-summary__next">
            <span>다음 확인</span>
            <div>
              {nextChecks.map((check) => (
                <b key={`${selectedNode}-${check}`}>{check}</b>
              ))}
            </div>
          </div>
          {showInspectorCommands && (
            <div className="command-bundle">
              <div className="command-bundle__head">
                <span>oc 명령</span>
                <button className="command-copy" onClick={copyInspectorCommands} type="button">전체 복사</button>
              </div>
              {inspector.commands.map((command) => (
                <article key={`${command.title}-${command.command}`}>
                  <div>
                    <strong>{command.title}</strong>
                    <code>{command.command}</code>
                  </div>
                  <button className="command-copy" onClick={() => copyCommand(command.command)} type="button">복사</button>
                </article>
              ))}
            </div>
          )}
        </div>
      </section>

      <Panel title="영향 후보">
        <div className="impact-candidate-list">
          {impactRows.map((row) => (
            <article className={`impact-candidate-row ${severityClass(row.severity)}`} key={row.id}>
              <StatusBadge severity={row.severity} />
              <div className="impact-candidate-row__body">
                <div className="impact-candidate-row__top">
                  <strong>{row.title}</strong>
                  <b>{row.metric}</b>
                </div>
                <p>{row.chips.slice(0, row.roleLabel === 'Primary signal' ? 4 : 3).join(' · ')}</p>
                <small>{row.roleLabel === 'Primary signal' ? 'Primary signal' : row.description}</small>
              </div>
            </article>
          ))}
          {clearedRows.length > 0 && (
            <div className="impact-cleared-line">
              <span>정상 의존성</span>
              <strong>{clearedRows.map((row) => `${row.title} ${row.metric}`).join(' · ')}</strong>
            </div>
          )}
        </div>
      </Panel>
    </section>
  );
};

const ResourceInventoryView: React.FC<{
  onAssistantLaunch?: AssistantLaunchHandler;
  summary: ClusterSummary;
}> = ({ onAssistantLaunch, summary }) => {
  const endpoints = buildEndpoints(summary);
  const resources = summary.resources?.items ?? [];
  const risk = endpoints.filter((endpoint) => endpoint.severity === 'risk').length;
  const warn = endpoints.filter((endpoint) => endpoint.severity === 'warn').length;

  return (
    <section className="resource-inventory stack-view">
      <section className="inventory-summary-grid">
        <KpiCard color={risk > 0 ? 'red' : 'green'} label="위험 리소스" sub={`주의 ${warn}`} value={risk} />
        <KpiCard color="blue" label="전체 리소스" sub="표시 대상" value={endpoints.length} />
        <KpiCard color={summary.nodes.notReady > 0 ? 'red' : 'green'} label="노드 상태" sub={`비정상 ${summary.nodes.notReady}`} value={`${summary.nodes.ready}/${summary.nodes.total}`} />
        <KpiCard color={summary.resources?.issues ? 'red' : 'green'} label="리소스 이슈" sub="게이트웨이 요약" value={summary.resources?.issues ?? 0} />
      </section>
      <EndpointTable endpoints={endpoints} onAssistantLaunch={onAssistantLaunch} />
      <Panel title="리소스 그룹 분포">
        <div className="resource-distribution">
          {resources.map((resource) => (
            <article key={resource.id}>
              <div>
                <strong>{resourceNameLabel(resource.id, resource.name, resource.kind)}</strong>
                <span>{localizeTelemetryText(resource.detail)}</span>
              </div>
              <div className="meter"><span style={{ width: `${Math.min(100, Number(resource.ready) / Math.max(1, resource.total) * 100)}%` }} /></div>
              <b>{resource.score}</b>
              {onAssistantLaunch && resource.issues > 0 && (
                <button
                  className="portal-button"
                  onClick={() =>
                    onAssistantLaunch({
                      context: endpointAssistantContext(
                        {
                          cpu: '-',
                          group: `전체 ${resource.total}`,
                          id: resource.id,
                          lastEvent: formatTime(summary.updatedAt),
                          latency: `이슈 ${resource.issues}건`,
                          memory: '-',
                          name: resourceNameLabel(resource.id, resource.name, resource.kind),
                          path: localizeTelemetryText(resource.detail),
                          severity: resource.severity,
                          type: ledgerKindLabel(resource.kind),
                        },
                        'resource-distribution',
                      ),
                    })
                  }
                  type="button"
                >
                  RCA
                </button>
              )}
            </article>
          ))}
        </div>
      </Panel>
    </section>
  );
};

const EventDetailDrawer: React.FC<{
  group: EventInboxGroup | null;
  onAssistantLaunch?: AssistantLaunchHandler;
  onClose: () => void;
  onOpenIssue: (item: QueueItem) => void;
}> = ({ group, onAssistantLaunch, onClose, onOpenIssue }) => {
  const commands = group ? eventCommands(group) : [];
  return (
    <div className={`portal-drawer event-detail-drawer ${group ? 'is-open' : ''}`} onClick={onClose}>
      <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
        <div className="portal-drawer__head">
          <div>
            <span>Event Detail</span>
            <strong>{group ? group.title : '이벤트 상세'}</strong>
          </div>
          <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
            <X />
          </button>
        </div>
        <div className="portal-drawer__body">
          {group && (
            <>
              <section className={`event-detail-hero ${severityClass(group.severity)}`}>
                <StatusBadge severity={group.severity} />
                <div>
                  <h2>{group.reason}</h2>
                  <p>{group.kind} / {group.target}</p>
                </div>
              </section>
              <section className="event-detail-grid">
                <div><span>Namespace</span><strong>{group.namespace}</strong></div>
                <div><span>Count</span><strong>{group.rows.length}</strong></div>
                <div><span>Last seen</span><strong>{group.time}</strong></div>
                <div><span>Related issue</span><strong>{group.relatedIssue?.title ?? '-'}</strong></div>
              </section>
              <section className="event-detail-section">
                <strong>Message</strong>
                <p>{group.detail}</p>
              </section>
              <section className="event-detail-section">
                <strong>Raw events</strong>
                <div className="event-raw-list">
                  {group.rows.map((row) => (
                    <article key={row.id}>
                      <StatusBadge severity={row.severity} />
                      <div>
                        <b>{row.title}</b>
                        <span>{row.detail}</span>
                        <small>{row.source} · {row.namespace} · {row.target} · {row.time}</small>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
              <section className="event-detail-section">
                <strong>Commands</strong>
                <div className="event-command-list">
                  {commands.map((command) => (
                    <article key={`${command.title}-${command.command}`}>
                      <span>{command.title}</span>
                      <code>{command.command}</code>
                    </article>
                  ))}
                </div>
              </section>
              {group.relatedIssue && (
                <button
                  className="portal-button event-issue-open"
                  onClick={() => {
                    onOpenIssue(group.relatedIssue as QueueItem);
                    onClose();
                  }}
                  type="button"
                >
                  연결 이슈 열기
                </button>
              )}
              {onAssistantLaunch && (
                <button
                  className="portal-button is-primary event-issue-open"
                  onClick={() => onAssistantLaunch({ context: eventAssistantContext(group, 'event-detail') })}
                  type="button"
                >
                  Assistant RCA
                </button>
              )}
            </>
          )}
        </div>
      </aside>
    </div>
  );
};

const AlertsEventsView: React.FC<{
  events: AiopsEventFeed;
  onAssistantLaunch?: AssistantLaunchHandler;
  onOpenItem: (item: QueueItem) => void;
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
}> = ({ events, onAssistantLaunch, onOpenItem, status, summary }) => {
  const rows = buildAlertEventRows(summary, status, events);
  const queues = buildQueues(summary, status);
  const rawEventRows = rows.filter((row) => row.source !== '게이트웨이 요약' && row.category !== '클러스터 알림');
  const normalRows = rawEventRows.filter(isNormalLifecycleEvent);
  const [severityFilter, setSeverityFilter] = React.useState<'all' | Severity>('all');
  const [viewMode, setViewMode] = React.useState<'grouped' | 'raw'>('grouped');
  const [showNormal, setShowNormal] = React.useState(false);
  const [reasonFilter, setReasonFilter] = React.useState('전체');
  const [objectFilter, setObjectFilter] = React.useState('전체');
  const [query, setQuery] = React.useState('');
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(10);
  const [selectedEventGroup, setSelectedEventGroup] = React.useState<EventInboxGroup | null>(null);
  const reasonOptions = ['전체', ...Array.from(new Set(rawEventRows.map(eventReason))).slice(0, 6)];
  const objectOptions = ['전체', ...Array.from(new Set(rawEventRows.map(eventObjectKind))).slice(0, 6)];
  const filteredRawRows = rawEventRows.filter((row) => {
    const matchesSeverity = severityFilter === 'all' || row.severity === severityFilter;
    const matchesNormal = showNormal || !isNormalLifecycleEvent(row);
    const matchesReason = reasonFilter === '전체' || eventReason(row) === reasonFilter;
    const matchesObject = objectFilter === '전체' || eventObjectKind(row) === objectFilter;
    const text = `${row.title} ${row.detail} ${row.target} ${row.source} ${row.namespace}`.toLowerCase();
    return matchesSeverity && matchesNormal && matchesReason && matchesObject && (!query.trim() || text.includes(query.trim().toLowerCase()));
  });
  const inboxGroups = buildEventInboxGroups(filteredRawRows, queues);
  const criticalCount = rawEventRows.filter((row) => row.severity === 'risk').length;
  const warningCount = rawEventRows.filter((row) => row.severity === 'warn').length;
  const connectedIssues = queues.length > 0 ? queues : sampleRcaQueues;
  const eventItemTotal = viewMode === 'grouped' ? inboxGroups.length : filteredRawRows.length;
  const pageCount = Math.max(1, Math.ceil(eventItemTotal / pageSize));
  const currentPage = Math.min(page, pageCount);
  const startIndex = (currentPage - 1) * pageSize;
  const rangeStart = eventItemTotal === 0 ? 0 : startIndex + 1;
  const rangeEnd = Math.min(startIndex + pageSize, eventItemTotal);
  const visibleGroupRows = viewMode === 'grouped' ? inboxGroups.slice(startIndex, startIndex + pageSize) : [];
  const visibleRawRows = viewMode === 'raw' ? filteredRawRows.slice(startIndex, startIndex + pageSize) : [];

  React.useEffect(() => {
    setPage(1);
  }, [objectFilter, pageSize, query, reasonFilter, severityFilter, showNormal, viewMode]);

  React.useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  return (
    <section className="alerts-events-view stack-view">
      <section className="event-stream-bar">
        <div>
          <span>Event Stream</span>
          <strong>{clusterLabel(summary)}</strong>
        </div>
        <p>
          {rawEventRows.length} events · Critical {criticalCount} · Warning {warningCount} · Normal {normalRows.length}
          {' · '}최근 동기화 {formatTime(summary.updatedAt)} · {viewMode === 'grouped' ? 'Reason 기준 그룹 보기' : '원본 이벤트 보기'}
          {!showNormal ? ' · Normal 숨김' : ''}
        </p>
      </section>

      <section className="alerts-events-grid">
        <Panel
          title="이벤트 인박스"
          action={
            <label className="portal-search">
              <Search />
              <input onChange={(event) => setQuery(event.target.value)} placeholder="reason, pod, namespace 검색" value={query} />
            </label>
          }
        >
          <div className="event-toolbar">
            <div className="portal-tabs alert-filter-tabs">
              {(['all', 'risk', 'warn', 'ok'] as Array<'all' | Severity>).map((filter) => (
                <button
                  className={severityFilter === filter ? 'is-active' : ''}
                  key={filter}
                  onClick={() => setSeverityFilter(filter)}
                  type="button"
                >
                  {filter === 'all' ? '전체' : severityLabel[filter]}
                </button>
              ))}
            </div>
            <div className="portal-tabs alert-filter-tabs">
              {(['grouped', 'raw'] as const).map((mode) => (
                <button className={viewMode === mode ? 'is-active' : ''} key={mode} onClick={() => setViewMode(mode)} type="button">
                  {mode === 'grouped' ? '그룹 보기' : '원본 보기'}
                </button>
              ))}
              <button className={showNormal ? 'is-active' : ''} onClick={() => setShowNormal((value) => !value)} type="button">
                Normal 표시
              </button>
            </div>
          </div>
          <div className="event-filter-row">
            <select onChange={(event) => setReasonFilter(event.target.value)} value={reasonFilter}>
              {reasonOptions.map((reason) => <option key={reason}>{reason}</option>)}
            </select>
            <select onChange={(event) => setObjectFilter(event.target.value)} value={objectFilter}>
              {objectOptions.map((object) => <option key={object}>{object}</option>)}
            </select>
          </div>

          {viewMode === 'grouped' ? (
            <div className="event-inbox">
              {visibleGroupRows.map((group) => {
                const targetCount = new Set(group.rows.map((row) => row.target)).size;
                const namespaceCount = new Set(group.rows.map((row) => row.namespace)).size;
                return (
                  <article className={severityClass(group.severity)} key={group.id}>
                    <StatusBadge severity={group.severity} />
                    <button onClick={() => setSelectedEventGroup(group)} type="button">
                      <div className="event-inbox__top">
                        <strong>{group.rows.length > 1 ? `${group.title} 반복 감지` : group.title}</strong>
                        <time>{group.time}</time>
                      </div>
                      <p>{targetCount}개 대상 · {namespaceCount}개 namespace · {group.rows.length}회</p>
                      <small>{group.target} · {group.detail}</small>
                      <span>{group.relatedIssue ? `연결 이슈 ${group.relatedIssue.title}` : '연결 이슈 없음'}</span>
                    </button>
                  </article>
                );
              })}
              {normalRows.length > 0 && !showNormal && (
                <div className="normal-collapse-row">
                  <strong>정상 lifecycle 이벤트 {normalRows.length}건 접힘</strong>
                  <span>{Array.from(new Set(normalRows.map(eventReason))).join(' · ')}</span>
                </div>
              )}
              {visibleGroupRows.length === 0 && <EmptyState label="조건에 맞는 이벤트 그룹이 없습니다." />}
            </div>
          ) : (
            <div className="event-ledger">
              {visibleRawRows.map((row) => (
                <article className={severityClass(row.severity)} key={row.id}>
                  <StatusBadge label={row.sample ? '샘플' : severityLabel[row.severity]} severity={row.severity} />
                  <button onClick={() => setSelectedEventGroup(eventGroupFromRow(row, queues))} type="button">
                    <strong>{eventReason(row)}</strong>
                    <span>{row.detail}</span>
                    <small>{eventObjectKind(row)} · {row.source} · {row.namespace} · {row.target}</small>
                  </button>
                  <time>{row.time}</time>
                </article>
              ))}
              {filteredRawRows.length === 0 && <EmptyState label="조건에 맞는 원본 이벤트가 없습니다." />}
            </div>
          )}

          <div className="table-pagination event-pagination">
            <span className="table-pagination__summary">
              {rangeStart}-{rangeEnd} / {eventItemTotal} {viewMode === 'grouped' ? '그룹' : '이벤트'}
            </span>
            <div className="event-pagination__actions">
              <label className="table-page-size event-page-size">
                <span>페이지당</span>
                <select
                  aria-label="페이지당 이벤트 수"
                  onChange={(event) => setPageSize(Number(event.target.value))}
                  value={pageSize}
                >
                  {eventInboxPageSizeOptions.map((option) => (
                    <option key={option} value={option}>
                      {option}
                    </option>
                  ))}
                </select>
              </label>
              <div className="table-pagination__controls">
                <button
                  aria-label="이전 페이지"
                  className="portal-icon-btn"
                  disabled={currentPage <= 1}
                  onClick={() => setPage((current) => Math.max(1, current - 1))}
                  title="이전 페이지"
                  type="button"
                >
                  <ChevronLeft />
                </button>
                <strong>{currentPage} / {pageCount}</strong>
                <button
                  aria-label="다음 페이지"
                  className="portal-icon-btn"
                  disabled={currentPage >= pageCount}
                  onClick={() => setPage((current) => Math.min(pageCount, current + 1))}
                  title="다음 페이지"
                  type="button"
                >
                  <ChevronRight />
                </button>
              </div>
            </div>
          </div>
        </Panel>

        <Panel title="연결된 이슈">
          <div className="issue-correlation-list">
            {connectedIssues.slice(0, 5).map((item) => (
              <article className={severityClass(item.severity)} key={item.id}>
                <StatusBadge severity={item.severity} />
                <div>
                  <strong>{item.title}</strong>
                  <span>{isPodIssue(item) ? `이벤트 ${criticalCount + warningCount}건 연결 · BackOff/Probe/Failed` : item.detail}</span>
                </div>
                <div className="issue-correlation-list__actions">
                  {onAssistantLaunch && (
                    <button
                      className="portal-button is-primary"
                      onClick={() => onAssistantLaunch({ context: queueAssistantContext(item, 'alert-linked-issue') })}
                      type="button"
                    >
                      RCA
                    </button>
                  )}
                  <button className="portal-button" onClick={() => onOpenItem(item)} type="button">상세</button>
                </div>
              </article>
            ))}
          </div>
        </Panel>
      </section>

      <EventDetailDrawer
        group={selectedEventGroup}
        onAssistantLaunch={onAssistantLaunch}
        onClose={() => setSelectedEventGroup(null)}
        onOpenIssue={onOpenItem}
      />
    </section>
  );
};

const WikiUploadDrawer: React.FC<{
  dragActive: boolean;
  handleUploadFiles: (fileList: FileList | null) => void;
  indexedCount: number;
  onClose: () => void;
  open: boolean;
  ragChunkSize: string;
  ragCollection: string;
  setDragActive: (value: boolean) => void;
  setRagChunkSize: (value: string) => void;
  setRagCollection: (value: string) => void;
  setShowAdvancedSettings: React.Dispatch<React.SetStateAction<boolean>>;
  showAdvancedSettings: boolean;
  uploadItems: WikiUploadItem[];
}> = ({
  dragActive,
  handleUploadFiles,
  indexedCount,
  onClose,
  open,
  ragChunkSize,
  ragCollection,
  setDragActive,
  setRagChunkSize,
  setRagCollection,
  setShowAdvancedSettings,
  showAdvancedSettings,
  uploadItems,
}) => (
  <div className={`portal-drawer wiki-drawer wiki-upload-drawer ${open ? 'is-open' : ''}`} onClick={onClose}>
    <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
      <div className="portal-drawer__head">
        <div>
          <span>문서 추가</span>
          <strong>Runbook 문서 업로드</strong>
        </div>
        <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
          <X />
        </button>
      </div>
      <div className="portal-drawer__body">
        <div
          className={`rag-dropzone ${dragActive ? 'is-active' : ''}`}
          onDragLeave={() => setDragActive(false)}
          onDragOver={(event) => {
            event.preventDefault();
            setDragActive(true);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragActive(false);
            handleUploadFiles(event.dataTransfer.files);
          }}
        >
          <Upload />
          <div>
            <strong>운영 지식으로 색인할 문서 선택</strong>
            <p>PDF, DOCX, MD, TXT, YAML, 로그 파일을 업로드할 수 있습니다.</p>
          </div>
          <label className="portal-button" htmlFor="wiki-upload-input">파일 선택</label>
          <input
            accept=".pdf,.doc,.docx,.md,.txt,.yaml,.yml,.json,.log"
            hidden
            id="wiki-upload-input"
            multiple
            onChange={(event) => {
              handleUploadFiles(event.target.files);
              event.target.value = '';
            }}
            type="file"
          />
        </div>
        <button className="wiki-advanced-toggle" onClick={() => setShowAdvancedSettings((value) => !value)} type="button">
          고급 설정 {showAdvancedSettings ? '접기' : '보기'}
        </button>
        {showAdvancedSettings && (
          <div className="rag-ingest-settings">
            <label>
              <span>컬렉션</span>
              <select onChange={(event) => setRagCollection(event.target.value)} value={ragCollection}>
                <option value="ocp-runbooks">ocp-runbooks</option>
                <option value="incident-rca">incident-rca</option>
                <option value="platform-policy">platform-policy</option>
              </select>
            </label>
            <label>
              <span>Chunk 크기</span>
              <select onChange={(event) => setRagChunkSize(event.target.value)} value={ragChunkSize}>
                <option value="600">600 tokens</option>
                <option value="900">900 tokens</option>
                <option value="1200">1200 tokens</option>
              </select>
            </label>
            <label>
              <span>검색 범위</span>
              <select defaultValue="ops">
                <option value="ops">운영팀 공개</option>
                <option value="private">업로드 사용자만</option>
                <option value="all">전체 포털</option>
              </select>
            </label>
          </div>
        )}
        <section className="wiki-drawer-section">
          <strong>업로드 대기열</strong>
          {uploadItems.length === 0 ? (
            <div className="wiki-index-compact">
              <article><span>최근 인덱싱 작업</span><strong>성공 {indexedCount} · 실패 0 · 대기 0</strong><small>마지막 성공 07. 03. 오전 09:20</small></article>
            </div>
          ) : (
            <div className="rag-upload-list">
              {uploadItems.map((item) => (
                <article key={item.id}>
                  <FileText />
                  <div>
                    <strong>{item.name}</strong>
                    <span>{item.type} · {item.size} · {item.collection} · 예상 chunk {item.chunks}</span>
                  </div>
                  <StatusBadge label={item.status} severity={uploadStatusSeverity(item.status)} />
                </article>
              ))}
            </div>
          )}
        </section>
      </div>
    </aside>
  </div>
);

const WikiDocDetailDrawer: React.FC<{
  activeDoc: KnowledgeDoc;
  onClose: () => void;
  open: boolean;
  searchResults: Array<{ doc: KnowledgeDoc; score: string; reason: string }>;
  setTestQuery: (value: string) => void;
  testQuery: string;
}> = ({ activeDoc, onClose, open, searchResults, setTestQuery, testQuery }) => (
  <div className={`portal-drawer wiki-drawer wiki-doc-detail-drawer ${open ? 'is-open' : ''}`} onClick={onClose}>
    <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
      <div className="portal-drawer__head">
        <div>
          <span>문서 상세</span>
          <strong>{activeDoc.title}</strong>
        </div>
        <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
          <X />
        </button>
      </div>
      <div className="portal-drawer__body">
        <article className="doc-preview">
          <div className="doc-preview__top">
            <StatusBadge label={activeDoc.status} severity={docStatusSeverity(activeDoc.status)} />
            <span>{activeDoc.category}</span>
          </div>
          <h2>{activeDoc.title}</h2>
          <p>{activeDoc.summary}</p>
          <div className="doc-readiness-grid">
            <article><span>검색 준비 상태</span><strong>{activeDoc.searchStatus}</strong></article>
            <article><span>RCA 연결</span><strong>{activeDoc.rcaLinks}건</strong></article>
            <article><span>마지막 검증일</span><strong>{activeDoc.verifiedAt}</strong></article>
            <article><span>문서 버전</span><strong>{activeDoc.version}</strong></article>
          </div>
          <div className="doc-section">
            <strong>적용 대상</strong>
            <div className="doc-tags">
              {activeDoc.targetScopes.map((tag) => <b key={tag}>{tag}</b>)}
            </div>
          </div>
          <div className="doc-section">
            <strong>연결 이슈</strong>
            <ul className="doc-linked-issues">
              {activeDoc.linkedIssues.map((issue) => <li key={issue}>{issue}</li>)}
            </ul>
          </div>
          <div className="doc-section">
            <strong>검색 키워드</strong>
            <div className="doc-tags is-muted">
              {activeDoc.keywords.map((tag) => <b key={tag}>{tag}</b>)}
            </div>
          </div>
          <ol className="checkpoint-list">
            {activeDoc.steps.map((step, index) => (
              <li key={step}><span>{String(index + 1).padStart(2, '0')}</span><p>{step}</p></li>
            ))}
          </ol>
          <footer>소유자 {activeDoc.owner} · 업데이트 {activeDoc.updatedAt}</footer>
        </article>
        <section className="wiki-drawer-section">
          <strong>검색 테스트</strong>
          <div className="wiki-search-test">
            <label className="portal-search">
              <Search />
              <input onChange={(event) => setTestQuery(event.target.value)} value={testQuery} />
            </label>
            <div className="wiki-search-results">
              {searchResults.map((result, index) => (
                <article key={result.doc.id}>
                  <strong>{index + 1}. {result.doc.title}</strong>
                  <span>점수 {result.score} · chunk {Math.min(result.doc.chunks, index + 3)} · {result.reason}</span>
                </article>
              ))}
            </div>
          </div>
        </section>
      </div>
    </aside>
  </div>
);

const WikiIndexDetailDrawer: React.FC<{
  indexedCount: number;
  onClose: () => void;
  open: boolean;
  pendingUploadCount: number;
  ragChunkSize: string;
  ragCollection: string;
  totalChunks: number;
}> = ({ indexedCount, onClose, open, pendingUploadCount, ragChunkSize, ragCollection, totalChunks }) => (
  <div className={`portal-drawer wiki-drawer ${open ? 'is-open' : ''}`} onClick={onClose}>
    <aside className="portal-drawer__panel" onClick={(event) => event.stopPropagation()}>
      <div className="portal-drawer__head">
        <div>
          <span>인덱싱 세부 상태</span>
          <strong>{ragCollection}</strong>
        </div>
        <button aria-label="닫기" className="portal-icon-btn" onClick={onClose} title="닫기" type="button">
          <X />
        </button>
      </div>
      <div className="portal-drawer__body">
        <div className="wiki-index-compact">
          <article><span>컬렉션</span><strong>{ragCollection}</strong><small>운영 Runbook 기본 컬렉션</small></article>
          <article><span>문서</span><strong>{indexedCount}개 색인</strong><small>{pendingUploadCount}개 대기</small></article>
          <article><span>청크</span><strong>{totalChunks}개</strong><small>{ragChunkSize} token 기준</small></article>
          <article><span>검색 상태</span><strong>검색 가능</strong><small>오류 0 · 마지막 색인 07. 03. 오전 09:20</small></article>
        </div>
        <section className="wiki-drawer-section">
          <strong>파이프라인</strong>
          <div className="rag-pipeline">
            {['업로드', '텍스트 추출', '청크 분리', '임베딩', '벡터 색인'].map((step, index) => (
              <article key={step}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{step}</strong>
              </article>
            ))}
          </div>
        </section>
      </div>
    </aside>
  </div>
);

const WikiDocsView: React.FC = () => {
  const [activeDocId, setActiveDocId] = React.useState(sampleKnowledgeDocs[0].id);
  const [query, setQuery] = React.useState('');
  const [category, setCategory] = React.useState('전체');
  const [ragCollection, setRagCollection] = React.useState('ocp-runbooks');
  const [ragChunkSize, setRagChunkSize] = React.useState('900');
  const [dragActive, setDragActive] = React.useState(false);
  const [uploadItems, setUploadItems] = React.useState<WikiUploadItem[]>([]);
  const [showAdvancedSettings, setShowAdvancedSettings] = React.useState(false);
  const [openDrawer, setOpenDrawer] = React.useState<'upload' | 'doc' | 'index' | null>(null);
  const [testQuery, setTestQuery] = React.useState('CrashLoopBackOff가 발생한 Pod를 어떻게 확인해?');
  const categories = ['전체', ...Array.from(new Set(sampleKnowledgeDocs.map((doc) => doc.category))), '검증 필요'];
  const docs = sampleKnowledgeDocs.filter((doc) => {
    const matchesCategory = category === '전체' || doc.category === category || (category === '검증 필요' && doc.status === '검증 필요');
    const text = `${doc.title} ${doc.summary} ${doc.tags.join(' ')} ${doc.keywords.join(' ')}`.toLowerCase();
    return matchesCategory && (!query.trim() || text.includes(query.trim().toLowerCase()));
  });
  const activeDoc = docs.find((doc) => doc.id === activeDocId) ?? docs[0] ?? sampleKnowledgeDocs[0];

  React.useEffect(() => {
    setActiveDocId((current) => (docs.some((doc) => doc.id === current) ? current : docs[0]?.id ?? sampleKnowledgeDocs[0].id));
  }, [docs]);

  const handleUploadFiles = React.useCallback((fileList: FileList | null) => {
    if (!fileList?.length) {
      return;
    }
    const nextItems = Array.from(fileList).map((file, index): WikiUploadItem => {
      const extension = file.name.includes('.') ? file.name.split('.').pop()?.toUpperCase() ?? 'FILE' : 'FILE';
      return {
        chunks: Math.max(1, Math.ceil(file.size / Math.max(1, Number(ragChunkSize) * 120))),
        collection: ragCollection,
        id: `${file.name}-${file.lastModified}-${index}`,
        name: file.name,
        size: formatUploadSize(file.size),
        status: '인덱싱 준비',
        type: extension,
        updatedAt: '방금 선택',
      };
    });
    setUploadItems((current) => [...nextItems, ...current]);
  }, [ragChunkSize, ragCollection]);

  const indexedCount = sampleKnowledgeDocs.length;
  const verifiedCount = sampleKnowledgeDocs.filter((doc) => doc.status === '검증됨').length;
  const reviewCount = sampleKnowledgeDocs.filter((doc) => doc.status === '검증 필요').length;
  const pendingUploadCount = uploadItems.length;
  const totalChunks = sampleKnowledgeDocs.reduce((total, doc) => total + doc.chunks, 0);
  const searchResults = buildDocSearchResults(sampleKnowledgeDocs, testQuery, activeDoc);

  return (
    <section className="wiki-workbench stack-view">
      <section className="wiki-knowledge-hero">
        <div>
          <span>운영 지식베이스</span>
          <h2>RCA와 AI 추천 액션에서 참조되는 Runbook 문서를 관리합니다.</h2>
          <p>{ragCollection} · 색인 {indexedCount} · 대기 {pendingUploadCount} · 이슈 0 · 마지막 색인 07. 03. 오전 09:20</p>
        </div>
        <div className="wiki-hero-actions">
          <button className="portal-button is-primary" onClick={() => setOpenDrawer('upload')} type="button">
            문서 추가
          </button>
          <button className="portal-button" onClick={() => setOpenDrawer('index')} type="button">
            인덱싱 세부 상태
          </button>
          <button className="portal-button" type="button">색인 재실행</button>
        </div>
        <div className="wiki-health-strip">
          <article><span>운영 문서</span><strong>{indexedCount}</strong></article>
          <article><span>검증 완료</span><strong>{verifiedCount}</strong></article>
          <article><span>검증 필요</span><strong>{reviewCount}</strong></article>
          <article><span>검색 chunk</span><strong>{totalChunks}</strong></article>
        </div>
      </section>

      <section className="wiki-layout wiki-layout--library">
        <Panel
          title="문서 라이브러리"
          action={
            <label className="portal-search">
              <Search />
              <input onChange={(event) => setQuery(event.target.value)} placeholder="문서, 대상, 키워드 검색" value={query} />
            </label>
          }
        >
          <div className="portal-tabs wiki-tabs">
            {categories.map((item) => (
              <button className={category === item ? 'is-active' : ''} key={item} onClick={() => setCategory(item)} type="button">
                {item}
              </button>
            ))}
          </div>
          <div className="doc-list">
            {docs.map((doc) => (
              <button
                className={doc.id === activeDoc.id ? 'is-selected' : ''}
                key={doc.id}
                onClick={() => {
                  setActiveDocId(doc.id);
                  setOpenDrawer('doc');
                }}
                type="button"
              >
                <div className="doc-list__head">
                  <strong>{doc.title}</strong>
                  <StatusBadge label={doc.status} severity={docStatusSeverity(doc.status)} />
                </div>
                <span>{doc.category} · {doc.targetScopes.slice(0, 3).join(' · ')}</span>
                <small>{doc.searchStatus} · {doc.chunks} 청크 · RCA 연결 {doc.rcaLinks}건 · 검증 {doc.verifiedAt}</small>
              </button>
            ))}
            {docs.length === 0 && <EmptyState label="조건에 맞는 문서가 없습니다." />}
          </div>
        </Panel>
      </section>

      <WikiUploadDrawer
        dragActive={dragActive}
        handleUploadFiles={handleUploadFiles}
        indexedCount={indexedCount}
        onClose={() => setOpenDrawer(null)}
        open={openDrawer === 'upload'}
        ragChunkSize={ragChunkSize}
        ragCollection={ragCollection}
        setDragActive={setDragActive}
        setRagChunkSize={setRagChunkSize}
        setRagCollection={setRagCollection}
        setShowAdvancedSettings={setShowAdvancedSettings}
        showAdvancedSettings={showAdvancedSettings}
        uploadItems={uploadItems}
      />
      <WikiDocDetailDrawer
        activeDoc={activeDoc}
        onClose={() => setOpenDrawer(null)}
        open={openDrawer === 'doc'}
        searchResults={searchResults}
        setTestQuery={setTestQuery}
        testQuery={testQuery}
      />
      <WikiIndexDetailDrawer
        indexedCount={indexedCount}
        onClose={() => setOpenDrawer(null)}
        open={openDrawer === 'index'}
        pendingUploadCount={pendingUploadCount}
        ragChunkSize={ragChunkSize}
        ragCollection={ragCollection}
        totalChunks={totalChunks}
      />
    </section>
  );
};

const ReportViewerDrawer: React.FC<{
  onClose: () => void;
  onDownloadArtifact: (report: GeneratedReport) => void;
  onDownloadHtml: (report: GeneratedReport) => void;
  onPrintPdf: (report: GeneratedReport) => void;
  report: GeneratedReport | null;
}> = ({ onClose, onDownloadArtifact, onDownloadHtml, onPrintPdf, report }) => (
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
                <button className="portal-button" onClick={() => onDownloadArtifact(report)} type="button">산출물 JSON</button>
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
    const text = stripPublicWebUrls(String(value ?? '')).replace(/\s+/g, ' ').trim();
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
        { label: 'OpenShift', value: displayOpenShiftVersion(summary.version.version) },
      ];
    }
    return [
      { label: '리소스 이슈', value: String(summary.resources?.issues ?? rows.length) },
      { label: '오퍼레이터 저하', value: String(summary.operators.degraded) },
      { label: 'OpenShift', value: displayOpenShiftVersion(summary.version.version) },
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

  const downloadJsonContent = (payload: unknown, filename: string) => {
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: 'application/json;charset=utf-8' });
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

  const createReportArtifact = (report: ReportItem, options: ReportBuildOptions): ReportArtifact => {
    const rows = reportIssueRows(report, options);
    const recommendations = reportRecommendations(report, rows, options);
    const records = status.spec.records;
    const ledgerEntries = buildLedgerEntries(actionRecords(status), records.auditRecords ?? [], { sample: false })
      .slice(-24)
      .map((entry) => ({
        action: ledgerActionLabel(entry.action),
        actor: entry.actor,
        artifact: entry.artifact,
        category: entry.category,
        gate: ledgerGateLabel(entry.gate),
        id: entry.id,
        phase: entry.phase,
        result: ledgerResultLabel(entry.result),
        target: ledgerTargetLabel(entry),
        time: entry.time,
        title: entry.title,
        variant: entry.variant,
      }));

    return {
      apiVersion: 'aiops.komsco/v1',
      kind: 'AIOpsReportArtifact',
      metadata: {
        cluster: clusterLabel(summary),
        dataWindow: options.dataWindowLabel,
        format: options.outputFormat,
        generatedAt: options.generatedAt,
        reportId: options.reportId,
        sourceSnapshotId: options.sourceSnapshotId,
        templateId: report.id,
      },
      spec: {
        actionsAndAudit: {
          actionProposals: records.actionProposals.length,
          approvalDecisions: records.approvalDecisions.length,
          auditRecords: records.auditRecords?.length ?? 0,
          executionRecords: records.executionRecords.length,
          ledgerEntries,
          sealedActionPlans: records.sealedActionPlans.length,
        },
        evidencePackage: {
          issue: report.id === 'rca-pack' && options.issue
            ? {
                category: options.issue.category,
                id: options.issue.id,
                severity: options.issue.severity,
                target: options.issue.target,
                title: compactReportText(options.issue.title, 120),
              }
            : undefined,
          rows,
        },
        executiveSummary: reportExecutiveSummary(report, rows, options),
        recommendations,
        reportJudgement: reportJudgement(report, rows, options),
        requiredData: report.requiredData,
        sections: options.sections,
        sourceStatus: {
          actionExecutorConfigured: status.spec.capabilities.actionExecutorConfigured,
          mutationsEnabled: status.spec.capabilities.mutationsEnabled,
          recordStoreEnabled: status.spec.capabilities.recordStoreEnabled,
        },
        title: report.title,
      },
    };
  };

  const createGeneratedReport = (report: ReportItem, format: ReportOutputFormat): GeneratedReport => {
    const generatedAt = new Date().toISOString();
    const options = currentReportBuildOptions(report, format, generatedAt);
    const html = reportHtml(report, options);
    const artifact = createReportArtifact(report, options);

    return {
      artifact,
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

  const downloadGeneratedArtifact = (report: GeneratedReport) => {
    downloadJsonContent(report.artifact, `${report.reportId}-artifact.json`);
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
                <StatusBadge label={report.status} severity={reportStatusSeverity(report.status)} />
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
                    <div className="report-history-actions">
                      <button className="portal-button" onClick={() => setOpenReport(item)} type="button">열기</button>
                      <button className="portal-button" onClick={() => downloadGeneratedArtifact(item)} type="button">JSON</button>
                    </div>
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
            <article><span>산출물 JSON</span><strong>보고서 메타데이터, 증거 패키지, 조치/감사 요약 포함</strong></article>
            <article><span>HTML</span><strong>다운로드 가능</strong></article>
            <article><span>PDF</span><strong>브라우저 저장 PDF 지원</strong></article>
            <article><span>DOCX</span><strong>준비 중</strong></article>
          </div>
        )}
      </Panel>

      <ReportViewerDrawer
        onClose={() => setOpenReport(null)}
        onDownloadArtifact={downloadGeneratedArtifact}
        onDownloadHtml={downloadGeneratedReport}
        onPrintPdf={printGeneratedReport}
        report={openReport}
      />
    </section>
  );
};

const SettingsView: React.FC<{ status: AiopsRuntimeStatus; summary: ClusterSummary }> = ({ status, summary }) => {
  const capabilities = status.spec.capabilities;
  const [policyMode, setPolicyMode] = React.useState(capabilities.mutationsEnabled ? '승인 후 실행' : '읽기/증거 수집');
  const [notifyOps, setNotifyOps] = React.useState(true);
  const [notifyAudit, setNotifyAudit] = React.useState(false);

  return (
    <section className="settings-workbench stack-view">
      <section className="sample-banner is-config">
        <strong>화면 설정</strong>
        <span>현재 설정 화면은 포털에서 정책과 표시 옵션을 확인하는 UI입니다.</span>
      </section>
      <section className="settings-grid">
        <Panel title="게이트웨이 연결">
          <div className="settings-form">
            <label><span>API URL</span><input readOnly value={displayApiEndpoint(summary.apiUrl)} /></label>
            <label><span>클러스터</span><input readOnly value={clusterLabel(summary)} /></label>
            <label><span>상태</span><input readOnly value={summary.healthScore >= 90 ? '정상' : '확인 필요'} /></label>
          </div>
        </Panel>
        <Panel title="승인/실행 정책">
          <div className="settings-form">
            <label>
              <span>정책 모드</span>
              <select onChange={(event) => setPolicyMode(event.target.value)} value={policyMode}>
                <option>읽기/증거 수집</option>
                <option>승인 후 실행</option>
                <option>수동 승인 전용</option>
              </select>
            </label>
            <div className="capability-list">
              <span>변경 실행 <strong>{capabilities.mutationsEnabled ? '허용' : '차단'}</strong></span>
              <span>조치 실행기 <strong>{capabilities.actionExecutorConfigured ? '설정됨' : '미설정'}</strong></span>
              <span>감사 원장 <strong>{capabilities.recordStoreEnabled ? '켜짐' : '꺼짐'}</strong></span>
            </div>
          </div>
        </Panel>
        <Panel title="알림 채널">
          <div className="toggle-list">
            <label><input checked={notifyOps} onChange={(event) => setNotifyOps(event.target.checked)} type="checkbox" /> 운영 채널 알림</label>
            <label><input checked={notifyAudit} onChange={(event) => setNotifyAudit(event.target.checked)} type="checkbox" /> 감사 채널 알림</label>
            <label><input checked readOnly type="checkbox" /> 포털 배너 알림</label>
          </div>
        </Panel>
        <Panel title="데이터 보존">
          <div className="settings-form">
            <label><span>감사 ConfigMap</span><input readOnly value={capabilities.recordStoreConfigMap ?? '미설정'} /></label>
            <label><span>이벤트 폴링</span><input readOnly value="30초" /></label>
            <label><span>샘플 데이터</span><input readOnly value="문서/보고서 화면에만 표시" /></label>
          </div>
        </Panel>
      </section>
    </section>
  );
};

const AppContent: React.FC<{
  activeView: NavView;
  clock: string;
  events: AiopsEventFeed;
  onAssistantLaunch?: AssistantLaunchHandler;
  onNavigate: (view: NavView) => void;
  onOpenItem: (item: QueueItem) => void;
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
}> = ({ activeView, clock, events, onAssistantLaunch, onNavigate, onOpenItem, status, summary }) => {
  if (activeView === 'dashboard') {
    return (
      <DashboardView
        clock={clock}
        events={events}
        onAssistantLaunch={onAssistantLaunch}
        onNavigate={onNavigate}
        onOpenItem={onOpenItem}
        status={status}
        summary={summary}
      />
    );
  }
  if (activeView === 'executions') {
    return <ExecutionRecordsView onNavigate={onNavigate} status={status} />;
  }
  if (activeView === 'rca') {
    return (
      <RcaView
        onAssistantLaunch={onAssistantLaunch}
        onNavigate={onNavigate}
        onOpenItem={onOpenItem}
        status={status}
        summary={summary}
      />
    );
  }
  if (activeView === 'service-map') {
    return <ServiceMapView onNavigate={onNavigate} summary={summary} />;
  }
  if (activeView === 'endpoints') {
    return <ResourceInventoryView onAssistantLaunch={onAssistantLaunch} summary={summary} />;
  }
  if (activeView === 'alerts') {
    return (
      <AlertsEventsView
        events={events}
        onAssistantLaunch={onAssistantLaunch}
        onOpenItem={onOpenItem}
        status={status}
        summary={summary}
      />
    );
  }
  if (activeView === 'wiki') {
    return <WikiDocsView />;
  }
  if (activeView === 'reports') {
    return <ReportsView status={status} summary={summary} />;
  }
  return <SettingsView status={status} summary={summary} />;
};

const ClusterSignalStrip: React.FC<{
  error: string;
  lastSnapshot: string;
  onNavigate: (view: NavView) => void;
  onRefresh: () => Promise<void>;
}> = ({ error, lastSnapshot, onNavigate, onRefresh }) => {
  const errorLine = error.split('\n').find(Boolean) ?? '게이트웨이 연결 실패';

  return (
    <div className="cluster-signal-strip">
      <span className="cluster-signal-strip__dot" aria-hidden="true" />
      <div>
        <strong>게이트웨이 신호 저하</strong>
        <span>실시간 클러스터 텔레메트리를 사용할 수 없어 마지막 수집 스냅샷을 표시합니다 · {lastSnapshot}</span>
        <small>{errorLine}</small>
      </div>
      <button onClick={() => void onRefresh()} type="button">
        연결 재시도
      </button>
      <button onClick={() => onNavigate('alerts')} type="button">
        게이트웨이 이벤트
      </button>
    </div>
  );
};

export const App: React.FC = () => {
  const clock = useLiveClock();
  const runtime = usePortalRuntime();
  const [activeView, setActiveView] = React.useState<NavView>(() => viewFromLocation());
  const [drawerItem, setDrawerItem] = React.useState<QueueItem | null>(null);
  const navigateToView = React.useCallback((view: NavView) => {
    if (activeView === view && viewFromLocation() === view) {
      return;
    }

    setActiveView((current) => (current === view ? current : view));
    setDrawerItem(null);

    const nextPath = standaloneRouteByView[view] ?? standaloneRouteByView.dashboard;
    if (window.location.pathname !== nextPath || window.location.hash) {
      window.history.pushState({ view }, '', nextPath);
    }
  }, [activeView]);

  React.useEffect(() => {
    const handleHistoryChange = () => {
      setActiveView(viewFromLocation());
      setDrawerItem(null);
    };

    window.addEventListener('popstate', handleHistoryChange);
    window.addEventListener('hashchange', handleHistoryChange);
    return () => {
      window.removeEventListener('popstate', handleHistoryChange);
      window.removeEventListener('hashchange', handleHistoryChange);
    };
  }, []);

  return (
    <div className="aiops-console-portal portal-shell">
      <Sidebar
        activeView={activeView}
        clock={clock}
        setActiveView={navigateToView}
        summary={runtime.summary}
      />
      <main className="portal-main">
        <Topbar
          activeView={activeView}
          alarmCount={aiopsAlarmCount(runtime.events)}
          isLive={runtime.isLive}
          loading={runtime.loading}
          onNavigate={navigateToView}
          onRefresh={runtime.refresh}
          summary={runtime.summary}
        />
        <section className="portal-content">
          {runtime.error && (
            <ClusterSignalStrip
              error={runtime.error}
              lastSnapshot={formatTime(runtime.summary.updatedAt)}
              onNavigate={navigateToView}
              onRefresh={runtime.refresh}
            />
          )}
          <AppContent
            activeView={activeView}
            clock={clock}
            events={runtime.events}
            onNavigate={navigateToView}
            onOpenItem={setDrawerItem}
            status={runtime.status}
            summary={runtime.summary}
          />
        </section>
      </main>
      <DetailDrawer
        clusterName={clusterLabel(runtime.summary)}
        item={drawerItem}
        onClose={() => setDrawerItem(null)}
        onNavigate={navigateToView}
      />
    </div>
  );
};

export const PortalEmbeddedPage: React.FC<{ view: NavView }> = ({ view }) => {
  const clock = useLiveClock();
  const runtime = usePortalRuntime();
  const [assistantDraftPrompt, setAssistantDraftPrompt] = React.useState<AssistantDraftPrompt | undefined>();
  const [drawerItem, setDrawerItem] = React.useState<QueueItem | null>(null);

  const navigateToView = React.useCallback((nextView: NavView) => {
    setDrawerItem(null);
    const nextRoute = standaloneRouteByView[nextView] ?? standaloneRouteByView.dashboard;
    if (window.location.pathname !== nextRoute) {
      window.location.assign(nextRoute);
    }
  }, []);

  React.useEffect(() => {
    setDrawerItem(null);
  }, [view]);

  const launchAssistant = React.useCallback<AssistantLaunchHandler>(
    ({ context, executionMode, taskMode = 'troubleshooting' }) => {
      setAssistantDraftPrompt({
        id: `aiops-${context.source}-${Date.now().toString(36)}`,
        pageContext: {
          aiopsExecutionMode: executionMode,
          aiopsLaunchContext: context,
          actionType: context.actionType,
          evidenceRefs: context.evidenceRefs,
          kind: context.kind,
          name: context.name,
          namespace: context.namespace,
          reason: context.reason,
          severity: context.severity,
          source: context.source,
        },
        prompt: context.promptDraft,
        taskMode,
      });
    },
    [],
  );

  return (
    <div className="aiops-console-portal portal-shell portal-shell--embedded">
      <main className="portal-main">
        <Topbar
          activeView={view}
          alarmCount={aiopsAlarmCount(runtime.events)}
          isLive={runtime.isLive}
          loading={runtime.loading}
          onNavigate={navigateToView}
          onRefresh={runtime.refresh}
          summary={runtime.summary}
        />
        <section className="portal-content">
          {runtime.error && (
            <ClusterSignalStrip
              error={runtime.error}
              lastSnapshot={formatTime(runtime.summary.updatedAt)}
              onNavigate={navigateToView}
              onRefresh={runtime.refresh}
            />
          )}
          <AppContent
            activeView={view}
            clock={clock}
            events={runtime.events}
            onAssistantLaunch={launchAssistant}
            onNavigate={navigateToView}
            onOpenItem={setDrawerItem}
            status={runtime.status}
            summary={runtime.summary}
          />
        </section>
      </main>
      <DetailDrawer
        clusterName={clusterLabel(runtime.summary)}
        item={drawerItem}
        onAssistantLaunch={launchAssistant}
        onClose={() => setDrawerItem(null)}
        onNavigate={navigateToView}
      />
      <AssistantLauncher draftPrompt={assistantDraftPrompt} onRunComplete={runtime.refresh} />
    </div>
  );
};
