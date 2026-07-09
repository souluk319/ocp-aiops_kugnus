import React from 'react';
import { Copy, Download, FileSearch } from 'lucide-react';
import type { QueueItem } from '../../types';
import type { V2Runtime } from '../V2App';
import type { V2View } from '../router';
import { Button, Card, CopyButton, Empty, SevBadge } from '../components/primitives';
import { V2Topology } from '../components/V2Topology';
import {
  buildPodRcaSummary,
  buildQueues,
  buildRcaCaseHeader,
  buildRcaCommandBundle,
  buildRcaEvidencePack,
  buildRcaFindings,
  buildRcaQueueGroups,
  buildRcaRunbookGates,
  buildRcaTimeline,
  clusterLabel,
  defaultRcaSelection,
  evidenceStatusLabel,
  formatTime,
  isClusterUpdateIssue,
  isDerivedWorkloadIssue,
  isPodIssue,
  rcaAvailableUpdates,
  rcaCaseId,
  rcaCurrentVersion,
  rcaIssueType,
  rcaQueueBadgeLabel,
  rcaQueueDetail,
  rcaReason,
  sampleRcaQueues,
} from '../lib/model';

export const V2Rca: React.FC<{
  onNavigate: (view: V2View) => void;
  onOpenItem: (item: QueueItem) => void;
  runtime: V2Runtime;
}> = ({ onNavigate, onOpenItem, runtime }) => {
  const { events, status, summary } = runtime;
  const liveQueues = buildQueues(summary, status);
  const sampleMode = liveQueues.length === 0;
  const queues = sampleMode ? sampleRcaQueues : liveQueues;
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
  const caseHeader = buildRcaCaseHeader(summary, selected, podSummary);
  const caseId = rcaCaseId(selected, selectedIndex);
  const [actionNote, setActionNote] = React.useState('');

  React.useEffect(() => {
    setSelectedId((current) => (queues.some((item) => item.id === current) ? current : defaultRcaSelection(queues)));
  }, [queues]);

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
      cluster: clusterLabel(summary),
      selected,
      issueType: selectedIssueType,
      podSummary:
        selectedIssueType === 'WORKLOAD_PODS' || selectedIssueType === 'WORKLOAD_DERIVED' ? podSummary : undefined,
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

  return (
    <div className="v2-view v2-rca">
      <section className={`v2-rca-case is-${selected?.severity ?? 'ok'}`}>
        <div className="v2-rca-case__main">
          <span className="v2-rca-case__family">{caseHeader.family}</span>
          <h2>
            <small>{caseId}</small>
            {caseHeader.title}
          </h2>
          <p>{caseHeader.finding}</p>
          <div className="v2-rca-case__telemetry">
            {caseHeader.metrics.map((metric) => (
              <span key={`${metric.label}-${metric.value}`}>
                {metric.label}
                <strong>{metric.value}</strong>
              </span>
            ))}
          </div>
          <div className="v2-rca-case__stats">
            <div>
              <span>증거</span>
              <strong>{evidencePack.length}</strong>
            </div>
            <div>
              <span>런북 게이트</span>
              <strong>{runbookGates.length}</strong>
            </div>
            <div>
              <span>타임라인</span>
              <strong>{timeline.length}</strong>
            </div>
            <div>
              <span>조사 큐</span>
              <strong>{queues.length}</strong>
            </div>
          </div>
          <div className="v2-rca-case__meta">
            <span>{caseHeader.issueLine}</span>
            <span>{caseHeader.scope}</span>
            <span>{caseHeader.caseState}</span>
            <span>{caseHeader.baseline}</span>
          </div>
        </div>
        <div className="v2-rca-case__actions">
          <Button icon={<Copy size={13} />} onClick={copyCommands} size="sm">
            oc 묶음
          </Button>
          <Button
            icon={<FileSearch size={13} />}
            onClick={() => setActionNote('원본 증거 YAML은 BE evidence store 연동 후 열 수 있습니다.')}
            size="sm"
          >
            원본 증거
          </Button>
          <Button icon={<Download size={13} />} onClick={exportBundle} size="sm" variant="primary">
            RCA 보고서
          </Button>
          {actionNote && <small className="v2-rca-case__note">{actionNote}</small>}
        </div>
      </section>

      <section className="v2-grid v2-grid--rca">
        <Card
          actions={<SevBadge label={sampleMode ? '샘플 데이터' : '실시간'} severity={sampleMode ? 'warn' : 'ok'} />}
          className="v2-rca-queue-card"
          title="조사 큐"
        >
          <div className="v2-rca-families">
            {queueGroups.map((group) => (
              <section className="v2-rca-family" key={group.id}>
                <h3>
                  {group.title}
                  <em>{group.items.length}</em>
                </h3>
                {group.items.map((item) => (
                  <button
                    className={`v2-rca-item is-${item.severity}${item.id === selected?.id ? ' is-selected' : ''}`}
                    key={item.id}
                    onClick={() => setSelectedId(item.id)}
                    type="button"
                  >
                    <SevBadge label={rcaQueueBadgeLabel(item)} severity={item.severity} />
                    <span className="v2-rca-item__text">
                      <strong>
                        {isPodIssue(item)
                          ? '파드 상태 저하'
                          : isDerivedWorkloadIssue(item)
                            ? `${item.target ?? item.title} 가용성 변화`
                            : item.title}
                      </strong>
                      <small>{rcaQueueDetail(summary, item, podSummary)}</small>
                    </span>
                  </button>
                ))}
              </section>
            ))}
          </div>
        </Card>

        <Card
          actions={
            selected && (
              <Button onClick={() => onOpenItem(selected)} size="sm">
                이슈 원본
              </Button>
            )
          }
          className="v2-rca-canvas-card"
          title="원인 분석 캔버스"
        >
          {selected ? (
            <div className="v2-findings">
              {findings.map((finding) => (
                <article className={`v2-finding is-${finding.tone}`} key={`${finding.kicker}-${finding.title}`}>
                  <span className="v2-finding__kicker">{finding.kicker}</span>
                  <strong>{finding.title}</strong>
                  <p>{finding.detail}</p>
                  <small>{finding.meta}</small>
                </article>
              ))}
            </div>
          ) : (
            <Empty label="분석할 이슈가 없습니다." />
          )}
        </Card>

        <Card className="v2-rca-evidence-card" title="증거 패키지">
          {selected ? (
            <div className="v2-evidence-pack">
              {evidencePack.map((row, index) => {
                const previous = evidencePack[index - 1];
                const showCommand = !previous || previous.source !== row.source || previous.command !== row.command;
                return (
                  <article className="v2-evidence-pack__row" key={`${row.source}-${row.field}`}>
                    <div className="v2-evidence-pack__grid">
                      <span className="v2-evidence-pack__source">{row.source}</span>
                      <strong>{row.field}</strong>
                      <b>{row.value}</b>
                      <em className={`is-${row.status}`}>{evidenceStatusLabel(row.status)}</em>
                    </div>
                    <small>
                      {row.collector} · {row.freshness}
                    </small>
                    {showCommand && (
                      <div className="v2-evidence-pack__cmd">
                        <code>{row.command}</code>
                        <CopyButton text={row.command} />
                      </div>
                    )}
                  </article>
                );
              })}
            </div>
          ) : (
            <Empty label="표시할 증거가 없습니다." />
          )}
        </Card>
      </section>

      <section className="v2-grid v2-grid--rca-trace">
        <Card
          className="v2-rca-trace-card"
          title={selectedIsUpdate ? '클러스터 업데이트 의존성 추적' : '워크로드 런타임 의존성 추적'}
        >
          {selectedIsUpdate ? (
            <div className="v2-update-trace">
              {[
                ['업데이트 채널', summary.version.channel ?? 'stable-4.20', `후보 ${rcaAvailableUpdates(summary, selected)}`],
                ['ClusterVersion', `version · 현재 ${rcaCurrentVersion(summary, selected)}`, `Upgradeable False · ${rcaReason(summary, selected)}`],
                ['CVO', 'Cluster Version Operator', 'RetrievedUpdates True · Progressing False'],
                ['CO', `ClusterOperators · Available ${summary.operators.available}/${summary.operators.total}`, `Degraded ${summary.operators.degraded} · Progressing ${summary.operators.progressing}`],
                ['MCP', 'MachineConfigPools', 'master/worker updated · degraded 0'],
                ['노드', `Ready ${summary.nodes.ready}/${summary.nodes.total}`, `NotReady ${summary.nodes.notReady}`],
                ['워크로드 영향', selected?.severity === 'risk' ? '높음' : '중간', '변경 창 검증 필요'],
              ].map(([title, detail, meta], index) => (
                <article className={`v2-update-trace__step${index === 1 ? ' is-attention' : ''}`} key={title}>
                  <span className="v2-update-trace__index">{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <strong>{title}</strong>
                    <p>{detail}</p>
                    <small>{meta}</small>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <V2Topology compact events={events} summary={summary} />
          )}
        </Card>

        <Card
          actions={
            <Button icon={<Copy size={13} />} onClick={copyCommands} size="sm">
              oc 복사
            </Button>
          }
          className="v2-runbook-card"
          title="런북 게이트"
        >
          <div className="v2-runbook-gates">
            {runbookGates.map((gate, index) => (
              <article className={`v2-runbook-gate is-${gate.tone}`} key={gate.id}>
                <span className="v2-runbook-gate__index">{String(index + 1).padStart(2, '0')}</span>
                <div className="v2-runbook-gate__body">
                  <strong>{gate.title}</strong>
                  <p>{gate.detail}</p>
                  <code>{gate.command}</code>
                </div>
                <div className="v2-runbook-gate__status">
                  <span className={`v2-gate-chip is-${gate.tone}`}>{gate.status}</span>
                  <small>{gate.gate}</small>
                </div>
              </article>
            ))}
          </div>
        </Card>
      </section>

      <section className="v2-grid v2-grid--two">
        <Card
          actions={
            <div className="v2-inline-actions">
              <Button icon={<Copy size={13} />} onClick={copyCommands} size="sm">
                oc 묶음 복사
              </Button>
              <Button icon={<Download size={13} />} onClick={exportBundle} size="sm">
                RCA 번들 내보내기
              </Button>
            </div>
          }
          title="RCA 명령 묶음"
        >
          <div className="v2-cmd-list">
            {commandBundle.map((command) => (
              <article className="v2-cmd-list__item" key={`${command.title}-${command.command}`}>
                <strong># {command.title}</strong>
                <code>{command.command}</code>
              </article>
            ))}
          </div>
          <div className="v2-rca-command-bar">
            <Button onClick={() => setActionNote('원본 증거 YAML은 BE evidence store 연동 후 열 수 있습니다.')} size="sm">
              원본 증거 열기
            </Button>
            <Button onClick={() => setActionNote('조치 후보는 실행 기록 화면에서 승인 상태와 서버 변경 여부까지 확인합니다.')} size="sm">
              조치 후보 확인
            </Button>
            <Button onClick={() => onNavigate('executions')} size="sm">
              조치 이력 보기
            </Button>
            {actionNote && <span className="v2-rca-command-bar__note">{actionNote}</span>}
          </div>
        </Card>

        <Card title="분석 타임라인">
          <div className="v2-rca-timeline">
            {timeline.map((entry) => (
              <article className="v2-rca-timeline__item" key={`${entry.title}-${entry.detail}`}>
                <time>{formatTime(summary.updatedAt)}</time>
                <div>
                  <strong>{entry.title}</strong>
                  <span>{entry.detail}</span>
                </div>
              </article>
            ))}
          </div>
        </Card>
      </section>
    </div>
  );
};
