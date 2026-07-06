import React from 'react';
import { AlertTriangle, Boxes, Cpu, Server } from 'lucide-react';
import type { V2Runtime } from '../V2App';
import { Card, CountUp, Donut, KpiStat, ProgressBar } from '../components/primitives';
import { V2EndpointTable } from '../components/V2EndpointTable';
import { buildEndpoints, localizeTelemetryText, resourceNameLabel } from '../lib/model';

export const V2Resources: React.FC<{ runtime: V2Runtime }> = ({ runtime }) => {
  const { summary } = runtime;
  const endpoints = buildEndpoints(summary);
  const resources = summary.resources?.items ?? [];
  const risk = endpoints.filter((endpoint) => endpoint.severity === 'risk').length;
  const warn = endpoints.filter((endpoint) => endpoint.severity === 'warn').length;
  const ok = endpoints.length - risk - warn;

  return (
    <div className="v2-view v2-resources">
      <section className="v2-kpi-row">
        <KpiStat
          icon={<AlertTriangle size={15} />}
          label="위험 리소스"
          severity={risk > 0 ? 'risk' : 'ok'}
          sub={`주의 ${warn}`}
          value={risk}
        />
        <KpiStat icon={<Boxes size={15} />} label="전체 리소스" severity="ok" sub="표시 대상" value={endpoints.length} />
        <KpiStat
          icon={<Server size={15} />}
          label="노드 상태"
          severity={summary.nodes.notReady > 0 ? 'risk' : 'ok'}
          sub={`비정상 ${summary.nodes.notReady}`}
          value={`${summary.nodes.ready}/${summary.nodes.total}`}
        />
        <KpiStat
          icon={<Cpu size={15} />}
          label="리소스 이슈"
          severity={summary.resources?.issues ? 'risk' : 'ok'}
          sub="게이트웨이 요약"
          value={summary.resources?.issues ?? 0}
        />
      </section>

      <V2EndpointTable endpoints={endpoints} />

      <section className="v2-grid v2-grid--distribution">
        <Card className="v2-distribution-card" title="리소스 그룹 분포">
          <div className="v2-distribution">
            {resources.map((resource) => {
              const ratio = Math.min(1, Number(resource.ready) / Math.max(1, resource.total));
              return (
                <article className="v2-distribution__row" key={resource.id}>
                  <div className="v2-distribution__text">
                    <strong>{resourceNameLabel(resource.id, resource.name, resource.kind)}</strong>
                    <span>{localizeTelemetryText(resource.detail)}</span>
                  </div>
                  <ProgressBar severity={resource.severity} value={ratio} />
                  <b className={`v2-distribution__score is-${resource.severity}`}>{resource.score}</b>
                </article>
              );
            })}
          </div>
        </Card>
        <Card className="v2-donut-card" title="상태 분포">
          <div className="v2-donut-wrap">
            <Donut
              center={
                <>
                  <strong>
                    <CountUp value={endpoints.length} />
                  </strong>
                  <span>리소스</span>
                </>
              }
              segments={[
                { severity: 'ok', value: ok },
                { severity: 'warn', value: warn },
                { severity: 'risk', value: risk },
              ]}
              size={150}
            />
            <ul className="v2-donut-legend">
              <li>
                <i className="is-ok" /> 정상 <strong>{ok}</strong>
              </li>
              <li>
                <i className="is-warn" /> 주의 <strong>{warn}</strong>
              </li>
              <li>
                <i className="is-risk" /> 위험 <strong>{risk}</strong>
              </li>
            </ul>
          </div>
        </Card>
      </section>
    </div>
  );
};
