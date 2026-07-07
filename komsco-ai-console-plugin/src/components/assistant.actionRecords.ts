import type { AiopsRuntimeStatus } from '../services/aiGateway';
import {
  ACTION_POLICY_LABELS,
  ACTION_POLICY_LABELS_EN,
  RISK_LABEL_KO,
} from './assistant.constants';
import type {
  AiopsExecutionMode,
  AiopsLifecycleStage,
  AiopsRecordView,
  ConversationActionRef,
  ExecutionOutcomeSummary,
  PlanSummary,
  UiLanguage,
} from './assistant.types';

export const getRecordSpecMap = (record: AiopsRecordView): Record<string, unknown> =>
  record.spec && typeof record.spec === 'object' ? record.spec : {};

export const asObjectMap = (value: unknown): Record<string, unknown> | undefined =>
  value && typeof value === 'object' ? (value as Record<string, unknown>) : undefined;

export const getRecordName = (record: AiopsRecordView): string => record.metadata?.name ?? '';

export const getSealedActionPlan = (
  record: AiopsRecordView,
): Record<string, unknown> | undefined => asObjectMap(getRecordSpecMap(record).sealedActionPlan);

const titleCaseToolName = (toolName: string): string =>
  toolName
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (letter) => letter.toUpperCase());

const ACTION_RECORD_KIND_LABELS_KO: Record<string, string> = {
  ActionProposalRecord: '조치 후보',
  ApprovalDecisionRecord: '승인 결정',
  ExecutionRecord: '실행 기록',
  SealedActionPlanRecord: 'Action Plan',
};

const ACTION_RECORD_KIND_LABELS_EN: Record<string, string> = {
  ActionProposalRecord: 'Action candidate',
  ApprovalDecisionRecord: 'Approval decision',
  ExecutionRecord: 'Execution record',
  SealedActionPlanRecord: 'Action Plan',
};

export const getActionToolLabel = (
  toolName: string | undefined,
  language: UiLanguage = 'ko',
): string => {
  const normalizedToolName = String(toolName || '').trim();
  if (language === 'en') {
    return (
      ACTION_RECORD_KIND_LABELS_EN[normalizedToolName] ??
      ACTION_POLICY_LABELS_EN[normalizedToolName] ??
      (normalizedToolName ? titleCaseToolName(normalizedToolName) : 'Action')
    );
  }

  return (
    ACTION_RECORD_KIND_LABELS_KO[normalizedToolName] ??
    ACTION_POLICY_LABELS[normalizedToolName] ??
    (normalizedToolName ? titleCaseToolName(normalizedToolName) : '조치')
  );
};

export const getActionRecordToolLabel = (
  record: AiopsRecordView,
  language: UiLanguage = 'ko',
): string => {
  return getActionToolLabel(getActionRecordToolName(record), language);
};

export const getPlanSummary = (
  record: AiopsRecordView,
  language: UiLanguage = 'ko',
): PlanSummary | null => {
  const plan = getSealedActionPlan(record);
  if (!plan) {
    return null;
  }

  const action = asObjectMap(plan.action);
  const safety = asObjectMap(plan.safety);
  const toolName = typeof action?.toolName === 'string' ? action.toolName : '';
  const risk = typeof safety?.risk === 'string' ? safety.risk : '';
  const riskInfo = RISK_LABEL_KO[risk] ?? { label: risk || '알 수 없음', tone: 'neutral' as const };

  return {
    risk,
    riskLabel: riskInfo.label,
    riskTone: riskInfo.tone,
    rollbackDescription:
      typeof safety?.rollbackDescription === 'string' ? safety.rollbackDescription : '',
    rollbackPossible: safety?.rollbackPossible === true,
    toolLabel:
      language === 'en'
        ? ACTION_POLICY_LABELS_EN[toolName] ?? titleCaseToolName(toolName || 'Action')
        : ACTION_POLICY_LABELS[toolName] ?? (toolName || '알 수 없는 정책'),
  };
};

export const getPlanDigest = (record: AiopsRecordView): string => {
  const plan = getSealedActionPlan(record);
  const digest = asObjectMap(plan?.digest);

  return typeof digest?.planDigest === 'string' ? digest.planDigest : '';
};

export const getApprovalDecision = (
  record: AiopsRecordView,
): Record<string, unknown> | undefined => asObjectMap(getRecordSpecMap(record).approvalDecision);

