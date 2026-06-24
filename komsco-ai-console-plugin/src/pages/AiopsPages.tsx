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
  type AiopsRecord,
  type AiopsRuntimeStatus,
  type ClusterSummary,
  fetchAiopsStatus,
  fetchClusterSummary,
} from '../services/aiGateway';
import AssistantLauncher from '../components/AssistantLauncher';
import kIcon from '../assets/k_icon.png';
import './aiops-pages.css';

type AiopsPageData = {
  error: string;
  loading: boolean;
  refresh: () => Promise<void>;
  status: AiopsRuntimeStatus | null;
  summary: ClusterSummary | null;
};

type Tone = 'danger' | 'info' | 'success' | 'warning';

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

const useAiopsPageData = (): AiopsPageData => {
  const [summary, setSummary] = React.useState<ClusterSummary | null>(null);
  const [status, setStatus] = React.useState<AiopsRuntimeStatus | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState('');

  const refresh = React.useCallback(async () => {
    setLoading(true);
    const [summaryResult, statusResult] = await Promise.allSettled([
      fetchClusterSummary(),
      fetchAiopsStatus(),
    ]);

    if (summaryResult.status === 'fulfilled') {
      setSummary(summaryResult.value);
    }

    if (statusResult.status === 'fulfilled') {
      setStatus(statusResult.value);
    }

    const errors = [summaryResult, statusResult]
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) => (result.reason instanceof Error ? result.reason.message : String(result.reason)));

    setError(errors.join('\n'));
    setLoading(false);
  }, []);

  React.useEffect(() => {
    void refresh();
  }, [refresh]);

  return { error, loading, refresh, status, summary };
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
    {data.loading && !data.status && !data.summary ? (
      <div className="komsco-ai-page__loading">
        <Spinner size="lg" />
      </div>
    ) : (
      children
    )}
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
                {collected
                  ? `${item.count} collected`
                  : item.reason || 'not collected yet'}
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
      label: 'Mutation gate',
      value: statusLoaded ? (capabilities?.mutationsEnabled ? 'enabled' : 'read-only') : 'status pending',
      tone: statusLoaded ? statusTone(!capabilities?.mutationsEnabled) : 'warning',
    },
    {
      label: 'Action executor',
      value: statusLoaded ? (capabilities?.actionExecutorConfigured ? 'connected' : 'not configured') : 'status pending',
      tone: statusLoaded ? statusTone(Boolean(capabilities?.actionExecutorConfigured)) : 'warning',
    },
    {
      label: 'Diagnostics',
      value: statusLoaded ? (capabilities?.diagnosticsEnabled ? 'enabled' : 'off') : 'status pending',
      tone: statusLoaded && capabilities?.diagnosticsEnabled ? 'info' : 'warning',
    },
    {
      label: 'Record ledger',
      value: statusLoaded ? (capabilities?.recordStoreEnabled ? 'on' : 'memory') : 'status pending',
      tone: statusLoaded && capabilities?.recordStoreEnabled ? 'success' : 'warning',
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
          {contract?.mode === 'read_only'
            ? 'read-only contract active'
            : contract?.mode
              ? 'controlled execution contract active'
              : 'safety contract not loaded'}
        </span>
      </div>
    </div>
  );
};

