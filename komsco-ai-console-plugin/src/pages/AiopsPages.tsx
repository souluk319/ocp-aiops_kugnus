import * as React from 'react';
import { Button, Spinner } from '@patternfly/react-core';
import {
  BoltIcon,
  ChartLineIcon,
  CheckCircleIcon,
  ClipboardCheckIcon,
  CubesIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  HistoryIcon,
  LockIcon,
  ProjectDiagramIcon,
  RobotIcon,
  ServerIcon,
  ShieldAltIcon,
  TachometerAltIcon,
} from '@patternfly/react-icons';
import {
  type AiopsActionCandidate,
  type AiopsAnomalyFinding,
  type AiopsOverview,
  type AiopsRecord,
  type AiopsRuntimeStatus,
  type ClusterSummary,
  type RagSearchResultItem,
  type RagUploadedDocument,
  approveActionPlan,
  createActionCandidatePlan,
  executeApprovedAction,
  fetchAiopsOverview,
  fetchAiopsStatus,
  fetchClusterSummary,
  fetchUploadedRagDocuments,
  searchRagDocuments,
  uploadRagDocumentFile,
} from '../services/aiGateway';
import AssistantLauncher from '../components/AssistantLauncher';
import { safeEvidenceText } from '../utils/evidenceDisplay';
import kIcon from '../assets/k_icon.png';
import './aiops-pages.css';

type AiopsPageData = {
  error: string;
  loading: boolean;
  overview: AiopsOverview | null;
  refresh: () => Promise<void>;
  status: AiopsRuntimeStatus | null;
  summary: ClusterSummary | null;
};

type Tone = 'danger' | 'info' | 'success' | 'warning';
type RagBackendStatus = NonNullable<AiopsRuntimeStatus['spec']['capabilities']['rag']>;

type AssistantDraftPromptRequest = {
  id: string;
  pageContext: Record<string, unknown>;
  prompt: string;
  taskMode: 'troubleshooting';
};

const ProductIcon: React.FC = () => (
  <img alt="" className="komsco-ai-page__product-icon" src={kIcon} />
);

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

const objectList = (value: unknown): Record<string, unknown>[] =>
  Array.isArray(value)
    ? value.filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    : [];

const compactToolName = (value: unknown): string => textValue(value).replace(/_/g, ' ');

const compactDigest = (value?: string): string => {
  if (!value) {
    return '';
  }

  return value.length > 28 ? `${value.slice(0, 24)}...` : value;
};

const DOCS_UPLOAD_ACCEPT = [
  '.pdf',
  '.docx',
  '.pptx',
  '.xlsx',
  '.txt',
  '.md',
  '.markdown',
  '.json',
  '.yaml',
  '.yml',
  '.log',
].join(',');