export const getApprovalId = (record: AiopsRecordView): string => {
  const decision = getApprovalDecision(record);

  return typeof decision?.approvalId === 'string' ? decision.approvalId : getRecordName(record);
};

export const getApprovalPlanDigest = (record: AiopsRecordView): string => {
  const decision = getApprovalDecision(record);

  return typeof decision?.planDigest === 'string' ? decision.planDigest : '';
};

export const findPlanByDigest = (
  plans: AiopsRecordView[],
  planDigest: string,
): AiopsRecordView | undefined => plans.find((plan) => getPlanDigest(plan) === planDigest);

export const hasApprovalForPlan = (approvals: AiopsRecordView[], planDigest: string): boolean =>
  approvals.some((record) => {
    const decision = getApprovalDecision(record);
    const status = String(decision?.status ?? '');

    return (
      decision?.planDigest === planDigest && ['approved', 'executed', 'rejected'].includes(status)
    );
  });

export const findApprovalForPlan = (
  approvals: AiopsRecordView[],
  planDigest: string,
  statuses: string[] = ['approved', 'executed', 'rejected'],
): AiopsRecordView | undefined =>
  approvals.find((record) => {
    const decision = getApprovalDecision(record);
    const status = String(decision?.status ?? '');

    return decision?.planDigest === planDigest && statuses.includes(status);
  });

export const hasExecutionForApproval = (
  executions: AiopsRecordView[],
  approvalId: string,
): boolean => executions.some((record) => getRecordSpecMap(record).approvalId === approvalId);

export const findExecutionForApproval = (
  executions: AiopsRecordView[],
  approvalId: string,
): AiopsRecordView | undefined =>
  executions.find((record) => getRecordSpecMap(record).approvalId === approvalId);

// evict_one_unhealthy_controller_owned_pod verification only checks the target
// immediately after the mutation call, before the controller has necessarily
// finished recreating the pod yet. A fresh "still present" read can therefore
// be transient noise for the first few seconds after execution.
const REMEDIATION_REASON_LABEL_KO: Record<string, string> = {
  target_pod_removed: '대상 Pod가 클러스터에서 제거되었습니다.',
  target_pod_deleting: '대상 Pod가 종료 처리 중입니다. 컨트롤러가 곧 새로 만듭니다.',
  target_pod_replaced: '컨트롤러가 대상 Pod를 새로 재생성했습니다.',
  target_pod_still_present:
    '조치를 실행했지만 대상 Pod가 아직 그대로입니다. 잠시 후 다시 확인해 주세요.',
  restart_annotation_observed: '배포에 재시작 요청이 반영되었습니다.',
  restart_annotation_not_observed: '재시작 반영이 아직 확인되지 않았습니다.',
  scale_spec_matches: '레플리카 수 변경이 반영되었습니다.',
  scale_spec_mismatch: '레플리카 수 변경이 아직 반영되지 않았습니다.',
  rollback_template_annotation_observed: '이전 리비전으로 롤백이 반영되었습니다.',
  rollback_annotation_not_observed: '롤백 반영이 아직 확인되지 않았습니다.',
  hpa_bounds_match: 'HPA 범위 변경이 반영되었습니다.',
  hpa_bounds_mismatch: 'HPA 범위 변경이 아직 반영되지 않았습니다.',
  no_postcondition_for_tool:
    '조치는 실행되었지만 이 조치 유형은 자동 확인을 지원하지 않습니다. 클러스터에서 직접 확인해 주세요.',
  target_resource_unavailable: '대상 리소스를 다시 조회하지 못해 결과를 확인하지 못했습니다.',
};

const REVIEW_ONLY_ACTION_TOOLS = new Set([
  'namespace_cleanup_review',
  'pod_diagnostic_review',
  'test_pod_create_review',
]);

export const isReviewOnlyToolName = (toolName: string | undefined): boolean =>
  REVIEW_ONLY_ACTION_TOOLS.has(String(toolName || '').trim());

