import * as React from 'react';
import { Button } from '@patternfly/react-core';

import { AssistantInlineActionRecords } from './AssistantActionRecords';
import { CoolSettingsIcon } from './coolicons';
import type { AiopsActionCandidate, AiopsRuntimeStatus } from '../services/aiGateway';
import type {
  AiopsExecutionMode,
  AiopsRecordAction,
  AiopsRecordView,
  ConversationActionRef,
  UiLanguage,
} from './assistant.types';

type AssistantCreateActionPlanButtonsProps = {
  actionFeedback?: {
    candidateId: string;
    message: string;
    tone: 'error' | 'pending' | 'success';
  } | null;
  actionRecordsByCandidateId?: Record<string, AiopsRecordView[]>;
  actionRefsByCandidateId?: Record<string, ConversationActionRef[]>;
  aiopsStatus: AiopsRuntimeStatus | null;
  busyActionId: string;
  busyCandidateId: string;
  candidates: AiopsActionCandidate[];
  createDisabledReason?: string;
  executionMode: AiopsExecutionMode;
  language: UiLanguage;
  onAction: (record: AiopsRecordView, action: AiopsRecordAction) => void;
  onCreatePlan: (candidate: AiopsActionCandidate) => void;
  resolveAction: (
    record: AiopsRecordView,
    aiopsStatus: AiopsRuntimeStatus | null,
    executionMode: AiopsExecutionMode,
  ) => AiopsRecordAction | null;
};

const actionCandidateSummaryLabel = (candidate: AiopsActionCandidate): string => {
  return candidate.title?.trim() || '조치 계획 검토';
};

const actionCandidateStateLabel = (candidate: AiopsActionCandidate): string => {
  if (candidate.statusLabel) {
    return candidate.statusLabel;
  }

  return candidate.approvalRequired ? '승인 필요' : '실행 가능';
};

const actionCandidateBriefStateLabel = (candidate: AiopsActionCandidate): string => {
  const state = actionCandidateStateLabel(candidate);
  const title = actionCandidateSummaryLabel(candidate);
  if (state.trim() !== title.trim()) {
    return state;
  }
  if (candidate.executable === false) {
    return '계획 후보';
  }
  return candidate.approvalRequired ? '승인 필요' : '실행 가능';
};

const actionCandidateTargetLabel = (candidate: AiopsActionCandidate): string => {
  const target = candidate.target;
  if (!target?.name) {
    return '대상 확인 필요';
  }
  if (target.namespace && target.namespace !== target.name) {
    return `${target.namespace}/${target.name}`;
  }
  return target.name;
};

const actionCandidateProblemLabel = (candidate: AiopsActionCandidate): string => {
  if (/deployment_container_command_fix|set_deployment_container_command|command_fix/i.test(candidate.sourceType || '')) {
    return 'command 오류 확인';
  }
  if (/pod_fix_or_rollback_review|fix[-_]?review|rollback/i.test(candidate.sourceType || '')) {
    return '원인 확인 완료';
  }
  if (/namespace_cleanup/i.test(candidate.sourceType || '')) {
    return '정리 후보 검토';
  }
  if (/test_pod_create/i.test(candidate.sourceType || '')) {
    return '테스트 Pod 생성 요청';
  }
  if (/crashloop|restart/i.test(`${candidate.sourceType || ''} ${candidate.sourceFindingId || ''}`)) {
    return '워크로드 이상 징후';
  }
  if (/diagnostic|rca|evidence/i.test(`${candidate.sourceType || ''} ${candidate.sourceFindingId || ''}`)) {
    return '문제 확인 필요';
  }
  return candidate.evidence ? '확인 결과 기반 조치 후보' : '운영 확인 필요';
};

const actionCandidateActionLabel = (candidate: AiopsActionCandidate): string => {
  const actionText = `${candidate.sourceType || ''} ${candidate.sourceFindingId || ''}`;
  if (/deployment_container_command_fix|set_deployment_container_command|command_fix/i.test(actionText)) {
    return 'Deployment command 수정 계획 생성';
  }
  if (/pod_fix_or_rollback_review|fix[-_]?review|rollback/i.test(actionText)) {
    return '수정/롤백 검토 계획 생성';
  }
  if (/pod.*diagnostic|pod_diagnostic|restart.*rca|crashloop/i.test(actionText)) {
    return '로그/describe/Event 확인 계획 생성';
  }
  if (/namespace_cleanup/i.test(actionText)) {
    return '사용 신호 재확인 계획 생성';
  }
  if (/test_pod_create/i.test(actionText)) {
    return '테스트 Pod 생성 계획 작성';
  }
  const firstStep = candidate.recommendationSteps?.[0];
  if (firstStep) {
    return firstStep.replace(/\s*Action Plan\s*생성\s*/gi, '계획 생성');
  }
  if (candidate.planDisabledReason) {
    return '대상 확인 후 계획 생성';
  }
  return candidate.executable === false ? '검토 계획 생성' : '승인 후 실행 준비';
};

