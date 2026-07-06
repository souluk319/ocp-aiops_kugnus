// v1 src/App.tsx에서 복사한 파생 헬퍼/샘플 데이터 — ver.2 목업 전용 사본.
// 원본(App.tsx)은 export하지 않으므로 여기서 독립적으로 유지한다.
import type {
  ActivityItem,
  AiopsEventFeed,
  AiopsEventItem,
  AiopsRecord,
  AiopsRuntimeStatus,
  AlertItem,
  ClusterSummary,
  Endpoint,
  QueueItem,
  ScopeItem,
  Severity,
} from '../../types';

export const mockExecutionRecords: AiopsRecord[] = [
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

export const mockAuditRecords: AiopsRecord[] = [
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

export const sampleRcaQueues: QueueItem[] = [
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

export type KnowledgeDoc = {
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

export type WikiUploadItem = {
  chunks: number;
  collection: string;
  id: string;
  name: string;
  size: string;
  status: '업로드 대기' | '인덱싱 준비' | '색인됨';
  type: string;
  updatedAt: string;
};

export const sampleKnowledgeDocs: KnowledgeDoc[] = [
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

export const formatUploadSize = (size: number): string => {
  if (size >= 1024 * 1024) {
    return `${(size / 1024 / 1024).toFixed(1)} MB`;
  }
  if (size >= 1024) {
    return `${Math.ceil(size / 1024)} KB`;
  }
  return `${size} B`;
};

export const uploadStatusSeverity = (status: WikiUploadItem['status']): Severity =>
  status === '색인됨' ? 'ok' : 'warn';

export const docStatusSeverity = (status: KnowledgeDoc['status']): Severity =>
  status === '검증됨' ? 'ok' : status === '초안' ? 'warn' : 'risk';

export const buildDocSearchResults = (docs: KnowledgeDoc[], query: string, activeDoc: KnowledgeDoc): Array<{ doc: KnowledgeDoc; score: string; reason: string }> => {
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

export const endpointPageSizeOptions = [10, 25, 50];
export const eventInboxPageSizeOptions = [10, 25, 50];

export const aiopsAlarmCount = (events: AiopsEventFeed): number =>
  events.spec.items.filter((item) => item.severity === 'risk' || item.severity === 'warn').length;

export const compactCount = (value: number): string => (value > 99 ? '99+' : String(value));

export const formatTime = (value?: string): string => {
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

export const asObject = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : {};

export const textValue = (value: unknown, fallback = '-'): string => {
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

export const localizeTelemetryText = (value: string): string =>
  value
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

export const actionRecords = (status: AiopsRuntimeStatus): AiopsRecord[] => [
  ...status.spec.records.actionProposals,
  ...status.spec.records.sealedActionPlans,
  ...status.spec.records.approvalDecisions,
  ...status.spec.records.executionRecords,
];

export const recordPhase = (record: AiopsRecord): string => {
  const spec = asObject(record.spec);
  const status = asObject(spec.status);
  const approvalDecision = asObject(spec.approvalDecision);
  const mutationOutcome = asObject(spec.mutationOutcome);

  return textValue(
    status.phase ?? approvalDecision.status ?? mutationOutcome.status ?? spec.action,
    'recorded',
  );
};

export const recordTarget = (record: AiopsRecord): string => {
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

export const recordKindLabel = (kind?: string): string => {
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

export const recordTone = (record: AiopsRecord, variant: 'audit' | 'action' = 'action'): ActivityItem['tone'] => {
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

export type LedgerEntry = {
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

export const targetProjection = (record: AiopsRecord): { kind: string; name: string; namespace: string; target: string } => {
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

export const ledgerCategory = (record: AiopsRecord, variant: 'action' | 'audit'): LedgerEntry['category'] => {
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

export const ledgerPhase = (entry: Pick<LedgerEntry, 'category'>, record: AiopsRecord, variant: 'action' | 'audit'): string => {
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

export const buildLedgerEntries = (
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

export const runWindowLabel = (entries: LedgerEntry[]): string => {
  if (entries.length === 0) {
    return '-';
  }
  const first = formatTime(entries[0].time);
  const last = formatTime(entries[entries.length - 1].time);
  return first === last ? first : `${first} - ${last}`;
};

export const ledgerActionLabel = (value: string): string => {
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

export const ledgerGateLabel = (value: string): string => {
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

export const ledgerKindLabel = (value: string): string => {
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

export const resourceNameLabel = (id: string, name: string, kind: string): string => {
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

export const ledgerTargetLabel = (entry: Pick<LedgerEntry, 'kind' | 'name' | 'namespace' | 'target'>): string => {
  const parts = [
    entry.namespace !== '-' ? entry.namespace : '',
    entry.kind !== '-' ? ledgerKindLabel(entry.kind) : '',
    entry.name !== '-' ? entry.name : '',
  ].filter(Boolean);

  return parts.length > 0 ? parts.join(' / ') : entry.target;
};

export const ledgerResultLabel = (value: string): string => {
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

export const mutationStatusLabel = (value: string): string => {
  const labels: Record<string, string> = {
    Blocked: '차단됨',
    Executed: '실행됨',
    'Not executed': '미실행',
    'Waiting approval': '승인 대기',
  };
  return labels[value] ?? value;
};

export const clusterLabel = (summary: ClusterSummary, error = ''): string => {
  if (!summary.apiUrl) {
    if (isOpenShiftAuthError(error)) {
      return 'OpenShift 인증 필요';
    }
    return 'OpenShift 상태 확인 필요';
  }

  try {
    return new URL(summary.apiUrl).hostname;
  } catch {
    return summary.apiUrl;
  }
};

export const resourceKeywords: Record<string, string[]> = {
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

export const pressureLabels = (pressures: ClusterSummary['nodes']['items'][number]['pressures']): string[] => {
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

export const nodeSeverity = (node: ClusterSummary['nodes']['items'][number]): Severity => {
  if (!node.ready) {
    return 'risk';
  }

  return pressureLabels(node.pressures).length > 0 ? 'warn' : 'ok';
};

export const operatorSeverity = (operator: ClusterSummary['operators']['issues'][number]): Severity => {
  if (!operator.available || operator.degraded) {
    return 'risk';
  }

  return operator.progressing ? 'warn' : 'ok';
};

export const formatCpu = (value?: string): string => {
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

export const formatMemory = (value?: string): string => {
  if (!value) {
    return '-';
  }

  if (value.endsWith('Ki')) {
    const gib = Number(value.slice(0, -2)) / 1024 / 1024;
    return Number.isFinite(gib) ? `${gib.toFixed(1)} GiB` : value;
  }

  return value;
};

export const aiopsWorkloadItems = (summary: ClusterSummary) => [
  ...(summary.aiopsWorkloads?.deployments ?? []),
  ...(summary.aiopsWorkloads?.daemonsets ?? []),
];

export const aiopsWorkloadNames = (summary: ClusterSummary, limit = 3): string => {
  const workloads = aiopsWorkloadItems(summary);
  const names = workloads.slice(0, limit).map((workload) => `${workload.namespace}/${workload.name}`);
  const extra = workloads.length - names.length;
  return extra > 0 ? `${names.join(', ')} 외 ${extra}` : names.join(', ');
};

export const buildScopes = (summary: ClusterSummary, status: AiopsRuntimeStatus): ScopeItem[] => {
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
      detail: `OCP ${summary.version.version ?? '-'} · API ${summary.apiUrl ?? '-'}`,
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

export const scopeDetailRows = (
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
    { label: 'API', value: summary.apiUrl ?? '-' },
    { label: 'OpenShift', value: summary.version.version ?? '-' },
    { label: '업데이트', value: formatTime(summary.updatedAt) },
  ];
};

export const buildQueues = (summary: ClusterSummary, status: AiopsRuntimeStatus): QueueItem[] => {
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
          `os ${node.osImage ?? '-'}`,
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
              `현재 ${summary.version.version ?? '-'}`,
              summary.version.availableUpdates?.length
                ? `추천 업데이트 ${summary.version.availableUpdates.join(', ')}`
                : '추천 업데이트 확인됨',
              summary.version.upgradeableReason ?? 'Upgradeable=False',
            ].join(' · '),
            evidence: [
              `current ${summary.version.version ?? '-'}`,
              `recommended updates ${summary.version.availableUpdates?.join(', ') || '-'}`,
              `conditional updates ${summary.version.conditionalUpdates?.join(', ') || '-'}`,
              `reason ${summary.version.upgradeableReason ?? 'Upgradeable=False'}`,
              summary.version.upgradeableMessage ?? 'ClusterVersion가 updateAvailable=true를 보고했습니다.',
            ],
            source: 'OpenShift ClusterVersion API',
            target: `OpenShift ${summary.version.version ?? '-'}`,
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

export const buildAlerts = (summary: ClusterSummary, status: AiopsRuntimeStatus): AlertItem[] =>
  buildQueues(summary, status).map((item) => ({
    id: `alert-${item.id}`,
    title: item.title,
    target: localizeTelemetryText(item.detail),
    severity: item.severity,
    time: formatTime(summary.updatedAt),
  }));

export const buildEndpoints = (summary: ClusterSummary): Endpoint[] => {
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
    path: `${node.osImage ?? '-'} / ${node.kubeletVersion ?? '-'}`,
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
          name: `OpenShift ${summary.version.version}`,
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

export const eventTone = (event: AiopsEventItem): ActivityItem['tone'] => {
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

export const eventActivityDetail = (event: AiopsEventItem): string =>
  [
    localizeTelemetryText(event.detail),
    sourceLabel(event.source),
    event.namespace ? `네임스페이스=${event.namespace}` : '',
  ]
    .filter(Boolean)
    .join(' · ');

export const buildActivities = (
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
      detail: `${summary.version.version ?? '-'} · ${summary.version.upgradeableReason ?? '사전 확인 필요'}`,
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

export type AlertEventRow = {
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

export type EventInboxGroup = {
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

export const sampleAlertEvents: AlertEventRow[] = [
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

export const buildAlertEventRows = (
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

export const eventSeverityRank: Record<Severity, number> = {
  ok: 0,
  warn: 1,
  risk: 2,
};

export const eventReason = (row: AlertEventRow): string => {
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

export const eventObjectKind = (row: AlertEventRow): string => {
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

export const isNormalLifecycleEvent = (row: AlertEventRow): boolean =>
  row.severity === 'ok' || /^(Pulled|Created|Scheduled|AddedInterface)$/i.test(eventReason(row));

export const relatedIssueForEvent = (group: Pick<EventInboxGroup, 'kind' | 'reason' | 'target'>, queues: QueueItem[]): QueueItem | undefined => {
  const haystack = `${group.kind} ${group.reason} ${group.target}`.toLowerCase();
  if (/pod|backoff|probe|failed|readiness/.test(haystack)) {
    return queues.find(isPodIssue) ?? queues.find(isDerivedWorkloadIssue);
  }
  if (/build/.test(haystack)) {
    return queues.find((item) => /build|deployment|디플로이먼트/i.test(`${item.title} ${item.detail}`));
  }
  return queues.find((item) => item.severity === 'risk') ?? queues[0];
};

export const buildEventInboxGroups = (rows: AlertEventRow[], queues: QueueItem[]): EventInboxGroup[] => {
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

export const eventGroupFromRow = (row: AlertEventRow, queues: QueueItem[]): EventInboxGroup => {
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

export const eventCommands = (group: EventInboxGroup): Array<{ command: string; title: string }> => {
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

export const reportHealthLabel = (summary: ClusterSummary): string => {
  if (summary.healthScore >= 90) {
    return '정상';
  }
  if (summary.healthScore >= 70) {
    return '주의';
  }
  return '위험';
};

export type RcaQueueGroup = {
  id: string;
  items: QueueItem[];
  title: string;
};

export type RcaEvidencePackRow = {
  collector: string;
  command: string;
  field: string;
  freshness: string;
  source: string;
  status: 'attention' | 'collected' | 'excluded' | 'normal';
  value: string;
};

export type RcaFindingRow = {
  detail: string;
  kicker: string;
  meta: string;
  title: string;
  tone: 'primary' | 'supporting' | 'validation';
};

export type RcaRunbookGate = {
  command: string;
  detail: string;
  gate: string;
  id: string;
  status: string;
  title: string;
  tone: 'ok' | 'warn' | 'risk';
};

export type RcaIssueType =
  | 'WORKLOAD_PODS'
  | 'WORKLOAD_DERIVED'
  | 'PLATFORM_UPDATE'
  | 'CLUSTER_OPERATOR'
  | 'NODE_HEALTH'
  | 'AIOPS_CONTROL'
  | 'OTHER';

export type PodRcaSummary = {
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

export type RcaCaseHeaderModel = {
  baseline: string;
  caseState: string;
  family: string;
  finding: string;
  issueLine: string;
  metrics: Array<{ label: string; value: string }>;
  scope: string;
  title: string;
};

export type RcaCommandBundleItem = {
  command: string;
  title: string;
};

export type RcaTimelineItem = {
  detail: string;
  title: string;
};

export type TopologyNodeKey =
  | 'daemonsets'
  | 'deployments'
  | 'nodes'
  | 'persistentvolumeclaims'
  | 'pods'
  | 'replicasets'
  | 'routes'
  | 'services'
  | 'statefulsets';

export type TopologyEdgeMode = 'all' | 'ownership' | 'runtime' | 'traffic';

export type TraceInspectorModel = {
  commands: Array<{ command: string; title: string }>;
  focus: string;
  insight: string;
  reasons: Array<{ detail: string; label: string }>;
  severity: Severity;
  signals: Array<{ label: string; tone?: Severity; value: string }>;
  title: string;
  trace: string;
};

export const isClusterUpdateIssue = (item: QueueItem): boolean =>
  item.category === '클러스터 버전' || /clusterversion|cluster update|upgradeable|업데이트 사전|ocp 업데이트/i.test(`${item.id} ${item.title} ${item.target ?? ''}`);

export const isPodIssue = (item: QueueItem | undefined): boolean =>
  Boolean(item && /(^resource-pods$)|pod|pods|파드/i.test(`${item.id} ${item.title} ${item.target ?? ''}`));

export const isDerivedWorkloadIssue = (item: QueueItem | undefined): boolean =>
  Boolean(item && /deployment|디플로이먼트|replicaset|레플리카셋|statefulset|daemonset/i.test(`${item.id} ${item.title} ${item.target ?? ''}`));

export const rcaIssueType = (item: QueueItem | undefined): RcaIssueType => {
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

export const resourceById = (summary: ClusterSummary, id: string) =>
  (summary.resources?.items ?? []).find((resource) => resource.id === id);

export const detailNumber = (detail: string | undefined, label: string): number => {
  if (!detail) {
    return 0;
  }
  const match = detail.match(new RegExp(`(?:^|[·,])\\s*${label}\\s+([0-9]+)`, 'i'));
  return match ? Number(match[1]) : 0;
};

export const buildPodRcaSummary = (summary: ClusterSummary): PodRcaSummary => {
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

export const podMetricLine = (podSummary: PodRcaSummary): string =>
  `실행중 ${podSummary.running} · 준비 ${podSummary.ready} · 대기 ${podSummary.pending} · 실패 ${podSummary.failed} · 완료 ${podSummary.completed} · 재시작 ${podSummary.restartsTotal}`;

export const podIssueFormula = (podSummary: PodRcaSummary): string =>
  `이슈 후보 ${podSummary.issueCandidates} = 대기 ${podSummary.pending} + 실패 ${podSummary.failed} + 실행중 미준비 ${podSummary.runningNotReady}`;

export const buildRcaQueueGroups = (queues: QueueItem[]): RcaQueueGroup[] => {
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

export const defaultRcaSelection = (queues: QueueItem[]): string =>
  queues.find(isPodIssue)?.id ?? queues.find((item) => item.severity === 'risk')?.id ?? queues.find(isClusterUpdateIssue)?.id ?? queues[0]?.id ?? '';

export const rcaCaseId = (item: QueueItem | undefined, index: number): string =>
  item && isClusterUpdateIssue(item) ? 'RCA-20250703-004' : `RCA-20250703-${String(index + 1).padStart(3, '0')}`;

export const rcaReason = (summary: ClusterSummary, item?: QueueItem): string => {
  const reasonEvidence = item ? evidenceRows(item).find((row) => row.label === 'reason')?.value : '';
  return summary.version.upgradeableReason ?? reasonEvidence ?? 'AdminAckRequired';
};

export const rcaCurrentVersion = (summary: ClusterSummary, item?: QueueItem): string => {
  const current = item ? evidenceRows(item).find((row) => row.label === 'current')?.value : '';
  return summary.version.version ?? current ?? '-';
};

export const rcaAvailableUpdates = (summary: ClusterSummary, item?: QueueItem): string => {
  const evidence = item ? evidenceRows(item).find((row) => row.label === 'recommended updates')?.value : '';
  return summary.version.availableUpdates?.join(' · ') || evidence || '-';
};

export const rcaConditionalUpdates = (summary: ClusterSummary, item?: QueueItem): string => {
  const evidence = item ? evidenceRows(item).find((row) => row.label === 'conditional updates')?.value : '';
  return summary.version.conditionalUpdates?.join(' · ') || evidence || '-';
};

export const buildRcaCaseHeader = (
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
      baseline: `클러스터 기준: OCP ${summary.version.version ?? '-'}`,
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
    baseline: `클러스터 기준: OCP ${summary.version.version ?? '-'}`,
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

export const rcaQueueBadgeLabel = (item: QueueItem): string => {
  if (isDerivedWorkloadIssue(item)) {
    return '파생';
  }
  return item.severity === 'risk' ? '높음' : '중간';
};

export const rcaQueueDetail = (summary: ClusterSummary, item: QueueItem, podSummary: PodRcaSummary): string => {
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

export const buildRcaFindings = (summary: ClusterSummary, item: QueueItem | undefined, podSummary: PodRcaSummary): RcaFindingRow[] => {
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

export const buildRcaEvidencePack = (
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

export const buildRcaRunbookGates = (
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

export const buildRcaCommandBundle = (
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

export const buildRcaTimeline = (
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

export const isOpenShiftAuthError = (error: string): boolean =>
  /Unauthorized|Missing OpenShift bearer token|openshift_user_auth_failed|사용자 인증|인증이 만료/.test(
    error,
  );

export const portalConnectionLabel = (isLive: boolean, error: string): string => {
  if (isLive) {
    return '게이트웨이 연결됨';
  }
  if (isOpenShiftAuthError(error)) {
    return 'OpenShift 인증 필요';
  }
  return '게이트웨이 연결 확인 필요';
};

export const resourceNodeDetail = (
  resource: NonNullable<ClusterSummary['resources']>['items'][number] | undefined,
  fallback: string,
): string => (resource ? `${resource.score} · ${resource.issues > 0 ? `이슈 ${resource.issues}건` : '정상'}` : fallback);

export const resourceNodeSeverity = (
  resource: NonNullable<ClusterSummary['resources']>['items'][number] | undefined,
  fallback: Severity = 'ok',
): Severity => resource?.severity ?? fallback;

export const topologyNodeLabel: Record<TopologyNodeKey, string> = {
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

export const topologyPrimarySignals = (summary: ClusterSummary): number =>
  resourceById(summary, 'pods')?.issues ?? 0;

export const topologyDerivedSignals = (summary: ClusterSummary): number =>
  (resourceById(summary, 'deployments')?.issues ?? 0) + (resourceById(summary, 'replicasets')?.issues ?? 0);

export const topologyOtherSignals = (summary: ClusterSummary): number =>
  Math.max(0, (summary.resources?.issues ?? 0) - topologyPrimarySignals(summary) - topologyDerivedSignals(summary));

export const topologyNodeSummary = (
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

export const topologyTracePath = (key: TopologyNodeKey): string => {
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

export const buildTraceInspector = (summary: ClusterSummary, key: TopologyNodeKey): TraceInspectorModel => {
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

export type ResourceSummaryItem = NonNullable<ClusterSummary['resources']>['items'][number];

export type ImpactSignalRow = {
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

export type ImpactSignalSection = {
  id: 'primary' | 'derived' | 'cleared';
  label: string;
  rows: ImpactSignalRow[];
};

export const resourceReadyText = (resource: ResourceSummaryItem | undefined): string =>
  resource ? String(resource.ready) : '-';

export const buildDerivedImpactRow = (resource: ResourceSummaryItem): ImpactSignalRow => {
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

export const buildImpactSignalStack = (summary: ClusterSummary): ImpactSignalSection[] => {
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

export const issueSeverityLabel: Record<QueueItem['severity'], string> = {
  risk: '위험',
  warn: '주의',
};

export const issueNextSteps = (item: QueueItem): string[] => {
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

export const incidentLevelLabel: Record<QueueItem['severity'], string> = {
  risk: '심각 신호',
  warn: '주의 신호',
};

export const evidencePrefixes = [
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

export const evidenceLabel = (label: string): string => {
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

export const evidenceStatusLabel = (status: 'attention' | 'collected' | 'excluded' | 'normal'): string => {
  const labels: Record<typeof status, string> = {
    attention: '확인 필요',
    collected: '수집됨',
    excluded: '제외',
    normal: '정상',
  };
  return labels[status];
};

export const splitEvidenceLine = (line: string): { label: string; value: string } => {
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

export const evidenceStatus = (label: string, value: string): 'attention' | 'collected' | 'normal' => {
  const combined = `${label} ${value}`.toLowerCase();
  if (/(issue|failed|pending|degraded|notready|unavailable|blocked|adminack|required|pressure)/.test(combined)) {
    return 'attention';
  }
  if (/(ready|available|current|collected|true|normal|succeeded)/.test(combined)) {
    return 'normal';
  }
  return 'collected';
};

export const evidenceRows = (item: QueueItem): Array<{ label: string; status: 'attention' | 'collected' | 'normal'; value: string }> =>
  item.evidence.map((line) => {
    const parsed = splitEvidenceLine(line);
    return {
      ...parsed,
      status: evidenceStatus(parsed.label, parsed.value),
    };
  });

export const issueMetrics = (item: QueueItem): string[] =>
  item.detail
    .split(' · ')
    .map((metric) => metric.trim())
    .filter(Boolean)
    .slice(0, 6);

export const affectedScope = (item: QueueItem): string => {
  const issueEvidence = evidenceRows(item).find((row) => row.label === 'issues');
  if (issueEvidence?.value && issueEvidence.value !== '0') {
    return `이슈 후보 ${issueEvidence.value}건`;
  }

  const failedMetric = issueMetrics(item).find((metric) => /failed|pending|notready|unavailable|issues/i.test(metric));
  return failedMetric ?? issueSeverityLabel[item.severity];
};

export const impactRows = (item: QueueItem): Array<{ label: string; value: string }> => [
  { label: '리소스', value: item.target ?? item.title },
  { label: '분류', value: item.category ?? '운영 이슈' },
  { label: '데이터 소스', value: item.source ?? '게이트웨이 요약' },
  { label: '스냅샷', value: item.updatedAt ?? '-' },
  { label: '영향 범위', value: affectedScope(item) },
];

export const commandResourceLabel = (item: QueueItem): string => {
  if (item.target) {
    return `${item.target} 보기`;
  }
  if (item.category === '리소스') {
    return '리소스 보기';
  }
  return '관련 리소스 보기';
};

export const queueMetaItems = (item: QueueItem): string[] =>
  [
    item.category ?? '운영 이슈',
    item.target ? `대상 ${item.target}` : '',
    item.updatedAt ? `업데이트 ${item.updatedAt}` : '',
  ].filter(Boolean);

export const activityToneLabel: Record<ActivityItem['tone'], string> = {
  blue: '수집',
  green: '정상',
  orange: '주의',
  red: '위험',
  violet: '기록',
};

export const auditLedgerFilters: Array<{ id: 'all' | LedgerEntry['category']; label: string }> = [
  { id: 'all', label: '전체' },
  { id: 'approval', label: '승인' },
  { id: 'mutation', label: '변경 실행' },
  { id: 'gateway', label: '게이트웨이' },
  { id: 'evidence', label: '증거' },
];