export const isReviewOnlyActionRecord = (record: AiopsRecordView): boolean => {
  const spec = getRecordSpecMap(record);
  const executorTrace = asObjectMap(spec.executorTrace);
  if (executorTrace?.reviewOnly === true) {
    return true;
  }

  const plan = getSealedActionPlan(record);
  const decision = getApprovalDecision(record);
  const candidate = asObjectMap(spec.candidateActionRequest);
  const action =
    asObjectMap(plan?.action) ?? asObjectMap(decision?.action) ?? asObjectMap(candidate?.action);
  const toolName =
    (typeof action?.toolName === 'string' ? action.toolName : '') ||
    (typeof executorTrace?.toolName === 'string' ? executorTrace.toolName : '');

  return isReviewOnlyToolName(toolName);
};

const reviewOnlyExecutionDetail = (toolName: string, reason: string): string => {
  const text = `${toolName} ${reason}`.toLowerCase();
  if (/namespace.*cleanup|namespace_cleanup/.test(text)) {
    return 'Namespace 정리 검토가 실행 기록으로 남았습니다. 실제 namespace 삭제는 실행하지 않았습니다.';
  }
  if (/test.*pod.*creation|test_pod_create/.test(text)) {
    return '테스트 Pod 생성 검토가 실행 기록으로 남았습니다. 실제 Pod 생성은 실행하지 않았습니다.';
  }
  if (/pod.*diagnostic|pod_diagnostic|diagnostic/.test(text)) {
    return 'Pod 진단 검토가 실행 기록으로 남았습니다. Pod 삭제나 재시작은 실행하지 않았습니다.';
  }
  return '검토 실행 기록이 남았습니다. 클러스터 변경은 실행하지 않았습니다.';
};

export const getExecutionOutcomeSummary = (
  record: AiopsRecordView,
  aiopsStatus: AiopsRuntimeStatus | null,
): ExecutionOutcomeSummary | null => {
  const decision = getApprovalDecision(record);
  const directSpec = getRecordSpecMap(record);
  const directExecutionRecord =
    !decision &&
    (record.kind === 'ExecutionRecord' || Boolean(directSpec.mutationOutcome) || Boolean(directSpec.approvalId));

  if (!decision && !directExecutionRecord) {
    return null;
  }

  const approvalId = decision ? getApprovalId(record) : '';
  const executions = aiopsStatus?.spec.records.executionRecords ?? [];
  const execution = directExecutionRecord ? record : findExecutionForApproval(executions, approvalId);
  if (!execution) {
    return null;
  }

  const executionSpec = getRecordSpecMap(execution);
  const executorTrace = asObjectMap(executionSpec.executorTrace);
  const isAutoPolicy =
    decision?.decidedBy === 'auto-policy' || executionSpec.decidedBy === 'auto-policy';
  const decisionAction = asObjectMap(decision?.action);
  const toolName = typeof decisionAction?.toolName === 'string' ? decisionAction.toolName : '';
  const executionToolName =
    toolName || (typeof executorTrace?.toolName === 'string' ? executorTrace.toolName : '');
  const mutationOutcome = asObjectMap(executionSpec.mutationOutcome);
  const remediationOutcome = asObjectMap(executionSpec.remediationOutcome);
  const mutationStatus = typeof mutationOutcome?.status === 'string' ? mutationOutcome.status : '';
  const remediationStatus =
    typeof remediationOutcome?.status === 'string' ? remediationOutcome.status : '';
  const remediationReason =
    typeof remediationOutcome?.reason === 'string' ? remediationOutcome.reason : '';
  const reviewOnly = executorTrace?.reviewOnly === true;

  const title = reviewOnly
    ? '검토 기록이 남았습니다.'
    : isAutoPolicy
    ? toolName
      ? `자동으로 조치를 실행했습니다 (정책: ${toolName})`
      : '자동으로 조치를 실행했습니다.'
    : '조치를 실행했습니다.';

  if (mutationStatus === 'mutation_failed') {
    return {
      tone: 'danger',
      title,
      detail: '실행 요청이 실패했습니다. 다시 시도하거나 직접 확인해 주세요.',
    };
  }
  if (mutationStatus === 'mutation_disabled') {
    return {
      tone: 'warn',
      title,
      detail: '실행 기능이 비활성화되어 있어 실제 클러스터에는 반영되지 않았습니다.',
    };
  }

  if (remediationStatus === 'verified') {
    return {
      tone: 'ok',
      title,
      detail:
        (reviewOnly ? reviewOnlyExecutionDetail(executionToolName, remediationReason) : '') ||
        REMEDIATION_REASON_LABEL_KO[remediationReason] ||
        '문제 해결이 확인되었습니다.',
    };
  }
  if (remediationStatus === 'verification_failed') {
    return {
      tone: 'warn',
      title,
      detail:
        (reviewOnly ? reviewOnlyExecutionDetail(executionToolName, remediationReason) : '') ||
        REMEDIATION_REASON_LABEL_KO[remediationReason] ||
        '실행은 됐지만 해결 여부가 아직 확인되지 않았습니다.',
    };
  }

  return {
    tone: 'warn',
    title,
    detail:
      (reviewOnly ? reviewOnlyExecutionDetail(executionToolName, remediationReason) : '') ||
      REMEDIATION_REASON_LABEL_KO[remediationReason] ||
      '실행은 됐지만 이 조치 유형은 자동 확인을 지원하지 않습니다. 클러스터에서 직접 확인해 주세요.',
  };
};

