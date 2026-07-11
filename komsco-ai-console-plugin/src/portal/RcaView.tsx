import * as React from 'react';
import type { AiopsExecutionMode, AssistantDraftPrompt, AssistantLaunchContext } from '../components/assistant.types';
import { buildRcaViewPageContext } from './aiopsPageContext';
import { isDerivedWorkloadIssue, isPodIssue } from './eventInboxModel';
import { severityClass, StatusBadge } from './portalBadges';
import { formatTime } from './portalModel';
import { evidenceStatusLabel } from './rcaEvidenceModel';
import {
  buildPodRcaSummary,
  buildRcaCaseHeader,
  buildRcaCommandBundle,
  buildRcaEvidencePack,
  buildRcaFindings,
  buildRcaQueueGroups,
  buildRcaRunbookGates,
  buildRcaTimeline,
  defaultRcaSelection,
  isClusterUpdateIssue,
  rcaAvailableUpdates,
  rcaCaseId,
  rcaCurrentVersion,
  rcaIssueType,
  rcaQueueBadgeLabel,
  rcaQueueDetail,
  rcaReason,
} from './rcaViewModel';
import type { ClusterSummary, NavView, QueueItem } from './types';

type AssistantLaunchRequest = {
  context: AssistantLaunchContext;
  executionMode?: AiopsExecutionMode;
  taskMode?: AssistantDraftPrompt['taskMode'];
};

type AssistantLaunchHandler = (request: AssistantLaunchRequest) => void;

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

