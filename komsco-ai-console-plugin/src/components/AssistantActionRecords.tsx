import * as React from 'react';
import { Button } from '@patternfly/react-core';

import {
  CoolCheckIcon,
  CoolClockIcon,
  CoolListChecklistIcon,
  CoolShieldCheckIcon,
  CoolTerminalIcon,
} from './coolicons';
import {
  getActionRecordProof,
  getActionRecordStage,
  getActionRecordStageLabel,
  getExecutionOutcomeSummary,
  getPhaseTone,
  getPlanSummary,
  getRecordName,
  getRecordPhase,
  getRecordTargetLabel,
  phaseLabelKo,
} from './assistant.actionRecords';
import type {
  AiopsExecutionMode,
  AiopsLifecycleStage,
  AiopsRecordAction,
  AiopsRecordView,
  ConversationActionRef,
} from './assistant.types';
import type { AiopsRuntimeStatus } from '../services/aiGateway';

const ACTION_STAGE_ORDER: AiopsLifecycleStage[] = ['proposal', 'plan', 'approval', 'execution'];

const StatusTag: React.FC<{
  label: string;
  tone?: 'ok' | 'warn' | 'danger' | 'review' | 'neutral';
}> = ({ label, tone = 'neutral' }) => (
  <span className={`komsco-ai__scope-tag komsco-ai__scope-tag--${tone}`}>{label}</span>
);

export const ActionStageDots: React.FC<{ stage: AiopsLifecycleStage }> = ({ stage }) => {
  const currentIndex = ACTION_STAGE_ORDER.indexOf(stage);

  return (
    <span className="komsco-ai__action-stage-dots" aria-hidden="true">
      {ACTION_STAGE_ORDER.map((step, index) => (
        <span
          className={`komsco-ai__action-stage-dot${
            index < currentIndex
              ? ' komsco-ai__action-stage-dot--done'
              : index === currentIndex
                ? ' komsco-ai__action-stage-dot--current'
                : ''
          }`}
          key={step}
        />
      ))}
    </span>
  );
};

export const ActionStageIcon: React.FC<{ stage: AiopsLifecycleStage }> = ({ stage }) => {
  const Icon =
    stage === 'execution'
      ? CoolCheckIcon
      : stage === 'approval'
        ? CoolClockIcon
        : stage === 'plan'
          ? CoolShieldCheckIcon
          : CoolListChecklistIcon;

  return (
    <span className={`komsco-ai__action-stage-icon is-${stage}`} aria-hidden="true">
      <Icon />
    </span>
  );
};

const primaryActionLabel = (action: AiopsRecordAction): string => {
  if (action.step === 'create-plan') {
    return 'Action Plan 생성';
  }
  if (action.step === 'approve-plan') {
    return '승인 요청';
  }
  if (action.step === 'approve-execute-plan') {
    return '승인 후 실행';
  }
  if (action.step === 'execute-approval') {
    return '실행';
  }
  return action.label;
};

const actionCardMetaLabel = (stage: AiopsLifecycleStage): string => {
  if (stage === 'proposal') {
    return '조치 후보';
  }
  if (stage === 'plan') {
    return '승인 가능한 계획';
  }
  if (stage === 'approval') {
    return '승인 결정';
  }
  return '실행 결과';
};

export const PlanSummaryBlock: React.FC<{
  executionMode?: AiopsExecutionMode;
  record: AiopsRecordView;
}> = ({ executionMode, record }) => {
  if (getActionRecordStage(record) !== 'plan') {
    return null;
  }

  const summary = getPlanSummary(record);
  if (!summary) {
    return null;
  }

  return (
    <div className="komsco-ai__plan-summary">
      <span className="komsco-ai__plan-summary-policy">{summary.toolLabel}</span>
      <StatusTag label={`위험도 ${summary.riskLabel}`} tone={summary.riskTone} />
      <span className="komsco-ai__plan-summary-rollback">
        {summary.rollbackPossible ? '자동 롤백 가능' : '자동 롤백 미지원'}
      </span>
      {executionMode !== 'unrestricted' &&
        (summary.risk === 'medium' || summary.risk === 'high') && (
          <p className="komsco-ai__plan-summary-note">
            위험도가 {summary.riskLabel}이라 이 조치를 제안한 본인은 승인할 수 없습니다. 다른
            담당자의 승인이 필요합니다.
          </p>
        )}
    </div>
  );
};

type AssistantRailActionRecordsProps = {
  aiopsStatus: AiopsRuntimeStatus | null;
  busyActionId: string;
  collapseRemaining?: boolean;
  emptyLabel: string;
  executionMode: AiopsExecutionMode;
  onAction: (record: AiopsRecordView, action: AiopsRecordAction) => void;
  records: AiopsRecordView[];
  resolveAction: (
    record: AiopsRecordView,
    aiopsStatus: AiopsRuntimeStatus | null,
    executionMode: AiopsExecutionMode,
  ) => AiopsRecordAction | null;
  visibleLimit?: number;
};

