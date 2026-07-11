import * as React from 'react';
import { ChevronLeft, ChevronRight, Search, X } from 'lucide-react';
import type {
  AiopsExecutionMode,
  AssistantDraftPrompt,
  AssistantLaunchContext,
} from '../components/assistant.types';
import {
  buildEventInboxGroups,
  eventGroupFromRow,
  eventObjectKind,
  eventReason,
  isNormalLifecycleEvent,
  isPodIssue,
} from './eventInboxModel';
import type { AlertEventRow, EventInboxGroup } from './eventInboxModel';
import { severityClass, severityLabel, StatusBadge } from './portalBadges';
import { formatTime } from './portalModel';
import type { AiopsRecord, AiopsRuntimeStatus, QueueItem, Severity } from './types';

type AssistantLaunchRequest = {
  context: AssistantLaunchContext;
  executionMode?: AiopsExecutionMode;
  taskMode?: AssistantDraftPrompt['taskMode'];
};

type AssistantLaunchHandler = (request: AssistantLaunchRequest) => void;

export type AlertsEventsViewProps = {
  buildAssistantContext: (group: EventInboxGroup) => AssistantLaunchContext;
  clusterName: string;
  fallbackQueues: QueueItem[];
  lastUpdatedAt: string;
  onAssistantLaunch?: AssistantLaunchHandler;
  onOpenItem: (item: QueueItem) => void;
  onPageContextChange?: (context: Record<string, unknown>) => void;
  queues: QueueItem[];
  rows: AlertEventRow[];
  status: AiopsRuntimeStatus;
};

const eventInboxPageSizeOptions = [10, 25, 50];

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

const EmptyState: React.FC<{ label: string }> = ({ label }) => (
  <div className="empty-state">{label}</div>
);

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

