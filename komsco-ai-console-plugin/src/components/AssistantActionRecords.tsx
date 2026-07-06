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
  asObjectMap,
  getActionRecordProof,
  getActionRecordStage,
  getActionRecordStageLabel,
  getExecutionOutcomeSummary,
  getPhaseTone,
  getPlanSummary,
  getRecordName,
  getRecordPhase,
  getRecordSpecMap,
  getRecordTargetLabel,
  getActionRecordToolName,
  phaseLabel,
} from './assistant.actionRecords';
import type {
  AiopsExecutionMode,
  AiopsLifecycleStage,
  AiopsRecordAction,
  AiopsRecordView,
  ConversationActionRef,
  UiLanguage,
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

const primaryActionLabel = (action: AiopsRecordAction, language: UiLanguage = 'ko'): string => {
  const isKo = language === 'ko';
  if (action.step === 'create-plan') {
    return isKo ? 'Action Plan 생성' : 'Create Action Plan';
  }
  if (action.step === 'approve-plan') {
    return isKo ? '승인 요청' : 'Request approval';
  }
  if (action.step === 'approve-execute-plan') {
    return isKo ? '승인 후 실행' : 'Approve and execute';
  }
  if (action.step === 'execute-approval') {
    return isKo ? '실행' : 'Execute';
  }
  return action.label;
};

const actionCardMetaLabel = (stage: AiopsLifecycleStage, language: UiLanguage = 'ko'): string => {
  const isKo = language === 'ko';
  if (stage === 'proposal') {
    return isKo ? '조치 후보' : 'Action candidate';
  }
  if (stage === 'plan') {
    return isKo ? '승인 가능한 계획' : 'Approval-ready plan';
  }
  if (stage === 'approval') {
    return isKo ? '승인 결정' : 'Approval decision';
  }
  return isKo ? '실행 결과' : 'Execution result';
};

const getActionCardTargetKind = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  const candidate = asObjectMap(spec.candidate);
  const candidateActionRequest = asObjectMap(spec.candidateActionRequest);
  const sealedActionPlan = asObjectMap(spec.sealedActionPlan);
  const approvalDecision = asObjectMap(spec.approvalDecision);
  const target =
    asObjectMap(spec.target) ??
    asObjectMap(candidate?.targetNode) ??
    asObjectMap(candidateActionRequest?.target) ??
    asObjectMap(sealedActionPlan?.target) ??
    asObjectMap(approvalDecision?.target);

  return typeof target?.kind === 'string' ? target.kind : '';
};

const actionCardTargetDisplayLabel = (
  stage: AiopsLifecycleStage,
  record?: AiopsRecordView,
  language: UiLanguage = 'ko',
): string => {
  const isKo = language === 'ko';
  const targetKind = record ? getActionCardTargetKind(record) : '';
  if (targetKind === 'Namespace') {
    if (stage === 'proposal') {
      return isKo ? '검토 네임스페이스' : 'Namespace to review';
    }
    if (stage === 'plan') {
      return isKo ? '대상 네임스페이스' : 'Target namespace';
    }
    if (stage === 'approval') {
      return isKo ? '승인 네임스페이스' : 'Approved namespace';
    }
    return isKo ? '실행 네임스페이스' : 'Executed namespace';
  }

  if (stage === 'proposal') {
    return isKo ? '검토 대상' : 'Target to review';
  }
  if (stage === 'plan') {
    return isKo ? '대상 워크로드' : 'Target workload';
  }
  if (stage === 'approval') {
    return isKo ? '승인 대상' : 'Approved target';
  }
  return isKo ? '실행 대상' : 'Executed target';
};

