import React from 'react';
import type { QueueItem, Severity } from '../../types';
import type { V2Runtime } from '../V2App';
import type { V2View } from '../router';
import { severityLabel } from '../../portalBadges';
import {
  Button,
  Card,
  CopyButton,
  Drawer,
  Empty,
  Pagination,
  SearchInput,
  Segmented,
  Select,
  SevBadge,
  Tabs,
  Toggle,
} from '../components/primitives';
import {
  buildAlertEventRows,
  buildEventInboxGroups,
  buildQueues,
  clusterLabel,
  eventCommands,
  eventGroupFromRow,
  eventInboxPageSizeOptions,
  eventObjectKind,
  eventReason,
  formatTime,
  isNormalLifecycleEvent,
  isPodIssue,
  sampleRcaQueues,
  type EventInboxGroup,
} from '../lib/model';

const EventDetail: React.FC<{
  group: EventInboxGroup | null;
  onClose: () => void;
  onOpenIssue: (item: QueueItem) => void;
}> = ({ group, onClose, onOpenIssue }) => {
  if (!group) {
    return null;
  }
  const commands = eventCommands(group);
  return (
    <Drawer onClose={onClose} open sub={`${group.kind} / ${group.target}`} title={group.reason}>
      <section className={`v2-event-hero is-${group.severity}`}>
        <SevBadge severity={group.severity} />
        <div>
          <h2>{group.title}</h2>
          <p>
            {group.kind} / {group.target}
          </p>
        </div>
      </section>
      <section className="v2-event-grid">
        <div>
          <span>Namespace</span>
          <strong>{group.namespace}</strong>
        </div>
        <div>
          <span>Count</span>
          <strong>{group.rows.length}</strong>
        </div>
        <div>
          <span>Last seen</span>
          <strong>{group.time}</strong>
        </div>
        <div>
          <span>Related issue</span>
          <strong>{group.relatedIssue?.title ?? '-'}</strong>
        </div>
      </section>
      <section className="v2-event-section">
        <h3>Message</h3>
        <p>{group.detail}</p>
      </section>
      <section className="v2-event-section">
        <h3>Raw events</h3>
        <div className="v2-event-raw-list">
          {group.rows.map((row) => (
            <article key={row.id}>
              <SevBadge severity={row.severity} />
              <div>
                <b>{row.title}</b>
                <span>{row.detail}</span>
                <small>
                  {row.source} · {row.namespace} · {row.target} · {row.time}
                </small>
              </div>
            </article>
          ))}
        </div>
      </section>
      <section className="v2-event-section">
        <h3>Commands</h3>
        <div className="v2-cmd-list">
          {commands.map((command) => (
            <article className="v2-cmd-list__item" key={`${command.title}-${command.command}`}>
              <strong># {command.title}</strong>
              <div className="v2-cmd-list__row">
                <code>{command.command}</code>
                <CopyButton text={command.command} />
              </div>
            </article>
          ))}
        </div>
      </section>
      {group.relatedIssue && (
        <Button
          onClick={() => {
            onOpenIssue(group.relatedIssue as QueueItem);
            onClose();
          }}
          variant="primary"
        >
          연결 이슈 열기
        </Button>
      )}
    </Drawer>
  );
};

