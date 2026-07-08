import React from 'react';
import { Download, Radio, Siren } from 'lucide-react';
import type { V2Runtime } from '../V2App';
import type { V2View } from '../router';
import { Button, Card, DefList, Empty, SevBadge, Tabs } from '../components/primitives';
import {
  actionRecords,
  buildOperationSummaries,
  buildLedgerEntries,
  formatTime,
  ledgerActionLabel,
  ledgerGateLabel,
  ledgerKindLabel,
  ledgerResultLabel,
  ledgerTargetLabel,
  localizeTelemetryText,
  mockAuditRecords,
  mockExecutionRecords,
  mutationStatusLabel,
  runWindowLabel,
  type LedgerEntry,
  type OperationSummary,
} from '../lib/model';

const ledgerFilters: Array<{ id: 'all' | LedgerEntry['category']; label: string }> = [
  { id: 'all', label: '전체' },
  { id: 'approval', label: '승인' },
  { id: 'mutation', label: '변경 실행' },
  { id: 'gateway', label: '게이트웨이' },
  { id: 'evidence', label: '증거' },
];

const entryServerChangeLabel = (entry: LedgerEntry): string => {
  const signal = `${entry.phase} ${entry.result} ${entry.action}`.toLowerCase();
  if (entry.category !== 'mutation') {
    return '아직 없음';
  }
  if (
    signal.includes('review_recorded') ||
    signal.includes('blocked') ||
    signal.includes('disabled') ||
    signal.includes('simulated')
  ) {
    return '서버 변경 없음';
  }
  if (signal.includes('succeeded') || signal.includes('executed')) {
    return '서버 변경 있음';
  }
  return '확인 필요';
};

const entryStatusLabel = (entry: LedgerEntry): string => {
  if (entry.category === 'mutation') {
    return entryServerChangeLabel(entry) === '서버 변경 없음' ? '검토 기록' : '실행 기록';
  }
  if (entry.category === 'approval') {
    return '승인/계획 기록';
  }
  return '조치 제안 기록';
};

const entryResultText = (entry: LedgerEntry): string => {
  const serverChange = entryServerChangeLabel(entry);
  if (entry.category === 'mutation' && serverChange === '서버 변경 없음') {
    return '검토 또는 로컬 검증 기록이 남았습니다. 서버 변경은 실행하지 않았습니다.';
  }
  if (entry.category === 'mutation') {
    return `${ledgerResultLabel(entry.result)} 상태로 실행 기록이 남았습니다. 세부 원장은 아래 표에서 확인할 수 있습니다.`;
  }
  if (entry.category === 'approval') {
    return '승인 또는 봉인된 계획 기록이 남았습니다. 실행 여부는 변경 실행 기록에서 확인합니다.';
  }
  return 'Action Plan 후보 또는 제안 기록이 남았습니다. 승인 전에는 서버 변경이 없습니다.';
};

const buildLedgerFallbackSummaries = (entries: LedgerEntry[]): OperationSummary[] =>
  entries
    .filter((entry) => entry.category === 'proposal' || entry.category === 'approval' || entry.category === 'mutation')
    .map((entry): OperationSummary => ({
      action: ledgerActionLabel(entry.action),
      detail: `${ledgerGateLabel(entry.gate)} · ${ledgerKindLabel(entry.kind)}`,
      evidence: entry.evidenceId,
      id: `ledger-summary-${entry.id}`,
      nextStep: entry.category === 'mutation'
        ? '대상 상태와 이벤트를 다시 확인하세요.'
        : '대상·영향·검증 방법을 확인한 뒤 승인 또는 거절하세요.',
      recordIds: [entry.auditId].filter((id) => id && id !== '-'),
      result: entryResultText(entry),
      serverChange: entryServerChangeLabel(entry),
      status: entryStatusLabel(entry),
      target: ledgerTargetLabel(entry),
      time: entry.time,
      title: ledgerActionLabel(entry.action),
      tone: entry.tone,
    }));

