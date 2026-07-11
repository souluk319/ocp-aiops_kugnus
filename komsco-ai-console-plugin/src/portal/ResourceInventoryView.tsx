import * as React from 'react';
import { ChevronLeft, ChevronRight, Search } from 'lucide-react';
import { KpiCard } from './DashboardView';
import { severityClass, StatusBadge } from './portalBadges';
import {
  buildEndpoints,
  localizeTelemetryText,
  resourceNameLabel,
} from './portalDisplayModel';
import type { ClusterSummary, Endpoint, Severity } from './types';

const endpointPageSizeOptions = [10, 25, 50];

const Panel: React.FC<{
  children: React.ReactNode;
  title: string;
}> = ({ children, title }) => (
  <section className="portal-panel ">
    <div className="portal-panel__head">
      <div className="portal-panel__title">{title}</div>
    </div>
    <div className="portal-panel__body">{children}</div>
  </section>
);

export const EndpointTable: React.FC<{
  endpoints: Endpoint[];
}> = ({ endpoints }) => {
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(10);
  const [query, setQuery] = React.useState('');
  const [severityFilter, setSeverityFilter] = React.useState<'all' | Severity>('all');
  const okCount = endpoints.filter((endpoint) => endpoint.severity === 'ok').length;
  const warnCount = endpoints.filter((endpoint) => endpoint.severity === 'warn').length;
  const riskCount = endpoints.filter((endpoint) => endpoint.severity === 'risk').length;
  const endpointTabs: Array<{ id: 'all' | Severity; label: string; value: number }> = [
    { id: 'all', label: '전체', value: endpoints.length },
    { id: 'ok', label: '정상', value: okCount },
    { id: 'warn', label: '주의', value: warnCount },
    { id: 'risk', label: '위험', value: riskCount },
  ];
  const normalizedQuery = query.trim().toLowerCase();
  const visibleEndpoints = endpoints.filter((endpoint) => {
    const matchesSeverity = severityFilter === 'all' || endpoint.severity === severityFilter;
    const searchable = `${endpoint.name} ${endpoint.type} ${endpoint.group} ${endpoint.path}`.toLowerCase();
    return matchesSeverity && (!normalizedQuery || searchable.includes(normalizedQuery));
  });
  const pageCount = Math.max(1, Math.ceil(visibleEndpoints.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const startIndex = (currentPage - 1) * pageSize;
  const pageEndpoints = visibleEndpoints.slice(startIndex, startIndex + pageSize);
  const rangeStart = visibleEndpoints.length === 0 ? 0 : startIndex + 1;
  const rangeEnd = Math.min(startIndex + pageSize, visibleEndpoints.length);

  React.useEffect(() => {
    setPage(1);
  }, [normalizedQuery, pageSize, severityFilter]);

  React.useEffect(() => {
    setPage((current) => Math.min(current, pageCount));
  }, [pageCount]);

  return (
    <section className="portal-panel table-panel">
      <div className="table-panel__top">
        <div className="portal-panel__title">클러스터 리소스</div>
        <div className="portal-tabs">
          {endpointTabs.map((tab) => (
            <button
              className={severityFilter === tab.id ? 'is-active' : ''}
              key={tab.id}
              onClick={() => setSeverityFilter(tab.id)}
              type="button"
            >
              {tab.label} {tab.value}
            </button>
          ))}
        </div>
        <label className="portal-search">
          <Search />
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="리소스 검색"
            value={query}
          />
        </label>
        <label className="table-page-size">
          <span>페이지당</span>
          <select
            aria-label="페이지당 리소스 수"
            onChange={(event) => setPageSize(Number(event.target.value))}
            value={pageSize}
          >
            {endpointPageSizeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>
      </div>
      <div className="table-scroll">
        <table className="endpoint-table">
          <thead>
            <tr>
              <th>이름</th>
              <th>유형</th>
              <th>그룹</th>
              <th>상태</th>
              <th>CPU</th>
              <th>메모리</th>
              <th>응답시간</th>
              <th>최근 이벤트</th>
            </tr>
          </thead>
          <tbody>
            {visibleEndpoints.length === 0 ? (
              <tr>
                <td colSpan={8}>조건에 맞는 리소스가 없습니다.</td>
              </tr>
            ) : (
              pageEndpoints.map((endpoint) => (
                <tr key={endpoint.id}>
                  <td>
                    <strong>{endpoint.name}</strong>
                    <small>{endpoint.path}</small>
                  </td>
                  <td>{endpoint.type}</td>
                  <td>{endpoint.group}</td>
                  <td>
                    <StatusBadge severity={endpoint.severity} />
                  </td>
                  <td>{endpoint.cpu}</td>
                  <td>{endpoint.memory}</td>
                  <td>{endpoint.latency}</td>
                  <td>
                    <span className={`event-dot ${severityClass(endpoint.severity)}`} />
                    {endpoint.lastEvent}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
      <div className="table-pagination">
        <span className="table-pagination__summary">
          {rangeStart}-{rangeEnd} / {visibleEndpoints.length}
        </span>
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
    </section>
  );
};

export const ResourceInventoryView: React.FC<{
  summary: ClusterSummary;
}> = ({ summary }) => {
  const endpoints = buildEndpoints(summary);
  const resources = summary.resources?.items ?? [];
  const risk = endpoints.filter((endpoint) => endpoint.severity === 'risk').length;
  const warn = endpoints.filter((endpoint) => endpoint.severity === 'warn').length;

  return (
    <section className="resource-inventory stack-view">
      <section className="inventory-summary-grid">
        <KpiCard color={risk > 0 ? 'red' : 'green'} label="위험 리소스" sub={`주의 ${warn}`} value={risk} />
        <KpiCard color="blue" label="전체 리소스" sub="표시 대상" value={endpoints.length} />
        <KpiCard color={summary.nodes.notReady > 0 ? 'red' : 'green'} label="노드 상태" sub={`비정상 ${summary.nodes.notReady}`} value={`${summary.nodes.ready}/${summary.nodes.total}`} />
        <KpiCard color={summary.resources?.issues ? 'red' : 'green'} label="리소스 이슈" sub="게이트웨이 요약" value={summary.resources?.issues ?? 0} />
      </section>
      <EndpointTable endpoints={endpoints} />
      <Panel title="리소스 그룹 분포">
        <div className="resource-distribution">
          {resources.map((resource) => (
            <article key={resource.id}>
              <div>
                <strong>{resourceNameLabel(resource.id, resource.name, resource.kind)}</strong>
                <span>{localizeTelemetryText(resource.detail)}</span>
              </div>
              <div className="meter"><span style={{ width: `${Math.min(100, Number(resource.ready) / Math.max(1, resource.total) * 100)}%` }} /></div>
              <b>{resource.score}</b>
            </article>
          ))}
        </div>
      </Panel>
    </section>
  );
};
