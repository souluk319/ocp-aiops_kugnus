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
  findPlanByDigest,
  getActionRecordProof,
  getActionRecordStage,
  getActionRecordStageLabel,
  getExecutionOutcomeSummary,
  getActionRecordToolLabel,
  getActionToolLabel,
  getApprovalPlanDigest,
  getPhaseTone,
  getPlanDigest,
  getPlanSummary,
  getRecordName,
  getRecordPhase,
  getRecordSpecMap,
  getRecordTargetLabel,
  getSealedActionPlan,
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

const highestActionStage = (records: AiopsRecordView[]): AiopsLifecycleStage => {
  return records.reduce<AiopsLifecycleStage>((highest, record) => {
    const stage = getActionRecordStage(record);
    return ACTION_STAGE_ORDER.indexOf(stage) > ACTION_STAGE_ORDER.indexOf(highest) ? stage : highest;
  }, 'proposal');
};

const actionFlowDescription = (
  records: AiopsRecordView[],
  hasResolvedRecords: boolean,
  readOnlyBlocked: boolean,
  language: UiLanguage,
): string => {
  const isKo = language === 'ko';
  if (!hasResolvedRecords) {
    return isKo
      ? '이 답변에 조치 흐름이 연결되어 있습니다. 기록이 연결되면 승인/실행 상태를 표시합니다.'
      : 'This answer is linked to the action flow. Approval and execution state appears after records are connected.';
  }
  if (readOnlyBlocked) {
    return isKo
      ? '읽기 전용 모드입니다. 승인·실행은 보내지 않고 제한 사유만 확인합니다.'
      : 'Read-only mode is active. Approval and execution are not sent.';
  }

  const stage = highestActionStage(records);
  if (stage === 'execution') {
    return isKo
      ? '실행 결과와 감사 기록을 표시합니다.'
      : 'Shows the execution result and audit record.';
  }
  if (stage === 'approval') {
    return isKo
      ? '승인이 완료됐습니다. 실행 버튼으로 결과를 기록합니다.'
      : 'Approval is complete. Use Execute to record the result.';
  }
  if (stage === 'plan') {
    return isKo
      ? '대상·영향·검증·롤백을 확인한 뒤 승인 또는 거절하세요.'
      : 'Review target, impact, verification, and rollback before approving or rejecting.';
  }
  return isKo
    ? '조치 후보가 접수됐습니다. Action Plan을 만들면 승인 단계로 진행합니다.'
    : 'The action candidate is ready. Create an Action Plan to continue.';
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

  const summary = getPlanSummary(record, language);
  if (!summary) {
    return null;
  }
  const isKo = language === 'ko';
  const toolLabel = summary.toolLabel;

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

const ActionRecordAuditDetail: React.FC<{
  language?: UiLanguage;
  record: AiopsRecordView;
}> = ({ language = 'ko', record }) => (
  <details className="komsco-ai__rail-command-detail">
    <summary>{language === 'ko' ? '감사 상세' : 'Audit detail'}</summary>
    <pre>{JSON.stringify(record, null, 2)}</pre>
  </details>
);

const ActionRefAuditDetail: React.FC<{
  actionRef: ConversationActionRef;
  language?: UiLanguage;
}> = ({ actionRef, language = 'ko' }) => (
  <details className="komsco-ai__rail-command-detail">
    <summary>{language === 'ko' ? '감사 상세' : 'Audit detail'}</summary>
    <pre>
      {JSON.stringify(
        {
          kind: actionRef.recordKind || 'ConversationActionRef',
          metadata: {
            createdAt: actionRef.createdAt,
            name: actionRef.recordName,
          },
          spec: {
            label: actionRef.label,
            messageAnchor: actionRef.messageAnchor,
            planDigest: actionRef.planDigest,
            stage: actionRef.stage,
            targetKey: actionRef.targetKey,
            toolName: actionRef.toolName,
          },
        },
        null,
        2,
      )}
    </pre>
  </details>
);

const stringList = (value: unknown): string[] =>
  Array.isArray(value)
    ? value
        .map((item) => String(item ?? '').trim())
        .filter(Boolean)
        .slice(0, 4)
    : [];

const textValue = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

const evidenceSummary = (refs: unknown, language: UiLanguage): string => {
  const items = Array.isArray(refs) ? refs : [];
  if (items.length === 0) {
    return language === 'ko' ? '추가 확인 필요' : 'Needs more evidence';
  }
  const labels = items
    .map((item) => {
      const map = asObjectMap(item);
      return textValue(map?.id) || textValue(map?.evidenceId) || textValue(map?.kind) || textValue(map?.source);
    })
    .filter(Boolean)
    .slice(0, 3);
  const countLabel =
    language === 'ko' ? `수집 ${items.length}건` : `${items.length} collected`;

  return labels.length > 0 ? `${countLabel} · ${labels.join(', ')}` : countLabel;
};

const targetSummary = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  const plan = asObjectMap(spec.sealedActionPlan);
  const decision = asObjectMap(spec.approvalDecision);
  const candidate = asObjectMap(spec.candidateActionRequest);
  const target =
    asObjectMap(plan?.target) ??
    asObjectMap(decision?.target) ??
    asObjectMap(candidate?.target) ??
    asObjectMap(spec.target);
  const kind = textValue(target?.kind);
  const label = getRecordTargetLabel(record);

  return kind ? `${kind} · ${label}` : label;
};

