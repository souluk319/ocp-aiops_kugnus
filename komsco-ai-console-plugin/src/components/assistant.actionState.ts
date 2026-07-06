import type { AiopsRuntimeStatus } from '../services/aiGateway';
import {
  findPlanByDigest,
  getApprovalDecision,
  getApprovalId,
  getApprovalPlanDigest,
  getPlanDigest,
  getRecordSpecMap,
  hasApprovalForPlan,
  hasExecutionForApproval,
} from './assistant.actionRecords';
import type {
  AiopsExecutionMode,
  AiopsLifecycleStage,
  AiopsRecordAction,
  AiopsRecordView,
  UiTone,
} from './assistant.types';

export const canUseActionExecution = (status: AiopsRuntimeStatus | null): boolean =>
  Boolean(
    status?.spec.capabilities.mutationsEnabled && status.spec.capabilities.actionExecutorConfigured,
  );

export const canUseUnrestrictedCommands = (status: AiopsRuntimeStatus | null): boolean =>
  Boolean(status?.spec.capabilities.unrestrictedCommandsEnabled);

export const getActionExecutionDisabledReason = (status: AiopsRuntimeStatus | null): string => {
  if (!status) {
    return 'AIOps 실행 상태를 아직 불러오지 못했습니다.';
  }

  const reasons = [];
  if (!status.spec.capabilities.mutationsEnabled) {
    reasons.push('변경 실행 기능이 비활성화되어 있습니다');
  }
  if (!status.spec.capabilities.actionExecutorConfigured) {
    reasons.push('Action Executor 연결 정보가 설정되지 않았습니다');
  }

  return reasons.join('; ');
};

export const getUnrestrictedDisabledReason = (status: AiopsRuntimeStatus | null): string => {
  if (!status) {
    return 'AIOps 실행 상태를 아직 불러오지 못했습니다.';
  }

  return status.spec.capabilities.unrestrictedCommandsEnabled
    ? ''
    : 'Gateway가 실행 무제한 capability를 허용하지 않았습니다';
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
    if (hasApprovalForPlan(records?.approvalDecisions ?? [], planDigest)) {
      return null;
    }

    if (executionMode === 'unrestricted') {
      return withModeGate({ label: '실행', step: 'approve-execute-plan' });
    }

    return withModeGate({ label: '승인', step: 'approve-plan' });
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

export const getExecutionModeShortLabel = (mode: AiopsExecutionMode): string => {
  if (mode === 'unrestricted') {
    return '무제한';
  }
  if (mode === 'execute') {
    return '실행';
  }
  return '읽기';
};

export const getActionLifecycleSteps = (status: AiopsRuntimeStatus | null) => {
  const records = status?.spec.records;

  return [
    {
      count: records?.actionProposals.length ?? 0,
      detail: '조치 후보 접수',
      key: 'proposal',
      label: '제안',
    },
    {
      count: records?.sealedActionPlans.length ?? 0,
      detail: '승인 필요 조치 계획',
      key: 'plan',
      label: '계획',
    },
    {
      count: records?.approvalDecisions.length ?? 0,
      detail: '승인 결정',
      key: 'approval',
      label: '승인',
    },
    {
      count: records?.executionRecords.length ?? 0,
      detail: '실행 기록',
      key: 'execution',
      label: '실행',
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
) => {
  if (!status) {
    return {
      label: '실행 상태',
      text: 'AIOps 실행 상태를 불러오는 중입니다. 상태가 확인될 때까지 실행이 비활성화됩니다.',
      tone: 'neutral' as UiTone,
      value: '대기 중',
    };
  }

  const actionExecutorConfigured = Boolean(status?.spec.capabilities.actionExecutorConfigured);
  const mutationsEnabled = Boolean(status?.spec.capabilities.mutationsEnabled);
  const actionsAllowed = canUseActionExecution(status) && executionModeAllowsActions(executionMode);
  const blockers: string[] = [];
  if (!actionExecutorConfigured) {
    blockers.push('Action Executor가 설정되지 않았습니다');
  }
  if (!mutationsEnabled) {
    blockers.push('변경 실행이 비활성화되어 있어 승인된 조치도 실제로 적용되지 않습니다');
  }
  if (!executionModeAllowsActions(executionMode)) {
    blockers.push('현재 모드에서는 제안·승인·실행이 제한됩니다');
  }

  if (blockers.length === 0 && actionsAllowed) {
    return {
      label: '현재 상태',
      text: '서버 측 검증을 통과하면 계획·승인·실행 요청을 보낼 수 있습니다.',
      tone: 'review' as UiTone,
      value: getExecutionModeShortLabel(executionMode),
    };
  }

  return {
    label: '제한 사유',
    text: blockers.join('; '),
    tone: 'warn' as UiTone,
    value: '설정 필요',
  };
};