export const getRecordPhase = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  const status = spec.status;
  if (status && typeof status === 'object' && 'phase' in status) {
    return String((status as Record<string, unknown>).phase ?? 'unknown');
  }
  const decision = spec.approvalDecision;
  if (decision && typeof decision === 'object' && 'status' in decision) {
    return String((decision as Record<string, unknown>).status ?? 'unknown');
  }
  const mutationOutcome = spec.mutationOutcome;
  if (mutationOutcome && typeof mutationOutcome === 'object' && 'status' in mutationOutcome) {
    return String((mutationOutcome as Record<string, unknown>).status ?? 'unknown');
  }
  return 'recorded';
};

export const getRecordTargetLabel = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  const directTarget = spec.target;
  const candidate = spec.candidate;
  const candidateActionRequest = spec.candidateActionRequest;
  const sealedActionPlan = spec.sealedActionPlan;
  const approvalDecision = spec.approvalDecision;
  const executorTrace = spec.executorTrace;
  const target =
    directTarget && typeof directTarget === 'object'
      ? directTarget
      : candidate && typeof candidate === 'object'
        ? (candidate as Record<string, unknown>).targetNode
        : candidateActionRequest && typeof candidateActionRequest === 'object'
          ? (candidateActionRequest as Record<string, unknown>).target
          : sealedActionPlan && typeof sealedActionPlan === 'object'
          ? (sealedActionPlan as Record<string, unknown>).target
          : approvalDecision && typeof approvalDecision === 'object'
            ? (approvalDecision as Record<string, unknown>).target
            : executorTrace && typeof executorTrace === 'object'
              ? (executorTrace as Record<string, unknown>).target
              : undefined;

  if (!target || typeof target !== 'object') {
    return record.metadata?.name ?? 'unknown';
  }

  const map = target as Record<string, unknown>;
  const namespace = map.namespace ? `${String(map.namespace)}/` : '';
  return `${namespace}${String(map.name ?? record.metadata?.name ?? 'unknown')}`;
};

export const getActionRecordToolName = (record: AiopsRecordView): string => {
  const spec = getRecordSpecMap(record);
  const candidateActionRequest = asObjectMap(spec.candidateActionRequest);
  const candidateAction = asObjectMap(candidateActionRequest?.action);
  const sealedActionPlan = asObjectMap(spec.sealedActionPlan);
  const sealedAction = asObjectMap(sealedActionPlan?.action);
  const approvalDecision = asObjectMap(spec.approvalDecision);
  const approvalAction = asObjectMap(approvalDecision?.action);
  const executorTrace = asObjectMap(spec.executorTrace);
  const toolName =
    candidateAction?.toolName ??
    sealedAction?.toolName ??
    approvalAction?.toolName ??
    executorTrace?.toolName ??
    spec.action ??
    record.kind ??
    'action';

  return String(toolName || 'action');
};

export const ACTION_STAGE_RANK: Record<AiopsLifecycleStage, number> = {
  approval: 3,
  execution: 4,
  plan: 2,
  proposal: 1,
};

export const actionRecordCreatedAt = (record: AiopsRecordView): number =>
  new Date(String(record.metadata?.createdAt ?? 0)).getTime() || 0;

export const actionRecordDedupeKey = (record: AiopsRecordView): string =>
  [
    getRecordTargetLabel(record).trim().toLowerCase(),
    getActionRecordToolName(record).trim().toLowerCase(),
  ].join('|');

