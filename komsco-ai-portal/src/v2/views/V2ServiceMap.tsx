import React from 'react';
import { ChevronRight } from 'lucide-react';
import type { V2Runtime } from '../V2App';
import type { V2View } from '../router';
import { Button, Card, CopyButton, Segmented, SevBadge, Toggle } from '../components/primitives';
import { V2Topology } from '../components/V2Topology';
import {
  buildImpactSignalStack,
  buildTraceInspector,
  clusterLabel,
  displayOpenShiftVersion,
  formatTime,
  topologyDerivedSignals,
  topologyPrimarySignals,
  topologyOtherSignals,
  type TopologyEdgeMode,
  type TopologyNodeKey,
} from '../lib/model';

const nextChecksByNode: Record<TopologyNodeKey, string[]> = {
  daemonsets: ['DaemonSet 상태', '노드별 Pod', '이벤트'],
  deployments: ['가용 수량', 'ReplicaSet', 'Pod readiness'],
  nodes: ['Node condition', 'Pressure', '스케줄링'],
  persistentvolumeclaims: ['PVC Bound', '마운트 이벤트', 'Pod 볼륨'],
  pods: ['Pod 이벤트', 'Container 상태', 'Owner chain'],
  replicasets: ['Ready 차이', 'Owner chain', 'Pod readiness'],
  routes: ['Route 대상', 'Service 연결', 'TLS/Host'],
  services: ['Selector', 'EndpointSlice', 'Pod 연결'],
  statefulsets: ['Ready 수량', 'PVC 연결', 'Pod identity'],
};