const planRecordForActionRecord = (
  record: AiopsRecordView,
  aiopsStatus: AiopsRuntimeStatus | null,
): AiopsRecordView | undefined => {
  if (getActionRecordStage(record) === 'plan') {
    return record;
  }
  const spec = getRecordSpecMap(record);
  const digest =
    getPlanDigest(record) ||
    getApprovalPlanDigest(record) ||
    (typeof spec.planDigest === 'string' ? spec.planDigest : '');

  return digest ? findPlanByDigest(aiopsStatus?.spec.records.sealedActionPlans ?? [], digest) : undefined;
};

const actionPlanRows = (
  record: AiopsRecordView,
  aiopsStatus: AiopsRuntimeStatus | null,
  language: UiLanguage,
): Array<{ key: string; label: string; value: string }> => {
  const isKo = language === 'ko';
  const planRecord = planRecordForActionRecord(record, aiopsStatus);
  const plan = planRecord ? getSealedActionPlan(planRecord) : undefined;
  const spec = getRecordSpecMap(record);
  const proposalPresentation = asObjectMap(spec.operatorPresentation);
  const presentation =
    asObjectMap(plan?.approvalPresentation) ?? proposalPresentation ?? {};
  const safety = asObjectMap(plan?.safety);
  const action = asObjectMap(plan?.action) ?? asObjectMap(asObjectMap(spec.candidateActionRequest)?.action);
  const impact = asObjectMap(presentation.impact);
  const planSummary = planRecord ? getPlanSummary(planRecord, language) : null;
  const verificationChecks = stringList(presentation.verificationChecks);
  const recommendationSteps = stringList(presentation.recommendationSteps);
  const prerequisiteChecks = stringList(presentation.prerequisiteChecks);
  const riskLabel =
    planSummary?.riskLabel || textValue(safety?.risk) || (isKo ? '확인 필요' : 'needs review');
  const rollbackDescription =
    textValue(safety?.rollbackDescription) ||
    (planSummary?.rollbackPossible
      ? isKo
        ? '자동 롤백 경로가 있습니다.'
        : 'Automatic rollback is available.'
      : isKo
        ? '자동 롤백 미지원. 실패 시 수동 복구 또는 새 Action Plan이 필요합니다.'
        : 'Automatic rollback is unavailable. Manual recovery or a new Action Plan is required.');
  const impactSummary =
    textValue(presentation.expectedImpact) ||
    [
      impact?.affectedWorkloads != null
        ? isKo
          ? `워크로드 ${impact.affectedWorkloads}개`
          : `${impact.affectedWorkloads} workload(s)`
        : '',
      impact?.affectedPods != null
        ? isKo
          ? `Pod ${impact.affectedPods}개`
          : `${impact.affectedPods} pod(s)`
        : '',
      impact?.availabilityRisk
        ? isKo
          ? `가용성 위험 ${String(impact.availabilityRisk) === 'unknown' ? '추가 확인 필요' : impact.availabilityRisk}`
          : `availability risk ${impact.availabilityRisk}`
        : '',
    ]
      .filter(Boolean)
      .join(' · ') ||
    (isKo ? '실행 전 영향 범위 확인 필요' : 'Impact scope must be reviewed before execution');
  const actionSummary =
    recommendationSteps.length > 0
      ? recommendationSteps.join(' · ')
      : `${getActionToolLabel(textValue(action?.toolName), language)}${
          action?.normalizedParameters
            ? isKo
              ? ' 실행'
              : ' execution'
            : ''
        }`;
  const approvalSummary = [
    isKo ? `위험도 ${riskLabel}` : `Risk ${riskLabel}`,
    prerequisiteChecks.length > 0
      ? isKo
        ? `사전 확인 ${prerequisiteChecks.length}건`
        : `${prerequisiteChecks.length} prerequisite check(s)`
      : '',
    isKo ? '승인 전 최신 대상/권한 재확인' : 'Recheck target freshness and authorization before approval',
  ]
    .filter(Boolean)
    .join(' · ');

  return [
    {
      key: 'target',
      label: isKo ? '대상' : 'Target',
      value: planRecord ? targetSummary(planRecord) : targetSummary(record),
    },
    {
      key: 'problem',
      label: isKo ? '문제' : 'Problem',
      value:
        textValue(presentation.problemSummary) ||
        textValue(spec.sourceType) ||
        (isKo ? '조회 결과 기반 조치 후보' : 'Evidence-backed action candidate'),
    },
    {
      key: 'evidence',
      label: isKo ? '확인 결과' : 'Evidence',
      value: evidenceSummary(presentation.evidenceRefs ?? spec.evidenceRefs, language),
    },
    { key: 'action', label: isKo ? '조치' : 'Action', value: actionSummary },
    { key: 'impact', label: isKo ? '예상 영향' : 'Expected impact', value: impactSummary },
    {
      key: 'verification',
      label: isKo ? '검증 방법' : 'Verification',
      value:
        verificationChecks.join(' · ') ||
        textValue(asObjectMap(plan?.metadata)?.verificationDeadline) ||
        (isKo ? '실행 후 상태와 이벤트를 다시 확인' : 'Recheck status and events after execution'),
    },
    {
      key: 'rollback',
      label: isKo ? '롤백/실패 시' : 'Rollback/failure',
      value: rollbackDescription,
    },
    {
      key: 'approval',
      label: isKo ? '승인 조건' : 'Approval condition',
      value: approvalSummary,
    },
  ].filter((row) => row.value.trim());
};