const formatBytes = (value?: number): string => {
  const size = typeof value === 'number' && Number.isFinite(value) ? value : 0;
  if (size < 1024) {
    return `${size} B`;
  }
  if (size < 1024 * 1024) {
    return `${(size / 1024).toFixed(1)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
};

const uploadedDocumentQuery = (document: RagUploadedDocument): string =>
  [document.title, document.sourceUri, document.documentId].filter(Boolean).join(' ');

const ragBackendTone = (status?: string): Tone => {
  if (status === 'configured') {
    return 'success';
  }
  if (status === 'unavailable') {
    return 'danger';
  }
  return 'warning';
};

const clampScore = (value?: number): number => {
  if (typeof value !== 'number' || Number.isNaN(value)) {
    return 0;
  }

  return Math.max(0, Math.min(100, value));
};

const healthTone = (score?: number): Tone => {
  const safeScore = clampScore(score);
  if (safeScore >= 85) {
    return 'success';
  }
  if (safeScore >= 65) {
    return 'warning';
  }
  return 'danger';
};

const statusTone = (value: boolean): Tone => (value ? 'success' : 'warning');

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

const actionRecords = (status: AiopsRuntimeStatus | null): AiopsRecord[] => {
  if (!status) {
    return [];
  }

  return [
    ...status.spec.records.actionProposals,
    ...status.spec.records.sealedActionPlans,
    ...status.spec.records.approvalDecisions,
    ...status.spec.records.executionRecords,
  ];
};

const chatTranscriptRecords = (status: AiopsRuntimeStatus | null): AiopsRecord[] =>
  status?.spec.records.chatTranscripts ?? [];

type ActionCandidateNextAction = 'approve-plan' | 'create-plan' | 'done' | 'execute-approval';

type ActionCandidateLifecycleState = {
  action: ActionCandidateNextAction;
  approvalId?: string;
  disabledReason?: string;
  label: string;
  phaseLabel: string;
  planDigest?: string;
  planId?: string;
  proof: string;
};

const recordName = (record?: AiopsRecord): string => record?.metadata?.name ?? '';

const candidateExecutableTool = (candidate: AiopsActionCandidate): string => {
  const kind = candidate.target?.kind ?? '';
  if (kind === 'Deployment') {
    return 'rollout_restart_deployment';
  }
  if (kind === 'Pod') {
    return 'evict_one_unhealthy_controller_owned_pod';
  }
  return '';
};

const planDigest = (record?: AiopsRecord): string => {
  const sealedActionPlan = asObject(asObject(record?.spec).sealedActionPlan);
  const digest = asObject(sealedActionPlan.digest);
  return textValue(digest.planDigest, '');
};

const approvalDecision = (record?: AiopsRecord): Record<string, unknown> =>
  asObject(asObject(record?.spec).approvalDecision);

const approvalId = (record?: AiopsRecord): string =>
  textValue(approvalDecision(record).approvalId, recordName(record));

const approvalPlanDigest = (record?: AiopsRecord): string =>
  textValue(approvalDecision(record).planDigest, '');

const targetMatchesCandidate = (
  target: Record<string, unknown>,
  candidate: AiopsActionCandidate,
): boolean => {
  const candidateTarget = candidate.target ?? {};
  return (
    textValue(target.kind, '') === textValue(candidateTarget.kind, '') &&
    textValue(target.namespace, '') === textValue(candidateTarget.namespace, '') &&
    textValue(target.name, '') === textValue(candidateTarget.name, '')
  );
};

const actionRecordMatchesCandidate = (
  record: AiopsRecord,
  candidate: AiopsActionCandidate,
): boolean => {
  const toolName = candidateExecutableTool(candidate);
  if (!toolName) {
    return false;
  }

  const spec = asObject(record.spec);
  const proposal = asObject(spec.candidateActionRequest);
  const sealedActionPlan = asObject(spec.sealedActionPlan);
  const action = Object.keys(proposal).length > 0 ? asObject(proposal.action) : asObject(sealedActionPlan.action);
  const target = Object.keys(proposal).length > 0 ? asObject(proposal.target) : asObject(sealedActionPlan.target);

  return textValue(action.toolName, '') === toolName && targetMatchesCandidate(target, candidate);
};

const actionCandidateLifecycle = (
  candidate: AiopsActionCandidate,
  status: AiopsRuntimeStatus | null,
): ActionCandidateLifecycleState => {
  const toolName = candidateExecutableTool(candidate);
  if (!toolName) {
    return {
      action: 'done',
      disabledReason: '현재 실행 API는 Deployment 재시작과 Pod eviction 후보만 연결되어 있습니다.',
      label: '실행 API 없음',
      phaseLabel: '설계 필요',
      proof: '이 후보는 아직 Gateway action registry에 묶이지 않았습니다.',
    };
  }

  const records = status?.spec.records;
  const plan = (records?.sealedActionPlans ?? []).find((item) =>
    actionRecordMatchesCandidate(item, candidate),
  );
  const digest = planDigest(plan);
  const approval = (records?.approvalDecisions ?? []).find(
    (item) => approvalPlanDigest(item) === digest && approvalDecision(item).status === 'approved',
  );
  const execution = (records?.executionRecords ?? []).find((item) => {
    const spec = asObject(item.spec);
    return (
      textValue(spec.planDigest, '') === digest ||
      (approval ? textValue(spec.approvalId, '') === approvalId(approval) : false)
    );
  });

  if (execution) {
    return {
      action: 'done',
      disabledReason: '이미 실행 기록이 있습니다.',
      label: '완료',
      phaseLabel: 'ExecutionRecord',
      proof: `${recordName(execution)} · ${recordPhase(execution)}`,
    };
  }

  if (approval && plan) {
    return {
      action: 'execute-approval',
      approvalId: approvalId(approval),
      label: '실행',
      phaseLabel: '승인 완료',
      planDigest: digest,
      planId: recordName(plan),
      proof: `${approvalId(approval)} · ${compactDigest(digest)}`,
    };
  }

  if (plan) {
    return {
      action: 'approve-plan',
      label: '승인',
      phaseLabel: '계획 생성됨',
      planDigest: digest,
      planId: recordName(plan),
      proof: `${recordName(plan)} · ${compactDigest(digest)}`,
    };
  }

  return {
    action: 'create-plan',
    label: '해결 계획 만들기',
    phaseLabel: '계획 전',
    proof: `${toolName} · live target 확인 후 계획 생성`,
  };
};

const useAiopsPageData = (): AiopsPageData => {
  const [summary, setSummary] = React.useState<ClusterSummary | null>(null);
  const [overview, setOverview] = React.useState<AiopsOverview | null>(null);
  const [status, setStatus] = React.useState<AiopsRuntimeStatus | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');

  const refresh = React.useCallback(async () => {
    setLoading(true);
    const [overviewResult, statusResult] = await Promise.allSettled([
      fetchAiopsOverview(),
      fetchAiopsStatus(),
    ]);

    if (overviewResult.status === 'fulfilled') {
      setOverview(overviewResult.value);
      setSummary(overviewResult.value.spec.clusterSummary);
    } else {
      setOverview(null);
      try {
        setSummary(await fetchClusterSummary());
      } catch {
        setSummary(null);
      }
    }

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value);
    }

    const errors = [overviewResult, statusResult]
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) =>
        result.reason instanceof Error ? result.reason.message : String(result.reason),
      );

    setError(errors.join('\n'));
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return { error, loading, overview, refresh, status, summary };
};

const PageShell: React.FC<{
  children: React.ReactNode;
  data: AiopsPageData;
  eyebrow: string;
  icon: React.ReactNode;
  title: string;
}> = ({ children, data, eyebrow, icon, title }) => (
  <div className="komsco-ai-page">
    <div className="komsco-ai-page__header">
      <div className="komsco-ai-page__title-block">
        <span className="komsco-ai-page__eyebrow">{eyebrow}</span>
        <h1>
          <span className="komsco-ai-page__title-icon">{icon}</span>
          {title}
        </h1>
      </div>
      <Button isDisabled={data.loading} onClick={() => void data.refresh()} variant="secondary">
        새로고침
      </Button>
    </div>
    {data.error && <div className="komsco-ai-page__error">{data.error}</div>}
    {data.loading && !data.status && !data.summary && (
      <div className="komsco-ai-page__loading">
        <Spinner size="lg" />
        <span>초기 관제 데이터를 수집 중입니다.</span>
      </div>
    )}
    {children}
  </div>
);

const EmptyState: React.FC<{ label: string }> = ({ label }) => (
  <div className="komsco-ai-page__empty">{label}</div>
);

const MetricTile: React.FC<{
  detail?: string;
  icon: React.ReactNode;
  label: string;
  tone: Tone;
  value: string | number;
}> = ({ detail, icon, label, tone, value }) => (
  <div className={`komsco-ai-page__metric komsco-ai-page__metric--${tone}`}>
    <span className="komsco-ai-page__metric-icon">{icon}</span>
    <span className="komsco-ai-page__metric-label">{label}</span>
    <strong>{value}</strong>
    {detail && <span className="komsco-ai-page__metric-detail">{detail}</span>}
  </div>
);

const OperatorFlowBoard: React.FC<{ data: AiopsPageData }> = ({ data }) => {
  const overview = data.overview;
  const status = data.status;
  const summary = data.summary;
  const overviewLoaded = Boolean(data.overview);
  const statusLoaded = Boolean(data.status);
  const anomalies = overview?.spec.anomalies?.spec;
  const actionCandidates = overview?.spec.actionCandidates?.spec;
  const evidenceStatus = status?.spec.safetyContract?.evidenceStatus ?? [];
  const collectedEvidence = evidenceStatus
    .filter((item) => item.status === 'collected')
    .reduce((total, item) => total + item.count, 0);
  const mutationsEnabled = Boolean(status?.spec.capabilities.mutationsEnabled);
  const actionExecutorReady = Boolean(status?.spec.capabilities.actionExecutorConfigured);
  const executionReady = mutationsEnabled && actionExecutorReady;
  const rcaStatus = status?.spec.safetyContract?.rcaContextStatus?.status;
  const rcaStatusLabel =
    rcaStatus === 'ready'
      ? 'RCA 근거 준비됨'
      : rcaStatus === 'missing_question'
        ? '질문 후 RCA 근거 생성'
        : statusLoaded
          ? 'RCA 근거 확인 중'
          : '질문 후 RCA 근거 생성';
  const flowItems = [
    {
      detail: summary ? `${summary.nodes.ready}/${summary.nodes.total} ready` : '상태 수집 중',
      icon: <ServerIcon />,
      label: '클러스터 상태',
      tone: !summary || summary.nodes.notReady ? 'warning' : 'success',
      value: overview
        ? (overview.spec.controlTower.statusLabel ?? '관제 상태 확인 중')
        : '관제 상태 확인 중',
    },
    {
      detail: overviewLoaded && anomalies ? `총 ${anomalies.totals?.total ?? 0}건` : '소스 확인 중',
      icon: <ExclamationTriangleIcon />,
      label: '이상 징후',
      tone: anomalyStatusTone(anomalies?.status),
      value: overviewLoaded ? (anomalies?.statusLabel ?? '이상 징후 확인 중') : '이상 징후 수집 중',
    },
    {
      detail: statusLoaded ? `근거 ${collectedEvidence} collected` : '근거 상태 확인 중',
      icon: <ClipboardCheckIcon />,
      label: 'RCA 근거',
      tone: collectedEvidence > 0 ? 'info' : 'warning',
      value: rcaStatusLabel,
    },
    {
      detail: executionReady ? '실행 계획 생성 가능' : '승인 전 분석 단계',
      icon: <BoltIcon />,
      label: '조치 후보',
      tone: actionCandidateTone(
        actionCandidates?.candidates?.[0]?.riskLevel,
        actionCandidates?.status,
      ),
      value: actionCandidates?.statusLabel ?? '조치 후보 확인 중',
    },
    {
      detail: '대화 기록 기본 접힘',
      icon: <HistoryIcon />,
      label: '감사·대화',
      tone: statusLoaded ? 'info' : 'warning',
      value: statusLoaded
        ? `감사 ${status?.spec.records.auditRecords?.length ?? 0}건`
        : '감사 상태 확인 중',
    },
    {
      detail: statusLoaded
        ? executionReady
          ? 'Action Executor 연결'
          : '실행 경로 확인 필요'
        : 'mutation 상태 확인 중',
      icon: <ShieldAltIcon />,
      label: '안전 정책',
      tone: statusLoaded ? (executionReady ? 'info' : 'warning') : 'warning',
      value: statusLoaded
        ? (status?.spec.safetyContract?.mode ?? '정책 확인 중')
        : '안전 정책 확인 중',
    },
  ] as const;

  return (
    <section className="komsco-ai-page__operator-flow" aria-label="AIOps operator flow">
      <div className="komsco-ai-page__operator-flow-head">
        <span className="komsco-ai-page__section-kicker">Operator flow</span>
        <h2>운영 흐름</h2>
      </div>
      <div className="komsco-ai-page__operator-flow-grid">
        {flowItems.map((item) => (
          <div className={`komsco-ai-page__operator-flow-item is-${item.tone}`} key={item.label}>
            <span className="komsco-ai-page__operator-flow-icon">{item.icon}</span>
            <span className="komsco-ai-page__operator-flow-label">{item.label}</span>
            <strong>{item.value}</strong>
            <small>{item.detail}</small>
          </div>
        ))}
      </div>
    </section>
  );
};

const dataSourceTone = (status?: string): Tone => {
  if (status === 'available') {
    return 'success';
  }
  if (status === 'error') {
    return 'danger';
  }
  return 'warning';
};

const anomalyStatusTone = (status?: string): Tone => {
  if (status === 'normal') {
    return 'success';
  }
  if (status === 'risk' || status === 'error') {
    return 'danger';
  }
  return 'warning';
};

const anomalySeverityTone = (severity?: string): Tone => {
  if (severity === '위험') {
    return 'danger';
  }
  if (severity === '정상') {
    return 'success';
  }
  return 'warning';
};

const anomalyResourceLabel = (finding: AiopsAnomalyFinding): string => {
  const resource = finding.resource ?? {};
  const namespace = finding.namespace || resource.namespace || 'cluster-scoped';
  const name = resource.name || finding.title;
  const kind = resource.kind || finding.category || 'Resource';

  return `${namespace}/${kind}/${name}`;
};

const actionCandidateTone = (riskLevel?: string, status?: string): Tone => {
  if (status === 'normal') {
    return 'success';
  }
  if (status === 'blocked' || riskLevel === 'high') {
    return 'danger';
  }
  return 'warning';
};

const actionCandidateTargetLabel = (candidate: AiopsActionCandidate): string => {
  const target = candidate.target ?? {};
  const namespace = target.namespace || 'cluster-scoped';
  const kind = target.kind || 'Resource';
  const name = target.name || candidate.title;
  return `${namespace}/${kind}/${name}`;
};

const findingTargetParts = (
  finding: AiopsAnomalyFinding,
): { kind: string; name: string; namespace: string } => {
  const resource = finding.resource ?? {};
  return {
    kind: resource.kind || finding.category || 'Resource',
    name: resource.name || finding.title,
    namespace: finding.namespace || resource.namespace || 'cluster-scoped',
  };
};

const isCrashLoopFinding = (finding: AiopsAnomalyFinding): boolean => {
  const haystack = [
    finding.type,
    finding.reason,
    finding.title,
    finding.message,
    finding.evidence,
    finding.statusLabel,
  ]
    .filter(Boolean)
    .join(' ')
    .toLowerCase();

  return haystack.includes('crashloop') || finding.type === 'pod_crashloop';
};

const actionCandidateMatchesFinding = (
  candidate: AiopsActionCandidate,
  finding: AiopsAnomalyFinding,
): boolean => {
  if (candidate.sourceFindingId && candidate.sourceFindingId === finding.id) {
    return true;
  }

  const target = candidate.target ?? {};
  const findingTarget = findingTargetParts(finding);
  return (
    target.namespace === findingTarget.namespace &&
    target.name === findingTarget.name &&
    (!target.kind || !findingTarget.kind || target.kind === findingTarget.kind)
  );
};

const findingEvidenceText = (finding: AiopsAnomalyFinding, fallback = '근거 수집 중'): string =>
  safeEvidenceText(finding.evidence || finding.message, fallback);

const findingNextCheckText = (
  finding: AiopsAnomalyFinding,
  fallback = '관련 Pod 상태, 이벤트, 로그 가능 여부 확인',
): string => safeEvidenceText(finding.nextCheck, fallback);

const buildFindingDemoPrompt = (
  finding: AiopsAnomalyFinding,
  candidate?: AiopsActionCandidate,
): string => {
  const target = anomalyResourceLabel(finding);
  const candidateLine = candidate
    ? `연결된 조치 후보: ${candidate.title} / ${candidate.statusLabel || '승인 전 확인 필요'}`
    : '연결된 조치 후보: 아직 특정 후보와 강하게 묶이지 않았으니 확인 필요로 표시';

  return [
    '다음 OpenShift 이상 징후를 RCA 분석하고, 승인 필요한 조치 후보까지 정리해줘.',
    '',
    `시나리오: CrashLoopBackOff 원인 분석`,
    `findingId: ${finding.id}`,
    `대상: ${target}`,
    `심각도: ${finding.severity}`,
    `원인 후보: ${finding.candidateCause || finding.reason || '추가 확인 필요'}`,
    `현재 근거: ${findingEvidenceText(finding)}`,
    `다음 확인: ${findingNextCheckText(finding)}`,
    candidateLine,
    '',
    '답변 형식:',
    '1. 확인된 근거',
    '2. 가능한 원인 후보',
    '3. 추가 확인 필요 근거',
    '4. 먼저 확인할 증거와 순서',
    '5. 실행 계획이 필요하면 승인 조건과 되돌림 기준',
    '',
    '주의: 로그 원문은 민감정보 가능성이 있으니 원문 노출 없이 필요 여부와 확인 방법만 정리해줘. 실제 변경은 계획, 승인, 검증 조건을 거쳐야 한다.',
  ].join('\n');
};

const buildFindingDemoDraft = (
  finding: AiopsAnomalyFinding,
  candidate?: AiopsActionCandidate,
): AssistantDraftPromptRequest => {
  const target = findingTargetParts(finding);
  return {
    id: `${finding.id}-${Date.now()}`,
    pageContext: {
      candidateId: candidate?.id,
      candidateStatusLabel: candidate?.statusLabel,
      findingId: finding.id,
      findingTitle: finding.title,
      scenarioId: isCrashLoopFinding(finding) ? 'crashloop' : finding.type,
      selectedAt: new Date().toISOString(),
      source: 'aiops-dashboard-anomaly-board',
      target,
    },
    prompt: buildFindingDemoPrompt(finding, candidate),
    taskMode: 'troubleshooting',
  };
};

const buildActionCandidatePrompt = (candidate: AiopsActionCandidate): AssistantDraftPromptRequest => {
  const target = candidate.target ?? {};
  const kind = target.kind || 'Deployment';
  const namespace = target.namespace || '';
  const name = target.name || '';
  const targetLabel = actionCandidateTargetLabel(candidate);
  const command =
    kind.toLowerCase() === 'pod'
      ? `Pod \`${namespace}/${name}\` evict 실행 계획을 생성해줘.`
      : `Deployment \`${namespace}/${name}\` rollout restart 실행 계획을 생성해줘.`;

  return {
    id: `${candidate.id}-${Date.now()}`,
    pageContext: {
      aiopsExecutionMode: 'execute',
      candidateId: candidate.id,
      candidateStatusLabel: candidate.statusLabel,
      selectedAt: new Date().toISOString(),
      source: 'aiops-dashboard-action-candidate-board',
      target,
    },
    prompt: [
      command,
      '',
      `조치 후보: ${candidate.title}`,
      `대상: ${targetLabel}`,
      `위험도: ${candidate.riskLabel || candidate.riskLevel || '확인 필요'}`,
      `근거: ${candidate.evidence || '근거 확인 필요'}`,
      `선행 확인: ${candidate.prerequisiteChecks?.[0] || '대상 리소스 상태 확인'}`,
      `예상 영향: ${candidate.expectedImpact || '영향 범위 확인 필요'}`,
      '',
      '실행은 바로 하지 말고, 먼저 Action Plan을 만들고 승인 버튼을 기다려.',
    ].join('\n'),
    taskMode: 'troubleshooting',
  };
};

const AnomalySummaryBoard: React.FC<{
  activeFindingId?: string;
  onAnalyzeFinding?: (finding: AiopsAnomalyFinding) => void;
  overview: AiopsOverview | null;
}> = ({ activeFindingId, onAnalyzeFinding, overview }) => {
  const anomalies = overview?.spec.anomalies?.spec;
  const status = anomalies?.status ?? (overview ? 'unknown' : 'loading');
  const tone = anomalyStatusTone(status);
  const findings = anomalies?.findings ?? [];
  const topFindings = findings.slice(0, 3);
  const totals = anomalies?.totals ?? {};
  const dataSources = anomalies?.dataSources ?? [];
  const failedSources = dataSources.filter((source) => source.status !== 'available');
  const normalSignals = anomalies?.normalSignals ?? [];
  const sourceText =
    dataSources.length > 0
      ? `${dataSources.filter((source) => source.status === 'available').length}/${dataSources.length} sources`
      : 'source pending';

  if (!overview) {
    return (
      <section
        className="komsco-ai-page__anomaly-board is-warning"
        aria-label="Cywell AI anomaly summary"
      >
        <div className="komsco-ai-page__anomaly-head">
          <div>
            <span>Cywell AI 이상 징후</span>
            <strong>overview 수집 중</strong>
          </div>
          <code>증거 수집</code>
        </div>
        <p>회사 OCP의 Alert, Pod, Operator, Event, 재시작 지표를 읽는 중입니다.</p>
      </section>
    );
  }

  return (
    <section
      className={`komsco-ai-page__anomaly-board is-${tone}`}
      aria-label="Cywell AI anomaly summary"
      data-anomaly-status={status}
      data-anomaly-total={totals.total ?? 0}
    >
      <div className="komsco-ai-page__anomaly-head">
        <div>
          <span>Cywell AI 이상 징후 자동 정리</span>
          <strong>{anomalies?.statusLabel ?? '이상 징후 상태 확인 중'}</strong>
        </div>
        <div className="komsco-ai-page__anomaly-badges">
          <code>{sourceText}</code>
          <code>{overview.spec.anomalies?.spec?.safety?.mode ?? '분석'}</code>
        </div>
      </div>

      <div className="komsco-ai-page__anomaly-totals" aria-label="Anomaly severity totals">
        <span className="is-danger">위험 {totals.danger ?? 0}</span>
        <span className="is-warning">확인 필요 {totals.attention ?? 0}</span>
        <span>주의 {totals.warning ?? 0}</span>
        <span>총 {totals.total ?? findings.length}</span>
      </div>

      {topFindings.length > 0 ? (
        <div
          className="komsco-ai-page__anomaly-list"
          data-visible-anomaly-count={topFindings.length}
        >
          {topFindings.map((finding) => {
            const findingTone = anomalySeverityTone(finding.severity);
            const crashLoopDemo = isCrashLoopFinding(finding);
            const active = activeFindingId === finding.id;
            return (
              <article
                className={`komsco-ai-page__anomaly-item is-${findingTone}${active ? ' is-active-demo' : ''}`}
                data-aiops-finding-id={finding.id}
                data-aiops-scenario={crashLoopDemo ? 'crashloop' : finding.type}
                key={finding.id}
              >
                <div className="komsco-ai-page__anomaly-item-head">
                  <span>{finding.severity}</span>
                  <strong>{finding.title}</strong>
                  <code>P{finding.priority}</code>
                </div>
                <dl>
                  <dt>대상</dt>
                  <dd>{anomalyResourceLabel(finding)}</dd>
                  <dt>원인 후보</dt>
                  <dd>{finding.candidateCause || finding.reason || '추가 확인 필요'}</dd>
                  <dt>근거</dt>
                  <dd>{findingEvidenceText(finding)}</dd>
                  <dt>다음 확인</dt>
                  <dd>{findingNextCheckText(finding, '관련 리소스 상태와 이벤트 확인')}</dd>
                </dl>
                <div className="komsco-ai-page__anomaly-actions">
                  {crashLoopDemo && <span className="komsco-ai-page__demo-badge">0.1.3 demo</span>}
                  {active && (
                    <span className="komsco-ai-page__demo-badge is-active">질문에 연결됨</span>
                  )}
                  {crashLoopDemo && (
                    <Button
                      data-aiops-demo-action="seed-chat-prompt"
                      isInline
                      onClick={() => onAnalyzeFinding?.(finding)}
                      variant="link"
                    >
                      챗봇으로 RCA 질문 생성
                    </Button>
                  )}
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div className="komsco-ai-page__anomaly-normal" data-visible-anomaly-count="0">
          {status === 'normal' ? <CheckCircleIcon /> : <ExclamationTriangleIcon />}
          <div>
            <strong>
              {status === 'normal'
                ? '현재 수집 범위에서 주요 이상 징후 없음'
                : '아직 정상으로 단정할 수 없음'}
            </strong>
            <span>
              {(failedSources.length > 0
                ? failedSources.map((source) => `${source.label}: ${source.status}`).join(' / ')
                : normalSignals.join(' / ')) || '데이터 소스 상태 확인 중'}
            </span>
          </div>
        </div>
      )}
    </section>
  );
};

const ActionCandidateBoard: React.FC<{
  activeCandidateId?: string;
  actionBusyId?: string;
  actionError?: string;
  actionNotice?: string;
  onCandidateAction?: (
    candidate: AiopsActionCandidate,
    lifecycle: ActionCandidateLifecycleState,
  ) => void;
  onPlanCandidate?: (candidate: AiopsActionCandidate) => void;
  overview: AiopsOverview | null;
  status: AiopsRuntimeStatus | null;
}> = ({
  activeCandidateId,
  actionBusyId = '',
  actionError = '',
  actionNotice = '',
  onCandidateAction,
  onPlanCandidate,
  overview,
  status: runtimeStatus,
}) => {
  const actionCandidates = overview?.spec.actionCandidates?.spec;
  const candidates = actionCandidates?.candidates ?? [];
  const visibleCandidates = candidates.slice(0, 3);
  const totals = actionCandidates?.totals ?? {};
  const candidateStatus = actionCandidates?.status ?? (overview ? 'unknown' : 'loading');
  const tone = actionCandidateTone(visibleCandidates[0]?.riskLevel, candidateStatus);
  const executionReady = Boolean(
    runtimeStatus?.spec.capabilities.mutationsEnabled &&
      runtimeStatus.spec.capabilities.actionExecutorConfigured,
  );
  const forbiddenVerbs = actionCandidates?.safety?.forbiddenMutationVerbs ?? [
    'apply',
    'delete',
    'patch',
    'scale',
    'exec',
  ];
  const mode = actionCandidates?.safety?.mode ?? (executionReady ? 'execute' : '분석');

  if (!overview) {
    return (
      <section
        className="komsco-ai-page__action-candidate-board is-warning"
        aria-label="AIOps action candidates"
      >
        <div className="komsco-ai-page__action-candidate-head">
          <div>
            <span>AIOps 복구 계획</span>
            <strong>overview 수집 중</strong>
          </div>
          <code>상태 확인 중</code>
        </div>
        <p>이상 징후를 읽은 뒤 복구 계획과 승인 가능한 조치 후보를 정리합니다.</p>
      </section>
    );
  }

  return (
    <section
      className={`komsco-ai-page__action-candidate-board is-${tone}`}
      aria-label="AIOps action candidates"
      data-action-candidate-status={candidateStatus}
      data-action-candidate-total={totals.total ?? candidates.length}
      data-action-candidate-execution={executionReady ? 'approval-gated' : 'not-ready'}
      data-action-candidate-mode={mode}
    >
      <div className="komsco-ai-page__action-candidate-head">
        <div>
          <span>Cywell AI 복구 계획</span>
          <strong>{actionCandidates?.statusLabel ?? '조치 후보 상태 확인 중'}</strong>
        </div>
        <div className="komsco-ai-page__action-candidate-badges">
          <code>{executionReady ? '승인 계획 가능' : '분석 후보'}</code>
          <code>{mode}</code>
          <code>승인 필요 {totals.approvalRequired ?? candidates.length}</code>
        </div>
      </div>

      <div className="komsco-ai-page__action-candidate-policy">
        <ShieldAltIcon />
        <span>
          {executionReady
            ? '계획/승인/검증 API 경로로 해결 계획 생성, 승인, 실행을 순서대로 호출하고 모든 기록을 남깁니다.'
            : `실행 경로 확인 전입니다. 차단 동작: ${forbiddenVerbs.join(', ')}`}
        </span>
      </div>
      {actionError && <div className="komsco-ai-page__action-candidate-feedback is-error">{actionError}</div>}
      {actionNotice && <div className="komsco-ai-page__action-candidate-feedback is-success">{actionNotice}</div>}

      {visibleCandidates.length > 0 ? (
        <div
          className="komsco-ai-page__action-candidate-list"
          data-visible-action-candidate-count={visibleCandidates.length}
        >
          {visibleCandidates.map((candidate) => {
            const lifecycle = actionCandidateLifecycle(candidate, runtimeStatus);
            const actionKey = `${lifecycle.action}:${candidate.id}`;
            const busy = actionBusyId === actionKey;
            const active = activeCandidateId === candidate.id;
            return (
              <article
                className={`komsco-ai-page__action-candidate${active ? ' is-active-demo' : ''}`}
                key={candidate.id}
              >
                <div className="komsco-ai-page__action-candidate-title">
                  <span>{candidate.riskLabel || candidate.riskLevel || '위험도 확인'}</span>
                  <strong>{candidate.title}</strong>
                  <code>P{candidate.priority ?? '-'}</code>
                </div>
                <dl>
                  <dt>대상</dt>
                  <dd>{actionCandidateTargetLabel(candidate)}</dd>
                  <dt>상태</dt>
                  <dd>
                    {lifecycle.phaseLabel}
                  </dd>
                  <dt>복구 계획</dt>
                  <dd>{candidate.recommendationSteps?.[0] || '근거 확인 후 승인 계획 생성'}</dd>
                  <dt>선행 확인</dt>
                  <dd>{candidate.prerequisiteChecks?.[0] || '관련 리소스 상태와 이벤트 확인'}</dd>
                  <dt>예상 영향</dt>
                  <dd>{candidate.expectedImpact || '승인 전 영향 범위 확인 필요'}</dd>
                  <dt>승인</dt>
                  <dd>{candidate.approvalRequired ? '승인 전 실행 불가' : '승인 정책 확인 필요'}</dd>
                  <dt>검증</dt>
                  <dd>{candidate.verificationChecks?.[0] || '조치 후 상태 재확인 필요'}</dd>
                  <dt>실행 흐름</dt>
                  <dd>{lifecycle.proof}</dd>
                </dl>
                <div className="komsco-ai-page__anomaly-actions">
                  {active && (
                    <span className="komsco-ai-page__demo-badge is-active">질문에 연결됨</span>
                  )}
                  <Button
                    isDisabled={busy || Boolean(lifecycle.disabledReason)}
                    isLoading={busy}
                    onClick={() => onCandidateAction?.(candidate, lifecycle)}
                    title={
                      lifecycle.disabledReason ||
                      'Gateway 실행 흐름에서 다음 단계를 진행합니다.'
                    }
                    variant={lifecycle.action === 'execute-approval' ? 'danger' : 'primary'}
                  >
                    {lifecycle.label}
                  </Button>
                  <Button
                    isInline
                    onClick={() => onPlanCandidate?.(candidate)}
                    title="이 후보를 챗봇 질문으로 보내 근거 설명을 다시 확인합니다."
                    variant="link"
                  >
                    근거 다시 묻기
                  </Button>
                </div>
              </article>
            );
          })}
        </div>
      ) : (
        <div
          className="komsco-ai-page__action-candidate-empty"
          data-visible-action-candidate-count="0"
        >
          <CheckCircleIcon />
          <div>
            <strong>
              {candidateStatus === 'normal'
                ? '현재 제안할 조치 후보 없음'
                : '조치 후보를 만들 만큼 근거가 충분하지 않음'}
            </strong>
            <span>
              {actionCandidates?.statusLabel ??
                '이상 징후 데이터와 필수 소스 상태를 먼저 확인합니다.'}
            </span>
          </div>
        </div>
      )}
    </section>
  );
};

const DataSourceBoard: React.FC<{ overview: AiopsOverview | null }> = ({ overview }) => {
  const dataSources = overview?.spec.dataSources ?? [];
  const controlTower = overview?.spec.controlTower;
  const monitoringProbe = overview?.spec.monitoring?.probe;

  if (!overview) {
    return (
      <section className="komsco-ai-page__source-board komsco-ai-page__source-board--pending">
        <div>
          <span>Cywell AI 관제탑</span>
          <strong>overview 수집 중</strong>
        </div>
        <p>회사 OCP의 실제 데이터 소스 상태를 확인하는 중입니다.</p>
      </section>
    );
  }

  return (
    <section className="komsco-ai-page__source-board" aria-label="Cywell AI data source status">
      <div className="komsco-ai-page__source-board-head">
        <div>
          <span>Cywell AI 관제탑</span>
          <strong>{controlTower?.statusLabel ?? '상태 확인 중'}</strong>
        </div>
        <code>{controlTower?.mode ?? 'evidence-check'}</code>
      </div>
      <div className="komsco-ai-page__source-grid">
        {dataSources.map((source) => {
          const tone = dataSourceTone(source.status);
          const reason = source.reason || (source.httpStatus ? `HTTP ${source.httpStatus}` : '');
          return (
            <div className={`komsco-ai-page__source is-${tone}`} key={source.name}>
              <span
                className={`komsco-ai-page__status-dot is-${tone === 'success' ? 'ok' : tone === 'danger' ? 'danger' : 'warn'}`}
              />
              <div className="komsco-ai-page__source-main">
                <strong>{source.label}</strong>
                <span>{source.status}</span>
                {reason && <p>{reason}</p>}
              </div>
            </div>
          );
        })}
      </div>
      <div className="komsco-ai-page__monitoring-line">
        <span>Thanos probe</span>
        <strong>{monitoringProbe?.status ?? 'unknown'}</strong>
        <code>{monitoringProbe?.query ?? 'up'}</code>
        {typeof monitoringProbe?.resultCount === 'number' && (
          <em>{monitoringProbe.resultCount} series</em>
        )}
      </div>
    </section>
  );
};

const CustomerTopologyPanel: React.FC<{ data: AiopsPageData }> = ({ data }) => {
  const summary = data.summary;
  const status = data.status;
  const overview = data.overview;
  const rag = status?.spec.capabilities.rag;
  const lightspeed = status?.spec.safetyContract?.lightspeedStatus;
  const dataSources = overview?.spec.dataSources ?? [];
  const availableSources = dataSources.filter((source) => source.status === 'available').length;
  const auditCount = status?.spec.records.auditRecords?.length ?? 0;
  const mutationEnabled = Boolean(status?.spec.capabilities.mutationsEnabled);
  const nodes = [
    {
      detail: summary?.apiUrl ?? 'API 상태 확인 중',
      icon: <ServerIcon />,
      label: '고객 OCP',
      tone: !summary || summary.nodes.notReady ? 'warning' : 'success',
      value: summary ? `${summary.nodes.ready}/${summary.nodes.total} nodes` : '수집 중',
    },
    {
      detail: overview ? `${availableSources}/${dataSources.length} data sources` : 'overview 수집 중',
      icon: <ChartLineIcon />,
      label: '관측 신호',
      tone: overview && availableSources === dataSources.length ? 'success' : 'warning',
      value: overview?.spec.controlTower.statusLabel ?? '확인 중',
    },
    {
      detail: rag?.collection || rag?.backendType || rag?.reason || 'RAG backend 확인 중',
      icon: <ClipboardCheckIcon />,
      label: 'LLM Wiki/RAG',
      tone: ragBackendTone(rag?.status),
      value: rag?.status ?? '확인 중',
    },
    {
      detail: lightspeed?.baseService ?? 'openshift-lightspeed',
      icon: <RobotIcon />,
      label: 'LLM 경로',
      tone: lightspeed?.fallbackActive ? 'warning' : status ? 'info' : 'warning',
      value: lightspeed?.streamProbe ?? 'probe 확인 중',
    },
    {
      detail: `${auditCount} audit records`,
      icon: <ShieldAltIcon />,
      label: '정책/감사',
      tone: status ? (mutationEnabled ? 'danger' : 'success') : 'warning',
      value: status?.spec.safetyContract?.mode ?? '확인 중',
    },
  ] as const;

  return (
    <section className="komsco-ai-page__customer-topology" aria-label="Customer operations topology">
      <div className="komsco-ai-page__customer-topology-head">
        <div>
          <span className="komsco-ai-page__section-kicker">Customer topology</span>
          <h2>고객 운영 토폴로지</h2>
        </div>
        <code>{status?.spec.subject?.username ?? 'subject 확인 중'}</code>
      </div>
      <div className="komsco-ai-page__customer-topology-grid">
        {nodes.map((node) => (
          <article
            className={`komsco-ai-page__customer-topology-node is-${node.tone}`}
            data-customer-topology-node={node.label}
            key={node.label}
          >
            <span className="komsco-ai-page__customer-topology-icon">{node.icon}</span>
            <span>{node.label}</span>
            <strong>{node.value}</strong>
            <small>{node.detail}</small>
          </article>
        ))}
      </div>
    </section>
  );
};

const HealthDial: React.FC<{ score?: number }> = ({ score }) => {
  if (score === undefined) {
    return (
      <div
        aria-label="Cluster health score not loaded"
        className="komsco-ai-page__health-dial komsco-ai-page__health-dial--unknown"
        role="img"
      >
        <div>
          <strong>-</strong>
          <span>pending</span>
        </div>
      </div>
    );
  }

  const safeScore = clampScore(score);
  const dialTone = healthTone(score);
  return (
    <div
      aria-label={`Cluster health score ${safeScore}`}
      className={`komsco-ai-page__health-dial komsco-ai-page__health-dial--${dialTone}`}
      role="img"
      style={{ '--health-score': `${safeScore}%` } as React.CSSProperties}
    >
      <div>
        <strong>{safeScore}</strong>
        <span>health</span>
      </div>
    </div>
  );
};

const EvidenceRail: React.FC<{ status: AiopsRuntimeStatus | null }> = ({ status }) => {
  const evidenceStatus = status?.spec.safetyContract?.evidenceStatus ?? [];
  if (evidenceStatus.length === 0) {
    return <EmptyState label="근거 수집 상태가 아직 없습니다." />;
  }

  return (
    <div className="komsco-ai-page__evidence-rail">
      {evidenceStatus.map((item) => {
        const collected = item.status === 'collected';
        return (
          <div className="komsco-ai-page__evidence-item" key={item.type}>
            <span className={`komsco-ai-page__status-dot ${collected ? 'is-ok' : 'is-warn'}`} />
            <div>
              <strong>{item.type}</strong>
              <span>
                {collected ? `${item.count} collected` : item.reason || 'not collected yet'}
              </span>
            </div>
          </div>
        );
      })}
    </div>
  );
};

const CapabilityBoard: React.FC<{ status: AiopsRuntimeStatus | null }> = ({ status }) => {
  const capabilities = status?.spec.capabilities;
  const contract = status?.spec.safetyContract;
  const statusLoaded = Boolean(status);
  const items = [
    {
      label: '실행 권한',
      value: statusLoaded
        ? capabilities?.mutationsEnabled
          ? '승인 경로 사용'
          : '분석만 가능'
        : '상태 확인 중',
      tone: statusLoaded ? statusTone(Boolean(capabilities?.mutationsEnabled)) : 'warning',
    },
    {
      label: 'Action executor',
      value: statusLoaded
        ? capabilities?.actionExecutorConfigured
          ? 'connected'
          : 'not configured'
        : '상태 확인 중',
      tone: statusLoaded ? statusTone(Boolean(capabilities?.actionExecutorConfigured)) : 'warning',
    },
    {
      label: 'Diagnostics',
      value: statusLoaded ? (capabilities?.diagnosticsEnabled ? 'enabled' : 'off') : '상태 확인 중',
      tone: statusLoaded && capabilities?.diagnosticsEnabled ? 'info' : 'warning',
    },
    {
      label: 'Record ledger',
      value: statusLoaded ? (capabilities?.recordStoreEnabled ? 'on' : 'memory') : '상태 확인 중',
      tone: statusLoaded && capabilities?.recordStoreEnabled ? 'success' : 'warning',
    },
    {
      label: 'Runbook RAG',
      value: statusLoaded ? (capabilities?.rag?.status ?? 'not reported') : '상태 확인 중',
      tone: statusLoaded && capabilities?.rag?.status !== 'not_configured' ? 'info' : 'warning',
    },
  ] as const;

  return (
    <div className="komsco-ai-page__capability-board">
      {items.map((item) => (
        <div className={`komsco-ai-page__capability is-${item.tone}`} key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
      <div className="komsco-ai-page__contract-line">
        <LockIcon />
        <span>
          {contract?.mode === 'evidence_check'
            ? '증거 우선 계약 활성'
            : contract?.mode
              ? '승인 기반 실행 계약 활성'
              : '안전 계약 확인 중'}
        </span>
      </div>
    </div>
  );
};

const LightspeedLink: React.FC<{ data: AiopsPageData }> = ({ data }) => {
  const lightspeedStatus = data.status?.spec.safetyContract?.lightspeedStatus;
  const gatewayStatusLoaded = Boolean(data.status) && !data.error;
  const baseService =
    lightspeedStatus?.baseService ?? 'openshift-lightspeed/lightspeed-app-server:8443';
  const streamProbe = lightspeedStatus?.streamProbe ?? 'probe pending';
  const fallbackActive = Boolean(lightspeedStatus?.fallbackActive);
  const contextDigest = compactDigest(lightspeedStatus?.lastContextDigest);

  return (
    <div className="komsco-ai-page__signal-stack">
      <div
        className={`komsco-ai-page__signal is-${fallbackActive || !gatewayStatusLoaded ? 'warning' : 'info'}`}
      >
        <span
          className={`komsco-ai-page__status-dot ${fallbackActive || !gatewayStatusLoaded ? 'is-warn' : 'is-info'}`}
        />
        <div>
          <strong>
            {fallbackActive
              ? 'Gateway fallback active'
              : gatewayStatusLoaded
                ? 'Gateway status loaded'
                : 'Gateway 상태 확인 중'}
          </strong>
          <span>
            {streamProbe}
            {lightspeedStatus?.lastStatus ? ` / ${lightspeedStatus.lastStatus}` : ''}
          </span>
        </div>
      </div>
      {contextDigest && (
        <div className="komsco-ai-page__endpoint-line">
          <span>Gateway context</span>
          <code>{contextDigest}</code>
        </div>
      )}
      {lightspeedStatus?.lastError && (
        <div className="komsco-ai-page__endpoint-line">
          <span>Last fallback reason</span>
          <code>{lightspeedStatus.lastError}</code>
        </div>
      )}
      <div className="komsco-ai-page__endpoint-line">
        <span>Lightspeed service</span>
        <code>{baseService}</code>
      </div>
      <div className="komsco-ai-page__endpoint-line">
        <span>Console plugin</span>
        <code>komsco-ai-console-plugin-kugnus</code>
      </div>
    </div>
  );
};

const ToolPlanPanel: React.FC<{ status: AiopsRuntimeStatus | null }> = ({ status }) => {
  const contract = status?.spec.safetyContract;
  const toolPlanStatus = contract?.toolPlanStatus;

  if (!contract || !toolPlanStatus) {
    return <EmptyState label="Tool Plan 상태를 아직 가져오지 못했습니다." />;
  }

  const plan =
    toolPlanStatus.latestRuntimePlan && typeof toolPlanStatus.latestRuntimePlan === 'object'
      ? toolPlanStatus.latestRuntimePlan
      : {
          source: toolPlanStatus.source,
          status: toolPlanStatus.status,
          latest_runtime_plan: toolPlanStatus.latestRuntimePlan ?? 'waiting_for_first_question',
          task_type: 'waiting_for_operational_question',
          target: { platform: 'openshift', namespace: 'current-console-context' },
          execution_policy: { mode: contract.mode },
          tool_plan: [
            {
              adapter: 'OpenShift',
              evidence_type: 'openshift_api',
              reason: '첫 질문 전에는 현재 콘솔 컨텍스트와 접근 가능한 리소스를 확인할 준비 상태를 표시',
              step: 1,
              tool: 'openshift_context_inspection',
              verb: 'get',
            },
            {
              adapter: 'OpenShift Lightspeed',
              evidence_type: 'openshift',
              reason: '수집된 Gateway context를 포함해 최종 답변을 만들 준비 상태를 표시',
              step: 2,
              tool: 'lightspeed_streaming_query',
              verb: 'get',
            },
          ],
          allowed_verbs: contract.allowedReadOnlyVerbs,
          forbidden_actions: contract.forbiddenActions,
        };
  const planMap = asObject(plan);
  const steps = objectList(planMap.tool_plan);
  const missingEvidence = objectList(planMap.missing_evidence);
  const adapterResolution = objectList(planMap.adapter_resolution).length
    ? objectList(planMap.adapter_resolution)
    : objectList(toolPlanStatus.adapterResolution);
  const validation = asObject(planMap.validation);
  const executionPolicy = asObject(planMap.execution_policy);
  const target = asObject(planMap.target);
  const taskType = textValue(planMap.task_type, '질문 실행 대기');
  const targetLabel = [
    textValue(target.platform, ''),
    textValue(target.namespace, ''),
    textValue(target.name, ''),
  ]
    .filter(Boolean)
    .join(' / ');
  const validationOk = validation.ok === true;
  const adapterForStep = (step: Record<string, unknown>, index: number) => {
    const stepKey = textValue(step.step, String(index + 1));
    const tool = textValue(step.tool, '');
    return adapterResolution.find(
      (item) => textValue(item.step, '') === stepKey || (tool && textValue(item.tool, '') === tool),
    );
  };

  return (
    <div className="komsco-ai-page__tool-plan" data-tool-plan-step-count={steps.length}>
      <div className="komsco-ai-page__tool-plan-summary">
        <div>
          <span>분류</span>
          <strong>{taskType}</strong>
        </div>
        <div>
          <span>대상</span>
          <strong>{targetLabel || '현재 콘솔 컨텍스트'}</strong>
        </div>
        <div>
          <span>실행 정책</span>
          <strong>{textValue(executionPolicy.mode, textValue(contract.mode, 'evidence_check'))}</strong>
        </div>
        <div>
          <span>검증</span>
          <strong>{validationOk ? 'evidence-check 통과' : textValue(toolPlanStatus.status, '대기')}</strong>
        </div>
      </div>
      {steps.length > 0 ? (
        <ol className="komsco-ai-page__tool-plan-steps" aria-label="Tool Plan 증거 수집 단계">
          {steps.map((step, index) => {
            const adapter = adapterForStep(step, index);
            const resolved = adapter?.resolved === true;
            const statusLabel = resolved ? 'adapter 연결됨' : textValue(adapter?.status, '확인 대기');
            const tool = textValue(step.official_tool, textValue(step.tool, 'tool'));

            return (
              <li
                className={`komsco-ai-page__tool-plan-step ${
                  resolved ? 'is-resolved' : 'is-pending'
                }`}
                data-tool-plan-step=""
                key={`${textValue(step.step, String(index + 1))}-${textValue(step.tool, 'tool')}`}
              >
                <div className="komsco-ai-page__tool-plan-step-head">
                  <span className="komsco-ai-page__tool-plan-step-index">
                    {textValue(step.step, String(index + 1))}
                  </span>
                  <div>
                    <strong>{compactToolName(tool)}</strong>
                    <small>
                      {textValue(step.adapter, textValue(adapter?.adapter, 'adapter'))}
                      {' / '}
                      {textValue(step.verb, textValue(adapter?.verb, 'get'))}
                      {' / '}
                      {textValue(step.evidence_type, textValue(adapter?.evidenceType, 'evidence'))}
                    </small>
                  </div>
                  <code>{statusLabel}</code>
                </div>
                <p>{textValue(step.reason, '이 단계가 필요한 이유가 아직 기록되지 않았습니다.')}</p>
                {adapter?.reason ? <em>{textValue(adapter.reason)}</em> : null}
              </li>
            );
          })}
        </ol>
      ) : (
        <div className="komsco-ai-page__tool-plan-waiting">
          질문 실행 대기: 챗봇에 운영 질문을 보내면 Tool Plan 단계가 먼저 생성됩니다.
        </div>
      )}
      {missingEvidence.length > 0 && (
        <div className="komsco-ai-page__tool-plan-missing">
          <strong>아직 부족한 근거</strong>
          <ul>
            {missingEvidence.map((item, index) => (
              <li key={`${textValue(item.type, 'missing')}-${index}`}>
                <code>{textValue(item.type, 'evidence')}</code>
                <span>{textValue(item.reason, '수집 경로 확인 필요')}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
      <details>
        <summary>
          <span>원본 Tool Plan JSON</span>
          <code>
            {toolPlanStatus.status ?? 'status unknown'}
            {typeof (plan as { task_type?: unknown }).task_type === 'string'
              ? ` · ${(plan as { task_type: string }).task_type}`
              : ''}
          </code>
        </summary>
        <pre>{JSON.stringify(plan, null, 2)}</pre>
      </details>
    </div>
  );
};

const RcaContextPanel: React.FC<{ status: AiopsRuntimeStatus | null }> = ({ status }) => {
  const contextStatus = status?.spec.safetyContract?.rcaContextStatus;

  if (!contextStatus) {
    return <EmptyState label="RCA Context 상태를 아직 가져오지 못했습니다." />;
  }

  const context =
    contextStatus.latestContext && typeof contextStatus.latestContext === 'object'
      ? contextStatus.latestContext
      : {
          digest: contextStatus.digest ?? 'waiting_for_first_question',
          source: contextStatus.source,
          status: contextStatus.status,
        };

  return (
    <div className="komsco-ai-page__tool-plan">
      <details>
        <summary>
          <span>상세 JSON</span>
          <code>{contextStatus.digest ?? contextStatus.status ?? 'waiting_for_first_question'}</code>
        </summary>
        <pre>{JSON.stringify(context, null, 2)}</pre>
      </details>
    </div>
  );
};

const AdapterBoard: React.FC<{ status: AiopsRuntimeStatus | null }> = ({ status }) => {
  const contractAdapters = status?.spec.safetyContract?.adapterStatus;
  if (!contractAdapters || contractAdapters.length === 0) {
    return <EmptyState label="OS adapter 상태를 아직 가져오지 못했습니다." />;
  }

  return (
    <div className="komsco-ai-page__adapter-board">
      {contractAdapters.map((adapter) => (
        <div className="komsco-ai-page__adapter" key={adapter.name}>
          <div className="komsco-ai-page__adapter-main">
            <div className="komsco-ai-page__adapter-head">
              <strong>{adapter.name}</strong>
              <code>{adapter.status}</code>
            </div>
            <span>{adapter.detail || adapter.reason}</span>
            {(adapter.disabledReason || adapter.reason) && (
              <p>{adapter.disabledReason || adapter.reason}</p>
            )}
            {adapter.nextAction && <em>{adapter.nextAction}</em>}
            {adapter.requirements && adapter.requirements.length > 0 && (
              <div className="komsco-ai-page__adapter-requirements">
                <span>requirements</span>
                <ul>
                  {adapter.requirements.map((requirement) => (
                    <li key={requirement}>{requirement}</li>
                  ))}
                </ul>
              </div>
            )}
            {adapter.supportedTools && adapter.supportedTools.length > 0 && (
              <div className="komsco-ai-page__adapter-tools">
                {adapter.supportedTools.slice(0, 3).map((tool) => (
                  <span key={tool.tool}>
                    {tool.tool}
                    {tool.status && tool.status !== 'available' ? ` · ${tool.status}` : ''}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

const OperatorIssues: React.FC<{ summary: ClusterSummary | null }> = ({ summary }) => {
  const issues = summary?.operators.issues ?? [];
  if (!summary) {
    return <EmptyState label="ClusterOperator 상태를 아직 가져오지 못했습니다." />;
  }

  if (issues.length === 0) {
    return <EmptyState label="보고된 ClusterOperator 이슈가 없습니다." />;
  }

  return (
    <div className="komsco-ai-page__issue-list">
      {issues.slice(0, 4).map((issue) => (
        <div className="komsco-ai-page__issue" key={issue.name}>
          <ExclamationCircleIcon />
          <div>
            <strong>{issue.name}</strong>
            <span>{issue.reason || issue.message || 'operator condition requires review'}</span>
          </div>
        </div>
      ))}
    </div>
  );
};

const RecordTable: React.FC<{
  emptyLabel: string;
  records: AiopsRecord[];
  variant?: 'audit' | 'action';
}> = ({ emptyLabel, records, variant = 'action' }) => {
  if (records.length === 0) {
    return <EmptyState label={emptyLabel} />;
  }

  return (
    <div className="komsco-ai-page__table-wrap">
      <table className="komsco-ai-page__table">
        <thead>
          <tr>
            <th>시간</th>
            <th>이름</th>
            <th>{variant === 'audit' ? 'Action' : '상태'}</th>
            <th>{variant === 'audit' ? 'Run' : '대상'}</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record, index) => {
            const spec = asObject(record.spec);

            return (
              <tr key={`${record.kind ?? 'record'}-${record.metadata?.name ?? index}`}>
                <td>{formatTime(record.metadata?.createdAt)}</td>
                <td>
                  <code>{record.metadata?.name ?? record.kind ?? 'record'}</code>
                </td>
                <td>{variant === 'audit' ? textValue(spec.action) : recordPhase(record)}</td>
                <td>
                  {variant === 'audit'
                    ? textValue(spec.runId ?? spec.requestId)
                    : recordTarget(record)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

const ChatTranscriptTable: React.FC<{ records: AiopsRecord[] }> = ({ records }) => {
  if (records.length === 0) {
    return <EmptyState label="아직 조회 가능한 챗봇 대화기록이 없습니다." />;
  }

  return (
    <div className="komsco-ai-page__table-wrap">
      <table className="komsco-ai-page__table komsco-ai-page__table--chat">
        <thead>
          <tr>
            <th>시간</th>
            <th>질문</th>
            <th>답변</th>
            <th>Run</th>
          </tr>
        </thead>
        <tbody>
          {records.map((record, index) => {
            const spec = asObject(record.spec);

            return (
              <tr key={`${record.metadata?.name ?? 'chat'}-${index}`}>
                <td>{formatTime(record.metadata?.createdAt)}</td>
                <td>{safeEvidenceText(textValue(spec.userMessage), '질문 없음')}</td>
                <td>{safeEvidenceText(textValue(spec.assistantAnswer), '답변 없음')}</td>
                <td>
                  <code>{textValue(spec.runId ?? spec.requestId)}</code>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
};

export const AiopsDashboardPage: React.FC = () => {
  const data = useAiopsPageData();
  const assistantStageRef = React.useRef<HTMLElement | null>(null);
  const [assistantDraftPrompt, setAssistantDraftPrompt] = React.useState<
    AssistantDraftPromptRequest | undefined
  >();
  const [candidateActionBusyId, setCandidateActionBusyId] = React.useState('');
  const [candidateActionError, setCandidateActionError] = React.useState('');
  const [candidateActionNotice, setCandidateActionNotice] = React.useState('');
  const actionCount = actionRecords(data.status).length;
  const auditCount = data.status?.spec.records.auditRecords?.length ?? 0;
  const actionCountValue = data.status ? actionCount : '-';
  const auditCountValue = data.status ? auditCount : '-';
  const operatorIssueCount = data.summary?.operators.issues.length ?? 0;
  const operatorIssueValue = data.summary ? operatorIssueCount : '-';
  const readyNodes = data.summary ? `${data.summary.nodes.ready}/${data.summary.nodes.total}` : '-';
  const safetyMode = data.status?.spec.safetyContract?.mode ?? '상태 확인 중';
  const lightspeedProbe =
    data.status?.spec.safetyContract?.lightspeedStatus?.streamProbe ?? 'probe 확인 중';
  const controlTower = data.overview?.spec.controlTower;
  const focusAssistant = React.useCallback(() => {
    const stage = assistantStageRef.current;
    if (!stage) {
      return;
    }

    const alignStage = () => {
      const rect = stage.getBoundingClientRect();
      if (rect.top >= 0 && rect.top < window.innerHeight * 0.72) {
        return;
      }

      window.scrollTo({
        behavior: 'auto',
        top: rect.top + window.scrollY - 96,
      });

      let parent = stage.parentElement;
      while (parent) {
        const style = window.getComputedStyle(parent);
        const scrollable =
          /(auto|scroll)/.test(style.overflowY) && parent.scrollHeight > parent.clientHeight;
        if (scrollable) {
          const parentRect = parent.getBoundingClientRect();
          const nextRect = stage.getBoundingClientRect();
          parent.scrollTop += nextRect.top - parentRect.top - 72;
        }
        parent = parent.parentElement;
      }
    };

    stage.scrollIntoView({ behavior: 'auto', block: 'center' });
    alignStage();
    window.requestAnimationFrame(alignStage);
    window.setTimeout(() => {
      stage?.querySelector<HTMLElement>('.komsco-ai__input textarea, .komsco-ai__input')?.focus();
    }, 250);
  }, []);
  const activeDemoFindingId =
    typeof assistantDraftPrompt?.pageContext.findingId === 'string'
      ? assistantDraftPrompt.pageContext.findingId
      : undefined;
  const activeActionCandidateId =
    typeof assistantDraftPrompt?.pageContext.candidateId === 'string'
      ? assistantDraftPrompt.pageContext.candidateId
      : undefined;
  const seedFindingPrompt = React.useCallback(
    (finding: AiopsAnomalyFinding) => {
      const candidates = data.overview?.spec.actionCandidates?.spec?.candidates ?? [];
      const matchingCandidate = candidates.find((candidate) =>
        actionCandidateMatchesFinding(candidate, finding),
      );

      setAssistantDraftPrompt(buildFindingDemoDraft(finding, matchingCandidate));
      focusAssistant();
    },
    [data.overview, focusAssistant],
  );
  const seedActionCandidatePrompt = React.useCallback(
    (candidate: AiopsActionCandidate) => {
      setAssistantDraftPrompt(buildActionCandidatePrompt(candidate));
      focusAssistant();
    },
    [focusAssistant],
  );
  const handleCandidateAction = React.useCallback(
    async (candidate: AiopsActionCandidate, lifecycle: ActionCandidateLifecycleState) => {
      if (lifecycle.disabledReason) {
        return;
      }

      const busyId = `${lifecycle.action}:${candidate.id}`;
      setCandidateActionBusyId(busyId);
      setCandidateActionError('');
      setCandidateActionNotice('');

      try {
        if (lifecycle.action === 'create-plan') {
          const result = await createActionCandidatePlan(candidate);
          setCandidateActionNotice(
            `해결 계획 생성: ${result.spec?.planId ?? result.metadata?.name ?? candidate.id}`,
          );
        } else if (lifecycle.action === 'approve-plan') {
          if (!lifecycle.planId || !lifecycle.planDigest) {
            throw new Error('승인할 planId 또는 planDigest가 없습니다.');
          }
          await approveActionPlan(lifecycle.planId, lifecycle.planDigest);
          setCandidateActionNotice(`승인 완료: ${lifecycle.planId}`);
        } else if (lifecycle.action === 'execute-approval') {
          if (!lifecycle.approvalId || !lifecycle.planId || !lifecycle.planDigest) {
            throw new Error('실행할 approvalId, planId 또는 planDigest가 없습니다.');
          }
          await executeApprovedAction(
            lifecycle.approvalId,
            lifecycle.planId,
            lifecycle.planDigest,
          );
          setCandidateActionNotice(`실행 요청 완료: ${lifecycle.approvalId}`);
        }
      } catch (error) {
        setCandidateActionError(
          error instanceof Error ? error.message : 'AIOps 해결 버튼 처리 실패',
        );
      } finally {
        await data.refresh().catch(() => undefined);
        setCandidateActionBusyId('');
      }
    },
    [data],
  );

  return (
    <PageShell data={data} eyebrow="Cywell AI" icon={<ProductIcon />} title="Cywell AI">
      <button
        aria-label="Cywell AI 챗봇으로 이동"
        className="komsco-ai-page__assistant-quick-toggle"
        onClick={focusAssistant}
        title="Cywell AI 챗봇으로 이동"
        type="button"
      >
        <img alt="" src={kIcon} />
      </button>
      <section className="komsco-ai-page__overview">
        <div className="komsco-ai-page__overview-main">
          <HealthDial score={data.summary?.healthScore} />
          <div>
            <span className="komsco-ai-page__section-kicker">Cluster signal</span>
            <h2>Cywell AI 관제탑</h2>
            <p>
              {controlTower?.statusLabel ??
                '로컬 콘솔에서 회사 OCP API와 Gateway를 증거 우선 계약으로 연결합니다.'}
            </p>
          </div>
        </div>
        <div className="komsco-ai-page__overview-side">
          <span>View</span>
          <strong>Cywell AI 관제탑 / OpenShift 기본 대시보드와 분리</strong>
          <span>API</span>
          <strong>{data.summary?.apiUrl ?? '상태 확인 중'}</strong>
          <span>Version</span>
          <strong>{data.summary?.version.version ?? '상태 확인 중'}</strong>
          <span>Safety</span>
          <strong>{safetyMode}</strong>
          <span>Lightspeed stream</span>
          <strong>{lightspeedProbe}</strong>
        </div>
      </section>

      <OperatorFlowBoard data={data} />

      <div className="komsco-ai-page__metrics">
        <MetricTile
          detail="readiness ratio"
          icon={<ServerIcon />}
          label="Ready nodes"
          tone={!data.summary || data.summary.nodes.notReady ? 'warning' : 'success'}
          value={readyNodes}
        />
        <MetricTile
          detail="degraded or progressing"
          icon={<TachometerAltIcon />}
          label="Operator issues"
          tone={!data.summary || operatorIssueCount > 0 ? 'warning' : 'success'}
          value={operatorIssueValue}
        />
        <MetricTile
          detail="Gateway audit ledger"
          icon={<HistoryIcon />}
          label="Audit records"
          tone={data.status && auditCount > 0 ? 'info' : 'warning'}
          value={auditCountValue}
        />
        <MetricTile
          detail="approved lifecycle"
          icon={<BoltIcon />}
          label="Execution records"
          tone={data.status && actionCount > 0 ? 'info' : 'warning'}
          value={actionCountValue}
        />
      </div>

      <AnomalySummaryBoard
        activeFindingId={activeDemoFindingId}
        onAnalyzeFinding={seedFindingPrompt}
        overview={data.overview}
      />

      <ActionCandidateBoard
        activeCandidateId={activeActionCandidateId}
        actionBusyId={candidateActionBusyId}
        actionError={candidateActionError}
        actionNotice={candidateActionNotice}
        onCandidateAction={handleCandidateAction}
        onPlanCandidate={seedActionCandidatePrompt}
        overview={data.overview}
        status={data.status}
      />

      <DataSourceBoard overview={data.overview} />

      <CustomerTopologyPanel data={data} />

      <section
        ref={assistantStageRef}
        className="komsco-ai-page__assistant-stage"
        aria-label="Cywell AI assistant"
      >
        <AssistantLauncher
          defaultOpen
          draftPrompt={assistantDraftPrompt}
          embedded
          lockOpen
          onRunComplete={data.refresh}
        />
      </section>

      <div className="komsco-ai-page__dashboard-grid">
        <section className="komsco-ai-page__panel komsco-ai-page__panel--wide">
          <div className="komsco-ai-page__panel-heading">
            <ChartLineIcon />
            <h2>Evidence posture</h2>
          </div>
          <EvidenceRail status={data.status} />
        </section>
        <section className="komsco-ai-page__panel">
          <div className="komsco-ai-page__panel-heading">
            <RobotIcon />
            <h2>Lightspeed link</h2>
          </div>
          <LightspeedLink data={data} />
        </section>
        <section className="komsco-ai-page__panel">
          <div className="komsco-ai-page__panel-heading">
            <ProjectDiagramIcon />
            <h2>Tool Plan</h2>
          </div>
          <ToolPlanPanel status={data.status} />
        </section>
        <section className="komsco-ai-page__panel">
          <div className="komsco-ai-page__panel-heading">
            <ClipboardCheckIcon />
            <h2>RCA Context JSON</h2>
          </div>
          <RcaContextPanel status={data.status} />
        </section>
        <section className="komsco-ai-page__panel">
          <div className="komsco-ai-page__panel-heading">
            <ServerIcon />
            <h2>OS-aware adapters</h2>
          </div>
          <AdapterBoard status={data.status} />
        </section>
        <section className="komsco-ai-page__panel">
          <div className="komsco-ai-page__panel-heading">
            <ShieldAltIcon />
            <h2>Safety contract</h2>
          </div>
          <CapabilityBoard status={data.status} />
        </section>
        <section className="komsco-ai-page__panel">
          <div className="komsco-ai-page__panel-heading">
            <CubesIcon />
            <h2>Operator attention</h2>
          </div>
          <OperatorIssues summary={data.summary} />
        </section>
        <section className="komsco-ai-page__panel komsco-ai-page__panel--wide">
          <div className="komsco-ai-page__panel-heading">
            <ProjectDiagramIcon />
            <h2>최근 실행 기록</h2>
          </div>
          <RecordTable
            emptyLabel="최근 승인 또는 실행 기록이 없습니다."
            records={actionRecords(data.status).slice(0, 5)}
          />
        </section>
      </div>
    </PageShell>
  );
};

export const AiopsDocsPage: React.FC = () => {
  const data = useAiopsPageData();
  const fileInputRef = React.useRef<HTMLInputElement | null>(null);
  const [documents, setDocuments] = React.useState<RagUploadedDocument[]>([]);
  const [documentsReason, setDocumentsReason] = React.useState('');
  const [ragBackend, setRagBackend] = React.useState<RagBackendStatus | null>(null);
  const [documentsLoading, setDocumentsLoading] = React.useState(true);
  const [documentsError, setDocumentsError] = React.useState('');
  const [selectedDocumentId, setSelectedDocumentId] = React.useState('');
  const [previewLoading, setPreviewLoading] = React.useState(false);
  const [previewError, setPreviewError] = React.useState('');
  const [previewReason, setPreviewReason] = React.useState('');
  const [previewStatus, setPreviewStatus] = React.useState('idle');
  const [previewResults, setPreviewResults] = React.useState<RagSearchResultItem[]>([]);
  const [uploading, setUploading] = React.useState(false);
  const [uploadMessage, setUploadMessage] = React.useState('');

  const selectedDocument = React.useMemo(
    () =>
      documents.find((document) => document.documentId === selectedDocumentId) ||
      documents[0] ||
      null,
    [documents, selectedDocumentId],
  );

  const loadDocuments = React.useCallback(async () => {
    setDocumentsLoading(true);
    setDocumentsError('');
    try {
      const payload = await fetchUploadedRagDocuments();
      const nextDocuments = payload.spec.documents ?? [];
      setDocumentsReason(payload.spec.reason ?? '');
      setRagBackend(payload.spec.backend ?? null);
      setDocuments(nextDocuments);
      setSelectedDocumentId((current) => {
        if (current && nextDocuments.some((document) => document.documentId === current)) {
          return current;
        }
        return nextDocuments[0]?.documentId ?? '';
      });
    } catch (error) {
      setDocumentsError(
        error instanceof Error ? error.message : '업로드 문서 목록을 불러오지 못했습니다.',
      );
    } finally {
      setDocumentsLoading(false);
    }
  }, []);

  React.useEffect(() => {
    void loadDocuments();
  }, [loadDocuments]);

  React.useEffect(() => {
    if (!selectedDocument) {
      setPreviewStatus('idle');
      setPreviewReason('');
      setPreviewResults([]);
      setPreviewError('');
      setPreviewLoading(false);
      return undefined;
    }

    let disposed = false;
    setPreviewLoading(true);
    setPreviewError('');
    void searchRagDocuments({
      filters: {
        runbookIds: [selectedDocument.documentId],
      },
      includeContent: true,
      query: uploadedDocumentQuery(selectedDocument),
      topK: 8,
    })
      .then((payload) => {
        if (disposed) {
          return;
        }
        setPreviewStatus(payload.spec.status);
        setPreviewReason(payload.spec.reason ?? '');
        setPreviewResults(payload.spec.results ?? []);
      })
      .catch((error) => {
        if (disposed) {
          return;
        }
        setPreviewStatus('error');
        setPreviewReason('');
        setPreviewResults([]);
        setPreviewError(
          error instanceof Error ? error.message : 'RAG 적재 preview를 불러오지 못했습니다.',
        );
      })
      .finally(() => {
        if (!disposed) {
          setPreviewLoading(false);
        }
      });

    return () => {
      disposed = true;
    };
  }, [selectedDocument]);

  const handleUploadChange = React.useCallback(
    async (event: React.ChangeEvent<HTMLInputElement>) => {
      const files = Array.from(event.currentTarget.files ?? []);
      event.currentTarget.value = '';
      if (files.length === 0) {
        return;
      }

      setUploading(true);
      setUploadMessage('');
      try {
        const uploaded = await Promise.all(
          files.map((file) =>
            uploadRagDocumentFile(file, {
              labels: { source: 'docs-page', version: 'v0.1.5' },
              namespace: 'komsco-ai-kugnus',
              sourceType: 'user-upload',
              version: 'v0.1.5',
            }),
          ),
        );
        const firstDocumentId = uploaded[0]?.spec.document.documentId ?? '';
        setUploadMessage(`${uploaded.length}개 문서를 RAG 저장소에 등록했습니다.`);
        await loadDocuments();
        if (firstDocumentId) {
          setSelectedDocumentId(firstDocumentId);
        }
      } catch (error) {
        setUploadMessage(error instanceof Error ? error.message : '문서 업로드에 실패했습니다.');
      } finally {
        setUploading(false);
      }
    },
    [loadDocuments],
  );

  const totalChunks = documents.reduce((total, document) => total + (document.chunkCount ?? 0), 0);
  const totalBytes = documents.reduce((total, document) => total + (document.contentBytes ?? 0), 0);
  const activeRagBackend = ragBackend ?? data.status?.spec.capabilities.rag ?? null;
  const ragStatus = activeRagBackend?.status ?? (documentsLoading ? 'checking' : 'unknown');

  return (
    <PageShell data={data} eyebrow="Cywell AI" icon={<ClipboardCheckIcon />} title="LLM Wiki">
      <section className="komsco-ai-page__docs-hero">
        <div>
          <span className="komsco-ai-page__section-kicker">Customer LLM Wiki</span>
          <h2>고객 지식/RAG 저장소</h2>
          <p>
            고객 문서를 업로드하고 pgvector RAG 적재, ACL, 검색 가능한 chunk preview를 확인합니다.
          </p>
        </div>
        <div className="komsco-ai-page__docs-actions">
          <input
            accept={DOCS_UPLOAD_ACCEPT}
            className="komsco-ai-page__docs-file-input"
            multiple
            onChange={handleUploadChange}
            ref={fileInputRef}
            type="file"
          />
          <Button
            isDisabled={uploading}
            onClick={() => fileInputRef.current?.click()}
            variant="primary"
          >
            {uploading ? '업로드 중' : '문서 업로드'}
          </Button>
          <Button
            isDisabled={documentsLoading}
            onClick={() => void loadDocuments()}
            variant="secondary"
          >
            목록 새로고침
          </Button>
        </div>
      </section>

      {uploadMessage && <div className="komsco-ai-page__docs-notice">{uploadMessage}</div>}
      {documentsError && <div className="komsco-ai-page__error">{documentsError}</div>}
      {!documentsError && documentsReason && (
        <div className="komsco-ai-page__docs-status-line">{documentsReason}</div>
      )}

      <div className="komsco-ai-page__metrics">
        <MetricTile
          detail={activeRagBackend?.collection || activeRagBackend?.backendType || 'gateway-only'}
          icon={<ServerIcon />}
          label="RAG backend"
          tone={ragBackendTone(activeRagBackend?.status)}
          value={ragStatus}
        />
        <MetricTile
          detail="visible to current OpenShift subject"
          icon={<ClipboardCheckIcon />}
          label="Documents"
          tone={documents.length > 0 ? 'success' : 'warning'}
          value={documentsLoading ? '...' : documents.length}
        />
        <MetricTile
          detail="retrievable RAG chunks"
          icon={<ProjectDiagramIcon />}
          label="Chunks"
          tone={totalChunks > 0 ? 'success' : 'warning'}
          value={documentsLoading ? '...' : totalChunks}
        />
        <MetricTile
          detail={activeRagBackend?.accessPath || 'gateway-only'}
          icon={<LockIcon />}
          label="ACL"
          tone={activeRagBackend?.aclRequired === false ? 'warning' : 'success'}
          value={activeRagBackend?.aclRequired === false ? 'OFF' : 'ON'}
        />
        <MetricTile
          detail="redacted preview only"
          icon={<ShieldAltIcon />}
          label="Raw content"
          tone="success"
          value="HIDDEN"
        />
        <MetricTile
          detail="stored content size"
          icon={<ServerIcon />}
          label="Size"
          tone={totalBytes > 0 ? 'info' : 'warning'}
          value={formatBytes(totalBytes)}
        />
      </div>

      <section className="komsco-ai-page__docs-layout">
        <div className="komsco-ai-page__panel komsco-ai-page__docs-list-panel">
          <div className="komsco-ai-page__panel-heading">
            <ClipboardCheckIcon />
            <h2>업로드 목록</h2>
          </div>
          {documentsLoading && documents.length === 0 ? (
            <EmptyState label="업로드 문서를 확인하는 중입니다." />
          ) : documents.length === 0 ? (
            <EmptyState label="아직 업로드된 문서가 없습니다." />
          ) : (
            <div className="komsco-ai-page__docs-list">
              {documents.map((document) => (
                <button
                  className={`komsco-ai-page__docs-item${
                    selectedDocument?.documentId === document.documentId
                      ? ' komsco-ai-page__docs-item--active'
                      : ''
                  }`}
                  key={document.documentId}
                  onClick={() => setSelectedDocumentId(document.documentId)}
                  type="button"
                >
                  <strong>{document.title}</strong>
                  <span>{document.sourceUri || document.documentId}</span>
                  <small>
                    {document.chunkCount ?? 0} chunks · {formatBytes(document.contentBytes)} ·{' '}
                    {formatTime(document.updatedAt || document.ingestedAt)}
                  </small>
                </button>
              ))}
            </div>
          )}
        </div>

        <div className="komsco-ai-page__panel komsco-ai-page__docs-viewer">
          <div className="komsco-ai-page__panel-heading">
            <ProjectDiagramIcon />
            <h2>적재 문서 뷰어</h2>
          </div>
          {!selectedDocument ? (
            <EmptyState label="문서를 선택하면 RAG 적재 상태가 표시됩니다." />
          ) : (
            <>
              <div className="komsco-ai-page__docs-detail">
                <div>
                  <span>문서명</span>
                  <strong>{selectedDocument.title}</strong>
                </div>
                <div>
                  <span>Document ID</span>
                  <strong>{selectedDocument.documentId}</strong>
                </div>
                <div>
                  <span>형식</span>
                  <strong>{selectedDocument.mimeType || selectedDocument.sourceType || '-'}</strong>
                </div>
                <div>
                  <span>Checksum</span>
                  <strong>{compactDigest(selectedDocument.checksum)}</strong>
                </div>
                <div>
                  <span>권한</span>
                  <strong>
                    {(selectedDocument.aclGroups ?? []).slice(0, 3).join(', ') ||
                      'current user scope'}
                  </strong>
                </div>
                <div>
                  <span>상태</span>
                  <strong>{previewLoading ? 'checking' : previewStatus}</strong>
                </div>
              </div>

              <div className="komsco-ai-page__docs-safety">
                원본 전체 파일을 그대로 노출하지 않고, Gateway가 반환한 redacted RAG chunk preview만
                표시합니다.
              </div>

              {previewLoading ? (
                <EmptyState label="적재 chunk를 확인하는 중입니다." />
              ) : previewError ? (
                <div className="komsco-ai-page__error">{previewError}</div>
              ) : previewResults.length === 0 ? (
                <EmptyState
                  label={previewReason || '검색 가능한 적재 chunk가 아직 확인되지 않았습니다.'}
                />
              ) : (
                <div className="komsco-ai-page__docs-preview-list">
                  {previewResults.map((result, index) => (
                    <article
                      className="komsco-ai-page__docs-preview"
                      key={result.id || `${result.documentId}-${index}`}
                    >
                      <div className="komsco-ai-page__docs-preview-head">
                        <strong>{result.title || selectedDocument.title}</strong>
                        <span>
                          score {typeof result.score === 'number' ? result.score.toFixed(3) : '-'}
                        </span>
                      </div>
                      <p>
                        {safeEvidenceText(
                          result.content || result.contentPreview || 'preview 없음',
                        )}
                      </p>
                      <small>{result.sourceUri || result.id || result.documentId}</small>
                    </article>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      </section>
    </PageShell>
  );
};

export const AiopsAuditPage: React.FC = () => {
  const data = useAiopsPageData();

  return (
    <PageShell data={data} eyebrow="Cywell AI" icon={<HistoryIcon />} title="감사 기록">
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <RobotIcon />
          <h2>최근 챗봇 대화기록</h2>
        </div>
        <ChatTranscriptTable records={chatTranscriptRecords(data.status)} />
      </section>
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <HistoryIcon />
          <h2>최근 Gateway 감사 레코드</h2>
        </div>
        <RecordTable
          emptyLabel="아직 조회 가능한 감사 기록이 없습니다."
          records={data.status?.spec.records.auditRecords ?? []}
          variant="audit"
        />
      </section>
    </PageShell>
  );
};

export const AiopsExecutionRecordsPage: React.FC = () => {
  const data = useAiopsPageData();

  return (
    <PageShell data={data} eyebrow="Cywell AI" icon={<ClipboardCheckIcon />} title="실행 기록">
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <ClipboardCheckIcon />
          <h2>승인·실행 라이프사이클</h2>
        </div>
        <RecordTable
          emptyLabel="최근 승인 또는 실행 기록이 없습니다."
          records={actionRecords(data.status)}
        />
      </section>
    </PageShell>
  );
};

export const AiopsPolicyPage: React.FC = () => {
  const data = useAiopsPageData();
  const capabilities = data.status?.spec.capabilities;
  const contract = data.status?.spec.safetyContract;

  return (
    <PageShell data={data} eyebrow="Cywell AI" icon={<ShieldAltIcon />} title="정책">
      <div className="komsco-ai-page__metrics">
        <MetricTile
          detail="host diagnostics collector"
          icon={<ServerIcon />}
          label="Diagnostics"
          tone={!data.status ? 'warning' : capabilities?.diagnosticsEnabled ? 'info' : 'warning'}
          value={!data.status ? 'PENDING' : capabilities?.diagnosticsEnabled ? 'ON' : 'OFF'}
        />
        <MetricTile
          detail="cluster mutation gate"
          icon={<ShieldAltIcon />}
          label="Mutations"
          tone={!data.status ? 'warning' : capabilities?.mutationsEnabled ? 'danger' : 'success'}
          value={!data.status ? 'PENDING' : capabilities?.mutationsEnabled ? 'ON' : 'OFF'}
        />
        <MetricTile
          detail="approval execution path"
          icon={<BoltIcon />}
          label="Action Executor"
          tone={
            !data.status
              ? 'warning'
              : capabilities?.actionExecutorConfigured
                ? 'success'
                : 'warning'
          }
          value={
            !data.status
              ? 'PENDING'
              : capabilities?.actionExecutorConfigured
                ? 'CONNECTED'
                : 'NOT CONFIGURED'
          }
        />
        <MetricTile
          detail="raw command execution"
          icon={<LockIcon />}
          label="Unrestricted"
          tone={
            !data.status
              ? 'warning'
              : capabilities?.unrestrictedCommandsEnabled
                ? 'danger'
                : 'success'
          }
          value={
            !data.status ? 'PENDING' : capabilities?.unrestrictedCommandsEnabled ? 'ON' : 'OFF'
          }
        />
      </div>
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <ShieldAltIcon />
          <h2>현재 안전 계약</h2>
        </div>
        <div className="komsco-ai-page__policy-list">
          <div>
            <CheckCircleIcon />
            <span>
              허용 읽기 동작:{' '}
              {(contract?.allowedReadOnlyVerbs ?? ['get', 'list', 'watch']).join(', ')}
            </span>
          </div>
          <div>
            <ExclamationTriangleIcon />
            <span>
              금지 동작:{' '}
              {(contract?.forbiddenActions ?? ['create', 'update', 'patch', 'delete']).join(', ')}
            </span>
          </div>
          <div>
            <HistoryIcon />
            <span>
              감사 기록은 Gateway 요청/완료/실패 및 실행 이벤트를 사용자 권한 기준으로 표시합니다.
            </span>
          </div>
        </div>
      </section>
    </PageShell>
  );
};
