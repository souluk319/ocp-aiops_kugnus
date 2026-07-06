import React from 'react';
import { ClipboardCheck, FileText, Network } from 'lucide-react';
import type { QueueItem } from '../../types';
import type { V2View } from '../router';
import { Drawer, SevBadge } from './primitives';
import {
  commandResourceLabel,
  evidenceLabel,
  evidenceRows,
  evidenceStatusLabel,
  impactRows,
  incidentLevelLabel,
  issueMetrics,
  issueNextSteps,
} from '../lib/model';

export const V2IssueDrawer: React.FC<{
  clusterName: string;
  item: QueueItem | null;
  onClose: () => void;
  onNavigate: (view: V2View) => void;
}> = ({ clusterName, item, onClose, onNavigate }) => {
  if (!item) {
    return null;
  }
  const metrics = issueMetrics(item);
  const impacts = impactRows(item);
  const evidence = evidenceRows(item);
  const runbook = issueNextSteps(item);
  const runCommand = (view: V2View) => {
    onClose();
    onNavigate(view);
  };

  return (
    <Drawer
      onClose={onClose}
      open
      sub={
        <span className="v2-issue-drawer__crumb">
          {clusterName} / {item.category ?? '운영 이슈'} / {item.target ?? item.title}
        </span>
      }
      title={item.title}
      wide
    >
      <section className={`v2-issue-hero is-${item.severity}`}>
        <div className="v2-issue-hero__top">
          <SevBadge label={incidentLevelLabel[item.severity]} severity={item.severity} />
          <div className="v2-issue-hero__telemetry">
            <span>
              감지 시각 <strong>{item.updatedAt ?? '-'}</strong>
            </span>
            <span>
              데이터 소스 <strong>{item.source ?? '게이트웨이 요약'}</strong>
            </span>
            <span>
              신뢰도 <strong>{item.updatedAt ? '실시간 소스' : '스냅샷'}</strong>
            </span>
          </div>
        </div>
        <p className="v2-issue-hero__detail">{item.detail}</p>
        {metrics.length > 0 && (
          <div className="v2-issue-hero__metrics">
            {metrics.map((metric) => (
              <span key={metric}>{metric}</span>
            ))}
          </div>
        )}
      </section>

      <section className="v2-issue-block">
        <h3 className="v2-issue-block__title">
          <Network size={14} />
          영향 범위
        </h3>
        <div className="v2-issue-impacts">
          {impacts.map((row) => (
            <div className="v2-issue-impacts__row" key={row.label}>
              <span>{row.label}</span>
              <strong>{row.value}</strong>
            </div>
          ))}
        </div>
      </section>

      <section className="v2-issue-block">
        <h3 className="v2-issue-block__title">
          <FileText size={14} />
          증거 스트림
        </h3>
        <div className="v2-evidence">
          <div className="v2-evidence__head">
            <span>신호</span>
            <span>값</span>
            <span>상태</span>
          </div>
          {evidence.map((row) => (
            <div className="v2-evidence__row" key={`${row.label}-${row.value}`}>
              <span>{evidenceLabel(row.label)}</span>
              <strong>{row.value}</strong>
              <em className={`is-${row.status}`}>{evidenceStatusLabel(row.status)}</em>
            </div>
          ))}
        </div>
      </section>

      <section className="v2-issue-block">
        <h3 className="v2-issue-block__title">
          <ClipboardCheck size={14} />
          런북 체크포인트
        </h3>
        <ol className="v2-runbook">
          {runbook.map((step, index) => (
            <li key={step}>
              <span className="v2-runbook__index">{String(index + 1).padStart(2, '0')}</span>
              <p>{step}</p>
              <em>{index === 2 ? '자동화 가능' : '미확인'}</em>
            </li>
          ))}
        </ol>
      </section>

      <div className="v2-issue-drawer__commands">
        <div className="v2-issue-drawer__commands-note">
          <span>다음 명령</span>
          <strong>권장: RCA 추적</strong>
        </div>
        <button className="v2-button is-primary is-md" onClick={() => runCommand('rca')} type="button">
          RCA 추적 열기
        </button>
        <button className="v2-button is-outline is-md" onClick={() => runCommand('resources')} type="button">
          {commandResourceLabel(item)}
        </button>
        <button className="v2-button is-ghost is-md" onClick={onClose} type="button">
          닫기
        </button>
      </div>
    </Drawer>
  );
};
