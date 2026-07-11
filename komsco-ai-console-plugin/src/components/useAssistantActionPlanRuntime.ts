import * as React from 'react';
import { highestLifecycleRecordForPlanDigest } from './assistant.actionDisplay';
import {
  findPlanByDigest,
  getApprovalId,
  getApprovalPlanDigest,
  getPlanDigest,
  getRecordName,
  getRecordSpecMap,
  isReviewOnlyActionRecord,
} from './assistant.actionRecords';
import {
  canUseUnrestrictedCommands,
  executionModeAllowsActions,
} from './assistant.actionState';
import { CLUSTER_SUMMARY_REFRESH_MS } from './assistant.constants';
import type {
  AiopsExecutionMode,
  AiopsRecordAction,
  AiopsRecordView,
} from './assistant.types';
import {
  type AiopsActionCandidate,
  type AiopsRuntimeStatus,
  approveActionPlan,
  createActionCandidatePlan,
  createActionPlan,
  executeApprovedAction,
  fetchActionCandidates,
  rejectActionPlan,
} from '../services/aiGateway';

type AiopsRuntimeRecordUpdates = Partial<AiopsRuntimeStatus['spec']['records']>;

export type ActionCandidateFeedback = {
  candidateId: string;
  message: string;
  tone: 'error' | 'pending' | 'success';
};

type UseAssistantActionPlanRuntimeOptions = {
  aiopsStatus: AiopsRuntimeStatus | null;
  executionMode: AiopsExecutionMode;
  getLatestAssistantMessageAnchor: () => string | undefined;
  onActionPlanCreated: (
    source: AiopsRecordView,
    plan: AiopsRecordView,
    messageAnchor?: string,
  ) => void;
  onActionRecordCreated: (record: AiopsRecordView, messageAnchor?: string) => void;
  onCandidatePlanCreated: (
    candidate: AiopsActionCandidate,
    plan: AiopsRecordView | undefined,
    messageAnchor?: string,
  ) => void;
  open: boolean;
  refreshAiopsRuntimeStatus: () => Promise<AiopsRuntimeStatus | null>;
  upsertAiopsRuntimeRecords: (updates: AiopsRuntimeRecordUpdates) => void;
};

const aiopsActionErrorMessage = (error: unknown): string => {
  const raw =
    error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : JSON.stringify(error ?? '');
  const text = raw.trim();
  const lower = text.toLowerCase();

  if (/digest|expectedplandigest|mismatch|does not match/.test(lower)) {
    return '조치 계획 검증값이 현재 기록과 맞지 않습니다. 최신 상태로 다시 조회한 뒤 계획을 다시 만들어 주세요.';
  }
  if (/expired|ttl|stale/.test(lower)) {
    return '조치 계획 또는 승인 토큰이 만료되었습니다. 같은 대상에 대해 새 계획을 만들어야 합니다.';
  }
  if (/forbidden|403|rbac|access|permission|ssar|denied/.test(lower)) {
    return '현재 사용자 권한으로는 이 조치를 실행할 수 없습니다. 대상 리소스 권한과 승인자를 확인해 주세요.';
  }
  if (/not found|404|target.*missing|target.*unavailable/.test(lower)) {
    return '대상 리소스를 찾지 못했습니다. 네임스페이스와 리소스 이름이 최신인지 확인해 주세요.';
  }
  if (/disabled|capability|executor|mutation.*disabled|mutations.*disabled/.test(lower)) {
    return '게이트웨이 실행 기능이 꺼져 있어 실제 변경을 보낼 수 없습니다. 실행 기능과 Action Executor 설정을 확인해 주세요.';
  }
  if (/already.*used|이미.*사용|이미.*실행|이미.*검토 기록/.test(lower)) {
    return '이 승인은 이미 실행 또는 검토 기록에 사용됐습니다. 실행 기록을 확인해 주세요.';
  }
  if (/not approved|승인 완료 상태가 아닌/.test(lower)) {
    return '승인 완료 상태가 아닌 기록입니다. 새 Action Plan을 다시 생성해 주세요.';
  }
  if (/separation of duties|same.*approver|requester and approver|요청자와 승인자/.test(lower)) {
    return '승인 정책상 요청자와 승인자가 달라야 합니다. 다른 운영자 계정으로 승인하거나 새 승인 절차를 시작해 주세요.';
  }
  if (/conflict|409/.test(lower)) {
    return '현재 화면의 계획/승인 상태와 서버 기록이 맞지 않습니다. 새로고침 후 같은 대상의 Action Plan을 다시 확인해 주세요.';
  }
  if (/failed|error|exception|timeout/.test(lower)) {
    return '조치 요청 처리 중 오류가 발생했습니다. 잠시 후 다시 시도하거나 실행 기록에서 원문 오류를 확인해 주세요.';
  }

  return text || 'AIOps 조치 요청을 완료하지 못했습니다.';
};