export const AssistantRailActionRecords: React.FC<AssistantRailActionRecordsProps> = ({
  aiopsStatus,
  busyActionId,
  collapseRemaining = false,
  emptyLabel,
  executionMode,
  onAction,
  records,
  resolveAction,
  visibleLimit = 6,
}) => {
  if (records.length === 0) {
    return <div className="komsco-ai__rail-empty">{emptyLabel}</div>;
  }

  const visibleRecords = records.slice(0, visibleLimit);
  const hiddenRecords = records.slice(visibleLimit);

  const renderRow = (record: AiopsRecordView) => {
    const phase = getRecordPhase(record);
    const action = resolveAction(record, aiopsStatus, executionMode);
    const actions =
      action?.step === 'approve-plan'
        ? [action, { ...action, label: '거절', step: 'reject-plan' as const }]
        : action
          ? [action]
          : [];

    return (
      <div
        className="komsco-ai__rail-command"
        data-action-lifecycle-stage={getActionRecordStage(record)}
        key={getRecordName(record) || phase}
      >
        <div className="komsco-ai__rail-command-head">
          <div className="komsco-ai__rail-command-title">
            <ActionStageDots stage={getActionRecordStage(record)} />
            <span>{getActionRecordStageLabel(record, executionMode)}</span>
            <code>{getRecordName(record) || record.kind || 'record'}</code>
          </div>
          {phase !== 'sealed' && <StatusTag label={phaseLabelKo(phase)} tone={getPhaseTone(phase)} />}
        </div>
        <p>{getRecordTargetLabel(record)}</p>
        <p className="komsco-ai__rail-action-proof">
          {getActionRecordProof(record, executionMode)}
        </p>
        <PlanSummaryBlock record={record} executionMode={executionMode} />
        {actions.length > 0 && (
          <div className="komsco-ai__rail-action-row">
            {actions.map((item) => {
              const actionId = `${item.step}:${getRecordName(record)}`;
              const busy = actionId === busyActionId;
              return (
                <Button
                  className="komsco-ai__action-button"
                  data-answer-action-step={item.step}
                  isDisabled={busy || Boolean(item.disabledReason)}
                  isLoading={busy}
                  key={item.step}
                  onClick={() => onAction(record, item)}
                  size="sm"
                  title={item.disabledReason}
                  variant={item.step === 'reject-plan' ? 'link' : 'secondary'}
                >
                  <span className="komsco-ai__rail-action-icon">
                    <CoolTerminalIcon />
                  </span>
                  {busy ? '처리 중' : item.label}
                </Button>
              );
            })}
            {action?.disabledReason && (
              <span className="komsco-ai__rail-action-note">{action.disabledReason}</span>
            )}
          </div>
        )}
        <details className="komsco-ai__rail-command-detail">
          <summary>상세보기 (JSON)</summary>
          <pre>{JSON.stringify(record, null, 2)}</pre>
        </details>
      </div>
    );
  };

  return (
    <>
      {visibleRecords.map(renderRow)}
      {collapseRemaining && hiddenRecords.length > 0 && (
        <details className="komsco-ai__rail-collapse">
          <summary>나머지 {hiddenRecords.length}건 펼쳐보기</summary>
          {hiddenRecords.map(renderRow)}
        </details>
      )}
    </>
  );
};

type AssistantAnswerActionsProps = {
  aiopsActionError: string;
  aiopsActionNotice: string;
  aiopsStatus: AiopsRuntimeStatus | null;
  busyActionId: string;
  executionMode: AiopsExecutionMode;
  fallbackRefs?: ConversationActionRef[];
  onAction: (record: AiopsRecordView, action: AiopsRecordAction) => void;
  records: AiopsRecordView[];
  resolveAction: (
    record: AiopsRecordView,
    aiopsStatus: AiopsRuntimeStatus | null,
    executionMode: AiopsExecutionMode,
  ) => AiopsRecordAction | null;
};

