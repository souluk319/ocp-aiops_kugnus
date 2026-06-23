import * as React from 'react';
import { Button, Spinner } from '@patternfly/react-core';
import {
  ClipboardCheckIcon,
  ExclamationTriangleIcon,
  HistoryIcon,
  RobotIcon,
  ShieldAltIcon,
} from '@patternfly/react-icons';
import {
  type AiopsRecord,
  type AiopsRuntimeStatus,
  type ClusterSummary,
  fetchAiopsStatus,
  fetchClusterSummary,
} from '../services/aiGateway';
import './aiops-pages.css';

type AiopsPageData = {
  error: string;
  loading: boolean;
  refresh: () => Promise<void>;
  status: AiopsRuntimeStatus | null;
  summary: ClusterSummary | null;
};

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

const StatGrid: React.FC<{ items: Array<{ label: string; value: string | number }> }> = ({
  items,
}) => (
  <div className="komsco-ai-page__stat-grid">
    {items.map((item) => (
      <div className="komsco-ai-page__stat" key={item.label}>
        <span>{item.label}</span>
        <strong>{item.value}</strong>
      </div>
    ))}
  </div>
);

const EmptyState: React.FC<{ label: string }> = ({ label }) => (
  <div className="komsco-ai-page__empty">{label}</div>
);

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
  const actionCount = actionRecords(data.status).length;
  const auditCount = data.status?.spec.records.auditRecords?.length ?? 0;

  return (
    <PageShell data={data} eyebrow="KOMSCO AIOps" icon={<RobotIcon />} title="AIOps Dashboard">
      <StatGrid
        items={[
          { label: 'Health score', value: data.summary ? `${data.summary.healthScore}/100` : '-' },
          {
            label: 'Ready nodes',
            value: data.summary ? `${data.summary.nodes.ready}/${data.summary.nodes.total}` : '-',
          },
          {
            label: 'Operator issues',
            value: data.summary?.operators.issues.length ?? '-',
          },
          { label: 'Audit records', value: auditCount },
          { label: 'Action records', value: actionCount },
        ]}
      />
      <div className="komsco-ai-page__grid">
        <section className="komsco-ai-page__panel">
          <h2>최근 실행 기록</h2>
          <RecordTable
            emptyLabel="최근 승인 또는 실행 기록이 없습니다."
            records={actionRecords(data.status).slice(0, 5)}
          />
        </section>
        <section className="komsco-ai-page__panel">
          <h2>최근 감사</h2>
          <RecordTable
            emptyLabel="최근 감사 기록이 없습니다."
            records={(data.status?.spec.records.auditRecords ?? []).slice(0, 5)}
            variant="audit"
          />
        </section>
      </div>
    </PageShell>
  );
};

export const AiopsAuditPage: React.FC = () => {
  const data = useAiopsPageData();

  return (
    <PageShell data={data} eyebrow="KOMSCO AIOps" icon={<HistoryIcon />} title="감사 기록">
      <section className="komsco-ai-page__panel">
        <h2>최근 Gateway 감사 레코드</h2>
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
      eyebrow="KOMSCO AIOps"
      icon={<ClipboardCheckIcon />}
      title="실행 기록"
    >
      <section className="komsco-ai-page__panel">
        <h2>승인·실행 라이프사이클</h2>
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

  return (
    <PageShell data={data} eyebrow="KOMSCO AIOps" icon={<ShieldAltIcon />} title="정책">
      <StatGrid
        items={[
          { label: 'Diagnostics', value: capabilities?.diagnosticsEnabled ? 'ON' : 'OFF' },
          { label: 'Mutations', value: capabilities?.mutationsEnabled ? 'ON' : 'OFF' },
          {
            label: 'Action Executor',
            value: capabilities?.actionExecutorConfigured ? 'CONNECTED' : 'NOT CONFIGURED',
          },
          {
            label: 'Unrestricted',
            value: capabilities?.unrestrictedCommandsEnabled ? 'ON' : 'OFF',
          },
          { label: 'Ledger', value: capabilities?.recordStoreEnabled ? 'ON' : 'OFF' },
        ]}
      />
      <section className="komsco-ai-page__panel">
        <h2>현재 정책 상태</h2>
        <div className="komsco-ai-page__policy-list">
          <div>
            <ExclamationTriangleIcon />
            <span>실험 무제한 모드는 지원되는 자연어 조치와 명령 실행을 Gateway 권한으로 수행합니다.</span>
          </div>
          <div>
            <ShieldAltIcon />
            <span>승인·실행 경로는 ActionProposal, SealedActionPlan, ApprovalDecision, ExecutionRecord로 추적됩니다.</span>
          </div>
          <div>
            <HistoryIcon />
            <span>감사 기록은 최근 Gateway 요청/완료/실패 및 실행 이벤트를 사용자 권한 기준으로 표시합니다.</span>
          </div>
        </div>
      </section>
    </PageShell>
  );
};