const actionCandidateApprovalLabel = (candidate: AiopsActionCandidate): string => {
  const actionText = `${candidate.sourceType || ''} ${candidate.sourceFindingId || ''}`;
  if (/deployment_container_command_fix|set_deployment_container_command|command_fix/i.test(actionText)) {
    return '승인 후 Deployment template patch 실행';
  }
  if (/pod_fix_or_rollback_review|fix[-_]?review|rollback/i.test(actionText)) {
    return '승인 전 클러스터 변경 없음, 수정안만 검토';
  }
  if (/pod.*diagnostic|pod_diagnostic|restart.*rca|crashloop/i.test(actionText)) {
    return candidate.approvalRequired ? '승인 후 읽기 조회만 실행' : '읽기 조회만 실행';
  }
  if (candidate.prerequisiteChecks?.length) {
    return candidate.prerequisiteChecks.slice(0, 2).join(', ');
  }
  return candidate.approvalRequired ? '승인 전 실행 없음' : '실행 전 최종 확인';
};

const actionCandidatePriorityLabel = (candidate: AiopsActionCandidate): string =>
  actionCandidateSummaryLabel(candidate);

const AssistantCreateActionPlanButtons: React.FC<AssistantCreateActionPlanButtonsProps> = ({
  actionFeedback,
  actionRecordsByCandidateId = {},
  actionRefsByCandidateId = {},
  aiopsStatus,
  busyActionId,
  busyCandidateId,
  candidates,
  createDisabledReason,
  executionMode,
  language,
  onAction,
  onCreatePlan,
  resolveAction,
}) => {
  const [expanded, setExpanded] = React.useState(candidates.length <= 1);
  const candidateKey = React.useMemo(
    () => candidates.map((candidate) => candidate.id).join('|'),
    [candidates],
  );
  const candidateActivityKey = React.useMemo(
    () =>
      candidates
        .map((candidate) => {
          const recordCount = actionRecordsByCandidateId[candidate.id]?.length ?? 0;
          const refCount = actionRefsByCandidateId[candidate.id]?.length ?? 0;
          return `${candidate.id}:${recordCount}:${refCount}`;
        })
        .join('|'),
    [actionRecordsByCandidateId, actionRefsByCandidateId, candidates],
  );
  const hasActionActivity = React.useMemo(
    () =>
      candidates.some(
        (candidate) =>
          (actionRecordsByCandidateId[candidate.id]?.length ?? 0) > 0 ||
          (actionRefsByCandidateId[candidate.id]?.length ?? 0) > 0,
      ),
    [actionRecordsByCandidateId, actionRefsByCandidateId, candidates],
  );

  React.useEffect(() => {
    setExpanded(candidates.length <= 1 || hasActionActivity);
  }, [candidateActivityKey, candidateKey, candidates.length, hasActionActivity]);

  if (candidates.length === 0) {
    return null;
  }

  const isKo = language === 'ko';
  const multiple = candidates.length > 1;
  const primaryCandidate = candidates[0];
  const groupId = `aiops-action-candidates-${candidateKey.replace(/[^A-Za-z0-9_-]/g, '-') || 'group'}`;

  return (
    <div
      className={`komsco-ai__create-action-plan${
        multiple ? ' komsco-ai__create-action-plan--grouped' : ''
      }${expanded ? ' is-expanded' : ' is-collapsed'}`}
      data-aiops-action-candidate-count={candidates.length}
      data-aiops-action-candidates-expanded={expanded ? 'true' : 'false'}
    >
      {multiple && (
        <button
          aria-controls={groupId}
          aria-expanded={expanded}
          className="komsco-ai__create-action-plan-summary"
          onClick={() => setExpanded((value) => !value)}
          type="button"
        >
          <span className="komsco-ai__create-action-plan-summary-main">
            <span className="komsco-ai__create-action-plan-summary-head">
              <strong>
                {isKo ? `Action Plan 후보 ${candidates.length}건` : `${candidates.length} Action Plan candidates`}
              </strong>
            </span>
            <span className="komsco-ai__create-action-plan-summary-priority">
              {isKo
                ? `우선 후보: ${actionCandidatePriorityLabel(primaryCandidate)}`
                : `Primary: ${actionCandidatePriorityLabel(primaryCandidate)}`}
            </span>
          </span>
          <span className="komsco-ai__create-action-plan-summary-toggle">
            {expanded ? (isKo ? '접기' : 'Collapse') : isKo ? '펼쳐보기' : 'Show'}
          </span>
        </button>
      )}
      {createDisabledReason && (
        <span className="komsco-ai__create-action-plan-mode-note">
          {isKo
            ? createDisabledReason
            : 'Action Plan candidates are visible in read-only mode. Switch to execution mode to create a plan.'}
        </span>
      )}
      <div
        className="komsco-ai__create-action-plan-list"
        hidden={multiple && !expanded}
        id={groupId}
      >
        {candidates.map((candidate) => {
          const busy = candidate.id === busyCandidateId;
          const disabledReason = candidate.planDisabledReason || createDisabledReason;
          const disabledByMode = Boolean(createDisabledReason) && !candidate.planDisabledReason;
          const feedback =
            actionFeedback?.candidateId === candidate.id ? actionFeedback : null;
          const inlineRecords = actionRecordsByCandidateId[candidate.id] ?? [];
          const inlineRefs = actionRefsByCandidateId[candidate.id] ?? [];
          const hasInlineActivity = inlineRecords.length > 0 || inlineRefs.length > 0;
          return (
            <div
              className={`komsco-ai__create-action-plan-row${
                hasInlineActivity ? ' has-action-activity' : ''
              }`}
              data-aiops-action-candidate-activity={hasInlineActivity ? 'true' : 'false'}
              data-aiops-action-candidate-feedback={feedback?.tone || 'none'}
              key={candidate.id}
            >
              <span className="komsco-ai__create-action-plan-meta">
                <span className="komsco-ai__create-action-plan-card-head">
                  <CoolSettingsIcon className="komsco-ai__create-action-plan-glyph" />
                  <span className="komsco-ai__create-action-plan-copy">
                    <span className="komsco-ai__create-action-plan-eyebrow">
                      {isKo ? 'Action Plan 후보' : 'Action candidate'}
                    </span>
                    <span className="komsco-ai__create-action-plan-title">
                      {isKo ? actionCandidateSummaryLabel(candidate) : 'Approval-gated action candidate'}
                    </span>
                  </span>
                </span>
                <span className="komsco-ai__create-action-plan-brief">
                  <span className="komsco-ai__create-action-plan-property">
                    <strong>{isKo ? '상태:' : 'State:'}</strong>
                    <span>{actionCandidateBriefStateLabel(candidate)}</span>
                  </span>
                  <span className="komsco-ai__create-action-plan-property">
                    <strong>{isKo ? '대상:' : 'Target:'}</strong>
                    <span>{actionCandidateTargetLabel(candidate)}</span>
                  </span>
                  <span className="komsco-ai__create-action-plan-property">
                    <strong>{isKo ? '조치:' : 'Action:'}</strong>
                    <span>{isKo ? actionCandidateActionLabel(candidate) : 'Create approval-ready plan'}</span>
                  </span>
                </span>
                <details className="komsco-ai__create-action-plan-details">
                  <summary>{isKo ? '문제/승인 조건 상세' : 'Issue and approval details'}</summary>
                  <span className="komsco-ai__create-action-plan-detail">
                    <strong>{isKo ? '대상' : 'Target'}</strong>
                    <span>{actionCandidateTargetLabel(candidate)}</span>
                  </span>
                  <span className="komsco-ai__create-action-plan-detail">
                    <strong>{isKo ? '문제' : 'Issue'}</strong>
                    <span>
                      {isKo ? actionCandidateProblemLabel(candidate) : actionCandidateStateLabel(candidate)}
                    </span>
                  </span>
                  <span className="komsco-ai__create-action-plan-detail">
                    <strong>{isKo ? '조치' : 'Action'}</strong>
                    <span>{isKo ? actionCandidateActionLabel(candidate) : 'Create approval-ready plan'}</span>
                  </span>
                  <span className="komsco-ai__create-action-plan-note">
                    <strong>{isKo ? '승인 조건' : 'Approval'}</strong>
                    <span>{isKo ? actionCandidateApprovalLabel(candidate) : 'No change before approval'}</span>
                  </span>
                </details>
                {candidate.planDisabledReason && (
                  <span className="komsco-ai__create-action-plan-disabled-reason">
                    {isKo
                      ? candidate.planDisabledReason
                      : 'A target resource is required before creating a plan.'}
                  </span>
                )}
                {feedback && (
                  <span className={`komsco-ai__create-action-plan-feedback is-${feedback.tone}`}>
                    {feedback.message}
                  </span>
                )}
                {hasInlineActivity && (
                  <AssistantInlineActionRecords
                    aiopsStatus={aiopsStatus}
                    busyActionId={busyActionId}
                    executionMode={executionMode}
                    fallbackRefs={inlineRefs}
                    language={language}
                    onAction={onAction}
                    records={inlineRecords}
                    resolveAction={resolveAction}
                  />
                )}
              </span>
              {!hasInlineActivity && (
                <Button
                  className="komsco-ai__action-button komsco-ai__create-action-plan-button"
                  data-aiops-action-candidate-locked={disabledByMode ? 'readonly' : disabledReason ? 'target' : 'none'}
                  isDisabled={busy || Boolean(disabledReason)}
                  isLoading={busy}
                  onClick={() => {
                    if (!disabledReason) {
                      onCreatePlan(candidate);
                    }
                  }}
                  size="sm"
                  variant="secondary"
                  aria-label={disabledReason || 'Action Plan 생성'}
                >
                  {busy
                    ? isKo
                      ? '생성 중'
                      : 'Creating'
                    : disabledReason
                      ? isKo
                        ? disabledByMode
                          ? '생성 잠김'
                          : '대상 확인 필요'
                        : disabledByMode
                          ? 'Locked'
                          : 'Target required'
                      : isKo
                        ? 'Action Plan 생성'
                        : 'Create Action Plan'}
                </Button>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};

export default AssistantCreateActionPlanButtons;
