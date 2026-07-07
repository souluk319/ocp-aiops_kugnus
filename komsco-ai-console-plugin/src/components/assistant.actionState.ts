import type { AiopsRuntimeStatus } from '../services/aiGateway';
import {
  findApprovalForPlan,
  findPlanByDigest,
  actionRecordCreatedAt,
  getActionRecordToolName,
  getApprovalDecision,
  getApprovalId,
  getApprovalPlanDigest,
  getPlanSummary,
  getPlanDigest,
  getRecordSpecMap,
  hasExecutionForApproval,
} from './assistant.actionRecords';
import type {
  AiopsExecutionMode,
  AiopsLifecycleStage,
  AiopsRecordAction,
  AiopsRecordView,
  UiLanguage,
  UiTone,
} from './assistant.types';

export const canUseActionExecution = (status: AiopsRuntimeStatus | null): boolean =>
  Boolean(
    status?.spec.capabilities.mutationsEnabled && status.spec.capabilities.actionExecutorConfigured,
  );

export const canUseUnrestrictedCommands = (status: AiopsRuntimeStatus | null): boolean =>
  Boolean(status?.spec.capabilities.unrestrictedCommandsEnabled);

export const getActionExecutionDisabledReason = (
  status: AiopsRuntimeStatus | null,
  language: UiLanguage = 'ko',
): string => {
  const isKo = language === 'ko';
  if (!status) {
    return isKo
      ? 'AIOps 실행 상태를 아직 불러오지 못했습니다.'
      : 'AIOps execution status has not loaded yet.';
  }

  const reasons = [];
  if (!status.spec.capabilities.mutationsEnabled) {
    reasons.push(isKo ? '변경 실행 기능이 비활성화되어 있습니다' : 'Mutation execution is disabled');
  }
  if (!status.spec.capabilities.actionExecutorConfigured) {
    reasons.push(
      isKo
        ? 'Action Executor 연결 정보가 설정되지 않았습니다'
        : 'Action Executor connection is not configured',
    );
  }

  return reasons.join('; ');
};

export const getUnrestrictedDisabledReason = (
  status: AiopsRuntimeStatus | null,
  language: UiLanguage = 'ko',
): string => {
  const isKo = language === 'ko';
  if (!status) {
    return isKo
      ? 'AIOps 실행 상태를 아직 불러오지 못했습니다.'
      : 'AIOps execution status has not loaded yet.';
  }

  return status.spec.capabilities.unrestrictedCommandsEnabled
    ? ''
    : isKo
      ? 'Gateway가 실행 무제한 capability를 허용하지 않았습니다'
      : 'Gateway does not allow unrestricted command capability';
};

export const executionModeAllowsActions = (mode: AiopsExecutionMode): boolean =>
  mode === 'execute' || mode === 'unrestricted';

export const getAiopsRecordAction = (
  record: AiopsRecordView,
  aiopsStatus: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
): AiopsRecordAction | null => {
  const spec = getRecordSpecMap(record);
  const kind = record.kind ?? '';
  const records = aiopsStatus?.spec.records;
  const modeDisabledReason = !canUseActionExecution(aiopsStatus)
    ? 'Gateway 실행 기능 미구성'
    : '';
  const withModeGate = (action: AiopsRecordAction): AiopsRecordAction =>
    modeDisabledReason
      ? { ...action, disabledReason: action.disabledReason ?? modeDisabledReason }
      : action;
  const unrestrictedDisabledReason =
    executionMode === 'unrestricted' && !canUseUnrestrictedCommands(aiopsStatus)
      ? 'Gateway가 실행 무제한 capability를 허용하지 않았습니다'
      : '';

  if (kind === 'ActionProposalRecord' || spec.candidateActionRequest) {
    return withModeGate({ label: '계획', step: 'create-plan' });
  }

  if (kind === 'SealedActionPlanRecord' || spec.sealedActionPlan) {
    const planDigest = getPlanDigest(record);
    if (!planDigest) {
      return withModeGate({
        disabledReason: 'plan digest 없음',
        label: executionMode === 'unrestricted' ? '실행' : '승인',
        step: executionMode === 'unrestricted' ? 'approve-execute-plan' : 'approve-plan',
      });
    }
    const planCreatedAt = actionRecordCreatedAt(record);
    const approvalRecords =
      planCreatedAt > 0
        ? (records?.approvalDecisions ?? []).filter(
            (approval) => actionRecordCreatedAt(approval) >= planCreatedAt,
          )
        : (records?.approvalDecisions ?? []);
    const approval = findApprovalForPlan(approvalRecords, planDigest);
    const approvalDecision = approval ? getApprovalDecision(approval) : undefined;
    const approvalStatus = String(approvalDecision?.status ?? '');

    if (approvalStatus === 'approved') {
      const approvalId = approval ? getApprovalId(approval) : '';
      if (hasExecutionForApproval(records?.executionRecords ?? [], approvalId)) {
        return null;
      }
      return withModeGate({
        label: '실행',
        step: 'execute-approval',
        disabledReason:
          executionMode === 'read-only'
            ? '읽기 전용 모드에서는 승인된 조치도 실행하지 않습니다'
            : undefined,
      });
    }
    if (approvalStatus === 'executed' || approvalStatus === 'rejected') {
      return null;
    }

    if (executionMode === 'unrestricted') {
      return withModeGate({
        label: '실행',
        step: 'approve-execute-plan',
        disabledReason: unrestrictedDisabledReason || undefined,
      });
    }

    const planSummary = getPlanSummary(record);
    const toolName = getActionRecordToolName(record);
    const approvalOnlyReview = toolName === 'namespace_cleanup_review';
    if ((planSummary?.risk === 'medium' || planSummary?.risk === 'high') && !approvalOnlyReview) {
      return withModeGate({
        label: '승인 요청',
        step: 'approve-plan',
        disabledReason: `위험도가 ${planSummary.riskLabel}이라 이 조치를 제안한 본인은 승인할 수 없습니다. 다른 담당자의 승인이 필요합니다.`,
      });
    }

    return withModeGate({
      label: approvalOnlyReview ? '승인 요청' : '승인',
      step: 'approve-plan',
    });
  }

  if (kind === 'ApprovalDecisionRecord' || spec.approvalDecision) {
    const decision = getApprovalDecision(record);
    const status = String(decision?.status ?? '');
    const approvalId = getApprovalId(record);
    const plan = findPlanByDigest(records?.sealedActionPlans ?? [], getApprovalPlanDigest(record));

    if (status !== 'approved') {
      return null;
    }
    if (hasExecutionForApproval(records?.executionRecords ?? [], approvalId)) {
      return null;
    }
    if (!plan) {
      return withModeGate({
        disabledReason: '연결된 plan 없음',
        label: '실행',
        step: 'execute-approval',
      });
    }

    return withModeGate({ label: '실행', step: 'execute-approval' });
  }

  return null;
};