export const RcaView: React.FC<{
  buildAssistantContext: (item: QueueItem, actionType: string) => AssistantLaunchContext;
  clusterName: string;
  fallbackQueues: QueueItem[];
  liveQueues: QueueItem[];
  onAssistantLaunch?: AssistantLaunchHandler;
  onNavigate: (view: NavView) => void;
  onOpenItem: (item: QueueItem) => void;
  onPageContextChange?: (context: Record<string, unknown>) => void;
  renderRuntimeTopology: () => React.ReactNode;
  summary: ClusterSummary;
}> = ({ buildAssistantContext, clusterName, fallbackQueues, liveQueues, onAssistantLaunch, onNavigate, onOpenItem, onPageContextChange, renderRuntimeTopology, summary }) => {
  const sampleMode = liveQueues.length === 0;
  const queues = sampleMode ? fallbackQueues : liveQueues;
  const [selectedId, setSelectedId] = React.useState(() => defaultRcaSelection(queues));
  const selected = queues.find((item) => item.id === selectedId) ?? queues[0];
  const selectedIndex = Math.max(0, queues.findIndex((item) => item.id === selected?.id));
  const selectedIsUpdate = selected ? isClusterUpdateIssue(selected) : false;
  const selectedIssueType = rcaIssueType(selected);
  const podSummary = buildPodRcaSummary(summary);
  const queueGroups = buildRcaQueueGroups(queues);
  const findings = buildRcaFindings(summary, selected, podSummary);
  const evidencePack = buildRcaEvidencePack(summary, selected, podSummary);
  const runbookGates = buildRcaRunbookGates(summary, selected, podSummary);
  const commandBundle = buildRcaCommandBundle(selected, runbookGates);
  const timeline = buildRcaTimeline(summary, selected, podSummary, findings);
  const caseHeader = buildRcaCaseHeader(summary, selected, podSummary, clusterName);
  const caseId = rcaCaseId(selected, selectedIndex);
  const [actionNote, setActionNote] = React.useState('');

  React.useEffect(() => {
    setSelectedId((current) => (queues.some((item) => item.id === current) ? current : defaultRcaSelection(queues)));
  }, [queues]);

  const rcaPageContext = React.useMemo(
    () => buildRcaViewPageContext({
      caseHeader,
      caseId,
      cluster: clusterName,
      dataSource: sampleMode ? 'sample' : 'live',
      evidence: evidencePack,
      findings,
      issueType: selectedIssueType,
      runbookGates,
      selectedIssue: selected ? {
        category: selected.category,
        detail: selected.detail,
        evidence: selected.evidence,
        id: selected.id,
        severity: selected.severity,
        source: selected.source,
        target: selected.target,
        title: selected.title,
        updatedAt: selected.updatedAt,
      } : undefined,
      timeline,
    }),
    [caseHeader, caseId, evidencePack, findings, runbookGates, sampleMode, selected, selectedIssueType, summary, timeline],
  );

  React.useEffect(() => {
    onPageContextChange?.(rcaPageContext);
  }, [onPageContextChange, rcaPageContext]);

  const copyCommands = React.useCallback(() => {
    const commands = commandBundle.map((command) => `# ${command.title}\n${command.command}`).join('\n\n');
    void navigator.clipboard?.writeText(commands);
    setActionNote('oc 명령 묶음을 클립보드에 복사했습니다.');
  }, [commandBundle]);

  const exportBundle = React.useCallback(() => {
    const bundle = {
      apiVersion: 'aiops.komsco/v1',
      generatedAt: new Date().toISOString(),
      kind: 'RcaBundle',
      caseId,
      cluster: clusterName,
      selected,
      issueType: selectedIssueType,
      podSummary: selectedIssueType === 'WORKLOAD_PODS' || selectedIssueType === 'WORKLOAD_DERIVED' ? podSummary : undefined,
      findings,
      evidencePack,
      runbookGates,
      commandBundle,
      timeline,
    };
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${caseId.toLowerCase()}-bundle.json`;
    link.click();
    URL.revokeObjectURL(url);
    setActionNote('RCA 번들 JSON을 생성했습니다.');
  }, [caseId, commandBundle, evidencePack, findings, podSummary, runbookGates, selected, selectedIssueType, summary, timeline]);

  const launchSelectedAssistant = React.useCallback(
    (actionType: string) => {
      if (!selected || !onAssistantLaunch) {
        return;
      }
      onAssistantLaunch({
        context: buildAssistantContext(selected, actionType),
      });
      setActionNote('선택한 RCA 컨텍스트를 Assistant에 전달했습니다.');
    },
    [buildAssistantContext, onAssistantLaunch, selected],
  );

  return (
    <section className="rca-workbench-v2 stack-view">
      <section className={`rca-case-header is-${selectedIssueType.toLowerCase().replaceAll('_', '-')}`}>
        <div className="rca-case-header__rail" aria-hidden="true">
          <span />
        </div>
        <div className="rca-case-header__main">
          <span className="rca-case-header__family">{caseHeader.family}</span>
          <h2><small>{caseId}</small>{caseHeader.title}</h2>
          <p>{caseHeader.finding}</p>
          <div className="rca-telemetry-row">
            {caseHeader.metrics.map((metric) => (
              <span key={`${metric.label}-${metric.value}`}>
                {metric.label}
                <strong>{metric.value}</strong>
              </span>
            ))}
          </div>
          <div className="rca-case-header__meta">
            <span>{caseHeader.issueLine}</span>
            <span>{caseHeader.scope}</span>
            <span>{caseHeader.caseState}</span>
            <span>{caseHeader.baseline}</span>
          </div>
        </div>
        <div className="rca-case-header__actions">
          {onAssistantLaunch && (
            <button className="portal-button is-primary" onClick={() => launchSelectedAssistant('rca')} type="button">
              Assistant RCA
            </button>
          )}
          <button className="portal-button" onClick={copyCommands} type="button">oc 묶음</button>
          <button className="portal-button" onClick={() => setActionNote('원본 증거 YAML은 BE evidence store 연동 후 열 수 있습니다.')} type="button">원본 증거</button>
          <button className="portal-button" onClick={exportBundle} type="button">RCA 보고서</button>
        </div>
      </section>

      <section className="rca-product-contract" aria-label="RCA 센터와 서비스 맵 역할">
        <article>
          <span>RCA 센터</span>
          <strong>증거 기반 원인 분석</strong>
          <p>원인 후보를 단순 텍스트로 끝내지 않고, 출처·필드·상태·확인 명령으로 검증합니다.</p>
          <b>증거 패키지 + Runbook Gate</b>
        </article>
        <article>
          <span>서비스 맵</span>
          <strong>의존성 기반 영향 경로</strong>
          <p>Route부터 Service, Pod, Node, PVC까지 이어지는 관계를 따라 장애 범위를 확인합니다.</p>
          <button className="portal-button" onClick={() => onNavigate('service-map')} type="button">
            서비스 맵 열기
          </button>
        </article>
      </section>

      <section className="rca-main-grid">
        <Panel
          className="rca-queue-panel"
          title="조사 큐"
          action={<StatusBadge label={sampleMode ? '샘플 데이터' : '실시간'} severity={sampleMode ? 'warn' : 'ok'} />}
        >
          <div className="rca-family-list">
            {queueGroups.map((group) => (
              <section key={group.id}>
                <h3>{group.title}</h3>
                {group.items.map((item) => (
                  <button
                    className={`rca-family-item ${item.id === selected?.id ? 'is-selected' : ''} ${severityClass(item.severity)}`}
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    type="button"
                  >
                    <StatusBadge label={rcaQueueBadgeLabel(item)} severity={item.severity} />
                    <span>
                      <strong>{isPodIssue(item) ? '파드 상태 저하' : isDerivedWorkloadIssue(item) ? `${item.target ?? item.title} 가용성 변화` : item.title}</strong>
                      <small>{rcaQueueDetail(summary, item, podSummary)}</small>
                    </span>
                  </button>
                ))}
              </section>
            ))}
          </div>
        </Panel>

        <Panel
          className="rca-canvas-panel"
          title="원인 분석 캔버스"
          action={
            selected && (
              <button className="portal-button" onClick={() => onOpenItem(selected)} type="button">
                이슈 원본
              </button>
            )
          }
        >
          {selected ? (
            <div className="finding-board">
              {findings.map((finding) => (
                <article className={`is-${finding.tone}`} key={`${finding.kicker}-${finding.title}`}>
                  <div>
                    <span>{finding.kicker}</span>
                    <strong>{finding.title}</strong>
                    <p>{finding.detail}</p>
                  </div>
                  <small>{finding.meta}</small>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState label="분석할 이슈가 없습니다." />
          )}
        </Panel>

        <Panel className="rca-evidence-panel" title="증거 패키지">
          {selected ? (
            <div className="evidence-pack-table">
              <div className="evidence-pack-table__head">
                <span>출처</span>
                <span>필드</span>
                <span>값</span>
                <span>상태</span>
              </div>
              {evidencePack.map((row, index) => {
                const previous = evidencePack[index - 1];
                const showCommand = !previous || previous.source !== row.source || previous.command !== row.command;
                return (
                  <article key={`${row.source}-${row.field}`}>
                    <span>{row.source}</span>
                    <strong>{row.field}</strong>
                    <b>{row.value}</b>
                    <em className={`is-${row.status}`}>{evidenceStatusLabel(row.status)}</em>
                    <small>{row.collector} · {row.freshness}</small>
                    {showCommand && <code>{row.command}</code>}
                  </article>
                );
              })}
            </div>
          ) : (
            <EmptyState label="표시할 증거가 없습니다." />
          )}
        </Panel>
      </section>

      <section className="portal-grid rca-trace-grid">
        <Panel
          className="rca-impact-panel"
          title={selectedIsUpdate ? '클러스터 업데이트 의존성 추적' : '워크로드 런타임 의존성 추적'}
        >
          {selectedIsUpdate ? (
            <div className="cluster-update-trace">
              {[
                ['업데이트 채널', summary.version.channel ?? 'stable-4.20', `후보 ${rcaAvailableUpdates(summary, selected)}`],
                ['ClusterVersion', `version · 현재 ${rcaCurrentVersion(summary, selected)}`, `Upgradeable False · ${rcaReason(summary, selected)}`],
                ['CVO', 'Cluster Version Operator', 'RetrievedUpdates True · Progressing False'],
                ['CO', `ClusterOperators · Available ${summary.operators.available}/${summary.operators.total}`, `Degraded ${summary.operators.degraded} · Progressing ${summary.operators.progressing}`],
                ['MCP', 'MachineConfigPools', 'master/worker updated · degraded 0'],
                ['노드', `Ready ${summary.nodes.ready}/${summary.nodes.total}`, `NotReady ${summary.nodes.notReady}`],
                ['워크로드 영향', selected?.severity === 'risk' ? '높음' : '중간', '변경 창 검증 필요'],
              ].map(([title, detail, meta], index, list) => (
                <React.Fragment key={title}>
                  <article className={index === 1 ? 'is-attention' : ''}>
                    <span>{String(index + 1).padStart(2, '0')}</span>
                    <strong>{title}</strong>
                    <p>{detail}</p>
                    <small>{meta}</small>
                  </article>
                  {index < list.length - 1 && <i aria-hidden="true" />}
                </React.Fragment>
              ))}
            </div>
          ) : (
            renderRuntimeTopology()
          )}
        </Panel>
        <Panel
          className="runbook-gates-panel"
          title="런북 게이트"
          action={
            <button className="portal-button" onClick={copyCommands} type="button">
              oc 복사
            </button>
          }
        >
          <div className="runbook-gate-list">
            {runbookGates.map((gate, index) => (
              <article className={`is-${gate.tone}`} key={gate.id}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <div>
                  <strong>{gate.title}</strong>
                  <p>{gate.detail}</p>
                  <code>{gate.command}</code>
                </div>
                <em>{gate.status}</em>
                <small>{gate.gate}</small>
              </article>
            ))}
          </div>
        </Panel>
      </section>

      <section className="portal-grid portal-grid--two">
        <Panel
          title="RCA 명령 묶음"
          action={
            <div className="rca-command-actions">
            <button className="portal-button" onClick={copyCommands} type="button">oc 묶음 복사</button>
            <button className="portal-button" onClick={exportBundle} type="button">RCA 번들 내보내기</button>
          </div>
          }
        >
          <div className="rca-command-preview">
            {commandBundle.map((command) => (
              <article key={`${command.title}-${command.command}`}>
                <strong># {command.title}</strong>
                <code>{command.command}</code>
              </article>
            ))}
          </div>
          <div className="rca-command-bar">
            <button className="portal-button" onClick={() => setActionNote('원본 증거 YAML은 BE evidence store 연동 후 열 수 있습니다.')} type="button">원본 증거 열기</button>
            <button
              className="portal-button"
              onClick={() => launchSelectedAssistant('action-plan')}
              type="button"
            >
              조치 후보 확인
            </button>
            <button className="portal-button" onClick={() => onNavigate('executions')} type="button">조치 이력 보기</button>
            {actionNote && <span>{actionNote}</span>}
          </div>
        </Panel>
        <Panel title="분석 타임라인">
          <div className="rca-audit-trail">
            {timeline.map((entry) => (
              <article key={`${entry.title}-${entry.detail}`}>
                <time>{formatTime(summary.updatedAt)}</time>
                <strong>{entry.title}</strong>
                <span>{entry.detail}</span>
              </article>
            ))}
          </div>
        </Panel>
      </section>
    </section>
  );
};