const OperationSummaryPanel: React.FC<{ summaries: OperationSummary[] }> = ({ summaries }) => (
  <Card
    className="v2-operation-summary-card"
    sub="제안·승인·실행 기록을 조치 단위로 정리합니다."
    title="조치 요약"
  >
    {summaries.length === 0 ? (
      <Empty label="아직 Action Plan 실행/검토 요약이 없습니다." />
    ) : (
      <div className="v2-operation-summary-list">
        {summaries.map((summary) => (
          <article className={`v2-operation-summary is-${summary.tone}`} key={summary.id}>
            <div className="v2-operation-summary__head">
              <div>
                <span>{summary.status}</span>
                <strong>{summary.title}</strong>
              </div>
              <span className={`v2-phase-chip is-${summary.tone}`}>{summary.serverChange}</span>
            </div>
            <dl className="v2-operation-summary__facts">
              <div>
                <dt>대상</dt>
                <dd>{summary.target}</dd>
              </div>
              <div>
                <dt>조치 내용</dt>
                <dd>{summary.action}</dd>
              </div>
              <div>
                <dt>결과</dt>
                <dd>{summary.result}</dd>
              </div>
              <div>
                <dt>확인 결과</dt>
                <dd>{summary.evidence}</dd>
              </div>
            </dl>
            <div className="v2-operation-summary__footer">
              <span>{summary.nextStep}</span>
              <small>{formatTime(summary.time)}</small>
            </div>
            <details className="v2-operation-summary__records">
              <summary>연결된 원장 기록 {summary.recordIds.length}건</summary>
              <div>
                {summary.recordIds.map((recordId) => (
                  <code className="v2-id-chip" key={recordId}>{recordId}</code>
                ))}
              </div>
            </details>
          </article>
        ))}
      </div>
    )}
  </Card>
);