const LightspeedLink: React.FC<{ data: AiopsPageData }> = ({ data }) => {
  const lightspeedStatus = data.status?.spec.safetyContract?.lightspeedStatus;
  const gatewayStatusLoaded = Boolean(data.status) && !data.error;
  const baseService = lightspeedStatus?.baseService ?? 'openshift-lightspeed/lightspeed-app-server:8443';

  return (
    <div className="komsco-ai-page__signal-stack">
      <div className={`komsco-ai-page__signal is-${gatewayStatusLoaded ? 'info' : 'warning'}`}>
        <span className={`komsco-ai-page__status-dot ${gatewayStatusLoaded ? 'is-info' : 'is-warn'}`} />
        <div>
          <strong>{gatewayStatusLoaded ? 'Gateway status loaded' : 'Gateway status pending'}</strong>
          <span>
            {lightspeedStatus?.streamProbe ?? 'Lightspeed stream probe not completed by status endpoint'}
          </span>
        </div>
      </div>
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
    toolPlanStatus.latestRuntimePlan &&
    typeof toolPlanStatus.latestRuntimePlan === 'object'
      ? toolPlanStatus.latestRuntimePlan
      : {
          source: toolPlanStatus.source,
          status: toolPlanStatus.status,
          latest_runtime_plan: toolPlanStatus.latestRuntimePlan ?? 'waiting_for_first_question',
          execution_policy: { mode: contract.mode },
          allowed_verbs: contract.allowedReadOnlyVerbs,
          forbidden_actions: contract.forbiddenActions,
        };

  return (
    <div className="komsco-ai-page__tool-plan">
      <pre>{JSON.stringify(plan, null, 2)}</pre>
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
      <pre>{JSON.stringify(context, null, 2)}</pre>
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
          <div>
            <strong>{adapter.name}</strong>
            <span>{adapter.detail}</span>
          </div>
          <code>{adapter.status}</code>
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
                <td>{variant === 'audit' ? textValue(spec.runId ?? spec.requestId) : recordTarget(record)}</td>
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
  const actionCount = actionRecords(data.status).length;
  const auditCount = data.status?.spec.records.auditRecords?.length ?? 0;
  const actionCountValue = data.status ? actionCount : '-';
  const auditCountValue = data.status ? auditCount : '-';
  const operatorIssueCount = data.summary?.operators.issues.length ?? 0;
  const operatorIssueValue = data.summary ? operatorIssueCount : '-';
  const readyNodes = data.summary
    ? `${data.summary.nodes.ready}/${data.summary.nodes.total}`
    : '-';
  const safetyMode = data.status?.spec.safetyContract?.mode ?? 'status pending';
  const lightspeedProbe =
    data.status?.spec.safetyContract?.lightspeedStatus?.streamProbe ?? 'probe pending';
  const focusAssistant = React.useCallback(() => {
    assistantStageRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    window.setTimeout(() => {
      assistantStageRef.current
        ?.querySelector<HTMLElement>('.komsco-ai__input textarea, .komsco-ai__input')
        ?.focus();
    }, 250);
  }, []);

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
            <h2>증거 기반 OpenShift 관제 대시보드</h2>
            <p>
              현재 화면은 로컬 콘솔에서 회사 OCP API와 Gateway를 읽기전용 우선 계약으로 연결해
              상태, 근거, 감사 흐름을 확인합니다.
            </p>
          </div>
        </div>
        <div className="komsco-ai-page__overview-side">
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
          detail="proposal to execution"
          icon={<BoltIcon />}
          label="Action records"
          tone={data.status && actionCount > 0 ? 'info' : 'warning'}
          value={actionCountValue}
        />
      </div>

      <section
        ref={assistantStageRef}
        className="komsco-ai-page__assistant-stage"
        aria-label="Cywell AI assistant"
      >
        <AssistantLauncher defaultOpen embedded lockOpen />
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
            <h2>Tool Plan JSON</h2>
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

export const AiopsAuditPage: React.FC = () => {
  const data = useAiopsPageData();

  return (
    <PageShell data={data} eyebrow="Cywell AI" icon={<HistoryIcon />} title="감사 기록">
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
    <PageShell
      data={data}
      eyebrow="Cywell AI"
      icon={<ClipboardCheckIcon />}
      title="실행 기록"
    >
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
          tone={!data.status ? 'warning' : capabilities?.actionExecutorConfigured ? 'success' : 'warning'}
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
          tone={!data.status ? 'warning' : capabilities?.unrestrictedCommandsEnabled ? 'danger' : 'success'}
          value={!data.status ? 'PENDING' : capabilities?.unrestrictedCommandsEnabled ? 'ON' : 'OFF'}
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
              허용 읽기 동작: {(contract?.allowedReadOnlyVerbs ?? ['get', 'list', 'watch']).join(', ')}
            </span>
          </div>
          <div>
            <ExclamationTriangleIcon />
            <span>
              금지 동작: {(contract?.forbiddenActions ?? ['create', 'update', 'patch', 'delete']).join(', ')}
            </span>
          </div>
          <div>
            <HistoryIcon />
            <span>감사 기록은 Gateway 요청/완료/실패 및 실행 이벤트를 사용자 권한 기준으로 표시합니다.</span>
          </div>
        </div>
      </section>
    </PageShell>
  );
};