const EventDetailDrawer: React.FC<{
  buildAssistantContext: (group: EventInboxGroup) => AssistantLaunchContext;
  group: EventInboxGroup | null;
  onAssistantLaunch?: AssistantLaunchHandler;
  onClose: () => void;
  onOpenIssue: (item: QueueItem) => void;
}> = ({ buildAssistantContext, group, onAssistantLaunch, onClose, onOpenIssue }) => {
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
                  onClick={() => onAssistantLaunch({ context: buildAssistantContext(group) })}
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

const feedbackSpecText = (record: AiopsRecord | undefined, key: string): string => {
  const value = record?.spec?.[key];
  return typeof value === 'string' ? value.trim() : '';
};

const feedbackRecordTime = (record: AiopsRecord): number => {
  const value = Date.parse(String(record.metadata?.createdAt || feedbackSpecText(record, 'submittedAt')));
  return Number.isFinite(value) ? value : 0;
};

const hasReviewableFeedbackTranscript = (record: AiopsRecord): boolean =>
  Boolean(feedbackSpecText(record, 'userMessage') && feedbackSpecText(record, 'assistantAnswer'));

const feedbackPreview = (value: string, fallback: string, maxLength = 150): string => {
  const normalized = value.replace(/\s+/g, ' ').trim();
  if (!normalized) {
    return fallback;
  }
  return normalized.length > maxLength ? `${normalized.slice(0, maxLength - 1).trim()}…` : normalized;
};

const feedbackRatingText = (record: AiopsRecord): string =>
  feedbackSpecText(record, 'rating') === 'down' ? '개선 필요' : '좋은 답변';

const feedbackRouteText = (route: string): string => {
  if (route.includes('/dashboards/aiops/alerts')) {
    return '알림 & 이벤트';
  }
  if (route.includes('/dashboards/aiops/rca')) {
    return 'RCA 센터';
  }
  if (route.includes('/dashboards/aiops/executions')) {
    return '실행 기록';
  }
  if (route.includes('/dashboards/aiops')) {
    return 'AIOps 대시보드';
  }
  return route || '화면 정보 없음';
};

const ChatFeedbackCandidatesPanel: React.FC<{ status: AiopsRuntimeStatus }> = ({ status }) => {
  const allRecords = [...(status.spec.records.chatFeedback ?? [])].sort(
    (a, b) => feedbackRecordTime(b) - feedbackRecordTime(a),
  );
  const records = allRecords.filter(hasReviewableFeedbackTranscript);
  const needsWork = records.filter((record) => feedbackSpecText(record, 'rating') === 'down');
  const goodCount = records.filter((record) => feedbackSpecText(record, 'rating') === 'up').length;
  const visibleRecords = (needsWork.length > 0 ? needsWork : records).slice(0, 5);

  return (
    <Panel
      action={
        <div className="feedback-candidate-metrics">
          <span>개선 {needsWork.length}</span>
          <span>좋음 {goodCount}</span>
        </div>
      }
      className="chat-feedback-candidates"
      title="답변 개선 후보"
    >
      <div className="feedback-candidate-intro">
        <strong>Runbook 반영은 수동 선별</strong>
        <span>싫어요와 메모가 남은 답변을 먼저 보여줍니다. 자동 학습이나 자동 반영은 하지 않습니다.</span>
      </div>
      {visibleRecords.length === 0 ? (
        <EmptyState label="질문과 답변이 함께 저장된 챗봇 피드백이 없습니다. Runbook 후보는 대화 원문이 있는 기록만 표시합니다." />
      ) : (
        <div className="feedback-candidate-list">
          {visibleRecords.map((record) => {
            const rating = feedbackSpecText(record, 'rating');
            const route = feedbackRouteText(feedbackSpecText(record, 'route'));
            const comment = feedbackSpecText(record, 'optionalComment');
            const userMessage = feedbackSpecText(record, 'userMessage');
            const assistantAnswer = feedbackSpecText(record, 'assistantAnswer');
            const source = feedbackSpecText(record, 'answerSource') || feedbackSpecText(record, 'source') || 'unknown';
            return (
              <article className={rating === 'down' ? 'is-needs-work' : 'is-good'} key={record.metadata?.name ?? `${route}-${record.metadata?.createdAt}`}>
                <div className="feedback-candidate-row__head">
                  <span className={`feedback-candidate-rating is-${rating === 'down' ? 'down' : 'up'}`}>
                    {feedbackRatingText(record)}
                  </span>
                  <strong>{feedbackPreview(comment, '메모 없음', 90)}</strong>
                  <time>{formatTime(record.metadata?.createdAt)}</time>
                </div>
                <dl className="feedback-candidate-facts">
                  <div>
                    <dt>화면</dt>
                    <dd>{route}</dd>
                  </div>
                  <div>
                    <dt>응답 경로</dt>
                    <dd>{source}</dd>
                  </div>
                </dl>
                <details>
                  <summary>질문·답변 보기</summary>
                  <div className="feedback-candidate-detail">
                    <b>유저 입력</b>
                    <p>{feedbackPreview(userMessage, '질문 원문 없음', 260)}</p>
                    <b>챗봇 답변</b>
                    <p>{feedbackPreview(assistantAnswer, '답변 원문 없음', 360)}</p>
                  </div>
                </details>
              </article>
            );
          })}
        </div>
      )}
    </Panel>
  );
};

export const AlertsEventsView: React.FC<AlertsEventsViewProps> = ({
  buildAssistantContext,
  clusterName,
  fallbackQueues,
  lastUpdatedAt,
  onAssistantLaunch,
  onPageContextChange,
  onOpenItem,
  queues,
  rows,
  status,
}) => {
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
  const connectedIssues = queues.length > 0 ? queues : fallbackQueues;
  const eventItemTotal = viewMode === 'grouped' ? inboxGroups.length : filteredRawRows.length;
  const pageCount = Math.max(1, Math.ceil(eventItemTotal / pageSize));
  const currentPage = Math.min(page, pageCount);
  const startIndex = (currentPage - 1) * pageSize;
  const rangeStart = eventItemTotal === 0 ? 0 : startIndex + 1;
  const rangeEnd = Math.min(startIndex + pageSize, eventItemTotal);
  const visibleGroupRows = viewMode === 'grouped' ? inboxGroups.slice(startIndex, startIndex + pageSize) : [];
  const visibleRawRows = viewMode === 'raw' ? filteredRawRows.slice(startIndex, startIndex + pageSize) : [];
  const visibleAlertsForContext = (viewMode === 'grouped' ? visibleGroupRows : visibleRawRows.map((row) => eventGroupFromRow(row, queues)))
    .slice(0, 6)
    .map((group) => {
      const targetCount = new Set(group.rows.map((row) => row.target)).size;
      const namespaceCount = new Set(group.rows.map((row) => row.namespace)).size;
      return {
        count: group.rows.length,
        detail: group.detail,
        kind: group.kind,
        namespace: group.namespace,
        namespaceCount,
        reason: group.reason,
        severity: group.severity,
        target: group.target,
        targetCount,
        time: group.time,
        title: group.rows.length > 1 ? `${group.title} 반복 감지` : group.title,
      };
    });
  const selectedAlertForContext = selectedEventGroup
    ? {
        count: selectedEventGroup.rows.length,
        detail: selectedEventGroup.detail,
        kind: selectedEventGroup.kind,
        namespace: selectedEventGroup.namespace,
        reason: selectedEventGroup.reason,
        severity: selectedEventGroup.severity,
        target: selectedEventGroup.target,
        time: selectedEventGroup.time,
        title: selectedEventGroup.rows.length > 1 ? `${selectedEventGroup.title} 반복 감지` : selectedEventGroup.title,
      }
    : undefined;
  const alertsPageContextJson = JSON.stringify({
    aiopsViewContext: {
      cluster: clusterName,
      counts: {
        critical: criticalCount,
        normal: normalRows.length,
        warning: warningCount,
        visible: visibleAlertsForContext.length,
      },
      filters: {
        object: objectFilter,
        page: currentPage,
        pageSize,
        query,
        reason: reasonFilter,
        severity: severityFilter,
        showNormal,
        viewMode,
      },
      pageTitle: '알림 & 이벤트',
      route: '/dashboards/aiops/alerts',
      selectedAlert: selectedAlertForContext,
      summary: `${rawEventRows.length} events · Critical ${criticalCount} · Warning ${warningCount} · Normal ${normalRows.length}`,
      visibleAlerts: visibleAlertsForContext,
      visibleConnectedIssues: connectedIssues.slice(0, 5).map((item) => ({
        detail: item.detail,
        id: item.id,
        severity: item.severity,
        target: item.target,
        title: item.title,
      })),
    },
  });

  React.useEffect(() => {
    setPage(1);
  }, [objectFilter, pageSize, query, reasonFilter, severityFilter, showNormal, viewMode]);

  React.useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  React.useEffect(() => {
    if (!onPageContextChange) {
      return;
    }
    onPageContextChange(JSON.parse(alertsPageContextJson) as Record<string, unknown>);
  }, [alertsPageContextJson, onPageContextChange]);

  return (
    <section className="alerts-events-view stack-view">
      <section className="event-stream-bar">
        <div>
          <span>Event Stream</span>
          <strong>{clusterName}</strong>
        </div>
        <p>
          {rawEventRows.length} events · Critical {criticalCount} · Warning {warningCount} · Normal {normalRows.length}
          {' · '}최근 동기화 {formatTime(lastUpdatedAt)} · {viewMode === 'grouped' ? 'Reason 기준 그룹 보기' : '원본 이벤트 보기'}
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
                  <button className="portal-button" onClick={() => onOpenItem(item)} type="button">상세</button>
                </div>
              </article>
            ))}
          </div>
        </Panel>
      </section>

      <ChatFeedbackCandidatesPanel status={status} />

      <EventDetailDrawer
        buildAssistantContext={buildAssistantContext}
        group={selectedEventGroup}
        onAssistantLaunch={onAssistantLaunch}
        onClose={() => setSelectedEventGroup(null)}
        onOpenIssue={onOpenItem}
      />
    </section>
  );
};