export const V2Executions: React.FC<{
  onNavigate: (view: V2View) => void;
  runtime: V2Runtime;
}> = ({ onNavigate, runtime }) => {
  const { status } = runtime;
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
  const operationSummaries = React.useMemo(() => buildOperationSummaries(records), [records]);
  const fallbackOperationSummaries = React.useMemo(() => buildLedgerFallbackSummaries(entries), [entries]);
  const visibleOperationSummaries =
    operationSummaries.length > 0 ? operationSummaries : fallbackOperationSummaries;
  const [selectedEntryId, setSelectedEntryId] = React.useState('');
  const selectedEntry = entries.find((entry) => entry.id === selectedEntryId) ?? entries[0];
  const [ledgerFilter, setLedgerFilter] = React.useState<'all' | LedgerEntry['category']>('all');
  const filteredEntries = ledgerFilter === 'all' ? entries : entries.filter((entry) => entry.category === ledgerFilter);

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

  const proposals = entries.filter((entry) => entry.category === 'proposal').length;
  const approvals = entries.filter((entry) => entry.category === 'approval').length;
  const mutations = entries.filter((entry) => entry.category === 'mutation').length;
  const failed = entries.filter((entry) => entry.tone === 'red').length;
  const runId = entries[0]?.runId ?? '-';
  const namespace = entries.find((entry) => entry.namespace !== '-')?.namespace ?? '-';
  const mutationStatus =
    mutations > 0 ? 'Executed' : approvals > 0 ? 'Waiting approval' : failed > 0 ? 'Blocked' : 'Not executed';

  const capabilities = status.spec.capabilities;
  const gates: Array<{ detail: string; label: string; tone: 'ok' | 'warn'; value: string }> = [
    {
      detail: capabilities.mutationsEnabled
        ? '승인되지 않은 변경은 게이트웨이 정책에서 차단합니다.'
        : '읽기/증거 수집 모드입니다. 클러스터 변경은 차단됩니다.',
      label: '변경 게이트',
      tone: capabilities.mutationsEnabled ? 'ok' : 'warn',
      value: capabilities.mutationsEnabled ? '켜짐' : '꺼짐',
    },
    {
      detail: approvals > 0
        ? '이 실행 흐름에 승인 검증 기록이 포함되어 있습니다.'
        : '현재 스트림에 승인 검증 기록이 없습니다.',
      label: '승인 검증',
      tone: approvals > 0 ? 'ok' : 'warn',
      value: approvals > 0 ? '준비됨' : '없음',
    },
    {
      detail: capabilities.actionExecutorConfigured
        ? '승인된 클러스터 조치를 실행할 수 있습니다.'
        : '외부 실행기가 설정되어 있지 않습니다.',
      label: '조치 실행기',
      tone: capabilities.actionExecutorConfigured ? 'ok' : 'warn',
      value: capabilities.actionExecutorConfigured ? '준비됨' : '미설정',
    },
    {
      detail: capabilities.diagnosticsEnabled
        ? '진단 증거 수집 경로가 활성화되어 있습니다.'
        : '증거는 현재 사용 가능한 게이트웨이 기록으로 제한됩니다.',
      label: '진단 수집',
      tone: capabilities.diagnosticsEnabled ? 'ok' : 'warn',
      value: capabilities.diagnosticsEnabled ? '켜짐' : '꺼짐',
    },
    {
      detail: capabilities.recordStoreEnabled
        ? localizeTelemetryText(capabilities.recordStoreConfigMap || '영구 감사 원장이 활성화되어 있습니다.')
        : '기록이 게이트웨이 영구 원장에 저장되지 않습니다.',
      label: '기록 원장',
      tone: capabilities.recordStoreEnabled ? 'ok' : 'warn',
      value: capabilities.recordStoreEnabled ? '켜짐' : '꺼짐',
    },
  ];

  return (
    <div className="v2-view v2-executions">
      <section className={`v2-source-strip${syntheticReplay ? ' is-synthetic' : ' is-live'}`}>
        <span className="v2-source-strip__pulse" aria-hidden="true" />
        <div className="v2-source-strip__text">
          <strong>{syntheticReplay ? '데이터 소스 · 샘플 재생 모드' : '데이터 소스 · 실시간 게이트웨이'}</strong>
          <span>
            {syntheticReplay
              ? '게이트웨이 실행/감사 스트림이 비어 있어 샘플 실행 흐름을 재생 중입니다. 실제 클러스터 변경 기록이 아닙니다.'
              : '실시간 게이트웨이 런타임에서 수집한 실행/감사 기록을 표시합니다.'}
          </span>
          <small>
            마지막 게이트웨이 확인 {formatTime(new Date().toISOString())} · 실제 기록 {realRecordCount}건 · 표시
            이벤트 {entries.length}건
          </small>
        </div>
        <div className="v2-source-strip__actions">
          <Button icon={<Siren size={13} />} onClick={() => onNavigate('alerts')} size="sm">
            게이트웨이 이벤트
          </Button>
          <Button icon={<Download size={13} />} onClick={exportAuditBundle} size="sm">
            감사 번들
          </Button>
          {realRecordCount === 0 && (
            <Button icon={<Radio size={13} />} onClick={() => setShowSyntheticReplay((current) => !current)} size="sm">
              {showSyntheticReplay ? '샘플 숨기기' : '샘플 보기'}
            </Button>
          )}
        </div>
      </section>

      <section className="v2-run-overview">
        <div className="v2-run-overview__id">
          <span>{syntheticReplay ? '샘플 실행' : '활성 실행'}</span>
          <strong>{runId}</strong>
          <small>{runWindowLabel(entries)}</small>
        </div>
        <div className="v2-run-overview__facts">
          <div>
            <span>이벤트</span>
            <strong>{entries.length}</strong>
          </div>
          <div>
            <span>제안</span>
            <strong>{proposals}</strong>
          </div>
          <div>
            <span>승인 게이트</span>
            <strong>{approvals}</strong>
          </div>
          <div>
            <span>변경 실행</span>
            <strong>{mutations}</strong>
          </div>
          <div>
            <span>감사 기록</span>
            <strong>{auditRecords.length}</strong>
          </div>
        </div>
        <div className="v2-run-overview__meta">
          <span>
            대상 네임스페이스 <strong>{namespace}</strong>
          </span>
          <span>
            정책 모드 <strong>{approvals > 0 ? '승인 필요' : '읽기 전용 증거 수집'}</strong>
          </span>
          <span>
            변경 상태 <strong>{mutationStatusLabel(mutationStatus)}</strong>
          </span>
          <span>
            조치 기록 <strong>{records.length}건</strong>
          </span>
        </div>
      </section>

      <OperationSummaryPanel summaries={visibleOperationSummaries} />

      <section className="v2-grid v2-grid--executions">
        <Card className="v2-trace-card" flush title="실행 추적">
          <div className="v2-trace">
            {entries.length === 0 ? (
              <Empty label="표시할 실행 추적 기록이 없습니다." />
            ) : (
              entries.map((entry, index) => (
                <button
                  className={`v2-trace__row is-${entry.tone}${entry.id === (selectedEntry?.id ?? '') ? ' is-selected' : ''}`}
                  key={entry.id}
                  onClick={() => setSelectedEntryId(entry.id)}
                  type="button"
                >
                  <span className="v2-trace__index">{String(index + 1).padStart(2, '0')}</span>
                  <span className="v2-trace__time">{formatTime(entry.time)}</span>
                  <span className="v2-trace__body">
                    <strong>{entry.phase}</strong>
                    <b>{ledgerActionLabel(entry.action)}</b>
                    {ledgerTargetLabel(entry) !== '-' && <small>{ledgerTargetLabel(entry)}</small>}
                  </span>
                  <span className="v2-trace__result">{ledgerResultLabel(entry.result)}</span>
                  {entry.sample && <span className="v2-trace__sample">샘플</span>}
                </button>
              ))
            )}
          </div>
        </Card>

        <Card
          actions={<SevBadge label="게이트웨이 상태" severity="ok" />}
          className="v2-gates-card"
          title="실행 제어 게이트"
        >
          <div className="v2-gates">
            {gates.map((gate) => (
              <article className="v2-gates__item" key={gate.label}>
                <div>
                  <strong>{gate.label}</strong>
                  <small>{gate.detail}</small>
                </div>
                <span className={`v2-badge is-${gate.tone}`}>
                  <span className="v2-badge__dot" aria-hidden="true" />
                  {gate.value}
                </span>
              </article>
            ))}
          </div>
          <div className="v2-selected-event">
            <h3>선택된 이벤트</h3>
            {selectedEntry ? (
              <DefList
                rows={[
                  { label: '단계', value: selectedEntry.phase },
                  { label: '대상', value: ledgerTargetLabel(selectedEntry) },
                  { label: '게이트', value: ledgerGateLabel(selectedEntry.gate) },
                  { label: '결과', value: ledgerResultLabel(selectedEntry.result) },
                  { label: '증거', value: selectedEntry.evidenceId },
                  { label: '감사 ID', value: selectedEntry.auditId },
                ]}
              />
            ) : (
              <Empty label="선택된 이벤트가 없습니다." />
            )}
          </div>
        </Card>
      </section>

      <Card
        actions={
          <Tabs
            active={ledgerFilter}
            items={ledgerFilters.map((filter) => ({
              id: filter.id,
              label: filter.label,
              count:
                filter.id === 'all'
                  ? entries.length
                  : entries.filter((entry) => entry.category === filter.id).length,
            }))}
            onChange={(id) => setLedgerFilter(id as 'all' | LedgerEntry['category'])}
          />
        }
        flush
        title="감사 원장"
      >
        <div className="v2-table-wrap">
          <table className="v2-table">
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
                  <td className="v2-table__empty" colSpan={10}>
                    표시할 감사 원장 항목이 없습니다.
                  </td>
                </tr>
              ) : (
                filteredEntries.map((entry) => (
                  <tr key={entry.id}>
                    <td>{formatTime(entry.time)}</td>
                    <td>
                      <span className={`v2-phase-chip is-${entry.tone}`}>{entry.phase}</span>
                    </td>
                    <td>
                      <div className="v2-endpoint-name">
                        <strong>{ledgerActionLabel(entry.action)}</strong>
                        <small>
                          {entry.actor}
                          {entry.sample ? ' · 샘플' : ''}
                        </small>
                      </div>
                    </td>
                    <td>{entry.namespace}</td>
                    <td>{ledgerKindLabel(entry.kind)}</td>
                    <td>{entry.name}</td>
                    <td>{ledgerGateLabel(entry.gate)}</td>
                    <td>{ledgerResultLabel(entry.result)}</td>
                    <td>
                      <code className="v2-id-chip">{entry.evidenceId}</code>
                    </td>
                    <td>
                      <code className="v2-id-chip">{entry.auditId}</code>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </Card>
    </div>
  );
};
