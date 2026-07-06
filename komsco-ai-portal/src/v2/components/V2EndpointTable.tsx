import React from 'react';
import type { Endpoint, Severity } from '../../types';
import { Card, DataTable, Pagination, SearchInput, SevBadge, Tabs } from './primitives';
import { endpointPageSizeOptions } from '../lib/model';

type Filter = 'all' | Severity;

export const V2EndpointTable: React.FC<{ endpoints: Endpoint[] }> = ({ endpoints }) => {
  const [filter, setFilter] = React.useState<Filter>('all');
  const [query, setQuery] = React.useState('');
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(endpointPageSizeOptions[0]);

  const filtered = endpoints.filter((endpoint) => {
    if (filter !== 'all' && endpoint.severity !== filter) {
      return false;
    }
    if (!query) {
      return true;
    }
    const haystack = `${endpoint.name} ${endpoint.type} ${endpoint.group} ${endpoint.path}`.toLowerCase();
    return haystack.includes(query.toLowerCase());
  });
  const pageCount = Math.max(1, Math.ceil(filtered.length / pageSize));
  const clampedPage = Math.min(page, pageCount);
  const pageRows = filtered.slice((clampedPage - 1) * pageSize, clampedPage * pageSize);

  const counts = {
    all: endpoints.length,
    ok: endpoints.filter((endpoint) => endpoint.severity === 'ok').length,
    warn: endpoints.filter((endpoint) => endpoint.severity === 'warn').length,
    risk: endpoints.filter((endpoint) => endpoint.severity === 'risk').length,
  };

  return (
    <Card
      actions={
        <div className="v2-endpoint-controls">
          <Tabs
            active={filter}
            items={[
              { id: 'all', label: '전체', count: counts.all },
              { id: 'risk', label: '위험', count: counts.risk },
              { id: 'warn', label: '주의', count: counts.warn },
              { id: 'ok', label: '정상', count: counts.ok },
            ]}
            onChange={(id) => {
              setFilter(id as Filter);
              setPage(1);
            }}
          />
          <SearchInput
            onChange={(value) => {
              setQuery(value);
              setPage(1);
            }}
            placeholder="리소스, 유형, 경로 검색"
            value={query}
          />
        </div>
      }
      flush
      title="엔드포인트 테이블"
    >
      <DataTable
        columns={[
          {
            key: 'name',
            label: '리소스',
            render: (row: Endpoint) => (
              <div className="v2-endpoint-name">
                <strong>{row.name}</strong>
                <small>{row.path}</small>
              </div>
            ),
          },
          { key: 'type', label: '유형', width: '110px' },
          { key: 'group', label: '그룹', width: '120px' },
          {
            key: 'severity',
            label: '상태',
            render: (row: Endpoint) => <SevBadge severity={row.severity} />,
            width: '92px',
          },
          { key: 'cpu', label: 'CPU', align: 'right', width: '90px' },
          { key: 'memory', label: '메모리', align: 'right', width: '96px' },
          { key: 'latency', label: '지연', align: 'right', width: '84px' },
          { key: 'lastEvent', label: '최근 이벤트', width: '160px' },
        ]}
        emptyLabel="조건에 맞는 리소스가 없습니다"
        rows={pageRows}
      />
      <Pagination
        onPage={setPage}
        onPageSize={(size) => {
          setPageSize(size);
          setPage(1);
        }}
        page={clampedPage}
        pageSize={pageSize}
        pageSizeOptions={endpointPageSizeOptions}
        total={filtered.length}
        unit="리소스"
      />
    </Card>
  );
};
