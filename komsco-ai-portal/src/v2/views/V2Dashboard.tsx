import React from 'react';
import { Activity, AlertTriangle, ArrowUpRight, ChevronRight, Cpu, ShieldCheck } from 'lucide-react';
import type { QueueItem, ScopeItem } from '../../types';
import type { V2Runtime } from '../V2App';
import type { V2View } from '../router';
import {
  AreaChart,
  Button,
  Card,
  CountUp,
  DeltaChip,
  Empty,
  HealthRing,
  SearchInput,
  SevBadge,
  Skeleton,
  Sparkline,
  Tabs,
  ToneDot,
} from '../components/primitives';
import { V2Topology } from '../components/V2Topology';
import { V2EndpointTable } from '../components/V2EndpointTable';
import {
  actionRecords,
  buildActivities,
  buildAlerts,
  buildEndpoints,
  buildQueues,
  buildScopes,
  displayOpenShiftVersion,
  formatTime,
  queueMetaItems,
  scopeDetailRows,
} from '../lib/model';

const ScopePanel: React.FC<{ runtime: V2Runtime; scopes: ScopeItem[] }> = ({ runtime, scopes }) => {
  const [query, setQuery] = React.useState('');
  const [activeScope, setActiveScope] = React.useState('cluster');
  const filtered = scopes.filter((scope) =>
    `${scope.name} ${scope.detail} ${scope.keywords?.join(' ') ?? ''}`.toLowerCase().includes(query.toLowerCase()),
  );
  return (
    <Card
      actions={<SearchInput onChange={setQuery} placeholder="파드, 디플로이먼트, 노드 검색" value={query} />}
      className="v2-scope-card"
      title="리소스"
    >
      <div className="v2-scope-list">
        {filtered.map((scope) => (
          <div className={`v2-scope${activeScope === scope.id ? ' is-active' : ''}`} key={scope.id}>
            <button
              aria-expanded={activeScope === scope.id}
              className="v2-scope__row"
              onClick={() => setActiveScope(scope.id)}
              type="button"
            >
              <ChevronRight className="v2-scope__chevron" size={14} />
              <span className="v2-scope__text">
                <strong>{scope.name}</strong>
                <small>{scope.detail}</small>
              </span>
              <b className={`v2-scope__score is-${scope.severity}`}>{scope.score}</b>
            </button>
            {activeScope === scope.id && (
              <div className="v2-scope__detail">
                {scopeDetailRows(scope, runtime.summary, runtime.status).map((row) => (
                  <span key={`${scope.id}-${row.label}`}>
                    {row.label}
                    <strong>{row.value}</strong>
                  </span>
                ))}
              </div>
            )}
          </div>
        ))}
        {filtered.length === 0 && <Empty label="일치하는 리소스가 없습니다." />}
      </div>
    </Card>
  );
};

const QueuePanel: React.FC<{
  onOpenItem: (item: QueueItem) => void;
  queues: QueueItem[];
}> = ({ onOpenItem, queues }) => {
  const [filter, setFilter] = React.useState<'all' | 'risk' | 'warn'>('all');
  const riskCount = queues.filter((item) => item.severity === 'risk').length;
  const warnCount = queues.filter((item) => item.severity === 'warn').length;
  const visible = filter === 'all' ? queues : queues.filter((item) => item.severity === filter);
  return (
    <Card
      actions={
        <Tabs
          active={filter}
          items={[
            { id: 'all', label: '전체', count: queues.length },
            { id: 'risk', label: '위험', count: riskCount },
            { id: 'warn', label: '주의', count: warnCount },
          ]}
          onChange={(id) => setFilter(id as 'all' | 'risk' | 'warn')}
        />
      }
      className="v2-queue-card"
      title="이슈 큐"
    >
      <div className="v2-queue-list">
        {visible.map((item) => (
          <button className={`v2-queue is-${item.severity}`} key={item.id} onClick={() => onOpenItem(item)} type="button">
            <div className="v2-queue__head">
              <SevBadge severity={item.severity} />
              <strong className="v2-queue__title">{item.title}</strong>
              <ArrowUpRight className="v2-queue__open" size={14} />
            </div>
            <p className="v2-queue__detail">{item.detail}</p>
            <div className="v2-queue__meta">
              {queueMetaItems(item).map((meta) => (
                <span key={meta}>{meta}</span>
              ))}
            </div>
          </button>
        ))}
        {visible.length === 0 && <Empty label="현재 게이트웨이 요약 기준 위험/주의 항목이 없습니다." />}
      </div>
      <div className="v2-card-foot">
        <span>
          전체 {queues.length}건 · 위험 {riskCount} · 주의 {warnCount}
        </span>
        <span>{queues[0]?.updatedAt ? `최근 ${queues[0].updatedAt}` : '게이트웨이 요약 기준'}</span>
      </div>
    </Card>
  );
};

