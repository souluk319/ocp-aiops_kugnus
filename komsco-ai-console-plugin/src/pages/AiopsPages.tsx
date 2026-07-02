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
import {
  type ActionCandidateLifecycleState,
  type AssistantDraftPromptRequest,
  ActionCandidateBoard,
  AnomalySummaryBoard,
  OperatorFlowBoard,
  actionCandidateMatchesFinding,
  buildActionCandidatePrompt,
  buildFindingDemoDraft,
} from './AiopsDashboardSections';
import { DocsHero, DocsLayout, DocsMetrics, uploadedDocumentQuery } from './AiopsDocsSections';
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
    ? value.filter(
        (item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object',
      )
    : [];

const compactToolName = (value: unknown): string => textValue(value).replace(/_/g, ' ');

const compactDigest = (value?: string): string => {
  if (!value) {
    return '';
  }

  return value.length > 28 ? `${value.slice(0, 24)}...` : value;
};

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

const dataSourceTone = (status?: string): Tone => {
  if (status === 'available') {
    return 'success';
  }
  if (status === 'error') {
    return 'danger';
  }
  return 'warning';
};

const runtimeModeLabel = (mode?: string): string => {
  if (mode === 'read-only' || mode === 'read_only') {
    return '읽기 전용';
  }
  if (mode === 'execute') {
    return '실행 가능';
  }
  if (mode === 'controlled_execution') {
    return '승인 실행';
  }
  if (mode === 'evidence_check') {
    return '증거 확인';
  }
  if (mode === 'unrestricted') {
    return '무제한 실행';
  }
  return mode || '상태 확인 중';
};

const probeStatusLabel = (status?: string): string => {
  if (status === 'succeeded' || status === 'available') {
    return '정상';
  }
  if (status === 'failed' || status === 'error') {
    return '확인 필요';
  }
  if (status === 'partial') {
    return '일부 제한';
  }
  if (status === 'probe pending' || status === 'checking') {
    return '확인 중';
  }
  return status || '확인 중';
};

const onOffLabel = (value?: boolean): string => {
  if (value === undefined) {
    return '확인 중';
  }
  return value ? '켜짐' : '꺼짐';
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
      detail: overview
        ? `데이터 소스 ${availableSources}/${dataSources.length}`
        : 'overview 수집 중',
      icon: <ChartLineIcon />,
      label: '관측 신호',
      tone: overview && availableSources === dataSources.length ? 'success' : 'warning',
      value: overview?.spec.controlTower.statusLabel ?? '확인 중',
    },
    {
      detail: rag?.collection || rag?.backendType || rag?.reason || 'RAG backend 확인 중',
      icon: <ClipboardCheckIcon />,
      label: '지식 저장소',
      tone: ragBackendTone(rag?.status),
      value: probeStatusLabel(rag?.status),
    },
    {
      detail: lightspeed?.baseService ?? 'openshift-lightspeed',
      icon: <RobotIcon />,
      label: '답변 경로',
      tone: lightspeed?.fallbackActive ? 'warning' : status ? 'info' : 'warning',
      value: probeStatusLabel(lightspeed?.streamProbe),
    },
    {
      detail: `감사 기록 ${auditCount}건`,
      icon: <ShieldAltIcon />,
      label: '정책/감사',
      tone: status ? (mutationEnabled ? 'danger' : 'success') : 'warning',
      value: runtimeModeLabel(status?.spec.safetyContract?.mode),
    },
  ] as const;

  return (
    <section
      className="komsco-ai-page__customer-topology"
      aria-label="Customer operations topology"
    >
      <div className="komsco-ai-page__customer-topology-head">
        <div>
          <span className="komsco-ai-page__section-kicker">운영 토폴로지</span>
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
          <span>대기</span>
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
        <span>점수</span>
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
                {collected ? `${item.count}건 수집` : item.reason || '아직 수집되지 않음'}
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
      label: '승인 실행기',
      value: statusLoaded
        ? capabilities?.actionExecutorConfigured
          ? '연결됨'
          : '미설정'
        : '상태 확인 중',
      tone: statusLoaded ? statusTone(Boolean(capabilities?.actionExecutorConfigured)) : 'warning',
    },
    {
      label: '진단 수집',
      value: statusLoaded ? onOffLabel(capabilities?.diagnosticsEnabled) : '상태 확인 중',
      tone: statusLoaded && capabilities?.diagnosticsEnabled ? 'info' : 'warning',
    },
    {
      label: '기록 저장',
      value: statusLoaded
        ? capabilities?.recordStoreEnabled
          ? '영구 저장'
          : '메모리'
        : '상태 확인 중',
      tone: statusLoaded && capabilities?.recordStoreEnabled ? 'success' : 'warning',
    },
    {
      label: '런북 검색',
      value: statusLoaded ? probeStatusLabel(capabilities?.rag?.status) : '상태 확인 중',
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
            ? '증거 확인 우선'
            : contract?.mode
              ? '승인 기반 실행'
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
              ? 'Gateway 우회 응답 사용 중'
              : gatewayStatusLoaded
                ? 'Gateway 상태 확인됨'
                : 'Gateway 상태 확인 중'}
          </strong>
          <span>
            {probeStatusLabel(streamProbe)}
            {lightspeedStatus?.lastStatus
              ? ` / ${probeStatusLabel(lightspeedStatus.lastStatus)}`
              : ''}
          </span>
        </div>
      </div>
      {contextDigest && (
        <div className="komsco-ai-page__endpoint-line">
          <span>Gateway 문맥</span>
          <code>{contextDigest}</code>
        </div>
      )}
      {lightspeedStatus?.lastError && (
        <div className="komsco-ai-page__endpoint-line">
          <span>최근 우회 사유</span>
          <code>{lightspeedStatus.lastError}</code>
        </div>
      )}
      <div className="komsco-ai-page__endpoint-line">
        <span>답변 서비스</span>
        <code>{baseService}</code>
      </div>
      <div className="komsco-ai-page__endpoint-line">
        <span>콘솔 플러그인</span>
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
              reason:
                '첫 질문 전에는 현재 콘솔 컨텍스트와 접근 가능한 리소스를 확인할 준비 상태를 표시',
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
          <strong>
            {textValue(executionPolicy.mode, textValue(contract.mode, 'evidence_check'))}
          </strong>
        </div>
        <div>
          <span>검증</span>
          <strong>
            {validationOk ? 'evidence-check 통과' : textValue(toolPlanStatus.status, '대기')}
          </strong>
        </div>
      </div>
      {steps.length > 0 ? (
        <ol className="komsco-ai-page__tool-plan-steps" aria-label="Tool Plan 증거 수집 단계">
          {steps.map((step, index) => {
            const adapter = adapterForStep(step, index);
            const resolved = adapter?.resolved === true;
            const statusLabel = resolved
              ? 'adapter 연결됨'
              : textValue(adapter?.status, '확인 대기');
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
          <code>
            {contextStatus.digest ?? contextStatus.status ?? 'waiting_for_first_question'}
          </code>
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

const RecordList: React.FC<{
  emptyLabel: string;
  records: AiopsRecord[];
  variant?: 'audit' | 'action';
}> = ({ emptyLabel, records, variant = 'action' }) => {
  if (records.length === 0) {
    return <EmptyState label={emptyLabel} />;
  }

  return (
    <div className="komsco-ai-page__record-list">
      {records.map((record, index) => {
        const spec = asObject(record.spec);
        const name = record.metadata?.name ?? record.kind ?? 'record';
        const phase = variant === 'audit' ? textValue(spec.action) : recordPhase(record);
        const target =
          variant === 'audit' ? textValue(spec.runId ?? spec.requestId) : recordTarget(record);

        return (
          <article
            className="komsco-ai-page__record-card"
            key={`${record.kind ?? 'record'}-${name}-${index}`}
          >
            <div className="komsco-ai-page__record-card-head">
              <span>{formatTime(record.metadata?.createdAt)}</span>
              <strong>{phase}</strong>
            </div>
            <code>{name}</code>
            <dl>
              <dt>{variant === 'audit' ? 'Run' : '대상'}</dt>
              <dd>{target}</dd>
            </dl>
          </article>
        );
      })}
    </div>
  );
};

const ChatTranscriptList: React.FC<{ records: AiopsRecord[] }> = ({ records }) => {
  if (records.length === 0) {
    return <EmptyState label="아직 조회 가능한 챗봇 대화기록이 없습니다." />;
  }

  return (
    <div className="komsco-ai-page__chat-log-list">
      {records.map((record, index) => {
        const spec = asObject(record.spec);
        const userMessage = safeEvidenceText(textValue(spec.userMessage), '질문 없음');
        const assistantAnswer = safeEvidenceText(textValue(spec.assistantAnswer), '답변 없음');

        return (
          <article
            className="komsco-ai-page__chat-log-card"
            key={`${record.metadata?.name ?? 'chat'}-${index}`}
          >
            <div className="komsco-ai-page__record-card-head">
              <span>{formatTime(record.metadata?.createdAt)}</span>
              <code>{textValue(spec.runId ?? spec.requestId)}</code>
            </div>
            <dl>
              <dt>질문</dt>
              <dd>{userMessage}</dd>
              <dt>답변</dt>
              <dd>{assistantAnswer}</dd>
            </dl>
          </article>
        );
      })}
    </div>
  );
};

export const AiopsDashboardPage: React.FC = () => {
  const data = useAiopsPageData();
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
  const safetyMode = runtimeModeLabel(data.status?.spec.safetyContract?.mode);
  const lightspeedProbe =
    data.status?.spec.safetyContract?.lightspeedStatus?.streamProbe ?? 'probe 확인 중';
  const controlTower = data.overview?.spec.controlTower;
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
    },
    [data.overview],
  );
  const seedActionCandidatePrompt = React.useCallback((candidate: AiopsActionCandidate) => {
    setAssistantDraftPrompt(buildActionCandidatePrompt(candidate));
  }, []);
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
          await executeApprovedAction(lifecycle.approvalId, lifecycle.planId, lifecycle.planDigest);
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
      <section className="komsco-ai-page__overview">
        <div className="komsco-ai-page__overview-main">
          <HealthDial score={data.summary?.healthScore} />
          <div>
            <span className="komsco-ai-page__section-kicker">클러스터 신호</span>
            <h2>Cywell AI 관제탑</h2>
            <p>
              {controlTower?.statusLabel ??
                '회사 OCP API와 Gateway에서 수집한 운영 신호를 요약합니다.'}
            </p>
          </div>
        </div>
        <div className="komsco-ai-page__overview-side">
          <span>화면</span>
          <strong>운영 요약과 우선 조치 후보</strong>
          <span>API</span>
          <strong>{data.summary?.apiUrl ?? '상태 확인 중'}</strong>
          <span>버전</span>
          <strong>{data.summary?.version.version ?? '상태 확인 중'}</strong>
          <span>실행 정책</span>
          <strong>{safetyMode}</strong>
          <span>답변 경로</span>
          <strong>{probeStatusLabel(lightspeedProbe)}</strong>
        </div>
      </section>

      <OperatorFlowBoard data={data} />

      <div className="komsco-ai-page__metrics">
        <MetricTile
          detail="readiness ratio"
          icon={<ServerIcon />}
          label="정상 노드"
          tone={!data.summary || data.summary.nodes.notReady ? 'warning' : 'success'}
          value={readyNodes}
        />
        <MetricTile
          detail="degraded/progressing"
          icon={<TachometerAltIcon />}
          label="Operator 이상"
          tone={!data.summary || operatorIssueCount > 0 ? 'warning' : 'success'}
          value={operatorIssueValue}
        />
        <MetricTile
          detail="Gateway 감사 기록"
          icon={<HistoryIcon />}
          label="감사 기록"
          tone={data.status && auditCount > 0 ? 'info' : 'warning'}
          value={auditCountValue}
        />
        <MetricTile
          detail="승인/실행 단계"
          icon={<BoltIcon />}
          label="실행 기록"
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

      <AssistantLauncher draftPrompt={assistantDraftPrompt} onRunComplete={data.refresh} />
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
  const documentsReasonLabel = documentsReason.includes('Uploaded RAG documents retrieved')
    ? 'RAG 저장소에서 문서 목록을 불러왔습니다.'
    : documentsReason;

  return (
    <PageShell data={data} eyebrow="Cywell AI" icon={<ClipboardCheckIcon />} title="고객 문서">
      <DocsHero
        fileInputRef={fileInputRef}
        loading={documentsLoading}
        onRefresh={() => void loadDocuments()}
        onUploadChange={handleUploadChange}
        uploading={uploading}
      />

      {uploadMessage && <div className="komsco-ai-page__docs-notice">{uploadMessage}</div>}
      {documentsError && <div className="komsco-ai-page__error">{documentsError}</div>}
      {!documentsError && documentsReasonLabel && (
        <div className="komsco-ai-page__docs-status-line">{documentsReasonLabel}</div>
      )}

      <DocsMetrics
        activeRagBackend={activeRagBackend}
        documents={documents}
        documentsLoading={documentsLoading}
        ragStatus={ragStatus}
        totalBytes={totalBytes}
        totalChunks={totalChunks}
      />

      <DocsLayout
        documents={documents}
        documentsLoading={documentsLoading}
        onSelectDocument={setSelectedDocumentId}
        previewError={previewError}
        previewLoading={previewLoading}
        previewReason={previewReason}
        previewResults={previewResults}
        previewStatus={previewStatus}
        selectedDocument={selectedDocument}
      />
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
        <ChatTranscriptList records={chatTranscriptRecords(data.status)} />
      </section>
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <HistoryIcon />
          <h2>최근 Gateway 감사 레코드</h2>
        </div>
        <RecordList
          emptyLabel="아직 조회 가능한 감사 기록이 없습니다."
          records={data.status?.spec.records.auditRecords ?? []}
          variant="audit"
        />
      </section>
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <ChartLineIcon />
          <h2>근거 수집 상태</h2>
        </div>
        <EvidenceRail status={data.status} />
      </section>
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <RobotIcon />
          <h2>답변 경로</h2>
        </div>
        <LightspeedLink data={data} />
      </section>
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <ProjectDiagramIcon />
          <h2>원본 Tool Plan JSON</h2>
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
          <h2>어댑터 상태</h2>
        </div>
        <AdapterBoard status={data.status} />
      </section>
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <ShieldAltIcon />
          <h2>안전 계약</h2>
        </div>
        <CapabilityBoard status={data.status} />
      </section>
      <DataSourceBoard overview={data.overview} />
      <CustomerTopologyPanel data={data} />
      <section className="komsco-ai-page__panel">
        <div className="komsco-ai-page__panel-heading">
          <CubesIcon />
          <h2>Operator 상태</h2>
        </div>
        <OperatorIssues summary={data.summary} />
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
        <RecordList
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
          detail="호스트 진단 수집기"
          icon={<ServerIcon />}
          label="진단 수집"
          tone={!data.status ? 'warning' : capabilities?.diagnosticsEnabled ? 'info' : 'warning'}
          value={!data.status ? '확인 중' : onOffLabel(capabilities?.diagnosticsEnabled)}
        />
        <MetricTile
          detail="클러스터 변경 허용 상태"
          icon={<ShieldAltIcon />}
          label="변경 게이트"
          tone={!data.status ? 'warning' : capabilities?.mutationsEnabled ? 'danger' : 'success'}
          value={!data.status ? '확인 중' : capabilities?.mutationsEnabled ? '열림' : '닫힘'}
        />
        <MetricTile
          detail="승인 후 실행 경로"
          icon={<BoltIcon />}
          label="승인 실행"
          tone={
            !data.status
              ? 'warning'
              : capabilities?.actionExecutorConfigured
                ? 'success'
                : 'warning'
          }
          value={
            !data.status ? '확인 중' : capabilities?.actionExecutorConfigured ? '연결됨' : '미설정'
          }
        />
        <MetricTile
          detail="서버 허용 여부"
          icon={<LockIcon />}
          label="무제한 실행"
          tone={
            !data.status
              ? 'warning'
              : capabilities?.unrestrictedCommandsEnabled
                ? 'danger'
                : 'success'
          }
          value={!data.status ? '확인 중' : onOffLabel(capabilities?.unrestrictedCommandsEnabled)}
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