export const getPhaseTone = (
  phase: string,
): 'ok' | 'warn' | 'danger' | 'review' | 'neutral' => {
  if (/verified|succeeded|completed|executed|approved|submitted|review_recorded/.test(phase)) {
    return 'ok';
  }
  if (/failed|denied|expired|disabled|mismatch|stale/.test(phase)) {
    return 'danger';
  }
  if (/waiting|pending|proposed|sealed|review/.test(phase)) {
    return 'review';
  }
  return 'neutral';
};

const PHASE_LABEL_KO: Record<string, string> = {
  approved: '승인됨',
  completed: '완료',
  denied: '거부됨',
  disabled: '비활성',
  executed: '실행됨',
  expired: '만료됨',
  failed: '실패',
  mismatch: '불일치',
  mutation_disabled: '실행 비활성',
  mutation_failed: '실행 실패',
  mutation_succeeded: '실행 완료',
  review_recorded: '검토 기록 완료',
  pending: '대기 중',
  proposed: '제안됨',
  rejected: '거절됨',
  sealed: '승인 대기',
  stale: '오래됨',
  submitted: '제출됨',
  succeeded: '성공',
  verified: '확인됨',
  waiting: '대기 중',
};

export const phaseLabelKo = (phase: string): string => PHASE_LABEL_KO[phase] || phase;

const PHASE_LABEL_EN: Record<string, string> = {
  approved: 'Approved',
  completed: 'Completed',
  denied: 'Denied',
  disabled: 'Disabled',
  executed: 'Executed',
  expired: 'Expired',
  failed: 'Failed',
  mismatch: 'Mismatch',
  mutation_disabled: 'Execution disabled',
  mutation_failed: 'Execution failed',
  mutation_succeeded: 'Execution complete',
  review_recorded: 'Review recorded',
  pending: 'Pending',
  proposed: 'Proposed',
  rejected: 'Rejected',
  sealed: 'Approval pending',
  stale: 'Stale',
  submitted: 'Submitted',
  succeeded: 'Succeeded',
  verified: 'Verified',
  waiting: 'Waiting',
};

export const phaseLabel = (phase: string, language: UiLanguage = 'ko'): string =>
  language === 'ko' ? phaseLabelKo(phase) : PHASE_LABEL_EN[phase] || phase;

export const getActionRecordStage = (record: AiopsRecordView): AiopsLifecycleStage => {
  const spec = getRecordSpecMap(record);
  const kind = record.kind ?? '';
  if (kind === 'ExecutionRecord' || spec.mutationOutcome || spec.approvalId) {
    return 'execution';
  }
  if (kind === 'ApprovalDecisionRecord' || spec.approvalDecision) {
    return 'approval';
  }
  if (kind === 'SealedActionPlanRecord' || spec.sealedActionPlan) {
    return 'plan';
  }
  return 'proposal';
};

export const getActionRecordStageLabel = (
  record: AiopsRecordView,
  executionMode?: AiopsExecutionMode,
  language: UiLanguage = 'ko',
): string => {
  const isKo = language === 'ko';
  const stage = getActionRecordStage(record);
  if (stage === 'execution') {
    if (isReviewOnlyActionRecord(record)) {
      return isKo ? '4단계 · 검토 기록 완료' : 'Step 4 · Review recorded';
    }
    return isKo ? '4단계 · 실행 완료' : 'Step 4 · Executed';
  }
  if (stage === 'approval') {
    if (isReviewOnlyActionRecord(record)) {
      return isKo ? '3단계 · 기록 대기' : 'Step 3 · Waiting to record';
    }
    return isKo ? '3단계 · 실행 대기' : 'Step 3 · Waiting to execute';
  }
  if (stage === 'plan') {
    if (executionMode === 'unrestricted') {
      return isKo ? '2단계 · 실행 가능' : 'Step 2 · Ready to execute';
    }
    return isKo ? '2단계 · 승인 필요' : 'Step 2 · Approval required';
  }
  return isKo ? '1단계 · 후보 접수' : 'Step 1 · Candidate received';
};

export const actionAnchorForMessageIndex = (messageIndex: number): string =>
  `assistant-message-${messageIndex}`;

