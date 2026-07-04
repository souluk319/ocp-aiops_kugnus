import * as React from 'react';
import { Button } from '@patternfly/react-core';

import { CoolTerminalIcon } from './coolicons';
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
  onAction,
  records,
  resolveAction,
}) => {
  if (records.length === 0) {
    return null;
  }

  return (
    <div
      className="komsco-ai__answer-actions"
      data-komsco-answer-action-buttons
      aria-label="챗봇 답변 직접 조치 버튼"
    >
      <div className="komsco-ai__answer-actions-head">
        <strong>바로 해결</strong>
        <span>검증된 AIOps 기록에서 다음 버튼만 표시합니다.</span>
      </div>
      {aiopsActionError && <div className="komsco-ai__rail-error">{aiopsActionError}</div>}
      {aiopsActionNotice && <div className="komsco-ai__rail-success">{aiopsActionNotice}</div>}
      <div className="komsco-ai__answer-action-list">
        {records.map((record) => {
          const action = resolveAction(record, aiopsStatus, executionMode);
          const actions =
            action?.step === 'approve-plan'
              ? [action, { ...action, label: '거절', step: 'reject-plan' as const }]
              : action
                ? [action]
                : [];

          const phase = getRecordPhase(record);

          if (actions.length === 0) {
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
                <div className="komsco-ai__answer-action-main">
                  <ActionStageDots stage="execution" />
                  <span>4단계 · 실행 완료</span>
                  <strong>{getRecordTargetLabel(record)}</strong>
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
              <div className="komsco-ai__answer-action-main">
                <ActionStageDots stage={getActionRecordStage(record)} />
                <span>{getActionRecordStageLabel(record, executionMode)}</span>
                <strong>{getRecordTargetLabel(record)}</strong>
                <small>{getActionRecordProof(record, executionMode)}</small>
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
                      {busy ? '처리 중' : item.label}
                    </Button>
                  );
                })}
              </div>
              {action?.disabledReason && (
                <div className="komsco-ai__answer-action-note">{action.disabledReason}</div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AssistantAnswerActions;