export const getExecutionModeShortLabel = (
  mode: AiopsExecutionMode,
  language: UiLanguage = 'ko',
): string => {
  const isKo = language === 'ko';
  if (mode === 'unrestricted') {
    return isKo ? '무제한' : 'Unrestricted';
  }
  if (mode === 'execute') {
    return isKo ? '실행' : 'Execute';
  }
  return isKo ? '읽기' : 'Read only';
};

export const getActionLifecycleSteps = (
  status: AiopsRuntimeStatus | null,
  language: UiLanguage = 'ko',
) => {
  const records = status?.spec.records;
  const isKo = language === 'ko';

  return [
    {
      count: records?.actionProposals.length ?? 0,
      detail: isKo ? '조치 후보 접수' : 'Action candidates',
      key: 'proposal',
      label: isKo ? '제안' : 'Candidate',
    },
    {
      count: records?.sealedActionPlans.length ?? 0,
      detail: isKo ? '승인 필요 조치 계획' : 'Approval-required plans',
      key: 'plan',
      label: isKo ? '계획' : 'Plan',
    },
    {
      count: records?.approvalDecisions.length ?? 0,
      detail: isKo ? '승인 결정' : 'Approval decisions',
      key: 'approval',
      label: isKo ? '승인' : 'Approval',
    },
    {
      count: records?.executionRecords.length ?? 0,
      detail: isKo ? '실행 기록' : 'Execution records',
      key: 'execution',
      label: isKo ? '실행' : 'Execution',
    },
  ] as Array<{
    count: number;
    detail: string;
    key: AiopsLifecycleStage;
    label: string;
  }>;
};

export const getActionLifecycleSummary = (
  status: AiopsRuntimeStatus | null,
  executionMode: AiopsExecutionMode,
  language: UiLanguage = 'ko',
) => {
  const isKo = language === 'ko';
  if (!status) {
    return {
      label: isKo ? '실행 상태' : 'Execution status',
      text: isKo
        ? 'AIOps 실행 상태를 불러오는 중입니다. 상태가 확인될 때까지 실행이 비활성화됩니다.'
        : 'AIOps execution status is loading. Execution stays disabled until the status is available.',
      tone: 'neutral' as UiTone,
      value: isKo ? '대기 중' : 'Pending',
    };
  }

  const actionExecutorConfigured = Boolean(status?.spec.capabilities.actionExecutorConfigured);
  const mutationsEnabled = Boolean(status?.spec.capabilities.mutationsEnabled);
  const actionsAllowed = canUseActionExecution(status) && executionModeAllowsActions(executionMode);
  const blockers: string[] = [];
  if (!actionExecutorConfigured) {
    blockers.push(
      isKo ? 'Action Executor가 설정되지 않았습니다' : 'Action Executor is not configured',
    );
  }
  if (!mutationsEnabled) {
    blockers.push(
      isKo
        ? '변경 실행이 비활성화되어 있어 승인된 조치도 실제로 적용되지 않습니다'
        : 'Mutation execution is disabled, so approved actions are not applied',
    );
  }
  if (!executionModeAllowsActions(executionMode)) {
    blockers.push(
      isKo
        ? '현재 모드에서는 제안·승인·실행이 제한됩니다'
        : 'The current mode limits proposal, approval, and execution requests',
    );
  }

  if (blockers.length === 0 && actionsAllowed) {
    return {
      label: isKo ? '현재 상태' : 'Current state',
      text: isKo
        ? '서버 측 검증을 통과하면 계획·승인·실행 요청을 보낼 수 있습니다.'
        : 'Plan, approval, and execution requests are available after server-side validation.',
      tone: 'review' as UiTone,
      value: getExecutionModeShortLabel(executionMode, language),
    };
  }

  return {
    label: isKo ? '제한 사유' : 'Blocking reason',
    text: blockers.join('; '),
    tone: 'warn' as UiTone,
    value: isKo ? '설정 필요' : 'Setup required',
  };
};