export const actionRefIdFromRecord = (record: AiopsRecordView): string =>
  [
    getRecordName(record) || record.kind || 'record',
    getPlanDigest(record) ||
      getApprovalPlanDigest(record) ||
      (typeof getRecordSpecMap(record).planDigest === 'string'
        ? getRecordSpecMap(record).planDigest
        : '') ||
      getRecordPhase(record),
    getRecordTargetLabel(record),
    getActionRecordToolName(record),
  ]
    .join('|')
    .toLowerCase();

export const conversationActionRefFromRecord = (
  record: AiopsRecordView,
  executionMode: AiopsExecutionMode,
  messageAnchor?: string,
): ConversationActionRef => ({
  createdAt: record.metadata?.createdAt,
  id: actionRefIdFromRecord(record),
  label: getActionRecordStageLabel(record, executionMode),
  messageAnchor,
  planDigest:
    getPlanDigest(record) ||
    getApprovalPlanDigest(record) ||
    (typeof getRecordSpecMap(record).planDigest === 'string'
      ? String(getRecordSpecMap(record).planDigest)
      : undefined),
  recordKind: record.kind,
  recordName: getRecordName(record) || undefined,
  reviewOnly: isReviewOnlyActionRecord(record) || undefined,
  stage: getActionRecordStage(record),
  targetKey: getRecordTargetLabel(record),
  toolName: getActionRecordToolName(record),
  updatedAt: Date.now(),
});

export const getActionRecordProof = (
  record: AiopsRecordView,
  executionMode?: AiopsExecutionMode,
  language: UiLanguage = 'ko',
): string => {
  const isKo = language === 'ko';
  const spec = getRecordSpecMap(record);
  const planDigest = getPlanDigest(record);
  const approvalPlanDigest = getApprovalPlanDigest(record);

  if (planDigest) {
    if (isReviewOnlyActionRecord(record)) {
      return isKo
        ? '검토 계획이 만들어졌습니다. 승인하면 클러스터 변경 없이 검토 기록을 남길 수 있습니다.'
        : 'The review plan is ready. Approval records the review without changing the cluster.';
    }
    if (executionMode === 'unrestricted') {
      return isKo
        ? '조치 계획이 만들어졌습니다. 실행하면 자동 승인 후 클러스터에 적용됩니다.'
        : 'The action plan is ready. Execution will auto-approve and apply it to the cluster.';
    }
    return isKo
      ? '조치 계획이 만들어졌습니다. 승인하면 실행할 수 있습니다.'
      : 'The action plan is ready. It can run after approval.';
  }
  if (approvalPlanDigest) {
    const decision = getApprovalDecision(record);
    const status = String(decision?.status ?? 'unknown');
    if (status === 'rejected') {
      return isKo ? '이 조치는 거절되었습니다.' : 'This action was rejected.';
    }
    if (status === 'approved') {
      if (isReviewOnlyActionRecord(record)) {
        return isKo
          ? '승인이 완료됐습니다. 기록 버튼을 누르면 클러스터 변경 없이 검토 결과를 남깁니다.'
          : 'Approval is complete. Use Record to save the review without changing the cluster.';
      }
      return isKo
        ? '승인이 완료됐습니다. 실행 버튼을 누르면 클러스터에 적용됩니다.'
        : 'Approval is complete. Use Execute to apply it to the cluster.';
    }
    if (status === 'executed') {
      if (isReviewOnlyActionRecord(record)) {
        return isKo
          ? '승인된 검토 결과가 감사 기록으로 남았습니다.'
          : 'The approved review has been recorded in the audit trail.';
      }
      return isKo
        ? '승인된 조치가 실행 완료되었습니다.'
        : 'The approved action has been executed.';
    }
    return isKo
      ? `승인 상태: ${phaseLabel(status, language)}`
      : `Approval status: ${phaseLabel(status, language)}`;
  }
  if (typeof spec.approvalId === 'string') {
    if (isReviewOnlyActionRecord(record)) {
      return isKo
        ? '검토 결과가 감사 기록으로 남았습니다. 클러스터 변경은 실행하지 않았습니다.'
        : 'The review result was recorded in the audit trail. No cluster change was executed.';
    }
    return isKo ? '조치가 실행 처리되었습니다.' : 'The action was processed for execution.';
  }
  return isKo
    ? '조치 후보가 접수됐습니다. 계획을 만들면 다음 단계로 진행됩니다.'
    : 'The action candidate was received. Create a plan to move to the next step.';
};