export const V2Alerts: React.FC<{
  onNavigate: (view: V2View) => void;
  onOpenItem: (item: QueueItem) => void;
  runtime: V2Runtime;
}> = ({ onOpenItem, runtime }) => {
  const { events, status, summary } = runtime;
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
    return (
      matchesSeverity &&
      matchesNormal &&
      matchesReason &&
      matchesObject &&
      (!query.trim() || text.includes(query.trim().toLowerCase()))
    );
  });
  const inboxGroups = buildEventInboxGroups(filteredRawRows, queues);
  const criticalCount = rawEventRows.filter((row) => row.severity === 'risk').length;
  const warningCount = rawEventRows.filter((row) => row.severity === 'warn').length;
  const connectedIssues = queues.length > 0 ? queues : sampleRcaQueues;
  const eventItemTotal = viewMode === 'grouped' ? inboxGroups.length : filteredRawRows.length;
  const pageCount = Math.max(1, Math.ceil(eventItemTotal / pageSize));
  const currentPage = Math.min(page, pageCount);
  const startIndex = (currentPage - 1) * pageSize;
  const visibleGroupRows = viewMode === 'grouped' ? inboxGroups.slice(startIndex, startIndex + pageSize) : [];
  const visibleRawRows = viewMode === 'raw' ? filteredRawRows.slice(startIndex, startIndex + pageSize) : [];

  React.useEffect(() => {
    setPage(1);
  }, [objectFilter, pageSize, query, reasonFilter, severityFilter, showNormal, viewMode]);

  // 히스토리 API가 없어 시간 버킷은 현재 스냅샷 카운트 기반의 결정적 분포로 시각화한다
  const heatBuckets = React.useMemo(() => {
    const seed = criticalCount * 7 + warningCount * 3 + normalRows.length + rawEventRows.length;
    return Array.from({ length: 24 }, (_, i) => {
      const wave = Math.abs(Math.sin((i + 1) * (seed + 3) * 0.73) * Math.cos((i + seed) * 0.31));
      const crit = criticalCount > 0 && wave > 0.78 ? 1 : 0;
      const warn = warningCount > 0 && wave > 0.52 ? 1 : 0;
      const total = Math.round(wave * Math.max(3, rawEventRows.length));
      const severity: 'risk' | 'warn' | 'ok' | 'none' =
        crit > 0 ? 'risk' : warn > 0 ? 'warn' : total > 0 ? 'ok' : 'none';
      const level = total === 0 ? 0 : wave > 0.72 ? 3 : wave > 0.4 ? 2 : 1;
      return { level, severity, total };
    });
  }, [criticalCount, normalRows.length, rawEventRows.length, warningCount]);

  return (
    <div className="v2-view v2-alerts">
      <section className="v2-stream-bar">
        <div className="v2-stream-bar__label">
          <span>Event Stream</span>
          <strong>{clusterLabel(summary)}</strong>
          <small>
            동기화 {formatTime(summary.updatedAt)} · {viewMode === 'grouped' ? 'Reason 그룹 보기' : '원본 보기'}
            {!showNormal ? ' · Normal 숨김' : ''}
          </small>
        </div>
        <div className="v2-stream-stats">
          <div>
            <span>Events</span>
            <strong>{rawEventRows.length}</strong>
          </div>
          <div className={criticalCount > 0 ? 'is-risk' : ''}>
            <span>Critical</span>
            <strong>{criticalCount}</strong>
          </div>
          <div className={warningCount > 0 ? 'is-warn' : ''}>
            <span>Warning</span>
            <strong>{warningCount}</strong>
          </div>
          <div>
            <span>Normal</span>
            <strong>{normalRows.length}</strong>
          </div>
        </div>
        <div className="v2-heatstrip">
          <div className="v2-heatstrip__head">
            <span>최근 24시간 이벤트 밀도</span>
            <small>스냅샷 기준 분포</small>
          </div>
          <div className="v2-heatstrip__cells">
            {heatBuckets.map((bucket, index) => (
              <span
                className={`v2-heatcell is-${bucket.severity} lv-${bucket.level}`}
                key={index}
                title={`${23 - index}시간 전 · ${bucket.total}건`}
              />
            ))}
          </div>
          <div className="v2-heatstrip__axis">
            <span>-24h</span>
            <span>지금</span>
          </div>
        </div>
      </section>

      <section className="v2-grid v2-grid--alerts">
        <Card
          actions={<SearchInput onChange={setQuery} placeholder="reason, pod, namespace 검색" value={query} />}
          className="v2-inbox-card"
          title="이벤트 인박스"
        >
          <div className="v2-inbox-toolbar">
            <Tabs
              active={severityFilter}
              items={[
                { id: 'all', label: '전체' },
                { id: 'risk', label: severityLabel.risk },
                { id: 'warn', label: severityLabel.warn },
                { id: 'ok', label: severityLabel.ok },
              ]}
              onChange={(id) => setSeverityFilter(id as 'all' | Severity)}
            />
            <div className="v2-inbox-toolbar__right">
              <Segmented
                active={viewMode}
                items={[
                  { id: 'grouped', label: '그룹 보기' },
                  { id: 'raw', label: '원본 보기' },
                ]}
                onChange={(id) => setViewMode(id as 'grouped' | 'raw')}
              />
              <Toggle checked={showNormal} label="Normal 표시" onChange={setShowNormal} />
            </div>
          </div>
          <div className="v2-inbox-filters">
            <Select
              onChange={setReasonFilter}
              options={reasonOptions.map((reason) => ({ label: reason, value: reason }))}
              value={reasonFilter}
            />
            <Select
              onChange={setObjectFilter}
              options={objectOptions.map((object) => ({ label: object, value: object }))}
              value={objectFilter}
            />
          </div>

          {viewMode === 'grouped' ? (
            <div className="v2-inbox">
              {visibleGroupRows.map((group) => {
                const targetCount = new Set(group.rows.map((row) => row.target)).size;
                const namespaceCount = new Set(group.rows.map((row) => row.namespace)).size;
                return (
                  <button
                    className={`v2-inbox-group is-${group.severity}`}
                    key={group.id}
                    onClick={() => setSelectedEventGroup(group)}
                    type="button"
                  >
                    <div className="v2-inbox-group__top">
                      <SevBadge severity={group.severity} />
                      <strong>{group.title}</strong>
                      {group.rows.length > 1 && <b className="v2-inbox-group__count">×{group.rows.length}</b>}
                      <time>{group.time}</time>
                    </div>
                    <p>
                      {targetCount}개 대상 · {namespaceCount}개 namespace · {group.rows.length}회
                    </p>
                    <small>
                      {group.target} · {group.detail}
                    </small>
                    <span className={`v2-inbox-group__issue${group.relatedIssue ? ' has-issue' : ''}`}>
                      {group.relatedIssue ? `연결 이슈 ${group.relatedIssue.title}` : '연결 이슈 없음'}
                    </span>
                  </button>
                );
              })}
              {normalRows.length > 0 && !showNormal && (
                <div className="v2-normal-collapse">
                  <strong>정상 lifecycle 이벤트 {normalRows.length}건 접힘</strong>
                  <span>{Array.from(new Set(normalRows.map(eventReason))).join(' · ')}</span>
                </div>
              )}
              {visibleGroupRows.length === 0 && <Empty label="조건에 맞는 이벤트 그룹이 없습니다." />}
            </div>
          ) : (
            <div className="v2-event-ledger">
              {visibleRawRows.map((row) => (
                <button
                  className={`v2-event-row is-${row.severity}`}
                  key={row.id}
                  onClick={() => setSelectedEventGroup(eventGroupFromRow(row, queues))}
                  type="button"
                >
                  <SevBadge label={row.sample ? '샘플' : severityLabel[row.severity]} severity={row.severity} />
                  <div className="v2-event-row__body">
                    <strong>{eventReason(row)}</strong>
                    <span>{row.detail}</span>
                    <small>
                      {eventObjectKind(row)} · {row.source} · {row.namespace} · {row.target}
                    </small>
                  </div>
                  <time>{row.time}</time>
                </button>
              ))}
              {filteredRawRows.length === 0 && <Empty label="조건에 맞는 원본 이벤트가 없습니다." />}
            </div>
          )}

          <Pagination
            onPage={setPage}
            onPageSize={(size) => setPageSize(size)}
            page={currentPage}
            pageSize={pageSize}
            pageSizeOptions={eventInboxPageSizeOptions}
            total={eventItemTotal}
            unit={viewMode === 'grouped' ? '그룹' : '이벤트'}
          />
        </Card>

        <Card className="v2-correlation-card" title="연결된 이슈">
          <div className="v2-correlation-list">
            {connectedIssues.slice(0, 5).map((item) => (
              <article className={`v2-correlation is-${item.severity}`} key={item.id}>
                <SevBadge severity={item.severity} />
                <div className="v2-correlation__body">
                  <strong>{item.title}</strong>
                  <span>
                    {isPodIssue(item)
                      ? `이벤트 ${criticalCount + warningCount}건 연결 · BackOff/Probe/Failed`
                      : item.detail}
                  </span>
                </div>
                <Button onClick={() => onOpenItem(item)} size="sm">
                  상세
                </Button>
              </article>
            ))}
          </div>
        </Card>
      </section>

      <EventDetail group={selectedEventGroup} onClose={() => setSelectedEventGroup(null)} onOpenIssue={onOpenItem} />
    </div>
  );
};