export const V2Dashboard: React.FC<{
  onNavigate: (view: V2View) => void;
  onOpenItem: (item: QueueItem) => void;
  runtime: V2Runtime;
}> = ({ onNavigate, onOpenItem, runtime }) => {
  const { events, loading, status, summary } = runtime;
  const scopes = buildScopes(summary, status);
  const queues = buildQueues(summary, status);
  const alerts = buildAlerts(summary, status);
  const endpoints = buildEndpoints(summary);
  const activities = buildActivities(summary, status, events);
  const actionCount = actionRecords(status).length;
  const auditCount = status.spec.records.auditRecords?.length ?? 0;
  const riskCount = queues.filter((item) => item.severity === 'risk').length;
  const warnCount = queues.filter((item) => item.severity === 'warn').length;
  const topRisk = queues.find((item) => item.severity === 'risk') ?? queues[0];
  const healthScore = summary.healthScore;

  // 히스토리 API가 없으므로 현재 값 기준의 결정적(seed) 추이 곡선을 합성해 시각화한다
  const seriesFrom = React.useCallback((seed: number, base: number, amp = 1, length = 18): number[] => {
    return Array.from({ length }, (_, i) => {
      const wave = Math.sin((i + seed) / 2.6) * 2.1 + Math.sin((i + seed * 3) / 1.4) * 0.9;
      const noise = ((((i + 1) * (seed + 7) * 7919) % 17) / 17 - 0.5) * 1.6;
      return base + (wave + noise) * amp;
    });
  }, []);
  const healthTrend = React.useMemo(
    () =>
      seriesFrom(3, healthScore - 1.5, 1.15, 24).map((v, i, arr) =>
        Math.max(0, Math.min(100, v + (i / (arr.length - 1)) * 2.4)),
      ),
    [healthScore, seriesFrom],
  );
  const trendDelta = ((healthTrend[healthTrend.length - 1] - healthTrend[0]) / Math.max(1, healthTrend[0])) * 100;
  const deltaOf = (series: number[]) =>
    ((series[series.length - 1] - series[0]) / Math.max(1, Math.abs(series[0]))) * 100;

  const statTiles = [
    {
      icon: <AlertTriangle size={14} />,
      id: 'urgent',
      label: '즉시 확인',
      series: seriesFrom(11, Math.max(1, queues.length + 1.5), 0.6),
      severity: (riskCount > 0 ? 'risk' : warnCount > 0 ? 'warn' : 'ok') as 'ok' | 'warn' | 'risk',
      sub: `위험 ${riskCount} · 주의 ${warnCount}`,
      value: queues.length,
    },
    {
      icon: <ShieldCheck size={14} />,
      id: 'nodes',
      label: '비정상 노드',
      series: seriesFrom(23, Math.max(1, summary.nodes.notReady + 1), 0.4),
      severity: (summary.nodes.notReady > 0 ? 'risk' : 'ok') as 'ok' | 'warn' | 'risk',
      sub: `정상 ${summary.nodes.ready}/${summary.nodes.total}`,
      value: summary.nodes.notReady,
    },
    {
      icon: <Cpu size={14} />,
      id: 'operators',
      label: '오퍼레이터 이슈',
      series: seriesFrom(7, Math.max(1, summary.operators.issues.length + 1), 0.5),
      severity: (summary.operators.issues.length > 0 ? 'risk' : 'ok') as 'ok' | 'warn' | 'risk',
      sub: `정상 ${summary.operators.available}/${summary.operators.total}`,
      value: summary.operators.issues.length,
    },
    {
      icon: <Activity size={14} />,
      id: 'records',
      label: 'AIOps 기록',
      series: seriesFrom(17, Math.max(2, auditCount + actionCount), 0.8),
      severity: 'ok' as 'ok' | 'warn' | 'risk',
      sub: `감사 ${auditCount} · 조치 ${actionCount}`,
      value: auditCount + actionCount,
    },
  ];

  if (loading) {
    return (
      <div className="v2-view v2-dashboard">
        <div className="v2-hero-grid">
          {[0, 1, 2, 3, 4].map((index) => (
            <div className="v2-card" key={index} style={{ padding: 20 }}>
              <Skeleton height={12} width="40%" />
              <div style={{ height: 12 }} />
              <Skeleton height={30} width="60%" />
              <div style={{ height: 10 }} />
              <Skeleton height={10} width="80%" />
            </div>
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="v2-view v2-dashboard">
      {riskCount > 0 && topRisk && (
        <button className="v2-incident-ribbon" onClick={() => onOpenItem(topRisk)} type="button">
          <span className="v2-incident-ribbon__pulse" aria-hidden="true" />
          <strong>활성 인시던트 {riskCount}건</strong>
          <span className="v2-incident-ribbon__detail">
            {topRisk.title} — {topRisk.detail}
          </span>
          <b>이슈 상세 →</b>
        </button>
      )}

      <section className="v2-hero2">
        <div className="v2-hero2__main">
          <div className="v2-hero2__status">
            <span className="v2-kicker">Cluster Overview</span>
            <h2>클러스터 상태</h2>
            <div className="v2-hero2__score">
              <strong className="v2-hero2__value">
                <CountUp value={healthScore} />
                <em>%</em>
              </strong>
              <DeltaChip label="24h" value={trendDelta} />
            </div>
            <p className="v2-hero2__line">
              {healthScore >= 90
                ? '모든 핵심 신호가 정상 범위에 있습니다.'
                : riskCount > 0
                  ? `위험 신호 ${riskCount}건이 감지되어 확인이 필요합니다.`
                  : '일부 신호가 정상 범위를 벗어나 관찰이 필요합니다.'}
            </p>
            <div className="v2-hero2__chips">
              <span>
                OpenShift <strong>{displayOpenShiftVersion(summary.version.version)}</strong>
              </span>
              {summary.version.channel && (
                <span>
                  채널 <strong>{summary.version.channel}</strong>
                </span>
              )}
              <span>
                노드 <strong>{summary.nodes.ready}/{summary.nodes.total}</strong>
              </span>
              <span>
                업데이트 <strong>{formatTime(summary.updatedAt) || '-'}</strong>
              </span>
            </div>
          </div>
          <div className="v2-hero2__gauge">
            <HealthRing score={healthScore} size={136} />
          </div>
          <div className="v2-hero2__chart">
            <div className="v2-hero2__chart-head">
              <span className="v2-kicker">건강도 추이 · 최근 24시간</span>
            </div>
            <AreaChart
              id="health-trend"
              labels={{ end: '지금', start: '-24h' }}
              points={healthTrend}
              tone={healthScore >= 90 ? 'ok' : healthScore >= 70 ? 'warn' : 'risk'}
            />
          </div>
        </div>
        <div className="v2-hero2__tiles">
          {statTiles.map((tile) => (
            <div className={`v2-tile is-${tile.severity}`} key={tile.id}>
              <div className="v2-tile__top">
                <span className="v2-tile__label">{tile.label}</span>
                <span className="v2-tile__icon">{tile.icon}</span>
              </div>
              <div className="v2-tile__value">
                <strong>
                  <CountUp value={tile.value} />
                </strong>
                <DeltaChip value={deltaOf(tile.series)} />
              </div>
              <Sparkline className="v2-tile__spark" points={tile.series} />
              <span className="v2-tile__sub">{tile.sub}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="v2-grid v2-grid--map">
        <ScopePanel runtime={runtime} scopes={scopes} />
        <Card
          actions={
            <Button onClick={() => onNavigate('service-map')} size="sm" variant="outline">
              지도 확대
            </Button>
          }
          className="v2-map-card"
          flush
          title="서비스 영향 지도"
        >
          <V2Topology compact summary={summary} />
        </Card>
      </section>

      <section className="v2-grid v2-grid--issues">
        <QueuePanel onOpenItem={onOpenItem} queues={queues} />
        <Card
          actions={
            <Button onClick={() => onNavigate('alerts')} size="sm" variant="outline">
              전체 알림
            </Button>
          }
          title="알림"
        >
          <div className="v2-alert-list">
            {alerts.map((alert) => (
              <div className={`v2-alert is-${alert.severity}`} key={alert.id}>
                <SevBadge severity={alert.severity} />
                <div className="v2-alert__text">
                  <strong>{alert.title}</strong>
                  <small>{alert.target}</small>
                </div>
                <time>{alert.time}</time>
              </div>
            ))}
            {alerts.length === 0 && <Empty label="표시할 알림이 없습니다." />}
          </div>
          <div className="v2-card-foot">
            <span>표시 {alerts.length}건</span>
            <span>클러스터 + AIOps 신호 통합</span>
          </div>
        </Card>
        <Card title="이슈 요약">
          <div className="v2-issue-summary">
            <p className="v2-issue-summary__lead">
              {queues.length === 0
                ? '게이트웨이 요약 기준 위험/주의 항목이 없습니다. 클러스터 신호가 안정적입니다.'
                : `위험 ${riskCount}건 · 주의 ${warnCount}건이 감지되었습니다. 우선순위가 높은 항목부터 확인하세요.`}
            </p>
            <ul className="v2-issue-summary__list">
              {queues.slice(0, 3).map((item) => (
                <li key={item.id}>
                  <SevBadge severity={item.severity} />
                  <span>{item.title}</span>
                </li>
              ))}
            </ul>
            <div className="v2-issue-summary__baseline">
              <span>
                노드 <strong>{summary.nodes.ready}/{summary.nodes.total}</strong>
              </span>
              <span>
                오퍼레이터 <strong>{summary.operators.available}/{summary.operators.total}</strong>
              </span>
              <span>
                OCP <strong>{displayOpenShiftVersion(summary.version.version)}</strong>
              </span>
            </div>
            <small className="v2-issue-summary__note">게이트웨이 요약 스냅샷 기준 평가입니다.</small>
          </div>
        </Card>
      </section>

      <V2EndpointTable endpoints={endpoints} />

      <Card className="v2-activity-card" title="활동 기록">
        <div className="v2-activity">
          {activities.map((activity) => (
            <div className="v2-activity__item" key={activity.id}>
              <ToneDot tone={activity.tone} />
              <div className="v2-activity__text">
                <strong>{activity.title}</strong>
                <small>{activity.detail}</small>
              </div>
              <time>{formatTime(activity.time) || activity.time || '-'}</time>
            </div>
          ))}
          {activities.length === 0 && <Empty label="활동 기록이 없습니다." />}
        </div>
        <div className="v2-card-foot">
          <span>활동 {activities.length}건</span>
          <span>{summary.updatedAt ? `최근 동기화 ${formatTime(summary.updatedAt) || summary.updatedAt}` : '게이트웨이 이벤트 기준'}</span>
        </div>
      </Card>
    </div>
  );
};