export const PlanSummaryBlock: React.FC<{
  executionMode?: AiopsExecutionMode;
  language?: UiLanguage;
  record: AiopsRecordView;
}> = ({ executionMode, language = 'ko', record }) => {
  if (getActionRecordStage(record) !== 'plan') {
    return null;
  }

  const summary = getPlanSummary(record);
  if (!summary) {
    return null;
  }
  const isKo = language === 'ko';
  const toolLabel = isKo
    ? summary.toolLabel
    : getActionRecordToolName(record)
        .replace(/_/g, ' ')
        .replace(/\b\w/g, (letter) => letter.toUpperCase());

  return (
    <div className="komsco-ai__plan-summary">
      <span className="komsco-ai__plan-summary-policy">{toolLabel}</span>
      <StatusTag
        label={isKo ? `위험도 ${summary.riskLabel}` : `Risk ${summary.risk || 'unknown'}`}
        tone={summary.riskTone}
      />
      <span className="komsco-ai__plan-summary-rollback">
        {summary.rollbackPossible
          ? isKo
            ? '자동 롤백 가능'
            : 'Auto rollback available'
          : isKo
            ? '자동 롤백 미지원'
            : 'Auto rollback unavailable'}
      </span>
      {executionMode !== 'unrestricted' &&
        (summary.risk === 'medium' || summary.risk === 'high') && (
          <p className="komsco-ai__plan-summary-note">
            {isKo
              ? `위험도가 ${summary.riskLabel}이라 이 조치를 제안한 본인은 승인할 수 없습니다. 다른 담당자의 승인이 필요합니다.`
              : 'Because this is a medium or high risk action, the requester cannot approve it. Another operator must approve it.'}
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
  language?: UiLanguage;
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
  language = 'ko',
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
        ? [
            action,
            { ...action, label: language === 'ko' ? '거절' : 'Reject', step: 'reject-plan' as const },
          ]
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
            <span>{getActionRecordStageLabel(record, executionMode, language)}</span>
            <code>{getRecordName(record) || record.kind || 'record'}</code>
          </div>
          {phase !== 'sealed' && (
            <StatusTag label={phaseLabel(phase, language)} tone={getPhaseTone(phase)} />
          )}
        </div>
        <p>{getRecordTargetLabel(record)}</p>
        <p className="komsco-ai__rail-action-proof">
          {getActionRecordProof(record, executionMode, language)}
        </p>
        <PlanSummaryBlock record={record} executionMode={executionMode} language={language} />
        {actions.length > 0 && (
          <div className="komsco-ai__rail-action-row">
            {actions.map((item) => {
              const actionId = `${item.step}:${getRecordName(record)}`;
              const busy = actionId === busyActionId;
              return (
                <Button
                  className="komsco-ai__action-button"
                  data-answer-action-step={item.step}
                  isDisabled={busy}
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
                  {busy ? (language === 'ko' ? '처리 중' : 'Processing') : primaryActionLabel(item, language)}
                </Button>
              );
            })}
            {action?.disabledReason && (
              <span className="komsco-ai__rail-action-note">{action.disabledReason}</span>
            )}
          </div>
        )}
        <details className="komsco-ai__rail-command-detail">
          <summary>{language === 'ko' ? '상세보기 (JSON)' : 'Details (JSON)'}</summary>
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
          <summary>
            {language === 'ko'
              ? `나머지 ${hiddenRecords.length}건 펼쳐보기`
              : `Show ${hiddenRecords.length} more`}
          </summary>
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
  language?: UiLanguage;
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
  language = 'ko',
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
      aria-label={
        language === 'ko' ? '챗봇 답변 직접 조치 버튼' : 'Copilot answer direct action buttons'
      }
    >
      <div className="komsco-ai__answer-actions-head">
        <strong>Action Plan</strong>
        <span>
          {!hasResolvedRecords
            ? language === 'ko'
              ? '좌측 조치 목록에 연결된 계획 흐름입니다. record 연결 후 승인 버튼을 표시합니다.'
              : 'This answer is linked to the action flow. Approval buttons appear after records are connected.'
            : readOnlyBlocked
              ? language === 'ko'
                ? '읽기 전용 모드입니다. 버튼은 유지하고 클릭 시 실행 제한 사유를 표시합니다.'
                : 'Read-only mode is active. Buttons stay visible and show the execution limit reason.'
              : language === 'ko'
                ? '승인 전 검증과 승인 상태를 표시합니다.'
                : 'Shows validation and approval state before execution.'}
        </span>
      </div>
      {aiopsActionError && <div className="komsco-ai__rail-error">{aiopsActionError}</div>}
      {aiopsActionNotice && <div className="komsco-ai__rail-success">{aiopsActionNotice}</div>}
      <div className="komsco-ai__answer-action-list">
        {records.map((record) => {
          const action = resolveAction(record, aiopsStatus, executionMode);
          const stage = getActionRecordStage(record);
          const actions =
            action?.step === 'approve-plan'
              ? [
                  action,
                  {
                    ...action,
                    label: language === 'ko' ? '거절' : 'Reject',
                    step: 'reject-plan' as const,
                  },
                ]
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
                    <span>{actionCardMetaLabel('execution', language)}</span>
                    <strong title={getRecordTargetLabel(record)}>
                      {actionCardTargetDisplayLabel('execution', record, language)}
                    </strong>
                    <small>{language === 'ko' ? '4단계 · 실행 완료' : 'Step 4 · Executed'}</small>
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
                  <span>{actionCardMetaLabel(stage, language)}</span>
                  <strong title={getRecordTargetLabel(record)}>
                    {actionCardTargetDisplayLabel(stage, record, language)}
                  </strong>
                  <small>{getActionRecordStageLabel(record, executionMode, language)}</small>
                </div>
              </div>
              <div className="komsco-ai__answer-action-proof">
                {getActionRecordProof(record, executionMode, language)}
              </div>
              <PlanSummaryBlock record={record} executionMode={executionMode} language={language} />
              <div className="komsco-ai__answer-action-controls">
                {actions.map((item) => {
                  const actionId = `${item.step}:${getRecordName(record)}`;
                  const busy = actionId === busyActionId;
                  return (
                    <Button
                      className="komsco-ai__action-button"
                      data-answer-action-step={item.step}
                      isDisabled={busy}
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
                      {busy
                        ? language === 'ko'
                          ? '처리 중'
                          : 'Processing'
                        : primaryActionLabel(item, language)}
                    </Button>
                  );
                })}
              </div>
              {(readOnlyBlocked || action?.disabledReason) && (
                <div className="komsco-ai__answer-action-note">
                  {action?.disabledReason ??
                    (language === 'ko'
                      ? '읽기 전용 모드에서는 승인·실행 요청을 보내지 않습니다. 실행하려면 실행 가능 또는 실행 무제한을 선택하세요.'
                      : 'Read-only mode does not send approval or execution requests. Select Execute or Unrestricted to run actions.')}
                </div>
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
                <span>{actionCardMetaLabel(ref.stage, language)}</span>
                <strong title={ref.targetKey || undefined}>
                  {actionCardTargetDisplayLabel(ref.stage, undefined, language)}
                </strong>
                <small>
                  {language === 'ko'
                    ? ref.label.replace(/^\d+단계\s*·\s*/, '')
                    : getActionRecordStageLabel(
                        { kind: ref.recordKind, metadata: { name: ref.recordName }, spec: {} },
                        executionMode,
                        language,
                      ).replace(/^Step\s+\d+\s*·\s*/, '')}
                </small>
              </div>
            </div>
            <div className="komsco-ai__answer-action-proof">
              {ref.toolName
                ? language === 'ko'
                  ? `${ref.toolName} 조치 흐름이 이 답변에 연결되어 있습니다. Gateway record가 연결되면 승인/실행 버튼을 표시합니다.`
                  : `${ref.toolName} action flow is linked to this answer. Approval and execution buttons appear after Gateway records are connected.`
                : language === 'ko'
                  ? '조치 흐름이 이 답변에 연결되어 있습니다. Gateway record가 연결되면 승인/실행 버튼을 표시합니다.'
                  : 'An action flow is linked to this answer. Approval and execution buttons appear after Gateway records are connected.'}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default AssistantAnswerActions;