export const V2ServiceMap: React.FC<{
  onNavigate: (view: V2View) => void;
  runtime: V2Runtime;
}> = ({ onNavigate, runtime }) => {
  const { events, summary } = runtime;
  const [affectedOnly, setAffectedOnly] = React.useState(false);
  const [edgeMode, setEdgeMode] = React.useState<TopologyEdgeMode>('all');
  const [showEdgeLabels, setShowEdgeLabels] = React.useState(true);
  const [selectedNode, setSelectedNode] = React.useState<TopologyNodeKey>('pods');
  const [showInspectorCommands, setShowInspectorCommands] = React.useState(false);
  const primarySignals = topologyPrimarySignals(summary);
  const derivedSignals = topologyDerivedSignals(summary);
  const otherSignals = topologyOtherSignals(summary);
  const inspector = buildTraceInspector(summary, selectedNode);
  const impactSignalSections = buildImpactSignalStack(summary);
  const traceNodes = inspector.trace.split(/\s*->\s*/);
  const compactFocus = inspector.focus.includes('·')
    ? inspector.focus.split('·').slice(1).join('·').trim()
    : inspector.focus;
  const summarySignals = inspector.signals.filter((signal) => signal.label !== '완료 제외').slice(0, 5);
  const nextChecks = nextChecksByNode[selectedNode];
  const impactRows = impactSignalSections.flatMap((section) =>
    section.id === 'cleared'
      ? []
      : section.rows.map((row) => ({
          ...row,
          roleLabel: section.id === 'primary' ? 'Primary signal' : 'Derived',
        })),
  );
  const clearedRows = impactSignalSections.find((section) => section.id === 'cleared')?.rows ?? [];
  const inspectorBundle = inspector.commands
    .map((command) => `# ${command.title}\n${command.command}`)
    .join('\n\n');

  return (
    <div className="v2-view v2-service-map">
      <section className="v2-map-toolbar">
        <div className="v2-map-toolbar__info">
          <span className="v2-map-toolbar__eyebrow">서비스 맵 / 클러스터 토폴로지</span>
          <strong>{clusterLabel(summary)}</strong>
          <p>
            전체 네임스페이스 · 스냅샷 {formatTime(summary.updatedAt)} · 게이트웨이 정상 · OCP {displayOpenShiftVersion(summary.version.version)}
            {summary.nodes.total === 1 ? ' · 단일 노드 런타임' : ''}
          </p>
          <small>
            활성 신호 {summary.resources?.issues ?? 0}건 · Primary 파드 {primarySignals}건 · Derived 컨트롤러 {derivedSignals}건
            {otherSignals > 0 ? ` · 기타 ${otherSignals}건` : ''}
          </small>
        </div>
        <div className="v2-map-toolbar__controls">
          <Toggle checked={affectedOnly} label="영향만" onChange={setAffectedOnly} />
          <Segmented
            active={edgeMode}
            items={[
              { id: 'all', label: '전체 관계' },
              { id: 'traffic', label: '트래픽' },
              { id: 'ownership', label: '소유 관계' },
              { id: 'runtime', label: '런타임' },
            ]}
            onChange={(id) => setEdgeMode(id as TopologyEdgeMode)}
          />
          <Toggle checked={showEdgeLabels} label="관계 라벨" onChange={setShowEdgeLabels} />
        </div>
      </section>

      <Card
        actions={
          <SevBadge
            label={`노드 ${summary.nodes.ready}/${summary.nodes.total}`}
            severity={summary.nodes.notReady > 0 ? 'risk' : 'ok'}
          />
        }
        className="v2-map-page-card"
        flush
        title="클러스터 리소스 관계도"
      >
        <V2Topology
          affectedOnly={affectedOnly}
          edgeMode={edgeMode}
          events={events}
          onSelectNode={setSelectedNode}
          selectedNode={selectedNode}
          showEdgeLabels={showEdgeLabels}
          summary={summary}
        />
      </Card>

      <Card
        actions={
          <div className="v2-inline-actions">
            <Button onClick={() => onNavigate('rca')} size="sm">
              RCA 열기
            </Button>
            <Button
              disabled={inspector.commands.length === 0}
              onClick={() => setShowInspectorCommands((value) => !value)}
              size="sm"
              variant={showInspectorCommands ? 'primary' : 'outline'}
            >
              {showInspectorCommands ? 'oc 명령 닫기' : 'oc 명령 보기'}
            </Button>
          </div>
        }
        className="v2-inspector-card"
        title="선택 경로 요약"
      >
        <div className="v2-inspector">
          <div className="v2-inspector__main">
            <span className="v2-inspector__eyebrow">선택 경로</span>
            <div aria-label={inspector.trace} className="v2-inspector__path">
              {traceNodes.map((node, index) => (
                <React.Fragment key={`${node}-${index}`}>
                  {index > 0 && <ChevronRight aria-hidden="true" size={13} />}
                  <strong>{node}</strong>
                </React.Fragment>
              ))}
            </div>
            <div className="v2-inspector__finding">
              <div>
                <strong>
                  {inspector.title} · {compactFocus}
                </strong>
                <p>{inspector.insight}</p>
              </div>
              <SevBadge severity={inspector.severity} />
            </div>
          </div>
          <div className="v2-inspector__signals">
            {summarySignals.map((signal) => (
              <article key={`${signal.label}-${signal.value}`}>
                <span>{signal.label}</span>
                <strong>{signal.value}</strong>
              </article>
            ))}
          </div>
          <div className="v2-inspector__next">
            <span>다음 확인</span>
            <div>
              {nextChecks.map((check) => (
                <b key={`${selectedNode}-${check}`}>{check}</b>
              ))}
            </div>
          </div>
          {showInspectorCommands && (
            <div className="v2-inspector__commands">
              <div className="v2-inspector__commands-head">
                <span>oc 명령</span>
                <CopyButton label="전체 복사" text={inspectorBundle} />
              </div>
              {inspector.commands.map((command) => (
                <article className="v2-inspector__command" key={`${command.title}-${command.command}`}>
                  <div>
                    <strong>{command.title}</strong>
                    <code>{command.command}</code>
                  </div>
                  <CopyButton text={command.command} />
                </article>
              ))}
            </div>
          )}
        </div>
      </Card>

      <Card title="영향 후보">
        <div className="v2-impact-candidates">
          {impactRows.map((row) => (
            <article className={`v2-impact-candidate is-${row.severity}`} key={row.id}>
              <SevBadge severity={row.severity} />
              <div className="v2-impact-candidate__body">
                <div className="v2-impact-candidate__top">
                  <strong>{row.title}</strong>
                  <b>{row.metric}</b>
                </div>
                <p>{row.chips.slice(0, row.roleLabel === 'Primary signal' ? 4 : 3).join(' · ')}</p>
                <small>{row.roleLabel === 'Primary signal' ? 'Primary signal' : row.description}</small>
              </div>
            </article>
          ))}
          {clearedRows.length > 0 && (
            <div className="v2-impact-cleared">
              <span>정상 의존성</span>
              <strong>{clearedRows.map((row) => `${row.title} ${row.metric}`).join(' · ')}</strong>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
};