const ActionPlanDecisionBlock: React.FC<{
  aiopsStatus: AiopsRuntimeStatus | null;
  language?: UiLanguage;
  record: AiopsRecordView;
}> = ({ aiopsStatus, language = 'ko', record }) => {
  const rows = actionPlanRows(record, aiopsStatus, language);
  if (rows.length === 0) {
    return null;
  }

  return (
    <div
      className="komsco-ai__action-plan-decision"
      data-action-plan-decision-card
      aria-label={language === 'ko' ? 'Action Plan 승인 판단 항목' : 'Action Plan approval checklist'}
    >
      {rows.map((row) => (
        <div
          className="komsco-ai__action-plan-decision-row"
          data-action-plan-field={row.key}
          key={row.key}
        >
          <span>{row.label}</span>
          <p title={row.value}>{row.value}</p>
        </div>
      ))}
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
            <span className="komsco-ai__rail-command-action-label">
              {getActionRecordToolLabel(record, language)}
            </span>
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
        <ActionPlanDecisionBlock aiopsStatus={aiopsStatus} record={record} language={language} />
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
                  {busy ? (language === 'ko' ? '처리 중' : 'Processing') : primaryActionLabel(item, language)}
                </Button>
              );
            })}
            {action?.disabledReason && (
              <span className="komsco-ai__rail-action-note">{action.disabledReason}</span>
            )}
          </div>
        )}
        <ActionRecordAuditDetail language={language} record={record} />
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
  const description = actionFlowDescription(
    records,
    hasResolvedRecords,
    readOnlyBlocked,
    language,
  );

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
        <span>{description}</span>
      </div>
      {aiopsActionError && <div className="komsco-ai__rail-error">{aiopsActionError}</div>}
      {aiopsActionNotice && !hasResolvedRecords && (
        <div className="komsco-ai__rail-success">{aiopsActionNotice}</div>
      )}
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
          const stageLabel = getActionRecordStageLabel(record, executionMode, language);
          const targetLabel = getRecordTargetLabel(record);
          const targetRoleLabel = actionCardTargetDisplayLabel(stage, record, language);
          const toolLabel = getActionRecordToolLabel(record, language);

          if (actions.length === 0 && !action) {
            const outcome = getExecutionOutcomeSummary(record, aiopsStatus);
            if (!outcome) {
              return null;
            }
            const outcomeIcon = outcome.tone === 'ok' ? '✓' : outcome.tone === 'warn' ? '!' : '✕';
            const outcomeStageLabel = language === 'ko' ? '4단계 · 실행 완료' : 'Step 4 · Executed';
            const outcomeTargetRoleLabel = actionCardTargetDisplayLabel('execution', record, language);

            return (
              <div
                className={`komsco-ai__answer-action-card komsco-ai__answer-action-card--${outcome.tone}`}
                data-action-lifecycle-stage="execution"
                key={getRecordName(record) || phase}
              >
                <div className="komsco-ai__answer-action-headline">
                  <ActionStageIcon stage="execution" />
                  <div className="komsco-ai__answer-action-main">
                    <span>{actionCardMetaLabel('execution', language)}</span>
                    <strong title={targetLabel}>{toolLabel}</strong>
                    <small title={outcomeTargetRoleLabel}>{`${outcomeStageLabel} · ${targetLabel}`}</small>
                  </div>
                </div>
                <div className="komsco-ai__answer-action-outcome">
                  <div className="komsco-ai__answer-action-outcome-title">
                    <span className="komsco-ai__answer-action-outcome-icon">{outcomeIcon}</span>
                    {outcome.title}
                  </div>
                  <div className="komsco-ai__answer-action-outcome-detail">{outcome.detail}</div>
                </div>
                <ActionPlanDecisionBlock aiopsStatus={aiopsStatus} record={record} language={language} />
                <ActionRecordAuditDetail language={language} record={record} />
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
                  <strong title={targetLabel}>{toolLabel}</strong>
                  <small title={targetRoleLabel}>{`${stageLabel} · ${targetLabel}`}</small>
                </div>
              </div>
              <div className="komsco-ai__answer-action-proof">
                {getActionRecordProof(record, executionMode, language)}
              </div>
              <PlanSummaryBlock record={record} executionMode={executionMode} language={language} />
              <ActionPlanDecisionBlock aiopsStatus={aiopsStatus} record={record} language={language} />
              {!readOnlyBlocked && actions.length > 0 && (
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
                        {busy
                          ? language === 'ko'
                            ? '처리 중'
                            : 'Processing'
                          : primaryActionLabel(item, language)}
                      </Button>
                    );
                  })}
                </div>
              )}
              {(readOnlyBlocked || action?.disabledReason) && (
                <div className="komsco-ai__answer-action-note">
                  {action?.disabledReason ??
                    (language === 'ko'
                      ? '읽기 전용 모드에서는 승인·실행 요청을 보내지 않습니다. 실행하려면 실행 가능 또는 실행 무제한을 선택하세요.'
                      : 'Read-only mode does not send approval or execution requests. Select Execute or Unrestricted to run actions.')}
                </div>
              )}
              <ActionRecordAuditDetail language={language} record={record} />
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
                  ? `${getActionToolLabel(ref.toolName, language)} 조치 흐름이 이 답변에 연결되어 있습니다. Gateway 기록이 연결되면 승인/실행 버튼을 표시합니다.`
                  : `${getActionToolLabel(ref.toolName, language)} action flow is linked to this answer. Approval and execution buttons appear after Gateway records are connected.`
                : language === 'ko'
                  ? '조치 흐름이 이 답변에 연결되어 있습니다. Gateway 기록이 연결되면 승인/실행 버튼을 표시합니다.'
                  : 'An action flow is linked to this answer. Approval and execution buttons appear after Gateway records are connected.'}
            </div>
            <ActionRefAuditDetail actionRef={ref} language={language} />
          </div>
        ))}
      </div>
    </div>
  );
};

export default AssistantAnswerActions;