const approvalRecordWithExecutedStatus = (
  approval: AiopsRecordView,
  execution: AiopsRecordView,
): AiopsRecordView => {
  const spec = getRecordSpecMap(approval);
  const decision =
    spec.approvalDecision && typeof spec.approvalDecision === 'object'
      ? (spec.approvalDecision as Record<string, unknown>)
      : undefined;

  if (!decision) {
    return approval;
  }

  return {
    ...approval,
    spec: {
      ...spec,
      approvalDecision: {
        ...decision,
        executedAt: execution.metadata?.createdAt ?? new Date().toISOString(),
        status: 'executed',
      },
    },
  };
};

export const useAssistantActionPlanRuntime = ({
  aiopsStatus,
  executionMode,
  getLatestAssistantMessageAnchor,
  onActionPlanCreated,
  onActionRecordCreated,
  onCandidatePlanCreated,
  open,
  refreshAiopsRuntimeStatus,
  upsertAiopsRuntimeRecords,
}: UseAssistantActionPlanRuntimeOptions) => {
  const [actionCandidates, setActionCandidates] = React.useState<AiopsActionCandidate[]>([]);
  const actionCandidatesRef = React.useRef<AiopsActionCandidate[]>([]);
  const [busyActionCandidateId, setBusyActionCandidateId] = React.useState('');
  const busyActionCandidateIdRef = React.useRef('');
  const [actionCandidateFeedback, setActionCandidateFeedback] =
    React.useState<ActionCandidateFeedback | null>(null);
  const [aiopsActionBusyId, setAiopsActionBusyId] = React.useState('');
  const aiopsActionBusyIdRef = React.useRef('');
  const [aiopsActionError, setAiopsActionError] = React.useState('');
  const [aiopsActionNotice, setAiopsActionNotice] = React.useState('');

  React.useEffect(() => {
    actionCandidatesRef.current = actionCandidates;
  }, [actionCandidates]);

  const refreshAiopsActionCandidates = React.useCallback(async () => {
    try {
      const summary = await fetchActionCandidates();
      const nextCandidates = summary.spec?.candidates ?? [];
      actionCandidatesRef.current = nextCandidates;
      setActionCandidates(nextCandidates);
      return nextCandidates;
    } catch {
      return actionCandidatesRef.current;
    }
  }, []);

  React.useEffect(() => {
    if (!open) {
      return undefined;
    }

    let disposed = false;
    const loadActionCandidates = async () => {
      if (!disposed) {
        await refreshAiopsActionCandidates();
      }
    };

    void loadActionCandidates();
    const timer = window.setInterval(() => {
      void loadActionCandidates();
    }, CLUSTER_SUMMARY_REFRESH_MS);

    return () => {
      disposed = true;
      window.clearInterval(timer);
    };
  }, [open, refreshAiopsActionCandidates]);

  const clearActionError = React.useCallback(() => {
    setAiopsActionError('');
  }, []);

  const clearActionCandidateFeedback = React.useCallback(() => {
    setActionCandidateFeedback(null);
  }, []);

  const resetActionActivity = React.useCallback(() => {
    setAiopsActionError('');
    setAiopsActionNotice('');
    setActionCandidateFeedback(null);
  }, []);

  const handleAiopsAction = React.useCallback(
    async (record: AiopsRecordView, action: AiopsRecordAction) => {
      if (action.disabledReason) {
        setAiopsActionError(action.disabledReason);
        setAiopsActionNotice('');
        return;
      }
      if (!executionModeAllowsActions(executionMode)) {
        setAiopsActionError(
          '읽기 전용 모드에서는 승인·실행을 만들지 않습니다. 실행하려면 실행 가능 또는 실행 무제한을 선택하세요.',
        );
        return;
      }

      const actionId = `${action.step}:${getRecordName(record)}`;
      if (aiopsActionBusyIdRef.current) {
        return;
      }
      aiopsActionBusyIdRef.current = actionId;
      setAiopsActionBusyId(actionId);
      setAiopsActionError('');
      setAiopsActionNotice('');
      const actionMessageAnchor = getLatestAssistantMessageAnchor();

      try {
        if (action.step === 'create-plan') {
          const proposalId = getRecordName(record);
          if (!proposalId) {
            throw new Error('Action proposal id is missing.');
          }
          const plan = await createActionPlan(proposalId);
          upsertAiopsRuntimeRecords({ sealedActionPlans: [plan] });
          setAiopsActionNotice('Action plan을 생성했습니다.');
          onActionPlanCreated(record, plan, actionMessageAnchor);
        }

        if (action.step === 'approve-plan') {
          const planId = getRecordName(record);
          const planDigest = getPlanDigest(record);
          if (!planId || !planDigest) {
            throw new Error('Action plan id 또는 digest가 없습니다.');
          }
          const approval = await approveActionPlan(planId, planDigest);
          upsertAiopsRuntimeRecords({ approvalDecisions: [approval] });
          setAiopsActionNotice('Action plan을 승인했습니다.');
          onActionRecordCreated(approval, actionMessageAnchor);
        }

        if (action.step === 'approve-execute-plan') {
          if (executionMode !== 'unrestricted') {
            setAiopsActionError(
              '승인과 실행을 한 번에 처리하는 동작은 실행 무제한 모드에서만 가능합니다.',
            );
            return;
          }
          if (!canUseUnrestrictedCommands(aiopsStatus)) {
            setAiopsActionError(
              'Gateway가 실행 무제한 capability를 허용하지 않아 자동 승인 후 실행을 보낼 수 없습니다.',
            );
            return;
          }
          const planId = getRecordName(record);
          const planDigest = getPlanDigest(record);
          if (!planId || !planDigest) {
            throw new Error('Action plan id 또는 digest가 없습니다.');
          }
          const approval = await approveActionPlan(planId, planDigest, 'lab-auto-unrestricted');
          const approvalId = getRecordName(approval);
          if (!approvalId) {
            throw new Error('자동 승인 id가 없습니다.');
          }
          const execution = await executeApprovedAction(approvalId, planId, planDigest);
          const executedApproval = approvalRecordWithExecutedStatus(approval, execution);
          upsertAiopsRuntimeRecords({
            approvalDecisions: [executedApproval],
            executionRecords: [execution],
          });
          setAiopsActionNotice('실행 무제한 모드로 자동 승인 후 실행했습니다.');
          onActionRecordCreated(executedApproval, actionMessageAnchor);
          onActionRecordCreated(execution, actionMessageAnchor);
        }

        if (action.step === 'reject-plan') {
          const planId = getRecordName(record);
          const planDigest = getPlanDigest(record);
          if (!planId || !planDigest) {
            throw new Error('Action plan id 또는 digest가 없습니다.');
          }
          const rejection = await rejectActionPlan(planId, planDigest);
          upsertAiopsRuntimeRecords({ approvalDecisions: [rejection] });
          setAiopsActionNotice('Action plan을 거절 기록했습니다.');
          onActionRecordCreated(rejection, actionMessageAnchor);
        }

        if (action.step === 'execute-approval') {
          const recordPlanDigest = getPlanDigest(record);
          const planDigest = getApprovalPlanDigest(record) || recordPlanDigest;
          const linkedApproval =
            recordPlanDigest && aiopsStatus
              ? aiopsStatus.spec.records.approvalDecisions.find(
                  (item) => getApprovalPlanDigest(item) === recordPlanDigest,
                )
              : undefined;
          const approvalId = getApprovalId(linkedApproval ?? record);
          const plan = findPlanByDigest(
            aiopsStatus?.spec.records.sealedActionPlans ?? [],
            planDigest,
          );
          const planId = plan ? getRecordName(plan) : '';
          if (!approvalId || !planId || !planDigest) {
            throw new Error('Approval 또는 연결된 action plan 정보가 없습니다.');
          }
          const execution = await executeApprovedAction(approvalId, planId, planDigest);
          const executedApproval = approvalRecordWithExecutedStatus(
            linkedApproval ?? record,
            execution,
          );
          upsertAiopsRuntimeRecords({
            approvalDecisions: [executedApproval],
            executionRecords: [execution],
          });
          setAiopsActionNotice(
            isReviewOnlyActionRecord(execution)
              ? '검토 기록을 남겼습니다. 클러스터 변경은 실행하지 않았습니다.'
              : '승인된 조치를 실행했습니다.',
          );
          onActionRecordCreated(executedApproval, actionMessageAnchor);
          onActionRecordCreated(execution, actionMessageAnchor);
        }

        await refreshAiopsRuntimeStatus();
      } catch (error) {
        setAiopsActionError(aiopsActionErrorMessage(error));
      } finally {
        aiopsActionBusyIdRef.current = '';
        setAiopsActionBusyId('');
      }
    },
    [
      aiopsStatus,
      executionMode,
      getLatestAssistantMessageAnchor,
      onActionPlanCreated,
      onActionRecordCreated,
      refreshAiopsRuntimeStatus,
      upsertAiopsRuntimeRecords,
    ],
  );

  const handleCreateActionPlanFromChat = React.useCallback(
    async (candidate: AiopsActionCandidate) => {
      if (candidate.planDisabledReason) {
        setAiopsActionNotice('');
        setAiopsActionError(candidate.planDisabledReason);
        setActionCandidateFeedback({
          candidateId: candidate.id,
          message: candidate.planDisabledReason,
          tone: 'error',
        });
        return;
      }
      if (busyActionCandidateIdRef.current) {
        return;
      }
      busyActionCandidateIdRef.current = candidate.id;
      setBusyActionCandidateId(candidate.id);
      setAiopsActionError('');
      setAiopsActionNotice('');
      setActionCandidateFeedback({
        candidateId: candidate.id,
        message: 'Action Plan 생성 중입니다.',
        tone: 'pending',
      });
      const actionMessageAnchor = getLatestAssistantMessageAnchor();

      try {
        const result = await createActionCandidatePlan(candidate);
        upsertAiopsRuntimeRecords({
          actionProposals: result.spec?.proposal ? [result.spec.proposal] : undefined,
          sealedActionPlans: result.spec?.plan ? [result.spec.plan] : undefined,
        });
        const createdMessage =
          executionMode === 'read-only'
            ? 'Action Plan을 생성했습니다. 읽기 전용 모드에서는 승인·실행 없이 계획 내용만 확인합니다.'
            : 'Action Plan을 생성했습니다. 아래 카드에서 승인 또는 실행을 이어갈 수 있습니다.';
        setAiopsActionNotice(createdMessage);
        setActionCandidateFeedback({
          candidateId: candidate.id,
          message: createdMessage,
          tone: 'success',
        });
        onCandidatePlanCreated(candidate, result.spec?.plan, actionMessageAnchor);
        const refreshedStatus = await refreshAiopsRuntimeStatus();
        const linkedPlanDigest =
          result.spec?.planDigest || (result.spec?.plan ? getPlanDigest(result.spec.plan) : '');
        const highestRecord = highestLifecycleRecordForPlanDigest(
          refreshedStatus,
          linkedPlanDigest,
        );
        if (highestRecord) {
          onActionRecordCreated(highestRecord, actionMessageAnchor);
        }
      } catch (error) {
        const message = aiopsActionErrorMessage(error);
        setAiopsActionError(message);
        setActionCandidateFeedback({
          candidateId: candidate.id,
          message,
          tone: 'error',
        });
      } finally {
        busyActionCandidateIdRef.current = '';
        setBusyActionCandidateId('');
      }
    },
    [
      executionMode,
      getLatestAssistantMessageAnchor,
      onActionRecordCreated,
      onCandidatePlanCreated,
      refreshAiopsRuntimeStatus,
      upsertAiopsRuntimeRecords,
    ],
  );

  return {
    actionCandidateFeedback,
    actionCandidates,
    aiopsActionBusyId,
    aiopsActionError,
    aiopsActionNotice,
    busyActionCandidateId,
    clearActionCandidateFeedback,
    clearActionError,
    handleAiopsAction,
    handleCreateActionPlanFromChat,
    refreshAiopsActionCandidates,
    resetActionActivity,
  };
};
