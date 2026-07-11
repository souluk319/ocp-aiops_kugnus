import * as React from 'react';
import {
  actionRecords,
  buildLedgerEntries,
  ledgerActionLabel,
  ledgerGateLabel,
  ledgerKindLabel,
  ledgerNamespaceRangeLabel,
  ledgerResultLabel,
  ledgerTargetLabel,
  mutationStatusLabel,
  runWindowLabel,
} from './executionLedgerModel';
import type { LedgerEntry } from './executionLedgerModel';
import { formatTime } from './portalModel';
import type { AiopsRecord, AiopsRuntimeStatus, NavView } from './types';

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

const EmptyState: React.FC<{ label: string }> = ({ label }) => (
  <div className="empty-state">{label}</div>
);

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
          : '실시간 게이트웨이에서 현재 표시 범위의 실행/승인/감사 기록을 보여줍니다.'}
      </span>
      <small>
        마지막 게이트웨이 확인 {formatTime(new Date().toISOString())} · 실제 기록 {realRecordCount}건 · 표시 이벤트 {entries.length}건 · 원장 JSON은 현재 표시 기록을 저장합니다.
      </small>
    </div>
    <div className="ledger-source-strip__actions">
      <button onClick={onGatewayLogs} type="button">알림 & 이벤트 보기</button>
      <button onClick={onExport} type="button">원장 JSON 내보내기</button>
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
  const namespace = ledgerNamespaceRangeLabel(entries);
  const mutationStatus = mutations > 0 ? 'Executed' : approvals > 0 ? 'Waiting approval' : failed > 0 ? 'Blocked' : 'Not executed';

  return (
    <section className="ledger-run-overview">
      <div>
        <span>{syntheticReplay ? '샘플 원장 요약' : '현재 원장 요약'}</span>
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
        <span>네임스페이스 범위 <strong>{namespace}</strong></span>
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
      <div className="portal-panel__title">조치 타임라인</div>
    </div>
    <div className="execution-trace">
      {entries.length === 0 ? (
        <EmptyState label="표시할 조치 타임라인 기록이 없습니다." />
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

const SelectedLedgerEvent: React.FC<{ entry?: LedgerEntry }> = ({ entry }) => (
  <div className="selected-ledger-event">
    <div className="selected-ledger-event__title">선택된 이벤트</div>
    {entry ? (
      <dl>
        <div><dt>단계</dt><dd>{entry.phase}</dd></div>
        <div><dt>대상</dt><dd>{ledgerTargetLabel(entry)}</dd></div>
        <div><dt>게이트</dt><dd>{ledgerGateLabel(entry.gate)}</dd></div>
        <div><dt>결과</dt><dd>{ledgerResultLabel(entry.result)}</dd></div>
        <div><dt>증거</dt><dd>{entry.evidenceId}</dd></div>
        <div><dt>감사 ID</dt><dd>{entry.auditId}</dd></div>
      </dl>
    ) : (
      <EmptyState label="선택된 이벤트가 없습니다." />
    )}
  </div>
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
      detail: capabilities.recordStoreEnabled
        ? `${capabilities.recordStoreConfigMap || '서버 원장에 기록됩니다.'} · Gateway 재시작 후에도 보존 대상입니다.`
        : '현재 화면에는 임시 기록이 표시됩니다. Gateway 재시작 후 사라질 수 있습니다.',
      label: '영구 원장',
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
            <div><strong>{item.label}</strong><small>{item.detail}</small></div>
            <span className={`guardrail-pill is-${item.tone}`}>{item.value}</span>
          </article>
        ))}
      </div>
      <SelectedLedgerEvent entry={selectedEntry} />
    </section>
  );
};

const auditLedgerFilters: Array<{ id: 'all' | LedgerEntry['category']; label: string }> = [
  { id: 'all', label: '전체' },
  { id: 'approval', label: '승인' },
  { id: 'mutation', label: '변경 실행' },
  { id: 'gateway', label: '게이트웨이' },
  { id: 'evidence', label: '증거' },
];

const AuditLedgerTable: React.FC<{ entries: LedgerEntry[] }> = ({ entries }) => {
  const [activeFilter, setActiveFilter] = React.useState<'all' | LedgerEntry['category']>('all');
  const filteredEntries = activeFilter === 'all' ? entries : entries.filter((entry) => entry.category === activeFilter);

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
              <th>시간</th><th>단계</th><th>조치</th><th>네임스페이스</th><th>종류</th>
              <th>이름</th><th>게이트</th><th>결과</th><th>증거</th><th>감사 ID</th>
            </tr>
          </thead>
          <tbody>
            {filteredEntries.length === 0 ? (
              <tr><td colSpan={10}>표시할 감사 원장 항목이 없습니다.</td></tr>
            ) : (
              filteredEntries.map((entry) => (
                <tr key={entry.id}>
                  <td>{formatTime(entry.time)}</td>
                  <td><span className={`ledger-phase is-${entry.tone}`}>{entry.phase}</span></td>
                  <td><strong>{ledgerActionLabel(entry.action)}</strong><small>{entry.actor}{entry.sample ? ' · 샘플' : ''}</small></td>
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

export const ExecutionRecordsView: React.FC<{
  onNavigate: (view: NavView) => void;
  status: AiopsRuntimeStatus;
}> = ({ onNavigate, status }) => {
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
      <RunOverviewStrip auditRecords={auditRecords} entries={entries} records={records} syntheticReplay={syntheticReplay} />
      <section className="operation-ledger__workspace">
        <ExecutionTracePanel entries={entries} onSelectEntry={setSelectedEntryId} selectedEntryId={selectedEntry?.id ?? ''} />
        <ControlGatesPanel entries={entries} selectedEntry={selectedEntry} status={status} />
      </section>
      <AuditLedgerTable entries={entries} />
    </section>
  );
};
