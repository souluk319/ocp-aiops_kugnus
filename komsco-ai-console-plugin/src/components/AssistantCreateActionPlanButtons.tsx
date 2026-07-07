import * as React from 'react';
import { Button } from '@patternfly/react-core';

import type { AiopsActionCandidate } from '../services/aiGateway';
import type { UiLanguage } from './assistant.types';

type AssistantCreateActionPlanButtonsProps = {
  busyCandidateId: string;
  candidates: AiopsActionCandidate[];
  language: UiLanguage;
  onCreatePlan: (candidate: AiopsActionCandidate) => void;
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
  if (candidate.prerequisiteChecks?.length) {
    return candidate.prerequisiteChecks.slice(0, 2).join(', ');
  }
  return candidate.approvalRequired ? '승인 전 실행 없음' : '실행 전 최종 확인';
};

const actionCandidatePriorityLabel = (candidate: AiopsActionCandidate): string =>
  actionCandidateSummaryLabel(candidate);

const AssistantCreateActionPlanButtons: React.FC<AssistantCreateActionPlanButtonsProps> = ({
  busyCandidateId,
  candidates,
  language,
  onCreatePlan,
}) => {
  const [expanded, setExpanded] = React.useState(candidates.length <= 1);
  const candidateKey = React.useMemo(
    () => candidates.map((candidate) => candidate.id).join('|'),
    [candidates],
  );

  React.useEffect(() => {
    setExpanded(candidates.length <= 1);
  }, [candidateKey, candidates.length]);

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
            <strong>{isKo ? `Action Plan 후보 ${candidates.length}건` : `${candidates.length} Action Plan candidates`}</strong>
            <span>
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
      <div
        className="komsco-ai__create-action-plan-list"
        hidden={multiple && !expanded}
        id={groupId}
      >
	        {candidates.map((candidate) => {
	          const busy = candidate.id === busyCandidateId;
	          const disabledReason = candidate.planDisabledReason;
	          return (
	            <div className="komsco-ai__create-action-plan-row" key={candidate.id}>
	              <span className="komsco-ai__create-action-plan-meta">
                <span className="komsco-ai__create-action-plan-eyebrow">
                  {isKo ? 'Action Plan 후보' : 'Action candidate'}
                </span>
                <span className="komsco-ai__create-action-plan-title">
                  {isKo ? actionCandidateSummaryLabel(candidate) : 'Approval-gated action candidate'}
                </span>
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
	                {disabledReason && (
	                  <span className="komsco-ai__create-action-plan-disabled-reason">
	                    {isKo ? disabledReason : 'A target resource is required before creating a plan.'}
	                  </span>
	                )}
	              </span>
	              <Button
	                className="komsco-ai__action-button komsco-ai__create-action-plan-button"
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
	                      ? '대상 확인 필요'
	                      : 'Target required'
	                    : isKo
	                      ? 'Action Plan 생성'
	                      : 'Create Action Plan'}
	              </Button>
	            </div>
	          );
        })}
      </div>
    </div>
  );
};

export default AssistantCreateActionPlanButtons;
