import * as React from 'react';
import {
  Activity,
  AlertTriangle,
  ChevronRight,
  Search,
} from 'lucide-react';
import { actionRecords } from './executionLedgerModel';
import { severityClass, StatusBadge } from './portalBadges';
import { formatTime } from './portalModel';
import type {
  ActivityItem,
  AiopsRuntimeStatus,
  AlertItem,
  ClusterSummary,
  Endpoint,
  NavView,
  QueueItem,
  ScopeItem,
} from './types';

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

export const DashboardView: React.FC<{
  activities: ActivityItem[];
  alerts: AlertItem[];
  clock: string;
  endpoints: Endpoint[];
  formatActivitySource: (source?: string) => string;
  formatOpenShiftVersion: (version?: string) => string;
  getScopeDetailRows: (scope: ScopeItem) => Array<{ label: string; value: string }>;
  onNavigate: (view: NavView) => void;
  onOpenItem: (item: QueueItem) => void;
  queues: QueueItem[];
  renderEndpointTable: (endpoints: Endpoint[]) => React.ReactNode;
  renderTopology: () => React.ReactNode;
  scopes: ScopeItem[];
  status: AiopsRuntimeStatus;
  summary: ClusterSummary;
}> = ({
  activities,
  alerts,
  clock,
  endpoints,
  formatActivitySource,
  formatOpenShiftVersion,
  getScopeDetailRows,
  onNavigate,
  onOpenItem,
  queues,
  renderEndpointTable,
  renderTopology,
  scopes,
  status,
  summary,
}) => {
  const [queueFilter, setQueueFilter] = React.useState<'all' | 'risk' | 'warn'>('all');
  const [scopeQuery, setScopeQuery] = React.useState('');
  const [activeScope, setActiveScope] = React.useState('cluster');
  const scopeListRef = React.useRef<HTMLDivElement>(null);
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
              <b>{formatOpenShiftVersion(summary.version.version)}</b>
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
                    {getScopeDetailRows(scope).map((row) => (
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
          {renderTopology()}
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
          <QueueList
            items={visibleQueues}
            onOpenItem={onOpenItem}
            onOpenRcaCenter={() => onNavigate('rca')}
          />
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

        <IssueSummary
          formatOpenShiftVersion={formatOpenShiftVersion}
          queues={queues}
          summary={summary}
        />
      </section>

      {renderEndpointTable(endpoints)}

      <section className="portal-grid portal-grid--activity">
        <ActivityTimeline activities={activities} formatActivitySource={formatActivitySource} />
      </section>
    </div>
  );
};

export const KpiCard: React.FC<{ color: 'red' | 'green' | 'blue'; label: string; sub: string; value: string | number }> = ({
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
  onOpenRcaCenter?: () => void;
  onOpenItem: (item: QueueItem) => void;
}> = ({
  items,
  onOpenRcaCenter,
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
            {onOpenRcaCenter && (
              <button
                className="portal-button is-primary"
                onClick={onOpenRcaCenter}
                type="button"
              >
                RCA 센터
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

const IssueSummary: React.FC<{
  formatOpenShiftVersion: (version?: string) => string;
  queues: QueueItem[];
  summary: ClusterSummary;
}> = ({ formatOpenShiftVersion, queues, summary }) => (
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
            <span>OCP <strong>{formatOpenShiftVersion(summary.version.version)}</strong></span>
          </div>
        </div>
      </>
    )}
  </Panel>
);

const activityToneLabel: Record<ActivityItem['tone'], string> = {
  blue: '수집',
  green: '정상',
  orange: '주의',
  red: '위험',
  violet: '기록',
};

const ActivityTimeline: React.FC<{
  activities: ActivityItem[];
  formatActivitySource: (source?: string) => string;
}> = ({ activities, formatActivitySource }) => (
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
                      <small>{formatActivitySource(activity.source ?? activity.category ?? 'AIOps')}</small>
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