const AssistantAnswerActions: React.FC<AssistantAnswerActionsProps> = ({
  aiopsActionError,
  aiopsActionNotice,
  aiopsStatus,
  busyActionId,
  executionMode,
  fallbackRefs = [],
  onAction,
  records,
  resolveAction,
}) => {
  const visibleFallbackRefs = records.length === 0 ? fallbackRefs.slice(0, 3) : [];

  if (records.length === 0 && visibleFallbackRefs.length === 0) {
    return null;
  }

  const readOnlyBlocked = executionMode === 'read-only';
  const hasResolvedRecords = records.length > 0;

  return (
    <div
      className="komsco-ai__answer-actions"
      data-komsco-answer-action-buttons
      aria-label="챗봇 답변 직접 조치 버튼"
    >
      <div className="komsco-ai__answer-actions-head">
        <strong>Action Plan</strong>
        <span>
          {!hasResolvedRecords
            ? '좌측 조치 목록에 연결된 계획 흐름입니다. record 연결 후 승인 버튼을 표시합니다.'
            : readOnlyBlocked
            ? '읽기 전용 모드라 조치 버튼은 숨기고 계획 상태만 보여줍니다.'
            : '승인 가능한 조치 흐름만 카드로 표시합니다.'}
        </span>
      </div>
      {aiopsActionError && <div className="komsco-ai__rail-error">{aiopsActionError}</div>}
      {aiopsActionNotice && <div className="komsco-ai__rail-success">{aiopsActionNotice}</div>}
      <div className="komsco-ai__answer-action-list">
        {records.map((record) => {
          const action = resolveAction(record, aiopsStatus, executionMode);
          const stage = getActionRecordStage(record);
          const actions =
            readOnlyBlocked
              ? []
              : action?.step === 'approve-plan'
              ? [action, { ...action, label: '거절', step: 'reject-plan' as const }]
              : action
                ? [action]
                : [];

          const phase = getRecordPhase(record);

          if (actions.length === 0 && !action) {
            const outcome = getExecutionOutcomeSummary(record, aiopsStatus);
            if (!outcome) {
              return null;
            }
            const outcomeIcon = outcome.tone === 'ok' ? '✓' : outcome.tone === 'warn' ? '!' : '✕';

            return (
              <div
                className={`komsco-ai__answer-action-card komsco-ai__answer-action-card--${outcome.tone}`}
                data-action-lifecycle-stage={getActionRecordStage(record)}
                key={getRecordName(record) || phase}
              >
                <div className="komsco-ai__answer-action-headline">
                  <ActionStageIcon stage="execution" />
                  <div className="komsco-ai__answer-action-main">
                    <span>{actionCardMetaLabel('execution')}</span>
                    <strong>{getRecordTargetLabel(record)}</strong>
                    <small>4단계 · 실행 완료</small>
                  </div>
                </div>
                <div className="komsco-ai__answer-action-outcome">
                  <div className="komsco-ai__answer-action-outcome-title">
                    <span className="komsco-ai__answer-action-outcome-icon">{outcomeIcon}</span>
                    {outcome.title}
                  </div>
                  <div className="komsco-ai__answer-action-outcome-detail">{outcome.detail}</div>
                </div>
              </div>
            );
          }

          return (
            <div
              className="komsco-ai__answer-action-card"
              data-action-lifecycle-stage={getActionRecordStage(record)}
              key={getRecordName(record) || phase}
            >
              <div className="komsco-ai__answer-action-headline">
                <ActionStageIcon stage={stage} />
                <div className="komsco-ai__answer-action-main">
                  <span>{actionCardMetaLabel(stage)}</span>
                  <strong>{getRecordTargetLabel(record)}</strong>
                  <small>{getActionRecordStageLabel(record, executionMode)}</small>
                </div>
              </div>
              <div className="komsco-ai__answer-action-proof">
                {getActionRecordProof(record, executionMode)}
              </div>
              <PlanSummaryBlock record={record} executionMode={executionMode} />
              <div className="komsco-ai__answer-action-controls">
                {actions.map((item) => {
                  const actionId = `${item.step}:${getRecordName(record)}`;
                  const busy = actionId === busyActionId;
                  return (
                    <Button
                      className="komsco-ai__action-button"
                      data-answer-action-step={item.step}
                      isDisabled={busy || Boolean(item.disabledReason)}
                      isLoading={busy}
                      key={item.step}
                      onClick={() => onAction(record, item)}
                      size="sm"
                      title={item.disabledReason}
                      variant={item.step === 'reject-plan' ? 'link' : 'secondary'}
                    >
                      <span className="komsco-ai__rail-action-icon">
                        <CoolTerminalIcon />
                      </span>
                      {busy ? '처리 중' : primaryActionLabel(item)}
                    </Button>
                  );
                })}
              </div>
              {!readOnlyBlocked && action?.disabledReason && (
                <div className="komsco-ai__answer-action-note">{action.disabledReason}</div>
              )}
            </div>
          );
        })}
        {visibleFallbackRefs.map((ref) => (
          <div
            className="komsco-ai__answer-action-card komsco-ai__answer-action-card--fallback"
            data-action-lifecycle-stage={ref.stage}
            key={ref.id}
          >
            <div className="komsco-ai__answer-action-headline">
              <ActionStageIcon stage={ref.stage} />
              <div className="komsco-ai__answer-action-main">
                <span>{actionCardMetaLabel(ref.stage)}</span>
                <strong>{ref.targetKey || '대상 확인 필요'}</strong>
                <small>{ref.label.replace(/^\d+단계\s*·\s*/, '')}</small>
              </div>
            </div>
            <div className="komsco-ai__answer-action-proof">
              {ref.toolName
                ? `${ref.toolName} 조치 흐름이 이 답변에 연결되어 있습니다. Gateway record가 연결되면 승인/실행 버튼을 표시합니다.`
                : '조치 흐름이 이 답변에 연결되어 있습니다. Gateway record가 연결되면 승인/실행 버튼을 표시합니다.'}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AssistantAnswerActions;
